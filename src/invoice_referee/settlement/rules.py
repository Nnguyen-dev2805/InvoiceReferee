"""Settlement rule engine (W02): deterministic B7/B7 checks, money and routing.

Responsibility split (System §S1): the reader only proposes observations and
relations; this module validates them, computes components and decides
statuses/issues. It never fabricates values: unknown stays ``None``, nothing
is clipped to budget, and no approval/receipt is implied.

Fact-key vocabulary consumed by the engine (produced by any compliant reader):

- ``expense.<id>.amount``      — claim gross, strict integer VND
- ``expense.<id>.purpose``     — BUSINESS | PERSONAL | UNKNOWN
- ``payment.<id>.amount``      — gross of a payment event, strict integer VND
- ``payment.<id>.payer``       — EMPLOYEE | COMPANY
- ``payment.<id>.status``      — RECEIVED | PENDING | FAILED
- ``history.advance.received`` / ``history.advance.returned``        — A / RA
- ``history.reimbursement.received`` / ``history.reimbursement.returned`` — P / RP
- ``budget.approved``          — B, the approved work budget
- B3 only: ``advance.request.amount``, ``forecast.employee``

Relation kinds: ``EXPENSE_PAYMENT`` (expense→payment, optional
``portion_vnd``; None means the whole payment settles that part) and
``SAME_EVENT`` (payment→payment dedup, one event counted once).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    CheckResult,
    ComponentSlot,
    ConditionalResult,
    ExpenseRow,
    Issue,
    MoneyComponents,
    Observation,
    Relation,
    Report,
    ReportComponents,
    RunInput,
)

_MONEY_KEYS_SUFFIXES = (
    ".amount", ".received", ".returned", "budget.approved",
    "advance.request.amount", "forecast.employee",
)

def calculate_net(components: MoneyComponents) -> int | None:
    """S = E - (A - RA) - (P - RP); any unknown component keeps the result None."""
    values = (components.e, components.a, components.ra, components.p, components.rp)
    if any(value is None for value in values):
        return None
    return components.e - (components.a - components.ra) - (components.p - components.rp)


# --- input validation (SYS-02: reject before aggregation) -------------------

def _validate_money(value: Any, key: str, fact_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainError(
            "INVALID_MONEY",
            f"Trường tiền {key} (fact {fact_id}) phải là integer VND, không bool/float/chuỗi.",
        )
    return value


def _validate_observations(observations: list[Observation]) -> None:
    """Reject duplicate IDs and non-integer money before any aggregation."""
    seen: set[str] = set()
    for observation in observations:
        if observation.fact_id in seen:
            raise DomainError(
                "DUPLICATE_FACT_ID",
                f"Fact ID trùng {observation.fact_id}; không ghi đè âm thầm.",
            )
        seen.add(observation.fact_id)
        if observation.read_state != "READ":
            continue
        if any(observation.key.endswith(suffix) or observation.key == suffix
                for suffix in _MONEY_KEYS_SUFFIXES):
            _validate_money(observation.value, observation.key, observation.fact_id)


def _by_key(observations: list[Observation]) -> dict[str, list[Observation]]:
    grouped: dict[str, list[Observation]] = {}
    for observation in observations:
        if observation.read_state != "READ":
            continue
        grouped.setdefault(observation.key, []).append(observation)
    return grouped


def _first(grouped: dict[str, list[Observation]], key: str) -> Observation | None:
    entries = grouped.get(key) or []
    return entries[0] if entries else None


def _validate_relations(relations: list[Relation],
                       expense_ids: set[str], payment_ids: set[str]) -> None:
    seen: set[str] = set()
    known = expense_ids | payment_ids
    for relation in relations:
        if relation.relation_id in seen:
            raise DomainError(
                "DUPLICATE_RELATION_ID",
                f"Relation ID trùng {relation.relation_id}; không ghi đè âm thầm.",
            )
        seen.add(relation.relation_id)
        for ref in (relation.from_id, relation.to_id):
            if relation.kind == "EXPENSE_PAYMENT":
                if relation.from_id not in expense_ids or relation.to_id not in payment_ids:
                    raise DomainError(
                        "UNKNOWN_REF",
                        f"Relation {relation.relation_id} tham chiếu đối tượng không có trong facts ({ref}).",
                    )
            elif relation.from_id not in known or relation.to_id not in known:
                raise DomainError(
                    "UNKNOWN_REF",
                    f"Relation {relation.relation_id} tham chiếu đối tượng không có trong facts ({ref}).",
                )
        if relation.portion_vnd is not None:
            _validate_money(relation.portion_vnd, f"relation.{relation.relation_id}",
                            relation.relation_id)


# --- B7 ----------------------------------------------------------------------

def _dedup_payments(payments: dict[str, dict[str, Any]],
                    relations: list[Relation], issues: list[Issue],
                    checks: list[CheckResult]) -> dict[str, str]:
    """Return payment_id -> canonical event id; one event counts once."""
    parent = {payment_id: payment_id for payment_id in payments}
    contradictions: list[str] = []
    for relation in sorted((r for r in relations if r.kind == "SAME_EVENT"),
                           key=lambda r: r.relation_id):
        first, second = relation.from_id, relation.to_id
        if first not in payments or second not in payments:
            continue
        root_first = parent[first]
        while parent[root_first] != root_first:
            root_first = parent[root_first]
        root_second = parent[second]
        while parent[root_second] != root_second:
            root_second = parent[root_second]
        if root_first != root_second:
            parent[root_second] = root_first
        if payments[first]["amount"] != payments[second]["amount"]:
            contradictions.append(relation.relation_id)
    canonical: dict[str, str] = {}
    for payment_id in payments:
        root = payment_id
        while parent[root] != root:
            root = parent[root]
        canonical[payment_id] = root
    if contradictions:
        issues.append(Issue(
            issue_id="I-DUP", type="MONEY_INCIDENT", owner="ACCOUNTANT",
            message="Hai bản ghi được ghép cùng sự kiện nhưng số tiền khác nhau; giữ cả hai và làm rõ.",
            refs=contradictions, blocked="money",
        ))
        checks.append(CheckResult(rule="duplicate_events", status="FAIL",
                                  refs=contradictions,
                                  reason="Cùng event nhưng amount khác nhau."))
    else:
        checks.append(CheckResult(
            rule="duplicate_events", status="PASS",
            refs=sorted({r.relation_id for r in relations if r.kind == "SAME_EVENT"}),
            reason="Không có mâu thuẫn same-event."))
    return canonical


def _evaluate_b7(run_input: RunInput, observations: list[Observation],
                 relations: list[Relation], run_id: str, mode: str) -> Report:
    grouped = _by_key(observations)
    all_obs = [o for entries in grouped.values() for o in entries]
    _validate_observations(observations)  # SYS-02: reject before aggregation

    expenses: dict[str, dict[str, Any]] = {}
    for observation in observations:
        parts = observation.key.split(".")
        if len(parts) == 3 and parts[0] == "expense":
            _, expense_id, field = parts
            expense = expenses.setdefault(expense_id, {"amount": None, "purpose": None,
                                                       "refs": [], "sources": []})
            if field == "amount" and observation.read_state == "READ":
                expense["amount"] = observation.value
            elif field == "purpose" and observation.read_state == "READ":
                expense["purpose"] = observation.value
            if observation.fact_id not in expense["refs"]:
                expense["refs"].append(observation.fact_id)
            if observation.source_id not in expense["sources"]:
                expense["sources"].append(observation.source_id)

    payments: dict[str, dict[str, Any]] = {}
    for observation in observations:
        parts = observation.key.split(".")
        if len(parts) == 3 and parts[0] == "payment":
            _, payment_id, field = parts
            payment = payments.setdefault(payment_id, {"amount": None, "payer": None,
                                                       "status": None, "sources": []})
            if observation.read_state == "READ":
                payment[field] = observation.value
            if observation.source_id not in payment["sources"]:
                payment["sources"].append(observation.source_id)

    _validate_relations(relations, set(expenses), set(payments))
    issues: list[Issue] = []
    checks: list[CheckResult] = []
    canonical = _dedup_payments(payments, relations, issues, checks)

    # Expense rows: eligibility split by payment evidence (R3/R5).
    rows: list[ExpenseRow] = []
    employee_total: int | None = 0
    company_total: int | None = 0
    eligibility_unknown: list[str] = []
    portion_overflows: list[str] = []
    for expense_id in sorted(expenses):
        expense = expenses[expense_id]
        links = [r for r in relations if r.kind == "EXPENSE_PAYMENT" and r.from_id == expense_id]
        refs = list(expense["refs"]) + list(expense["sources"])
        employee_portion = 0
        company_portion = 0
        pending = False
        seen_events: set[str] = set()
        for link in sorted(links, key=lambda r: r.relation_id):
            payment = payments[link.to_id]
            event = canonical[link.to_id]
            if event in seen_events:
                continue  # same underlying event counted once
            seen_events.add(event)
            refs.append(link.relation_id)
            refs.append(link.to_id)
            refs.extend(s for s in payment["sources"] if s not in refs)
            if payment.get("status") != "RECEIVED":
                pending = True
                continue
            portion = link.portion_vnd if link.portion_vnd is not None else payment["amount"]
            if payment.get("payer") == "COMPANY":
                company_portion += portion
            elif payment.get("payer") == "EMPLOYEE":
                employee_portion += portion
            else:
                pending = True
        amount = expense["amount"]
        if amount is not None and employee_portion + company_portion > amount:
            portion_overflows.append(expense_id)
        purpose = expense["purpose"]
        if purpose == "PERSONAL":
            state = "PERSONAL_EXCLUDED"
            reason = "Phần cá nhân không thuộc công việc; loại khỏi T/E, giữ hóa đơn gốc."
        elif amount is None:
            state = "UNKNOWN"
            reason = "Số tiền khai báo chưa đọc được; không dùng subtotal thay toàn bộ."
        elif pending:
            state = "UNKNOWN"
            reason = "Phần thanh toán chưa xác lập (trạng thái chưa RECEIVED hoặc payer không rõ)."
        elif employee_portion + company_portion > amount:
            state = "UNKNOWN"
            reason = "Tổng phần vượt hóa đơn; giữ incident, không tự cắt số."
        elif purpose == "BUSINESS" and links:
            state = "ELIGIBLE"
            reason = "Chi phí công việc do nhân viên chi, có nguồn đủ."
        elif purpose == "BUSINESS" and not links:
            state = "UNKNOWN"
            reason = "Chưa có căn cứ thanh toán (chưa ghép payment)."
        else:
            state = "UNKNOWN"
            reason = "Mục đích chưa rõ; hỏi trước, không tự loại hay tự chấp nhận."
        if state == "PERSONAL_EXCLUDED":
            pass  # excluded from both E and T, amounts kept in the row
        elif state == "ELIGIBLE":
            employee_total += employee_portion
            company_total += company_portion
        else:
            employee_total = None
            company_total = None
            eligibility_unknown.append(expense_id)
        rows.append(ExpenseRow(
            expense_id=expense_id, claimed_amount_vnd=amount,
            eligible_employee_vnd=employee_portion if state == "ELIGIBLE" else None,
            company_direct_vnd=company_portion if state == "ELIGIBLE" else None,
            state=state, refs=refs, reason=reason,
        ))

    if eligibility_unknown:
        checks.append(CheckResult(rule="eligibility", status="UNRESOLVED",
                                  refs=eligibility_unknown,
                                  reason="Có khoản chưa đủ căn cứ eligibility/payer."))
        issues.append(Issue(
            issue_id="I-ELIGIBILITY", type="FACT", owner="EMPLOYEE",
            message="Có khoản chưa đủ căn cứ (số/mục đích/phần thanh toán); "
                    "không dùng subtotal thay toàn bộ, không tự chấp nhận.",
            refs=eligibility_unknown, blocked="components",
        ))
    else:
        checks.append(CheckResult(rule="eligibility", status="PASS",
                                  refs=[r.expense_id for r in rows],
                                  reason="Mọi khoản đã đủ căn cứ hoặc bị loại có nguồn."))
    if portion_overflows:
        checks.append(CheckResult(rule="payer_parts", status="FAIL", refs=portion_overflows,
                                  reason="Phần thanh toán vượt gross; giữ incident."))
        issues.append(Issue(
            issue_id="I-PORTION", type="MONEY_INCIDENT", owner="ACCOUNTANT",
            message="Phần thanh toán vượt tổng hóa đơn; giữ gross và làm rõ, không cắt số.",
            refs=portion_overflows, blocked="components",
        ))
    else:
        checks.append(CheckResult(rule="payer_parts", status="PASS",
                                  refs=[r.expense_id for r in rows],
                                  reason="Phần không vượt gross."))

    # History (A/RA/P/RP) — unknown stays None, never 0 (R5).
    def history_value(name: str) -> tuple[int | None, list[str]]:
        observation = _first(grouped, f"history.{name}")
        if observation is None:
            return None, []
        return observation.value, [observation.source_id, observation.fact_id]

    a, a_refs = history_value("advance.received")
    ra, ra_refs = history_value("advance.returned")
    p, p_refs = history_value("reimbursement.received")
    rp, rp_refs = history_value("reimbursement.returned")
    missing_history = [name for name, value in
                       (("advance.received", a), ("advance.returned", ra),
                        ("reimbursement.received", p), ("reimbursement.returned", rp))
                       if value is None]
    if missing_history:
        checks.append(CheckResult(rule="history_coverage", status="UNRESOLVED",
                                  refs=[f"history.{n}" for n in missing_history],
                                  reason="Thiếu lịch sử tiền trong scope; không suy bằng 0."))
        issues.append(Issue(
            issue_id="I-HISTORY", type="FACT", owner="ACCOUNTANT",
            message="Thiếu lịch sử tiền (advance/reimbursement) trong scope đã khai báo; "
                    "cần nguồn company-side, không suy bằng 0.",
            refs=[f"history.{n}" for n in missing_history], blocked="net",
        ))
    else:
        checks.append(CheckResult(rule="history_coverage", status="PASS",
                                  refs=a_refs + ra_refs + p_refs + rp_refs,
                                  reason="Lịch sử A/RA/P/RP đủ nguồn."))

    # Budget B (R6).
    budget_obs = _first(grouped, "budget.approved")
    b = budget_obs.value if budget_obs else None
    b_refs = [budget_obs.source_id, budget_obs.fact_id] if budget_obs else []
    t = None
    if employee_total is not None:
        t = employee_total + (company_total or 0)
    conditional: list[ConditionalResult] = []
    if b is None:
        checks.append(CheckResult(rule="budget", status="UNRESOLVED", refs=[],
                                  reason="Chưa có ngân sách B hợp lệ; xin decision đúng quyền."))
        issues.append(Issue(
            issue_id="I-BUDGET", type="AUTHORITY", owner="APPROVER",
            message="Chưa có ngân sách B được duyệt cho work; cần decision đúng scope.",
            blocked="budget",
        ))
    elif t is not None and t > b:
        checks.append(CheckResult(
            rule="budget", status="FAIL", refs=b_refs,
            reason=f"T={t} vượt B={b}; xin exception, không cắt T về B."))
        issues.append(Issue(
            issue_id="I-BUDGET", type="AUTHORITY", owner="APPROVER",
            message=f"Tổng chi {t} vượt ngân sách {b}; cần exception decision, không tự nâng B.",
            refs=b_refs, blocked="proposal",
        ))
        net = calculate_net(MoneyComponents(e=employee_total, a=a, ra=ra, p=p, rp=rp))
        conditional.append(ConditionalResult(
            condition="Người có quyền chấp nhận exception toàn bộ phần vượt ngân sách",
            net_vnd=net,
            components=MoneyComponents(e=employee_total, a=a, ra=ra, p=p, rp=rp),
        ))
    else:
        checks.append(CheckResult(rule="budget", status="PASS", refs=b_refs,
                                  reason="T trong ngân sách (kể cả bằng B)."))

    calculated = calculate_net(MoneyComponents(e=employee_total, a=a, ra=ra, p=p, rp=rp))

    # Authority routing (R8): proposed only when a grant covers the amount.
    work_ref = run_input.submission.work_ref
    covering = [g for g in run_input.authority
                if g.work_ref is None or g.work_ref == work_ref]
    authority_ok = (calculated is not None and b is not None and
                    t is not None and t <= b and
                    any(g.max_settlement_vnd >= abs(calculated) for g in covering))
    if calculated is None:
        checks.append(CheckResult(rule="authority", status="NOT_APPLICABLE", refs=[],
                                  reason="Chưa có net để xét quyền."))
    elif authority_ok:
        checks.append(CheckResult(
            rule="authority", status="PASS",
            refs=[g.actor_ref for g in covering
                  if g.max_settlement_vnd >= abs(calculated)],
            reason="Có người có quyền đủ hạn mức cho số đề nghị."))
    else:
        checks.append(CheckResult(rule="authority", status="UNRESOLVED",
                                  refs=[g.actor_ref for g in covering],
                                  reason="Chưa có quyền đủ hạn mức; giữ calculated, chưa đề nghị."))
        issues.append(Issue(
            issue_id="I-AUTHORITY", type="AUTHORITY", owner="APPROVER",
            message="Chưa có người có quyền duyệt mức này trong scope; cần decision/quyền đúng scope.",
            blocked="proposal",
        ))

    proposed = calculated if (calculated is not None and authority_ok
                              and not missing_history
                              and not eligibility_unknown) else None
    completion = "COMPLETE" if not any(i.unresolved for i in issues) else "INCOMPLETE"
    if completion == "COMPLETE":
        if calculated is None:
            next_step = "Chưa tính được net; bổ sung nguồn còn thiếu."
        elif calculated > 0:
            next_step = (f"Trình kế toán rà soát rồi đề nghị người có quyền duyệt "
                         f"chi thêm {calculated} VND.")
        elif calculated < 0:
            next_step = (f"Trình kế toán rà soát; nhân viên đề nghị hoàn lại "
                         f"{-calculated} VND sau khi công ty xác nhận.")
        else:
            next_step = "Cân bằng; kiểm các closure gates trước khi đóng, không tự sinh đề nghị chi/thu."
    else:
        next_step = "Xử lý các issue theo owner, bổ sung nguồn/decision rồi chạy lại phần ảnh hưởng."

    return Report(
        run_id=run_id, job="B7", completion=completion, mode=mode,
        generated_at=datetime.now(timezone.utc),
        components=ReportComponents(
            t=ComponentSlot(value=t, state="KNOWN" if t is not None else "UNKNOWN",
                            refs=[r.expense_id for r in rows]),
            b=ComponentSlot(value=b, state="KNOWN" if b is not None else "UNKNOWN",
                            refs=b_refs),
            e=ComponentSlot(value=employee_total,
                             state="KNOWN" if employee_total is not None else "UNKNOWN",
                             refs=[r.expense_id for r in rows if r.state == "ELIGIBLE"]),
            a=ComponentSlot(value=a, state="KNOWN" if a is not None else "UNKNOWN",
                            refs=a_refs),
            ra=ComponentSlot(value=ra, state="KNOWN" if ra is not None else "UNKNOWN",
                             refs=ra_refs),
            p=ComponentSlot(value=p, state="KNOWN" if p is not None else "UNKNOWN",
                            refs=p_refs),
            rp=ComponentSlot(value=rp, state="KNOWN" if rp is not None else "UNKNOWN",
                             refs=rp_refs),
        ),
        calculated_net_vnd=calculated, proposed_net_vnd=proposed,
        conditional_results=conditional, expense_rows=rows, checks=checks,
        issues=issues, next_step=next_step,
        source_refs=sorted({s.id for s in run_input.sources}),
    )


# --- B3 ----------------------------------------------------------------------

def _evaluate_b3(run_input: RunInput, observations: list[Observation],
                 relations: list[Relation], run_id: str, mode: str) -> Report:
    grouped = _by_key(observations)
    _validate_observations(observations)  # SYS-02: reject before aggregation
    issues: list[Issue] = []
    checks: list[CheckResult] = []

    def value_of(key: str) -> tuple[int | None, list[str]]:
        observation = _first(grouped, key)
        if observation is None:
            return None, []
        return observation.value, [observation.source_id, observation.fact_id]

    request, request_refs = value_of("advance.request.amount")
    forecast, forecast_refs = value_of("forecast.employee")
    budget_obs = _first(grouped, "budget.approved")
    b = budget_obs.value if budget_obs else None
    b_refs = [budget_obs.source_id, budget_obs.fact_id] if budget_obs else []
    a, a_refs = value_of("history.advance.received")
    ra, ra_refs = value_of("history.advance.returned")

    checks.append(CheckResult(
        rule="request_positive", status="PASS" if (request is not None and request > 0) else "UNRESOLVED",
        refs=request_refs,
        reason="Số xin ứng > 0." if request else "Chưa có số xin ứng rõ."))
    if request is None or request <= 0:
        issues.append(Issue(
            issue_id="I-REQUEST", type="FACT", owner="EMPLOYEE",
            message="Số tiền xin ứng chưa rõ hoặc không dương; cần khai báo rõ.",
            refs=request_refs, blocked="request",
        ))

    if forecast is None:
        checks.append(CheckResult(rule="forecast", status="UNRESOLVED", refs=[],
                                  reason="Chưa có dự toán phần employee trong scope."))
        issues.append(Issue(
            issue_id="I-FORECAST", type="FACT", owner="EMPLOYEE",
            message="Thiếu dự toán phần employee; không so với toàn bộ B.",
            blocked="request",
        ))
    elif request is not None and request > forecast:
        checks.append(CheckResult(
            rule="forecast", status="FAIL", refs=forecast_refs + request_refs,
            reason=f"Số xin {request} vượt dự toán employee {forecast}; người có quyền quyết."))
        issues.append(Issue(
            issue_id="I-FORECAST", type="AUTHORITY", owner="APPROVER",
            message=f"Số xin ứng {request} vượt dự toán {forecast}; không tự giảm, chuyển người có quyền.",
            refs=forecast_refs + request_refs, blocked="request",
        ))
    else:
        checks.append(CheckResult(rule="forecast", status="PASS",
                                  refs=forecast_refs + request_refs,
                                  reason="Số xin trong dự toán employee."))

    if b is None:
        checks.append(CheckResult(rule="budget", status="UNRESOLVED", refs=[],
                                  reason="Chưa có ngân sách B hợp lệ."))
        issues.append(Issue(
            issue_id="I-BUDGET", type="AUTHORITY", owner="APPROVER",
            message="Chưa có ngân sách B được duyệt; không lấy đề nghị làm B.",
            blocked="budget",
        ))
    else:
        checks.append(CheckResult(rule="budget", status="PASS", refs=b_refs,
                                  reason="B hợp lệ để so dự toán."))

    if a is None or ra is None:
        checks.append(CheckResult(rule="history_coverage", status="UNRESOLVED",
                                  refs=a_refs + ra_refs,
                                  reason="Thiếu lịch sử ứng trong scope."))
        issues.append(Issue(
            issue_id="I-HISTORY", type="FACT", owner="ACCOUNTANT",
            message="Thiếu lịch sử ứng (A/RA) trong scope; không suy bằng 0.",
            refs=a_refs + ra_refs, blocked="history",
        ))
    else:
        checks.append(CheckResult(rule="history_coverage", status="PASS",
                                  refs=a_refs + ra_refs,
                                  reason="Lịch sử ứng đủ nguồn."))

    completion = "COMPLETE" if not any(i.unresolved for i in issues) else "INCOMPLETE"
    next_step = ("Kiểm tra đề nghị đã đủ cho người quyết định tiếp; không đòi invoice "
                 "sau công việc ở bước B3." if completion == "COMPLETE"
                 else "Xử lý các issue theo owner rồi chạy lại phần ảnh hưởng.")
    return Report(
        run_id=run_id, job="B3", completion=completion, mode=mode,
        generated_at=datetime.now(timezone.utc),
        components=ReportComponents(
            t=ComponentSlot(value=None, state="UNKNOWN", refs=[]),
            b=ComponentSlot(value=b, state="KNOWN" if b is not None else "UNKNOWN", refs=b_refs),
            e=ComponentSlot(value=None, state="UNKNOWN", refs=[]),
            a=ComponentSlot(value=a, state="KNOWN" if a is not None else "UNKNOWN", refs=a_refs),
            ra=ComponentSlot(value=ra, state="KNOWN" if ra is not None else "UNKNOWN", refs=ra_refs),
            p=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
            rp=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
        ),
        calculated_net_vnd=None, proposed_net_vnd=None,
        conditional_results=[], expense_rows=[], checks=checks, issues=issues,
        next_step=next_step,
        source_refs=sorted({s.id for s in run_input.sources}),
    )


def evaluate(run_input: RunInput, observations: list[Observation],
             relations: list[Relation], run_id: str = "R-ENGINE",
             mode: str | None = None) -> Report:
    """Dispatch by job; B7 computes settlement, B3 checks the advance request."""
    reader_mode = mode or run_input.config.get("reader_mode", "UNKNOWN")
    if run_input.submission.job == "B3":
        return _evaluate_b3(run_input, observations, relations, run_id, reader_mode)
    return _evaluate_b7(run_input, observations, relations, run_id, reader_mode)

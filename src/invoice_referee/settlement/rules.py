"""Settlement rule engine (W02): deterministic B7/B3 checks, money and routing.

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

Quality discipline (contradictions/relations):

- Two usable observations for one key with different values are a
  CONTRADICTION: the value stays ``None``, both refs are kept in the
  ``I-CONTRADICTION`` issue — the engine never silently picks one.
- Only ``USABLE`` observations count as known; a READ-but-unusable fact is
  refused by the ``fact_quality`` gate (I-QUALITY) instead of fabricating.
- Only ``ESTABLISHED`` relations reconcile money: a PROPOSED/UNCLEAR link is
  surfaced (``relation_status``/I-LINK) but never treated as payment evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    CheckResult,
    ComponentSlot,
    ConditionalResult,
    CriticalFact,
    ExpenseRow,
    Issue,
    MoneyComponents,
    Observation,
    Relation,
    Report,
    ReportComponents,
    ReportLink,
    RunInput,
)

MONEY_KEY_SUFFIXES = (
    ".amount", ".received", ".returned", "budget.approved",
    "advance.request.amount", "forecast.employee",
)

HISTORY_KEYS = (
    "history.advance.received", "history.advance.returned",
    "history.reimbursement.received", "history.reimbursement.returned",
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
                for suffix in MONEY_KEY_SUFFIXES):
            _validate_money(observation.value, observation.key, observation.fact_id)


def _is_money_key(key: str) -> bool:
    return any(key.endswith(suffix) or key == suffix for suffix in MONEY_KEY_SUFFIXES)


# --- fact resolution: quality, contradictions, no silent pick ---------------

def _usable_entries(observations: list[Observation],
                    key: str) -> list[Observation]:
    """Only READ + USABLE observations can make a value known."""
    return [o for o in observations
            if o.key == key and o.read_state == "READ" and o.usability == "USABLE"]


def _nonusable_entries(observations: list[Observation],
                       key: str) -> list[Observation]:
    """READ facts refused by the quality gate (never fabricated into known)."""
    return [o for o in observations
            if o.key == key and o.read_state == "READ" and o.usability != "USABLE"]


def _unclear_entries(observations: list[Observation],
                     key: str) -> list[Observation]:
    return [o for o in observations
            if o.key == key and o.read_state == "UNCLEAR"]


def _resolve(observations: list[Observation], key: str
             ) -> tuple[Any | None, list[str], bool]:
    """Resolve one key: (value, refs, contradicted); no first-non-null pick."""
    entries = _usable_entries(observations, key)
    if not entries:
        return None, [], False
    refs: list[str] = []
    for entry in entries:
        refs.extend([entry.source_id, entry.fact_id])
    distinct: list[Any] = []
    for entry in entries:
        if entry.value not in distinct:
            distinct.append(entry.value)
    if len(distinct) > 1:
        return None, refs, True
    return entries[0].value, refs, False


def _fact_state(observations: list[Observation], key: str) -> CriticalFact:
    """Expose one consumed fact with its quality state (KNOWN..UNUSABLE)."""
    value, refs, contradicted = _resolve(observations, key)
    if contradicted:
        return CriticalFact(key=key, value=None, state="CONTRADICTED", refs=refs)
    if value is not None:
        return CriticalFact(key=key, value=value, state="KNOWN", refs=refs)
    bad = _nonusable_entries(observations, key)
    if bad:
        return CriticalFact(key=key, value=None, state="UNUSABLE",
                             refs=[ref for o in bad
                                   for ref in (o.source_id, o.fact_id)])
    bad = _unclear_entries(observations, key)
    if bad:
        return CriticalFact(key=key, value=None, state="UNCLEAR",
                             refs=[ref for o in bad
                                   for ref in (o.source_id, o.fact_id)])
    return CriticalFact(key=key, value=None, state="UNKNOWN", refs=refs)


def _contradiction_issues(contradictions: list[tuple[str, list[str]]],
                          issues: list[Issue],
                          checks: list[CheckResult]) -> None:
    """One issue per contradictory key; money keys are MONEY_INCIDENT."""
    for key, refs in contradictions:
        if key in HISTORY_KEYS or key == "budget.approved":
            owner = "ACCOUNTANT"
            blocked = "net" if key in HISTORY_KEYS else "budget"
        else:
            owner = "EMPLOYEE"
            blocked = "components"
        issue_type = "MONEY_INCIDENT" if _is_money_key(key) else "FACT"
        issues.append(Issue(
            issue_id="I-CONTRADICTION", type=issue_type,  # type: ignore[arg-type]
            owner=owner,  # type: ignore[arg-type]
            message=f"Hai nguồn cho {key} khác nhau; giữ cả hai refs, "
                    f"không chọn một, không suy bằng 0.",
            refs=refs, blocked=blocked,
        ))
    if contradictions:
        keys = [key for key, _ in contradictions]
        checks.append(CheckResult(
            rule="contradictions", status="FAIL", refs=keys,
            reason="Có mâu thuẫn số liệu giữa các nguồn; làm rõ trước."))


def _quality_issues(observations: list[Observation], keys: list[str],
                    issues: list[Issue], checks: list[CheckResult]) -> None:
    """READ-but-unusable facts never become known (numeric quality gate)."""
    bad: list[str] = []
    for key in keys:
        bad.extend(ref for o in _nonusable_entries(observations, key)
                   for ref in (o.source_id, o.fact_id))
    if not bad:
        return
    checks.append(CheckResult(
        rule="fact_quality", status="UNRESOLVED", refs=bad,
        reason="Có fact đọc được nhưng chất lượng không đủ dùng làm known."))
    issues.append(Issue(
        issue_id="I-QUALITY", type="FACT", owner="EMPLOYEE",
        message="Có fact chất lượng không đạt (mờ/thiếu căn cứ); cần nguồn "
                "đọc được rõ hơn, không dùng READABLE thay số hợp lệ.",
        refs=bad, blocked="components",
    ))


def _link_issues(relations: list[Relation], issues: list[Issue],
                 checks: list[CheckResult]) -> None:
    """Only ESTABLISHED relations reconcile; others are surfaced, not used."""
    unestablished = [r.relation_id for r in relations
                     if r.status != "ESTABLISHED"]
    if not unestablished:
        checks.append(CheckResult(
            rule="relation_status", status="PASS",
            refs=[r.relation_id for r in relations],
            reason="Mọi quan hệ đối chiếu đã được xác lập."))
        return
    checks.append(CheckResult(
        rule="relation_status", status="UNRESOLVED", refs=unestablished,
        reason="Có quan hệ chưa ESTABLISHED (PROPOSED/UNCLEAR); không dùng "
               "làm căn cứ đối chiếu tiền."))
    issues.append(Issue(
        issue_id="I-LINK", type="FACT", owner="EMPLOYEE",
        message="Có quan hệ expense–payment/same-event chưa được xác lập; "
                "cần nguồn xác nhận, không tự coi đã ghép.",
        refs=unestablished, blocked="components",
    ))


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
    """Return payment_id -> canonical event id; one ESTABLISHED event counts once."""
    parent = {payment_id: payment_id for payment_id in payments}
    contradictions: list[str] = []
    for relation in sorted((r for r in relations
                            if r.kind == "SAME_EVENT"
                            and r.status == "ESTABLISHED"),
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
            refs=sorted({r.relation_id for r in relations
                         if r.kind == "SAME_EVENT"}),
            reason="Không có mâu thuẫn same-event."))
    return canonical


def _evaluate_b7(run_input: RunInput, observations: list[Observation],
                 relations: list[Relation], run_id: str, mode: str,
                 technical_issues: list[Issue] | None = None) -> Report:
    _validate_observations(observations)  # SYS-02: reject before aggregation

    issues: list[Issue] = list(technical_issues or [])
    checks: list[CheckResult] = []
    contradictions: list[tuple[str, list[str]]] = []

    # Expense/payment fields resolve per key with contradiction detection.
    expenses: dict[str, dict[str, Any]] = {}
    for observation in observations:
        parts = observation.key.split(".")
        if len(parts) == 3 and parts[0] == "expense":
            _, expense_id, field = parts
            expense = expenses.setdefault(expense_id, {"amount": None, "purpose": None,
                                                       "refs": [], "sources": []})
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
            if observation.source_id not in payment["sources"]:
                payment["sources"].append(observation.source_id)

    all_keys: set[str] = {o.key for o in observations}
    for key in sorted(all_keys):
        parts = key.split(".")
        value, refs, contradicted = _resolve(observations, key)
        if len(parts) == 3 and parts[0] == "expense":
            expense = expenses[parts[1]]
            if parts[2] in ("amount", "purpose"):
                expense[parts[2]] = value
            if contradicted:
                contradictions.append((key, refs))
        elif len(parts) == 3 and parts[0] == "payment":
            payment = payments[parts[1]]
            if parts[2] in ("amount", "payer", "status"):
                payment[parts[2]] = value
            if contradicted:
                contradictions.append((key, refs))
        elif key in HISTORY_KEYS or key == "budget.approved":
            if contradicted:
                contradictions.append((key, refs))

    _validate_relations(relations, set(expenses), set(payments))
    _contradiction_issues(contradictions, issues, checks)
    _quality_issues(observations, sorted(all_keys), issues, checks)
    _link_issues(relations, issues, checks)
    canonical = _dedup_payments(payments, relations, issues, checks)

    # Expense rows: eligibility split by ESTABLISHED payment evidence (R3/R5).
    rows: list[ExpenseRow] = []
    employee_total: int | None = 0
    company_total: int | None = 0
    eligibility_unknown: list[str] = []
    portion_overflows: list[str] = []
    for expense_id in sorted(expenses):
        expense = expenses[expense_id]
        links = [r for r in relations if r.kind == "EXPENSE_PAYMENT"
                 and r.status == "ESTABLISHED" and r.from_id == expense_id]
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
            if portion is None:
                pending = True  # số payment chưa biết rõ → không settled
                continue
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
            reason = "Chưa có căn cứ thanh toán (chưa ghép payment xác lập)."
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
    a, a_refs, _ = _resolve(observations, "history.advance.received")
    ra, ra_refs, _ = _resolve(observations, "history.advance.returned")
    p, p_refs, _ = _resolve(observations, "history.reimbursement.received")
    rp, rp_refs, _ = _resolve(observations, "history.reimbursement.returned")
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
    b, b_refs, _ = _resolve(observations, "budget.approved")
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

    # Authority routing (R8): proposed only when a grant covers the amount and
    # nothing unresolved remains (không đề nghị khi còn mâu thuẫn/issue mở).
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

    completion = "COMPLETE" if not any(i.unresolved for i in issues) else "INCOMPLETE"
    proposed = calculated if (calculated is not None and authority_ok
                              and completion == "COMPLETE") else None
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

    direction = ("COMPANY_TO_EMPLOYEE" if calculated is not None and calculated > 0
                 else "EMPLOYEE_TO_COMPANY" if calculated is not None and calculated < 0
                 else "BALANCED" if calculated == 0 else None)
    # "relation" là pseudo-key của reader, không phải fact; quan hệ nằm ở links.
    critical_keys = sorted(k for k in all_keys | set(HISTORY_KEYS)
                           if k != "relation")
    critical_facts = [_fact_state(observations, key) for key in critical_keys]
    links = [ReportLink(relation_id=r.relation_id, kind=r.kind, from_id=r.from_id,
                        to_id=r.to_id, portion_vnd=r.portion_vnd, status=r.status)
             for r in relations]

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
        direction=direction,
        conditional_results=conditional, expense_rows=rows, checks=checks,
        issues=issues, critical_facts=critical_facts, links=links,
        next_step=next_step,
        source_refs=sorted({s.id for s in run_input.sources}),
    )


# --- B3 ----------------------------------------------------------------------

def _evaluate_b3(run_input: RunInput, observations: list[Observation],
                 relations: list[Relation], run_id: str, mode: str,
                 technical_issues: list[Issue] | None = None) -> Report:
    _validate_observations(observations)  # SYS-02: reject before aggregation
    issues: list[Issue] = list(technical_issues or [])
    checks: list[CheckResult] = []
    contradictions: list[tuple[str, list[str]]] = []

    all_keys: set[str] = {o.key for o in observations}
    resolved: dict[str, tuple[Any | None, list[str], bool]] = {}
    for key in sorted(all_keys):
        resolved[key] = _resolve(observations, key)
        if resolved[key][2]:
            contradictions.append((key, resolved[key][1]))
    _contradiction_issues(contradictions, issues, checks)
    _quality_issues(observations, sorted(all_keys), issues, checks)
    _link_issues(relations, issues, checks)

    def value_of(key: str) -> tuple[int | None, list[str]]:
        value, refs, _ = resolved.get(key, (None, [], False))
        return value, refs

    # Ưu tiên khai báo native form; import ngoài dùng fact từ nguồn (R1: số xin
    # là đề nghị, không phải evidence và không phải actual advance).
    form = run_input.submission.form
    declared_request = form.get("request_amount_vnd")
    declared_forecast = form.get("forecast_employee_vnd")
    request, request_refs = value_of("advance.request.amount")
    if declared_request is not None:
        request = declared_request
        request_refs = ["declaration:request_amount_vnd"]
    forecast, forecast_refs = value_of("forecast.employee")
    if declared_forecast is not None:
        forecast = declared_forecast
        forecast_refs = ["declaration:forecast_employee_vnd"]
    b, b_refs = value_of("budget.approved")
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

    # Authority routing (R8): ai đủ quyền duyệt số xin trong scope work này.
    work_ref = run_input.submission.work_ref
    covering = [g for g in run_input.authority
                if g.work_ref is None or g.work_ref == work_ref]
    if request is None:
        checks.append(CheckResult(rule="authority", status="NOT_APPLICABLE",
                                  refs=[],
                                  reason="Chưa có số xin rõ để xét quyền."))
    elif any(g.max_settlement_vnd >= request for g in covering):
        checks.append(CheckResult(
            rule="authority", status="PASS",
            refs=[g.actor_ref for g in covering
                  if g.max_settlement_vnd >= request],
            reason="Có người có quyền hạn mức cho số xin trong scope."))
    else:
        checks.append(CheckResult(
            rule="authority", status="UNRESOLVED",
            refs=[g.actor_ref for g in covering],
            reason="Chưa có quyền đủ hạn mức đúng scope; chuyển người có quyền."))
        issues.append(Issue(
            issue_id="I-AUTHORITY", type="AUTHORITY", owner="APPROVER",
            message="Chưa có người có quyền duyệt mức xin này trong scope work; "
                    "không tự hạ số xin để lọt quyền.",
            refs=[g.actor_ref for g in covering], blocked="request",
        ))

    completion = "COMPLETE" if not any(i.unresolved for i in issues) else "INCOMPLETE"
    next_step = ("Đề nghị đã đủ căn cứ cho người quyết định tiếp; không đòi chứng từ "
                 "sau công việc ở bước kiểm tra ứng." if completion == "COMPLETE"
                 else "Xử lý các issue theo owner rồi chạy lại phần ảnh hưởng.")
    critical_facts = [_fact_state(observations, key)
                      for key in sorted(k for k in
                                        (all_keys | {"advance.request.amount",
                                                    "forecast.employee"})
                                        if k != "relation")]
    links = [ReportLink(relation_id=r.relation_id, kind=r.kind, from_id=r.from_id,
                        to_id=r.to_id, portion_vnd=r.portion_vnd, status=r.status)
             for r in relations]
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
        critical_facts=critical_facts, links=links,
        checks=checks, issues=issues,
        next_step=next_step,
        source_refs=sorted({s.id for s in run_input.sources}),
    )


def evaluate(run_input: RunInput, observations: list[Observation],
             relations: list[Relation], run_id: str = "R-ENGINE",
             mode: str | None = None,
             technical_issues: list[Issue] | None = None) -> Report:
    """Dispatch by job; B7 computes settlement, B3 checks the advance request."""
    reader_mode = mode or run_input.config.get("reader_mode", "UNKNOWN")
    if run_input.submission.job == "B3":
        return _evaluate_b3(run_input, observations, relations, run_id,
                           reader_mode, technical_issues)
    return _evaluate_b7(run_input, observations, relations, run_id,
                       reader_mode, technical_issues)

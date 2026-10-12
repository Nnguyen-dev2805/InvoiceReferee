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
    ReportLink,
    RunInput,
)

# Common helpers/constants live in ``rules_common`` (re-exported).
from invoice_referee.settlement.rules_common import (  # noqa: E402
    MONEY_KEY_SUFFIXES,
    HISTORY_KEYS,
    calculate_net,
    _validate_money,
    _validate_observations,
    _is_money_key,
    _advance_event_refs,
    _advance_question,
    covering_grant,
    _usable_entries,
    _nonusable_entries,
    _unclear_entries,
    _resolve,
    _fact_state,
    _contradiction_issues,
    _quality_issues,
    _link_issues,
    _validate_relations,
)

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

    # Declared claims from a linked intake form (statements, not facts).
    claim_rows = []
    form = run_input.submission.form or {}
    if isinstance(form, dict) and form.get("schema_version") == "b7-linked-intake-v1":
        from invoice_referee.settlement.linked_context import (
            claim_comparisons as _claim_comparisons,
            load_b7_linked_intake,
        )
        intake = load_b7_linked_intake(form)
        claim_rows = intake.expense_rows
    claim_ids = {row.claim_id for row in claim_rows}
    _validate_relations(relations, set(expenses), set(payments), claim_ids)
    _contradiction_issues(contradictions, issues, checks)
    _quality_issues(observations, sorted(all_keys), issues, checks)
    _link_issues(relations, issues, checks)
    canonical = _dedup_payments(payments, relations, issues, checks)

    # Expense rows: eligibility split by ESTABLISHED payment evidence (R3/R5).
    # No expense entries is NOT a verified zero: T/E stay None (INCOMPLETE).
    rows: list[ExpenseRow] = []
    employee_total: int | None = 0 if expenses else None
    company_total: int | None = 0 if expenses else None
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

    if not expenses:
        # No expense entry read at all: T/E unknown, ask for the expense source.
        checks.append(CheckResult(
            rule="eligibility", status="UNRESOLVED", refs=[],
            reason="Không có khoản chi nào đọc được; T/E unknown, không phải 0."))
        issues.append(Issue(
            issue_id="I-ELIGIBILITY", type="FACT", owner="EMPLOYEE",
            message="Chưa đọc được khoản chi nào (thiếu nguồn/bảng kê); không suy 0.",
            refs=[], blocked="components",
        ))
    elif eligibility_unknown:
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
        # If an advance attempt event is present, ask specifically about it
        # (event ref / amount / decision / cutoff) with source refs, instead of
        # a generic "missing history" question (plan Task 3.3).
        advance_refs = _advance_event_refs(observations)
        if "advance.received" in missing_history and advance_refs["event_ref"]:
            issues.append(Issue(
                issue_id="I-HISTORY", type="FACT", owner="ACCOUNTANT",
                message=_advance_question(advance_refs, run_input),
                refs=advance_refs["refs"], blocked="net",
            ))
        else:
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
    # ``final_e`` is the amount that feeds the decided net. T>B (or unresolved
    # budget) keeps it unknown: E is not decided until the exception is.
    final_e = employee_total
    conditional: list[ConditionalResult] = []
    if b is None:
        checks.append(CheckResult(rule="budget", status="UNRESOLVED", refs=[],
                                  reason="Chưa có ngân sách B hợp lệ; xin decision đúng quyền."))
        issues.append(Issue(
            issue_id="I-BUDGET", type="AUTHORITY", owner="APPROVER",
            message="Chưa có ngân sách B được duyệt cho work; cần decision đúng scope.",
            blocked="budget",
        ))
        # Missing B does not by itself undecide E: E is a verified expense
        # total. Only an undecided exception (T>B) keeps the final E unknown.
    elif t is not None and t > b:
        # T>B is a POLICY breach: surface it, do not clip, and keep the final
        # E/S unknown — the accept-all amount is a CONDITIONAL result, not a
        # decided one. A scoped exception authority only routes the review.
        checks.append(CheckResult(
            rule="budget", status="FAIL", refs=b_refs,
            reason=f"T={t} vượt B={b}; xin exception, không cắt T về B."))
        issues.append(Issue(
            issue_id="I-BUDGET", type="POLICY", owner="APPROVER",
            message=f"Tổng chi {t} vượt ngân sách {b} là {t - b}; cần quyết định "
                    f"ngoại lệ (khoản/phần/lý do), không tự nâng B.",
            refs=b_refs, blocked="proposal",
        ))
        net = calculate_net(MoneyComponents(e=employee_total, a=a, ra=ra, p=p, rp=rp))
        conditional.append(ConditionalResult(
            condition="Người có quyền chấp nhận exception toàn bộ phần vượt ngân sách",
            net_vnd=net,
            components=MoneyComponents(e=employee_total, a=a, ra=ra, p=p, rp=rp),
        ))
        final_e = None  # E not decided while the exception is undecided
    else:
        checks.append(CheckResult(rule="budget", status="PASS", refs=b_refs,
                                  reason="T trong ngân sách (kể cả bằng B)."))

    calculated = calculate_net(MoneyComponents(e=final_e, a=a, ra=ra, p=p, rp=rp))

    # Authority routing (R8): a grant must cover the employee cost AND the
    # settlement amount, in scope/time. T<=B is a POLICY concern, not part of
    # the authority check. No grant covers => AUTHORITY issue; the raw grant
    # that covers the net is not proof of covering E/exception.
    work_ref = run_input.submission.work_ref
    employee_ref = run_input.submission.employee_ref
    effective_at = run_input.submission.money_as_of
    authority_grant = None
    if calculated is not None:
        authority_grant = covering_grant(
            run_input.authority, employee_ref, work_ref, effective_at,
            employee_cost_vnd=employee_total,
            settlement_vnd=calculated,
            total_work_cost_vnd=t,
            exception_required=False,
        )
    authority_ok = authority_grant is not None
    if calculated is None:
        checks.append(CheckResult(rule="authority", status="NOT_APPLICABLE", refs=[],
                                  reason="Chưa có net để xét quyền."))
    elif authority_ok:
        checks.append(CheckResult(
            rule="authority", status="PASS",
            refs=[authority_grant.actor_ref],
            reason="Có người có quyền đủ hạn mức (employee cost + settlement) "
                   "trong scope/thời hạn cho số đề nghị."))
    else:
        checks.append(CheckResult(
            rule="authority", status="UNRESOLVED",
            refs=[g.actor_ref for g in run_input.authority],
            reason="Chưa có quyền đủ hạn mức (employee cost/settlement) trong "
                   "scope; giữ calculated, chưa đề nghị."))
        issues.append(Issue(
            issue_id="I-AUTHORITY", type="AUTHORITY", owner="APPROVER",
            message="Chưa có người có quyền duyệt mức này trong scope; cần "
                    "decision/quyền đúng scope.",
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
    comparisons = []
    if claim_rows:
        from invoice_referee.settlement.linked_context import (
            claim_comparisons as _claim_comparisons,
        )
        comparisons = _claim_comparisons(claim_rows, relations, expenses)

    return Report(
        run_id=run_id, job="B7", completion=completion, mode=mode,
        generated_at=datetime.now(timezone.utc),
        components=ReportComponents(
            t=ComponentSlot(value=t, state="KNOWN" if t is not None else "UNKNOWN",
                            refs=[r.expense_id for r in rows]),
            b=ComponentSlot(value=b, state="KNOWN" if b is not None else "UNKNOWN",
                            refs=b_refs),
            e=ComponentSlot(value=final_e,
                             state="KNOWN" if final_e is not None else "UNKNOWN",
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
        claim_comparisons=comparisons,
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
    """Dispatch by job/form; B7 computes settlement, legacy B3 keeps the old
    advance checks, B3 v1 (b3-intake-v1) evaluates the intake proposal."""
    from invoice_referee.settlement.b3_intake import evaluate_b3_proposal, is_b3_v1

    reader_mode = mode or run_input.config.get("reader_mode", "UNKNOWN")
    if run_input.submission.job == "B3" and is_b3_v1(run_input.submission.form):
        return evaluate_b3_proposal(run_input, observations, run_id=run_id,
                                    mode=reader_mode,
                                    technical_issues=technical_issues)
    if run_input.submission.job == "B3":
        return _evaluate_b3(run_input, observations, relations, run_id,
                           reader_mode, technical_issues)
    return _evaluate_b7(run_input, observations, relations, run_id,
                       reader_mode, technical_issues)

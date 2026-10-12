"""B9 settlement fulfillment & closure helpers (b7-linked-intake-v1).

Deterministic Python classifies actual settlement money from a human-reviewed
source, projects it against the approved decision, revalidates that a correct
fulfillment keeps the original decision valid, and decides closure blockers.
No bank transfer, no AI/bank verification, no LLM.

Separation of meanings (spec §2, §4, §6):
- APPROVED (B8 decision) != RECEIVED (recorded money) != FULFILLED (obligation
  covered) != CLOSED. ``fulfilled_vnd`` caps at the approved amount; the raw
  gross is never clipped, and an excess is kept as an OVERPAY incident.
"""
from __future__ import annotations

from datetime import datetime

from invoice_referee.settlement.models import (
    B7ClosureView,
    B7DecisionView,
    B7FulfillmentReceipt,
    B7FulfillmentSummary,
    B7MoneyEventView,
    B7MoneyIncident,
    B7RevalidationView,
    Report,
    SourceRecord,
)

# Fields a confirmed receipt must have a READ source for.
_REQUIRED_FIELDS = (
    "amount_vnd", "currency", "payer_ref", "payee_ref", "event_at",
    "receiver_outcome", "event_namespace", "event_ref",
)
_PAY_PURPOSES = ("REIMBURSEMENT_RECEIVED",)
_COLLECT_PURPOSES = ("ADVANCE_RETURN", "REIMBURSEMENT_RETURN")
# Incidents that make the remaining amount not assertable / block closure.
_BLOCKING_INCIDENTS = (
    "WRONG_RECIPIENT", "WRONG_PAYER", "OVERPAY", "CONFLICTING_EVENT",
    "UNALLOCATED", "REVERSAL", "AFTER_CUTOFF",
)
_NONFINAL_STATES = ("PENDING", "UNKNOWN")


def _incident(code: str, reason: str, *, event_ids=None, refs=None,
              excess_vnd=None) -> B7MoneyIncident:
    return B7MoneyIncident(code=code, event_ids=event_ids or [], refs=refs or [],
                           excess_vnd=excess_vnd, reason=reason)


def _receiver_confirmed(payload) -> bool:
    for field in payload.evidence:
        if field.field == "receiver_outcome" and field.read_state == "READ" \
                and field.value == "RECEIVED":
            return True
    return False


def classify_b7_money(payload, *, employee_ref: str, work_ref: str,
                      company_ref: str | None, sources: list[SourceRecord],
                      effective_at: datetime
                      ) -> tuple[str, list[B7MoneyIncident]]:
    """Derive an event's classification + incidents from its own facts.

    A RECEIVED event is a CONFIRMED_RECEIPT only when it reaches the correct
    party (the employee for a reimbursement, the configured company for a
    return), carries a READ receiver outcome, resolves to retained sources and
    is allocated to this work. Wrong party / unknown purpose / conflicting
    outcome keep the raw event as an INCIDENT — never a RECEIVED shortcut.
    """
    incidents: list[B7MoneyIncident] = []
    source_ids = {s.id for s in sources}
    unresolved = [f.source_id for f in payload.evidence
                  if f.source_id not in source_ids]
    if unresolved:
        incidents.append(_incident(
            "SOURCE_UNRESOLVED", refs=sorted(set(unresolved)),
            reason="Nguồn căn cứ không thuộc hồ sơ; giữ raw, chưa xác nhận."))
    read_fields = {f.field for f in payload.evidence if f.read_state == "READ"}
    missing = [name for name in _REQUIRED_FIELDS if name not in read_fields]
    if missing:
        incidents.append(_incident(
            "SOURCE_UNRESOLVED", refs=missing,
            reason=f"Thiếu trường nguồn bắt buộc: {', '.join(missing)}."))

    if payload.purpose == "UNKNOWN":
        incidents.append(_incident(
            "UNALLOCATED",
            reason="Chưa rõ nguồn nghĩa vụ (RA/P/RP); không tự phân bổ."))
        return "INCIDENT", incidents

    pay = payload.purpose in _PAY_PURPOSES
    if pay:
        expected_payee = employee_ref
        expected_payer = company_ref
    else:
        expected_payee = company_ref
        expected_payer = employee_ref
    if not pay and company_ref is None:
        incidents.append(_incident(
            "UNALLOCATED",
            reason="Chưa cấu hình company_ref; không xác định công ty nhận."))
        return "INCIDENT", incidents
    if payload.payee_ref is not None and expected_payee is not None \
            and payload.payee_ref != expected_payee:
        incidents.append(_incident(
            "WRONG_RECIPIENT",
            reason=(f"Người nhận {payload.payee_ref} không phải bên nghĩa vụ "
                    f"{expected_payee}; giữ raw, không tính thực nhận.")))
    if payload.payer_ref is not None and expected_payer is not None \
            and payload.payer_ref != expected_payer \
            and payload.payer_ref not in ("COMPANY", "EMPLOYEE"):
        incidents.append(_incident(
            "WRONG_PAYER",
            reason=(f"Bên trả {payload.payer_ref} không khớp nghĩa vụ "
                    f"{expected_payer}; giữ raw, cần kế toán xử lý.")))

    # Explicit same-work allocation: a work_ref that contradicts the case scope
    # is not a silent match.
    for field in payload.evidence:
        if field.field == "work_ref" and field.read_state == "READ" \
                and isinstance(field.value, str) and field.value != work_ref:
            incidents.append(_incident(
                "UNALLOCATED",
                reason=(f"Nguồn ghi công việc {field.value} khác phạm vi hồ sơ "
                        f"{work_ref}; không phân bổ.")))

    if payload.event_at is not None and payload.event_at > effective_at:
        incidents.append(_incident(
            "AFTER_CUTOFF",
            reason="Sự kiện vượt mốc đối chiếu hiện tại; giữ lịch sử, cần "
                   "cập nhật coverage và chạy lại."))

    if any(i.code in ("WRONG_RECIPIENT", "WRONG_PAYER", "UNALLOCATED",
                      "SOURCE_UNRESOLVED") for i in incidents):
        return "INCIDENT", incidents

    if payload.reported_status == "FAILED":
        return "FAILED", incidents
    if payload.reported_status == "CANCELLED":
        return "CANCELLED", incidents
    if payload.reported_status in ("PENDING", "UNCONFIRMED"):
        return "PENDING", incidents
    # reported_status == RECEIVED: an unresolved/missing required field or a
    # non-READ receiver outcome cannot be a confirmed receipt.
    if missing or not _receiver_confirmed(payload):
        return "UNCONFIRMED", incidents
    return "CONFIRMED_RECEIPT", incidents


def canonical_event_id(namespace: str | None, ref: str | None,
                       fallback_id: str) -> str:
    """Economic identity: namespace+ref when both known, else the record id."""
    if namespace and ref:
        return f"{namespace}:{ref}"
    return fallback_id


def receipt_state(classification: str) -> str:
    return {
        "CONFIRMED_RECEIPT": "CONFIRMED",
        "PENDING": "PENDING",
        "FAILED": "FAILED",
        "CANCELLED": "CANCELLED",
    }.get(classification, "UNKNOWN")


def _superseded_receipts(receipts: list[B7FulfillmentReceipt]) -> set[str]:
    """event_ids of nonfinal receipts a LATER final event supersedes.

    Ordering is positional (creation order): a final event only supersedes an
    EARLIER nonfinal one of the same canonical identity. A later conflicting
    observation never removes an already-confirmed receipt.
    """
    final_states = ("CONFIRMED", "FAILED", "CANCELLED")
    superseded: set[str] = set()
    for later_index, later in enumerate(receipts):
        if later.state not in final_states:
            continue
        for earlier_index, earlier in enumerate(receipts):
            if earlier_index >= later_index:
                break
            if earlier.canonical_id == later.canonical_id \
                    and earlier.state in _NONFINAL_STATES:
                superseded.add(earlier.event_id)
    return superseded


def project_b7_fulfillment(decision_id: str, approved_vnd: int, direction: str,
                           receipts: list[B7FulfillmentReceipt], *,
                           as_of: datetime, knowledge_cutoff: datetime
                           ) -> B7FulfillmentSummary:
    """Project one decision's fulfillment from its qualifying receipts.

    Only CONFIRMED qualifying receipts count toward the received total; the raw
    gross is never clipped (an excess adds an OVERPAY incident). Pending/unknown
    or any blocking incident makes ``remaining_vnd`` null while the known
    subtotal stays visible. A BALANCED decision needs no money event.
    """
    scoped = [r for r in receipts if r.decision_id == decision_id]
    superseded = _superseded_receipts(scoped)
    active = [r for r in scoped if r.event_id not in superseded]
    incidents: list[B7MoneyIncident] = []
    for receipt in active:
        incidents.extend(receipt.incidents)
    if any(r.after_cutoff for r in active):
        incidents.append(_incident(
            "AFTER_CUTOFF",
            reason="Có sự kiện vượt mốc đối chiếu hiện tại; giữ lịch sử, cần "
                   "cập nhật coverage và chạy lại trước khi đối chiếu."))
    confirmed = [r for r in active
                 if r.state == "CONFIRMED" and r.qualifying and not r.after_cutoff]
    pending_count = sum(1 for r in active if r.state == "PENDING")
    unknown_count = sum(1 for r in active if r.state == "UNKNOWN")
    recorded = sum(r.amount_vnd for r in confirmed
                   if r.amount_vnd is not None) if confirmed else None
    if direction != "BALANCED" and recorded is not None \
            and recorded > approved_vnd:
        incidents.append(_incident(
            "OVERPAY", excess_vnd=recorded - approved_vnd,
            reason="Số thực nhận vượt số đã duyệt; giữ gross, cần xử lý."))
    blocking = [i for i in incidents if i.code in _BLOCKING_INCIDENTS]

    if direction == "BALANCED":
        return B7FulfillmentSummary(
            decision_id=decision_id, direction=direction,
            approved_vnd=approved_vnd, recorded_received_vnd=recorded,
            fulfilled_vnd=0, remaining_vnd=0, known_remaining_vnd=0,
            pending_count=pending_count, unknown_count=unknown_count,
            incidents=incidents,
            status="BLOCKED" if (blocking or pending_count or unknown_count)
            else "BALANCED",
            managed_scope=f"decision:{decision_id}", as_of=as_of,
            knowledge_cutoff=knowledge_cutoff)

    uncertain = bool(blocking or pending_count or unknown_count)
    if recorded is None:
        fulfilled = None if active else 0
        remaining = None if uncertain else approved_vnd
    else:
        fulfilled = min(recorded, approved_vnd)
        remaining = None if uncertain else max(approved_vnd - recorded, 0)
    known_remaining = max(approved_vnd - (recorded or 0), 0)

    if blocking:
        status = "BLOCKED"
    elif pending_count or unknown_count:
        status = "BLOCKED"
    elif not active:
        status = "WAITING"
    elif recorded is not None and recorded >= approved_vnd:
        status = "FULFILLED"
    elif recorded is not None and recorded > 0:
        status = "PARTIAL"
    else:
        status = "WAITING"

    return B7FulfillmentSummary(
        decision_id=decision_id, direction=direction, approved_vnd=approved_vnd,
        recorded_received_vnd=recorded, fulfilled_vnd=fulfilled,
        remaining_vnd=remaining, known_remaining_vnd=known_remaining,
        pending_count=pending_count, unknown_count=unknown_count,
        incidents=incidents, status=status,
        managed_scope=f"decision:{decision_id}", as_of=as_of,
        knowledge_cutoff=knowledge_cutoff)


def _qualifying_sums(events: list[B7MoneyEventView]) -> dict[str, int]:
    sums = {"REIMBURSEMENT_RECEIVED": 0, "ADVANCE_RETURN": 0,
            "REIMBURSEMENT_RETURN": 0}
    for event in events:
        if event.classification != "CONFIRMED_RECEIPT":
            continue
        if event.after_cutoff or event.gross_vnd is None:
            continue
        if event.purpose in sums:
            sums[event.purpose] += event.gross_vnd
    return sums


def revalidate_b7_decision(decision: B7DecisionView, current_report: Report,
                           canonical_history: dict,
                           qualifying_events: list[B7MoneyEventView],
                           current_cost_signature: str) -> B7RevalidationView:
    """Keep the original decision valid when only correct fulfillment changed.

    The accepted cost basis (E/T/B) must be unchanged; the whole-history delta
    (A/RA/P/RP) must equal exactly the canonical qualifying receipts, with no
    extra advance/return. Anything else is NEEDS_RECHECK — the original decision
    is never rewritten and the new report S does not become a new approval.
    """
    reasons: list[str] = []
    qualifying_ids = [e.id for e in qualifying_events
                      if e.classification == "CONFIRMED_RECEIPT"]
    if decision is None or decision.outcome != "APPROVE" \
            or decision.target is None or decision.history_baseline is None:
        return B7RevalidationView(
            original_decision_id=decision.id if decision else "",
            current_report_id=current_report.run_id, status="NEEDS_RECHECK",
            cost_signature=current_cost_signature,
            receipt_history_signature="", qualifying_event_ids=qualifying_ids,
            blocked_reasons=["Chưa có quyết định APPROVE có baseline để đối chiếu."],
            refs=list(current_report.source_refs),
            created_at=current_report.generated_at)
    target = decision.target
    baseline = decision.history_baseline
    components = current_report.components

    def known(slot) -> int | None:
        return slot.value if slot.state == "KNOWN" \
            and isinstance(slot.value, int) and not isinstance(slot.value, bool) \
            else None

    e, t, b = known(components.e), known(components.t), known(components.b)
    if e is None or e != target.employee_cost_vnd:
        reasons.append("Chi phí nhân viên được duyệt (E) đã thay đổi.")
    if t is None or t != target.total_work_cost_vnd:
        reasons.append("Tổng chi phí công việc (T) đã thay đổi.")
    if b is None or b != target.budget_vnd:
        reasons.append("Ngân sách (B) đã thay đổi.")

    sums = _qualifying_sums(qualifying_events)
    deltas = {
        "a": (known(components.a), baseline.a),
        "ra": (known(components.ra), baseline.ra),
        "p": (known(components.p), baseline.p),
        "rp": (known(components.rp), baseline.rp),
    }
    for key, (value, base) in deltas.items():
        if value is None or base is None:
            reasons.append(f"Thành phần {key.upper()} không xác định/đã đổi.")
    if not any("không xác định" in r for r in reasons):
        delta_a = known(components.a) - baseline.a
        delta_ra = known(components.ra) - baseline.ra
        delta_p = known(components.p) - baseline.p
        delta_rp = known(components.rp) - baseline.rp
        if delta_a != 0:
            reasons.append("Có thay đổi ứng (A) ngoài fulfillment; cần recheck.")
        if delta_ra != sums["ADVANCE_RETURN"]:
            reasons.append("Hoàn ứng (RA) không khớp receipt đủ căn cứ.")
        if delta_p != sums["REIMBURSEMENT_RECEIVED"]:
            reasons.append("Công ty trả thêm (P) không khớp receipt đủ căn cứ.")
        if delta_rp != sums["REIMBURSEMENT_RETURN"]:
            reasons.append("Nhân viên trả lại (RP) không khớp receipt đủ căn cứ.")

    status = "VALID" if not reasons else "NEEDS_RECHECK"
    return B7RevalidationView(
        original_decision_id=decision.id,
        current_report_id=current_report.run_id, status=status,
        cost_signature=current_cost_signature,
        receipt_history_signature="|".join(sorted(qualifying_ids)),
        qualifying_event_ids=qualifying_ids, blocked_reasons=reasons,
        refs=list(current_report.source_refs),
        created_at=current_report.generated_at)


def b7_closure_blockers(*, report: Report | None, decision: B7DecisionView | None,
                        fulfillment: B7FulfillmentSummary | None,
                        revalidation: B7RevalidationView | None,
                        scope_current: bool, coverage_current: bool,
                        stop_active: bool, open_question_count: int
                        ) -> list[str]:
    """Every reason a linked settlement closure must be refused; [] means ok.

    S=0 alone is not sufficient: a valid approved decision, revalidated
    fulfillment with no remaining/pending/incident, current scope/coverage and
    no Stop/open question must all hold.
    """
    blockers: list[str] = []
    if stop_active:
        blockers.append("Hồ sơ đang Stop; không đóng khi control đang giữ.")
    if decision is None or decision.outcome != "APPROVE":
        blockers.append("Chưa có quyết định quyết toán được duyệt đúng phạm vi.")
    if revalidation is None or revalidation.status != "VALID":
        blockers.append("Chưa revalidate fulfillment đúng cho quyết định gốc.")
    if report is None or report.completion != "COMPLETE" \
            or report.calculated_net_vnd != 0:
        blockers.append("Report hiện hành chưa COMPLETE với S=0 có căn cứ.")
    if fulfillment is None:
        blockers.append("Chưa có đối chiếu fulfillment cho quyết định.")
    else:
        if fulfillment.status not in ("FULFILLED", "BALANCED"):
            blockers.append(
                f"Nghĩa vụ chưa thực hiện đủ (trạng thái {fulfillment.status}).")
        if fulfillment.remaining_vnd not in (0, None) \
                and (fulfillment.remaining_vnd or 0) > 0:
            blockers.append(
                f"Còn phần chưa thực nhận: remaining {fulfillment.remaining_vnd}.")
        if fulfillment.remaining_vnd is None and fulfillment.status != "BALANCED":
            blockers.append("Còn pending/unknown; chưa xác định phần còn lại.")
        if fulfillment.pending_count or fulfillment.unknown_count:
            blockers.append("Còn sự kiện tiền pending/unknown chưa đối chiếu.")
        incident_codes = sorted({i.code for i in fulfillment.incidents})
        if incident_codes:
            blockers.append(
                "Còn money incident chưa xử lý: " + ", ".join(incident_codes) + ".")
    if not scope_current:
        blockers.append("Phạm vi (scope) không còn đúng/đủ cho đóng.")
    if not coverage_current:
        blockers.append("Coverage hiện hành chưa đủ tới mốc đóng.")
    if open_question_count:
        blockers.append(
            f"Còn {open_question_count} câu hỏi trọng yếu chưa được xử lý.")
    return blockers


def closure_matches(closure: B7ClosureView, payload) -> bool:
    """True when a closure request re-uses the same decision/report/reason."""
    return (closure.decision_id == payload.decision_id
            and closure.current_report_id == payload.current_report_id
            and closure.reason == payload.reason)

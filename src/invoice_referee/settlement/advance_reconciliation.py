"""B5 advance-funding bookkeeping (b3-intake-v1).

Deterministic projection of *actual* advance money events against a B3
approval. This module decides nothing about whether money moved: it aggregates
human-source-reviewed records and keeps pending/unknown/incidents distinct.
No bank transfer, no AI/bank verification, no closure.

Separation of meanings (spec §1, §4):
- APPROVED (B3 decision) ≠ RECEIVED (recorded money) ≠ FULFILLED (obligation
  covered). ``recorded_received_vnd`` is the gross actually recorded; a
  fulfillment is only the part that covers the approved obligation.
"""
from __future__ import annotations

from datetime import datetime, timezone

from invoice_referee.settlement.models import (
    B3AdvanceEventView,
    B3DecisionView,
    B3FundingIncident,
    B3FundingSummary,
)

_NONFINAL = ("PENDING", "FAILED", "CANCELLED", "UNCONFIRMED")
_FINAL_RECEIVED = "RECEIVED"

# Core receipt facts every confirmed RECEIVED must read from a retained source.
_RECEIPT_CORE_FIELDS = (
    "amount_vnd", "currency", "payer_side", "payee_ref", "event_at",
    "receiver_outcome", "event_namespace", "event_ref", "method",
)
# Every RECEIVED additionally needs the human-readable receiver name.
_RECEIPT_REQUIRED_FIELDS = _RECEIPT_CORE_FIELDS + ("receiver_name",)


def _as_aware(value: datetime | None) -> datetime | None:
    """Normalize a datetime to an aware instant for value comparison."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _value_matches(field: str, evidence_value, payload) -> bool:
    """Whether an evidence field's value agrees with the payload's own fact."""
    if field == "amount_vnd":
        return evidence_value == payload.gross_vnd
    if field == "currency":
        return str(evidence_value).strip().upper() == "VND"
    if field == "payer_side":
        return evidence_value == payload.payer_side
    if field == "payee_ref":
        return evidence_value == payload.payee_ref
    if field == "receiver_outcome":
        return evidence_value == payload.reported_status
    if field == "event_namespace":
        return evidence_value == payload.event_namespace
    if field == "event_ref":
        return evidence_value == payload.event_ref
    if field == "method":
        return evidence_value == payload.method
    if field == "event_at":
        got = evidence_value
        if isinstance(got, str):
            try:
                got = datetime.fromisoformat(got)
            except ValueError:
                return False
        return _as_aware(got) == _as_aware(payload.event_at)
    if field == "receiver_name":
        details = payload.receipt_details
        name = getattr(details, "receiver_name", None) if details else None
        # The name is a free-text read; when details carry one it must agree.
        return name is None or str(evidence_value).strip() == name.strip()
    return True


def validate_advance_receipt(payload, proof_source_ids: set[str],
                             receipt_sources: list) -> list[str]:
    """Reasons a reported RECEIVED is not yet a confirmed, sourced receipt.

    A RECEIVED claim is only bookkeeping until every required fact is read
    from a retained B5 proof source (human source review, READ state) with the
    source belonging to this case, and the method-specific receipt condition
    holds. The result is a list of issue strings; empty means evidence-ok. This
    never calls OCR/LLM/signature recognition and never edits the source.
    """
    if payload.reported_status != _FINAL_RECEIVED:
        return []

    issues: list[str] = []
    by_field: dict[str, list] = {}
    for entry in payload.evidence:
        by_field.setdefault(entry.field, []).append(entry)

    for field in _RECEIPT_REQUIRED_FIELDS:
        entries = by_field.get(field, [])
        if not entries:
            issues.append(f"Thiếu căn cứ đã đọc cho trường {field}.")
            continue
        if len(entries) > 1:
            issues.append(f"Trường {field} có nhiều hơn một căn cứ; không rõ.")
            continue
        entry = entries[0]
        if entry.source_id not in proof_source_ids:
            issues.append(
                f"Căn cứ {field} không thuộc chứng từ ứng đã ghi nhận.")
        if entry.origin != "HUMAN_SOURCE_REVIEW":
            issues.append(f"Căn cứ {field} không phải người đọc nguồn.")
        if entry.read_state != "READ":
            issues.append(f"Căn cứ {field} chưa được đọc rõ (không READ).")
        if not (entry.locator or "").strip():
            issues.append(f"Căn cứ {field} thiếu vị trí (locator).")
        if entry.raw is None or not str(entry.raw).strip():
            issues.append(f"Căn cứ {field} thiếu nội dung nguyên văn.")
        if entry.read_state == "READ" and not _value_matches(
                field, entry.value, payload):
            issues.append(f"Căn cứ {field} không khớp dữ kiện sự kiện.")

    # Method-specific receipt condition + configured source.
    method_sources = {s.namespace for s in receipt_sources
                      if s.method == payload.method}
    if not method_sources:
        issues.append(
            "Chưa cấu hình nguồn chi cho phương thức này; không ghi nhận "
            "mới khi thiếu cấu hình.")
    elif payload.event_namespace not in method_sources:
        issues.append(
            "Nguồn chi không thuộc cấu hình cho phương thức đã chọn.")

    details = payload.receipt_details
    if payload.method == "BANK_TRANSFER":
        scope = getattr(details, "proof_scope", None) if details else None
        if scope != "RECEIVER_CONFIRMED":
            issues.append(
                "Chuyển khoản chưa đủ căn cứ người hưởng nhận "
                "(proof_scope phải là RECEIVER_CONFIRMED).")
    elif payload.method == "CASH":
        ack = getattr(details, "acknowledgement", None) if details else None
        if ack != "ACKNOWLEDGED":
            issues.append(
                "Phiếu chi chưa có xác nhận giao/nhận "
                "(acknowledgement phải là ACKNOWLEDGED).")
        voucher = getattr(details, "voucher_number", None) if details else None
        if not voucher or voucher != payload.event_ref:
            issues.append(
                "Số phiếu chi phải khớp mã sự kiện (event_ref) của phiếu.")
    return issues


def _is_confirmed_receipt(event: B3AdvanceEventView) -> bool:
    """A canonical confirmed RECEIVED to the right employee, company-paid."""
    return (event.reported_status == _FINAL_RECEIVED
            and event.classification == "CONFIRMED_RECEIPT"
            and event.payer_side == "COMPANY"
            and event.gross_vnd is not None)


def _superseded_ids(events: list[B3AdvanceEventView]) -> set[str]:
    """Ids of nonfinal events a later final event of the same identity replaces.

    A pending/unknown event stays in history but, once a final RECEIVED/FAILED/
    CANCELLED for the same economic identity (namespace+ref) or an explicit
    ``supersedes_event_id`` arrives, it no longer makes the total uncertain.
    """
    superseded: set[str] = set()
    for later in events:
        if later.supersedes_event_id:
            superseded.add(later.supersedes_event_id)
        if later.reported_status not in ("RECEIVED", "FAILED", "CANCELLED"):
            continue
        for earlier in events:
            if earlier.id == later.id:
                continue
            if (earlier.reported_status in _NONFINAL
                    and later.event_namespace is not None
                    and later.event_namespace == earlier.event_namespace
                    and later.event_ref is not None
                    and later.event_ref == earlier.event_ref):
                superseded.add(earlier.id)
    return superseded


def project_b3_funding(decision: B3DecisionView | None,
                       events: list[B3AdvanceEventView],
                       stop_active: bool) -> B3FundingSummary:
    """Aggregate managed advance events against the approval.

    Only canonical confirmed RECEIVED events to the correct employee, paid by
    the company, count toward ``recorded_received_vnd``/``fulfilled_vnd``. Final
    gross is never clipped: overpayment keeps the raw sum and adds an OVERPAY
    incident. Unknown/pending/conflict events make the total uncertain
    (``remaining_vnd`` null) while keeping the known subtotal.
    """
    approved = None
    if decision is not None and decision.outcome == "APPROVE":
        approved = decision.advance_vnd

    superseded = _superseded_ids(events)
    active = [e for e in events if e.id not in superseded]

    incidents: list[B3FundingIncident] = []
    for event in active:
        incidents.extend(event.incidents)

    recorded: int | None = None
    if active:
        confirmed = [e for e in active if _is_confirmed_receipt(e)]
        recorded = sum(e.gross_vnd for e in confirmed) if confirmed else None

    pending_count = sum(1 for e in active
                        if e.reported_status in ("PENDING", "UNCONFIRMED"))
    unknown_count = sum(1 for e in active
                        if e.reported_status == "RECEIVED"
                        and e.gross_vnd is None)

    # Uncertainty: a nonfinal/unknown/conflict event, or an incident that
    # affects the total, means remaining cannot be asserted.
    uncertain = (pending_count > 0 or unknown_count > 0
                 or any(e.classification in ("UNCONFIRMED", "CONFLICT")
                        for e in active))

    fulfilled: int | None = None
    remaining: int | None = None
    if approved is not None:
        if recorded is None:
            fulfilled = None if uncertain else 0
            remaining = None if uncertain else approved
        else:
            fulfilled = min(recorded, approved)
            if uncertain:
                remaining = None
            else:
                remaining = max(approved - recorded, 0)
    elif recorded is not None:
        # No approved obligation: recorded money with no decision is unallocated.
        incidents.append(B3FundingIncident(
            kind="UNAUTHORIZED_OR_UNALLOCATED",
            event_ids=[e.id for e in active], refs=[],
            amount_vnd=recorded,
            reason="Có tiền thực nhận nhưng chưa gắn quyết định hợp lệ."))
        fulfilled = None
        remaining = None

    # Overpay: raw sum exceeds the approved amount.
    if approved is not None and recorded is not None and recorded > approved:
        incidents.append(B3FundingIncident(
            kind="OVERPAY", event_ids=[e.id for e in active], refs=[],
            amount_vnd=recorded - approved,
            reason="Số thực nhận vượt số đã duyệt; giữ gross, cần xử lý."))

    status = _status(approved, recorded, uncertain, incidents, active)
    if stop_active and status == "FULFILLED":
        # Stop does not auto-advance; facts are kept but not marked complete.
        status = "PARTIAL"

    scope = (f"decision:{decision.id}" if decision is not None
             else "unallocated")
    return B3FundingSummary(
        decision_id=decision.id if decision is not None else None,
        approved_vnd=approved,
        recorded_received_vnd=recorded,
        fulfilled_vnd=fulfilled,
        remaining_vnd=remaining,
        pending_count=pending_count,
        unknown_count=unknown_count,
        incidents=incidents,
        status=status,
        scope=scope,
        as_of=events[-1].created_at if events else None,
    )


def _status(approved: int | None, recorded: int | None, uncertain: bool,
            incidents: list[B3FundingIncident],
            events: list[B3AdvanceEventView]) -> str:
    blocking = [i for i in incidents
                if i.kind in ("OVERPAY", "WRONG_RECIPIENT",
                              "UNAUTHORIZED_OR_UNALLOCATED",
                              "CONFLICTING_OUTCOME")]
    if blocking:
        return "NEEDS_RESOLUTION"
    if not events:
        return "NOT_RECORDED"
    if uncertain:
        return "PENDING" if any(e.reported_status == "PENDING" for e in events) \
            else "UNCONFIRMED"
    if approved is not None and recorded is not None and recorded >= approved:
        return "FULFILLED"
    if recorded is not None and recorded > 0:
        return "PARTIAL"
    return "NOT_RECORDED"


def derive_classification(payload, employee_ref: str,
                          incidents: list[B3FundingIncident], *,
                          evidence_ok: bool) -> str:
    """Derive an event's classification from its own facts (never free text).

    RECEIVED is CONFIRMED_RECEIPT only when it reaches the right employee paid
    by the company with a known gross AND ``evidence_ok`` (the caller's guard
    found every required sourced fact). The guard result is passed explicitly —
    it is never defaulted to True, so an unproven RECEIVED stays UNCONFIRMED.
    A conflicting outcome is CONFLICT; otherwise the reported status maps
    directly.
    """
    if any(i.kind == "CONFLICTING_OUTCOME" for i in incidents):
        return "CONFLICT"
    if payload.reported_status == "RECEIVED":
        if (evidence_ok and payload.payer_side == "COMPANY"
                and payload.gross_vnd is not None
                and payload.payee_ref == employee_ref):
            return "CONFIRMED_RECEIPT"
        return "UNCONFIRMED"
    if payload.reported_status == "PENDING":
        return "PENDING"
    if payload.reported_status in ("FAILED", "CANCELLED"):
        return "NO_RECEIPT"
    return "UNCONFIRMED"

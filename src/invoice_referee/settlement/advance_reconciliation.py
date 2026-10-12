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

from invoice_referee.settlement.models import (
    B3AdvanceEventView,
    B3DecisionView,
    B3FundingIncident,
    B3FundingSummary,
)

_NONFINAL = ("PENDING", "FAILED", "CANCELLED", "UNCONFIRMED")
_FINAL_RECEIVED = "RECEIVED"


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
                          incidents: list[B3FundingIncident]) -> str:
    """Derive an event's classification from its own facts (never free text).

    RECEIVED is CONFIRMED_RECEIPT only when it reaches the right employee paid
    by the company with a known gross; a conflicting outcome is CONFLICT;
    otherwise the reported status maps directly.
    """
    if any(i.kind == "CONFLICTING_OUTCOME" for i in incidents):
        return "CONFLICT"
    if payload.reported_status == "RECEIVED":
        if (payload.payer_side == "COMPANY" and payload.gross_vnd is not None
                and payload.payee_ref == employee_ref):
            return "CONFIRMED_RECEIPT"
        return "UNCONFIRMED"
    if payload.reported_status == "PENDING":
        return "PENDING"
    if payload.reported_status in ("FAILED", "CANCELLED"):
        return "NO_RECEIPT"
    return "UNCONFIRMED"

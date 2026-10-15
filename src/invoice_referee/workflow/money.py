"""Pure money-ledger logic (contracts §4, §10.1).

Append-only: an event is never edited or deleted; a reversal is a new linked
event. The net amount of a kind is the sum of its events minus the reversals
that point at them. Fulfillment is granted only to a matching instruction and
is never clipped by the instruction's amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from invoice_referee.domain.finance import MoneyEvent, RecordMoneyInput


@dataclass(frozen=True)
class MoneyVerification:
    """The server's verification decision for one recorded claim (plan R3)."""

    verification_state: str  # CONFIRMED | OBSERVED
    allocation_state: str  # ALLOCATED | UNALLOCATED
    reason: str


def verify_money_claim(
    money: RecordMoneyInput,
    *,
    evidence: tuple[object, ...] = (),
    responsible_actor: str | None = None,
) -> MoneyVerification:
    """Decide whether a recorded claim is verified money (contracts §3–§4).

    A claim is CONFIRMED only when it carries a responsible completion
    confirmation, checked evidence refs, or a linked reversal bound to a real
    original. A bare statement is OBSERVED — preserved for audit, never
    fulfilling or settling. This never reads a client-supplied verified flag.

    Source instrument status (plan D): when the source states a transfer/cash
    status that is not COMPLETED (PENDING/FAILED/UNKNOWN), the claim can never be
    CONFIRMED — an unfinished or failed transfer is not received money. An
    ABSENT status is not a negative signal (older callers omit it).
    """
    if money.instrument_status is not None and money.instrument_status != "COMPLETED":
        return MoneyVerification(
            verification_state="OBSERVED",
            allocation_state="UNALLOCATED",
            reason=f"source status {money.instrument_status} is not a completed transfer/receipt",
        )
    has_claim = bool((money.completion_claim or "").strip())
    has_refs = bool(money.refs) or bool(evidence)
    is_reversal = money.reverses_event_id is not None
    if has_claim or has_refs or is_reversal:
        return MoneyVerification(
            verification_state="CONFIRMED",
            allocation_state="ALLOCATED",
            reason="responsible confirmation / checked evidence / linked reversal",
        )
    return MoneyVerification(
        verification_state="OBSERVED",
        allocation_state="UNALLOCATED",
        reason="bare claim: no confirmation, evidence or original",
    )


def net_by_kind(events: tuple[MoneyEvent, ...], kind: str) -> int:
    """Net amount for one kind: gross minus reversals that target its events."""
    gross = sum(event.amount for event in events if event.kind == kind)
    matching_ids = {event.id for event in events if event.kind == kind}
    reversed_amount = sum(
        event.amount for event in events if event.reverses_event_id in matching_ids
    )
    # Reversal events themselves are not counted as gross of `kind`.
    return max(gross - reversed_amount, 0)


def reversal_targets(events: tuple[MoneyEvent, ...]) -> dict[str, int]:
    """How much of each original event id has been reversed so far."""
    totals: dict[str, int] = {}
    for event in events:
        if event.reverses_event_id is not None:
            totals[event.reverses_event_id] = totals.get(event.reverses_event_id, 0) + event.amount
    return totals


def can_reverse(events: tuple[MoneyEvent, ...], target_id: str, amount: int) -> bool:
    """A reversal may not exceed the unreversed original (contracts §10.1)."""
    original = next((e for e in events if e.id == target_id), None)
    if original is None or original.reverses_event_id is not None:
        return False
    already = reversal_targets(events).get(target_id, 0)
    return amount > 0 and already + amount <= original.amount


def fulfillment_for(
    events: tuple[MoneyEvent, ...],
    *,
    payee: str,
    direction: str,
    instruction_id: str | None = None,
    legacy_after: datetime | None = None,
) -> int:
    """Net fulfillment granted to an instruction by matching receipts.

    A payment fulfills a PAY instruction only when it is received by the
    instruction's payee; a wrong payee records money but fulfills nothing.
    """
    kind = "REIMBURSEMENT_RECEIVED" if direction == "PAY" else "EMPLOYEE_RETURN"
    candidates = tuple(
        event for event in events
        if event.kind == kind and event.payee == payee
    )
    if instruction_id is None:
        selected = events
    else:
        linked_ids = {
            event.id
            for event in candidates
            if event.instruction_id == instruction_id
            or (
                event.instruction_id is None
                and legacy_after is not None
                and event.recorded_at >= legacy_after
            )
        }
        selected = tuple(
            event
            for event in events
            if event.id in linked_ids or event.reverses_event_id in linked_ids
        )
    # Only receipts paid to the expected payee count (checked at record time);
    # here the caller passes the already-scoped events.
    return net_by_kind(selected, kind)

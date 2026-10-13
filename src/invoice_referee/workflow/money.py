"""Pure money-ledger logic (contracts §4, §10.1).

Append-only: an event is never edited or deleted; a reversal is a new linked
event. The net amount of a kind is the sum of its events minus the reversals
that point at them. Fulfillment is granted only to a matching instruction and
is never clipped by the instruction's amount.
"""

from __future__ import annotations

from invoice_referee.domain.finance import MoneyEvent


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
    events: tuple[MoneyEvent, ...], *, payee: str, direction: str
) -> int:
    """Net fulfillment granted to an instruction by matching receipts.

    A payment fulfills a PAY instruction only when it is received by the
    instruction's payee; a wrong payee records money but fulfills nothing.
    """
    if direction == "PAY":
        received = net_by_kind(events, "REIMBURSEMENT_RECEIVED")
    else:
        received = net_by_kind(events, "EMPLOYEE_RETURN")
    # Only receipts paid to the expected payee count (checked at record time);
    # here the caller passes the already-scoped events.
    return received

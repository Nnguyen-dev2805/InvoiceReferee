from datetime import UTC, datetime

from invoice_referee.domain.finance import MoneyEvent
from invoice_referee.workflow.money import fulfillment_for


def _event(
    event_id: str,
    kind: str,
    amount: int,
    *,
    instruction_id: str | None,
    reverses_event_id: str | None = None,
) -> MoneyEvent:
    now = datetime(2026, 10, 15, tzinfo=UTC)
    return MoneyEvent(
        id=event_id,
        external_key=f"bank:{event_id}",
        kind=kind,
        scope="activity:money-test",
        payer="company:demo" if kind == "REIMBURSEMENT_RECEIVED" else "employee:employee-a",
        payee="employee:employee-a" if kind == "REIMBURSEMENT_RECEIVED" else "company:demo",
        amount=amount,
        event_at=now,
        recorded_at=now,
        verification_state="CONFIRMED",
        allocation_state="ALLOCATED",
        reverses_event_id=reverses_event_id,
        instruction_id=instruction_id,
    )


def test_fulfillment_uses_only_the_named_instruction_and_its_reversals() -> None:
    events = (
        _event("old-pay", "REIMBURSEMENT_RECEIVED", 900_000, instruction_id="instruction:old"),
        _event("current-pay", "REIMBURSEMENT_RECEIVED", 2_000_000, instruction_id="instruction:current"),
        _event(
            "reverse-current",
            "REVERSAL",
            500_000,
            instruction_id="instruction:current",
            reverses_event_id="current-pay",
        ),
        _event("return", "EMPLOYEE_RETURN", 300_000, instruction_id="instruction:collect"),
    )

    assert fulfillment_for(
        events,
        payee="employee:employee-a",
        direction="PAY",
        instruction_id="instruction:current",
    ) == 1_500_000
    assert fulfillment_for(
        events,
        payee="company:demo",
        direction="COLLECT",
        instruction_id="instruction:collect",
    ) == 300_000


def test_legacy_fulfillment_without_an_instruction_id_keeps_old_behavior() -> None:
    events = (
        _event("legacy-a", "EMPLOYEE_RETURN", 100_000, instruction_id=None),
        _event("legacy-b", "EMPLOYEE_RETURN", 200_000, instruction_id=None),
    )

    assert fulfillment_for(events, payee="company:demo", direction="COLLECT") == 300_000

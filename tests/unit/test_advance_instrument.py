"""D: recording actual advance money from a document — status/kind discipline.

The accountant's "Ghi nhận tiền ứng thực nhận" form reports the instrument
method and the SOURCE status; the SERVER decides verification. A source status
that is not COMPLETED (pending/failed/unclear) never becomes confirmed received
money. An unfinished/failed transfer is not A.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.workflow.money import verify_money_claim

NOW = datetime(2026, 10, 12, tzinfo=UTC)


def _money(*, status: str | None, method: str | None = "TRANSFER", claim: str | None = "Đã nhận đủ") -> RecordMoneyInput:
    return RecordMoneyInput(
        external_key="bank:ADV-F01",
        claimed_kind="ADVANCE_RECEIVED",
        claimed_scope="activity:1",
        payer="company:demo",
        payee="employee:a",
        amount=4_000_000,
        event_at=NOW,
        completion_claim=claim,
        reason="ghi nhận ứng thực nhận",
        instrument_method=method,  # type: ignore[arg-type]
        instrument_status=status,  # type: ignore[arg-type]
    )


def test_completed_transfer_with_responsible_confirmation_confirms() -> None:
    result = verify_money_claim(_money(status="COMPLETED"), responsible_actor="employee:accountant-demo")
    assert result.verification_state == "CONFIRMED"


def test_pending_transfer_never_confirms() -> None:
    result = verify_money_claim(_money(status="PENDING"), responsible_actor="employee:accountant-demo")
    assert result.verification_state == "OBSERVED"
    assert result.allocation_state == "UNALLOCATED"


def test_failed_transfer_never_confirms() -> None:
    result = verify_money_claim(_money(status="FAILED"), responsible_actor="employee:accountant-demo")
    assert result.verification_state == "OBSERVED"


def test_unknown_status_never_confirms() -> None:
    result = verify_money_claim(_money(status="UNKNOWN"), responsible_actor="employee:accountant-demo")
    assert result.verification_state == "OBSERVED"


def test_absent_status_does_not_block_a_confirmed_claim() -> None:
    # Backward compatibility: an older caller that omits the status is judged on
    # its confirmation/refs as before.
    result = verify_money_claim(_money(status=None), responsible_actor="employee:accountant-demo")
    assert result.verification_state == "CONFIRMED"


def test_record_money_input_rejects_unknown_instrument_method() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _money(status="COMPLETED", method="CHEQUE")

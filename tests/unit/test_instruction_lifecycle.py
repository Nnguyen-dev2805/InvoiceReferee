"""The instruction retain/suspend/replace decision, pure (contracts §10.1; R3)."""

from __future__ import annotations

from invoice_referee.workflow.instructions import InstructionState, reconcile_instruction


def _active(**overrides: object) -> InstructionState:
    fields = {
        "id": "i:1",
        "direction": "PAY",
        "amount": 4_000_000,
        "cost_basis": "basis-a",
        "fulfilled_amount": 0,
        "execution_state": "NOT_STARTED",
        "status": "ISSUED",
    }
    fields.update(overrides)
    return InstructionState(**fields)  # type: ignore[arg-type]


def test_no_active_instruction_issues() -> None:
    d = reconcile_instruction(None, direction="PAY", amount=4_000_000, cost_basis="a")
    assert d.action == "ISSUE"


def test_same_basis_direction_amount_retains() -> None:
    d = reconcile_instruction(
        _active(), direction="PAY", amount=4_000_000, cost_basis="basis-a"
    )
    assert d.action == "RETAIN"


def test_partial_remaining_is_the_retain_comparison() -> None:
    # I4 fulfilled2 => remaining2; a receipt that keeps S=2 retains the order.
    d = reconcile_instruction(
        _active(fulfilled_amount=2_000_000, status="PARTIAL"),
        direction="PAY",
        amount=2_000_000,
        cost_basis="basis-a",
    )
    assert d.action == "RETAIN"


def test_unresolved_execution_blocks_replacement() -> None:
    d = reconcile_instruction(
        _active(execution_state="OPEN", cost_basis="basis-old"),
        direction="PAY",
        amount=4_000_000,
        cost_basis="basis-new",
    )
    assert d.action == "SUSPEND"
    assert d.result_state == "WAITING"


def test_suspended_remainder_reactivates() -> None:
    d = reconcile_instruction(
        _active(status="SUSPENDED"), direction="PAY", amount=4_000_000, cost_basis="basis-a"
    )
    assert d.action == "REACTIVATE"


def test_handed_off_unknown_stays_waiting_on_reactivate() -> None:
    d = reconcile_instruction(
        _active(status="SUSPENDED", execution_state="UNKNOWN"),
        direction="PAY",
        amount=4_000_000,
        cost_basis="basis-a",
    )
    assert d.action == "REACTIVATE"
    assert d.result_state == "WAITING"


def test_changed_basis_replaces() -> None:
    d = reconcile_instruction(
        _active(cost_basis="basis-old"),
        direction="PAY",
        amount=4_000_000,
        cost_basis="basis-new",
    )
    assert d.action == "REPLACE"

"""T7: actual money, fulfillment, overpay, reversal and supplement (contracts §4, §10.1).

Money is append-only and the actual projection is never clipped to an
instruction's amount. Fulfillment is granted only to the matching instruction;
a reversal reopens the net remaining; the client can never set verified/origin
or the net effect.
"""

from __future__ import annotations

import pytest


async def test_partial_payment_keeps_one_remaining(app_fixture):
    # E6/A2 => I4. Record P2 => S2, the SAME instruction keeps remaining2.
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    assert v.instructions[0].amount == 4_000_000
    paid = await app_fixture.record_received(instruction_amount=4_000_000, received=2_000_000)
    assert paid.actual_money.P.value == 2_000_000
    assert len(paid.instructions) == 1
    assert paid.instructions[0].fulfilled_amount == 2_000_000
    assert paid.instructions[0].remaining == 2_000_000


async def test_actual_overpay_not_clipped(app_fixture):
    v = await app_fixture.record_received(instruction_amount=4_000_000, received=5_000_000)
    assert v.actual_money.P.value == 5_000_000
    assert v.instructions[0].fulfilled_amount == 4_000_000
    assert v.issues  # overpay is an incident, not silently absorbed


async def test_wrong_payee_is_not_a_fulfillment(app_fixture):
    v = await app_fixture.record_received(
        instruction_amount=4_000_000, received=2_000_000, payee="vendor:other"
    )
    # Money recorded (it really moved) but it does not fulfill the instruction.
    assert v.instructions[0].fulfilled_amount == 0


async def test_duplicate_external_key_is_not_counted_twice(app_fixture):
    first = await app_fixture.record_received(
        instruction_amount=4_000_000, received=2_000_000, external_key="bank:txn-1"
    )
    second = await app_fixture.record_received(
        instruction_amount=4_000_000, received=2_000_000, external_key="bank:txn-1"
    )
    assert second.actual_money.P.value == 2_000_000  # not 4m


async def test_reversal_reopens_net_remaining(app_fixture):
    # I4 -> P2 -> reverse2 => P0, remaining4.
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    await app_fixture.record_received(instruction_amount=4_000_000, received=2_000_000)
    reversed_v = await app_fixture.reverse_last_received()
    assert reversed_v.actual_money.P.value == 0
    assert reversed_v.instructions[0].remaining == 4_000_000


async def test_reversal_leaves_partial_net(app_fixture):
    # I4 -> P4 -> reverse1 => net P3, remaining1; not SETTLED.
    await app_fixture.submit_packet("coverage-e6", mode="STUB")
    await app_fixture.record_received(instruction_amount=4_000_000, received=4_000_000)
    v = await app_fixture.reverse_last_received(amount=1_000_000)
    assert v.actual_money.P.value == 3_000_000
    assert v.state != "SETTLED"


async def test_bare_receipt_without_proof_does_not_settle(app_fixture):
    # A bare money claim with no completion claim and no refs is not verified
    # money (contracts §3–§4): it is preserved for audit but must not fulfill
    # the instruction or settle the case.
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")  # I4
    assert v.instructions[0].amount == 4_000_000
    after = await app_fixture.record_received(
        instruction_amount=4_000_000,
        received=4_000_000,
        completion_claim=None,
    )
    assert after.instructions[0].fulfilled_amount == 0
    assert after.state != "SETTLED"
    row = app_fixture.query_one(
        "SELECT verification_state FROM money_events "
        "WHERE kind = 'REIMBURSEMENT_RECEIVED' ORDER BY recorded_at DESC LIMIT 1"
    )
    assert row is not None and row["verification_state"] == "OBSERVED"


async def test_confirmed_receipt_with_proof_settles(app_fixture):
    # The same receipt with a responsible completion claim is verified money:
    # it fulfills the instruction and settles the case.
    await app_fixture.submit_packet("coverage-e6", mode="STUB")
    after = await app_fixture.record_received(
        instruction_amount=4_000_000,
        received=4_000_000,
        completion_claim="Đã nhận đủ, đối chiếu sao kê ngân hàng",
    )
    assert after.instructions[0].fulfilled_amount == 4_000_000
    assert after.state == "SETTLED"

"""T7: actual money, fulfillment, overpay, reversal and supplement (contracts §4, §10.1).

Money is append-only and the actual projection is never clipped to an
instruction's amount. Fulfillment is granted only to the matching instruction;
a reversal reopens the net remaining; the client can never set verified/origin
or the net effect.
"""

from __future__ import annotations

import pytest
from invoice_referee.api.routes import SESSION_COOKIE


def _accountant_client(app_fixture):
    client = app_fixture.fresh_client()
    client.cookies.set(
        SESSION_COOKIE,
        app_fixture.session_for(
            tenant="tenant:demo",
            actor="employee:accountant-demo",
            persona="accountant",
        ),
    )
    return client


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
    # New P/R entries must be tied to a source document; a bare claim cannot be
    # written into the actual ledger or fulfill the instruction.
    from invoice_referee.workflow.service import UnsupportedCommandError

    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")  # I4
    assert v.instructions[0].amount == 4_000_000
    with pytest.raises(UnsupportedCommandError, match="chứng từ thực tế"):
        await app_fixture.record_received(
            instruction_amount=4_000_000,
            received=4_000_000,
            completion_claim=None,
            refs=(),
        )
    assert app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE kind = 'REIMBURSEMENT_RECEIVED'"
    )["n"] == 0


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


async def test_supplemental_payment_is_bound_to_one_instruction_and_idempotent(app_fixture):
    view = await app_fixture.submit_packet("money-i4", mode="STUB")
    instruction = view.instructions[0]
    assert instruction.direction == "PAY"
    source = view.sources[0]
    client = _accountant_client(app_fixture)

    def payload(command_id: str, version: int):
        return client.post(
            f"/api/cases/{view.id}/actuals",
            headers={
                "X-Command-Id": command_id,
                "X-Expected-Version": str(version),
            },
            json={
                "money": {
                    "external_key": "transfer:SUPPLEMENT-001",
                    "claimed_kind": "REIMBURSEMENT_RECEIVED",
                    "claimed_scope": view.activity,
                    "payer": "company:demo",
                    "payee": "employee:employee-a",
                    "amount": 2_000_000,
                    "event_at": "2026-10-10T10:00:00+07:00",
                    "completion_claim": "Kế toán xác nhận đã đối chiếu chứng từ chuyển khoản.",
                    "reason": "Ghi nhận khoản công ty đã chi bổ sung.",
                    "instrument_method": "TRANSFER",
                    "instrument_status": "COMPLETED",
                    "instrument_reference": "SUPPLEMENT-001",
                    "instruction_id": instruction.id,
                    "refs": [{
                        "source_id": source.id,
                        "source_sha256": source.digest,
                        "page": 1,
                        "exact_quote": "Chứng từ chi bổ sung đã xác nhận",
                    }],
                }
            },
        )

    first = await payload("cmd:pay-bound-first", view.version)
    assert first.status_code == 200, first.text
    first_view = first.json()["case_view"]
    events = [event for event in first_view["money_history"] if event["kind"] == "REIMBURSEMENT_RECEIVED"]
    assert len(events) == 1
    assert events[0]["instruction_id"] == instruction.id
    assert first_view["instructions"][0]["fulfilled_amount"] == 2_000_000

    second = await payload("cmd:pay-bound-retry", first_view["version"])
    assert second.status_code == 200, second.text
    second_view = second.json()["case_view"]
    events = [event for event in second_view["money_history"] if event["kind"] == "REIMBURSEMENT_RECEIVED"]
    assert len(events) == 1
    assert second_view["instructions"][0]["remaining"] == 2_000_000


async def test_actual_pay_cannot_be_recorded_without_the_active_instruction_id(app_fixture):
    view = await app_fixture.submit_packet("money-i4", mode="STUB")
    source = view.sources[0]
    client = _accountant_client(app_fixture)
    response = await client.post(
        f"/api/cases/{view.id}/actuals",
        headers={
            "X-Command-Id": "cmd:pay-unbound",
            "X-Expected-Version": str(view.version),
        },
        json={"money": {
            "external_key": "transfer:UNBOUND-001",
            "claimed_kind": "REIMBURSEMENT_RECEIVED",
            "claimed_scope": view.activity,
            "payer": "company:demo",
            "payee": "employee:employee-a",
            "amount": 1_000_000,
            "event_at": "2026-10-10T10:00:00+07:00",
            "completion_claim": "Kế toán xác nhận đã đối chiếu chứng từ chuyển khoản.",
            "reason": "Ghi nhận khoản công ty đã chi bổ sung.",
            "instrument_method": "TRANSFER",
            "instrument_status": "COMPLETED",
            "instrument_reference": "UNBOUND-001",
            "refs": [{
                "source_id": source.id,
                "source_sha256": source.digest,
                "page": 1,
                "exact_quote": "Chứng từ chi bổ sung",
            }],
        }},
    )

    assert response.status_code == 400, response.text
    assert app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (view.id,)
    )["n"] == 0


async def test_payment_rejects_stale_wrong_direction_and_foreign_root_instructions(app_fixture):
    first = await app_fixture.submit_packet("money-i4", activity="activity:travel-a")
    other = await app_fixture.submit_packet("dup-invoice", activity="activity:travel-b")
    pay = first.instructions[0]
    foreign_pay = other.instructions[0]
    source = first.sources[0]
    client = _accountant_client(app_fixture)

    async def submit(command_id: str, instruction_id: str, kind: str = "REIMBURSEMENT_RECEIVED"):
        return await client.post(
            f"/api/cases/{first.id}/actuals",
            headers={
                "X-Command-Id": command_id,
                "X-Expected-Version": str(app_fixture.workflow._query_one(
                    "SELECT version FROM cases WHERE id = ?", (first.id,)
                )["version"]),
            },
            json={"money": {
                "external_key": f"transfer:{command_id}",
                "claimed_kind": kind,
                "claimed_scope": first.activity,
                "payer": "company:demo" if kind == "REIMBURSEMENT_RECEIVED" else "employee:employee-a",
                "payee": "employee:employee-a" if kind == "REIMBURSEMENT_RECEIVED" else "company:demo",
                "amount": 100_000,
                "event_at": "2026-10-10T10:00:00+07:00",
                "completion_claim": "Đã kiểm tra chứng từ giao dịch.",
                "reason": "Đã đối chiếu chứng từ thực tế.",
                "instrument_method": "TRANSFER",
                "instrument_status": "COMPLETED",
                "instrument_reference": command_id,
                "instruction_id": instruction_id,
                "refs": [{
                    "source_id": source.id,
                    "source_sha256": source.digest,
                    "page": 1,
                    "exact_quote": "Chứng từ giao dịch",
                }],
            }},
        )

    foreign = await submit("FOREIGN-INSTRUCTION", foreign_pay.id)
    wrong_direction = await submit("WRONG-DIRECTION", pay.id, "EMPLOYEE_RETURN")
    stale = await submit("STALE-INSTRUCTION", "instruction:already-closed")

    assert foreign.status_code == 409, foreign.text
    assert wrong_direction.status_code == 422, wrong_direction.text
    assert stale.status_code == 409, stale.text
    assert app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (first.id,)
    )["n"] == 0


async def test_fulfilled_instruction_rejects_a_new_transaction_but_allows_same_key_retry(app_fixture):
    view = await app_fixture.submit_packet("money-i4", mode="STUB")
    instruction = view.instructions[0]
    source = view.sources[0]
    client = _accountant_client(app_fixture)

    async def submit(command_id: str, key: str, amount: int, version: int):
        return await client.post(
            f"/api/cases/{view.id}/actuals",
            headers={"X-Command-Id": command_id, "X-Expected-Version": str(version)},
            json={"money": {
                "external_key": f"transfer:{key}",
                "claimed_kind": "REIMBURSEMENT_RECEIVED",
                "claimed_scope": view.activity,
                "payer": "company:demo",
                "payee": "employee:employee-a",
                "amount": amount,
                "event_at": "2026-10-10T10:00:00+07:00",
                "completion_claim": "Kế toán xác nhận đã đối chiếu chứng từ chuyển khoản.",
                "reason": "Ghi nhận khoản công ty đã chi bổ sung.",
                "instrument_method": "TRANSFER",
                "instrument_status": "COMPLETED",
                "instrument_reference": key,
                "instruction_id": instruction.id,
                "refs": [{
                    "source_id": source.id,
                    "source_sha256": source.digest,
                    "page": 1,
                    "exact_quote": "Chứng từ chi bổ sung đã xác nhận",
                }],
            }},
        )

    first = await submit("cmd:pay-fully", "SUPPLEMENT-FULL", 4_000_000, view.version)
    assert first.status_code == 200, first.text
    after_first = first.json()["case_view"]
    assert after_first["instructions"][0]["status"] == "FULFILLED"

    retry = await submit("cmd:pay-fully-retry", "SUPPLEMENT-FULL", 4_000_000, after_first["version"])
    assert retry.status_code == 200, retry.text
    assert len([
        event for event in retry.json()["case_view"]["money_history"]
        if event["kind"] == "REIMBURSEMENT_RECEIVED"
    ]) == 1

    new_transaction = await submit(
        "cmd:pay-stale-new", "SUPPLEMENT-AFTER-FULFILLED", 100_000,
        retry.json()["case_view"]["version"],
    )
    assert new_transaction.status_code == 409, new_transaction.text
    assert app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE root_id = ? AND kind = 'REIMBURSEMENT_RECEIVED'",
        (view.id,),
    )["n"] == 1

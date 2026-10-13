"""T6: routine submission and the actionable human path (contracts §5, §10.1–10.4).

A routine root with verified evidence becomes one actionable instruction with
no human recheck; a root missing a material fact becomes a FACT issue owned by
the right person, with no instruction. The workflow commits eligibility,
conclusion, instruction and usage atomically.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.commands import Answer, DecisionCommand


async def test_routine_issues_one_payment(app_fixture):
    v = await app_fixture.submit_packet("travel-clean", mode="STUB")
    assert len(v.instructions) == 1
    assert v.instructions[0].amount == 3_000_000
    assert v.state == "READY_TO_EXECUTE"
    assert v.conclusion is not None and v.conclusion.status == "OUTSTANDING"


async def test_missing_payer_becomes_fact_card_not_instruction(app_fixture):
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    assert v.instructions == ()
    assert v.state == "WAITING"
    assert any(issue.kind == "FACT" for issue in v.issues)
    # The card names the owner and is answerable.
    card = app_fixture.question_card(v.id, v.issues[0].id)
    assert card.owner
    assert card.required_answer


async def test_incomplete_funds_has_no_instruction(app_fixture):
    # Missing history coverage: no zero is asserted, so no S=0 balanced claim.
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    assert v.instructions == ()
    assert v.state in ("WAITING", "TECHNICAL_ERROR")


async def test_submit_is_idempotent_on_same_basis(app_fixture):
    first = await app_fixture.submit_packet("travel-clean", mode="STUB")
    second = await app_fixture.submit_packet("travel-clean", mode="STUB")
    assert first.instructions[0].id == second.instructions[0].id
    assert len(second.instructions) == 1  # retry does not issue a second order


async def test_answer_by_wrong_owner_does_not_resolve(app_fixture):
    # missing-history has no coverage, so the FACT issue is owned by the
    # accountant; an employee answering it must not resolve it.
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    issue = next(i for i in v.issues if i.kind == "FACT")
    assert issue.owner == "accountant"
    with pytest.raises(Exception):
        await app_fixture.answer(
            v.id,
            Answer(
                issue_id=issue.id,
                basis_id="basis:x",
                answer_kind="FACT",
                value="employee:employee-a",
                reason="tôi trả",
            ),
            actor="employee:employee-a",  # employee, not the accountant owner
        )


async def test_unproved_approval_does_not_resolve(app_fixture):
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    issue = v.issues[0]
    with pytest.raises(Exception):
        await app_fixture.decide(
            v.id,
            DecisionCommand(
                issue_ids=(issue.id,),
                basis_id="basis:forged",
                actions=("RECOGNIZE_COST",),
                effect_scope="activity:travel-a",
                reason="đồng ý",
            ),
            actor="employee:employee-a",  # employee holds no RECOGNIZE_COST grant
        )


async def test_existing_instruction_covers_obligation(app_fixture):
    # E6/A2 => I4; a retry/new command keeps the SAME instruction (no duplicate).
    first = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    assert len(first.instructions) == 1
    assert first.instructions[0].amount == 4_000_000
    retry = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    assert len(retry.instructions) == 1
    assert retry.instructions[0].id == first.instructions[0].id


async def test_same_invoice_two_roots_does_not_issue_twice(app_fixture):
    # The same economic invoice filed under two activities in one tenant must
    # not produce two instructions: the first root is the canonical owner.
    a = await app_fixture.submit_packet("dup-invoice", mode="STUB", activity="activity:travel-a")
    b = await app_fixture.submit_packet("dup-invoice", mode="STUB", activity="activity:travel-b")
    assert len(a.instructions) == 1
    # The second root must not get a duplicate instruction for the same invoice.
    assert b.instructions == ()


async def test_same_amount_changed_basis_supersedes(app_fixture):
    # I4 on basisX, then a verified replacement expenseY with the same S: the
    # old remainder is superseded and a single new instruction is actionable.
    first = await app_fixture.submit_packet("changed-basis", mode="STUB")
    assert len(first.instructions) == 1
    old_id = first.instructions[0].id
    second = await app_fixture.submit_packet("changed-basis-v2", mode="STUB")
    active = [i for i in second.instructions if i.status in ("ISSUED", "PARTIAL")]
    assert len(active) == 1
    assert active[0].id != old_id

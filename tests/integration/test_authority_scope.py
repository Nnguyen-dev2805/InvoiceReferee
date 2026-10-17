"""Authority is scoped and amount-bounded at the decision boundary (§5, §10.3).

A grant authorizes one action, one scope and an amount ceiling. A decision that
exceeds the grant's max_amount, or acts on a scope the grant does not cover,
must be refused — not silently accepted because the actor holds *some* grant.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import Decide
from invoice_referee.domain.issues import DecisionCommand
from invoice_referee.workflow.service import UnsupportedCommandError


async def _approver_ctx(app_fixture, root_id: str) -> CommandContext:
    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="approver", actor_id="employee:approver"
    )
    return CommandContext(
        session_id=session.session_id,
        actor_id="employee:approver",
        command_id=f"cmd:{root_id}:approve",
        expected_case_version=app_fixture._version(root_id),
    )


async def test_decision_over_grant_amount_is_refused(app_fixture,monkeypatch):
    # The approver grant ceiling is 20m; a 25m decision must be refused even
    # though the actor holds an ISSUE_PAYMENT grant.
    from tests.escalation_shapes import scenario
    v = await scenario(app_fixture,monkeypatch,cost=25_000_000,advance=25_000_000)
    issue = next(i for i in v.issues if i.kind == "AUTHORITY")
    ctx = await _approver_ctx(app_fixture, v.id)
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(
            ctx,
            Decide(
                root_id=v.id,
                decision=DecisionCommand(
                    issue_ids=(issue.id,),
                    basis_id=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id).basis_id,
                    actions=("RECOGNIZE_COST",),
                    effect_scope="activity:travel-a",
                    amount=25_000_000,
                    reason="vượt hạn mức",
                ),
            ),
        )


async def test_decision_within_grant_amount_is_accepted(app_fixture,monkeypatch):
    # 20m is exactly the ceiling and is accepted (inclusive).
    from tests.escalation_shapes import scenario
    v = await scenario(app_fixture,monkeypatch,cost=20_000_000,advance=20_000_000)
    issue = next(i for i in v.issues if i.kind == "AUTHORITY")
    ctx = await _approver_ctx(app_fixture, v.id)
    result = await app_fixture.workflow.execute(
        ctx,
        Decide(
            root_id=v.id,
            decision=DecisionCommand(
                issue_ids=(issue.id,),
                basis_id=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id).basis_id,
                actions=("RECOGNIZE_COST",),
                effect_scope="activity:travel-a",
                amount=20_000_000,
                reason="trong hạn mức",
            ),
        ),
    )
    assert result.case_view is not None

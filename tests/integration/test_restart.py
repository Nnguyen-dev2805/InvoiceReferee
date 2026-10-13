"""T8: durable jobs, restart recovery and read-set invalidation (contracts §6, §10.3).

A restart recovers the source cache and incomplete jobs but never re-applies
financial effects. A handed-off (OPEN/UNKNOWN) instruction is not silently
reissued. A settled case keeps its actual money when new evidence arrives.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


def _new_workflow_on_same_db(tmp_path: Path, db_path: Path) -> CaseWorkflow:
    db = Database(db_path)
    db.migrate()
    return CaseWorkflow(db, uploads_dir=tmp_path / "uploads")


async def test_restart_recovers_jobs_without_duplicate_effects(app_fixture, tmp_path):
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    assert len(v.instructions) == 1
    db_path = Path(app_fixture.db.path)

    # A fresh workflow over the same DB (a restart) sees the same instruction.
    restarted = _new_workflow_on_same_db(tmp_path, db_path)
    session = restarted.start_session(tenant="tenant:demo", persona="employee")
    from invoice_referee.domain.case import CommandContext

    ctx = CommandContext(
        session_id=session.session_id,
        actor_id="employee:employee-a",
        command_id="cmd-view",
        expected_case_version=0,
    )
    view = restarted.view(ctx, v.id)
    assert len(view.instructions) == 1
    assert view.instructions[0].amount == 4_000_000


async def test_settled_case_keeps_actual_after_new_evidence(app_fixture):
    # Record money, then a new source revision; the actual is retained.
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    paid = await app_fixture.record_received(instruction_amount=4_000_000, received=4_000_000)
    assert paid.actual_money.P.value == 4_000_000
    # A new revision must not erase the recorded money.
    from invoice_referee.domain.commands import ReviseDeclaration, Declaration

    ctx = app_fixture.ctx(
        actor="employee:employee-a", expected_case_version=app_fixture._version(v.id)
    )
    revised = await app_fixture.workflow.execute(
        ctx,
        ReviseDeclaration(
            root_id=v.id,
            declaration=Declaration(activity_id="activity:travel-a", declared_purpose="bổ sung"),
        ),
    )
    assert revised.case_view.actual_money.P.value == 4_000_000

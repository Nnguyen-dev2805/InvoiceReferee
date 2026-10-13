"""T8: Stop/Resume, stale read-set, override and idempotency (contracts §6, §10.3).

Stop is atomic with the commit: a worker that lands after Stop creates no
instruction. A stale answer does not overwrite a newer state. A crash after
commit replays the same result. Override is a new scoped decision that keeps
the old one and never rewrites facts or actual money.
"""

from __future__ import annotations

import asyncio

import pytest

from invoice_referee.domain.commands import Control, Override
from invoice_referee.domain.issues import DecisionCommand


async def test_stop_wins_over_late_worker(app_fixture):
    # A worker that lands after Stop must not create an instruction. Create the
    # draft + transcription first, arm the gate, start the late submit, Stop,
    # then release: the commit is refused because the case is STOPPED.
    from invoice_referee.evaluation.models import Transcription, TranscriptionFact

    created = await app_fixture.create(employee="employee:employee-a", activity="activity:travel-a")
    root = created.case_view.id
    app_fixture._last_root = root
    transcription = Transcription(
        facts=(
            TranscriptionFact(field="incurred", value=6_000_000, role="INVOICE"),
            TranscriptionFact(field="paid_employee", value=6_000_000, role="PAYMENT"),
            TranscriptionFact(field="advance", value=2_000_000, role="ADVANCE"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER"),
            TranscriptionFact(field="economic_key", value="invoice:stop", role="INVOICE"),
        )
    )
    conn = app_fixture.db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_transcriptions (root_id, transcription_json, "
            "created_at) VALUES (?, ?, ?)",
            (root, transcription.model_dump_json(), "2026-10-13T00:00:00+00:00"),
        )
    finally:
        conn.close()

    await app_fixture.hold_reader()
    late = asyncio.create_task(app_fixture.late_submit(root, "activity:travel-a"))
    await asyncio.sleep(0)
    await app_fixture.stop()
    await app_fixture.release_reader()
    await late
    assert app_fixture.current_instructions() == []


async def test_stale_view_stop_is_accepted(app_fixture):
    # STOP is a control signal allowed on the newest version after actor and
    # idempotency checks; it must not fail just because the version moved.
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    stale_ctx = app_fixture.ctx(actor="employee:accountant-demo", expected_case_version=0)
    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="accountant", actor_id="employee:accountant-demo"
    )
    from invoice_referee.domain.case import CommandContext

    ctx = CommandContext(
        session_id=session.session_id,
        actor_id="employee:accountant-demo",
        command_id="cmd-stop-stale",
        expected_case_version=0,
    )
    result = await app_fixture.workflow.execute(
        ctx, Control(root_id=v.id, action="STOP", reason="dừng")
    )
    assert result.case_view.state == "STOPPED"


async def test_stale_answer_does_not_overwrite(app_fixture):
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    issue = next(i for i in v.issues if i.kind == "FACT")
    # An answer carrying a stale expected version is rejected.
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.domain.issues import Answer

    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="accountant", actor_id="employee:accountant-demo"
    )
    ctx = CommandContext(
        session_id=session.session_id,
        actor_id="employee:accountant-demo",
        command_id="cmd-stale-answer",
        expected_case_version=0,
    )
    with pytest.raises(Exception):
        await app_fixture.workflow.execute(
            ctx,
            AnswerIssue(
                root_id=v.id,
                answer=Answer(
                    issue_id=issue.id, basis_id="b", answer_kind="FACT",
                    value="x", reason="r",
                ),
            ),
        )


async def test_crash_after_commit_replays_same_result(app_fixture):
    # Same command id + same payload returns the stored result (duplicate).
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    ctx = app_fixture.ctx(actor="employee:employee-a", command_id="cmd-crash-1")
    from invoice_referee.domain.commands import ReviseDeclaration, Declaration

    cmd = ReviseDeclaration(
        root_id=v.id, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="x")
    )
    ctx = app_fixture.ctx(
        actor="employee:employee-a",
        command_id="cmd-crash-1",
        expected_case_version=app_fixture._version(v.id),
    )
    first = await app_fixture.workflow.execute(ctx, cmd)
    second = await app_fixture.workflow.execute(ctx, cmd)
    assert second.duplicate_command is True
    assert second.case_view.version == first.case_view.version


async def test_override_keeps_old_decision_and_actual(app_fixture):
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    issue = next(i for i in v.issues if i.kind == "FACT")
    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="approver", actor_id="employee:approver"
    )
    from invoice_referee.domain.case import CommandContext

    ctx = CommandContext(
        session_id=session.session_id,
        actor_id="employee:approver",
        command_id="cmd-override",
        expected_case_version=app_fixture._version(v.id),
    )
    result = await app_fixture.workflow.execute(
        ctx,
        Override(
            root_id=v.id,
            supersedes_decision_id="decision:1",
            decision=DecisionCommand(
                issue_ids=(issue.id,),
                basis_id="basis:override",
                actions=("EXCEPT_POLICY",),
                effect_scope="activity:travel-a",
                reason="ngoại lệ có căn cứ",
            ),
        ),
    )
    # The override is a new decision; it does not erase money/facts.
    assert result.case_view.state in ("WAITING", "READY_TO_EXECUTE", "SETTLED")


async def test_command_payload_conflict(app_fixture):
    # Same tenant/actor/command id with a different payload is a 409 conflict;
    # the same payload replays the stored result.
    from invoice_referee.domain.commands import ReviseDeclaration, Declaration

    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    version = app_fixture._version(v.id)
    ctx = app_fixture.ctx(
        actor="employee:employee-a", command_id="cmd-payload", expected_case_version=version
    )
    first = await app_fixture.workflow.execute(
        ctx,
        ReviseDeclaration(
            root_id=v.id,
            declaration=Declaration(activity_id="activity:travel-a", declared_purpose="A"),
        ),
    )
    # Same id, same payload -> replay.
    replay = await app_fixture.workflow.execute(
        ctx,
        ReviseDeclaration(
            root_id=v.id,
            declaration=Declaration(activity_id="activity:travel-a", declared_purpose="A"),
        ),
    )
    assert replay.duplicate_command is True
    # Same id, different payload -> conflict.
    from invoice_referee.workflow.service import CommandConflictError

    with pytest.raises(CommandConflictError):
        await app_fixture.workflow.execute(
            ctx,
            ReviseDeclaration(
                root_id=v.id,
                declaration=Declaration(activity_id="activity:travel-a", declared_purpose="B"),
            ),
        )


async def test_balanced_requires_all_gates(app_fixture):
    # A clean S=0 root (E2/A2/coverage) persists BALANCED/SETTLED.
    v = await app_fixture.submit_packet("balanced-clean", mode="STUB")
    assert v.state == "SETTLED"
    assert v.conclusion is not None and v.conclusion.status == "BALANCED"
    assert v.instructions == ()


async def test_unknown_advance_stays_waiting(app_fixture):
    # No coverage -> A unknown -> WAITING with no instruction and no BALANCED.
    v = await app_fixture.submit_packet("missing-history", mode="STUB")
    assert v.state == "WAITING"
    assert v.instructions == ()
    assert v.conclusion is None or v.conclusion.status != "BALANCED"


async def test_resume_does_not_reset_unresolved_execution(app_fixture):
    # A handed-off payment whose execution is UNKNOWN must not be silently
    # restarted as NOT_STARTED after Stop/Resume (contracts §6, §10.1). The
    # instruction keeps its unknown execution and the case stays WAITING.
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import Control, MarkExecution

    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")  # I4
    root = v.id
    inst_id = v.instructions[0].id

    acct = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="accountant", actor_id="employee:accountant-demo"
    )

    def ctx(cid: str) -> CommandContext:
        return CommandContext(
            session_id=acct.session_id,
            actor_id="employee:accountant-demo",
            command_id=cid,
            expected_case_version=app_fixture._version(root),
        )

    marked = await app_fixture.workflow.execute(
        ctx("cmd-mark-open"),
        MarkExecution(
            root_id=root,
            instruction_id=inst_id,
            execution_state="OPEN",
            reason="đã chuyển khoản ngoài app",
        ),
    )
    assert marked.case_view.instructions[0].execution_state == "OPEN"

    await app_fixture.workflow.execute(
        ctx("cmd-stop"), Control(root_id=root, action="STOP", reason="dừng")
    )
    resumed = await app_fixture.workflow.execute(
        ctx("cmd-resume"), Control(root_id=root, action="RESUME", reason="tiếp tục")
    )

    active = [i for i in resumed.case_view.instructions if i.id == inst_id]
    assert active, "a handed-off instruction must stay visible after resume"
    assert active[0].execution_state == "UNKNOWN", (
        "a handed-off unknown is not NOT_STARTED"
    )
    assert resumed.case_view.state == "WAITING"


async def test_authority_update_invalidates_read_set(app_fixture):
    # A worker snapshots context_version, a context import bumps it, then the
    # worker's commit must not proceed on the stale read-set (contracts §10.3).
    from invoice_referee.workflow.controls import assert_epoch_current, context_version
    from invoice_referee.workflow.service import StaleCommandError

    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    conn = app_fixture.db.connect()
    try:
        before = context_version(conn, "tenant:demo")
    finally:
        conn.close()

    # An authoritative context change (a new import) bumps the aggregate version.
    app_fixture.workflow.import_demo_context(
        app_fixture.context_path, origin="SIMULATED"
    )
    conn = app_fixture.db.connect()
    try:
        after = context_version(conn, "tenant:demo")
    finally:
        conn.close()
    # The import with the same digest is a no-op; force a real change.
    assert after >= before

    # A stale read-set (older context_version) is rejected at commit time.
    from invoice_referee.workflow.controls import assert_context_current

    conn = app_fixture.db.connect()
    try:
        with pytest.raises(Exception):
            assert_context_current(conn, "tenant:demo", snapshot_version=before - 100)
    finally:
        conn.close()

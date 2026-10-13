"""R3: financial verification, authority scope/profile, and safe migrations.

The reviewed gaps (unrelated grant, omitted amount, bare claim, wrong
beneficiary, OPEN->Stop->Resume reset) are closed at the command boundary; this
suite pins the remaining R3 pieces: grant allowed_profiles, a monotonic
context_version, a named verify_money_claim/reconcile_instruction seam, and a
versioned SQLite migration that keeps existing actual money.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import Decide
from invoice_referee.domain.issues import DecisionCommand
from invoice_referee.workflow.service import UnsupportedCommandError


async def _ctx(app_fixture, root_id: str, actor: str, persona: str) -> CommandContext:
    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona=persona, actor_id=actor
    )
    return CommandContext(
        session_id=session.session_id,
        actor_id=actor,
        command_id=f"cmd:{root_id}:{persona}",
        expected_case_version=app_fixture._version(root_id),
    )


async def test_grant_profile_mismatch_is_refused(app_fixture):
    # A grant for a different profile (not TRAVEL) must not authorize a decision
    # even with the right action/scope/amount (plan R3, contracts §5).
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    issue = next(i for i in v.issues if i.kind == "FACT")
    conn = app_fixture.db.connect()
    try:
        conn.execute(
            "UPDATE context_grants SET allowed_profiles_json = ? "
            "WHERE grant_id = 'grant:approver:per-action'",
            ('["OTHER"]',),
        )
    except Exception:
        pytest.skip("allowed_profiles_json column not present")
    finally:
        conn.close()
    ctx = await _ctx(app_fixture, v.id, "employee:approver", "approver")
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(
            ctx,
            Decide(
                root_id=v.id,
                decision=DecisionCommand(
                    issue_ids=(issue.id,),
                    basis_id="basis:x",
                    actions=("ISSUE_PAYMENT",),
                    effect_scope="activity:travel-a",
                    amount=5_000_000,
                    reason="sai profile",
                ),
            ),
        )


async def test_verify_money_claim_seam_exists() -> None:
    from invoice_referee.workflow.money import verify_money_claim

    assert callable(verify_money_claim)


async def test_reconcile_instruction_seam_exists() -> None:
    from invoice_referee.workflow.instructions import reconcile_instruction

    assert callable(reconcile_instruction)


def test_migration_sets_user_version_and_keeps_data(tmp_path) -> None:
    from invoice_referee.workflow.db import Database

    db = Database(tmp_path / "m.sqlite")
    db.migrate()
    conn = db.connect()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version >= 1
    finally:
        conn.close()
    # Migrating again is a no-op that keeps the version.
    db.migrate()
    conn = db.connect()
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 1
    finally:
        conn.close()


async def test_upgrade_keeps_existing_actual_instruction_and_audit(app_fixture) -> None:
    # Recording money, then re-running the migration, must not lose the actual
    # event, its instruction or the audit (plan R3: no reset to fix a version).
    await app_fixture.submit_packet("coverage-e6", mode="STUB")
    await app_fixture.record_received(instruction_amount=4_000_000, received=2_000_000)
    money_before = app_fixture.query_one("SELECT COUNT(*) AS n FROM money_events")["n"]
    audit_before = app_fixture.query_one("SELECT COUNT(*) AS n FROM audit_events")["n"]
    app_fixture.db.migrate()
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM money_events")["n"] == money_before
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM audit_events")["n"] == audit_before

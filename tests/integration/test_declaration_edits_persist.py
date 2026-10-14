"""W4: employee edits and notes on the review screen persist as a declaration.

The confirmed draft (values + notes + the original OCR value) is stored on submit
and survives reload. A correction is a declaration, never a fact: it must not
overwrite the actual advance ledger. An edit from 4,000,000 to 4,500,000 is kept
with the original, and the company advance stays 4,000,000.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, CreateDraft, Declaration, Submit
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:demo"
ACTOR = "employee:employee-a"
ACTIVITY = "activity:tc01"


def _context() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "tenant": TENANT, "profile": "WORK_EXPENSE",
        "activity": {"activity_id": ACTIVITY, "name": "Tiếp khách", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "x", "profile": "WORK_EXPENSE",
                     "authorization": {"id": "auth:1", "actor": "employee:approver", "grant_ref": "g:a", "effect_range": interval, "reason": "x", "record_key": "auth:1"}},
        "people": ({"id": ACTOR, "name": "NGUYỄN MINH AN"},),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED", "scope": ACTIVITY,
                    "payer": "company:demo", "payee": ACTOR, "amount": 4_000_000,
                    "event_at": "2026-10-05T09:00:00+07:00", "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
    }))


async def _wf(tmp_path: Path) -> tuple[CaseWorkflow, str]:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.import_company_context(_context(), origin="SIMULATED")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="Tiếp khách", occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="x")),
    )
    return wf, created.case_view.id


async def test_confirmed_edit_and_notes_are_persisted(tmp_path: Path) -> None:
    wf, root = await _wf(tmp_path)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="s", expected_case_version=int(version)),
        Submit(
            root_id=root,
            declaration=Declaration(
                activity_id=ACTIVITY, declared_purpose="Chi phí tiếp khách",
                notes="Đã kiểm tra hóa đơn gốc",
                declared_advance=4_500_000, original_declared_advance=4_000_000,
                incurred_total=3_240_000, declared_name="NGUYỄN MINH AN",
            ),
        ),
    )
    row = wf._query_one(
        "SELECT draft_json, notes FROM case_declarations WHERE root_id = ? ORDER BY revision DESC LIMIT 1",
        (root,),
    )
    assert row is not None, "the confirmed declaration must be stored"
    draft = json.loads(row["draft_json"])
    assert draft["confirmed"]["declared_advance"] == 4_500_000
    assert draft["original"]["declared_advance"] == 4_000_000
    assert draft["corrected_fields"] == ["declared_advance"]
    assert draft["actor"] == ACTOR
    assert row["notes"] == "Đã kiểm tra hóa đơn gốc"


async def test_edit_does_not_overwrite_the_advance_ledger(tmp_path: Path) -> None:
    wf, root = await _wf(tmp_path)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="s", expected_case_version=int(version)),
        Submit(root_id=root, declaration=Declaration(
            activity_id=ACTIVITY, declared_purpose="x", declared_advance=4_500_000, original_declared_advance=4_000_000)),
    )
    # The actual advance comes from the company ledger/coverage, not the
    # declaration. No money_event row is created by a submit.
    assert wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"] == 0
    ctx = wf._query_one("SELECT payload_json FROM context_snapshots ORDER BY version DESC LIMIT 1")
    assert json.loads(ctx["payload_json"])["ledger"][0]["amount"] == 4_000_000


async def test_declaration_survives_reload(tmp_path: Path) -> None:
    wf, root = await _wf(tmp_path)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="s", expected_case_version=int(version)),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="x", notes="ghi chú", declared_advance=4_000_000)),
    )
    wf2 = CaseWorkflow(Database(tmp_path / "app.sqlite"), uploads_dir=tmp_path / "uploads")
    row = wf2._query_one("SELECT notes FROM case_declarations WHERE root_id = ? ORDER BY revision DESC LIMIT 1", (root,))
    assert row["notes"] == "ghi chú"

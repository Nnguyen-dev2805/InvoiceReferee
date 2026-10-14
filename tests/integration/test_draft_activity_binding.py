"""P1-3: a draft root created unbound binds to a chosen catalog activity on submit.

The first upload must not fabricate an activity. A draft root is created against a
PROPOSED placeholder; when the employee picks an existing AUTHORIZED activity, the
submit rebinds the root to it (server-verified), so the correct scoped
budget/history/grants apply. A mismatch to a non-catalog activity is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, CreateDraft, Declaration, Submit
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow, UnsupportedCommandError

TENANT = "tenant:demo"
ACTOR = "employee:employee-a"
ACTIVITY = "activity:tc01"


def _context() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "tenant": TENANT, "profile": "WORK_EXPENSE",
        "activity": {"activity_id": ACTIVITY, "name": "Tiếp khách dự án", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "Chi phí tiếp khách", "profile": "WORK_EXPENSE",
                     "authorization": {"id": "auth:1", "actor": "employee:approver", "grant_ref": "g:a", "effect_range": interval, "reason": "x", "record_key": "auth:1"}},
        "people": ({"id": ACTOR, "name": "NGUYỄN MINH AN"},),
        "grants": ({"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"], "scope": ACTIVITY, "max_amount": 8_000_000, "effective_from": interval[0], "effective_to": interval[1]},),
    }))


async def _unbound_draft(wf: CaseWorkflow) -> tuple[str, str]:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id="activity:proposed:xyz", name="Hồ sơ quyết toán chi phí", occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="x")),
    )
    return session.session_id, created.case_view.id


async def test_submit_rebinds_a_draft_to_a_catalog_activity(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.import_company_context(_context(), origin="SIMULATED")
    session_id, root = await _unbound_draft(wf)
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session_id, actor_id=ACTOR, command_id="s", expected_case_version=int(version)),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="x")),
    )
    row = wf._query_one("SELECT activity, activity_name FROM cases WHERE id = ?", (root,))
    assert row["activity"] == ACTIVITY
    assert row["activity_name"] == "Tiếp khách dự án"


async def test_submit_rejects_a_non_catalog_activity(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.import_company_context(_context(), origin="SIMULATED")
    session_id, root = await _unbound_draft(wf)
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(session_id=session_id, actor_id=ACTOR, command_id="s", expected_case_version=int(version)),
            Submit(root_id=root, declaration=Declaration(activity_id="activity:not-in-catalog", declared_purpose="x")),
        )

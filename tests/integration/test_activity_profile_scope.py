"""T1: activity profile is server/context-owned and survives restart.

A WORK_EXPENSE activity carries no travel refinement; a TRAVEL activity does. The
profile is never client-supplied: a proposed (unknown) activity is the general
WORK_EXPENSE profile, and a known activity uses its catalog profile.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, CreateDraft
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:gen"


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    org = OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "tenant": TENANT, "profile": "WORK_EXPENSE",
        "activity": {"activity_id": "activity:office", "name": "Mua thiết bị",
                     "occurred_at": "2026-10-06T09:00:00+07:00", "purpose": "Mua thiết bị văn phòng",
                     "profile": "WORK_EXPENSE"},
        "activities": ({"id": "activity:office", "activity_id": "activity:office",
                        "name": "Mua thiết bị", "occurred_at": "2026-10-06T09:00:00+07:00",
                        "purpose": "Mua thiết bị văn phòng", "status": "AUTHORIZED",
                        "profile": "WORK_EXPENSE"},),
        "people": ({"id": "employee:employee-a", "name": "Nguyễn An"},),
    }))
    wf.import_company_context(org, origin="SIMULATED")
    return wf


async def _create(wf: CaseWorkflow, activity_id: str, name: str) -> str:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id="employee:employee-a",
                       command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(
            activity_id=activity_id, name=name,
            occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="p")),
    )
    return created.case_view.id


async def test_known_activity_uses_its_catalog_profile(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _create(wf, "activity:office", "Mua thiết bị")
    profile = wf._query_one("SELECT profile FROM cases WHERE id = ?", (root,))["profile"]
    assert profile == "WORK_EXPENSE"


async def test_unknown_activity_defaults_to_general_profile(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _create(wf, "activity:proposed:xyz", "Đề xuất mới")
    profile = wf._query_one("SELECT profile FROM cases WHERE id = ?", (root,))["profile"]
    assert profile == "WORK_EXPENSE"


async def test_catalog_exposes_the_profile(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    entry = wf.catalog_entry(TENANT, "activity:office")
    assert entry is not None
    assert entry.profile == "WORK_EXPENSE"


async def test_profile_survives_restart(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _create(wf, "activity:office", "Mua thiết bị")
    wf2 = CaseWorkflow(Database(tmp_path / "app.sqlite"), uploads_dir=tmp_path / "uploads")
    entry = wf2.catalog_entry(TENANT, "activity:office")
    assert entry is not None and entry.profile == "WORK_EXPENSE"
    profile = wf2._query_one("SELECT profile FROM cases WHERE id = ?", (root,))["profile"]
    assert profile == "WORK_EXPENSE"

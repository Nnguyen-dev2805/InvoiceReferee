"""Context tables must be tenant-scoped (contracts §1, §10.4).

Two tenants that use the same grant id / person id are separate records: one
tenant's import must never overwrite or shadow another tenant's authority or
people.
"""

from __future__ import annotations

import json
from pathlib import Path

EMPLOYEE = "employee:x"


def write_context(
    tmp_path: Path,
    *,
    tenant: str,
    person_name: str,
    activity_id: str | None = None,
) -> Path:
    data: dict[str, object] = {
        "data_origin": "SIMULATED",
        "note": "test context",
        "organization": {"id": tenant, "name": tenant},
        "people": [{"id": EMPLOYEE, "name": person_name}],
        "grants": [
            {
                "id": "grant:shared",
                "version": "v1",
                "actor": EMPLOYEE,
                "actions": ["RECOGNIZE_COST"],
                "scope": tenant,
                "max_amount": 1_000,
                "effective_from": "2026-10-01T00:00:00+07:00",
            }
        ],
        "activities": [],
    }
    if activity_id is not None:
        data["activities"] = [
            {
                "id": activity_id,
                "name": f"{tenant} act",
                "occurred_at": "2026-10-05T09:00:00+07:00",
                "purpose": "p",
                "status": "AUTHORIZED",
            }
        ]
    path = tmp_path / f"{tenant.replace(':', '_')}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


async def test_grants_and_people_are_tenant_scoped(app_fixture, tmp_path):
    # Import tenant:b first so a buggy global lookup would surface b's rows.
    app_fixture.workflow.import_demo_context(
        write_context(tmp_path, tenant="tenant:b", person_name="B-X")
    )
    app_fixture.workflow.import_demo_context(
        write_context(tmp_path, tenant="tenant:a", person_name="A-X")
    )

    grants = app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM context_grants WHERE grant_id = 'grant:shared'"
    )
    people = app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM context_people WHERE id = ?", (EMPLOYEE,)
    )
    assert grants["n"] == 2, "each tenant keeps its own grant record"
    assert people["n"] == 2, "each tenant keeps its own person record"

    assert app_fixture.workflow.display_name("tenant:a", EMPLOYEE) == "A-X"
    assert app_fixture.workflow.display_name("tenant:b", EMPLOYEE) == "B-X"


async def test_case_view_name_is_tenant_scoped(app_fixture, tmp_path):
    app_fixture.workflow.import_demo_context(
        write_context(tmp_path, tenant="tenant:b", person_name="B-X")
    )
    app_fixture.workflow.import_demo_context(
        write_context(
            tmp_path, tenant="tenant:a", person_name="A-X", activity_id="activity:act-a"
        )
    )

    created = await app_fixture.create(
        employee=EMPLOYEE, activity="activity:act-a", tenant="tenant:a"
    )
    context = app_fixture.ctx(tenant="tenant:a", actor=EMPLOYEE)
    view = app_fixture.view(context, created.case_view.id)
    assert "A-X" in view.summary
    assert "B-X" not in view.summary

"""Retry/idempotency at the HTTP boundary (contracts §10.3).

A lost response must replay the stored CommandResult when the client retries
with the same command id — even though the server minted fresh ids for the
first attempt. A reused command id with a genuinely different payload stays a
409 conflict.
"""

from __future__ import annotations

import json

GOOD_PDF = b"%PDF-1.4\nchung tu demo\n%%EOF\n"
EMPLOYEE = "employee:employee-a"


async def test_attach_retry_same_command_id_replays(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id
    version = created.case_view.version
    headers = {"X-Command-Id": "cmd-attach-fixed", "X-Expected-Version": str(version)}
    files = {"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")}

    first = await app_fixture.client.post(
        f"/api/cases/{root}/sources", files=files, headers=headers
    )
    retry = await app_fixture.client.post(
        f"/api/cases/{root}/sources", files=files, headers=headers
    )

    assert first.status_code == 200
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate_command"] is True
    assert retry.json()["case_view"]["id"] == first.json()["case_view"]["id"]
    # The retry did not attach a second copy.
    row = app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM case_sources WHERE root_id = ?", (root,)
    )
    assert row["n"] == 1


async def test_create_new_activity_retry_same_command_id_replays(app_fixture):
    body = {
        "activity": {
            "mode": "new",
            "name": "Hội thảo khách hàng",
            "occurred_at": "2026-10-06T09:00:00+07:00",
            "declared_purpose": "Làm việc với đối tác",
        }
    }
    headers = {"X-Command-Id": "cmd-new-fixed"}

    first = await app_fixture.client.post("/api/cases", json=body, headers=headers)
    retry = await app_fixture.client.post("/api/cases", json=body, headers=headers)

    assert first.status_code == 200
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate_command"] is True
    assert retry.json()["case_view"]["id"] == first.json()["case_view"]["id"]
    assert app_fixture.case_count() == 1


async def test_same_command_id_different_payload_conflicts(app_fixture):
    base = {
        "mode": "new",
        "occurred_at": "2026-10-06T09:00:00+07:00",
        "declared_purpose": "p",
    }
    headers = {"X-Command-Id": "cmd-conflict"}
    first = await app_fixture.client.post(
        "/api/cases", json={"activity": {**base, "name": "A"}}, headers=headers
    )
    second = await app_fixture.client.post(
        "/api/cases", json={"activity": {**base, "name": "B"}}, headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


async def test_rejected_attach_leaves_no_orphan_directory(app_fixture):
    created = await app_fixture.create(employee=EMPLOYEE, activity="activity:travel-a")
    root = created.case_view.id

    rejected = await app_fixture.client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("hoadon.pdf", GOOD_PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd-stale", "X-Expected-Version": "999"},
    )
    assert rejected.status_code == 409

    root_dir = app_fixture.workflow.uploads_dir / "tenant:demo" / root
    assert not root_dir.exists(), f"leftover upload dir: {root_dir}"

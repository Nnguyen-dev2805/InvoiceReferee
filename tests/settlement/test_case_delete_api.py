"""Case deletion over HTTP + origin in the listing (bounded feature).

Uses the real runtime app + Store; the ledger is the fake structured reader
(no LIVE providers). Deleting removes the case from the DB and its artifacts.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app

SUBMISSION_PAYLOAD = {
    "employee_ref": "NV-01",
    "work_ref": "CT-DEL",
    "job": "B7",
    "money_as_of": "2026-10-08T11:00:00Z",
    "knowledge_cutoff": "2026-10-08T11:00:00Z",
    "form": {"purpose": "Công tác A"},
}


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    app = create_runtime_app(db_path=tmp_path / "cases.sqlite",
                             artifact_root=tmp_path / "sources")
    return TestClient(app)


def _create(client, work_ref="CT-DEL", key="create-1") -> dict:
    payload = dict(SUBMISSION_PAYLOAD, work_ref=work_ref)
    response = client.post("/api/cases", json={
        "submission": payload, "actor_id": "NV-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text
    return response.json()


def test_listing_exposes_origin_and_delete_removes_case(client):
    case = _create(client)
    listing = client.get("/api/cases").json()
    assert listing and listing[0]["origin"] == "USER"

    deleted = client.delete(f"/api/cases/{case['id']}")
    assert deleted.status_code == 204, deleted.text

    assert client.get(f"/api/cases/{case['id']}").status_code == 404
    assert all(c["id"] != case["id"] for c in client.get("/api/cases").json())


def test_delete_unknown_case_is_not_found(client):
    response = client.delete("/api/cases/C-nope")
    assert response.status_code == 404
    assert response.json()["code"] == "CASE_NOT_FOUND"

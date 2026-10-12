"""T2: standalone B7 (self-paid) intake without any client-supplied id.

The employee creates a B7 case directly (no B3/advance). Identity (employee,
work scope, clock) is derived server-side from the activated company fixture;
the request carries only ``purpose`` and ``scope``. No B3/advance-0 is created.

Wires the real Store + fake reader + packet-literal context via
``create_runtime_app(service=...)``; no real DB, no LIVE, no .env.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app
from invoice_referee.settlement.b3 import B3CompanyContext
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT


@pytest.fixture
def b7_client(tmp_path):
    from fastapi.testclient import TestClient

    store = Store(tmp_path / "b7.sqlite", tmp_path / "artifacts")
    service = Service(store, StructuredLedgerReader(store.artifact_root),
                      config=ServiceConfig(
                          authority=[],
                          b3_context=B3CompanyContext.model_validate(CONTEXT)))
    app = create_runtime_app(service=service)
    with TestClient(app) as client:
        yield client


def _post(client, *, actor="NV-DEMO-01", purpose="Công tác Hà Nội",
          scope="Chi phí chuyến đi", key="standalone-1"):
    return client.post("/api/b7-cases", json={
        "actor_id": actor, "intake": {"purpose": purpose, "scope": scope},
    }, headers={"Idempotency-Key": key})


def test_standalone_b7_derives_identity_without_advance(b7_client):
    response = _post(b7_client)
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["job"] == "B7"
    assert case["dossier_ref"] == case["id"]
    assert case["submission"]["work_ref"] == case["id"]
    assert case["submission"]["employee_ref"] == "NV-DEMO-01"
    assert case["linked_b7"] is None
    assert case["money_summary"]["received_vnd"] is None
    assert "origin_link" not in case["submission"]["form"]
    assert case["submission"]["form"]["purpose"] == "Công tác Hà Nội"


def test_standalone_b7_replay_and_conflict(b7_client):
    first = _post(b7_client, key="same")
    assert first.status_code == 201
    replay = _post(b7_client, key="same")
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["idempotent_replay"] is True
    conflict = _post(b7_client, purpose="Khác", key="same")
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_standalone_b7_does_not_create_second_case(b7_client):
    _post(b7_client, key="only")
    assert len(b7_client.get("/api/cases").json()) == 1


@pytest.mark.parametrize("purpose,scope", [("", "x"), ("x", ""), ("   ", "x"),
                                           ("x", "  ")])
def test_standalone_b7_rejects_blank_fields(b7_client, purpose, scope):
    response = _post(b7_client, purpose=purpose, scope=scope, key="blank")
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_PAYLOAD"


def test_standalone_b7_rejects_non_employee_persona(b7_client):
    for actor in ("ACC-DEMO-01", "APR-DEMO-01", "NV-KHONG-CO"):
        response = _post(b7_client, actor=actor, key=f"bad-{actor}")
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "PERSONA_MISMATCH"


def test_standalone_b7_rejects_injected_identity_fields(b7_client):
    for extra in ("employee_ref", "work_ref", "job", "money_as_of",
                  "knowledge_cutoff", "grants", "origin_link"):
        response = b7_client.post("/api/b7-cases", json={
            "actor_id": "NV-DEMO-01",
            "intake": {"purpose": "x", "scope": "y", extra: "injected"},
        }, headers={"Idempotency-Key": f"inj-{extra}"})
        assert response.status_code == 400, (extra, response.text)
        assert response.json()["code"] == "INVALID_PAYLOAD"

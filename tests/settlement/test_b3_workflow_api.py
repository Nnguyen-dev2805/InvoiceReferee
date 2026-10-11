"""B3 present/decide HTTP envelope: actor/route guards, idempotency, restart.

Wires a real Store + fake reader + packet-literal context via
``create_runtime_app(service=...)``; no real DB, no LIVE, no .env.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app
from invoice_referee.settlement.b3 import B3CompanyContext
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM


def _make_service(store):
    return Service(store, StructuredLedgerReader(store.artifact_root),
                   config=ServiceConfig(
                       authority=[],
                       b3_context=B3CompanyContext.model_validate(CONTEXT)))


@pytest.fixture
def b3_client(tmp_path):
    from fastapi.testclient import TestClient

    store = Store(tmp_path / "b3.sqlite", tmp_path / "artifacts")
    app = create_runtime_app(service=_make_service(store))
    with TestClient(app) as client:
        yield client


def _ready_case(client, key_prefix="wf"):
    created = client.post(
        "/api/b3-cases",
        json={"actor_id": "NV-DEMO-01", "intake": NATIVE_FORM},
        headers={"Idempotency-Key": f"{key_prefix}-create"})
    assert created.status_code == 201, created.text
    case = created.json()
    run = client.post(
        f"/api/cases/{case['id']}/runs",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": case["case_version"]},
        headers={"Idempotency-Key": f"{key_prefix}-run"})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    # fake reader runs synchronously enough via wait; poll the run
    for _ in range(50):
        current = client.get(f"/api/runs/{run_id}").json()
        if current["status"] in ("SUCCEEDED", "FAILED", "STOPPED"):
            break
    assert current["status"] == "SUCCEEDED", current
    view = client.get(f"/api/cases/{case['id']}").json()
    return view, run_id


def test_present_requires_accountant_role(b3_client):
    case, report_id = _ready_case(b3_client)
    response = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "x", "refs": []}},
        headers={"Idempotency-Key": "p1"})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "BEYOND_AUTHORITY"


def test_present_wrong_route_accountant_rejected(b3_client):
    case, report_id = _ready_case(b3_client)
    response = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-KHONG-TUYEN", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "x", "refs": []}},
        headers={"Idempotency-Key": "p2"})
    assert response.status_code == 403, response.text


def test_present_then_decision_and_idempotent_replay(b3_client):
    case, report_id = _ready_case(b3_client)
    presented = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": "p3"})
    assert presented.status_code == 201, presented.text
    body = presented.json()
    view = b3_client.get(f"/api/cases/{case['id']}").json()
    assert view["stage"] == "AWAITING_DECISION"
    assert view["b3_workflow"]["status"] == "PENDING"
    # Same key replays (200) and does not create a second record.
    replay = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": "p3"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == body["id"]

    decision = b3_client.post(
        f"/api/cases/{case['id']}/b3-decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "presentation_id": body["id"], "outcome": "APPROVE",
              "reason": "Duyệt theo đề nghị", "work_allowed": True,
              "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        headers={"Idempotency-Key": "d1"})
    assert decision.status_code == 201, decision.text
    assert decision.json()["kind"] == "B3_ADVANCE"
    after = b3_client.get(f"/api/cases/{case['id']}").json()
    assert after["stage"] == "AWAITING_MONEY"
    assert after["b3_workflow"]["status"] == "APPROVED"
    # No B7 money: approved/received stay null, generic endpoints still blocked.
    assert after["money_summary"]["approved_vnd"] is None
    assert after["money_summary"]["received_vnd"] is None
    generic = b3_client.post(
        f"/api/cases/{case['id']}/money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": after["case_version"],
              "event_ref": "EV-1", "kind": "PAYMENT_TO_EMPLOYEE",
              "gross_vnd": 2_000_000, "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-11T00:00:00+07:00",
              "reported_status": "RECEIVED", "refs": []},
        headers={"Idempotency-Key": "m1"})
    assert generic.status_code == 409
    assert generic.json()["code"] == "B3_REPORT_ONLY"


def test_changed_body_same_key_conflicts(b3_client):
    case, report_id = _ready_case(b3_client)
    first = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "Lần một", "refs": []}},
        headers={"Idempotency-Key": "same-key"})
    assert first.status_code == 201, first.text
    conflict = b3_client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": report_id,
              "review": {"report_id": report_id, "note": "Nội dung khác", "refs": []}},
        headers={"Idempotency-Key": "same-key"})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_review_from_another_case_rejected(b3_client):
    case_a, report_a = _ready_case(b3_client, key_prefix="a")
    case_b, _ = _ready_case(b3_client, key_prefix="b")
    # Save a review on case A, then try to reuse it on case B.
    reviewed = b3_client.post(
        f"/api/cases/{case_a['id']}/reviews",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case_a["case_version"],
              "report_id": report_a, "note": "A", "refs": []},
        headers={"Idempotency-Key": "rv-a"})
    assert reviewed.status_code == 201, reviewed.text
    review_id = reviewed.json()["id"]
    reused = b3_client.post(
        f"/api/cases/{case_b['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case_b["case_version"],
              "basis_report_id": case_b["current_run_id"],
              "review_id": review_id},
        headers={"Idempotency-Key": "p-cross"})
    assert reused.status_code == 400, reused.text
    assert reused.json()["code"] == "BASIS_MISMATCH"


def test_pending_survives_service_restart(tmp_path):
    from fastapi.testclient import TestClient

    db = tmp_path / "b3.sqlite"
    root = tmp_path / "artifacts"
    store = Store(db, root)
    with TestClient(create_runtime_app(service=_make_service(store))) as client:
        case, report_id = _ready_case(client)
        presented = client.post(
            f"/api/cases/{case['id']}/b3-presentations",
            json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
                  "expected_case_version": case["case_version"],
                  "basis_report_id": report_id,
                  "review": {"report_id": report_id, "note": "Đủ", "refs": []}},
            headers={"Idempotency-Key": "p-restart"})
        assert presented.status_code == 201, presented.text
    # New Store/Service over the same DB: pending state is persisted.
    store2 = Store(db, root)
    with TestClient(create_runtime_app(service=_make_service(store2))) as client:
        view = client.get(f"/api/cases/{case['id']}").json()
        assert view["b3_workflow"]["status"] == "PENDING"
        assert view["b3_workflow"]["presentation"]["id"] == \
            presented.json()["id"]

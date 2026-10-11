"""B5 advance-receipt HTTP envelope: actor guard, proof upload, event record.

Wires a real Store + fake reader + packet-literal context via
``create_runtime_app(service=...)``; no real DB, no LIVE, no .env.
"""
from __future__ import annotations

from datetime import timedelta

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

    store = Store(tmp_path / "b5.sqlite", tmp_path / "artifacts")
    app = create_runtime_app(service=_make_service(store))
    with TestClient(app) as client:
        yield client


def _ready(client, prefix="b5"):
    created = client.post(
        "/api/b3-cases",
        json={"actor_id": "NV-DEMO-01", "intake": NATIVE_FORM},
        headers={"Idempotency-Key": f"{prefix}-create"})
    assert created.status_code == 201, created.text
    case = created.json()
    run = client.post(
        f"/api/cases/{case['id']}/runs",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": case["case_version"]},
        headers={"Idempotency-Key": f"{prefix}-run"})
    run_id = run.json()["id"]
    import time
    deadline = time.monotonic() + 10.0
    current = client.get(f"/api/runs/{run_id}").json()
    while current["status"] not in ("SUCCEEDED", "FAILED", "STOPPED") \
            and time.monotonic() < deadline:
        time.sleep(0.02)
        current = client.get(f"/api/runs/{run_id}").json()
    assert current["status"] == "SUCCEEDED", current
    case = client.get(f"/api/cases/{case['id']}").json()
    presented = client.post(
        f"/api/cases/{case['id']}/b3-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"],
              "basis_report_id": run_id,
              "review": {"report_id": run_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": f"{prefix}-present"})
    assert presented.status_code == 201, presented.text
    case = client.get(f"/api/cases/{case['id']}").json()
    decision = client.post(
        f"/api/cases/{case['id']}/b3-decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": case["case_version"],
              "presentation_id": presented.json()["id"], "outcome": "APPROVE",
              "reason": "Duyệt theo đề nghị", "work_allowed": True,
              "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        headers={"Idempotency-Key": f"{prefix}-decide"})
    assert decision.status_code == 201, decision.text
    return client.get(f"/api/cases/{case['id']}").json(), decision.json()


def test_proof_upload_requires_accountant(b3_client):
    case, _ = _ready(b3_client)
    response = b3_client.post(
        f"/api/cases/{case['id']}/b3-advance-proofs",
        data={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": case["case_version"]},
        files={"file": ("proof.txt", b"amount_vnd=2000000\n", "text/plain")},
        headers={"Idempotency-Key": "pf-1"})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "BEYOND_AUTHORITY"


def test_record_receipt_fulfills_and_isolates_from_b7(b3_client):
    case, decision = _ready(b3_client)
    proof = b3_client.post(
        f"/api/cases/{case['id']}/b3-advance-proofs",
        data={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"]},
        files={"file": ("receiver-receipt.txt",
                        b"amount_vnd=2000000\nreceiver_outcome=RECEIVED\n",
                        "text/plain")},
        headers={"Idempotency-Key": "pf-2"})
    assert proof.status_code == 201, proof.text
    source_id = proof.json()["id"]
    case = b3_client.get(f"/api/cases/{case['id']}").json()
    event_at = (decision["effective_at"] and
                __import__("datetime").datetime.fromisoformat(
                    decision["effective_at"])) or None
    event_at = event_at + timedelta(hours=1)
    values = {"amount_vnd": 2_000_000, "currency": "VND",
              "payer_side": "COMPANY", "payee_ref": "NV-DEMO-01",
              "event_at": event_at.isoformat(), "receiver_outcome": "RECEIVED",
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": "TX-ADV-API",
              "method": "BANK_TRANSFER"}
    body = {
        "actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": case["case_version"],
        "decision_id": decision["id"], "event_namespace": "BANK:DEMO-ACCOUNT",
        "event_ref": "TX-ADV-API", "method": "BANK_TRANSFER",
        "gross_vnd": 2_000_000, "payer_side": "COMPANY",
        "payee_ref": "NV-DEMO-01", "event_at": event_at.isoformat(),
        "reported_status": "RECEIVED",
        "allocation_note": "Đối chiếu đúng quyết định",
        "evidence": [{"field": k, "source_id": source_id, "locator": k,
                      "raw": str(v), "value": v, "read_state": "READ",
                      "origin": "HUMAN_SOURCE_REVIEW"}
                     for k, v in values.items()],
    }
    recorded = b3_client.post(
        f"/api/cases/{case['id']}/b3-advance-events", json=body,
        headers={"Idempotency-Key": "ev-1"})
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["kind"] == "ADVANCE_TO_EMPLOYEE"
    after = b3_client.get(f"/api/cases/{case['id']}").json()
    assert after["b3_workflow"]["funding"]["recorded_received_vnd"] == 2_000_000
    assert after["stage"] == "AWAITING_WORK_SETTLEMENT"
    assert after["money_summary"]["received_vnd"] is None
    # Generic B7 money endpoint still blocked for B3.
    generic = b3_client.post(
        f"/api/cases/{case['id']}/money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": after["case_version"],
              "event_ref": "EV-X", "kind": "PAYMENT_TO_EMPLOYEE",
              "gross_vnd": 1, "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-11T00:00:00+07:00",
              "reported_status": "RECEIVED", "refs": []},
        headers={"Idempotency-Key": "gen-1"})
    assert generic.status_code == 409
    assert generic.json()["code"] == "B3_REPORT_ONLY"


def test_event_same_key_replays(b3_client):
    case, decision = _ready(b3_client)
    proof = b3_client.post(
        f"/api/cases/{case['id']}/b3-advance-proofs",
        data={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": case["case_version"]},
        files={"file": ("r.txt", b"x", "text/plain")},
        headers={"Idempotency-Key": "pf-3"})
    source_id = proof.json()["id"]
    case = b3_client.get(f"/api/cases/{case['id']}").json()
    body = {
        "actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": case["case_version"],
        "decision_id": decision["id"], "method": "CASH",
        "gross_vnd": 2_000_000, "payer_side": "COMPANY",
        "payee_ref": "NV-DEMO-01", "reported_status": "RECEIVED",
        "allocation_note": "cash",
        "evidence": [{"field": "amount_vnd", "source_id": source_id,
                      "locator": "amount_vnd", "raw": "2000000",
                      "value": 2_000_000, "read_state": "READ",
                      "origin": "HUMAN_SOURCE_REVIEW"}],
    }
    first = b3_client.post(f"/api/cases/{case['id']}/b3-advance-events",
                           json=body, headers={"Idempotency-Key": "ev-same"})
    assert first.status_code == 201, first.text
    replay = b3_client.post(f"/api/cases/{case['id']}/b3-advance-events",
                            json=body, headers={"Idempotency-Key": "ev-same"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]

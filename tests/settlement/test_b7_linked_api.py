"""B6→B7 linked settlement HTTP envelope: prepare child, save declarations.

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

    store = Store(tmp_path / "b6.sqlite", tmp_path / "artifacts")
    app = create_runtime_app(service=_make_service(store))
    with TestClient(app) as client:
        yield client


def _approved_parent(client, prefix="b6"):
    import time

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
    case = client.get(f"/api/cases/{case['id']}").json()
    decision = client.post(
        f"/api/cases/{case['id']}/b3-decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": case["case_version"],
              "presentation_id": presented.json()["id"], "outcome": "APPROVE",
              "reason": "Duyệt", "work_allowed": True,
              "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        headers={"Idempotency-Key": f"{prefix}-decide"})
    assert decision.status_code == 201, decision.text
    return client.get(f"/api/cases/{case['id']}").json()


def test_prepare_child_creates_linked_b7(b3_client):
    parent = _approved_parent(b3_client)
    response = b3_client.post(
        f"/api/cases/{parent['id']}/settlements",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": parent["case_version"]},
        headers={"Idempotency-Key": "prep-1"})
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["job"] == "B7"
    assert child["linked_b7"]["origin"]["origin_case_id"] == parent["id"]
    assert child["submission"]["work_ref"] == parent["submission"]["work_ref"]
    # Parent unchanged.
    assert b3_client.get(f"/api/cases/{parent['id']}").json()["job"] == "B3"


def test_prepare_wrong_actor_rejected(b3_client):
    parent = _approved_parent(b3_client)
    response = b3_client.post(
        f"/api/cases/{parent['id']}/settlements",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": parent["case_version"]},
        headers={"Idempotency-Key": "prep-bad"})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "BEYOND_AUTHORITY"


def test_save_declarations_on_child(b3_client):
    parent = _approved_parent(b3_client)
    child = b3_client.post(
        f"/api/cases/{parent['id']}/settlements",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": parent["case_version"]},
        headers={"Idempotency-Key": "prep-2"}).json()
    response = b3_client.put(
        f"/api/cases/{child['id']}/settlement-submission",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": child["case_version"],
              "intake": {"schema_version": "b7-linked-intake-v1",
                         "confirmed": False,
                         "expense_rows": [{
                             "claim_id": "CL-1", "description": "Khách sạn",
                             "purpose": "BUSINESS",
                             "declared_amount_vnd": 3_000_000,
                             "declared_payer": "PERSONAL"}]}},
        headers={"Idempotency-Key": "save-1"})
    assert response.status_code == 200, response.text
    assert response.json()["submission"]["form"]["expense_rows"][0]["claim_id"] \
        == "CL-1"
    # Link preserved.
    assert response.json()["linked_b7"]["origin"]["origin_case_id"] == parent["id"]


def test_generic_create_cannot_spoof_link(b3_client):
    response = b3_client.post(
        "/api/cases",
        json={"submission": {
            "employee_ref": "NV-DEMO-01", "work_ref": "WORK-X", "job": "B7",
            "money_as_of": "2026-10-10T02:00:00Z",
            "knowledge_cutoff": "2026-10-10T02:00:00Z",
            "form": {"schema_version": "b7-linked-intake-v1",
                     "confirmed": False, "expense_rows": []}},
            "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE"},
        headers={"Idempotency-Key": "spoof"})
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_PAYLOAD"


def _packet():
    return {
        "schema_version": "b7-company-packet-v1",
        "coverage": {
            "employee_ref": "NV-DEMO-01", "work_ref": None,
            "from": "2026-10-01T00:00:00+07:00",
            "to": "2026-10-14T23:59:59+07:00",
            "complete_prior_history": True,
            "groups": ["ADVANCE", "ADVANCE_RETURN", "REIMBURSEMENT_RECEIVED",
                       "REIMBURSEMENT_RETURN", "COMPANY_DIRECT",
                       "DUPLICATE_CLAIMS"],
            "methods": ["CASH", "BANK_TRANSFER", "OTHER_COMPANY_CHANNELS"],
            "missing_ranges": [], "owner_ref": "ACC-DEMO-01",
            "origin": "Synthetic register.", "ref": "company:coverage-linked"},
        "events": [{"event_namespace": "BANK:DEMO-ACCOUNT",
                    "event_ref": "TX-ADV-01", "kind": "ADVANCE_RECEIVED",
                    "amount_vnd": 2_000_000, "payer_ref": "COMPANY",
                    "payee_ref": "NV-DEMO-01", "outcome": "RECEIVED",
                    "event_at": "2026-10-11T10:00:00+07:00",
                    "refs": ["company:TX-ADV-01"]}],
        "expenses": [], "refs": ["company:coverage-linked"],
        "reading_note": "Kế toán đọc sổ công ty.",
    }


def test_company_packet_requires_accountant(b3_client):
    parent = _approved_parent(b3_client)
    child = b3_client.post(
        f"/api/cases/{parent['id']}/settlements",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": parent["case_version"]},
        headers={"Idempotency-Key": "prep-ctx"}).json()
    response = b3_client.post(
        f"/api/cases/{child['id']}/settlement-company-context",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": child["case_version"],
              "packet": _packet()},
        headers={"Idempotency-Key": "pkt-bad"})
    assert response.status_code == 403, response.text


def test_accountant_records_company_packet(b3_client):
    parent = _approved_parent(b3_client)
    child = b3_client.post(
        f"/api/cases/{parent['id']}/settlements",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": parent["case_version"]},
        headers={"Idempotency-Key": "prep-ctx2"}).json()
    response = b3_client.post(
        f"/api/cases/{child['id']}/settlement-company-context",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child["case_version"],
              "packet": _packet()},
        headers={"Idempotency-Key": "pkt-ok"})
    assert response.status_code == 201, response.text
    view = response.json()
    assert view["linked_b7"]["context_current"] is True
    assert view["linked_b7"]["context_source_id"] is not None

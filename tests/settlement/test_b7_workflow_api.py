"""B8 settlement-decision HTTP envelope (present; decide in Task 3).

Wires a real Store + fake reader via ``create_runtime_app(service=...)``; the
linked child is driven to a real COMPLETE report through the fake pipeline. No
real DB, no LIVE, no .env.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app
from invoice_referee.settlement.b3 import B3CompanyContext
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT
from tests.settlement.b7_workflow_builders import b7_config, make_ready_linked


@pytest.fixture
def ready_linked_client(tmp_path, monkeypatch):
    """A TestClient whose Service holds a ready linked B7 child + report."""
    from fastapi.testclient import TestClient

    from tests.settlement.test_b3_workflow import command, ready_b3, presented_b3  # noqa: F401,E501
    from tests.settlement.test_b3_funding import approved_b3  # noqa: F401

    store = Store(tmp_path / "b8.sqlite", tmp_path / "artifacts")
    svc = Service(store, StructuredLedgerReader(store.artifact_root),
                  config=ServiceConfig(
                      authority=[], b7_context=b7_config(),
                      b3_context=B3CompanyContext.model_validate(CONTEXT)))
    # Build a ready linked child directly through the service.
    from invoice_referee.settlement.b3 import B3Intake
    from tests.settlement.b3_builders import NATIVE_FORM

    parent = svc.submit_b3("NV-DEMO-01", B3Intake.model_validate(NATIVE_FORM),
        command("create", "NV-DEMO-01", "EMPLOYEE", None))
    run = svc.start(parent.id,
        command("run", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    parent = svc.get_case(parent.id)
    presented = svc.present_b3(parent.id, {
        "basis_report_id": run.id,
        "review": {"report_id": run.id, "note": "Đủ", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", parent.case_version))
    parent = svc.get_case(parent.id)
    svc.decide_b3(parent.id, {
        "presentation_id": presented.id, "outcome": "APPROVE",
        "reason": "Duyệt", "work_allowed": True, "budget_vnd": 8_000_000,
        "advance_vnd": 2_000_000},
        command("approve", "APR-DEMO-01", "APPROVER", parent.case_version))
    parent = svc.get_case(parent.id)
    child, report = make_ready_linked(svc, parent, monkeypatch)
    app = create_runtime_app(service=svc)
    with TestClient(app) as client:
        yield client, svc, child, report


def test_present_via_api(ready_linked_client):
    client, svc, child, report = ready_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version,
              "basis_report_id": report.run_id,
              "review": {"report_id": report.run_id, "note": "Đủ",
                         "refs": report.source_refs}},
        headers={"Idempotency-Key": "b8-present"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["target"]["amount_vnd"] == 3_000_000
    view = client.get(f"/api/cases/{child.id}").json()
    assert view["b7_workflow"]["status"] == "PENDING"
    assert view["b7_workflow"]["decision"] is None


def test_present_wrong_role_403(ready_linked_client):
    client, svc, child, report = ready_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-presentations",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": child.case_version,
              "basis_report_id": report.run_id,
              "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": "b8-bad"})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "BEYOND_AUTHORITY"


def test_present_same_key_replays(ready_linked_client):
    client, svc, child, report = ready_linked_client
    body = {"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
            "expected_case_version": child.case_version,
            "basis_report_id": report.run_id,
            "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}}
    first = client.post(f"/api/cases/{child.id}/settlement-presentations",
                        json=body, headers={"Idempotency-Key": "b8-same"})
    assert first.status_code == 201, first.text
    replay = client.post(f"/api/cases/{child.id}/settlement-presentations",
                         json=body, headers={"Idempotency-Key": "b8-same"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]


def test_present_unknown_field_422(ready_linked_client):
    client, svc, child, report = ready_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version,
              "basis_report_id": report.run_id,
              "review": {"report_id": report.run_id, "note": "Đủ", "refs": []},
              "amount_vnd": 3_000_000},
        headers={"Idempotency-Key": "b8-extra"})
    assert response.status_code == 422, response.text


def test_approve_via_api(ready_linked_client):
    client, svc, child, report = ready_linked_client
    presented = client.post(
        f"/api/cases/{child.id}/settlement-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version,
              "basis_report_id": report.run_id,
              "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": "b8-p2"})
    assert presented.status_code == 201, presented.text
    view = client.get(f"/api/cases/{child.id}").json()
    decision = client.post(
        f"/api/cases/{child.id}/settlement-decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "presentation_id": presented.json()["id"], "outcome": "APPROVE",
              "reason": "Duyệt theo kết quả đã rà soát"},
        headers={"Idempotency-Key": "b8-d1"})
    assert decision.status_code == 201, decision.text
    body = decision.json()
    assert body["kind"] == "B7_SETTLEMENT"
    assert body["target"]["amount_vnd"] == 3_000_000
    after = client.get(f"/api/cases/{child.id}").json()
    assert after["b7_workflow"]["status"] == "APPROVED"
    assert after["money_summary"]["received_vnd"] is None


def test_decide_client_amount_422(ready_linked_client):
    client, svc, child, report = ready_linked_client
    presented = client.post(
        f"/api/cases/{child.id}/settlement-presentations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version,
              "basis_report_id": report.run_id,
              "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        headers={"Idempotency-Key": "b8-p3"})
    view = client.get(f"/api/cases/{child.id}").json()
    response = client.post(
        f"/api/cases/{child.id}/settlement-decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "presentation_id": presented.json()["id"], "outcome": "APPROVE",
              "reason": "Duyệt", "amount_vnd": 2_000_000},
        headers={"Idempotency-Key": "b8-d2"})
    assert response.status_code == 422, response.text

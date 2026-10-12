"""B9 settlement fulfillment HTTP envelope: proof upload + typed money event.

Wires a real Store + fake reader via ``create_runtime_app(service=...)``; the
linked child is driven to a real APPROVE decision through the fake pipeline.
No real DB, no LIVE, no .env.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app
from invoice_referee.settlement.b3_intake import B3CompanyContext, B3Intake
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM
from tests.settlement.b7_workflow_builders import b7_config, make_ready_linked


@pytest.fixture
def approved_linked_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from tests.settlement.test_b3_workflow import command

    store = Store(tmp_path / "b9.sqlite", tmp_path / "artifacts")
    svc = Service(store, StructuredLedgerReader(store.artifact_root),
                  config=ServiceConfig(
                      authority=[], b7_context=b7_config(),
                      b3_context=B3CompanyContext.model_validate(CONTEXT)))
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
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("b9p", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt"},
        command("b9d", "APR-DEMO-01", "APPROVER", child.case_version))
    app = create_runtime_app(service=svc)
    with TestClient(app) as client:
        yield client, svc, svc.get_case(child.id), decision


def _money_text(amount=2_000_000, event_ref="TX-1"):
    return ("amount_vnd=%d\ncurrency=VND\npayer_ref=COMPANY\n"
            "payee_ref=NV-DEMO-01\nevent_at=2026-10-14T08:00:00+07:00\n"
            "receiver_outcome=RECEIVED\nevent_namespace=BANK:DEMO-ACCOUNT\n"
            "event_ref=%s\nmethod=BANK_TRANSFER\n"
            "purpose=REIMBURSEMENT_RECEIVED\n" % (amount, event_ref))


def test_proof_upload_and_money_event_via_api(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    proof = client.post(
        f"/api/cases/{child.id}/settlement-money-proofs",
        data={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version, "note": "chứng từ"},
        files={"file": ("proof.txt", _money_text().encode(), "text/plain")},
        headers={"Idempotency-Key": "b9-proof"})
    assert proof.status_code == 201, proof.text
    source_id = proof.json()["id"]
    view = client.get(f"/api/cases/{child.id}").json()
    response = client.post(
        f"/api/cases/{child.id}/settlement-money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "decision_id": decision.id, "event_namespace": "BANK:DEMO-ACCOUNT",
              "event_ref": "TX-1", "method": "BANK_TRANSFER", "gross_vnd": 2_000_000,
              "payer_ref": "COMPANY", "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-14T08:00:00+07:00",
              "reported_status": "RECEIVED", "purpose": "REIMBURSEMENT_RECEIVED",
              "allocation_note": "Đối chiếu",
              "evidence": [
                  {"field": "amount_vnd", "source_id": source_id, "locator": "a",
                   "raw": "2000000", "value": 2_000_000, "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "currency", "source_id": source_id, "locator": "c",
                   "raw": "VND", "value": "VND", "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "payer_ref", "source_id": source_id, "locator": "p",
                   "raw": "COMPANY", "value": "COMPANY", "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "payee_ref", "source_id": source_id, "locator": "y",
                   "raw": "NV-DEMO-01", "value": "NV-DEMO-01",
                   "read_state": "READ", "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "event_at", "source_id": source_id, "locator": "t",
                   "raw": "2026-10-14T08:00:00+07:00",
                   "value": "2026-10-14T08:00:00+07:00", "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "receiver_outcome", "source_id": source_id,
                   "locator": "o", "raw": "RECEIVED", "value": "RECEIVED",
                   "read_state": "READ", "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "event_namespace", "source_id": source_id,
                   "locator": "n", "raw": "BANK:DEMO-ACCOUNT",
                   "value": "BANK:DEMO-ACCOUNT", "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"},
                  {"field": "event_ref", "source_id": source_id, "locator": "r",
                   "raw": "TX-1", "value": "TX-1", "read_state": "READ",
                   "origin": "HUMAN_SOURCE_REVIEW"}]},
        headers={"Idempotency-Key": "b9-money"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["classification"] == "CONFIRMED_RECEIPT"
    after = client.get(f"/api/cases/{child.id}").json()
    assert after["b7_workflow"]["fulfillment"]["remaining_vnd"] == 1_000_000


def test_money_event_wrong_role_403(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-money-events",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": child.case_version, "decision_id": decision.id,
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": "TX-1",
              "method": "BANK_TRANSFER", "gross_vnd": 2_000_000,
              "payer_ref": "COMPANY", "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-14T08:00:00+07:00",
              "reported_status": "RECEIVED", "purpose": "REIMBURSEMENT_RECEIVED",
              "allocation_note": "x", "evidence": []},
        headers={"Idempotency-Key": "b9-bad"})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "BEYOND_AUTHORITY"


def test_money_event_unknown_field_422(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version, "decision_id": decision.id,
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": "TX-1",
              "method": "BANK_TRANSFER", "gross_vnd": 2_000_000,
              "payer_ref": "COMPANY", "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-14T08:00:00+07:00",
              "reported_status": "RECEIVED", "purpose": "REIMBURSEMENT_RECEIVED",
              "allocation_note": "x", "evidence": [], "client_amount": 1},
        headers={"Idempotency-Key": "b9-extra"})
    assert response.status_code == 422, response.text


def test_money_event_zero_amount_422(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    response = client.post(
        f"/api/cases/{child.id}/settlement-money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": child.case_version, "decision_id": decision.id,
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": "TX-1",
              "method": "BANK_TRANSFER", "gross_vnd": 0,
              "payer_ref": "COMPANY", "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-14T08:00:00+07:00",
              "reported_status": "RECEIVED", "purpose": "REIMBURSEMENT_RECEIVED",
              "allocation_note": "x", "evidence": []},
        headers={"Idempotency-Key": "b9-zero"})
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_PAYLOAD"


def _record_money_via_api(client, child, decision, source_id, *, amount,
                          ref, purpose="REIMBURSEMENT_RECEIVED",
                          payee="NV-DEMO-01", payer="COMPANY", key="ev"):
    evidence = [
        {"field": f, "source_id": source_id, "locator": f, "raw": str(v),
         "value": v, "read_state": "READ", "origin": "HUMAN_SOURCE_REVIEW"}
        for f, v in [("amount_vnd", amount), ("currency", "VND"),
                     ("payer_ref", payer), ("payee_ref", payee),
                     ("event_at", "2026-10-14T08:00:00+07:00"),
                     ("receiver_outcome", "RECEIVED"),
                     ("event_namespace", "BANK:DEMO-ACCOUNT"), ("event_ref", ref),
                     ("method", "BANK_TRANSFER"), ("purpose", purpose)]]
    view = client.get(f"/api/cases/{child.id}").json()
    return client.post(
        f"/api/cases/{child.id}/settlement-money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"], "decision_id": decision.id,
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": ref,
              "method": "BANK_TRANSFER", "gross_vnd": amount,
              "payer_ref": payer, "payee_ref": payee,
              "event_at": "2026-10-14T08:00:00+07:00",
              "reported_status": "RECEIVED", "purpose": purpose,
              "allocation_note": "Đối chiếu", "evidence": evidence},
        headers={"Idempotency-Key": key})


def _proof_via_api(client, child, *, amount, ref, key):
    text = _money_text(amount=amount, event_ref=ref)
    version = client.get(f"/api/cases/{child.id}").json()["case_version"]
    response = client.post(
        f"/api/cases/{child.id}/settlement-money-proofs",
        data={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": version},
        files={"file": (f"{key}.txt", text.encode(), "text/plain")},
        headers={"Idempotency-Key": f"proof-{key}"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_full_fulfillment_close_via_api(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    s1 = _proof_via_api(client, child, amount=2_000_000, ref="TX-1", key="a")
    _record_money_via_api(client, child, decision, s1, amount=2_000_000,
                          ref="TX-1", key="ev-a")
    s2 = _proof_via_api(client, child, amount=1_000_000, ref="TX-2", key="b")
    _record_money_via_api(client, child, decision, s2, amount=1_000_000,
                          ref="TX-2", key="ev-b")
    view = client.get(f"/api/cases/{child.id}").json()
    refreshed = client.post(
        f"/api/cases/{child.id}/settlement-money-context/refresh",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"]},
        headers={"Idempotency-Key": "b9-ctx"})
    assert refreshed.status_code == 200, refreshed.text
    view = client.get(f"/api/cases/{child.id}").json()
    run = client.post(f"/api/cases/{child.id}/runs",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": view["case_version"]},
        headers={"Idempotency-Key": "b9-run"})
    assert run.status_code in (200, 201, 202), run.text
    run_id = run.json()["id"]
    import time
    for _ in range(50):
        if client.get(f"/api/runs/{run_id}").json()["status"] == "SUCCEEDED":
            break
        time.sleep(0.05)
    view = client.get(f"/api/cases/{child.id}").json()
    reval = client.post(f"/api/cases/{child.id}/settlement-revalidations",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"]},
        headers={"Idempotency-Key": "b9-reval"})
    assert reval.status_code == 201, reval.text
    assert reval.json()["status"] == "VALID", reval.text
    view = client.get(f"/api/cases/{child.id}").json()
    closed = client.post(f"/api/cases/{child.id}/settlement-closures",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "decision_id": decision.id, "current_report_id": run_id,
              "reason": "Đủ căn cứ, hết nghĩa vụ"},
        headers={"Idempotency-Key": "b9-close"})
    assert closed.status_code == 201, closed.text
    assert closed.json()["kind"] == "SETTLEMENT_COMPLETE"
    after = client.get(f"/api/cases/{child.id}").json()
    assert after["stage"] == "SETTLEMENT_CLOSED"


def test_handoff_via_api(approved_linked_client):
    client, svc, child, decision = approved_linked_client
    s1 = _proof_via_api(client, child, amount=2_000_000, ref="TX-1", key="h")
    _record_money_via_api(client, child, decision, s1, amount=2_000_000,
                          ref="TX-1", key="ev-h")
    view = client.get(f"/api/cases/{child.id}").json()
    handoff = client.post(f"/api/cases/{child.id}/settlement-handoffs",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
        headers={"Idempotency-Key": "b9-handoff"})
    assert handoff.status_code == 201, handoff.text
    assert handoff.json()["remaining_vnd"] == 1_000_000

"""W05 API slice: decision/review/money/control/handoff/closure over HTTP.

Runs the same service the UI uses; expected codes follow System §S6 mapping.
Numbers come from the Rulebook formula on the synthetic ledger, not the engine.
"""
from __future__ import annotations

import time

import pytest

from invoice_referee.api.settlement import create_runtime_app

SUBMISSION_PAYLOAD = {
    "employee_ref": "NV-01",
    "work_ref": "CT-W05",
    "job": "B7",
    "money_as_of": "2026-10-08T11:00:00Z",
    "knowledge_cutoff": "2026-10-08T11:00:00Z",
    "form": {"purpose": "Công tác A"},
}

LEDGER = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 2000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 0\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    app = create_runtime_app(db_path=tmp_path / "cases.sqlite",
                             artifact_root=tmp_path / "sources")
    return TestClient(app)


def _get_case(client, case_id: str) -> dict:
    return client.get(f"/api/cases/{case_id}").json()


def _succeeded_case(client) -> dict:
    created = client.post("/api/cases", json={
        "submission": SUBMISSION_PAYLOAD,
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "create-1"})
    assert created.status_code == 201, created.text
    case = created.json()
    upload = client.post(f"/api/cases/{case['id']}/sources",
                        files={"file": ("d.txt", LEDGER.encode("utf-8"),
                                        "text/plain")},
                        data={"actor_id": "NV-01", "demo_role": "EMPLOYEE",
                              "expected_case_version": str(case["case_version"])},
                        headers={"Idempotency-Key": "src-1"})
    assert upload.status_code == 201, upload.text
    view = _get_case(client, case["id"])
    run = client.post(f"/api/cases/{case['id']}/runs", json={
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        "expected_case_version": view["case_version"],
    }, headers={"Idempotency-Key": "run-1"})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = client.get(f"/api/runs/{run_id}").json()
        if current["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT",
                                  "STOPPED", "SUPERSEDED", "INTERRUPTED"}:
            break
        time.sleep(0.05)
    assert current["status"] == "SUCCEEDED", current
    return _get_case(client, case["id"])


def _decision_payload(view: dict, **overrides) -> dict:
    payload = {
        "actor_id": "P-DEMO", "demo_role": "APPROVER",
        "expected_case_version": view["case_version"],
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE", "reason": "duyệt theo report",
        "basis_report_id": view["current_run_id"], "conditions": [],
    }
    payload.update(overrides)
    return payload


def test_decision_endpoint_authority_replay_and_conflict(client):
    view = _succeeded_case(client)
    beyond = client.post(f"/api/cases/{view['id']}/decisions",
                        json=_decision_payload(view, actor_id="NV-01",
                                               demo_role="EMPLOYEE"),
                        headers={"Idempotency-Key": "dec-x"})
    assert beyond.status_code == 403, beyond.text
    assert beyond.json()["code"] == "BEYOND_AUTHORITY"

    first = client.post(f"/api/cases/{view['id']}/decisions",
                        json=_decision_payload(view),
                        headers={"Idempotency-Key": "dec-1"})
    assert first.status_code == 201, first.text
    decision = first.json()
    assert decision["amount_vnd"] == 3_000_000
    assert decision["basis_report_id"] == view["current_run_id"]

    replay = client.post(f"/api/cases/{view['id']}/decisions",
                        json=_decision_payload(view),
                        headers={"Idempotency-Key": "dec-1"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"] is True

    conflict = client.post(f"/api/cases/{view['id']}/decisions",
                           json=_decision_payload(view, amount_vnd=2_000_000),
                           headers={"Idempotency-Key": "dec-1"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    after = _get_case(client, view["id"])
    assert after["stage"] == "AWAITING_MONEY"
    assert after["money_summary"]["approved_vnd"] == 3_000_000
    assert after["money_summary"]["remaining_vnd"] == 3_000_000


def test_review_endpoint_is_not_approval(client):
    view = _succeeded_case(client)
    carrying_amount = client.post(
        f"/api/cases/{view['id']}/reviews",
        json={"actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "report_id": view["current_run_id"], "note": "x",
              "refs": [], "amount_vnd": 1},
        headers={"Idempotency-Key": "rev-bad"})
    assert carrying_amount.status_code == 400, carrying_amount.text
    assert carrying_amount.json()["code"] == "REVIEW_NOT_APPROVAL"

    review = client.post(
        f"/api/cases/{view['id']}/reviews",
        json={"actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "report_id": view["current_run_id"],
              "note": "Đã rà soát đối chiếu và mở nguồn.",
              "refs": []},
        headers={"Idempotency-Key": "rev-1"})
    assert review.status_code == 201, review.text
    # review không tạo approval
    assert _get_case(client, view["id"])["money_summary"]["approved_vnd"] is None


def test_money_endpoint_dedup_and_summary_incidents(client):
    view = _succeeded_case(client)
    first = client.post(f"/api/cases/{view['id']}/money-events", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": view["case_version"],
        "event_ref": "EV-1", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 4_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00Z", "reported_status": "RECEIVED",
        "refs": [],
    }, headers={"Idempotency-Key": "money-1"})
    assert first.status_code == 201, first.text

    duplicate = client.post(f"/api/cases/{view['id']}/money-events", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "event_ref": "EV-1", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 4_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00Z", "reported_status": "RECEIVED",
        "refs": [],
    }, headers={"Idempotency-Key": "money-2"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "DUPLICATE_EVENT_REF"


def test_stop_handoff_and_closure_endpoints(client):
    view = _succeeded_case(client)
    decision = client.post(f"/api/cases/{view['id']}/decisions",
                          json=_decision_payload(view),
                          headers={"Idempotency-Key": "dec-1"}).json()

    stop = client.post(f"/api/cases/{view['id']}/control", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "action": "STOP", "reason": "kiểm tra",
    }, headers={"Idempotency-Key": "stop-1"})
    assert stop.status_code == 201, stop.text
    assert stop.json()["stop_active"] is True

    stopped_view = _get_case(client, view["id"])
    handoff = client.post(f"/api/cases/{view['id']}/handoffs", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": stopped_view["case_version"],
        "decision_id": decision["id"],
    }, headers={"Idempotency-Key": "hand-1"})
    assert handoff.status_code == 409
    assert handoff.json()["code"] == "STOP_ACTIVE"

    resume = client.post(f"/api/cases/{view['id']}/control", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "action": "RESUME", "reason": "đã xử lý",
    }, headers={"Idempotency-Key": "resume-1"})
    assert resume.status_code == 201, resume.text
    assert resume.json()["stop_active"] is False

    fresh = _get_case(client, view["id"])
    handoff = client.post(f"/api/cases/{view['id']}/handoffs", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": fresh["case_version"],
        "decision_id": decision["id"],
    }, headers={"Idempotency-Key": "hand-2"})
    assert handoff.status_code == 201, handoff.text
    assert handoff.json()["decision_id"] == decision["id"]

    blocked = client.post(f"/api/cases/{view['id']}/closures", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "kind": "SETTLEMENT_COMPLETE", "basis": "x",
    }, headers={"Idempotency-Key": "close-1"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "CLOSURE_BLOCKED"

    paid = client.post(f"/api/cases/{view['id']}/money-events", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "event_ref": "EV-PAY", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 3_000_000, "decision_id": decision["id"],
        "payee_ref": "NV-01", "event_at": "2026-10-08T13:00:00Z",
        "reported_status": "RECEIVED", "refs": [],
    }, headers={"Idempotency-Key": "money-pay"})
    assert paid.status_code == 201, paid.text

    closed = client.post(f"/api/cases/{view['id']}/closures", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "kind": "SETTLEMENT_COMPLETE",
        "basis": "Đã thực nhận đủ 3.000.000; remaining 0, không còn incident.",
    }, headers={"Idempotency-Key": "close-2"})
    assert closed.status_code == 201, closed.text
    assert _get_case(client, view["id"])["stage"] == "SETTLEMENT_CLOSED"

    again = client.post(f"/api/cases/{view['id']}/closures", json={
        "actor_id": "ACC-01", "demo_role": "ACCOUNTANT",
        "expected_case_version": _get_case(client, view["id"])["case_version"],
        "kind": "SETTLEMENT_COMPLETE", "basis": "nội dung khác",
    }, headers={"Idempotency-Key": "close-3"})
    assert again.status_code == 409
    assert again.json()["code"] == "CASE_CLOSED"

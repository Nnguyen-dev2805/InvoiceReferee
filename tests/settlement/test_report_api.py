"""W02 API slice: run B7 through the same service the UI uses.

Sources are synthetic "structured ledger" text files (fake reader mode); the
expected numbers come from the Rulebook formula, never from the engine.
"""
from __future__ import annotations

import time

import pytest

from invoice_referee.api.settlement import create_runtime_app

SUBMISSION_PAYLOAD = {
    "employee_ref": "NV-01",
    "work_ref": "CT-01",
    "job": "B7",
    "money_as_of": "2026-10-08T11:00:00Z",
    "knowledge_cutoff": "2026-10-08T11:00:00Z",
    "form": {"purpose": "Công tác A"},
}

Q01_BILL = (
    "# ledger giả lập: hóa đơn + chứng từ thanh toán\n"
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)
Q01_MONEY = (
    "fact F6 history.advance.received 2000000\n"
    "fact F7 history.advance.returned 0\n"
    "fact F8 history.reimbursement.received 0\n"
    "fact F9 history.reimbursement.returned 0\n"
    "fact F10 budget.approved 8000000\n"
)


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    app = create_runtime_app(db_path=tmp_path / "cases.sqlite",
                             artifact_root=tmp_path / "sources")
    return TestClient(app)


def _create_case(client, key="create-1") -> dict:
    response = client.post("/api/cases", json={
        "submission": SUBMISSION_PAYLOAD,
        "actor_id": "NV-01",
        "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, case_id: str, filename: str, content: str, version: int, key: str):
    response = client.post(f"/api/cases/{case_id}/sources",
                          files={"file": (filename, content.encode("utf-8"),
                                          "text/plain")},
                          data={"actor_id": "NV-01", "demo_role": "EMPLOYEE",
                                "expected_case_version": str(version)},
                          headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text
    return response.json()


def _start_run(client, case_id: str, version: int, key="run-1") -> dict:
    response = client.post(f"/api/cases/{case_id}/runs", json={
        "actor_id": "NV-01",
        "demo_role": "EMPLOYEE",
        "expected_case_version": version,
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 202, response.text
    return response.json()


def _wait_terminal(client, run_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT",
                             "STOPPED", "SUPERSEDED", "INTERRUPTED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run chưa terminal sau {timeout}s: {run}")


def _q01_setup(client) -> tuple[str, str]:
    case = _create_case(client)
    _upload(client, case["id"], "hoa-don.txt", Q01_BILL, case["case_version"], "src-1")
    view = client.get(f"/api/cases/{case['id']}").json()
    _upload(client, case["id"], "lich-su-tien.txt", Q01_MONEY, view["case_version"],
            "src-2")
    view = client.get(f"/api/cases/{case['id']}").json()
    run = _start_run(client, case["id"], view["case_version"])
    return run["id"], case["id"]


def test_q01_report_is_sourced_complete_and_proposed(client):
    run_id, case_id = _q01_setup(client)
    run = _wait_terminal(client, run_id)
    assert run["status"] == "SUCCEEDED", run
    assert run["completion"] == "COMPLETE"
    assert run["mode"] == "FAKE_OR_REPLAY"

    report = client.get(f"/api/runs/{run_id}/report").json()
    assert report["components"]["e"]["value"] == 5_000_000
    assert report["components"]["a"]["value"] == 2_000_000
    assert report["components"]["t"]["value"] == 5_000_000
    assert report["components"]["b"]["value"] == 8_000_000
    assert report["calculated_net_vnd"] == 3_000_000
    assert report["proposed_net_vnd"] == 3_000_000
    assert report["issues"] == []
    assert report["completion"] == "COMPLETE"
    row = report["expense_rows"][0]
    assert row["expense_id"] == "EXP-1"
    assert row["eligible_employee_vnd"] == 5_000_000
    assert row["refs"], "phải có refs để mở nguồn từ từng số"
    # report refs phải mở được nguồn thật
    source_ids = {s["id"] for s in
                  client.get(f"/api/cases/{case_id}").json()["sources"]}
    assert source_ids


def test_q03_negative_net_via_same_service(client):
    case = _create_case(client, key="create-q03")
    bill = Q01_BILL.replace("5000000", "3300000")
    _upload(client, case["id"], "hoa-don.txt", bill, case["case_version"], "src-1")
    money = Q01_MONEY.replace("fact F6 history.advance.received 2000000",
                              "fact F6 history.advance.received 4000000")
    view = client.get(f"/api/cases/{case['id']}").json()
    _upload(client, case["id"], "lich-su-tien.txt", money, view["case_version"], "src-2")
    view = client.get(f"/api/cases/{case['id']}").json()
    run = _start_run(client, case["id"], view["case_version"], key="run-q03")
    _wait_terminal(client, run["id"])
    report = client.get(f"/api/runs/{run['id']}/report").json()
    assert report["calculated_net_vnd"] == -700_000
    assert report["proposed_net_vnd"] == -700_000


def test_q04_zero_balance_creates_no_request_or_approval(client):
    case = _create_case(client, key="create-q04")
    _upload(client, case["id"], "hoa-don.txt", Q01_BILL, case["case_version"], "src-1")
    money = Q01_MONEY.replace("fact F8 history.reimbursement.received 0",
                              "fact F8 history.reimbursement.received 3000000")
    view = client.get(f"/api/cases/{case['id']}").json()
    _upload(client, case["id"], "lich-su-tien.txt", money, view["case_version"], "src-2")
    view = client.get(f"/api/cases/{case['id']}").json()
    run = _start_run(client, case["id"], view["case_version"], key="run-q04")
    _wait_terminal(client, run["id"])
    report = client.get(f"/api/runs/{run['id']}/report").json()
    assert report["calculated_net_vnd"] == 0
    assert report["proposed_net_vnd"] == 0
    assert report["completion"] == "COMPLETE"
    flattened = report
    assert "payment_request" not in flattened
    assert "approved" not in flattened


def test_unknown_amount_report_is_incomplete_with_fact_issue(client):
    case = _create_case(client, key="create-unknown")
    bill = (
        "unclear F1 expense.EXP-1.amount tổng bị che một góc\n"
        "fact F2 expense.EXP-1.purpose BUSINESS\n"
    )
    _upload(client, case["id"], "hoa-don.txt", bill, case["case_version"], "src-1")
    _upload(client, case["id"], "lich-su-tien.txt", Q01_MONEY, 2, "src-2")
    view = client.get(f"/api/cases/{case['id']}").json()
    run = _start_run(client, case["id"], view["case_version"], key="run-unknown")
    _wait_terminal(client, run["id"])
    run = client.get(f"/api/runs/{run['id']}").json()
    assert run["status"] == "SUCCEEDED"
    assert run["completion"] == "INCOMPLETE"
    report = client.get(f"/api/runs/{run['id']}/report").json()
    assert report["calculated_net_vnd"] is None
    assert report["proposed_net_vnd"] is None
    assert any(i["type"] == "FACT" and i["unresolved"] for i in report["issues"])


def test_get_report_does_not_recompute(client):
    run_id, _ = _q01_setup(client)
    _wait_terminal(client, run_id)
    first = client.get(f"/api/runs/{run_id}/report").json()
    second = client.get(f"/api/runs/{run_id}/report").json()
    assert first == second
    assert first["generated_at"] == second["generated_at"]


def test_start_run_retry_same_key_returns_same_run(client):
    case = _create_case(client, key="create-retry")
    _upload(client, case["id"], "hoa-don.txt", Q01_BILL, case["case_version"], "src-1")
    view = client.get(f"/api/cases/{case['id']}").json()
    _upload(client, case["id"], "lich-su-tien.txt", Q01_MONEY, view["case_version"],
            "src-2")
    view = client.get(f"/api/cases/{case['id']}").json()
    first = client.post(f"/api/cases/{case['id']}/runs", json={
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        "expected_case_version": view["case_version"],
    }, headers={"Idempotency-Key": "run-retry"})
    assert first.status_code == 202
    replay = client.post(f"/api/cases/{case['id']}/runs", json={
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        "expected_case_version": view["case_version"] + 1,
    }, headers={"Idempotency-Key": "run-retry"})
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    _wait_terminal(client, first.json()["id"])
    # Snapshot đổi (bổ sung nguồn) → same key khác payload phải bị chặn
    _upload(client, case["id"], "nguon-them.txt", "fact F99 budget.approved 9000000\n",
            view["case_version"] + 1, "src-3")
    conflict = client.post(f"/api/cases/{case['id']}/runs", json={
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        "expected_case_version": view["case_version"] + 2,
    }, headers={"Idempotency-Key": "run-retry"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_start_run_stale_version_blocked(client):
    case = _create_case(client, key="create-stale")
    stale = client.post(f"/api/cases/{case['id']}/runs", json={
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        "expected_case_version": 99,
    }, headers={"Idempotency-Key": "run-stale"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "STALE_VERSION"


def test_report_not_ready_returns_run_status(client):
    case = _create_case(client, key="create-notready")
    run = _start_run(client, case["id"], case["case_version"], key="run-notready")
    response = client.get(f"/api/runs/{run['id']}/report")
    assert response.status_code in {200, 409}
    if response.status_code == 409:
        assert response.json()["code"] == "REPORT_NOT_READY"
    _wait_terminal(client, run["id"])
    ok = client.get(f"/api/runs/{run['id']}/report")
    assert ok.status_code == 200

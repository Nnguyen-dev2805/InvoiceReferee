"""Task 2: B3 v1 intake API — persona, idempotent work id, snapshot context,
B3_REPORT_ONLY transaction guards (Product P2a, System S6).

The client fixture wires a real Store + fake reader + explicit ServiceConfig
(packet-literal context); tests depend on no real DB and no .env.
"""
from __future__ import annotations

import pytest

from invoice_referee.api.settlement import create_runtime_app
from invoice_referee.settlement.b3 import B3CompanyContext
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM


@pytest.fixture
def b3_client(tmp_path):
    from fastapi.testclient import TestClient

    store = Store(tmp_path / "b3.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    service = Service(store, reader, config=ServiceConfig(
        authority=[],
        b3_context=B3CompanyContext.model_validate(CONTEXT),
    ))
    app = create_runtime_app(service=service)
    with TestClient(app) as client:
        yield client


def _create_b3(client, payload, key="create-b3", expect=201):
    response = client.post("/api/b3-cases", json=payload,
                          headers={"Idempotency-Key": key})
    assert response.status_code == expect, response.text
    return response


def _web_payload(**form_overrides) -> dict:
    form = dict(NATIVE_FORM)
    form.update(form_overrides)
    return {"actor_id": "NV-DEMO-01", "intake": form}


# --- demo context -------------------------------------------------------------

def test_demo_context_lists_people_routes(b3_client):
    response = b3_client.get("/api/demo-context")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == "synthetic-verbal-v2"
    assert body["synthetic"] is True
    assert body["demo_clock"] is not None
    assert {p["actor_ref"] for p in body["people"]} == {
        "NV-DEMO-01", "ACC-DEMO-01", "APR-DEMO-01"}
    assert body["routes"][0]["approver_ref"] == "APR-DEMO-01"
    # endpoint không cấp quyền do client nhập: không trả grants
    assert "grants" not in body


# --- POST /api/b3-cases -------------------------------------------------------

def test_create_web_auto_profile_work_clock(b3_client):
    created = _create_b3(b3_client, _web_payload()).json()
    submission = created["submission"]
    assert submission["employee_ref"] == "NV-DEMO-01"
    assert submission["work_ref"].startswith("WORK-")
    assert submission["job"] == "B3"
    assert submission["form"]["schema_version"] == "b3-intake-v1"
    # clock mô phỏng của fixture synthetic, không phải giờ máy client
    assert submission["money_as_of"] == "2026-10-10T09:00:00+07:00"
    assert submission["knowledge_cutoff"] == "2026-10-10T09:00:00+07:00"


def test_create_retry_keeps_generated_work(b3_client):
    payload = {"actor_id": "NV-DEMO-01",
               "intake": NATIVE_FORM}
    headers = {"Idempotency-Key": "same-command"}
    first = b3_client.post("/api/b3-cases", json=payload, headers=headers)
    second = b3_client.post("/api/b3-cases", json=payload, headers=headers)
    assert first.status_code < 300 and second.status_code < 300
    assert first.json()["id"] == second.json()["id"]
    assert (first.json()["submission"]["work_ref"]
            == second.json()["submission"]["work_ref"])
    assert second.json()["idempotent_replay"] is True


def test_create_same_key_changed_payload_conflicts(b3_client):
    _create_b3(b3_client, _web_payload(), key="conflict-key")
    response = _create_b3(b3_client, _web_payload(request_amount_vnd=3_000_000),
                         key="conflict-key", expect=409)
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_rejects_fake_actor(b3_client):
    response = _create_b3(b3_client, {
        "actor_id": "NV-KHONG-TON-TAI", "intake": NATIVE_FORM},
        expect=403)
    assert response.json()["code"] == "PERSONA_MISMATCH"


def test_create_rejects_approver_persona_as_submitter(b3_client):
    response = _create_b3(b3_client, {
        "actor_id": "APR-DEMO-01", "intake": NATIVE_FORM},
        expect=403)
    assert response.json()["code"] == "PERSONA_MISMATCH"


def test_create_rejects_employee_supplied_context(b3_client):
    form = dict(NATIVE_FORM)
    form["grants"] = [{"actor_ref": "NV-DEMO-01", "max_advance_vnd": 10**9}]
    response = _create_b3(b3_client, {
        "actor_id": "NV-DEMO-01", "intake": form}, expect=400)
    assert response.json()["code"] == "INVALID_PAYLOAD"


def test_legacy_create_case_rejects_b3_intake_form(b3_client):
    response = b3_client.post("/api/cases", json={
        "submission": {
            "employee_ref": "NV-DEMO-01", "work_ref": "WORK-TU-NHAP",
            "job": "B3",
            "money_as_of": "2026-10-10T09:00:00+07:00",
            "knowledge_cutoff": "2026-10-10T09:00:00+07:00",
            "form": NATIVE_FORM,
        },
        "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "legacy-b3"})
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_PAYLOAD"


def test_create_draft_import_allowed_empty(b3_client):
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    created = _create_b3(b3_client, {
        "actor_id": "NV-DEMO-01", "intake": draft}).json()
    assert created["submission"]["form"]["confirmed"] is False
    assert created["submission"]["form"]["request_amount_vnd"] is None


# --- PATCH submission ---------------------------------------------------------

def test_patch_b3_preserves_identity_and_updates_form(b3_client):
    created = _create_b3(b3_client, _web_payload()).json()
    form = dict(NATIVE_FORM)
    form["request_amount_vnd"] = 3_000_000
    response = b3_client.patch(
        f"/api/cases/{created['id']}/submission",
        json={
            "submission": {
                "employee_ref": "NV-THON-PHIEN",  # client không được đổi
                "work_ref": "WORK-THON-PHIEN",
                "job": "B3",
                "money_as_of": "2020-01-01T00:00:00Z",
                "knowledge_cutoff": "2020-01-01T00:00:00Z",
                "form": form,
            },
            "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
            "expected_case_version": created["case_version"],
            "reason": "Sửa số xin sau khi xem lại dự toán",
        },
        headers={"Idempotency-Key": "patch-b3-1"})
    assert response.status_code == 200, response.text
    view = response.json()
    submission = view["submission"]
    assert submission["employee_ref"] == "NV-DEMO-01"
    assert submission["work_ref"] == created["submission"]["work_ref"]
    assert submission["money_as_of"] == created["submission"]["money_as_of"]
    assert submission["form"]["request_amount_vnd"] == 3_000_000
    assert view["input_revision"] == created["input_revision"] + 1


def test_patch_b3_stale_version_rejected(b3_client):
    created = _create_b3(b3_client, _web_payload()).json()
    response = b3_client.patch(
        f"/api/cases/{created['id']}/submission",
        json={
            "submission": {**created["submission"], "form": NATIVE_FORM},
            "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
            "expected_case_version": created["case_version"] + 5,
            "reason": "bản cũ",
        },
        headers={"Idempotency-Key": "patch-b3-stale"})
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_VERSION"


def test_patch_b3_requires_intake_form(b3_client):
    created = _create_b3(b3_client, _web_payload()).json()
    response = b3_client.patch(
        f"/api/cases/{created['id']}/submission",
        json={
            "submission": {**created["submission"],
                           "form": {"purpose": "x", "scope": "y"}},
            "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
            "expected_case_version": created["case_version"],
            "reason": "form sai loại",
        },
        headers={"Idempotency-Key": "patch-b3-legacy"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PAYLOAD"


def test_patch_legacy_case_rejects_intake_form(b3_client):
    created = b3_client.post("/api/cases", json={
        "submission": {
            "employee_ref": "NV-01", "work_ref": "CT-LEGACY", "job": "B3",
            "money_as_of": "2026-10-08T11:00:00Z",
            "knowledge_cutoff": "2026-10-08T11:00:00Z",
            "form": {"purpose": "Công tác legacy"},
        },
        "actor_id": "NV-01", "demo_role": "EMPLOYEE",
    }, headers={"Idempotency-Key": "legacy-create-1"})
    assert created.status_code == 201, created.text
    view = created.json()
    response = b3_client.patch(
        f"/api/cases/{view['id']}/submission",
        json={
            "submission": {**view["submission"], "form": NATIVE_FORM},
            "actor_id": "NV-01", "demo_role": "EMPLOYEE",
            "expected_case_version": view["case_version"],
            "reason": "cố di trú sang form mới",
        },
        headers={"Idempotency-Key": "patch-legacy-migrate"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PAYLOAD"


# --- B3_REPORT_ONLY transaction guards ---------------------------------------

def _confirmed_case_with_run(b3_client, key="b3-run") -> dict:
    created = _create_b3(b3_client, _web_payload(), key=key).json()
    run = b3_client.post(
        f"/api/cases/{created['id']}/runs",
        json={"actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version": created["case_version"]},
        headers={"Idempotency-Key": f"{key}-run"})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    for _ in range(100):
        status = b3_client.get(f"/api/runs/{run_id}").json()["status"]
        if status not in ("QUEUED", "RUNNING"):
            break
    return b3_client.get(f"/api/cases/{created['id']}").json()


def test_b3_settlement_decision_rejected(b3_client):
    view = _confirmed_case_with_run(b3_client)
    response = b3_client.post(
        f"/api/cases/{view['id']}/decisions",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "kind": "SETTLEMENT", "amount_vnd": 2_000_000,
              "direction": "PAY_EMPLOYEE",
              "reason": "cố duyệt ứng qua SETTLEMENT",
              "basis_report_id": view["current_run_id"]},
        headers={"Idempotency-Key": "b3-decide-1"})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "B3_REPORT_ONLY"


def test_b3_money_handoff_closure_rejected(b3_client):
    view = _confirmed_case_with_run(b3_client)
    case_id = view["id"]
    money = b3_client.post(
        f"/api/cases/{case_id}/money-events",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "event_ref": "EVT-1", "kind": "PAYMENT_TO_EMPLOYEE",
              "gross_vnd": 2_000_000, "payee_ref": "NV-DEMO-01",
              "event_at": "2026-10-10T10:00:00+07:00",
              "reported_status": "RECEIVED"},
        headers={"Idempotency-Key": "b3-money-1"})
    assert money.status_code == 409
    assert money.json()["code"] == "B3_REPORT_ONLY"
    closure = b3_client.post(
        f"/api/cases/{case_id}/closures",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "kind": "REJECTED_REQUEST_ENDED", "basis": "kết thúc"},
        headers={"Idempotency-Key": "b3-close-1"})
    assert closure.status_code == 409
    assert closure.json()["code"] == "B3_REPORT_ONLY"
    handoff = b3_client.post(
        f"/api/cases/{case_id}/handoffs",
        json={"actor_id": "APR-DEMO-01", "demo_role": "APPROVER",
              "expected_case_version": view["case_version"],
              "decision_id": "D-KHONG-CO"},
        headers={"Idempotency-Key": "b3-handoff-1"})
    assert handoff.status_code == 409
    assert handoff.json()["code"] == "B3_REPORT_ONLY"


def test_b3_allowed_actions_do_not_advertise_unsupported(b3_client):
    view = _confirmed_case_with_run(b3_client)
    actions = {a["action"] for a in view["allowed_actions"]}
    assert "DECIDE" not in actions
    assert "RECORD_MONEY" not in actions
    assert "CLOSE_CASE" not in actions
    assert "START_RUN" in actions or "REVIEW" in actions


def test_b3_draft_review_rejected_after_confirm_allowed(b3_client):
    draft = _create_b3(b3_client, {
        "actor_id": "NV-DEMO-01",
        "intake": {"schema_version": "b3-intake-v1",
                   "intake_method": "IMPORT", "confirmed": False}},
        key="b3-draft").json()
    view = b3_client.get(f"/api/cases/{draft['id']}").json()
    review = b3_client.post(
        f"/api/cases/{view['id']}/reviews",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "report_id": view["current_run_id"] or "R-NONE",
              "note": "rà soát draft"},
        headers={"Idempotency-Key": "b3-review-draft"})
    assert review.status_code == 409
    assert review.json()["code"] == "B3_REPORT_ONLY"


# --- run snapshot context -----------------------------------------------------

def test_run_b3_context_endpoint_returns_snapshot(b3_client):
    view = _confirmed_case_with_run(b3_client)
    run_id = view["current_run_id"]
    response = b3_client.get(f"/api/runs/{run_id}/b3-context")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == "synthetic-verbal-v2"
    assert body["grants"][0]["ref"] == "company:grant-01"
    assert body["coverage"][0]["ref"] == "company:coverage-01"
    assert body["history"] == []


def test_run_b3_context_unknown_run_404(b3_client):
    response = b3_client.get("/api/runs/R-KHONG-CO/b3-context")
    assert response.status_code == 404


def test_b3_control_stop_resume_still_works(b3_client):
    view = _confirmed_case_with_run(b3_client)
    stop = b3_client.post(
        f"/api/cases/{view['id']}/control",
        json={"actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
              "expected_case_version": view["case_version"],
              "action": "STOP", "reason": "chờ làm rõ"},
        headers={"Idempotency-Key": "b3-stop-1"})
    assert stop.status_code == 201, stop.text
    after = b3_client.get(f"/api/cases/{view['id']}").json()
    assert after["stop_active"] is True


# --- Task 5: fake integration flows (PIPELINE_FAKE_OR_REPLAY) -------------------

from pathlib import Path

from invoice_referee.settlement.b3 import load_b3_context

PACKET = Path("data/settlement/b3-verbal-v2")

B3_REQUEST_LEDGER = (
    "fact F1 document.role ADVANCE_REQUEST\n"
    "fact F2 person.name Nguyễn_An\n"
    "fact F3 trip.destination Hà_Nội\n"
    "fact F4 trip.start 2026-10-12\n"
    "fact F5 trip.end 2026-10-13\n"
    "fact F6 trip.purpose Khảo_sát_yêu_cầu_và_thống_nhất_phạm_vi_triển_khai_dự_án_tại_Hà_Nội.\n"
    "fact F7 advance.request.amount 2000000\n"
    "fact F8 advance.request.amount_words Hai_triệu_đồng\n"
    "fact F9 advance.request.amount_words_value 2000000\n"
    "fact F10 advance.settlement_due 2026-10-16\n"
)
B3_FORECAST_LEDGER = (
    "fact C1 document.role FORECAST\n"
    "fact C2 person.name Nguyễn_An\n"
    "fact C3 trip.destination Hà_Nội\n"
    "fact C4 trip.start 2026-10-12\n"
    "fact C5 trip.end 2026-10-13\n"
    "fact C6 forecast.row.flight.description Vé_máy_bay_khứ_hồi\n"
    "fact C7 forecast.row.flight.company 3000000\n"
    "fact C8 forecast.row.flight.employee 0\n"
    "fact C9 forecast.row.hotel.description Khách_sạn\n"
    "fact C10 forecast.row.hotel.company 0\n"
    "fact C11 forecast.row.hotel.employee 3000000\n"
    "fact C12 forecast.row.ground.description Di_chuyển_tại_Hà_Nội\n"
    "fact C13 forecast.row.ground.company 0\n"
    "fact C14 forecast.row.ground.employee 1000000\n"
    "fact C15 forecast.row.meal.description Bữa_ăn_phục_vụ_công_việc\n"
    "fact C16 forecast.row.meal.company 0\n"
    "fact C17 forecast.row.meal.employee 1000000\n"
    "fact C18 forecast.company 3000000\n"
    "fact C19 forecast.employee 5000000\n"
    "fact C20 forecast.total 8000000\n"
)


class _NormalizingLedgerReader(StructuredLedgerReader):
    """Ledger giả lập không chứa dấu cách trong value; chuẩn hóa lại như reader."""

    def read(self, source, keys, budget):
        observations = super().read(source, keys, budget)
        return [o.model_copy(update={"value": o.value.replace("_", " ")})
                if isinstance(o.value, str) and o.key != "document.role"
                else o for o in observations]


def _wait_run_terminal(client, run_id: str, timeout_s: float = 10.0) -> dict:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("QUEUED", "RUNNING"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run chưa terminal sau {timeout_s}s: {run}")


def _upload_b3(client, case_id, filename, content, version, key):
    response = client.post(f"/api/cases/{case_id}/sources",
                          files={"file": (filename,
                                          content.encode("utf-8"),
                                          "text/plain")},
                          data={"actor_id": "NV-DEMO-01",
                                "demo_role": "EMPLOYEE",
                                "expected_case_version": str(version)},
                          headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text
    return response.json()


def _start_b3_run(client, case_id, version, key):
    response = client.post(f"/api/cases/{case_id}/runs", json={
        "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
        "expected_case_version": version,
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 202, response.text
    return response.json()


@pytest.fixture
def b3_fake_client(tmp_path):
    """App với reader fake chuẩn hóa ledger — không phụ thuộc .env/DB thật."""
    from fastapi.testclient import TestClient

    store = Store(tmp_path / "b3.sqlite", tmp_path / "artifacts")
    reader = _NormalizingLedgerReader(store.artifact_root)
    service = Service(store, reader, config=ServiceConfig(
        authority=[],
        b3_context=B3CompanyContext.model_validate(CONTEXT),
    ))
    app = create_runtime_app(service=service)
    with TestClient(app) as client:
        yield client


def test_native_submitted_run_report(b3_fake_client):
    created = _create_b3(b3_fake_client, _web_payload(), key="native-1").json()
    run = _start_b3_run(b3_fake_client, created["id"],
                        created["case_version"], "native-run-1")
    ended = _wait_run_terminal(b3_fake_client, run["id"])
    assert ended["status"] == "SUCCEEDED", ended
    report = b3_fake_client.get(f"/api/runs/{run['id']}/report").json()
    assert report["b3"] is not None
    assert report["b3"]["readiness"] == "READY_FOR_ACCOUNTANT_REVIEW"
    assert report["b3"]["forecast_company_vnd"] == 3_000_000
    assert report["b3"]["forecast_employee_vnd"] == 5_000_000
    assert report["b3"]["forecast_total_vnd"] == 8_000_000
    assert report["components"]["a"]["value"] == 0
    assert report["components"]["b"]["value"] is None
    assert report["b3"]["work_permission"] == "PENDING_DECISION"
    assert report["b3"]["advance_approval"] == "PENDING_DECISION"
    assert report["completion"] == "COMPLETE"
    assert report["issues"] == []


def test_import_preview_then_confirm_keeps_source_refs(b3_fake_client):
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    created = _create_b3(b3_fake_client, {
        "actor_id": "NV-DEMO-01", "intake": draft},
        key="import-1").json()
    case_id = created["id"]
    version = created["case_version"]
    req_source = _upload_b3(b3_fake_client, case_id, "de-nghi.txt",
                             B3_REQUEST_LEDGER, version, "src-req")
    view = b3_fake_client.get(f"/api/cases/{case_id}").json()
    _upload_b3(b3_fake_client, case_id, "du-toan.txt", B3_FORECAST_LEDGER,
               view["case_version"], "src-fc")
    view = b3_fake_client.get(f"/api/cases/{case_id}").json()
    run = _start_b3_run(b3_fake_client, case_id, view["case_version"],
                        "preview-run")
    ended = _wait_run_terminal(b3_fake_client, run["id"])
    assert ended["status"] == "SUCCEEDED", ended
    report = b3_fake_client.get(f"/api/runs/{run['id']}/report").json()
    # preview: draft chưa nộp, nhưng facts đã có nguồn/refs
    assert report["b3"]["readiness"] == "DRAFT_CONFIRMATION_REQUIRED"
    assert report["b3"]["forecast_total_vnd"] == 8_000_000
    refs = report["b3"]["field_refs"]["request_amount_vnd"]
    assert any(req_source["id"] in ref for ref in refs)

    # confirm PATCH với full fields (khớp giấy) rồi chạy lại
    confirm_form = {
        "schema_version": "b3-intake-v1", "intake_method": "IMPORT",
        "confirmed": True, "destination": "Hà Nội",
        "trip_start": "2026-10-12", "trip_end": "2026-10-13",
        "purpose": "Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án "
                   "tại Hà Nội.",
        "assignment_note": None, "request_amount_vnd": 2_000_000,
        "settlement_due": "2026-10-16",
        "estimate_rows": [
            {"row_id": "flight", "description": "Vé máy bay khứ hồi",
             "basis": "1 vé khứ hồi", "company_vnd": 3_000_000,
             "employee_vnd": 0},
            {"row_id": "hotel", "description": "Khách sạn", "basis": "1 đêm",
             "company_vnd": 0, "employee_vnd": 3_000_000},
            {"row_id": "ground", "description": "Di chuyển tại Hà Nội",
             "basis": "Tổng chi phí di chuyển dự kiến",
             "company_vnd": 0, "employee_vnd": 1_000_000},
            {"row_id": "meal", "description": "Bữa ăn phục vụ công việc",
             "basis": "Tổng chi phí bữa ăn dự kiến",
             "company_vnd": 0, "employee_vnd": 1_000_000},
        ],
    }
    patched = b3_fake_client.patch(
        f"/api/cases/{case_id}/submission",
        json={"submission": {**created["submission"], "form": confirm_form},
              "actor_id": "NV-DEMO-01", "demo_role": "EMPLOYEE",
              "expected_case_version":
                  b3_fake_client.get(f"/api/cases/{case_id}").json()["case_version"],
              "reason": "Đã rà soát bản nháp, xác nhận nộp"},
        headers={"Idempotency-Key": "confirm-1"})
    assert patched.status_code == 200, patched.text
    view = b3_fake_client.get(f"/api/cases/{case_id}").json()
    run2 = _start_b3_run(b3_fake_client, case_id, view["case_version"],
                         "confirm-run")
    ended2 = _wait_run_terminal(b3_fake_client, run2["id"])
    assert ended2["status"] == "SUCCEEDED", ended2
    report2 = b3_fake_client.get(f"/api/runs/{run2['id']}/report").json()
    assert report2["b3"]["readiness"] == "READY_FOR_ACCOUNTANT_REVIEW"
    assert report2["b3"]["intake"]["confirmed"] is True
    # original refs vẫn giữ sau confirm (không silently supersede)
    refs2 = report2["b3"]["field_refs"]["request_amount_vnd"]
    assert any(req_source["id"] in ref for ref in refs2)


def test_matcher_spy_not_called_for_b3v1_but_called_for_b7(tmp_path):
    """reader.match không được gọi cho B3 v1; B7 vẫn gọi (plan Task 5)."""
    from fastapi.testclient import TestClient

    class MatchSpyReader(_NormalizingLedgerReader):
        def __init__(self, root):
            super().__init__(root)
            self.match_calls = 0

        def match(self, run_input, candidates, budget):
            self.match_calls += 1
            return super().match(run_input, candidates, budget)

    store = Store(tmp_path / "spy.sqlite", tmp_path / "artifacts")
    reader = MatchSpyReader(store.artifact_root)
    service = Service(store, reader, config=ServiceConfig(
        authority=[],
        b3_context=B3CompanyContext.model_validate(CONTEXT)))
    app = create_runtime_app(service=service)
    with TestClient(app) as client:
        created = _create_b3(client, _web_payload(), key="spy-b3").json()
        run = _start_b3_run(client, created["id"],
                            created["case_version"], "spy-b3-run")
        _wait_run_terminal(client, run["id"])
        assert reader.match_calls == 0

        b7 = client.post("/api/cases", json={
            "submission": {
                "employee_ref": "NV-01", "work_ref": "CT-1", "job": "B7",
                "money_as_of": "2026-10-08T11:00:00Z",
                "knowledge_cutoff": "2026-10-08T11:00:00Z",
                "form": {"purpose": "B7"},
            },
            "actor_id": "NV-01", "demo_role": "EMPLOYEE",
        }, headers={"Idempotency-Key": "spy-b7"})
        view = client.get(f"/api/cases/{b7.json()['id']}").json()
        run7 = _start_b3_run(client, view["id"], view["case_version"],
                             "spy-b7-run")
        _wait_run_terminal(client, run7["id"])
        assert reader.match_calls == 1


def test_run_context_snapshot_immutable_when_config_changes(tmp_path):
    from fastapi.testclient import TestClient

    store = Store(tmp_path / "ctx.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    context_a = B3CompanyContext.model_validate(CONTEXT)
    service_a = Service(store, reader, config=ServiceConfig(
        authority=[], b3_context=context_a))
    app_a = create_runtime_app(service=service_a)
    with TestClient(app_a) as client:
        created = _create_b3(client, _web_payload(), key="ctx-1").json()
        run = _start_b3_run(client, created["id"],
                            created["case_version"], "ctx-run-1")
        _wait_run_terminal(client, run["id"])
        old = client.get(f"/api/runs/{run['id']}/b3-context").json()
    assert old["grants"][0]["max_budget_vnd"] == 10_000_000

    # đổi config sau run: run mới mang snapshot mới, run cũ giữ nguyên
    changed = {**CONTEXT,
               "grants": [{**CONTEXT["grants"][0],
                           "max_budget_vnd": 7_000_000}]}
    service_b = Service(store, reader, config=ServiceConfig(
        authority=[], b3_context=B3CompanyContext.model_validate(changed)))
    app_b = create_runtime_app(service=service_b)
    with TestClient(app_b) as client:
        created2 = _create_b3(client, _web_payload(), key="ctx-2").json()
        run2 = _start_b3_run(client, created2["id"],
                             created2["case_version"], "ctx-run-2")
        _wait_run_terminal(client, run2["id"])
        new = client.get(f"/api/runs/{run2['id']}/b3-context").json()
        still_old = client.get(f"/api/runs/{run['id']}/b3-context").json()
    assert new["grants"][0]["max_budget_vnd"] == 7_000_000
    assert still_old["grants"][0]["max_budget_vnd"] == 10_000_000


def test_stop_and_revise_during_b3_run_are_controlled(tmp_path):
    import threading

    from fastapi.testclient import TestClient

    class BarrierReader(StructuredLedgerReader):
        def __init__(self, root):
            super().__init__(root)
            self.entered = threading.Event()
            self.release = threading.Event()

        def read(self, source, keys, budget):
            self.entered.set()
            assert self.release.wait(timeout=10)
            return super().read(source, keys, budget)

    store = Store(tmp_path / "ctrl.sqlite", tmp_path / "artifacts")
    reader = BarrierReader(store.artifact_root)
    service = Service(store, reader, config=ServiceConfig(
        authority=[], b3_context=B3CompanyContext.model_validate(CONTEXT)))
    app = create_runtime_app(service=service)
    try:
        with TestClient(app) as client:
            created = _create_b3(client, {
                "actor_id": "NV-DEMO-01",
                "intake": {"schema_version": "b3-intake-v1",
                           "intake_method": "IMPORT", "confirmed": False}},
                key="ctrl-1").json()
            case_id = created["id"]
            _upload_b3(client, case_id, "de-nghi.txt", B3_REQUEST_LEDGER,
                       created["case_version"], "ctrl-src-1")
            view = client.get(f"/api/cases/{case_id}").json()
            _upload_b3(client, case_id, "du-toan.txt", B3_FORECAST_LEDGER,
                       view["case_version"], "ctrl-src-2")
            view = client.get(f"/api/cases/{case_id}").json()
            run = _start_b3_run(client, case_id, view["case_version"],
                                "ctrl-run-1")
            assert reader.entered.wait(timeout=10)
            view = client.get(f"/api/cases/{case_id}").json()
            stop = client.post(f"/api/cases/{case_id}/control", json={
                "actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
                "expected_case_version": view["case_version"],
                "action": "STOP", "reason": "chờ làm rõ giữa run",
            }, headers={"Idempotency-Key": "ctrl-stop"})
            assert stop.status_code == 201, stop.text
            reader.release.set()
            ended = _wait_run_terminal(client, run["id"])
            assert ended["status"] == "STOPPED"  # output muộn không thành current
            report = client.get(f"/api/runs/{run['id']}/report")
            assert report.status_code == 409  # REPORT_NOT_READY
            resume = client.post(f"/api/cases/{case_id}/control", json={
                "actor_id": "ACC-DEMO-01", "demo_role": "ACCOUNTANT",
                "expected_case_version":
                    client.get(f"/api/cases/{case_id}").json()["case_version"],
                "action": "RESUME", "reason": "đã làm rõ",
            }, headers={"Idempotency-Key": "ctrl-resume"})
            assert resume.status_code == 201, resume.text
            view = client.get(f"/api/cases/{case_id}").json()
            run2 = _start_b3_run(client, case_id, view["case_version"],
                                 "ctrl-run-2")
            ended2 = _wait_run_terminal(client, run2["id"])
            assert ended2["status"] == "SUCCEEDED"
    finally:
        reader.release.set()


@pytest.mark.skipif(not PACKET.exists(), reason="packet b3-verbal-v2 local only")
def test_packet_context_hash_matches_manifest():
    import hashlib
    import json

    manifest = json.loads((PACKET / "manifest.json").read_text(encoding="utf-8"))
    entry = next(f for f in manifest["files"]
                if f["path"] == "company-context/context.json")
    digest = hashlib.sha256(
        (PACKET / "company-context" / "context.json").read_bytes()).hexdigest()
    assert digest == entry["sha256"]


@pytest.mark.skipif(not PACKET.exists(), reason="packet b3-verbal-v2 local only")
def test_native_run_matches_business_oracle(tmp_path):
    """Oracle (single-author, chưa phải measured gold) chỉ dùng làm assertion."""
    import json

    from fastapi.testclient import TestClient

    oracle = json.loads((PACKET / "expected" / "business-oracle.json")
                        .read_text(encoding="utf-8"))
    context = load_b3_context(PACKET / "company-context" / "context.json")
    store = Store(tmp_path / "oracle.sqlite", tmp_path / "artifacts")
    service = Service(store, StructuredLedgerReader(store.artifact_root),
                      config=ServiceConfig(authority=[], b3_context=context))
    app = create_runtime_app(service=service)
    with TestClient(app) as client:
        created = _create_b3(client, _web_payload(), key="oracle-1").json()
        run = _start_b3_run(client, created["id"],
                            created["case_version"], "oracle-run")
        ended = _wait_run_terminal(client, run["id"])
        assert ended["status"] == "SUCCEEDED", ended
        report = client.get(f"/api/runs/{run['id']}/report").json()
    proposal = report["b3"]
    assert proposal["readiness"] == oracle["readiness"]
    assert report["b3"]["intake"]["request_amount_vnd"] == oracle["request_vnd"]
    assert proposal["forecast_company_vnd"] == oracle["forecast_company_vnd"]
    assert proposal["forecast_employee_vnd"] == oracle["forecast_employee_vnd"]
    assert proposal["forecast_total_vnd"] == oracle["forecast_total_vnd"]
    assert report["components"]["a"]["value"] == oracle["actual_advance_vnd"]
    assert report["components"]["ra"]["value"] == oracle["actual_advance_return_vnd"]
    assert proposal["work_permission"] == oracle["work_permission"]
    assert proposal["advance_approval"] == oracle["advance_approval"]
    assert report["components"]["b"]["value"] == oracle["approved_budget_vnd"]
    assert report["calculated_net_vnd"] == oracle["net_settlement_vnd"]
    # must_not: không đòi giấy lệnh công tác, không tự duyệt/ghi received/đóng
    for issue in report["issues"]:
        assert "giấy lệnh" not in issue["message"]
        assert "travel order" not in issue["message"]
    assert report["completion"] == "COMPLETE"

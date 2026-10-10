import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient


def _load_app(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INVOICE_REFEREE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INVOICE_REFEREE_DISABLE_WORKER", "1")
    monkeypatch.setenv("UC03_DOCUMENT_PIPELINE_ENABLED", "0")
    module = importlib.import_module("app.fastapi_app")
    module = importlib.reload(module)
    return module.app


def test_fastapi_employee_and_accounting_pages_render(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _load_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        employee_page = client.get("/employee/settlements/new")
        assert employee_page.status_code == 200
        assert "Hoàn ứng và quyết toán chi phí" in employee_page.text
        assert "Thêm chứng từ" in employee_page.text
        assert "settlement-form.js?v=20261010-2" in employee_page.text
        assert client.get("/accounting/cases").status_code == 200
        assert "Hàng đợi hồ sơ" in client.get("/accounting/cases").text


def test_multipart_submission_is_visible_to_accounting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _load_app(tmp_path, monkeypatch)
    payload = {
        "settlement_type": "EMPLOYEE_REIMBURSEMENT",
        "source_type": "DIGITAL_FORM",
        "business_context": {"purpose": "Tiếp khách dự án Demo"},
        "expense_items": [
            {
                "item_id": "ITEM-001",
                "category": "CLIENT_MEAL",
                "description": "Bữa trưa với khách hàng",
                "claimed_amount": "1200000",
                "currency": "VND",
                "evidence_names": ["bill.jpg"],
            }
        ],
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/settlements",
            data={"payload": json.dumps(payload)},
            files={
                "evidence_files": (
                    "bill.jpg",
                    b"image-content",
                    "image/jpeg",
                )
            },
        )
        assert response.status_code == 202
        case_id = response.json()["case_id"]

        assert client.post("/internal/process-next").json() == {"processed": True}
        case_response = client.get(f"/api/v1/cases/{case_id}")
        assert case_response.status_code == 200
        assert case_response.json()["automation_decision"] == "AUTO_PROCESS"
        detail = client.get(f"/accounting/cases/{case_id}")
        assert detail.status_code == 200
        assert "Bữa trưa với khách hàng" in detail.text
        assert "Kết quả kiểm tra và dẫn chứng" in detail.text
        assert "Điều kiện đã đáp ứng" in detail.text
        assert '<details class="passed-findings">' in detail.text
        assert "Chứng từ nguồn" in detail.text
        assert f'/api/v1/cases/{case_id}/documents/' in detail.text
        assert '<img ' in detail.text

        queue = client.get("/accounting/cases")
        assert queue.status_code == 200
        assert "Lý do chính" in queue.text
        assert "Hồ sơ đã vượt qua các kiểm tra bắt buộc" in queue.text

        action = client.post(
            f"/accounting/cases/{case_id}/actions",
            data={
                "action_type": "REQUEST_MORE_INFO",
                "reason": "Vui lòng bổ sung tên khách hàng tham dự.",
                "override_decision": "",
            },
            follow_redirects=False,
        )
        assert action.status_code == 303
        updated = client.get(f"/api/v1/cases/{case_id}").json()
        assert updated["workflow_status"] == "WAITING_EMPLOYEE"
        assert updated["automation_decision"] == "REQUEST_INFO"

        deleted = client.post(
            f"/accounting/cases/{case_id}/delete",
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert deleted.headers["location"] == (
            f"/accounting/cases?deleted={case_id}"
        )
        assert client.get(f"/api/v1/cases/{case_id}").status_code == 404
        confirmation = client.get(deleted.headers["location"])
        assert "Đã xóa hồ sơ" in confirmation.text


def test_submission_accepts_multiple_evidence_files_for_multiple_items(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _load_app(tmp_path, monkeypatch)
    payload = {
        "settlement_type": "EMPLOYEE_REIMBURSEMENT",
        "source_type": "DIGITAL_FORM",
        "business_context": {"purpose": "Công tác dự án Demo"},
        "expense_items": [
            {
                "item_id": "ITEM-001",
                "category": "TAXI",
                "description": "Taxi ra sân bay",
                "claimed_amount": "250000",
                "currency": "VND",
                "evidence_names": ["taxi.jpg"],
            },
            {
                "item_id": "ITEM-002",
                "category": "HOTEL",
                "description": "Khách sạn công tác",
                "claimed_amount": "1500000",
                "currency": "VND",
                "evidence_names": ["hotel.pdf"],
            },
        ],
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/settlements",
            data={"payload": json.dumps(payload)},
            files=[
                ("evidence_files", ("taxi.jpg", b"taxi", "image/jpeg")),
                (
                    "evidence_files",
                    ("hotel.pdf", b"hotel", "application/pdf"),
                ),
            ],
        )

        assert response.status_code == 202
        case = client.get(
            f"/api/v1/cases/{response.json()['case_id']}"
        ).json()
        assert {
            document["linked_item_id"] for document in case["documents"]
        } == {"ITEM-001", "ITEM-002"}

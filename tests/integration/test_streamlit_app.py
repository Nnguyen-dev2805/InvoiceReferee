import base64
from pathlib import Path

from streamlit.testing.v1 import AppTest

from invoice_referee.domain import ClaimDraft, EvidenceRole, UploadPayload
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository


def test_description_only_submission_runs_end_to_end(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_path = Path(__file__).parents[2] / "app" / "streamlit_app.py"
    monkeypatch.setenv("INVOICE_REFEREE_DATA_DIR", str(tmp_path))

    app = AppTest.from_file(str(app_path), default_timeout=10).run()

    assert len(app.exception) == 0
    assert len(app.text_input) == 2
    assert len(app.text_area) == 1
    assert [button.label for button in app.button] == ["Xóa nội dung", "Gửi kiểm tra"]

    app.text_input[1].set_value("Đề nghị hoàn ứng tiếp khách")
    app.text_area[0].set_value(
        "Em đi tiếp khách công ty ABC tối qua hết 2.500.000 đồng."
    )
    app.button[1].click().run()

    assert len(app.exception) == 0
    case_dirs = list((tmp_path / "submissions").glob("CASE-*"))
    assert len(case_dirs) == 1
    assert (case_dirs[0] / "submission.json").exists()
    assert (case_dirs[0] / "audit.jsonl").exists()
    assert (case_dirs[0] / "processing.json").exists()


def test_sidebar_opens_ocr_debug_for_submitted_image(
    tmp_path: Path,
    monkeypatch,
) -> None:
    submissions_root = tmp_path / "submissions"
    store = LocalCaseStore(
        submissions_root,
        id_factory=lambda: "CASE-OCR-UI",
    )
    store.save_submission(
        ClaimDraft(
            subject="Kiểm tra bill",
            body="Chi phí dự án Phoenix",
        ),
        [
            UploadPayload(
                original_name="bill.png",
                content=base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                    "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
                mime_type="image/png",
                role=EvidenceRole.PRIMARY_DOCUMENT,
            )
        ],
        [],
    )
    repository = LocalEvidenceRepository(submissions_root)
    evidence = repository.list_cases()[0].evidence[0]
    repository.save_ocr_result(
        evidence,
        {
            "provider": "mistral",
            "model": "mistral-ocr-latest",
            "response": {
                "pages": [
                    {
                        "index": 0,
                        "markdown": "# HÓA ĐƠN",
                        "dimensions": {"dpi": 200, "width": 100, "height": 100},
                        "confidence_scores": {
                            "word_confidence_scores": [
                                {"text": "#", "confidence": 0.99, "start_index": 0},
                                {
                                    "text": " HÓA",
                                    "confidence": 0.95,
                                    "start_index": 1,
                                },
                                {
                                    "text": " ĐƠN",
                                    "confidence": 0.98,
                                    "start_index": 5,
                                },
                            ],
                            "average_page_confidence_score": 0.97,
                            "minimum_page_confidence_score": 0.95,
                        },
                        "blocks": [
                            {
                                "type": "title",
                                "content": "# HÓA ĐƠN",
                                "top_left_x": 1,
                                "top_left_y": 1,
                                "bottom_right_x": 80,
                                "bottom_right_y": 20,
                            }
                        ],
                    }
                ]
            },
        },
    )
    monkeypatch.setenv("INVOICE_REFEREE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    app_path = Path(__file__).parents[2] / "app" / "streamlit_app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.radio[0].set_value("OCR kiểm thử").run()

    assert len(app.exception) == 0
    assert len(app.selectbox) == 2
    assert [button.label for button in app.button] == []
    assert [tab.label for tab in app.tabs] == [
        "Văn bản",
        "Confidence theo từ",
        "Blocks",
        "JSON",
    ]
    assert len(app.expander) == 1
    assert "Block 01 · title · exact" in app.expander[0].label


def test_accounting_page_splits_processed_cases(tmp_path: Path, monkeypatch) -> None:
    submissions_root = tmp_path / "submissions"
    store = LocalCaseStore(
        submissions_root,
        id_factory=lambda: "CASE-ACCOUNTING-UI",
    )
    store.save_submission(
        ClaimDraft(
            subject="Hoàn ứng tiếp khách",
            body="Tiếp khách công ty ABC",
        ),
        [],
        [],
    )
    repository = LocalEvidenceRepository(submissions_root)
    repository.save_processing_result(
        "CASE-ACCOUNTING-UI",
        {
            "schema_version": "1.0",
            "case_id": "CASE-ACCOUNTING-UI",
            "decision": "NEEDS_HUMAN",
            "processed_at": "2026-09-21T10:00:00+07:00",
            "summary": "Thiếu bill evidence.",
            "reasoning": "Hồ sơ chỉ có business context.",
            "findings": [
                {
                    "rule_id": "MISSING_BILL_EVIDENCE",
                    "status": "FAIL",
                    "message": "Hồ sơ không có bill hoặc chứng từ chính.",
                    "source_refs": [],
                }
            ],
            "ocr_evidence_ids": [],
            "kimi_analysis": None,
            "processing_errors": [],
        },
    )
    monkeypatch.setenv("INVOICE_REFEREE_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[2] / "app" / "streamlit_app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.radio[0].set_value("Kế toán").run()

    assert len(app.exception) == 0
    assert [tab.label for tab in app.tabs] == [
        "Đã pass (0)",
        "Cần xác minh (1)",
    ]
    assert len(app.expander) == 1
    assert "CASE-ACCOUNTING-UI" in app.expander[0].label
    assert any(button.label == "Xóa hồ sơ" for button in app.button)

    next(button for button in app.button if button.label == "Xóa hồ sơ").click().run()
    assert any(button.label == "Xác nhận xóa" for button in app.button)

    next(
        button for button in app.button if button.label == "Xác nhận xóa"
    ).click().run()
    app.run()
    assert not (submissions_root / "CASE-ACCOUNTING-UI").exists()
    assert len(app.expander) == 0


def test_sidebar_opens_ocr_structure_debug(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INVOICE_REFEREE_DATA_DIR", str(tmp_path))
    app_path = Path(__file__).parents[2] / "app" / "streamlit_app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.radio[0].set_value("OCR cấu trúc").run()

    assert len(app.exception) == 0
    assert len(app.get("file_uploader")) == 1
    assert len(app.slider) == 1
    assert app.slider[0].value == 0.85
    assert any("Chọn một ảnh" in info.value for info in app.info)

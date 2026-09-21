from app.views.accounting_review import _accounting_reasoning, _accounting_summary
from pathlib import Path

from invoice_referee.storage import StoredCase, StoredEvidence


def _case() -> StoredCase:
    return StoredCase(
        case_id="CASE-UI-001",
        submitted_at="2026-09-21T10:00:00+07:00",
        subject="Chi phí tiếp khách",
        body="Tiếp khách công ty ABC",
        evidence=(),
    )


def test_accounting_reasoning_hides_technical_identifiers() -> None:
    result = {
        "decision": "NEEDS_HUMAN",
        "low_confidence_candidates": [
            {
                "candidate_id": "EV-001:page-0-block-4",
                "evidence_id": "EV-001",
                "source_file": "Hoa_don.jpg",
            }
        ],
        "confidence_analysis": {
            "block_assessments": [
                {
                    "candidate_id": "EV-001:page-0-block-4",
                    "review_action": "ASK_HUMAN",
                    "canonical_fields": ["tax_amount"],
                    "human_question": (
                        "Xác nhận EV-001 tại page-0-block-4 vì confidence thấp."
                    ),
                }
            ]
        },
    }

    message = _accounting_reasoning(_case(), result)

    assert message == "Vui lòng kiểm tra Hoa_don.jpg và xác nhận tiền thuế."
    assert "EV-" not in message
    assert "block" not in message


def test_accounting_summary_explains_policy_signal_without_agent_jargon() -> None:
    result = {
        "decision": "PASS",
        "confidence_analysis": {
            "block_assessments": [
                {"review_action": "DEFER_TO_POLICY"},
            ]
        },
    }

    assert _accounting_summary(result) == (
        "Có 1 nội dung cần kiểm tra theo chính sách chi phí."
    )


def test_accounting_reasoning_prioritizes_inventory_conflict() -> None:
    result = {
        "decision": "NEEDS_HUMAN",
        "summary": "Hóa đơn và nguồn kiểm kê có dữ liệu cần kế toán xác nhận.",
        "findings": [
            {
                "rule_id": "INVENTORY_QUANTITY_MISMATCH",
                "status": "FAIL",
                "message": (
                    "Số lượng củ sắn không khớp: hóa đơn ghi 25992 kg, "
                    "phiếu nhập kho ghi 2 kg."
                ),
            }
        ],
        "inventory_analysis": {"applicability": "APPLICABLE"},
    }

    assert _accounting_summary(result) == result["summary"]
    assert "25992 kg" in _accounting_reasoning(_case(), result)
    assert "2 kg" in _accounting_reasoning(_case(), result)


def test_old_coverage_error_names_missing_supporting_file_and_fields() -> None:
    case = StoredCase(
        case_id="CASE-UI-002",
        submitted_at="2026-09-22T00:00:00+07:00",
        subject="Đối chiếu nhiên liệu",
        body="Đã nhận đủ dầu.",
        evidence=(
            StoredEvidence(
                case_id="CASE-UI-002",
                evidence_id="EV-PRIMARY",
                role="PRIMARY_DOCUMENT",
                original_name="bill_transportation.pdf",
                mime_type="application/pdf",
                size_bytes=1,
                relative_path="primary/bill.pdf",
                absolute_path=Path("bill.pdf"),
            ),
            StoredEvidence(
                case_id="CASE-UI-002",
                evidence_id="EV-SUPPORT",
                role="SUPPORTING_DOCUMENT",
                original_name="kiem_ke.pdf",
                mime_type="application/pdf",
                size_bytes=1,
                relative_path="supporting/report.pdf",
                absolute_path=Path("report.pdf"),
            ),
        ),
    )
    result = {
        "decision": "NEEDS_HUMAN",
        "findings": [
            {
                "rule_id": "INVENTORY_EXTRACTION_COVERAGE_INVALID",
                "status": "ERROR",
                "message": "Inventory Agent chưa trả đủ dữ liệu.",
            }
        ],
        "inventory_analysis": {
            "document_facts": [{"evidence_id": "EV-PRIMARY"}]
        },
    }

    message = _accounting_reasoning(case, result)

    assert "kiem_ke.pdf" in message
    assert "nhà cung cấp và MST" in message
    assert "số lượng" in message

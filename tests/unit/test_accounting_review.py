from app.views.accounting_review import _accounting_reasoning, _accounting_summary
from invoice_referee.storage import StoredCase


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

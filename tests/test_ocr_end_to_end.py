"""End-to-end OCR scenarios through the production review() path (recorded)."""

from __future__ import annotations

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.ingestion import normalization as norm  # noqa: E402
from invoice_referee.services.extractor import extract_invoice, ExtractionError  # noqa: E402
from verify.ocr_harness import load_ocr_case, RecordedOCREngine, run_case  # noqa: E402


@pytest.mark.parametrize(
    ("fixture_id", "expected_action"),
    [
        ("OCR01", "AUTO_PROCESS"),
        ("OCR06", "REQUEST_INFO"),
        ("OCR07", "AUTO_PROCESS"),
        ("OCR08", "REQUEST_INFO"),
        ("OCR09", "ESCALATE"),
        ("OCR10", "REQUEST_INFO"),
    ],
)
def test_ocr_document_reaches_policy_correct_action(fixture_id, expected_action):
    result = run_case(fixture_id)
    assert result.decision_action == expected_action


def test_ocr07_correction_is_preserved_and_auto_processes():
    # OCR misreads PO-0O1; the reviewer corrects to PO-001 -> AUTO_PROCESS.
    result = run_case("OCR07")
    assert result.decision_action == "AUTO_PROCESS"
    assert result.field_matches["po_id"] is True


def test_ocr_engine_failure_is_not_a_business_decision():
    class FailingEngine:
        def analyze(self, pages):
            raise RuntimeError("model unavailable")

    case = load_ocr_case("OCR01")
    with pytest.raises(ExtractionError):
        extract_invoice(
            transaction_id=case.base_evidence["transaction_id"],
            filename=case.filename,
            claimed_mime=case.mime_type,
            content=case.path.read_bytes(),
            po=norm.to_purchase_order(case.base_evidence["purchase_order"]),
            engine=FailingEngine(),
            actor="test-reviewer",
        )


def test_unified_audit_spans_upload_to_decision():
    from verify.ocr_harness import _extract, build_field_reviews
    from invoice_referee.ingestion.pipeline import apply_field_reviews, reviewed_invoice_to_evidence
    from invoice_referee.services.reviewer import review

    case = load_ocr_case("OCR01")
    result, audit, _ = _extract(case, live=False)
    reviewed = apply_field_reviews(result, build_field_reviews(case.field_review_spec, result), actor="eval")
    audit.record_extraction_reviewed(reviewed, actor="eval")
    evidence = reviewed_invoice_to_evidence(reviewed, case.base_evidence)
    for rec in evidence.get("payment_history", []):
        rec["invoice_id"] = evidence["invoice"]["invoice_id"]
    review_result = review(evidence, audit=audit)

    types = [e.event_type for e in review_result.audit_events]
    assert types[0] == "DOCUMENT_UPLOADED"
    assert "OCR_COMPLETED" in types
    assert "EXTRACTION_REVIEWED" in types
    assert "DECISION_MADE" in types
    ids = [e.event_id for e in review_result.audit_events]
    assert len(ids) == len(set(ids))  # one collision-free sequence

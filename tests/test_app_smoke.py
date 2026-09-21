"""Headless smoke tests for the Streamlit app via AppTest."""

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

from invoice_referee.domain import models as m

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def _field_candidate(name, value):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value),
        normalized_value=value,
        confidence=0.96,
        status=m.FieldStatus.EXTRACTED,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=[f"BLK-{name.upper()}"],
        extraction_method="EXACT_KEY_VALUE",
    )


def _seed_extraction_result(at):
    """Seed session state with an extraction result so the review UI renders."""
    fields = {
        "invoice_number": _field_candidate("invoice_number", "0000123"),
        "po_id": _field_candidate("po_id", "PO-001"),
        "total_amount": _field_candidate("total_amount", 9_000_000),
    }
    line = {
        "description": _field_candidate("description", "Item A"),
        "unit_price": _field_candidate("unit_price", 3_000_000),
        "line_total": _field_candidate("line_total", 9_000_000),
    }
    result = m.InvoiceExtractionResult(
        document_id="DOC-1",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields,
        line_items=[line],
        field_candidates={name: [c] for name, c in fields.items()},
    )
    from invoice_referee.audit.store import AuditStore
    at.session_state["extraction_result"] = result
    at.session_state["extraction_audit"] = AuditStore(transaction_id="TX-OCR")
    at.session_state["extraction_base_evidence"] = {"transaction_id": "TX-OCR"}
    at.run()


def _fresh():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def test_app_runs_without_exception():
    at = _fresh()
    assert not at.exception
    assert at.title[0].value.startswith("🧾")


def test_run_full_verify_button_reports_all_pass():
    at = _fresh()
    btn = next(b for b in at.button if b.label == "▶ Run Full Verify")
    btn.click().run()
    assert not at.exception
    successes = [s.value for s in at.success]
    assert any("9/9 cases passed" in s for s in successes)


def test_core_verify_button_reports_pass():
    at = _fresh()
    next(b for b in at.button if b.label == "Core Verify").click().run()
    assert not at.exception
    assert any("4/4 cases passed" in s.value for s in at.success)


def test_sample_review_shows_decision():
    at = _fresh()
    # Default sample is the first (TC01); click Review.
    next(b for b in at.button if b.label == "Review").click().run()
    assert not at.exception
    markdown_blob = " ".join(md.value for md in at.markdown)
    assert "AUTO_PROCESS" in markdown_blob


def test_document_mode_rejects_missing_upload_without_exception():
    at = _fresh()
    at.radio[0].set_value("Invoice Document").run()
    next(b for b in at.button if b.label == "Process invoice").click().run()
    assert not at.exception
    assert any("Upload" in w.value for w in at.warning)


def test_extraction_review_renders_line_item_controls():
    at = _fresh()
    _seed_extraction_result(at)
    assert not at.exception
    # Line-item review controls are rendered as selectbox/form elements.
    labels = [s.label for s in at.selectbox]
    assert any("line_items[0].unit_price" in lb for lb in labels)
    assert any("line_items[0].line_total" in lb for lb in labels)
    assert any("total_amount" in lb for lb in labels)


def test_extraction_review_does_not_proceed_until_reviewed():
    at = _fresh()
    _seed_extraction_result(at)
    assert not at.exception
    # While extraction is NEEDS_REVIEW the decision is NOT shown; the app stays
    # on the extraction review panel (the "Extracted fields" subheader).
    subheaders = [sh.value for sh in at.subheader]
    assert any("Extracted fields" in sh for sh in subheaders)
    # The business decision must not be rendered while extraction is not REVIEWED.
    markdown_blob = " ".join(md.value for md in at.markdown)
    assert "AUTO_PROCESS" not in markdown_blob

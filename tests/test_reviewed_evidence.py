"""Tests for human review commands and reviewed-evidence handoff."""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.pipeline import (
    FieldReview,
    apply_field_reviews,
    reviewed_invoice_to_evidence,
)


def _candidate(name, value, status=m.FieldStatus.EXTRACTED, method="OCR_RULE"):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=["B1"],
        extraction_method=method,
    )


def _full_reviewed_fields():
    """A complete set of critical header fields, all EXTRACTED."""
    values = {
        "invoice_number": "0000123",
        "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL",
        "vendor_tax_code": "0101234567",
        "vendor_id": "V-ABC",
        "po_id": "PO-001",
        "invoice_date": "2026-09-13",
        "currency": "VND",
        "total_amount": 30_000_000,
    }
    return {name: _candidate(name, value) for name, value in values.items()}


def _result(fields=None, line_items=None):
    return m.InvoiceExtractionResult(
        document_id="DOC-abc123",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields or {},
        line_items=line_items or [],
    )


def _base_evidence():
    return {
        "transaction_id": "TX-OCR-1",
        "transaction_type": "PO_GOODS_PURCHASE",
        "purchase_order": {"po_id": "PO-001"},
    }


# --- FieldReview construction ------------------------------------------------


def test_correct_requires_reason():
    with pytest.raises(ValueError):
        FieldReview.correct(30_000_000, reason="")


def test_mark_unknown_requires_reason():
    with pytest.raises(ValueError):
        FieldReview.mark_unknown("")


# --- apply_field_reviews -----------------------------------------------------


def test_confirm_marks_field_confirmed():
    result = _result(fields={"total_amount": _candidate("total_amount", 30_000_000)})
    reviewed = apply_field_reviews(result, {"total_amount": FieldReview.confirm()}, actor="ap@x")
    assert reviewed.fields["total_amount"].status is m.FieldStatus.CONFIRMED


def test_human_correction_preserves_original_candidate():
    result = _result(fields={"total_amount": _candidate("total_amount", 80_000_000)})
    reviewed = apply_field_reviews(
        result,
        {"total_amount": FieldReview.correct(30_000_000, reason="verified on invoice")},
        actor="ap@example.com",
    )
    field = reviewed.fields["total_amount"]
    assert field.status is m.FieldStatus.CORRECTED
    assert field.normalized_value == 30_000_000
    assert field.original_normalized_value == 80_000_000
    assert field.extraction_method == "HUMAN"


def test_mark_unknown_never_becomes_zero():
    result = _result(fields=_full_reviewed_fields())
    result.fields["total_amount"] = _candidate("total_amount", 80_000_000)
    reviews = {name: FieldReview.confirm() for name in result.fields}
    reviews["total_amount"] = FieldReview.mark_unknown("unreadable")
    reviewed = apply_field_reviews(result, reviews, actor="ap@example.com")
    evidence = reviewed_invoice_to_evidence(reviewed, _base_evidence())
    assert evidence["invoice"]["total_amount"] is None
    assert evidence["invoice"]["flagged"] is True


def test_line_item_review_by_key():
    line = {"unit_price": _candidate("unit_price", 3_000_000)}
    result = _result(line_items=[line])
    reviewed = apply_field_reviews(
        result,
        {"line_items[0].unit_price": FieldReview.correct(3_500_000, reason="typo")},
        actor="ap@x",
    )
    assert reviewed.line_items[0]["unit_price"].normalized_value == 3_500_000
    assert reviewed.line_items[0]["unit_price"].status is m.FieldStatus.CORRECTED


# --- REVIEWED gating ---------------------------------------------------------


def test_status_reviewed_only_when_all_critical_resolved():
    result = _result(fields=_full_reviewed_fields())
    # Confirm all but one critical field.
    reviews = {name: FieldReview.confirm() for name in result.fields if name != "po_id"}
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    assert reviewed.status is m.ExtractionStatus.NEEDS_REVIEW

    reviewed2 = apply_field_reviews(result, {"po_id": FieldReview.confirm()}, actor="ap@x")
    assert reviewed2.status is m.ExtractionStatus.REVIEWED


# --- reviewed_invoice_to_evidence --------------------------------------------


def test_reviewed_evidence_is_not_flagged_when_all_confirmed():
    result = _result(fields=_full_reviewed_fields())
    reviews = {name: FieldReview.confirm() for name in result.fields}
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    evidence = reviewed_invoice_to_evidence(reviewed, _base_evidence())
    assert evidence["invoice"]["flagged"] is False
    assert evidence["invoice"]["source_type"] == "OCR"
    assert evidence["invoice"]["total_amount"] == 30_000_000
    assert evidence["extraction_metadata"]["document_id"] == "DOC-abc123"


def test_reviewed_evidence_generates_invoice_id_when_absent():
    result = _result(fields=_full_reviewed_fields())
    reviews = {name: FieldReview.confirm() for name in result.fields}
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    evidence = reviewed_invoice_to_evidence(reviewed, _base_evidence())
    assert evidence["invoice"]["invoice_id"] == "INV-abc123"


def test_reviewed_evidence_preserves_provenance_metadata():
    result = _result(fields=_full_reviewed_fields())
    reviews = {name: FieldReview.confirm() for name in result.fields}
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    evidence = reviewed_invoice_to_evidence(reviewed, _base_evidence())
    prov = evidence["extraction_metadata"]["field_provenance"]["total_amount"]
    assert prov["evidence_block_ids"] == ["B1"]
    assert prov["status"] == "CONFIRMED"

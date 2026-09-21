"""Tests for extraction validation (confidence/conflict/LLM/arithmetic)."""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.extraction_validation import validate_extraction


def _candidate(
    name="total_amount",
    value=30_000_000,
    confidence=0.99,
    status=m.FieldStatus.EXTRACTED,
    method="OCR_RULE",
    warnings=None,
):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=confidence,
        status=status,
        page_number=1,
        bounding_box=None,
        extraction_method=method,
        warnings=list(warnings or []),
    )


def _result(fields=None, line_items=None):
    return m.InvoiceExtractionResult(
        document_id="DOC-1",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields or {},
        line_items=line_items or [],
    )


def test_high_confidence_critical_field_stays_extracted():
    result = _result(fields={"total_amount": _candidate(confidence=0.99)})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.EXTRACTED


def test_low_confidence_critical_field_requires_confirmation():
    result = _result(fields={"total_amount": _candidate(confidence=0.89)})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.NEEDS_CONFIRMATION


def test_missing_value_is_missing():
    result = _result(fields={"total_amount": _candidate(value=None, confidence=None)})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.MISSING


def test_llm_candidate_always_requires_confirmation():
    result = _result(
        fields={"po_id": _candidate(name="po_id", value="PO-001", confidence=0.99, method="LLM_ASSISTED")}
    )
    validated = validate_extraction(result)
    assert validated.fields["po_id"].status is m.FieldStatus.NEEDS_CONFIRMATION


def test_ocr_native_text_conflict_is_explicit():
    candidate = _candidate(
        value=30_000_000,
        confidence=0.99,
        warnings=["native PDF text says 80.000.000"],
    )
    result = _result(fields={"total_amount": candidate})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.CONFLICTING


def test_human_resolved_status_is_preserved():
    result = _result(
        fields={"total_amount": _candidate(status=m.FieldStatus.CORRECTED, confidence=None)}
    )
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.CORRECTED


def test_line_arithmetic_mismatch_is_warned():
    line = {
        "invoiced_quantity": _candidate("invoiced_quantity", 2, confidence=0.99),
        "unit_price": _candidate("unit_price", 3_000_000, confidence=0.99),
        "line_total": _candidate("line_total", 9_000_000, confidence=0.99),
    }
    result = _result(line_items=[line])
    validated = validate_extraction(result)
    assert any("arithmetic mismatch" in w for w in validated.line_items[0]["line_total"].warnings)


def test_sum_of_lines_vs_total_mismatch_is_warned():
    fields = {"total_amount": _candidate("total_amount", 10_000_000, confidence=0.99)}
    line = {
        "invoiced_quantity": _candidate("invoiced_quantity", 2, confidence=0.99),
        "unit_price": _candidate("unit_price", 3_000_000, confidence=0.99),
        "line_total": _candidate("line_total", 6_000_000, confidence=0.99),
    }
    result = _result(fields=fields, line_items=[line])
    validated = validate_extraction(result)
    assert any("sum of line totals" in w for w in validated.warnings)


# --- Task 6: separated-confidence validation ----------------------------------


def _candidate_v2(
    name="total_amount",
    value=30_000_000,
    provider_confidence=0.99,
    mapping_score=0.99,
    extraction_method="EXACT_KEY_VALUE",
    status=m.FieldStatus.EXTRACTED,
    warnings=None,
):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=None,
        status=status,
        page_number=1,
        bounding_box=None,
        extraction_method=extraction_method,
        warnings=list(warnings or []),
        provider_confidence=provider_confidence,
        mapping_score=mapping_score,
    )


def _result_v2(fields=None, line_items=None):
    return m.InvoiceExtractionResult(
        document_id="DOC-1",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields or {},
        line_items=line_items or [],
        audit_events=[],
        field_candidates={},
        line_item_candidate_sets=[],
        warnings=[],
    )


def test_fuzzy_spatial_always_requires_confirmation_even_with_high_ocr_confidence():
    candidate = _candidate_v2(
        extraction_method="FUZZY_SPATIAL",
        provider_confidence=0.999,
        mapping_score=0.92,
    )
    result = _result_v2(fields={"total_amount": candidate})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.NEEDS_CONFIRMATION


def test_provider_annotation_always_requires_confirmation():
    candidate = _candidate_v2(
        extraction_method="PROVIDER_ANNOTATION",
        provider_confidence=0.999,
    )
    result = _result_v2(fields={"po_id": candidate})
    validated = validate_extraction(result)
    assert validated.fields["po_id"].status is m.FieldStatus.NEEDS_CONFIRMATION


def test_uses_provider_confidence_not_mapping_score_for_ocr_threshold():
    # OCR confidence below threshold, mapping score high -> still needs confirmation.
    candidate = _candidate_v2(
        extraction_method="EXACT_SPATIAL",
        provider_confidence=0.50,
        mapping_score=1.0,
    )
    result = _result_v2(fields={"total_amount": candidate})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.NEEDS_CONFIRMATION


def test_repeated_validation_does_not_duplicate_warnings():
    """validate_extraction is called more than once on the same result."""
    result = _result(
        fields={"total_amount": _candidate(name="total_amount", value=100)},
        line_items=[
            {
                "invoiced_quantity": _candidate("invoiced_quantity", 1, method="TABLE_ITEM"),
                "unit_price": _candidate("unit_price", 2, method="TABLE_ITEM"),
                "line_total": _candidate("line_total", 3, method="TABLE_ITEM"),
            }
        ],
    )
    validate_extraction(result)
    first = list(result.warnings)
    validate_extraction(result)
    assert result.warnings == first


def test_conflicting_status_is_preserved():
    candidate = _candidate_v2(
        extraction_method="TABLE_SUMMARY",
        provider_confidence=0.99,
        status=m.FieldStatus.CONFLICTING,
    )
    result = _result_v2(fields={"total_amount": candidate})
    validated = validate_extraction(result)
    assert validated.fields["total_amount"].status is m.FieldStatus.CONFLICTING

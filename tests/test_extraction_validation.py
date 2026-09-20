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

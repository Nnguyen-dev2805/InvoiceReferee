"""Tests for pure OCR presentation helpers (no Streamlit import)."""

from __future__ import annotations

import io

import pytest

from invoice_referee.domain import models as m
from app.extraction_presentation import (
    field_rows,
    line_item_rows,
    build_field_reviews,
    critical_unresolved_count,
    alternatives_for,
)
from invoice_referee.ingestion.pipeline import FieldReview, apply_field_reviews


def _cand(name, value, status=m.FieldStatus.EXTRACTED, box=None, method="EXACT_KEY_VALUE",
          provider_confidence=0.95, mapping_score=1.0, section_role="HEADER",
          evidence=None):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=box,
        evidence_block_ids=evidence or ["B1"],
        extraction_method=method,
        provider_confidence=provider_confidence,
        mapping_score=mapping_score,
        section_role=section_role,
    )


def _result(fields=None, line_items=None, field_candidates=None):
    fields = fields or {
        "total_amount": _cand("total_amount", 30_000_000),
        "po_id": _cand("po_id", "PO-001"),
    }
    line_items = line_items if line_items is not None else [{"unit_price": _cand("unit_price", 3_000_000)}]
    field_candidates = field_candidates if field_candidates is not None else {
        name: [fields[name]] for name in fields
    }
    return m.InvoiceExtractionResult(
        "DOC-1", m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields, line_items=line_items,
        field_candidates=field_candidates,
    )


def test_field_rows_expose_value_status_and_provenance():
    rows = field_rows(_result())
    total = next(r for r in rows if r["field"] == "total_amount")
    assert total["value"] == 30_000_000
    assert total["status"] == "EXTRACTED"
    assert total["page"] == 1


def test_field_rows_show_method_scores_section_and_conflict():
    selected = _cand("total_amount", 9_000_000, status=m.FieldStatus.CONFLICTING,
                     method="TABLE_SUMMARY", provider_confidence=0.99, mapping_score=1.0,
                     section_role="SUMMARY", evidence=["R9C0", "R9C5"])
    alt = _cand("total_amount", 7_000_000, method="EXACT_KEY_VALUE", evidence=["KV-1"])
    result = _result(
        fields={"total_amount": selected},
        field_candidates={"total_amount": [selected, alt]},
        line_items=[],
    )
    row = field_rows(result)[0]
    assert row["field"] == "total_amount"
    assert row["method"] == "TABLE_SUMMARY"
    assert row["ocr_confidence"] == pytest.approx(0.99)
    assert row["mapping_score"] == pytest.approx(1.0)
    assert row["section"] == "SUMMARY"
    assert row["alternatives"] == 1
    assert row["status"] == "CONFLICTING"
    assert row["evidence"] == ["R9C0", "R9C5"]


def test_alternatives_for_exposes_method_value_and_provenance():
    selected = _cand("total_amount", 9_000_000, method="TABLE_SUMMARY", evidence=["R9C5"])
    alt = _cand("total_amount", 7_000_000, method="EXACT_KEY_VALUE", evidence=["KV-1"])
    result = _result(
        fields={"total_amount": selected},
        field_candidates={"total_amount": [selected, alt]},
        line_items=[],
    )
    alts = alternatives_for(result, "total_amount")
    assert len(alts) == 1
    assert alts[0]["method"] == "EXACT_KEY_VALUE"
    assert alts[0]["value"] == 7_000_000
    assert alts[0]["evidence"] == ["KV-1"]


def test_line_item_rows_flatten_values():
    rows = line_item_rows(_result())
    assert rows == [{"unit_price": 3_000_000}]


def test_build_field_reviews_maps_headers_and_line_items():
    result = _result()
    form = {
        "total_amount": {"action": "CONFIRM"},
        "po_id": {"action": "CORRECT", "value": "PO-002", "reason": "typo"},
        "line_items[0].unit_price": {"action": "MARK_UNKNOWN", "reason": "smudged"},
    }
    reviews = build_field_reviews(form, result)
    assert reviews["total_amount"].action == "CONFIRM"
    assert reviews["po_id"].action == "CORRECT"
    assert reviews["line_items[0].unit_price"].action == "MARK_UNKNOWN"

    # And they apply cleanly through the pipeline.
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    assert reviewed.fields["po_id"].normalized_value == "PO-002"
    assert reviewed.line_items[0]["unit_price"].normalized_value is None


def test_build_field_reviews_includes_every_line_item_cell():
    result = _result()
    result.line_items[0] = {
        "description": _cand("description", "Item A"),
        "invoiced_quantity": _cand("invoiced_quantity", 2),
        "unit_price": _cand("unit_price", 3_000_000),
        "line_total": _cand("line_total", 6_000_000),
    }
    form = {
        "line_items[0].description": {"action": "CONFIRM"},
        "line_items[0].invoiced_quantity": {"action": "CONFIRM"},
        "line_items[0].unit_price": {"action": "CONFIRM"},
        "line_items[0].line_total": {"action": "CONFIRM"},
    }
    reviews = build_field_reviews(form, result)
    assert "line_items[0].description" in reviews
    assert "line_items[0].invoiced_quantity" in reviews
    assert "line_items[0].unit_price" in reviews
    assert "line_items[0].line_total" in reviews


def test_review_not_ready_while_status_is_needs_review():
    from app.extraction_presentation import review_is_ready
    # result has unresolved criticals, so apply_field_reviews keeps NEEDS_REVIEW.
    assert review_is_ready(_result()) is False


def test_review_becomes_ready_only_after_all_criticals_resolved():
    from app.extraction_presentation import review_is_ready
    result = _result()
    for name in result.fields:
        result.fields[name].status = m.FieldStatus.CONFIRMED
    for line in result.line_items:
        for cell in line.values():
            cell.status = m.FieldStatus.CONFIRMED
    # line_item cells resolved plus fields: mark every critical resolved.
    result.status = m.ExtractionStatus.REVIEWED
    assert review_is_ready(result) is True


def test_critical_unresolved_count_counts_pending_criticals():
    result = _result()
    assert critical_unresolved_count(result) == 2  # total_amount + po_id pending
    result.fields["total_amount"].status = m.FieldStatus.CONFIRMED
    assert critical_unresolved_count(result) == 1


def test_draw_candidate_overlay_returns_png():
    pytest.importorskip("PIL")
    from PIL import Image

    from app.extraction_presentation import draw_candidate_overlay

    buffer = io.BytesIO()
    Image.new("RGB", (200, 100), (255, 255, 255)).save(buffer, format="PNG")
    page = m.DocumentPage("DOC-1", 1, buffer.getvalue(), 200, 100, 300, None)
    candidate = _cand("total_amount", 30_000_000, box=m.BoundingBox(0.1, 0.1, 0.5, 0.4))
    out = draw_candidate_overlay(page, candidate)
    assert out.startswith(b"\x89PNG")

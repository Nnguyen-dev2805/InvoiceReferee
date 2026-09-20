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
)
from invoice_referee.ingestion.pipeline import FieldReview, apply_field_reviews


def _cand(name, value, status=m.FieldStatus.EXTRACTED, box=None):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=box,
        evidence_block_ids=["B1"],
    )


def _result():
    fields = {
        "total_amount": _cand("total_amount", 30_000_000),
        "po_id": _cand("po_id", "PO-001"),
    }
    line = {"unit_price": _cand("unit_price", 3_000_000)}
    return m.InvoiceExtractionResult("DOC-1", m.ExtractionStatus.NEEDS_REVIEW, fields=fields, line_items=[line])


def test_field_rows_expose_value_status_and_provenance():
    rows = field_rows(_result())
    total = next(r for r in rows if r["field"] == "total_amount")
    assert total["value"] == 30_000_000
    assert total["status"] == "EXTRACTED"
    assert total["page"] == 1


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

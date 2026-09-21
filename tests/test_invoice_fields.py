"""Tests for deterministic invoice field + line-item extraction (no model)."""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields


def _block(block_id, text, *, row=None, col=None, block_type="TEXT", conf=0.96, page=1):
    return m.OCRBlock(
        block_id=block_id,
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type=block_type,
        row_index=row,
        column_index=col,
    )


def _doc(blocks):
    return m.OCRDocument(
        document_id="DOC-1",
        pages=[],
        blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine="recorded",
        engine_version="v1",
        processing_ms=0,
    )


def test_extracts_header_fields_with_provenance():
    doc = _doc(
        [
            _block("B1", "Ký hiệu: 2C23TTU"),
            _block("B2", "Số hóa đơn: 0000123"),
            _block("B3", "Mã số thuế: 0101234567"),
            _block("B4", "Tổng cộng: 30.000.000 VND"),
        ]
    )
    result = extract_invoice_fields(doc)
    assert result.fields["invoice_series"].normalized_value == "2C23TTU"
    assert result.fields["invoice_number"].normalized_value == "0000123"
    assert result.fields["vendor_tax_code"].normalized_value == "0101234567"
    assert result.fields["total_amount"].normalized_value == 30_000_000
    assert result.fields["total_amount"].evidence_block_ids == ["B4"]
    assert result.fields["total_amount"].page_number == 1
    assert result.status is m.ExtractionStatus.NEEDS_REVIEW


def test_unreadable_money_stays_none_and_flags_missing():
    doc = _doc([_block("B1", "Tổng cộng: khoảng 45 triệu")])
    result = extract_invoice_fields(doc)
    total = result.fields["total_amount"]
    assert total.normalized_value is None
    assert total.status is m.FieldStatus.MISSING
    assert total.evidence_block_ids == ["B1"]


def test_day_first_date_is_normalized_to_iso():
    doc = _doc([_block("B1", "Ngày hóa đơn: 13/09/2026")])
    result = extract_invoice_fields(doc)
    assert result.fields["invoice_date"].normalized_value == "2026-09-13"


def test_impossible_date_stays_none():
    doc = _doc([_block("B1", "Ngày hóa đơn: 45/13/2026")])
    result = extract_invoice_fields(doc)
    assert result.fields["invoice_date"].normalized_value is None


def test_reconstructs_line_items_from_table_cells():
    blocks = [
        _block("H0", "Mô tả", row=0, col=0, block_type="TABLE_CELL"),
        _block("H1", "Số lượng", row=0, col=1, block_type="TABLE_CELL"),
        _block("H2", "Đơn giá", row=0, col=2, block_type="TABLE_CELL"),
        _block("H3", "Thành tiền", row=0, col=3, block_type="TABLE_CELL"),
        _block("R1C0", "Dell Monitor", row=1, col=0, block_type="TABLE_CELL"),
        _block("R1C1", "2", row=1, col=1, block_type="TABLE_CELL"),
        _block("R1C2", "3.000.000", row=1, col=2, block_type="TABLE_CELL"),
        _block("R1C3", "6.000.000", row=1, col=3, block_type="TABLE_CELL"),
        _block("R2C0", "USB Cable", row=2, col=0, block_type="TABLE_CELL"),
        _block("R2C1", "5", row=2, col=1, block_type="TABLE_CELL"),
        _block("R2C2", "100.000", row=2, col=2, block_type="TABLE_CELL"),
        _block("R2C3", "500.000", row=2, col=3, block_type="TABLE_CELL"),
    ]
    result = extract_invoice_fields(_doc(blocks))
    assert len(result.line_items) == 2
    assert result.line_items[0]["description"].normalized_value == "Dell Monitor"
    assert result.line_items[0]["invoiced_quantity"].normalized_value == 2
    assert result.line_items[0]["unit_price"].normalized_value == 3_000_000
    assert result.line_items[0]["line_total"].normalized_value == 6_000_000
    assert result.line_items[1]["invoiced_quantity"].normalized_value == 5


def test_no_table_yields_no_line_items():
    result = extract_invoice_fields(_doc([_block("B1", "Số hóa đơn: 0000123")]))
    assert result.line_items == []


def test_no_headers_records_warning():
    result = extract_invoice_fields(_doc([_block("B1", "random text with no label")]))
    assert "no header fields could be extracted" in result.warnings

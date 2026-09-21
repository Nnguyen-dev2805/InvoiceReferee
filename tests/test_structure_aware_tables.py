"""Tests for structure-aware table extraction (Task 5).

Covers line-item extraction (DATA rows only; no ordinal/empty/summary rows as
items), summary money fields from classified rows, and the ``a.jpg`` regression
that motivated the structure-aware pipeline. No model inference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields
from invoice_referee.ingestion.document_structure import analyze_document_structure
from invoice_referee.ingestion.invoice_fields import extract_table_candidates


# --- fixture loader ------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures_structure"


def _load_a_jpg_document():
    with open(FIXTURES / "a_jpg_blocks.json", encoding="utf-8") as fh:
        raw = json.load(fh)
    page = raw["pages"][0]
    width = page["dimensions"]["width"]
    height = page["dimensions"]["height"]
    blocks = []
    for b in page["blocks"]:
        poly = b.get("poly")
        if poly:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            box = m.BoundingBox(
                x1=min(xs) / width, y1=min(ys) / height,
                x2=max(xs) / width, y2=max(ys) / height,
            )
        else:
            box = m.BoundingBox(0.0, 0.0, 1.0, 1.0)
        blocks.append(m.OCRBlock(
            block_id=b["block_id"],
            page_number=b.get("page_number", page["page_number"]),
            text=b["text"],
            confidence=float(b.get("confidence", 0.0)),
            bounding_box=box,
            block_type=b["block_type"],
            row_index=b.get("row_index"),
            column_index=b.get("column_index"),
            table_index=b.get("table_index"),
        ))
    return m.OCRDocument(
        document_id=raw["document_id"],
        pages=[],
        blocks=blocks,
        full_text=" ".join(b.text for b in blocks if b.text),
        engine=raw.get("engine", "mistral"),
        engine_version=raw.get("engine_version", "ocr-4-1"),
        processing_ms=0,
    )


@pytest.fixture
def a_jpg_ocr_document():
    return _load_a_jpg_document()


# --- helpers -------------------------------------------------------------------


def _tb(text, row, col, table=0, block_id=None, page=1, conf=0.99,
        box=None, btype="TABLE_CELL"):
    return m.OCRBlock(
        block_id=block_id or f"P{page}-T{table}-R{row}-C{col}",
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=box or m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type=btype,
        table_index=table,
        row_index=row,
        column_index=col,
    )


def _tdb(text, row, col, table=0, block_id=None, page=1, conf=0.99, box=None):
    return _tb(text, row, col, table=table, block_id=block_id, page=page,
               conf=conf, box=box, btype="TABLE_CELL")


def _doc(blocks):
    return m.OCRDocument(
        document_id="DOC-1", pages=[], blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine="test", engine_version="test", processing_ms=0,
    )


# --- a.jpg regression ----------------------------------------------------------


def test_a_jpg_yields_two_items_and_table_total(a_jpg_ocr_document):
    result = extract_invoice_fields(a_jpg_ocr_document)
    assert len(result.line_items) == 2
    assert result.line_items[0]["description"].normalized_value == "Khóa học thực hành kế toán tổng hợp"
    assert result.line_items[1]["description"].normalized_value == "Dịch vụ kế toán thuế quý 3/2023"
    assert result.fields["total_amount"].normalized_value == 9_000_000
    assert result.fields["total_amount"].extraction_method == "TABLE_SUMMARY"
    assert result.fields["total_amount"].evidence_block_ids == [
        "P1-M0-P1-T0R9C0",
        "P1-M0-P1-T0R9C5",
    ]


def test_a_jpg_line_items_have_correct_quantities(a_jpg_ocr_document):
    result = extract_invoice_fields(a_jpg_ocr_document)
    assert result.line_items[0]["invoiced_quantity"].normalized_value == 2
    assert result.line_items[0]["unit_price"].normalized_value == 3_500_000
    assert result.line_items[0]["line_total"].normalized_value == 7_000_000
    assert result.line_items[1]["invoiced_quantity"].normalized_value == 1


def test_a_jpg_seller_tax_extracted(a_jpg_ocr_document):
    result = extract_invoice_fields(a_jpg_ocr_document)
    assert result.fields["vendor_tax_code"].normalized_value == "0110329220"


# --- non-data-row exclusion ----------------------------------------------------


def test_ordinal_empty_summary_and_ambiguous_rows_never_become_items():
    blocks = [
        # header row
        _tdb("STT", 0, 0), _tdb("Mô tả", 0, 1), _tdb("Thành tiền", 0, 2),
        # ordinal row
        _tdb("1", 1, 0), _tdb("2", 1, 1), _tdb("3", 1, 2),
        # empty row
        _tdb("", 2, 0), _tdb("", 2, 1), _tdb("", 2, 2),
        # grand-total summary row
        _tdb("Tổng cộng", 3, 0), _tdb("", 3, 1), _tdb("9.000.000", 3, 2),
    ]
    structure = analyze_document_structure(_doc(blocks))
    table = extract_table_candidates(_doc(blocks), structure)
    descriptions = [line.get("description").normalized_value
                    for line in table.selected_line_items if "description" in line]
    assert "1" not in descriptions
    assert "2" not in descriptions
    assert None not in descriptions
    assert "Tổng cộng" not in descriptions


def test_ambiguous_row_without_description_is_not_a_line_item():
    blocks = [
        _tdb("Mô tả", 0, 0), _tdb("Thành tiền", 0, 1),
        _tdb("7.000.000", 1, 0), _tdb("", 1, 1),  # no description cell -> not a line item
    ]
    structure = analyze_document_structure(_doc(blocks))
    table = extract_table_candidates(_doc(blocks), structure)
    # Row 1 has money but no description -> not a DATA row -> no line item.
    assert table.selected_line_items == []


# --- summary extraction --------------------------------------------------------


def test_specific_summary_labels_map_to_distinct_fields():
    blocks = [
        _tdb("Mô tả", 0, 0), _tdb("Thành tiền", 0, 1),
        _tdb("Cộng tiền hàng", 1, 0), _tdb("8.000.000", 1, 1),
        _tdb("Tổng tiền thuế", 2, 0), _tdb("800.000", 2, 1),
        _tdb("Chiết khấu", 3, 0), _tdb("0", 3, 1),
        _tdb("Phí vận chuyển", 4, 0), _tdb("200.000", 4, 1),
        _tdb("Tổng cộng thanh toán", 5, 0), _tdb("9.000.000", 5, 1),
    ]
    structure = analyze_document_structure(_doc(blocks))
    table = extract_table_candidates(_doc(blocks), structure)
    fc = table.field_candidates
    assert fc["subtotal_amount"][0].normalized_value == 8_000_000
    assert fc["tax_amount"][0].normalized_value == 800_000
    assert fc["discount_amount"][0].normalized_value == 0
    assert fc["shipping_amount"][0].normalized_value == 200_000
    assert fc["total_amount"][0].normalized_value == 9_000_000

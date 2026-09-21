"""Task 6 integration tests: candidate-set preservation + cross-field warnings.

Confirms extract_invoice_fields preserves selected AND alternative candidates
(for audit/conflict review), and that cross-field semantic warnings are emitted.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields


def _block(block_id, text, *, row=None, col=None, table_index=0,
           block_type="TEXT", conf=0.96, page=1, box=None,
           btype=None):
    if btype is not None:
        block_type = btype
    return m.OCRBlock(
        block_id=block_id,
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=box or m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type=block_type,
        row_index=row,
        column_index=col,
        table_index=table_index if block_type == "TABLE_CELL" and row is not None else None,
    )


def _doc(blocks):
    return m.OCRDocument(
        document_id="DOC-1", pages=[], blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine="recorded", engine_version="v1", processing_ms=0,
    )


def _tb(text, block_id, **kw):
    return _block(block_id, text, btype="TEXT", **kw)


def _kv(text, block_id, **kw):
    return _block(block_id, text, btype="KEY_VALUE", **kw)


def test_total_conflict_preserves_selected_and_alternatives():
    """Two totals (label:value and split label/value) produce conflicting totals."""
    document_obj = _doc([
        _kv("Tổng cộng: 7.000.000", "KV-TOT",
            box=m.BoundingBox(0.05, 0.55, 0.5, 0.58)),
        _tb("Tổng cộng: 9.000.000", "SP-TOT",
            box=m.BoundingBox(0.05, 0.60, 0.5, 0.63)),
    ])
    result = extract_invoice_fields(document_obj)
    assert result.fields["total_amount"].status is m.FieldStatus.CONFLICTING
    assert len(result.field_candidates["total_amount"]) == 2
    assert {c.normalized_value for c in result.field_candidates["total_amount"]} == {
        7_000_000,
        9_000_000,
    }


def test_conflict_does_not_merge_agreeing_evidence():
    """When a table total and a label:value total agree, evidence is merged."""
    document_obj = _doc([
        _kv("Tổng cộng: 9.000.000", "KV-TOT",
            box=m.BoundingBox(0.05, 0.55, 0.5, 0.58)),
        _block("T9C0", "Tổng cộng thanh toán", block_type="TABLE_CELL",
               row=9, col=0, conf=0.99, box=m.BoundingBox(0.05, 0.70, 0.3, 0.73)),
        _block("T9C5", "9.000.000", block_type="TABLE_CELL",
               row=9, col=5, conf=0.99, box=m.BoundingBox(0.5, 0.70, 0.6, 0.73)),
    ])
    result = extract_invoice_fields(document_obj)
    assert result.fields["total_amount"].normalized_value == 9_000_000
    assert result.fields["total_amount"].status is m.FieldStatus.EXTRACTED


# --- cross-field semantic warnings ---------------------------------------------


def test_warning_when_seller_and_buyer_tax_codes_are_identical():
    document_obj = _doc([
        _kv("Đơn vị bán (Seller): A", "SELLER-NAME",
            box=m.BoundingBox(0.05, 0.10, 0.6, 0.13)),
        _kv("Mã số thuế: 0101234567", "SELLER-TAX",
            box=m.BoundingBox(0.05, 0.14, 0.4, 0.17)),
        _kv("Đơn vị mua (Buyer): B", "BUYER-NAME",
            box=m.BoundingBox(0.05, 0.20, 0.6, 0.23)),
        _kv("Mã số thuế: 0101234567", "BUYER-TAX",
            box=m.BoundingBox(0.05, 0.24, 0.4, 0.27)),
    ])
    result = extract_invoice_fields(document_obj)
    assert result.fields["vendor_tax_code"].normalized_value == "0101234567"
    assert any("seller and buyer tax code" in w.lower() for w in result.warnings)


def test_warning_when_invoice_total_exceeds_line_sum():
    """Header total is 10M but lines sum to 6M -> semantic mismatch warning."""
    blocks = [
        _block("H0", "Mô tả", block_type="TABLE_CELL", row=0, col=0),
        _block("H1", "Số lượng", block_type="TABLE_CELL", row=0, col=1),
        _block("H2", "Đơn giá", block_type="TABLE_CELL", row=0, col=2),
        _block("H3", "Thành tiền", block_type="TABLE_CELL", row=0, col=3),
        _block("R1C0", "Item A", block_type="TABLE_CELL", row=1, col=0, conf=0.99),
        _block("R1C1", "1", block_type="TABLE_CELL", row=1, col=1, conf=0.99),
        _block("R1C2", "3.000.000", block_type="TABLE_CELL", row=1, col=2, conf=0.99),
        _block("R1C3", "6.000.000", block_type="TABLE_CELL", row=1, col=3, conf=0.99),
        _kv("Tổng cộng: 10.000.000", "HDR-TOT",
            box=m.BoundingBox(0.05, 0.80, 0.5, 0.83)),
    ]
    result = extract_invoice_fields(_doc(blocks))
    assert result.fields["total_amount"].normalized_value == 10_000_000
    assert any("line totals" in w.lower() for w in result.warnings)

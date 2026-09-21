"""Tests for structure-aware header extraction (Task 4).

No model inference. Builds small provider-neutral OCRDocuments and asserts that
`extract_header_candidates` produces the right candidate(s) per field, scoped by
section role and spatial binding, with fuzzy matching that never confuses tax.
"""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.ingestion.invoice_fields import (
    extract_header_candidates,
    fuzzy_label_match,
    FUZZY_LABEL_THRESHOLD,
)
from invoice_referee.ingestion.candidate_resolver import resolve_field_candidates


# --- helpers -------------------------------------------------------------------


def table_cell(text, *, table=0, row=0, col=0, block_id=None, page=1,
                box=None, conf=0.99):
    return m.OCRBlock(
        block_id=block_id or f"P{page}-T{table}-R{row}-C{col}",
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=box or m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type="TABLE_CELL",
        table_index=table,
        row_index=row,
        column_index=col,
    )


def text_block(text, block_id, *, page=1, box=None, btype=None, conf=0.99):
    if btype is None:
        btype = "KEY_VALUE" if (":" in text or "：" in text) else "TEXT"
    return m.OCRBlock(
        block_id=block_id,
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=box or m.BoundingBox(0.05, 0.05, 0.5, 0.1),
        block_type=btype,
    )


def document(blocks):
    return m.OCRDocument(
        document_id="DOC-1",
        pages=[],
        blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine="test",
        engine_version="test",
        processing_ms=0,
    )


def seller_buyer_blocks(buyer_first=False):
    """Seller and buyer tax-code blocks; buyer may come first in reading order.

    Boxes are placed on distinct y-bands so section role is unambiguous.
    """
    seller_name = text_block("Đơn vị bán (Seller): CÔNG TY A", "SELLER-NAME",
                             box=m.BoundingBox(0.05, 0.10, 0.6, 0.13))
    seller_tax = text_block("Mã số thuế: 0110329220", "SELLER-TAX",
                            box=m.BoundingBox(0.05, 0.14, 0.4, 0.17))
    buyer_name = text_block("Đơn vị mua (Buyer): Nguyễn Thị Mai", "BUYER-NAME",
                            box=m.BoundingBox(0.05, 0.20, 0.5, 0.23))
    buyer_tax = text_block("Mã số thuế: 0110329573", "BUYER-TAX",
                           box=m.BoundingBox(0.05, 0.24, 0.4, 0.27))
    # buyer_first keeps buyer blocks earlier in *reading order* (lower y).
    if buyer_first:
        buyer_name.box = m.BoundingBox(0.05, 0.10, 0.5, 0.13)
        buyer_tax.box = m.BoundingBox(0.05, 0.14, 0.4, 0.17)
        seller_name.box = m.BoundingBox(0.05, 0.20, 0.6, 0.23)
        seller_tax.box = m.BoundingBox(0.05, 0.24, 0.4, 0.27)
        return [buyer_name, buyer_tax, seller_name, seller_tax]
    return [seller_name, seller_tax, buyer_name, buyer_tax]


def document_with_dates(header, signature):
    return document([
        text_block(header, "HDR-DATE", box=m.BoundingBox(0.05, 0.05, 0.5, 0.08)),
        text_block("Mô tả", row=0, col=0, table=0,
                   box=m.BoundingBox(0.05, 0.35, 0.5, 0.4)),
        text_block(signature, "SIGN-DATE", box=m.BoundingBox(0.6, 0.7, 0.9, 0.73)),
    ])


def split_total_document(label="Amount due", value="9.000.000"):
    return document([
        text_block(label, "LABEL", btype="TEXT",
                   box=m.BoundingBox(0.05, 0.30, 0.15, 0.33)),
        text_block(value, "VALUE", btype="TEXT",
                   box=m.BoundingBox(0.17, 0.30, 0.27, 0.33)),
    ])


# --- tests ---------------------------------------------------------------------


def test_seller_tax_code_uses_section_not_first_unscoped_match():
    from invoice_referee.ingestion.document_structure import analyze_document_structure
    document_obj = document(seller_buyer_blocks(buyer_first=True))
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)
    assert candidates["vendor_tax_code"][0].normalized_value == "0110329220"
    assert candidates["vendor_tax_code"][0].section_role == "SELLER"


def test_header_date_outranks_signature_date():
    from invoice_referee.ingestion.document_structure import analyze_document_structure
    document_obj = document([
        text_block("Ngày 10 tháng 07 năm 2023", "HDR-DATE",
                   box=m.BoundingBox(0.05, 0.05, 0.5, 0.08)),
        table_cell("Mô tả", row=0, col=0,
                   box=m.BoundingBox(0.05, 0.35, 0.5, 0.40)),
        table_cell("Thành tiền", row=0, col=1,
                   box=m.BoundingBox(0.5, 0.35, 0.95, 0.40)),
        table_cell("Dịch vụ X", row=1, col=0,
                   box=m.BoundingBox(0.05, 0.41, 0.5, 0.45)),
        table_cell("1.000.000", row=1, col=1,
                   box=m.BoundingBox(0.5, 0.41, 0.95, 0.45)),
        text_block("Người bán hàng (Seller)", "SIGN-LABEL",
                   box=m.BoundingBox(0.6, 0.70, 0.9, 0.73)),
        text_block("Ngày: 11/07/2023", "SIGN-DATE",
                   box=m.BoundingBox(0.65, 0.78, 0.85, 0.81)),
    ])
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)
    resolution = resolve_field_candidates("invoice_date", candidates["invoice_date"])
    assert resolution.selected.normalized_value == "2023-07-10"
    assert resolution.selected.section_role == "HEADER"


def test_exact_label_binds_value_in_right_neighbor():
    from invoice_referee.ingestion.document_structure import analyze_document_structure
    document_obj = split_total_document(label="Amount due", value="9.000.000")
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)
    total = candidates["total_amount"][0]
    assert total.normalized_value == 9_000_000
    assert total.extraction_method == "EXACT_SPATIAL"
    assert total.evidence_block_ids == ["LABEL", "VALUE"]


def test_fuzzy_label_handles_small_ocr_error_but_never_tax_as_total():
    fuzzy = fuzzy_label_match("tỗng cộmg thanh toan", field_name="total_amount")
    assert fuzzy is not None
    assert fuzzy >= FUZZY_LABEL_THRESHOLD
    assert fuzzy_label_match("tổng tiền thuế", field_name="total_amount") is None


def test_exact_key_value_block_extracts_and_marks_confirmed():
    """Backward-compat: simple label:value blocks still produce candidates."""
    document_obj = document([
        text_block("Ký hiệu: 2C23TTU", "B1"),
        text_block("Số hóa đơn: 0000123", "B2"),
        text_block("Mã số thuế: 0101234567", "B3"),
        text_block("Tổng cộng: 30.000.000 VND", "B4"),
    ])
    candidates = extract_header_candidates(document_obj, None)
    assert candidates["invoice_series"][0].normalized_value == "2C23TTU"
    assert candidates["invoice_number"][0].normalized_value == "0000123"
    assert candidates["vendor_tax_code"][0].normalized_value == "0101234567"
    assert candidates["total_amount"][0].normalized_value == 30_000_000

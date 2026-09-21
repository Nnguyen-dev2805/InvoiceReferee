"""Tests for deterministic document-structure analysis (Task 2).

These build small provider-neutral OCRDocuments and assert section roles,
table-row roles, and spatial neighbors. No model inference is involved.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.document_structure import (
    analyze_document_structure,
    classify_table_row,
    normalize_label,
)


# --- helpers -----------------------------------------------------------------


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


def _a_jpg_structure_document():
    """Reproduce the a.jpg table shape: header + ordinal + 2 data + 5 empty + total."""
    blocks = []
    # row 0: column labels
    for col, label in enumerate(
        ["STT (No.)", "Tên hàng hóa, dịch vụ (Description)", "ĐVT (Unit)",
         "SL (Quantity)", "Đơn giá (Unit Price)", "Thành tiền (Amount)"]
    ):
        blocks.append(table_cell(label, row=0, col=col))
    # row 1: ordinal / formula labels
    for col, label in enumerate(["1", "2", "3", "4", "5", "6 = 4 x 5"]):
        blocks.append(table_cell(label, row=1, col=col))
    # row 2 + 3: real data
    blocks += [
        table_cell("1", row=2, col=0),
        table_cell("Khóa học thực hành kế toán tổng hợp", row=2, col=1),
        table_cell("Khóa", row=2, col=2),
        table_cell("02", row=2, col=3),
        table_cell("3.500.000", row=2, col=4),
        table_cell("7.000.000", row=2, col=5),
        table_cell("2", row=3, col=0),
        table_cell("Dịch vụ kế toán thuế quý 3/2023", row=3, col=1),
        table_cell("Quý", row=3, col=2),
        table_cell("01", row=3, col=3),
        table_cell("2.000.000", row=3, col=4),
        table_cell("2.000.000", row=3, col=5),
    ]
    # rows 4..8: empty
    for row in range(4, 9):
        for col in range(6):
            blocks.append(table_cell("", row=row, col=col))
    # row 9: grand total label + value
    blocks.append(table_cell("Tổng cộng tiền thanh toán (Total payment):", row=9, col=0))
    for col in range(1, 5):
        blocks.append(table_cell("", row=9, col=col))
    blocks.append(table_cell("9.000.000", row=9, col=5))
    return document(blocks)


# --- table row roles ---------------------------------------------------------


def test_classifies_a_jpg_table_rows():
    structure = analyze_document_structure(_a_jpg_structure_document())
    assert structure.row_role_by_key[(1, 0, 0)] is m.TableRowRole.COLUMN_HEADER
    assert structure.row_role_by_key[(1, 0, 1)] is m.TableRowRole.ORDINAL_HEADER
    assert structure.row_role_by_key[(1, 0, 2)] is m.TableRowRole.DATA
    assert structure.row_role_by_key[(1, 0, 3)] is m.TableRowRole.DATA
    for row in range(4, 9):
        assert structure.row_role_by_key[(1, 0, row)] is m.TableRowRole.EMPTY
    assert structure.row_role_by_key[(1, 0, 9)] is m.TableRowRole.GRAND_TOTAL


def test_table_cells_without_table_index_still_get_a_section():
    """A provider emitting row_index but no table_index must not lose sections."""
    row = [
        table_cell("Mô tả", row=0, col=0, table=None),
        table_cell("Thành tiền", row=0, col=1, table=None),
        table_cell("Dịch vụ X", row=1, col=0, table=None),
        table_cell("1.000.000", row=1, col=1, table=None),
    ]
    structure = analyze_document_structure(document(row))
    assert structure.section_by_block_id, "table cells must still be sectioned"
    assert all(
        role is m.SectionRole.ITEM_TABLE
        for role in structure.section_by_block_id.values()
    )


def test_data_row_with_summary_word_in_description_is_not_a_summary_row():
    """An item described as "tax finalization" is a line item, not a tax total."""
    row = [
        table_cell("Dịch vụ tax finalization", row=1, col=0),
        table_cell("1", row=1, col=1),
        table_cell("2.000.000", row=1, col=2),
    ]
    assert classify_table_row(row) is m.TableRowRole.DATA


def test_data_row_with_shipping_word_in_description_is_not_a_summary_row():
    row = [
        table_cell("Shipping container rental", row=1, col=0),
        table_cell("1", row=1, col=1),
        table_cell("3.000.000", row=1, col=2),
    ]
    assert classify_table_row(row) is m.TableRowRole.DATA


def test_real_tax_total_row_is_still_tax():
    row = [
        table_cell("Tổng tiền thuế", row=1, col=0),
        table_cell("800.000", row=1, col=1),
    ]
    assert classify_table_row(row) is m.TableRowRole.TAX


def test_specific_summary_labels_beat_generic_total():
    blocks = [
        # a data-ish header first so the table is recognized
        table_cell("Mô tả", row=0, col=0),
        table_cell("Thành tiền", row=0, col=1),
        table_cell("Tổng tiền thuế", row=1, col=0),
        table_cell("800.000", row=1, col=1),
        table_cell("Cộng tiền hàng", row=2, col=0),
        table_cell("8.000.000", row=2, col=1),
        table_cell("Tổng cộng thanh toán", row=3, col=0),
        table_cell("9.000.000", row=3, col=1),
    ]
    structure = analyze_document_structure(document(blocks))
    assert structure.row_role_by_key[(1, 0, 1)] is m.TableRowRole.TAX
    assert structure.row_role_by_key[(1, 0, 2)] is m.TableRowRole.SUBTOTAL
    assert structure.row_role_by_key[(1, 0, 3)] is m.TableRowRole.GRAND_TOTAL


# --- sections ----------------------------------------------------------------


def _document_with_seller_buyer_and_signature():
    return document([
        text_block("Đơn vị bán (Seller): CÔNG TY A", "SELLER-NAME",
                   box=m.BoundingBox(0.05, 0.10, 0.6, 0.13)),
        text_block("MST (Tax Code): 0110329220", "SELLER-TAX",
                   box=m.BoundingBox(0.05, 0.14, 0.4, 0.17)),
        text_block("Người mua (Buyer): Nguyễn Thị Mai", "BUYER-NAME",
                   box=m.BoundingBox(0.05, 0.20, 0.5, 0.23)),
        text_block("MST (Tax Code): 0110329573", "BUYER-TAX",
                   box=m.BoundingBox(0.05, 0.24, 0.4, 0.27)),
        # item table so signature is classified as "after table"
        table_cell("Mô tả", row=0, col=0, box=m.BoundingBox(0.05, 0.35, 0.5, 0.4)),
        table_cell("Thành tiền", row=0, col=1, box=m.BoundingBox(0.5, 0.35, 0.95, 0.4)),
        table_cell("Dịch vụ X", row=1, col=0, box=m.BoundingBox(0.05, 0.41, 0.5, 0.45)),
        table_cell("1.000.000", row=1, col=1, box=m.BoundingBox(0.5, 0.41, 0.95, 0.45)),
        text_block("Người bán hàng (Seller)", "SIGN-LABEL",
                   box=m.BoundingBox(0.6, 0.7, 0.9, 0.73)),
        text_block("Ngày: 11/07/2023", "SIGN-DATE",
                   box=m.BoundingBox(0.65, 0.78, 0.85, 0.81)),
    ])


def test_duplicate_tax_labels_receive_different_sections():
    structure = analyze_document_structure(_document_with_seller_buyer_and_signature())
    assert structure.section_by_block_id["SELLER-TAX"] is m.SectionRole.SELLER
    assert structure.section_by_block_id["BUYER-TAX"] is m.SectionRole.BUYER
    assert structure.section_by_block_id["SIGN-DATE"] is m.SectionRole.SIGNATURE


def test_footer_notice_is_classified_footer():
    structure = analyze_document_structure(document([
        text_block("Số hóa đơn: 0001", "HDR", box=m.BoundingBox(0.05, 0.05, 0.5, 0.08)),
        text_block("Giải pháp Hóa đơn Điện tử cung cấp bởi Bkav http://ehoadon.vn",
                   "FOOT", box=m.BoundingBox(0.05, 0.93, 0.95, 0.97)),
    ]))
    assert structure.section_by_block_id["FOOT"] is m.SectionRole.FOOTER


# --- spatial index -----------------------------------------------------------


def _split_label_value_document():
    return document([
        text_block("Amount due", "LABEL", btype="TEXT",
                   box=m.BoundingBox(0.05, 0.30, 0.15, 0.33)),
        text_block("9.000.000", "RIGHT-NEAR", btype="TEXT",
                   box=m.BoundingBox(0.17, 0.30, 0.27, 0.33)),
        text_block("VND", "RIGHT-FAR", btype="TEXT",
                   box=m.BoundingBox(0.28, 0.30, 0.34, 0.33)),
        text_block("footnote", "BELOW", btype="TEXT",
                   box=m.BoundingBox(0.05, 0.35, 0.15, 0.38)),
        text_block("elsewhere", "OTHER-SECTION", btype="TEXT",
                   box=m.BoundingBox(0.05, 0.95, 0.3, 0.98)),
    ])


def test_spatial_index_orders_same_section_right_then_below():
    structure = analyze_document_structure(_split_label_value_document())
    assert structure.right_neighbor_by_block_id["LABEL"] == ["RIGHT-NEAR", "RIGHT-FAR"]
    assert structure.below_neighbor_by_block_id["LABEL"] == ["BELOW"]
    assert "OTHER-SECTION" not in structure.right_neighbor_by_block_id["LABEL"]


# --- normalize_label ---------------------------------------------------------


def test_normalize_label_strips_and_folds():
    assert normalize_label("  Tổng Cộng :  ") == "tổng cộng"
    # Surrounding punctuation/parentheses are trimmed at the edges.
    assert normalize_label("(Seller)") == "seller"
    assert normalize_label("") == ""

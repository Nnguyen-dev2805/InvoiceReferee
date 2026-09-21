"""Tests for structure-aware header extraction (Task 4).

No model inference. Builds small provider-neutral OCRDocuments and asserts that
`extract_header_candidates` produces the right candidate(s) per field, scoped by
section role and spatial binding, with fuzzy matching that never confuses tax.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.invoice_fields import (
    extract_header_candidates,
    fuzzy_label_match,
    FUZZY_LABEL_THRESHOLD,
)
from invoice_referee.ingestion.candidate_resolver import resolve_field_candidates


# --- helpers -------------------------------------------------------------------


@pytest.mark.parametrize("text,field,expected", [
    ("Date: 10/07/2023", "invoice_date", "2023-07-10"),
    ("Ma so thue: 0110329220", "vendor_tax_code", "0110329220"),
    ("Ngay 14 thang 07 nam 2023", "invoice_date", "2023-07-14"),
])
def test_explicit_english_and_unaccented_vietnamese_headers(text, field, expected):
    from invoice_referee.ingestion.invoice_fields import extract_invoice_fields
    result = extract_invoice_fields(document([text_block(text, "HEADER")]))
    candidate = result.fields.get(field)
    assert candidate is not None
    assert candidate.normalized_value == expected
    assert candidate.evidence_block_ids == ["HEADER"]
    assert candidate.extraction_method != "FUZZY_SPATIAL"


@pytest.mark.parametrize("label", ["Update", "Candidate", "Due date"])
def test_bare_english_date_alias_does_not_match_other_labels(label):
    from invoice_referee.ingestion.invoice_fields import extract_invoice_fields
    result = extract_invoice_fields(document([text_block(f"{label}: 10/07/2023", "OTHER")]))
    assert "invoice_date" not in result.fields


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


# --- tax-code semantic routing (seller vs buyer) -------------------------------


def test_seller_and_buyer_tax_codes_route_to_separate_fields():
    """Two different tax codes are two different facts, not one conflict."""
    from invoice_referee.ingestion.document_structure import analyze_document_structure

    document_obj = document(seller_buyer_blocks())
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)

    assert "vendor_tax_code" in candidates
    assert "buyer_tax_code" in candidates
    assert "unscoped_tax_code" not in candidates

    vendor = resolve_field_candidates("vendor_tax_code", candidates["vendor_tax_code"])
    buyer = resolve_field_candidates("buyer_tax_code", candidates["buyer_tax_code"])
    assert vendor.selected.normalized_value == "0110329220"
    assert buyer.selected.normalized_value == "0110329573"
    assert vendor.selected.status is not m.FieldStatus.CONFLICTING
    assert buyer.selected.status is not m.FieldStatus.CONFLICTING


def test_seller_and_buyer_tax_codes_keep_their_own_provenance():
    from invoice_referee.ingestion.document_structure import analyze_document_structure

    document_obj = document(seller_buyer_blocks())
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)

    vendor = resolve_field_candidates("vendor_tax_code", candidates["vendor_tax_code"])
    buyer = resolve_field_candidates("buyer_tax_code", candidates["buyer_tax_code"])
    assert vendor.selected.evidence_block_ids == ["SELLER-TAX"]
    assert vendor.selected.section_role == "SELLER"
    assert buyer.selected.evidence_block_ids == ["BUYER-TAX"]
    assert buyer.selected.section_role == "BUYER"


def test_two_different_seller_tax_codes_conflict():
    """Two different values that are both the seller's tax code are a real conflict."""
    from invoice_referee.ingestion.document_structure import analyze_document_structure

    document_obj = document([
        text_block("Đơn vị bán (Seller): CÔNG TY A", "SELLER-NAME",
                   box=m.BoundingBox(0.05, 0.10, 0.6, 0.13)),
        text_block("Mã số thuế: 0110329220", "SELLER-TAX-1",
                   box=m.BoundingBox(0.05, 0.14, 0.4, 0.17)),
        text_block("Mã số thuế: 0110329999", "SELLER-TAX-2",
                   box=m.BoundingBox(0.05, 0.18, 0.4, 0.21)),
    ])
    structure = analyze_document_structure(document_obj)
    candidates = extract_header_candidates(document_obj, structure)
    resolution = resolve_field_candidates("vendor_tax_code", candidates["vendor_tax_code"])
    assert resolution.conflicting is True
    assert resolution.selected.status is m.FieldStatus.CONFLICTING


def test_tax_code_in_an_unknown_section_is_not_claimed_as_vendor():
    """A tax code we cannot attribute to a party must not become the vendor's."""
    from invoice_referee.ingestion.document_structure import analyze_document_structure

    document_obj = document([
        # No seller/buyer anchor, and the block sits below the item table, so the
        # structure cannot attribute it to either party.
        table_cell("Mô tả", row=0, col=0,
                   box=m.BoundingBox(0.05, 0.30, 0.5, 0.35)),
        table_cell("Dịch vụ X", row=1, col=0,
                   box=m.BoundingBox(0.05, 0.36, 0.5, 0.40)),
        text_block("Mã số thuế: 0110329220", "ORPHAN-TAX",
                   box=m.BoundingBox(0.05, 0.60, 0.4, 0.63)),
    ])
    structure = analyze_document_structure(document_obj)
    assert structure.section_by_block_id["ORPHAN-TAX"] is m.SectionRole.SIGNATURE

    candidates = extract_header_candidates(document_obj, structure)
    assert "vendor_tax_code" not in candidates
    assert "unscoped_tax_code" in candidates

    unscoped = resolve_field_candidates("unscoped_tax_code", candidates["unscoped_tax_code"])
    assert unscoped.selected.normalized_value == "0110329220"
    assert unscoped.selected.status is m.FieldStatus.NEEDS_CONFIRMATION
    assert unscoped.selected.evidence_block_ids == ["ORPHAN-TAX"]


def test_header_tax_code_is_treated_as_the_seller():
    """Invoices that print the tax code above any party anchor mean the seller."""
    from invoice_referee.ingestion.document_structure import analyze_document_structure

    document_obj = document([
        text_block("Số hóa đơn: 0000123", "NUM",
                   box=m.BoundingBox(0.05, 0.05, 0.4, 0.08)),
        text_block("Mã số thuế: 0110329220", "HDR-TAX",
                   box=m.BoundingBox(0.05, 0.09, 0.4, 0.12)),
    ])
    structure = analyze_document_structure(document_obj)
    assert structure.section_by_block_id["HDR-TAX"] is m.SectionRole.HEADER

    candidates = extract_header_candidates(document_obj, structure)
    assert "vendor_tax_code" in candidates
    assert "buyer_tax_code" not in candidates
    vendor = resolve_field_candidates("vendor_tax_code", candidates["vendor_tax_code"])
    assert vendor.selected.normalized_value == "0110329220"
    assert vendor.selected.status is not m.FieldStatus.CONFLICTING


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


@pytest.mark.parametrize("label,method", [
    ("Amount due", "EXACT_SPATIAL"),
    ("Amounl due", "FUZZY_SPATIAL"),
])
@pytest.mark.parametrize("right_value,expected,source", [
    (None, 9000000, "BELOW"),
    ("8.000.000", 8000000, "RIGHT"),
    ("unreadable", 9000000, "BELOW"),
])
def test_spatial_binding_falls_below_only_when_right_does_not_resolve(
    label, method, right_value, expected, source,
):
    from invoice_referee.ingestion.document_structure import analyze_document_structure
    blocks = [
        text_block(label, "LABEL", box=m.BoundingBox(0.05, 0.10, 0.25, 0.13)),
        text_block("9.000.000", "BELOW", box=m.BoundingBox(0.05, 0.15, 0.25, 0.18)),
    ]
    if right_value is not None:
        blocks.append(text_block(right_value, "RIGHT", box=m.BoundingBox(0.27, 0.10, 0.47, 0.13)))
    doc = document(blocks)
    candidates = extract_header_candidates(doc, analyze_document_structure(doc))
    total = next(c for c in candidates.get("total_amount", []) if c.extraction_method == method)
    assert total.normalized_value == expected
    assert total.evidence_block_ids == ["LABEL", source]
    if method == "FUZZY_SPATIAL":
        assert total.status == m.FieldStatus.NEEDS_CONFIRMATION


@pytest.mark.parametrize("value,expected", [("9.000.000", 9000000), ("9.OOO.OOO", None)])
def test_inline_fuzzy_matching_only_repairs_label_not_value(value, expected):
    from invoice_referee.ingestion.document_structure import analyze_document_structure
    doc = document([text_block(f"Amounl due: {value}", "INLINE")])
    candidates = extract_header_candidates(doc, analyze_document_structure(doc))
    total = next(c for c in candidates.get("total_amount", []) if c.extraction_method == "FUZZY_SPATIAL")
    assert total.normalized_value == expected
    assert total.evidence_block_ids == ["INLINE"]
    assert total.status == m.FieldStatus.NEEDS_CONFIRMATION


def test_exact_key_value_block_extracts_and_marks_confirmed():
    """Backward-compat: simple label:value blocks still produce candidates.

    A tax code with no structure at all cannot be attributed to a party, so it
    lands in ``unscoped_tax_code`` for human review rather than being guessed as
    the vendor's (see ``test_tax_code_in_an_unknown_section_is_not_claimed_as_vendor``).
    """
    document_obj = document([
        text_block("Ký hiệu: 2C23TTU", "B1"),
        text_block("Số hóa đơn: 0000123", "B2"),
        text_block("Mã số thuế: 0101234567", "B3"),
        text_block("Tổng cộng: 30.000.000 VND", "B4"),
    ])
    candidates = extract_header_candidates(document_obj, None)
    assert candidates["invoice_series"][0].normalized_value == "2C23TTU"
    assert candidates["invoice_number"][0].normalized_value == "0000123"
    assert "vendor_tax_code" not in candidates
    assert candidates["unscoped_tax_code"][0].normalized_value == "0101234567"
    assert candidates["total_amount"][0].normalized_value == 30_000_000

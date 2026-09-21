"""End-to-end regression for the recorded ``a.jpg`` block set (Task 10).

The structure-aware pipeline was motivated by this one real OCR capture: a
Vietnamese invoice whose item table has an ordinal column, an empty filler row
and a grand-total row inside the table. This test pins the whole path —
structure analysis, candidate collection, resolution and validation — against
that recording, so a regression anywhere in it is caught by one assertion set.

No model inference: the fixture is a recorded provider-neutral block set.
"""

from __future__ import annotations

from invoice_referee.ingestion.extraction_validation import validate_extraction
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields


def test_a_jpg_structure_regression(a_jpg_ocr_document):
    result = validate_extraction(extract_invoice_fields(a_jpg_ocr_document))

    # Exactly the two real item rows become line items; the ordinal row, the
    # empty filler row and the grand-total row must not.
    assert len(result.line_items) == 2

    assert result.fields["total_amount"].normalized_value == 9_000_000
    assert result.fields["vendor_tax_code"].normalized_value == "0110329220"
    # The source image reads "Ngày 11 tháng 07 năm 2023"; day-first gives July 11.
    assert result.fields["invoice_date"].normalized_value == "2023-07-11"

    # The grand total cites both its label cell and its value cell.
    assert result.fields["total_amount"].evidence_block_ids == [
        "P1-M0-P1-T0R9C0",
        "P1-M0-P1-T0R9C5",
    ]

    # A line item's description is never the ordinal number or an empty cell.
    assert not any(
        line["description"].normalized_value in (None, "2")
        for line in result.line_items
    )


def test_a_jpg_line_item_descriptions_are_real_goods(a_jpg_ocr_document):
    result = validate_extraction(extract_invoice_fields(a_jpg_ocr_document))
    descriptions = [line["description"].normalized_value for line in result.line_items]
    assert descriptions == [
        "Khóa học thực hành kế toán tổng hợp",
        "Dịch vụ kế toán thuế quý 3/2023",
    ]


def test_a_jpg_quantity_comes_from_the_quantity_column(a_jpg_ocr_document):
    result = validate_extraction(extract_invoice_fields(a_jpg_ocr_document))
    quantities = [line["invoiced_quantity"].normalized_value for line in result.line_items]
    assert quantities == [2, 1]

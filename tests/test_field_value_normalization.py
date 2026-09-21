"""Field-value normalization: raw extracted text -> a typed value, by field name.

Deciding *which field* a piece of text belongs to is the model's job; deciding
*what that text means* is code's job. This module is the second half, and it is
what turns a grounded `raw_text` into a typed value.

The value is always derived from the field name, never from the model: a model
that returns ``9000000`` for a block reading ``9.000.000`` is rejected by
grounding, and if it returned a normalized number anyway, the number would be
re-derived here rather than trusted.
"""

from __future__ import annotations

import pytest

from invoice_referee.ingestion.field_normalization import (
    DATE_FIELDS,
    MONEY_FIELDS,
    normalize_field_value,
    normalize_line_value,
)


def test_field_sets_cover_header_and_line_item_money():
    assert {"total_amount", "subtotal_amount", "tax_amount"} <= MONEY_FIELDS
    assert "invoice_date" in DATE_FIELDS
    assert "receipt_datetime" in DATE_FIELDS


# --- header fields ------------------------------------------------------------


@pytest.mark.parametrize("field,raw,expected", [
    ("total_amount", "9.000.000", 9_000_000),
    ("total_amount", "4.035.570đ", 4_035_570),
    ("subtotal_amount", "3.698.750đ", 3_698_750),
    ("tax_amount", "336.820", 336_820),
    ("invoice_date", "Ngày 11 tháng 07 năm 2023", "2023-07-11"),
    ("receipt_datetime", "18/09/2026 (10:03 - 21:52)", "2026-09-18"),
    ("invoice_number", "0000123", "0000123"),
    ("vendor_tax_code", "0110329220", "0110329220"),
    ("po_id", "PO-001", "PO-001"),
    ("merchant_name", "SEN NAM BỘ", "SEN NAM BỘ"),
])
def test_header_field_normalization(field, raw, expected):
    assert normalize_field_value(field, raw) == expected


def test_unreadable_value_stays_none_never_zero():
    assert normalize_field_value("total_amount", "unreadable") is None
    assert normalize_field_value("total_amount", "") is None
    assert normalize_field_value("invoice_date", "not a date") is None


# --- line items ---------------------------------------------------------------


@pytest.mark.parametrize("field,raw,expected", [
    ("unit_price", "3.500.000", 3_500_000),
    ("line_total", "7.000.000", 7_000_000),
    ("invoiced_quantity", "02", 2),
    ("invoiced_quantity", "15", 15),
    ("description", "Khóa học kế toán", "Khóa học kế toán"),
])
def test_line_item_normalization(field, raw, expected):
    assert normalize_line_value(field, raw) == expected


@pytest.mark.parametrize("raw", ["1,65", "1,55", "0,272", "0,272kg"])
def test_fractional_quantity_is_none_not_a_100x_larger_number(raw):
    """`1,65` means 1.65. Reading it as 165 is a different number, not a rounding."""
    assert normalize_line_value("invoiced_quantity", raw) is None


def test_quantity_with_no_digits_is_none():
    assert normalize_line_value("invoiced_quantity", "kg") is None

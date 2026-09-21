"""Normalization of receipt values, driven by the real recorded receipt.

Live semantic extraction of the recorded ``b.jpg`` receipt surfaced two real
defects in value normalization. Both corrupt a printed number rather than
declining to read it, which is the one thing the extraction invariants forbid:

1. a decimal quantity was read as a large integer — ``1,65`` (1.65 kg of fish)
   became ``165``, and ``0,272kg`` became ``272``;
2. ``receipt_datetime`` had no normalizer at all, so a printed date stayed a raw
   string instead of becoming an ISO date.

A value that cannot be read must stay ``None``. It must never become a different
number that happens to be made of the same digits.
"""

from __future__ import annotations

import pytest

from invoice_referee.ingestion.field_normalization import (
    normalize_field_value,
    normalize_line_value,
)


# --- decimal quantities -------------------------------------------------------
#
# A quantity is an integer by contract, so a fractional quantity cannot be
# represented. Reading `1,65` as `165` is not a rounding — it is a different
# number, 100x the printed one, and it would silently pass an arithmetic check
# that the human never saw. The honest outcome is "cannot represent this", i.e.
# None plus human review. The raw text stays on the candidate, so the human still
# sees `1,65`.


@pytest.mark.parametrize("raw", ["1,65", "1,55", "0,272", "0,272kg"])
def test_fractional_quantity_stays_none_rather_than_becoming_another_number(raw):
    assert normalize_line_value("invoiced_quantity", raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("02", 2),
    ("1", 1),
    ("96", 96),
    ("15", 15),
])
def test_integer_quantity_still_normalizes(raw, expected):
    assert normalize_line_value("invoiced_quantity", raw) == expected


def test_unreadable_quantity_stays_none_never_zero():
    assert normalize_line_value("invoiced_quantity", "kg") is None
    assert normalize_line_value("invoiced_quantity", "") is None


# --- receipt datetime ---------------------------------------------------------


def test_receipt_datetime_normalizes_to_an_iso_date():
    """The receipt prints a date plus a time range; the date is what matters."""
    assert (
        normalize_field_value("receipt_datetime", "18/09/2026 (10:03 - 21:52)")
        == "2026-09-18"
    )


def test_receipt_datetime_accepts_a_plain_date():
    assert normalize_field_value("receipt_datetime", "18/09/2026") == "2026-09-18"


def test_receipt_datetime_unparseable_stays_none():
    assert normalize_field_value("receipt_datetime", "not a date") is None


# --- money on a receipt -------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("4.035.570đ", 4_035_570),
    ("336.820đ", 336_820),
    ("3.698.750đ", 3_698_750),
])
def test_receipt_money_with_a_trailing_currency_marker(raw, expected):
    """OCR glues `đ` onto the amount; the marker is not part of the value."""
    assert normalize_field_value("total_amount", raw) == expected

"""Numeric provenance: a money value is supported only by a real money token.

A real invoice line reads `Thuế GTGT (8%): 400.000`. The value 400000 must be
supported by that quote, but the percentage `8%` must NOT be mistaken for money
(and a document number must not be mistaken for a money value). The old
"first number in the quote" rule picked `8` and demoted a correctly-read tax to
UNREADABLE. Provenance is now token-based: every digit-run the value claims must
appear as a real token in the quote, ignoring percentage tokens.
"""

from __future__ import annotations

from invoice_referee.evidence.extraction import _value_supported


def test_tax_quote_with_percentage_and_amount_accepts_the_money() -> None:
    assert _value_supported(400000, "Thuế GTGT (8%): 400.000")
    assert _value_supported("400000", "Thuế GTGT (8%): 400.000")
    assert _value_supported(240000, "Thuế GTGT (8%): 240.000")


def test_a_percentage_token_is_not_money() -> None:
    # The only number in the quote is a percentage; it cannot support value 8.
    assert not _value_supported(8, "Thuế GTGT (8%): 400.000")


def test_a_wrong_money_value_is_rejected() -> None:
    assert not _value_supported(999000, "Tổng cộng: 450.000")
    assert not _value_supported(999000, "Thuế GTGT (8%): 400.000")


def test_a_wrong_identifier_is_rejected() -> None:
    # A serial-prefixed document number must match by its own parts, not any
    # number that happens to be nearby.
    assert not _value_supported("IR26E00000999", "Ký hiệu: IR26E\n\nSố: 00000101")


def test_serial_prefixed_number_is_supported_by_its_parts() -> None:
    # LIVE TC01: the model reads "IR26E00000101" while the quote holds the serial
    # "IR26E" and the number "00000101" on two lines.
    assert _value_supported("IR26E00000101", "Ký hiệu: IR26E\n\nSố: 00000101")


def test_plain_money_and_date_are_still_supported() -> None:
    assert _value_supported("3240000", "TỔNG CỘNG THANH TOÁN: 3.240.000 VND")
    assert _value_supported("2026-10-10", "Ngày 10 tháng 10 năm 2026")
    assert not _value_supported("2026-10-11", "Ngày 10 tháng 10 năm 2026")

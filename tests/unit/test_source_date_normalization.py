"""Dates must keep their source meaning, not merely share its digits."""

from datetime import date

import pytest

from invoice_referee.evidence.extraction import _value_supported
from invoice_referee.reconciliation.linking import _link_date


@pytest.mark.parametrize("text", [
    "10 tháng 10 năm 2026", "ngày 10 tháng 10 năm 2026",
    "Ngày 10\ntháng 10 năm 2026", "10/10/2026", "2026-10-10",
])
def test_source_date_formats_identify_the_same_day(text: str) -> None:
    assert _link_date(text) == date(2026, 10, 10)


@pytest.mark.parametrize("text", [
    "31 tháng 2 năm 2026", "10 tháng 10", "2026-10-10 junk", "31/02/2026",
])
def test_incomplete_or_invalid_date_is_not_guessed(text: str) -> None:
    assert _link_date(text) is None


@pytest.mark.parametrize(("value", "quote"), [
    ("2026-11-10", "ngày 11 tháng 10 năm 2026"),
    ("2026-02-31", "ngày 31 tháng 2 năm 2026"),
    ("2026-10-11", "Lập ngày 11/10/2026; thanh toán ngày 12/10/2026"),
])
def test_wrong_or_ambiguous_normalized_date_is_not_supported(value: str, quote: str) -> None:
    assert not _value_supported(value, quote)


def test_explicit_timestamp_is_preserved_but_invented_time_is_rejected() -> None:
    stamp = "2026-10-05T09:00:00+07:00"
    assert _value_supported(stamp, f"Giao dịch: {stamp}")
    assert not _value_supported("2026-10-05T10:00:00+07:00", f"Giao dịch: {stamp}")
    assert not _value_supported(stamp, "Ngày giao dịch: 05/10/2026")

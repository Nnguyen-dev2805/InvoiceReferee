"""Source calendar days, preserving day/month order and never guessing a year."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime


_DATE = re.compile(
    r"(?<![\w])(?:"
    r"(?P<iso_year>\d{4})-(?P<iso_month>\d{2})-(?P<iso_day>\d{2})"
    r"|(?P<day>\d{1,2})(?P<sep>[/.-])(?P<month>\d{1,2})(?P=sep)(?P<year>\d{4})"
    r"|(?:ngày\s+)?(?P<vn_day>\d{1,2})\s+tháng\s+(?P<vn_month>\d{1,2})\s+năm\s+(?P<vn_year>\d{4})"
    r")(?![\w])",
    re.IGNORECASE,
)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}.*", re.DOTALL)


def _calendar_day(match: re.Match[str]) -> date | None:
    for prefix in ("iso_", "vn_", ""):
        if match.group(prefix + "year") is not None:
            try:
                return date(*(int(match.group(prefix + part)) for part in ("year", "month", "day")))
            except ValueError:
                return None
    return None


def parse_source_date(value: str | None) -> date | None:
    """Parse one full source value; trailing junk and incomplete dates stay unknown."""
    text = unicodedata.normalize("NFC", value or "").strip()
    if _TIMESTAMP.fullmatch(text):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    match = _DATE.fullmatch(text)
    return _calendar_day(match) if match else None


def date_is_supported(value: str, quote: str, *, field_name: str | None = None) -> bool | None:
    """Match calendar days in source order; only explicit trip ranges select endpoints."""
    text = unicodedata.normalize("NFC", value).strip()
    day = parse_source_date(text)
    if day is None:
        # A malformed date must not fall through to identifier/number matching.
        return False if _DATE.fullmatch(text) or _TIMESTAMP.fullmatch(text) else None
    source = unicodedata.normalize("NFC", quote)
    if _TIMESTAMP.fullmatch(text):
        # A date alone does not support an invented clock time or timezone.
        return text in source
    matches = list(_DATE.finditer(source))
    days = [_calendar_day(match) for match in matches]
    if not days or any(item is None for item in days):
        return False
    if len(set(days)) == 1:
        return day == days[0]
    if (
        len(days) == 2
        and field_name in {"trip_start", "trip_end"}
        and re.search(r"\b(?:từ|from)\b", source[:matches[0].start()], re.IGNORECASE)
        and re.fullmatch(r"\s*(?:đến|to|[-–—])\s*", source[matches[0].end():matches[1].start()], re.IGNORECASE)
        and days[0] <= days[1]
    ):
        return day == days[0 if field_name == "trip_start" else 1]
    return False

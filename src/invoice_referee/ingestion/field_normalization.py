"""Field-value normalization: raw extracted text -> a typed value, by field name.

Deciding *which field* a piece of text belongs to is the model's job; deciding
*what that text means* is code's job. This module does only the second, so the
extractor can change without changing the meaning of a value.

Nothing here guesses. A value that cannot be read as the field's type stays
``None`` and goes to human review; it is never coerced into ``""`` or ``0``.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from invoice_referee.ingestion import normalization as norm

# Header fields normalised as money.
MONEY_FIELDS = frozenset({
    "total_amount",
    "subtotal_amount",
    "tax_amount",
    "discount_amount",
    "shipping_amount",
})

# Header fields normalised as dates. ``receipt_datetime`` is a receipt's
# date-and-time string ("18/09/2026 (10:03 - 21:52)"); the date part is what the
# pipeline needs, and ``normalize_date`` already reads a leading date token.
DATE_FIELDS = frozenset({"invoice_date", "signature_date", "receipt_datetime"})

# Line-item fields normalised as money.
LINE_MONEY_FIELDS = frozenset({"unit_price", "line_total"})


def normalize_field_value(field_name: str, raw_text: Any):
    """Normalize a header/candidate value according to its canonical field type."""
    if field_name in MONEY_FIELDS:
        return norm.normalize_money(raw_text)
    if field_name in DATE_FIELDS:
        return norm.normalize_date(raw_text)
    return norm.normalize_id(raw_text)


def normalize_quantity(text: Any) -> Optional[int]:
    """Read a printed quantity as an integer, or ``None`` if it is not one.

    A quantity is an integer by contract, so a *fractional* quantity (``1,65`` —
    1.65 kg of fish) cannot be represented and must not be turned into one.
    Stripping the non-digits would read ``1,65`` as ``165``, a different number
    100x the printed one, which would then quietly pass an arithmetic check the
    human never saw. ``None`` keeps the field unresolved and sends it to review,
    and the raw text stays on the candidate so the human still sees ``1,65``.

    A trailing unit (``0,272kg``) is dropped before the decision: it is never part
    of the number.
    """
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", text).strip()
    if not cleaned:
        return None
    # A decimal separator means a fractional quantity, which is unrepresentable.
    if "," in cleaned or "." in cleaned:
        return None
    return int(cleaned) if cleaned.lstrip("-").isdigit() else None


def normalize_line_value(field_name: str, text: Any):
    """Normalize one line-item cell value according to its canonical field type."""
    if field_name in LINE_MONEY_FIELDS:
        return norm.normalize_money(text)
    if field_name == "invoiced_quantity":
        return normalize_quantity(text)
    return norm.normalize_id(text)

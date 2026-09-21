"""Normalization: raw extracted fields -> canonical domain objects.

Rules (see docs/DATA_MODEL.md, DECISION_FLOW.md step 2):
- Money becomes integer VND. Thousand separators ("," or ".") and VND suffixes
  are stripped. Anything that cannot be read as whole VND stays ``None``.
- Dates are ISO ``YYYY-MM-DD`` or ``None``.
- Unknown/unreadable fields stay ``None`` and are never guessed into values.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from invoice_referee.domain import models as m

_MONEY_SUFFIXES = ("VND", "VNĐ", "₫", "Đ", "D")


def normalize_money(value: Any) -> Optional[int]:
    """Return integer VND, or ``None`` if the value cannot be read as whole VND."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if not value.is_integer() or value < 0:
            return None
        return int(value)
    if isinstance(value, str):
        s = value.strip().upper()
        for suffix in _MONEY_SUFFIXES:
            s = s.replace(suffix, "")
        s = s.replace("_", "").replace(" ", "")
        # Negative money is not a valid VND amount; it must stay unknown so the
        # caller flags it rather than tripping the non-negative contract.
        if not s or s.startswith(("-", "+")):
            return None
        # Thousand separators in both English ("30,000,000") and Vietnamese
        # ("30.000.000") formatting. A separator must be followed by exactly
        # three digits; anything else ("1.5", "30,5") is an ambiguous decimal
        # and VND has no minor unit, so the value stays unknown.
        if "." in s or "," in s:
            groups = re.split(r"[.,]", s)
            if not groups[0].isdigit():
                return None
            if not all(group.isdigit() and len(group) == 3 for group in groups[1:]):
                return None
            return int("".join(groups))
        if s.isdigit():
            return int(s)
        return None
    return None


# Accepted input date formats, tried in order. ISO is the canonical output.
# Vietnamese invoices are day-first (dd/mm/yyyy), so day precedes month for the
# slash/dot/dash separated forms. SYNTHETIC assumption for the prototype: a
# day-first locale. An out-of-range day/month (e.g. 13/13) fails all formats and
# stays None rather than being guessed.
_DATE_INPUT_FORMATS = (
    "%Y-%m-%d",   # 2026-09-13  (ISO, canonical)
    "%d/%m/%Y",   # 13/09/2026  (VN invoice, most common)
    "%d-%m-%Y",   # 13-09-2026
    "%d.%m.%Y",   # 13.09.2026
    "%Y/%m/%d",   # 2026/09/13
)

# Vietnamese long form: "Ngày 10 tháng 07 năm 2023" (day/month/year).
# Allows an optional leading "ngày" and optional "ngày"/"tháng"/"năm" markers.
# OCR frequently drops the Vietnamese tone marks, so the unaccented spellings
# ("ngay", "thang", "nam") are accepted as explicit alternatives. This is a
# bounded token list, not general diacritic folding: an unknown word still fails.
_VI_DATE_RE = re.compile(
    r"(?:ngày\s*|ngay\s*)?(?P<day>\d{1,2})\s*"
    r"(?:tháng\s*|thang\s*|/|-|\.)(?P<month>\d{1,2})\s*"
    r"(?:năm\s*|nam\s*|/|-|\.)(?P<year>\d{4})"
)


def normalize_date(value: Any) -> Optional[str]:
    """Return an ISO ``YYYY-MM-DD`` string, or ``None`` if unparseable.

    Accepts ISO plus common day-first invoice formats (dd/mm/yyyy, dd-mm-yyyy,
    dd.mm.yyyy) and the Vietnamese long form ``Ngày 10 tháng 07 năm 2023``.
    Ambiguity note: a value like ``03/04/2026`` is read day-first as 3 April
    2026 (Vietnamese convention); an impossible date (month > 12, day > 31)
    returns ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in _DATE_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return parsed.strftime("%Y-%m-%d")
    # OCR often reads a timestamp alongside the date ("13/09/2026 14:30").
    # No accepted format carries a time, so retry with the leading token.
    head = s.split()[0] if " " in s else ""
    if head and head != s:
        for fmt in _DATE_INPUT_FORMATS:
            try:
                parsed = datetime.strptime(head, fmt)
            except ValueError:
                continue
            return parsed.strftime("%Y-%m-%d")
    m = _VI_DATE_RE.search(s)
    if m:
        try:
            parsed = datetime(int(m["year"]), int(m["month"]), int(m["day"]))
        except ValueError:
            return None
        return parsed.strftime("%Y-%m-%d")
    return None


def normalize_id(value: Any) -> Optional[str]:
    """Return a stripped identifier string, or ``None`` if empty."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize_text(value: Any) -> Optional[str]:
    """Return a stripped string, or ``None`` for a missing or non-string value.

    Unlike :func:`normalize_id`, a wrong type (number, list, dict) is rejected
    instead of being stringified into a bogus value.
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    return s or None


def _quantity(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip()
        if s.lstrip("-").isdigit():
            return int(s)
    return None


def _enum(value: Any, enum_cls, default):
    if value is None:
        return default
    try:
        return enum_cls(str(value).strip().upper())
    except ValueError:
        return default


def _enum_or_none(value: Any, enum_cls):
    """Return an enum member, ``None`` for a supplied-but-unparseable value.

    Distinct from :func:`_enum`, which swallows an unparseable value into a
    default. Here an absent value is the caller's business; a supplied garbage
    value returns ``None`` so the caller can flag it instead of guessing.
    """
    if value is None:
        return None
    try:
        return enum_cls(str(value).strip().upper())
    except ValueError:
        return None


# --- Domain object builders --------------------------------------------------


def to_po_line_item(raw: dict) -> m.POLineItem:
    return m.POLineItem(
        item_id=normalize_id(raw.get("item_id")),
        description=raw.get("description"),
        ordered_quantity=_quantity(raw.get("ordered_quantity")),
        unit_price=normalize_money(raw.get("unit_price")),
        line_total=normalize_money(raw.get("line_total")),
        supplier_sku=normalize_id(raw.get("supplier_sku")),
    )


def to_receipt_line_item(raw: dict) -> m.ReceiptLineItem:
    return m.ReceiptLineItem(
        item_id=normalize_id(raw.get("item_id")),
        description=raw.get("description"),
        received_quantity=_quantity(raw.get("received_quantity")),
    )


def to_invoice_line_item(raw: dict) -> m.InvoiceLineItem:
    return m.InvoiceLineItem(
        item_id=normalize_id(raw.get("item_id")),
        description=raw.get("description"),
        invoiced_quantity=_quantity(raw.get("invoiced_quantity")),
        unit_price=normalize_money(raw.get("unit_price")),
        line_total=normalize_money(raw.get("line_total")),
    )


def to_purchase_order(raw: dict) -> m.PurchaseOrder:
    return m.PurchaseOrder(
        po_id=normalize_id(raw.get("po_id")),
        vendor_id=normalize_id(raw.get("vendor_id")),
        vendor_tax_code=normalize_id(raw.get("vendor_tax_code")),
        vendor_name=raw.get("vendor_name"),
        currency=normalize_id(raw.get("currency")) or "VND",
        order_date=normalize_date(raw.get("order_date")),
        items=[to_po_line_item(i) for i in raw.get("items", []) if i],
        approved_total=normalize_money(raw.get("approved_total")),
        status=normalize_id(raw.get("status")),
    )


def to_goods_receipt(raw: dict) -> m.GoodsReceipt:
    return m.GoodsReceipt(
        receipt_id=normalize_id(raw.get("receipt_id")),
        po_id=normalize_id(raw.get("po_id")),
        received_date=normalize_date(raw.get("received_date")),
        items=[to_receipt_line_item(i) for i in raw.get("items", []) if i],
        status=normalize_id(raw.get("status")),
    )


def _supplied_but_unparseable(raw: dict, key: str, normalized: Any) -> bool:
    """True if ``key`` was provided as a non-empty value but failed to normalize."""
    raw_value = raw.get(key)
    if raw_value is None:
        return False
    if isinstance(raw_value, str) and not raw_value.strip():
        return False
    return normalized is None


def to_supplier_invoice(raw: dict) -> m.SupplierInvoice:
    total_amount = normalize_money(raw.get("total_amount"))
    invoice_date = normalize_date(raw.get("invoice_date"))
    # Sprint 1 is VND-only: an absent currency block is routine and defaults to
    # VND. Any *other* supplied currency is out of scope and must not silently
    # pass as VND, so it is surfaced as None + flag.
    currency = normalize_id(raw.get("currency"))
    currency_unsupported = currency is not None and currency.upper() != "VND"
    # An absent invoice type is an ordinary original invoice. A supplied type we
    # cannot parse (e.g. "CREDIT_NOTE") must not silently become ORIGINAL.
    invoice_type = _enum_or_none(raw.get("invoice_type"), m.InvoiceType)
    invoice_type_unreadable = invoice_type is None and _supplied_but_unparseable(
        raw, "invoice_type", invoice_type
    )
    # A critical field that was supplied but could not be read is an uncertainty
    # we must surface, not silently drop.
    flagged = (
        bool(raw.get("flagged", False))
        or _supplied_but_unparseable(raw, "total_amount", total_amount)
        or _supplied_but_unparseable(raw, "invoice_date", invoice_date)
        or currency_unsupported
        or invoice_type_unreadable
    )
    return m.SupplierInvoice(
        invoice_id=normalize_id(raw.get("invoice_id")),
        invoice_number=normalize_id(raw.get("invoice_number")),
        invoice_series=normalize_id(raw.get("invoice_series")),
        invoice_type=invoice_type or m.InvoiceType.ORIGINAL,
        related_invoice_number=normalize_id(raw.get("related_invoice_number")),
        vendor_id=normalize_id(raw.get("vendor_id")),
        vendor_tax_code=normalize_id(raw.get("vendor_tax_code")),
        vendor_name=raw.get("vendor_name"),
        po_id=normalize_id(raw.get("po_id")),
        invoice_date=invoice_date,
        currency=None if currency_unsupported else (currency or "VND"),
        items=[to_invoice_line_item(i) for i in raw.get("items", []) if i],
        total_amount=total_amount,
        source_type=_enum(raw.get("source_type"), m.SourceType, m.SourceType.JSON),
        confidence=raw.get("confidence", 1.0),
        flagged=flagged,
    )


def to_payment_record(raw: dict) -> m.PaymentRecord:
    return m.PaymentRecord(
        payment_id=normalize_id(raw.get("payment_id")),
        invoice_id=normalize_id(raw.get("invoice_id")),
        status=_enum(raw.get("status"), m.PaymentStatus, m.PaymentStatus.UNKNOWN),
        paid_amount=normalize_money(raw.get("paid_amount")),
        payment_date=normalize_date(raw.get("payment_date")),
    )


def to_approval_record(raw: dict) -> m.ApprovalRecord:
    return m.ApprovalRecord(
        approval_id=normalize_id(raw.get("approval_id")),
        po_id=normalize_id(raw.get("po_id")),
        approval_type=normalize_id(raw.get("approval_type")),
        item_id=normalize_id(raw.get("item_id")),
        approved_value=normalize_money(raw.get("approved_value")),
        approved_text_value=normalize_id(raw.get("approved_text_value")),
        approved_amount_delta=normalize_money(raw.get("approved_amount_delta")),
        approved_by=raw.get("approved_by"),
        approved_at=raw.get("approved_at"),
        status=normalize_id(raw.get("status")),
    )

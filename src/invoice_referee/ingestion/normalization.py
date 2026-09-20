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
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip().upper()
        for suffix in _MONEY_SUFFIXES:
            s = s.replace(suffix, "")
        # Thousand separators in both English ("30,000,000") and Vietnamese
        # ("30.000.000") formatting; VND has no fractional part.
        s = s.replace(",", "").replace(".", "").replace("_", "").replace(" ", "")
        if s.startswith("-"):
            sign, digits = -1, s[1:]
        else:
            sign, digits = 1, s
        if digits.isdigit():
            return sign * int(digits)
        return None
    return None


def normalize_date(value: Any) -> Optional[str]:
    """Return an ISO ``YYYY-MM-DD`` string, or ``None`` for unknown/other formats."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
        return s
    return None


def normalize_id(value: Any) -> Optional[str]:
    """Return a stripped identifier string, or ``None`` if empty."""
    if value is None:
        return None
    s = str(value).strip()
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


# --- Domain object builders --------------------------------------------------


def to_po_line_item(raw: dict) -> m.POLineItem:
    return m.POLineItem(
        item_id=normalize_id(raw.get("item_id")),
        description=raw.get("description"),
        ordered_quantity=_quantity(raw.get("ordered_quantity")),
        unit_price=normalize_money(raw.get("unit_price")),
        line_total=normalize_money(raw.get("line_total")),
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
    # A critical field that was supplied but could not be read is an uncertainty
    # we must surface, not silently drop.
    flagged = (
        bool(raw.get("flagged", False))
        or _supplied_but_unparseable(raw, "total_amount", total_amount)
        or _supplied_but_unparseable(raw, "invoice_date", invoice_date)
    )
    return m.SupplierInvoice(
        invoice_id=normalize_id(raw.get("invoice_id")),
        invoice_number=normalize_id(raw.get("invoice_number")),
        invoice_series=normalize_id(raw.get("invoice_series")),
        invoice_type=_enum(raw.get("invoice_type"), m.InvoiceType, m.InvoiceType.ORIGINAL),
        related_invoice_number=normalize_id(raw.get("related_invoice_number")),
        vendor_id=normalize_id(raw.get("vendor_id")),
        vendor_tax_code=normalize_id(raw.get("vendor_tax_code")),
        vendor_name=raw.get("vendor_name"),
        po_id=normalize_id(raw.get("po_id")),
        invoice_date=invoice_date,
        currency=normalize_id(raw.get("currency")) or "VND",
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

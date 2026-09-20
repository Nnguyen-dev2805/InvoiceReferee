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
        item_id=normalize_id(raw.get("item_id")) or "",
        description=raw.get("description"),
        ordered_quantity=_quantity(raw.get("ordered_quantity")) or 0,
        unit_price=normalize_money(raw.get("unit_price")) or 0,
        line_total=normalize_money(raw.get("line_total")) or 0,
    )


def to_receipt_line_item(raw: dict) -> m.ReceiptLineItem:
    return m.ReceiptLineItem(
        item_id=normalize_id(raw.get("item_id")) or "",
        description=raw.get("description"),
        received_quantity=_quantity(raw.get("received_quantity")) or 0,
    )


def to_invoice_line_item(raw: dict) -> m.InvoiceLineItem:
    return m.InvoiceLineItem(
        item_id=normalize_id(raw.get("item_id")) or "",
        description=raw.get("description"),
        invoiced_quantity=_quantity(raw.get("invoiced_quantity")) or 0,
        unit_price=normalize_money(raw.get("unit_price")) or 0,
        line_total=normalize_money(raw.get("line_total")) or 0,
    )


def to_purchase_order(raw: dict) -> m.PurchaseOrder:
    return m.PurchaseOrder(
        po_id=normalize_id(raw.get("po_id")) or "",
        vendor_id=normalize_id(raw.get("vendor_id")) or "",
        vendor_name=raw.get("vendor_name"),
        currency=raw.get("currency", "VND"),
        order_date=normalize_date(raw.get("order_date")),
        items=[to_po_line_item(i) for i in raw.get("items", [])],
        approved_total=normalize_money(raw.get("approved_total")) or 0,
        status=raw.get("status", "APPROVED"),
    )


def to_goods_receipt(raw: dict) -> m.GoodsReceipt:
    return m.GoodsReceipt(
        receipt_id=normalize_id(raw.get("receipt_id")) or "",
        po_id=normalize_id(raw.get("po_id")) or "",
        received_date=normalize_date(raw.get("received_date")) or "",
        items=[to_receipt_line_item(i) for i in raw.get("items", [])],
        status=raw.get("status", "RECEIVED"),
    )


def to_supplier_invoice(raw: dict) -> m.SupplierInvoice:
    raw_amount = raw.get("total_amount")
    total_amount = normalize_money(raw_amount)
    # An amount that was supplied but could not be read is a critical uncertainty.
    flagged = bool(raw.get("flagged", False)) or (raw_amount is not None and total_amount is None)
    return m.SupplierInvoice(
        invoice_id=normalize_id(raw.get("invoice_id")) or "",
        invoice_number=normalize_id(raw.get("invoice_number")) or "",
        invoice_series=normalize_id(raw.get("invoice_series")) or "",
        invoice_type=_enum(raw.get("invoice_type"), m.InvoiceType, m.InvoiceType.ORIGINAL),
        related_invoice_number=normalize_id(raw.get("related_invoice_number")),
        vendor_id=normalize_id(raw.get("vendor_id")) or "",
        vendor_tax_code=normalize_id(raw.get("vendor_tax_code")) or "",
        vendor_name=raw.get("vendor_name"),
        po_id=normalize_id(raw.get("po_id")) or "",
        invoice_date=normalize_date(raw.get("invoice_date")) or "",
        currency=raw.get("currency", "VND"),
        items=[to_invoice_line_item(i) for i in raw.get("items", [])],
        total_amount=total_amount,
        source_type=_enum(raw.get("source_type"), m.SourceType, m.SourceType.JSON),
        confidence=raw.get("confidence", 1.0),
        flagged=flagged,
    )


def to_payment_record(raw: dict) -> m.PaymentRecord:
    return m.PaymentRecord(
        payment_id=normalize_id(raw.get("payment_id")),
        invoice_id=normalize_id(raw.get("invoice_id")) or "",
        status=_enum(raw.get("status"), m.PaymentStatus, m.PaymentStatus.UNKNOWN),
        paid_amount=normalize_money(raw.get("paid_amount")) or 0,
        payment_date=normalize_date(raw.get("payment_date")),
    )


def to_approval_record(raw: dict) -> m.ApprovalRecord:
    return m.ApprovalRecord(
        approval_id=normalize_id(raw.get("approval_id")) or "",
        po_id=normalize_id(raw.get("po_id")) or "",
        approval_type=raw.get("approval_type", ""),
        item_id=normalize_id(raw.get("item_id")),
        approved_value=normalize_money(raw.get("approved_value")),
        approved_amount_delta=normalize_money(raw.get("approved_amount_delta")),
        approved_by=raw.get("approved_by"),
        approved_at=raw.get("approved_at"),
        status=raw.get("status", ""),
    )

"""Tests for extraction (JSON adapter) and normalization."""

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion import json_adapter, normalization as norm


# --- normalize_money ---------------------------------------------------------


def test_money_passthrough_int():
    assert norm.normalize_money(30_000_000) == 30_000_000


def test_money_parses_english_thousands_separator():
    assert norm.normalize_money("30,000,000") == 30_000_000


def test_money_parses_vietnamese_thousands_separator_and_suffix():
    assert norm.normalize_money("30.000.000 VND") == 30_000_000


def test_money_parses_whole_float():
    assert norm.normalize_money(30_000_000.0) == 30_000_000


def test_money_fractional_float_is_unknown():
    # Fractional VND cannot be represented as integer money -> stays unknown.
    assert norm.normalize_money(30_000_000.5) is None


def test_money_none_stays_none():
    assert norm.normalize_money(None) is None


def test_money_unparseable_stays_none():
    assert norm.normalize_money("about 45M or 48M") is None


# --- normalize_date ----------------------------------------------------------


def test_date_iso_passthrough():
    assert norm.normalize_date("2026-09-13") == "2026-09-13"


def test_date_invalid_stays_none():
    assert norm.normalize_date("13/09/2026") is None


def test_date_none_stays_none():
    assert norm.normalize_date(None) is None


# --- normalize_id ------------------------------------------------------------


def test_id_strips_whitespace():
    assert norm.normalize_id("  PO-001 ") == "PO-001"


def test_id_empty_becomes_none():
    assert norm.normalize_id("   ") is None


# --- JSON adapter: ExtractedDocument -----------------------------------------


def test_extract_document_preserves_source_ref_and_type():
    raw = {"invoice_number": "0000123", "total_amount": 30_000_000}
    doc = json_adapter.extract_document(
        raw, document_type="SUPPLIER_INVOICE", source_ref="fixture://TC01/invoice.json"
    )
    assert isinstance(doc, m.ExtractedDocument)
    assert doc.document_type == "SUPPLIER_INVOICE"
    assert doc.source_type is m.SourceType.JSON
    assert doc.source_ref == "fixture://TC01/invoice.json"
    assert doc.extractor == "json_adapter"
    assert doc.fields["invoice_number"] == "0000123"
    assert doc.parse_warnings == []


def test_extract_document_carries_input_parse_warnings():
    raw = {"total_amount": None, "parse_warnings": ["total_amount unreadable"]}
    doc = json_adapter.extract_document(raw, document_type="SUPPLIER_INVOICE", source_ref="paste")
    assert "total_amount unreadable" in doc.parse_warnings


def test_extract_document_does_not_guess_missing_fields():
    raw = {"invoice_number": "0000123"}
    doc = json_adapter.extract_document(raw, document_type="SUPPLIER_INVOICE", source_ref="paste")
    assert "total_amount" not in doc.fields


# --- normalization to domain objects -----------------------------------------


def test_to_supplier_invoice_normalizes_amount_and_type():
    inv = norm.to_supplier_invoice(
        {
            "invoice_id": "INV-001",
            "invoice_number": "0000123",
            "invoice_series": "2C23TTU",
            "invoice_type": "original",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-13",
            "total_amount": "30.000.000 VND",
            "items": [
                {"item_id": "ITEM-001", "invoiced_quantity": 10, "unit_price": "3.000.000", "line_total": "30.000.000"}
            ],
        }
    )
    assert inv.total_amount == 30_000_000
    assert inv.invoice_type is m.InvoiceType.ORIGINAL
    assert inv.items[0].unit_price == 3_000_000


def test_to_supplier_invoice_unreadable_amount_flags_and_stays_none():
    inv = norm.to_supplier_invoice(
        {
            "invoice_id": "INV-015",
            "invoice_number": "0000999",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-015",
            "invoice_date": "2026-09-13",
            "total_amount": "45M hoặc 48M",
            "items": [],
        }
    )
    assert inv.total_amount is None
    assert inv.flagged is True


def test_to_payment_record_unknown_status_preserved():
    rec = norm.to_payment_record({"invoice_id": "INV-001", "status": "weird-status"})
    assert rec.status is m.PaymentStatus.UNKNOWN


def test_to_payment_record_maps_partially_paid():
    rec = norm.to_payment_record(
        {"invoice_id": "INV-001", "status": "PARTIALLY_PAID", "paid_amount": "10,000,000"}
    )
    assert rec.status is m.PaymentStatus.PARTIALLY_PAID
    assert rec.paid_amount == 10_000_000


def test_to_purchase_order_normalizes_total():
    po = norm.to_purchase_order(
        {
            "po_id": "PO-001",
            "vendor_id": "V-ABC",
            "approved_total": "30,000,000",
            "status": "APPROVED",
            "items": [
                {"item_id": "ITEM-001", "ordered_quantity": 10, "unit_price": "3,000,000", "line_total": "30,000,000"}
            ],
        }
    )
    assert po.approved_total == 30_000_000
    assert po.items[0].ordered_quantity == 10


def test_to_approval_record_only_uses_structured_fields():
    apr = norm.to_approval_record(
        {
            "approval_id": "APR-001",
            "po_id": "PO-001",
            "approval_type": "UNIT_PRICE_CHANGE",
            "approved_value": "3,500,000",
            "status": "APPROVED",
        }
    )
    assert apr.approved_value == 3_500_000
    assert apr.status == "APPROVED"


# --- Fail-closed: missing critical fields stay unknown (Task 2) ---------------


def _invoice_raw():
    return {
        "invoice_id": "INV-001",
        "invoice_number": "0000123",
        "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL",
        "vendor_id": "V-ABC",
        "vendor_tax_code": "0101234567",
        "po_id": "PO-001",
        "invoice_date": "2026-09-13",
        "total_amount": 30_000_000,
        "items": [],
    }


def test_missing_invoice_line_values_stay_unknown():
    line = norm.to_invoice_line_item({"description": "Monitor"})
    assert line.item_id is None
    assert line.invoiced_quantity is None
    assert line.unit_price is None
    assert line.line_total is None


def test_missing_po_line_values_stay_unknown():
    line = norm.to_po_line_item({"description": "Monitor"})
    assert line.item_id is None
    assert line.ordered_quantity is None
    assert line.unit_price is None
    assert line.line_total is None


def test_missing_receipt_line_values_stay_unknown():
    line = norm.to_receipt_line_item({"description": "Monitor"})
    assert line.item_id is None
    assert line.received_quantity is None


def test_missing_po_values_stay_unknown():
    po = norm.to_purchase_order({"items": []})
    assert po.po_id is None
    assert po.vendor_id is None
    assert po.approved_total is None
    assert po.status is None


def test_missing_goods_receipt_values_stay_unknown():
    gr = norm.to_goods_receipt({"items": []})
    assert gr.receipt_id is None
    assert gr.po_id is None
    assert gr.received_date is None
    assert gr.status is None


def test_purchase_order_carries_vendor_tax_code():
    po = norm.to_purchase_order(
        {"po_id": "PO-001", "vendor_id": "V-ABC", "vendor_tax_code": "0101234567", "items": []}
    )
    assert po.vendor_tax_code == "0101234567"


def test_missing_invoice_identity_values_stay_unknown():
    inv = norm.to_supplier_invoice({"items": []})
    assert inv.invoice_id is None
    assert inv.invoice_number is None
    assert inv.invoice_series is None
    assert inv.vendor_id is None
    assert inv.vendor_tax_code is None
    assert inv.po_id is None
    assert inv.invoice_date is None
    assert inv.total_amount is None


def test_missing_payment_amount_stays_unknown():
    rec = norm.to_payment_record({"invoice_id": "INV-001", "status": "UNPAID"})
    assert rec.paid_amount is None


def test_invalid_invoice_date_stays_unknown_and_flags_invoice():
    raw = _invoice_raw()
    raw["invoice_date"] = "13/09/2026"
    invoice = norm.to_supplier_invoice(raw)
    assert invoice.invoice_date is None
    assert invoice.flagged is True

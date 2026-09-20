"""Shared test factories."""

import copy

import pytest

from invoice_referee.transaction.builder import build_transaction
from invoice_referee.checks import engine

_ROUTINE = {
    "transaction_id": "TX-01",
    "transaction_type": "PO_GOODS_PURCHASE",
    "purchase_order": {
        "po_id": "PO-001",
        "vendor_id": "V-ABC",
        "approved_total": 30_000_000,
        "status": "APPROVED",
        "items": [
            {"item_id": "ITEM-001", "ordered_quantity": 10, "unit_price": 3_000_000, "line_total": 30_000_000}
        ],
    },
    "goods_receipts": [
        {
            "receipt_id": "GR-001",
            "po_id": "PO-001",
            "received_date": "2026-09-12",
            "items": [{"item_id": "ITEM-001", "received_quantity": 10}],
        }
    ],
    "invoice": {
        "invoice_id": "INV-001",
        "invoice_number": "0000123",
        "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL",
        "vendor_id": "V-ABC",
        "vendor_tax_code": "0101234567",
        "po_id": "PO-001",
        "invoice_date": "2026-09-13",
        "total_amount": 30_000_000,
        "items": [
            {"item_id": "ITEM-001", "invoiced_quantity": 10, "unit_price": 3_000_000, "line_total": 30_000_000}
        ],
    },
    "payment_history": [{"invoice_id": "INV-001", "status": "UNPAID", "paid_amount": 0}],
}


@pytest.fixture
def routine_evidence():
    """Return a deep copy of a routine PO-goods-purchase evidence dict."""

    def _make():
        return copy.deepcopy(_ROUTINE)

    return _make


@pytest.fixture
def build_inputs():
    """Return (transaction, checks) for a raw evidence dict."""

    def _build(evidence):
        tx = build_transaction(evidence)
        checks = engine.run_checks(tx)
        return tx, checks

    return _build

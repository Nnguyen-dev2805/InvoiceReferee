"""Tests for build_transaction (evidence linking)."""

import pytest

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction


def _routine_evidence():
    return {
        "transaction_id": "TX-001",
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
                "status": "RECEIVED",
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


def test_builds_routine_transaction():
    tx = build_transaction(_routine_evidence())
    assert tx.transaction_id == "TX-001"
    assert tx.transaction_type is m.TransactionType.PO_GOODS_PURCHASE
    assert tx.po.po_id == "PO-001"
    assert len(tx.goods_receipts) == 1
    assert tx.invoice.invoice_id == "INV-001"
    assert tx.payment_history[0].status is m.PaymentStatus.UNPAID


def test_missing_po_is_not_invented():
    ev = _routine_evidence()
    del ev["purchase_order"]
    tx = build_transaction(ev)
    assert tx.po is None
    # invoice still references a PO id, so the type stays PO_GOODS_PURCHASE
    assert tx.transaction_type is m.TransactionType.PO_GOODS_PURCHASE


def test_missing_goods_receipt_yields_empty_list():
    ev = _routine_evidence()
    del ev["goods_receipts"]
    tx = build_transaction(ev)
    assert tx.goods_receipts == []


def test_multiple_goods_receipts_are_linked():
    ev = _routine_evidence()
    ev["goods_receipts"].append(
        {
            "receipt_id": "GR-002",
            "po_id": "PO-001",
            "received_date": "2026-09-14",
            "items": [{"item_id": "ITEM-001", "received_quantity": 5}],
        }
    )
    tx = build_transaction(ev)
    assert [gr.receipt_id for gr in tx.goods_receipts] == ["GR-001", "GR-002"]


def test_prior_invoices_are_linked():
    ev = _routine_evidence()
    ev["prior_invoices"] = [
        {
            "invoice_id": "INV-000",
            "invoice_number": "0000100",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-11",
            "total_amount": 12_000_000,
            "items": [
                {"item_id": "ITEM-001", "invoiced_quantity": 4, "unit_price": 3_000_000, "line_total": 12_000_000}
            ],
        }
    ]
    tx = build_transaction(ev)
    assert len(tx.prior_invoices) == 1
    assert tx.prior_invoices[0].invoice_id == "INV-000"


def test_invoice_relationship_metadata_preserved():
    ev = _routine_evidence()
    ev["invoice"]["invoice_type"] = "ADJUSTMENT"
    ev["invoice"]["related_invoice_number"] = "0000100"
    tx = build_transaction(ev)
    assert tx.invoice.invoice_type is m.InvoiceType.ADJUSTMENT
    assert tx.invoice.related_invoice_number == "0000100"


def test_approval_evidence_linked_only_when_present():
    ev = _routine_evidence()
    ev["approvals"] = [
        {
            "approval_id": "APR-001",
            "po_id": "PO-001",
            "approval_type": "UNIT_PRICE_CHANGE",
            "approved_value": 3_500_000,
            "status": "APPROVED",
        }
    ]
    tx = build_transaction(ev)
    assert len(tx.approvals) == 1
    assert tx.approvals[0].approval_id == "APR-001"

    tx2 = build_transaction(_routine_evidence())
    assert tx2.approvals == []


def test_unknown_payment_status_preserved():
    ev = _routine_evidence()
    ev["payment_history"] = [{"invoice_id": "INV-001", "status": "???"}]
    tx = build_transaction(ev)
    assert tx.payment_history[0].status is m.PaymentStatus.UNKNOWN


def test_known_but_unsupported_type_preserved_for_scope():
    ev = _routine_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    tx = build_transaction(ev)
    assert tx.transaction_type is None
    assert tx.declared_transaction_type == "SERVICE_INVOICE"


def test_type_unknown_when_no_declaration_and_no_po_reference():
    ev = {
        "transaction_id": "TX-UNK",
        "invoice": {
            "invoice_id": "INV-X",
            "invoice_number": "1",
            "invoice_series": "S",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V",
            "vendor_tax_code": "0",
            "po_id": None,
            "invoice_date": "2026-09-13",
            "total_amount": 1000,
            "items": [],
        },
    }
    tx = build_transaction(ev)
    assert tx.transaction_type is None
    assert tx.declared_transaction_type is None


def test_unreadable_invoice_amount_stays_unknown_end_to_end():
    ev = _routine_evidence()
    ev["invoice"]["total_amount"] = "45M hoặc 48M"
    tx = build_transaction(ev)
    assert tx.invoice.total_amount is None
    assert tx.invoice.flagged is True


# --- Evidence issues (Task 3) ------------------------------------------------


def test_routine_evidence_has_no_issues():
    tx = build_transaction(_routine_evidence())
    assert tx.evidence_issues == []


def test_po_not_approved_is_an_evidence_issue():
    ev = _routine_evidence()
    ev["purchase_order"]["status"] = "DRAFT"
    tx = build_transaction(ev)
    assert any(i.issue_id == "PO_STATUS" for i in tx.evidence_issues)


def test_missing_po_status_is_an_evidence_issue():
    ev = _routine_evidence()
    del ev["purchase_order"]["status"]
    tx = build_transaction(ev)
    assert any(i.issue_id == "PO_STATUS" for i in tx.evidence_issues)


def test_invoice_pointing_to_wrong_po_is_an_evidence_issue():
    ev = _routine_evidence()
    ev["invoice"]["po_id"] = "PO-WRONG"
    tx = build_transaction(ev)
    assert any(i.issue_id == "INVOICE_PO_LINK" for i in tx.evidence_issues)


def test_receipt_pointing_to_wrong_po_is_an_evidence_issue():
    ev = _routine_evidence()
    ev["goods_receipts"][0]["po_id"] = "PO-WRONG"
    tx = build_transaction(ev)
    assert any(i.issue_id == "RECEIPT_PO_LINK" for i in tx.evidence_issues)


def test_receipt_not_received_is_an_evidence_issue():
    ev = _routine_evidence()
    ev["goods_receipts"][0]["status"] = "PENDING"
    tx = build_transaction(ev)
    assert any(i.issue_id == "RECEIPT_STATUS" for i in tx.evidence_issues)


def test_missing_receipt_status_is_an_evidence_issue():
    ev = _routine_evidence()
    del ev["goods_receipts"][0]["status"]
    tx = build_transaction(ev)
    assert any(i.issue_id == "RECEIPT_STATUS" for i in tx.evidence_issues)

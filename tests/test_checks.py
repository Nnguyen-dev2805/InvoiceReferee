"""Tests for the deterministic check engine (8 checks)."""

import copy

import pytest

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from invoice_referee.checks import engine
from invoice_referee.checks import (
    vendor as vendor_check,
    item as item_check,
    quantity as quantity_check,
    price as price_check,
    amount as amount_check,
    duplicate as duplicate_check,
    payment as payment_check,
    po_limit as po_limit_check,
)


def _tc01_evidence():
    """Routine exact match: PO 30M, received 10/10, invoice 30M, unpaid."""
    return {
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


def _tx(evidence):
    return build_transaction(evidence)


def _by_id(results, check_id):
    return next(r for r in results if r.check_id == check_id)


# --- Engine: routine all PASS ------------------------------------------------


def test_run_checks_routine_all_pass():
    results = engine.run_checks(_tx(_tc01_evidence()))
    ids = {r.check_id for r in results}
    assert ids == {
        "CHECK_VENDOR",
        "CHECK_ITEM",
        "CHECK_QUANTITY",
        "CHECK_PRICE",
        "CHECK_AMOUNT",
        "CHECK_DUPLICATE",
        "CHECK_PAYMENT",
        "CHECK_PO_LIMIT",
    }
    assert all(r.status is m.CheckStatus.PASS for r in results)


def test_checks_never_return_decision_actions():
    results = engine.run_checks(_tx(_tc01_evidence()))
    decision_values = {"AUTO_PROCESS", "REQUEST_INFO", "ESCALATE"}
    for r in results:
        assert r.status.value not in decision_values


# --- Vendor (P02) ------------------------------------------------------------


def test_vendor_mismatch_without_approval_fails():
    ev = _tc01_evidence()
    ev["invoice"]["vendor_id"] = "V-XYZ"
    r = vendor_check.check_vendor(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P02"


def test_vendor_mismatch_with_approved_change_passes():
    ev = _tc01_evidence()
    ev["invoice"]["vendor_id"] = "V-XYZ"
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "VENDOR_CHANGE",
            "approved_text_value": "V-XYZ",
            "status": "APPROVED",
        }
    ]
    r = vendor_check.check_vendor(_tx(ev))
    assert r.status is m.CheckStatus.PASS


def test_vendor_change_approval_for_other_vendor_does_not_cover():
    ev = _tc01_evidence()
    ev["invoice"]["vendor_id"] = "V-XYZ"
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "VENDOR_CHANGE",
            "approved_text_value": "V-OTHER",
            "status": "APPROVED",
        }
    ]
    r = vendor_check.check_vendor(_tx(ev))
    assert r.status is m.CheckStatus.FAIL


def test_vendor_unknown_when_po_missing():
    ev = _tc01_evidence()
    del ev["purchase_order"]
    r = vendor_check.check_vendor(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


# --- Item (P03) --------------------------------------------------------------


def test_item_not_in_po_fails():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["item_id"] = "ITEM-999"
    r = item_check.check_item(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P03"


# --- Quantity (P05): current + cumulative per item ---------------------------


def test_quantity_exceeds_receipt_fails_tc07():
    ev = _tc01_evidence()
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 8
    ev["invoice"]["items"][0]["invoiced_quantity"] = 10
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P05"
    assert r.expected == 8
    assert r.actual == 10


def test_cumulative_quantity_exceeds_receipt_fails_tc16():
    ev = _tc01_evidence()
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 10
    ev["invoice"]["items"][0]["invoiced_quantity"] = 4
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
            "total_amount": 24_000_000,
            "items": [{"item_id": "ITEM-001", "invoiced_quantity": 8, "unit_price": 3_000_000, "line_total": 24_000_000}],
        }
    ]
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.actual == 12  # 8 prior + 4 current
    assert r.expected == 10


def test_quantity_unknown_when_no_goods_receipt():
    ev = _tc01_evidence()
    del ev["goods_receipts"]
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


def test_quantity_unknown_when_received_quantity_missing():
    ev = _tc01_evidence()
    del ev["goods_receipts"][0]["items"][0]["received_quantity"]
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


def test_quantity_approval_must_bind_to_item_and_quantity():
    # Over-receipt on ITEM-001, but the approval is for a different item.
    ev = _tc01_evidence()
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 8
    ev["invoice"]["items"][0]["invoiced_quantity"] = 12
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "QUANTITY_CHANGE",
            "item_id": "OTHER",
            "approved_value": 12,
            "status": "APPROVED",
        }
    ]
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.FAIL


def test_quantity_over_receipt_with_exact_approval_passes():
    ev = _tc01_evidence()
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 8
    ev["invoice"]["items"][0]["invoiced_quantity"] = 12
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "QUANTITY_CHANGE",
            "item_id": "ITEM-001",
            "approved_value": 12,
            "status": "APPROVED",
        }
    ]
    r = quantity_check.check_quantity(_tx(ev))
    assert r.status is m.CheckStatus.PASS


def test_vendor_unknown_when_vendor_id_missing():
    ev = _tc01_evidence()
    ev["invoice"]["vendor_id"] = None
    r = vendor_check.check_vendor(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


def test_item_unknown_when_item_id_missing():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["item_id"] = None
    r = item_check.check_item(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


# --- Price (P06) -------------------------------------------------------------


def test_unit_price_mismatch_fails_tc08():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["unit_price"] = 3_500_000
    r = price_check.check_price(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P06"


def test_unit_price_mismatch_with_approval_passes():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["unit_price"] = 3_500_000
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "UNIT_PRICE_CHANGE",
            "item_id": "ITEM-001",
            "approved_value": 3_500_000,
            "status": "APPROVED",
        }
    ]
    r = price_check.check_price(_tx(ev))
    assert r.status is m.CheckStatus.PASS


def test_price_approval_value_must_equal_invoice_value():
    # Approval authorises 3,100,000 but the invoice bills 3,500,000 -> not covered.
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["unit_price"] = 3_500_000
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-001",
            "approval_type": "UNIT_PRICE_CHANGE",
            "item_id": "ITEM-001",
            "approved_value": 3_100_000,
            "status": "APPROVED",
        }
    ]
    r = price_check.check_price(_tx(ev))
    assert r.status is m.CheckStatus.FAIL


def test_price_approval_for_other_po_does_not_cover():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["unit_price"] = 3_500_000
    ev["approvals"] = [
        {
            "approval_id": "APR-1",
            "po_id": "PO-999",
            "approval_type": "UNIT_PRICE_CHANGE",
            "item_id": "ITEM-001",
            "approved_value": 3_500_000,
            "status": "APPROVED",
        }
    ]
    r = price_check.check_price(_tx(ev))
    assert r.status is m.CheckStatus.FAIL


def test_unit_price_missing_is_unknown():
    ev = _tc01_evidence()
    ev["invoice"]["items"][0]["unit_price"] = None
    r = price_check.check_price(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


# --- Amount (P07) ------------------------------------------------------------


def test_invoice_exceeds_po_fails_tc09():
    ev = _tc01_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    r = amount_check.check_amount(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P07"


def test_amount_unknown_when_unreadable_tc15():
    ev = _tc01_evidence()
    ev["invoice"]["total_amount"] = "45M hoặc 48M"  # unreadable -> None + flagged
    r = amount_check.check_amount(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


# --- Duplicate (P09) ---------------------------------------------------------


def test_duplicate_same_identity_fails_tc11():
    ev = _tc01_evidence()
    ev["prior_invoices"] = [
        {
            "invoice_id": "INV-OLD",
            "invoice_number": "0000123",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-01",
            "total_amount": 30_000_000,
            "items": [],
        }
    ]
    r = duplicate_check.check_duplicate(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P09"


def test_adjustment_linked_to_original_is_not_duplicate():
    ev = _tc01_evidence()
    ev["invoice"]["invoice_type"] = "ADJUSTMENT"
    ev["invoice"]["related_invoice_number"] = "0000100"
    ev["prior_invoices"] = [
        {
            "invoice_id": "INV-OLD",
            "invoice_number": "0000123",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-01",
            "total_amount": 30_000_000,
            "items": [],
        }
    ]
    r = duplicate_check.check_duplicate(_tx(ev))
    assert r.status is m.CheckStatus.PASS


# --- Payment (P10/P11) -------------------------------------------------------


def test_payment_paid_fails_tc12():
    ev = _tc01_evidence()
    ev["payment_history"] = [{"invoice_id": "INV-001", "status": "PAID", "paid_amount": 30_000_000}]
    r = payment_check.check_payment(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P10"


def test_payment_partially_paid_fails_tc17():
    ev = _tc01_evidence()
    ev["payment_history"] = [{"invoice_id": "INV-001", "status": "PARTIALLY_PAID", "paid_amount": 10_000_000}]
    r = payment_check.check_payment(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.actual == "PARTIALLY_PAID"


def test_payment_unknown_status_is_unknown():
    ev = _tc01_evidence()
    ev["payment_history"] = [{"invoice_id": "INV-001", "status": "???"}]
    r = payment_check.check_payment(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN
    assert r.policy_rule_id == "P11"


def test_payment_missing_history_is_unknown():
    ev = _tc01_evidence()
    del ev["payment_history"]
    r = payment_check.check_payment(_tx(ev))
    assert r.status is m.CheckStatus.UNKNOWN


# --- Cumulative PO limit (P08) -----------------------------------------------


def test_cumulative_po_limit_exceeded_fails_tc10():
    ev = _tc01_evidence()
    ev["invoice"]["total_amount"] = 15_000_000
    ev["prior_invoices"] = [
        {
            "invoice_id": "INV-A",
            "invoice_number": "0000101",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-11",
            "total_amount": 20_000_000,
            "items": [],
        }
    ]
    r = po_limit_check.check_po_limit(_tx(ev))
    assert r.status is m.CheckStatus.FAIL
    assert r.policy_rule_id == "P08"
    assert r.actual == 35_000_000
    assert r.expected == 30_000_000


def test_cumulative_po_limit_within_passes_tc03():
    ev = _tc01_evidence()
    ev["invoice"]["total_amount"] = 18_000_000
    ev["prior_invoices"] = [
        {
            "invoice_id": "INV-A",
            "invoice_number": "0000101",
            "invoice_series": "2C23TTU",
            "invoice_type": "ORIGINAL",
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "po_id": "PO-001",
            "invoice_date": "2026-09-11",
            "total_amount": 12_000_000,
            "items": [],
        }
    ]
    r = po_limit_check.check_po_limit(_tx(ev))
    assert r.status is m.CheckStatus.PASS


# --- Gating by transaction type ----------------------------------------------


def test_checks_not_applicable_for_outside_policy_type():
    ev = _tc01_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    results = engine.run_checks(_tx(ev))
    assert all(r.status is m.CheckStatus.NOT_APPLICABLE for r in results)


def test_checks_not_applicable_for_unknown_type():
    ev = _tc01_evidence()
    del ev["transaction_type"]
    del ev["purchase_order"]
    ev["invoice"]["po_id"] = None
    results = engine.run_checks(_tx(ev))
    assert all(r.status is m.CheckStatus.NOT_APPLICABLE for r in results)

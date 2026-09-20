"""Shared helpers for deterministic checks.

These helpers only read structured facts. They never make a Decision and never
mutate the Transaction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from invoice_referee.domain import models as m

APPROVED = "APPROVED"


def _po_id(tx: m.Transaction) -> Optional[str]:
    return tx.po.po_id if tx.po else None


def has_approval(
    tx: m.Transaction,
    approval_type: str,
    *,
    item_id: Optional[str] = None,
    approved_value: Optional[int] = None,
    approved_text_value: Optional[str] = None,
) -> bool:
    """True only if an exact, PO-bound APPROVED approval exists.

    An approval must belong to the same PO and carry the exact item/value the
    caller is trying to justify. A blanket approval no longer silently covers a
    mismatch it was never issued for.
    """
    for a in tx.approvals:
        if a.status != APPROVED:
            continue
        if a.po_id != _po_id(tx):
            continue
        if a.approval_type != approval_type:
            continue
        if item_id is not None and a.item_id != item_id:
            continue
        if approved_value is not None and a.approved_value != approved_value:
            continue
        if approved_text_value is not None and a.approved_text_value != approved_text_value:
            continue
        return True
    return False


def approved_amount_delta(tx: m.Transaction) -> int:
    """Sum of approved explicit amount increases (AMOUNT_CHANGE) for this PO."""
    total = 0
    for a in tx.approvals:
        if (
            a.status == APPROVED
            and a.po_id == _po_id(tx)
            and a.approval_type == "AMOUNT_CHANGE"
            and a.approved_amount_delta
        ):
            total += a.approved_amount_delta
    return total


def invoice_quantity_facts_complete(tx: m.Transaction) -> bool:
    """True only if every quantity fact needed for the quantity check is present."""
    for gr in tx.goods_receipts:
        for line in gr.items:
            if line.item_id is None or line.received_quantity is None:
                return False
    invoices = list(tx.prior_invoices)
    if tx.invoice:
        invoices.append(tx.invoice)
    for inv in invoices:
        for line in inv.items:
            if line.item_id is None or line.invoiced_quantity is None:
                return False
    return True


def cumulative_received_by_item(tx: m.Transaction) -> dict[str, int]:
    received: dict[str, int] = defaultdict(int)
    for gr in tx.goods_receipts:
        for line in gr.items:
            received[line.item_id] += line.received_quantity
    return dict(received)


def cumulative_invoiced_by_item(tx: m.Transaction) -> dict[str, int]:
    """Prior invoices for the same PO plus the current invoice, summed per item."""
    invoiced: dict[str, int] = defaultdict(int)
    po_id = tx.invoice.po_id if tx.invoice else None
    for prior in tx.prior_invoices:
        if po_id is None or prior.po_id == po_id:
            for line in prior.items:
                invoiced[line.item_id] += line.invoiced_quantity
    if tx.invoice:
        for line in tx.invoice.items:
            invoiced[line.item_id] += line.invoiced_quantity
    return dict(invoiced)


def prior_invoice_total_for_po(tx: m.Transaction) -> int:
    """Sum of readable prior invoice totals bound to the current PO."""
    po_id = tx.invoice.po_id if tx.invoice else None
    total = 0
    for prior in tx.prior_invoices:
        if (po_id is None or prior.po_id == po_id) and prior.total_amount is not None:
            total += prior.total_amount
    return total


def evidence_refs(tx: m.Transaction) -> list[str]:
    refs: list[str] = []
    if tx.po and tx.po.po_id:
        refs.append(tx.po.po_id)
    refs.extend(gr.receipt_id for gr in tx.goods_receipts if gr.receipt_id)
    if tx.invoice and tx.invoice.invoice_id:
        refs.append(tx.invoice.invoice_id)
    return refs

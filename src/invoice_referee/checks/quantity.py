"""Check 3 — Quantity match (P05): current + cumulative invoiced vs received per item."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_QUANTITY"


def check_quantity(tx: m.Transaction) -> m.CheckResult:
    if tx.invoice is None or not tx.goods_receipts:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P05",
            reason="Cannot verify quantity without invoice and goods receipt",
            evidence_refs=s.evidence_refs(tx),
        )

    if not s.invoice_quantity_facts_complete(tx):
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P05",
            reason="A required item identifier or quantity is missing",
            evidence_refs=s.evidence_refs(tx),
        )

    received = s.cumulative_received_by_item(tx)
    invoiced = s.cumulative_invoiced_by_item(tx)

    worst_item = None
    for item_id, inv_qty in invoiced.items():
        rec_qty = received.get(item_id, 0)
        if inv_qty > rec_qty:
            worst_item = (item_id, rec_qty, inv_qty)
            break

    if worst_item is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.PASS,
            policy_rule_id="P05",
            reason="Cumulative invoiced quantity does not exceed received quantity",
            evidence_refs=s.evidence_refs(tx),
        )

    item_id, rec_qty, inv_qty = worst_item
    # An over-receipt is only covered by an approval bound to this exact item
    # and the invoiced quantity it authorises.
    if s.has_approval(tx, "QUANTITY_CHANGE", item_id=item_id, approved_value=inv_qty):
        status, reason = m.CheckStatus.PASS, "Quantity over receipt covered by approved quantity change"
    else:
        status = m.CheckStatus.FAIL
        reason = (
            f"Item {item_id}: cumulative invoiced quantity {inv_qty} exceeds received quantity {rec_qty}"
        )

    return m.CheckResult(
        check_id=CHECK_ID,
        status=status,
        policy_rule_id="P05",
        expected=rec_qty,
        actual=inv_qty,
        reason=reason,
        evidence_refs=s.evidence_refs(tx),
    )

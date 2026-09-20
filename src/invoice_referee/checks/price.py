"""Check 4 — Unit price match (P06)."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_PRICE"


def check_price(tx: m.Transaction) -> m.CheckResult:
    if tx.po is None or tx.invoice is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P06",
            reason="Cannot compare unit price without both PO and invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    po_price = {line.item_id: line.unit_price for line in tx.po.items}
    mismatch = None
    for line in tx.invoice.items:
        approved = po_price.get(line.item_id)
        if approved is None:
            continue  # item existence is handled by CHECK_ITEM
        if line.unit_price != approved:
            # An approved price change for this item resolves the mismatch.
            if s.has_approval(tx, "UNIT_PRICE_CHANGE", item_id=line.item_id):
                continue
            mismatch = (line.item_id, approved, line.unit_price)
            break

    if mismatch is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.PASS,
            policy_rule_id="P06",
            reason="Invoice unit prices match approved prices (or approved change exists)",
            evidence_refs=s.evidence_refs(tx),
        )

    item_id, approved, actual = mismatch
    return m.CheckResult(
        check_id=CHECK_ID,
        status=m.CheckStatus.FAIL,
        policy_rule_id="P06",
        expected=approved,
        actual=actual,
        reason=f"Item {item_id}: invoice unit price {actual} does not match approved {approved}",
        evidence_refs=s.evidence_refs(tx),
    )

"""Check 2 — Item match (P03): invoice items must belong to the PO."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_ITEM"


def check_item(tx: m.Transaction) -> m.CheckResult:
    if tx.po is None or tx.invoice is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P03",
            reason="Cannot compare items without both PO and invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    po_items = {line.item_id for line in tx.po.items}
    invoice_items = [line.item_id for line in tx.invoice.items]
    unknown_items = [i for i in invoice_items if i not in po_items]

    if not unknown_items:
        status, reason = m.CheckStatus.PASS, "All invoice items exist on the PO"
    elif s.has_approval(tx, "ITEM_CHANGE"):
        status, reason = m.CheckStatus.PASS, "Extra items covered by an approved item change"
    else:
        status = m.CheckStatus.FAIL
        reason = f"Invoice items not present on PO: {', '.join(unknown_items)}"

    return m.CheckResult(
        check_id=CHECK_ID,
        status=status,
        policy_rule_id="P03",
        expected=sorted(po_items),
        actual=invoice_items,
        reason=reason,
        evidence_refs=s.evidence_refs(tx),
    )

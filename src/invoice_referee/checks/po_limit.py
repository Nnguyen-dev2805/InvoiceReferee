"""Check 8 — Cumulative PO limit (P08): sum of invoices for a PO vs approved total."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_PO_LIMIT"


def check_po_limit(tx: m.Transaction) -> m.CheckResult:
    if tx.po is None or tx.invoice is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P08",
            reason="Cannot check cumulative PO limit without PO and invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    if tx.invoice.total_amount is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P08",
            reason="Current invoice amount is unreadable/unknown",
            evidence_refs=s.evidence_refs(tx),
        )

    cumulative = s.prior_invoice_total_for_po(tx) + tx.invoice.total_amount
    approved_ceiling = tx.po.approved_total + s.approved_amount_delta(tx)

    if cumulative <= approved_ceiling:
        status, reason = m.CheckStatus.PASS, "Cumulative invoice total does not exceed approved PO amount"
    else:
        status = m.CheckStatus.FAIL
        reason = f"Cumulative invoice total {cumulative} exceeds approved PO amount {approved_ceiling}"

    return m.CheckResult(
        check_id=CHECK_ID,
        status=status,
        policy_rule_id="P08",
        expected=approved_ceiling,
        actual=cumulative,
        reason=reason,
        evidence_refs=s.evidence_refs(tx),
    )

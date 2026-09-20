"""Check 5 — Amount check (P07): invoice total vs approved PO amount."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_AMOUNT"


def check_amount(tx: m.Transaction) -> m.CheckResult:
    if tx.po is None or tx.invoice is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P07",
            reason="Cannot check amount without both PO and invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    if tx.invoice.total_amount is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P07",
            reason="Invoice total amount is unreadable/unknown",
            evidence_refs=s.evidence_refs(tx),
        )

    if tx.po.approved_total is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P07",
            reason="Approved PO amount is unreadable/unknown",
            evidence_refs=s.evidence_refs(tx),
        )

    approved_ceiling = tx.po.approved_total + s.approved_amount_delta(tx)
    actual = tx.invoice.total_amount

    if actual <= approved_ceiling:
        status, reason = m.CheckStatus.PASS, "Invoice amount within approved PO amount"
    else:
        status = m.CheckStatus.FAIL
        reason = f"Invoice amount {actual} exceeds approved amount {approved_ceiling}"

    return m.CheckResult(
        check_id=CHECK_ID,
        status=status,
        policy_rule_id="P07",
        expected=approved_ceiling,
        actual=actual,
        reason=reason,
        evidence_refs=s.evidence_refs(tx),
    )

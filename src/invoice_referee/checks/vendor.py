"""Check 1 — Vendor match (P02)."""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_VENDOR"


def check_vendor(tx: m.Transaction) -> m.CheckResult:
    if tx.po is None or tx.invoice is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P02",
            reason="Cannot compare vendor without both PO and invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    if tx.po.vendor_id is None or tx.invoice.vendor_id is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P02",
            reason="Vendor identity is missing on the PO or invoice",
            evidence_refs=s.evidence_refs(tx),
        )

    expected = tx.po.vendor_id
    actual = tx.invoice.vendor_id
    if actual == expected:
        status, reason = m.CheckStatus.PASS, "Invoice vendor matches approved PO vendor"
    elif s.has_approval(tx, "VENDOR_CHANGE", approved_text_value=actual):
        status, reason = m.CheckStatus.PASS, "Vendor differs but an approved vendor change exists"
    else:
        status, reason = m.CheckStatus.FAIL, "Invoice vendor does not match PO vendor"

    return m.CheckResult(
        check_id=CHECK_ID,
        status=status,
        policy_rule_id="P02",
        expected=expected,
        actual=actual,
        reason=reason,
        evidence_refs=s.evidence_refs(tx),
    )

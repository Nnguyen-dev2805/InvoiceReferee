"""Check 7 — Payment status (P10/P11).

Routine progression is only allowed for a clearly UNPAID invoice. PAID and
PARTIALLY_PAID fail routine progression (P10); missing/unknown status is UNKNOWN
(P11) and must never be silently treated as UNPAID.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_PAYMENT"


def _record_for_invoice(tx: m.Transaction) -> Optional[m.PaymentRecord]:
    if tx.invoice is None:
        return tx.payment_history[0] if tx.payment_history else None
    for rec in tx.payment_history:
        if rec.invoice_id == tx.invoice.invoice_id:
            return rec
    return None


def check_payment(tx: m.Transaction) -> m.CheckResult:
    rec = _record_for_invoice(tx)

    if rec is None or rec.status is m.PaymentStatus.UNKNOWN:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P11",
            reason="Payment status is missing or undetermined",
            evidence_refs=s.evidence_refs(tx),
        )

    if rec.status is m.PaymentStatus.UNPAID:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.PASS,
            policy_rule_id="P10",
            expected="UNPAID",
            actual="UNPAID",
            reason="Invoice is unpaid and eligible for routine payment review",
            evidence_refs=s.evidence_refs(tx),
        )

    # PAID or PARTIALLY_PAID -> stop routine progression.
    return m.CheckResult(
        check_id=CHECK_ID,
        status=m.CheckStatus.FAIL,
        policy_rule_id="P10",
        expected="UNPAID",
        actual=rec.status.value,
        reason=f"Invoice payment status is {rec.status.value}; paid_amount={rec.paid_amount}",
        evidence_refs=s.evidence_refs(tx),
    )

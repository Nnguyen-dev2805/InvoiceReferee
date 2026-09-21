"""Check 6 — Duplicate invoice (P09).

Identity prefers vendor_tax_code + invoice_series + invoice_number, falling back
to vendor_id + invoice_number. An ADJUSTMENT/REPLACEMENT invoice that links to an
original is a historical relationship, not a duplicate.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s

CHECK_ID = "CHECK_DUPLICATE"


def _identity(inv: m.SupplierInvoice) -> Optional[tuple]:
    """The strong identity tuple, or ``None`` when it cannot be established.

    Duplicate identity prefers vendor_tax_code + invoice_series +
    invoice_number. A missing component is not a licence to fall back to a
    weaker key: amount and date alone never prove a duplicate, and a
    vendor_id + number guess would both miss real duplicates and invent false
    ones. An unprovable identity is UNKNOWN.
    """
    if inv.vendor_tax_code and inv.invoice_series and inv.invoice_number:
        return ("strong", inv.vendor_tax_code, inv.invoice_series, inv.invoice_number)
    return None


def check_duplicate(tx: m.Transaction) -> m.CheckResult:
    inv = tx.invoice
    if inv is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P09",
            reason="No invoice to check for duplicates",
            evidence_refs=s.evidence_refs(tx),
        )

    if inv.invoice_number is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P09",
            reason="Invoice number is missing; duplicate identity cannot be established",
            evidence_refs=s.evidence_refs(tx),
        )

    # Adjustment/replacement linked to an original is an intentional relationship.
    if inv.invoice_type in (m.InvoiceType.ADJUSTMENT, m.InvoiceType.REPLACEMENT) and inv.related_invoice_number:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.PASS,
            policy_rule_id="P09",
            reason=f"{inv.invoice_type.value} linked to original {inv.related_invoice_number}; not a duplicate",
            evidence_refs=s.evidence_refs(tx),
        )

    identity = _identity(inv)
    if identity is None:
        return m.CheckResult(
            check_id=CHECK_ID,
            status=m.CheckStatus.UNKNOWN,
            policy_rule_id="P09",
            reason=(
                "Invoice identity is incomplete (needs vendor tax code, series "
                "and number); a duplicate cannot be proven or ruled out"
            ),
            evidence_refs=s.evidence_refs(tx),
        )

    for prior in tx.prior_invoices:
        if _identity(prior) == identity:
            return m.CheckResult(
                check_id=CHECK_ID,
                status=m.CheckStatus.FAIL,
                policy_rule_id="P09",
                expected="unique invoice identity",
                actual=inv.invoice_number,
                reason="Invoice identity already exists in history",
                evidence_refs=s.evidence_refs(tx) + ([prior.invoice_id] if prior.invoice_id else []),
            )

    return m.CheckResult(
        check_id=CHECK_ID,
        status=m.CheckStatus.PASS,
        policy_rule_id="P09",
        reason="Invoice identity not seen in history",
        evidence_refs=s.evidence_refs(tx),
    )

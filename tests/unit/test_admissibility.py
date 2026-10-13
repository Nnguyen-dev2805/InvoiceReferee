"""Admissibility: which observations may become a Fact (contracts §2–§3).

Read states are observations, never Fact.KNOWN. A ref that exists does not by
itself prove payer/relation. An invoice/guest name does not prove who paid; a
payment proof does (§3).
"""

from __future__ import annotations

from invoice_referee.domain.evidence import EvidenceUnit, Observation
from invoice_referee.reconciliation.admissibility import confirm_admissibility
from tests.factories import ref, scope


def _obs(field: str, *, state: str, quote: str = "Tổng cộng 450.000") -> Observation:
    return Observation(
        field=field,
        raw=quote,
        normalized=450_000,
        read_state=state,  # type: ignore[arg-type]
        ref=ref("receipt-1", quote=quote),
    )


def _unit(role: str) -> EvidenceUnit:
    return EvidenceUnit(source="source:receipt-1", page_range=(1, 1), role=role)  # type: ignore[arg-type]


def test_unread_page_is_not_a_known_fact() -> None:
    fact = confirm_admissibility(_obs("amount", state="NOT_READ"), _unit("INVOICE"), scope())
    assert fact.state != "KNOWN"


def test_missing_and_error_are_not_known() -> None:
    for state in ("MISSING", "UNREADABLE", "ERROR"):
        fact = confirm_admissibility(_obs("amount", state=state), _unit("INVOICE"), scope())
        assert fact.state != "KNOWN"


def test_clear_invoice_amount_is_known() -> None:
    fact = confirm_admissibility(_obs("amount", state="CLEAR"), _unit("INVOICE"), scope())
    assert fact.state == "KNOWN"


def test_invoice_name_does_not_prove_payer() -> None:
    # A name/buyer on the invoice is not proof of who actually paid (§3).
    fact = confirm_admissibility(
        _obs("payer_identity", state="CLEAR"), _unit("INVOICE"), scope()
    )
    assert fact.state == "UNKNOWN"


def test_receipt_role_does_not_prove_payer() -> None:
    fact = confirm_admissibility(
        _obs("payer_identity", state="CLEAR"), _unit("RECEIVED"), scope()
    )
    assert fact.state == "UNKNOWN"


def test_payment_proof_supports_payer() -> None:
    # A payment proof that records the payer supports the employee-paid claim.
    fact = confirm_admissibility(
        _obs("payer_identity", state="CLEAR"), _unit("PAYMENT"), scope()
    )
    assert fact.state == "KNOWN"

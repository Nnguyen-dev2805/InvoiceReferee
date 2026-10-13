"""Admissibility predicates: may this observation become a Fact? (contracts §2–§3).

Deliberately a small predicate table for the §3 claims, not a generic
semantic-proof engine. A read state that is not CLEAR is never KNOWN; a field
is only KNOWN when the source's role actually supports that claim (an invoice
name does not prove who paid; a payment proof does).
"""

from __future__ import annotations

from invoice_referee.domain.case import CaseScope
from invoice_referee.domain.common import Fact
from invoice_referee.domain.evidence import EvidenceRole, EvidenceUnit, Observation

# Which source roles may support each claim field (§3 table).
_FIELD_ROLES: dict[str, frozenset[EvidenceRole]] = {
    # Incurred expense/T: a final expense document (invoice/request/receipt).
    "amount": frozenset({"INVOICE", "REQUEST", "PAYMENT", "RECEIVED"}),
    "incurred": frozenset({"INVOICE", "REQUEST", "PAYMENT", "RECEIVED"}),
    # Employee-paid/E candidate: a payment proof that records the payer.
    "payer_identity": frozenset({"PAYMENT"}),
    "payer": frozenset({"PAYMENT"}),
    # A/P/R/received: a completed transfer/receipt/ledger.
    "received": frozenset({"PAYMENT", "RECEIVED", "LEDGER"}),
}


def confirm_admissibility(
    observation: Observation, unit: EvidenceUnit, context: CaseScope
) -> Fact[int]:
    """Turn one observation into a Fact, or UNKNOWN when it is not admissible."""
    key = f"observation:{observation.field}"
    if observation.read_state != "CLEAR":
        # NOT_READ/MISSING/UNREADABLE/ERROR are never a KNOWN fact.
        return Fact[int](key=key, state="UNKNOWN", refs=(observation.ref,))
    supported = _FIELD_ROLES.get(observation.field)
    if supported is None or unit.role not in supported:
        return Fact[int](key=key, state="UNKNOWN", refs=(observation.ref,))
    if observation.normalized is None:
        return Fact[int](key=key, state="UNKNOWN", refs=(observation.ref,))
    return Fact[int](
        key=key,
        value=int(observation.normalized),
        state="KNOWN",
        refs=(observation.ref,),
    )

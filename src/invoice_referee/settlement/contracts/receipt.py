"""B5 advance-receipt READING contracts (b3-intake-v1).

The accountant uploads a receipt (bank transfer advice or cash voucher). The
reader extracts *facts* with real source/locator/quote provenance; a
deterministic Python step proposes a draft (matched employee, amount, method
details) and surfaces warnings. Nothing here creates a money event or decides
"received": the accountant reviews/edits and the existing ``record_receipt``
guard is the only place that classifies a real receipt.

Separation kept explicit:
- ``B3ReceiptFact`` = a raw read from the document (source + locator + quote).
- ``B3ReceiptProposal`` = deterministic suggestion (matched employee, scope).
- The accountant's confirmation reuses ``B3AdvanceEventPayload`` (unchanged).

No bank connection, no signature authentication, no money movement.
"""
from __future__ import annotations

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

from invoice_referee.settlement.contracts.advance import (
    B3EventMethod,
    B3FundingClassification,
    B3PayerSide,
)
from invoice_referee.settlement.contracts.run import ReadState

# Receipt-only key grammar. ``receipt.amount`` ends in ``.amount`` so the
# reader's existing money-key check applies (a non-integer read stays UNCLEAR,
# never a guessed conversion). Bank and cash fields are separate keys.
RECEIPT_SCALAR_KEYS = [
    "receipt.amount", "receipt.currency",
    "receipt.payer_name", "receipt.receiver_name",
    "receipt.event_at", "receipt.event_ref", "receipt.narrative",
    "receipt.outcome_text", "receipt.proof_scope",
    "receipt.bank_name", "receipt.sender_account",
    "receipt.recipient_bank", "receipt.recipient_account",
    "receipt.voucher_number", "receipt.handed_by_name",
    "receipt.acknowledgement",
]
RECEIPT_KEYS = RECEIPT_SCALAR_KEYS

ReceiptReadStatus = Literal["READ", "PARTIAL", "FAILED"]
ReceiptProofScope = Literal[
    "ORDER_ONLY", "SENDER_DEBIT", "RECEIVER_CONFIRMED", "UNCONFIRMED"]
ReceiptAcknowledgement = Literal["ACKNOWLEDGED", "NOT_HANDED", "UNCONFIRMED"]


class B3ReceiptFact(BaseModel):
    """One field read from the receipt with its real provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    raw: str | None = None
    value: StrictInt | str | None = None
    read_state: ReadState
    locator: str | None = None
    page: StrictInt | None = None
    quote: str | None = None


class B3ReceiptProposal(BaseModel):
    """Deterministic suggestions from the read facts — never a decision.

    ``payee_ref`` is the *proposed* employee match (or ``OTHER``/``None``); the
    raw name stays in ``receiver_name`` so the two are never conflated. A name
    that merely looks similar does not prove the same person.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    amount_vnd: StrictInt | None = None
    currency: str | None = None
    payer_side: B3PayerSide = "UNKNOWN"
    payee_ref: str | None = None
    receiver_name: str | None = None
    payer_name: str | None = None
    event_at: AwareDatetime | None = None
    event_ref: str | None = None
    narrative: str | None = None
    outcome_text: str | None = None
    method: B3EventMethod | None = None
    proof_scope: ReceiptProofScope | None = None
    acknowledgement: ReceiptAcknowledgement | None = None
    voucher_number: str | None = None
    handed_by_name: str | None = None
    bank_name: str | None = None
    sender_account: str | None = None
    recipient_bank: str | None = None
    recipient_account: str | None = None
    # Proposed classification from the read scope alone; the accountant's
    # confirmed event still goes through the backend guard.
    classification_hint: B3FundingClassification | None = None


class B3ReceiptWarning(BaseModel):
    """A review warning shown near the related field; never auto-resolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    field: str | None = None


class B3ReceiptReadView(BaseModel):
    """A stored receipt read (draft) the accountant reviews and edits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    source_id: str
    filename: str
    status: ReceiptReadStatus
    reader_mode: str
    created_at: AwareDatetime
    facts: list[B3ReceiptFact] = Field(default_factory=list)
    proposal: B3ReceiptProposal
    warnings: list[B3ReceiptWarning] = Field(default_factory=list)
    error: str | None = None
    idempotent_replay: bool = False

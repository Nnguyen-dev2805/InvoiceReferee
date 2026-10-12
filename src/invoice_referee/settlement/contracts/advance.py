"""Advance (B3) present/approve and B5 receipt contracts (b3-intake-v1)."""
from __future__ import annotations

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)



# --- B3 v1 present-and-approve contracts (b3-intake-v1) ----------------------
#
# A presentation records that an accountant routed a confirmed B3 basis to the
# configured approver; a B3 decision records the approver's APPROVE/RETURN/
# REFUSE. Approval is NOT receipt: no money event, handoff or closure is created
# here. These live in this module so ``CaseView`` can carry the projection
# without a models<->b3_workflow import cycle.

B3WorkflowStatus = Literal[
    "NOT_PRESENTED", "PENDING", "RETURNED", "REFUSED", "APPROVED",
    "NEEDS_RECHECK",
]
B3DecisionOutcome = Literal["APPROVE", "RETURN", "REFUSE"]
B3DecisionValidity = Literal["VALID", "RECHECK_REQUIRED"]


class B3PresentationView(BaseModel):
    """A persisted presentation: which basis an accountant routed to whom."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    basis_report_id: str
    review_id: str
    employee_ref: str
    work_ref: str
    accountant_ref: str
    approver_ref: str
    basis_input_revision: StrictInt
    basis_control_epoch: StrictInt
    basis_signature: str
    context_signature: str
    created_at: AwareDatetime
    idempotent_replay: bool = False


class B3DecisionPayload(BaseModel):
    """Approver's B3 outcome; three outcomes, one decision.

    APPROVE requires ``work_allowed=true`` and both money figures > 0; RETURN
    and REFUSE require all three approved fields to be ``None``. No extra
    conditions/actor/rights are accepted — authority comes from the backend
    company context, never from this payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentation_id: str
    outcome: B3DecisionOutcome
    reason: str
    work_allowed: StrictBool | None = None
    budget_vnd: StrictInt | None = None
    advance_vnd: StrictInt | None = None

    @model_validator(mode="after")
    def _outcome_shape(self) -> "B3DecisionPayload":
        if not self.reason.strip():
            raise ValueError("Lý do quyết định không được để trắng.")
        if self.outcome == "APPROVE":
            if self.work_allowed is not True:
                raise ValueError(
                    "APPROVE phải cho phép công việc (work_allowed=true).")
            if self.budget_vnd is None or self.budget_vnd <= 0:
                raise ValueError("APPROVE phải có budget_vnd > 0.")
            if self.advance_vnd is None or self.advance_vnd <= 0:
                raise ValueError("APPROVE phải có advance_vnd > 0.")
        else:
            if (self.work_allowed is not None or self.budget_vnd is not None
                    or self.advance_vnd is not None):
                raise ValueError(
                    "RETURN/REFUSE không được mang work_allowed/budget_vnd/"
                    "advance_vnd (để null).")
        return self


class B3DecisionView(BaseModel):
    """A recorded B3 advance decision bound to its presentation basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: Literal["B3_ADVANCE"]
    presentation_id: str
    outcome: B3DecisionOutcome
    reason: str
    work_allowed: StrictBool | None = None
    budget_vnd: StrictInt | None = None
    advance_vnd: StrictInt | None = None
    basis_report_id: str
    basis_review_id: str
    basis_input_revision: StrictInt
    basis_control_epoch: StrictInt
    basis_signature: str
    context_signature: str
    employee_ref: str
    work_ref: str
    actor_id: str
    grant_ref: str
    effective_at: AwareDatetime
    created_at: AwareDatetime
    idempotent_replay: bool = False


class B3WorkflowView(BaseModel):
    """Current B3 workflow projection derived from records + basis, not free text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: B3WorkflowStatus
    presentation: B3PresentationView | None = None
    decision: B3DecisionView | None = None
    basis_current: bool
    decision_validity: B3DecisionValidity | None = None
    blocked_reason: str | None = None
    accountant_ref: str | None = None
    approver_ref: str | None = None
    funding: "B3FundingSummary | None" = None
    advance_events: list["B3AdvanceEventView"] = Field(default_factory=list)


# --- B5: advance receipts (actual money to employee) -------------------------
#
# Approval is NOT receipt. These records are the accountant's bookkeeping of an
# actual money event with human-source-reviewed evidence — no bank transfer, no
# AI/bank verification. Reported status and derived classification stay
# separate; unknown is never a fabricated 0.

B3MoneyFieldName = Literal[
    "amount_vnd", "currency", "payer_side", "payee_ref", "event_at",
    "receiver_outcome", "event_namespace", "event_ref", "method",
    # Per-method receipt facts (D4): the human-readable receiver name is a
    # required read for a confirmed receipt; the rest are method-specific.
    "receiver_name", "proof_scope", "bank_status_text", "voucher_number",
    "handed_by_name", "acknowledgement",
]
B3ReadState = Literal["READ", "UNCLEAR", "NOT_FOUND"]
B3EventMethod = Literal["BANK_TRANSFER", "CASH"]
B3PayerSide = Literal["COMPANY", "EMPLOYEE", "OTHER", "UNKNOWN"]
B3AdvanceReportedStatus = Literal[
    "RECEIVED", "PENDING", "FAILED", "CANCELLED", "UNCONFIRMED",
]
B3FundingClassification = Literal[
    "CONFIRMED_RECEIPT", "PENDING", "NO_RECEIPT", "UNCONFIRMED", "CONFLICT",
]
B3FundingIncidentKind = Literal[
    "OVERPAY", "WRONG_RECIPIENT", "UNAUTHORIZED_OR_UNALLOCATED",
    "AMBIGUOUS_EVENT_REF", "CONFLICTING_OUTCOME",
]
B3FundingStatus = Literal[
    "NOT_RECORDED", "PARTIAL", "PENDING", "UNCONFIRMED", "FULFILLED",
    "NEEDS_RESOLUTION",
]


class B3MoneyFieldEvidence(BaseModel):
    """One field read from a retained source by a human accountant review.

    This is HUMAN_SOURCE_REVIEW: a person read the source and recorded the
    field's raw text and typed value with its locator. It is NOT OCR/LLM output
    and NOT bank/forensic authentication.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: B3MoneyFieldName
    source_id: str
    locator: str
    raw: str | None = None
    value: StrictInt | str | None = None
    read_state: B3ReadState
    origin: Literal["HUMAN_SOURCE_REVIEW"]


class B3BankReceiptDetails(BaseModel):
    """Bank-transfer receipt facts read by the accountant from the source.

    These are optional corroborating context (account/bank may be masked) and
    never substitute for the required receipt evidence. ``proof_scope`` records
    how far the source proves the money reached the receiver.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["BANK_TRANSFER"]
    receiver_name: str | None = None
    sender_name: str | None = None
    bank_name: str | None = None
    sender_account: str | None = None
    recipient_bank: str | None = None
    recipient_account: str | None = None
    bank_status_text: str | None = None
    proof_scope: Literal[
        "ORDER_ONLY", "SENDER_DEBIT", "RECEIVER_CONFIRMED", "UNCONFIRMED"]


class B3CashReceiptDetails(BaseModel):
    """Cash-voucher receipt facts read by the accountant from the source.

    A printed approval line or pre-printed name is not an acknowledgement;
    ``acknowledgement`` is the delivery/handover result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["CASH"]
    voucher_number: str | None = None
    cashbook_label: str | None = None
    handed_by_name: str | None = None
    receiver_name: str | None = None
    acknowledgement: Literal["ACKNOWLEDGED", "NOT_HANDED", "UNCONFIRMED"]


class B3AdvanceEventPayload(BaseModel):
    """Accountant's record of an actual advance money event (no bank action).

    ``gross_vnd`` is strict integer VND when known, else ``None`` (unknown is
    not 0). ``refs`` are derived from the evidence, never client-supplied.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: B3EventMethod
    gross_vnd: StrictInt | None = None
    payer_side: B3PayerSide
    payee_ref: str | None = None
    event_at: AwareDatetime | None = None
    reported_status: B3AdvanceReportedStatus
    evidence: list[B3MoneyFieldEvidence] = Field(default_factory=list)
    allocation_note: str
    supersedes_event_id: str | None = None
    receipt_details: "B3BankReceiptDetails | B3CashReceiptDetails | None" = None

    @model_validator(mode="after")
    def _shape(self) -> "B3AdvanceEventPayload":
        if not self.allocation_note.strip():
            raise ValueError("allocation_note không được để trắng.")
        if self.gross_vnd is not None and self.gross_vnd <= 0:
            raise ValueError("gross_vnd phải dương khi biết; unknown để null.")
        if self.receipt_details is not None \
                and self.receipt_details.kind != self.method:
            raise ValueError(
                "receipt_details.kind phải khớp method của sự kiện.")
        return self


class B3FundingIncident(BaseModel):
    """A kept funding discrepancy (never clipped or auto-recovered)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: B3FundingIncidentKind
    event_ids: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    amount_vnd: StrictInt | None = None
    reason: str


class B3AdvanceEventView(BaseModel):
    """A persisted advance money event with derived classification + incidents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: Literal["ADVANCE_TO_EMPLOYEE"]
    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: B3EventMethod
    gross_vnd: StrictInt | None = None
    payer_side: B3PayerSide
    payee_ref: str | None = None
    event_at: AwareDatetime | None = None
    reported_status: B3AdvanceReportedStatus
    evidence: list[B3MoneyFieldEvidence] = Field(default_factory=list)
    allocation_note: str
    supersedes_event_id: str | None = None
    employee_ref: str
    work_ref: str
    classification: B3FundingClassification
    actor_id: str
    created_at: AwareDatetime
    after_money_cutoff: bool = False
    incidents: list[B3FundingIncident] = Field(default_factory=list)
    receipt_details: "B3BankReceiptDetails | B3CashReceiptDetails | None" = None
    evidence_issues: list[str] = Field(default_factory=list)
    idempotent_replay: bool = False


class B3FundingSummary(BaseModel):
    """Advance funding projection scoped to a decision + managed events.

    Scope is this decision and the events this store manages — never a claim
    that whole-work A/coverage is complete. ``None`` totals mean unknown.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    approved_vnd: StrictInt | None = None
    recorded_received_vnd: StrictInt | None = None
    fulfilled_vnd: StrictInt | None = None
    remaining_vnd: StrictInt | None = None
    pending_count: int = 0
    unknown_count: int = 0
    incidents: list[B3FundingIncident] = Field(default_factory=list)
    status: B3FundingStatus
    scope: str
    as_of: AwareDatetime | None = None

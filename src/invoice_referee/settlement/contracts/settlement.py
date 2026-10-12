"""Linked settlement (B6->B7/B8/B9) and W05 decision contracts."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from invoice_referee.settlement.contracts.b3_contracts import B3Coverage
from invoice_referee.settlement.contracts.report import Issue, MoneyComponents
from invoice_referee.settlement.contracts.run import AuthorityGrant


# --- B6→B7 linked settlement (b7-linked-intake-v1) ---------------------------
#
# A linked child is a NEW B7 case that shares the parent B3's employee/work and
# carries an immutable origin link. Declarations (claim rows) are statements,
# never payment facts; forecast/approved-advance never become actual expense.
# This slice is report-only: no B8 decision, payment, handoff or closure.

B7LinkedSchema = "b7-linked-intake-v1"
B7DeclaredPayer = Literal["PERSONAL", "COMPANY", "UNKNOWN"]
B7ClaimStatus = Literal["MATCHED", "CONFLICT", "UNRESOLVED"]
B7CompanyEventKind = Literal[
    "ADVANCE_RECEIVED", "ADVANCE_RETURN", "REIMBURSEMENT_RECEIVED",
    "REIMBURSEMENT_RETURN", "COMPANY_DIRECT",
]
B7CompanyEventOutcome = Literal[
    "RECEIVED", "PENDING", "FAILED", "CANCELLED", "UNKNOWN",
]
B7ExpensePurpose = Literal["BUSINESS", "PERSONAL", "UNKNOWN"]


class B7OriginLink(BaseModel):
    """Immutable server-owned link from a B7 child back to its B3 parent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_case_id: str
    employee_ref: str
    work_ref: str
    created_at: AwareDatetime
    # B9: server-owned pointer to a closed settlement this child adjusts.
    adjustment_of_case_id: str | None = None


class B7ClaimRow(BaseModel):
    """One declared actual expense row; a statement, never a payment fact.

    ``claim_id`` is a claim-namespace id (never an invoice/payment id).
    Unknown amount stays ``None`` (never 0); declared payer is a declaration.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    description: str
    expense_date: date | None = None
    declared_amount_vnd: StrictInt | None = None
    purpose: str
    declared_payer: B7DeclaredPayer
    source_ids: list[str] = Field(default_factory=list)
    payment_statement: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> "B7ClaimRow":
        if not self.description.strip():
            raise ValueError("Mô tả khoản chi không được để trắng.")
        if self.declared_amount_vnd is not None and self.declared_amount_vnd < 0:
            raise ValueError("declared_amount_vnd không được âm; unknown để null.")
        return self


class B7LinkedIntake(BaseModel):
    """Employee declaration form for a linked B7 settlement (WEB)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["b7-linked-intake-v1"]
    confirmed: bool = False
    expense_rows: list[B7ClaimRow] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def _unique_claims(self) -> "B7LinkedIntake":
        ids = [row.claim_id for row in self.expense_rows]
        if len(ids) != len(set(ids)):
            raise ValueError("claim_id trùng trong khai báo.")
        if self.confirmed and not self.expense_rows:
            raise ValueError(
                "Xác nhận nộp cần ít nhất một khoản chi khai báo.")
        return self


class B7StandaloneIntake(BaseModel):
    """Employee declaration for a self-paid B7 settlement (no B3/advance).

    Carries only the business content the employee types: purpose and scope.
    Identity (employee/work/clock) and any authority are server-derived; no
    client-supplied employee/work/job/clock/parent/amount/authority fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: str
    scope: str

    @field_validator("purpose", "scope")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("purpose/scope không được rỗng.")
        return stripped


class LinkedB7View(BaseModel):
    """Projection of a linked B7 case's origin/context/limits for API/UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: B7OriginLink
    context_source_id: str | None = None
    context_current: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    managed_advance_subtotal_vnd: StrictInt | None = None


class B7CompanyConfig(BaseModel):
    """Backend-owned B7 settlement authority config (separate from B3Grant).

    B7 rights are distinct from the B3 advance grant: never inherit B3
    max_budget/max_advance, and never fall back to a broad demo grant when this
    config is absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["b7-company-config-v1"]
    version: str
    activated: bool
    synthetic: bool
    demo_clock: AwareDatetime | None = None
    grants: list[AuthorityGrant] = Field(default_factory=list)
    ref: str
    # Backend-owned company identity for collection receipts. When None, an
    # unknown payee is never normalized to "the company": a return can only be
    # classified as company-received when this ref is configured and matches.
    company_ref: str | None = None

    @model_validator(mode="after")
    def _clock_scope(self) -> "B7CompanyConfig":
        if self.demo_clock is not None and not (self.activated and self.synthetic):
            raise ValueError(
                "Clock cố định chỉ áp dụng cho B7 config synthetic đã activated; "
                "config thật dùng giờ máy.")
        return self


class B7CompanyEvent(BaseModel):
    """A company-side actual money event (semantic, not a status string)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_namespace: str
    event_ref: str
    kind: B7CompanyEventKind
    amount_vnd: StrictInt | None = None
    payer_ref: str | None = None
    payee_ref: str | None = None
    employee_ref: str | None = None
    work_ref: str | None = None
    outcome: B7CompanyEventOutcome
    event_at: AwareDatetime | None = None
    known_at: AwareDatetime | None = None
    refs: list[str] = Field(default_factory=list)


class B7CompanyExpense(BaseModel):
    """A company-side actual expense (not a money event; no forecast field)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expense_ref: str
    issuer_ref: str
    document_ref: str
    amount_vnd: StrictInt | None = None
    purpose: B7ExpensePurpose
    expense_date: date | None = None
    refs: list[str] = Field(default_factory=list)
    payment_event_refs: list[str] = Field(default_factory=list)


class B7CompanyPacket(BaseModel):
    """Source-backed company register for whole-work settlement checks.

    Provided by the accountant; the employee cannot edit it. Absence of a row
    is never silently zero — coverage groups/opening balances decide.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["b7-company-packet-v1"]
    coverage: "B3Coverage"  # noqa: F821 — imported from b3 at module load
    events: list[B7CompanyEvent] = Field(default_factory=list)
    expenses: list[B7CompanyExpense] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    reading_note: str

    @model_validator(mode="after")
    def _identity_unique(self) -> "B7CompanyPacket":
        keys = [(e.event_namespace, e.event_ref) for e in self.events]
        if len(keys) != len(set(keys)):
            raise ValueError("event namespace/ref trùng trong company packet.")
        return self


class LinkedB7ContextSnapshot(BaseModel):
    """Server-built linked context: imported facts, no final S/outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_case_id: str
    parent_fingerprint: str
    decision_ref: str | None = None
    managed_advance_refs: list[str] = Field(default_factory=list)
    company_packet_ref: str | None = None
    context_version: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    b7_authority_version: str | None = None
    history: dict[str, StrictInt | None] = Field(default_factory=dict)
    budget_vnd: StrictInt | None = None
    company_packet: "B7CompanyPacket | None" = None
    company_events: list[B7CompanyEvent] = Field(default_factory=list)
    company_expenses: list[B7CompanyExpense] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    money_as_of: AwareDatetime | None = None
    knowledge_cutoff: AwareDatetime | None = None


class B7ClaimComparison(BaseModel):
    """Comparison of one declared claim against its matched actual expense."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    expense_id: str | None = None
    declared_amount_vnd: StrictInt | None = None
    verified_amount_vnd: StrictInt | None = None
    payer_declaration: B7DeclaredPayer | None = None
    verified_payer: str | None = None
    status: B7ClaimStatus
    refs: list[str] = Field(default_factory=list)
    reason: str = ""


# --- B8: settlement decision (b7-linked-intake-v1) ---------------------------
#
# The accountant presents a current report; the approver APPROVES/RETURNS/
# REFUSES on the exact basis. The target (E/S/direction/amount) is server-derived
# and never client-supplied. Approval is NOT receipt.

B7WorkflowStatus = Literal[
    "NOT_PRESENTED", "PENDING", "RETURNED", "REFUSED", "APPROVED",
    "NEEDS_RECHECK",
]
B7DecisionOutcome = Literal["APPROVE", "RETURN", "REFUSE"]
B7DecisionDirection = Literal[
    "PAY_EMPLOYEE", "COLLECT_FROM_EMPLOYEE", "BALANCED",
]


class B7DecisionTarget(BaseModel):
    """Server-derived decision target: what APPROVE commits to (no client input).

    Lives in models so ``B7PresentationView``/``B7DecisionView`` resolve without
    a models<->b7_workflow import cycle; ``b7_workflow.settlement_target`` builds
    it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_cost_vnd: StrictInt
    total_work_cost_vnd: StrictInt
    budget_vnd: StrictInt
    signed_net_vnd: StrictInt
    direction: B7DecisionDirection
    amount_vnd: StrictInt


class B7PresentPayload(BaseModel):
    """Accountant presentation input: exactly one review source, nonblank note."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    basis_report_id: str
    review_id: str | None = None
    review: "ReviewPayload | None" = None
    supersedes_decision_id: str | None = None

    @model_validator(mode="after")
    def _exactly_one_review_source(self) -> "B7PresentPayload":
        if (self.review_id is None) == (self.review is None):
            raise ValueError(
                "Cần đúng một trong review_id (review đã lưu) hoặc review "
                "(note+refs mới), không cả hai hoặc không có.")
        if self.review is not None:
            if not self.review.note.strip():
                raise ValueError("Ghi chú rà soát không được để trắng.")
            if self.review.report_id != self.basis_report_id:
                raise ValueError(
                    "review.report_id phải bằng basis_report_id của presentation.")
        return self


class B7PresentationView(BaseModel):
    """A persisted settlement presentation: basis report/review/signatures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    employee_ref: str
    work_ref: str
    basis_report_id: str
    basis_review_id: str
    accountant_ref: str
    approver_ref: str
    basis_input_revision: StrictInt
    control_epoch: StrictInt
    business_signature: str
    parent_fingerprint: str
    config_signature: str
    target: "B7DecisionTarget"
    created_at: AwareDatetime
    idempotent_replay: bool = False


class B7DecisionPayload(BaseModel):
    """Approver's settlement outcome; no client amount/rights accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    presentation_id: str
    outcome: B7DecisionOutcome
    reason: str

    @model_validator(mode="after")
    def _reason_nonblank(self) -> "B7DecisionPayload":
        if not self.reason.strip():
            raise ValueError("Lý do quyết định không được để trắng.")
        return self


class B7DecisionView(BaseModel):
    """A recorded settlement decision bound to its presentation basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: Literal["B7_SETTLEMENT"]
    outcome: B7DecisionOutcome
    reason: str
    presentation_id: str
    basis_report_id: str
    basis_review_id: str
    employee_ref: str
    work_ref: str
    actor_id: str
    effective_at: AwareDatetime
    created_at: AwareDatetime
    basis_input_revision: StrictInt
    control_epoch: StrictInt
    business_signature: str
    parent_fingerprint: str
    config_signature: str
    authority_signature: str
    target: "B7DecisionTarget | None" = None
    history_baseline: "MoneyComponents | None" = None
    supersedes_decision_id: str | None = None
    idempotent_replay: bool = False


class B7WorkflowView(BaseModel):
    """Current settlement workflow projection from records + basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: B7WorkflowStatus
    presentation: B7PresentationView | None = None
    decision: B7DecisionView | None = None
    basis_current: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    accountant_ref: str | None = None
    approver_ref: str | None = None
    fulfillment: "B7FulfillmentSummary | None" = None
    revalidation: "B7RevalidationView | None" = None
    current_handoff: "B7HandoffView | None" = None
    closure: "B7ClosureView | None" = None


# --- B9: settlement fulfillment & closure (b7-linked-intake-v1) --------------
#
# Actual money (company pays the employee; the employee returns an advance or a
# reimbursement) is recorded by the accountant from a retained source and
# reconciled against the approved decision. Approval != receipt != closure.
# These are typed B7 events, distinct from the B5 advance and generic W05 money.

B7MoneyFieldName = Literal[
    "amount_vnd", "currency", "payer_ref", "payee_ref", "event_at",
    "receiver_outcome", "event_namespace", "event_ref", "method", "purpose",
    "work_ref",
]
B7ReadState = Literal["READ", "UNCERTAIN", "MISSING"]
B7EventMethod = Literal["BANK_TRANSFER", "CASH"]
B7ReportedStatus = Literal[
    "RECEIVED", "PENDING", "FAILED", "CANCELLED", "UNCONFIRMED",
]
B7MoneyPurpose = Literal[
    "REIMBURSEMENT_RECEIVED", "ADVANCE_RETURN", "REIMBURSEMENT_RETURN",
    "UNKNOWN",
]
B7MoneyClassification = Literal[
    "CONFIRMED_RECEIPT", "PENDING", "FAILED", "CANCELLED", "UNCONFIRMED",
    "INCIDENT",
]
B7MoneyIncidentKind = Literal[
    "WRONG_RECIPIENT", "WRONG_PAYER", "OVERPAY", "CONFLICTING_EVENT",
    "UNALLOCATED", "REVERSAL", "AFTER_CUTOFF", "SOURCE_UNRESOLVED",
]


class B7MoneyFieldEvidence(BaseModel):
    """One money field read from a retained source by a human accountant.

    HUMAN_SOURCE_REVIEW: a person read the source and recorded the raw text and
    typed value with its locator. Not OCR/LLM output and not bank
    authentication.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: B7MoneyFieldName
    source_id: str
    locator: str
    raw: str | None = None
    value: StrictInt | str | None = None
    read_state: B7ReadState
    origin: Literal["HUMAN_SOURCE_REVIEW"]


class B7MoneyEventPayload(BaseModel):
    """Accountant's record of an actual settlement money event (no bank action).

    ``gross_vnd`` is strict integer VND when known, else ``None`` (unknown is
    not 0). Employee/work/classification are server-derived, never client input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: B7EventMethod
    gross_vnd: StrictInt | None = None
    payer_ref: str | None = None
    payee_ref: str | None = None
    event_at: AwareDatetime | None = None
    reported_status: B7ReportedStatus
    purpose: B7MoneyPurpose
    evidence: list[B7MoneyFieldEvidence] = Field(default_factory=list)
    allocation_note: str
    supersedes_event_id: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> "B7MoneyEventPayload":
        if not self.allocation_note.strip():
            raise ValueError("allocation_note không được để trắng.")
        if self.gross_vnd is not None and self.gross_vnd <= 0:
            raise ValueError("gross_vnd phải dương khi biết; unknown để null.")
        return self


class B7MoneyIncident(BaseModel):
    """A kept money discrepancy (never clipped or auto-recovered)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: B7MoneyIncidentKind
    event_ids: list[str] = Field(default_factory=list)
    excess_vnd: StrictInt | None = None
    refs: list[str] = Field(default_factory=list)
    reason: str


class B7MoneyEventView(BaseModel):
    """A persisted settlement money event with derived classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: Literal["B7_SETTLEMENT_EVENT"]
    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: B7EventMethod
    gross_vnd: StrictInt | None = None
    payer_ref: str | None = None
    payee_ref: str | None = None
    event_at: AwareDatetime | None = None
    reported_status: B7ReportedStatus
    purpose: B7MoneyPurpose
    evidence: list[B7MoneyFieldEvidence] = Field(default_factory=list)
    allocation_note: str
    supersedes_event_id: str | None = None
    employee_ref: str
    work_ref: str
    actor_id: str
    created_at: AwareDatetime
    known_at: AwareDatetime | None = None
    classification: B7MoneyClassification
    after_cutoff: bool = False
    incidents: list[B7MoneyIncident] = Field(default_factory=list)
    idempotent_replay: bool = False


class B7FulfillmentReceipt(BaseModel):
    """Backend-only qualifying receipt projection for one decision.

    ``qualifying`` is derived from evidence/parties/purpose/work/baseline — never
    a request field. ``canonical_id`` is the validated economic identity/alias.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    canonical_id: str
    decision_id: str
    amount_vnd: StrictInt | None = None
    state: Literal["CONFIRMED", "PENDING", "UNKNOWN", "FAILED", "CANCELLED"]
    qualifying: bool
    after_cutoff: bool = False
    incidents: list[B7MoneyIncident] = Field(default_factory=list)


class B7FulfillmentSummary(BaseModel):
    """Decision-scoped fulfillment: approved vs confirmed receipts + remaining.

    Scope is this decision and the events the store manages — never a claim
    that whole-work A/coverage is complete. ``None`` totals mean unknown.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    direction: B7DecisionDirection
    approved_vnd: StrictInt
    recorded_received_vnd: StrictInt | None = None
    fulfilled_vnd: StrictInt | None = None
    remaining_vnd: StrictInt | None = None
    known_remaining_vnd: StrictInt | None = None
    pending_count: StrictInt = 0
    unknown_count: StrictInt = 0
    incidents: list[B7MoneyIncident] = Field(default_factory=list)
    status: Literal["WAITING", "PARTIAL", "FULFILLED", "BLOCKED", "BALANCED"]
    managed_scope: str
    as_of: AwareDatetime
    knowledge_cutoff: AwareDatetime


class B7RevalidationView(BaseModel):
    """Whether a correct fulfillment keeps the original decision valid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_decision_id: str
    current_report_id: str
    status: Literal["VALID", "NEEDS_RECHECK"]
    cost_signature: str
    receipt_history_signature: str
    qualifying_event_ids: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    created_at: AwareDatetime


class B7HandoffPayload(BaseModel):
    """Stage-A handoff request: which decision, and why."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    reason: str

    @model_validator(mode="after")
    def _reason_nonblank(self) -> "B7HandoffPayload":
        if not self.reason.strip():
            raise ValueError("Lý do bàn giao không được để trắng.")
        return self


class B7HandoffView(BaseModel):
    """An audit-backed handoff reference for the remaining obligation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    decision_id: str
    report_id: str
    employee_ref: str
    work_ref: str
    actor_id: str
    direction: str
    remaining_vnd: StrictInt
    obligation_signature: str
    business_signature: str
    receipt_history_signature: str
    refs: list[str] = Field(default_factory=list)
    created_at: AwareDatetime
    valid_until: AwareDatetime | None = None
    idempotent_replay: bool = False


class B7ClosurePayload(BaseModel):
    """Accountant's closure request; gates are checked before acceptance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    current_report_id: str
    reason: str

    @model_validator(mode="after")
    def _reason_nonblank(self) -> "B7ClosurePayload":
        if not self.reason.strip():
            raise ValueError("Lý do đóng không được để trắng.")
        return self


class B7ClosureView(BaseModel):
    """An immutable closure snapshot for a linked settlement child."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    decision_id: str
    current_report_id: str
    actor_id: str
    kind: Literal["SETTLEMENT_COMPLETE"]
    employee_ref: str
    work_ref: str
    close_as_of: AwareDatetime
    knowledge_cutoff: AwareDatetime
    created_at: AwareDatetime
    input_revision: StrictInt
    control_epoch: StrictInt
    business_signature: str
    receipt_history_signature: str
    parent_fingerprint: str
    source_refs: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    original_decision_id: str
    revalidation_ref: str | None = None
    reason: str
    idempotent_replay: bool = False


class B7AdjustmentPayload(BaseModel):
    """Request to open a post-closure adjustment child (reason only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str

    @model_validator(mode="after")
    def _reason_nonblank(self) -> "B7AdjustmentPayload":
        if not self.reason.strip():
            raise ValueError("Lý do điều chỉnh không được để trắng.")
        return self


# --- W05: decision, review, money, handoff, closure contracts (S6) -----------

DecisionKind = Literal["SETTLEMENT"]
DecisionDirection = Literal["PAY_EMPLOYEE", "COLLECT_FROM_EMPLOYEE", "REFUSE"]
MoneyEventKind = Literal["PAYMENT_TO_EMPLOYEE", "PAYMENT_FROM_EMPLOYEE"]
ReportedStatus = Literal["RECEIVED", "PENDING"]
ControlAction = Literal["STOP", "RESUME"]
ClosureKind = Literal["SETTLEMENT_COMPLETE", "REJECTED_REQUEST_ENDED"]


class DecisionPayload(BaseModel):
    """Approval/refusal input; amount never overrides the report's arithmetic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: DecisionKind
    amount_vnd: StrictInt | None = None
    direction: DecisionDirection
    reason: str
    basis_report_id: str
    conditions: list[str] = Field(default_factory=list)
    exception_of: str | None = None


class ReviewPayload(BaseModel):
    """Accountant review note: an observation, never an approval.

    Carrying an amount is rejected with REVIEW_NOT_APPROVAL — review cannot
    smuggle a money decision through the review path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    note: str
    refs: list[str] = Field(default_factory=list)


class B3PresentPayload(BaseModel):
    """Accountant presentation input: a saved review or a new note+refs.

    Exactly one of ``review_id`` (reuse a stored review) or ``review`` (a new
    note/refs to store) must be given. A new review's ``report_id`` must equal
    ``basis_report_id`` and its note must not be blank.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    basis_report_id: str
    review_id: str | None = None
    review: ReviewPayload | None = None

    @model_validator(mode="after")
    def _exactly_one_review_source(self) -> "B3PresentPayload":
        if (self.review_id is None) == (self.review is None):
            raise ValueError(
                "Cần đúng một trong review_id (review đã lưu) hoặc review "
                "(note+refs mới), không cả hai hoặc không có.")
        if self.review is not None:
            if not self.review.note.strip():
                raise ValueError("Ghi chú rà soát không được để trắng.")
            if self.review.report_id != self.basis_report_id:
                raise ValueError(
                    "review.report_id phải bằng basis_report_id của presentation.")
        return self


class MoneyEventPayload(BaseModel):
    """An actual money event as reported; gross truth, never clipped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_ref: str
    kind: MoneyEventKind
    gross_vnd: StrictInt
    decision_id: str | None = None
    payee_ref: str
    event_at: AwareDatetime
    reported_status: ReportedStatus
    refs: list[str] = Field(default_factory=list)


class HandoffPayload(BaseModel):
    """Stage-A handoff reference: which approved decision the cashier gets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str


class ClosurePayload(BaseModel):
    """Closure declaration; gates are checked before it is accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ClosureKind
    basis: str


class DecisionView(BaseModel):
    """A recorded human decision with its typed, immutable basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: DecisionKind
    amount_vnd: StrictInt | None = None
    direction: DecisionDirection
    reason: str
    basis_report_id: str
    basis_case_version: StrictInt
    basis_input_revision: StrictInt
    exception_of: str | None = None
    conditions: list[str] = Field(default_factory=list)
    actor_id: str
    created_at: AwareDatetime
    idempotent_replay: bool = False


class ReviewView(BaseModel):
    """A recorded accountant review; it does not create approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    report_id: str
    note: str
    refs: list[str] = Field(default_factory=list)
    actor_id: str
    created_at: AwareDatetime
    idempotent_replay: bool = False


class MoneyEventView(BaseModel):
    """A persisted money event with its cutoff flag kept visible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    event_ref: str
    kind: MoneyEventKind
    gross_vnd: StrictInt
    decision_id: str | None = None
    payee_ref: str
    event_at: AwareDatetime
    reported_status: ReportedStatus
    refs: list[str] = Field(default_factory=list)
    after_cutoff: bool
    created_at: AwareDatetime
    idempotent_replay: bool = False


class ClosureView(BaseModel):
    """A recorded closure: settlement-complete and request-rejected are distinct."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: ClosureKind
    basis: str
    actor_id: str
    created_at: AwareDatetime
    idempotent_replay: bool = False

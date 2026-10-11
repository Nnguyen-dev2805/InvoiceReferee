"""Settlement MVP contracts (W01): strict Pydantic records for intake.

Records follow the frozen-contract style of ``domain.models``: no extra
fields, immutable, ``None`` means unknown (never a sentinel ``0``). The plan
allows extending record fields as later tasks genuinely need them.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from time import monotonic as _monotonic
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3CompanyContext, B3Coverage, B3Proposal

Job = Literal["B3", "B7"]
DemoRole = Literal["EMPLOYEE", "ACCOUNTANT", "APPROVER"]
# Who created a case: a person via the UI/API, or the system (eval/verify/seed).
CaseOrigin = Literal["USER", "SYSTEM"]
CaseStage = Literal[
    "CHECKING",
    "ACCOUNTING_REVIEW",
    "AWAITING_DECISION",
    "AWAITING_MONEY",
    "AWAITING_WORK_SETTLEMENT",
    "RESOLVING_OBLIGATIONS",
    "ADVANCE_REQUEST_REFUSED",
    "SETTLEMENT_REQUEST_REFUSED",
    "READY_TO_CLOSE",
    "REJECTED_REQUEST_ENDED",
    "SETTLEMENT_CLOSED",
]

# Resource envelope v0 (System §S8, pilot config; not verified capacity).
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_ACTIVE_SOURCES_PER_CASE = 20


class Submission(BaseModel):
    """Employee declaration for a job; unknown fields stay ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_ref: str
    work_ref: str
    job: Job
    money_as_of: AwareDatetime
    knowledge_cutoff: AwareDatetime
    form: dict[str, Any] = Field(default_factory=dict)


class Command(BaseModel):
    """A mutation request: idempotent by ``key`` within (operation, actor, scope)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt | None = None
    body: dict[str, Any] = Field(default_factory=dict)


class Upload(BaseModel):
    """Raw source bytes plus declared provenance, before validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str
    content: bytes
    provenance: dict[str, Any] = Field(default_factory=dict)


class SourceRecord(BaseModel):
    """A stored source original: backend-owned ID, hash and provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    filename: str
    media_type: str
    sha256: str
    size_bytes: StrictInt
    status: Literal["ACCEPTED"]
    uploader_actor_id: str
    received_at: AwareDatetime
    supersedes_source_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    original_path: Path
    idempotent_replay: bool = False


class SourceView(BaseModel):
    """Source metadata safe to expose over the API (no server paths)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    filename: str
    media_type: str
    sha256: str
    size_bytes: StrictInt
    status: Literal["ACCEPTED"]
    uploader_actor_id: str
    received_at: AwareDatetime
    supersedes_source_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class AllowedAction(BaseModel):
    """One action the current actor may perform, with the reason it is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    reason: str


class MoneyIncident(BaseModel):
    """A kept money discrepancy (never clipped or rewritten to fit approval)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["OVERPAY", "WRONG_RECIPIENT"]
    excess_vnd: StrictInt | None = None
    event_ref: str | None = None
    payee_ref: str | None = None


class MoneySummary(BaseModel):
    """Approved vs actually received: approval is not receipt (R9).

    ``None`` means unknown/not-yet, never a hidden ``0``. ``remaining_vnd``
    floors at 0 only when the excess is preserved as an OVERPAY incident.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    approved_vnd: StrictInt | None = None
    received_vnd: StrictInt | None = None
    remaining_vnd: StrictInt | None = None
    pending_events: StrictInt = 0
    incidents: list[MoneyIncident] = Field(default_factory=list)


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

    @model_validator(mode="after")
    def _shape(self) -> "B3AdvanceEventPayload":
        if not self.allocation_note.strip():
            raise ValueError("allocation_note không được để trắng.")
        if self.gross_vnd is not None and self.gross_vnd <= 0:
            raise ValueError("gross_vnd phải dương khi biết; unknown để null.")
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


class CaseView(BaseModel):
    """Projection of a case for API/UI: versions, stage, sources, actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    job: Job
    case_version: StrictInt
    input_revision: StrictInt
    control_epoch: StrictInt
    stop_active: bool
    stage: CaseStage
    current_run_id: str | None = None
    submission: Submission
    sources: list[SourceView] = Field(default_factory=list)
    allowed_actions: list[AllowedAction] = Field(default_factory=list)
    money_summary: dict[str, Any] = Field(default_factory=dict)
    origin: CaseOrigin = "USER"
    b3_workflow: B3WorkflowView | None = None
    linked_b7: LinkedB7View | None = None
    b7_workflow: B7WorkflowView | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    idempotent_replay: bool = False


class CaseSummary(BaseModel):
    """Listing row for GET /api/cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    job: Job
    employee_ref: str
    work_ref: str
    stage: CaseStage
    case_version: StrictInt
    updated_at: AwareDatetime
    origin: CaseOrigin = "USER"


class AuditEntry(BaseModel):
    """One accepted (or replayed) command in the case history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    kind: str
    operation: str
    actor_id: str
    command_key: str
    occurred_at: AwareDatetime
    detail: dict[str, Any] = Field(default_factory=dict)


class ResponsePayload(BaseModel):
    """A human answer to a question; refs point at uploaded sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    source_ids: list[str] = Field(default_factory=list)


class QuestionView(BaseModel):
    """An unresolved report issue surfaced to its owner with refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    issue_id: str
    owner: IssueOwner
    message: str
    refs: list[str] = Field(default_factory=list)
    blocked: str | None = None
    status: Literal["OPEN", "ANSWERED", "RESOLVED", "SUPERSEDED"]
    created_at: AwareDatetime
    origin_run_id: str | None = None
    answered_at: AwareDatetime | None = None
    resolved_run_id: str | None = None


class ResponseView(BaseModel):
    """A recorded response; accepted=False keeps the question open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question_id: str
    case_id: str
    actor_id: str
    demo_role: DemoRole
    content: str
    source_ids: list[str] = Field(default_factory=list)
    accepted: bool
    reason: str
    created_at: AwareDatetime
    idempotent_replay: bool = False


class CaseSnapshot(BaseModel):
    """Immutable input snapshot for a run (consumed by W02+)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    case_version: StrictInt
    input_revision: StrictInt
    control_epoch: StrictInt
    stop_active: bool
    stage: CaseStage
    submission: Submission
    sources: list[SourceRecord] = Field(default_factory=list)


def canonical_json(value: Any) -> str:
    """Stable JSON text: sorted keys, no padding — the fingerprint basis."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def fingerprint(operation: str, payload: dict[str, Any]) -> str:
    """SHA256 over the semantic payload of a command (key/version excluded)."""
    basis = canonical_json({"operation": operation, "payload": payload})
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# --- Reading and linking contracts (System §S2) -----------------------------

ReadState = Literal["READ", "NOT_FOUND", "UNCLEAR"]
Usability = Literal["USABLE", "UNCERTAIN", "UNUSABLE"]
RelationKind = Literal["EXPENSE_PAYMENT", "SAME_EVENT", "CLAIM_EXPENSE"]
RelationStatus = Literal["ESTABLISHED", "PROPOSED", "UNCLEAR"]
RunStatus = Literal[
    "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT",
    "STOPPED", "SUPERSEDED", "INTERRUPTED",
]


class Observation(BaseModel):
    """One normalized field read from a source, with its locator and basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    key: str
    raw: str | None = None
    read_state: ReadState
    value: StrictInt | str | dict[str, Any] | None = None
    source_id: str
    page: StrictInt | None = None
    row: StrictInt | None = None
    locator: str | None = None
    basis: str | None = None
    usability: Usability = "USABLE"


class Relation(BaseModel):
    """A proposed/established link between facts (expense↔payment, dedup)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str
    kind: RelationKind
    from_id: str
    to_id: str
    portion_vnd: StrictInt | None = None
    supporting_refs: list[str] = Field(default_factory=list)
    status: RelationStatus
    reason: str = ""


class AuthorityGrant(BaseModel):
    """Demo authority grant: an actor may decide up to limits, per work.

    ``max_settlement_vnd`` bounds the settlement amount (net paid/collected);
    the v2 fields bound the employee cost and an optional work-cost exception.
    A missing limit is NOT unlimited: a grant that does not cover a needed
    limit simply does not cover that content (Rulebook R8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_ref: str
    work_ref: str | None = None
    max_settlement_vnd: StrictInt
    employee_ref: str | None = None
    max_employee_cost_vnd: StrictInt | None = None
    max_exception_work_cost_vnd: StrictInt | None = None
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None


class RunInput(BaseModel):
    """Immutable snapshot a run evaluates; persisted with the run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    case_version: StrictInt
    input_revision: StrictInt
    control_epoch: StrictInt
    submission: Submission
    sources: list[SourceRecord] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    authority: list[AuthorityGrant] = Field(default_factory=list)
    response_refs: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    b3_context: B3CompanyContext | None = None
    snapshot_hash: str


class RunBudget(BaseModel):
    """Per-run resource envelope: wall-clock deadline and provider calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deadline: float
    max_calls: StrictInt
    calls: StrictInt = 0

    def reserve_call(self) -> None:
        if self.calls >= self.max_calls:
            raise DomainError(
                "BUDGET_EXHAUSTED",
                "Hết số lượt gọi cho phép của run; giữ partial output và lý do.",
            )
        if _monotonic() > self.deadline:
            raise DomainError(
                "BUDGET_EXHAUSTED",
                "Run vượt deadline; không fake kết quả sau mốc.",
            )
        object.__setattr__(self, "calls", self.calls + 1)


# --- Report contracts (System §S3) -------------------------------------------

class MoneyComponents(BaseModel):
    """Arithmetic components: None means unknown, never 0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    e: StrictInt | None
    a: StrictInt | None
    ra: StrictInt | None
    p: StrictInt | None
    rp: StrictInt | None


class ComponentSlot(BaseModel):
    """One money component with its value-or-null, state and source refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: StrictInt | None
    state: Literal["KNOWN", "UNKNOWN", "PENDING", "NOT_APPLICABLE"]
    refs: list[str] = Field(default_factory=list)


class ReportComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    t: ComponentSlot
    b: ComponentSlot
    e: ComponentSlot
    a: ComponentSlot
    ra: ComponentSlot
    p: ComponentSlot
    rp: ComponentSlot


class ExpenseRow(BaseModel):
    """One claimed expense with eligibility split and refs to open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expense_id: str
    claimed_amount_vnd: StrictInt | None
    eligible_employee_vnd: StrictInt | None = None
    company_direct_vnd: StrictInt | None = None
    state: Literal[
        "ELIGIBLE", "PERSONAL_EXCLUDED", "COMPANY_DIRECT", "UNKNOWN", "EXCLUDED"
    ]
    refs: list[str] = Field(default_factory=list)
    reason: str = ""


CheckStatus = Literal["PASS", "FAIL", "UNRESOLVED", "NOT_APPLICABLE"]


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    status: CheckStatus
    refs: list[str] = Field(default_factory=list)
    reason: str = ""


IssueType = Literal[
    "FACT", "POLICY", "AUTHORITY", "MONEY_INCIDENT", "TECHNICAL", "CONTROL"
]
IssueOwner = Literal["EMPLOYEE", "ACCOUNTANT", "APPROVER"]


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_id: str
    type: IssueType
    owner: IssueOwner
    message: str
    refs: list[str] = Field(default_factory=list)
    blocked: str | None = None
    unresolved: bool = True


class CriticalFact(BaseModel):
    """One consumed fact key with its resolved value and quality state.

    ``CONTRADICTED`` keeps ``None`` (no silent pick), ``UNUSABLE`` is a READ
    fact the quality gate refuses, ``UNCLEAR`` an unreadable extraction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: StrictInt | str | None = None
    state: Literal["KNOWN", "UNKNOWN", "CONTRADICTED", "UNCLEAR", "UNUSABLE"]
    refs: list[str] = Field(default_factory=list)


class ReportLink(BaseModel):
    """One reconciliation relation exposed with its establishment status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str
    kind: RelationKind
    from_id: str
    to_id: str
    portion_vnd: StrictInt | None = None
    status: RelationStatus


class ConditionalResult(BaseModel):
    """A policy scenario from verified facts, not an approved amount."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: str
    net_vnd: StrictInt | None
    components: MoneyComponents


class Report(BaseModel):
    """Sourced check report; proposed≠approved≠actual (those come later)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    job: Job
    completion: Literal["COMPLETE", "INCOMPLETE"]
    mode: str
    generated_at: AwareDatetime
    components: ReportComponents
    calculated_net_vnd: StrictInt | None
    proposed_net_vnd: StrictInt | None
    direction: Literal["COMPANY_TO_EMPLOYEE", "EMPLOYEE_TO_COMPANY",
                       "BALANCED"] | None = None
    conditional_results: list[ConditionalResult] = Field(default_factory=list)
    expense_rows: list[ExpenseRow] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    critical_facts: list[CriticalFact] = Field(default_factory=list)
    links: list[ReportLink] = Field(default_factory=list)
    b3: B3Proposal | None = None
    claim_comparisons: list[B7ClaimComparison] = Field(default_factory=list)
    next_step: str = ""
    source_refs: list[str] = Field(default_factory=list)


class CallTrace(BaseModel):
    """One provider call (or direct parse note) with identity and usage.

    ``usage`` is None when the API returns no usage — never a fabricated 0.
    Real APIs nest detail objects (``prompt_tokens_details`` /
    ``completion_tokens_details``), so a value is an int or one level of
    int/null pairs. Non-numeric leaves are dropped, never fatal: usage is
    diagnostics and must not fail a run.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    stage: Literal["read", "ocr", "extract", "match"]
    source_id: str | None = None
    requested_model: str | None = None
    response_model: str | None = None
    usage: dict[str, int | dict[str, int | None] | None] | None = None
    ok: bool
    error_code: str | None = None
    detail: str | None = None
    duration_ms: StrictInt = 0

    @field_validator("usage", mode="before")
    @classmethod
    def _coerce_usage(cls, value: object) -> object:
        """Normalize raw provider usage into int / one-level-int-dict values.

        Keeps known numeric leaves, keeps one level of nested numeric detail,
        and drops anything else (strings, bools, deeper nesting) so a stray
        provider field can never raise and fail the run.
        """
        if not isinstance(value, dict):
            return None

        def leaf(item: object) -> int | None:
            return item if isinstance(item, int) and not isinstance(item, bool) \
                else None

        cleaned: dict[str, int | dict[str, int | None] | None] = {}
        for key, item in value.items():
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                cleaned[key] = item
            elif isinstance(item, dict):
                cleaned[key] = {str(k): leaf(v) for k, v in item.items()}
        return cleaned


class RunView(BaseModel):
    """Projection of a run for API/UI: status first, report by its own route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    case_id: str
    status: RunStatus
    mode: str
    input_revision: StrictInt
    control_epoch: StrictInt
    stage: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    detail: str | None = None
    completion: Literal["COMPLETE", "INCOMPLETE"] | None = None
    trace: list[CallTrace] = Field(default_factory=list)
    idempotent_replay: bool = False


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


# Resolve forward references declared above (ReviewPayload, B7DecisionTarget,
# MoneyComponents are defined later in this module).
for _model in (B7PresentPayload, B7PresentationView, B7DecisionView,
               B7WorkflowView):
    _model.model_rebuild()

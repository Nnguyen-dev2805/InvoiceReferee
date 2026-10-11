"""Settlement MVP contracts (W01): strict Pydantic records for intake.

Records follow the frozen-contract style of ``domain.models``: no extra
fields, immutable, ``None`` means unknown (never a sentinel ``0``). The plan
allows extending record fields as later tasks genuinely need them.
"""
from __future__ import annotations

import hashlib
import json
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
from invoice_referee.settlement.b3 import B3CompanyContext, B3Proposal

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
RelationKind = Literal["EXPENSE_PAYMENT", "SAME_EVENT"]
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

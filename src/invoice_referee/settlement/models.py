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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from invoice_referee.domain.models import DomainError

Job = Literal["B3", "B7"]
DemoRole = Literal["EMPLOYEE", "ACCOUNTANT", "APPROVER"]
CaseStage = Literal[
    "CHECKING",
    "ACCOUNTING_REVIEW",
    "AWAITING_DECISION",
    "AWAITING_MONEY",
    "AWAITING_WORK_SETTLEMENT",
    "RESOLVING_OBLIGATIONS",
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
    """Demo authority grant: an actor may approve up to an amount, per work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_ref: str
    work_ref: str | None = None
    max_settlement_vnd: StrictInt


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
    next_step: str = ""
    source_refs: list[str] = Field(default_factory=list)


class CallTrace(BaseModel):
    """One provider call (or direct parse note) with identity and usage.

    ``usage`` is None when the API returns no usage — never a fabricated 0.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    stage: Literal["read", "ocr", "extract", "match"]
    source_id: str | None = None
    requested_model: str | None = None
    response_model: str | None = None
    usage: dict[str, int | None] | None = None
    ok: bool
    error_code: str | None = None
    detail: str | None = None
    duration_ms: StrictInt = 0


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

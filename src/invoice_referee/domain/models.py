"""T01 domain contracts — frozen Pydantic v2 records, enums and errors.

This module is the shared contract ledger locked at T01 (master plan §3.1).
Downstream tasks must not rename these records/enums. Design rules:

- All records forbid extra fields and are immutable (``ConfigDict(extra='forbid',
  frozen=True)``).
- Claim/payment amounts are strict positive integer VND (``StrictInt`` rejects
  bool); document numerics are carried as canonical strings, never floats.
- Optional means ``None``, never a sentinel ``0``.
- IDs are opaque strings; datetimes are UTC-aware (``AwareDatetime``).
- Default collections use factories.
"""
from __future__ import annotations

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictInt,
    model_validator,
)

# --- Enum-like Literal aliases (values fixed by System §3/§5–§8) ----------------

Profile = Literal['TRAVEL', 'CLIENT_MEAL', 'WORK_PURCHASE', 'OTHER']
PurposeType = Literal['BUSINESS', 'PERSONAL', 'UNKNOWN']
PayerType = Literal['PERSONAL', 'COMPANY', 'ADVANCE', 'VENDOR', 'UNKNOWN']
DemoMode = Literal['EMPLOYEE', 'REVIEWER', 'APPROVER', 'POLICY_OWNER']
PolicyActor = Literal['POLICY_OWNER', 'SYSTEM']

EvidenceRole = Literal['PRIMARY_BILL', 'GOODS_RECEIPT', 'CONTEXT']
Reading = Literal['READABLE', 'UNREADABLE', 'UNKNOWN']
SourceKind = Literal['DOCUMENT', 'EMPLOYEE_DECLARATION', 'HUMAN_CONFIRMATION']
Usability = Literal['USABLE', 'MISSING', 'UNCERTAIN', 'UNUSABLE', 'NOT_APPLICABLE']
DocumentKind = Literal['BILL', 'GOODS_RECEIPT', 'CREDIT_NOTE', 'UNKNOWN']
DocumentTemplate = Literal[
    'TOTAL_ONLY', 'SIMPLE_ITEMIZED', 'ITEMIZED_WITH_ADJUSTMENTS', 'UNKNOWN'
]
CheckStatus = Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE']
IssueClass = Literal['FACTUAL_UNKNOWN', 'OUTSIDE_POLICY', 'BEYOND_AUTHORITY']
IssueStatus = Literal['OPEN', 'RESOLVED', 'DENIED']
AuthorizationKind = Literal['POLICY_EXCEPTION', 'AMOUNT_APPROVAL']
DecisionAction = Literal[
    'CREATE_PAYMENT_REQUEST', 'REQUEST_INFO', 'ESCALATE', 'REJECT', 'NONE'
]
CompletionBasis = Literal['ROUTINE_AUTO', 'HUMAN_AUTHORIZED']
ExecutionStatus = Literal[
    'QUEUED', 'RUNNING', 'STOP_REQUESTED', 'STOPPED', 'SUCCEEDED', 'FAILED'
]
WorkflowState = Literal[
    'DRAFT', 'REVIEWING', 'WAITING_INPUT', 'WAITING_APPROVAL',
    'REQUEST_CREATED', 'REJECTED', 'STOPPED', 'TECHNICAL_ERROR',
]
HumanActionKind = Literal[
    'SUPPLY_DECLARATION', 'ADD_EVIDENCE', 'PROPOSE_CORRECTION', 'CONFIRM_FIELD',
    'CONFIRM_MAPPING', 'GRANT_POLICY_EXCEPTION', 'APPROVE_AMOUNT', 'DENY',
    'STOP', 'OVERRIDE',
]
PaymentRequestStatus = Literal['CREATED', 'SUPERSEDED', 'REVOKED']
StopStatus = Literal['STOP_REQUESTED', 'STOPPED', 'ALREADY_COMPLETED']


class Record(BaseModel):
    """Strict, immutable base for every domain record."""

    model_config = ConfigDict(extra='forbid', frozen=True)


# --- Claim and policy ----------------------------------------------------------

class Claim(Record):
    employee_id: str
    profile: Profile
    purpose_type: PurposeType
    purpose: str
    trip: str
    attendees: list[str] = Field(default_factory=list)
    requested_amount_vnd: StrictInt | None = Field(
        default=None, gt=0, le=999_999_999_999_999
    )
    payer_type: PayerType
    received_full: bool | None = None


class PolicyConfig(Record):
    version: str
    origin: str
    activation_id: str | None = None
    active: bool
    currency: str
    auto_approval_max: int = Field(ge=0)
    standard_policy_max: int = Field(ge=0)
    inventory_date_gap_days: int = Field(ge=0)
    comparison_money_tolerance: str
    normalized_unit_price_tolerance: str
    word_review_threshold: str
    threshold_version: str


# --- Evidence ------------------------------------------------------------------

class Evidence(Record):
    id: str
    case_id: str
    role: EvidenceRole
    original_name: str
    stored_path: str
    sha256: str
    mime: str
    size: int = Field(ge=0)


# --- Source registry -----------------------------------------------------------

class SourceRef(Record):
    evidence_id: str
    page_index: int = Field(ge=0)
    block_id: str
    locator: str
    raw_value: str


class SourceWord(Record):
    id: str
    text: str
    score: str | None = None


class SourceBlock(Record):
    evidence_id: str
    page_index: int = Field(ge=0)
    block_id: str
    text: str
    words: list[SourceWord] = Field(default_factory=list)
    locators: dict[str, list[str]] = Field(default_factory=dict)


class SourceRegistry(Record):
    evidence_id: str
    blocks: list[SourceBlock] = Field(default_factory=list)
    unassigned_words: list[SourceWord] = Field(default_factory=list)
    uncovered_item_regions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def _reject_duplicate_ids(self) -> 'SourceRegistry':
        seen_blocks: set[str] = set()
        seen_words: set[str] = set()
        for block in self.blocks:
            if block.block_id in seen_blocks:
                raise ValueError(f'duplicate block_id: {block.block_id}')
            seen_blocks.add(block.block_id)
            for word in block.words:
                if word.id in seen_words:
                    raise ValueError(f'duplicate word id: {word.id}')
                seen_words.add(word.id)
        for word in self.unassigned_words:
            if word.id in seen_words:
                raise ValueError(f'duplicate word id: {word.id}')
            seen_words.add(word.id)
        return self


# --- Facts ---------------------------------------------------------------------

class QualityObservation(Record):
    field: str
    reading: Reading
    requires_verification: bool
    refs: list[SourceRef] = Field(default_factory=list)


class FieldFact(Record):
    field: str
    raw_value: str
    normalized_value: JsonValue
    refs: list[SourceRef] = Field(default_factory=list)
    source_kind: SourceKind
    observations: list[QualityObservation] = Field(default_factory=list)
    usability: Usability
    normalization_trace: list[str] = Field(default_factory=list)


class ItemFacts(Record):
    id: str
    name: FieldFact
    quantity: FieldFact
    unit: FieldFact
    unit_price: FieldFact
    line_amount: FieldFact


class DocumentFacts(Record):
    evidence_id: str
    kind: DocumentKind
    template: DocumentTemplate
    fields: dict[str, FieldFact] = Field(default_factory=dict)
    items: list[ItemFacts] = Field(default_factory=list)
    covered_item_regions: list[str] = Field(default_factory=list)


class MappingProposal(Record):
    pairs: list[tuple[str, str]] = Field(default_factory=list)
    refs: list[SourceRef] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class EvidenceBundle(Record):
    documents: list[DocumentFacts] = Field(default_factory=list)
    registries: dict[str, SourceRegistry] = Field(default_factory=dict)
    mapping: MappingProposal | None = None


# --- Checks, issues, authorizations -------------------------------------------

class CheckResult(Record):
    rule_id: str
    status: CheckStatus
    dependencies: list[str] = Field(default_factory=list)
    refs: list[SourceRef] = Field(default_factory=list)
    reason: str
    issue_ids: list[str] = Field(default_factory=list)


class Issue(Record):
    id: str
    stable_key: str
    issue_class: IssueClass
    owner_mode: DemoMode
    question: str
    refs: list[SourceRef] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    status: IssueStatus


class Authorization(Record):
    action_id: str
    kind: AuthorizationKind
    case_version: int
    policy_version: str
    profile: Profile
    purpose: str
    amount_vnd: StrictInt = Field(gt=0, le=999_999_999_999_999)
    mode: DemoMode
    reason: str


# --- Decision and pipeline -----------------------------------------------------

class Decision(Record):
    action: DecisionAction
    completion_basis: CompletionBasis | None = None
    accepted_amount_vnd: StrictInt | None = Field(default=None, gt=0, le=999_999_999_999_999)
    checks: list[CheckResult] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    technical_code: str | None = None


class StageIdentity(Record):
    stage: str
    request_hash: str
    prompt_version: str
    model_id: str
    schema_version: str
    provider: str


class PipelineResult(Record):
    decision: Decision
    bundle: EvidenceBundle
    artifacts: list[str] = Field(default_factory=list)
    identities: list[StageIdentity] = Field(default_factory=list)
    stage_durations_ms: dict[str, int] = Field(default_factory=dict)
    provider_calls: int
    repair_calls: int


# --- Human actions and snapshots ----------------------------------------------

class HumanAction(Record):
    id: str
    case_id: str
    case_version: int
    issue_id: str | None = None
    mode: DemoMode
    kind: HumanActionKind
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str
    created_at: AwareDatetime


class CaseSnapshot(Record):
    case_id: str
    case_version: int
    claim: Claim
    evidence: list[Evidence] = Field(default_factory=list)
    policy: PolicyConfig
    authorizations: list[Authorization] = Field(default_factory=list)
    confirmations: list[HumanAction] = Field(default_factory=list)
    active_action_ids: list[str] = Field(default_factory=list)
    input_hash: str


# --- Persistence records -------------------------------------------------------

class RunRecord(Record):
    id: str
    case_id: str
    input_hash: str
    case_version: int
    status: ExecutionStatus
    stop_requested: bool
    stage: str
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    policy_version: str
    threshold_version: str
    identities: list[StageIdentity] = Field(default_factory=list)
    result: PipelineResult | None = None


class CaseRecord(Record):
    id: str
    case_version: int
    claim: Claim
    current_run_id: str | None = None
    workflow_state: WorkflowState
    evidence: list[Evidence] = Field(default_factory=list)


class PaymentRequest(Record):
    id: str
    case_id: str
    run_id: str
    payee: str
    amount_vnd: StrictInt = Field(gt=0, le=999_999_999_999_999)
    currency: Literal['VND']
    completion_basis: CompletionBasis
    status: PaymentRequestStatus
    policy_version: str


# --- API / provider boundary records ------------------------------------------

class Upload(Record):
    original_name: str
    mime: str
    content: bytes
    role: EvidenceRole


class AnalysisRequest(Record):
    evidence: Evidence
    registry: SourceRegistry
    required_fields: list[str] = Field(default_factory=list)
    threshold_version: str


class RawOcr(Record):
    provider: str
    model_id: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    received_at: AwareDatetime


class AuditEvent(Record):
    id: str
    case_id: str | None = None
    run_id: str | None = None
    case_version: int | None = None
    timestamp: AwareDatetime
    kind: str
    stage: str
    reason: str
    refs: list[SourceRef] = Field(default_factory=list)
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class StopReply(Record):
    status: StopStatus
    run_id: str


# --- Errors --------------------------------------------------------------------

class DomainError(Exception):
    """Machine-readable domain error: ``code`` is stable, ``message`` business-friendly."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f'{code}: {message}')


class StoppedRun(DomainError):
    """Stop was acknowledged; no late business action may be applied."""

    def __init__(self, message: str = 'Run stopped; no late business action applied.') -> None:
        super().__init__('STOPPED', message)

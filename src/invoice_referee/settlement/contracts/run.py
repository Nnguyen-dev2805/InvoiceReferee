"""Reading, linking and run contracts (System §S2/S3)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

from time import monotonic as _monotonic

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.contracts.b3_contracts import B3CompanyContext
from invoice_referee.settlement.contracts.base import SourceRecord, Submission


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

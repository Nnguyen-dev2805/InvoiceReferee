"""Case, question and audit contracts (System §S2/S6)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

from invoice_referee.settlement.contracts.advance import B3WorkflowView
from invoice_referee.settlement.contracts.base import (
    AllowedAction,
    CaseOrigin,
    CaseStage,
    DemoRole,
    Job,
    SourceRecord,
    SourceView,
    Submission,
)
from invoice_referee.settlement.contracts.report import IssueOwner
from invoice_referee.settlement.contracts.settlement import (
    B7WorkflowView,
    LinkedB7View,
)


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
    # Shared root of the business dossier (B3 root for B3/linked B7/adjustment;
    # own id for a standalone B7). Read-only projection; ``id`` stays the record
    # /stage identity used by URLs, versions, sources and commands.
    dossier_ref: str | None = None
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
    dossier_ref: str | None = None
    confirmed: bool = True


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

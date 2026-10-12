"""Base settlement contracts: ids, roles, submission/source/money summary."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

from pathlib import Path


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

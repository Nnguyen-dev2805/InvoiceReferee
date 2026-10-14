"""API request models and payload builders (plan T2).

Client bodies use extra=forbid so a raw client-supplied role/budget/activity id
can never ride along into server authority (contracts §10.4).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from invoice_referee.domain.common import EvidenceRef, UtcDatetime
from invoice_referee.workflow.service import (
    PERSONAS,
    CaseWorkflow,
    DemoSession,
    default_actor,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExistingActivity(ApiModel):
    mode: Literal["existing"] = "existing"
    activity_id: str


class NewActivity(ApiModel):
    mode: Literal["new"] = "new"
    name: str
    occurred_at: UtcDatetime
    declared_purpose: str


ActivityChoice = Annotated[
    Union[ExistingActivity, NewActivity], Field(discriminator="mode")
]


class CreateCaseRequest(ApiModel):
    activity: ActivityChoice


class PersonaSwitchRequest(ApiModel):
    persona: Literal["employee", "accountant", "approver"]


class PaidClaimRequest(ApiModel):
    """A client's typed Q32 employee paid-claim (plan A2).

    The client states the invoice reference, integer VND amount, the source refs
    and a reason. It cannot supply the actor/verifier/known state — the server
    derives those from the session and the uploaded bytes.
    """

    invoice_reference: str
    amount: int
    refs: list[EvidenceRef] = Field(default_factory=list)
    reason: str


class SubmitRequest(ApiModel):
    activity_id: str | None = None
    confirmed_activity_id: str | None = None
    declared_purpose: str
    notes: str | None = None
    employee_paid_claims: list[PaidClaimRequest] = Field(default_factory=list)
    # The employee-confirmed draft (W4). A declaration, not a verified fact.
    declared_name: str | None = None
    destination: str | None = None
    trip_start: str | None = None
    trip_end: str | None = None
    declared_advance: int | None = None
    incurred_total: int | None = None
    original_declared_advance: int | None = None


class AnswerRequest(ApiModel):
    issue_id: str
    basis_id: str
    answer_kind: str
    value: str | int | None = None
    reason: str


class DecisionRequest(ApiModel):
    issue_ids: list[str]
    basis_id: str
    actions: list[str]
    effect_scope: str
    amount: int | None = None
    reason: str


class MoneyInput(ApiModel):
    """A client's claim about money that moved; the server verifies it (§4)."""

    external_key: str
    claimed_kind: str
    claimed_scope: str
    payer: str
    payee: str
    amount: int
    event_at: UtcDatetime
    completion_claim: str | None = None
    reverses_event_id: str | None = None
    reason: str
    # The "record actual money" form's source metadata (plan D): the observed
    # instrument method/status/reference. The server still decides verification.
    instrument_method: Literal["TRANSFER", "CASH"] | None = None
    instrument_status: Literal["COMPLETED", "PENDING", "FAILED", "UNKNOWN"] | None = (
        None
    )
    instrument_reference: str | None = None
    # Source refs from the read voucher (page/quote locators). The server
    # verifies them; a foreign digest is rejected before any write (14/10/2026).
    refs: list[EvidenceRef] = Field(default_factory=list)


class RecordActualRequest(ApiModel):
    money: MoneyInput


class ControlRequest(ApiModel):
    action: Literal["STOP", "RESUME"]
    reason: str


class VerifyRequest(ApiModel):
    suite: Literal["core", "escalation", "development"] = "development"
    mode: Literal["LIVE", "RECORDED_REPLAY", "STUB"] = "STUB"


class OverrideRequest(ApiModel):
    supersedes_decision_id: str
    issue_ids: list[str]
    basis_id: str
    actions: list[str]
    effect_scope: str
    amount: int | None = None
    reason: str


def session_payload(
    workflow: CaseWorkflow,
    session: DemoSession,
    *,
    mode: str,
    settings: object | None,
    frontend_dir: Path | None,
) -> dict[str, object]:
    import_info = workflow.last_context_import(session.tenant)
    missing: list[str] = []
    if settings is not None:
        missing = list(settings.missing_for_live())  # type: ignore[attr-defined]
    return {
        "session": {
            "session_id": session.session_id,
            "tenant": session.tenant,
            "persona": session.persona,
            "actor_id": session.actor_id,
            "actor_name": workflow.display_name(session.tenant, session.actor_id),
        },
        "personas": [
            {
                "id": persona,
                "label": label,
                "actor_id": default_actor(persona, session.tenant),
                "actor_name": workflow.display_name(
                    session.tenant, default_actor(persona, session.tenant)
                ),
            }
            for persona, label in PERSONAS
        ],
        "activity_catalog": [
            {
                "id": entry.activity_id,
                "name": entry.name,
                "occurred_at": entry.occurred_at.isoformat()
                if entry.occurred_at
                else None,
                "purpose": entry.purpose,
                "status": entry.status,
                "budget_amount": entry.budget_amount,
                "profile": entry.profile,
            }
            for entry in workflow.catalog(session.tenant)
        ],
        "mode": mode,
        "diagnostics": {
            "mode": mode,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}",
            "context_digest": import_info["digest"] if import_info else None,
            "context_origin": import_info["origin"] if import_info else None,
            "frontend_built": bool(frontend_dir is not None and frontend_dir.is_dir()),
            "missing_live_settings": missing,
        },
    }

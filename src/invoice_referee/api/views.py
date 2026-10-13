"""API request models and payload builders (plan T2).

Client bodies use extra=forbid so a raw client-supplied role/budget/activity id
can never ride along into server authority (contracts §10.4).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

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
    occurred_at: datetime
    declared_purpose: str


ActivityChoice = Annotated[
    Union[ExistingActivity, NewActivity], Field(discriminator="mode")
]


class CreateCaseRequest(ApiModel):
    activity: ActivityChoice


class PersonaSwitchRequest(ApiModel):
    persona: Literal["employee", "accountant", "approver"]


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
                "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
                "purpose": entry.purpose,
                "status": entry.status,
                "budget_amount": entry.budget_amount,
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

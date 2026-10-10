"""Track A decision contracts shared by policy, storage, and UI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AutomationDecision(StrEnum):
    AUTO_PROCESS = "AUTO_PROCESS"
    REQUEST_INFO = "REQUEST_INFO"
    ESCALATE = "ESCALATE"


class UncertaintyType(StrEnum):
    NONE = "NONE"
    FACTUAL_UNKNOWN = "FACTUAL_UNKNOWN"
    OUTSIDE_POLICY = "OUTSIDE_POLICY"
    BEYOND_AUTHORITY = "BEYOND_AUTHORITY"
    SUSPICIOUS = "SUSPICIOUS"


class DecisionTarget(StrEnum):
    ACCOUNTANT = "ACCOUNTANT"
    EMPLOYEE = "EMPLOYEE"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    CHIEF_ACCOUNTANT = "CHIEF_ACCOUNTANT"
    DIRECTOR = "DIRECTOR"


class SettlementFinding(BaseModel):
    rule_id: str
    status: str
    message: str
    uncertainty_type: UncertaintyType = UncertaintyType.NONE
    target: DecisionTarget = DecisionTarget.ACCOUNTANT
    question: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class SettlementDecision(BaseModel):
    automation_decision: AutomationDecision
    uncertainty_type: UncertaintyType
    primary_finding_code: str | None = None
    target: DecisionTarget = DecisionTarget.ACCOUNTANT
    question: str | None = None
    reason: str
    source_refs: list[str] = Field(default_factory=list)


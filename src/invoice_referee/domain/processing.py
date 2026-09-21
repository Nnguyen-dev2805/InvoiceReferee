"""Processing results shared by workflow, storage, and review UI."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProcessingDecision(StrEnum):
    PASS = "PASS"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class RuleFinding(BaseModel):
    rule_id: str
    status: Literal["PASS", "FAIL", "ERROR"]
    message: str
    source_refs: list[str] = Field(default_factory=list)


class KimiAnalysis(BaseModel):
    business_context_present: bool
    conflict_detected: bool
    summary: str
    reasoning: str
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class CaseProcessingResult(BaseModel):
    schema_version: str = "1.0"
    case_id: str
    decision: ProcessingDecision
    processed_at: str
    summary: str
    reasoning: str
    findings: list[RuleFinding] = Field(default_factory=list)
    ocr_evidence_ids: list[str] = Field(default_factory=list)
    kimi_analysis: KimiAnalysis | None = None
    processing_errors: list[str] = Field(default_factory=list)

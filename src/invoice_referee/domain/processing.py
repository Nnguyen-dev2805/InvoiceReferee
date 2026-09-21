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
    status: Literal["PASS", "WARN", "FAIL", "ERROR"]
    message: str
    source_refs: list[str] = Field(default_factory=list)


class BlockAssessment(BaseModel):
    candidate_id: str
    importance: Literal["CRITICAL", "NON_CRITICAL", "UNKNOWN"]
    quality_state: Literal[
        "READABLE",
        "SEMANTICALLY_READABLE",
        "UNCERTAIN",
        "UNREADABLE",
        "UNKNOWN",
    ] = "UNKNOWN"
    review_action: Literal[
        "CONTINUE", "ASK_HUMAN", "DEFER_TO_POLICY"
    ] = "ASK_HUMAN"
    canonical_fields: list[str] = Field(default_factory=list)
    observed_text: str = ""
    semantic_category: str | None = None
    reason: str
    human_question: str | None = None


class FieldAssessment(BaseModel):
    evidence_id: str
    field_name: str
    status: Literal[
        "FOUND",
        "NOT_FOUND_IN_OCR",
        "UNCERTAIN",
        "NOT_APPLICABLE",
        "UNKNOWN",
    ]
    importance: Literal["CRITICAL", "NON_CRITICAL", "UNKNOWN"]
    source_refs: list[str] = Field(default_factory=list)
    reason: str
    human_question: str | None = None


class MissingValueAnalysis(BaseModel):
    document_types: dict[str, str] = Field(default_factory=dict)
    field_assessments: list[FieldAssessment] = Field(default_factory=list)


class ConfidenceAnalysis(BaseModel):
    document_types: dict[str, str] = Field(default_factory=dict)
    block_assessments: list[BlockAssessment] = Field(default_factory=list)


class KimiAnalysis(BaseModel):
    business_context_present: bool
    conflict_detected: bool
    summary: str
    reasoning: str
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    document_types: dict[str, str] = Field(default_factory=dict)
    block_assessments: list[BlockAssessment] = Field(default_factory=list)


class CaseProcessingResult(BaseModel):
    schema_version: str = "1.1"
    case_id: str
    decision: ProcessingDecision
    processed_at: str
    summary: str
    reasoning: str
    findings: list[RuleFinding] = Field(default_factory=list)
    ocr_evidence_ids: list[str] = Field(default_factory=list)
    low_confidence_candidates: list[dict[str, Any]] = Field(default_factory=list)
    # Legacy field retained only for processing.json files created by older runs.
    missing_value_analysis: MissingValueAnalysis | None = None
    confidence_analysis: ConfidenceAnalysis | None = None
    # Kept so previously persisted processing.json files remain readable.
    kimi_analysis: KimiAnalysis | None = None
    processing_errors: list[str] = Field(default_factory=list)

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
    requires_verification: bool | None = None
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


class EvidenceQualityResult(BaseModel):
    evidence_id: str
    filename: str
    status: Literal["CLEAR", "NEEDS_HUMAN", "ERROR"]
    candidate_count: int = 0
    blocking_fields: list[str] = Field(default_factory=list)
    warning_fields: list[str] = Field(default_factory=list)


class InventoryLineItemFact(BaseModel):
    item_id: str
    raw_name: str
    quantity: str | None = None
    unit: str | None = None
    unit_price: str | None = None
    line_amount: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class InventoryDocumentFacts(BaseModel):
    evidence_id: str
    document_type: str
    supplier_name: str | None = None
    supplier_tax_code: str | None = None
    document_date: str | None = None
    document_number: str | None = None
    receipt_status: Literal[
        "RECEIVED_FULL",
        "RECEIVED_PARTIAL",
        "PENDING",
        "REJECTED",
        "UNKNOWN",
        "NOT_APPLICABLE",
    ] = "UNKNOWN"
    subtotal_amount: str | None = None
    total_amount: str | None = None
    items: list[InventoryLineItemFact] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class InventoryTextReport(BaseModel):
    is_inventory_report: bool = False
    supplier_name: str | None = None
    supplier_tax_code: str | None = None
    report_date: str | None = None
    receipt_status: Literal[
        "RECEIVED_FULL",
        "RECEIVED_PARTIAL",
        "PENDING",
        "REJECTED",
        "UNKNOWN",
    ] = "UNKNOWN"
    items: list[InventoryLineItemFact] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class InventoryItemMatch(BaseModel):
    primary_item_id: str
    supporting_item_id: str
    semantic_match: bool
    reason: str


class InventoryAnalysis(BaseModel):
    applicability: Literal["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"]
    applicability_reason: str
    document_facts: list[InventoryDocumentFacts] = Field(default_factory=list)
    text_report: InventoryTextReport | None = None
    suggested_item_matches: list[InventoryItemMatch] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class ConflictSourceValue(BaseModel):
    source_id: str
    item_id: str | None = None
    value: str | None = None
    unit: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class ConflictComparison(BaseModel):
    comparison_id: str
    field: str
    item_name: str | None = None
    left: ConflictSourceValue
    right: ConflictSourceValue
    status: Literal["MATCH", "MISMATCH", "UNKNOWN"]
    reason: str
    human_question: str | None = None


class PotentialConflict(BaseModel):
    code: str
    field: str
    description: str
    source_refs: list[str] = Field(default_factory=list)
    human_question: str | None = None


class ConflictAnalysis(BaseModel):
    applicability: Literal["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"]
    applicability_reason: str
    document_facts: list[InventoryDocumentFacts] = Field(default_factory=list)
    text_report: InventoryTextReport | None = None
    suggested_item_matches: list[InventoryItemMatch] = Field(default_factory=list)
    comparisons: list[ConflictComparison] = Field(default_factory=list)
    potential_conflicts: list[PotentialConflict] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class KimiAnalysis(BaseModel):
    business_context_present: bool
    conflict_detected: bool
    summary: str
    reasoning: str
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    document_types: dict[str, str] = Field(default_factory=dict)
    block_assessments: list[BlockAssessment] = Field(default_factory=list)


class CaseProcessingResult(BaseModel):
    schema_version: str = "1.3"
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
    evidence_quality: list[EvidenceQualityResult] = Field(default_factory=list)
    inventory_analysis: InventoryAnalysis | None = None
    conflict_analysis: ConflictAnalysis | None = None
    # Kept so previously persisted processing.json files remain readable.
    kimi_analysis: KimiAnalysis | None = None
    processing_errors: list[str] = Field(default_factory=list)

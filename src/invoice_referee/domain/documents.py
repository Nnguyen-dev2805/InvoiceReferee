"""Document/evidence pipeline DTOs (contracts §12, plan E1).

These are strict, oracle-free value objects for the OCR → classification →
extraction → matching pipeline. They are *proposals*: a `FOUND` field is a
sourced candidate, never a `Fact.KNOWN`, and nothing here has a financial
effect. Money/quantity normalization is code-owned; bool is never an amount.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Mapping, TypeAlias

from pydantic import Field, model_validator

from invoice_referee.domain.common import EvidenceRef, Id, StrictModel
from invoice_referee.domain.issues import ProcessingProblem

# --- Enums (contracts §12.2/§12.3) -----------------------------------------

DOCUMENT_TYPES: tuple[str, ...] = (
    "E_INVOICE",
    "PAPER_RECEIPT",
    "CARD_SLIP",
    "PAYMENT_PROOF",
    "TRANSPORT_TICKET",
    "HOTEL_RECEIPT",
    "COLLECTION_RECEIPT",
    "CONTRACT",
    "QUOTATION",
    "PURCHASE_ORDER",
    "ACCEPTANCE_RECORD",
    "DELIVERY_NOTE",
    "GOODS_RECEIPT",
    "SUPPLIER_CONFIRMATION",
    "OTHER",
    "UNKNOWN",
    "SETTLEMENT_FORM",
)
DocumentType = Literal[
    "E_INVOICE",
    "PAPER_RECEIPT",
    "CARD_SLIP",
    "PAYMENT_PROOF",
    "TRANSPORT_TICKET",
    "HOTEL_RECEIPT",
    "COLLECTION_RECEIPT",
    "CONTRACT",
    "QUOTATION",
    "PURCHASE_ORDER",
    "ACCEPTANCE_RECORD",
    "DELIVERY_NOTE",
    "GOODS_RECEIPT",
    "SUPPLIER_CONFIRMATION",
    "OTHER",
    "UNKNOWN",
    "SETTLEMENT_FORM",
]

DOCUMENT_EVIDENCE_ROLES: tuple[str, ...] = (
    "SETTLEMENT_DECLARATION",
    "ORIGINAL_EXPENSE_EVIDENCE",
    "PAYMENT_EVIDENCE",
    "SUPPORTING_DOCUMENT",
    "UNKNOWN",
)
DocumentEvidenceRole = Literal[
    "SETTLEMENT_DECLARATION",
    "ORIGINAL_EXPENSE_EVIDENCE",
    "PAYMENT_EVIDENCE",
    "SUPPORTING_DOCUMENT",
    "UNKNOWN",
]

FIELD_STATES: tuple[str, ...] = (
    "FOUND",
    "NOT_PRESENT",
    "UNREADABLE",
    "AMBIGUOUS",
    "NOT_APPLICABLE",
)
FieldState = Literal["FOUND", "NOT_PRESENT", "UNREADABLE", "AMBIGUOUS", "NOT_APPLICABLE"]

LinkStatus = Literal["AUTO_LINK", "SUGGEST_LINK"]
LinkMethod = Literal["INVOICE_NUMBER_EXACT", "AMOUNT_AND_CONTENT", "LLM_RESOLVED"]
RowEvidenceStatus = Literal["ORIGINAL_EVIDENCE", "ALTERNATIVE_EVIDENCE", "NO_EVIDENCE"]
AlternativeEvidenceType = Literal[
    "PAYMENT_PROOF",
    "RECEIPT_OR_COLLECTION_NOTE",
    "CONTRACT_OR_ACCEPTANCE",
    "SUPPLIER_CONFIRMATION",
    "OTHER",
]
CategoryCandidate = Literal[
    "TAXI", "CLIENT_MEAL", "HOTEL", "TRAVEL", "OFFICE_SUPPLIES", "OTHER"
]
CoverageState = Literal["OCR_COMPLETE", "NOT_READ", "ERROR"]
ConfidenceStatus = Literal["ASSESSED", "SKIPPED_NO_NUMERIC_CANDIDATES", "UNRESOLVED"]
ProfileStatus = Literal["CLEAR", "NEEDS_HUMAN", "UNKNOWN"]
ProfileIssueStatus = Literal["UNRESOLVED", "INVALID"]
MatchFindingStatus = Literal["PASS", "UNRESOLVED"]

# Money/quantity is normalized by code to Decimal; bool is never money.
MONEY_FIELD_HINTS = ("amount", "total", "subtotal", "tax", "price", "fee", "discount")

# --- OCR types (contracts §12.1) -------------------------------------------


class OcrWord(StrictModel):
    text: str
    block_start: int | None = None
    block_end: int | None = None
    confidence: float | None = None


class BBox(StrictModel):
    top_left_x: float
    top_left_y: float
    bottom_right_x: float
    bottom_right_y: float


class OcrBlock(StrictModel):
    id: str
    kind: str
    content: str
    bbox: BBox | None = None
    words: tuple[OcrWord, ...] = ()


class OcrPage(StrictModel):
    page: Annotated[int, Field(ge=1)]
    markdown: str
    blocks: tuple[OcrBlock, ...] = ()


class OcrSourceResult(StrictModel):
    source_id: Id
    source_digest: str = Field(min_length=1)
    provider: str
    model: str
    pages: tuple[OcrPage, ...] = ()
    raw_artifact_ref: str | None = None
    problems: tuple[ProcessingProblem, ...] = ()
    complete: bool = True


class PageCoverage(StrictModel):
    source_id: Id
    page: Annotated[int, Field(ge=1)]
    state: CoverageState
    artifact_ref: str | None = None
    problem: str | None = None


# --- Classification (contracts §12.2) --------------------------------------


class DocumentClassification(StrictModel):
    document_id: Id
    source_id: Id
    page_range: tuple[int, int]
    block_ids: tuple[str, ...] = ()
    document_type: DocumentType
    roles: tuple[DocumentEvidenceRole, ...] = ()
    role_refs: Mapping[DocumentEvidenceRole, tuple[EvidenceRef, ...]] = {}
    alternative_document_types: tuple[DocumentType, ...] = ()
    classification_confidence: float | None = None
    signals: tuple[str, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _ordered_page_range(self) -> DocumentClassification:
        start, end = self.page_range
        if start < 1 or end < start:
            raise ValueError("page_range must be 1-based and ordered (start <= end)")
        return self

    @model_validator(mode="after")
    def _confidence_in_range(self) -> DocumentClassification:
        if self.classification_confidence is not None and not (
            0.0 <= self.classification_confidence <= 1.0
        ):
            raise ValueError("classification_confidence must be within [0, 1]")
        return self


# --- Extraction (contracts §12.3) ------------------------------------------

CandidateValue: TypeAlias = str | int | Decimal | bool | tuple[str, ...]


class ValueAlternative(StrictModel):
    value: CandidateValue
    refs: tuple[EvidenceRef, ...] = ()


class FieldCandidate(StrictModel):
    field: str
    state: FieldState
    value: CandidateValue | None = None
    alternatives: tuple[ValueAlternative, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _state_matches_value(self) -> FieldCandidate:
        if self.state == "FOUND":
            if self.value is None:
                raise ValueError("a FOUND field requires a value")
            if not self.refs:
                raise ValueError("a FOUND field requires at least one ref")
        elif self.state == "AMBIGUOUS":
            if self.value is not None:
                raise ValueError("an AMBIGUOUS field must not carry a single value")
            if len(self.alternatives) < 2:
                raise ValueError("an AMBIGUOUS field needs at least two alternatives")
            if any(not alt.refs for alt in self.alternatives):
                raise ValueError("each AMBIGUOUS alternative must carry its own ref")
        else:
            if self.value is not None:
                raise ValueError(f"a {self.state} field must not carry a value")
        # A money-ish field must never be a bool (bool is a subclass of int).
        if self.value is not None and isinstance(self.value, bool):
            raise ValueError("a bool is not a valid candidate value")
        return self

    @model_validator(mode="after")
    def _money_float_rejected(self) -> FieldCandidate:
        if (
            self.value is not None
            and isinstance(self.value, float)
            and any(h in self.field for h in MONEY_FIELD_HINTS)
        ):
            raise ValueError("money fields must be Decimal/int, not float")
        return self


class DocumentLine(StrictModel):
    id: Id
    fields: tuple[FieldCandidate, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()


class DocumentProfileIssue(StrictModel):
    code: str
    field: str | None = None
    status: ProfileIssueStatus
    message: str
    refs: tuple[EvidenceRef, ...] = ()
    blocking: bool = True


class DocumentAnalysis(StrictModel):
    source_id: Id
    document_id: Id
    document_type: DocumentType
    roles: tuple[DocumentEvidenceRole, ...] = ()
    role_refs: Mapping[DocumentEvidenceRole, tuple[EvidenceRef, ...]] = {}
    page_range: tuple[int, int] = (1, 1)
    block_ids: tuple[str, ...] = ()
    classification_confidence: float | None = None
    alternative_document_types: tuple[DocumentType, ...] = ()
    classification_refs: tuple[EvidenceRef, ...] = ()
    fields: tuple[FieldCandidate, ...] = ()
    line_items: tuple[DocumentLine, ...] = ()
    confidence_status: ConfidenceStatus = "UNRESOLVED"
    confidence_refs: tuple[EvidenceRef, ...] = ()
    profile_status: ProfileStatus = "UNKNOWN"
    profile_findings: tuple[DocumentProfileIssue, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()
    warnings: tuple[str, ...] = ()


# --- Matching (contracts §12.4) --------------------------------------------


class EvidenceLink(StrictModel):
    item_id: Id
    source_id: Id
    document_id: Id
    status: LinkStatus
    method: LinkMethod
    score: Decimal
    allocated_amount: Decimal | None = None
    explanation: str
    refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _score_bounds(self) -> EvidenceLink:
        if not (Decimal("0") <= self.score <= Decimal("1")):
            raise ValueError("link score must be within [0, 1]")
        if self.allocated_amount is not None and self.allocated_amount < 0:
            raise ValueError("allocated_amount must not be negative")
        return self


class DocumentRowMatch(StrictModel):
    item_id: Id
    paper_amount: Decimal | None = None
    category_candidate: CategoryCandidate | None = None
    evidence_status: RowEvidenceStatus
    alternative_evidence_type: AlternativeEvidenceType | None = None
    matched_document_date: object | None = None
    original_total: Decimal | None = None
    allocated_total: Decimal | None = None
    no_evidence_reason: str | None = None
    refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _allocation_bounded_by_source(self) -> DocumentRowMatch:
        # An explicit allocation may not exceed the source document total.
        if (
            self.allocated_total is not None
            and self.original_total is not None
            and self.allocated_total > self.original_total
        ):
            raise ValueError("allocated_total must not exceed original_total")
        return self


class EvidenceMatchFinding(StrictModel):
    code: str
    status: MatchFindingStatus
    message: str
    refs: tuple[EvidenceRef, ...] = ()


class EvidenceMatchingResult(StrictModel):
    links: tuple[EvidenceLink, ...] = ()
    rows: tuple[DocumentRowMatch, ...] = ()
    findings: tuple[EvidenceMatchFinding, ...] = ()
    unmatched_source_ids: tuple[Id, ...] = ()


# --- Confidence review (contracts §12.3) -----------------------------------

ConfidenceImportance = Literal["CRITICAL", "NON_CRITICAL", "UNKNOWN"]
QualityState = Literal["READABLE", "SEMANTICALLY_READABLE", "UNCERTAIN", "UNREADABLE", "UNKNOWN"]
ReviewAction = Literal["CONTINUE", "ASK_HUMAN", "DEFER_TO_POLICY"]
ConfidenceReviewStatus = Literal["ASSESSED", "SKIPPED_NO_NUMERIC_CANDIDATES", "TECHNICAL_ERROR"]


class ConfidenceCandidate(StrictModel):
    candidate_id: Id
    source_id: Id
    page: Annotated[int, Field(ge=1)]
    block_id: str
    content: str
    low_words: tuple[OcrWord, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()


class BlockAssessment(StrictModel):
    candidate_id: Id
    importance: ConfidenceImportance
    quality_state: QualityState
    review_action: ReviewAction
    canonical_fields: tuple[str, ...] = ()
    observed_text: str | None = None
    reason: str
    human_question: str | None = None
    requires_verification: bool | None = None


class ConfidenceReview(StrictModel):
    status: ConfidenceReviewStatus
    block_assessments: tuple[BlockAssessment, ...] = ()

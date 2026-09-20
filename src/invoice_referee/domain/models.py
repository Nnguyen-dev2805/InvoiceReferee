"""Domain data contracts for InvoiceReferee Sprint 1.

Schema source of truth: docs/DATA_MODEL.md.

Design rules enforced here:
- Money is integer VND. Floats and bools are rejected (see ``_money``).
- Quantities are integers in the MVP.
- Unknown fields stay ``None`` instead of guessed values.
- Enums pin the exact allowed values so downstream modules share one contract.

These are contracts only. No workflow orchestration or business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# --- Enums -------------------------------------------------------------------


class DecisionAction(str, Enum):
    """The only three user-facing agent actions."""

    AUTO_PROCESS = "AUTO_PROCESS"
    REQUEST_INFO = "REQUEST_INFO"
    ESCALATE = "ESCALATE"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class UncertaintyType(str, Enum):
    FACTUAL_UNKNOWN = "FACTUAL_UNKNOWN"
    OUTSIDE_POLICY = "OUTSIDE_POLICY"
    BEYOND_AUTHORITY = "BEYOND_AUTHORITY"


class PaymentStatus(str, Enum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    UNKNOWN = "UNKNOWN"


class ScopeStatus(str, Enum):
    """Tri-state scope. Never collapse UNKNOWN and OUTSIDE_POLICY into a bool."""

    IN_SCOPE = "IN_SCOPE"
    OUTSIDE_POLICY = "OUTSIDE_POLICY"
    UNKNOWN = "UNKNOWN"


class TransactionType(str, Enum):
    """Sprint 1 supports only PO-based goods purchases."""

    PO_GOODS_PURCHASE = "PO_GOODS_PURCHASE"


class WorkflowStatus(str, Enum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"


class InvoiceType(str, Enum):
    ORIGINAL = "ORIGINAL"
    ADJUSTMENT = "ADJUSTMENT"
    REPLACEMENT = "REPLACEMENT"


class SourceType(str, Enum):
    JSON = "JSON"
    XML = "XML"
    PDF_TEXT = "PDF_TEXT"
    OCR = "OCR"


# --- Validation helpers ------------------------------------------------------


def _money(value: int, field_name: str) -> int:
    """Validate an integer VND money value.

    Rejects ``bool`` (a subclass of int), ``float`` and negatives so that no
    floating-point money enters the pipeline.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer VND value, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative, got {value}")
    return value


def _quantity(value: int, field_name: str) -> int:
    """Validate a non-negative integer quantity."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer quantity, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative, got {value}")
    return value


# --- Extraction contract -----------------------------------------------------


@dataclass
class ExtractedDocument:
    """Canonical extraction output shared by every source adapter."""

    document_type: str
    source_type: SourceType
    source_ref: str
    extractor: str
    fields: dict[str, Any] = field(default_factory=dict)
    parse_warnings: list[str] = field(default_factory=list)


# --- Evidence line items -----------------------------------------------------


@dataclass
class POLineItem:
    item_id: Optional[str]
    ordered_quantity: Optional[int]
    unit_price: Optional[int]
    line_total: Optional[int]
    description: Optional[str] = None

    def __post_init__(self) -> None:
        # Validate only present values; a missing critical field stays None
        # (it must never be guessed into a passing 0).
        if self.ordered_quantity is not None:
            _quantity(self.ordered_quantity, "ordered_quantity")
        if self.unit_price is not None:
            _money(self.unit_price, "unit_price")
        if self.line_total is not None:
            _money(self.line_total, "line_total")


@dataclass
class ReceiptLineItem:
    item_id: Optional[str]
    received_quantity: Optional[int]
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if self.received_quantity is not None:
            _quantity(self.received_quantity, "received_quantity")


@dataclass
class InvoiceLineItem:
    item_id: Optional[str]
    invoiced_quantity: Optional[int]
    unit_price: Optional[int]
    line_total: Optional[int]
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if self.invoiced_quantity is not None:
            _quantity(self.invoiced_quantity, "invoiced_quantity")
        if self.unit_price is not None:
            _money(self.unit_price, "unit_price")
        if self.line_total is not None:
            _money(self.line_total, "line_total")


# --- Evidence documents ------------------------------------------------------


@dataclass
class PurchaseOrder:
    po_id: Optional[str]
    vendor_id: Optional[str]
    items: list[POLineItem]
    approved_total: Optional[int]
    status: Optional[str]
    vendor_tax_code: Optional[str] = None
    vendor_name: Optional[str] = None
    currency: Optional[str] = "VND"
    order_date: Optional[str] = None

    def __post_init__(self) -> None:
        if self.approved_total is not None:
            _money(self.approved_total, "approved_total")


@dataclass
class GoodsReceipt:
    receipt_id: Optional[str]
    po_id: Optional[str]
    items: list[ReceiptLineItem]
    received_date: Optional[str]
    status: Optional[str] = None


@dataclass
class SupplierInvoice:
    invoice_id: Optional[str]
    invoice_number: Optional[str]
    invoice_series: Optional[str]
    invoice_type: InvoiceType
    vendor_id: Optional[str]
    vendor_tax_code: Optional[str]
    po_id: Optional[str]
    invoice_date: Optional[str]
    items: list[InvoiceLineItem]
    total_amount: Optional[int]
    related_invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    currency: Optional[str] = "VND"
    source_type: SourceType = SourceType.JSON
    confidence: float = 1.0
    flagged: bool = False

    def __post_init__(self) -> None:
        # Money is validated only when present; an unreadable amount stays None
        # (it must not be guessed into a passing value).
        if self.total_amount is not None:
            _money(self.total_amount, "total_amount")


@dataclass
class ApprovalRecord:
    approval_id: Optional[str]
    po_id: Optional[str]
    approval_type: Optional[str]
    status: Optional[str]
    item_id: Optional[str] = None
    approved_value: Optional[int] = None
    approved_text_value: Optional[str] = None
    approved_amount_delta: Optional[int] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.approved_value is not None:
            _money(self.approved_value, "approved_value")
        if self.approved_amount_delta is not None:
            _money(self.approved_amount_delta, "approved_amount_delta")


@dataclass
class PaymentRecord:
    invoice_id: Optional[str]
    status: PaymentStatus
    paid_amount: Optional[int] = None
    payment_date: Optional[str] = None
    payment_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.paid_amount is not None:
            _money(self.paid_amount, "paid_amount")


# --- Analysis objects --------------------------------------------------------


@dataclass
class CheckResult:
    check_id: str
    status: CheckStatus
    policy_rule_id: Optional[str] = None
    expected: Any = None
    actual: Any = None
    reason: Optional[str] = None
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class EvidenceIssue:
    """A structural evidence problem found while linking a Transaction.

    Distinct from a CheckResult: an issue means the evidence cannot be trusted
    to auto-process (wrong linkage or a non-routine document status), not that a
    business comparison failed. It maps to REQUEST_INFO, never AUTO_PROCESS.
    """

    issue_id: str
    policy_rule_id: str
    reason: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Uncertainty:
    type: UncertaintyType
    field: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class PolicyContext:
    scope_status: ScopeStatus
    authority_threshold_vnd: int
    applicable_rule_ids: list[str] = field(default_factory=list)
    deterministic_uncertainties: list[UncertaintyType] = field(default_factory=list)

    def __post_init__(self) -> None:
        _money(self.authority_threshold_vnd, "authority_threshold_vnd")


@dataclass
class AgentAssessment:
    """Structured LLM proposal. Never the final decision."""

    proposed_uncertainty_type: Optional[UncertaintyType]
    proposed_action: DecisionAction
    explanation: str
    primary_check_id: Optional[str] = None
    question: Optional[str] = None
    target: Optional[str] = None
    policy_rule_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    fallback_used: bool = False


@dataclass
class Decision:
    action: DecisionAction
    reason: str
    uncertainty: Optional[Uncertainty] = None
    question: Optional[str] = None
    target: Optional[str] = None
    policy_rule_ids: list[str] = field(default_factory=list)
    decided_at: Optional[str] = None


@dataclass
class AuditEvent:
    event_type: str
    actor: str = "InvoiceReferee"
    event_id: Optional[str] = None
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None
    rule_id: Optional[str] = None
    input_refs: list[str] = field(default_factory=list)
    result: Optional[str] = None
    reason: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


# --- Human controls ----------------------------------------------------------


@dataclass
class HumanStop:
    actor: str
    previous_workflow_status: WorkflowStatus
    new_workflow_status: WorkflowStatus
    reason: str
    timestamp: Optional[str] = None
    stop_id: Optional[str] = None


@dataclass
class HumanOverride:
    actor: str
    original_action: DecisionAction
    overridden_action: DecisionAction
    reason: str
    timestamp: Optional[str] = None
    override_id: Optional[str] = None

    def __post_init__(self) -> None:
        # An override must resolve to one of the three user-facing actions.
        # STOPPED is a workflow status, never a decision.
        if not isinstance(self.overridden_action, DecisionAction):
            self.overridden_action = DecisionAction(self.overridden_action)
        if not isinstance(self.original_action, DecisionAction):
            self.original_action = DecisionAction(self.original_action)


# --- Transaction container ---------------------------------------------------


@dataclass
class Transaction:
    transaction_id: str
    transaction_type: Optional[TransactionType]
    declared_transaction_type: Optional[str] = None
    po: Optional[PurchaseOrder] = None
    goods_receipts: list[GoodsReceipt] = field(default_factory=list)
    invoice: Optional[SupplierInvoice] = None
    prior_invoices: list[SupplierInvoice] = field(default_factory=list)
    payment_history: list[PaymentRecord] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    evidence_issues: list[EvidenceIssue] = field(default_factory=list)
    decision: Optional[Decision] = None
    audit_log: list[AuditEvent] = field(default_factory=list)
    workflow_status: WorkflowStatus = WorkflowStatus.ACTIVE
    human_stops: list[HumanStop] = field(default_factory=list)
    human_overrides: list[HumanOverride] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- Unified review output ---------------------------------------------------


@dataclass
class ReviewResult:
    transaction: Transaction
    checks: list[CheckResult]
    policy_context: PolicyContext
    agent_assessment: Optional[AgentAssessment]
    decision: Decision
    audit_events: list[AuditEvent] = field(default_factory=list)


# --- OCR / document extraction contracts -------------------------------------
#
# These describe the Supplier-Invoice OCR path only. They carry candidate facts
# with provenance; they never carry a final Agent action. See
# docs/superpowers/specs/2026-09-20-invoice-ocr-pipeline-design.md sections 8.x.


class FieldStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    CONFLICTING = "CONFLICTING"


class ExtractionStatus(str, Enum):
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED = "REVIEWED"
    FAILED = "FAILED"


@dataclass
class UploadedDocument:
    """A validated uploaded document. Raw bytes live here, never in audit events."""

    document_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    content: bytes


@dataclass
class DocumentPage:
    document_id: str
    page_number: int
    image_bytes: bytes
    width: int
    height: int
    dpi: int
    native_text: Optional[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BoundingBox:
    """Coordinates normalized to page dimensions (0..1), ordered x1<=x2, y1<=y2."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x1 <= self.x2 <= 1.0):
            raise ValueError("x coordinates must be normalized and ordered (0<=x1<=x2<=1)")
        if not (0.0 <= self.y1 <= self.y2 <= 1.0):
            raise ValueError("y coordinates must be normalized and ordered (0<=y1<=y2<=1)")


@dataclass
class OCRBlock:
    block_id: str
    page_number: int
    text: str
    confidence: float
    bounding_box: BoundingBox
    block_type: str  # TEXT | KEY_VALUE | TABLE_CELL
    row_index: Optional[int] = None
    column_index: Optional[int] = None


@dataclass
class OCRDocument:
    document_id: str
    pages: list[DocumentPage]
    blocks: list[OCRBlock]
    full_text: str
    engine: str
    engine_version: str
    processing_ms: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class FieldCandidate:
    """One extracted field value with provenance and human-review lineage.

    ``extraction_method`` is one of NATIVE_PDF_TEXT, OCR_RULE, OCR_TABLE,
    LLM_ASSISTED, or HUMAN. A missing value stays ``None``; it is never coerced
    into an empty string or zero to satisfy a downstream dataclass.
    """

    field_name: str
    raw_text: Optional[str]
    normalized_value: Any
    confidence: Optional[float]
    status: FieldStatus
    page_number: Optional[int]
    bounding_box: Optional[BoundingBox]
    evidence_block_ids: list[str] = field(default_factory=list)
    extraction_method: str = "OCR_RULE"
    warnings: list[str] = field(default_factory=list)
    original_raw_text: Optional[str] = None
    original_normalized_value: Any = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be within [0, 1] or None")


@dataclass
class InvoiceExtractionResult:
    document_id: str
    status: ExtractionStatus
    fields: dict[str, FieldCandidate] = field(default_factory=dict)
    line_items: list[dict[str, FieldCandidate]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)

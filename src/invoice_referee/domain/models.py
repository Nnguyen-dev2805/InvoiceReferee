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
    item_id: str
    ordered_quantity: int
    unit_price: int
    line_total: int
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _quantity(self.ordered_quantity, "ordered_quantity")
        _money(self.unit_price, "unit_price")
        _money(self.line_total, "line_total")


@dataclass
class ReceiptLineItem:
    item_id: str
    received_quantity: int
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _quantity(self.received_quantity, "received_quantity")


@dataclass
class InvoiceLineItem:
    item_id: str
    invoiced_quantity: int
    unit_price: int
    line_total: int
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _quantity(self.invoiced_quantity, "invoiced_quantity")
        _money(self.unit_price, "unit_price")
        _money(self.line_total, "line_total")


# --- Evidence documents ------------------------------------------------------


@dataclass
class PurchaseOrder:
    po_id: str
    vendor_id: str
    items: list[POLineItem]
    approved_total: int
    status: str
    vendor_name: Optional[str] = None
    currency: str = "VND"
    order_date: Optional[str] = None

    def __post_init__(self) -> None:
        _money(self.approved_total, "approved_total")


@dataclass
class GoodsReceipt:
    receipt_id: str
    po_id: str
    items: list[ReceiptLineItem]
    received_date: str
    status: str = "RECEIVED"


@dataclass
class SupplierInvoice:
    invoice_id: str
    invoice_number: str
    invoice_series: str
    invoice_type: InvoiceType
    vendor_id: str
    vendor_tax_code: str
    po_id: str
    invoice_date: str
    items: list[InvoiceLineItem]
    total_amount: Optional[int]
    related_invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    currency: str = "VND"
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
    approval_id: str
    po_id: str
    approval_type: str
    status: str
    item_id: Optional[str] = None
    approved_value: Optional[int] = None
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
    invoice_id: str
    status: PaymentStatus
    paid_amount: int = 0
    payment_date: Optional[str] = None
    payment_id: Optional[str] = None

    def __post_init__(self) -> None:
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

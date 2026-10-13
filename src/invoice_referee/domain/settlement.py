"""Domain contracts for UC-03 expense settlement and reimbursement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SettlementType(StrEnum):
    ADVANCE_SETTLEMENT = "ADVANCE_SETTLEMENT"
    EMPLOYEE_REIMBURSEMENT = "EMPLOYEE_REIMBURSEMENT"


class SubmissionSourceType(StrEnum):
    DIGITAL_FORM = "DIGITAL_FORM"
    PAPER_SCAN = "PAPER_SCAN"


class SettlementDocumentRole(StrEnum):
    SETTLEMENT_REQUEST_FORM = "SETTLEMENT_REQUEST_FORM"
    EXPENSE_EVIDENCE = "EXPENSE_EVIDENCE"


class ExpenseDocumentType(StrEnum):
    """Canonical UC-03 document types returned by the extraction agent."""

    E_INVOICE = "E_INVOICE"
    PAPER_RECEIPT = "PAPER_RECEIPT"
    CARD_SLIP = "CARD_SLIP"
    PAYMENT_PROOF = "PAYMENT_PROOF"
    TRANSPORT_TICKET = "TRANSPORT_TICKET"
    HOTEL_RECEIPT = "HOTEL_RECEIPT"
    COLLECTION_RECEIPT = "COLLECTION_RECEIPT"
    CONTRACT = "CONTRACT"
    QUOTATION = "QUOTATION"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    ACCEPTANCE_RECORD = "ACCEPTANCE_RECORD"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    SUPPLIER_CONFIRMATION = "SUPPLIER_CONFIRMATION"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ExpenseDocumentRole(StrEnum):
    REQUEST_FORM = "REQUEST_FORM"
    ORIGINAL_EVIDENCE = "ORIGINAL_EVIDENCE"
    SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT"
    UNKNOWN = "UNKNOWN"


class DocumentFieldState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNREADABLE = "UNREADABLE"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DocumentValidityStatus(StrEnum):
    CLEAR = "CLEAR"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    OUTSIDE_POLICY = "OUTSIDE_POLICY"


class DocumentFieldImportance(StrEnum):
    """How a missing field affects the next stage of the UC-03 workflow.

    The value is deliberately attached to the document profile instead of a
    filename or OCR phrase.  That keeps a parking ticket from being evaluated
    with electronic-invoice requirements, for example.
    """

    CRITICAL = "CRITICAL"
    CORROBORATABLE = "CORROBORATABLE"
    INFORMATIONAL = "INFORMATIONAL"


ORIGINAL_EXPENSE_DOCUMENT_TYPES = frozenset(
    {
        ExpenseDocumentType.E_INVOICE,
        ExpenseDocumentType.PAPER_RECEIPT,
        ExpenseDocumentType.TRANSPORT_TICKET,
        ExpenseDocumentType.HOTEL_RECEIPT,
        ExpenseDocumentType.COLLECTION_RECEIPT,
    }
)

SUPPORTING_EXPENSE_DOCUMENT_TYPES = frozenset(
    {
        ExpenseDocumentType.CARD_SLIP,
        ExpenseDocumentType.PAYMENT_PROOF,
        ExpenseDocumentType.CONTRACT,
        ExpenseDocumentType.QUOTATION,
        ExpenseDocumentType.PURCHASE_ORDER,
        ExpenseDocumentType.ACCEPTANCE_RECORD,
        ExpenseDocumentType.DELIVERY_NOTE,
        ExpenseDocumentType.GOODS_RECEIPT,
        ExpenseDocumentType.SUPPLIER_CONFIRMATION,
    }
)


class ExpenseCategory(StrEnum):
    UNKNOWN = "UNKNOWN"
    CLIENT_MEAL = "CLIENT_MEAL"
    TRAVEL = "TRAVEL"
    HOTEL = "HOTEL"
    TAXI = "TAXI"
    OFFICE_SUPPLIES = "OFFICE_SUPPLIES"
    OPERATIONS = "OPERATIONS"
    PERSONAL = "PERSONAL"
    OTHER = "OTHER"


class ExpenseEvidenceStatus(StrEnum):
    ORIGINAL_EVIDENCE = "ORIGINAL_EVIDENCE"
    ALTERNATIVE_EVIDENCE = "ALTERNATIVE_EVIDENCE"
    UNMATCHED_EVIDENCE = "UNMATCHED_EVIDENCE"
    NO_EVIDENCE = "NO_EVIDENCE"


class AlternativeEvidenceType(StrEnum):
    PAYMENT_PROOF = "PAYMENT_PROOF"
    RECEIPT_OR_COLLECTION_NOTE = "RECEIPT_OR_COLLECTION_NOTE"
    CONTRACT_OR_ACCEPTANCE = "CONTRACT_OR_ACCEPTANCE"
    SUPPLIER_CONFIRMATION = "SUPPLIER_CONFIRMATION"
    OTHER = "OTHER"


class EmployeeProfile(BaseModel):
    employee_id: str = "EMP-DEMO-001"
    name: str = "Nguyễn Minh An"
    department: str = "Phòng Kinh doanh"
    position: str = "Nhân viên"
    data_classification: str = "SYNTHETIC"


class BusinessContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    purpose: str = ""
    project_code: str | None = None
    client_name: str | None = None
    activity_start_date: date | None = None
    activity_end_date: date | None = None


class ExpenseItemDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: str
    category: ExpenseCategory
    description: str
    expense_date: date | None = None
    claimed_amount: Decimal = Field(gt=0)
    currency: str = "VND"
    evidence_names: list[str] = Field(default_factory=list)
    evidence_status: ExpenseEvidenceStatus = ExpenseEvidenceStatus.ORIGINAL_EVIDENCE
    alternative_evidence_type: AlternativeEvidenceType | None = None
    evidence_exception_reason: str | None = None
    # Legacy internal field. New employee forms must not ask users to enter it.
    policy_exception_code: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_evidence_declaration(self) -> "ExpenseItemDraft":
        reason = (self.evidence_exception_reason or "").strip()
        if self.evidence_status == ExpenseEvidenceStatus.ALTERNATIVE_EVIDENCE:
            if self.alternative_evidence_type is None:
                raise ValueError("Bằng chứng thay thế phải có loại tài liệu.")
            if not reason:
                raise ValueError(
                    "Bằng chứng thay thế phải nêu lý do không có chứng từ gốc."
                )
        if self.evidence_status == ExpenseEvidenceStatus.NO_EVIDENCE and not reason:
            raise ValueError("Khoản không có chứng từ phải nêu rõ lý do.")
        return self


class SettlementDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    settlement_type: SettlementType
    source_type: SubmissionSourceType
    employee: EmployeeProfile = Field(default_factory=EmployeeProfile)
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    advance_id: str | None = None
    allocated_advance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    beneficiary_name: str | None = None
    bank_account_number: str | None = None
    bank_name: str | None = None
    paper_no_evidence_reason: str | None = None
    currency: str = "VND"
    expense_items: list[ExpenseItemDraft] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def require_items_for_digital_form(self) -> "SettlementDraft":
        if (
            self.source_type == SubmissionSourceType.DIGITAL_FORM
            and not self.expense_items
        ):
            raise ValueError("Form điện tử phải có ít nhất một khoản chi.")
        return self

    @property
    def claimed_total(self) -> Decimal:
        return sum(
            (item.claimed_amount for item in self.expense_items),
            start=Decimal("0"),
        )


@dataclass(frozen=True, slots=True)
class SettlementUpload:
    original_name: str
    content: bytes
    mime_type: str
    role: SettlementDocumentRole
    linked_item_id: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def sha256(self) -> str:
        return sha256(self.content).hexdigest()


class SettlementReceipt(BaseModel):
    case_id: str
    workflow_status: str
    processing_status: str
    submitted_at: str
    claimed_total: Decimal
    currency: str
    document_count: int = Field(ge=0)


class DocumentLineFact(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_amount: Decimal | None = None
    source_refs: list[str] = Field(default_factory=list)


class ExpenseDocumentFacts(BaseModel):
    document_id: str
    document_type: ExpenseDocumentType
    classification_confidence: float | None = Field(default=None, ge=0, le=1)
    classification_signals: list[str] = Field(default_factory=list)
    alternative_document_types: list[ExpenseDocumentType] = Field(default_factory=list)
    issuer_name: str | None = None
    issuer_tax_code: str | None = None
    buyer_name: str | None = None
    buyer_tax_code: str | None = None
    document_number: str | None = None
    template_number: str | None = None
    serial_number: str | None = None
    document_date: date | None = None
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    tax: Decimal | None = None
    service_charge: Decimal | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = None
    payer_name: str | None = None
    payee_name: str | None = None
    transaction_reference: str | None = None
    transaction_status: str | None = None
    confirmation_present: bool | None = None
    line_items: list[DocumentLineFact] = Field(default_factory=list)
    field_states: dict[str, DocumentFieldState] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class DocumentValidityIssue(BaseModel):
    code: str
    field: str | None = None
    message: str
    question: str | None = None
    blocking: bool = True
    importance: DocumentFieldImportance = DocumentFieldImportance.CRITICAL
    corroboratable: bool = False


class DocumentValidityResult(BaseModel):
    document_id: str
    document_type: str
    document_role: ExpenseDocumentRole
    status: DocumentValidityStatus
    eligible_for_matching: bool
    required_fields: list[str] = Field(default_factory=list)
    present_fields: list[str] = Field(default_factory=list)
    issues: list[DocumentValidityIssue] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class PaperSettlementLine(BaseModel):
    line_id: str
    description: str
    invoice_refs: list[str] = Field(default_factory=list)
    amount: Decimal | None = None
    note: str | None = None
    requires_evidence: bool = False
    no_evidence_reason: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class PaperSettlementFacts(BaseModel):
    document_id: str
    document_type: str = "PAPER_SETTLEMENT_REQUEST"
    purpose: str | None = None
    total_amount: Decimal | None = None
    advance_amount: Decimal | None = None
    reimbursement_amount: Decimal | None = None
    beneficiary_name: str | None = None
    bank_account_number: str | None = None
    bank_name: str | None = None
    lines: list[PaperSettlementLine] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)

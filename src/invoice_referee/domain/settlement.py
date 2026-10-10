"""Domain contracts for UC-03 expense settlement and reimbursement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettlementType(StrEnum):
    ADVANCE_SETTLEMENT = "ADVANCE_SETTLEMENT"
    EMPLOYEE_REIMBURSEMENT = "EMPLOYEE_REIMBURSEMENT"


class SubmissionSourceType(StrEnum):
    DIGITAL_FORM = "DIGITAL_FORM"
    PAPER_SCAN = "PAPER_SCAN"


class SettlementDocumentRole(StrEnum):
    SETTLEMENT_REQUEST_FORM = "SETTLEMENT_REQUEST_FORM"
    EXPENSE_EVIDENCE = "EXPENSE_EVIDENCE"


class ExpenseCategory(StrEnum):
    CLIENT_MEAL = "CLIENT_MEAL"
    TRAVEL = "TRAVEL"
    HOTEL = "HOTEL"
    TAXI = "TAXI"
    OFFICE_SUPPLIES = "OFFICE_SUPPLIES"
    OPERATIONS = "OPERATIONS"
    PERSONAL = "PERSONAL"
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
    policy_exception_code: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class SettlementDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    settlement_type: SettlementType
    source_type: SubmissionSourceType
    employee: EmployeeProfile = Field(default_factory=EmployeeProfile)
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    advance_id: str | None = None
    allocated_advance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = "VND"
    expense_items: list[ExpenseItemDraft] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

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
    document_type: str
    issuer_name: str | None = None
    issuer_tax_code: str | None = None
    buyer_name: str | None = None
    buyer_tax_code: str | None = None
    document_number: str | None = None
    serial_number: str | None = None
    document_date: date | None = None
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    tax: Decimal | None = None
    service_charge: Decimal | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = None
    line_items: list[DocumentLineFact] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


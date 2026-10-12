"""B3 verbal-assignment intake/report contracts (``b3-intake-v1``).

Pure data contracts: the form declaration, the backend-owned company context
fixture and the report proposal. This module imports nothing from
``settlement.models`` (nor ``DomainError``), so ``models`` can reference
``RunInput.b3_context`` / ``Report.b3`` without a circular import. ``b3.py``
re-exports these names and keeps the evaluation helpers that do need models.

Invariants (Rulebook R1/R2/R5/R6/R8, Product P2a):

- Money is strict integer VND; ``None`` is unknown, never a hidden ``0``.
- An IMPORT draft may be partially empty; a confirmed submission must be
  complete with a positive request and at least one estimate row.
- The company context is backend fixture data (explicit version/activation);
  an employee upload never supplies or overrides it.
- A fixed demo clock is only accepted for an activated synthetic fixture.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

B3_INTAKE_SCHEMA = "b3-intake-v1"


class B3EstimateRow(BaseModel):
    """One forecast row: company-paid and employee-paid parts stay separate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_id: str
    description: str
    basis: str | None = None
    company_vnd: StrictInt | None = None
    employee_vnd: StrictInt | None = None

    @model_validator(mode="after")
    def _amounts_not_negative(self) -> "B3EstimateRow":
        for name in ("company_vnd", "employee_vnd"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(
                    f"{name} không được âm; số mờ/thiếu để null, không ghi âm."
                )
        return self


class B3Intake(BaseModel):
    """Employee declaration for a B3 verbal assignment (form as lời khai)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["b3-intake-v1"]
    intake_method: Literal["WEB", "IMPORT"]
    confirmed: bool
    destination: str | None = None
    trip_start: date | None = None
    trip_end: date | None = None
    purpose: str | None = None
    assignment_note: str | None = None
    request_amount_vnd: StrictInt | None = None
    settlement_due: date | None = None
    estimate_rows: list[B3EstimateRow] = Field(default_factory=list)

    @field_validator("destination", "purpose", "assignment_note")
    @classmethod
    def _blank_text_is_none(cls, value: str | None) -> str | None:
        # Chuỗi rỗng/toàn khoảng trắng = chưa khai (null), không phải giá trị
        # hợp lệ; bản confirmed vẫn bắt buộc các trường chính khác None.
        if value is not None and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _check(self) -> "B3Intake":
        row_ids = [row.row_id for row in self.estimate_rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("row_id trùng trong estimate_rows; không ghi đè.")
        if self.request_amount_vnd is not None and self.request_amount_vnd < 0:
            raise ValueError("request_amount_vnd không được âm.")
        if self.trip_start is not None and self.trip_end is not None \
                and self.trip_end < self.trip_start:
            raise ValueError("trip_end trước trip_start; ngày không hợp lệ.")
        if self.trip_end is not None and self.settlement_due is not None \
                and self.settlement_due < self.trip_end:
            raise ValueError("settlement_due trước trip_end; hạn không hợp lệ.")
        if not self.confirmed:
            return self  # draft IMPORT được thiếu fields; null là unknown
        missing = [name for name, value in (
            ("destination", self.destination),
            ("purpose", self.purpose),
            ("trip_start", self.trip_start),
            ("trip_end", self.trip_end),
            ("settlement_due", self.settlement_due),
            ("request_amount_vnd", self.request_amount_vnd),
        ) if value is None]
        if missing:
            raise ValueError(
                f"Bản đã xác nhận thiếu trường bắt buộc: {missing}."
            )
        if self.request_amount_vnd <= 0:
            raise ValueError("Số xin ứng phải dương; 0/không rõ phải null.")
        if not self.estimate_rows:
            raise ValueError("Cần ít nhất một dòng dự toán cho bản đã xác nhận.")
        return self


# --- company context fixture (backend-owned) ----------------------------------

class B3Person(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_ref: str
    role: Literal["EMPLOYEE", "ACCOUNTANT", "APPROVER"]
    name: str
    department: str | None = None


class B3Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_ref: str
    accountant_ref: str
    approver_ref: str


class B3Grant(BaseModel):
    """Demo authority grant: actor may decide for an employee (all works when
    ``work_ref`` is ``None``) inside an effective window.

    A missing limit is unknown, never unlimited (R8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_ref: str
    employee_ref: str
    work_ref: str | None = None
    allow_work: bool = False
    max_budget_vnd: StrictInt | None = None
    max_advance_vnd: StrictInt | None = None
    effective_from: AwareDatetime
    effective_to: AwareDatetime
    ref: str

    @model_validator(mode="after")
    def _positive_limits(self) -> "B3Grant":
        for name in ("max_budget_vnd", "max_advance_vnd"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} phải dương khi có.")
        return self


class B3Coverage(BaseModel):
    """Company-side observation scope for one employee (all works when
    ``work_ref`` is ``None``); ``complete_prior_history`` includes opening
    balances, without it an absent opening balance stays unknown."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    employee_ref: str
    work_ref: str | None = None
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    complete_prior_history: bool = False
    groups: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    missing_ranges: list[dict[str, Any]] = Field(default_factory=list)
    owner_ref: str
    origin: str
    ref: str

    @model_validator(mode="after")
    def _window(self) -> "B3Coverage":
        if self.to < self.from_:
            raise ValueError("Cửa sổ coverage to trước from.")
        return self


B3HistoryKind = Literal[
    "ADVANCE", "ADVANCE_RETURN", "ADVANCE_APPROVAL", "PENDING_ADVANCE",
    "WORK_DECISION", "BUDGET_DECISION",
]
B3HistoryStatus = Literal[
    "RECEIVED", "PENDING", "APPROVED", "REFUSED", "CANCELLED",
]

# RECEIVED chỉ dành cho tiền đã thực nhận; APPROVED không tự thành RECEIVED.
_KIND_STATUSES: dict[str, tuple[str, ...]] = {
    "ADVANCE": ("RECEIVED",),
    "ADVANCE_RETURN": ("RECEIVED",),
    "ADVANCE_APPROVAL": ("APPROVED", "REFUSED", "CANCELLED"),
    "PENDING_ADVANCE": ("PENDING",),
    "WORK_DECISION": ("APPROVED", "REFUSED", "CANCELLED"),
    "BUDGET_DECISION": ("APPROVED", "REFUSED", "CANCELLED"),
}


class B3HistoryRecord(BaseModel):
    """One company-side event/decision; always scoped to a concrete work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_ref: str
    employee_ref: str
    work_ref: str
    kind: B3HistoryKind
    amount_vnd: StrictInt | None = None
    event_at: AwareDatetime
    known_at: AwareDatetime
    status: B3HistoryStatus
    ref: str

    @model_validator(mode="after")
    def _kind_status_amount(self) -> "B3HistoryRecord":
        if self.status not in _KIND_STATUSES[self.kind]:
            raise ValueError(
                f"kind {self.kind} không hợp lệ với status {self.status}."
            )
        if self.amount_vnd is None:
            if self.kind != "WORK_DECISION":
                raise ValueError(
                    f"amount_vnd bắt buộc cho kind {self.kind}; chỉ "
                    "WORK_DECISION được bỏ số."
                )
        elif self.amount_vnd <= 0:
            raise ValueError("amount_vnd phải dương khi có.")
        return self


class B3ReceiptSource(BaseModel):
    """A configured place an advance may be paid from (bank account or cashbook).

    Two options for the pilot — not an account-management/treasury store. The
    ``namespace`` is the backend-configured value the money event carries; the
    ``label`` is what the accountant sees. A missing config keeps readonly
    history and blocks new records; no fallback namespace is invented.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["BANK_TRANSFER", "CASH"]
    namespace: str
    label: str

    @field_validator("namespace", "label")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("namespace/label nguồn chi không được để trắng.")
        return value


class B3CompanyContext(BaseModel):
    """Backend-owned synthetic company fixture for the B3 v1 slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["b3-company-context-v1"]
    version: str
    activated: bool
    synthetic: bool
    demo_clock: AwareDatetime | None = None
    people: list[B3Person] = Field(default_factory=list)
    routes: list[B3Route] = Field(default_factory=list)
    grants: list[B3Grant] = Field(default_factory=list)
    coverage: list[B3Coverage] = Field(default_factory=list)
    history: list[B3HistoryRecord] = Field(default_factory=list)
    receipt_sources: list[B3ReceiptSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _clock_and_duplicates(self) -> "B3CompanyContext":
        if self.demo_clock is not None and not (self.activated and self.synthetic):
            raise ValueError(
                "Clock cố định chỉ áp dụng cho fixture synthetic đã activated; "
                "context thật dùng giờ máy."
            )
        actor_refs = [p.actor_ref for p in self.people]
        if len(actor_refs) != len(set(actor_refs)):
            raise ValueError("actor_ref trùng trong people.")
        for records, key in ((self.grants, "ref"), (self.coverage, "ref"),
                             (self.history, "event_ref")):
            refs = [getattr(record, key) for record in records]
            if len(refs) != len(set(refs)):
                raise ValueError(f"{key} trùng trong context {records[0]!r}.")
        namespaces = [s.namespace for s in self.receipt_sources]
        if len(namespaces) != len(set(namespaces)):
            raise ValueError("namespace trùng trong receipt_sources.")
        return self


# --- proposal contract (Report.b3) ---------------------------------------------

B3Readiness = Literal[
    "DRAFT_CONFIRMATION_REQUIRED", "NEEDS_INFORMATION",
    "NEEDS_AUTHORIZED_REVIEW", "READY_FOR_ACCOUNTANT_REVIEW",
]
B3DecisionState = Literal["PENDING_DECISION", "NEEDS_REVIEW"]


class B3Proposal(BaseModel):
    """Sourced B3 proposal: readiness, forecasts, routing and field refs.

    COMPLETE ở report nghĩa là checks tiền/source/history/routing đủ để kế
    toán rà soát — không nghĩa là đã được duyệt. Current work/B/advance pending
    là next decisions, không phải issue.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness: B3Readiness
    intake: B3Intake
    forecast_company_vnd: StrictInt | None = None
    forecast_employee_vnd: StrictInt | None = None
    forecast_total_vnd: StrictInt | None = None
    work_permission: B3DecisionState
    advance_approval: B3DecisionState
    accountant_ref: str | None = None
    approver_ref: str | None = None
    field_refs: dict[str, list[str]] = Field(default_factory=dict)

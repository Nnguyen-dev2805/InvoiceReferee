"""B3 verbal assignment intake/report contracts (b3-intake-v1, Task 1).

Records here are pure data: the form declaration, the backend-owned company
context fixture and the report proposal. They deliberately import nothing from
``settlement.models`` at module import time so ``models`` can reference
``RunInput.b3_context`` / ``Report.b3`` without a circular import; evaluation
helpers further down import models lazily.

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


# --- helpers -------------------------------------------------------------------

def load_b3_context(path) -> B3CompanyContext:
    """Load an explicitly configured context file; malformed is a startup error.

    An absent/unset path is the caller's "not configured" case; a configured
    file that fails validation must never fall back to implicit authority.
    """
    import json
    from pathlib import Path

    from invoice_referee.domain.models import DomainError

    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"Không đọc được SETTLEMENT_B3_CONTEXT_PATH ({file}): {error}",
        ) from error
    except json.JSONDecodeError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File context B3 không phải JSON hợp lệ ({file}): {error}",
        ) from error
    try:
        return B3CompanyContext.model_validate(data)
    except Exception as error:  # pydantic ValidationError
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File context B3 không hợp lệ ({file}): {error}",
        ) from error


def is_b3_v1(form: dict[str, Any] | None) -> bool:
    """True khi form theo hợp đồng b3-intake-v1 (case B3 mới); legacy không đổi."""
    return isinstance(form, dict) and form.get("schema_version") == B3_INTAKE_SCHEMA


# --- B3 v1 evaluation (Task 3) --------------------------------------------------
#
# Reader key grammar (System §S2/S4; B3 v1 không gọi generic payment matcher):
#   document.role = ADVANCE_REQUEST | FORECAST | SUPPORTING
#   person.employee_ref; person.name
#   trip.destination; trip.start; trip.end; trip.purpose
#   advance.request.amount; advance.request.amount_words
#   advance.request.amount_words_value; advance.settlement_due
#   forecast.company; forecast.employee; forecast.total
#   forecast.row.<row_id>.description/.basis/.company/.employee
#
# rule IDs: trip_context, request_positive, amount_words_consistency,
# estimate_arithmetic, request_forecast_consistency, proposal_relation,
# source_form_consistency, history_coverage, prior_advance_state, decision_route.

B3_V1_KEYS = ["document.role", "person.", "trip.", "advance.", "forecast."]

_ROW_FIELDS = ("description", "basis", "company", "employee")
_TRIP_FIELDS = ("trip.destination", "trip.start", "trip.end", "trip.purpose")
_B3_MONEY_KEYS = ("forecast.company", "forecast.employee", "forecast.total")


def _is_b3_grammar_key(key: str) -> bool:
    parts = key.split(".")
    if key == "document.role":
        return True
    if len(parts) == 2 and parts[0] == "person" and parts[1] in ("employee_ref",
                                                                  "name"):
        return True
    if key in _TRIP_FIELDS:
        return True
    if key in ("advance.request.amount", "advance.request.amount_words",
               "advance.request.amount_words_value", "advance.settlement_due"):
        return True
    if key in _B3_MONEY_KEYS:
        return True
    if len(parts) == 4 and parts[0] == "forecast" and parts[1] == "row" \
            and parts[3] in _ROW_FIELDS:
        return True
    return False


def _form_ref(input_revision: int, path: str) -> str:
    return f"form:{input_revision}:{path}"


def evaluate_b3_proposal(run_input, observations, *, run_id: str, mode: str,
                        technical_issues=None):
    """Initial B3 proposal từ lời khai + nguồn + company context (P2a).

    Form là lời khai; import dùng Reader observations có refs rồi người nộp
    xác nhận. Python kiểm số học/mâu thuẫn/coverage/quyền — không có approval
    nào được tạo ở đây; work/B/advance pending là next decisions.
    """
    from datetime import datetime, timezone

    from pydantic import ValidationError

    from invoice_referee.domain.models import DomainError
    from invoice_referee.settlement import rules as rules
    from invoice_referee.settlement.models import (
        CheckResult,
        ComponentSlot,
        Issue,
        Report,
        ReportComponents,
    )

    try:
        intake = B3Intake.model_validate(run_input.submission.form)
    except ValidationError as error:
        raise DomainError(
            "INVALID_PAYLOAD", f"Form B3 v1 không hợp lệ: {error}",
        ) from error

    # B3 money keys ngoài MONEY_KEY_SUFFIXES của B7: reject trước aggregation.
    for observation in observations:
        if observation.read_state != "READ":
            continue
        key = observation.key
        if key in _B3_MONEY_KEYS or (
                key.startswith("forecast.row.")
                and key.rsplit(".", 1)[-1] in ("company", "employee")):
            if isinstance(observation.value, bool) or \
                    not isinstance(observation.value, int):
                raise DomainError(
                    "INVALID_MONEY",
                    f"Trường tiền {key} (fact {observation.fact_id}) phải là "
                    f"integer VND, không bool/float/chuỗi.",
                )

    context = run_input.b3_context
    employee_ref = run_input.submission.employee_ref
    work_ref = run_input.submission.work_ref
    money_as_of = run_input.submission.money_as_of
    knowledge_cutoff = run_input.submission.knowledge_cutoff
    revision = run_input.input_revision

    issues: list[Issue] = list(technical_issues or [])
    checks: list[CheckResult] = []
    contradictions: list[tuple[str, list[str]]] = []

    # --- group observations into per-(source, page) document units ----------
    units: dict[tuple[str, int | None], list] = {}
    for observation in observations:
        units.setdefault((observation.source_id, observation.page),
                         []).append(observation)

    def unit_value(unit, key):
        return rules._resolve(unit, key)

    request_units: list[tuple[tuple, list]] = []
    forecast_units: list[tuple[tuple, list]] = []
    for unit_key in sorted(units):
        unit = units[unit_key]
        role, role_refs, role_contra = unit_value(unit, "document.role")
        has_request = any(o.read_state == "READ"
                          and o.key.startswith("advance.request.")
                          for o in unit)
        has_forecast = any(o.read_state == "READ" and o.key.startswith("forecast.")
                           for o in unit)
        inferred = ("ADVANCE_REQUEST" if has_request and not has_forecast
                    else "FORECAST" if has_forecast and not has_request else None)
        final_role = role if role is not None else inferred
        if role is not None and inferred is not None and role != inferred:
            # giấy khai role nhưng nội dung mâu thuẫn; giữ cả hai làm rõ
            contradictions.append(("document.role", role_refs))
        if final_role == "ADVANCE_REQUEST":
            request_units.append((unit_key, unit))
        elif final_role == "FORECAST":
            forecast_units.append((unit_key, unit))

    # --- scalar resolution with contradiction detection -----------------------
    all_keys = {o.key for o in observations}
    resolved: dict[str, tuple[Any, list[str], bool]] = {}
    for key in sorted(all_keys):
        resolved[key] = rules._resolve(observations, key)
        # document.role là key theo từng tài liệu/trang: khác nhau giữa các
        # giấy là bình thường, không phải mâu thuẫn toàn hồ sơ.
        if resolved[key][2] and _is_b3_grammar_key(key) and key != "document.role":
            contradictions.append((key, resolved[key][1]))

    def value_of(key):
        return resolved.get(key, (None, [], False))

    # --- request value: nguồn (import) hoặc form (native) --------------------
    if request_units:
        request_amount, request_refs, request_contra = value_of(
            "advance.request.amount")
        if request_contra:
            request_amount = None
    else:
        request_amount = intake.request_amount_vnd
        request_refs = ([_form_ref(revision, "request_amount_vnd")]
                        if request_amount is not None else [])
        request_contra = False

    # --- forecast rows: theo unit, dedup bản trùng, conflict giữ nguyên -------
    def unit_rows(unit):
        row_ids = sorted({o.key.split(".")[2] for o in unit
                          if o.key.startswith("forecast.row.")
                          and len(o.key.split(".")) == 4})
        rows: dict[str, dict[str, Any]] = {}
        for row_id in row_ids:
            row: dict[str, Any] = {"company": None, "employee": None,
                                   "description": None, "basis": None,
                                   "refs": [], "bad_refs": [], "contra": False}
            for field in _ROW_FIELDS:
                value, refs, contra = unit_value(
                    unit, f"forecast.row.{row_id}.{field}")
                row[field] = value
                row["refs"].extend(refs)
                if contra:
                    row["contra"] = True
                if value is None:
                    bad = [o for o in unit
                           if o.key == f"forecast.row.{row_id}.{field}"
                           and o.read_state in ("UNCLEAR", "READ")
                           and (o.read_state == "UNCLEAR"
                                or o.usability != "USABLE")]
                    row["bad_refs"].extend(
                        ref for o in bad for ref in (o.source_id, o.fact_id))
            rows[row_id] = row
        return rows

    def canonical(rows) -> tuple:
        return tuple((rid, rows[rid]["description"], rows[rid]["basis"],
                      rows[rid]["company"], rows[rid]["employee"])
                     for rid in sorted(rows))

    def sums(rows):
        company = employee = 0
        ok_company = ok_employee = bool(rows)
        for row in rows.values():
            if row["company"] is None:
                ok_company = False
            else:
                company += row["company"]
            if row["employee"] is None:
                ok_employee = False
            else:
                employee += row["employee"]
        return (company if ok_company else None,
                employee if ok_employee else None)

    forecast_rows: dict[str, dict[str, Any]] = {}
    forecast_refs: list[str] = []
    forecast_bad_refs: list[str] = []
    forecast_conflict = False
    if forecast_units:
        canonical_sets = []
        for _, unit in forecast_units:
            rows = unit_rows(unit)
            canonical_sets.append(canonical(rows))
            forecast_refs.extend(
                ref for row in rows.values() for ref in row["refs"]
                if ref not in forecast_refs)
            forecast_bad_refs.extend(
                ref for row in rows.values() for ref in row["bad_refs"]
                if ref not in forecast_bad_refs)
            if any(row["contra"] for row in rows.values()):
                forecast_conflict = True
        if len({set_ for set_ in canonical_sets}) > 1:
            forecast_conflict = True  # hai bản forecast khác nội dung
        forecast_rows = unit_rows(forecast_units[0][1])
        for _, unit in forecast_units[1:]:
            for row_id, row in unit_rows(unit).items():
                if row_id not in forecast_rows:
                    forecast_conflict = True
        unit_names = {unit_value(unit, "person.name")[0]
                      for _, unit in forecast_units}
        unit_names.discard(None)
        if len(unit_names) > 1:
            forecast_conflict = True  # khác người => khác nội dung, không cộng
        for field in _TRIP_FIELDS:
            values = {unit_value(unit, field)[0]
                      for _, unit in forecast_units}
            values.discard(None)
            if len(values) > 1:
                forecast_conflict = True
    forecast_company, forecast_employee = sums(forecast_rows)
    printed_company, printed_company_refs, _ = value_of("forecast.company")
    printed_employee, printed_employee_refs, _ = value_of("forecast.employee")
    printed_total, printed_total_refs, _ = value_of("forecast.total")

    form_rows = {row.row_id: {
        "company": row.company_vnd, "employee": row.employee_vnd,
        "description": row.description, "basis": row.basis,
    } for row in intake.estimate_rows}
    form_company, form_employee = sums(form_rows)

    if forecast_units and not forecast_conflict:
        proposal_company, proposal_employee = forecast_company, forecast_employee
    elif not forecast_units:
        proposal_company, proposal_employee = form_company, form_employee
    else:
        proposal_company = proposal_employee = None
    proposal_total = (proposal_company + proposal_employee
                      if proposal_company is not None
                      and proposal_employee is not None else None)

    # --- checks ---------------------------------------------------------------

    # trip_context: destination/purpose/dates đã rõ (form hoặc giấy đề nghị)
    trip_source = {field.split(".", 1)[1]: value_of(field)[0]
                   for field in _TRIP_FIELDS}
    trip_known = all(
        (getattr(intake, {"destination": "destination",
                          "start": "trip_start", "end": "trip_end",
                          "purpose": "purpose"}[name]) is not None
         or trip_source.get(name) is not None)
        for name in ("destination", "start", "end", "purpose"))
    checks.append(CheckResult(
        rule="trip_context",
        status="PASS" if trip_known else "UNRESOLVED",
        refs=[_form_ref(revision, "destination"),
              _form_ref(revision, "trip_start"),
              _form_ref(revision, "trip_end"),
              _form_ref(revision, "purpose")],
        reason=("Nơi đến/ngày/mục đích công tác đã rõ."
                if trip_known else
                "Chưa đủ nơi đến/ngày/mục đích; draft được thiếu fields.")))
    if not trip_known and intake.confirmed:
        issues.append(Issue(
            issue_id="I-B3-TRIP", type="FACT", owner="EMPLOYEE",
            message="Thiếu nơi đến/ngày/mục đích công tác; cần khai rõ.",
            refs=[_form_ref(revision, "destination")], blocked="trip",
        ))

    # request_positive
    checks.append(CheckResult(
        rule="request_positive",
        status="PASS" if request_amount is not None and request_amount > 0
        else "UNRESOLVED",
        refs=request_refs,
        reason=("Số xin ứng > 0." if request_amount else
                "Chưa có số xin ứng rõ; null là unknown, không dùng 0.")))
    if request_amount is None or request_amount <= 0:
        issues.append(Issue(
            issue_id="I-B3-REQUEST", type="FACT", owner="EMPLOYEE",
            message="Số tiền xin ứng chưa rõ hoặc không dương; cần nguồn rõ.",
            refs=request_refs, blocked="request",
        ))

    # amount_words_consistency: Python so số, không để LLM kết luận check.
    if request_units:
        words_raw, words_refs, _ = value_of("advance.request.amount_words")
        words_value, words_value_refs, _ = value_of(
            "advance.request.amount_words_value")
        refs = words_refs + words_value_refs + request_refs
        if words_raw is None:
            status = "NOT_APPLICABLE"
            reason = "Giấy đề nghị không có dòng số bằng chữ."
        elif words_value is None:
            status = "UNRESOLVED"
            reason = (f"Chưa diễn giải được số bằng chữ ({words_raw!r}); "
                      f"không đoán số.")
            issues.append(Issue(
                issue_id="I-B3-WORDS", type="FACT", owner="EMPLOYEE",
                message=f"Chưa diễn giải được số bằng chữ {words_raw!r}; "
                        f"không đoán số, cần làm rõ giấy.",
                refs=refs, blocked="request",
            ))
        elif request_amount is not None and words_value != request_amount:
            status = "FAIL"
            reason = (f"Số bằng chữ diễn giải {words_value} khác số "
                      f"{request_amount}; giữ cả hai, không clip.")
            issues.append(Issue(
                issue_id="I-B3-WORDS", type="FACT", owner="EMPLOYEE",
                message=f"Số bằng chữ ({words_value}) khác số ghi "
                        f"({request_amount}); phải làm rõ, không tự giảm.",
                refs=refs, blocked="request",
            ))
        else:
            status = "PASS"
            reason = "Số bằng chữ khớp số ghi trên giấy đề nghị."
        checks.append(CheckResult(rule="amount_words_consistency",
                                  status=status, refs=refs, reason=reason))
    else:
        checks.append(CheckResult(
            rule="amount_words_consistency", status="NOT_APPLICABLE",
            refs=[_form_ref(revision, "request_amount_vnd")],
            reason="Form native không có dòng số bằng chữ."))

    # estimate_arithmetic: rows là cơ sở; printed totals chỉ để đối chiếu.
    arithmetic_refs = list(forecast_refs) + [
        ref for refs in (printed_company_refs, printed_employee_refs,
                         printed_total_refs) for ref in refs
        if ref not in forecast_refs]
    arithmetic_conflicts: list[str] = []
    if forecast_bad_refs:
        issues.append(Issue(
            issue_id="I-B3-ARITHMETIC", type="FACT", owner="EMPLOYEE",
            message="Có dòng dự toán mờ/không đọc được; giữ null cho phần đó, "
                    "không dùng tổng in hoặc tổng một phần.",
            refs=forecast_bad_refs, blocked="forecast",
        ))
    if proposal_company is None or proposal_employee is None:
        arithmetic_status = "UNRESOLVED" if not forecast_conflict else "FAIL"
        arithmetic_reason = ("Bảng dự toán chưa đủ rows rõ để tính tổng "
                             "(null là unknown, không suy bằng 0/tổng in)."
                             if not forecast_conflict else
                             "Các bản dự toán mâu thuẫn nhau; giữ nguyên, "
                             "không cộng hai bản.")
    else:
        mismatches = []
        for printed, computed, name, refs in (
                (printed_company, proposal_company, "company",
                 printed_company_refs),
                (printed_employee, proposal_employee, "employee",
                 printed_employee_refs),
                (printed_total, proposal_total, "total", printed_total_refs)):
            if printed is not None and printed != computed:
                mismatches.append((name, printed, computed, refs))
        if mismatches:
            arithmetic_status = "FAIL"
            arithmetic_reason = "; ".join(
                f"tổng in {name} {printed} khác tổng rows {computed}"
                for name, printed, computed, _ in mismatches)
            for name, printed, computed, refs in mismatches:
                arithmetic_conflicts.extend(
                    ref for ref in refs if ref not in arithmetic_conflicts)
            issues.append(Issue(
                issue_id="I-B3-ARITHMETIC", type="FACT", owner="EMPLOYEE",
                message=f"Tổng in trên dự toán khác tổng các dòng "
                        f"({arithmetic_reason}); giữ cả hai, không chọn một.",
                refs=arithmetic_conflicts + [
                    ref for ref in forecast_refs
                    if ref not in arithmetic_conflicts],
                blocked="forecast",
            ))
        else:
            arithmetic_status = "PASS"
            arithmetic_reason = "Rows đủ và khớp tổng in (nếu có)."
    checks.append(CheckResult(rule="estimate_arithmetic",
                              status=arithmetic_status,
                              refs=arithmetic_refs, reason=arithmetic_reason))

    # request_forecast_consistency: business check với forecast phần employee.
    if request_amount is None or proposal_employee is None:
        checks.append(CheckResult(
            rule="request_forecast_consistency", status="UNRESOLVED",
            refs=request_refs,
            reason="Chưa đủ số xin hoặc dự toán employee để so."))
    elif request_amount > proposal_employee:
        checks.append(CheckResult(
            rule="request_forecast_consistency", status="FAIL",
            refs=request_refs + [
                _form_ref(revision, "estimate_rows")],
            reason=(f"Số xin {request_amount} vượt dự toán employee "
                    f"{proposal_employee}; không tự giảm, người có quyền quyết.")))
        issues.append(Issue(
            issue_id="I-B3-FORECAST", type="AUTHORITY", owner="APPROVER",
            message=(f"Số xin ứng {request_amount} vượt dự toán phần nhân viên "
                     f"{proposal_employee}; giữ số xin, chuyển người có quyền "
                     f"xét, không clip."),
            refs=request_refs, blocked="request",
        ))
    else:
        checks.append(CheckResult(
            rule="request_forecast_consistency", status="PASS",
            refs=request_refs,
            reason="Số xin trong dự toán phần employee (R6)."))

    # proposal_relation: ghép đề nghị ↔ dự toán theo identity/trip, không
    # fuzzy-join; thiếu identity hoặc mâu thuẫn => unresolved.
    relation_refs: list[str] = list(request_refs) + [
        ref for ref in forecast_refs if ref not in request_refs]
    persona = None
    if context is not None:
        persona = next((p for p in context.people
                         if p.actor_ref == employee_ref), None)
    person_values = [resolved[key][0] for key in ("person.name",)
                     if key in resolved and resolved[key][0] is not None]
    if not forecast_units and not request_units:
        relation_status = "PASS" if intake.confirmed else "UNRESOLVED"
        relation_reason = ("Đề nghị và dự toán cùng một lời khai đã xác nhận."
                           if intake.confirmed else
                           "Draft chưa xác nhận; quan hệ chưa chốt.")
        checks.append(CheckResult(rule="proposal_relation",
                                  status=relation_status,
                                  refs=[_form_ref(revision, "request_amount_vnd"),
                                        _form_ref(revision, "estimate_rows")],
                                  reason=relation_reason))
    else:
        problems: list[str] = []
        if not request_units:
            problems.append("chưa có giấy đề nghị đọc được")
        if not forecast_units:
            problems.append("chưa có dự toán đọc được")
        names = [value for value in person_values if isinstance(value, str)]
        if not names:
            problems.append("chưa xác định được người trên giấy")
        else:
            if len(set(names)) > 1:
                problems.append(f"tên khác nhau giữa các giấy {sorted(set(names))}")
            if persona is not None and names[0] != persona.name and \
                    set(names) != {persona.name}:
                problems.append(
                    f"tên trên giấy khác persona được chọn ({persona.name})")
                issues.append(Issue(
                    issue_id="I-B3-IDENTITY", type="FACT", owner="EMPLOYEE",
                    message=(f"Tên trên giấy ({sorted(set(names))}) khác "
                             f"persona {persona.name}; liên kết dossier là "
                             f"lời khai, cần nhân viên làm rõ, không suy mã "
                             f"nhân viên từ tên."),
                    refs=relation_refs, blocked="relation",
                ))
        for field in _TRIP_FIELDS:
            values = {unit_value(unit, field)[0]
                      for _, unit in request_units + forecast_units}
            values.discard(None)
            if len(values) > 1:
                problems.append(f"{field} khác nhau giữa các giấy")
        if forecast_conflict:
            problems.append("các bản dự toán khác nội dung")
        if problems:
            relation_status = "UNRESOLVED"
            checks.append(CheckResult(
                rule="proposal_relation", status=relation_status,
                refs=relation_refs,
                reason="; ".join(problems) + "; không tự ghép/quy về một."))
            if not any(issue.issue_id == "I-B3-IDENTITY"
                       for issue in issues):
                issues.append(Issue(
                    issue_id="I-B3-RELATION", type="FACT", owner="EMPLOYEE",
                    message=("Chưa xác lập được quan hệ đề nghị ↔ dự toán: "
                             + "; ".join(problems)
                             + "; không coi đã ghép."),
                    refs=relation_refs, blocked="relation",
                ))
        else:
            checks.append(CheckResult(
                rule="proposal_relation", status="PASS", refs=relation_refs,
                reason="Đề nghị và dự toán cùng người/trip; bản trùng nội dung "
                       "không tính hai lần."))

    # source_form_consistency: form là lời khai, không đè nguồn.
    form_source_refs: list[str] = []
    form_source_problems: list[str] = []
    if request_units or forecast_units:
        pairs = [
            ("request_amount_vnd", intake.request_amount_vnd, request_amount,
             request_refs),
            ("settlement_due",
             intake.settlement_due.isoformat()
             if intake.settlement_due else None,
             value_of("advance.settlement_due")[0], []),
        ]
        for field in _TRIP_FIELDS:
            name = field.split(".", 1)[1]
            form_value = getattr(intake, {
                "destination": "destination", "start": "trip_start",
                "end": "trip_end", "purpose": "purpose"}[name])
            if form_value is not None and not isinstance(form_value, str):
                form_value = form_value.isoformat()  # date → YYYY-MM-DD
            pairs.append((name, form_value, value_of(field)[0], []))
        pairs.extend([
            ("forecast_company_vnd", form_company,
             printed_company, printed_company_refs),
            ("forecast_employee_vnd", form_employee,
             printed_employee, printed_employee_refs),
        ])
        for name, form_value, source_value, refs in pairs:
            if form_value is None or source_value is None:
                continue
            if form_value != source_value:
                form_source_problems.append(
                    f"{name}: form {form_value} khác nguồn {source_value}")
                form_source_refs.append(_form_ref(revision, name))
                form_source_refs.extend(
                    ref for ref in refs if ref not in form_source_refs)
        if form_source_problems:
            checks.append(CheckResult(
                rule="source_form_consistency", status="FAIL",
                refs=form_source_refs,
                reason="; ".join(form_source_problems)
                       + "; giữ cả hai, không form-wins."))
            issues.append(Issue(
                issue_id="I-B3-FORM-SOURCE", type="FACT", owner="EMPLOYEE",
                message=("Lời khai xác nhận khác giấy đã nộp ("
                         + "; ".join(form_source_problems)
                         + "); phải làm rõ, không lấy form đè nguồn."),
                refs=form_source_refs, blocked="relation",
            ))
        else:
            checks.append(CheckResult(
                rule="source_form_consistency", status="PASS",
                refs=[_form_ref(revision, "request_amount_vnd"),
                      _form_ref(revision, "settlement_due")],
                reason="Lời khai khớp giấy đã nộp (hoặc chưa có gì mâu thuẫn)."))
    else:
        checks.append(CheckResult(
            rule="source_form_consistency", status="PASS",
            refs=[_form_ref(revision, "request_amount_vnd")],
            reason="Native form: không có giấy ngoài để mâu thuẫn."))

    # --- company context: coverage, history, quyền -----------------------------
    coverage_refs: list[str] = []
    coverage_ok = False
    if context is None or not context.activated:
        checks.append(CheckResult(
            rule="history_coverage", status="UNRESOLVED", refs=[],
            reason="Chưa cấu hình company fixture/context; lịch sử không rõ, "
                   "không suy bằng 0."))
        issues.append(Issue(
            issue_id="I-B3-CONTEXT", type="FACT", owner="ACCOUNTANT",
            message="Chưa cấu hình SETTLEMENT_B3_CONTEXT_PATH; cần company "
                    "context để biết coverage/history/tuyến quyền.",
            refs=[], blocked="history",
        ))
    else:
        for record in context.coverage:
            if record.employee_ref != employee_ref:
                continue
            if record.work_ref is not None and record.work_ref != work_ref:
                continue
            if not (record.from_ <= money_as_of <= record.to):
                continue
            if not record.complete_prior_history:
                continue  # không suy số dư đầu kỳ bằng 0 khi cờ không có
            if "ADVANCE" not in record.groups or \
                    "ADVANCE_RETURN" not in record.groups:
                continue
            coverage_ok = True
            coverage_refs.append(record.ref)
        if coverage_ok:
            checks.append(CheckResult(
                rule="history_coverage", status="PASS", refs=coverage_refs,
                reason="Coverage company-side đủ scope/as-of cho lịch sử ứng."))
        else:
            checks.append(CheckResult(
                rule="history_coverage", status="UNRESOLVED", refs=[],
                reason="Thiếu coverage đúng employee/work/as-of; A/RA không "
                       "được suy bằng 0."))
            issues.append(Issue(
                issue_id="I-B3-HISTORY", type="FACT", owner="ACCOUNTANT",
                message="Thiếu coverage company-side đúng scope/mốc; cần kế "
                        "toán xác nhận nguồn lịch sử, không suy bằng 0.",
                refs=[], blocked="history",
            ))

    # history: A/RA từ RECEIVED đúng scope/cutoffs; decisions giữ riêng trạng thái.
    sum_a = sum_ra = 0
    a_refs: list[str] = list(coverage_refs)
    prior_refs: list[str] = []
    pending_refs: list[str] = []
    refused_refs: list[str] = []
    approved_refs: list[str] = []
    work_decision_refs: list[str] = []
    b_value: int | None = None
    b_refs: list[str] = []
    budget_amounts: list[int] = []
    if context is not None:
        for record in context.history:
            if record.employee_ref != employee_ref or record.work_ref != work_ref:
                continue
            in_window = (record.event_at <= money_as_of
                         and record.known_at <= knowledge_cutoff)
            if not in_window:
                continue  # sau cutoff: giữ raw ref, không cộng, không quyết
            prior_refs.append(record.ref)
            if record.kind == "ADVANCE" and record.status == "RECEIVED":
                sum_a += record.amount_vnd or 0
            elif record.kind == "ADVANCE_RETURN" and record.status == "RECEIVED":
                sum_ra += record.amount_vnd or 0
            elif record.kind == "PENDING_ADVANCE":
                pending_refs.append(record.ref)
            elif record.kind == "ADVANCE_APPROVAL":
                if record.status == "APPROVED":
                    approved_refs.append(record.ref)
                elif record.status == "REFUSED":
                    refused_refs.append(record.ref)
            elif record.kind == "WORK_DECISION":
                work_decision_refs.append(record.ref)
            elif record.kind == "BUDGET_DECISION" and record.status == "APPROVED":
                budget_amounts.append(record.amount_vnd or 0)
                b_refs.append(record.ref)
        if len(budget_amounts) == 1:
            b_value = budget_amounts[0]
        elif len(set(budget_amounts)) > 1:
            b_value = None  # hai decision B khác nhau: không auto chọn
            issues.append(Issue(
                issue_id="I-B3-BUDGET-CONFLICT", type="FACT", owner="ACCOUNTANT",
                message="Có nhiều quyết định ngân sách khác nhau cho work; "
                        "không tự chọn, làm rõ.",
                refs=b_refs, blocked="budget",
            ))
    # zero chỉ đủ coverage; thiếu coverage giữ unknown (R5)
    a_value = sum_a if coverage_ok else None
    ra_value = sum_ra if coverage_ok else None
    if coverage_ok:
        a_refs.extend(ref for ref in prior_refs if ref not in a_refs)

    for ref in pending_refs:
        issues.append(Issue(
            issue_id="I-B3-PRIOR-PENDING", type="AUTHORITY", owner="APPROVER",
            message=(f"Còn đề nghị ứng PENDING ({ref}) cho cùng work; không "
                     f"tự tạo ứng mới/trùng, người có quyền xét."),
            refs=[ref], blocked="request",
        ))
    for ref in approved_refs:
        issues.append(Issue(
            issue_id="I-B3-PRIOR-APPROVED", type="AUTHORITY", owner="APPROVER",
            message=(f"Đã có quyết định duyệt ứng trước ({ref}) cho work; phải "
                     f"xét để không thực hiện trùng."),
            refs=[ref], blocked="request",
        ))
    for ref in refused_refs:
        issues.append(Issue(
            issue_id="I-B3-PRIOR-REFUSED", type="AUTHORITY", owner="APPROVER",
            message=(f"Có từ chối duyệt ứng còn hiệu lực ({ref}) cho work; "
                     f"resubmit không tự vượt qua."),
            refs=[ref], blocked="request",
        ))
    checks.append(CheckResult(
        rule="prior_advance_state",
        status="PASS" if not (pending_refs or approved_refs or refused_refs)
        else "UNRESOLVED",
        refs=prior_refs or coverage_refs,
        reason=("Không có pending/approval/refusal trước cho work."
                if not (pending_refs or approved_refs or refused_refs)
                else "Có quyết định/đề nghị ứng trước cho work; giữ trạng "
                     "thái/số riêng, route đúng người.")))

    # decision_route: grant đúng scope/thời điểm; limit thiếu là unknown.
    active_grants = []
    if context is not None:
        for grant in context.grants:
            if grant.employee_ref != employee_ref:
                continue
            if grant.work_ref is not None and grant.work_ref != work_ref:
                continue
            if not (grant.effective_from <= money_as_of <= grant.effective_to):
                continue
            active_grants.append(grant)
    route_refs = [grant.ref for grant in active_grants]
    work_ok = any(g.allow_work for g in active_grants)
    if request_amount is not None:
        advance_ok = any(g.max_advance_vnd is not None
                         and g.max_advance_vnd >= request_amount
                         for g in active_grants)
    else:
        advance_ok = False
    if proposal_total is not None:
        budget_ok = any(g.max_budget_vnd is not None
                        and g.max_budget_vnd >= proposal_total
                        for g in active_grants)
    else:
        budget_ok = False
    if not active_grants:
        issues.append(Issue(
            issue_id="I-B3-ROUTE", type="AUTHORITY", owner="APPROVER",
            message="Chưa có grant quyền còn hiệu lực cho employee/work ở mốc "
                    "này; cần nguồn quyền đúng scope, không mặc định hạn mức.",
            refs=[], blocked="decision",
        ))
    else:
        if not work_ok:
            issues.append(Issue(
                issue_id="I-B3-ROUTE-WORK", type="AUTHORITY", owner="APPROVER",
                message="Chưa có người được phép work cho nhân viên này ở mốc "
                        "xin; cần decision/quyền đúng scope.",
                refs=route_refs, blocked="decision",
            ))
        if request_amount is not None and not advance_ok:
            issues.append(Issue(
                issue_id="I-B3-ROUTE-ADVANCE", type="AUTHORITY", owner="APPROVER",
                message=(f"Không ai còn hạn mức ứng đủ cho số xin "
                         f"{request_amount}; không tự hạ số xin để lọt quyền."),
                refs=route_refs + request_refs, blocked="decision",
            ))
        if proposal_total is not None and not budget_ok:
            issues.append(Issue(
                issue_id="I-B3-ROUTE-BUDGET", type="AUTHORITY", owner="APPROVER",
                message=(f"Dự toán tổng {proposal_total} vượt hạn mức ngân sách "
                         f"của người duyệt; cần exception/quyền đúng, không "
                         f"min(T,B)."),
                refs=route_refs, blocked="decision",
            ))
    route_status = ("PASS" if active_grants and work_ok
                    and (request_amount is None or advance_ok)
                    and (proposal_total is None or budget_ok)
                    else "UNRESOLVED")
    checks.append(CheckResult(
        rule="decision_route", status=route_status, refs=route_refs,
        reason=("Có người đủ quyền cho work/B/advance ở mốc này (pending là "
                "next decision)." if route_status == "PASS" else
                "Tuyến quyền chưa đủ cho nội dung đang xin; route đúng người, "
                "không tự giảm số.")))

    work_permission = ("PENDING_DECISION"
                       if work_ok and not work_decision_refs else "NEEDS_REVIEW")
    advance_approval = ("PENDING_DECISION"
                        if advance_ok and not (pending_refs or approved_refs
                                               or refused_refs)
                        else "NEEDS_REVIEW")

    rules._contradiction_issues(contradictions, issues, checks)
    rules._quality_issues(observations, sorted(
        key for key in all_keys if _is_b3_grammar_key(key)), issues, checks)

    # --- readiness -------------------------------------------------------------
    unresolved_information = any(
        issue.unresolved and issue.owner in ("EMPLOYEE", "ACCOUNTANT")
        and issue.type in ("FACT", "TECHNICAL", "POLICY", "MONEY_INCIDENT")
        for issue in issues)
    unresolved_authority = any(
        issue.unresolved and issue.type == "AUTHORITY" for issue in issues)
    if not intake.confirmed:
        readiness = "DRAFT_CONFIRMATION_REQUIRED"
    elif unresolved_information:
        readiness = "NEEDS_INFORMATION"
    elif unresolved_authority:
        readiness = "NEEDS_AUTHORIZED_REVIEW"
    else:
        readiness = "READY_FOR_ACCOUNTANT_REVIEW"
    completion = ("COMPLETE" if readiness == "READY_FOR_ACCOUNTANT_REVIEW"
                  and not any(issue.unresolved for issue in issues)
                  else "INCOMPLETE")

    next_step = {
        "DRAFT_CONFIRMATION_REQUIRED":
            "Nhân viên xem bản nháp, sửa và xác nhận trước khi nộp B3.",
        "NEEDS_INFORMATION":
            "Xử lý issue theo owner (làm rõ nguồn/khai báo/coverage) rồi "
            "chạy lại phần ảnh hưởng.",
        "NEEDS_AUTHORIZED_REVIEW":
            "Đủ căn cứ để trình; người có quyền xét work/B/advance — "
            "report chưa là phê duyệt.",
        "READY_FOR_ACCOUNTANT_REVIEW":
            "Đủ để kế toán rà soát và trình người đủ quyền quyết định "
            "work/B/advance; chưa phê duyệt, chưa chi.",
    }[readiness]

    # --- field refs -------------------------------------------------------------
    field_refs: dict[str, list[str]] = {}
    for name in ("destination", "trip_start", "trip_end", "purpose",
                 "settlement_due", "request_amount_vnd"):
        refs = [_form_ref(revision, name)]
        for field in _TRIP_FIELDS + ("advance.settlement_due",
                                      "advance.request.amount"):
            if field.rsplit(".", 1)[-1] in name or name.startswith(field):
                refs.extend(ref for ref in resolved.get(field, (None, [], False))[1]
                            if ref not in refs)
        field_refs[name] = refs
    if request_units:
        field_refs["request_amount_vnd"].extend(
            ref for ref in request_refs
            if ref not in field_refs["request_amount_vnd"])
    for row in intake.estimate_rows:
        for side in ("company_vnd", "employee_vnd"):
            field_refs[f"estimate_rows.{row.row_id}.{side}"] = [
                _form_ref(revision, f"estimate_rows.{row.row_id}.{side}")]
    for row_id, row in forecast_rows.items():
        for side in ("company", "employee"):
            key = f"estimate_rows.{row_id}.{side}_vnd"
            refs = [_form_ref(revision, key)] if any(
                r.row_id == row_id for r in intake.estimate_rows) else []
            refs.extend(ref for ref in row["refs"] if ref not in refs)
            field_refs[key] = refs

    accountant_ref = approver_ref = None
    if context is not None:
        for route in context.routes:
            if route.employee_ref == employee_ref:
                accountant_ref = route.accountant_ref
                approver_ref = route.approver_ref

    critical_facts = [rules._fact_state(observations, key)
                      for key in sorted(k for k in all_keys
                                        if _is_b3_grammar_key(k))]

    # Draft IMPORT: proposal.intake mang facts trích xuất (kèm refs ở
    # field_refs) để người nộp xem/sửa rồi xác nhận; bản confirmed giữ
    # nguyên lời khai đã nộp.
    proposal_intake = intake
    if not intake.confirmed and (request_units or forecast_units):
        from datetime import date as _date

        def _as_date(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    return _date.fromisoformat(value)
                except ValueError:
                    return None
            return value if isinstance(value, _date) else None

        trip_source = {field: value_of(field)[0] for field in _TRIP_FIELDS}
        try:
            proposal_intake = B3Intake(
                schema_version="b3-intake-v1",
                intake_method=intake.intake_method,
                confirmed=False,
                destination=trip_source.get("trip.destination")
                or intake.destination,
                trip_start=_as_date(trip_source.get("trip.start"))
                or intake.trip_start,
                trip_end=_as_date(trip_source.get("trip.end"))
                or intake.trip_end,
                purpose=trip_source.get("trip.purpose") or intake.purpose,
                assignment_note=intake.assignment_note,
                request_amount_vnd=(request_amount
                                    if request_units else
                                    intake.request_amount_vnd),
                settlement_due=(_as_date(
                    value_of("advance.settlement_due")[0])
                    or intake.settlement_due),
                estimate_rows=[
                    B3EstimateRow(
                        row_id=rid,
                        description=row["description"] or "",
                        basis=row["basis"],
                        company_vnd=row["company"],
                        employee_vnd=row["employee"],
                    ) for rid, row in sorted(forecast_rows.items())
                ],
            )
        except Exception:
            proposal_intake = intake  # extraction không dựng được form hợp lệ

    proposal = B3Proposal(
        readiness=readiness, intake=proposal_intake,
        forecast_company_vnd=proposal_company,
        forecast_employee_vnd=proposal_employee,
        forecast_total_vnd=proposal_total,
        work_permission=work_permission,  # type: ignore[arg-type]
        advance_approval=advance_approval,  # type: ignore[arg-type]
        accountant_ref=accountant_ref, approver_ref=approver_ref,
        field_refs=field_refs,
    )
    return Report(
        run_id=run_id, job="B3", completion=completion, mode=mode,
        generated_at=datetime.now(timezone.utc),
        components=ReportComponents(
            t=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
            b=ComponentSlot(value=b_value,
                            state="KNOWN" if b_value is not None else "UNKNOWN",
                            refs=b_refs),
            e=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
            a=ComponentSlot(value=a_value,
                            state="KNOWN" if coverage_ok else "UNKNOWN",
                            refs=a_refs),
            ra=ComponentSlot(value=ra_value,
                             state="KNOWN" if coverage_ok else "UNKNOWN",
                             refs=list(coverage_refs)),
            p=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
            rp=ComponentSlot(value=None, state="NOT_APPLICABLE", refs=[]),
        ),
        calculated_net_vnd=None, proposed_net_vnd=None, direction=None,
        expense_rows=[], conditional_results=[],
        checks=checks, issues=issues,
        critical_facts=critical_facts, links=[],
        b3=proposal,
        next_step=next_step,
        source_refs=sorted({s.id for s in run_input.sources}),
    )

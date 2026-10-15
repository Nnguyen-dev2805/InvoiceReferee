"""Pure dossier↔advance/activity linking (server-owned identity; 14/10/2026).

The employee uploads settlement documents and reviews a draft; the BACKEND
decides which advance/work dossier the settlement belongs to. The employee never
picks a standing "activity" code. This module is PURE: no I/O, no model call. It
expresses, with source refs, one of four outcomes:

- ``LINKED``            a strong basis identified exactly one dossier/activity;
- ``NEEDS_CONFIRMATION`` only a weak basis (name/purpose/date/amount) matched, or
  several candidates remain — a human must confirm;
- ``NOT_FOUND``         no basis matched; the draft is accepted as a NEW,
  server-owned dossier (no fabricated budget/grant);
- ``CONFLICT``          strong bases point at DIFFERENT dossiers — the conflict is
  kept, never resolved by priority order or by dropping the contradicting source.

Settlement-to-dossier basis priority (strongest first):
  A. INHERITED            the settlement started from a known advance dossier
                          (a server-owned link on the root).
  B. DOCUMENT_REFERENCE   an advance/dossier number printed on the document,
                          matched in THIS company with a unique namespace.
  C. TRANSACTION_IDENTITY a transaction/voucher code that already exists in the
                          company ledger, matched by a namespaced reference.
  D. WEAK_SIMILARITY      name/purpose/date/amount similarity — candidates only,
                          never an automatic link even when there is just one.

For settlement-to-dossier linking, weak purpose/name similarity remains
candidate-only. Accountant-uploaded advance vouchers use the separate
``link_advance_multifield`` decision: a specific purpose is only one required
signal alongside identity, organization, declared advance, chronology,
transaction ownership and tenant-wide uniqueness. The LLM extracts; code decides,
and the first list element is never taken as the answer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.finance import ActivityLinkSignal
from invoice_referee.source_dates import parse_source_date

LinkStatus = Literal["LINKED", "NEEDS_CONFIRMATION", "NOT_FOUND", "CONFLICT"]
LinkBasis = Literal[
    "INHERITED", "DOCUMENT_REFERENCE", "TRANSACTION_IDENTITY",
    "MULTI_FIELD_MATCH", "WEAK_SIMILARITY"
]

# Order matters: a stronger basis outranks a weaker one when picking the result.
_BASIS_RANK: dict[str, int] = {
    "INHERITED": 4,
    "DOCUMENT_REFERENCE": 3,
    "TRANSACTION_IDENTITY": 2,
    "MULTI_FIELD_MATCH": 2,
    "WEAK_SIMILARITY": 1,
}


@dataclass(frozen=True)
class ActivityCandidate:
    """One catalog activity a settlement could belong to (server-owned)."""

    activity_id: str
    name: str
    status: str = "AUTHORIZED"
    purpose: str | None = None
    # The namespaced reference(s) printed on an advance/dossier for THIS activity
    # (e.g. "TU-2026-001"). A bare number is not a global unique id.
    references: tuple[str, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class LedgerTxn:
    """A company ledger money event used for reference matching (read-only)."""

    external_key: str
    activity: str
    employee: str
    amount: int
    kind: str
    # The namespaced transaction identity: "<namespace>:<reference>"
    # (e.g. "bank:ACB-001", "cash:PC-2026-014"). None when the source has none.
    namespace: str | None = None
    reference: str | None = None
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class LinkCandidate:
    """One dossier/activity the settlement could link to, with its basis."""

    activity_id: str
    name: str
    basis: LinkBasis
    refs: tuple[EvidenceRef, ...] = ()
    amount: int | None = None
    occurred_at: str | None = None
    employee: str | None = None


@dataclass(frozen=True)
class LinkResult:
    """The server's linking decision for one settlement draft."""

    status: LinkStatus
    activity_id: str | None = None
    basis: LinkBasis | None = None
    candidates: tuple[LinkCandidate, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()
    reasons: tuple[str, ...] = ()
    # The material fields the strong bases disagreed on (CONFLICT only).
    conflicting_fields: tuple[str, ...] = ()
    # Who must resolve an open question: "employee" (confirm a link) or
    # "accountant" (a money/identity question). None when nothing is open.
    owner: str | None = None
    requires_confirmation: bool = False
    # True when the result was derived from a server-owned inherited link.
    inherited: bool = False
    signals: tuple[ActivityLinkSignal, ...] = ()
    candidate_count: int = 0


@dataclass(frozen=True)
class AdvanceLinkCandidate:
    """One tenant-scoped settlement dossier considered for an advance."""

    root_id: str
    activity_id: str
    employee_id: str
    employee_name: str
    purpose: str | None
    declared_advance: int | None
    settlement_date: str | None
    declared_name: str | None = None
    source_clear: bool = True
    work_start: str | None = None
    work_end: str | None = None
    ambiguous_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    purpose_refs: tuple[EvidenceRef, ...] = ()
    declared_advance_refs: tuple[EvidenceRef, ...] = ()
    settlement_date_refs: tuple[EvidenceRef, ...] = ()
    employee_refs: tuple[EvidenceRef, ...] = ()
    declared_name_refs: tuple[EvidenceRef, ...] = ()
    reference_refs: tuple[EvidenceRef, ...] = ()
    work_period_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class AdvanceLinkEvidence:
    """Read-only facts from the saved voucher plus server-owned root identity."""

    root_id: str
    activity_id: str
    employee_id: str
    employee_name: str
    employee_name_unique: bool
    expected_company_names: tuple[str, ...]
    payer_name: str | None
    payee_name: str | None
    amount: int | None
    transaction_reference: str | None
    payment_date: str | None
    payment_purpose: str | None
    payer_refs: tuple[EvidenceRef, ...] = ()
    payee_refs: tuple[EvidenceRef, ...] = ()
    amount_refs: tuple[EvidenceRef, ...] = ()
    payment_date_refs: tuple[EvidenceRef, ...] = ()
    payment_purpose_refs: tuple[EvidenceRef, ...] = ()
    activity_reference: str | None = None
    activity_reference_refs: tuple[EvidenceRef, ...] = ()
    transaction_reference_refs: tuple[EvidenceRef, ...] = ()
    transaction_owner_refs: tuple[EvidenceRef, ...] = ()
    mapped_reference_activity: str | None = None
    transaction_owner_root: str | None = None
    transaction_owner_activity: str | None = None
    other_draft_roots: tuple[str, ...] = ()
    ambiguous_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()


def _norm(value: object) -> str:
    """Format-only normalization (case/whitespace/diacritics). No fuzzy match."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


_PURPOSE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("noi", "dung", "chuyen", "tien"),
    ("ung", "tien"),
    ("chi", "phi"),
    ("ve", "viec"),
)
_PURPOSE_GENERIC_TOKENS = frozenset(
    {
        "chi", "phi", "ung", "tien", "chuyen", "khoan", "noi", "dung",
        "ve", "viec", "tiep", "khach", "phuc", "vu", "du", "an",
        "cong", "tac", "lam", "cho", "tai", "muc", "dich", "de",
        "nghi", "thanh", "toan",
    }
)
_MIN_PURPOSE_ANCHOR_TOKENS = 3


def _purpose_core(value: str | None) -> tuple[str, ...]:
    """Return specific project words, excluding common payment/expense boilerplate."""
    text = _norm(value)
    tokens = re.sub(r"[^a-z0-9\s]", " ", text).split()
    while tokens:
        prefix = next((p for p in _PURPOSE_PREFIXES if tuple(tokens[: len(p)]) == p), None)
        if prefix is None:
            break
        tokens = tokens[len(prefix) :]
    return tuple(token for token in tokens if token not in _PURPOSE_GENERIC_TOKENS)


def _link_date(value: str | None) -> date | None:
    return parse_source_date(value)


def link_advance_multifield(
    evidence: AdvanceLinkEvidence,
    candidates: tuple[AdvanceLinkCandidate, ...],
) -> LinkResult:
    """Link a saved advance to one settlement using tenant-scoped source facts.

    This is deliberately stricter than semantic or token similarity. After known
    receipt prefixes and generic business words are removed, the specific purpose
    cores must match exactly and contain at least three distinct anchor tokens.
    Money compares to the paper's declared advance, not its expense total. Time
    checks source chronology only; no arbitrary rolling window is inferred.
    """
    signals: list[ActivityLinkSignal] = []
    conflicts: list[str] = []
    target = next((c for c in candidates if c.root_id == evidence.root_id), None)

    if target is not None and "advance_reference" in target.conflicting_fields:
        signals.append(
            ActivityLinkSignal(
                field="reference",
                state="CONFLICT",
                summary="Các giấy quyết toán ghi mã khoản ứng mâu thuẫn nhau.",
                refs=tuple(dict.fromkeys((
                    *evidence.activity_reference_refs,
                    *target.reference_refs,
                ))),
            )
        )
        conflicts.append("activity")
    elif target is not None and "advance_reference" in target.ambiguous_fields:
        signals.append(
            ActivityLinkSignal(
                field="reference",
                state="AMBIGUOUS",
                summary="Chưa đọc rõ mã khoản ứng trên giấy quyết toán.",
                refs=target.reference_refs,
            )
        )
    elif evidence.mapped_reference_activity is not None:
        mapped_state = (
            "MATCHED"
            if evidence.mapped_reference_activity == evidence.activity_id
            else "CONFLICT"
        )
        signals.append(
            ActivityLinkSignal(
                field="reference",
                state=mapped_state,
                summary=(
                    "Mã khoản ứng khớp hoạt động trong hồ sơ."
                    if mapped_state == "MATCHED"
                    else "Mã khoản ứng đã ánh xạ sang hoạt động khác."
                ),
                refs=evidence.activity_reference_refs,
            )
        )
        if mapped_state == "CONFLICT":
            conflicts.append("activity")
    elif evidence.activity_reference:
        signals.append(
            ActivityLinkSignal(
                field="reference",
                state="UNMAPPED",
                summary="Mã trên biên nhận chưa được ánh xạ; tiếp tục xét căn cứ khác.",
                refs=evidence.activity_reference_refs,
            )
        )
    else:
        signals.append(
            ActivityLinkSignal(
                field="reference",
                state="MISSING",
                summary="Biên nhận không có mã khoản ứng đọc được.",
            )
        )

    transaction_refs = tuple(dict.fromkeys((
        *evidence.transaction_reference_refs,
        *evidence.transaction_owner_refs,
    )))
    if evidence.transaction_owner_root not in (None, evidence.root_id) or (
        evidence.transaction_owner_activity not in (None, evidence.activity_id)
    ):
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="CONFLICT",
                summary="Mã giao dịch đã được ghi nhận trong hồ sơ/hoạt động khác.",
                refs=transaction_refs,
            )
        )
        conflicts.append("transaction")
    elif "transaction_reference" in evidence.conflicting_fields:
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="AMBIGUOUS",
                summary="Biên nhận có nhiều cách đọc mã giao dịch.",
                refs=evidence.transaction_reference_refs,
            )
        )
    elif "transaction_reference" in evidence.ambiguous_fields:
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="AMBIGUOUS",
                summary="Chưa đọc rõ mã giao dịch trên biên nhận.",
                refs=evidence.transaction_reference_refs,
            )
        )
    elif not evidence.transaction_reference:
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="MISSING",
                summary="Thiếu mã giao dịch để chống ghi nhận trùng.",
                refs=evidence.transaction_reference_refs,
            )
        )
    else:
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="MATCHED",
                summary=(
                    "Mã giao dịch đã có trong đúng hồ sơ; ghi lại sẽ không cộng tiền lần hai."
                    if evidence.transaction_owner_root == evidence.root_id
                    or evidence.transaction_owner_activity == evidence.activity_id
                    else "Mã giao dịch có trên chứng từ và chưa thấy dùng ở hồ sơ khác."
                ),
                refs=transaction_refs,
            )
        )
    if evidence.other_draft_roots:
        signals.append(
            ActivityLinkSignal(
                field="transaction",
                state="AMBIGUOUS",
                summary="Mã giao dịch đã có bản nháp ở hồ sơ khác; cần kiểm tra.",
                refs=evidence.transaction_reference_refs,
            )
        )

    payee = _norm(evidence.payee_name)
    expected_employee = _norm(evidence.employee_name)
    declared_name = _norm(target.declared_name) if target is not None else ""
    if "payee_name" in evidence.conflicting_fields or (
        target is not None and "declared_name" in target.conflicting_fields
    ):
        employee_state = "CONFLICT"
        employee_summary = "Các bản đọc ghi nhận tên người nhận/người đề nghị mâu thuẫn nhau."
        conflicts.append("employee")
    elif "payee_name" in evidence.ambiguous_fields or (
        target is not None and "declared_name" in target.ambiguous_fields
    ):
        employee_state = "AMBIGUOUS"
        employee_summary = "Chứng từ có nhiều cách đọc tên người nhận/người đề nghị."
    elif target is not None and target.employee_id != evidence.employee_id:
        employee_state = "CONFLICT"
        employee_summary = "Nhân viên của hồ sơ không khớp danh tính server-owned của hoạt động."
        conflicts.append("employee")
    elif not payee or not expected_employee or not declared_name:
        employee_state = "MISSING"
        employee_summary = "Thiếu tên người nhận hoặc người đề nghị để xác minh nhân viên."
    elif payee != expected_employee or declared_name != expected_employee:
        employee_state = "CONFLICT"
        employee_summary = "Người nhận hoặc người đề nghị không khớp nhân viên hồ sơ."
        conflicts.append("employee")
    elif not evidence.employee_name_unique:
        employee_state = "AMBIGUOUS"
        employee_summary = "Tên người nhận trùng với định danh khác trong tổ chức."
    else:
        employee_state = "MATCHED"
        employee_summary = "Người nhận và người đề nghị khớp nhân viên của hồ sơ."
    if employee_state == "MISSING":
        signals.append(
            ActivityLinkSignal(
                field="employee",
                state=employee_state,
                summary=employee_summary,
                refs=tuple(dict.fromkeys((
                    *evidence.payee_refs,
                    *(target.employee_refs if target is not None else ()),
                    *(target.declared_name_refs if target is not None else ()),
                ))),
            )
        )
    else:
        signals.append(
            ActivityLinkSignal(
                field="employee",
                state=employee_state,
                summary=employee_summary,
                refs=tuple(dict.fromkeys((
                    *evidence.payee_refs,
                    *(target.employee_refs if target is not None else ()),
                    *(target.declared_name_refs if target is not None else ()),
                ))),
            )
        )

    expected_companies = {
        _norm(name) for name in evidence.expected_company_names if _norm(name)
    }
    payer = _norm(evidence.payer_name)
    if "payer_name" in evidence.conflicting_fields:
        signals.append(
            ActivityLinkSignal(
                field="company",
                state="CONFLICT",
                summary="Các bản đọc ghi nhận bên chuyển mâu thuẫn nhau.",
                refs=evidence.payer_refs,
            )
        )
        conflicts.append("company")
    elif "payer_name" in evidence.ambiguous_fields:
        signals.append(
            ActivityLinkSignal(
                field="company",
                state="AMBIGUOUS",
                summary="Chứng từ có nhiều cách đọc tên bên chuyển.",
                refs=evidence.payer_refs,
            )
        )
    elif not payer or not expected_companies:
        signals.append(
            ActivityLinkSignal(
                field="company",
                state="MISSING",
                summary="Chưa đủ căn cứ đối chiếu bên chuyển với nguồn tiền tổ chức.",
                refs=evidence.payer_refs,
            )
        )
    elif payer not in expected_companies:
        signals.append(
            ActivityLinkSignal(
                field="company",
                state="CONFLICT",
                summary="Bên chuyển không khớp tổ chức/nguồn tiền đã cấu hình.",
                refs=evidence.payer_refs,
            )
        )
        conflicts.append("company")
    else:
        signals.append(
            ActivityLinkSignal(
                field="company",
                state="MATCHED",
                summary="Bên chuyển khớp tổ chức đã cấu hình.",
                refs=evidence.payer_refs,
            )
        )

    purpose_core = _purpose_core(evidence.payment_purpose)
    if target is None or target.activity_id != evidence.activity_id:
        signals.append(
            ActivityLinkSignal(
                field="purpose",
                state="MISSING",
                summary="Không tìm thấy giấy quyết toán đã đọc cho hồ sơ này.",
            )
        )
        purpose_core = ()
    else:
        settlement_core = _purpose_core(target.purpose)
        purpose_refs = tuple(dict.fromkeys((
            *evidence.payment_purpose_refs,
            *target.purpose_refs,
        )))
        if "payment_purpose" in evidence.conflicting_fields or "purpose" in target.conflicting_fields:
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="CONFLICT",
                    summary="Các bản đọc ghi nhận nội dung công việc mâu thuẫn nhau.",
                    refs=purpose_refs,
                )
            )
            conflicts.append("purpose")
        elif "payment_purpose" in evidence.ambiguous_fields or "purpose" in target.ambiguous_fields:
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="AMBIGUOUS",
                    summary="Chứng từ có nhiều cách đọc về nội dung công việc.",
                    refs=purpose_refs,
                )
            )
        elif not evidence.payment_purpose or not target.purpose:
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="MISSING",
                    summary="Thiếu nội dung chuyển tiền hoặc mục đích quyết toán.",
                    refs=purpose_refs,
                )
            )
        elif (
            len(set(purpose_core)) < _MIN_PURPOSE_ANCHOR_TOKENS
            or len(set(settlement_core)) < _MIN_PURPOSE_ANCHOR_TOKENS
        ):
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="MISMATCH",
                    summary="Nội dung còn chung chung, chưa có cụm dự án đủ phân biệt.",
                    refs=purpose_refs,
                )
            )
        elif purpose_core != settlement_core:
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="MISMATCH",
                    summary="Nội dung chuyển tiền và mục đích quyết toán khác cụm dự án.",
                    refs=purpose_refs,
                )
            )
        else:
            signals.append(
                ActivityLinkSignal(
                    field="purpose",
                    state="MATCHED",
                    summary="Cụm dự án cụ thể khớp giữa biên nhận và giấy quyết toán.",
                    refs=purpose_refs,
                )
            )
        if not target.source_clear:
            purpose_signal = next(
                (index for index, signal in enumerate(signals) if signal.field == "purpose"),
                None,
            )
            if purpose_signal is not None and signals[purpose_signal].state == "MATCHED":
                signals[purpose_signal] = ActivityLinkSignal(
                    field="purpose",
                    state="MISSING",
                    summary="Giấy quyết toán chưa có đủ trường trọng yếu được đọc rõ.",
                    refs=tuple(dict.fromkeys((
                        *evidence.payment_purpose_refs,
                        *target.purpose_refs,
                    ))),
                )

    amount_refs = tuple(dict.fromkeys((
        *evidence.amount_refs,
        *(target.declared_advance_refs if target is not None else ()),
    )))
    if "amount" in evidence.conflicting_fields or (
        target is not None and "declared_advance" in target.conflicting_fields
    ):
        signals.append(
            ActivityLinkSignal(
                field="advance_amount",
                state="CONFLICT",
                summary="Các bản đọc ghi nhận số tiền ứng mâu thuẫn nhau.",
                refs=amount_refs,
            )
        )
        conflicts.append("advance_amount")
    elif "amount" in evidence.ambiguous_fields or (
        target is not None and "declared_advance" in target.ambiguous_fields
    ):
        signals.append(
            ActivityLinkSignal(
                field="advance_amount",
                state="AMBIGUOUS",
                summary="Chứng từ có nhiều cách đọc về số tiền ứng.",
                refs=amount_refs,
            )
        )
    elif target is None or evidence.amount is None or target.declared_advance is None:
        signals.append(
            ActivityLinkSignal(
                field="advance_amount",
                state="MISSING",
                summary="Thiếu tiền thực nhận hoặc số ứng khai trên giấy quyết toán.",
                refs=amount_refs,
            )
        )
    elif evidence.amount != target.declared_advance:
        signals.append(
            ActivityLinkSignal(
                field="advance_amount",
                state="MISMATCH",
                summary="Tiền thực nhận khác số ứng khai; cần kiểm tra phần nhận/đợt ứng.",
                refs=amount_refs,
            )
        )
    else:
        signals.append(
            ActivityLinkSignal(
                field="advance_amount",
                state="MATCHED",
                summary="Tiền thực nhận khớp số ứng khai trên giấy quyết toán.",
                refs=amount_refs,
            )
        )

    payment_day = _link_date(evidence.payment_date)
    settlement_day = _link_date(target.settlement_date) if target else None
    work_end = _link_date(target.work_end) if target else None
    target_date_conflict = bool(
        target is not None
        and {"document_date", "trip_start", "trip_end"} & set(target.conflicting_fields)
    )
    target_date_ambiguous = bool(
        target is not None
        and {"document_date", "trip_start", "trip_end"} & set(target.ambiguous_fields)
    )
    if "event_at" in evidence.conflicting_fields or target_date_conflict:
        time_state = "CONFLICT"
        time_summary = "Các bản đọc ghi nhận ngày giao dịch/ngày lập giấy mâu thuẫn nhau."
        conflicts.append("time")
    elif "event_at" in evidence.ambiguous_fields or target_date_ambiguous:
        time_state = "AMBIGUOUS"
        time_summary = "Chứng từ có nhiều cách đọc về ngày giao dịch/ngày lập giấy."
    elif not evidence.payment_date or target is None or not target.settlement_date:
        time_state = "MISSING"
        time_summary = "Thiếu ngày giao dịch hoặc ngày lập giấy; không tự điền ngày công tác."
    elif payment_day is None or settlement_day is None or (target.work_end and work_end is None):
        time_state = "MISMATCH"
        time_summary = "Có ngày trên chứng từ nhưng ngày không hợp lệ hoặc chưa hiểu định dạng; cần kiểm tra nguồn."
    elif payment_day > settlement_day or (work_end is not None and payment_day > work_end):
        time_state = "MISMATCH"
        time_summary = "Thứ tự ngày giao dịch chưa phù hợp với giấy/thời gian công việc."
    else:
        time_state = "MATCHED"
        time_summary = "Ngày chuyển có trước ngày lập giấy; ngày hóa đơn không dùng thay ngày công tác."
    signals.append(
        ActivityLinkSignal(
            field="time",
            state=time_state,
            summary=time_summary,
            refs=tuple(dict.fromkeys((
                *evidence.payment_date_refs,
                *(target.settlement_date_refs if target is not None else ()),
                *(target.work_period_refs if target is not None else ()),
            ))),
        )
    )

    signal_refs = tuple(dict.fromkeys(
        ref for signal in signals for ref in signal.refs
    ))
    if conflicts:
        return LinkResult(
            status="CONFLICT",
            refs=signal_refs,
            reasons=("Có mâu thuẫn mạnh về danh tính, tổ chức, mã hoặc giao dịch.",),
            conflicting_fields=tuple(dict.fromkeys(conflicts)),
            owner="accountant",
            signals=tuple(signals),
        )

    possible_roots: set[str] = set()
    if purpose_core and len(set(purpose_core)) >= _MIN_PURPOSE_ANCHOR_TOKENS:
        for candidate in candidates:
            if candidate.employee_id != evidence.employee_id:
                continue
            if _purpose_core(candidate.purpose) == purpose_core:
                possible_roots.add(candidate.root_id)
    possible_roots.update(root for root in evidence.other_draft_roots if root != evidence.root_id)
    candidate_count = len(possible_roots)
    candidate_state = "MATCHED" if candidate_count == 1 else "AMBIGUOUS" if candidate_count > 1 else "MISSING"
    candidate_summary = (
        "Chỉ có một hồ sơ phù hợp trong tenant."
        if candidate_count == 1
        else "Có nhiều hồ sơ cùng phù hợp; cần xác nhận."
        if candidate_count > 1
        else "Chưa xác định được hồ sơ phù hợp."
    )
    signals.append(
        ActivityLinkSignal(
            field="candidates",
            state=candidate_state,
            summary=candidate_summary,
        )
    )

    required_fields = {"employee", "company", "purpose", "advance_amount", "time", "transaction"}
    states = {signal.field: signal.state for signal in signals}
    auto_ready = (
        target is not None
        and target.activity_id == evidence.activity_id
        and evidence.employee_name_unique
        and candidate_count == 1
        and all(states.get(field) == "MATCHED" for field in required_fields)
    )
    if auto_ready:
        basis: LinkBasis = (
            "DOCUMENT_REFERENCE"
            if evidence.mapped_reference_activity == evidence.activity_id
            else "TRANSACTION_IDENTITY"
            if evidence.transaction_owner_root == evidence.root_id
            or evidence.transaction_owner_activity == evidence.activity_id
            else "MULTI_FIELD_MATCH"
        )
        return LinkResult(
            status="LINKED",
            activity_id=evidence.activity_id,
            basis=basis,
            refs=signal_refs,
            reasons=("Tự liên kết bằng danh tính, tổ chức, nội dung, tiền ứng và thời gian.",),
            signals=tuple(signals),
            candidate_count=1,
        )
    return LinkResult(
        status="NEEDS_CONFIRMATION",
        refs=signal_refs,
        reasons=("Chưa đủ căn cứ duy nhất để tự liên kết; kế toán cần kiểm tra phần còn thiếu hoặc mâu thuẫn.",),
        owner="accountant",
        requires_confirmation=True,
        signals=tuple(signals),
        candidate_count=candidate_count,
    )


def _ref_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _refs_match(a: str, b: str) -> bool:
    """Two references name the same document.

    Normalized-equal always matches. A suffix match tolerates a serial prefix
    ("IR26E00000101" vs "00000101": the char before the suffix is a letter), but
    NOT a bare number that is glued to a preceding digit ("001" vs "TU-2026-001"
    → "2026001"): there the "001" is part of a larger number, not its own token.
    """
    na, nb = _ref_key(a), _ref_key(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) < len(nb):
        shorter, longer = na, nb
    elif len(nb) < len(na):
        shorter, longer = nb, na
    else:
        return False
    if not longer.endswith(shorter):
        return False
    # Reject a suffix that is glued to a preceding DIGIT (part of a bigger number).
    preceding = longer[len(longer) - len(shorter) - 1]
    return not preceding.isdigit()


def link_dossier(
    *,
    employee: str,
    current_activity: str | None,
    current_activity_proposed: bool,
    document_references: tuple[str, ...] = (),
    transaction_references: tuple[str, ...] = (),
    catalog: tuple[ActivityCandidate, ...] = (),
    ledger: tuple[LedgerTxn, ...] = (),
    weak_text: str | None = None,
    weak_amount: int | None = None,
    weak_date: str | None = None,
) -> LinkResult:
    """Decide which dossier/activity a settlement belongs to (pure).

    Only strong bases (A/B/C) can produce ``LINKED``; the weak basis (D) can only
    produce candidates. Strong bases pointing at different dossiers produce
    ``CONFLICT`` and are never collapsed by priority order.
    """
    strong: list[LinkCandidate] = []
    reasons: list[str] = []

    # A. INHERITED: a known server-owned link on the root.
    if current_activity and not current_activity_proposed:
        entry = _find_activity(catalog, current_activity)
        strong.append(
            LinkCandidate(
                activity_id=current_activity,
                name=entry.name if entry is not None else current_activity,
                basis="INHERITED",
                refs=entry.refs if entry is not None else (),
                employee=employee,
            )
        )
        reasons.append("Hồ sơ quyết toán kế thừa liên kết tạm ứng đã có trên máy chủ.")

    # B. DOCUMENT_REFERENCE: an advance/dossier number printed on the document.
    for ref in document_references:
        for entry in catalog:
            if any(_refs_match(ref, candidate) for candidate in entry.references):
                strong.append(
                    LinkCandidate(
                        activity_id=entry.activity_id,
                        name=entry.name,
                        basis="DOCUMENT_REFERENCE",
                        refs=entry.refs,
                        employee=employee,
                    )
                )
                reasons.append(
                    f"Số hồ sơ/tạm ứng '{ref}' trên tài liệu khớp hoạt động {entry.activity_id}."
                )

    # C. TRANSACTION_IDENTITY: a namespaced transaction code in the ledger.
    for ref in transaction_references:
        for txn in ledger:
            if txn.reference is None:
                continue
            if _refs_match(ref, txn.reference) or (
                txn.namespace is not None and _refs_match(ref, f"{txn.namespace}:{txn.reference}")
            ):
                strong.append(
                    LinkCandidate(
                        activity_id=txn.activity,
                        name=_activity_name(catalog, txn.activity),
                        basis="TRANSACTION_IDENTITY",
                        refs=txn.refs,
                        amount=txn.amount,
                        employee=txn.employee,
                    )
                )
                reasons.append(
                    f"Mã giao dịch '{ref}' đã có trong lịch sử công ty (hoạt động {txn.activity})."
                )

    # A strong basis to a DIFFERENT employee is a material contradiction, not a
    # link: the settlement's employee must own the linked dossier.
    mismatched = [c for c in strong if c.employee is not None and _norm(c.employee) != _norm(employee)]
    if mismatched:
        return LinkResult(
            status="CONFLICT",
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons) + (
                "Căn cứ mạnh trỏ tới hồ sơ của nhân viên khác; không tự gắn.",
            ),
            conflicting_fields=("employee",),
            owner="accountant",
        )

    distinct = _distinct_activities(strong)
    if len(distinct) > 1:
        # Strong bases to different dossiers: keep the conflict.
        return LinkResult(
            status="CONFLICT",
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons) + (
                "Nhiều căn cứ mạnh trỏ tới các hồ sơ khác nhau; giữ mâu thuẫn để xác minh.",
            ),
            conflicting_fields=("activity",),
            owner="accountant",
        )
    if len(distinct) == 1:
        best = max(strong, key=lambda c: _BASIS_RANK[c.basis])
        return LinkResult(
            status="LINKED",
            activity_id=best.activity_id,
            basis=best.basis,
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons),
            inherited=best.basis == "INHERITED",
        )

    # D. WEAK_SIMILARITY: candidates only, never an automatic link.
    weak = _weak_candidates(
        catalog, text=weak_text, amount=weak_amount, date=weak_date, employee=employee
    )
    if weak:
        return LinkResult(
            status="NEEDS_CONFIRMATION",
            candidates=weak,
            refs=tuple(r for c in weak for r in c.refs),
            reasons=(
                "Chỉ có căn cứ yếu (tên/nội dung/ngày/số tiền); cần người xác nhận.",
            ),
            owner="employee",
            requires_confirmation=True,
        )

    return LinkResult(
        status="NOT_FOUND",
        reasons=("Không tìm thấy hồ sơ tạm ứng/công việc khớp; tiếp nhận hồ sơ độc lập.",),
    )


def _find_activity(
    catalog: tuple[ActivityCandidate, ...], activity_id: str
) -> ActivityCandidate | None:
    for entry in catalog:
        if entry.activity_id == activity_id:
            return entry
    return None


def _activity_name(catalog: tuple[ActivityCandidate, ...], activity_id: str) -> str:
    entry = _find_activity(catalog, activity_id)
    return entry.name if entry is not None else activity_id


def _distinct_activities(candidates: list[LinkCandidate]) -> set[str]:
    return {c.activity_id for c in candidates}


def _dedupe(candidates: list[LinkCandidate]) -> list[LinkCandidate]:
    seen: set[tuple[str, str]] = set()
    out: list[LinkCandidate] = []
    for c in candidates:
        key = (c.activity_id, c.basis)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _all_refs(candidates: list[LinkCandidate]) -> tuple[EvidenceRef, ...]:
    return tuple(r for c in candidates for r in c.refs)


def _weak_candidates(
    catalog: tuple[ActivityCandidate, ...],
    *,
    text: str | None,
    amount: int | None,
    date: str | None,
    employee: str,
) -> tuple[LinkCandidate, ...]:
    """Name/purpose similarity candidates. Never an automatic link, even if one.

    A weak match is a human-confirmable candidate: the purpose/name overlaps the
    activity's purpose/name. Amount/date are comparison metadata, not identity.
    """
    if not text:
        return ()
    needle = _norm(text)
    if not needle:
        return ()
    out: list[LinkCandidate] = []
    for entry in catalog:
        haystacks = [entry.name, entry.purpose or ""]
        if any(needle == _norm(h) for h in haystacks if h):
            out.append(
                LinkCandidate(
                    activity_id=entry.activity_id,
                    name=entry.name,
                    basis="WEAK_SIMILARITY",
                    refs=entry.refs,
                    amount=amount,
                    occurred_at=date,
                    employee=employee,
                )
            )
    return tuple(out)

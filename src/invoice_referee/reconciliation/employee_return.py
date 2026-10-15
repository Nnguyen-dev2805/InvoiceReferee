"""Source-backed matching for an employee return against one collect instruction."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Literal

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.finance import MoneyMovementSignal

ReturnMatchStatus = Literal[
    "MATCHED", "OVERPAY", "NEEDS_REVIEW", "CONFLICT", "NOT_COMPLETED",
    "STALE", "ALREADY_RECORDED",
]


@dataclass(frozen=True)
class EmployeeReturnMatch:
    status: ReturnMatchStatus
    signals: tuple[MoneyMovementSignal, ...]


def _normalize_party(value: str | None) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(
        "".join(character for character in text.casefold() if character.isalnum() or character.isspace()).split()
    )


def read_field(document, name: str):
    """Return one unambiguous source field and all of its evidence refs."""
    candidates = [field for field in document.fields if field.field == name]
    refs = tuple(dict.fromkeys(ref for field in candidates for ref in field.refs))
    if any(field.state == "AMBIGUOUS" for field in candidates):
        return None, refs, "ambiguous"
    found = [field for field in candidates if field.state == "FOUND"]
    values = {_normalize_party(str(field.value)) for field in found}
    if len(values) > 1:
        return None, refs, "conflict"
    if not found:
        return None, refs, None
    return found[0].value, refs, None


def match_employee_return(
    *,
    root_id: str,
    instruction_id: str,
    instruction_active: bool,
    instruction_remaining: int,
    instruction_date: date,
    as_of: date,
    employee_name: str | None,
    company_name: str | None,
    payer_name: str | None,
    payee_name: str | None,
    amount: int | None,
    event_date: date | None,
    transaction_reference: str | None,
    instrument_status: str,
    ambiguous_fields: tuple[str, ...] = (),
    conflicting_fields: tuple[str, ...] = (),
    transaction_owner_root: str | None = None,
    already_recorded: bool = False,
    field_refs: dict[str, tuple[EvidenceRef, ...]] | None = None,
) -> EmployeeReturnMatch:
    """Compare the employee's transfer proof with the currently issued COLLECT.

    No fuzzy party matching or date window is used. A partial receipt is valid;
    a surplus remains visible as OVERPAY and is never clipped in the ledger.
    """
    signals: list[MoneyMovementSignal] = []
    evidence_refs = field_refs or {}
    conflicts = False
    needs_review = False

    if not instruction_active:
        signals.append(MoneyMovementSignal(
            field="instruction", state="STALE",
            summary="Lệnh thu đã hoàn tất hoặc không còn hiệu lực.",
        ))
    else:
        signals.append(MoneyMovementSignal(
            field="instruction", state="MATCHED",
            summary=f"Chứng từ được đối chiếu với lệnh thu còn lại {instruction_remaining:,} VND.",
        ))

    for field_name, value, expected, label in (
        ("payer_name", payer_name, employee_name, "bên chuyển/nhân viên"),
        ("payee_name", payee_name, company_name, "bên nhận/công ty"),
    ):
        signal_field = "payer" if field_name == "payer_name" else "payee"
        if field_name in conflicting_fields:
            state = "CONFLICT"
            summary = f"Các bản đọc ghi nhận {label} mâu thuẫn nhau."
            conflicts = True
        elif field_name in ambiguous_fields:
            state = "AMBIGUOUS"
            summary = f"Chưa đọc rõ {label} trên chứng từ hoàn trả."
            needs_review = True
        elif not value or not expected:
            state = "MISSING"
            summary = f"Thiếu {label} để đối chiếu giao dịch hoàn trả."
            needs_review = True
        elif _normalize_party(value) != _normalize_party(expected):
            state = "CONFLICT"
            summary = f"{label.capitalize()} trên chứng từ không khớp hồ sơ."
            conflicts = True
        else:
            state = "MATCHED"
            summary = f"{label.capitalize()} khớp hồ sơ."
        signals.append(MoneyMovementSignal(
            field=signal_field,
            state=state,
            summary=summary,
            refs=evidence_refs.get(field_name, ()),
        ))

    overpay = False
    if "amount" in conflicting_fields:
        signals.append(MoneyMovementSignal(
            field="amount", state="CONFLICT", summary="Các bản đọc ghi nhận số tiền hoàn mâu thuẫn.",
            refs=evidence_refs.get("amount", ()),
        ))
        conflicts = True
    elif "amount" in ambiguous_fields:
        signals.append(MoneyMovementSignal(
            field="amount", state="AMBIGUOUS", summary="Chưa đọc rõ số tiền hoàn trên chứng từ.",
            refs=evidence_refs.get("amount", ()),
        ))
        needs_review = True
    elif amount is None or amount <= 0:
        signals.append(MoneyMovementSignal(
            field="amount", state="MISSING", summary="Thiếu số tiền thực chuyển trên chứng từ.",
            refs=evidence_refs.get("amount", ()),
        ))
        needs_review = True
    elif amount > instruction_remaining:
        signals.append(MoneyMovementSignal(
            field="amount", state="OVERPAY",
            summary=f"Số hoàn {amount:,} VND vượt lệnh thu còn {instruction_remaining:,} VND.",
            refs=evidence_refs.get("amount", ()),
        ))
        overpay = True
    else:
        signals.append(MoneyMovementSignal(
            field="amount", state="MATCHED",
            summary=f"Số tiền khớp phần lệnh thu còn lại {instruction_remaining:,} VND.",
            refs=evidence_refs.get("amount", ()),
        ))

    if "event_at" in conflicting_fields:
        date_state, date_summary = "CONFLICT", "Các bản đọc ghi nhận ngày giao dịch mâu thuẫn."
        conflicts = True
    elif "event_at" in ambiguous_fields:
        date_state, date_summary = "AMBIGUOUS", "Chưa đọc rõ ngày giao dịch trên chứng từ hoàn trả."
        needs_review = True
    elif event_date is None:
        date_state, date_summary = "MISSING", "Thiếu ngày giao dịch trên chứng từ hoàn trả."
        needs_review = True
    elif event_date < instruction_date or event_date > as_of:
        date_state, date_summary = "MISMATCH", "Ngày chuyển chưa hợp lý với thời điểm lệnh thu/hệ thống."
        needs_review = True
    else:
        date_state, date_summary = "MATCHED", "Ngày giao dịch được đọc rõ sau khi có lệnh thu."
    signals.append(MoneyMovementSignal(
        field="event_at",
        state=date_state,
        summary=date_summary,
        refs=evidence_refs.get("event_at", ()),
    ))

    if transaction_owner_root not in (None, root_id):
        transaction_state, transaction_summary = "CONFLICT", "Mã giao dịch đã thuộc hồ sơ khác."
        conflicts = True
    elif "transaction_reference" in conflicting_fields:
        transaction_state, transaction_summary = "CONFLICT", "Các bản đọc ghi mã giao dịch mâu thuẫn."
        conflicts = True
    elif "transaction_reference" in ambiguous_fields:
        transaction_state, transaction_summary = "AMBIGUOUS", "Chưa đọc rõ mã giao dịch hoàn trả."
        needs_review = True
    elif not transaction_reference or not transaction_reference.strip():
        transaction_state, transaction_summary = "MISSING", "Thiếu mã giao dịch để chống ghi nhận trùng."
        needs_review = True
    else:
        transaction_state, transaction_summary = "MATCHED", "Đã đọc mã giao dịch trên chứng từ."
    signals.append(MoneyMovementSignal(
        field="transaction", state=transaction_state, summary=transaction_summary,
        refs=evidence_refs.get("transaction_reference", ()),
    ))

    if instrument_status != "COMPLETED":
        status_state, status_summary = "NOT_COMPLETED", "Giao dịch chưa hoàn tất; chưa thể ghi tiền công ty đã nhận."
    else:
        status_state, status_summary = "MATCHED", "Chứng từ ghi giao dịch hoàn tất."
    signals.append(MoneyMovementSignal(
        field="source_status", state=status_state, summary=status_summary,
        refs=evidence_refs.get("transaction_status", ()),
    ))

    if conflicts:
        status: ReturnMatchStatus = "CONFLICT"
    elif not instruction_active:
        status = "STALE"
    elif already_recorded:
        status = "ALREADY_RECORDED"
    elif instrument_status != "COMPLETED":
        status = "NOT_COMPLETED"
    elif needs_review:
        status = "NEEDS_REVIEW"
    elif overpay:
        status = "OVERPAY"
    else:
        status = "MATCHED"
    return EmployeeReturnMatch(status=status, signals=tuple(signals))

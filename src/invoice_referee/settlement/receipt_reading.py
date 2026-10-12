"""Deterministic draft builder for a B5 advance-receipt read (b3-intake-v1).

The reader returns raw ``Observation`` facts; this module turns them into a
``B3ReceiptReadView``: a normalized *proposal* plus review *warnings*. It is
pure Python — no provider, no LLM decision. The proposal suggests; the
accountant edits; the existing ``record_receipt`` guard is the only place that
classifies a real receipt and moves money.

Rules kept explicit (spec §A/§B):
- A name that merely looks like the employee does NOT prove the same person:
  the proposal only sets ``payee_ref`` to the employee when the raw name
  matches the fixture name exactly; a similar-but-different name stays ``OTHER``
  with a warning.
- "Lập lệnh thành công"/"Paid" chung chung/only sender-debit never become
  RECEIVER_CONFIRMED. Cash approval or a pre-printed name is not a handover.
- A missing/unclear fact stays None — the approved amount or profile is never
  used to fill it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from invoice_referee.settlement.contracts.receipt import (
    B3ReceiptFact,
    B3ReceiptProposal,
    B3ReceiptReadView,
    B3ReceiptWarning,
)
from invoice_referee.settlement.models import Observation

# Fields the reader must return for a receipt read (grammar = RECEIPT_KEYS).
_AMOUNT_KEYS = ("receipt.amount",)
_TEXT_KEYS = (
    "receipt.currency", "receipt.payer_name", "receipt.receiver_name",
    "receipt.event_ref", "receipt.narrative", "receipt.outcome_text",
    "receipt.proof_scope", "receipt.bank_name", "receipt.sender_account",
    "receipt.recipient_bank", "receipt.recipient_account",
    "receipt.voucher_number", "receipt.handed_by_name",
    "receipt.acknowledgement",
)


def _read_map(observations: list[Observation]) -> dict[str, Observation]:
    """Last READ observation per key wins (one value per key for the draft)."""
    result: dict[str, Observation] = {}
    for observation in observations:
        if observation.key.startswith("receipt.") and \
                observation.read_state == "READ":
            result[observation.key] = observation
    return result


def _fact(observation: Observation) -> B3ReceiptFact:
    quote = None
    if observation.basis and "trích: " in observation.basis:
        quote = observation.basis.split("trích: ", 1)[1]
    return B3ReceiptFact(
        key=observation.key, raw=observation.raw,
        value=observation.value if isinstance(
            observation.value, (int, str)) else None,
        read_state=observation.read_state, locator=observation.locator,
        page=observation.page, quote=quote or observation.raw,
    )


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _norm_name(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def build_receipt_draft(
    *,
    read_id: str,
    case_id: str,
    source_id: str,
    filename: str,
    reader_mode: str,
    created_at: datetime,
    observations: list[Observation],
    method: str,
    employee_ref: str,
    employee_name: str | None,
    approved_vnd: int | None,
    remaining_vnd: int | None,
    recorded_received_vnd: int | None,
) -> B3ReceiptReadView:
    """Assemble the stored draft read from raw observations (pure function)."""
    by_key = _read_map(observations)
    facts = [_fact(by_key[k]) for k in sorted(by_key)]
    warnings: list[B3ReceiptWarning] = []

    def text(key: str) -> str | None:
        observation = by_key.get(key)
        if observation is None:
            return None
        value = observation.value
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
        return None

    amount: int | None = None
    amount_observation = by_key.get("receipt.amount")
    if amount_observation is not None and isinstance(
            amount_observation.value, int) and not isinstance(
            amount_observation.value, bool):
        amount = amount_observation.value
    elif amount_observation is not None:
        warnings.append(B3ReceiptWarning(
            code="AMOUNT_UNCLEAR", field="receipt.amount",
            message="Số tiền chưa đọc rõ; nhập tay theo nguồn nếu cần."))

    currency = text("receipt.currency")
    receiver_name = text("receipt.receiver_name")
    payer_name = text("receipt.payer_name")
    event_at = _parse_instant(by_key["receipt.event_at"].value
                              if "receipt.event_at" in by_key else None)
    event_ref = text("receipt.event_ref")
    narrative = text("receipt.narrative")
    outcome_text = text("receipt.outcome_text")
    proof_scope = text("receipt.proof_scope")
    acknowledgement = text("receipt.acknowledgement")
    voucher_number = text("receipt.voucher_number")
    handed_by_name = text("receipt.handed_by_name")

    # Method: bank vs cash by the fields actually read, never by assumption.
    if method == "CASH":
        if voucher_number is None:
            warnings.append(B3ReceiptWarning(
                code="VOUCHER_MISSING", field="receipt.voucher_number",
                message="Chưa đọc được số phiếu chi; đối chiếu với nguồn."))
        if acknowledgement != "ACKNOWLEDGED":
            warnings.append(B3ReceiptWarning(
                code="CASH_NOT_HANDED", field="receipt.acknowledgement",
                message="Phiếu chưa có xác nhận giao/nhận tiền; chưa đủ căn "
                        "cứ để ghi đã nhận."))
    else:
        if proof_scope != "RECEIVER_CONFIRMED":
            warnings.append(B3ReceiptWarning(
                code="BANK_SCOPE_NOT_RECEIVER", field="receipt.proof_scope",
                message="Chứng từ chưa đủ căn cứ người hưởng nhận (mới lập "
                        "lệnh hoặc chỉ trích nợ bên gửi)."))

    # Payee matching: exact fixture-name match only; similar ≠ same person.
    payee_ref: str | None = None
    if receiver_name is not None:
        if employee_name is not None and \
                _norm_name(receiver_name) == _norm_name(employee_name):
            payee_ref = employee_ref
        else:
            payee_ref = "OTHER"
            warnings.append(B3ReceiptWarning(
                code="RECEIVER_NOT_MATCHED", field="receipt.receiver_name",
                message=f"Người nhận “{receiver_name}” không khớp tên nhân "
                        f"viên hồ sơ; kế toán xác minh trước khi ghi."))

    # Amount vs the remaining obligation (comparison only; never clip).
    if amount is not None and remaining_vnd is not None and amount > remaining_vnd:
        warnings.append(B3ReceiptWarning(
            code="AMOUNT_EXCEEDS_REMAINING", field="receipt.amount",
            message=f"Số đọc {amount:,} vượt phần còn lại "
                    f"{remaining_vnd:,}; giữ raw, kế toán xử lý phần vượt."
            .replace(",", ".")))
    if recorded_received_vnd is not None and event_ref is not None:
        warnings.append(B3ReceiptWarning(
            code="EVENT_MAYBE_DUPLICATE", field="receipt.event_ref",
            message="Hồ sơ đã có sự kiện thực nhận; kiểm tra mã giao dịch để "
                    "tránh ghi trùng."))

    # Classification hint from scope only (never a decision).
    if method == "BANK_TRANSFER":
        hint = {
            "RECEIVER_CONFIRMED": "CONFIRMED_RECEIPT",
            "SENDER_DEBIT": "UNCONFIRMED",
            "ORDER_ONLY": "UNCONFIRMED",
        }.get(proof_scope or "", "UNCONFIRMED")
    else:
        hint = "CONFIRMED_RECEIPT" if acknowledgement == "ACKNOWLEDGED" \
            else "UNCONFIRMED"

    proposal = B3ReceiptProposal(
        amount_vnd=amount, currency=currency,
        payer_side="COMPANY" if payer_name else "UNKNOWN",
        payee_ref=payee_ref, receiver_name=receiver_name, payer_name=payer_name,
        event_at=event_at, event_ref=event_ref, narrative=narrative,
        outcome_text=outcome_text, method=method,  # type: ignore[arg-type]
        proof_scope=proof_scope if proof_scope in (
            "ORDER_ONLY", "SENDER_DEBIT", "RECEIVER_CONFIRMED",
            "UNCONFIRMED") else None,  # type: ignore[arg-type]
        acknowledgement=acknowledgement if acknowledgement in (
            "ACKNOWLEDGED", "NOT_HANDED", "UNCONFIRMED") else None,
        voucher_number=voucher_number, handed_by_name=handed_by_name,
        bank_name=text("receipt.bank_name"),
        sender_account=text("receipt.sender_account"),
        recipient_bank=text("receipt.recipient_bank"),
        recipient_account=text("receipt.recipient_account"),
        classification_hint=hint,  # type: ignore[arg-type]
    )

    status = "READ" if facts else "PARTIAL"
    return B3ReceiptReadView(
        id=read_id, case_id=case_id, source_id=source_id, filename=filename,
        status=status, reader_mode=reader_mode, created_at=created_at,
        facts=facts, proposal=proposal, warnings=warnings,
    )

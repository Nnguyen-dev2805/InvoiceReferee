"""Pure mapper: a read document -> a prefilled "record advance received" draft.

The accountant's "Ghi nhận tiền ứng thực nhận" form reads a transfer receipt or a
cash voucher and prefills the fields it can prove. This is PURE: no I/O, no model
call, no mutation. It never invents a value (a missing amount is None and flagged,
never zero), and it never asserts that money was received — the draft always
requires the accountant's responsible confirmation, and the SERVER decides
verification when the actual event is recorded.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from invoice_referee.domain.common import EvidenceRef, parse_vnd
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate

AdvanceMethod = Literal["TRANSFER", "CASH"]
AdvanceStatus = Literal["COMPLETED", "PENDING", "FAILED", "UNKNOWN"]

# The field vocabulary the read may expose for an instrument document.
_STATUS_MAP: dict[str, AdvanceStatus] = {
    "completed": "COMPLETED",
    "hoàn tất": "COMPLETED",
    "thành công": "COMPLETED",
    "đã nhận": "COMPLETED",
    "đã giao": "COMPLETED",
    "pending": "PENDING",
    "đang xử lý": "PENDING",
    "chờ xử lý": "PENDING",
    "failed": "FAILED",
    "thất bại": "FAILED",
    "lỗi": "FAILED",
}


class AdvanceDraft(NamedTuple):
    """A prefilled, uncommitted proposal for the accountant to review/confirm."""

    source_id: str
    scope: str
    employee: str
    amount: int | None
    payer_name: str | None
    payee_name: str | None
    transaction_reference: str | None
    instrument_method: AdvanceMethod | None
    instrument_status: AdvanceStatus
    event_at: str | None
    refs: tuple[EvidenceRef, ...]
    missing_fields: tuple[str, ...]
    requires_confirmation: bool = True


def _field(document: DocumentAnalysis, name: str) -> FieldCandidate | None:
    for candidate in document.fields:
        if candidate.field == name:
            return candidate
    return None


def _found_value(document: DocumentAnalysis, *names: str) -> object | None:
    """The first FOUND value among the candidate field names.

    A transfer receipt reads as PAYMENT_PROOF (canonical `amount`,
    `transaction_reference`, `payee_name`, `transaction_status`); a cash voucher
    may read as a receipt-like document (`total_amount`, `document_number`,
    `payment_confirmation_text`). The mapper reads the union so a clearly-read
    field is prefilled instead of forcing the accountant to retype it.
    """
    for name in names:
        candidate = _field(document, name)
        if candidate is not None and candidate.state == "FOUND":
            return candidate.value
    return None


def _refs(document: DocumentAnalysis) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    for candidate in document.fields:
        if candidate.state == "FOUND":
            refs.extend(candidate.refs)
    return tuple(refs)


def _status(document: DocumentAnalysis) -> AdvanceStatus:
    raw = _found_value(document, "transaction_status")
    if raw is not None:
        text = str(raw).strip().casefold()
        for token, status in _STATUS_MAP.items():
            if token in text:
                return status
    # A receipt-like cash voucher may state the handover in
    # `payment_confirmation_text` ("Số tiền đã giao … đã nhận …"); a stated
    # handover is COMPLETED, otherwise the status stays UNKNOWN.
    confirmation = _found_value(
        document, "payment_confirmation_text", "collection_reason"
    )
    if confirmation is not None:
        text = str(confirmation).casefold()
        if "đã nhận" in text or "đã giao" in text or "hoàn tất" in text:
            return "COMPLETED"
    return "UNKNOWN"


def _method(
    document: DocumentAnalysis, method_hint: str | None
) -> AdvanceMethod | None:
    if method_hint in ("TRANSFER", "CASH"):
        return method_hint  # type: ignore[return-value]
    # A payment proof that names a provider/account implies a transfer; a
    # document typed as a cash voucher implies cash. Absent a signal, unknown.
    text = " ".join(
        str(c.value) for c in document.fields if c.state == "FOUND"
    ).casefold()
    if any(
        token in text for token in ("chuyển khoản", "transfer", "ngân hàng", "bank")
    ):
        return "TRANSFER"
    if any(token in text for token in ("tiền mặt", "cash", "phiếu chi")):
        return "CASH"
    return None


def draft_advance_from_document(
    document: DocumentAnalysis,
    *,
    scope: str,
    employee: str,
    method_hint: str | None = None,
) -> AdvanceDraft:
    """Prefill an advance-received draft from one read document (pure)."""
    amount = parse_vnd(_found_value(document, "amount", "total_amount"))
    payer_name = _found_value(document, "payer_name", "issuer_name")
    # The receiver stays unresolved when the document does not name one: the
    # server must NOT substitute the dossier employee and pretend it matched
    # (14/10/2026). The accountant resolves the missing payee with evidence.
    payee_name = _found_value(document, "payee_name", "buyer_person_name")
    reference = _found_value(document, "transaction_reference", "document_number")
    event_at = _found_value(document, "event_at", "document_date")

    missing: list[str] = []
    if amount is None:
        missing.append("amount")
    if payee_name is None:
        missing.append("payee_name")
    if reference is None:
        missing.append("transaction_reference")
    if _status(document) == "UNKNOWN":
        missing.append("instrument_status")

    return AdvanceDraft(
        source_id=document.source_id,
        scope=scope,
        employee=employee,
        amount=amount,
        payer_name=str(payer_name) if payer_name is not None else None,
        payee_name=str(payee_name) if payee_name is not None else None,
        transaction_reference=str(reference) if reference is not None else None,
        instrument_method=_method(document, method_hint),
        instrument_status=_status(document),
        event_at=str(event_at) if event_at is not None else None,
        refs=_refs(document),
        missing_fields=tuple(missing),
    )

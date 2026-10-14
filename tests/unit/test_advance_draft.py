"""D: prefill the "record advance received" draft from a read document.

The accountant uploads a transfer receipt or cash voucher; the pipeline reads it
and produces a DRAFT (prefilled fields, never a committed event). A field that is
clearly read is prefilled; a missing/ambiguous field is flagged, not guessed. The
draft never invents a value and never sets a "received" state.
"""

from __future__ import annotations

from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.reconciliation.advance import draft_advance_from_document

SHA = "a" * 64


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _doc(*fields: FieldCandidate, dtype: str = "PAYMENT_PROOF") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:" + dtype, document_type=dtype,  # type: ignore[arg-type]
        roles=("PAYMENT_EVIDENCE",), page_range=(1, 1), fields=tuple(fields),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def test_transfer_receipt_prefills_the_draft() -> None:
    doc = _doc(
        _found("transaction_reference", "FT-UC03-F01-0001"),
        _found("transaction_status", "COMPLETED"),
        _found("payer_name", "Công ty InvoiceReferee"),
        _found("payee_name", "Nguyễn An"),
        _found("amount", "4.000.000 đ"),
        _found("event_at", "2026-10-05"),
        _found("payment_provider", "Ngân hàng Demo"),
    )
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a")
    assert draft.amount == 4_000_000
    assert draft.payer_name == "Công ty InvoiceReferee"
    assert draft.payee_name == "Nguyễn An"
    assert draft.transaction_reference == "FT-UC03-F01-0001"
    assert draft.instrument_status == "COMPLETED"
    assert draft.instrument_method == "TRANSFER"
    assert draft.missing_fields == ()
    assert draft.source_id == "source:1"
    assert draft.refs, "the draft must carry the source ref of the read fields"


def test_cash_voucher_infers_cash_method() -> None:
    doc = _doc(
        _found("transaction_reference", "PC-UC03-F01-0001"),
        _found("transaction_status", "COMPLETED"),
        _found("payee_name", "Nguyễn An"),
        _found("amount", "4.000.000 đ"),
        dtype="OTHER",
    )
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a", method_hint="CASH")
    assert draft.instrument_method == "CASH"
    assert draft.amount == 4_000_000


def test_missing_amount_is_flagged_not_zero() -> None:
    doc = _doc(
        _found("transaction_reference", "FT-1"),
        _found("payee_name", "Nguyễn An"),
    )
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a")
    assert draft.amount is None
    assert "amount" in draft.missing_fields
    assert draft.transaction_reference == "FT-1"


def test_unreadable_status_is_not_completed() -> None:
    doc = _doc(
        _found("amount", "4.000.000 đ"),
        FieldCandidate(field="transaction_status", state="UNREADABLE"),
    )
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a")
    assert draft.instrument_status != "COMPLETED"


def test_draft_carries_no_received_state() -> None:
    # A draft is a proposal; it must not claim money was received.
    doc = _doc(_found("amount", "4.000.000 đ"), _found("transaction_status", "COMPLETED"))
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a")
    assert draft.requires_confirmation is True


def test_receipt_like_cash_voucher_is_prefilled() -> None:
    # A real model reads the cash voucher as a receipt-like document
    # (COLLECTION_RECEIPT): total_amount/document_number/payment_confirmation_text.
    # The mapper must read that vocabulary, not force the accountant to retype.
    doc = _doc(
        _found("issuer_name", "Công ty InvoiceReferee"),
        _found("document_number", "PC-UC03-F01-0001"),
        _found("document_date", "05/10/2026"),
        _found("total_amount", "4.000.000 đ"),
        _found("payment_confirmation_text", "Số tiền đã giao 4.000.000 đ Số tiền đã nhận 4.000.000 đ"),
        dtype="COLLECTION_RECEIPT",
    )
    draft = draft_advance_from_document(doc, scope="activity:uc03-f01", employee="employee:employee-a", method_hint="CASH")
    assert draft.amount == 4_000_000
    assert draft.transaction_reference == "PC-UC03-F01-0001"
    assert draft.payer_name == "Công ty InvoiceReferee"
    assert draft.instrument_status == "COMPLETED"
    assert draft.instrument_method == "CASH"
    assert draft.missing_fields == ()

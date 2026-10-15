"""Pure settlement-draft mapper: ReadResult -> the employee review draft.

This replaces the pypdf+regex draft path (report P1-1). The draft the employee
reviews is derived from the SAME typed evidence report the reconciler consumes, so
a PDF with text, a scanned PDF and a PNG/JPEG all go through the one OCR pipeline.
It is PURE: no I/O, no model call.

Rules:
- a FOUND field becomes a filled value; a field that is not FOUND stays None
  (never a fabricated 0 or a demo fact) and is recorded in `field_states`;
- a row's amount/refs come from the settlement form; its `matched_invoice` is set
  only from a real evidence LINK (never a guessed file);
- no trip fields are invented for a non-travel paper.
"""

from __future__ import annotations

from typing import Any

from invoice_referee.domain.common import parse_vnd
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate
from invoice_referee.domain.evidence import ReadResult, SourceRef
from invoice_referee.reconciliation.document_arithmetic import (
    check_document_arithmetic,
    is_settlement_summary_row,
)

# The settlement-form fields the review screen surfaces.
_SURFACED_FIELDS = (
    "declared_name",
    "trip_destination",
    "purpose",
    "trip_start",
    "trip_end",
    "printed_total",
    "declared_advance",
)


def _field(document: DocumentAnalysis, name: str) -> FieldCandidate | None:
    for candidate in document.fields:
        if candidate.field == name:
            return candidate
    return None


def _found(document: DocumentAnalysis, name: str) -> Any:
    candidate = _field(document, name)
    if candidate is not None and candidate.state == "FOUND":
        return candidate.value
    return None


def _line_candidate(line, name: str) -> FieldCandidate | None:
    for candidate in line.fields:
        if candidate.field == name:
            return candidate
    return None


def _line_field(line, name: str) -> Any:
    candidate = _line_candidate(line, name)
    return candidate.value if candidate is not None and candidate.state == "FOUND" else None


def _refs(line) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for candidate in line.fields:
        refs = list(candidate.refs)
        for alternative in candidate.alternatives:
            refs.extend(alternative.refs)
        for ref in refs:
            out.append(ref.model_dump(mode="json"))
    for ref in line.refs:
        out.append(ref.model_dump(mode="json"))
    return out


def _paper(report: ReadResult) -> DocumentAnalysis | None:
    return next((d for d in report.documents if d.document_type == "SETTLEMENT_FORM"), None)


def _filename_by_source(sources: tuple[SourceRef, ...]) -> dict[str, str]:
    return {source.id: (source.filename or source.id) for source in sources}


def _matched_by_document(report: ReadResult) -> dict[str, str]:
    """document_id -> source_id for AUTO_LINK evidence only (a verified link)."""
    out: dict[str, str] = {}
    for link in report.links:
        if link.status == "AUTO_LINK":
            out[link.document_id] = link.source_id
    return out


def _suggested_by_document(report: ReadResult) -> dict[str, str]:
    """document_id -> source_id for SUGGEST_LINK evidence (unconfirmed)."""
    out: dict[str, str] = {}
    for link in report.links:
        if link.status == "SUGGEST_LINK":
            out[link.document_id] = link.source_id
    return out


def build_settlement_draft(
    report: ReadResult, *, sources: tuple[SourceRef, ...] = ()
) -> dict[str, object]:
    """Map the typed evidence report into the employee review draft (pure)."""
    paper = _paper(report)
    names = _filename_by_source(sources)

    field_states: dict[str, str] = {}
    for name in _SURFACED_FIELDS:
        candidate = _field(paper, name) if paper is not None else None
        field_states[name] = candidate.state if candidate is not None else "NOT_PRESENT"

    declared_name = _found(paper, "declared_name") if paper is not None else None
    destination = _found(paper, "trip_destination") if paper is not None else None
    purpose = _found(paper, "purpose") if paper is not None else None
    trip_start = _found(paper, "trip_start") if paper is not None else None
    trip_end = _found(paper, "trip_end") if paper is not None else None
    printed_total = parse_vnd(_found(paper, "printed_total")) if paper is not None else None
    declared_advance = parse_vnd(_found(paper, "declared_advance")) if paper is not None else None

    # invoice document_id -> matched source filename (only for a real AUTO_LINK);
    # a SUGGEST_LINK is surfaced separately as an unconfirmed suggestion.
    matched = _matched_by_document(report)
    suggested = _suggested_by_document(report)
    doc_by_id = {d.document_id: d for d in report.documents}

    expenses: list[dict[str, object]] = []
    if paper is not None:
        for index, line in enumerate(paper.line_items, start=1):
            amount_candidate = _line_candidate(line, "amount")
            description_candidate = _line_candidate(line, "description")
            amount = (
                parse_vnd(amount_candidate.value)
                if amount_candidate is not None and amount_candidate.state == "FOUND"
                else None
            )
            refs_value = _line_field(line, "invoice_refs") or ()
            if isinstance(refs_value, str):
                refs_value = (refs_value,)
            invoice_no = str(refs_value[0]) if refs_value else None
            description_value = _line_field(line, "description")
            description = str(description_value) if description_value is not None else None
            if description is not None and is_settlement_summary_row(description):
                continue
            # A row is matched only when a real link ties an invoice document to
            # it (by invoice number); never a guessed file.
            matched_filename = None
            suggested_filename = None
            if invoice_no is not None:
                for document in report.documents:
                    number = _found(document, "document_number")
                    if number is None:
                        continue
                    if _normalize(number) == _normalize(invoice_no):
                        source_id = matched.get(document.document_id)
                        if source_id is not None:
                            matched_filename = names.get(source_id)
                        suggest_id = suggested.get(document.document_id)
                        if suggest_id is not None:
                            suggested_filename = names.get(suggest_id)
                        break
            expenses.append({
                "description": description,
                "invoice_no": invoice_no,
                "amount": amount,
                "amount_state": (
                    amount_candidate.state if amount_candidate is not None
                    else "NOT_PRESENT"
                ),
                "description_state": (
                    description_candidate.state if description_candidate is not None
                    else "NOT_PRESENT"
                ),
                "source_filename": names.get(paper.source_id),
                "status": "UNRESOLVED" if amount is None or description is None else (
                    "CLEAR" if matched_filename is not None else (
                    "SUGGESTED" if suggested_filename is not None else "UNMATCHED"
                    )
                ),
                "matched_invoice": matched_filename,
                "suggested_invoice": suggested_filename,
                "refs": _refs(line),
            })

    incurred_total = printed_total
    incurred_total_basis = "PRINTED_TOTAL" if printed_total is not None else None
    if (
        incurred_total is None
        and expenses
        and all(isinstance(expense["amount"], int) for expense in expenses)
    ):
        incurred_total = sum(int(expense["amount"]) for expense in expenses)
        incurred_total_basis = "ROW_SUM"

    invoices: list[dict[str, object]] = []
    for document in report.documents:
        if document.document_type in ("E_INVOICE", "PAPER_RECEIPT", "COLLECTION_RECEIPT"):
            invoices.append({
                "filename": names.get(document.source_id),
                "invoice_no": _found(document, "document_number"),
                "seller": _found(document, "issuer_name"),
                "amount": parse_vnd(_found(document, "total_amount")),
            })

    warnings: list[str] = []
    if paper is None:
        warnings.append("Không tìm thấy giấy quyết toán/đề nghị trong chứng từ đã tải lên.")
    if declared_advance is None:
        warnings.append("Chưa đọc được số tiền tạm ứng trên giấy; nhân viên vui lòng kiểm tra.")
    if printed_total is None and not expenses:
        warnings.append("Chưa đọc được tổng chi phí; nhân viên vui lòng kiểm tra.")
    if printed_total is None and expenses and any(expense["amount"] is None for expense in expenses):
        incurred_total = None
        incurred_total_basis = None
    # Document-internal arithmetic (TC06/TC11): the SAME findings the reconciler
    # turns into blocking FACTs are surfaced here, so the employee sees the
    # contradiction on the review screen — not a silent "looks fine" draft.
    arithmetic_findings: list[dict[str, object]] = []
    for document in report.documents:
        for finding in check_document_arithmetic(document):
            arithmetic_findings.append({
                "code": finding.code,
                "basis": finding.basis,
                "question": finding.question,
                "refs": [ref.model_dump(mode="json") for ref in finding.refs],
            })
            warnings.append(finding.basis)

    # The "activity content" shown on the review screen: a travel paper names its
    # destination, but a non-travel paper (client reception, office purchase) has
    # no trip_destination and carries its content in `purpose` ("Về việc/Nội
    # dung"). Show what was actually read rather than "Chưa đọc được".
    activity_name = None
    if destination:
        activity_name = f"Công tác {destination}"
    elif purpose:
        activity_name = purpose

    return {
        "declared_name": declared_name,
        "destination": destination,
        "activity_name": activity_name,
        "trip_start": trip_start,
        "trip_end": trip_end,
        "occurred_at": None,
        "declared_purpose": purpose,
        "incurred_total": incurred_total,
        "incurred_total_basis": incurred_total_basis,
        "declared_advance": declared_advance,
        "expenses": expenses,
        "invoices": invoices,
        "warnings": warnings,
        "arithmetic_findings": arithmetic_findings,
        "field_states": field_states,
        "provider_mode": report.provider_mode,
        "data_origin": report.data_origin,
    }


def _normalize(value: object) -> str:
    import re

    return re.sub(r"[^A-Z0-9]", "", str(value).upper())

"""W1: the settlement draft is derived from the OCR ReadResult (no regex).

The draft the employee reviews must come from the same typed evidence report the
reconciler consumes: FOUND fields become filled values with source refs; an
unread field stays null (never a fabricated 0 or demo fact). TC01's original
GIẤY ĐỀ NGHỊ HOÀN ỨNG is a client-reception report, not a trip to Hà Nội.
"""

from __future__ import annotations

from decimal import Decimal

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate, EvidenceLink
from invoice_referee.domain.evidence import ReadResult, SourceRef
from invoice_referee.reconciliation.settlement_draft import build_settlement_draft

SHA = "a" * 64


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="source:report", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _paper() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:report", document_id="source:report:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            _found("declared_name", "NGUYỄN MINH AN", "Người đề nghị: NGUYỄN MINH AN"),
            _found("purpose", "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "Nội dung: Chi phí tiếp khách"),
            _found("printed_total", "3240000", "3.240.000"),
            _found("declared_advance", "4000000", "4.000.000"),
        ),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"),
            _found("amount", "3240000"),
            _found("invoice_refs", ("00000101",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:invoice", document_id="source:invoice:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(
            _found("document_number", "00000101"),
            _found("issuer_name", "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT"),
            _found("total_amount", "3240000"),
            _found("document_date", "2026-10-10"),
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _sources() -> tuple[SourceRef, ...]:
    return (
        SourceRef(id="source:report", digest=SHA, tenant="tenant:demo", media="PDF",
                  storage_key="k/report", filename="report_hoan_ung.pdf"),
        SourceRef(id="source:invoice", digest=SHA, tenant="tenant:demo", media="PDF",
                  storage_key="k/invoice", filename="hoa_don_dien_tu.pdf"),
    )


def _report(*, documents, links=()) -> ReadResult:
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=documents, links=links)


def _link() -> EvidenceLink:
    return EvidenceLink(
        item_id="ITEM-001", source_id="source:invoice",
        document_id="source:invoice:1-1:E_INVOICE", status="AUTO_LINK",
        method="INVOICE_NUMBER_EXACT", score=Decimal("1"), explanation="exact",
    )


def test_tc01_draft_reads_real_values_from_the_report() -> None:
    draft = build_settlement_draft(_report(documents=(_paper(), _invoice()), links=(_link(),)), sources=_sources())
    assert draft["declared_name"] == "NGUYỄN MINH AN"
    assert draft["declared_purpose"] == "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"
    assert draft["incurred_total"] == 3_240_000
    assert draft["declared_advance"] == 4_000_000
    assert draft["expenses"] and draft["expenses"][0]["amount"] == 3_240_000
    assert draft["expenses"][0]["invoice_no"] == "00000101"
    assert draft["expenses"][0]["matched_invoice"] == "hoa_don_dien_tu.pdf"
    # No fabricated trip to Hà Nội: TC01 has no trip_destination.
    assert draft["destination"] is None
    assert "Hà Nội" not in (draft["activity_name"] or "")


def test_non_travel_activity_name_falls_back_to_the_paper_content() -> None:
    # A non-travel paper (no trip_destination) still carries its content
    # ("Về việc/Nội dung"); the activity-name field must show what was read, not
    # "Chưa đọc được" (report: activity content not extracted).
    draft = build_settlement_draft(_report(documents=(_paper(), _invoice()), links=(_link(),)), sources=_sources())
    assert draft["activity_name"] == "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"


def test_unread_money_stays_null_not_zero() -> None:
    paper = _paper().model_copy(update={
        "fields": (
            _found("declared_name", "NGUYỄN MINH AN"),
            _found("purpose", "Chi phí tiếp khách"),
        ),
        "line_items": (),
    })
    draft = build_settlement_draft(_report(documents=(paper,)), sources=_sources())
    assert draft["incurred_total"] is None
    assert draft["declared_advance"] is None


def test_no_original_evidence_marks_row_not_matched() -> None:
    # A row whose invoice is absent must NOT show a matched link.
    draft = build_settlement_draft(_report(documents=(_paper(),)), sources=_sources())
    assert draft["expenses"]
    assert draft["expenses"][0].get("matched_invoice") is None
    assert draft["expenses"][0]["status"] != "CLEAR"


def test_draft_carries_source_refs_and_field_states() -> None:
    draft = build_settlement_draft(_report(documents=(_paper(), _invoice()), links=(_link(),)), sources=_sources())
    assert draft["field_states"]["declared_name"] == "FOUND"
    assert draft["expenses"][0]["refs"], "the row must carry a source ref"

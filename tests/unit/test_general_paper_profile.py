"""T1: server-owned activity profile + general (non-travel) paper contract.

The activity's business profile (TRAVEL vs WORK_EXPENSE) is server/context-owned,
not a global hard-coded TRAVEL. A general settlement form is not forced to carry
trip fields; a travel paper still requires trip context. Missing trip context on a
travel paper is a FACT, never invented data.
"""

from __future__ import annotations

from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.evidence.document_validity import validate_document
from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES, required_fields_for
from invoice_referee.domain.documents import ConfidenceReview, OcrPage, OcrSourceResult

SHA = "a" * 64


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _ocr(markdown: str) -> OcrSourceResult:
    return OcrSourceResult(
        source_id="s", source_digest=SHA, provider="fake", model="fake",
        pages=(OcrPage(page=1, markdown=markdown),),
    )


def _review() -> ConfidenceReview:
    return ConfidenceReview(status="ASSESSED", block_assessments=())


def _general_paper() -> DocumentAnalysis:
    # A general (non-travel) settlement form: no trip fields at all.
    return DocumentAnalysis(
        source_id="s", document_id="s:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            _found("declared_name", "Nguyễn An", "Nguyễn An"),
            _found("purpose", "Mua thiết bị văn phòng", "Mua thiết bị văn phòng"),
            _found("printed_total", "5400000", "5.400.000 đ"),
        ),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Máy in", "Máy in"),
            _found("amount", "5400000", "5.400.000 đ"),
            _found("invoice_refs", ("IR2",), "IR2"),
        )),),
        confidence_status="ASSESSED", profile_status="UNKNOWN",
    )


def test_general_profile_does_not_require_trip_fields() -> None:
    required = required_fields_for("SETTLEMENT_FORM", "WORK_EXPENSE")
    assert "trip_destination" not in required
    assert "trip_start" not in required
    assert "trip_end" not in required
    assert "declared_name" in required
    assert "purpose" in required


def test_travel_profile_requires_trip_fields() -> None:
    required = required_fields_for("SETTLEMENT_FORM", "TRAVEL")
    assert {"trip_destination", "trip_start", "trip_end"} <= set(required)


def test_general_paper_validates_clear_without_trip() -> None:
    markdown = "Người đề nghị: Nguyễn An\nMục đích: Mua thiết bị văn phòng\nTổng: 5.400.000 đ\nMáy in 5.400.000 đ IR2"
    result = validate_document(_general_paper(), _ocr(markdown), _review(), activity_profile="WORK_EXPENSE")
    assert result.profile_status == "CLEAR", [f.code for f in result.profile_findings]


def test_travel_paper_missing_trip_is_needs_human() -> None:
    markdown = "Người đề nghị: Nguyễn An\nMục đích: Công tác\nTổng: 5.400.000 đ\nVé 5.400.000 đ IR2"
    result = validate_document(_general_paper(), _ocr(markdown), _review(), activity_profile="TRAVEL")
    assert result.profile_status == "NEEDS_HUMAN"
    assert any(f.field in ("trip_destination", "trip_start", "trip_end") for f in result.profile_findings)

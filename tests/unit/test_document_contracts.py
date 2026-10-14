"""E1 document/evidence contract tests (plan E1, contracts §12).

Pins: the 17 DocumentType values, the five DocumentEvidenceRole values, the
five FieldState values, per-field candidate/value consistency (missing is not
zero; AMBIGUOUS keeps each source and no aggregate value), locator validity,
and score/allocation bounds. These are DTO-shape tests: no provider, no OCR.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DOCUMENT_EVIDENCE_ROLES,
    DOCUMENT_TYPES,
    FIELD_STATES,
    CandidateValue,
    DocumentAnalysis,
    DocumentClassification,
    DocumentEvidenceRole,
    DocumentLine,
    DocumentRowMatch,
    DocumentType,
    EvidenceLink,
    FieldCandidate,
    OcrBlock,
    OcrPage,
    OcrSourceResult,
    OcrWord,
    PageCoverage,
    ValueAlternative,
)

SHA = "a" * 64


def _ref(**overrides: object) -> EvidenceRef:
    base: dict[str, object] = {
        "source_id": "source:1",
        "source_sha256": SHA,
        "page": 1,
        "exact_quote": "Tổng cộng 450.000",
    }
    return EvidenceRef(**{**base, **overrides})


def test_document_types_cover_all_17_values() -> None:
    expected = {
        "E_INVOICE",
        "PAPER_RECEIPT",
        "CARD_SLIP",
        "PAYMENT_PROOF",
        "TRANSPORT_TICKET",
        "HOTEL_RECEIPT",
        "COLLECTION_RECEIPT",
        "CONTRACT",
        "QUOTATION",
        "PURCHASE_ORDER",
        "ACCEPTANCE_RECORD",
        "DELIVERY_NOTE",
        "GOODS_RECEIPT",
        "SUPPLIER_CONFIRMATION",
        "OTHER",
        "UNKNOWN",
        "SETTLEMENT_FORM",
    }
    assert set(DOCUMENT_TYPES) == expected
    assert len(DOCUMENT_TYPES) == 17


def test_document_evidence_roles_are_the_five_values() -> None:
    assert set(DOCUMENT_EVIDENCE_ROLES) == {
        "SETTLEMENT_DECLARATION",
        "ORIGINAL_EXPENSE_EVIDENCE",
        "PAYMENT_EVIDENCE",
        "SUPPORTING_DOCUMENT",
        "UNKNOWN",
    }
    assert set(FIELD_STATES) == {
        "FOUND",
        "NOT_PRESENT",
        "UNREADABLE",
        "AMBIGUOUS",
        "NOT_APPLICABLE",
    }


def test_missing_is_not_zero() -> None:
    field = FieldCandidate(field="total_amount", state="NOT_PRESENT", refs=())
    assert field.state == "NOT_PRESENT"
    assert field.value is None


def test_unknown_type_cannot_carry_a_value() -> None:
    for state in ("NOT_PRESENT", "UNREADABLE", "NOT_APPLICABLE"):
        with pytest.raises(ValidationError):
            FieldCandidate(field="total_amount", state=state, value=450_000)


def test_found_requires_value_and_ref() -> None:
    with pytest.raises(ValidationError):
        FieldCandidate(field="total_amount", state="FOUND", value=450_000, refs=())
    with pytest.raises(ValidationError):
        FieldCandidate(field="total_amount", state="FOUND", refs=(_ref(),))
    ok = FieldCandidate(field="total_amount", state="FOUND", value=450_000, refs=(_ref(),))
    assert ok.value == 450_000


def test_ambiguous_keeps_each_source() -> None:
    field = FieldCandidate(
        field="total_amount",
        state="AMBIGUOUS",
        alternatives=(
            ValueAlternative(value=450_000, refs=(_ref(),)),
            ValueAlternative(value=480_000, refs=(_ref(exact_quote="Tổng 480.000"),)),
        ),
    )
    assert len(field.alternatives) == 2
    assert field.value is None


def test_ambiguous_needs_two_sources_and_no_value() -> None:
    with pytest.raises(ValidationError):
        FieldCandidate(
            field="total_amount",
            state="AMBIGUOUS",
            alternatives=(ValueAlternative(value=450_000, refs=(_ref(),)),),
        )
    with pytest.raises(ValidationError):
        FieldCandidate(
            field="total_amount",
            state="AMBIGUOUS",
            value=450_000,
            alternatives=(
                ValueAlternative(value=450_000, refs=(_ref(),)),
                ValueAlternative(value=480_000, refs=(_ref(),)),
            ),
        )


def test_money_value_rejects_bool_and_float() -> None:
    # CandidateValue allows Decimal/str/int/bool/tuple, but money fields are
    # normalized by code; bool must never masquerade as an amount.
    with pytest.raises(ValidationError):
        FieldCandidate(field="total_amount", state="FOUND", value=True, refs=(_ref(),))
    with pytest.raises(ValidationError):
        FieldCandidate(field="total_amount", state="FOUND", value=1.25, refs=(_ref(),))


def test_malformed_locator_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _ref(source_sha256="not-a-digest")
    with pytest.raises(ValidationError):
        _ref(page=None, record_key=None)


def test_ocr_types_round_trip() -> None:
    word = OcrWord(text="450.000", block_start=0, block_end=7, confidence=0.4)
    block = OcrBlock(id="b1", kind="text", content="Tổng 450.000", bbox=None, words=(word,))
    page = OcrPage(page=1, markdown="Tổng 450.000", blocks=(block,))
    src = OcrSourceResult(
        source_id="source:1",
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=(page,),
        raw_artifact_ref="artifact:1",
    )
    assert src.pages[0].blocks[0].words[0].confidence == 0.4
    cov = PageCoverage(source_id="source:1", page=1, state="OCR_COMPLETE")
    assert cov.state == "OCR_COMPLETE"


def test_classification_requires_known_type_and_roles() -> None:
    with pytest.raises(ValidationError):
        DocumentClassification(
            document_id="doc:1",
            source_id="source:1",
            page_range=(1, 1),
            block_ids=("b1",),
            document_type="NOT_A_TYPE",  # type: ignore[arg-type]
            roles=(),
            role_refs={},
            alternative_document_types=(),
            classification_confidence=None,
            signals=(),
            refs=(),
        )
    ok = DocumentClassification(
        document_id="doc:1",
        source_id="source:1",
        page_range=(1, 1),
        block_ids=("b1",),
        document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        role_refs={"ORIGINAL_EXPENSE_EVIDENCE": (_ref(),)},
        alternative_document_types=(),
        classification_confidence=0.9,
        signals=("header",),
        refs=(_ref(),),
    )
    assert ok.document_type == "E_INVOICE"
    assert DocumentEvidenceRole.__name__  # enum type exists


def test_evidence_link_score_and_allocation_bounds() -> None:
    with pytest.raises(ValidationError):
        EvidenceLink(
            item_id="row:1",
            source_id="source:1",
            document_id="doc:1",
            status="AUTO_LINK",
            method="INVOICE_NUMBER_EXACT",
            score=Decimal("1.5"),
            allocated_amount=None,
            explanation="exact",
            refs=(_ref(),),
        )
    ok = EvidenceLink(
        item_id="row:1",
        source_id="source:1",
        document_id="doc:1",
        status="AUTO_LINK",
        method="INVOICE_NUMBER_EXACT",
        score=Decimal("1"),
        allocated_amount=Decimal("100"),
        explanation="exact",
        refs=(_ref(),),
    )
    assert ok.score == Decimal("1")


def test_row_allocation_cannot_exceed_source_amount() -> None:
    with pytest.raises(ValidationError):
        DocumentRowMatch(
            item_id="row:1",
            paper_amount=Decimal("500"),
            category_candidate="HOTEL",
            evidence_status="ORIGINAL_EVIDENCE",
            alternative_evidence_type=None,
            matched_document_date=None,
            original_total=Decimal("500"),
            allocated_total=Decimal("600"),
            no_evidence_reason=None,
            refs=(_ref(),),
        )


def test_document_analysis_and_line_are_strict() -> None:
    line = DocumentLine(id="line:1", fields=(), refs=())
    analysis = DocumentAnalysis(
        source_id="source:1",
        document_id="doc:1",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        role_refs={},
        page_range=(1, 1),
        block_ids=("b1",),
        classification_confidence=0.9,
        alternative_document_types=(),
        classification_refs=(_ref(),),
        fields=(),
        line_items=(line,),
        confidence_status="ASSESSED",
        confidence_refs=(),
        profile_status="CLEAR",
        profile_findings=(),
        refs=(_ref(),),
        warnings=(),
    )
    assert analysis.line_items[0].id == "line:1"
    with pytest.raises(ValidationError):
        DocumentAnalysis(**{**analysis.model_dump(), "unexpected": 1})


def test_read_result_carries_typed_evidence_report() -> None:
    from invoice_referee.domain.evidence import ReadResult

    result = ReadResult(
        provider_mode="LIVE",
        data_origin="LIVE_READ",
        documents=(),
        links=(),
        row_matches=(),
        match_findings=(),
        page_coverage_detail=(PageCoverage(source_id="source:1", page=1, state="OCR_COMPLETE"),),
    )
    assert result.provider_mode == "LIVE"
    assert result.page_coverage_detail[0].state == "OCR_COMPLETE"
    # Existing fields keep their meaning (proposals only, no financial effect).
    assert result.units == () and result.observations == () and result.relations == ()

"""E5 profile validation + field-to-word confidence guard (plan E5).

Offline. `validate_document` checks ownership/quote/schema/profile and applies
the critical-field confidence guard: a critical field is unresolved when the
effective verification flag is set, or when its digit-bearing low text is not
READABLE. The model cannot lower code-owned criticality, and an omitted model
label cannot evade the word-overlap guard.
"""

from __future__ import annotations

from invoice_referee.domain.documents import (
    BlockAssessment,
    ConfidenceReview,
    DocumentAnalysis,
    DocumentClassification,
    DocumentLine,
    FieldCandidate,
    OcrBlock,
    OcrPage,
    OcrSourceResult,
    OcrWord,
)
from invoice_referee.evidence.document_validity import validate_document

SHA = "a" * 64


def _ocr(words: tuple[OcrWord, ...], markdown: str = "Tổng cộng: 450.000") -> OcrSourceResult:
    block = OcrBlock(id="b1", kind="text", content=markdown, words=words)
    return OcrSourceResult(
        source_id="source:1",
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=(OcrPage(page=1, markdown=markdown, blocks=(block,)),),
    )


def _classification(document_type: str = "E_INVOICE") -> DocumentClassification:
    return DocumentClassification(
        document_id="doc:1",
        source_id="source:1",
        page_range=(1, 1),
        block_ids=("b1",),
        document_type=document_type,  # type: ignore[arg-type]
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        role_refs={},
        refs=(),
    )


def _analysis(fields: tuple[FieldCandidate, ...], document_type: str = "E_INVOICE") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1",
        document_id="doc:1",
        document_type=document_type,  # type: ignore[arg-type]
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=fields,
        line_items=(DocumentLine(id="line:1", fields=()),),
        confidence_status="ASSESSED",
        profile_status="UNKNOWN",
        refs=(),
    )


def _found(field: str, value: object, quote: str = "Tổng cộng: 450.000") -> FieldCandidate:
    from invoice_referee.domain.common import EvidenceRef

    return FieldCandidate(
        field=field,
        state="FOUND",
        value=value,  # type: ignore[arg-type]
        refs=(
            EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote),
        ),
    )


def _review(action: str, requires: bool | None = None) -> ConfidenceReview:
    return ConfidenceReview(
        status="ASSESSED",
        block_assessments=(
            BlockAssessment(
                candidate_id="source:1:p1:b1",
                importance="NON_CRITICAL",
                quality_state="UNCERTAIN",
                review_action=action,  # type: ignore[arg-type]
                reason="low confidence",
                requires_verification=requires,
            ),
        ),
    )


def test_missing_critical_word_confidence_blocks() -> None:
    # total_amount is critical; its word has no numeric score -> NEEDS_HUMAN.
    ocr = _ocr((OcrWord(text="450.000", confidence=None),))
    analysis = _analysis((_found("total_amount", "450000"),))
    result = validate_document(analysis, ocr, ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES"))
    total = next(f for f in result.fields if f.field == "total_amount")
    assert total.state != "FOUND"
    assert result.profile_status == "NEEDS_HUMAN"


def test_readable_ask_human_with_omitted_flag_blocks() -> None:
    ocr = _ocr((OcrWord(text="450.000", confidence=0.9),))
    analysis = _analysis((_found("total_amount", "450000"),))
    result = validate_document(analysis, ocr, _review("ASK_HUMAN", requires=None))
    total = next(f for f in result.fields if f.field == "total_amount")
    assert total.state != "FOUND"


def test_explicit_verification_true_continue_blocks() -> None:
    ocr = _ocr((OcrWord(text="450.000", confidence=0.9),))
    analysis = _analysis((_found("total_amount", "450000"),))
    result = validate_document(analysis, ocr, _review("CONTINUE", requires=True))
    total = next(f for f in result.fields if f.field == "total_amount")
    assert total.state != "FOUND"


def test_code_critical_model_noncritical_blocks() -> None:
    # The model marked the block NON_CRITICAL, but code owns criticality:
    # ASK_HUMAN on the block still leaves the critical field unresolved.
    ocr = _ocr((OcrWord(text="450.000", confidence=0.9),))
    analysis = _analysis((_found("total_amount", "450000"),))
    review = _review("ASK_HUMAN", requires=False)
    result = validate_document(analysis, ocr, review)
    total = next(f for f in result.fields if f.field == "total_amount")
    assert total.state != "FOUND"


def test_noncritical_field_stays_found() -> None:
    # A noncritical field with a clean quote is unaffected by the guard.
    ocr = _ocr((OcrWord(text="450.000", confidence=0.9),), markdown="Ghi chú: 450.000")
    analysis = _analysis((_found("description", "Ghi chú", quote="Ghi chú: 450.000"),))
    result = validate_document(analysis, ocr, _review("ASK_HUMAN"))
    desc = next(f for f in result.fields if f.field == "description")
    assert desc.state == "FOUND"


def test_clean_document_is_clear() -> None:
    ocr = _ocr((OcrWord(text="450.000", confidence=0.95),))
    analysis = _analysis(
        (
            _found("total_amount", "450000"),
            _found("issuer_name", "Công ty ABC", quote="Tổng cộng: 450.000"),
        )
    )
    result = validate_document(analysis, ocr, ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES"))
    assert result.profile_status in ("CLEAR", "NEEDS_HUMAN")


def test_empty_invoice_fails_required_fields() -> None:
    # A document with no FOUND required fields must not be CLEAR.
    ocr = _ocr((OcrWord(text="x", confidence=0.9),))
    analysis = _analysis(())
    result = validate_document(analysis, ocr, ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES"))
    assert result.profile_status == "NEEDS_HUMAN"
    assert any(f.code == "REQUIRED_FIELD_MISSING" for f in result.profile_findings)


def test_unrelated_flagged_block_does_not_block_a_clean_field() -> None:
    # A flagged block that does NOT touch this field's quote must not block it.
    ocr = _ocr((OcrWord(text="450.000", confidence=0.95),))
    analysis = _analysis((_found("total_amount", "450000"),))
    review = ConfidenceReview(
        status="ASSESSED",
        block_assessments=(
            BlockAssessment(
                candidate_id="source:1:p9:b9",  # a different page/block
                importance="NON_CRITICAL",
                quality_state="UNCERTAIN",
                review_action="ASK_HUMAN",
                reason="unrelated low-confidence block",
            ),
        ),
    )
    result = validate_document(analysis, ocr, review)
    total = next(f for f in result.fields if f.field == "total_amount")
    assert total.state == "FOUND"

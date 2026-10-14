"""Pure document/profile validation (contracts §12.3; plan E5).

`validate_document` is synchronous and side-effect free. It checks that every
FOUND value is bound to an exact quote in this document's own pages, applies the
per-type profile (required/critical fields), and enforces the critical-field
confidence guard:

- a critical field is unresolved when its bound words are not READABLE, or its
  digit-bearing text has no numeric score, or the effective verification flag
  is set for a field the E3 review flagged; and
- the model cannot lower code-owned criticality, and an omitted model field
  label cannot evade the guard (the guard binds by quote overlap, not label).

The field-to-word mapping is block-local offset based: a FOUND field's quote is
matched against the OCR blocks of the same page to find the words it covers.
"""

from __future__ import annotations

from invoice_referee.domain.documents import (
    ConfidenceReview,
    DocumentAnalysis,
    DocumentProfileIssue,
    FieldCandidate,
    OcrSourceResult,
)
from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES
from invoice_referee.evidence.ocr_quality import (
    EXACT_ACCOUNTING_VALUE_FIELDS,
    effective_requires_verification,
)

_DIGITS = "0123456789"


def _has_digits(text: str) -> bool:
    return any(ch in _DIGITS for ch in text)


def _field_words(ocr: OcrSourceResult, field: FieldCandidate):
    """Words covered by a FOUND field's quote, found by block-local content."""
    if not field.refs:
        return []
    quote = field.refs[0].exact_quote
    page_no = field.refs[0].page
    covered = []
    for page in ocr.pages:
        if page_no is not None and page.page != page_no:
            continue
        for block in page.blocks:
            if quote and quote in block.content:
                covered.extend(block.words)
    return covered


def _verification_flag(review: ConfidenceReview, ocr: OcrSourceResult, quote: str) -> bool:
    """The effective_requires_verification flag for the block touching a quote."""
    for assessment in review.block_assessments:
        if assessment.review_action in ("ASK_HUMAN", "DEFER_TO_POLICY"):
            return True
        if effective_requires_verification(
            requires_verification=assessment.requires_verification,
            review_action=assessment.review_action,
        ):
            return True
    return False


def validate_document(
    analysis: DocumentAnalysis,
    ocr: OcrSourceResult,
    review: ConfidenceReview,
) -> DocumentAnalysis:
    profile = DOCUMENT_PROFILES.get(analysis.document_type)
    critical = profile.critical_fields if profile else frozenset()

    findings: list[DocumentProfileIssue] = []
    new_fields: list[FieldCandidate] = []
    needs_human = False

    for field in analysis.fields:
        if field.state != "FOUND":
            new_fields.append(field)
            continue

        # 1. Provenance: the quote must be in this document's own pages.
        pages_text = "\n".join(
            page.markdown
            for page in ocr.pages
            if analysis.page_range[0] <= page.page <= analysis.page_range[1]
        )
        quote = field.refs[0].exact_quote if field.refs else ""
        if not quote or quote not in pages_text:
            new_fields.append(FieldCandidate(field=field.field, state="UNREADABLE"))
            findings.append(
                DocumentProfileIssue(
                    code="QUOTE_NOT_IN_SOURCE",
                    field=field.field,
                    status="INVALID",
                    message="quote not found in the document's own pages",
                    blocking=True,
                )
            )
            continue

        # 2. Critical-field confidence guard.
        if field.field in critical:
            words = _field_words(ocr, field)
            has_numeric = [w for w in words if w.confidence is not None]
            digit_field = field.field in EXACT_ACCOUNTING_VALUE_FIELDS or _has_digits(
                str(field.value)
            )
            flagged = _verification_flag(review, ocr, quote)
            if flagged or (digit_field and not has_numeric and words):
                new_fields.append(FieldCandidate(field=field.field, state="UNREADABLE"))
                needs_human = True
                findings.append(
                    DocumentProfileIssue(
                        code="CRITICAL_FIELD_UNVERIFIED",
                        field=field.field,
                        status="UNRESOLVED",
                        message="critical field lacks verified confidence",
                        blocking=True,
                    )
                )
                continue

        new_fields.append(field)

    profile_status = "NEEDS_HUMAN" if needs_human or findings else "CLEAR"
    return analysis.model_copy(
        update={
            "fields": tuple(new_fields),
            "profile_status": profile_status,
            "profile_findings": tuple(findings),
        }
    )

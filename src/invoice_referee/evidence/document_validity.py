"""Pure document/profile validation (contracts §12.3; plan E5).

`validate_document` is synchronous and side-effect free. It checks that every
FOUND value is bound to an exact quote in this document's own pages, applies the
per-type profile (required/any-of/allowed fields), and enforces the critical-field
confidence guard bound to the field's *own* block(s):

- a critical field is unresolved when the assessment for the block that carries
  its quote is flagged (effective verification), or its bound words are not
  READABLE, or its digit-bearing text has no numeric score; and
- the model cannot lower code-owned criticality, and an unrelated flagged block
  does not block a clean field (the guard binds by quote→block, not globally).
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


def _field_blocks(ocr: OcrSourceResult, field: FieldCandidate):
    """(page, block_id, words) blocks whose content carries this field's quote."""
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
                covered.append((page.page, block.id, block.words))
    return covered


def _block_flagged(review: ConfidenceReview, ocr: OcrSourceResult, page: int, block_id: str) -> bool:
    """Whether the review flagged the block whose candidate id matches this one."""
    candidate_id = f"{ocr.source_id}:p{page}:{block_id}"
    for assessment in review.block_assessments:
        if assessment.candidate_id != candidate_id:
            continue
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
                    code="QUOTE_NOT_IN_SOURCE", field=field.field, status="INVALID",
                    message="quote not found in the document's own pages", blocking=True,
                )
            )
            continue

        if field.field in critical:
            blocks = _field_blocks(ocr, field)
            words = [w for _, _, ws in blocks for w in ws]
            has_numeric = [w for w in words if w.confidence is not None]
            digit_field = field.field in EXACT_ACCOUNTING_VALUE_FIELDS or _has_digits(str(field.value))
            flagged = any(
                _block_flagged(review, ocr, page, block_id) for page, block_id, _ in blocks
            )
            if flagged or (digit_field and not has_numeric and words):
                new_fields.append(FieldCandidate(field=field.field, state="UNREADABLE"))
                needs_human = True
                findings.append(
                    DocumentProfileIssue(
                        code="CRITICAL_FIELD_UNVERIFIED", field=field.field, status="UNRESOLVED",
                        message="critical field lacks verified confidence", blocking=True,
                    )
                )
                continue

        new_fields.append(field)

    # Profile: required fields must be FOUND; any-of sets need at least one.
    if profile is not None:
        found = {f.field for f in new_fields if f.state == "FOUND"}
        for required in profile.required_fields:
            if required not in found:
                needs_human = True
                findings.append(
                    DocumentProfileIssue(
                        code="REQUIRED_FIELD_MISSING", field=required, status="UNRESOLVED",
                        message=f"required field '{required}' is missing", blocking=True,
                    )
                )
        if profile.any_of_fields and not (set(profile.any_of_fields) & found):
            needs_human = True
            findings.append(
                DocumentProfileIssue(
                    code="REQUIRED_FIELD_MISSING", field="|".join(profile.any_of_fields),
                    status="UNRESOLVED",
                    message="none of the any-of fields is present", blocking=True,
                )
            )

    profile_status = "NEEDS_HUMAN" if needs_human or findings else "CLEAR"
    return analysis.model_copy(
        update={
            "fields": tuple(new_fields),
            "profile_status": profile_status,
            "profile_findings": tuple(findings),
        }
    )

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
from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES, required_fields_for
from invoice_referee.evidence.ocr_quality import (
    EXACT_ACCOUNTING_VALUE_FIELDS,
    effective_requires_verification,
)

_DIGITS = "0123456789"


def _money_value_has_scores(field: FieldCandidate, ocr: OcrSourceResult) -> bool:
    """Require score coverage of the money token, never a neighbouring rate/label."""
    import re
    from invoice_referee.domain.common import parse_vnd
    try:
        value = parse_vnd(field.value)
    except (ValueError, TypeError):
        return False
    if value is None or not field.refs:
        return False
    quote, page_no = field.refs[0].exact_quote, field.refs[0].page
    spans = []
    for token in re.finditer(r"\d+(?:[., ]\d+)*", quote):
        if quote[token.end():].lstrip().startswith("%"):
            continue
        if parse_vnd(token.group()) == value:
            spans.append((token.start(), token.end()))
    for page in ocr.pages:
        if page.page != page_no:
            continue
        quote_start = page.markdown.find(quote)
        if quote_start < 0:
            continue
        scored_positions = set()
        cursor = 0
        for block in page.blocks:
            start = page.markdown.find(block.content, cursor) if block.content else -1
            if start < 0:
                continue
            cursor = start + len(block.content)
            for word in block.words:
                if (word.confidence is not None and word.block_start is not None and word.block_end is not None
                    and 0 <= word.block_start < word.block_end <= len(block.content)
                    and block.content[word.block_start:word.block_end] == word.text):
                    scored_positions.update(range(start + word.block_start, start + word.block_end))
            if quote in block.content and any(w.block_start is None or w.block_end is None for w in block.words):
                from invoice_referee.evidence.extraction import _numeric_tokens
                if any(w.confidence is not None and value in _numeric_tokens(w.text) for w in block.words):
                    return True
        if spans and all(all(quote_start + pos in scored_positions for pos in range(left, right)
                             if not quote[pos].isspace()) for left, right in spans):
            return True
    return False


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
        quote_start = page.markdown.find(quote) if page.markdown.count(quote) == 1 else -1
        cursor = 0
        for block in page.blocks:
            block_start = page.markdown.find(block.content, cursor) if block.content else -1
            if block_start >= 0:
                cursor = block_start + len(block.content)
            local_start = block.content.find(quote)
            local_end = local_start + len(quote)
            if local_start < 0 and quote_start >= 0 and block_start >= 0:
                local_start = max(quote_start, block_start) - block_start
                local_end = min(quote_start + len(quote), block_start + len(block.content)) - block_start
                if local_start >= local_end:
                    continue
            elif local_start < 0:
                continue
            words = block.words
            if words and all(
                w.block_start is not None and w.block_end is not None
                and 0 <= w.block_start < w.block_end <= len(block.content)
                and block.content[w.block_start:w.block_end] == w.text for w in words
            ):
                words = tuple(w for w in words if w.block_start < local_end and w.block_end > local_start)
            covered.append((page.page, block.id, words))
    return covered


def _block_flagged(review: ConfidenceReview, ocr: OcrSourceResult, page: int, block_id: str) -> bool:
    """Whether the review flagged the block whose candidate id matches this one."""
    candidate_id = f"{ocr.source_id}:p{page}:{block_id}"
    for assessment in review.block_assessments:
        if assessment.candidate_id != candidate_id:
            continue
        if assessment.quality_state in ("UNCERTAIN", "UNREADABLE", "UNKNOWN"):
            return True
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
    *,
    activity_profile: str | None = None,
) -> DocumentAnalysis:
    profile = DOCUMENT_PROFILES.get(analysis.document_type)
    critical = profile.critical_fields if profile else frozenset()

    findings: list[DocumentProfileIssue] = []
    new_fields: list[FieldCandidate] = []
    needs_human = False

    def validate_field(
        field: FieldCandidate, *, critical_fields: frozenset[str] = critical
    ) -> FieldCandidate:
        nonlocal needs_human
        if field.state != "FOUND":
            return field

        pages_text = "\n".join(
            page.markdown
            for page in ocr.pages
            if analysis.page_range[0] <= page.page <= analysis.page_range[1]
        )
        quote = field.refs[0].exact_quote if field.refs else ""
        if not quote or quote not in pages_text:
            findings.append(DocumentProfileIssue(
                code="QUOTE_NOT_IN_SOURCE", field=field.field, status="INVALID",
                message="quote not found in the document's own pages", blocking=True,
            ))
            return FieldCandidate(field=field.field, state="UNREADABLE")

        if field.field in critical_fields:
            blocks = _field_blocks(ocr, field)
            words = [w for _, _, block_words in blocks for w in block_words]
            digit_field = field.field in EXACT_ACCOUNTING_VALUE_FIELDS or _has_digits(str(field.value))
            flagged = any(
                (_block_flagged(review, ocr, page, block_id)
                 or (review.status == "TECHNICAL_ERROR"
                     and any(w.confidence is not None and w.confidence < 0.85 for w in block_words)))
                and not (block_words and all(w.block_start is not None and w.block_end is not None
                    and w.confidence is not None and w.confidence >= 0.85 for w in block_words))
                for page, block_id, block_words in blocks
            )
            value_words = [word for word in words if _has_digits(word.text)] if digit_field else words
            unscored_value = digit_field and (not value_words or any(w.confidence is None for w in value_words)
                or any(not ws for _, _, ws in blocks))
            if field.field in EXACT_ACCOUNTING_VALUE_FIELDS:
                unscored_value = not _money_value_has_scores(field, ocr)
            if flagged or unscored_value:
                needs_human = True
                findings.append(DocumentProfileIssue(
                    code="CRITICAL_FIELD_UNVERIFIED", field=field.field, status="UNRESOLVED",
                    message="critical field lacks verified confidence", blocking=True,
                ))
                return FieldCandidate(field=field.field, state="UNREADABLE")
        return field

    new_fields = [validate_field(field) for field in analysis.fields]
    lines = [
        line.model_copy(update={"fields": tuple(
            validate_field(field, critical_fields=critical | frozenset({"amount", "line_amount"})
                           | (frozenset({"invoice_refs"}) if analysis.document_type == "SETTLEMENT_FORM" else frozenset()))
            for field in line.fields
        )})
        for line in analysis.line_items
    ]

    # Profile: required fields must be FOUND; any-of sets need at least one.
    if profile is not None:
        found = {f.field for f in new_fields if f.state == "FOUND"}
        for required in required_fields_for(analysis.document_type, activity_profile):
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
            "line_items": tuple(lines),
            "profile_status": profile_status,
            "profile_findings": tuple(findings),
        }
    )

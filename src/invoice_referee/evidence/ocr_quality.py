"""Conditional OCR-confidence gate (contracts §12.3; plan E3).

Ports Hoangha's `collect_low_confidence_blocks` semantics (pinned revision
`1ee33487…`): a meaningful OCR word whose numeric score is below 0.85 makes its
block a candidate. With no numeric candidates the model is not called and the
result is `SKIPPED_NO_NUMERIC_CANDIDATES` — never a quality PASS. The model only
judges readability; it never replaces OCR text or supplies a field value.

This stage records block quality. Field-level criticality (missing confidence on
a critical field ⇒ unresolved) is applied in E5, after extraction supplies the
quote that binds a field to its words.
"""

from __future__ import annotations

import re
from typing import Any

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    BlockAssessment,
    ConfidenceCandidate,
    ConfidenceReview,
    OcrSourceResult,
    OcrWord,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroError

DEFAULT_WORD_REVIEW_THRESHOLD = 0.85

# Exact accounting fields Hoangha treats as verification-requiring.
EXACT_ACCOUNTING_VALUE_FIELDS = frozenset(
    {"total_amount", "subtotal", "tax", "line_amount", "unit_price", "amount", "printed_total"}
)

_DECORATIVE = re.compile(r"^[#|*_\-]+$")
_MARKDOWN_LINK = re.compile(r"^\[[^]]+\]\([^)]+\)$")


def is_meaningful_ocr_word(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _DECORATIVE.fullmatch(stripped):
        return False
    if _MARKDOWN_LINK.fullmatch(stripped):
        return False
    return True


def collect_low_confidence_blocks(
    ocr: OcrSourceResult, threshold: float = DEFAULT_WORD_REVIEW_THRESHOLD
) -> tuple[ConfidenceCandidate, ...]:
    """Collect one candidate per block holding a meaningful low-score word."""
    if not 0 < threshold <= 1:
        raise ValueError("OCR word confidence threshold must be within (0, 1]")
    candidates: list[ConfidenceCandidate] = []
    for page in ocr.pages:
        for block in page.blocks:
            low_words = tuple(
                word
                for word in block.words
                if is_meaningful_ocr_word(word.text)
                and isinstance(word.confidence, (int, float))
                and float(word.confidence) < threshold
            )
            if not low_words:
                continue
            candidates.append(
                ConfidenceCandidate(
                    candidate_id=f"{ocr.source_id}:p{page.page}:{block.id}",
                    source_id=ocr.source_id,
                    page=page.page,
                    block_id=block.id,
                    content=block.content,
                    low_words=low_words,
                    refs=(
                        EvidenceRef(
                            source_id=ocr.source_id,
                            source_sha256=ocr.source_digest,
                            page=page.page,
                            exact_quote=block.content or block.id,
                        ),
                    ),
                )
            )
    return tuple(candidates)


def effective_requires_verification(
    *, requires_verification: bool | None, review_action: str
) -> bool:
    """Hoangha's helper: an explicit boolean wins, else ASK_HUMAN implies it."""
    if requires_verification is not None:
        return requires_verification
    return review_action == "ASK_HUMAN"


async def review_ocr_quality(
    candidates: tuple[ConfidenceCandidate, ...],
    *,
    llm: object,
    budget: RunBudget,
    sources: tuple[OcrSourceResult, ...] = (),
) -> ConfidenceReview:
    """One batched review of the low-confidence candidates (plan E3).

    With no candidates the model is not called. Every candidate must receive
    exactly one assessment; a missing/duplicate/unexpected id, or any provider
    error, is `TECHNICAL_ERROR` (never a pass).
    """
    if not candidates:
        return ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=())

    expected = {candidate.candidate_id for candidate in candidates}
    from invoice_referee.evidence.prompts import OCR_CONFIDENCE_SYSTEM_PROMPT, CONFIDENCE_VERSION
    from invoice_referee.evidence.structured_output import complete_structured
    from invoice_referee.evidence.xkiro import XkiroSchemaError

    def validate(payload: dict) -> ConfidenceReview:
        raw = payload.get("assessments")
        if not isinstance(raw, list):
            raise XkiroSchemaError("assessments must be an array")
        seen = set()
        assessments = []
        required = {"candidate_id", "importance", "quality_state", "review_action",
                    "requires_verification", "canonical_fields", "reason"}
        for item in raw:
            if not isinstance(item, dict) or not required <= item.keys():
                raise XkiroSchemaError("assessment missing required fields")
            candidate_id = item["candidate_id"]
            if not isinstance(candidate_id, str) or candidate_id not in expected or candidate_id in seen:
                raise XkiroSchemaError("assessment candidate_id missing, duplicate or unexpected")
            if type(item["requires_verification"]) is not bool:
                raise XkiroSchemaError("requires_verification must be a boolean")
            if not isinstance(item["canonical_fields"], list) or not all(isinstance(f, str) for f in item["canonical_fields"]):
                raise XkiroSchemaError("canonical_fields must be a string array")
            if not isinstance(item["reason"], str) or not item["reason"].strip():
                raise XkiroSchemaError("assessment reason is required")
            verification = item["requires_verification"]
            if not all(isinstance(item[key], str) for key in ("importance", "quality_state", "review_action")):
                raise XkiroSchemaError("assessment enums must be strings")
            if item["review_action"] != ("ASK_HUMAN" if verification else "CONTINUE"):
                raise XkiroSchemaError("review_action disagrees with requires_verification")
            if item["quality_state"] in {"UNKNOWN", "UNCERTAIN", "UNREADABLE"} and not verification and item["importance"] != "NON_CRITICAL":
                raise XkiroSchemaError("uncertain accounting value requires verification")
            try:
                assessments.append(BlockAssessment(**{**item, "canonical_fields": tuple(item["canonical_fields"])}))
            except Exception as error:
                raise XkiroSchemaError(f"invalid assessment: {error}") from error
            seen.add(candidate_id)
        if seen != expected:
            raise XkiroSchemaError("assessments must cover all candidates exactly once")
        return ConfidenceReview(status="ASSESSED", block_assessments=tuple(assessments))

    try:
        return await complete_structured(llm, system=OCR_CONFIDENCE_SYSTEM_PROMPT,
            user=_serialize_candidates(candidates, sources), budget=budget, validate=validate,
            stage="confidence-review", prompt_version=CONFIDENCE_VERSION,
            schema_version="ocr-block-assessment-json-v2")
    except XkiroError:
        return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())


def _serialize_candidates(candidates: tuple[ConfidenceCandidate, ...], sources: tuple[OcrSourceResult, ...] = ()) -> str:
    import json

    def neighbors(candidate):
        for source in sources:
            if source.source_id != candidate.source_id:
                continue
            for page in source.pages:
                if page.page != candidate.page:
                    continue
                for index, block in enumerate(page.blocks):
                    if block.id == candidate.block_id:
                        return {"previous_block": page.blocks[index - 1].content if index else None,
                                "next_block": page.blocks[index + 1].content if index + 1 < len(page.blocks) else None}
        return {"previous_block": None, "next_block": None}

    return json.dumps(
        {
            "sources": [{"source_id": src.source_id,
                         "pages": [{"page": page.page, "markdown": page.markdown} for page in src.pages]}
                        for src in sources if any(c.source_id == src.source_id for c in candidates)],
            "context_limited": not bool(sources),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "source_id": candidate.source_id,
                    "page": candidate.page,
                    "block_id": candidate.block_id,
                    "content": candidate.content,
                    **neighbors(candidate),
                    "low_words": [
                        {"text": word.text, "confidence": word.confidence, "block_start": word.block_start, "block_end": word.block_end}
                        for word in candidate.low_words
                    ],
                }
                for candidate in candidates
            ]
        },
        ensure_ascii=False,
    )

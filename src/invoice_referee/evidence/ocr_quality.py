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
) -> ConfidenceReview:
    """One batched review of the low-confidence candidates (plan E3).

    With no candidates the model is not called. Every candidate must receive
    exactly one assessment; a missing/duplicate/unexpected id, or any provider
    error, is `TECHNICAL_ERROR` (never a pass).
    """
    if not candidates:
        return ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=())

    expected = {candidate.candidate_id for candidate in candidates}
    system = (
        "You judge OCR readability only. For each candidate, return one "
        "assessment with the same candidate_id. Never replace the OCR text or "
        "supply a field value. Reply as JSON: {\"assessments\": [...]}."
    )
    user = _serialize_candidates(candidates)
    try:
        payload = await llm.complete_json(system=system, user=user, budget=budget)  # type: ignore[attr-defined]
    except XkiroError:
        return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())

    raw = payload.get("assessments")
    if not isinstance(raw, list):
        return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())

    seen: set[str] = set()
    assessments: list[BlockAssessment] = []
    for item in raw:
        if not isinstance(item, dict):
            return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id not in expected or candidate_id in seen:
            return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())
        seen.add(candidate_id)
        try:
            assessments.append(
                BlockAssessment(
                    candidate_id=candidate_id,
                    importance=item.get("importance", "UNKNOWN"),
                    quality_state=item.get("quality_state", "UNKNOWN"),
                    review_action=item.get("review_action", "ASK_HUMAN"),
                    canonical_fields=tuple(item.get("canonical_fields") or ()),
                    observed_text=item.get("observed_text"),
                    reason=str(item.get("reason") or ""),
                    human_question=item.get("human_question"),
                    requires_verification=item.get("requires_verification"),
                )
            )
        except Exception:
            return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())
    if seen != expected:
        return ConfidenceReview(status="TECHNICAL_ERROR", block_assessments=())
    return ConfidenceReview(status="ASSESSED", block_assessments=tuple(assessments))


def _serialize_candidates(candidates: tuple[ConfidenceCandidate, ...]) -> str:
    import json

    return json.dumps(
        {
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "page": candidate.page,
                    "block_id": candidate.block_id,
                    "content": candidate.content,
                    "low_words": [
                        {"text": word.text, "confidence": word.confidence}
                        for word in candidate.low_words
                    ],
                }
                for candidate in candidates
            ]
        },
        ensure_ascii=False,
    )

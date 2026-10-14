"""E3 OCR-confidence gate tests (plan E3, contracts §12.3).

Offline: a fake LLM stands in for X-Kiro. A meaningful word below 0.85 creates
a candidate; a page with no numeric scores is SKIPPED_NO_NUMERIC_CANDIDATES and
must not call the model and must not be labelled a quality PASS. Every candidate
must get exactly one assessment; missing/duplicate/unexpected IDs are technical.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.documents import (
    ConfidenceCandidate,
    OcrBlock,
    OcrPage,
    OcrSourceResult,
    OcrWord,
)
from invoice_referee.evidence.ocr_quality import (
    collect_low_confidence_blocks,
    review_ocr_quality,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroError

SHA = "a" * 64


def _src(pages: tuple[OcrPage, ...]) -> OcrSourceResult:
    return OcrSourceResult(
        source_id="source:1",
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=pages,
    )


def _page(words: tuple[OcrWord, ...], content: str = "Tổng 450.000") -> OcrPage:
    block = OcrBlock(id="b1", kind="text", content=content, words=words)
    return OcrPage(page=1, markdown=content, blocks=(block,))


def test_word_threshold_boundary() -> None:
    ocr = _src(
        (
            _page(
                (
                    OcrWord(text="ok", confidence=0.85),
                    OcrWord(text="low", confidence=0.849),
                    OcrWord(text="none", confidence=None),
                )
            ),
        )
    )
    candidates = collect_low_confidence_blocks(ocr)
    assert len(candidates) == 1
    assert tuple(w.confidence for w in candidates[0].low_words) == (0.849,)


def test_decorative_tokens_are_not_candidates() -> None:
    ocr = _src(
        (
            _page(
                (
                    OcrWord(text="---", confidence=0.1),
                    OcrWord(text="   ", confidence=0.2),
                    OcrWord(text="[x](y)", confidence=0.3),
                )
            ),
        )
    )
    assert collect_low_confidence_blocks(ocr) == ()


class FakeLlm:
    def __init__(self, *, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.calls = 0

    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {"assessments": []}


async def test_no_scores_is_skipped_not_pass() -> None:
    ocr = _src((_page((OcrWord(text="Tổng", confidence=None),)),))
    llm = FakeLlm()
    review = await review_ocr_quality(collect_low_confidence_blocks(ocr), llm=llm, budget=RunBudget())
    assert review.status == "SKIPPED_NO_NUMERIC_CANDIDATES"
    assert llm.calls == 0
    assert review.block_assessments == ()


async def test_low_word_triggers_one_assessment_per_candidate() -> None:
    ocr = _src((_page((OcrWord(text="450.000", confidence=0.4),)),))
    candidates = collect_low_confidence_blocks(ocr)
    llm = FakeLlm(
        responses=[
            {
                "assessments": [
                    {
                        "candidate_id": candidates[0].candidate_id,
                        "importance": "CRITICAL",
                        "quality_state": "UNCERTAIN",
                        "review_action": "ASK_HUMAN",
                        "canonical_fields": ["total_amount"],
                        "observed_text": "450.000",
                        "reason": "low confidence on an amount",
                    }
                ]
            }
        ]
    )
    review = await review_ocr_quality(candidates, llm=llm, budget=RunBudget())
    assert review.status == "ASSESSED"
    assert len(review.block_assessments) == 1
    assert review.block_assessments[0].review_action == "ASK_HUMAN"


async def test_missing_candidate_assessment_is_technical() -> None:
    ocr = _src((_page((OcrWord(text="450.000", confidence=0.4),)),))
    candidates = collect_low_confidence_blocks(ocr)
    llm = FakeLlm(responses=[{"assessments": []}])
    review = await review_ocr_quality(candidates, llm=llm, budget=RunBudget())
    assert review.status == "TECHNICAL_ERROR"


async def test_duplicate_candidate_assessment_is_technical() -> None:
    ocr = _src((_page((OcrWord(text="450.000", confidence=0.4),)),))
    candidates = collect_low_confidence_blocks(ocr)
    one = {
        "candidate_id": candidates[0].candidate_id,
        "importance": "NON_CRITICAL",
        "quality_state": "READABLE",
        "review_action": "CONTINUE",
        "canonical_fields": [],
        "observed_text": "450.000",
        "reason": "ok",
    }
    llm = FakeLlm(responses=[{"assessments": [one, one]}])
    review = await review_ocr_quality(candidates, llm=llm, budget=RunBudget())
    assert review.status == "TECHNICAL_ERROR"


async def test_llm_error_is_technical() -> None:
    ocr = _src((_page((OcrWord(text="450.000", confidence=0.4),)),))
    candidates = collect_low_confidence_blocks(ocr)

    class BoomLlm:
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            raise XkiroError("HTTP 500")

    review = await review_ocr_quality(candidates, llm=BoomLlm(), budget=RunBudget())
    assert review.status == "TECHNICAL_ERROR"


def test_effective_requires_verification_follows_hoangha_rule() -> None:
    from invoice_referee.evidence.ocr_quality import effective_requires_verification

    # A present boolean wins; otherwise ASK_HUMAN implies verification.
    assert (
        effective_requires_verification(requires_verification=False, review_action="ASK_HUMAN")
        is False
    )
    assert (
        effective_requires_verification(requires_verification=True, review_action="CONTINUE")
        is True
    )
    assert (
        effective_requires_verification(requires_verification=None, review_action="ASK_HUMAN")
        is True
    )
    assert (
        effective_requires_verification(requires_verification=None, review_action="CONTINUE")
        is False
    )

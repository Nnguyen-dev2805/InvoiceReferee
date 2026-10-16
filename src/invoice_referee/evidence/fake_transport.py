"""Fixture transport for provider-free RECORDED_REPLAY reads (S6, 18/10/2026).

DEV/TEST-ONLY: canned OCR pages (+block boxes/word confidences) and canned LLM
extraction payloads keyed by explicit fixture markers. Wired ONLY when
`fake_llm_dir` is set (dev server flag / tests) — never the production
composition. Reports produced this way are labelled RECORDED_REPLAY.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OCR_WIDTH = 1000.0
OCR_HEIGHT = 1400.0


def amount_block_box() -> dict:
    """OCR-space box around a fixture amount line (matches the generator layout)."""
    return {
        "top_left_x": 60.0,
        "top_left_y": 960.0,
        "bottom_right_x": 620.0,
        "bottom_right_y": 1010.0,
    }


class FakeReader:
    """Dev/test-only OCR reader serving canned pages (never providers)."""

    provider_name = "fixture"
    model = "fixture-ocr-1"

    def __init__(self, pages: dict[str, dict]) -> None:
        # Accepts name-keyed pages ({name: {digest, markdown, blocks}}) or
        # digest-keyed pages ({digest: {...}}); lookup is always by digest.
        self._by_digest: dict[str, dict] = {}
        for key, page in pages.items():
            self._by_digest[page.get("digest", key)] = page

    @classmethod
    def from_dir(cls, outdir: Path) -> FakeReader:
        return cls(json.loads((outdir / "pages.json").read_text(encoding="utf-8")))

    async def read_source(
        self,
        source,
        *,
        budget,
        artifacts,
        source_bytes,
        expected_pages=None,
        root_id="",
    ):
        from invoice_referee.domain.documents import (
            OcrBlock,
            OcrPage,
            OcrSourceResult,
            OcrWord,
            BBox,
        )

        page = self._by_digest.get(source.digest)
        if page is None:
            raise TimeoutError(f"no fixture recording for {source.digest}")
        blocks = tuple(
            OcrBlock(
                id=b["id"],
                kind=b["kind"],
                content=b["content"],
                bbox=BBox(**b["bbox"]) if b["bbox"] else None,
                words=tuple(
                    OcrWord(text=w["text"], confidence=w["confidence"])
                    for w in b["words"]
                ),
            )
            for b in page["blocks"]
        )
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="fixture",
            model="fixture-ocr-1",
            pages=(OcrPage(page=1, markdown=page["markdown"], blocks=blocks),),
            raw_artifact_ref=None,
            problems=(),
            complete=True,
        )


class FakeLLM:
    """Dev/test-only LLM serving canned extraction payloads by fixture marker."""

    model = "fixture-llm-1"
    max_input_chars = 1_000_000

    def __init__(self, payloads: dict[str, dict]) -> None:
        self._payloads = payloads
        self.calls: list[str] = []

    async def complete_json(self, *, system: str, user: str, budget) -> dict:
        from invoice_referee.evidence.trace import RunBudget

        if isinstance(budget, RunBudget):
            budget.charge_llm()
        # Confidence-review calls embed the source markdown (hence fixture
        # markers): detect them FIRST by their candidate payload shape.
        if '"candidate_id"' in user:
            ids = re.findall(r'"candidate_id":\s*"([^"]+)"', user)
            return {
                "assessments": [
                    {
                        "candidate_id": candidate_id,
                        "importance": "NON_CRITICAL",
                        "quality_state": "READABLE",
                        "review_action": "CONTINUE",
                        "canonical_fields": ["total_amount"],
                        "requires_verification": False,
                        "reason": "Chữ số đọc được, khớp ngữ cảnh khối.",
                        "observed_text": "1500000",
                        "human_question": "",
                    }
                    for candidate_id in dict.fromkeys(ids)
                ],
            }
        markers = re.findall(r"FIXTURE-S6-[A-Z-]+", system + "\n" + user)
        key = markers[0] if markers else ""
        if key not in self._payloads:
            raise TimeoutError(f"no fixture LLM payload for marker {key!r}")
        self.calls.append(key)
        return json.loads(json.dumps(self._payloads[key]))


def write_llm_dir(outdir: Path, payloads: dict[str, dict]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    for marker, payload in payloads.items():
        (outdir / f"{marker}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def write_pages_json(outdir: Path, pages: dict[str, dict]) -> None:
    """Digest-keyed OCR pages for the dev-server fixture reader."""
    outdir.mkdir(parents=True, exist_ok=True)
    by_digest = {page["digest"]: page for page in pages.values()}
    (outdir / "pages.json").write_text(
        json.dumps(by_digest, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def load_llm_dir(outdir: Path) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for path in sorted(outdir.glob("FIXTURE-*.json")):
        payloads[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return payloads

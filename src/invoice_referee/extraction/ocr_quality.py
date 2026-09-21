"""Build evidence-scoped review candidates from word-level OCR confidence."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_WORD_REVIEW_THRESHOLD = 0.85


def is_meaningful_ocr_word(text: str) -> bool:
    """Return whether an OCR token carries content worth confidence review."""
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[#|*_\-]+", stripped):
        return False
    if re.fullmatch(r"\[[^]]+\]\([^)]+\)", stripped):
        return False
    return True


def collect_low_confidence_blocks(
    hierarchy: dict[str, Any],
    *,
    evidence_id: str,
    threshold: float = DEFAULT_WORD_REVIEW_THRESHOLD,
) -> list[dict[str, Any]]:
    """Collect each block containing at least one meaningful low-score word."""
    if not 0 < threshold <= 1:
        raise ValueError("OCR word confidence threshold phải nằm trong (0, 1].")

    candidates: list[dict[str, Any]] = []
    for page in hierarchy.get("pages") or []:
        blocks = page.get("blocks") or []
        for block_index, block in enumerate(blocks):
            low_words = [
                {
                    "text": word.get("text") or "",
                    "confidence": word.get("confidence"),
                    "start_index": word.get("start_index"),
                    "end_index": word.get("end_index"),
                }
                for word in block.get("words") or []
                if is_meaningful_ocr_word(str(word.get("text") or ""))
                and isinstance(word.get("confidence"), (int, float))
                and float(word["confidence"]) < threshold
            ]
            if not low_words:
                continue

            previous_block = blocks[block_index - 1] if block_index > 0 else None
            next_block = (
                blocks[block_index + 1]
                if block_index + 1 < len(blocks)
                else None
            )
            block_id = str(block.get("block_id") or "")
            candidates.append(
                {
                    "candidate_id": f"{evidence_id}:{block_id}",
                    "evidence_id": evidence_id,
                    "page_index": page.get("page_index"),
                    "block_id": block_id,
                    "block_type": block.get("type") or "unknown",
                    "content": block.get("content") or "",
                    "bounding_box": block.get("bounding_box") or {},
                    "mapping_status": (block.get("mapping") or {}).get("status"),
                    "block_confidence": block.get("confidence") or {},
                    "low_words": low_words,
                    "previous_block": (
                        {
                            "block_id": previous_block.get("block_id"),
                            "content": previous_block.get("content") or "",
                        }
                        if previous_block
                        else None
                    ),
                    "next_block": (
                        {
                            "block_id": next_block.get("block_id"),
                            "content": next_block.get("content") or "",
                        }
                        if next_block
                        else None
                    ),
                }
            )
    return candidates

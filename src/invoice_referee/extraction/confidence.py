"""Utilities for normalizing OCR confidence scores."""

from __future__ import annotations

from typing import Any

LOW_CONFIDENCE_THRESHOLD = 0.70
REVIEW_CONFIDENCE_THRESHOLD = 0.85


def confidence_level(confidence: float) -> str:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return "low"
    if confidence < REVIEW_CONFIDENCE_THRESHOLD:
        return "review"
    return "good"


def extract_word_confidence_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Mistral's page-level word scores into rows for inspection."""
    rows: list[dict[str, Any]] = []
    pages = (result.get("response") or {}).get("pages") or []

    for page_number, page in enumerate(pages, start=1):
        confidence_scores = page.get("confidence_scores") or {}
        word_scores = confidence_scores.get("word_confidence_scores") or []
        for word_score in word_scores:
            confidence = word_score.get("confidence")
            if not isinstance(confidence, (int, float)):
                continue
            normalized_confidence = float(confidence)
            rows.append(
                {
                    "page": page_number,
                    "text": word_score.get("text") or "",
                    "confidence": normalized_confidence,
                    "start_index": word_score.get("start_index"),
                    "level": confidence_level(normalized_confidence),
                }
            )

    return rows

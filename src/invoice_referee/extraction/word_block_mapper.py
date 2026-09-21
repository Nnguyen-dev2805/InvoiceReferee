"""Restructure flat Mistral OCR words and blocks into a hierarchy."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .confidence import REVIEW_CONFIDENCE_THRESHOLD, confidence_level

PARTIAL_MATCH_THRESHOLD = 0.75
MAX_PARTIAL_START_OFFSET = 8


def _get(mapping: dict[str, Any], snake_case: str, camel_case: str) -> Any:
    if snake_case in mapping:
        return mapping[snake_case]
    return mapping.get(camel_case)


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n")
    return re.sub(r"\s+", " ", value).strip()


def _is_content_word(text: str) -> bool:
    stripped = text.strip()
    if not stripped or re.fullmatch(r"#+", stripped):
        return False
    return re.fullmatch(r"\[[^]]+\]\([^)]+\)", stripped) is None


def _normalize_word(word: dict[str, Any]) -> dict[str, Any]:
    text = str(word.get("text") or "")
    start_index = _get(word, "start_index", "startIndex")
    confidence = word.get("confidence")
    normalized: dict[str, Any] = {
        "text": text,
        "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
        "start_index": start_index,
        "end_index": start_index + len(text) if isinstance(start_index, int) else None,
    }
    if normalized["confidence"] is not None:
        normalized["level"] = confidence_level(normalized["confidence"])
    if word.get("logprob") is not None:
        normalized["logprob"] = word["logprob"]
    return normalized


def _confidence_summary(
    words: list[dict[str, Any]],
    *,
    source: str,
    content_only: bool = True,
) -> dict[str, Any]:
    values = [
        word["confidence"]
        for word in words
        if (not content_only or _is_content_word(word["text"]))
        and word.get("confidence") is not None
    ]
    if not values:
        return {
            "source": source,
            "average": None,
            "minimum": None,
            "word_count": 0,
            "review_word_count": 0,
        }
    return {
        "source": source,
        "average": sum(values) / len(values),
        "minimum": min(values),
        "word_count": len(values),
        "review_word_count": sum(
            value < REVIEW_CONFIDENCE_THRESHOLD for value in values
        ),
    }


def _find_contiguous_match(
    words: list[dict[str, Any]],
    cursor: int,
    target: str,
) -> tuple[int, int, str, float] | None:
    normalized_target = _normalize_text(target)
    if not normalized_target:
        return None

    best_partial: tuple[int, int, str, float] | None = None
    target_length = len(normalized_target)

    for start in range(cursor, len(words)):
        raw_candidate = ""
        for end in range(start + 1, len(words) + 1):
            raw_candidate += words[end - 1]["text"]
            normalized_candidate = _normalize_text(raw_candidate)

            if raw_candidate == target:
                return start, end, "exact", 1.0
            if normalized_candidate == normalized_target:
                return start, end, "normalized", 1.0

            if start - cursor <= MAX_PARTIAL_START_OFFSET and normalized_candidate:
                similarity = SequenceMatcher(
                    None,
                    normalized_candidate,
                    normalized_target,
                    autojunk=False,
                ).ratio()
                if (
                    similarity >= PARTIAL_MATCH_THRESHOLD
                    and (best_partial is None or similarity > best_partial[3])
                ):
                    best_partial = start, end, "partial", similarity

            if len(normalized_candidate) > max(target_length * 1.4, target_length + 40):
                break

    return best_partial


def _table_reference_index(
    words: list[dict[str, Any]],
    cursor: int,
    table_id: str,
) -> int | None:
    for index in range(cursor, len(words)):
        if table_id and table_id in words[index]["text"]:
            return index
    return None


def _bounding_box(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "top_left_x": _get(block, "top_left_x", "topLeftX"),
        "top_left_y": _get(block, "top_left_y", "topLeftY"),
        "bottom_right_x": _get(block, "bottom_right_x", "bottomRightX"),
        "bottom_right_y": _get(block, "bottom_right_y", "bottomRightY"),
    }


def _extract_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("pages"), list):
        return response["pages"]
    if isinstance(payload.get("pages"), list):
        return payload["pages"]
    if "blocks" in payload and (
        "confidenceScores" in payload or "confidence_scores" in payload
    ):
        return [payload]
    raise ValueError("JSON không chứa page metadata hợp lệ của Mistral OCR.")


def _restructure_page(page: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    raw_scores = _get(page, "confidence_scores", "confidenceScores") or {}
    raw_words = _get(
        raw_scores,
        "word_confidence_scores",
        "wordConfidenceScores",
    ) or []
    words = sorted(
        (_normalize_word(word) for word in raw_words),
        key=lambda word: (
            word["start_index"] is None,
            word["start_index"] if word["start_index"] is not None else 0,
        ),
    )
    assigned_indices: set[int] = set()
    cursor = 0
    blocks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    page_index = page.get("index", fallback_index)

    for block_index, raw_block in enumerate(page.get("blocks") or []):
        block_id = f"page-{page_index}-block-{block_index}"
        content = str(raw_block.get("content") or "")
        table_id = _get(raw_block, "table_id", "tableId")
        block_type = raw_block.get("type") or "unknown"
        nested_block: dict[str, Any] = {
            "block_id": block_id,
            "type": block_type,
            "content": content,
            "bounding_box": _bounding_box(raw_block),
        }
        if table_id is not None:
            nested_block["table_id"] = table_id

        if block_type == "table" and table_id:
            reference_index = _table_reference_index(words, cursor, str(table_id))
            references: list[dict[str, Any]] = []
            if reference_index is not None:
                reference = words[reference_index]
                references.append(reference)
                assigned_indices.add(reference_index)
                cursor = reference_index + 1
                status = "table_reference"
            else:
                status = "unmatched"
                warnings.append(
                    {
                        "code": "TABLE_REFERENCE_NOT_FOUND",
                        "block_id": block_id,
                        "message": f"Không tìm thấy word reference cho bảng {table_id}.",
                    }
                )
            nested_block.update(
                {
                    "confidence": _confidence_summary(
                        references,
                        source="table_reference",
                        content_only=False,
                    ),
                    "mapping": {
                        "status": status,
                        "method": "table_id",
                        "coverage": 1.0 if references else 0.0,
                    },
                    "words": [],
                    "references": references,
                }
            )
            blocks.append(nested_block)
            continue

        match = _find_contiguous_match(words, cursor, content)
        if match is None:
            nested_words: list[dict[str, Any]] = []
            nested_block.update(
                {
                    "confidence": _confidence_summary(
                        nested_words,
                        source="derived_from_words",
                    ),
                    "mapping": {
                        "status": "unmatched",
                        "method": "sequential_text_alignment",
                        "coverage": 0.0,
                    },
                    "words": nested_words,
                }
            )
            warnings.append(
                {
                    "code": "BLOCK_NOT_MATCHED",
                    "block_id": block_id,
                    "message": "Không ánh xạ được block vào chuỗi word liên tiếp.",
                }
            )
            blocks.append(nested_block)
            continue

        start, end, status, coverage = match
        nested_words = words[start:end]
        assigned_indices.update(range(start, end))
        cursor = end
        nested_block.update(
            {
                "text_span": {
                    "start_index": nested_words[0]["start_index"],
                    "end_index": nested_words[-1]["end_index"],
                },
                "confidence": _confidence_summary(
                    nested_words,
                    source="derived_from_words",
                ),
                "mapping": {
                    "status": status,
                    "method": "sequential_text_alignment",
                    "coverage": coverage,
                },
                "words": nested_words,
            }
        )
        if status == "partial":
            warnings.append(
                {
                    "code": "BLOCK_PARTIALLY_MATCHED",
                    "block_id": block_id,
                    "message": "Block chỉ khớp một phần với chuỗi word.",
                    "coverage": coverage,
                }
            )
        blocks.append(nested_block)

    unassigned_words = [
        word for index, word in enumerate(words) if index not in assigned_indices
    ]
    if any(_is_content_word(word["text"]) for word in unassigned_words):
        warnings.append(
            {
                "code": "UNASSIGNED_WORDS",
                "message": "Một số word có nội dung chưa được gán vào block.",
                "count": sum(
                    _is_content_word(word["text"]) for word in unassigned_words
                ),
            }
        )

    page_confidence = _confidence_summary(words, source="mistral_word_scores")
    average = _get(
        raw_scores,
        "average_page_confidence_score",
        "averagePageConfidenceScore",
    )
    minimum = _get(
        raw_scores,
        "minimum_page_confidence_score",
        "minimumPageConfidenceScore",
    )
    if isinstance(average, (int, float)):
        page_confidence["average"] = float(average)
    if isinstance(minimum, (int, float)):
        page_confidence["minimum"] = float(minimum)

    dimensions = page.get("dimensions") or {}
    return {
        "page_index": page_index,
        "dimensions": {
            "dpi": dimensions.get("dpi"),
            "width": dimensions.get("width"),
            "height": dimensions.get("height"),
        },
        "confidence": page_confidence,
        "blocks": blocks,
        "unassigned_words": unassigned_words,
        "warnings": warnings,
    }


def restructure_mistral_ocr(
    payload: dict[str, Any],
    *,
    source_file: str | None = None,
) -> dict[str, Any]:
    """Convert Mistral OCR metadata to page -> block -> word hierarchy."""
    pages = _extract_pages(payload)
    source: dict[str, Any] = {
        "provider": payload.get("provider") or "mistral",
        "model": payload.get("model") or "mistral-ocr-latest",
        "confidence_granularity": "word",
    }
    if source_file:
        source["file"] = source_file

    return {
        "schema_version": "1.0",
        "source": source,
        "pages": [
            _restructure_page(page, page_index)
            for page_index, page in enumerate(pages)
        ],
    }

"""Normalize PaddleOCR outputs and merge OCR regions into structure blocks."""

from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable

MATCHED_CONTAINMENT_THRESHOLD = 0.70
AMBIGUOUS_CONTAINMENT_THRESHOLD = 0.40
DEFAULT_REVIEW_THRESHOLD = 0.85

BBox = tuple[float, float, float, float]


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def bbox_from_any(value: Any) -> BBox | None:
    """Convert xyxy, polygon, or named-coordinate objects to an xyxy bbox."""
    if isinstance(value, dict):
        coordinate_keys = (
            ("x1", "y1", "x2", "y2"),
            ("left", "top", "right", "bottom"),
            ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y"),
        )
        for keys in coordinate_keys:
            coordinates = [value.get(key) for key in keys]
            if all(_finite_number(item) for item in coordinates):
                return _valid_bbox(tuple(float(item) for item in coordinates))

    if not isinstance(value, (list, tuple)):
        return None
    if len(value) == 4 and all(_finite_number(item) for item in value):
        return _valid_bbox(tuple(float(item) for item in value))

    points = [
        point
        for point in value
        if isinstance(point, (list, tuple))
        and len(point) >= 2
        and _finite_number(point[0])
        and _finite_number(point[1])
    ]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return _valid_bbox((min(xs), min(ys), max(xs), max(ys)))


def _valid_bbox(bbox: BBox) -> BBox | None:
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _bbox_area(bbox: BBox) -> float:
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def _intersection_area(first: BBox, second: BBox) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height


def _containment(inner: BBox, outer: BBox) -> float:
    area = _bbox_area(inner)
    return _intersection_area(inner, outer) / area if area else 0.0


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _numeric_tokens(value: str) -> list[str]:
    return re.findall(r"\d[\d.,:/-]*", value)


def _percentile_10(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.10) - 1)
    return ordered[index]


def _confidence_summary(
    regions: list[dict[str, Any]],
    review_threshold: float,
) -> dict[str, Any]:
    values = [
        float(region["confidence"])
        for region in regions
        if _finite_number(region.get("confidence"))
    ]
    return {
        "scope": "text_region",
        "method": "aggregate_child_rec_scores",
        "minimum": min(values) if values else None,
        "p10": _percentile_10(values),
        "average": sum(values) / len(values) if values else None,
        "scored_region_count": len(values),
        "low_region_count": sum(value < review_threshold for value in values),
        "review_threshold": review_threshold,
    }


def _content_comparison(ocr_text: str, vl_text: str) -> dict[str, Any]:
    normalized_ocr = _normalize_text(ocr_text)
    normalized_vl = _normalize_text(vl_text)
    if not normalized_ocr or not normalized_vl:
        return {
            "status": "not_compared",
            "similarity": None,
            "numeric_conflict": False,
        }

    similarity = SequenceMatcher(
        None,
        normalized_ocr,
        normalized_vl,
        autojunk=False,
    ).ratio()
    ocr_numbers = _numeric_tokens(normalized_ocr)
    vl_numbers = _numeric_tokens(normalized_vl)
    numeric_conflict = bool(ocr_numbers and vl_numbers and ocr_numbers != vl_numbers)
    return {
        "status": "conflict" if numeric_conflict or similarity < 0.65 else "consistent",
        "similarity": round(similarity, 4),
        "numeric_conflict": numeric_conflict,
    }


def normalize_paddle_ocr_page(
    payload: dict[str, Any],
    *,
    page_index: int,
) -> list[dict[str, Any]]:
    """Convert one PaddleOCR result page into OCR text regions."""
    result = payload.get("res") if isinstance(payload.get("res"), dict) else payload
    texts = result.get("rec_texts") or []
    scores = result.get("rec_scores") or []
    boxes = result.get("rec_boxes") or result.get("rec_polys") or []

    regions: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        bbox = bbox_from_any(boxes[index]) if index < len(boxes) else None
        if bbox is None:
            continue
        score = scores[index] if index < len(scores) else None
        regions.append(
            {
                "id": f"page-{page_index}-region-{index}",
                "text": str(text or ""),
                "bbox": list(bbox),
                "confidence": float(score) if _finite_number(score) else None,
                "confidence_scope": "text_region",
                "source": "PP_OCR",
            }
        )
    return regions


def normalize_paddle_structure_page(
    payload: dict[str, Any],
    *,
    page_index: int,
) -> list[dict[str, Any]]:
    """Convert one PaddleOCR-VL result page into structure blocks."""
    result = payload.get("res") if isinstance(payload.get("res"), dict) else payload
    parsing_results = result.get("parsing_res_list") or []
    layout_boxes = (result.get("layout_det_res") or {}).get("boxes") or []
    if not layout_boxes and isinstance(result.get("boxes"), list):
        layout_boxes = result["boxes"]

    normalized_layout: list[dict[str, Any]] = []
    for box in layout_boxes:
        bbox = bbox_from_any(box.get("coordinate") or box.get("bbox"))
        if bbox is not None:
            normalized_layout.append({**box, "normalized_bbox": bbox})

    blocks: list[dict[str, Any]] = []
    if not parsing_results:
        for index, layout in enumerate(normalized_layout):
            blocks.append(
                {
                    "id": f"page-{page_index}-block-{index}",
                    "type": str(layout.get("label") or "unknown"),
                    "bbox": list(layout["normalized_bbox"]),
                    "reading_order": index,
                    "vl_content": "",
                    "layout_confidence": (
                        float(layout["score"])
                        if _finite_number(layout.get("score"))
                        else None
                    ),
                    "source": "PP_DOC_LAYOUT_V3",
                }
            )
        return blocks

    for index, raw_block in enumerate(parsing_results):
        bbox = bbox_from_any(raw_block.get("block_bbox") or raw_block.get("bbox"))
        if bbox is None:
            continue
        block_type = str(raw_block.get("block_label") or raw_block.get("type") or "unknown")
        matching_layout = [
            layout
            for layout in normalized_layout
            if str(layout.get("label") or "") == block_type
        ]
        layout_score = None
        if matching_layout:
            best_layout = max(
                matching_layout,
                key=lambda item: _intersection_area(bbox, item["normalized_bbox"]),
            )
            if _intersection_area(bbox, best_layout["normalized_bbox"]) > 0:
                score = best_layout.get("score")
                layout_score = float(score) if _finite_number(score) else None

        blocks.append(
            {
                "id": f"page-{page_index}-block-{index}",
                "type": block_type,
                "bbox": list(bbox),
                "reading_order": raw_block.get("block_order", index),
                "vl_content": str(raw_block.get("block_content") or ""),
                "layout_confidence": layout_score,
                "source": "PADDLE_OCR_VL",
            }
        )
    return blocks


def _sorted_regions(regions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        regions,
        key=lambda region: (
            (region.get("bbox") or [0, 0, 0, 0])[1],
            (region.get("bbox") or [0, 0, 0, 0])[0],
        ),
    )


def merge_ocr_structure_page(
    *,
    page_index: int,
    width: int,
    height: int,
    ocr_regions: list[dict[str, Any]],
    structure_blocks: list[dict[str, Any]],
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> dict[str, Any]:
    """Assign OCR regions to structure blocks and aggregate block metadata."""
    warnings: list[dict[str, Any]] = []
    valid_blocks: list[dict[str, Any]] = []
    for block in structure_blocks:
        bbox = bbox_from_any(block.get("bbox"))
        if bbox is None:
            warnings.append({"code": "INVALID_BLOCK_BBOX", "block_id": block.get("id")})
            continue
        valid_blocks.append({**block, "bbox": list(bbox), "_bbox": bbox})

    if not valid_blocks:
        for index, region in enumerate(ocr_regions):
            bbox = bbox_from_any(region.get("bbox"))
            if bbox is None:
                continue
            valid_blocks.append(
                {
                    "id": f"page-{page_index}-fallback-block-{index}",
                    "type": "text",
                    "bbox": list(bbox),
                    "_bbox": bbox,
                    "reading_order": index,
                    "vl_content": "",
                    "layout_confidence": None,
                    "source": "OCR_FALLBACK",
                }
            )
        if valid_blocks:
            warnings.append({"code": "STRUCTURE_FALLBACK_USED"})

    assignments: dict[str, list[dict[str, Any]]] = {
        str(block["id"]): [] for block in valid_blocks
    }
    unmatched: list[dict[str, Any]] = []

    for region in ocr_regions:
        region_bbox = bbox_from_any(region.get("bbox"))
        if region_bbox is None:
            warnings.append({"code": "INVALID_OCR_BBOX", "region_id": region.get("id")})
            unmatched.append({**region, "mapping_status": "invalid_bbox"})
            continue

        candidates = [
            (
                _containment(region_bbox, block["_bbox"]),
                _bbox_area(block["_bbox"]),
                block,
            )
            for block in valid_blocks
            if _intersection_area(region_bbox, block["_bbox"]) > 0
        ]
        if not candidates:
            unmatched.append({**region, "mapping_status": "unmatched"})
            continue

        candidates.sort(key=lambda item: (-item[0], item[1]))
        containment, _, selected = candidates[0]
        if containment < AMBIGUOUS_CONTAINMENT_THRESHOLD:
            unmatched.append(
                {
                    **region,
                    "mapping_status": "unmatched",
                    "best_containment": round(containment, 4),
                }
            )
            continue

        mapping_status = (
            "matched"
            if containment >= MATCHED_CONTAINMENT_THRESHOLD
            else "ambiguous"
        )
        assignments[str(selected["id"])].append(
            {
                **region,
                "bbox": list(region_bbox),
                "mapping_status": mapping_status,
                "containment": round(containment, 4),
            }
        )

    merged_blocks: list[dict[str, Any]] = []
    for block in sorted(
        valid_blocks,
        key=lambda item: (
            item.get("reading_order") is None,
            item.get("reading_order") if item.get("reading_order") is not None else 0,
        ),
    ):
        block_regions = _sorted_regions(assignments[str(block["id"])])
        ocr_text = "\n".join(
            region.get("text", "").strip()
            for region in block_regions
            if region.get("text", "").strip()
        )
        vl_text = str(block.get("vl_content") or "")
        confidence = _confidence_summary(block_regions, review_threshold)
        comparison = _content_comparison(ocr_text, vl_text)
        mapping_status = "empty"
        if block_regions:
            mapping_status = (
                "ambiguous"
                if any(region["mapping_status"] == "ambiguous" for region in block_regions)
                else "matched"
            )

        merged_blocks.append(
            {
                "id": block["id"],
                "type": block.get("type", "unknown"),
                "bbox": block["bbox"],
                "reading_order": block.get("reading_order"),
                "text": ocr_text or vl_text,
                "text_source": "PP_OCR" if ocr_text else "PADDLE_OCR_VL",
                "vl_text": vl_text,
                "layout_confidence": block.get("layout_confidence"),
                "ocr_regions": block_regions,
                "words": [],
                "block_confidence": confidence["minimum"],
                "confidence": confidence,
                "mapping": {
                    "status": mapping_status,
                    "method": "bbox_containment",
                    "region_count": len(block_regions),
                },
                "content_comparison": comparison,
            }
        )

    return {
        "page_index": page_index,
        "dimensions": {"width": width, "height": height},
        "coordinate_space": "processed_page",
        "blocks": merged_blocks,
        "unmatched_ocr_regions": unmatched,
        "warnings": warnings,
    }


def build_ocr_structure_document(
    pages: list[dict[str, Any]],
    *,
    file_name: str,
    ocr_model: str,
    structure_model: str,
) -> dict[str, Any]:
    """Wrap merged pages in the public OCR structure schema."""
    block_count = sum(len(page.get("blocks") or []) for page in pages)
    unmatched_count = sum(
        len(page.get("unmatched_ocr_regions") or []) for page in pages
    )
    return {
        "schema_version": "1.0",
        "source": {
            "file_name": file_name,
            "ocr_model": ocr_model,
            "structure_model": structure_model,
            "confidence_granularity": "text_region",
        },
        "summary": {
            "page_count": len(pages),
            "block_count": block_count,
            "unmatched_ocr_region_count": unmatched_count,
        },
        "pages": pages,
    }


__all__ = [
    "AMBIGUOUS_CONTAINMENT_THRESHOLD",
    "MATCHED_CONTAINMENT_THRESHOLD",
    "bbox_from_any",
    "build_ocr_structure_document",
    "merge_ocr_structure_page",
    "normalize_paddle_ocr_page",
    "normalize_paddle_structure_page",
]

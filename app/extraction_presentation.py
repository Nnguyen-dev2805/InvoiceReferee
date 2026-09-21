"""Pure presentation helpers for the OCR confirmation UI (no Streamlit import).

These turn an ``InvoiceExtractionResult`` into display rows, draw a bounding-box
overlay on a page image, and build ``FieldReview`` commands from submitted form
values. Kept import-light so they are unit-testable without Streamlit.
"""

from __future__ import annotations

import io
from typing import Any

from invoice_referee.domain import models as m
from invoice_referee.ingestion.pipeline import FieldReview


def field_rows(result: m.InvoiceExtractionResult) -> list[dict]:
    """Build header-field display rows with method, scores, section, and conflict info."""
    return [
        {
            "field": name,
            "value": candidate.normalized_value,
            "confidence": candidate.confidence,
            "ocr_confidence": candidate.provider_confidence,
            "mapping_score": candidate.mapping_score,
            "method": candidate.extraction_method,
            "alternatives": len(alternatives_for(result, name)),
            "evidence": list(candidate.evidence_block_ids),
            "status": candidate.status.value,
            "page": candidate.page_number,
            "warnings": "; ".join(candidate.warnings),
        }
        for name, candidate in result.fields.items()
    ]


def line_item_rows(result: m.InvoiceExtractionResult) -> list[dict]:
    return [
        {name: candidate.normalized_value for name, candidate in line.items()}
        for line in result.line_items
    ]


def alternatives_for(result: m.InvoiceExtractionResult, field_name: str) -> list[dict]:
    """Return alternatives (non-selected candidates) for a field, for audit/review.

    Each dict contains method, raw value, normalized value, and evidence block IDs.
    The currently selected candidate is excluded.
    """
    candidates = result.field_candidates.get(field_name, [])
    if not candidates:
        return []
    selected = result.fields.get(field_name)
    selected_id = id(selected)
    return [
        {
            "method": c.extraction_method,
            "raw_value": c.raw_text,
            "value": c.normalized_value,
            "evidence": list(c.evidence_block_ids),
        }
        for c in candidates
        if id(c) != selected_id and c.normalized_value is not None
    ]


def review_is_ready(result: m.InvoiceExtractionResult) -> bool:
    """Whether extraction has been fully reviewed and may proceed to business review."""
    return result.status is m.ExtractionStatus.REVIEWED


def draw_candidate_overlay(page: m.DocumentPage, candidate: m.FieldCandidate) -> bytes:
    """Return PNG bytes of the page image with the candidate's box outlined."""
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(page.image_bytes)).convert("RGB")
    if candidate.bounding_box is not None:
        box = candidate.bounding_box
        ImageDraw.Draw(image).rectangle(
            (
                box.x1 * image.width,
                box.y1 * image.height,
                box.x2 * image.width,
                box.y2 * image.height,
            ),
            outline="red",
            width=4,
        )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _review_from_submission(submitted: dict[str, Any]) -> FieldReview:
    action = submitted["action"]
    if action == "CONFIRM":
        return FieldReview.confirm()
    if action == "CORRECT":
        return FieldReview.correct(submitted["value"], reason=submitted.get("reason", ""))
    return FieldReview.mark_unknown(submitted.get("reason", ""))


def build_field_reviews(
    form_values: dict[str, dict],
    result: m.InvoiceExtractionResult,
) -> dict[str, FieldReview]:
    """Turn submitted per-field form values into FieldReview commands.

    Header keys are the field name; line-item keys are
    ``line_items[{index}].{field_name}``.
    """
    reviews: dict[str, FieldReview] = {}
    for name in result.fields:
        if name in form_values:
            reviews[name] = _review_from_submission(form_values[name])
    for index, line in enumerate(result.line_items):
        for name in line:
            key = f"line_items[{index}].{name}"
            if key in form_values:
                reviews[key] = _review_from_submission(form_values[key])
    return reviews


def critical_unresolved_count(result: m.InvoiceExtractionResult) -> int:
    """How many critical header fields still need a human decision."""
    from invoice_referee.ingestion.extraction_validation import CRITICAL_FIELDS

    resolved = {m.FieldStatus.CONFIRMED, m.FieldStatus.CORRECTED}
    return sum(
        1
        for name in CRITICAL_FIELDS
        if name in result.fields and result.fields[name].status not in resolved
    )

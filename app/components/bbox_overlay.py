"""Render OCR block bounding boxes on a source image."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

GOOD_COLOR = "#12805C"
REVIEW_COLOR = "#D97706"
LOW_COLOR = "#D92D20"
UNKNOWN_COLOR = "#667085"


def _block_color(block: dict[str, Any]) -> str:
    mapping_status = (block.get("mapping") or {}).get("status")
    if mapping_status == "unmatched":
        return LOW_COLOR
    if mapping_status == "partial":
        return REVIEW_COLOR

    minimum = (block.get("confidence") or {}).get("minimum")
    if not isinstance(minimum, (int, float)):
        return UNKNOWN_COLOR
    if minimum < 0.70:
        return LOW_COLOR
    if minimum < 0.85:
        return REVIEW_COLOR
    return GOOD_COLOR


def _scaled_box(
    bounding_box: dict[str, Any],
    *,
    scale_x: float,
    scale_y: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int] | None:
    coordinates = (
        bounding_box.get("top_left_x"),
        bounding_box.get("top_left_y"),
        bounding_box.get("bottom_right_x"),
        bounding_box.get("bottom_right_y"),
    )
    if not all(isinstance(value, (int, float)) for value in coordinates):
        return None

    left, top, right, bottom = coordinates
    left = max(0, min(image_width - 1, round(left * scale_x)))
    top = max(0, min(image_height - 1, round(top * scale_y)))
    right = max(0, min(image_width - 1, round(right * scale_x)))
    bottom = max(0, min(image_height - 1, round(bottom * scale_y)))
    if right < left or bottom < top:
        return None
    return left, top, right, bottom


def render_bbox_overlay(image_path: Path, page: dict[str, Any]) -> Image.Image:
    """Return an EXIF-corrected image annotated with hierarchical OCR blocks."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    dimensions = page.get("dimensions") or {}
    ocr_width = dimensions.get("width")
    ocr_height = dimensions.get("height")
    if not isinstance(ocr_width, (int, float)) or ocr_width <= 0:
        raise ValueError("OCR page width không hợp lệ.")
    if not isinstance(ocr_height, (int, float)) or ocr_height <= 0:
        raise ValueError("OCR page height không hợp lệ.")

    scale_x = image.width / ocr_width
    scale_y = image.height / ocr_height
    line_width = max(3, round(min(image.width, image.height) / 220))
    font_size = max(14, round(image.width / 34))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    draw = ImageDraw.Draw(image)

    for block_number, block in enumerate(page.get("blocks") or [], start=1):
        box = _scaled_box(
            block.get("bounding_box") or {},
            scale_x=scale_x,
            scale_y=scale_y,
            image_width=image.width,
            image_height=image.height,
        )
        if box is None:
            continue

        color = _block_color(block)
        draw.rectangle(box, outline=color, width=line_width)
        label = f"B{block_number:02d}"
        text_box = draw.textbbox((0, 0), label, font=font)
        label_width = text_box[2] - text_box[0] + 8
        label_height = text_box[3] - text_box[1] + 6
        label_left = box[0]
        label_top = max(0, box[1] - label_height)
        draw.rectangle(
            (
                label_left,
                label_top,
                min(image.width - 1, label_left + label_width),
                min(image.height - 1, label_top + label_height),
            ),
            fill=color,
        )
        draw.text(
            (label_left + 4, label_top + 2),
            label,
            fill="white",
            font=font,
        )

    return image

"""Render a source document page with one OCR review region highlighted."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

BOX_COLOR = (194, 45, 35, 255)
BOX_FILL = (194, 45, 35, 44)


def _load_page(path: Path, page_index: int) -> Image.Image:
    if page_index < 0:
        raise ValueError("Chỉ số trang không hợp lệ.")
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as document:
            if page_index >= document.page_count:
                raise ValueError("Trang OCR không tồn tại trong PDF.")
            pixmap = document[page_index].get_pixmap(
                matrix=pymupdf.Matrix(2, 2),
                alpha=False,
            )
            return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    with Image.open(path) as source:
        try:
            source.seek(page_index)
        except EOFError as exc:
            raise ValueError("Trang OCR không tồn tại trong ảnh.") from exc
        return ImageOps.exif_transpose(source).convert("RGB")


def render_ocr_block_preview(
    path: Path,
    *,
    page_index: int,
    bounding_box: dict[str, Any],
    ocr_width: float,
    ocr_height: float,
) -> Image.Image:
    """Return the requested page with a visible box around one OCR block."""

    if ocr_width <= 0 or ocr_height <= 0:
        raise ValueError("Kích thước trang OCR không hợp lệ.")
    image = _load_page(path, page_index)
    image.thumbnail((2200, 3000), Image.Resampling.LANCZOS)
    coordinates = (
        bounding_box.get("top_left_x"),
        bounding_box.get("top_left_y"),
        bounding_box.get("bottom_right_x"),
        bounding_box.get("bottom_right_y"),
    )
    if not all(isinstance(value, (int, float)) for value in coordinates):
        raise ValueError("Bounding box OCR không hợp lệ.")

    left, top, right, bottom = coordinates
    scale_x = image.width / float(ocr_width)
    scale_y = image.height / float(ocr_height)
    box = (
        max(0, min(image.width - 1, round(float(left) * scale_x))),
        max(0, min(image.height - 1, round(float(top) * scale_y))),
        max(0, min(image.width - 1, round(float(right) * scale_x))),
        max(0, min(image.height - 1, round(float(bottom) * scale_y))),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("Bounding box OCR không có diện tích hợp lệ.")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    line_width = max(4, round(min(image.size) / 180))
    draw.rectangle(box, fill=BOX_FILL, outline=BOX_COLOR, width=line_width)

    label = "Vùng OCR cần kiểm tra"
    font_size = max(16, round(image.width / 48))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    text_box = draw.textbbox((0, 0), label, font=font)
    label_width = text_box[2] - text_box[0] + 16
    label_height = text_box[3] - text_box[1] + 12
    label_left = box[0]
    label_top = max(0, box[1] - label_height)
    draw.rectangle(
        (
            label_left,
            label_top,
            min(image.width - 1, label_left + label_width),
            min(image.height - 1, label_top + label_height),
        ),
        fill=BOX_COLOR,
    )
    draw.text(
        (label_left + 8, label_top + 5),
        label,
        fill="white",
        font=font,
    )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

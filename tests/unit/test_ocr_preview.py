"""OCR preview renderer: real box on real bytes, honest refusals."""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.evidence.ocr_preview import render_ocr_block_preview


def _pdf(tmp_path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("T", str(Path("assets/fonts/NotoSans-Regular.ttf"))))
    path = tmp_path / "doc.pdf"
    doc = canvas.Canvas(str(path), pagesize=A4)
    doc.setFont("T", 14)
    doc.drawString(60, 750, "Số tiền: 1500000")
    doc.showPage()
    doc.save()
    return path


def test_renders_box_on_pdf_page(tmp_path: Path) -> None:
    image = render_ocr_block_preview(
        _pdf(tmp_path),
        page_index=0,
        bounding_box={
            "top_left_x": 50.0,
            "top_left_y": 60.0,
            "bottom_right_x": 300.0,
            "bottom_right_y": 120.0,
        },
        ocr_width=595.0,
        ocr_height=842.0,
    )
    assert image.size[0] > 0 and image.size[1] > 0
    # The box is actually drawn: red-ish pixels exist around the box area.
    pixels = image.load()
    reds = sum(
        1
        for x in range(0, image.size[0], 7)
        for y in range(0, image.size[1], 7)
        if pixels[x, y][0] > 150 and pixels[x, y][1] < 100
    )
    assert reds > 0


def test_vietnamese_label_renders_without_tofu(tmp_path: Path) -> None:
    image = render_ocr_block_preview(
        _pdf(tmp_path),
        page_index=0,
        bounding_box={
            "top_left_x": 50.0,
            "top_left_y": 60.0,
            "bottom_right_x": 300.0,
            "bottom_right_y": 120.0,
        },
        ocr_width=595.0,
        ocr_height=842.0,
    )
    # Label band is drawn (dark red pixels in the top strip above the box).
    pixels = image.load()
    dark_reds = sum(
        1
        for x in range(0, image.size[0], 5)
        for y in range(0, 120, 5)
        if pixels[x, y][0] > 120 and pixels[x, y][1] < 110
    )
    assert dark_reds > 0


def test_invalid_box_or_page_is_refused_not_invented(tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    with pytest.raises(ValueError):
        render_ocr_block_preview(
            path,
            page_index=5,
            bounding_box={
                "top_left_x": 1.0,
                "top_left_y": 1.0,
                "bottom_right_x": 2.0,
                "bottom_right_y": 2.0,
            },
            ocr_width=595.0,
            ocr_height=842.0,
        )
    with pytest.raises(ValueError):
        render_ocr_block_preview(
            path,
            page_index=0,
            bounding_box={
                "top_left_x": 10.0,
                "top_left_y": 10.0,
                "bottom_right_x": 10.0,
                "bottom_right_y": 10.0,
            },
            ocr_width=595.0,
            ocr_height=842.0,
        )

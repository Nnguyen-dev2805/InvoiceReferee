"""Tests for baseline image preprocessing (requires the ``ocr`` extra)."""

from __future__ import annotations

import io

import pytest

pytest.importorskip("PIL")
pytest.importorskip("cv2")

from PIL import Image  # noqa: E402

from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.ingestion.image_preprocessing import preprocess_pages  # noqa: E402


def _page_from_image(img: Image.Image, warnings=None) -> m.DocumentPage:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return m.DocumentPage(
        document_id="DOC-1",
        page_number=1,
        image_bytes=buffer.getvalue(),
        width=img.width,
        height=img.height,
        dpi=300,
        native_text=None,
        warnings=list(warnings or []),
    )


def _text_image(size=(1000, 700), skew_degrees: float = 0.0) -> Image.Image:
    from PIL import ImageDraw

    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for row in range(80, size[1] - 80, 60):
        draw.rectangle([120, row, size[0] - 120, row + 24], fill=(0, 0, 0))
    if skew_degrees:
        img = img.rotate(skew_degrees, expand=True, fillcolor=(255, 255, 255))
    return img


def test_preprocessing_returns_rgb_png_page():
    page = _page_from_image(_text_image())
    processed = preprocess_pages([page])[0]
    assert processed.image_bytes.startswith(b"\x89PNG")
    assert processed.dpi == 300
    assert processed.page_number == 1


def test_preprocessing_applies_exif_orientation():
    # A portrait image tagged as EXIF orientation 6 must come out landscape.
    from PIL import Image as PILImage

    base = PILImage.new("RGB", (400, 800), (255, 255, 255))
    buffer = io.BytesIO()
    exif = base.getexif()
    exif[274] = 6  # Orientation tag: rotate 90° CW
    base.save(buffer, format="JPEG", exif=exif)
    page = m.DocumentPage(
        document_id="DOC-1",
        page_number=1,
        image_bytes=buffer.getvalue(),
        width=400,
        height=800,
        dpi=300,
        native_text=None,
    )
    processed = preprocess_pages([page])[0]
    assert processed.width > processed.height


def test_large_skew_is_warned_not_destructively_rotated():
    page = _page_from_image(_text_image(skew_degrees=20))
    processed = preprocess_pages([page])[0]
    assert any("skew" in w.lower() for w in processed.warnings)


def test_no_content_image_is_left_unrotated_without_warning():
    blank = Image.new("RGB", (600, 400), (255, 255, 255))
    processed = preprocess_pages([_page_from_image(blank)])[0]
    assert not any("skew" in w.lower() for w in processed.warnings)


def test_preprocessing_preserves_native_text_and_prior_warnings():
    page = _page_from_image(_text_image())
    page.native_text = "Invoice No: 123"
    page.warnings.append("pre-existing warning")
    processed = preprocess_pages([page])[0]
    assert processed.native_text == "Invoice No: 123"
    assert "pre-existing warning" in processed.warnings

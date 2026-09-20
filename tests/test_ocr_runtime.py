import os

import pytest


pytestmark = pytest.mark.ocr_runtime


@pytest.mark.skipif(
    os.environ.get("RUN_OCR_RUNTIME") != "1",
    reason="set RUN_OCR_RUNTIME=1 in an environment with the OCR extra installed",
)
def test_local_ocr_runtime_imports_and_initializes():
    import fitz
    import paddle
    from paddleocr import PPStructureV3

    assert fitz.VersionBind
    assert tuple(int(part) for part in paddle.__version__.split(".")[:2]) >= (3, 3)
    assert PPStructureV3 is not None


@pytest.mark.skipif(
    os.environ.get("RUN_OCR_RUNTIME") != "1",
    reason="set RUN_OCR_RUNTIME=1 in an environment with the OCR extra installed",
)
def test_local_ocr_runtime_reads_a_generated_invoice():
    """One real local inference over a generated one-page invoice image."""
    import io

    from PIL import Image, ImageDraw

    from invoice_referee.domain import models as m
    from invoice_referee.ingestion.ocr import PaddleOCREngine

    img = Image.new("RGB", (1000, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((80, 80), "INVOICE", fill=(0, 0, 0))
    draw.text((80, 160), "So: 0000123", fill=(0, 0, 0))
    draw.text((80, 240), "Tong cong: 30.000.000 VND", fill=(0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    page = m.DocumentPage(
        document_id="DOC-runtime",
        page_number=1,
        image_bytes=buffer.getvalue(),
        width=1000,
        height=700,
        dpi=300,
        native_text=None,
    )

    result = PaddleOCREngine().analyze([page])
    assert result.blocks, "local OCR returned no blocks"
    upper = result.full_text.upper()
    assert "INVOICE" in upper or any(ch.isdigit() for ch in result.full_text)

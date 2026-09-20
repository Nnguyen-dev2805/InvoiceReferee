"""Render validated documents into DocumentPage images.

PDF pages are rasterized at 300 DPI; embedded native text is preserved as
secondary evidence (it does not bypass OCR). Images are decoded and normalized
to RGB, then re-encoded as a single lossless PNG page. No temporary file is
required: everything works on in-memory bytes.

Heavy providers are imported lazily so the JSON path runs without the ``ocr``
extra.
"""

from __future__ import annotations

import io

from invoice_referee.domain import models as m

RENDER_DPI = 300


def render_pdf(document: m.UploadedDocument) -> list[m.DocumentPage]:
    import pymupdf

    pages: list[m.DocumentPage] = []
    doc = pymupdf.open(stream=document.content, filetype="pdf")
    try:
        zoom = RENDER_DPI / 72
        matrix = pymupdf.Matrix(zoom, zoom)
        for index, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pixmap.tobytes("png")
            native_text = (page.get_text("text") or "").strip() or None
            pages.append(
                m.DocumentPage(
                    document_id=document.document_id,
                    page_number=index,
                    image_bytes=image_bytes,
                    width=pixmap.width,
                    height=pixmap.height,
                    dpi=RENDER_DPI,
                    native_text=native_text,
                )
            )
    finally:
        doc.close()
    return pages


def render_image(document: m.UploadedDocument) -> list[m.DocumentPage]:
    from PIL import Image

    with Image.open(io.BytesIO(document.content)) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        buffer = io.BytesIO()
        rgb.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    return [
        m.DocumentPage(
            document_id=document.document_id,
            page_number=1,
            image_bytes=image_bytes,
            width=width,
            height=height,
            dpi=RENDER_DPI,
            native_text=None,  # images carry no embedded text layer
        )
    ]

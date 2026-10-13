"""Bounded native PDF helpers (contracts §6, §8; plan T5).

Native text extraction and page rendering with hard limits (pages, image
pixels). Native text presence alone does not prove the visual truth: a scan or
hybrid document needs OCR or a rendered comparison, so callers get both the
text and a render callback rather than a single "is readable" verdict.
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_PAGES = 20
MAX_IMAGE_PIXELS = 20_000_000


class PdfLimitError(ValueError):
    """A PDF exceeded a pilot ceiling (page count / image pixels)."""


def native_text(pdf_path: Path, *, max_pages: int = MAX_PAGES) -> dict[int, str]:
    """Extract native text per 1-based page, bounded by page count."""
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    if len(reader.pages) > max_pages:
        raise PdfLimitError(f"PDF has {len(reader.pages)} pages > limit {max_pages}")
    result: dict[int, str] = {}
    for index, page in enumerate(reader.pages, start=1):
        result[index] = page.extract_text() or ""
    return result


def render_page_png(
    pdf_path: Path, page: int, *, scale: float = 2.0, max_pixels: int = MAX_IMAGE_PIXELS
) -> bytes:
    """Render one 1-based page to PNG bytes, bounded by image pixels."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    bitmap = pdf[page - 1].render(scale=scale)
    image = bitmap.to_pil()
    if image.width * image.height > max_pixels:
        raise PdfLimitError(
            f"rendered image {image.width}x{image.height} exceeds {max_pixels} pixels"
        )
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def page_count(pdf_path: Path) -> int:
    import pypdf

    return len(pypdf.PdfReader(str(pdf_path)).pages)

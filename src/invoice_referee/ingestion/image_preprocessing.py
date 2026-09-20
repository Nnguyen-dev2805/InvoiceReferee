"""Baseline image preprocessing for the OCR path.

Accepted Sprint 1 baseline (OCR design §9.3):
- EXIF orientation normalization;
- RGB normalization;
- deskew ONLY for an estimated angle in [0.5, 10] degrees;
- a larger skew is warned, never destructively rotated;
- NO denoise, unwarp, or contrast enhancement (they can destroy small
  invoice characters).

Providers (Pillow, OpenCV) are imported lazily so the JSON path runs without
the ``ocr`` extra.
"""

from __future__ import annotations

import io
from typing import Optional

from invoice_referee.domain import models as m

MIN_DESKEW_DEG = 0.5
MAX_DESKEW_DEG = 10.0


def preprocess_pages(pages: list[m.DocumentPage]) -> list[m.DocumentPage]:
    return [_preprocess_page(page) for page in pages]


def _preprocess_page(page: m.DocumentPage) -> m.DocumentPage:
    from PIL import Image, ImageOps

    warnings = list(page.warnings)

    with Image.open(io.BytesIO(page.image_bytes)) as opened:
        # EXIF orientation first, then a stable RGB working copy.
        img = ImageOps.exif_transpose(opened)
        img = img.convert("RGB")

        skew = _estimate_skew(img)
        if skew is not None and MIN_DESKEW_DEG <= abs(skew) <= MAX_DESKEW_DEG:
            img = img.rotate(-skew, expand=True, fillcolor=(255, 255, 255))
        elif skew is not None and abs(skew) > MAX_DESKEW_DEG:
            warnings.append(
                f"Large skew ~{skew:.1f}° detected; left uncorrected to avoid "
                "destroying characters"
            )

        width, height = img.size
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    return m.DocumentPage(
        document_id=page.document_id,
        page_number=page.page_number,
        image_bytes=image_bytes,
        width=width,
        height=height,
        dpi=page.dpi,
        native_text=page.native_text,
        warnings=warnings,
    )


def _estimate_skew(img) -> Optional[float]:
    """Estimate page skew in degrees from dark (text) pixels.

    Returns ``None`` when there is not enough content to estimate reliably.
    Positive/negative sign follows a clockwise-positive convention suitable for
    ``PIL.Image.rotate(-skew)``.
    """
    import cv2
    import numpy as np

    gray = np.array(img.convert("L"))
    # Text becomes white on black so findNonZero picks up the characters.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None or len(coords) < 50:
        return None

    angle = cv2.minAreaRect(coords)[-1]
    # OpenCV returns the angle in (0, 90]; fold it into (-45, 45].
    if angle > 45:
        angle -= 90
    return float(angle)

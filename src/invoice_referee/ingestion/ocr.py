"""OCR engine boundary and the local PaddleOCR/PP-StructureV3 adapter.

Downstream code depends only on the provider-neutral ``OCRDocument``. The
provider-specific shape stops here: ``map_paddle_response`` converts a recorded
or live response into ``OCRBlock`` objects, and ``PaddleOCREngine`` wraps the
local model behind the ``OCREngine`` protocol.

The recorded/adapter response schema (provider-neutral) is::

    {
      "pages": [
        {
          "page_number": 1,
          "blocks": [
            {
              "block_id": "BLK-001",
              "text": "30.000.000 VND",
              "confidence": 0.97,
              "poly": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],  # pixel coords
              "block_type": "TEXT",          # TEXT | KEY_VALUE | TABLE_CELL
              "row_index": null,
              "column_index": null
            }
          ]
        }
      ]
    }

PaddleOCR is imported lazily so the JSON-only and recorded-response paths run
without the optional ``ocr`` extra.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Protocol

from invoice_referee.domain import models as m

ENGINE_NAME = "paddleocr-pp-structure-v3"


class OCREngine(Protocol):
    def analyze(self, pages: list[m.DocumentPage]) -> m.OCRDocument:
        ...


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _normalized_box(poly: list[list[float]], width: int, height: int) -> m.BoundingBox:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    w = float(width) or 1.0
    h = float(height) or 1.0
    x1 = _clamp01(min(xs) / w)
    x2 = _clamp01(max(xs) / w)
    y1 = _clamp01(min(ys) / h)
    y2 = _clamp01(max(ys) / h)
    return m.BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)


def map_paddle_response(raw: Any, pages: list[m.DocumentPage]) -> list[m.OCRBlock]:
    """Map a provider-neutral response into ``OCRBlock`` objects with provenance.

    Coordinates are normalized against the matching page's dimensions so UI
    rendering is independent of pixel resolution.
    """
    dims = {p.page_number: (p.width, p.height) for p in pages}
    blocks: list[m.OCRBlock] = []
    for page in raw.get("pages", []):
        page_number = page.get("page_number", 1)
        width, height = dims.get(page_number, (1, 1))
        for block in page.get("blocks", []):
            poly = block.get("poly")
            box = _normalized_box(poly, width, height) if poly else m.BoundingBox(0.0, 0.0, 1.0, 1.0)
            blocks.append(
                m.OCRBlock(
                    block_id=block["block_id"],
                    page_number=page_number,
                    text=block.get("text", ""),
                    confidence=float(block.get("confidence", 0.0)),
                    bounding_box=box,
                    block_type=block.get("block_type", "TEXT"),
                    row_index=block.get("row_index"),
                    column_index=block.get("column_index"),
                )
            )
    return blocks


class PaddleOCREngine:
    """Local PaddleOCR/PP-StructureV3 adapter.

    A ``runner`` may be injected for deterministic tests; by default the local
    model is built lazily on first use.
    """

    def __init__(self, runner=None, engine_version: Optional[str] = None):
        self._runner = runner
        self._engine_version = engine_version

    def analyze(self, pages: list[m.DocumentPage]) -> m.OCRDocument:
        if not pages:
            raise ValueError("analyze requires at least one page")
        runner = self._runner or self._build_runner()
        started = time.perf_counter()
        raw = runner(pages)
        blocks = map_paddle_response(raw, pages)
        return m.OCRDocument(
            document_id=pages[0].document_id,
            pages=pages,
            blocks=blocks,
            full_text="\n".join(block.text for block in blocks),
            engine=ENGINE_NAME,
            engine_version=self._engine_version or self._resolve_version(),
            processing_ms=int((time.perf_counter() - started) * 1000),
            warnings=[],
        )

    def _resolve_version(self) -> str:
        try:
            import paddleocr

            return f"paddleocr-{paddleocr.__version__}"
        except Exception:
            return "unknown"

    def _build_runner(self):
        """Build a runner backed by the local PP-StructureV3 model (lazy import)."""
        import io

        import numpy as np
        from paddleocr import PPStructureV3
        from PIL import Image

        pipeline = PPStructureV3()

        def _run(pages: list[m.DocumentPage]) -> dict:
            out_pages = []
            for page in pages:
                image = np.array(Image.open(io.BytesIO(page.image_bytes)).convert("RGB"))
                result = pipeline.predict(image)
                out_pages.append(
                    {
                        "page_number": page.page_number,
                        "blocks": _blocks_from_ppstructure(result, page.page_number),
                    }
                )
            return {"pages": out_pages}

        return _run


def _blocks_from_ppstructure(result: Any, page_number: int) -> list[dict]:
    """Best-effort conversion of PP-StructureV3 output into the neutral schema.

    PP-StructureV3 output shape varies by version, so this reads the common
    OCR text/score/box fields defensively. Live-model behavior is exercised only
    by the ``ocr_runtime`` smoke test; deterministic tests use recorded JSON.
    """
    blocks: list[dict] = []
    counter = 0
    items = result if isinstance(result, list) else [result]
    for item in items:
        ocr = None
        if isinstance(item, dict):
            ocr = item.get("overall_ocr_res") or item.get("ocr_res") or item
        rec_texts = _get(ocr, "rec_texts") or []
        rec_scores = _get(ocr, "rec_scores") or []
        rec_polys = _get(ocr, "rec_polys") or _get(ocr, "dt_polys") or []
        for idx, text in enumerate(rec_texts):
            counter += 1
            score = rec_scores[idx] if idx < len(rec_scores) else 0.0
            poly = rec_polys[idx] if idx < len(rec_polys) else None
            poly_list = [[float(x), float(y)] for x, y in poly] if poly is not None else None
            blocks.append(
                {
                    "block_id": f"P{page_number}-B{counter:04d}",
                    "text": str(text),
                    "confidence": float(score),
                    "poly": poly_list,
                    "block_type": "TEXT",
                }
            )
    return blocks


def _get(obj: Any, key: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

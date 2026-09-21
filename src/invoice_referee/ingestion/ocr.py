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

import re
import time
from typing import Any, Optional, Protocol

from invoice_referee.domain import models as m

ENGINE_NAME = "paddleocr-pp-structure-v3"

# Parse a table cell's identity from the tail of a block id. Matches the last
# ``T<table>`` group followed by a header (``H<col>``) or data (``R<row>C<col>``)
# marker, so composite Mistral ids like ``P1-M0-P1-T0R9C5`` resolve to (0, 9, 5).
_TABLE_ID = re.compile(r"T(?P<table>\d+)(?:H(?P<hcol>\d+)|R(?P<row>\d+)(?:C(?P<col>\d+))?)$")


def parse_table_position(block_id: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Return ``(table_index, row_index, column_index)`` parsed from a block id.

    A header cell id (``T0H3``) has no row index; its trailing number is the
    column. Non-table ids yield ``(None, None, None)``. This is the compatibility
    path only: provider-native row/column/table metadata always wins over it.
    """
    match = _TABLE_ID.search(block_id)
    if not match:
        return None, None, None
    table = int(match.group("table"))
    if match.group("hcol") is not None:
        # Header row: row 0, column = the number after H.
        return table, 0, int(match.group("hcol"))
    row = int(match.group("row"))
    col = int(match.group("col")) if match.group("col") is not None else None
    return table, row, col


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
            table_idx, row_idx, col_idx = _resolve_table_position(block)
            blocks.append(
                m.OCRBlock(
                    block_id=block["block_id"],
                    page_number=page_number,
                    text=block.get("text", ""),
                    confidence=float(block.get("confidence") or 0.0),
                    bounding_box=box,
                    block_type=block.get("block_type", "TEXT"),
                    row_index=row_idx,
                    column_index=col_idx,
                    table_index=table_idx,
                )
            )
    return blocks


def _resolve_table_position(block: dict) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Provider-native row/column/table metadata wins; parse the id as fallback."""
    parsed_table, parsed_row, parsed_col = parse_table_position(block.get("block_id", ""))
    table_idx = block.get("table_index")
    row_idx = block.get("row_index")
    col_idx = block.get("column_index")
    return (
        table_idx if table_idx is not None else parsed_table,
        row_idx if row_idx is not None else parsed_row,
        col_idx if col_idx is not None else parsed_col,
    )


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


# --- Mistral Document AI OCR adapter -----------------------------------------
#
# A hosted alternative to the local model: it avoids downloading/warming weights
# but sends the (rendered) invoice page to Mistral. Provider-specific shape
# still stops here — analyze() returns the same provider-neutral OCRDocument.
# Mistral OCR returns Markdown per page; ``markdown_to_blocks`` converts that to
# the neutral block schema (header key:value lines + Markdown-table cells).

MISTRAL_ENGINE_NAME = "mistral-ocr"
MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
DEFAULT_MISTRAL_OCR_MODEL = "mistral-ocr-latest"


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    s = line.strip().strip("|")
    cells = [c.strip() for c in s.split("|")]
    return bool(cells) and all(set(c) <= set("-: ") and "-" in c for c in cells if c != "")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_blocks(markdown: str, page_number: int) -> list[dict]:
    """Convert one page of Mistral OCR Markdown into neutral block dicts.

    Non-table lines become TEXT/KEY_VALUE blocks; a Markdown table becomes
    TABLE_CELL blocks with row/column indices (header row = row 0, data rows
    from row 1). Bounding boxes are not available from Markdown, so blocks carry
    no ``poly`` (a full-page box is used) but always retain a block id.
    """
    blocks: list[dict] = []
    counter = 0
    lines = markdown.splitlines()
    i = 0
    table_index = 0
    while i < len(lines):
        line = lines[i]
        if _is_table_row(line) and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            # Header row.
            header = _split_row(line)
            for col, cell in enumerate(header):
                counter += 1
                blocks.append(_md_block(f"P{page_number}-T{table_index}H{col}", cell, page_number,
                                        block_type="TABLE_CELL", row=0, col=col))
            i += 2  # skip header + separator
            data_row = 1
            while i < len(lines) and _is_table_row(lines[i]):
                for col, cell in enumerate(_split_row(lines[i])):
                    counter += 1
                    blocks.append(_md_block(f"P{page_number}-T{table_index}R{data_row}C{col}", cell,
                                            page_number, block_type="TABLE_CELL", row=data_row, col=col))
                data_row += 1
                i += 1
            table_index += 1
            continue

        text = line.strip()
        if text and not _is_table_separator(line):
            counter += 1
            btype = "KEY_VALUE" if ":" in text or "：" in text else "TEXT"
            blocks.append(_md_block(f"P{page_number}-B{counter:04d}", text, page_number, block_type=btype))
        i += 1
    return blocks


def _md_block(block_id, text, page_number, *, block_type, row=None, col=None) -> dict:
    return {
        "block_id": block_id,
        "text": text,
        # Markdown carries no per-line confidence; None -> fail-closed later.
        "confidence": None,
        "poly": None,
        "block_type": block_type,
        "row_index": row,
        "column_index": col,
    }


def _block_bbox(block: dict) -> Optional[list[list[float]]]:
    """Poly from a Mistral block: flat top_left_*/bottom_right_* or a nested bbox."""
    x0 = block.get("top_left_x")
    y0 = block.get("top_left_y")
    x1 = block.get("bottom_right_x")
    y1 = block.get("bottom_right_y")
    if None in (x0, y0, x1, y1):
        bbox = block.get("bbox")
        if isinstance(bbox, dict):
            x0 = bbox.get("top_left_x", bbox.get("x0"))
            y0 = bbox.get("top_left_y", bbox.get("y0"))
            x1 = bbox.get("bottom_right_x", bbox.get("x1"))
            y1 = bbox.get("bottom_right_y", bbox.get("y1"))
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            x0, y0, x1, y1 = bbox[:4]
    if None in (x0, y0, x1, y1):
        return None
    return [[float(x0), float(y0)], [float(x1), float(y0)], [float(x1), float(y1)], [float(x0), float(y1)]]


def _block_confidence(block: dict) -> Optional[float]:
    """Block-level confidence from Mistral's confidence_scores, or a flat field."""
    scores = block.get("confidence_scores")
    if isinstance(scores, dict):
        val = scores.get("average_content_confidence_score")
        if val is not None:
            return float(val)
    conf = block.get("confidence")
    return float(conf) if conf is not None else None


def _block_content(block: dict) -> str:
    return block.get("content") or block.get("markdown") or block.get("text") or ""


def _page_dimensions(result) -> Optional[tuple[int, int]]:
    """(width, height) from a Mistral page-result dict, if present."""
    if isinstance(result, dict):
        dims = result.get("dimensions")
        if isinstance(dims, dict) and dims.get("width") and dims.get("height"):
            return int(dims["width"]), int(dims["height"])
    return None


def _looks_like_markdown_table(content: str) -> bool:
    lines = content.splitlines()
    return any(_is_table_row(ln) for ln in lines) and any(_is_table_separator(ln) for ln in lines)


def blocks_from_mistral_page(page_result: dict, page_number: int) -> list[dict]:
    """Convert a Mistral page ``blocks`` array into neutral block dicts.

    Reads the real block schema (flat top_left_*/bottom_right_* pixel coords,
    ``content`` text, ``confidence_scores.average_content_confidence_score``,
    ``type``). A block whose content is a Markdown table is expanded into
    TABLE_CELL blocks (inheriting the table's box/confidence).
    """
    out: list[dict] = []
    counter = 0
    table_index = 0
    for block in page_result.get("blocks", []):
        content = _block_content(block)
        conf = _block_confidence(block)
        poly = _block_bbox(block)
        label = str(block.get("type") or block.get("label") or "").lower()

        if _looks_like_markdown_table(content) or "table" in label:
            for cell in markdown_to_blocks(content, page_number):
                cell["poly"] = poly
                cell["confidence"] = conf
                cell["block_id"] = f"P{page_number}-M{table_index}-{cell['block_id']}"
                # The provider-native table index is the outer M counter; the
                # inner markdown table index is always 0 per expanded block.
                cell["table_index"] = table_index
                out.append(cell)
            table_index += 1
            continue

        text = content.strip()
        if not text:
            continue
        counter += 1
        btype = "KEY_VALUE" if (":" in text or "：" in text) else "TEXT"
        out.append(
            {
                "block_id": f"P{page_number}-BLK{counter:04d}",
                "text": text,
                "confidence": conf,
                "poly": poly,
                "block_type": btype,
                "row_index": None,
                "column_index": None,
            }
        )
    return out


def _map_mistral_response(raw_pages: list[dict], pages: list[m.DocumentPage]) -> list[m.OCRBlock]:
    dims = {p.page_number: (p.width, p.height) for p in pages}
    blocks: list[m.OCRBlock] = []
    for page in raw_pages:
        page_number = page.get("page_number", 1)
        # Block coordinates are in Mistral's reported page space; prefer it over
        # our rendered page size (they differ, e.g. PDF rendered at 300 DPI).
        width, height = page.get("dimensions") or dims.get(page_number, (1, 1))
        for block in page.get("blocks", []):
            poly = block.get("poly")
            box = _normalized_box(poly, width, height) if poly else m.BoundingBox(0.0, 0.0, 1.0, 1.0)
            conf = block.get("confidence")
            table_idx, row_idx, col_idx = _resolve_table_position(block)
            blocks.append(
                m.OCRBlock(
                    block_id=block["block_id"],
                    page_number=page_number,
                    text=block.get("text", ""),
                    # No confidence from the provider -> 0.0 so validation marks
                    # the field NEEDS_CONFIRMATION (a hosted value is never
                    # auto-trusted). OCR 4+ supplies real block confidence.
                    confidence=0.0 if conf is None else float(conf),
                    bounding_box=box,
                    block_type=block.get("block_type", "TEXT"),
                    row_index=row_idx,
                    column_index=col_idx,
                    table_index=table_idx,
                )
            )
    return blocks


class MistralOCREngine:
    """Mistral Document AI OCR adapter (hosted; no local model download).

    Uses the OCR-4+ ``include_blocks`` + block-level confidence when available so
    fields carry real bounding boxes and confidence. Falls back to parsing the
    per-page Markdown when a response has no ``blocks`` array.

    ``transcribe`` (callable: DocumentPage -> Markdown str OR a page-result dict)
    can be injected for deterministic tests; by default each rendered page image
    is sent to the Mistral OCR endpoint as a base64 data URL.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MISTRAL_OCR_MODEL,
        timeout: float = 60.0,
        transcribe=None,
        urlopen=None,
    ):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._transcribe = transcribe
        self._urlopen = urlopen

    def analyze(self, pages: list[m.DocumentPage]) -> m.OCRDocument:
        if not pages:
            raise ValueError("analyze requires at least one page")
        started = time.perf_counter()
        raw_pages = []
        for page in pages:
            result = (self._transcribe or self._call_api)(page)
            raw_pages.append(
                {
                    "page_number": page.page_number,
                    "blocks": self._to_blocks(result, page.page_number),
                    "dimensions": _page_dimensions(result),
                }
            )
        blocks = _map_mistral_response(raw_pages, pages)
        return m.OCRDocument(
            document_id=pages[0].document_id,
            pages=pages,
            blocks=blocks,
            full_text="\n".join(b.text for b in blocks),
            engine=MISTRAL_ENGINE_NAME,
            engine_version=self._model,
            processing_ms=int((time.perf_counter() - started) * 1000),
            warnings=[],
        )

    @staticmethod
    def _to_blocks(result, page_number: int) -> list[dict]:
        # str -> Markdown path; dict with blocks -> block path; else its markdown.
        if isinstance(result, str):
            return markdown_to_blocks(result, page_number)
        if isinstance(result, dict) and result.get("blocks"):
            return blocks_from_mistral_page(result, page_number)
        markdown = result.get("markdown", "") if isinstance(result, dict) else ""
        return markdown_to_blocks(markdown, page_number)

    def _call_api(self, page: m.DocumentPage) -> dict:
        import base64
        import json as _json
        import urllib.request

        if not self._api_key:
            raise ValueError("MistralOCREngine requires an API key for live calls")

        b64 = base64.b64encode(page.image_bytes).decode("ascii")
        payload = {
            "model": self._model,
            "document": {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
            # OCR 4+: paragraph-level boxes + structural labels + block confidence.
            "include_blocks": True,
            "confidence_scores_granularity": "block",
        }
        request = urllib.request.Request(
            MISTRAL_OCR_URL,
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": "InvoiceReferee/0.1",
            },
            method="POST",
        )
        opener = self._urlopen or urllib.request.urlopen
        with opener(request, timeout=self._timeout) as resp:
            data = _json.loads(resp.read())
        result_pages = data.get("pages") or []
        return result_pages[0] if result_pages else {}

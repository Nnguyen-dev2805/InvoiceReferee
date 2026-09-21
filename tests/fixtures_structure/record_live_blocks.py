"""Opt-in recorder: run the configured OCR engine on one real image and save the
provider-neutral block set as a fixture.

This is a *diagnostic* tool, not part of the test suite. It exists so a recorded
fixture can be reproduced from the real image it was captured from, instead of
being hand-transcribed (a hand-transcribed date was once wrong by one day — see
the Task 10 ledger entry for ``a_jpg_blocks.json``).

What it writes: only ``OCRDocument`` blocks — block id, text, confidence, page,
bounding box, block type, table/row/column indices. It never writes the image
bytes, the raw provider response, or any API key.

Usage (requires ``MISTRAL_API_KEY`` / ``OCR_ENGINE`` in ``.env``)::

    python -m tests.fixtures_structure.record_live_blocks \\
        --file data/image/sen_non_bo.jpg --document-id B-JPG \\
        --out tests/fixtures_structure/b_jpg_blocks.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_MIME_BY_SUFFIX = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def record(image_path: Path, document_id: str) -> dict:
    """Return the serialized ``OCRDocument`` for one image file."""
    from invoice_referee.ingestion.document_router import render_document
    from invoice_referee.ingestion.file_validation import validate_upload
    from invoice_referee.ingestion.image_preprocessing import preprocess_pages
    from invoice_referee.ingestion.ocr_config import engine_from_env

    mime = _MIME_BY_SUFFIX.get(image_path.suffix.lower())
    if mime is None:
        raise SystemExit(f"unsupported image suffix: {image_path.suffix}")

    document = validate_upload(image_path.name, mime, image_path.read_bytes())
    pages = preprocess_pages(render_document(document))
    ocr_document = engine_from_env().analyze(pages)
    page = pages[0]

    out_pages = []
    for source_page in pages:
        out_pages.append(
            {
                "page_number": source_page.page_number,
                "dimensions": {
                    "width": source_page.width,
                    "height": source_page.height,
                    "dpi": source_page.dpi,
                },
                "blocks": [],
            }
        )
    by_page = {p["page_number"]: p for p in out_pages}

    for block in ocr_document.blocks:
        target = by_page.get(block.page_number) or out_pages[0]
        width = target["dimensions"]["width"]
        height = target["dimensions"]["height"]
        box = block.bounding_box
        target["blocks"].append(
            {
                "block_id": block.block_id,
                "page_number": block.page_number,
                "text": block.text,
                "confidence": block.confidence,
                "block_type": block.block_type,
                "poly": [
                    [round(box.x1 * width), round(box.y1 * height)],
                    [round(box.x2 * width), round(box.y1 * height)],
                    [round(box.x2 * width), round(box.y2 * height)],
                    [round(box.x1 * width), round(box.y2 * height)],
                ],
                "row_index": block.row_index,
                "column_index": block.column_index,
                "table_index": block.table_index,
            }
        )

    return {
        "document_id": document_id,
        "engine": ocr_document.engine,
        "engine_version": ocr_document.engine_version,
        "source_note": f"recorded from {image_path.name}; image bytes and raw response are NOT stored",
        "pages": out_pages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    payload = record(args.file, args.document_id)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    n_blocks = sum(len(p["blocks"]) for p in payload["pages"])
    print(f"wrote {args.out} ({n_blocks} blocks)", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - diagnostic entry point
    raise SystemExit(main())

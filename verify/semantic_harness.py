"""Opt-in live diagnostic for the LLM-first semantic extractor.

Runs a **recorded** block set through the real configured LLM and reports what
grounded. It is a diagnostic, not a scored harness: the recorded fixtures are
compared against a live model, so the numbers are a smoke signal about the
provider and the prompt, not an accuracy claim about the extractor.

Opt-in only (``--live``), and it never writes the raw model response or any image
bytes anywhere — only the grounded field names, values, and rejection reasons are
printed. Without ``--live`` it exits 0 having done nothing, so it is safe to call
from a script.

Usage::

    python -m verify.semantic_harness --live                     # both fixtures
    python -m verify.semantic_harness --live --fixture b_jpg_blocks.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from invoice_referee.domain import models as m

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures_structure"

DEFAULT_FIXTURES = ("a_jpg_blocks.json", "b_jpg_blocks.json")


def _load_document(filename: str) -> m.OCRDocument:
    raw = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    blocks: list[m.OCRBlock] = []
    for page in raw.get("pages", []):
        width = page.get("dimensions", {}).get("width", 1) or 1
        height = page.get("dimensions", {}).get("height", 1) or 1
        for entry in page.get("blocks", []):
            poly = entry.get("poly")
            if poly:
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                box = m.BoundingBox(
                    min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height
                )
            else:
                box = m.BoundingBox(0.0, 0.0, 1.0, 1.0)
            blocks.append(
                m.OCRBlock(
                    block_id=entry["block_id"],
                    page_number=entry.get("page_number", page.get("page_number", 1)),
                    text=entry.get("text", ""),
                    confidence=float(entry.get("confidence", 0.0)),
                    bounding_box=box,
                    block_type=entry.get("block_type", "TEXT"),
                    row_index=entry.get("row_index"),
                    column_index=entry.get("column_index"),
                    table_index=entry.get("table_index"),
                )
            )
    return m.OCRDocument(
        document_id=raw.get("document_id", "LIVE"),
        pages=[],
        blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine=raw.get("engine", "recorded"),
        engine_version=raw.get("engine_version", "recorded"),
        processing_ms=0,
    )


def run_one(filename: str) -> int:
    """Run one recorded fixture through the live semantic extractor."""
    from invoice_referee.agent.config import client_from_env
    from invoice_referee.ingestion.semantic_extraction import extract_semantics

    client = client_from_env()
    if client is None:
        print(f"{filename}: no LLM client configured (LLM_API_KEY missing)", file=sys.stderr)
        return 0

    document = _load_document(filename)
    result = extract_semantics(document, client)

    print(f"=== {filename} ({len(document.blocks)} blocks) ===")
    print(f"document_type : {result.document_type.value}")
    print(f"fields        : {len(result.fields)}")
    for name, candidate in sorted(result.fields.items()):
        print(
            f"  {name:18} raw={candidate.raw_text!r} "
            f"normalized={candidate.normalized_value!r} "
            f"blocks={candidate.evidence_block_ids}"
        )
    print(f"line_items    : {len(result.line_items)}")
    for index, line in enumerate(result.line_items):
        cells = ", ".join(
            f"{name}={cand.normalized_value!r}" for name, cand in sorted(line.items())
        )
        print(f"  [{index}] {cells}")
    if result.warnings:
        print(f"rejected      : {len(result.warnings)}")
        for warning in result.warnings:
            print(f"  - {warning}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="actually call the configured LLM (opt-in; no response is stored)",
    )
    parser.add_argument("--fixture", action="append", default=None)
    args = parser.parse_args(argv)

    if not args.live:
        print("diagnostic skipped: pass --live to call the configured LLM", file=sys.stderr)
        return 0

    for filename in args.fixture or list(DEFAULT_FIXTURES):
        code = run_one(filename)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":  # pragma: no cover - diagnostic entry point
    raise SystemExit(main())

"""CLI for converting Mistral OCR metadata to block-word hierarchy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from invoice_referee.extraction import restructure_mistral_ocr


def _default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.hierarchical.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nhóm word confidence của Mistral OCR vào từng block.",
    )
    parser.add_argument("input", type=Path, help="File JSON đầu vào")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="File JSON đầu ra; mặc định thêm hậu tố .hierarchical.json",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = (args.output or _default_output_path(input_path)).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = restructure_mistral_ocr(payload, source_file=input_path.name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    page_count = len(result["pages"])
    block_count = sum(len(page["blocks"]) for page in result["pages"])
    warning_count = sum(len(page["warnings"]) for page in result["pages"])
    print(f"Output: {output_path}")
    print(f"Pages: {page_count} | Blocks: {block_count} | Warnings: {warning_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

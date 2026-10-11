"""Render and validate generated UC-03 DOCX/PDF fixtures."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import aspose.words as aw
import pymupdf
from PIL import Image, ImageDraw, ImageFont

VISIBLE_FIXTURE_MARKERS = (
    "DỮ LIỆU KIỂM THỬ",
    "KHÔNG CÓ GIÁ TRỊ PHÁP LÝ",
    "MÔ PHỎNG",
    "GIẢ LẬP",
    "DEMO",
    "PHỤC VỤ KIỂM THỬ",
)


def contact_sheets(images: list[Path], output: Path, prefix: str) -> list[Path]:
    sheets: list[Path] = []
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 18)
    for batch_index in range(0, len(images), 10):
        batch = images[batch_index : batch_index + 10]
        canvas = Image.new("RGB", (900, 3000), "white")
        draw = ImageDraw.Draw(canvas)
        for index, path in enumerate(batch):
            image = Image.open(path).convert("RGB")
            image.thumbnail((410, 520))
            column = index % 2
            row = index // 2
            x = 20 + column * 440
            y = 42 + row * 585
            draw.text((x, y - 28), path.stem, fill="black", font=font)
            canvas.paste(image, (x, y))
        sheet = output / f"{prefix}-{batch_index // 10 + 1}.png"
        canvas.save(sheet)
        sheets.append(sheet)
    return sheets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/testcase_uc3"))
    parser.add_argument("--output", type=Path, default=Path("data/.qa/uc3_testcases"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    docx_output = output / "docx"
    pdf_output = output / "pdf"
    docx_output.mkdir(parents=True)
    pdf_output.mkdir(parents=True)

    errors: list[str] = []
    docx_images: list[Path] = []
    pdf_images: list[Path] = []
    docx_files = sorted(root.rglob("*.docx"))
    pdf_files = sorted(root.rglob("*.pdf"))
    expected_files = sorted(root.rglob("expected.json"))
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        manifest = []
        errors.append(f"Invalid manifest.json: {exc}")
    if len(manifest) != 25:
        errors.append(f"Expected 25 manifest cases, found {len(manifest)}")
    if len(expected_files) != len(manifest):
        errors.append(
            f"Expected {len(manifest)} expected.json files, found {len(expected_files)}"
        )

    expected_document_count = 0
    for path in expected_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("synthetic_test_data") is not True:
                errors.append(f"Synthetic marker missing: {path}")
            submission = payload.get("submission", {})
            document_names = [
                submission.get("request_document"),
                *submission.get("evidence_documents", []),
            ]
            document_names = [name for name in document_names if name]
            expected_document_count += len(document_names)
            for name in document_names:
                pdf_path = path.parent / name
                docx_path = pdf_path.with_suffix(".docx")
                if not pdf_path.exists():
                    errors.append(f"Referenced PDF missing: {pdf_path}")
                if not docx_path.exists():
                    errors.append(f"Editable DOCX missing: {docx_path}")
            if payload.get("schema_version") == "2.0":
                report_lines = payload.get("accounting_facts", {}).get("report_lines", [])
                expectations = payload.get("line_support_expectations", [])
                line_ids = [line.get("line_id") for line in report_lines]
                expectation_ids = [item.get("report_line_id") for item in expectations]
                if len(line_ids) != len(set(line_ids)):
                    errors.append(f"Duplicate report line id: {path}")
                if sorted(line_ids) != sorted(expectation_ids):
                    errors.append(f"Line support coverage mismatch: {path}")
                submitted_evidence = set(submission.get("evidence_documents", []))
                for item in expectations:
                    for filename in item.get("document_files", []):
                        if filename not in submitted_evidence:
                            errors.append(
                                f"Line support references unsubmitted file {filename}: {path}"
                            )
        except Exception as exc:
            errors.append(f"Invalid expected.json {path}: {exc}")

    if len(pdf_files) != expected_document_count:
        errors.append(
            f"Expected {expected_document_count} PDF files, found {len(pdf_files)}"
        )
    if len(docx_files) != expected_document_count:
        errors.append(
            f"Expected {expected_document_count} DOCX files, found {len(docx_files)}"
        )

    for path in docx_files:
        relative = path.relative_to(root)
        stem = f"{relative.parent.name}_{path.stem}"
        try:
            document = aw.Document(str(path))
            if document.page_count != 1:
                errors.append(f"DOCX page count {document.page_count}: {relative}")
            visible_text = document.get_text().upper()
            for marker in VISIBLE_FIXTURE_MARKERS:
                if marker in visible_text:
                    errors.append(f"Visible fixture marker '{marker}' in DOCX: {relative}")
            rendered = docx_output / f"{stem}.png"
            document.save(str(rendered))
            docx_images.append(rendered)
        except Exception as exc:
            errors.append(f"Cannot render DOCX {relative}: {exc}")

    for path in pdf_files:
        relative = path.relative_to(root)
        stem = f"{relative.parent.name}_{path.stem}"
        try:
            document = pymupdf.open(path)
            if document.page_count != 1:
                errors.append(f"PDF page count {document.page_count}: {relative}")
            text = "\n".join(page.get_text() for page in document).upper()
            for marker in VISIBLE_FIXTURE_MARKERS:
                if marker in text:
                    errors.append(f"Visible fixture marker '{marker}' in PDF: {relative}")
            pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(1.0, 1.0), alpha=False)
            rendered = pdf_output / f"{stem}.png"
            pixmap.save(rendered)
            pdf_images.append(rendered)
        except Exception as exc:
            errors.append(f"Cannot inspect PDF {relative}: {exc}")

    sheets = [
        *contact_sheets(docx_images, output, "docx-sheet"),
        *contact_sheets(pdf_images, output, "pdf-sheet"),
    ]
    summary = {
        "root": str(root),
        "docx_count": len(docx_files),
        "pdf_count": len(pdf_files),
        "expected_count": len(expected_files),
        "contact_sheets": [str(path) for path in sheets],
        "errors": errors,
    }
    (output / "qa_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

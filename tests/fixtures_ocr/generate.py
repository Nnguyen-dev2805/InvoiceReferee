"""Generate the synthetic OCR evaluation set (15 documents + recorded OCR).

Writes, under this directory:
- ``generated/`` : real renderable PDF/PNG/JPEG invoice files;
- ``recorded/``  : the provider-neutral OCR response recorded per document;
- ``manifest.json`` : per-case base evidence, field-review spec, and ground truth.

Production extraction never reads ``manifest.json``. It reads the document bytes
and (in deterministic tests) the recorded OCR response. Ground-truth expected
values live only in the manifest, consumed by the evaluation harness.

Run:  python tests/fixtures_ocr/generate.py
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"
RECORDED = HERE / "recorded"

random.seed(20260920)


# --- low-level document writers ----------------------------------------------


def _write_pdf(path: Path, lines: list[str], pages: int = 1) -> None:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line)
            y += 24
    path.write_bytes(doc.tobytes())
    doc.close()


def _write_image(path: Path, lines: list[str], fmt: str, *, rotate=0, low_contrast=False) -> None:
    from PIL import Image, ImageDraw

    bg = (235, 235, 235) if low_contrast else (255, 255, 255)
    fg = (150, 150, 150) if low_contrast else (0, 0, 0)
    img = Image.new("RGB", (1000, 700), bg)
    draw = ImageDraw.Draw(img)
    y = 60
    for line in lines:
        draw.text((60, y), line, fill=fg)
        y += 40
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=bg)
    img.save(path, format=fmt)


# --- recorded OCR response helpers -------------------------------------------


def _text_block(bid, text, y1):
    return {
        "block_id": bid,
        "text": text,
        "confidence": 0.97,
        "poly": [[80, y1], [900, y1], [900, y1 + 30], [80, y1 + 30]],
        "block_type": "KEY_VALUE",
    }


def _cell(bid, text, row, col, conf=0.97):
    x = 80 + col * 220
    y = 400 + row * 40
    return {
        "block_id": bid,
        "text": text,
        "confidence": conf,
        "poly": [[x, y], [x + 200, y], [x + 200, y + 30], [x + 80, y + 30]],
        "block_type": "TABLE_CELL",
        "row_index": row,
        "column_index": col,
    }


def _header_blocks(*, number="0000123", series="2C23TTU", tax="0101234567",
                   po="PO-001", date="2026-09-13", total="30.000.000 VND", total_conf=0.97):
    blocks = [
        _text_block("BLK-SER", f"Ký hiệu: {series}", 100),
        _text_block("BLK-NUM", f"Số hóa đơn: {number}", 140),
        _text_block("BLK-TAX", f"Mã số thuế: {tax}", 180),
        _text_block("BLK-PO", f"Số PO: {po}", 220),
        _text_block("BLK-DATE", f"Ngày hóa đơn: {date}", 260),
    ]
    tot = _text_block("BLK-TOT", f"Tổng cộng: {total}", 300)
    tot["confidence"] = total_conf
    blocks.append(tot)
    return blocks


def _table(rows):
    """rows: list of (desc, qty, unit, total). Returns header + data cells."""
    cells = [
        _cell("H0", "Mô tả", 0, 0),
        _cell("H1", "Số lượng", 0, 1),
        _cell("H2", "Đơn giá", 0, 2),
        _cell("H3", "Thành tiền", 0, 3),
    ]
    for r, (desc, qty, unit, total) in enumerate(rows, start=1):
        cells.append(_cell(f"R{r}C0", desc, r, 0))
        cells.append(_cell(f"R{r}C1", str(qty), r, 1))
        cells.append(_cell(f"R{r}C2", unit, r, 2))
        cells.append(_cell(f"R{r}C3", total, r, 3))
    return cells


def _recorded(header_blocks, table_cells):
    return {"pages": [{"page_number": 1, "blocks": header_blocks + table_cells}]}


# --- base evidence template --------------------------------------------------


def _base_evidence(tx_id, *, approved_total=30_000_000, received_qty=10, po_id="PO-001",
                   items=None, invoice_id_key="INV-OCR"):
    items = items or [
        {"item_id": "ITEM-001", "description": "Dell Monitor", "ordered_quantity": 10,
         "unit_price": 3_000_000, "line_total": 30_000_000}
    ]
    return {
        "transaction_id": tx_id,
        "transaction_type": "PO_GOODS_PURCHASE",
        "purchase_order": {
            "po_id": po_id,
            "vendor_id": "V-ABC",
            "vendor_tax_code": "0101234567",
            "approved_total": approved_total,
            "status": "APPROVED",
            "items": items,
        },
        "goods_receipts": [
            {"receipt_id": "GR-001", "po_id": po_id, "received_date": "2026-09-12",
             "status": "RECEIVED", "items": [{"item_id": "ITEM-001", "received_quantity": received_qty}]}
        ],
        "payment_history": [{"invoice_id": invoice_id_key, "status": "UNPAID", "paid_amount": 0}],
    }


# --- case catalogue ----------------------------------------------------------


def _cases() -> dict:
    cases: dict = {}

    routine_table = [("Dell Monitor", 10, "3.000.000", "30.000.000")]

    # OCR01-05 text PDFs (routine variants).
    for n in range(1, 6):
        cid = f"OCR{n:02d}"
        cases[cid] = {
            "kind": "TEXT_PDF",
            "ext": "pdf",
            "mime_type": "application/pdf",
            "recorded": _recorded(_header_blocks(), _table(routine_table)),
            "base_evidence": _base_evidence(f"OCR-TX-{n:02d}", invoice_id_key=f"INV-{cid}"),
            "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {}},
            "expected": {
                "invoice_number": "0000123",
                "invoice_series": "2C23TTU",
                "vendor_tax_code": "0101234567",
                "po_id": "PO-001",
                "invoice_date": "2026-09-13",
                "total_amount": 30_000_000,
            },
            "expected_action": "AUTO_PROCESS",
            "invoice_id_key": f"INV-{cid}",
        }

    # OCR06 scanned PDF with unreadable amount -> mark unknown -> REQUEST_INFO.
    cases["OCR06"] = {
        "kind": "SCANNED_PDF",
        "ext": "pdf",
        "mime_type": "application/pdf",
        "recorded": _recorded(
            _header_blocks(total="45 trieu hoac 48 trieu", total_conf=0.55),
            _table(routine_table),
        ),
        "base_evidence": _base_evidence("OCR-TX-06", invoice_id_key="INV-OCR06"),
        "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {"total_amount": {"action": "MARK_UNKNOWN", "reason": "unreadable amount"}}},
        "expected": {"total_amount": None},
        "expected_action": "REQUEST_INFO",
        "invoice_id_key": "INV-OCR06",
    }

    # OCR07 scanned PDF, OCR misreads PO id, reviewer corrects it -> AUTO_PROCESS.
    cases["OCR07"] = {
        "kind": "SCANNED_PDF",
        "ext": "pdf",
        "mime_type": "application/pdf",
        "recorded": _recorded(_header_blocks(po="PO-0O1"), _table(routine_table)),
        "base_evidence": _base_evidence("OCR-TX-07", invoice_id_key="INV-OCR07"),
        "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {"po_id": {"action": "CORRECT", "value": "PO-001", "reason": "OCR misread O for 0"}}},
        "expected": {"po_id": "PO-001"},
        "expected_action": "AUTO_PROCESS",
        "invoice_id_key": "INV-OCR07",
    }

    # OCR08 scanned PDF, confirmed quantity exceeds receipt -> REQUEST_INFO.
    cases["OCR08"] = {
        "kind": "SCANNED_PDF",
        "ext": "pdf",
        "mime_type": "application/pdf",
        "recorded": _recorded(
            _header_blocks(total="36.000.000 VND"),
            _table([("Dell Monitor", 12, "3.000.000", "36.000.000")]),
        ),
        "base_evidence": _base_evidence("OCR-TX-08", approved_total=36_000_000, received_qty=10, invoice_id_key="INV-OCR08"),
        "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {}},
        "expected": {"total_amount": 36_000_000},
        "expected_action": "REQUEST_INFO",
        "invoice_id_key": "INV-OCR08",
    }

    # OCR09 scanned PDF, beyond-authority total -> ESCALATE.
    cases["OCR09"] = {
        "kind": "SCANNED_PDF",
        "ext": "pdf",
        "mime_type": "application/pdf",
        "recorded": _recorded(
            _header_blocks(total="120.000.000 VND"),
            _table([("Server Rack", 10, "12.000.000", "120.000.000")]),
        ),
        "base_evidence": _base_evidence(
            "OCR-TX-09", approved_total=120_000_000, received_qty=10, invoice_id_key="INV-OCR09",
            items=[{"item_id": "ITEM-001", "description": "Server Rack", "ordered_quantity": 10,
                    "unit_price": 12_000_000, "line_total": 120_000_000}],
        ),
        "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {}},
        "expected": {"total_amount": 120_000_000},
        "expected_action": "ESCALATE",
        "invoice_id_key": "INV-OCR09",
    }

    # OCR10 scanned PDF referencing the wrong PO -> REQUEST_INFO (evidence issue).
    cases["OCR10"] = {
        "kind": "SCANNED_PDF",
        "ext": "pdf",
        "mime_type": "application/pdf",
        "recorded": _recorded(_header_blocks(po="PO-999"), _table(routine_table)),
        "base_evidence": _base_evidence("OCR-TX-10", invoice_id_key="INV-OCR10"),
        "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {}},
        "expected": {"po_id": "PO-999"},
        "expected_action": "REQUEST_INFO",
        "invoice_id_key": "INV-OCR10",
    }

    # OCR11-15 images (PNG/JPEG), routine; include rotated, low-contrast, multi-row.
    image_specs = [
        ("OCR11", "PNG", {}),
        ("OCR12", "JPEG", {"rotate": 3}),
        ("OCR13", "PNG", {"low_contrast": True}),
        ("OCR14", "JPEG", {}),
        ("OCR15", "PNG", {}),
    ]
    for cid, fmt, opts in image_specs:
        table = routine_table
        base = _base_evidence(f"OCR-TX-{cid[-2:]}", invoice_id_key=f"INV-{cid}")
        if cid == "OCR15":
            # multi-row table.
            table = [("Dell Monitor", 6, "3.000.000", "18.000.000"),
                     ("USB Cable", 20, "600.000", "12.000.000")]
            base = _base_evidence(
                f"OCR-TX-{cid[-2:]}", approved_total=30_000_000, received_qty=6, invoice_id_key=f"INV-{cid}",
                items=[
                    {"item_id": "ITEM-001", "description": "Dell Monitor", "ordered_quantity": 6,
                     "unit_price": 3_000_000, "line_total": 18_000_000},
                    {"item_id": "ITEM-002", "description": "USB Cable", "ordered_quantity": 20,
                     "unit_price": 600_000, "line_total": 12_000_000},
                ],
            )
            base["goods_receipts"][0]["items"] = [
                {"item_id": "ITEM-001", "received_quantity": 6},
                {"item_id": "ITEM-002", "received_quantity": 20},
            ]
        total = "30.000.000 VND" if cid != "OCR15" else "30.000.000 VND"
        cases[cid] = {
            "kind": "IMAGE",
            "ext": "png" if fmt == "PNG" else "jpg",
            "mime_type": "image/png" if fmt == "PNG" else "image/jpeg",
            "fmt": fmt,
            "opts": opts,
            "recorded": _recorded(_header_blocks(total=total), _table(table)),
            "base_evidence": base,
            "field_reviews": {"mode": "CONFIRM_ALL", "overrides": {}},
            "expected": {"invoice_number": "0000123", "total_amount": 30_000_000},
            "expected_action": "AUTO_PROCESS",
            "invoice_id_key": f"INV-{cid}",
        }

    return cases


def main() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    RECORDED.mkdir(parents=True, exist_ok=True)

    cases = _cases()
    manifest: dict = {}

    for cid, case in cases.items():
        filename = f"{cid}.{case['ext']}"
        path = GENERATED / filename
        header_lines = [b["text"] for b in case["recorded"]["pages"][0]["blocks"] if b["block_type"] == "KEY_VALUE"]

        if case["mime_type"] == "application/pdf":
            pages = 3 if case["kind"] == "SCANNED_PDF" and cid == "OCR06" else 1
            _write_pdf(path, ["HOA DON GIA TRI GIA TANG"] + header_lines, pages=pages)
        else:
            _write_image(path, ["HOA DON"] + header_lines, case["fmt"], **case["opts"])

        recorded_rel = f"recorded/{cid}.json"
        (RECORDED / f"{cid}.json").write_text(
            json.dumps(case["recorded"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

        manifest[cid] = {
            "file": filename,
            "kind": case["kind"],
            "mime_type": case["mime_type"],
            "recorded_ocr": recorded_rel,
            "base_evidence": case["base_evidence"],
            "field_reviews": case["field_reviews"],
            "expected": case["expected"],
            "expected_action": case["expected_action"],
            "invoice_id_key": case["invoice_id_key"],
        }

    (HERE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(manifest)} OCR evaluation documents into {GENERATED}")


if __name__ == "__main__":
    main()

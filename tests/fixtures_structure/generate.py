"""Generate the structure-generalization evaluation set.

Deterministically produces 20 provider-neutral recorded-block fixtures (two per
layout family) plus ``manifest.json``. Run from the repo root:

    .venv/bin/python tests/fixtures_structure/generate.py

The generator writes provider-neutral OCRDocument JSON (block_id, text,
confidence, poly, block_type, table/row/column indices) and a manifest with
expected row roles, fields, line-item counts, and selected evidence. Production
code never imports the manifest.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Money multiplier applied to the second case of each layout family so the two
# variants are genuinely different documents rather than byte-identical clones.
_VARIANT_FACTOR = 2

HERE = Path(__file__).resolve().parent
RECORDED = HERE / "recorded"
MANIFEST_PATH = HERE / "manifest.json"

# Page reference size used for poly coordinates (px). Deterministic per run.
PAGE_W = 676
PAGE_H = 907


@dataclass
class Block:
    block_id: str
    text: str
    block_type: str = "TEXT"
    row: Optional[int] = None
    col: Optional[int] = None
    table: Optional[int] = None
    page: int = 1
    conf: float = 0.97
    x: float = 0.5
    y: float = 0.5
    w: float = 0.2
    h: float = 0.03


def poly(x: float, y: float, w: float, h: float):
    """Serialize normalized layout coordinates in the recorded pixel space."""
    return [
        [px * PAGE_W, py * PAGE_H]
        for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    ]


def _block_dict(b: Block) -> dict:
    d: dict[str, Any] = {
        "block_type": b.block_type,
        "block_id": b.block_id,
        "text": b.text,
        "confidence": b.conf,
        "poly": poly(b.x, b.y, b.w, b.h),
    }
    if b.row is not None:
        d["row_index"] = b.row
    if b.col is not None:
        d["column_index"] = b.col
    if b.table is not None:
        d["table_index"] = b.table
    return d


def doc_to_json(document_id: str, pages: list[list[Block]]) -> dict:
    return {
        "document_id": document_id,
        "engine": "recorded",
        "engine_version": "structure-v1",
        "pages": [
            {
                "page_number": i + 1,
                "dimensions": {"width": PAGE_W, "height": PAGE_H, "dpi": 200},
                "blocks": [_block_dict(b) for b in page_blocks],
            }
            for i, page_blocks in enumerate(pages)
        ],
    }


def kv(block_id: str, text: str, *, page: int = 1, y: float = 0.5, conf: float = 0.97, x: float = 0.05) -> Block:
    """A label:value header block."""
    return Block(block_id, text, block_type="KEY_VALUE", page=page, conf=conf, x=x, y=y, w=0.5, h=0.03)


_kv = kv


def cell(block_id: str, text: str, *, row: int, col: int, table: int = 0, page: int = 1,
         conf: float = 0.97) -> Block:
    x = 0.05 + col * 0.12
    y = 0.30 + row * 0.035
    return Block(block_id, text, block_type="TABLE_CELL", row=row, col=col, table=table,
                 page=page, conf=conf, x=x, y=y, w=0.11, h=0.03)


ITEM_TABLE_HEADER = [
    ("H0", "STT"), ("H1", "Mô tả"), ("H2", "Số lượng"), ("H3", "Đơn giá"), ("H4", "Thành tiền"),
]


def item_table_headers(table: int = 0, page: int = 1) -> list[Block]:
    out = []
    for col, (bid, text) in enumerate(ITEM_TABLE_HEADER):
        out.append(cell(f"T{table}H{col}", text, row=0, col=col, table=table, page=page, conf=0.95))
    return out


def data_row(row: int, desc: str, qty: str, price: str, total: str, *,
             table: int = 0, page: int = 1, first_col: int = 0) -> list[Block]:
    """Build one item DATA row (cols 1..4 carry description/qty/price/total)."""
    values = [desc, qty, price, total]
    out = []
    for col, text in enumerate(values, start=first_col + 1):
        out.append(cell(f"T{table}R{row}C{col}", text, row=row, col=col, table=table, page=page))
    return out


def gen_table_footer_total(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Total row sits below the items (KEY_VALUE-style grand total in table)."""
    cid = f"ST{2*i+1:02d}"
    blocks = [_kv("SER", "Ký hiệu: 2C23TTU", y=0.08),
              _kv("NUM", "Số hóa đơn: 0000123", y=0.12),
              _kv("TAX", "Mã số thuế: 0110329220", y=0.16),
              _kv("DTE", "Ngày 10 tháng 07 năm 2023", y=0.20)]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Khóa học kế toán tổng hợp", "02", "3.500.000", "7.000.000", table=0)
    blocks += data_row(2, "Dịch vụ kế toán thuế quý 3", "01", "2.000.000", "2.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng tiền thanh toán", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "9.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 9000000, "invoice_date": "2023-07-10",
                   "vendor_tax_code": "0110329220"},
        "line_item_count": 2,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


def gen_total_inside_table(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Grand-total row is inside the same item table (a.jpg-derived set)."""
    cid = f"ST{2*i+2:02d}"
    blocks = [_kv("SER", "Ký hiệu: 1D24BBE", y=0.08),
              _kv("NUM", "Số hóa đơn: 0000456", y=0.12),
              _kv("TAX", "Mã số thuế: 0110329220", y=0.16),
              _kv("DTE", "Ngày 11 tháng 07 năm 2023", y=0.20)]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Hàng hóa A", "03", "1.000.000", "3.000.000", table=0)
    blocks += data_row(2, "Hàng hóa B", "02", "2.000.000", "4.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "7.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 7000000, "invoice_date": "2023-07-11"},
        "line_item_count": 2,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


def gen_subtotal_tax_total(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Subtotal, tax, shipping, discount and final total rows."""
    cid = f"ST{2*i+3:02d}"
    # DATA item occupies row 1; summary rows sit below at rows 4..8 (no overlap).
    rows = [
        (4, "Cộng tiền hàng", "8.000.000"),
        (5, "Tổng tiền thuế GTGT", "800.000"),
        (6, "Chiết khấu", "0"),
        (7, "Phí vận chuyển", "200.000"),
        (8, "Tổng cộng thanh toán", "9.000.000"),
    ]
    blocks = [_kv("SER", "Ký hiệu: 3E55CC0", y=0.08),
              _kv("NUM", "Số hóa đơn: 0000789", y=0.12)]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Sản phẩm X", "10", "800.000", "8.000.000", table=0)
    for row, label, value in rows:
        blocks.append(cell(f"T0R{row}C0", label, row=row, col=0, table=0, conf=0.90))
        blocks.append(cell(f"T0R{row}C5", value, row=row, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:4": "SUBTOTAL", "1:0:5": "TAX", "1:0:6": "DISCOUNT",
                      "1:0:7": "SHIPPING", "1:0:8": "GRAND_TOTAL"},
        "fields": {"subtotal_amount": 8000000, "tax_amount": 800000, "discount_amount": 0,
                   "shipping_amount": 200000, "total_amount": 9000000},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R8C0", "T0R8C5"]},
    }
    return cid, expected, [blocks]


def gen_label_above_value(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Separate header labels sit above their values, with a positive gap."""
    cid = f"ST{2*i+4:02d}"
    blocks = []
    for bid, label, value, y in (
        ("SER", "Ký hiệu:", "4F66DD1", 0.02),
        ("NUM", "Số hóa đơn:", "0000111", 0.09),
        ("TAX", "Mã số thuế:", "0110329220", 0.16),
        ("DTE", "Ngày hóa đơn", "10/07/2023", 0.23),
    ):
        blocks.append(Block(f"{bid}-L", label, x=0.05, y=y, w=0.5, h=0.02))
        blocks.append(Block(f"{bid}-V", value, x=0.05, y=y + 0.03, w=0.5, h=0.02))
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Vật tư Y", "05", "1.000.000", "5.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "5.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 5000000, "vendor_tax_code": "0110329220",
                   "invoice_date": "2023-07-10"},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


def gen_multiple_tables(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Two separate item tables on one page."""
    cid = f"ST{2*i+5:02d}"
    blocks = [_kv("SER", "Ký hiệu: 5G77EE2", y=0.06),
              _kv("NUM", "Số hóa đơn: 0000222", y=0.10),
              _kv("TAX", "Mã số thuế: 0110329220", y=0.14),
              _kv("DTE", "Ngày 12 tháng 07 năm 2023", y=0.18)]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Nhóm hàng 1", "02", "3.000.000", "6.000.000", table=0)
    blocks += item_table_headers(1, 1)
    blocks += data_row(1, "Nhóm hàng 2", "01", "2.000.000", "2.000.000", table=1)
    # Tổng ở footer bảng 2.
    blocks.append(cell("T1R9C0", "Tổng cộng", row=9, col=0, table=1, conf=0.88))
    blocks.append(cell("T1R9C5", "8.000.000", row=9, col=5, table=1, conf=0.95))
    expected = {
        "row_roles": {"1:1:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 8000000, "invoice_date": "2023-07-12"},
        "line_item_count": 2,
        "selected_evidence": {"total_amount": ["T1R9C0", "T1R9C5"]},
    }
    return cid, expected, [blocks]


def gen_multi_page_invoice(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Items continue across two pages."""
    cid = f"ST{2*i+6:02d}"
    page1 = [_kv("SER", "Ký hiệu: 6H88FF3", y=0.06),
             _kv("NUM", "Số hóa đơn: 0000333", y=0.10),
             _kv("TAX", "Mã số thuế: 0110329220", y=0.14),
             _kv("DTE", "Ngày 13 tháng 07 năm 2023", y=0.18)]
    page1 += item_table_headers(0, 1)
    page1 += data_row(1, "Mặt hàng P1", "05", "1.000.000", "5.000.000", table=0, page=1)
    page2 = item_table_headers(0, 2)
    page2 += data_row(1, "Mặt hàng P2", "02", "2.000.000", "4.000.000", table=0, page=2)
    page2.append(cell("P2T0R9C0", "Tổng cộng", row=9, col=0, table=0, page=2, conf=0.88))
    page2.append(cell("P2T0R9C5", "9.000.000", row=9, col=5, table=0, page=2, conf=0.95))
    expected = {
        "row_roles": {"2:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 9000000, "invoice_date": "2023-07-13"},
        "line_item_count": 2,
        "selected_evidence": {"total_amount": ["P2T0R9C0", "P2T0R9C5"]},
    }
    return cid, expected, [page1, page2]


def gen_seller_buyer_duplicate(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Seller and buyer sections share the same 'Mã số thuế' label; duplicate tax codes
    should produce a cross-field warning, not a merge."""
    cid = f"ST{2*i+7:02d}"
    blocks = [
        _kv("SELLER-NAME", "Đơn vị bán: Công ty ABC", y=0.07),
        _kv("SELLER-TAX", "Mã số thuế: 0101234567", y=0.10),
        _kv("BUYER-NAME", "Đơn vị mua: Công ty XYZ", y=0.14),
        _kv("BUYER-TAX", "Mã số thuế: 0101234567", y=0.17),
    ]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Linh kiện điện tử", "04", "1.500.000", "6.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "6.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 6000000, "vendor_tax_code": "0101234567"},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
        "warning": "seller and buyer tax code",
    }
    return cid, expected, [blocks]


def gen_different_header_signature_dates(i: int) -> tuple[str, dict, list[list[Block]]]:
    """A header invoice date differs from a signature date at the bottom."""
    cid = f"ST{2*i+8:02d}"
    blocks = [
        _kv("SER", "Ký hiệu: 7J99GG4", y=0.07),
        _kv("NUM", "Số hóa đơn: 0000444", y=0.10),
        _kv("TAX", "Mã số thuế: 0110329220", y=0.14),
        # Header date (top) should win over the signature date (bottom).
        _kv("DTE-HDR", "Ngày 10 tháng 07 năm 2023", y=0.18),
    ]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Dịch vụ bảo trì", "01", "6.000.000", "6.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "6.000.000", row=9, col=5, table=0, conf=0.95))
    blocks += [_kv("SIGN-DTE", "Ký ngày: 15/08/2023", y=0.85)]
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 6000000, "invoice_date": "2023-07-10"},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


def gen_english_labels(i: int) -> tuple[str, dict, list[list[Block]]]:
    """English alternative labels (INVOICE NO, TAX ID, TOTAL)."""
    cid = f"ST{2*i+9:02d}"
    blocks = [
        _kv("SER", "Invoice series: 8K00HH5", y=0.07),
        _kv("NUM", "Invoice number: 0000555", y=0.10),
        _kv("TAX", "Tax ID: 0110329220", y=0.14),
        _kv("DTE", "Date: 10/07/2023", y=0.18),
    ]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Office supplies", "06", "500.000", "3.000.000", table=0)
    blocks.append(cell("T0R9C0", "Total", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "3.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 3000000, "invoice_date": "2023-07-10",
                   "vendor_tax_code": "0110329220"},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


def gen_ocr_corrupted_labels(i: int) -> tuple[str, dict, list[list[Block]]]:
    """Labels are OCR-corrupted (fuzzy), so only fuzzy label matching recovers them."""
    cid = f"ST{2*i+10:02d}"
    blocks = [
        _kv("SER", "Ky hieu: 9L11II6", y=0.07, conf=0.99),
        _kv("NUM", "So hoa don: 0000666", y=0.10, conf=0.99),
        _kv("TAX", "Ma so thue: 0110329220", y=0.14, conf=0.99),
        _kv("DTE", "Ngay 14 thang 07 nam 2023", y=0.18, conf=0.99),
    ]
    blocks += item_table_headers(0, 1)
    blocks += data_row(1, "Vật tư chính xác", "02", "2.000.000", "4.000.000", table=0)
    blocks.append(cell("T0R9C0", "Tổng cộng", row=9, col=0, table=0, conf=0.88))
    blocks.append(cell("T0R9C5", "4.000.000", row=9, col=5, table=0, conf=0.95))
    expected = {
        "row_roles": {"1:0:9": "GRAND_TOTAL"},
        "fields": {"total_amount": 4000000, "invoice_date": "2023-07-14",
                   "vendor_tax_code": "0110329220"},
        "line_item_count": 1,
        "selected_evidence": {"total_amount": ["T0R9C0", "T0R9C5"]},
    }
    return cid, expected, [blocks]


_GENERATORS = [
    gen_table_footer_total,
    gen_total_inside_table,
    gen_subtotal_tax_total,
    gen_label_above_value,
    gen_multiple_tables,
    gen_multi_page_invoice,
    gen_seller_buyer_duplicate,
    gen_different_header_signature_dates,
    gen_english_labels,
    gen_ocr_corrupted_labels,
]

FAMILY_NAMES = {
    "TABLE_FOOTER_TOTAL": gen_table_footer_total,
    "TOTAL_INSIDE_TABLE": gen_total_inside_table,
    "SUBTOTAL_TAX_TOTAL": gen_subtotal_tax_total,
    "LABEL_ABOVE_VALUE": gen_label_above_value,
    "MULTIPLE_TABLES": gen_multiple_tables,
    "MULTI_PAGE_INVOICE": gen_multi_page_invoice,
    "SELLER_BUYER_DUPLICATE_LABELS": gen_seller_buyer_duplicate,
    "DIFFERENT_HEADER_SIGNATURE_DATES": gen_different_header_signature_dates,
    "ENGLISH_LABELS": gen_english_labels,
    "OCR_CORRUPTED_LABELS": gen_ocr_corrupted_labels,
}


_MONEY_TEXT = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_MONEY_FIELD_KEYS = {
    "total_amount",
    "subtotal_amount",
    "tax_amount",
    "discount_amount",
    "shipping_amount",
}


def _scale_money_text(text: str, factor: int) -> str:
    """Scale a separator-formatted money string by ``factor``, keeping the
    original separator style. Non-money text (ids, tax codes, dates) is left
    untouched, so identity values are not corrupted."""
    if not _MONEY_TEXT.match(text.strip()):
        return text
    sep = "." if "." in text else ","
    scaled = int(re.sub(r"[.,]", "", text)) * factor
    return f"{scaled:,}".replace(",", sep)


def _scale_variant(pages: list[list[Block]], expected: dict, factor: int) -> tuple[list[list[Block]], dict]:
    """Produce a genuinely different variant of the same layout.

    Money is multiplied by ``factor`` in both the recorded text and the expected
    values. Multiplication distributes over the arithmetic the harness checks
    (qty x price == line_total, and components sum to the total), so the layout
    and every invariant stay valid while the document is no longer a clone.
    """
    scaled_pages: list[list[Block]] = []
    for page in pages:
        scaled_page = []
        for b in page:
            scaled = dataclasses.replace(b, text=_scale_money_text(b.text, factor))
            scaled_page.append(scaled)
        scaled_pages.append(scaled_page)

    scaled_expected = json.loads(json.dumps(expected))
    fields = scaled_expected.get("fields") or {}
    for key in _MONEY_FIELD_KEYS & set(fields):
        if isinstance(fields[key], int):
            fields[key] = fields[key] * factor
    return scaled_pages, scaled_expected


def generate() -> dict:
    """Produce (case_id -> manifest entry) and write recorded fixture files."""
    manifest: dict[str, dict] = {}
    family_by_gen = list(FAMILY_NAMES.items())
    RECORDED.mkdir(parents=True, exist_ok=True)

    seq = 0
    for _slot, (family, gen) in enumerate(family_by_gen):
        for variant in range(2):
            seq += 1
            _cid, expected, pages = gen(seq)
            if variant == 1:
                # Second case in a family: same layout, different amounts, so
                # the pair is two real documents instead of one counted twice.
                pages, expected = _scale_variant(pages, expected, _VARIANT_FACTOR)
            cid = f"ST{seq:02d}"
            fixture_path = RECORDED / f"{cid}.json"
            fixture_path.write_text(
                json.dumps(doc_to_json(cid, pages), ensure_ascii=False, indent=2)
            )
            manifest[cid] = {
                "family": family,
                "recorded": f"recorded/{cid}.json",
                "expected": expected,
            }

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    manifest = generate()
    print(f"wrote {len(manifest)} fixtures -> {RECORDED}")
    print(f"wrote manifest -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()

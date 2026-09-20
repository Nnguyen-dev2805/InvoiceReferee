"""Deterministic invoice field extraction from OCR blocks.

Maps OCR text/layout into candidate header fields and line items, each carrying
provenance (page, bounding box, source block IDs). This module extracts
*candidates only*; it never decides a business action and never invents a value.
Missing values stay ``None``.

Internal ``vendor_id``/``item_id`` are NOT resolved here — they require exact
structured mapping or human selection (see ``identity_resolution``).
"""

from __future__ import annotations

import re
from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion import normalization as norm

# Allow-listed label aliases (lowercased). Vietnamese + English.
FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "invoice_number": ("số hóa đơn", "invoice no", "invoice number", "số"),
    "invoice_series": ("ký hiệu", "series"),
    "vendor_tax_code": ("mã số thuế", "tax code", "tax id", "mst"),
    "po_id": ("purchase order", "po number", "po no", "số po", "đơn hàng"),
    "invoice_date": ("ngày hóa đơn", "invoice date", "ngày", "date"),
    "total_amount": ("tổng cộng", "tổng thanh toán", "total amount", "grand total", "tổng tiền"),
}

# Header fields that normalize as money / date / plain id.
_MONEY_FIELDS = {"total_amount"}
_DATE_FIELDS = {"invoice_date"}

# Line-item column aliases (lowercased) mapped to canonical field names.
_LINE_COLUMNS: dict[str, tuple[str, ...]] = {
    "description": ("mô tả", "description", "tên hàng", "hàng hóa", "diễn giải"),
    "invoiced_quantity": ("số lượng", "quantity", "qty", "sl"),
    "unit_price": ("đơn giá", "unit price", "price"),
    "line_total": ("thành tiền", "line total", "amount", "total"),
}


def _split_label_value(text: str) -> Optional[tuple[str, str]]:
    """Split a ``label: value`` block. Returns ``(label, value)`` or ``None``."""
    for sep in (":", "："):
        if sep in text:
            label, _, value = text.partition(sep)
            return label.strip().lower(), value.strip()
    return None


def _match_field(label: str) -> Optional[str]:
    """Return the field name whose alias best matches ``label``."""
    best: Optional[str] = None
    best_len = 0
    for field_name, aliases in FIELD_LABELS.items():
        for alias in aliases:
            if alias in label and len(alias) > best_len:
                best = field_name
                best_len = len(alias)
    return best


def _normalize_value(field_name: str, value: str):
    if field_name in _MONEY_FIELDS:
        return norm.normalize_money(value)
    if field_name in _DATE_FIELDS:
        return norm.normalize_date(value)
    return norm.normalize_id(value)


def _candidate(
    field_name: str,
    raw_text: Optional[str],
    value,
    block: Optional[m.OCRBlock],
) -> m.FieldCandidate:
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=raw_text,
        normalized_value=value,
        confidence=block.confidence if block else None,
        status=m.FieldStatus.EXTRACTED if value is not None else m.FieldStatus.MISSING,
        page_number=block.page_number if block else None,
        bounding_box=block.bounding_box if block else None,
        evidence_block_ids=[block.block_id] if block else [],
        extraction_method="OCR_RULE",
        warnings=[] if value is not None else ["value could not be normalized"],
    )


def _extract_headers(document: m.OCRDocument) -> dict[str, m.FieldCandidate]:
    fields: dict[str, m.FieldCandidate] = {}
    for block in document.blocks:
        parts = _split_label_value(block.text)
        if not parts:
            continue
        label, value = parts
        if not value:
            continue
        field_name = _match_field(label)
        if field_name is None or field_name in fields:
            continue
        fields[field_name] = _candidate(
            field_name, value, _normalize_value(field_name, value), block
        )
    return fields


def _extract_line_items(document: m.OCRDocument) -> list[dict[str, m.FieldCandidate]]:
    """Reconstruct line items from TABLE_CELL blocks using row/column indices."""
    cells = [
        b
        for b in document.blocks
        if b.block_type == "TABLE_CELL" and b.row_index is not None and b.column_index is not None
    ]
    if not cells:
        return []

    # Resolve which canonical field each column maps to, using header row (row 0).
    column_field: dict[int, str] = {}
    header_cells = [c for c in cells if c.row_index == 0]
    for cell in header_cells:
        text = cell.text.strip().lower()
        for field_name, aliases in _LINE_COLUMNS.items():
            if any(alias in text for alias in aliases):
                column_field[cell.column_index] = field_name
                break

    if not column_field:
        return []

    rows: dict[int, dict[str, m.FieldCandidate]] = {}
    for cell in cells:
        if cell.row_index == 0:
            continue  # header row is not data
        field_name = column_field.get(cell.column_index)
        if field_name is None:
            continue
        value = _normalize_line_value(field_name, cell.text)
        rows.setdefault(cell.row_index, {})[field_name] = _candidate(
            field_name, cell.text, value, cell
        )

    return [rows[key] for key in sorted(rows)]


def _normalize_line_value(field_name: str, text: str):
    if field_name in ("unit_price", "line_total"):
        return norm.normalize_money(text)
    if field_name == "invoiced_quantity":
        cleaned = re.sub(r"[^\d-]", "", text)
        return int(cleaned) if cleaned and cleaned.lstrip("-").isdigit() else None
    return norm.normalize_id(text)


def extract_invoice_fields(document: m.OCRDocument) -> m.InvoiceExtractionResult:
    """Extract header field and line-item candidates from an OCR document."""
    fields = _extract_headers(document)
    line_items = _extract_line_items(document)

    warnings: list[str] = []
    if not fields:
        warnings.append("no header fields could be extracted")

    return m.InvoiceExtractionResult(
        document_id=document.document_id,
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields,
        line_items=line_items,
        warnings=warnings,
    )

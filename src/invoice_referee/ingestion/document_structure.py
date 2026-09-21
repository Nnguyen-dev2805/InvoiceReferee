"""Deterministic document-structure analysis for invoice OCR.

Derives a provider-neutral :class:`DocumentStructure` from an ``OCRDocument``:
which section each block belongs to, the role of every table row, and spatial
neighbor relations for split label/value binding. It computes *where meaning
lives*; it never reads or normalizes field values.

Pure functions and standard library only (``unicodedata``, ``re``). The gap and
overlap constants below are prototype configuration, evaluated on the
development set — not universal geometry rules.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion import normalization as norm

# --- spatial configuration (prototype; evaluate on the dev set) --------------
MIN_VERTICAL_OVERLAP = 0.50
MIN_HORIZONTAL_OVERLAP = 0.30
MAX_RIGHT_GAP = 0.20
MAX_BELOW_GAP = 0.12


def normalize_label(text: str) -> str:
    """NFKC-fold, lowercase, collapse whitespace, and trim label punctuation."""
    value = unicodedata.normalize("NFKC", text or "").casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n:：()")


# --- column / summary concept aliases (normalized, longest-first) ------------
_COLUMN_CONCEPTS: dict[str, tuple[str, ...]] = {
    "description": ("tên hàng hóa, dịch vụ", "mô tả", "description", "tên hàng", "diễn giải"),
    "unit": ("đvt", "unit", "đơn vị tính"),
    "quantity": ("sl", "số lượng", "quantity", "qty"),
    "unit_price": ("đơn giá", "unit price", "price"),
    "line_total": ("thành tiền", "line total", "amount", "thanh tien"),
}

# Summary aliases, most specific first. Order of the fields also encodes
# specificity when two aliases would otherwise tie.
_SUMMARY_ALIASES: tuple[tuple[str, m.TableRowRole], ...] = (
    ("tổng cộng tiền thanh toán", m.TableRowRole.GRAND_TOTAL),
    ("tổng cộng thanh toán", m.TableRowRole.GRAND_TOTAL),
    ("tổng tiền thanh toán", m.TableRowRole.GRAND_TOTAL),
    ("total payment", m.TableRowRole.GRAND_TOTAL),
    ("grand total", m.TableRowRole.GRAND_TOTAL),
    ("amount due", m.TableRowRole.GRAND_TOTAL),
    ("tổng tiền thuế", m.TableRowRole.TAX),
    ("tiền thuế gtgt", m.TableRowRole.TAX),
    ("thuế gtgt", m.TableRowRole.TAX),
    ("tax", m.TableRowRole.TAX),
    ("vat", m.TableRowRole.TAX),
    ("cộng tiền hàng", m.TableRowRole.SUBTOTAL),
    ("thành tiền chưa thuế", m.TableRowRole.SUBTOTAL),
    ("subtotal", m.TableRowRole.SUBTOTAL),
    ("chiết khấu", m.TableRowRole.DISCOUNT),
    ("giảm giá", m.TableRowRole.DISCOUNT),
    ("discount", m.TableRowRole.DISCOUNT),
    ("phí vận chuyển", m.TableRowRole.SHIPPING),
    ("phí giao hàng", m.TableRowRole.SHIPPING),
    ("shipping", m.TableRowRole.SHIPPING),
    # Generic total alias is last so it never overrides a specific one.
    ("tổng cộng", m.TableRowRole.GRAND_TOTAL),
    ("tổng tiền", m.TableRowRole.GRAND_TOTAL),
)

# --- section anchors (normalized substrings) ---------------------------------
_SELLER_ANCHORS = ("đơn vị bán", "người bán", "seller", "bên bán")
_BUYER_ANCHORS = ("đơn vị mua", "người mua", "buyer", "bên mua")
_SIGNATURE_ANCHORS = ("người bán hàng", "người mua hàng", "ký điện tử",
                      "signed", "signature", "chữ ký")
_FOOTER_ANCHORS = ("http://", "https://", "www.", "tra cứu", "mã tra cứu",
                   "giải pháp hóa đơn", "cung cấp bởi")


# --- table grouping / classification -----------------------------------------


def _group_table_rows(document: m.OCRDocument) -> dict[tuple[int, int, int], list[m.OCRBlock]]:
    rows: dict[tuple[int, int, int], list[m.OCRBlock]] = defaultdict(list)
    for block in document.blocks:
        if block.block_type != "TABLE_CELL":
            continue
        if block.table_index is None or block.row_index is None:
            continue
        rows[(block.page_number, block.table_index, block.row_index)].append(block)
    for cells in rows.values():
        cells.sort(key=lambda b: b.column_index if b.column_index is not None else 10_000)
    return dict(rows)


def _is_money(text: str) -> bool:
    return norm.normalize_money(text) is not None


def _looks_ordinal(cells_text: list[str]) -> bool:
    """A row of bare column numbers / formula labels like ``1 2 3 4 5 6=4x5``."""
    hits = 0
    for raw in cells_text:
        t = raw.strip()
        if not t:
            continue
        # A single small integer, or a formula such as "6 = 4 x 5".
        if re.fullmatch(r"\d{1,2}", t):
            hits += 1
        elif re.fullmatch(r"\d+\s*=\s*\d+\s*[x×*]\s*\d+", t):
            hits += 1
    return hits >= 3


def classify_table_row(cells: list[m.OCRBlock]) -> m.TableRowRole:
    """Classify one grouped table row deterministically, in fixed order."""
    texts = [c.text for c in cells]
    normalized = [normalize_label(t) for t in texts]

    # EMPTY: nothing after normalization.
    if all(not n for n in normalized):
        return m.TableRowRole.EMPTY

    # COLUMN_HEADER: >=2 distinct column concepts matched.
    matched_concepts = set()
    for n in normalized:
        for concept, aliases in _COLUMN_CONCEPTS.items():
            if any(alias in n for alias in aliases):
                matched_concepts.add(concept)
                break
    if len(matched_concepts) >= 2:
        return m.TableRowRole.COLUMN_HEADER

    # ORDINAL_HEADER: >=3 column-number / formula cells.
    if _looks_ordinal(texts):
        return m.TableRowRole.ORDINAL_HEADER

    # SUMMARY family: a specific label cell + at least one money cell elsewhere.
    summary_role = _match_summary_role(normalized)
    if summary_role is not None and any(_is_money(t) for t in texts):
        return summary_role

    # DATA: non-empty description + quantity + (unit price or line total).
    if _looks_like_data_row(cells, normalized):
        return m.TableRowRole.DATA

    return m.TableRowRole.AMBIGUOUS


def _match_summary_role(normalized_cells: list[str]) -> Optional[m.TableRowRole]:
    """Longest, most-specific alias wins across all cells in the row."""
    best_role: Optional[m.TableRowRole] = None
    best_len = 0
    for n in normalized_cells:
        for alias, role in _SUMMARY_ALIASES:
            if alias in n and len(alias) > best_len:
                best_role = role
                best_len = len(alias)
    return best_role


def _looks_like_data_row(cells: list[m.OCRBlock], normalized: list[str]) -> bool:
    # Heuristic without column mapping: a text description cell, a small-integer
    # quantity cell, and at least one money cell.
    has_description = any(
        n and not _is_money(c.text) and not re.fullmatch(r"\d{1,3}", c.text.strip())
        for c, n in zip(cells, normalized)
    )
    has_quantity = any(re.fullmatch(r"0?\d{1,3}", c.text.strip()) for c in cells)
    money_cells = sum(1 for c in cells if _is_money(c.text))
    return has_description and has_quantity and money_cells >= 1


# --- section classification --------------------------------------------------


def _classify_sections(
    document: m.OCRDocument,
    row_role_by_key: dict[tuple[int, int, int], m.TableRowRole],
) -> dict[str, m.SectionRole]:
    sections: dict[str, m.SectionRole] = {}

    # Item-table vertical extent (per page) from classified table cells.
    table_top: dict[int, float] = {}
    table_bottom: dict[int, float] = {}
    for block in document.blocks:
        if block.block_type != "TABLE_CELL":
            continue
        key = (block.page_number, block.table_index, block.row_index)
        role = row_role_by_key.get(key)
        if role in (m.TableRowRole.SUBTOTAL, m.TableRowRole.TAX, m.TableRowRole.DISCOUNT,
                    m.TableRowRole.SHIPPING, m.TableRowRole.GRAND_TOTAL):
            sections[block.block_id] = m.SectionRole.SUMMARY
        elif role is not None:
            sections[block.block_id] = m.SectionRole.ITEM_TABLE
        bb = block.bounding_box
        if bb is not None:
            p = block.page_number
            table_top[p] = min(table_top.get(p, bb.y1), bb.y1)
            table_bottom[p] = max(table_bottom.get(p, bb.y2), bb.y2)

    # Non-table blocks by reading order (page, y, x).
    non_table = [b for b in document.blocks if b.block_type != "TABLE_CELL"]
    non_table.sort(key=lambda b: (b.page_number, b.bounding_box.y1 if b.bounding_box else 0,
                                  b.bounding_box.x1 if b.bounding_box else 0))

    current = m.SectionRole.HEADER
    for block in non_table:
        n = normalize_label(block.text)
        p = block.page_number
        below_table = (
            block.bounding_box is not None
            and p in table_bottom
            and block.bounding_box.y1 >= table_bottom[p]
        )
        # Footer wins wherever it appears.
        if any(a in n for a in _FOOTER_ANCHORS):
            sections[block.block_id] = m.SectionRole.FOOTER
            current = m.SectionRole.FOOTER
            continue
        if below_table and any(a in n for a in _SIGNATURE_ANCHORS):
            current = m.SectionRole.SIGNATURE
        elif any(a in n for a in _SIGNATURE_ANCHORS) and below_table:
            current = m.SectionRole.SIGNATURE
        elif any(a in n for a in _SELLER_ANCHORS) and not below_table:
            current = m.SectionRole.SELLER
        elif any(a in n for a in _BUYER_ANCHORS) and not below_table:
            current = m.SectionRole.BUYER
        elif below_table and current in (m.SectionRole.HEADER, m.SectionRole.SELLER,
                                         m.SectionRole.BUYER):
            current = m.SectionRole.SIGNATURE
        sections[block.block_id] = current
    return sections


# --- spatial neighbors -------------------------------------------------------


def _overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    """Fraction of the shorter interval covered by the intersection."""
    lo = max(a1, b1)
    hi = min(a2, b2)
    inter = max(0.0, hi - lo)
    shorter = min(a2 - a1, b2 - b1)
    if shorter <= 0:
        return 0.0
    return inter / shorter


def _build_neighbors(
    document: m.OCRDocument,
    sections: dict[str, m.SectionRole],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    blocks = [b for b in document.blocks if b.block_type != "TABLE_CELL" and b.bounding_box]
    right: dict[str, list[str]] = {}
    below: dict[str, list[str]] = {}
    for anchor in blocks:
        ab = anchor.bounding_box
        rights: list[tuple[float, str]] = []
        belows: list[tuple[float, str]] = []
        for other in blocks:
            if other.block_id == anchor.block_id:
                continue
            if other.page_number != anchor.page_number:
                continue
            if sections.get(other.block_id) != sections.get(anchor.block_id):
                continue
            ob = other.bounding_box
            # right neighbor
            v_overlap = _overlap(ab.y1, ab.y2, ob.y1, ob.y2)
            gap_right = ob.x1 - ab.x2
            if v_overlap >= MIN_VERTICAL_OVERLAP and 0 <= gap_right <= MAX_RIGHT_GAP:
                rights.append((gap_right, other.block_id))
            # below neighbor
            h_overlap = _overlap(ab.x1, ab.x2, ob.x1, ob.x2)
            gap_below = ob.y1 - ab.y2
            if h_overlap >= MIN_HORIZONTAL_OVERLAP and 0 <= gap_below <= MAX_BELOW_GAP:
                belows.append((gap_below, other.block_id))
        right[anchor.block_id] = [bid for _, bid in sorted(rights)]
        below[anchor.block_id] = [bid for _, bid in sorted(belows)]
    return right, below


# --- public entry point ------------------------------------------------------


def analyze_document_structure(document: m.OCRDocument) -> m.DocumentStructure:
    """Return the deterministic structural view of an ``OCRDocument``."""
    blocks_by_row = _group_table_rows(document)
    row_role_by_key = {key: classify_table_row(cells) for key, cells in blocks_by_row.items()}
    sections = _classify_sections(document, row_role_by_key)
    right, below = _build_neighbors(document, sections)
    return m.DocumentStructure(
        section_by_block_id=sections,
        row_role_by_key=row_role_by_key,
        blocks_by_table_row=blocks_by_row,
        right_neighbor_by_block_id=right,
        below_neighbor_by_block_id=below,
        warnings=[],
    )

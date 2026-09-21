"""Deterministic invoice field extraction from OCR blocks.

Maps OCR text/layout into candidate header fields and line items, each carrying
provenance (page, bounding box, source block IDs). This module extracts
*candidates only*; it never decides a business action and never invents a value.
Missing values stay ``None``.

Two extraction styles share the same public entry point ``extract_invoice_fields``:

- ``extract_header_candidates`` — header/seller/buyer/date total amount fields,
  scoped by ``DocumentStructure`` section roles and spatial neighbour binding.
- ``extract_table_candidates`` — line items (data rows only) and summary money
  fields (subtotal/tax/discount/shipping/total) from classified table rows.

These extractors are deterministic. A semantic LLM fallback is *not* wired in by
default; it is reserved for Task 7 and is disabled by configuration.

Internal ``vendor_id``/``item_id`` are NOT resolved here — they require exact
structured mapping or human selection (see ``identity_resolution``).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion import normalization as norm
from invoice_referee.ingestion.document_structure import (
    analyze_document_structure,
    normalize_label,
)
from invoice_referee.ingestion.candidate_resolver import resolve_field_candidates
from invoice_referee.ingestion.extraction_validation import validate_extraction

# --- Extraction-only field sets (do NOT leak into business schema) --------------

# Header fields that are normalised as money.
MONEY_FIELDS = {"total_amount", "subtotal_amount", "tax_amount",
                "discount_amount", "shipping_amount"}

# Header fields that are normalised as dates.
DATE_FIELDS = {"invoice_date", "signature_date"}

# Allow-listed label aliases (normalized, longest-first).
# Header aliases drive EXACT_KEY_VALUE and EXACT_SPATIAL extraction; they must be
# specific enough that a substring match cannot confuse fields (e.g. "tổng tiền
# thuế" must never match a "tổng cộng" total alias). Fuzzy matching is bounded by
# FUZZY_LABEL_THRESHOLD and is never used on values/IDs/tax/PO/date/number.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "invoice_series": ("mẫu số - ký hiệu", "ký hiệu", "serial no", "series"),
    "invoice_number": ("số hóa đơn", "invoice no", "invoice number", "số"),
    "vendor_tax_code": ("mã số thuế", "ma so thue", "tax code", "tax id", "mst"),
    "po_id": ("purchase order", "po number", "po no", "số po", "đơn hàng"),
    "invoice_date": ("ngày hóa đơn", "ngay hoa don", "invoice date", "ngày", "ngay", "date"),
    "total_amount": ("tổng cộng thanh toán", "tổng thanh toán",
                     "total payment", "grand total", "amount due",
                     "tổng cộng", "total amount"),
}

# Line-item column aliases (normalized, longest-first) -> canonical field names.
LINE_COLUMNS: dict[str, tuple[str, ...]] = {
    "description": ("tên hàng hóa, dịch vụ", "mô tả", "description", "tên hàng", "diễn giải"),
    "invoiced_quantity": ("số lượng", "quantity", "qty", "sl"),
    "unit_price": ("đơn giá", "unit price", "price"),
    "line_total": ("thành tiền", "line total", "amount", "total"),
}

# Row summary label -> canonical summary field. Order is longest/most-specific
# first so a longer alias wins a tie at the same length band.
_SUMMARY_FIELD_BY_ROLE = {
    m.TableRowRole.GRAND_TOTAL: "total_amount",
    m.TableRowRole.TAX: "tax_amount",
    m.TableRowRole.SUBTOTAL: "subtotal_amount",
    m.TableRowRole.DISCOUNT: "discount_amount",
    m.TableRowRole.SHIPPING: "shipping_amount",
}

# Fuzzy label matching: values/IDs/tax/PO/date/number are never fuzzy-matched.
# Fuzzy matching only ever touches header *labels*. Threshold is prototype config.
FUZZY_LABEL_THRESHOLD = 0.82


# --- value dispatch ------------------------------------------------------------


def normalize_candidate_value(field_name: str, raw_text: str):
    """Normalize a raw OCR value according to its canonical field type."""
    if field_name in MONEY_FIELDS:
        return norm.normalize_money(raw_text)
    if field_name in DATE_FIELDS:
        return norm.normalize_date(raw_text)
    return norm.normalize_id(raw_text)


def _normalize_line_value(field_name: str, text: str):
    if field_name in ("unit_price", "line_total"):
        return norm.normalize_money(text)
    if field_name == "invoiced_quantity":
        cleaned = re.sub(r"[^\d-]", "", text)
        return int(cleaned) if cleaned and cleaned.lstrip("-").isdigit() else None
    return norm.normalize_id(text)


# --- fuzzy label matching ------------------------------------------------------


def fuzzy_label_match(label_text: str, field_name: str) -> Optional[float]:
    """Return the best fuzzy label ratio for ``field_name`` or ``None``.

    Only header label text is compared; fuzzy matching never operates on
    values/IDs/tax/PO/number/date. Scores are rounded to 2 decimals.
    """
    normalized = normalize_label(label_text)
    if not normalized or field_name not in HEADER_ALIASES:
        return None
    best = 0.0
    for alias in HEADER_ALIASES[field_name]:
        ratio = SequenceMatcher(None, normalized, alias).ratio()
        if ratio > best:
            best = ratio
    if best < FUZZY_LABEL_THRESHOLD:
        return None
    return round(best, 2)


# --- exact label matching ------------------------------------------------------


def _alias_matches(alias: str, label: str) -> bool:
    """True when ``alias`` identifies ``label``.

    A single-word alias ("số", "ngày", "mst", "total") is too generic to match
    as a substring: "Số tài khoản" (bank account) and "Số điện thoại" would
    otherwise be read as the invoice number. Such an alias must equal the whole
    label, or lead a value that is itself parseable in the alias's own domain —
    e.g. the Vietnamese date form "Ngày 10 tháng 07 năm 2023", where "ngày" is
    the label and the remainder is the value. "Ngày giao hàng" (delivery date)
    still fails because its remainder is not a date. Multi-word aliases keep the
    substring rule so "số hóa đơn" matches "số hóa đơn ký hiệu ...".
    """
    if alias == label:
        return True
    if " " in alias:
        return alias in label
    if label.startswith(alias + " "):
        return _extract_date(label[len(alias):]) is not None
    return False


def _match_field(label: str) -> Optional[str]:
    """Return the field whose longest alias matches ``label``."""
    best: Optional[str] = None
    best_len = 0
    for field_name, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if _alias_matches(alias, label) and len(alias) > best_len:
                best = field_name
                best_len = len(alias)
    return best


def _split_label_value(text: str) -> Optional[tuple[str, str]]:
    """Split a ``label: value`` block. Returns ``(label, value)`` or ``None``."""
    for sep in (":", "："):
        if sep in text:
            label, _, value = text.partition(sep)
            return label.strip().lower(), value.strip()
    return None


# --- date extraction from arbitrary text ---------------------------------------


_DATE_TOKEN = re.compile(
    r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}\s*(?:tháng|thang)\s*\d{1,2}\s*(?:năm|nam)\s*\d{4}"
)


def _extract_date(raw_text: str) -> Optional[str]:
    """Pull the first parseable date out of arbitrary text; else ``None``."""
    if not raw_text:
        return None
    for match in _DATE_TOKEN.finditer(raw_text):
        candidate = norm.normalize_date(match.group(0))
        if candidate is not None:
            return candidate
    return None


# --- candidate construction ----------------------------------------------------


def _candidate(
    field_name: str,
    raw_text: str,
    value,
    block: Optional[m.OCRBlock],
    *,
    extraction_method: str = "EXACT_KEY_VALUE",
    evidence_block_ids=None,
    section_role: Optional[str] = None,
    mapping_score: float = 1.0,
) -> m.FieldCandidate:
    status = m.FieldStatus.EXTRACTED if value is not None else m.FieldStatus.MISSING
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=raw_text,
        normalized_value=value,
        confidence=block.confidence if block else None,
        status=status,
        page_number=block.page_number if block else None,
        bounding_box=block.bounding_box if block else None,
        evidence_block_ids=list(evidence_block_ids or ([block.block_id] if block else [])),
        extraction_method=extraction_method,
        warnings=[] if value is not None else ["value could not be normalized"],
        provider_confidence=block.confidence if block else None,
        mapping_score=mapping_score,
        section_role=section_role,
    )


# --- header / section-aware extraction -----------------------------------------


def _section_role_for(structure, block: m.OCRBlock) -> Optional[str]:
    if structure is None:
        return None
    return structure.section_by_block_id.get(block.block_id)


def _exact_key_value_candidates(document: m.OCRDocument, structure) -> dict[str, list[m.FieldCandidate]]:
    """One-block ``label: value`` candidates (EXACT_KEY_VALUE)."""
    fields: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    for block in document.blocks:
        if block.block_type == "TABLE_CELL":
            continue
        parts = _split_label_value(block.text)
        if not parts:
            continue
        label, value = parts
        if not value:
            continue
        field_name = _match_field(label)
        if field_name is None:
            continue
        normalized = normalize_candidate_value(field_name, value)
        fields[field_name].append(_candidate(
            field_name, value, normalized, block,
            extraction_method="EXACT_KEY_VALUE",
            section_role=_section_role_for(structure, block),
        ))
    return fields


def _section_aware_candidates(document: m.OCRDocument, structure) -> dict[str, list[m.FieldCandidate]]:
    """Section-scoped field candidates (SECTION_AWARE).

    Resolves fields that appear in multiple sections (e.g. two tax codes) by
    choosing the section-appropriate one: ``vendor_tax_code`` from the SELLER
    section, ``invoice_date`` from HEADER (preferred) over SIGNATURE.
    """
    fields: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    if structure is None:
        return fields

    for block in document.blocks:
        if block.block_type == "TABLE_CELL":
            continue
        section = structure.section_by_block_id.get(block.block_id)
        if section is None or not block.text:
            continue
        text = block.text
        # Match on the label part only, so a value that happens to contain a
        # date ("Ngày giao hàng: 13/09/2026") cannot make the whole line look
        # like an invoice-date label.
        parts = _split_label_value(text)
        label = normalize_label(parts[0] if parts else text)

        # vendor_tax_code from the SELLER section only.
        if section == "SELLER" and _match_field(label) == "vendor_tax_code":
            parts = _split_label_value(text)
            value = parts[1] if parts else text
            normalized = norm.normalize_id(value)
            fields["vendor_tax_code"].append(_candidate(
                "vendor_tax_code", value, normalized, block,
                extraction_method="SECTION_AWARE", section_role=section,
            ))
            continue

        # invoice_date: a date-bearing block in HEADER or SIGNATURE. The bare
        # "ngày" alias must not match a different date such as "Ngày giao hàng"
        # (delivery date); only the invoice-date aliases qualify.
        if section in ("HEADER", "SIGNATURE") and _match_field(label) == "invoice_date":
            normalized = _extract_date(text)
            if normalized is None and ":" in text:
                normalized = _extract_date(text.split(":", 1)[1])
            fields["invoice_date"].append(_candidate(
                "invoice_date", text, normalized, block,
                extraction_method="SECTION_AWARE", section_role=section,
            ))
    return fields


def _exact_spatial_candidates(
    document: m.OCRDocument, structure
) -> dict[str, list[m.FieldCandidate]]:
    """Bind a free TEXT label block to its nearest right/below value block."""
    fields: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    if structure is None:
        return fields
    blocks_by_id = {b.block_id: b for b in document.blocks}
    for block in document.blocks:
        if block.block_type == "TABLE_CELL":
            continue
        section = structure.section_by_block_id.get(block.block_id)
        label = normalize_label(block.text)
        if not label:
            continue
        field_name = _match_field(label)
        if field_name is None:
            continue
        # Inline values already have exact candidates; spatial binding is for
        # labels without a value. Prefer valid right values before looking below.
        parts = _split_label_value(block.text)
        if parts and parts[1]:
            continue
        neighbors = (structure.right_neighbor_by_block_id.get(block.block_id, [])
                     + structure.below_neighbor_by_block_id.get(block.block_id, []))
        for neighbor_id in neighbors:
            neighbor = blocks_by_id.get(neighbor_id)
            if neighbor is None or not neighbor.text or neighbor.text.strip() == "":
                continue
            value_text = neighbor.text.strip()
            normalized = normalize_candidate_value(field_name, value_text)
            if normalized is None:
                continue
            fields[field_name].append(_candidate(
                field_name, value_text, normalized, neighbor,
                extraction_method="EXACT_SPATIAL",
                evidence_block_ids=[block.block_id, neighbor_id],
                section_role=section,
            ))
            break  # first normalizable right/below neighbor wins
    return fields


def _fuzzy_spatial_candidates(
    document: m.OCRDocument, structure
) -> dict[str, list[m.FieldCandidate]]:
    """Fuzzy label match for blocks that exact matching missed (NEEDS_CONFIRMATION)."""
    fields: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    if structure is None:
        return fields
    # Track which (field, block) pairs were already produced by exact methods.
    for block in document.blocks:
        if block.block_type == "TABLE_CELL":
            continue
        text = block.text or ""
        parts = _split_label_value(text)
        label = parts[0] if parts else text
        if not label:
            continue
        for field_name in HEADER_ALIASES:
            if _match_field(normalize_label(label)) == field_name:
                continue  # exact extraction already owns this label
            score = fuzzy_label_match(label, field_name)
            if score is None:
                continue
            # Derive a value via label:value split or nearest value neighbor.
            value = None
            value_text = ""
            block_ids = [block.block_id]
            if parts:
                _, value_text = parts
                value = normalize_candidate_value(field_name, value_text)
            if value is None:
                neighbors = (structure.right_neighbor_by_block_id.get(block.block_id, [])
                             + structure.below_neighbor_by_block_id.get(block.block_id, []))
                for neighbor_id in neighbors:
                    neighbor = next((b for b in document.blocks if b.block_id == neighbor_id), None)
                    if neighbor and neighbor.text and neighbor.text.strip():
                        neighbor_text = neighbor.text.strip()
                        value = normalize_candidate_value(field_name, neighbor_text)
                        if value is None:
                            continue
                        value_text = neighbor_text
                        block_ids = [block.block_id, neighbor_id]
                        break
            candidate = _candidate(
                field_name, value_text, value, block,
                extraction_method="FUZZY_SPATIAL",
                evidence_block_ids=block_ids,
                section_role=structure.section_by_block_id.get(block.block_id),
                mapping_score=score,
            )
            candidate.status = m.FieldStatus.NEEDS_CONFIRMATION
            fields[field_name].append(candidate)
    return fields


# Sections preferred when multiple candidates survive for one field. The order
# breaks ties at equal method priority: a higher-precedence section candidate is
# placed before a lower-precedence one so the resolver (first valued winner)
# picks the structurally correct value.
_SECTION_PRIORITY: dict[str, int] = {
    m.SectionRole.HEADER.value: 0,
    m.SectionRole.SELLER.value: 1,
    m.SectionRole.BUYER.value: 2,
    m.SectionRole.ITEM_TABLE.value: 3,
    m.SectionRole.SUMMARY.value: 4,
    m.SectionRole.SIGNATURE.value: 5,
    m.SectionRole.FOOTER.value: 6,
    m.SectionRole.UNKNOWN.value: 7,
    None: 8,
}


def _reorder_by_section(candidates: list[m.FieldCandidate]) -> list[m.FieldCandidate]:
    """Stable-sort candidates by section priority (ties keep input order)."""
    return sorted(
        candidates,
        key=lambda c: _SECTION_PRIORITY.get(c.section_role, 8),
    )


def extract_header_candidates(
    document: m.OCRDocument, structure: Optional[m.DocumentStructure] = None
) -> dict[str, list[m.FieldCandidate]]:
    """Produce all header/date/total-amount candidates, section & spatially aware.

    Candidates are returned in priority order: exact methods first, then section
    awareness, then spatial, then fuzzy. Within each method tier, section priority
    breaks ties so that, e.g., a HEADER-section date precedes a SIGNATURE-section
    date for the same field.
    """
    sources = (
        _exact_key_value_candidates(document, structure),
        _section_aware_candidates(document, structure),
        _exact_spatial_candidates(document, structure),
        _fuzzy_spatial_candidates(document, structure),
    )
    merged: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    for source in sources:
        for field_name, candidates in source.items():
            merged[field_name].extend(candidates)
    # Re-stable-order within each field by section priority (HEADER > SELLER >
    # BUYER > ... > SIGNATURE). This makes section role break method-priority
    # ties deterministically without changing the resolver.
    return {name: _reorder_by_section(cands) for name, cands in merged.items()}


# --- table extraction (line items + summary) -----------------------------------


def _column_mapping(
    header_cells: list[m.OCRBlock],
) -> dict[int, str]:
    """Map a column index to a canonical line-item field using header row text."""
    mapping: dict[int, str] = {}
    for cell in header_cells:
        if cell.column_index is None:
            continue
        text = normalize_label(cell.text)
        if not text:
            continue
        for field_name, aliases in LINE_COLUMNS.items():
            if any(alias in text for alias in aliases):
                mapping[cell.column_index] = field_name
                break
    return mapping


def _row_cells_by_column(cells: list[m.OCRBlock]) -> dict[int, m.OCRBlock]:
    return {c.column_index: c for c in cells if c.column_index is not None}


@dataclass
class TableExtraction:
    """Output of table item + summary extraction."""

    field_candidates: dict[str, list[m.FieldCandidate]] = field(default_factory=dict)
    selected_line_items: list[dict[str, m.FieldCandidate]] = field(default_factory=list)
    line_item_candidate_sets: list[dict[str, list[m.FieldCandidate]]] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)


def _money_value(text: str) -> Optional[int]:
    return norm.normalize_money(text)


def _summary_field_for_row(row_key, cells: list[m.OCRBlock], role: m.TableRowRole) -> Optional[m.FieldCandidate]:
    """Build a summary money candidate for a classified summary row.

    The rightmost money cell is the value; the leftmost text cell is the label.
    Cites both; uses the minimum provider confidence among cited blocks and a full
    mapping score for an exact summary alias.
    """
    field_name = _SUMMARY_FIELD_BY_ROLE.get(role)
    if field_name is None:
        return None

    money_cells = [c for c in cells if _money_value(c.text) is not None]
    if not money_cells:
        return None
    # Rightmost money cell (by column index) is the total value.
    value_cell = max(money_cells, key=lambda c: c.column_index if c.column_index is not None else 0)
    value = _money_value(value_cell.text)
    if value is None:
        return None

    label_cell = cells[0] if cells else value_cell
    evidence = []
    if label_cell is not value_cell:
        evidence.append(label_cell.block_id)
    evidence.append(value_cell.block_id)
    evidence = list(dict.fromkeys(evidence))

    confidences = [c.confidence for c in cells if c.confidence is not None]
    provider_conf = min(confidences) if confidences else None
    # The summary alias is matched exactly here, so mapping_score is full.
    return _candidate(
        field_name,
        value_cell.text,
        value,
        value_cell,
        extraction_method="TABLE_SUMMARY",
        evidence_block_ids=evidence,
        section_role="SUMMARY",
        mapping_score=1.0,
    )


def _data_row_line_item(cells: list[m.OCRBlock], column_map: dict[int, str]) -> dict[str, m.FieldCandidate]:
    """Turn a DATA row's cells into a line-item candidate dict (per canonical field)."""
    by_col = _row_cells_by_column(cells)
    item: dict[str, m.FieldCandidate] = {}
    for col, field_name in column_map.items():
        cell = by_col.get(col)
        if cell is None or not cell.text or not cell.text.strip():
            continue
        value = _normalize_line_value(field_name, cell.text)
        item[field_name] = _candidate(
            field_name, cell.text, value, cell,
            extraction_method="TABLE_ITEM",
            section_role=None,
            mapping_score=1.0,
        )
    if not item:
        return {}
    # Keep only rows that contribute a description — that is what separates a real
    # line item from a stray total or blank row (plan quality invariant #13).
    if "description" not in item:
        return {}
    return item


def extract_table_candidates(
    document: m.OCRDocument, structure: m.DocumentStructure
) -> TableExtraction:
    """Extract line items (DATA rows) and summary money fields from tables."""
    table = TableExtraction()
    if structure is None:
        return table

    column_map: Optional[dict[int, str]] = None
    line_item_candidate_sets: list[dict[str, list[m.FieldCandidate]]] = []
    selected_line_items: list[dict[str, m.FieldCandidate]] = []
    summary_candidates: dict[str, list[m.FieldCandidate]] = defaultdict(list)

    for row_key, cells in structure.blocks_by_table_row.items():
        role = structure.row_role_by_key.get(row_key)
        if role is None:
            continue
        if role is m.TableRowRole.COLUMN_HEADER:
            column_map = _column_mapping(cells)
            continue
        if role is m.TableRowRole.DATA and column_map is not None:
            item = _data_row_line_item(cells, column_map)
            if item:
                candidate_set = {
                    name: [candidate] for name, candidate in item.items()
                }
                line_item_candidate_sets.append(candidate_set)
                selected_line_items.append(item)
            continue
        if role in (m.TableRowRole.SUBTOTAL, m.TableRowRole.TAX,
                    m.TableRowRole.SHIPPING, m.TableRowRole.DISCOUNT,
                    m.TableRowRole.GRAND_TOTAL):
            summary = _summary_field_for_row(row_key, cells, role)
            if summary is not None:
                summary_candidates[summary.field_name].append(summary)

    table.line_item_candidate_sets = line_item_candidate_sets
    table.selected_line_items = selected_line_items
    table.field_candidates = dict(summary_candidates)
    return table


def merge_candidate_sets(
    *sources: dict[str, list[m.FieldCandidate]],
) -> dict[str, list[m.FieldCandidate]]:
    """Merge candidate sets without overwriting; preserves all alternatives."""
    merged: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    for source in sources:
        if not source:
            continue
        for field_name, candidates in source.items():
            merged[field_name].extend(candidates)
    return dict(merged)


def extract_invoice_fields(document: m.OCRDocument) -> m.InvoiceExtractionResult:
    """Extract header field and line-item candidates from an OCR document.

    Public signature is unchanged from the pre-structure-aware pipeline. Internally
    this now runs structure analysis, section-aware header extraction, table
    item/summary extraction, explicit candidate resolution, and validation.
    Validation assigns confirmation status and emits arithmetic/semantic warnings.
    """
    structure = analyze_document_structure(document)
    header_sets = extract_header_candidates(document, structure)
    table = extract_table_candidates(document, structure)

    field_sets = merge_candidate_sets(header_sets, table.field_candidates)
    resolutions = {
        name: resolve_field_candidates(name, candidates)
        for name, candidates in field_sets.items()
    }

    selected_fields = {
        name: r.selected for name, r in resolutions.items() if r.selected is not None
    }

    warnings: list[str] = list(structure.warnings)
    if not selected_fields:
        warnings.append("no header fields could be extracted")

    _add_cross_field_warnings(document, structure, selected_fields, table, warnings)

    result = m.InvoiceExtractionResult(
        document_id=document.document_id,
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=selected_fields,
        line_items=table.selected_line_items,
        field_candidates=field_sets,
        line_item_candidate_sets=table.line_item_candidate_sets,
        warnings=warnings,
    )

    validate_extraction(result)
    return result


def _add_cross_field_warnings(
    document: m.OCRDocument,
    structure: m.DocumentStructure,
    selected_fields: dict[str, m.FieldCandidate],
    table: TableExtraction,
    warnings: list[str],
) -> None:
    """Semantic cross-field warnings that no single field can assert alone.

    These are advisory signals for human review; they do not change the selected
    candidate or suppress CONFLICTING status. Extraction-only money fields are
    scoped to ``InvoiceExtractionResult`` and never leak into the business schema.
    """
    # Warn when seller and buyer tax codes are identical (possible copy/paste).
    _warn_identical_seller_buyer_tax(document, structure, selected_fields, warnings)

    # Warn when the header total disagrees with the reconstructed line sum.
    _warn_total_vs_line_sum(selected_fields, table, warnings)


def _warn_identical_seller_buyer_tax(
    document, structure, selected_fields, warnings
) -> None:
    seller_tax = _find_tax_in_section(document, structure, "SELLER")
    buyer_tax = _find_tax_in_section(document, structure, "BUYER")
    if seller_tax is not None and buyer_tax is not None and seller_tax == buyer_tax:
        warnings.append(
            "seller and buyer tax code are identical; possible copy/paste error"
        )


def _find_tax_in_section(document, structure, section_name: str) -> Optional[str]:
    """Return the normalized tax code text found in the named section, if any."""
    for block in document.blocks:
        if block.block_type == "TABLE_CELL":
            continue
        if structure.section_by_block_id.get(block.block_id) != section_name:
            continue
        parts = _split_label_value(block.text)
        if parts is None:
            continue
        # Match the tax-code label specifically ("mã số thuế" / "mst" / "tax code").
        label = parts[0]
        for alias in HEADER_ALIASES["vendor_tax_code"]:
            if alias in label:
                return norm.normalize_id(parts[1])
    return None


def _warn_total_vs_line_sum(
    selected_fields: dict[str, m.FieldCandidate],
    table: TableExtraction,
    warnings: list[str],
) -> None:
    """Warn when present line totals don't add up to the invoice total."""
    total = _value_from_candidate(selected_fields.get("total_amount"))
    if total is None:
        return
    line_sum = 0
    have_all = bool(table.selected_line_items)
    for line in table.selected_line_items:
        line_total = _value_from_candidate(line.get("line_total"))
        if line_total is None:
            have_all = False
        else:
            line_sum += line_total
    if have_all and line_sum != total:
        warnings.append(
            f"sum of line totals ({line_sum}) does not equal invoice total ({total})"
        )


def _value_from_candidate(candidate: Optional[m.FieldCandidate]):
    return candidate.normalized_value if candidate is not None else None

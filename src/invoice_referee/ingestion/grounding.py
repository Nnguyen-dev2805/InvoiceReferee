"""Grounding verifier for LLM semantic extraction.

The LLM is an *extractor*, never a decision maker. This module is the only thing
between an untrusted model response and the deterministic pipeline, so it is
pure, total, and fails closed: anything it cannot prove against the ``OCRDocument``
is dropped and recorded, never silently accepted and never guessed.

Acceptance requires **all** of:

1. the cited ``block_id`` exists in the document;
2. ``raw_text`` occurs verbatim in the cited blocks — which by itself also forbids
   normalized values, arithmetic, and OCR "correction" (a model answering
   ``9000000`` for a block reading ``9.000.000`` fails here);
3. the field is in the allow-list for the detected document type;
4. the response carries no forbidden key (identity, policy, or action). A model
   that emits policy output is not a model whose other output should be trusted,
   so a forbidden key rejects the entire response.

No LLM call happens here and no value is normalized here — normalization stays in
``ingestion.normalization``, driven by field name.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from invoice_referee.domain import models as m

# --- field profiles -----------------------------------------------------------

# Allow-listed fields per document type. ``UNKNOWN`` allows nothing: without a
# known document type there is no basis for claiming any field, so the extraction
# keeps raw OCR evidence and goes to human review.
FIELD_PROFILES: dict[m.DocumentType, frozenset[str]] = {
    m.DocumentType.SUPPLIER_INVOICE: frozenset({
        "vendor_tax_code",
        "buyer_tax_code",
        "invoice_series",
        "invoice_number",
        "invoice_date",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
        # The buyer's PO reference is printed on the invoice and is a critical
        # field a human must confirm, so the model has to be allowed to read it.
        # Omitting it silently made every LLM-extracted invoice incomplete.
        "po_id",
    }),
    m.DocumentType.RESTAURANT_RECEIPT: frozenset({
        "merchant_name",
        "receipt_number",
        "receipt_datetime",
        "table_number",
        "cashier_name",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
    }),
    m.DocumentType.TEMPORARY_BILL: frozenset({
        "merchant_name",
        "receipt_number",
        "receipt_datetime",
        "table_number",
        "cashier_name",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
    }),
    m.DocumentType.POS_RECEIPT: frozenset({
        "merchant_name",
        "receipt_number",
        "receipt_datetime",
        "table_number",
        "cashier_name",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
    }),
    m.DocumentType.UNKNOWN: frozenset(),
}

# Line-item field names the semantic extractor may emit. Identity (``item_id``) is
# resolved structurally downstream and must never come from the model.
#
# ``quantity`` is the plain name the model is asked to use (it is the word printed
# in a table header); ``invoiced_quantity`` is the canonical business field name.
# Both are accepted here and mapped to the canonical name in the extractor, so the
# model is never required to know internal field naming.
LINE_ITEM_FIELDS: frozenset[str] = frozenset({
    "description",
    "quantity",
    "invoiced_quantity",
    "unit_price",
    "line_total",
    "supplier_sku",
})

# Keys the model must never emit. Presence of any one rejects the whole response.
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "vendor_id",
    "item_id",
    "po_id",
    "policy_rule_ids",
    "policy_rules",
    "action",
    "proposed_action",
    "proposed_uncertainty_type",
    "decision",
    "approved_total",
    "authority_threshold_vnd",
    "scope_status",
})


# --- document type classification ---------------------------------------------

# Anchor phrases, most specific first. OCR mangles Vietnamese diacritics on real
# receipts (the recorded bill reads "PHIẾU TẠM TĨNH"), so matching is done on a
# diacritic-folded form and the anchors are stored folded.
_TYPE_ANCHORS: tuple[tuple[str, m.DocumentType], ...] = (
    ("phieu tam tinh", m.DocumentType.TEMPORARY_BILL),
    ("phieu tinh tien", m.DocumentType.POS_RECEIPT),
    ("hoa don gia tri gia tang", m.DocumentType.SUPPLIER_INVOICE),
    ("hoa don gtgt", m.DocumentType.SUPPLIER_INVOICE),
    ("hoa don thanh toan", m.DocumentType.POS_RECEIPT),
    ("hoa don ban hang", m.DocumentType.SUPPLIER_INVOICE),
)


def _fold(text: str) -> str:
    """NFKD-fold, drop combining marks, lowercase, collapse whitespace.

    Used only to match *document-type anchors* — never to match values, tax codes,
    dates, or numbers, which must stay byte-faithful.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # Vietnamese "đ" does not decompose into a base letter + mark.
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return " ".join(stripped.lower().split())


def classify_document_type(text: str) -> m.DocumentType:
    """Classify a title/anchor string into a :class:`DocumentType`.

    Returns ``UNKNOWN`` when no anchor matches. Tolerates the diacritic damage a
    real OCR provider produces; never guesses from layout or position.
    """
    folded = _fold(text)
    if not folded:
        return m.DocumentType.UNKNOWN
    for anchor, doc_type in _TYPE_ANCHORS:
        if anchor in folded:
            return doc_type
    return m.DocumentType.UNKNOWN


# --- grounded output ----------------------------------------------------------


@dataclass
class GroundedField:
    """One accepted mapping: field name, verbatim raw text, and its citations."""

    field_name: str
    raw_text: str
    block_ids: list[str] = field(default_factory=list)


@dataclass
class GroundedLineItem:
    """One accepted line item: per-field verbatim values and citations."""

    values: dict[str, GroundedField] = field(default_factory=dict)


@dataclass
class GroundedExtraction:
    """What survived grounding. ``rejected`` explains every dropped mapping."""

    document_type: m.DocumentType = m.DocumentType.UNKNOWN
    document_type_block_ids: list[str] = field(default_factory=list)
    fields: list[GroundedField] = field(default_factory=list)
    line_items: list[GroundedLineItem] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


# --- grounding ----------------------------------------------------------------


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


# Currency markers that OCR glues directly onto a number ("4.035.570đ"). They are
# letters, so the alphanumeric boundary rule below would reject a correctly copied
# amount. This is a bounded, explicit list of *boundary* characters — it does not
# touch or compare the value itself.
_CURRENCY_BOUNDARY_CHARS = frozenset("đĐ₫$€£¥")


def _is_boundary(char: str) -> bool:
    return (not char.isalnum()) or char in _CURRENCY_BOUNDARY_CHARS


def _appears_verbatim(raw_text: str, block_text: str) -> bool:
    """Whether ``raw_text`` occurs in ``block_text`` as a standalone segment.

    Plain substring containment is too weak for short values: ``"3"`` is a
    substring of ``"Số hóa đơn: 0000123"``, so a fabricated quantity of 3 would
    "ground" against an invoice number. A match must therefore be bounded by a
    non-alphanumeric character (or a currency marker), or be the whole block.

    This is still literal text matching — no normalization, no case folding, no
    whitespace collapsing — so a model that reformats, computes, or corrects the
    OCR text still fails.
    """
    if not raw_text:
        return False
    if raw_text == block_text.strip():
        return True
    start = 0
    while True:
        index = block_text.find(raw_text, start)
        if index == -1:
            return False
        before = block_text[index - 1] if index > 0 else ""
        after_index = index + len(raw_text)
        after = block_text[after_index] if after_index < len(block_text) else ""
        if (not before or _is_boundary(before)) and (not after or _is_boundary(after)):
            return True
        start = index + 1


def _has_forbidden_key(payload: dict) -> Optional[str]:
    """Return the first forbidden key found anywhere in the payload, if any."""
    for key in payload:
        if isinstance(key, str) and key.strip().lower() in FORBIDDEN_KEYS:
            return key
    return None


def _ground_citation(
    raw_text: Any,
    block_ids: Any,
    *,
    text_by_id: dict[str, str],
    label: str,
    rejected: list[str],
) -> Optional[GroundedField]:
    """Validate one (raw_text, block_ids) pair, or record why it was rejected."""
    if not isinstance(block_ids, list) or not block_ids:
        rejected.append(f"{label}: no block_ids cited")
        return None
    if not all(isinstance(b, str) for b in block_ids):
        rejected.append(f"{label}: block_ids must be strings")
        return None

    missing = [b for b in block_ids if b not in text_by_id]
    if missing:
        rejected.append(f"{label}: cited block(s) not in document: {missing}")
        return None

    if not isinstance(raw_text, str) or not raw_text:
        rejected.append(f"{label}: raw_text is missing or not a string")
        return None

    # Verbatim containment. This one check enforces "no normalized values, no
    # arithmetic, no OCR correction" without special-casing any of them.
    if not any(_appears_verbatim(raw_text, text_by_id[b]) for b in block_ids):
        rejected.append(f"{label}: raw_text {raw_text!r} not present verbatim in cited blocks")
        return None

    return GroundedField(field_name=label, raw_text=raw_text, block_ids=list(block_ids))


def ground_payload(payload: Any, document: m.OCRDocument) -> GroundedExtraction:
    """Ground a parsed LLM payload against ``document``. Never raises."""
    rejected: list[str] = []
    text_by_id = {b.block_id: b.text for b in document.blocks}

    if not isinstance(payload, dict):
        return GroundedExtraction(rejected=["response is not a JSON object"])

    forbidden = _has_forbidden_key(payload)
    if forbidden is not None:
        # Reject the whole response: a model that emits identity/policy/action
        # output is not a model whose field mappings should be trusted.
        return GroundedExtraction(
            rejected=[f"response contains forbidden key {forbidden!r}; whole response rejected"]
        )

    # 1. Document type: must cite a real block; the value must be a known type.
    doc_type = m.DocumentType.UNKNOWN
    doc_type_blocks: tuple[str, ...] = ()
    type_obj = payload.get("document_type")
    if isinstance(type_obj, dict):
        value = type_obj.get("value")
        if isinstance(value, str):
            try:
                doc_type = m.DocumentType(value.strip().upper())
            except ValueError:
                rejected.append(f"document_type {value!r} is not a known document type")
                doc_type = m.DocumentType.UNKNOWN
        else:
            rejected.append("document_type.value is missing or not a string")
        blocks = type_obj.get("block_ids")
        if isinstance(blocks, list) and blocks and all(isinstance(b, str) for b in blocks):
            if all(b in text_by_id for b in blocks):
                doc_type_blocks = list(blocks)
            else:
                rejected.append("document_type cites a block not in the document")
                doc_type = m.DocumentType.UNKNOWN
        else:
            rejected.append("document_type cites no block_ids")
            doc_type = m.DocumentType.UNKNOWN
    else:
        rejected.append("document_type is missing or malformed")

    if doc_type is m.DocumentType.UNKNOWN:
        return GroundedExtraction(
            document_type=m.DocumentType.UNKNOWN,
            document_type_block_ids=(),
            rejected=rejected,
        )

    allowed = FIELD_PROFILES[doc_type]

    # 2. Header fields.
    fields: list[GroundedField] = []
    seen: set[str] = set()
    for entry in _as_list(payload.get("fields")):
        if not isinstance(entry, dict):
            rejected.append("field entry is not an object")
            continue
        name = entry.get("field_name")
        if not isinstance(name, str) or not name:
            rejected.append("field entry has no field_name")
            continue
        if name not in allowed:
            rejected.append(f"{name}: not allowed for {doc_type.value}")
            continue
        if name in seen:
            rejected.append(f"{name}: duplicate mapping")
            continue
        grounded = _ground_citation(
            entry.get("raw_text"), entry.get("block_ids"),
            text_by_id=text_by_id, label=name, rejected=rejected,
        )
        if grounded is not None:
            fields.append(grounded)
            seen.add(name)

    # 3. Line items: every cell must ground, or the row is dropped entirely.
    line_items: list[GroundedLineItem] = []
    for index, raw_item in enumerate(_as_list(payload.get("line_items"))):
        if not isinstance(raw_item, dict):
            rejected.append(f"line_items[{index}]: not an object")
            continue
        values: dict[str, GroundedField] = {}
        for cell_name, cell in raw_item.items():
            if cell_name not in LINE_ITEM_FIELDS:
                rejected.append(f"line_items[{index}].{cell_name}: not an allowed line-item field")
                continue
            if not isinstance(cell, dict):
                rejected.append(f"line_items[{index}].{cell_name}: not an object")
                continue
            grounded = _ground_citation(
                cell.get("raw_text"), cell.get("block_ids"),
                text_by_id=text_by_id,
                label=f"line_items[{index}].{cell_name}",
                rejected=rejected,
            )
            if grounded is not None:
                values[cell_name] = grounded
        if values:
            line_items.append(GroundedLineItem(values=values))
        else:
            rejected.append(f"line_items[{index}]: no cell could be grounded; row dropped")

    return GroundedExtraction(
        document_type=doc_type,
        document_type_block_ids=doc_type_blocks,
        fields=fields,
        line_items=line_items,
        rejected=rejected,
    )

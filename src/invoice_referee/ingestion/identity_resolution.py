"""Resolve internal vendor/item identities for extracted invoice fields.

Internal IDs are never guessed from OCR text. They are resolved only by:
- an exact structured mapping (vendor tax code, supplier SKU), or
- explicit human selection from PO candidates.

OCR supplies the vendor tax code and item descriptions/SKUs; the structured PO
(with ``vendor_tax_code`` and optional ``supplier_sku`` per line) supplies the
internal IDs. An ambiguous or non-matching mapping produces a candidate that
requires human confirmation, never an auto-filled ID.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m


def _human_or_structured_candidate(
    field_name: str, value: Optional[str], method: str
) -> m.FieldCandidate:
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=None,
        normalized_value=value,
        confidence=None,
        status=m.FieldStatus.EXTRACTED if value is not None else m.FieldStatus.MISSING,
        page_number=None,
        bounding_box=None,
        evidence_block_ids=[],
        extraction_method=method,
        warnings=[] if value is not None else ["no exact structured mapping"],
    )


def _needs_confirmation_candidate(field_name: str, reason: str) -> m.FieldCandidate:
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=None,
        normalized_value=None,
        confidence=None,
        status=m.FieldStatus.NEEDS_CONFIRMATION,
        page_number=None,
        bounding_box=None,
        evidence_block_ids=[],
        extraction_method="OCR_RULE",
        warnings=[reason],
    )


def _missing_candidate(field_name: str, reason: str) -> m.FieldCandidate:
    return m.FieldCandidate(
        field_name=field_name,
        raw_text=None,
        normalized_value=None,
        confidence=None,
        status=m.FieldStatus.MISSING,
        page_number=None,
        bounding_box=None,
        evidence_block_ids=[],
        extraction_method="OCR_RULE",
        warnings=[reason],
    )


def resolve_invoice_identities(
    result: m.InvoiceExtractionResult,
    po: m.PurchaseOrder,
) -> m.InvoiceExtractionResult:
    """Resolve ``vendor_id`` and per-line ``item_id`` against the structured PO.

    Vendor: an exact tax-code match yields the PO vendor ID from the vendor
    master; anything else stays unresolved. Items: an exact supplier-SKU match
    resolves automatically; a description-only match requires human selection.
    """
    tax_candidate = result.fields.get("vendor_tax_code")
    tax = tax_candidate.normalized_value if tax_candidate else None

    if tax is not None and po.vendor_tax_code is not None and tax == po.vendor_tax_code:
        result.fields["vendor_id"] = _human_or_structured_candidate(
            "vendor_id", po.vendor_id, "PO_VENDOR_MASTER"
        )
    else:
        result.fields["vendor_id"] = _missing_candidate(
            "vendor_id", "vendor tax code does not exactly match the PO vendor"
        )

    _resolve_line_items(result, po)
    return result


def _sku_index(po: m.PurchaseOrder) -> dict[str, str]:
    index: dict[str, str] = {}
    for line in po.items:
        sku = getattr(line, "supplier_sku", None)
        if sku and line.item_id:
            index[str(sku)] = line.item_id
    return index


def _description_index(po: m.PurchaseOrder) -> dict[str, str]:
    index: dict[str, str] = {}
    for line in po.items:
        if line.description and line.item_id:
            index[line.description.strip().lower()] = line.item_id
    return index


def _resolve_line_items(result: m.InvoiceExtractionResult, po: m.PurchaseOrder) -> None:
    sku_index = _sku_index(po)
    desc_index = _description_index(po)

    for line in result.line_items:
        if "item_id" in line and line["item_id"].normalized_value is not None:
            continue  # already resolved upstream

        sku_candidate = line.get("supplier_sku")
        sku = sku_candidate.normalized_value if sku_candidate else None
        if sku is not None and str(sku) in sku_index:
            line["item_id"] = _human_or_structured_candidate(
                "item_id", sku_index[str(sku)], "PO_SKU_MAP"
            )
            continue

        desc_candidate = line.get("description")
        desc = desc_candidate.normalized_value if desc_candidate else None
        if desc is not None and str(desc).strip().lower() in desc_index:
            # Description match alone is not identity proof: require confirmation.
            candidate = _needs_confirmation_candidate(
                "item_id", "matched a PO item by description only; confirm the PO item"
            )
            candidate.normalized_value = desc_index[str(desc).strip().lower()]
            line["item_id"] = candidate
        else:
            line["item_id"] = _missing_candidate(
                "item_id", "no exact supplier-SKU match to a PO item"
            )

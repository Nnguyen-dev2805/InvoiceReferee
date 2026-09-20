"""Tests for exact vendor/item identity resolution (no fuzzy auto-confirm)."""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.identity_resolution import resolve_invoice_identities


def _field(name, value, status=m.FieldStatus.EXTRACTED):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=["B1"],
    )


def _po(vendor_tax_code="0101234567", vendor_id="V-ABC", items=None):
    return m.PurchaseOrder(
        po_id="PO-001",
        vendor_id=vendor_id,
        vendor_tax_code=vendor_tax_code,
        approved_total=30_000_000,
        status="APPROVED",
        items=items or [],
    )


def _result(fields=None, line_items=None):
    return m.InvoiceExtractionResult(
        document_id="DOC-1",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields or {},
        line_items=line_items or [],
    )


def test_vendor_resolves_on_exact_tax_code_match():
    result = _result(fields={"vendor_tax_code": _field("vendor_tax_code", "0101234567")})
    resolved = resolve_invoice_identities(result, _po())
    vid = resolved.fields["vendor_id"]
    assert vid.normalized_value == "V-ABC"
    assert vid.extraction_method == "PO_VENDOR_MASTER"


def test_vendor_unresolved_on_tax_code_mismatch():
    result = _result(fields={"vendor_tax_code": _field("vendor_tax_code", "9999999999")})
    resolved = resolve_invoice_identities(result, _po())
    vid = resolved.fields["vendor_id"]
    assert vid.normalized_value is None
    assert vid.status is m.FieldStatus.MISSING


def test_vendor_unresolved_when_tax_code_absent():
    resolved = resolve_invoice_identities(_result(), _po())
    assert resolved.fields["vendor_id"].normalized_value is None


def test_item_resolves_on_exact_supplier_sku():
    po = _po(
        items=[
            m.POLineItem(
                item_id="ITEM-001",
                ordered_quantity=10,
                unit_price=3_000_000,
                line_total=30_000_000,
                description="Dell Monitor",
                supplier_sku="SKU-DELL",
            )
        ]
    )
    line = {"supplier_sku": _field("supplier_sku", "SKU-DELL")}
    resolved = resolve_invoice_identities(_result(line_items=[line]), po)
    item = resolved.line_items[0]["item_id"]
    assert item.normalized_value == "ITEM-001"
    assert item.extraction_method == "PO_SKU_MAP"


def test_item_description_only_match_requires_confirmation():
    po = _po(
        items=[
            m.POLineItem(
                item_id="ITEM-001",
                ordered_quantity=10,
                unit_price=3_000_000,
                line_total=30_000_000,
                description="Dell Monitor",
            )
        ]
    )
    line = {"description": _field("description", "dell monitor")}
    resolved = resolve_invoice_identities(_result(line_items=[line]), po)
    item = resolved.line_items[0]["item_id"]
    assert item.status is m.FieldStatus.NEEDS_CONFIRMATION
    assert item.normalized_value == "ITEM-001"  # proposed, not confirmed


def test_item_unresolved_when_no_match():
    po = _po(items=[m.POLineItem("ITEM-001", 10, 3_000_000, 30_000_000, description="Monitor")])
    line = {"description": _field("description", "Completely Different Thing")}
    resolved = resolve_invoice_identities(_result(line_items=[line]), po)
    assert resolved.line_items[0]["item_id"].status is m.FieldStatus.MISSING

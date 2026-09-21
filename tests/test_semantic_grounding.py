"""Grounding verifier: the LLM may only cite OCR blocks that exist and match.

These are pure-function tests — no LLM, no OCR. Every rejection rule in the
LLM-first design is pinned here, because grounding is the only thing standing
between an untrusted model response and the deterministic pipeline.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.grounding import (
    FORBIDDEN_KEYS,
    FIELD_PROFILES,
    ground_payload,
)


# --- helpers ------------------------------------------------------------------


def _block(block_id, text, *, page=1, conf=0.99, block_type="TEXT", row=None, col=None):
    return m.OCRBlock(
        block_id=block_id,
        page_number=page,
        text=text,
        confidence=conf,
        bounding_box=m.BoundingBox(0.1, 0.1, 0.5, 0.2),
        block_type=block_type,
        row_index=row,
        column_index=col,
    )


def _doc(blocks):
    return m.OCRDocument(
        document_id="DOC-1",
        pages=[],
        blocks=blocks,
        full_text="\n".join(b.text for b in blocks),
        engine="recorded",
        engine_version="v1",
        processing_ms=0,
    )


INVOICE_BLOCKS = [
    _block("BLK-TYPE", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG"),
    _block("BLK-SERIES", "Ký hiệu: 2C23TTU"),
    _block("BLK-NUMBER", "Số hóa đơn: 0000123"),
    _block("BLK-VENDOR-TAX", "Mã số thuế: 0110329220"),
    _block("BLK-DATE", "Ngày 11 tháng 07 năm 2023"),
    _block("BLK-TOTAL", "Tổng cộng: 9.000.000"),
]


def _invoice_payload(**overrides):
    payload = {
        "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["BLK-TYPE"]},
        "fields": [
            {"field_name": "invoice_number", "raw_text": "0000123", "block_ids": ["BLK-NUMBER"]},
            {"field_name": "invoice_series", "raw_text": "2C23TTU", "block_ids": ["BLK-SERIES"]},
            {"field_name": "vendor_tax_code", "raw_text": "0110329220", "block_ids": ["BLK-VENDOR-TAX"]},
            {"field_name": "invoice_date", "raw_text": "Ngày 11 tháng 07 năm 2023", "block_ids": ["BLK-DATE"]},
            {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["BLK-TOTAL"]},
        ],
        "line_items": [],
    }
    payload.update(overrides)
    return payload


# --- profiles -----------------------------------------------------------------


def test_invoice_and_receipt_profiles_do_not_share_party_fields():
    """A receipt has no tax codes; an invoice has no cashier/table."""
    assert "vendor_tax_code" in FIELD_PROFILES[m.DocumentType.SUPPLIER_INVOICE]
    assert "vendor_tax_code" not in FIELD_PROFILES[m.DocumentType.TEMPORARY_BILL]
    assert "receipt_number" in FIELD_PROFILES[m.DocumentType.TEMPORARY_BILL]
    assert "receipt_number" not in FIELD_PROFILES[m.DocumentType.SUPPLIER_INVOICE]
    # UNKNOWN accepts nothing, so nothing can be claimed without a known type.
    assert FIELD_PROFILES[m.DocumentType.UNKNOWN] == frozenset()


def test_forbidden_keys_cover_identity_policy_and_action():
    for key in ("vendor_id", "item_id", "policy_rule_ids", "action",
                "proposed_action", "decision", "approved_total"):
        assert key in FORBIDDEN_KEYS


def test_invoice_profile_covers_every_critical_field_the_human_must_confirm():
    """A critical field missing from the profile can never be extracted at all.

    ``po_id`` is printed on a real invoice and a human must confirm it, so the
    model must be allowed to read it. Omitting a critical field from the profile
    does not make it safer — it makes every invoice permanently incomplete, and
    the failure is silent because the field is simply never proposed.
    """
    from invoice_referee.ingestion.extraction_validation import CRITICAL_FIELDS

    profile = FIELD_PROFILES[m.DocumentType.SUPPLIER_INVOICE]
    # ``vendor_id`` is the one exception: it is an internal identity resolved by
    # exact tax-code match downstream, and must never come from the model.
    assert CRITICAL_FIELDS - profile == {"vendor_id"}


# --- happy path ---------------------------------------------------------------


def test_grounded_invoice_payload_is_accepted():
    grounded = ground_payload(_invoice_payload(), _doc(INVOICE_BLOCKS))
    assert grounded.document_type is m.DocumentType.SUPPLIER_INVOICE
    assert grounded.document_type_block_ids == ["BLK-TYPE"]
    assert {f.field_name for f in grounded.fields} == {
        "invoice_number", "invoice_series", "vendor_tax_code",
        "invoice_date", "total_amount",
    }
    assert grounded.rejected == []


def test_grounded_field_keeps_raw_text_and_citations():
    grounded = ground_payload(_invoice_payload(), _doc(INVOICE_BLOCKS))
    total = next(f for f in grounded.fields if f.field_name == "total_amount")
    assert total.raw_text == "9.000.000"
    assert total.block_ids == ["BLK-TOTAL"]


# --- rejection rules ----------------------------------------------------------


def test_rejects_citation_to_a_block_that_does_not_exist():
    payload = _invoice_payload(fields=[
        {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["GHOST"]},
    ])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []
    assert any("GHOST" in r for r in grounded.rejected)


def test_rejects_raw_text_not_present_in_the_cited_block():
    """The model may not supply a value that the cited block does not contain."""
    payload = _invoice_payload(fields=[
        {"field_name": "invoice_number", "raw_text": "9999999", "block_ids": ["BLK-NUMBER"]},
    ])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []
    assert any("9999999" in r for r in grounded.rejected)


def test_rejects_a_normalized_value_instead_of_the_raw_ocr_text():
    """`9.000.000` is the OCR text; `9000000` is a computed value and is rejected."""
    payload = _invoice_payload(fields=[
        {"field_name": "total_amount", "raw_text": "9000000", "block_ids": ["BLK-TOTAL"]},
    ])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []


def test_rejects_a_field_outside_the_document_type_allow_list():
    """A receipt field claimed on a supplier invoice is not coerced, it is dropped."""
    payload = _invoice_payload(fields=[
        {"field_name": "cashier_name", "raw_text": "0000123", "block_ids": ["BLK-NUMBER"]},
    ])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []
    assert any("cashier_name" in r for r in grounded.rejected)


def test_rejects_a_line_item_that_cites_no_real_block():
    """A fabricated line item cannot be grounded, so it is not emitted."""
    payload = _invoice_payload(line_items=[{
        "description": {"raw_text": "Khóa học kế toán", "block_ids": ["BLK-NOPE"]},
        "quantity": {"raw_text": "2", "block_ids": ["BLK-NOPE"]},
    }])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.line_items == []


def test_rejects_the_whole_response_when_it_returns_policy_or_action():
    """A model that emits policy output is not trusted for anything else either."""
    payload = _invoice_payload(proposed_action="AUTO_PROCESS")
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []
    assert grounded.line_items == []
    assert grounded.document_type is m.DocumentType.UNKNOWN
    assert any("proposed_action" in r for r in grounded.rejected)


def test_rejects_the_whole_response_when_it_invents_an_identity():
    payload = _invoice_payload(fields=[
        {"field_name": "vendor_id", "raw_text": "V-ABC", "block_ids": ["BLK-VENDOR-TAX"]},
    ])
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.fields == []
    assert any("vendor_id" in r for r in grounded.rejected)


# --- document type ------------------------------------------------------------


def test_unknown_document_type_accepts_no_fields():
    payload = _invoice_payload(document_type={"value": "UNKNOWN", "block_ids": ["BLK-TYPE"]})
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.document_type is m.DocumentType.UNKNOWN
    assert grounded.fields == []


def test_unrecognized_document_type_value_falls_back_to_unknown():
    payload = _invoice_payload(document_type={"value": "PIZZA_RECEIPT", "block_ids": ["BLK-TYPE"]})
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.document_type is m.DocumentType.UNKNOWN
    assert grounded.fields == []


def test_document_type_citation_must_also_exist():
    payload = _invoice_payload(document_type={"value": "SUPPLIER_INVOICE", "block_ids": ["GHOST"]})
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.document_type is m.DocumentType.UNKNOWN


def test_ocr_corrupted_receipt_label_still_classifies():
    """The real receipt reads `PHIẾU TẠM TĨNH`; the classifier must still see a bill."""
    from invoice_referee.ingestion.grounding import classify_document_type

    assert classify_document_type("PHIẾU TẠM TĨNH") is m.DocumentType.TEMPORARY_BILL
    assert classify_document_type("PHIẾU TẠM TÍNH") is m.DocumentType.TEMPORARY_BILL
    assert classify_document_type("PHIEU TINH TIEN") is m.DocumentType.POS_RECEIPT
    assert classify_document_type("HÓA ĐƠN GIÁ TRỊ GIA TĂNG") is m.DocumentType.SUPPLIER_INVOICE


# --- malformed input ----------------------------------------------------------


@pytest.mark.parametrize("payload", [
    None,
    "not a dict",
    {},
    {"fields": "not a list"},
    {"document_type": "SUPPLIER_INVOICE"},
])
def test_malformed_payload_grounds_to_nothing_without_raising(payload):
    grounded = ground_payload(payload, _doc(INVOICE_BLOCKS))
    assert grounded.document_type is m.DocumentType.UNKNOWN
    assert grounded.fields == []
    assert grounded.line_items == []

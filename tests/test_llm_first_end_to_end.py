"""End-to-end: LLM-first extraction -> human review -> the existing review() path.

This closes the loop the design promises. A supplier invoice extracted by the LLM
must reach the *unchanged* production business pipeline and be decided by the
deterministic Decision Guard; a receipt must never get there. The JSON review path
and the deterministic policy suites are untouched by any of it.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

import pymupdf  # noqa: E402

from invoice_referee.agent.llm_client import LLMClient  # noqa: E402
from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.ingestion.pipeline import (  # noqa: E402
    FieldReview,
    apply_field_reviews,
    reviewed_extraction_to_evidence,
)
from invoice_referee.services.extractor import extract_invoice  # noqa: E402
from invoice_referee.services.reviewer import review  # noqa: E402


def _pdf_bytes() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Invoice")
    data = doc.tobytes()
    doc.close()
    return data


BLOCKS = [
    ("B1", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG", "TEXT"),
    ("B2", "Ký hiệu: 2C23TTU", "KEY_VALUE"),
    ("B3", "Số hóa đơn: 0000123", "KEY_VALUE"),
    ("B4", "Mã số thuế: 0110329220", "KEY_VALUE"),
    ("B5", "Ngày 11 tháng 07 năm 2023", "KEY_VALUE"),
    ("B6", "Tổng cộng: 9.000.000", "KEY_VALUE"),
    # Real supplier invoices print the buyer's PO reference; every recorded OCR
    # fixture does, and `po_id` is a critical field a human must confirm.
    ("B7", "Số PO: PO-001", "KEY_VALUE"),
    ("R1C0", "Khóa học kế toán", "TABLE_CELL"),
    ("R1C1", "2", "TABLE_CELL"),
    ("R1C2", "3.500.000", "TABLE_CELL"),
    ("R1C3", "7.000.000", "TABLE_CELL"),
]


class BlockEngine:
    def analyze(self, pages):
        blocks = [
            m.OCRBlock(
                block_id=bid, page_number=1, text=text, confidence=0.99,
                bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2), block_type=btype,
            )
            for bid, text, btype in BLOCKS
        ]
        return m.OCRDocument(
            document_id=pages[0].document_id, pages=pages, blocks=blocks,
            full_text="\n".join(b.text for b in blocks),
            engine="recorded", engine_version="v1", processing_ms=0,
        )


class FakeClient(LLMClient):
    def __init__(self, body):
        self.body = body

    def complete(self, prompt: str) -> str:
        return self.body


INVOICE_RESPONSE = json.dumps({
    "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
    "fields": [
        {"field_name": "invoice_series", "raw_text": "2C23TTU", "block_ids": ["B2"]},
        {"field_name": "invoice_number", "raw_text": "0000123", "block_ids": ["B3"]},
        {"field_name": "vendor_tax_code", "raw_text": "0110329220", "block_ids": ["B4"]},
        {"field_name": "invoice_date", "raw_text": "Ngày 11 tháng 07 năm 2023", "block_ids": ["B5"]},
        {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["B6"]},
        {"field_name": "po_id", "raw_text": "PO-001", "block_ids": ["B7"]},
    ],
    "line_items": [{
        "description": {"raw_text": "Khóa học kế toán", "block_ids": ["R1C0"]},
        "quantity": {"raw_text": "2", "block_ids": ["R1C1"]},
        "unit_price": {"raw_text": "3.500.000", "block_ids": ["R1C2"]},
        "line_total": {"raw_text": "7.000.000", "block_ids": ["R1C3"]},
    }],
})


def _po():
    return m.PurchaseOrder(
        po_id="PO-001", vendor_id="V-ABC", vendor_tax_code="0110329220",
        approved_total=9_000_000, status="APPROVED",
        items=[m.POLineItem("ITEM-001", 2, 3_500_000, 7_000_000, description="Khóa học kế toán")],
    )


def _base_evidence():
    """Structured evidence. The PO link is supplied here, not read from the image.

    The invoice document prints no PO reference, and it should not have to: the
    PO is structured JSON on both paths. Only the invoice's own facts come from
    extraction, which is what makes the two paths comparable.
    """
    return {
        "transaction_id": "TX-E2E",
        "transaction_type": "PO_GOODS_PURCHASE",
        # The PO reference is structured input; no document prints it.
        "invoice": {"po_id": "PO-001"},
        "purchase_order": {
            "po_id": "PO-001", "vendor_id": "V-ABC", "vendor_tax_code": "0110329220",
            "approved_total": 9_000_000, "status": "APPROVED",
            "items": [{
                "item_id": "ITEM-001", "ordered_quantity": 2,
                "unit_price": 3_500_000, "line_total": 7_000_000,
                "description": "Khóa học kế toán",
            }],
        },
        "goods_receipts": [{
            "receipt_id": "GR-001", "po_id": "PO-001",
            "received_date": "2026-09-12", "status": "RECEIVED",
            "items": [{"item_id": "ITEM-001", "received_quantity": 2}],
        }],
        "payment_history": [{"invoice_id": "INV-E2E", "status": "UNPAID", "paid_amount": 0}],
    }


def _extract():
    return extract_invoice(
        transaction_id="TX-E2E",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=BlockEngine(),
        actor="judge@demo",
        llm_client=FakeClient(INVOICE_RESPONSE),
    )


# --- invoice reaches review() -------------------------------------------------


def test_llm_extracted_invoice_reaches_the_unchanged_review_path():
    """The LLM path feeds the real production pipeline; the Guard still decides."""
    result, audit = _extract()
    assert result.document_type is m.DocumentType.SUPPLIER_INVOICE

    # A human confirms every critical field (invariant 19).
    reviews = {name: FieldReview.confirm() for name in result.fields}
    for index, line in enumerate(result.line_items):
        for name in line:
            reviews[f"line_items[{index}].{name}"] = FieldReview.confirm()
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")

    evidence = reviewed_extraction_to_evidence(reviewed, _base_evidence())
    assert evidence["document_type"] == "SUPPLIER_INVOICE"

    # The invoice id is generated from the document, so payment history must be
    # re-pointed at it — exactly as the OCR evaluation harness does.
    for record in evidence.get("payment_history", []):
        record["invoice_id"] = evidence["invoice"]["invoice_id"]

    review_result = review(evidence, audit=audit)
    # The decision comes from resolve_action, not from the extractor.
    assert review_result.decision.action in (
        m.DecisionAction.AUTO_PROCESS,
        m.DecisionAction.REQUEST_INFO,
        m.DecisionAction.ESCALATE,
    )
    assert review_result.transaction.invoice.total_amount == 9_000_000
    assert review_result.transaction.invoice.vendor_id == "V-ABC"


def test_llm_path_decision_is_the_same_as_the_equivalent_json_input():
    """Extraction source must not change the decision for identical facts.

    The same facts entering as structured JSON and as an LLM-extracted invoice
    must produce the same action, because the Guard reads facts, not provenance.
    """
    result, audit = _extract()
    reviews = {name: FieldReview.confirm() for name in result.fields}
    for index, line in enumerate(result.line_items):
        for name in line:
            reviews[f"line_items[{index}].{name}"] = FieldReview.confirm()
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    ocr_evidence = reviewed_extraction_to_evidence(reviewed, _base_evidence())
    for record in ocr_evidence.get("payment_history", []):
        record["invoice_id"] = ocr_evidence["invoice"]["invoice_id"]

    json_evidence = _base_evidence()
    json_evidence["invoice"] = {
        "invoice_id": "INV-E2E", "invoice_number": "0000123", "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL", "vendor_id": "V-ABC", "vendor_tax_code": "0110329220",
        "po_id": "PO-001", "invoice_date": "2023-07-11", "total_amount": 9_000_000,
        "items": [{
            "item_id": "ITEM-001", "invoiced_quantity": 2,
            "unit_price": 3_500_000, "line_total": 7_000_000,
            "description": "Khóa học kế toán",
        }],
    }

    from_ocr = review(ocr_evidence)
    from_json = review(json_evidence)
    assert from_ocr.decision.action is from_json.decision.action


def test_llm_extracted_receipt_cannot_reach_review():
    """A receipt is refused routing, so the PO-based pipeline never sees it."""
    receipt_response = json.dumps({
        "document_type": {"value": "TEMPORARY_BILL", "block_ids": ["B1"]},
        "fields": [
            {"field_name": "receipt_number", "raw_text": "0000123", "block_ids": ["B3"]},
            {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["B6"]},
        ],
        "line_items": [],
    })
    result, _ = extract_invoice(
        transaction_id="TX-E2E", filename="receipt.pdf", claimed_mime="application/pdf",
        content=_pdf_bytes(), po=_po(), engine=BlockEngine(), actor="judge@demo",
        llm_client=FakeClient(receipt_response),
    )
    assert result.document_type is m.DocumentType.TEMPORARY_BILL

    reviews = {name: FieldReview.confirm() for name in result.fields}
    reviewed = apply_field_reviews(result, reviews, actor="ap@x")
    with pytest.raises(m.UnsupportedDocumentTypeError):
        reviewed_extraction_to_evidence(reviewed, _base_evidence())


# --- the JSON path is untouched -----------------------------------------------


def test_structured_json_review_path_is_unaffected():
    """The required Sprint 1 ingestion path still works with no LLM and no OCR."""
    evidence = _base_evidence()
    evidence["invoice"] = {
        "invoice_id": "INV-E2E", "invoice_number": "0000123", "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL", "vendor_id": "V-ABC", "vendor_tax_code": "0110329220",
        "po_id": "PO-001", "invoice_date": "2023-07-11", "total_amount": 9_000_000,
        "items": [{
            "item_id": "ITEM-001", "invoiced_quantity": 2,
            "unit_price": 3_500_000, "line_total": 7_000_000,
            "description": "Khóa học kế toán",
        }],
    }
    result = review(evidence)  # no client: deterministic fallback
    assert result.agent_assessment.fallback_used is True
    assert result.decision.action is m.DecisionAction.AUTO_PROCESS

"""Tests for the OCR extraction orchestration service (fake engine, no model)."""

from __future__ import annotations

import io
import json

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

import pymupdf  # noqa: E402

from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.services.extractor import extract_invoice, ExtractionError  # noqa: E402
from invoice_referee.ingestion.file_validation import DocumentInputError  # noqa: E402
from invoice_referee.agent.llm_client import LLMClient  # noqa: E402


def _pdf_bytes(text: str = "Invoice") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _po():
    return m.PurchaseOrder(
        po_id="PO-001",
        vendor_id="V-ABC",
        vendor_tax_code="0101234567",
        approved_total=30_000_000,
        status="APPROVED",
        items=[m.POLineItem("ITEM-001", 10, 3_000_000, 30_000_000, description="Dell Monitor")],
    )


class FakeEngine:
    """Returns a fixed OCRDocument regardless of the rendered pages."""

    def analyze(self, pages: list[m.DocumentPage]) -> m.OCRDocument:
        def block(bid, text):
            return m.OCRBlock(bid, 1, text, 0.96, m.BoundingBox(0.1, 0.1, 0.9, 0.2), "TEXT")

        blocks = [
            block("B1", "Ký hiệu: 2C23TTU"),
            block("B2", "Số hóa đơn: 0000123"),
            block("B3", "Mã số thuế: 0101234567"),
            block("B4", "Tổng cộng: 30.000.000 VND"),
        ]
        return m.OCRDocument(
            document_id=pages[0].document_id,
            pages=pages,
            blocks=blocks,
            full_text="\n".join(b.text for b in blocks),
            engine="fake",
            engine_version="v1",
            processing_ms=0,
        )


class FailingEngine:
    def analyze(self, pages):
        raise RuntimeError("model unavailable")


class CountingLLMClient(LLMClient):
    """Replays a grounded semantic response and counts the calls."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return json.dumps({
            "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
            "fields": [
                {"field_name": "invoice_series", "raw_text": "2C23TTU", "block_ids": ["B1"]},
                {"field_name": "invoice_number", "raw_text": "0000123", "block_ids": ["B2"]},
                {"field_name": "vendor_tax_code", "raw_text": "0101234567", "block_ids": ["B3"]},
                {"field_name": "total_amount", "raw_text": "30.000.000", "block_ids": ["B4"]},
            ],
            "line_items": [],
        })



def test_extract_invoice_runs_every_stage():
    result, audit = extract_invoice(
        transaction_id="TX-001",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=FakeEngine(),
        actor="judge@demo",
        llm_client=CountingLLMClient(),
    )
    assert result.status is m.ExtractionStatus.NEEDS_REVIEW
    assert result.fields["total_amount"].normalized_value == 30_000_000
    assert result.fields["vendor_id"].normalized_value == "V-ABC"  # resolved by tax code
    types = [e.event_type for e in audit.events][:3]
    assert types == ["DOCUMENT_UPLOADED", "DOCUMENT_VALIDATED", "OCR_COMPLETED"]
    assert any(e.event_type == "FIELD_EXTRACTED" for e in audit.events)


def test_extract_invoice_shares_transaction_id_on_audit():
    _, audit = extract_invoice(
        transaction_id="TX-XYZ",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=FakeEngine(),
        actor="judge@demo",
        llm_client=CountingLLMClient(),
    )
    assert audit.transaction_id == "TX-XYZ"


def test_bad_upload_raises_document_input_error():
    with pytest.raises(DocumentInputError):
        extract_invoice(
            transaction_id="TX-001",
            filename="invoice.pdf",
            claimed_mime="application/pdf",
            content=b"not a pdf",
            po=_po(),
            engine=FakeEngine(),
            actor="judge@demo",
        )


def test_engine_failure_raises_extraction_error_not_business_decision():
    with pytest.raises(ExtractionError):
        extract_invoice(
            transaction_id="TX-001",
            filename="invoice.pdf",
            claimed_mime="application/pdf",
            content=_pdf_bytes(),
            po=_po(),
            engine=FailingEngine(),
            actor="judge@demo",
        )


def test_extractor_calls_the_semantic_client_exactly_once():
    client = CountingLLMClient()
    result, _ = extract_invoice(
        transaction_id="TX-001",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=FakeEngine(),
        actor="judge@demo",
        llm_client=client,
    )
    assert client.calls == 1
    assert result.document_type is m.DocumentType.SUPPLIER_INVOICE
    assert result.fields["vendor_id"].normalized_value == "V-ABC"


def test_without_a_client_extraction_fails_closed():
    """No client means no fields and human review, never a silent substitution."""
    result, _ = extract_invoice(
        transaction_id="TX-001",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=FakeEngine(),
        actor="judge@demo",
    )
    assert result.document_type is m.DocumentType.UNKNOWN
    assert result.status is m.ExtractionStatus.NEEDS_REVIEW
    assert not any(
        c.extraction_method == "LLM_ASSISTED" for c in result.fields.values()
    )

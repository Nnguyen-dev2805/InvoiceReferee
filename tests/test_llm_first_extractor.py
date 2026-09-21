"""The production extractor is LLM-first and only.

There is no label/layout/fuzzy mapper to fall back to. These tests pin what
replaced it: the semantic extractor runs, grounding constrains it, deterministic
identity resolution still applies, and a missing client fails closed instead of
quietly switching to a different extractor.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

import pymupdf  # noqa: E402

from invoice_referee.agent.llm_client import LLMClient  # noqa: E402
from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.services.extractor import extract_invoice  # noqa: E402


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
        vendor_tax_code="0110329220",
        approved_total=9_000_000,
        status="APPROVED",
        items=[m.POLineItem("ITEM-001", 2, 3_500_000, 7_000_000, description="Khóa học")],
    )


INVOICE_BLOCKS = [
    ("B1", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG", "TEXT"),
    ("B2", "Ký hiệu: 2C23TTU", "KEY_VALUE"),
    ("B3", "Số hóa đơn: 0000123", "KEY_VALUE"),
    ("B4", "Mã số thuế: 0110329220", "KEY_VALUE"),
    ("B5", "Ngày 11 tháng 07 năm 2023", "KEY_VALUE"),
    ("B6", "Tổng cộng: 9.000.000", "KEY_VALUE"),
]


class BlockEngine:
    """An OCREngine returning a fixed recorded block set."""

    def analyze(self, pages):
        blocks = [
            m.OCRBlock(
                block_id=bid, page_number=1, text=text, confidence=0.99,
                bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2), block_type=btype,
            )
            for bid, text, btype in INVOICE_BLOCKS
        ]
        return m.OCRDocument(
            document_id=pages[0].document_id, pages=pages, blocks=blocks,
            full_text="\n".join(b.text for b in blocks),
            engine="recorded", engine_version="v1", processing_ms=0,
        )


SEMANTIC_RESPONSE = json.dumps({
    "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
    "fields": [
        {"field_name": "invoice_series", "raw_text": "2C23TTU", "block_ids": ["B2"]},
        {"field_name": "invoice_number", "raw_text": "0000123", "block_ids": ["B3"]},
        {"field_name": "vendor_tax_code", "raw_text": "0110329220", "block_ids": ["B4"]},
        {"field_name": "invoice_date", "raw_text": "Ngày 11 tháng 07 năm 2023", "block_ids": ["B5"]},
        {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["B6"]},
    ],
    "line_items": [],
})


class CountingClient(LLMClient):
    def __init__(self, body=SEMANTIC_RESPONSE):
        self.body = body
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        return self.body


def _extract(**kwargs):
    return extract_invoice(
        transaction_id="TX-001",
        filename="invoice.pdf",
        claimed_mime="application/pdf",
        content=_pdf_bytes(),
        po=_po(),
        engine=BlockEngine(),
        actor="judge@demo",
        **kwargs,
    )


# --- the semantic extractor is the production path ---------------------------


def test_semantic_extractor_runs_and_sets_the_document_type():
    client = CountingClient()
    result, _ = _extract(llm_client=client)
    assert client.calls == 1
    assert result.document_type is m.DocumentType.SUPPLIER_INVOICE
    assert result.fields["invoice_number"].normalized_value == "0000123"
    assert result.fields["vendor_tax_code"].normalized_value == "0110329220"
    assert result.fields["total_amount"].normalized_value == 9_000_000


def test_no_field_from_the_model_is_auto_accepted():
    """Invariant 19: a human confirms every critical field, LLM or not."""
    result, _ = _extract(llm_client=CountingClient())
    model_sourced = [
        c for c in result.fields.values() if c.extraction_method == "LLM_ASSISTED"
    ]
    assert model_sourced
    for candidate in model_sourced:
        assert candidate.status is m.FieldStatus.NEEDS_CONFIRMATION


def test_prompt_offers_the_blocks_and_the_allowed_fields():
    client = CountingClient()
    _extract(llm_client=client)
    prompt = client.prompts[0]
    assert "B3" in prompt
    assert "Số hóa đơn: 0000123" in prompt
    assert "invoice_number" in prompt


# --- fail closed --------------------------------------------------------------


def test_missing_client_fails_closed_instead_of_switching_extractors():
    """No client is a configuration error, not a reason to use another extractor.

    Extraction yields no fields, the document type stays UNKNOWN, and the result
    goes to human review — rather than a different mapper silently filling in
    values the caller did not ask for.
    """
    result, _ = _extract(llm_client=None)
    assert result.document_type is m.DocumentType.UNKNOWN
    assert not any(
        c.extraction_method == "LLM_ASSISTED" for c in result.fields.values()
    )
    assert result.status is m.ExtractionStatus.NEEDS_REVIEW


def test_ungrounded_response_leaves_the_field_unknown():
    client = CountingClient(body=json.dumps({
        "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
        "fields": [{"field_name": "total_amount", "raw_text": "999", "block_ids": ["B6"]}],
        "line_items": [],
    }))
    result, _ = _extract(llm_client=client)
    assert result.document_type is m.DocumentType.SUPPLIER_INVOICE
    assert "total_amount" not in result.fields
    assert result.status is m.ExtractionStatus.NEEDS_REVIEW


# --- deterministic stages still apply ----------------------------------------


def test_identity_resolution_binds_vendor_id_by_exact_tax_code():
    """The model never supplies vendor_id; identity resolution does."""
    result, _ = _extract(llm_client=CountingClient())
    assert result.fields["vendor_id"].normalized_value == "V-ABC"
    assert result.fields["vendor_id"].extraction_method == "PO_VENDOR_MASTER"


def test_grounding_rejections_are_recorded_in_warnings():
    client = CountingClient(body=json.dumps({
        "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
        "fields": [
            {"field_name": "vendor_id", "raw_text": "V-ABC", "block_ids": ["B4"]},
        ],
        "line_items": [],
    }))
    result, _ = _extract(llm_client=client)
    assert any("vendor_id" in w for w in result.warnings)
    assert result.fields["vendor_id"].normalized_value is None


def test_a_top_level_action_rejects_the_whole_response():
    """A model answering as a decision maker is not trusted for anything."""
    client = CountingClient(body=json.dumps({
        "document_type": {"value": "SUPPLIER_INVOICE", "block_ids": ["B1"]},
        "fields": [
            {"field_name": "total_amount", "raw_text": "9.000.000", "block_ids": ["B6"]},
        ],
        "proposed_action": "AUTO_PROCESS",
    }))
    result, _ = _extract(llm_client=client)
    assert result.document_type is m.DocumentType.UNKNOWN
    assert any("forbidden key" in w for w in result.warnings)
    assert not any(
        c.extraction_method == "LLM_ASSISTED" for c in result.fields.values()
    )


def test_engine_failure_raises_extraction_error_not_a_decision():
    from invoice_referee.services.extractor import ExtractionError

    class FailingEngine:
        def analyze(self, pages):
            raise RuntimeError("model unavailable")

    with pytest.raises(ExtractionError):
        extract_invoice(
            transaction_id="TX-001", filename="invoice.pdf",
            claimed_mime="application/pdf", content=_pdf_bytes(), po=_po(),
            engine=FailingEngine(), actor="judge@demo", llm_client=CountingClient(),
        )

"""Tests for the Mistral OCR adapter (recorded markdown, no live key)."""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.ocr import (
    MistralOCREngine,
    MISTRAL_ENGINE_NAME,
    markdown_to_blocks,
)
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields


SAMPLE_MARKDOWN = """HOA DON GIA TRI GIA TANG
Ký hiệu: 2C23TTU
Số hóa đơn: 0000123
Mã số thuế: 0101234567
Số PO: PO-001
Ngày hóa đơn: 2026-09-13

| Mô tả | Số lượng | Đơn giá | Thành tiền |
| --- | --- | --- | --- |
| Dell Monitor | 10 | 3.000.000 | 30.000.000 |

Tổng cộng: 30.000.000 VND
"""


def _page():
    return m.DocumentPage("DOC-1", 1, b"\x89PNG", 1000, 1400, 300, None)


def test_markdown_to_blocks_splits_headers_and_table():
    blocks = markdown_to_blocks(SAMPLE_MARKDOWN, 1)
    kinds = {b["block_type"] for b in blocks}
    assert "TABLE_CELL" in kinds
    assert "KEY_VALUE" in kinds
    # Header row present at row 0, one data row at row 1.
    table_rows = {b["row_index"] for b in blocks if b["block_type"] == "TABLE_CELL"}
    assert table_rows == {0, 1}
    # Every block has an id.
    assert all(b["block_id"] for b in blocks)


def test_engine_returns_provider_neutral_ocrdocument():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_MARKDOWN)
    doc = engine.analyze([_page()])
    assert isinstance(doc, m.OCRDocument)
    assert doc.engine == MISTRAL_ENGINE_NAME
    assert doc.document_id == "DOC-1"
    assert any(b.block_type == "TABLE_CELL" for b in doc.blocks)


def test_mistral_markdown_confidence_is_zero_so_fields_need_confirmation():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_MARKDOWN)
    doc = engine.analyze([_page()])
    assert all(b.confidence == 0.0 for b in doc.blocks)


# --- OCR-4+ blocks path (real bbox + block confidence) -----------------------

# Mirrors the real Mistral OCR page schema: flat top_left_*/bottom_right_*
# pixel coords, ``content`` text, and nested ``confidence_scores``.
SAMPLE_PAGE_RESULT = {
    "markdown": "ignored when blocks present",
    "dimensions": {"width": 1000, "height": 1400, "dpi": 200},
    "blocks": [
        {
            "type": "text",
            "content": "Số hóa đơn: 0000123",
            "confidence_scores": {"average_content_confidence_score": 0.98},
            "top_left_x": 80, "top_left_y": 100, "bottom_right_x": 620, "bottom_right_y": 140,
        },
        {
            "type": "text",
            "content": "Mã số thuế: 0101234567",
            "confidence_scores": {"average_content_confidence_score": 0.95},
            "top_left_x": 80, "top_left_y": 160, "bottom_right_x": 620, "bottom_right_y": 200,
        },
        {
            "type": "table",
            "content": "| Mô tả | Số lượng | Đơn giá | Thành tiền |\n| --- | --- | --- | --- |\n| Dell Monitor | 10 | 3.000.000 | 30.000.000 |",
            "confidence_scores": {"average_content_confidence_score": 0.93},
            "top_left_x": 60, "top_left_y": 400, "bottom_right_x": 940, "bottom_right_y": 520,
        },
        {
            "type": "text",
            "content": "Tổng cộng: 30.000.000 VND",
            "confidence_scores": {"average_content_confidence_score": 0.99},
            "top_left_x": 80, "top_left_y": 560, "bottom_right_x": 620, "bottom_right_y": 600,
        },
    ],
}


def test_ocr4_blocks_carry_real_confidence_and_bbox():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_PAGE_RESULT)
    doc = engine.analyze([_page()])
    num = next(b for b in doc.blocks if "0000123" in b.text)
    assert num.confidence == pytest.approx(0.98)
    # Normalized against Mistral's reported page dimensions (1000x1400).
    assert num.bounding_box.x1 == pytest.approx(0.08)
    assert num.bounding_box.x2 == pytest.approx(0.62)
    assert num.bounding_box.y1 == pytest.approx(100 / 1400)


def test_ocr4_table_block_expands_into_cells():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_PAGE_RESULT)
    doc = engine.analyze([_page()])
    cells = [b for b in doc.blocks if b.block_type == "TABLE_CELL"]
    assert cells
    assert {b.row_index for b in cells} == {0, 1}
    # Cells inherit the table's confidence.
    assert all(b.confidence == pytest.approx(0.93) for b in cells)


def test_ocr4_fields_extract_with_confidence():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_PAGE_RESULT)
    doc = engine.analyze([_page()])
    result = extract_invoice_fields(doc)
    assert result.fields["invoice_number"].normalized_value == "0000123"
    assert result.fields["invoice_number"].confidence == pytest.approx(0.98)
    assert result.fields["total_amount"].normalized_value == 30_000_000
    assert result.line_items[0]["unit_price"].normalized_value == 3_000_000


def test_extracted_fields_flow_from_mistral_markdown():
    engine = MistralOCREngine(transcribe=lambda page: SAMPLE_MARKDOWN)
    doc = engine.analyze([_page()])
    result = extract_invoice_fields(doc)
    assert result.fields["invoice_number"].normalized_value == "0000123"
    assert result.fields["vendor_tax_code"].normalized_value == "0101234567"
    assert result.fields["total_amount"].normalized_value == 30_000_000
    assert len(result.line_items) == 1
    assert result.line_items[0]["unit_price"].normalized_value == 3_000_000


def test_live_call_requires_api_key():
    engine = MistralOCREngine(api_key=None)
    with pytest.raises(ValueError):
        engine.analyze([_page()])


def test_call_api_posts_base64_and_requests_blocks():
    captured = {}

    class _Resp:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def fake_urlopen(request, timeout=None):
        import json

        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.data)
        body = json.dumps({"pages": [SAMPLE_PAGE_RESULT]}).encode()
        return _Resp(body)

    engine = MistralOCREngine(api_key="sk-test", model="ocr-4-1", urlopen=fake_urlopen)
    doc = engine.analyze([_page()])
    assert captured["url"].endswith("/v1/ocr")
    assert captured["auth"] == "Bearer sk-test"
    # OCR-4+ block extraction + block confidence must be requested.
    assert captured["payload"]["include_blocks"] is True
    assert captured["payload"]["confidence_scores_granularity"] == "block"
    assert captured["payload"]["model"] == "ocr-4-1"
    assert doc.engine == MISTRAL_ENGINE_NAME
    assert any("0000123" in b.text for b in doc.blocks)

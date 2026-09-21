"""Deterministic tests for the OCR adapter (no model inference).

These use a recorded provider-neutral response and an injected runner, so they
run without the optional ``ocr`` extra.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.ocr import (
    PaddleOCREngine,
    map_paddle_response,
    ENGINE_NAME,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ocr" / "paddle_structure_response.json"


@pytest.fixture
def recorded_paddle_response():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _page(width=1000, height=1400, page_number=1):
    return m.DocumentPage(
        document_id="DOC-abc",
        page_number=page_number,
        image_bytes=b"\x89PNG",
        width=width,
        height=height,
        dpi=300,
        native_text=None,
    )


def test_map_paddle_response_normalizes_box_and_reads_fields(recorded_paddle_response):
    blocks = map_paddle_response(recorded_paddle_response, [_page(width=1000, height=1400)])
    assert len(blocks) == 2
    first = blocks[0]
    assert first.block_id == "BLK-001"
    assert first.text == "30.000.000 VND"
    assert first.confidence == pytest.approx(0.97)
    assert first.page_number == 1
    # 124/1000 and 992/1000 -> normalized x range.
    assert first.bounding_box.x1 == pytest.approx(0.124)
    assert first.bounding_box.x2 == pytest.approx(0.992)
    assert first.bounding_box.y1 == pytest.approx(0.5)
    assert 0.0 <= first.bounding_box.y2 <= 1.0
    assert blocks[1].block_type == "KEY_VALUE"


def test_engine_wraps_blocks_into_ocrdocument(recorded_paddle_response):
    engine = PaddleOCREngine(
        runner=lambda pages: recorded_paddle_response, engine_version="fixture-v1"
    )
    result = engine.analyze([_page()])
    assert isinstance(result, m.OCRDocument)
    assert result.engine == ENGINE_NAME
    assert result.engine_version == "fixture-v1"
    assert result.document_id == "DOC-abc"
    assert "30.000.000 VND" in result.full_text
    assert len(result.blocks) == 2
    assert result.processing_ms >= 0


def test_engine_requires_pages():
    engine = PaddleOCREngine(runner=lambda pages: {"pages": []})
    with pytest.raises(ValueError):
        engine.analyze([])


def test_missing_poly_falls_back_to_full_page_box():
    raw = {"pages": [{"page_number": 1, "blocks": [
        {"block_id": "B1", "text": "x", "confidence": 0.5, "block_type": "TEXT"}
    ]}]}
    blocks = map_paddle_response(raw, [_page()])
    box = blocks[0].bounding_box
    assert (box.x1, box.y1, box.x2, box.y2) == (0.0, 0.0, 1.0, 1.0)


def test_coordinates_are_clamped_into_unit_range():
    raw = {"pages": [{"page_number": 1, "blocks": [
        {"block_id": "B1", "text": "x", "confidence": 0.5,
         "poly": [[-10, -10], [2000, -10], [2000, 3000], [-10, 3000]],
         "block_type": "TEXT"}
    ]}]}
    blocks = map_paddle_response(raw, [_page(width=1000, height=1400)])
    box = blocks[0].bounding_box
    assert box.x1 == 0.0 and box.y1 == 0.0
    assert box.x2 == 1.0 and box.y2 == 1.0


def test_map_paddle_response_preserves_table_index():
    raw = {"pages": [{"page_number": 1, "blocks": [
        {"block_id": "B1", "text": "9.000.000", "confidence": 0.9,
         "block_type": "TABLE_CELL", "table_index": 1, "row_index": 9, "column_index": 5}
    ]}]}
    block = map_paddle_response(raw, [_page()])[0]
    assert (block.table_index, block.row_index, block.column_index) == (1, 9, 5)

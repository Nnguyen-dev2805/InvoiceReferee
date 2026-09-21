"""Shared test factories."""

import copy
import json
from pathlib import Path

import pytest

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from invoice_referee.checks import engine

_FIXTURES_STRUCTURE = Path(__file__).parent / "fixtures_structure"


def _load_recorded_document(filename):
    """Load a recorded provider-neutral block set from ``fixtures_structure``."""
    with open(_FIXTURES_STRUCTURE / filename, encoding="utf-8") as fh:
        raw = json.load(fh)
    page = raw["pages"][0]
    width = page["dimensions"]["width"]
    height = page["dimensions"]["height"]
    blocks = []
    for b in page["blocks"]:
        poly = b.get("poly")
        if poly:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            box = m.BoundingBox(
                x1=min(xs) / width, y1=min(ys) / height,
                x2=max(xs) / width, y2=max(ys) / height,
            )
        else:
            box = m.BoundingBox(0.0, 0.0, 1.0, 1.0)
        blocks.append(m.OCRBlock(
            block_id=b["block_id"],
            page_number=b.get("page_number", page["page_number"]),
            text=b["text"],
            confidence=float(b.get("confidence", 0.0)),
            bounding_box=box,
            block_type=b["block_type"],
            row_index=b.get("row_index"),
            column_index=b.get("column_index"),
            table_index=b.get("table_index"),
        ))
    return m.OCRDocument(
        document_id=raw["document_id"],
        pages=[],
        blocks=blocks,
        full_text=" ".join(b.text for b in blocks if b.text),
        engine=raw.get("engine", "mistral"),
        engine_version=raw.get("engine_version", "ocr-4-1"),
        processing_ms=0,
    )


@pytest.fixture
def a_jpg_ocr_document():
    """The recorded ``a.jpg`` block set as an ``OCRDocument``."""
    return _load_recorded_document("a_jpg_blocks.json")


@pytest.fixture
def b_jpg_ocr_document():
    """The recorded receipt block set (the task spec's ``b.jpg``).

    Captured live from ``data/image/sen_non_bo.jpg`` — the real ``PHIẾU TẠM TĨNH``
    whose receipt number and total the extraction spec names.
    """
    return _load_recorded_document("b_jpg_blocks.json")

_ROUTINE = {
    "transaction_id": "TX-01",
    "transaction_type": "PO_GOODS_PURCHASE",
    "purchase_order": {
        "po_id": "PO-001",
        "vendor_id": "V-ABC",
        "approved_total": 30_000_000,
        "status": "APPROVED",
        "items": [
            {"item_id": "ITEM-001", "ordered_quantity": 10, "unit_price": 3_000_000, "line_total": 30_000_000}
        ],
    },
    "goods_receipts": [
        {
            "receipt_id": "GR-001",
            "po_id": "PO-001",
            "received_date": "2026-09-12",
            "status": "RECEIVED",
            "items": [{"item_id": "ITEM-001", "received_quantity": 10}],
        }
    ],
    "invoice": {
        "invoice_id": "INV-001",
        "invoice_number": "0000123",
        "invoice_series": "2C23TTU",
        "invoice_type": "ORIGINAL",
        "vendor_id": "V-ABC",
        "vendor_tax_code": "0101234567",
        "po_id": "PO-001",
        "invoice_date": "2026-09-13",
        "total_amount": 30_000_000,
        "items": [
            {"item_id": "ITEM-001", "invoiced_quantity": 10, "unit_price": 3_000_000, "line_total": 30_000_000}
        ],
    },
    "payment_history": [{"invoice_id": "INV-001", "status": "UNPAID", "paid_amount": 0}],
}


@pytest.fixture
def routine_evidence():
    """Return a deep copy of a routine PO-goods-purchase evidence dict."""

    def _make():
        return copy.deepcopy(_ROUTINE)

    return _make


@pytest.fixture
def build_inputs():
    """Return (transaction, checks) for a raw evidence dict."""

    def _build(evidence):
        tx = build_transaction(evidence)
        checks = engine.run_checks(tx)
        return tx, checks

    return _build

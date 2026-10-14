"""E5 typed extraction + provenance tests (plan E5, contracts §12.3).

Offline: a fake LLM returns a field payload. Extraction must produce one
state-aware FieldCandidate per applicable field, keep repeated lines, and let
code (not the model) key line ids. Provenance is verified against the OCR text:
a quote from another source/page, a paraphrase, or a real quote with the wrong
normalized value must not become FOUND. Missing is never zero.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.documents import (
    DocumentClassification,
    OcrBlock,
    OcrPage,
    OcrSourceResult,
    OcrWord,
)
from invoice_referee.evidence.extraction import extract_document
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroSchemaError

SHA = "a" * 64


def _ocr(markdown: str = "HÓA ĐƠN\nSố: 001\nNgày: 01/10/2026\nTổng cộng: 450.000") -> OcrSourceResult:
    block = OcrBlock(
        id="b1",
        kind="text",
        content=markdown,
        words=(OcrWord(text="450.000", block_start=30, block_end=37, confidence=0.9),),
    )
    return OcrSourceResult(
        source_id="source:1",
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=(OcrPage(page=1, markdown=markdown, blocks=(block,)),),
    )


def _classification(document_type: str = "E_INVOICE") -> DocumentClassification:
    return DocumentClassification(
        document_id="doc:1",
        source_id="source:1",
        page_range=(1, 1),
        block_ids=("b1",),
        document_type=document_type,  # type: ignore[arg-type]
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        role_refs={},
        refs=(),
    )


class FakeLlm:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        self.calls += 1
        return self.payload


async def test_found_requires_a_supported_value_and_ref() -> None:
    llm = FakeLlm(
        {
            "fields": [
                {"field": "document_number", "state": "FOUND", "value": "001",
                 "quote": "Số: 001"},
                {"field": "total_amount", "state": "FOUND", "value": "450000",
                 "quote": "Tổng cộng: 450.000"},
            ],
            "lines": [],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    by_field = {f.field: f for f in analysis.fields}
    assert by_field["total_amount"].state == "FOUND"
    assert by_field["total_amount"].value == "450000"
    assert by_field["total_amount"].refs


async def test_quote_from_other_source_is_rejected() -> None:
    llm = FakeLlm(
        {
            "fields": [
                {"field": "total_amount", "state": "FOUND", "value": "450000",
                 "quote": "Số tiền trên một hóa đơn khác hoàn toàn"},
            ],
            "lines": [],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    total = next(f for f in analysis.fields if f.field == "total_amount")
    assert total.state != "FOUND"


async def test_real_quote_with_mismatching_value_is_rejected() -> None:
    # The quote exists but the normalized value is not supported by it.
    llm = FakeLlm(
        {
            "fields": [
                {"field": "total_amount", "state": "FOUND", "value": "999000",
                 "quote": "Tổng cộng: 450.000"},
            ],
            "lines": [],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    total = next(f for f in analysis.fields if f.field == "total_amount")
    assert total.state != "FOUND"


async def test_missing_field_is_not_present_not_zero() -> None:
    llm = FakeLlm(
        {
            "fields": [
                {"field": "issuer_tax_code", "state": "NOT_PRESENT"},
            ],
            "lines": [],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    tax = next(f for f in analysis.fields if f.field == "issuer_tax_code")
    assert tax.state == "NOT_PRESENT"
    assert tax.value is None


async def test_line_ids_are_assigned_by_code_not_model() -> None:
    llm = FakeLlm(
        {
            "fields": [],
            "lines": [
                {"id": "model-supplied", "fields": [
                    {"field": "description", "state": "FOUND", "value": "Khách sạn",
                     "quote": "HÓA ĐƠN"},
                ]},
            ],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert analysis.line_items
    assert analysis.line_items[0].id != "model-supplied"


async def test_second_schema_failure_is_unresolved() -> None:
    # The model returns a shape the DTO rejects; one repair is allowed, then the
    # document stays unresolved rather than passing.
    class BadLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            self.calls += 1
            return {"fields": "not-a-list", "lines": []}

    llm = BadLlm()
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert analysis.profile_status in ("NEEDS_HUMAN", "UNKNOWN")
    assert llm.calls <= 2  # at most one repair


async def test_line_field_with_fabricated_quote_is_demoted() -> None:
    llm = FakeLlm(
        {
            "fields": [],
            "lines": [
                {"id": "model", "fields": [
                    {"field": "amount", "state": "FOUND", "value": "600000",
                     "quote": "Số tiền bịa hoàn toàn không có trong nguồn"},
                ]},
            ],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    line = analysis.line_items[0]
    amount = next(f for f in line.fields if f.field == "amount")
    assert amount.state != "FOUND"


async def test_line_field_with_mismatching_value_is_demoted() -> None:
    # The quote exists ("Tổng cộng: 450.000") but the value is not derivable.
    llm = FakeLlm(
        {
            "fields": [],
            "lines": [
                {"id": "model", "fields": [
                    {"field": "amount", "state": "FOUND", "value": "999000",
                     "quote": "Tổng cộng: 450.000"},
                ]},
            ],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    amount = next(f for f in analysis.line_items[0].fields if f.field == "amount")
    assert amount.state != "FOUND"

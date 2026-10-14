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


async def test_accepts_field_name_alias() -> None:
    # A real model returned {"name": ..., "value": ...} instead of {"field": ...};
    # the parser must accept the alias or every field becomes name ""/UNREADABLE.
    llm = FakeLlm({
        "fields": [
            {"name": "total_amount", "state": "FOUND", "value": "450000",
             "quote": "Tổng cộng: 450.000", "page": 1},
        ],
        "lines": [],
    })
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert any(f.field == "total_amount" for f in analysis.fields)
    assert all(f.field != "" for f in analysis.fields)


async def test_found_without_quote_is_not_found() -> None:
    # The model gave a value but no supporting quote; it cannot be FOUND.
    llm = FakeLlm({
        "fields": [{"name": "total_amount", "state": "FOUND", "value": "450000", "page": 1}],
        "lines": [],
    })
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    total = next(f for f in analysis.fields if f.field == "total_amount")
    assert total.state != "FOUND"


async def test_extraction_prompt_pins_the_schema_keys() -> None:
    captured: dict[str, str] = {}

    class RecLlm:
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            captured["system"] = system
            return {"fields": [], "lines": []}

    await extract_document(_ocr(), _classification(), llm=RecLlm(), budget=RunBudget())
    for key in ("field", "state", "value", "quote", "page"):
        assert key in captured["system"]


async def test_field_name_aliases_are_canonicalized() -> None:
    # Plan §12: model synonyms map to the profile vocabulary, so a correctly
    # read invoice is not reported as missing required fields.
    from invoice_referee.evidence.extraction import canonical_field_name

    assert canonical_field_name("invoice_number") == "document_number"
    assert canonical_field_name("seller_name") == "issuer_name"
    assert canonical_field_name("seller_tax_code") == "issuer_tax_code"
    assert canonical_field_name("invoice_date") == "document_date"
    assert canonical_field_name("symbol_code") == "serial_number"
    assert canonical_field_name("payment_method") == "payment_method_text"
    assert canonical_field_name("total_amount") == "total_amount"  # already canonical
    assert canonical_field_name("") == ""


async def test_extraction_canonicalizes_field_names_end_to_end() -> None:
    llm = FakeLlm({
        "fields": [
            {"name": "seller_name", "state": "FOUND", "value": "Công ty ABC",
             "quote": "HÓA ĐƠN", "page": 1},
        ],
        "lines": [],
    })
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert any(f.field == "issuer_name" for f in analysis.fields)


def test_iso_date_value_supported_by_vietnamese_quote() -> None:
    from invoice_referee.evidence.extraction import _value_supported

    # Model normalized a Vietnamese date to ISO; the quote holds the same date.
    assert _value_supported("2026-10-10", "Ngày 10 tháng 10 năm 2026")
    # A different date is not supported.
    assert not _value_supported("2026-10-11", "Ngày 10 tháng 10 năm 2026")


# --- Bug A: SETTLEMENT_FORM field-name aliases (real provider output) --------


def _settlement_ocr() -> OcrSourceResult:
    md = (
        "GIẤY ĐỀ NGHỊ QUYẾT TOÁN CÔNG TÁC\n"
        "Người đề nghị: Nguyễn An\n"
        "Nơi công tác: Hà Nội\n"
        "Thời gian công tác: từ 06/10/2026 đến 10/10/2026\n"
        "Mục đích: Làm việc với khách hàng tại Hà Nội\n"
        "Tổng chi phí đề nghị quyết toán: 3.240.000 đ\n"
        "Số tiền đã tạm ứng theo khai báo: 4.000.000 đ\n"
        "Số tiền đề nghị nhân viên hoàn lại: 760.000 đ\n"
        "Số tiền đề nghị công ty chi thêm: 0 đ"
    )
    block = OcrBlock(id="b1", kind="text", content=md, words=())
    return OcrSourceResult(
        source_id="source:1",
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=(OcrPage(page=1, markdown=md, blocks=(block,)),),
    )


def test_settlement_form_aliases_are_scoped_by_document_type() -> None:
    from invoice_referee.evidence.extraction import canonical_field_name

    # SETTLEMENT_FORM synonyms map to the profile vocabulary...
    assert canonical_field_name("requester_name", "SETTLEMENT_FORM") == "declared_name"
    assert canonical_field_name("work_location", "SETTLEMENT_FORM") == "trip_destination"
    assert canonical_field_name("start_date", "SETTLEMENT_FORM") == "trip_start"
    assert canonical_field_name("end_date", "SETTLEMENT_FORM") == "trip_end"
    assert canonical_field_name("total_expense", "SETTLEMENT_FORM") == "printed_total"
    assert canonical_field_name("total_amount_numeric", "SETTLEMENT_FORM") == "printed_total"
    assert canonical_field_name("advance_amount", "SETTLEMENT_FORM") == "declared_advance"
    assert canonical_field_name("refund_amount", "SETTLEMENT_FORM") == "printed_return"
    # ...without leaking into the invoice vocabulary (total_amount stays canonical).
    assert canonical_field_name("total_amount", "E_INVOICE") == "total_amount"
    assert canonical_field_name("total_amount") == "total_amount"


async def test_settlement_form_aliases_end_to_end() -> None:
    # A real model returns natural names; without scoped aliases every required
    # SETTLEMENT_FORM field is reported missing (false NEEDS_HUMAN).
    llm = FakeLlm(
        {
            "fields": [
                {"field": "requester_name", "state": "FOUND", "value": "Nguyễn An",
                 "quote": "Người đề nghị: Nguyễn An", "page": 1},
                {"field": "work_location", "state": "FOUND", "value": "Hà Nội",
                 "quote": "Nơi công tác: Hà Nội", "page": 1},
                {"field": "start_date", "state": "FOUND", "value": "06/10/2026",
                 "quote": "Thời gian công tác: từ 06/10/2026 đến 10/10/2026", "page": 1},
                {"field": "end_date", "state": "FOUND", "value": "10/10/2026",
                 "quote": "Thời gian công tác: từ 06/10/2026 đến 10/10/2026", "page": 1},
                {"field": "subject", "state": "FOUND", "value": "Làm việc với khách hàng tại Hà Nội",
                 "quote": "Mục đích: Làm việc với khách hàng tại Hà Nội", "page": 1},
                {"field": "total_expense", "state": "FOUND", "value": "3240000",
                 "quote": "Tổng chi phí đề nghị quyết toán: 3.240.000 đ", "page": 1},
                {"field": "advance_amount", "state": "FOUND", "value": "4000000",
                 "quote": "Số tiền đã tạm ứng theo khai báo: 4.000.000 đ", "page": 1},
                {"field": "refund_amount", "state": "FOUND", "value": "760000",
                 "quote": "Số tiền đề nghị nhân viên hoàn lại: 760.000 đ", "page": 1},
            ],
            "lines": [],
        }
    )
    analysis = await extract_document(
        _settlement_ocr(), _classification("SETTLEMENT_FORM"), llm=llm, budget=RunBudget()
    )
    found = {f.field for f in analysis.fields if f.state == "FOUND"}
    assert {
        "declared_name", "trip_destination", "trip_start", "trip_end",
        "purpose", "printed_total", "declared_advance", "printed_return",
    } <= found


# --- Bug B: the model returns line rows, sometimes as raw OCR strings --------


async def test_line_items_key_is_accepted() -> None:
    # The pinned prompt asks for `line_items`; the parser must read that key too.
    llm = FakeLlm(
        {
            "fields": [],
            "line_items": [
                {"fields": [
                    {"field": "description", "state": "FOUND", "value": "Khách sạn",
                     "quote": "HÓA ĐƠN", "page": 1},
                ]},
            ],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert len(analysis.line_items) == 1


async def test_raw_string_lines_do_not_crash_and_yield_no_rows() -> None:
    # A real model dumped raw OCR lines as a list of strings. They are not
    # structured rows, so code cannot fabricate fields; it must not crash and
    # must not invent line items.
    llm = FakeLlm(
        {
            "fields": [{"field": "total_amount", "state": "FOUND", "value": "450000",
                        "quote": "Tổng cộng: 450.000", "page": 1}],
            "lines": ["HÓA ĐƠN", "| STT | NỘI DUNG |", "Tổng cộng: 450.000"],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    assert analysis.line_items == ()
    assert any(f.field == "total_amount" for f in analysis.fields)


async def test_row_invoice_refs_list_value_is_stored_as_tuple() -> None:
    llm = FakeLlm(
        {
            "fields": [],
            "line_items": [
                {"fields": [
                    {"field": "amount", "state": "FOUND", "value": "450000",
                     "quote": "Tổng cộng: 450.000", "page": 1},
                    {"field": "invoice_refs", "state": "FOUND", "value": ["001"],
                     "quote": "Số: 001", "page": 1},
                ]},
            ],
        }
    )
    analysis = await extract_document(_ocr(), _classification(), llm=llm, budget=RunBudget())
    row = analysis.line_items[0]
    refs = next(f for f in row.fields if f.field == "invoice_refs")
    assert refs.state == "FOUND"
    assert refs.value == ("001",)

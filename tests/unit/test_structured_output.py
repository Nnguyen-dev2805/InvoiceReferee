"""Behavioral regressions for bounded extraction recovery."""
import json

import pytest

from invoice_referee.domain.documents import DocumentClassification, OcrPage, OcrSourceResult
from invoice_referee.evidence.extraction import extract_document
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroTransportError


def source():
    return OcrSourceResult(source_id="s", source_digest="a" * 64, provider="mistral",
                           model="ocr", pages=(OcrPage(page=1, markdown="Tổng: 120.000"),))


def unit():
    return DocumentClassification(document_id="d", source_id="s", page_range=(1, 1),
                                  document_type="E_INVOICE")


class Responses:
    def __init__(self, values):
        self.values = iter(values)
        self.requests = []

    async def complete_json(self, *, system, user, budget):
        self.requests.append((system, user))
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


VALID = {"fields": [{"field": "total_amount", "state": "FOUND", "value": 120000,
                      "quote": "Tổng: 120.000", "page": 1}], "line_items": []}


async def test_repair_contains_previous_response_and_validation_error():
    llm = Responses([{"fields": "broken", "line_items": []}, VALID])
    result = await extract_document(source(), unit(), llm=llm, budget=RunBudget())
    assert result.fields and result.fields[0].value == 120000
    assert len(llm.requests) == 2
    assert "broken" in llm.requests[1][1] and "fields" in llm.requests[1][1]
    assert llm.requests[0][1] != llm.requests[1][1]


async def test_two_documents_share_one_repair_slot():
    bad = {"fields": "broken", "line_items": []}
    llm = Responses([bad, VALID, bad, VALID])
    budget = RunBudget()
    first = await extract_document(source(), unit(), llm=llm, budget=budget)
    second = await extract_document(source(), unit(), llm=llm, budget=budget)
    assert first.fields
    assert second.profile_status == "NEEDS_HUMAN"
    assert len(llm.requests) == 3


async def test_oversize_repair_keeps_source_and_does_not_call_again():
    llm = Responses([{"fields": "x" * 2000, "line_items": []}, VALID])
    llm.max_input_chars = 1000
    budget = RunBudget()
    result = await extract_document(source(), unit(), llm=llm, budget=budget)
    assert result.profile_status == "NEEDS_HUMAN"
    assert len(llm.requests) == 1
    assert "Tổng: 120.000" in llm.requests[0][1]
    assert budget.schema_repairs == 0


async def test_confidence_and_extraction_share_one_repair_slot():
    from invoice_referee.domain.documents import ConfidenceCandidate
    from invoice_referee.evidence.ocr_quality import review_ocr_quality
    candidate = ConfidenceCandidate(candidate_id="c1", source_id="s", page=1, block_id="b1", content="120.000")
    assessment = {"candidate_id": "c1", "importance": "CRITICAL", "quality_state": "READABLE",
        "review_action": "CONTINUE", "requires_verification": False, "canonical_fields": ["total_amount"], "reason": "Giá trị rõ"}
    llm = Responses([{"assessments": []}, {"assessments": [assessment]}, {"fields": "broken"}, VALID])
    budget = RunBudget()
    review = await review_ocr_quality((candidate,), llm=llm, budget=budget)
    result = await extract_document(source(), unit(), llm=llm, budget=budget)
    assert review.status == "ASSESSED"
    assert result.profile_status == "NEEDS_HUMAN"
    assert budget.schema_repairs == 1 and len(llm.requests) == 3


async def test_transport_not_repaired():
    llm = Responses([XkiroTransportError("HTTP 503"), VALID])
    with pytest.raises(XkiroTransportError):
        await extract_document(source(), unit(), llm=llm, budget=RunBudget())
    assert len(llm.requests) == 1


async def test_exhausted_deadline_does_not_call_provider():
    llm = Responses([VALID])
    result = await extract_document(source(), unit(), llm=llm,
                                    budget=RunBudget(processing_deadline_s=0))
    assert result.profile_status == "NEEDS_HUMAN"
    assert not llm.requests


async def test_quote_must_belong_to_claimed_page():
    ocr = source().model_copy(update={"pages": (OcrPage(page=1, markdown="Trang đầu"),
                                               OcrPage(page=2, markdown="Tổng: 120.000"))})
    classification = unit().model_copy(update={"page_range": (1, 2)})
    result = await extract_document(ocr, classification, llm=Responses([VALID]), budget=RunBudget())
    assert result.fields[0].state == "UNREADABLE"


async def test_identical_quote_on_a_page_outside_document_unit_is_rejected():
    ocr = source().model_copy(update={"pages": (OcrPage(page=1, markdown="Tổng: 120.000"),
                                               OcrPage(page=2, markdown="Tổng: 120.000"))})
    result = await extract_document(ocr, unit().model_copy(update={"page_range": (2, 2)}),
                                     llm=Responses([VALID]), budget=RunBudget())
    assert result.fields[0].state == "UNREADABLE"


async def test_invalid_nested_field_state_is_repaired():
    bad = {"fields": [{"field": "total_amount", "state": "PRESENT"}], "line_items": []}
    llm = Responses([bad, VALID])
    try:
        result = await extract_document(source(), unit(), llm=llm, budget=RunBudget())
    except Exception as error:
        result = error
    assert not isinstance(result, Exception)
    assert result.fields[0].value == 120000


async def test_encoded_invoice_reference_array_is_normalized_before_matching():
    ocr = source().model_copy(update={"pages": (OcrPage(page=1, markdown="Số INV-X9"),)})
    payload = {"fields": [], "line_items": [{"fields": [{"field": "invoice_refs", "state": "FOUND",
        "value": '["INV-X9"]', "quote": "Số INV-X9", "page": 1}]}]}
    result = await extract_document(ocr, unit().model_copy(update={"document_type": "SETTLEMENT_FORM"}),
                                     llm=Responses([payload]), budget=RunBudget())
    assert result.line_items[0].fields[0].value == ("INV-X9",)


@pytest.mark.parametrize("quote,value,state", [
    ("Trạng thái giao dịch: Hoàn tất", "COMPLETED", "FOUND"),
    ("Trạng thái giao dịch: Thất bại", "COMPLETED", "UNREADABLE"),
    ("Trạng thái giao dịch: Không thành công", "COMPLETED", "UNREADABLE"),
    ("Trạng thái giao dịch: Đang xử lý", "PENDING", "FOUND"),
    ("Status: NOT COMPLETED", "COMPLETED", "UNREADABLE"),
    ("Status: not successful", "SUCCESS", "UNREADABLE"),
])
async def test_normalized_transaction_status_requires_exact_source_meaning(quote, value, state):
    ocr = source().model_copy(update={"pages": (OcrPage(page=1, markdown=quote),)})
    payload = {"fields": [{"field": "transaction_status", "state": "FOUND", "value": value,
                            "quote": quote, "page": 1}], "line_items": []}
    result = await extract_document(ocr, unit().model_copy(update={"document_type": "PAYMENT_PROOF"}),
                                     llm=Responses([payload]), budget=RunBudget())
    assert result.fields[0].state == state


async def test_ambiguous_values_keep_two_source_backed_alternatives():
    ocr = source().model_copy(update={"pages": (OcrPage(page=1, markdown="120.000 hoặc 130.000"),)})
    payload = {"fields": [{"field": "total_amount", "state": "AMBIGUOUS", "alternatives": [
        {"value": 120000, "quote": "120.000", "page": 1},
        {"value": 130000, "quote": "130.000", "page": 1}]}], "line_items": []}
    try:
        result = await extract_document(ocr, unit(), llm=Responses([payload]), budget=RunBudget())
    except Exception as error:
        result = error
    assert not isinstance(result, Exception)
    assert result.fields[0].state == "AMBIGUOUS"
    assert result.fields[0].value is None
    assert [v.value for v in result.fields[0].alternatives] == [120000, 130000]

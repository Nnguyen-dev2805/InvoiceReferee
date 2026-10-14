"""E4 document classification tests (plan E4, contracts §12.2).

Offline: a fake LLM stands in for X-Kiro. One batch call per root; a document's
type and roles are separate; the code-owned type→role map is not overridable by
the model; an ambiguous/low result is UNKNOWN and never selects an extraction
schema. A PDF may hold several units with distinct, code-owned document ids.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.documents import OcrPage, OcrSourceResult
from invoice_referee.evidence.classification import (
    DEFAULT_TYPE_ROLES,
    classify_documents,
    compatible_roles,
)
from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroError

SHA = "a" * 64


def _ocr(source_id: str, pages: tuple[OcrPage, ...]) -> OcrSourceResult:
    return OcrSourceResult(
        source_id=source_id,
        source_digest=SHA,
        provider="mistral",
        model="ocr-1",
        pages=pages,
    )


def _page(n: int, text: str) -> OcrPage:
    return OcrPage(page=n, markdown=text)


class FakeLlm:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = 0
        self.stages: list[str] = []

    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        self.calls += 1
        self.stages.append("CLASSIFY")
        return self.response


def test_all_17_types_have_a_code_owned_role_map() -> None:
    from invoice_referee.domain.documents import DOCUMENT_TYPES

    assert set(DEFAULT_TYPE_ROLES) == set(DOCUMENT_TYPES)


def test_original_and_supporting_types_map_correctly() -> None:
    assert compatible_roles("E_INVOICE") == ("ORIGINAL_EXPENSE_EVIDENCE",)
    assert compatible_roles("PAYMENT_PROOF") == ("SUPPORTING_DOCUMENT",)
    assert compatible_roles("SETTLEMENT_FORM") == ("SETTLEMENT_DECLARATION",)
    assert compatible_roles("UNKNOWN") == ("UNKNOWN",)


def test_document_profiles_cover_all_types() -> None:
    from invoice_referee.domain.documents import DOCUMENT_TYPES

    assert set(DOCUMENT_PROFILES) == set(DOCUMENT_TYPES)
    # SETTLEMENT_FORM is new (Hoangha has no entry) and must have required fields.
    assert DOCUMENT_PROFILES["SETTLEMENT_FORM"].required_fields


async def test_classification_batch_precedes_extraction() -> None:
    ocr = (_ocr("source:1", (_page(1, "HÓA ĐƠN GTGT"),)),)
    llm = FakeLlm(
        {
            "documents": [
                {
                    "source_id": "source:1",
                    "page_range": [1, 1],
                    "document_type": "E_INVOICE",
                    "roles": ["ORIGINAL_EXPENSE_EVIDENCE"],
                    "signals": ["header"],
                }
            ]
        }
    )
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert llm.calls == 1, "one batch classification call per root"
    assert result[0].document_type == "E_INVOICE"
    assert result[0].roles == ("ORIGINAL_EXPENSE_EVIDENCE",)


async def test_unknown_never_selects_a_guessed_schema() -> None:
    ocr = (_ocr("source:1", (_page(1, "blurry"),)),)
    llm = FakeLlm(
        {
            "documents": [
                {
                    "source_id": "source:1",
                    "page_range": [1, 1],
                    "document_type": "UNKNOWN",
                    "roles": ["UNKNOWN"],
                    "alternative_document_types": ["E_INVOICE", "PAPER_RECEIPT"],
                }
            ]
        }
    )
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert result[0].document_type == "UNKNOWN"
    assert result[0].alternative_document_types == ("E_INVOICE", "PAPER_RECEIPT")


async def test_model_cannot_add_an_incompatible_role() -> None:
    # The model claims PAYMENT_EVIDENCE on an invoice without separate payment
    # facts; the code-owned map must drop it.
    ocr = (_ocr("source:1", (_page(1, "HÓA ĐƠN"),)),)
    llm = FakeLlm(
        {
            "documents": [
                {
                    "source_id": "source:1",
                    "page_range": [1, 1],
                    "document_type": "E_INVOICE",
                    "roles": ["ORIGINAL_EXPENSE_EVIDENCE", "PAYMENT_EVIDENCE"],
                }
            ]
        }
    )
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert result[0].roles == ("ORIGINAL_EXPENSE_EVIDENCE",)


async def test_mixed_pdf_has_two_document_units() -> None:
    ocr = (
        _ocr(
            "source:1",
            (_page(1, "HÓA ĐƠN"), _page(2, "BIÊN NHẬN")),
        ),
    )
    llm = FakeLlm(
        {
            "documents": [
                {
                    "source_id": "source:1",
                    "page_range": [1, 1],
                    "document_type": "E_INVOICE",
                    "roles": ["ORIGINAL_EXPENSE_EVIDENCE"],
                },
                {
                    "source_id": "source:1",
                    "page_range": [2, 2],
                    "document_type": "PAPER_RECEIPT",
                    "roles": ["ORIGINAL_EXPENSE_EVIDENCE"],
                },
            ]
        }
    )
    units = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert len(units) == 2
    assert len({u.document_id for u in units}) == 2


async def test_unexpected_source_id_is_rejected() -> None:
    ocr = (_ocr("source:1", (_page(1, "x"),)),)
    llm = FakeLlm(
        {
            "documents": [
                {
                    "source_id": "source:other",
                    "page_range": [1, 1],
                    "document_type": "E_INVOICE",
                    "roles": ["ORIGINAL_EXPENSE_EVIDENCE"],
                }
            ]
        }
    )
    with pytest.raises(XkiroError):
        await classify_documents(ocr, llm=llm, budget=RunBudget())


async def test_out_of_range_page_is_rejected() -> None:
    ocr = (_ocr("source:1", (_page(1, "x"),)),)  # only 1 page
    llm = FakeLlm({"documents": [
        {"source_id": "source:1", "page_range": [1, 9],
         "document_type": "E_INVOICE", "roles": ["ORIGINAL_EXPENSE_EVIDENCE"]}
    ]})
    with pytest.raises(XkiroError):
        await classify_documents(ocr, llm=llm, budget=RunBudget())


async def test_overlapping_units_are_rejected() -> None:
    ocr = (_ocr("source:1", (_page(1, "a"), _page(2, "b"))),)
    llm = FakeLlm({"documents": [
        {"source_id": "source:1", "page_range": [1, 2], "document_type": "E_INVOICE",
         "roles": ["ORIGINAL_EXPENSE_EVIDENCE"]},
        {"source_id": "source:1", "page_range": [2, 2], "document_type": "PAPER_RECEIPT",
         "roles": ["ORIGINAL_EXPENSE_EVIDENCE"]},
    ]})
    with pytest.raises(XkiroError):
        await classify_documents(ocr, llm=llm, budget=RunBudget())


async def test_unknown_model_type_falls_back_to_unknown_not_crash() -> None:
    # A model may return a free-form label ("INVOICE"); it must map to UNKNOWN
    # rather than raising a ValidationError that crashes the pipeline.
    ocr = (_ocr("source:1", (_page(1, "HÓA ĐƠN"),)),)
    llm = FakeLlm({"documents": [
        {"source_id": "source:1", "page_range": [1, 1],
         "document_type": "INVOICE", "roles": ["ORIGINAL_EXPENSE_EVIDENCE"]}
    ]})
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert result[0].document_type == "UNKNOWN"
    assert result[0].roles == ("UNKNOWN",)


async def test_unknown_role_is_dropped() -> None:
    ocr = (_ocr("source:1", (_page(1, "x"),)),)
    llm = FakeLlm({"documents": [
        {"source_id": "source:1", "page_range": [1, 1],
         "document_type": "E_INVOICE", "roles": ["INVOICE_ROLE", "ORIGINAL_EXPENSE_EVIDENCE"]}
    ]})
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert result[0].roles == ("ORIGINAL_EXPENSE_EVIDENCE",)


async def test_unknown_alternative_type_is_dropped() -> None:
    ocr = (_ocr("source:1", (_page(1, "x"),)),)
    llm = FakeLlm({"documents": [
        {"source_id": "source:1", "page_range": [1, 1],
         "document_type": "E_INVOICE", "roles": ["ORIGINAL_EXPENSE_EVIDENCE"],
         "alternative_document_types": ["INVOICE", "PAPER_RECEIPT"]}
    ]})
    result = await classify_documents(ocr, llm=llm, budget=RunBudget())
    assert result[0].alternative_document_types == ("PAPER_RECEIPT",)

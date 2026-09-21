"""Document-type routing: a receipt must never be dressed up as a supplier invoice.

The business path (`review()`) only understands PO-based supplier invoices. If a
receipt were converted into invoice evidence it would be silently mislabelled —
`Số:` would become an invoice number and a receipt total an invoice total. These
tests pin the boundary: invoice evidence or an explicit refusal.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain import models as m
from invoice_referee.ingestion.pipeline import (
    FieldReview,
    apply_field_reviews,
    reviewed_extraction_to_evidence,
)


def _candidate(name, value, *, status=m.FieldStatus.EXTRACTED, method="LLM_ASSISTED"):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value) if value is not None else None,
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=["B1"],
        extraction_method=method,
    )


def _invoice_result(document_type=m.DocumentType.SUPPLIER_INVOICE):
    fields = {
        "invoice_number": _candidate("invoice_number", "0000123"),
        "invoice_series": _candidate("invoice_series", "2C23TTU"),
        "vendor_tax_code": _candidate("vendor_tax_code", "0110329220"),
        "vendor_id": _candidate("vendor_id", "V-ABC", method="PO_VENDOR_MASTER"),
        "po_id": _candidate("po_id", "PO-001"),
        "invoice_date": _candidate("invoice_date", "2023-07-11"),
        "total_amount": _candidate("total_amount", 9_000_000),
    }
    return m.InvoiceExtractionResult(
        document_id="DOC-a",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields,
        document_type=document_type,
    )


def _receipt_result():
    fields = {
        "merchant_name": _candidate("merchant_name", "SEN NAM BỘ"),
        "receipt_number": _candidate("receipt_number", "2627003876"),
        "receipt_datetime": _candidate("receipt_datetime", "2026-09-18"),
        "total_amount": _candidate("total_amount", 4_035_570),
        "tax_amount": _candidate("tax_amount", 336_820),
    }
    return m.InvoiceExtractionResult(
        document_id="DOC-b",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=fields,
        document_type=m.DocumentType.TEMPORARY_BILL,
    )


def _base_evidence():
    return {
        "transaction_id": "TX-1",
        "transaction_type": "PO_GOODS_PURCHASE",
        "purchase_order": {"po_id": "PO-001"},
    }


def _confirm_all(result):
    reviews = {name: FieldReview.confirm() for name in result.fields}
    return apply_field_reviews(result, reviews, actor="ap@x")


# --- invoice path -------------------------------------------------------------


def test_reviewed_invoice_produces_invoice_evidence():
    reviewed = _confirm_all(_invoice_result())
    evidence = reviewed_extraction_to_evidence(reviewed, _base_evidence())
    assert evidence["invoice"]["invoice_number"] == "0000123"
    assert evidence["invoice"]["total_amount"] == 9_000_000
    assert evidence["invoice"]["source_type"] == "OCR"
    assert evidence["document_type"] == "SUPPLIER_INVOICE"


def test_invoice_routing_is_allowed_even_when_status_is_needs_review():
    """Routing is a type decision, not a completeness decision.

    An incomplete invoice still becomes invoice evidence: the business pipeline is
    what turns missing facts into REQUEST_INFO, and it must see the real values.
    """
    reviewed = _invoice_result()  # nothing confirmed
    evidence = reviewed_extraction_to_evidence(reviewed, _base_evidence())
    assert evidence["invoice"]["total_amount"] == 9_000_000


# --- receipt path -------------------------------------------------------------


@pytest.mark.parametrize("doc_type", [
    m.DocumentType.RESTAURANT_RECEIPT,
    m.DocumentType.TEMPORARY_BILL,
    m.DocumentType.POS_RECEIPT,
])
def test_receipt_never_becomes_invoice_evidence(doc_type):
    result = _receipt_result()
    result.document_type = doc_type
    with pytest.raises(m.UnsupportedDocumentTypeError):
        reviewed_extraction_to_evidence(_confirm_all(result), _base_evidence())


def test_receipt_refusal_names_the_document_type():
    result = _receipt_result()
    with pytest.raises(m.UnsupportedDocumentTypeError) as excinfo:
        reviewed_extraction_to_evidence(_confirm_all(result), _base_evidence())
    assert "TEMPORARY_BILL" in str(excinfo.value)


def test_unknown_document_type_is_refused():
    """An unestablished type is a fail-closed condition, not an invoice."""
    result = _receipt_result()
    result.document_type = m.DocumentType.UNKNOWN
    with pytest.raises(m.UnsupportedDocumentTypeError):
        reviewed_extraction_to_evidence(_confirm_all(result), _base_evidence())


def test_receipt_evidence_is_still_available_as_receipt_evidence():
    """The refusal is about routing, not about throwing the extraction away."""
    result = _receipt_result()
    evidence = reviewed_extraction_to_evidence(
        _confirm_all(result), _base_evidence(), allow_receipt=True
    )
    assert "invoice" not in evidence
    assert evidence["receipt"]["receipt_number"] == "2627003876"
    assert evidence["receipt"]["total_amount"] == 4_035_570
    assert evidence["document_type"] == "TEMPORARY_BILL"
    # A receipt must not carry invoice-only keys.
    assert "invoice_number" not in evidence["receipt"]
    assert "vendor_tax_code" not in evidence["receipt"]


# --- backward compatibility ---------------------------------------------------


def test_legacy_rule_path_keeps_its_invoice_only_converter():
    """The rule-based path keeps `reviewed_invoice_to_evidence` working unchanged.

    That converter predates `DocumentType` and only ever produced invoice evidence
    from the deterministic extractor. It is left alone so the baseline path is not
    broken by the LLM-first routing rules; only the new, type-aware converter
    enforces them.
    """
    from invoice_referee.ingestion.pipeline import reviewed_invoice_to_evidence

    result = m.InvoiceExtractionResult(
        document_id="DOC-a",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=_invoice_result().fields,
    )
    assert result.document_type is m.DocumentType.UNKNOWN
    evidence = reviewed_invoice_to_evidence(_confirm_all(result), _base_evidence())
    assert evidence["invoice"]["invoice_number"] == "0000123"


def test_type_aware_converter_refuses_an_untyped_result():
    """The new converter will not infer a type: UNKNOWN is refused, not assumed."""
    result = m.InvoiceExtractionResult(
        document_id="DOC-a",
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=_invoice_result().fields,
    )
    with pytest.raises(m.UnsupportedDocumentTypeError):
        reviewed_extraction_to_evidence(_confirm_all(result), _base_evidence())

"""OCR extraction orchestration service.

`extract_invoice` runs the full document-to-candidates pipeline and returns an
``InvoiceExtractionResult`` plus the shared ``AuditStore`` (so the later
business ``review()`` continues one audit timeline). It never issues a business
action. A technical failure raises ``DocumentInputError`` (bad upload) or
``ExtractionError`` (engine/processing failure) — never a silent guessed field.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.agent.llm_client import LLMClient
from invoice_referee.audit.store import AuditStore
from invoice_referee.ingestion.file_validation import DocumentInputError, validate_upload
from invoice_referee.ingestion.document_router import render_document
from invoice_referee.ingestion.image_preprocessing import preprocess_pages
from invoice_referee.ingestion.invoice_fields import extract_invoice_fields
from invoice_referee.ingestion.identity_resolution import resolve_invoice_identities
from invoice_referee.ingestion.extraction_validation import validate_extraction
from invoice_referee.ingestion.llm_mapper import merge_llm_candidates
from invoice_referee.ingestion.ocr import OCREngine


class ExtractionError(RuntimeError):
    """A technical failure during extraction (not a business decision)."""


def extract_invoice(
    *,
    transaction_id: str,
    filename: str,
    claimed_mime: str,
    content: bytes,
    po: m.PurchaseOrder,
    engine: OCREngine,
    actor: str,
    llm_client: Optional[LLMClient] = None,
    enable_llm_mapping: bool = False,
) -> tuple[m.InvoiceExtractionResult, AuditStore]:
    """Validate, render, OCR, extract, resolve, and validate one Supplier Invoice.

    Returns the extraction result (status ``NEEDS_REVIEW``) and the shared audit
    store. The optional LLM mapper runs only when ``enable_llm_mapping`` is True
    and a client is supplied.
    """
    try:
        document = validate_upload(filename, claimed_mime, content)
        audit = AuditStore(transaction_id=transaction_id)
        audit.record_document_uploaded(document, actor=actor)
        audit.record_document_validated(document, actor=actor)

        pages = preprocess_pages(render_document(document))
        ocr_document = engine.analyze(pages)
        audit.record_ocr_completed(ocr_document)

        result = extract_invoice_fields(ocr_document)
        result = resolve_invoice_identities(result, po)
        if enable_llm_mapping and llm_client is not None:
            result = merge_llm_candidates(result, ocr_document, llm_client)
        result = validate_extraction(result)

        for candidate in result.fields.values():
            audit.record_field_event("FIELD_EXTRACTED", candidate, actor=actor)

        result.audit_events = list(audit.events)
        return result, audit
    except DocumentInputError:
        raise  # technical input error surfaces unchanged
    except Exception as exc:  # provider/rendering/OCR failure
        raise ExtractionError(f"invoice extraction failed: {type(exc).__name__}") from exc

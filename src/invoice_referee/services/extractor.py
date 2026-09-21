"""OCR extraction orchestration service.

`extract_invoice` runs the full document-to-candidates pipeline and returns an
``InvoiceExtractionResult`` plus the shared ``AuditStore`` (so the later business
``review()`` continues one audit timeline). It never issues a business action. A
technical failure raises ``DocumentInputError`` (bad upload) or ``ExtractionError``
(engine/processing failure) — never a silent guessed field.

Extraction is **LLM-first and only**: the semantic extractor maps OCR blocks to
fields by meaning, and the grounding verifier checks every mapping against the
cited blocks. There is no label/layout/fuzzy mapper to fall back to — a document
the model cannot ground stays unresolved and goes to human review, which is the
fail-closed direction. The deterministic stages downstream are unchanged:
normalization, identity resolution, validation, and human confirmation.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.agent.llm_client import LLMClient
from invoice_referee.audit.store import AuditStore
from invoice_referee.ingestion.file_validation import DocumentInputError, validate_upload
from invoice_referee.ingestion.document_router import render_document
from invoice_referee.ingestion.image_preprocessing import preprocess_pages
from invoice_referee.ingestion.identity_resolution import resolve_invoice_identities
from invoice_referee.ingestion.extraction_validation import validate_extraction
from invoice_referee.ingestion.ocr import OCREngine
from invoice_referee.ingestion.semantic_extraction import extract_semantics


class ExtractionError(RuntimeError):
    """A technical failure during extraction (not a business decision)."""


def _result_from_semantics(
    semantic, document: m.OCRDocument, po: m.PurchaseOrder
) -> m.InvoiceExtractionResult:
    """Build an extraction result from a grounded semantic extraction.

    Identity resolution binds ``vendor_id`` only on an exact tax-code match, and
    validation assigns confirmation status. A model-sourced field can never be
    auto-accepted — validation forces ``NEEDS_CONFIRMATION`` for LLM_ASSISTED.
    """
    result = m.InvoiceExtractionResult(
        document_id=document.document_id,
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields=dict(semantic.fields),
        line_items=list(semantic.line_items),
        field_candidates={
            name: [candidate] for name, candidate in semantic.fields.items()
        },
        line_item_candidate_sets=[
            {name: [candidate] for name, candidate in line.items()}
            for line in semantic.line_items
        ],
        warnings=list(semantic.warnings),
        document_type=semantic.document_type,
    )
    result = resolve_invoice_identities(result, po)
    return result


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
) -> tuple[m.InvoiceExtractionResult, AuditStore]:
    """Validate, render, OCR, extract semantically, resolve, and validate.

    Returns the extraction result (status ``NEEDS_REVIEW``) and the shared audit
    store. A missing client is a configuration error, not a reason to fall back to
    a different extractor: extraction fails closed with no fields, and the case
    goes to human review.
    """
    try:
        document = validate_upload(filename, claimed_mime, content)
        audit = AuditStore(transaction_id=transaction_id)
        audit.record_document_uploaded(document, actor=actor)
        audit.record_document_validated(document, actor=actor)

        pages = preprocess_pages(render_document(document))
        ocr_document = engine.analyze(pages)
        audit.record_ocr_completed(ocr_document)

        semantic = extract_semantics(ocr_document, llm_client)
        result = _result_from_semantics(semantic, ocr_document, po)
        result = validate_extraction(result)

        for candidate in result.fields.values():
            audit.record_field_event("FIELD_EXTRACTED", candidate, actor=actor)

        result.audit_events = list(audit.events)
        return result, audit
    except DocumentInputError:
        raise  # technical input error surfaces unchanged
    except Exception as exc:  # provider/rendering/OCR failure
        raise ExtractionError(f"invoice extraction failed: {type(exc).__name__}") from exc

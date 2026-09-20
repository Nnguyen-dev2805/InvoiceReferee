"""Route a validated document to the PDF or image rendering path.

The router is the single entry point (`render_document`) that downstream OCR
uses; it hides whether the source was a PDF or an image and always yields
``DocumentPage`` objects with normalized image bytes.
"""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.ingestion import pdf_renderer


def render_document(document: m.UploadedDocument) -> list[m.DocumentPage]:
    if document.mime_type == "application/pdf":
        return pdf_renderer.render_pdf(document)
    if document.mime_type in ("image/png", "image/jpeg"):
        return pdf_renderer.render_image(document)
    # validate_upload already rejects anything else; guard defensively.
    raise ValueError(f"unsupported document type for rendering: {document.mime_type}")

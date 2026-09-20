"""Supplier-Invoice upload validation (fail-closed, provider errors contained).

Accepts exactly one PDF/PNG/JPEG invoice. Validation inspects magic bytes rather
than trusting the filename, enforces size/page limits, and rejects encrypted or
undecodable files as technical input errors. These are NOT ``REQUEST_INFO``
business decisions; they never reach the review pipeline.

Heavy providers (PyMuPDF, Pillow) are imported lazily so the core JSON review
runs without the optional ``ocr`` extra installed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from invoice_referee.domain import models as m

# Sprint 1 contract (see OCR design §5.1).
MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 5

# Magic-byte signatures per allow-listed MIME type.
SIGNATURES = {
    "application/pdf": lambda data: data.startswith(b"%PDF-"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
}


class DocumentInputError(ValueError):
    """A technical problem with the uploaded file, not a business uncertainty."""


def validate_upload(filename: str, claimed_mime: str, content: bytes) -> m.UploadedDocument:
    """Validate an uploaded invoice and return an :class:`UploadedDocument`.

    Raises :class:`DocumentInputError` for unsupported types, oversize files,
    MIME/content mismatches, encrypted or undecodable documents, and PDFs
    outside the one-to-five page range.
    """
    if claimed_mime not in SIGNATURES:
        raise DocumentInputError("unsupported invoice file type")
    if not content:
        raise DocumentInputError("invoice file is empty")
    if len(content) > MAX_BYTES:
        raise DocumentInputError("invoice file must be at most 10 MiB")
    if not SIGNATURES[claimed_mime](content):
        raise DocumentInputError("file content does not match its MIME type")

    if claimed_mime == "application/pdf":
        _validate_pdf(content)
    else:
        _validate_image(content)

    digest = hashlib.sha256(content).hexdigest()
    return m.UploadedDocument(
        document_id=f"DOC-{digest[:16]}",
        filename=Path(filename).name,  # sanitize: never trust a user path
        mime_type=claimed_mime,
        size_bytes=len(content),
        sha256=digest,
        content=content,
    )


def _validate_pdf(content: bytes) -> None:
    import pymupdf

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception:
        # Do not leak raw bytes or provider internals in the message.
        raise DocumentInputError("invoice PDF could not be opened") from None

    try:
        if doc.needs_pass:
            raise DocumentInputError("password-protected PDF is not supported")
        page_count = doc.page_count
        if page_count < 1:
            raise DocumentInputError("invoice PDF has no pages")
        if page_count > MAX_PDF_PAGES:
            raise DocumentInputError("invoice PDF must have at most 5 pages")
    finally:
        doc.close()


def _validate_image(content: bytes) -> None:
    import io

    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()  # structural integrity only
    except Image.DecompressionBombError:
        raise DocumentInputError("invoice image exceeds the safe pixel limit") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise DocumentInputError("invoice image could not be decoded") from None

    # verify() leaves the image object unusable; reopen for dimensions.
    try:
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
    except Image.DecompressionBombError:
        raise DocumentInputError("invoice image exceeds the safe pixel limit") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise DocumentInputError("invoice image could not be decoded") from None

    if width <= 0 or height <= 0:
        raise DocumentInputError("invoice image has invalid dimensions")

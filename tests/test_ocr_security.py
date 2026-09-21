"""Security tests for the OCR upload boundary (requires ocr extra)."""

from __future__ import annotations

import io

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from invoice_referee.domain import models as m  # noqa: E402
from invoice_referee.ingestion.file_validation import DocumentInputError, validate_upload  # noqa: E402


def _pdf(pages=1, encrypt=False):
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page().insert_text((72, 72), "Invoice")
    kwargs = {}
    if encrypt:
        kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "o", "user_pw": "u"}
    data = doc.tobytes(**kwargs)
    doc.close()
    return data


def _png(size=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_filename_path_traversal_is_sanitized():
    doc = validate_upload("../../../etc/passwd.pdf", "application/pdf", _pdf())
    assert "/" not in doc.filename
    assert ".." not in doc.filename


def test_mime_mismatch_rejected():
    with pytest.raises(DocumentInputError):
        validate_upload("x.png", "image/png", _pdf())


def test_encrypted_pdf_rejected():
    with pytest.raises(DocumentInputError):
        validate_upload("x.pdf", "application/pdf", _pdf(encrypt=True))


def test_corrupt_image_rejected():
    with pytest.raises(DocumentInputError):
        validate_upload("x.png", "image/png", b"\x89PNG\r\n\x1a\n corrupt")


def test_oversize_rejected():
    with pytest.raises(DocumentInputError):
        validate_upload("x.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1))


def test_uploaded_document_does_not_leak_bytes_into_audit():
    from invoice_referee.audit.store import AuditStore

    doc = validate_upload("inv.pdf", "application/pdf", _pdf())
    store = AuditStore(transaction_id="TX-1")
    ev = store.record_document_uploaded(doc)
    payload = store.export_json()
    assert "content" not in ev.details
    assert doc.sha256 in payload  # identified by hash, not raw bytes
    assert "%PDF" not in payload

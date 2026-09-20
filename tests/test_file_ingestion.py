"""Tests for upload validation and PDF/image rendering.

These require the optional ``ocr`` extra (PyMuPDF, Pillow). They are skipped
when it is not installed, so the core JSON suite still runs everywhere.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PIL")

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from invoice_referee.ingestion.file_validation import (  # noqa: E402
    DocumentInputError,
    validate_upload,
)
from invoice_referee.ingestion.document_router import render_document  # noqa: E402


# --- factories ---------------------------------------------------------------


def make_pdf(text: str = "Invoice No: 123", page_count: int = 1, encrypt: bool = False) -> bytes:
    doc = pymupdf.open()
    for _ in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    kwargs = {}
    if encrypt:
        kwargs = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "owner",
            "user_pw": "user",
        }
    data = doc.tobytes(**kwargs)
    doc.close()
    return data


def make_image(fmt: str = "PNG", size=(400, 300), color=(255, 255, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def pdf_bytes_factory():
    return make_pdf


# --- allow-list / signature --------------------------------------------------


def test_rejects_unsupported_mime():
    with pytest.raises(DocumentInputError, match="unsupported"):
        validate_upload("invoice.gif", "image/gif", b"GIF89a")


def test_rejects_extension_mime_magic_mismatch():
    with pytest.raises(DocumentInputError, match="does not match"):
        validate_upload("invoice.pdf", "application/pdf", b"not-a-pdf")


def test_rejects_empty_file():
    with pytest.raises(DocumentInputError, match="empty"):
        validate_upload("invoice.pdf", "application/pdf", b"")


def test_rejects_oversize_file():
    big = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 1)
    with pytest.raises(DocumentInputError, match="10 MiB"):
        validate_upload("invoice.pdf", "application/pdf", big)


# --- PDF validation ----------------------------------------------------------


def test_accepts_valid_pdf_and_hashes_it():
    content = make_pdf(page_count=1)
    doc = validate_upload("Invoice #7.pdf", "application/pdf", content)
    assert doc.mime_type == "application/pdf"
    assert doc.filename == "Invoice #7.pdf"
    assert doc.size_bytes == len(content)
    assert len(doc.sha256) == 64
    assert doc.document_id.startswith("DOC-")


def test_sanitizes_filename_path():
    content = make_pdf(page_count=1)
    doc = validate_upload("../../etc/passwd.pdf", "application/pdf", content)
    assert "/" not in doc.filename
    assert doc.filename == "passwd.pdf"


def test_rejects_more_than_five_pdf_pages():
    content = make_pdf(page_count=6)
    with pytest.raises(DocumentInputError, match="at most 5 pages"):
        validate_upload("invoice.pdf", "application/pdf", content)


def test_rejects_encrypted_pdf():
    content = make_pdf(page_count=1, encrypt=True)
    with pytest.raises(DocumentInputError, match="password-protected"):
        validate_upload("invoice.pdf", "application/pdf", content)


def test_rejects_corrupt_pdf():
    # Correct magic bytes but a truncated/garbage body.
    content = b"%PDF-1.4\n garbage that is not a real pdf body"
    with pytest.raises(DocumentInputError):
        validate_upload("invoice.pdf", "application/pdf", content)


# --- image validation --------------------------------------------------------


def test_accepts_valid_png():
    doc = validate_upload("scan.png", "image/png", make_image("PNG"))
    assert doc.mime_type == "image/png"


def test_accepts_valid_jpeg():
    doc = validate_upload("scan.jpg", "image/jpeg", make_image("JPEG"))
    assert doc.mime_type == "image/jpeg"


def test_rejects_corrupt_image():
    content = b"\x89PNG\r\n\x1a\n" + b"not really png data"
    with pytest.raises(DocumentInputError):
        validate_upload("scan.png", "image/png", content)


# --- rendering ---------------------------------------------------------------


def test_renders_pdf_at_300_dpi_and_preserves_native_text():
    document = validate_upload(
        "invoice.pdf", "application/pdf", make_pdf(text="Invoice No: 123", page_count=1)
    )
    pages = render_document(document)
    assert len(pages) == 1
    assert pages[0].dpi == 300
    assert pages[0].page_number == 1
    assert pages[0].width > 0 and pages[0].height > 0
    assert pages[0].image_bytes.startswith(b"\x89PNG")
    assert "Invoice No: 123" in (pages[0].native_text or "")


def test_renders_every_pdf_page():
    document = validate_upload("invoice.pdf", "application/pdf", make_pdf(page_count=3))
    pages = render_document(document)
    assert [p.page_number for p in pages] == [1, 2, 3]


def test_renders_image_as_single_rgb_png_page():
    document = validate_upload("scan.jpg", "image/jpeg", make_image("JPEG", size=(640, 480)))
    pages = render_document(document)
    assert len(pages) == 1
    assert pages[0].native_text is None
    assert pages[0].image_bytes.startswith(b"\x89PNG")  # normalized to PNG
    assert (pages[0].width, pages[0].height) == (640, 480)

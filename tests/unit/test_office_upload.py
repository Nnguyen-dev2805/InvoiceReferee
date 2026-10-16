"""Office uploads: DOC/DOCX sniff + local text extraction (RED first)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

REAL_DOCX = Path(
    "data/tham-khao/uc-03/tc25-tai-lieu-thay-the-lech-so-tien-voi-report/report_hoan_ung.docx"
)


def _mini_docx(paragraphs: tuple[str, ...]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("[Content_Types].xml", content_types)
        handle.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_sniff_docx_by_content_not_extension():
    from invoice_referee.api.routes import _sniff_media

    assert (
        _sniff_media(_mini_docx(("GIẤY QUYẾT TOÁN",)), filename="upload.bin") == "DOCX"
    )


def test_sniff_doc_by_ole_header():
    from invoice_referee.api.routes import _sniff_media

    assert _sniff_media(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512) == "DOC"


def test_sniff_still_accepts_pdf_png_jpeg_and_rejects_junk():
    from invoice_referee.api.routes import _sniff_media

    assert _sniff_media(b"%PDF-1.4 fake") == "PDF"
    assert _sniff_media(b"\x89PNG\r\n\x1a\nrest") == "PNG"
    assert _sniff_media(b"\xff\xd8\xff rest") == "JPEG"
    assert _sniff_media(b"just some text") is None
    # A zip that is not a Word document is not a DOCX.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as handle:
        handle.writestr("hello.txt", "hi")
    assert _sniff_media(buffer.getvalue(), filename="a.docx") is None


def test_docx_extracts_real_fixture_text():
    from invoice_referee.evidence.office import extract_office_pages

    pages = extract_office_pages(REAL_DOCX.read_bytes(), "DOCX")
    assert pages, "a real settlement .docx must yield at least one page"
    joined = "\n".join(pages)
    assert "HOÀN ỨNG" in joined and "NGUYỄN MINH AN" in joined


def test_docx_tables_are_kept_in_reading_order():
    from invoice_referee.evidence.office import extract_office_pages

    data = _mini_docx(("Dòng một 900000",))
    pages = extract_office_pages(data, "DOCX")
    assert any("Dòng một 900000" in page for page in pages)


def test_doc_extracts_text_from_word_binary():
    from invoice_referee.evidence.office import extract_office_pages

    pages = extract_office_pages(_make_word_doc("Di chuyển nội thành 700000"), "DOC")
    assert any("Di chuyển nội thành 700000" in page for page in pages)


def _make_word_doc(text: str) -> bytes:
    """Build a minimal Word 97-2003 binary inside a hand-written OLE container.

    Test-only writer; the reader under test (`office._doc_pages`) parses this
    through real OLE + Fib/Clx/piece-table logic, so offsets must be exact.
    The text is padded past 4096 stream bytes to stay on regular FAT sectors
    (no MiniFAT involved).
    """
    import struct

    padded = text + "\n" * 3000
    encoded = padded.encode("utf-16-le")
    n = len(padded)
    fib_len = 512
    clx_body = (
        b"\x01"
        + struct.pack("<I", 0)  # fc patched below
        + struct.pack("<H", 0)  # prm
        + struct.pack("<i", 0)  # cp start
        + struct.pack("<i", n)  # cp end
    )
    clx = b"\x02" + struct.pack("<I", len(clx_body)) + clx_body
    text_off = fib_len + len(clx)
    pad = b"\x00" if text_off % 2 else b""
    text_off += len(pad)
    fc = 0x40000000 | (text_off // 2)
    clx_body = (
        b"\x01"
        + struct.pack("<I", fc)
        + struct.pack("<H", 0)
        + struct.pack("<i", 0)
        + struct.pack("<i", n)
    )
    clx = b"\x02" + struct.pack("<I", len(clx_body)) + clx_body
    assert fib_len + len(clx) + len(pad) == text_off
    word_doc = bytearray(fib_len) + clx + pad + encoded
    assert len(word_doc) == text_off + len(encoded)
    assert len(word_doc) >= 4096, "keep the stream on regular FAT sectors"
    # --- Fib: nFib=0x00C1 (Word 97); fcClx/lcbClx at 0x01A2/0x01A6.
    struct.pack_into("<H", word_doc, 0, 0xA5EC)
    struct.pack_into("<H", word_doc, 2, 0x00C1)
    struct.pack_into("<I", word_doc, 0x01A2, fib_len)
    struct.pack_into("<I", word_doc, 0x01A6, len(clx))
    return _wrap_ole(bytes(word_doc))


def _wrap_ole(stream: bytes) -> bytes:
    """Wrap one WordDocument stream in a minimal 512-byte-sector OLE file."""
    import struct

    ENDOFCHAIN = 0xFFFFFFFE
    FREESECT = 0xFFFFFFFF
    FATSECT = 0xFFFFFFFD
    SECTOR = 512
    n_data = (len(stream) + SECTOR - 1) // SECTOR
    data = stream + b"\x00" * (n_data * SECTOR - len(stream))

    header = bytearray(SECTOR)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 0x0003)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 44, 1)  # csectFat
    struct.pack_into("<I", header, 48, 1)  # sectDirStart
    struct.pack_into("<I", header, 56, 0x1000)  # mini cutoff
    struct.pack_into("<I", header, 60, ENDOFCHAIN)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)
    struct.pack_into("<109I", header, 76, 0, *([FREESECT] * 108))

    entries = [FATSECT, ENDOFCHAIN] + list(range(3, 2 + n_data - 1)) + [ENDOFCHAIN]
    entries += [FREESECT] * (128 - len(entries))
    fat = struct.pack("<128I", *entries)

    def _dir_entry(name: str, typ: int, start: int, size: int, child: int) -> bytes:
        entry = bytearray(128)
        raw = name.encode("utf-16-le") + b"\x00\x00"
        entry[0 : len(raw)] = raw
        struct.pack_into("<H", entry, 64, len(raw))
        entry[66] = typ
        entry[67] = 1
        struct.pack_into("<i", entry, 68, -1)
        struct.pack_into("<i", entry, 72, -1)
        struct.pack_into("<i", entry, 76, child)
        struct.pack_into("<I", entry, 116, start if start >= 0 else 0xFFFFFFFF)
        struct.pack_into("<I", entry, 120, size)
        return bytes(entry)

    directory = (
        _dir_entry("Root Entry", 5, -1, 0, 1)
        + _dir_entry("WordDocument", 2, 2, len(stream), -1)
        + bytes(256)
    )
    return bytes(header) + fat + directory + data


async def test_reader_converts_docx_without_provider_call(tmp_path):
    from invoice_referee.domain.evidence import SourceRef
    from invoice_referee.evidence.artifacts import ArtifactStore
    from invoice_referee.evidence.reader import FileOcrReader
    from invoice_referee.evidence.trace import RunBudget

    class ExplodingProvider:
        async def ocr_file(self, *args, **kwargs):
            raise AssertionError("office docs must not reach the OCR provider")

    data = _mini_docx(("Tổng cộng: 900000",))
    source = SourceRef(
        id="source:docx",
        digest="d" * 64,
        tenant="tenant:demo",
        media="DOCX",
        storage_key="k",
    )
    result = await FileOcrReader(provider=ExplodingProvider()).read_source(
        source,
        budget=RunBudget(),
        artifacts=ArtifactStore(root=tmp_path / "a"),
        source_bytes=data,
    )
    assert result.pages, "converted pages must be present"
    assert result.provider == "local-office"
    assert "Tổng cộng: 900000" in result.pages[0].markdown


def test_media_literals_accept_office():
    from invoice_referee.domain.evidence import Media

    assert set(Media.__args__) >= {"PDF", "PNG", "JPEG", "DOC", "DOCX"}

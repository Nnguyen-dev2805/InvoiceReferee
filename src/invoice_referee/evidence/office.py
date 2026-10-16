"""Local Office text extraction (contracts §12.1; 17/10/2026 DOC/DOCX support).

Mistral OCR only accepts PDF/images, so Word documents are converted locally
to page text and wrapped as an `OcrSourceResult` with `provider="local-office"`
— never sent to a provider, never given fabricated word confidence (scores are
None, so the OCR-confidence gate honestly skips them). Quote provenance still
applies: every extracted value must quote an exact substring of these pages.

- DOCX: stdlib zip+xml (paragraphs + tables in document order). No new dependency.
- DOC (Word 97-2003): `olefile` + the spec piece table (Fib -> Clx -> pieces).
  Non-Word OLE containers and encrypted files raise OfficeError (a TECHNICAL
  problem downstream, never a silent empty read).
"""

from __future__ import annotations

import io
import struct
import zipfile

OFFICE_VERSION = "local-office-text-v1"


class OfficeError(RuntimeError):
    """A Word document could not be converted to text."""


def sniff_office(data: bytes) -> str | None:
    """Return "DOCX"/"DOC" from bytes, or None (content-based, not extension)."""
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as handle:
                names = set(handle.namelist())
                if "word/document.xml" in names:
                    return "DOCX"
        except zipfile.BadZipFile:
            pass
        return None
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "DOC"
    return None


def extract_office_pages(data: bytes, media: str) -> list[str]:
    """Extract page texts from Word bytes; raises OfficeError when unreadable."""
    if media == "DOCX":
        return _docx_pages(data)
    if media == "DOC":
        return _doc_pages(data)
    raise OfficeError(f"not an office document: {media}")


def _docx_pages(data: bytes) -> list[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        xml_bytes = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise OfficeError(f"cannot read word/document.xml: {error}") from error
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise OfficeError(f"word/document.xml is not valid XML: {error}") from error
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    pages: list[str] = []
    current: list[str] = []

    def flush() -> None:
        text = "\n".join(line for line in current if line.strip())
        if text.strip():
            pages.append(text)
        current.clear()

    for element in root.iter():
        tag = element.tag
        if tag == f"{namespace}lastRenderedPageBreak":
            flush()
        elif tag == f"{namespace}p":
            texts = [node.text or "" for node in element.iter(f"{namespace}t")]
            line = "".join(texts)
            # A table cell paragraph keeps its own line so rows stay readable.
            current.append(line)
        elif tag == f"{namespace}tr":
            current.append("")  # blank line between table rows
    flush()
    if not pages:
        raise OfficeError("no readable paragraphs in word/document.xml")
    return pages


def _doc_pages(data: bytes) -> list[str]:
    import olefile

    if not olefile.isOleFile(io.BytesIO(data)):
        raise OfficeError("not an OLE container")
    try:
        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            if not ole.exists("WordDocument"):
                raise OfficeError("OLE container has no WordDocument stream")
            with ole.openstream("WordDocument") as stream:
                blob = stream.read()
    except OSError as error:
        raise OfficeError(f"cannot open WordDocument stream: {error}") from error
    text = _word_document_text(blob)
    if not text.strip():
        raise OfficeError("no readable text in the WordDocument stream")
    # Legacy .doc has no page map: one page per ~45 non-empty lines.
    lines = [line for line in text.splitlines() if line.strip()]
    pages = ["\n".join(lines[index : index + 45]) for index in range(0, len(lines), 45)]
    return pages or [text]


def _word_document_text(blob: bytes) -> str:
    """Read text via the Fib piece table (MS-DOC Word 97-2003 layout).

    Fib (512 bytes here) -> fcClx/lcbClx (offsets depend on nFib) -> Clx ->
    Pcdt -> Pcd pieces (cp ranges + fc file offsets; bit 0x40000000 of fc
    marks uncompressed UTF-16LE, otherwise single-byte encoding).
    """
    if len(blob) < 512 or struct.unpack_from("<H", blob, 0)[0] != 0xA5EC:
        raise OfficeError("bad Word file header (wIdent != 0xA5EC)")
    n_fib = struct.unpack_from("<H", blob, 2)[0]
    # fcClx/lcbClx offset by nFib version (MS-DOC §2.2 FibRgFcLcb*).
    if n_fib >= 0x00D9:
        off_clx, off_lcb = 0x01A2, 0x01A6
    elif n_fib >= 0x00C1:
        off_clx, off_lcb = 0x01A2, 0x01A6
    else:
        raise OfficeError(f"unsupported Word version nFib=0x{n_fib:04X}")
    if len(blob) < off_lcb + 4:
        raise OfficeError("Word header too short for the Clx table locator")
    fc_clx, lcb_clx = struct.unpack_from("<II", blob, off_clx)
    if lcb_clx == 0 or fc_clx + lcb_clx > len(blob):
        raise OfficeError("empty or out-of-range Clx piece table")
    clx = blob[fc_clx : fc_clx + lcb_clx]
    if not clx or clx[0] != 0x02:
        raise OfficeError("Clx does not start with a Pcdt (0x02)")
    claimed = struct.unpack_from("<I", clx, 1)[0]
    cursor = 1 + 4
    end = 1 + 4 + claimed
    pieces: list[tuple[int, int, int, bool]] = []  # (cp_start, cp_end, fc, unicode)
    while cursor < end:
        if cursor >= len(clx):
            raise OfficeError("truncated piece table")
        kind = clx[cursor]
        cursor += 1
        if kind == 0x01:  # Pcd: fc(4) | prm(2) | cpStart(4) | cpEnd(4)
            if cursor + 14 > len(clx):
                raise OfficeError("truncated piece descriptor")
            fc_raw = struct.unpack_from("<I", clx, cursor)[0]
            cp_start, cp_end = struct.unpack_from("<ii", clx, cursor + 6)
            cursor += 14
            is_unicode = bool(fc_raw & 0x40000000)
            # Unicode pieces store byte_offset // 2; ansi pieces store byte offset.
            fc = (fc_raw & ~0x40000000) * 2 if is_unicode else fc_raw
            pieces.append((cp_start, cp_end, fc, is_unicode))
        elif kind == 0x02:  # nested Pcdt: lcb then recurse inline
            if cursor + 4 > len(clx):
                raise OfficeError("truncated nested piece table")
            nested = struct.unpack_from("<I", clx, cursor)[0]
            cursor += 4
            end = min(end, cursor + nested)
        else:
            raise OfficeError(f"unknown Clx entry 0x{kind:02X}")
    out: list[str] = []
    for _cp_start, cp_end, fc, is_unicode in pieces:
        length_chars = max(cp_end - _cp_start, 0)
        if is_unicode:
            raw = blob[fc : fc + length_chars * 2]
            chars = raw.decode("utf-16-le", errors="replace")
        else:
            raw = blob[fc : fc + length_chars]
            chars = raw.decode("cp1252", errors="replace")
        out.append(chars)
    text = "".join(out)
    # Word control codes (0x07 cell mark, 0x0D paragraph) become line breaks.
    return text.replace("\r\x07", "\n").replace("\x07", "\n").replace("\r", "\n")

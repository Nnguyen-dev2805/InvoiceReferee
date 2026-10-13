"""R1 document rendering: real PDFs whose visible text carries the facts.

Native text PDFs are drawn with ReportLab + the bundled NotoSans (Vietnamese
glyphs). A scan document is rendered to a bitmap and embedded as an image-only
page, so no text layer carries the amount (plan R1). Rendering returns logical
locators/digest/page/quote only — never Facts, money or permissions.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from du_lieu_kiem_thu.ho_so import DocumentSpec

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSans-Regular.ttf"
# A fixed producer date makes two builds of the same spec byte-identical
# (plan R1: deterministic dates/seed/metadata).
_FIXED_DATE = "20261013000000+0000"


def _register_font() -> str:
    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
    return "NotoSans"


def render_document(spec: DocumentSpec, out_dir: Path) -> Path:
    """Render one document into ``out_dir``; return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / spec.filename
    if spec.scan:
        _render_scan(spec, path)
    else:
        _render_text(spec, path)
    return path


def _render_text(spec: DocumentSpec, path: Path) -> None:
    font = _register_font()
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle(spec.role)
    c.setAuthor("InvoiceReferee synthetic")
    c.setSubject("invariant=1")
    c._doc.info.producer = "InvoiceReferee"
    c.setFont(font, 13)
    y = A4[1] - 70
    for line in spec.lines:
        c.drawString(60, y, line)
        y -= 26
    c.showPage()
    c.save()


def _render_scan(spec: DocumentSpec, path: Path) -> None:
    """Render the page, rasterize it, and embed it as an image-only PDF page."""
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader

    font = _register_font()
    # 1. Draw the source page to a temporary text PDF (never shipped).
    tmp = path.with_suffix(".src.pdf")
    c = canvas.Canvas(str(tmp), pagesize=A4, invariant=1)
    c._doc.info.producer = "InvoiceReferee"
    c.setFont(font, 15)
    y = A4[1] - 80
    for line in spec.lines:
        c.drawString(60, y, line)
        y -= 30
    c.showPage()
    c.save()

    # 2. Rasterize and re-embed so the shipped file has no text layer.
    pdf = pdfium.PdfDocument(str(tmp))
    bitmap = pdf[0].render(scale=2.0)
    image = bitmap.to_pil()
    img_path = path.with_suffix(".png")
    image.save(img_path, "PNG")

    c2 = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c2._doc.info.producer = "InvoiceReferee"
    c2.drawImage(ImageReader(str(img_path)), 0, 0, width=A4[0], height=A4[1])
    c2.showPage()
    c2.save()

    tmp.unlink(missing_ok=True)
    img_path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

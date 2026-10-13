"""Build the 4 M0 baseline inputs (plan T5): text / clear scan / unclear scan / non-doc.

Each is a real file the M0 runner reads once. They live under .runtime/evidence
(ignored), not the repo, because they are local measurement fixtures.
"""

from __future__ import annotations

import io
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"


def _text_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("NotoSans", 12)
    c.drawString(60, A4[1] - 60, "HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    c.drawString(60, A4[1] - 90, "Đơn vị: Công ty Demo")
    c.drawString(60, A4[1] - 120, "Số tiền: 3.000.000 VND")
    c.showPage()
    c.save()


def _render_png(pdf_path: Path, png_path: Path, scale: float, *, blur: bool = False) -> None:
    import pypdfium2 as pdfium
    from PIL import ImageFilter

    pdf = pdfium.PdfDocument(str(pdf_path))
    image = pdf[0].render(scale=scale).to_pil()
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=2))
    image.save(png_path, "PNG")


def _scan_pdf(path: Path, *, unclear: bool = False) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    tmp_pdf = path.with_suffix(".src.pdf")
    tmp_png = path.with_suffix(".png")
    _text_pdf(tmp_pdf)
    _render_png(tmp_pdf, tmp_png, scale=1.0 if unclear else 2.0, blur=unclear)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(ImageReader(str(tmp_png)), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()
    tmp_pdf.unlink(missing_ok=True)
    tmp_png.unlink(missing_ok=True)


def _non_document(path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 50, 750, 550], outline="black", width=3)
    draw.text((300, 300), "anh gia dinh", fill="black")
    image.save(path, "PNG")


def main() -> int:
    out = PROJECT_ROOT / ".runtime" / "evidence" / "m0" / "inputs"
    out.mkdir(parents=True, exist_ok=True)
    _text_pdf(out / "text.pdf")
    _scan_pdf(out / "clear_scan.pdf", unclear=False)
    _scan_pdf(out / "unclear_scan.pdf", unclear=True)
    _non_document(out / "non_document.png")
    for f in sorted(out.iterdir()):
        print(f"{f.name}: {f.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

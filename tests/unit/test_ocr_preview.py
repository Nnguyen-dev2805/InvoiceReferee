from pathlib import Path

from PIL import Image
import pymupdf

from app.web.ocr_preview import BOX_COLOR, render_ocr_block_preview


def test_render_ocr_block_preview_draws_requested_region(tmp_path: Path) -> None:
    source = tmp_path / "bill.png"
    Image.new("RGB", (200, 200), "white").save(source)

    preview = render_ocr_block_preview(
        source,
        page_index=0,
        bounding_box={
            "top_left_x": 25,
            "top_left_y": 25,
            "bottom_right_x": 75,
            "bottom_right_y": 75,
        },
        ocr_width=100,
        ocr_height=100,
    )

    assert preview.size == (200, 200)
    assert preview.getpixel((50, 50)) == BOX_COLOR[:3]
    assert preview.getpixel((150, 150)) == BOX_COLOR[:3]
    assert preview.getpixel((10, 190)) == (255, 255, 255)


def test_render_ocr_block_preview_supports_pdf_pages(tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=300)
        page.insert_text((20, 30), "Invoice total 2,500,000")
        document.save(source)

    preview = render_ocr_block_preview(
        source,
        page_index=0,
        bounding_box={
            "top_left_x": 10,
            "top_left_y": 10,
            "bottom_right_x": 90,
            "bottom_right_y": 30,
        },
        ocr_width=100,
        ocr_height=150,
    )

    assert preview.width == 400
    assert preview.height == 600
    assert preview.getpixel((40, 40)) == BOX_COLOR[:3]

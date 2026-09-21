from pathlib import Path

from PIL import Image, ImageColor

from app.components.bbox_overlay import GOOD_COLOR, LOW_COLOR, render_bbox_overlay


def test_render_bbox_overlay_scales_boxes_and_colors_by_confidence(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "invoice.png"
    Image.new("RGB", (200, 400), "white").save(image_path)
    page = {
        "dimensions": {"width": 100, "height": 200},
        "blocks": [
            {
                "bounding_box": {
                    "top_left_x": 10,
                    "top_left_y": 20,
                    "bottom_right_x": 40,
                    "bottom_right_y": 50,
                },
                "mapping": {"status": "exact"},
                "confidence": {"minimum": 0.95},
            },
            {
                "bounding_box": {
                    "top_left_x": 50,
                    "top_left_y": 60,
                    "bottom_right_x": 90,
                    "bottom_right_y": 90,
                },
                "mapping": {"status": "exact"},
                "confidence": {"minimum": 0.40},
            },
        ],
    }

    overlay = render_bbox_overlay(image_path, page)

    assert overlay.size == (200, 400)
    assert overlay.getpixel((20, 40)) == ImageColor.getrgb(GOOD_COLOR)
    assert overlay.getpixel((100, 120)) == ImageColor.getrgb(LOW_COLOR)

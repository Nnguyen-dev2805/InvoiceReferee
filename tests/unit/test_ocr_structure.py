from invoice_referee.extraction import (
    bbox_from_any,
    merge_ocr_structure_page,
    normalize_paddle_ocr_page,
    normalize_paddle_structure_page,
)


def test_bbox_from_polygon() -> None:
    assert bbox_from_any([[10, 20], [80, 18], [82, 42], [9, 45]]) == (
        9.0,
        18.0,
        82.0,
        45.0,
    )


def test_normalizers_convert_paddle_results() -> None:
    ocr_regions = normalize_paddle_ocr_page(
        {
            "res": {
                "rec_texts": ["Tổng thanh toán", "85.773.600"],
                "rec_scores": [0.98, 0.91],
                "rec_boxes": [[110, 210, 400, 250], [650, 210, 850, 250]],
            }
        },
        page_index=0,
    )
    blocks = normalize_paddle_structure_page(
        {
            "res": {
                "parsing_res_list": [
                    {
                        "block_bbox": [100, 200, 900, 280],
                        "block_label": "text",
                        "block_content": "Tổng thanh toán: 85.773.600",
                        "block_order": 3,
                    }
                ],
                "layout_det_res": {
                    "boxes": [
                        {
                            "label": "text",
                            "score": 0.97,
                            "coordinate": [100, 200, 900, 280],
                        }
                    ]
                },
            }
        },
        page_index=0,
    )

    assert ocr_regions[1]["confidence"] == 0.91
    assert ocr_regions[1]["confidence_scope"] == "text_region"
    assert blocks[0]["type"] == "text"
    assert blocks[0]["layout_confidence"] == 0.97
    assert blocks[0]["reading_order"] == 3


def test_structure_normalizer_accepts_layout_detection_result() -> None:
    blocks = normalize_paddle_structure_page(
        {
            "res": {
                "boxes": [
                    {
                        "label": "table",
                        "score": 0.94,
                        "coordinate": [20, 30, 400, 500],
                    }
                ]
            }
        },
        page_index=2,
    )

    assert blocks == [
        {
            "id": "page-2-block-0",
            "type": "table",
            "bbox": [20.0, 30.0, 400.0, 500.0],
            "reading_order": 0,
            "vl_content": "",
            "layout_confidence": 0.94,
            "source": "PP_DOC_LAYOUT_V3",
        }
    ]


def test_merge_assigns_regions_and_aggregates_confidence() -> None:
    page = merge_ocr_structure_page(
        page_index=0,
        width=1000,
        height=1400,
        ocr_regions=[
            {
                "id": "r1",
                "text": "Tổng thanh toán:",
                "bbox": [110, 210, 400, 250],
                "confidence": 0.98,
            },
            {
                "id": "r2",
                "text": "85.773.600",
                "bbox": [650, 210, 850, 250],
                "confidence": 0.91,
            },
        ],
        structure_blocks=[
            {
                "id": "block_01",
                "type": "text",
                "bbox": [100, 200, 900, 280],
                "reading_order": 1,
                "vl_content": "Tổng thanh toán: 85.773.600",
                "layout_confidence": 0.97,
            }
        ],
    )

    block = page["blocks"][0]
    assert block["text"] == "Tổng thanh toán:\n85.773.600"
    assert block["text_source"] == "PP_OCR"
    assert block["block_confidence"] == 0.91
    assert block["confidence"]["low_region_count"] == 0
    assert block["mapping"]["status"] == "matched"
    assert page["unmatched_ocr_regions"] == []


def test_merge_marks_ambiguous_unmatched_and_numeric_conflict() -> None:
    page = merge_ocr_structure_page(
        page_index=0,
        width=1000,
        height=1400,
        ocr_regions=[
            {
                "id": "ambiguous",
                "text": "Tổng: 100.000",
                "bbox": [80, 110, 280, 150],
                "confidence": 0.81,
            },
            {
                "id": "outside",
                "text": "Ngoài block",
                "bbox": [700, 700, 850, 740],
                "confidence": 0.99,
            },
        ],
        structure_blocks=[
            {
                "id": "block_01",
                "type": "text",
                "bbox": [100, 100, 200, 180],
                "reading_order": 1,
                "vl_content": "Tổng: 200.000",
            }
        ],
    )

    block = page["blocks"][0]
    assert block["mapping"]["status"] == "ambiguous"
    assert block["confidence"]["low_region_count"] == 1
    assert block["content_comparison"]["numeric_conflict"] is True
    assert page["unmatched_ocr_regions"][0]["id"] == "outside"


def test_merge_falls_back_to_ocr_regions_without_structure() -> None:
    page = merge_ocr_structure_page(
        page_index=1,
        width=500,
        height=800,
        ocr_regions=[
            {
                "id": "r1",
                "text": "Phiếu thu",
                "bbox": [10, 20, 150, 50],
                "confidence": 0.96,
            }
        ],
        structure_blocks=[],
    )

    assert page["blocks"][0]["text"] == "Phiếu thu"
    assert page["blocks"][0]["mapping"]["status"] == "matched"
    assert page["warnings"] == [{"code": "STRUCTURE_FALLBACK_USED"}]

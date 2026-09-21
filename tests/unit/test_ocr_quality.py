from invoice_referee.extraction import collect_low_confidence_blocks


def test_collects_diverse_bill_labels_without_hardcoded_keywords() -> None:
    hierarchy = {
        "pages": [
            {
                "page_index": 0,
                "blocks": [
                    {
                        "block_id": "page-0-block-0",
                        "type": "text",
                        "content": "Grand Total: 1,200,000",
                        "bounding_box": {"top_left_x": 1},
                        "mapping": {"status": "exact"},
                        "confidence": {"minimum": 0.62},
                        "words": [
                            {"text": "Grand", "confidence": 0.96},
                            {"text": " Total", "confidence": 0.94},
                            {"text": " 1,200,000", "confidence": 0.62},
                        ],
                    },
                    {
                        "block_id": "page-0-block-1",
                        "type": "text",
                        "content": "Khách phải trả: 1.200.000đ",
                        "bounding_box": {},
                        "mapping": {"status": "exact"},
                        "confidence": {"minimum": 0.71},
                        "words": [
                            {"text": "Khách phải trả", "confidence": 0.97},
                            {"text": " 1.200.000đ", "confidence": 0.71},
                        ],
                    },
                ],
            }
        ]
    }

    candidates = collect_low_confidence_blocks(
        hierarchy,
        evidence_id="EV-BILL-001",
    )

    assert [candidate["block_id"] for candidate in candidates] == [
        "page-0-block-0",
        "page-0-block-1",
    ]
    assert candidates[0]["candidate_id"] == "EV-BILL-001:page-0-block-0"
    assert candidates[0]["next_block"]["block_id"] == "page-0-block-1"
    assert candidates[1]["previous_block"]["block_id"] == "page-0-block-0"


def test_ignores_low_confidence_formatting_tokens() -> None:
    hierarchy = {
        "pages": [
            {
                "page_index": 0,
                "blocks": [
                    {
                        "block_id": "page-0-block-0",
                        "type": "title",
                        "content": "### HÓA ĐƠN",
                        "words": [
                            {"text": "###", "confidence": 0.20},
                            {"text": "\n", "confidence": 0.10},
                            {"text": " HÓA ĐƠN", "confidence": 0.98},
                        ],
                    }
                ],
            }
        ]
    }

    assert collect_low_confidence_blocks(
        hierarchy,
        evidence_id="EV-001",
    ) == []

from invoice_referee.extraction import restructure_mistral_ocr


def _word(text: str, confidence: float, start_index: int) -> dict:
    return {
        "text": text,
        "confidence": confidence,
        "logprob": 0,
        "startIndex": start_index,
    }


def test_restructure_maps_contiguous_words_to_exact_block() -> None:
    payload = {
        "index": 0,
        "dimensions": {"dpi": 200, "width": 100, "height": 200},
        "confidenceScores": {
            "wordConfidenceScores": [
                _word("#", 0.99, 0),
                _word(" HÓA", 0.95, 1),
                _word(" ĐƠN", 0.80, 5),
            ],
            "averagePageConfidenceScore": 0.91,
            "minimumPageConfidenceScore": 0.80,
        },
        "blocks": [
            {
                "topLeftX": 1,
                "topLeftY": 2,
                "bottomRightX": 50,
                "bottomRightY": 20,
                "content": "# HÓA ĐƠN",
                "confidenceScores": None,
                "type": "title",
            }
        ],
    }

    result = restructure_mistral_ocr(payload)

    page = result["pages"][0]
    block = page["blocks"][0]
    assert block["mapping"] == {
        "status": "exact",
        "method": "sequential_text_alignment",
        "coverage": 1.0,
    }
    assert [word["text"] for word in block["words"]] == ["#", " HÓA", " ĐƠN"]
    assert block["confidence"]["word_count"] == 2
    assert block["confidence"]["minimum"] == 0.80
    assert block["confidence"]["review_word_count"] == 1
    assert page["unassigned_words"] == []


def test_restructure_normalizes_whitespace_and_maps_table_reference() -> None:
    payload = {
        "index": 2,
        "dimensions": {},
        "confidenceScores": {
            "wordConfidenceScores": [
                _word("Tên", 0.92, 0),
                _word("  công", 0.88, 3),
                _word(" ty", 0.97, 9),
                _word("[tbl-0.md](tbl-0.md)", 0.96, 12),
            ]
        },
        "blocks": [
            {
                "content": "Tên công ty",
                "type": "text",
                "topLeftX": 0,
                "topLeftY": 0,
                "bottomRightX": 10,
                "bottomRightY": 10,
            },
            {
                "content": "| Mục | Thành tiền |",
                "type": "table",
                "tableId": "tbl-0.md",
                "topLeftX": 0,
                "topLeftY": 11,
                "bottomRightX": 10,
                "bottomRightY": 20,
            },
        ],
    }

    page = restructure_mistral_ocr(payload)["pages"][0]

    assert page["blocks"][0]["mapping"]["status"] == "normalized"
    table = page["blocks"][1]
    assert table["mapping"]["status"] == "table_reference"
    assert table["words"] == []
    assert table["references"][0]["text"] == "[tbl-0.md](tbl-0.md)"
    assert table["confidence"]["average"] == 0.96
    assert page["unassigned_words"] == []


def test_restructure_marks_partial_and_unmatched_content() -> None:
    payload = {
        "response": {
            "pages": [
                {
                    "index": 0,
                    "confidence_scores": {
                        "word_confidence_scores": [
                            {
                                "text": "Khach san",
                                "confidence": 0.91,
                                "start_index": 0,
                            },
                            {
                                "text": " con lai",
                                "confidence": 0.82,
                                "start_index": 10,
                            },
                        ]
                    },
                    "blocks": [
                        {"content": "Khách san", "type": "text"},
                        {"content": "Không xuất hiện", "type": "text"},
                    ],
                }
            ]
        }
    }

    page = restructure_mistral_ocr(payload)["pages"][0]

    assert page["blocks"][0]["mapping"]["status"] == "partial"
    assert page["blocks"][1]["mapping"]["status"] == "unmatched"
    warning_codes = {warning["code"] for warning in page["warnings"]}
    assert "BLOCK_PARTIALLY_MATCHED" in warning_codes
    assert "BLOCK_NOT_MATCHED" in warning_codes
    assert "UNASSIGNED_WORDS" in warning_codes

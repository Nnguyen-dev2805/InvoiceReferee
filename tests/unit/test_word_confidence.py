from invoice_referee.extraction import (
    confidence_level,
    extract_word_confidence_rows,
)


def test_extract_word_confidence_rows_flattens_pages() -> None:
    result = {
        "response": {
            "pages": [
                {
                    "confidence_scores": {
                        "word_confidence_scores": [
                            {"text": "Tong", "confidence": 0.98, "start_index": 0},
                            {"text": "tien", "confidence": 0.62, "start_index": 5},
                        ]
                    }
                },
                {
                    "confidence_scores": {
                        "word_confidence_scores": [
                            {"text": "VAT", "confidence": 0.81, "start_index": 0}
                        ]
                    }
                },
            ]
        }
    }

    assert extract_word_confidence_rows(result) == [
        {
            "page": 1,
            "text": "Tong",
            "confidence": 0.98,
            "start_index": 0,
            "level": "good",
        },
        {
            "page": 1,
            "text": "tien",
            "confidence": 0.62,
            "start_index": 5,
            "level": "low",
        },
        {
            "page": 2,
            "text": "VAT",
            "confidence": 0.81,
            "start_index": 0,
            "level": "review",
        },
    ]


def test_confidence_level_uses_review_thresholds() -> None:
    assert confidence_level(0.69) == "low"
    assert confidence_level(0.70) == "review"
    assert confidence_level(0.84) == "review"
    assert confidence_level(0.85) == "good"


def test_extract_word_confidence_rows_handles_old_results() -> None:
    result = {"response": {"pages": [{"markdown": "No word scores"}]}}

    assert extract_word_confidence_rows(result) == []

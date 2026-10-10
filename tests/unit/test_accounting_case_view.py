from app.web.routes import _decorate_accounting_case


class _OcrRepository:
    def load_ocr_artifact(self, _case_id: str, _document_id: str):
        return {
            "provider": "mistral",
            "response": {
                "pages": [
                    {
                        "index": 0,
                        "dimensions": {"width": 1000, "height": 2000},
                        "confidence_scores": {
                            "word_confidence_scores": [
                                {
                                    "text": "Tổng thanh toán: ",
                                    "confidence": 0.99,
                                    "start_index": 0,
                                },
                                {
                                    "text": "2.500.00O",
                                    "confidence": 0.61,
                                    "start_index": 17,
                                },
                            ]
                        },
                        "blocks": [
                            {
                                "type": "text",
                                "content": "Tổng thanh toán: 2.500.00O",
                                "top_left_x": 500,
                                "top_left_y": 1500,
                                "bottom_right_x": 900,
                                "bottom_right_y": 1600,
                            }
                        ],
                    }
                ]
            },
        }


def test_accounting_case_resolves_ocr_block_as_annotated_evidence() -> None:
    case = {
        "case_id": "SET-VIEW-001",
        "documents": [
            {
                "document_id": "DOC-001",
                "role": "EXPENSE_EVIDENCE",
                "linked_item_id": "ITEM-001",
                "original_name": "bill.png",
                "mime_type": "image/png",
            }
        ],
        "expense_items": [
            {"item_id": "ITEM-001", "description": "Tiếp khách"}
        ],
        "findings": [
            {
                "rule_id": "SET_QUALITY_001",
                "status": "FAIL",
                "source_refs": ["DOC:DOC-001:page-0-block-0"],
            },
            {
                "rule_id": "SET_CONTEXT_001",
                "status": "PASS",
                "source_refs": [],
            },
            {
                "rule_id": "SET_LIMIT_001",
                "status": "WARN",
                "source_refs": [],
            },
            {
                "rule_id": "SET_EXTRACTION_001",
                "status": "ERROR",
                "source_refs": [],
            },
        ],
        "decision": {
            "source_refs": ["DOC:DOC-001:page-0-block-0"]
        },
    }

    decorated = _decorate_accounting_case(case, _OcrRepository())

    preview = decorated["findings"][0]["evidence_previews"][0]
    assert preview["excerpt"] == "Tổng thanh toán: 2.500.00O"
    assert preview["low_words"] == [
        {"text": "2.500.00O", "confidence": 0.61}
    ]
    assert "left:50.000%" in preview["annotation_style"]
    assert "top:75.000%" in preview["annotation_style"]
    assert decorated["expense_items"][0]["documents"][0]["document_id"] == (
        "DOC-001"
    )
    assert [
        finding["status"] for finding in decorated["attention_findings"]
    ] == ["ERROR", "FAIL", "WARN"]
    assert [finding["status"] for finding in decorated["passed_findings"]] == [
        "PASS"
    ]

from types import SimpleNamespace

import pytest

from invoice_referee.extraction import KimiReasoningAdapter, KimiResponseError


class FakeCompletions:
    def __init__(self, *contents: str, finish_reason: str = "stop") -> None:
        self.contents = list(contents)
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason=self.finish_reason,
                )
            ]
        )


class FlakyCompletions(FakeCompletions):
    def __init__(self, *contents: str) -> None:
        super().__init__(*contents)
        self.attempts = 0

    def create(self, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            raise OSError(10013, "socket access forbidden")
        return super().create(**kwargs)


CONFIDENCE_JSON = """{
  "block_assessments": [
    {
      "candidate_id": "EV-001:page-0-block-4",
      "importance": "CRITICAL",
      "quality_state": "UNCERTAIN",
      "review_action": "ASK_HUMAN",
      "requires_verification": true,
      "canonical_fields": ["total_amount"],
      "observed_text": "2.442.960đ",
      "semantic_category": null,
      "reason": "Giá trị có confidence thấp.",
      "human_question": "Vui lòng xác nhận tổng thanh toán."
    }
  ]
}"""

CONFLICT_JSON = """{
  "applicability": "NOT_APPLICABLE",
  "applicability_reason": "Bill dịch vụ không phát sinh nhập kho.",
  "document_facts": [],
  "text_report": null,
  "suggested_item_matches": [],
  "comparisons": [],
  "potential_conflicts": [],
  "extraction_warnings": []
}"""

INVALID_CONFLICT_JSON = """{
  "applicability": "APPLICABLE",
  "applicability_reason": "Có hóa đơn và phiếu nhập kho.",
  "document_facts": [],
  "text_report": null,
  "suggested_item_matches": [],
  "comparisons": [],
  "potential_conflicts": [
    {
      "conflict_id": "CONF-001",
      "description": "Chưa rõ trạng thái nhận hàng.",
      "source_refs": ["EV-REPORT"],
      "human_question": "Lô hàng đã được nhận đủ chưa?"
    }
  ],
  "extraction_warnings": []
}"""

PAPER_SETTLEMENT_JSON = """{
  "document_id": "DOC-FORM",
  "document_type": "PAPER_SETTLEMENT_REQUEST",
  "purpose": "Chi phí ăn trưa Kiều Hoa Quán",
  "total_amount": 3314780,
  "advance_amount": 4000000,
  "reimbursement_amount": 685220,
  "beneficiary_name": "HỨA THỊ NGHĨA",
  "bank_account_number": "0123456789",
  "bank_name": "Ngân hàng Demo",
  "lines": [
    {
      "line_id": "LINE-001",
      "description": "Chi phí ăn trưa Kiều Hoa Quán",
      "invoice_refs": ["HQ54201", "KHQ54202"],
      "amount": 3314780,
      "note": "Đính kèm bảng kê",
      "requires_evidence": true,
      "no_evidence_reason": null,
      "source_refs": ["DOC:DOC-FORM"]
    }
  ],
  "source_refs": ["DOC:DOC-FORM"],
  "extraction_warnings": []
}"""

EXPENSE_DOCUMENT_JSON = """{
  "document_id": "DOC-RECEIPT",
  "document_type": "PAPER_RECEIPT",
  "classification_confidence": 0.97,
  "classification_signals": ["Có tên cửa hàng, ngày và tổng thanh toán"],
  "alternative_document_types": [],
  "issuer_name": "Nhà hàng Demo",
  "issuer_tax_code": null,
  "buyer_name": null,
  "buyer_tax_code": null,
  "document_number": null,
  "template_number": null,
  "serial_number": null,
  "document_date": "2026-10-10",
  "subtotal": null,
  "discount": null,
  "tax": null,
  "service_charge": null,
  "total_amount": 450000,
  "payment_method": "Tiền mặt",
  "payer_name": null,
  "payee_name": null,
  "transaction_reference": null,
  "transaction_status": null,
  "confirmation_present": null,
  "line_items": [],
  "field_states": {
    "issuer_name": "PRESENT",
    "document_date": "PRESENT",
    "total_amount": "PRESENT",
    "buyer_tax_code": "NOT_APPLICABLE"
  },
  "source_refs": ["DOC:DOC-RECEIPT"],
  "extraction_warnings": []
}"""


def build_adapter(completions: FakeCompletions) -> KimiReasoningAdapter:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return KimiReasoningAdapter(
        token="token",
        secret="secret",
        base_url="https://example.test/v1",
        client=client,
    )


def test_kimi_adapter_retries_transient_windows_socket_error() -> None:
    completions = FlakyCompletions(CONFIDENCE_JSON)
    adapter = build_adapter(completions)
    adapter.retry_delays = (0,)

    result = adapter.analyze_confidence({"evidence": {}})

    assert completions.attempts == 2
    assert result.block_assessments[0].quality_state == "UNCERTAIN"


def test_confidence_agent_uses_its_dedicated_prompt() -> None:
    completions = FakeCompletions(CONFIDENCE_JSON)
    adapter = build_adapter(completions)

    confidence = adapter.analyze_confidence({"evidence": {}})

    assert confidence.document_types == {}
    assert confidence.block_assessments[0].review_action == "ASK_HUMAN"
    assert len(completions.calls) == 1
    prompt = completions.calls[0]["messages"][0]["content"]
    assert "Confidence Quality Agent" in prompt
    assert "Missing Value Agent" not in prompt
    assert "MỘT evidence" in prompt
    assert "requires_verification" in prompt
    assert "KHÔNG được sử dụng business context" in prompt
    assert "Không dùng DEFER_TO_POLICY" in prompt
    assert "Không đưa candidate_id" in prompt
    assert completions.calls[0]["extra_body"] == {"reasoning_effort": "low"}
    assert completions.calls[0]["max_tokens"] == 8192


def test_adapter_finds_schema_json_after_surrounding_text() -> None:
    completions = FakeCompletions(
        f"Phân tích có ký hiệu {{không phải JSON}}.\n{CONFIDENCE_JSON}\nĐã xong."
    )
    adapter = build_adapter(completions)

    result = adapter.analyze_confidence({"evidence": {}})

    assert result.block_assessments[0].quality_state == "UNCERTAIN"
    assert len(completions.calls) == 1


def test_adapter_retries_confidence_once_for_truncated_json() -> None:
    completions = FakeCompletions('{"document_types":', CONFIDENCE_JSON)
    adapter = build_adapter(completions)

    result = adapter.analyze_confidence({"evidence": {}})

    assert result.block_assessments[0].canonical_fields == ["total_amount"]
    assert len(completions.calls) == 2
    assert "không thể được hệ thống đọc" in completions.calls[1]["messages"][-1]["content"]


def test_adapter_sends_specific_conflict_schema_errors_to_repair() -> None:
    completions = FakeCompletions(INVALID_CONFLICT_JSON, CONFLICT_JSON)
    adapter = build_adapter(completions)

    result = adapter.analyze_conflict({"documents": []})

    assert result.applicability == "NOT_APPLICABLE"
    assert len(completions.calls) == 2
    repair_prompt = completions.calls[1]["messages"][-1]["content"]
    assert "potential_conflicts.0.code" in repair_prompt
    assert "potential_conflicts.0.field" in repair_prompt
    assert "Field required" in repair_prompt


def test_adapter_fails_closed_after_two_invalid_responses() -> None:
    completions = FakeCompletions("không có JSON", "vẫn không có JSON")
    adapter = build_adapter(completions)

    with pytest.raises(KimiResponseError) as error:
        adapter.analyze_confidence({"evidence": {}})

    assert error.value.stage == "Confidence Quality Agent"
    assert len(error.value.diagnostics) == 2
    assert "finish_reason=stop" in str(error.value)


def test_conflict_agent_receives_all_sources_and_uses_dedicated_prompt() -> None:
    completions = FakeCompletions(CONFLICT_JSON)
    adapter = build_adapter(completions)
    payload = {
        "business_context": {"description": "Đã nhận đủ 10 máy tính."},
        "documents": [
            {"evidence_id": "EV-BILL", "role": "PRIMARY_DOCUMENT"},
            {"evidence_id": "EV-REPORT", "role": "SUPPORTING_DOCUMENT"},
        ],
    }

    result = adapter.analyze_conflict(payload)

    assert result.applicability == "NOT_APPLICABLE"
    assert len(completions.calls) == 1
    messages = completions.calls[0]["messages"]
    assert "Cross-source Conflict Agent" in messages[0]["content"]
    assert "không kiểm tra confidence OCR" in messages[0]["content"]
    assert "document_facts" in messages[0]["content"]
    assert "Luôn trả text_report=null" in messages[0]["content"]
    assert "business_context chỉ" in messages[0]["content"]
    assert "không phải chứng từ hay nguồn kiểm kê" in messages[0]["content"]
    assert "Không dùng\n  EMPLOYEE_CLAIM" in messages[0]["content"]
    assert "Không dùng conflict_id" in messages[0]["content"]
    assert '"code":"RECEIPT_STATUS_CONFLICT"' in messages[0]["content"]
    assert '"field":"receipt_status"' in messages[0]["content"]
    assert "potential_conflicts=[]" in messages[0]["content"]
    assert '"EV-BILL"' in messages[1]["content"]
    assert '"EV-REPORT"' in messages[1]["content"]
    assert '"business_context"' in messages[1]["content"]


def test_paper_settlement_extractor_keeps_rows_and_evidence_requirement() -> None:
    completions = FakeCompletions(PAPER_SETTLEMENT_JSON)
    adapter = build_adapter(completions)

    result = adapter.extract_paper_settlement(
        {"document_id": "DOC-FORM", "ocr_text": "Giấy đề nghị hoàn ứng"}
    )

    assert result.lines[0].invoice_refs == ["HQ54201", "KHQ54202"]
    assert result.lines[0].requires_evidence is True
    assert result.bank_account_number == "0123456789"
    assert result.beneficiary_name == "HỨA THỊ NGHĨA"
    prompt = completions.calls[0]["messages"][0]["content"]
    assert "Paper Settlement Form" in prompt
    assert "Extraction Agent" in prompt
    assert 'requires_evidence=true' in prompt
    assert "bank_account_number" in prompt
    assert "không ghép evidence" in prompt


def test_expense_extractor_classifies_document_without_using_filename() -> None:
    completions = FakeCompletions(EXPENSE_DOCUMENT_JSON)
    adapter = build_adapter(completions)

    result = adapter.extract_expense_document(
        {
            "document_id": "DOC-RECEIPT",
            "filename": "scan-001.jpg",
            "ocr_text": "Nhà hàng Demo - Tổng thanh toán 450.000",
        }
    )

    assert result.document_type == "PAPER_RECEIPT"
    assert result.classification_confidence == 0.97
    assert result.field_states["buyer_tax_code"] == "NOT_APPLICABLE"
    prompt = completions.calls[0]["messages"][0]["content"]
    assert "không dựa vào tên file" in prompt
    assert "PAYMENT_PROOF" in prompt
    assert "classification_signals" in prompt

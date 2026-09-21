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


CONFIDENCE_JSON = """{
  "document_types": {"EV-001": "PAPER_RECEIPT"},
  "block_assessments": [
    {
      "candidate_id": "EV-001:page-0-block-4",
      "importance": "CRITICAL",
      "quality_state": "UNCERTAIN",
      "review_action": "ASK_HUMAN",
      "canonical_fields": ["total_amount"],
      "observed_text": "2.442.960đ",
      "semantic_category": null,
      "reason": "Giá trị có confidence thấp.",
      "human_question": "Vui lòng xác nhận tổng thanh toán."
    }
  ]
}"""


def build_adapter(completions: FakeCompletions) -> KimiReasoningAdapter:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return KimiReasoningAdapter(
        token="token",
        secret="secret",
        base_url="https://example.test/v1",
        client=client,
    )


def test_confidence_agent_uses_its_dedicated_prompt() -> None:
    completions = FakeCompletions(CONFIDENCE_JSON)
    adapter = build_adapter(completions)

    confidence = adapter.analyze_confidence({"documents": []})

    assert confidence.document_types["EV-001"] == "PAPER_RECEIPT"
    assert confidence.block_assessments[0].review_action == "ASK_HUMAN"
    assert len(completions.calls) == 1
    prompt = completions.calls[0]["messages"][0]["content"]
    assert "Confidence Quality Agent" in prompt
    assert "Missing Value Agent" not in prompt
    assert "DEFER_TO_POLICY" in prompt
    assert "Không đưa candidate_id" in prompt
    assert completions.calls[0]["extra_body"] == {"reasoning_effort": "low"}
    assert completions.calls[0]["max_tokens"] == 8192


def test_adapter_finds_schema_json_after_surrounding_text() -> None:
    completions = FakeCompletions(
        f"Phân tích có ký hiệu {{không phải JSON}}.\n{CONFIDENCE_JSON}\nĐã xong."
    )
    adapter = build_adapter(completions)

    result = adapter.analyze_confidence({"documents": []})

    assert result.block_assessments[0].quality_state == "UNCERTAIN"
    assert len(completions.calls) == 1


def test_adapter_retries_confidence_once_for_truncated_json() -> None:
    completions = FakeCompletions('{"document_types":', CONFIDENCE_JSON)
    adapter = build_adapter(completions)

    result = adapter.analyze_confidence({"documents": []})

    assert result.block_assessments[0].canonical_fields == ["total_amount"]
    assert len(completions.calls) == 2
    assert "không thể được hệ thống đọc" in completions.calls[1]["messages"][-1]["content"]


def test_adapter_fails_closed_after_two_invalid_responses() -> None:
    completions = FakeCompletions("không có JSON", "vẫn không có JSON")
    adapter = build_adapter(completions)

    with pytest.raises(KimiResponseError) as error:
        adapter.analyze_confidence({"documents": []})

    assert error.value.stage == "Confidence Quality Agent"
    assert len(error.value.diagnostics) == 2
    assert "finish_reason=stop" in str(error.value)

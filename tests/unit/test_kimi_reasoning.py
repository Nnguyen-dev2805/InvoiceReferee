from types import SimpleNamespace

from invoice_referee.extraction import KimiReasoningAdapter


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self.content))
            ]
        )


def test_kimi_adapter_calls_model_once_and_parses_json() -> None:
    completions = FakeCompletions(
        """```json
        {
          "business_context_present": true,
          "conflict_detected": false,
          "summary": "Đủ dữ liệu",
          "reasoning": "Bill phù hợp với nội dung đề nghị.",
          "conflicts": []
        }
        ```"""
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    adapter = KimiReasoningAdapter(
        token="token",
        secret="secret",
        base_url="https://example.test/v1",
        client=client,
    )

    result = adapter.analyze({"case_id": "CASE-001", "documents": []})

    assert result.business_context_present is True
    assert result.conflict_detected is False
    assert len(completions.calls) == 1
    assert "reasoning_effort" not in completions.calls[0]

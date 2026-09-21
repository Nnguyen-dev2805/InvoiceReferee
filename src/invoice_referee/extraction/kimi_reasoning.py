"""Kimi adapter for one-shot case extraction and reasoning."""

from __future__ import annotations

import json
from typing import Any

from invoice_referee.domain import KimiAnalysis


SYSTEM_PROMPT = """Bạn là tác tử hỗ trợ kế toán Việt Nam.
Bạn nhận business context và kết quả OCR của từng tài liệu độc lập.
Chỉ dùng dữ kiện được cung cấp, không tự bịa hoặc điền giá trị còn thiếu.
Hãy xác định business context có đủ để hiểu mục đích khoản chi hay không và
hai nguồn có mâu thuẫn trực tiếp về số tiền, ngày, đối tác hoặc nội dung chi hay không.
Trả về đúng một JSON object, không bọc Markdown, theo schema:
{
  "business_context_present": true,
  "conflict_detected": false,
  "summary": "Tóm tắt ngắn cho kế toán",
  "reasoning": "Lý do rõ ràng, nêu dữ kiện và nguồn đã đối chiếu",
  "conflicts": []
}
Không trả chain-of-thought; chỉ trả kết luận và rationale có thể kiểm toán.
"""


def _parse_json_object(response_text: str) -> dict[str, Any]:
    text = response_text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Kimi không trả về JSON object hợp lệ.") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("Kimi không trả về JSON object hợp lệ.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Kimi response phải là một JSON object.")
    return parsed


class KimiReasoningAdapter:
    """Call one OpenAI-compatible Kimi endpoint per complete case."""

    def __init__(
        self,
        token: str,
        secret: str,
        base_url: str,
        model: str = "moonshotai/Kimi-K3",
        client: Any | None = None,
    ) -> None:
        if not token or not secret or not base_url or not model:
            raise ValueError("Cấu hình Kimi chưa đầy đủ.")
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=f"{token}.{secret}")
        self.client = client
        self.model = model

    def analyze(self, case_payload: dict[str, Any]) -> KimiAnalysis:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        case_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=4096,
            top_p=0.95,
            stream=False,
        )
        response_text = completion.choices[0].message.content or ""
        return KimiAnalysis.model_validate(_parse_json_object(response_text))

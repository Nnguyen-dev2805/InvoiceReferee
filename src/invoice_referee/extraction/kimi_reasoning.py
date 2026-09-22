"""Kimi adapters for extraction-quality checks without business decisions."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from invoice_referee.domain import (
    ConfidenceAnalysis,
    ConflictAnalysis,
)

from .conflict_reasoning import CONFLICT_SYSTEM_PROMPT

MAX_OUTPUT_TOKENS = 8192
MAX_REPAIR_CONTEXT_CHARS = 16_000
AnalysisModel = TypeVar("AnalysisModel", bound=BaseModel)


REPAIR_PROMPT = """Phản hồi trước không thể được hệ thống đọc thành JSON đúng schema.
Hãy tạo lại toàn bộ kết quả. Chỉ trả về đúng một JSON object hợp lệ, không dùng
Markdown, không thêm lời dẫn, không thêm nội dung sau JSON. Mọi chuỗi phải
được escape đúng chuẩn JSON và không được bỏ sót đối tượng cần đánh giá.
"""


CONFIDENCE_SYSTEM_PROMPT = """Bạn là Evidence Confidence Quality Agent. Mỗi
lần bạn chỉ đánh giá MỘT evidence đã được OCR và các candidate block có word
confidence thấp của chính evidence đó.

Nhiệm vụ duy nhất:
1. Đánh giá MỌI candidate block đúng một lần, giữ nguyên candidate_id.
2. Xác định nội dung còn đọc được nguyên giá trị, chỉ đọc được ý nghĩa chung,
   chưa chắc chắn hay không đọc được.
3. Map nội dung vào canonical_fields theo ngữ nghĩa.
4. Đặt requires_verification=true khi giá trị trong block không thể được dùng
   an toàn nếu chưa có người xác nhận. Đặt false khi vẫn đọc được hoặc chỉ là
   nội dung không thiết yếu.
5. Không sửa, tự đoán hoặc lấy dữ liệu từ nguồn khác để bù vào phần chưa rõ.

Bạn KHÔNG nhận và KHÔNG được sử dụng business context hoặc chứng từ khác. Không
kiểm tra missing field toàn tài liệu, conflict, policy, thuế, danh mục chi phí,
hạn mức, gian lận hoặc đưa ra quyết định hồ sơ.

quality_state chỉ được là READABLE, SEMANTICALLY_READABLE, UNCERTAIN,
UNREADABLE hoặc UNKNOWN:
- READABLE: giá trị vẫn đọc được đầy đủ.
- SEMANTICALLY_READABLE: chữ có thể sai nhưng vẫn nhận diện chắc ý nghĩa chung.
- UNCERTAIN/UNREADABLE: giá trị không thể sử dụng an toàn.
- UNKNOWN: context trong evidence chưa đủ để đánh giá.

review_action chỉ là khuyến nghị chất lượng:
- CONTINUE khi requires_verification=false.
- ASK_HUMAN khi requires_verification=true.
Không dùng DEFER_TO_POLICY. Quality Gate bằng code sẽ quyết định field nào cần
cho bước đối chiếu tiếp theo.

Ví dụ:
- "Helineken" vẫn nhận diện chắc là một tên mặt hàng: SEMANTICALLY_READABLE,
  requires_verification=false.
- Tổng tiền chỉ nhìn được một phần: UNCERTAIN, requires_verification=true.
- Lời chào hoặc chân trang mờ: NON_CRITICAL, requires_verification=false.
- Thuế suất không đọc được: canonical_fields=["tax_rate"], UNCERTAIN và
  requires_verification=true. Agent chỉ báo chất lượng; không tự quyết định nó
  có chặn kiểm kê hay không.

Quy tắc viết human_question:
- Chỉ tạo khi requires_verification=true.
- Dùng tên file hoặc loại chứng từ, nêu trực tiếp giá trị cần xác nhận.
- Không đưa candidate_id, evidence_id, page/block ID, confidence score, schema,
  canonical field hoặc thuật ngữ OCR vào câu hỏi.

Trả về đúng một JSON object, không bọc Markdown:
{
  "block_assessments": [
    {
      "candidate_id": "EV-001:page-0-block-4",
      "importance": "CRITICAL",
      "quality_state": "UNCERTAIN",
      "review_action": "ASK_HUMAN",
      "requires_verification": true,
      "canonical_fields": ["total_amount"],
      "observed_text": "2.442.?60đ",
      "semantic_category": null,
      "reason": "Không đọc chắc một chữ số của tổng thanh toán.",
      "human_question": "Vui lòng kiểm tra hóa đơn và xác nhận tổng thanh toán."
    }
  ]
}

Không trả chain-of-thought, policy, conflict hoặc kết luận hồ sơ.
"""


def _json_objects(response_text: str) -> list[dict[str, Any]]:
    """Find complete JSON objects even when the model adds surrounding text."""

    text = response_text.strip().lstrip("\ufeff")
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    seen_ranges: set[tuple[int, int]] = set()

    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            parsed, consumed = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        end = start + consumed
        if isinstance(parsed, dict) and (start, end) not in seen_ranges:
            objects.append(parsed)
            seen_ranges.add((start, end))

    return objects


def _parse_analysis(
    response_text: str,
    model_type: type[AnalysisModel],
) -> AnalysisModel:
    objects = _json_objects(response_text)
    if not objects:
        raise ValueError("Kimi không trả về JSON object hoàn chỉnh.")

    validation_errors: list[str] = []
    for parsed in objects:
        try:
            return model_type.model_validate(parsed)
        except Exception as exc:
            validation_errors.append(str(exc))

    detail = validation_errors[0] if validation_errors else "sai schema"
    raise ValueError(f"Kimi trả về JSON nhưng không đúng schema: {detail}")


class KimiResponseError(ValueError):
    """Raised after every bounded JSON recovery attempt has failed."""

    def __init__(self, stage: str, diagnostics: list[dict[str, Any]]) -> None:
        self.stage = stage
        self.diagnostics = diagnostics
        details = "; ".join(
            (
                f"lần {item['attempt']}: {item['character_count']} ký tự, "
                f"finish_reason={item['finish_reason']}, lỗi={item['error']}"
            )
            for item in diagnostics
        )
        super().__init__(
            f"Kimi {stage} không trả về JSON hợp lệ sau "
            f"{len(diagnostics)} lần thử. {details}"
        )


class KimiReasoningAdapter:
    """Call Kimi for bounded structured extraction stages."""

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

    def _complete(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=MAX_OUTPUT_TOKENS,
            top_p=0.95,
            stream=False,
            extra_body={"reasoning_effort": "low"},
        )
        choice = completion.choices[0]
        content = choice.message.content
        if isinstance(content, str):
            response_text = content
        elif content is None:
            response_text = ""
        else:
            response_text = json.dumps(content, ensure_ascii=False, default=str)
        return response_text, str(getattr(choice, "finish_reason", "unknown"))

    def _analyze(
        self,
        case_payload: dict[str, Any],
        *,
        stage: str,
        system_prompt: str,
        model_type: type[AnalysisModel],
    ) -> AnalysisModel:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    case_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        diagnostics: list[dict[str, Any]] = []

        response_text, finish_reason = self._complete(messages)
        try:
            return _parse_analysis(response_text, model_type)
        except ValueError as exc:
            first_validation_error = str(exc)
            diagnostics.append(
                {
                    "attempt": 1,
                    "character_count": len(response_text),
                    "finish_reason": finish_reason,
                    "error": first_validation_error,
                }
            )

        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": response_text[-MAX_REPAIR_CONTEXT_CHARS:],
            },
            {
                "role": "user",
                "content": (
                    f"{REPAIR_PROMPT}\n\n"
                    "Các lỗi schema cụ thể của kết quả trước:\n"
                    f"{first_validation_error}\n\n"
                    "Hãy sửa chính xác các lỗi trên và trả lại toàn bộ JSON."
                ),
            },
        ]
        repaired_text, repaired_finish_reason = self._complete(repair_messages)
        try:
            return _parse_analysis(repaired_text, model_type)
        except ValueError as exc:
            diagnostics.append(
                {
                    "attempt": 2,
                    "character_count": len(repaired_text),
                    "finish_reason": repaired_finish_reason,
                    "error": str(exc),
                }
            )
            raise KimiResponseError(stage, diagnostics) from exc

    def analyze_confidence(
        self,
        case_payload: dict[str, Any],
    ) -> ConfidenceAnalysis:
        return self._analyze(
            case_payload,
            stage="Confidence Quality Agent",
            system_prompt=CONFIDENCE_SYSTEM_PROMPT,
            model_type=ConfidenceAnalysis,
        )

    def analyze_conflict(
        self,
        case_payload: dict[str, Any],
    ) -> ConflictAnalysis:
        return self._analyze(
            case_payload,
            stage="Cross-source Conflict Agent",
            system_prompt=CONFLICT_SYSTEM_PROMPT,
            model_type=ConflictAnalysis,
        )

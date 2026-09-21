"""Kimi adapters for extraction-quality checks without business decisions."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from invoice_referee.domain import ConfidenceAnalysis

MAX_OUTPUT_TOKENS = 8192
MAX_REPAIR_CONTEXT_CHARS = 16_000
AnalysisModel = TypeVar("AnalysisModel", bound=BaseModel)


REPAIR_PROMPT = """Phản hồi trước không thể được hệ thống đọc thành JSON đúng schema.
Hãy tạo lại toàn bộ kết quả. Chỉ trả về đúng một JSON object hợp lệ, không dùng
Markdown, không thêm lời dẫn, không thêm nội dung sau JSON. Mọi chuỗi phải
được escape đúng chuẩn JSON và không được bỏ sót đối tượng cần đánh giá.
"""


CONFIDENCE_SYSTEM_PROMPT = """Bạn là Confidence Quality Agent kiểm tra chất
lượng extraction của các candidate block có word confidence thấp. Bạn không
phải tác tử duyệt kế toán.

Nhiệm vụ duy nhất:
1. Phân loại từng evidence theo toàn bộ OCR context và giữ nguyên evidence_id
   trong document_types.
2. Đánh giá MỌI candidate block đúng một lần và giữ nguyên candidate_id.
3. Xác định phần confidence thấp có làm mơ hồ dữ liệu tài chính/định danh hay
   chỉ làm sai chính tả nội dung mô tả như tên món ăn.
4. Không sửa hoặc tự đoán chữ/số. Chỉ ghi observed_text đúng nội dung OCR.
5. Chọn review_action cho từng block. Chỉ tạo human_question khi action là
   ASK_HUMAN; câu hỏi phải chỉ rõ chứng từ, thông tin và điều cần xác nhận.
6. Nếu nội dung vẫn nhận diện được ở mức ngữ nghĩa và có thể liên quan policy
   (ví dụ bia/rượu), gắn semantic_category và DEFER_TO_POLICY. Không tự kết
   luận nội dung đó được phép hay bị cấm.

Không kiểm tra missing field toàn tài liệu, policy, xung đột, tính hợp lệ,
gian lận, hạn mức hoặc đưa ra PASS/REJECT.

Quy tắc viết cho kế toán:
- reason là ghi chú kỹ thuật ngắn để kiểm toán nội bộ.
- human_question phải là tiếng Việt tự nhiên, ngắn gọn và có thể hành động.
- Dùng tên file hoặc loại chứng từ để kế toán nhận biết nguồn.
- Không đưa candidate_id, evidence_id, page/block ID, confidence score, tên
  schema, canonical field hay thuật ngữ OCR vào human_question.
- Không nói "block này", "confidence thấp" hoặc "OCR đọc" với kế toán.
- Nêu trực tiếp thông tin cần xác nhận và giá trị đang nhìn thấy nếu có.
- Nếu một vùng có nhiều thông tin liên quan, gom thành một câu hỏi dễ đọc.

Ví dụ human_question tốt:
- "Vui lòng kiểm tra hóa đơn Hoa_don.jpg và xác nhận tổng thanh toán có phải
  2.442.960đ không."
- "Vui lòng xác nhận mã số thuế người bán và người mua trên hóa đơn điện tử."

Ví dụ không được dùng:
- "Xác nhận EV-001 tại page-0-block-4 vì confidence 0.62."

importance chỉ được là CRITICAL, NON_CRITICAL, UNKNOWN.
quality_state chỉ được là READABLE, SEMANTICALLY_READABLE, UNCERTAIN,
UNREADABLE, UNKNOWN.
- READABLE: phần confidence thấp không làm giá trị cần dùng trở nên mơ hồ.
- SEMANTICALLY_READABLE: chữ có thể sai nhưng vẫn nhận diện được loại nội dung.
- UNCERTAIN/UNREADABLE: không đủ tin cậy để dùng mà không có người xác minh.
- UNKNOWN: không đủ context để đánh giá.

review_action chỉ được là:
- CONTINUE: lỗi không ảnh hưởng dữ liệu cần dùng ở bước extraction.
- ASK_HUMAN: phải xác minh trước khi tiếp tục vì dữ liệu tài chính, định danh
  hoặc đối tượng hàng hóa bắt buộc đang không rõ.
- DEFER_TO_POLICY: extraction đủ hiểu ý nghĩa chung nhưng nội dung có thể cần
  Policy Agent xem xét. Action này KHÔNG chặn extraction và không hỏi human.

Quy tắc theo loại chứng từ:
- Bill nhà hàng/cafe: tên món sai vài ký tự thường là CONTINUE nếu số lượng,
  đơn giá, thành tiền và tổng tiền rõ.
- Tên đồ uống, đồ ăn hay các đồ dùng không phải định danh liên quan đến nhiệp vụ kế toán như "Helineken" vẫn nhận diện được là bia: dùng
  SEMANTICALLY_READABLE + DEFER_TO_POLICY, không ASK_HUMAN chỉ vì sai chính tả.
- Hóa đơn điện tử, phiếu nhập kho, mua tài sản/vật tư: ASK_HUMAN nếu tên hàng
  mờ đến mức không xác định được đối tượng mua.
- Tổng tiền, thuế, ngày, số hóa đơn, MST, số lượng, đơn giá hoặc thành tiền:
  ASK_HUMAN khi phần giá trị cần dùng thực sự không rõ.
- Lời chào, chân trang và tên món không ảnh hưởng đối soát: CONTINUE.

Map canonical_fields theo ngữ nghĩa, không phụ thuộc nhãn hay layout cố định.
Trả về đúng một JSON object, không bọc Markdown:
{
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
      "reason": "Giá trị tiền nằm trong block có confidence thấp.",
      "human_question": "Vui lòng xác nhận tổng thanh toán tại block B04 có phải 2.442.960đ không."
    }
  ]
}
Không trả chain-of-thought, kết luận hồ sơ hay khẳng định nghiệp vụ.
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
            validation_errors.append(str(exc).splitlines()[0])

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
    """Call Kimi only for confidence-quality assessment."""

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
            diagnostics.append(
                {
                    "attempt": 1,
                    "character_count": len(response_text),
                    "finish_reason": finish_reason,
                    "error": str(exc),
                }
            )

        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": response_text[-MAX_REPAIR_CONTEXT_CHARS:],
            },
            {"role": "user", "content": REPAIR_PROMPT},
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

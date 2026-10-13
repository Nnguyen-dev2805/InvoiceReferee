"""Kimi adapters for extraction-quality checks without business decisions."""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from invoice_referee.domain import (
    ConfidenceAnalysis,
    ConflictAnalysis,
    EvidenceReconciliationAnalysis,
    ExpenseDocumentFacts,
    PaperSettlementFacts,
)

from .conflict_reasoning import CONFLICT_SYSTEM_PROMPT
from .evidence_reconciliation import EVIDENCE_RECONCILIATION_SYSTEM_PROMPT
from .network_resilience import call_with_service_retry

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

Input có document_type và required_fields đã được Extraction Agent xác định.
Hãy đánh giá mức độ quan trọng theo đúng loại chứng từ đó. Không yêu cầu MST,
mẫu số, ký hiệu hoặc trường của hóa đơn GTGT đối với vé, bill, phiếu thu, bằng
chứng thanh toán hay tài liệu thay thế nếu required_fields không yêu cầu.
Input cũng có extracted_usable_fields: đây là các giá trị đã được trích xuất rõ
từ cùng chứng từ. Nếu chỉ nhãn của một field mờ (ví dụ chữ "Tổng cộng") nhưng
giá trị tổng tiền đã rõ trong extracted_usable_fields, block đó không cần người
xác nhận: canonical_fields có thể ghi total_amount nhưng phải đặt
requires_verification=false. Chỉ ASK_HUMAN khi chính giá trị kế toán trọng yếu
không thể dùng an toàn.

Mỗi candidate block, kể cả NON_CRITICAL hoặc CONTINUE, vẫn PHẢI có đúng một
object trong block_assessments. Số object trả về phải bằng số candidate đầu
vào. Không được bỏ qua candidate không quan trọng và không được trả danh sách
rỗng khi candidate_blocks không rỗng.

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
- "Vẻ máy bay" trong mô tả vẫn hiểu chắc là "Vé máy bay":
  SEMANTICALLY_READABLE, requires_verification=false. Lỗi chính tả, dấu tiếng
  Việt hoặc một phần tên hàng không được ASK_HUMAN khi vẫn đủ hiểu loại chi phí
  và các số tiền/định danh trọng yếu đã rõ.
- Tổng tiền chỉ nhìn được một phần: UNCERTAIN, requires_verification=true.
- Lời chào hoặc chân trang mờ: NON_CRITICAL, requires_verification=false.
- "Tổng cộng:" bị mờ nhưng tổng thanh toán đã đọc rõ: READABLE hoặc
  SEMANTICALLY_READABLE, requires_verification=false.
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


EXPENSE_EXTRACTION_SYSTEM_PROMPT = """Bạn là Expense Document Extraction Agent.
Mỗi lần bạn chỉ phân loại và trích xuất dữ kiện từ MỘT chứng từ đã OCR. Không
đánh giá policy, không quyết định duyệt, không suy đoán dữ kiện không xuất hiện
và không dùng business context để bù dữ liệu chứng từ.

Trước hết phân loại tài liệu theo nội dung nhìn thấy, không dựa vào tên file:
- E_INVOICE: hóa đơn điện tử/hóa đơn GTGT có số hóa đơn, ký hiệu, mẫu số và MST.
- PAPER_RECEIPT: bill/biên lai bán hàng của cửa hàng, nhà hàng hoặc POS receipt.
- CARD_SLIP: slip máy quẹt thẻ; chỉ chứng minh thao tác thanh toán.
- PAYMENT_PROOF: ảnh chuyển khoản/sao kê/xác nhận giao dịch ngân hàng hoặc ví.
- TRANSPORT_TICKET: vé máy bay, tàu, xe hoặc chứng từ chuyến đi.
- HOTEL_RECEIPT: bill/phiếu thanh toán khách sạn không phải hóa đơn điện tử.
- COLLECTION_RECEIPT: phiếu thu có bên nộp, bên thu và số phiếu.
- CONTRACT, QUOTATION, PURCHASE_ORDER: hợp đồng, báo giá hoặc đơn đặt hàng.
- ACCEPTANCE_RECORD, DELIVERY_NOTE, GOODS_RECEIPT: biên bản nghiệm thu, phiếu
  giao hàng hoặc phiếu nhập/nhận hàng.
- SUPPLIER_CONFIRMATION: xác nhận của nhà cung cấp.
- OTHER hoặc UNKNOWN chỉ dùng khi thật sự không thể xếp vào các loại trên.
Một hóa đơn khách sạn vẫn là E_INVOICE nếu có đầy đủ dấu hiệu hóa đơn điện tử.

Giữ nguyên document_id từ input. Chuẩn hóa số tiền thành số JSON không có dấu
phân cách hàng nghìn. Trường không đọc được dùng null. source_refs phải trỏ đến
document_id hoặc page/block được cung cấp.

classification_confidence nằm trong [0,1]. classification_signals là các dấu
hiệu trực tiếp nhìn thấy dùng để phân loại. alternative_document_types chỉ ghi
loại còn có khả năng đúng. field_states ghi trạng thái của các trường kế toán
quan trọng bằng PRESENT, ABSENT, UNREADABLE, INVALID hoặc NOT_APPLICABLE. Không
đánh dấu PRESENT nếu giá trị trả về là null.

extraction_warnings chỉ ghi mâu thuẫn hoặc độ mơ hồ có thể làm sai định danh
chứng từ, ngày, MST, số tiền, trạng thái thanh toán hoặc tính hợp lệ pháp lý.
Không cảnh báo lỗi chính tả, thiếu dấu hay sai một ký tự trong tên hàng hóa/dịch
vụ khi vẫn hiểu chắc nội dung và không làm thay đổi số tiền hoặc bản chất khoản
chi. Ví dụ "Vẻ máy bay" vẫn trích xuất là mô tả dòng và không tạo warning.
Sau khi phân loại, không cảnh báo việc thiếu trường không áp dụng cho loại chứng
từ đó. Ví dụ TRANSPORT_TICKET, PAPER_RECEIPT và PAYMENT_PROOF không phải hóa
đơn GTGT nên thiếu MST bên bán/bên mua không phải extraction_warning.

Trả về đúng một JSON object, không bọc Markdown:
{
  "document_id": "DOC-001",
  "document_type": "E_INVOICE",
  "classification_confidence": 0.98,
  "classification_signals": ["Có ký hiệu, mẫu số và số hóa đơn"],
  "alternative_document_types": [],
  "issuer_name": null,
  "issuer_tax_code": null,
  "buyer_name": null,
  "buyer_tax_code": null,
  "document_number": null,
  "template_number": null,
  "serial_number": null,
  "document_date": null,
  "subtotal": null,
  "discount": null,
  "tax": null,
  "service_charge": null,
  "total_amount": null,
  "payment_method": null,
  "payer_name": null,
  "payee_name": null,
  "transaction_reference": null,
  "transaction_status": null,
  "confirmation_present": null,
  "line_items": [
    {
      "description": "Tên hàng hóa hoặc dịch vụ",
      "quantity": null,
      "unit_price": null,
      "line_amount": null,
      "source_refs": ["DOC:DOC-001"]
    }
  ],
  "field_states": {
    "buyer_tax_code": "PRESENT",
    "total_amount": "PRESENT"
  },
  "source_refs": ["DOC:DOC-001"],
  "extraction_warnings": []
}

Không trả chain-of-thought; chỉ trả dữ kiện và cảnh báo trích xuất ngắn gọn.
"""


PAPER_SETTLEMENT_EXTRACTION_SYSTEM_PROMPT = """Bạn là Paper Settlement Form
Extraction Agent. Bạn chỉ trích xuất dữ kiện từ MỘT giấy đề nghị hoàn ứng hoặc
quyết toán đã OCR. Không đánh giá policy, không ghép evidence và không tự tạo
dữ kiện không xuất hiện.

Giữ nguyên document_id. Mỗi dòng chi phí trong bảng phải trở thành đúng một
line. Bỏ qua dòng tổng cộng. Chuẩn hóa số tiền thành số JSON không có dấu phân
cách hàng nghìn. invoice_refs là danh sách số hóa đơn/chứng từ ghi tại dòng.

Phải giữ nguyên nội dung cột ghi chú trong note.
- requires_evidence=true khi dòng thể hiện phải có tài liệu kèm theo, ví dụ có
  số hóa đơn, ghi "đính kèm bảng kê", "đính kèm thống kê", "kèm chứng từ",
  "có hóa đơn" hoặc cách diễn đạt tương đương.
- Khi ghi chú ghi "không có chứng từ", "không có hóa đơn" hoặc có giải thích
  tương đương: requires_evidence=false và no_evidence_reason phải chứa nguyên
  nội dung ghi chú nhìn thấy trên đơn.
- Khi ghi chú trống và không có số chứng từ: requires_evidence=false và
  no_evidence_reason=null.
  Giá trị false này chỉ phản ánh đơn không ghi rõ việc đính kèm; không có nghĩa
  dòng chi được miễn chứng từ. Policy engine sẽ yêu cầu evidence hoặc giải
  trình riêng cho mọi dòng chi.
Không tự suy đoán lý do không xuất hiện trên đơn.

Quy tắc số tiền quyết toán:
- advance_amount là đúng số nằm cạnh nhãn "số tiền đã tạm ứng" hoặc cách ghi
  tương đương; null nếu đơn không có hoặc không đọc được.
- reimbursement_amount là trị tuyệt đối của khoản chênh lệch được ghi rõ trên
  đơn (công ty trả thêm hoặc nhân viên hoàn lại); null nếu đơn không ghi.
- Không tự suy ra chiều dòng tiền và không tự tính giá trị còn thiếu. Python sẽ
  tính lại từ total_amount và advance_amount.

Thông tin chuyển khoản là tùy chọn:
- beneficiary_name, bank_account_number và bank_name chỉ lấy khi nhìn thấy rõ
  trên đơn; không có hoặc không đọc được thì trả null.
- Không lấy số tài khoản của nhà cung cấp trên hóa đơn evidence làm tài khoản
  nhận tiền của người đề nghị hoàn ứng.

extraction_warnings chỉ ghi các vấn đề kế toán trọng yếu nhìn thấy rõ, ví dụ số
tiền bằng chữ khác số, tổng dòng khác tổng cộng, số hoàn ứng/hoàn trả mâu thuẫn
hoặc giá trị bắt buộc không đọc được. Không ghi lỗi chính tả, thiếu dấu, sai một
ký tự trong mô tả hàng hóa/dịch vụ, lỗi trình bày hoặc khác biệt không làm thay
đổi số tiền, định danh chứng từ hay bản chất khoản chi.

Trả về đúng một JSON object, không bọc Markdown:
{
  "document_id": "DOC-001",
  "document_type": "PAPER_SETTLEMENT_REQUEST",
  "purpose": null,
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
      "source_refs": ["DOC:DOC-001"]
    }
  ],
  "source_refs": ["DOC:DOC-001"],
  "extraction_warnings": []
}

Không trả chain-of-thought; chỉ trả dữ kiện và cảnh báo trích xuất ngắn gọn.
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
        retry_delays: tuple[float, ...] = (0.75, 2.0),
    ) -> None:
        if not token or not secret or not base_url or not model:
            raise ValueError("Cấu hình Kimi chưa đầy đủ.")
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=f"{token}.{secret}")
        self.client = client
        self.model = model
        self.retry_delays = retry_delays

    def _complete(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        completion = call_with_service_retry(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=MAX_OUTPUT_TOKENS,
                top_p=0.95,
                stream=False,
                extra_body={"reasoning_effort": "low"},
            ),
            service="Kimi/Modal",
            retry_delays=self.retry_delays,
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
        result_validator: Callable[[AnalysisModel], None] | None = None,
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

        def parse_and_validate(response: str) -> AnalysisModel:
            result = _parse_analysis(response, model_type)
            if result_validator is not None:
                result_validator(result)
            return result

        response_text, finish_reason = self._complete(messages)
        try:
            return parse_and_validate(response_text)
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
            return parse_and_validate(repaired_text)
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
        candidate_ids = [
            str(candidate.get("candidate_id") or "")
            for candidate in (
                (case_payload.get("evidence") or {}).get("candidate_blocks") or []
            )
            if candidate.get("candidate_id")
        ]

        def validate_coverage(result: BaseModel) -> None:
            if not candidate_ids:
                return
            if not isinstance(result, ConfidenceAnalysis):
                raise ValueError("Confidence Agent trả sai loại kết quả.")
            counts: dict[str, int] = {}
            for assessment in result.block_assessments:
                counts[assessment.candidate_id] = counts.get(
                    assessment.candidate_id, 0
                ) + 1
            expected = set(candidate_ids)
            actual = set(counts)
            missing = sorted(expected.difference(actual))
            unexpected = sorted(actual.difference(expected))
            duplicated = sorted(
                candidate_id for candidate_id, count in counts.items() if count != 1
            )
            if missing or unexpected or duplicated:
                raise ValueError(
                    "Confidence Agent chưa đánh giá đúng một lần cho mọi candidate. "
                    f"expected_count={len(candidate_ids)}, "
                    f"actual_count={len(result.block_assessments)}, "
                    f"missing={missing}, unexpected={unexpected}, "
                    f"duplicated={duplicated}."
                )

        return self._analyze(
            case_payload,
            stage="Confidence Quality Agent",
            system_prompt=CONFIDENCE_SYSTEM_PROMPT,
            model_type=ConfidenceAnalysis,
            result_validator=validate_coverage,
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

    def analyze_evidence_reconciliation(
        self,
        case_payload: dict[str, Any],
    ) -> EvidenceReconciliationAnalysis:
        return self._analyze(
            case_payload,
            stage="Evidence Reconciliation Agent",
            system_prompt=EVIDENCE_RECONCILIATION_SYSTEM_PROMPT,
            model_type=EvidenceReconciliationAnalysis,
        )

    def extract_expense_document(
        self,
        document_payload: dict[str, Any],
    ) -> ExpenseDocumentFacts:
        return self._analyze(
            document_payload,
            stage="Expense Document Extraction Agent",
            system_prompt=EXPENSE_EXTRACTION_SYSTEM_PROMPT,
            model_type=ExpenseDocumentFacts,
        )

    def extract_paper_settlement(
        self,
        document_payload: dict[str, Any],
    ) -> PaperSettlementFacts:
        return self._analyze(
            document_payload,
            stage="Paper Settlement Form Extraction Agent",
            system_prompt=PAPER_SETTLEMENT_EXTRACTION_SYSTEM_PROMPT,
            model_type=PaperSettlementFacts,
        )

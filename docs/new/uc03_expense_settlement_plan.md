# UC-03 Implementation Plan - Hoàn ứng và quyết toán chi phí

## 1. Vai trò trong sản phẩm và cuộc thi

- Đây là workflow Track A chính.
- Mục tiêu: tự xử lý hồ sơ thường quy đến trạng thái sẵn sàng cho kế toán, đồng thời dừng đúng lúc và tạo câu hỏi/chuyển cấp cụ thể.
- Tác tử không tự phê duyệt chi phí, không tự giải ngân và không tự tạo bút toán.
- Thành công được đo bằng hai chỉ số: tỷ lệ bỏ sót case cần chuyển tiếp và tỷ lệ chuyển tiếp không cần thiết.

## 2. Phạm vi nghiệp vụ

### 2.1. Hai subtype

```text
ADVANCE_SETTLEMENT
  Nhân viên đã nhận tiền tạm ứng.
  Bắt buộc advance_id và allocated_advance_amount.

EMPLOYEE_REIMBURSEMENT
  Nhân viên tự chi tiền.
  Không có advance_id; công ty hoàn lại approved amount.
```

### 2.2. Hai kênh đầu vào

```text
DIGITAL_FORM
  Structured settlement form + evidence.

PAPER_SCAN
  Giấy đề nghị hoàn ứng/quyết toán đã ký + evidence.
```

### 2.3. Ngoài phạm vi MVP

- Xác thực chữ ký tay.
- Chữ ký số thật.
- Kết nối ngân hàng, ERP hoặc cổng hóa đơn thật.
- Tự động thanh toán/thu hồi.
- Kết luận khấu trừ VAT hoặc thuế thu nhập doanh nghiệp như tư vấn pháp lý cuối cùng.

## 3. Khoảng cách so với code hiện tại

Code hiện có đã làm được:

- Nhận mô tả và file.
- OCR từng evidence.
- Gom low-confidence word theo block.
- Confidence Agent một lần cho mỗi evidence có candidate.
- Conflict Agent cho bill và supporting document.
- Policy đối chiếu nhận hàng cơ bản.
- UI Kế toán hiển thị evidence, bbox và reasoning.

Cần thay đổi:

- `ClaimDraft` -> case-specific structured payload.
- Nhiều expense item trong một `ExpenseCase`.
- Liên kết item-evidence và allocation.
- Advance reference/balance.
- Policy chi phí, duplicate history và authority.
- `PASS/NEEDS_HUMAN` -> action Track A rõ loại uncertainty.
- Human action, audit, stop/override và Verify harness.

## 4. Hợp đồng đầu vào

### 4.1. Digital form

```json
{
  "case_type": "EXPENSE_SETTLEMENT",
  "settlement_type": "ADVANCE_SETTLEMENT",
  "source_type": "DIGITAL_FORM",
  "employee": {
    "employee_id": "EMP-DEMO-001",
    "name": "Nguyễn Minh An",
    "department": "Phòng Kinh doanh",
    "position": "Nhân viên"
  },
  "business_context": {
    "purpose": "Công tác gặp khách hàng tại Hà Nội",
    "project_code": "DEMO-2026",
    "client_name": "Khách hàng Demo",
    "activity_start_date": "2026-10-15",
    "activity_end_date": "2026-10-17"
  },
  "advance_id": "ADV-202610-001",
  "expense_items": [
    {
      "item_id": "ITEM-001",
      "category": "MEAL",
      "description": "Tiếp khách trưa ngày 16/10",
      "claimed_amount": "1200000",
      "currency": "VND",
      "document_refs": ["DOC-001"]
    }
  ]
}
```

### 4.2. Paper scan

Tài liệu chính `SETTLEMENT_REQUEST_FORM` chứa:

- Đơn vị, ngày lập.
- Người đề nghị, chức vụ, bộ phận.
- Bảng khoản chi: nội dung, số hóa đơn, số tiền và ghi chú.
- Tổng cộng bằng số và bằng chữ.
- Số đã tạm ứng nếu có.
- Số đề nghị thanh toán thêm hoặc số phải hoàn lại.
- Thông tin chuyển khoản nếu mẫu có.
- Chữ ký theo `PolicyConfig`.

Evidence có thể là hóa đơn điện tử, bill giấy, vé, chứng từ thanh toán hoặc tài liệu ngoại lệ được policy cho phép.

### 4.3. Quy tắc submit

- `ADVANCE_SETTLEMENT` bắt buộc `advance_id`.
- `EMPLOYEE_REIMBURSEMENT` cấm gắn advance đang mở nếu người dùng chưa đổi subtype.
- Mỗi expense item phải có evidence hoặc `policy_exception_code`.
- File được gắn document role, không chỉ `PRIMARY/SUPPORTING`.
- Nhân viên chọn subtype; hệ thống cảnh báo nhưng không tự đổi âm thầm.

## 5. Domain model mục tiêu

Tạo `src/invoice_referee/domain/settlement.py`:

```python
class SettlementType(StrEnum):
    ADVANCE_SETTLEMENT = "ADVANCE_SETTLEMENT"
    EMPLOYEE_REIMBURSEMENT = "EMPLOYEE_REIMBURSEMENT"

class ExpenseItem(BaseModel):
    item_id: str
    category: str
    description: str
    expense_date: date | None
    claimed_amount: Decimal
    currency: str
    document_ids: list[str]
    allocation_ids: list[str]
    policy_exception_code: str | None
    source_refs: list[str]

class ExpenseDocumentFacts(BaseModel):
    document_id: str
    document_type: str
    issuer_name: str | None
    issuer_tax_code: str | None
    buyer_name: str | None
    buyer_tax_code: str | None
    document_number: str | None
    serial_number: str | None
    document_date: date | None
    subtotal: Decimal | None
    discount: Decimal | None
    tax: Decimal | None
    service_charge: Decimal | None
    total_amount: Decimal | None
    payment_method: str | None
    line_items: list[DocumentLineFact]
    source_refs: list[str]

class EvidenceAllocation(BaseModel):
    allocation_id: str
    expense_item_id: str
    document_id: str
    allocated_amount: Decimal
    source_refs: list[str]

class ExpenseItemReview(BaseModel):
    item_id: str
    claimed_amount: Decimal
    document_amount: Decimal | None
    proposed_eligible_amount: Decimal
    approved_amount: Decimal | None
    policy_status: str
    findings: list[str]
    source_refs: list[str]

class SettlementComputation(BaseModel):
    claimed_total: Decimal
    document_total: Decimal
    proposed_eligible_total: Decimal
    approved_expense_amount: Decimal | None
    allocated_advance_amount: Decimal
    company_pays_employee: Decimal | None
    employee_returns_company: Decimal | None
    remaining_advance_balance: Decimal | None
```

`approved_amount` và các số tiền quyết toán cuối phải là `None` trước hành động xác nhận của con người.

## 6. Source reference contract

Mọi fact phải trỏ về một trong hai dạng:

```text
FORM:{case_id}:{field_path}
DOC:{document_id}:PAGE:{page}:BBOX:{x1},{y1},{x2},{y2}
```

Không sử dụng candidate/block ID làm câu giải thích cho kế toán. ID kỹ thuật chỉ nằm trong audit/debug.

## 7. Pipeline xử lý

```text
Submit
  -> technical validation
  -> required-input validation
  -> save immutable source files
  -> for each scanned document:
       OCR
       low-confidence candidate collection
       Confidence Agent nếu có candidate
       block nếu critical field chưa rõ
       document classification/extraction
  -> parse structured form trực tiếp nếu DIGITAL_FORM
  -> validate extraction coverage
  -> link expense items to documents
  -> duplicate checks
  -> arithmetic and allocation checks
  -> category/deadline/authority policy
  -> compute proposed eligible amounts
  -> Decision Guard
  -> persist result and audit
  -> accounting review UI
```

### 7.1. Fail-fast nhưng không mất findings

- Thiếu file bắt buộc: không gọi OCR/LLM; tạo `REQUEST_INFO` ngay.
- Một file critical chưa rõ: dừng trước cross-source policy, nhưng giữ kết quả quality của mọi file đã xử lý.
- Tool/LLM lỗi sau retry: fail closed, không dùng output dở dang để tính tiền.
- Khi chạy lại, dùng OCR/facts cache theo `sha256 + model_version + prompt_version`.

## 8. Chiến lược OCR và LLM

Với `N` file scan:

1. OCR: tối đa `N` call, một call/file, dùng cache.
2. Confidence Agent: tối đa `N` call; gom mọi candidate của cùng file trong một call, không gọi từng block.
3. Extraction Agent: tối đa `N` call; structured output kiểm tra bằng Pydantic.
4. Item-evidence linker: tối đa một call cho toàn case nếu exact reference chưa đủ.
5. Policy interpretation LLM: tối đa một call cho các category/context chưa phân loại được; action cuối vẫn do code.

Worst case lý thuyết là `3N + 2` external calls, nhưng file không có low-confidence candidate không gọi Confidence Agent; digital form không gọi OCR/extraction cho form chính.

Prompt phải tách riêng:

- Confidence prompt: chỉ chất lượng và tầm quan trọng của vùng nghi ngờ.
- Extraction prompt: chỉ trích xuất facts, không đánh giá policy.
- Linking prompt: chỉ đề xuất liên kết item-document.
- Category prompt: chỉ chuẩn hóa category/purpose khi rule deterministic chưa đủ.

## 9. Liên kết khoản khai báo với evidence

Thứ tự:

1. Số hóa đơn/document reference do nhân viên khai trùng chính xác.
2. Một evidence được chọn trực tiếp cho item trong form.
3. So khớp amount/date/vendor.
4. LLM đề xuất semantic link.
5. Mơ hồ -> `REQUEST_INFO`, không tự chọn.

Một document có thể cấp evidence cho nhiều item, nhưng bắt buộc có `EvidenceAllocation` và:

```text
sum(allocation của document) <= document accepted total
```

Một item có thể có nhiều document, ví dụ vé + phí hành lý.

## 10. Duplicate detection

### 10.1. Exact duplicate

Khóa ưu tiên:

```text
electronic invoice: seller_tax_code + serial_number + invoice_number
paper receipt: normalized_issuer + date + total + perceptual_hash
payment proof: transaction_reference + amount + date
```

Exact duplicate trong cùng case hoặc lịch sử -> `ESCALATE/OUTSIDE_POLICY`; document không được cộng lần hai.

### 10.2. Probable duplicate

Tín hiệu gần giống nhưng chưa đủ chắc -> `REQUEST_INFO/FACTUAL_UNKNOWN` với hai nguồn cần xác nhận. Không tự kết luận gian lận.

## 11. Phép tính

Sử dụng `Decimal`, currency-specific rounding và không parse số bằng `float`.

### 11.1. Document arithmetic

```text
expected_total = subtotal - discount + tax + service_charge
```

Chỉ áp dụng thành phần có mặt và đúng document type. Không ép bill giấy phải có tax/discount.

### 11.2. Case totals

```text
claimed_total = sum(expense_item.claimed_amount)
document_total = sum(unique accepted document allocation)
proposed_eligible_total = sum(item.proposed_eligible_amount)
```

### 11.3. Settlement sau human approval

```text
A = allocated_advance_amount
E = approved_expense_amount
D = E - A

company_pays_employee = max(D, 0)
employee_returns_company = max(-D, 0)
```

Với `EMPLOYEE_REIMBURSEMENT`, `A = 0`.

Không sử dụng trường có nhãn mơ hồ trên giấy như “số tiền đề nghị hoàn ứng” để suy ra chiều tiền. Luôn tính lại từ A và E.

## 12. PolicyConfig demo

```yaml
policy_id: DEMO-EXPENSE-2026
policy_version: "1.0"
data_classification: SYNTHETIC
base_currency: VND
submission_window_days: 30
authority_amount_vnd: 50000000
ocr_word_review_threshold: 0.85
require_business_purpose: true
require_project_for_categories: [TRAVEL, CLIENT_MEAL]
prohibited_categories: [PERSONAL]
category_limits:
  CLIENT_MEAL:
    per_case: 5000000
  TAXI:
    per_item: 2000000
evidence_optional_categories: []
required_paper_signature_roles:
  - REQUESTER
  - CHIEF_ACCOUNTANT
  - DIRECTOR
```

Đây là policy giả lập; UI và slide phải ghi rõ.

## 13. Rule catalog

| Rule ID | Kiểm tra | Failure class/action |
| --- | --- | --- |
| `SET_INPUT_001` | Đúng subtype và đủ form chính | Thiếu -> `FACTUAL_UNKNOWN/REQUEST_INFO` |
| `SET_ADV_001` | `ADVANCE_SETTLEMENT` có advance hợp lệ | Thiếu/không truy cập -> `REQUEST_INFO` |
| `SET_DOC_001` | Mỗi item có evidence hoặc exception | Thiếu -> `REQUEST_INFO` |
| `SET_QUALITY_001` | Critical field mỗi file đọc rõ | Không rõ -> `REQUEST_INFO` |
| `SET_SIGNATURE_001` | Đơn giấy đủ signature role | Thiếu/mờ -> `REQUEST_INFO` |
| `SET_LINK_001` | Item-evidence link xác định | Mơ hồ -> `REQUEST_INFO` |
| `SET_DUP_001` | Không exact duplicate | Trùng -> `OUTSIDE_POLICY/ESCALATE` |
| `SET_DUP_002` | Probable duplicate được xác minh | Chưa rõ -> `REQUEST_INFO` |
| `SET_ARITH_001` | Document arithmetic nhất quán | Mâu thuẫn -> `REQUEST_INFO` |
| `SET_TOTAL_001` | Claimed/form total khớp sum item | Mâu thuẫn -> `REQUEST_INFO` |
| `SET_ALLOC_001` | Allocation không vượt document | Vượt -> `REQUEST_INFO` |
| `SET_CONTEXT_001` | Purpose/project đủ theo category | Thiếu -> `REQUEST_INFO` |
| `SET_CATEGORY_001` | Category được phép | Bị cấm rõ -> `OUTSIDE_POLICY/ESCALATE` |
| `SET_LIMIT_001` | Item/category trong limit | Vượt rõ -> `OUTSIDE_POLICY/ESCALATE` hoặc approval exception theo config |
| `SET_DEADLINE_001` | Nộp trong thời hạn | Quá hạn rõ -> `OUTSIDE_POLICY/ESCALATE` |
| `SET_AUTH_001` | Tổng trong thẩm quyền | Vượt -> `BEYOND_AUTHORITY/ESCALATE` |
| `SET_ANOMALY_001` | Không có anomaly đủ mạnh | Có bằng chứng -> `SUSPICIOUS/ESCALATE` |

## 14. Decision Guard

Thứ tự ưu tiên:

```text
1. System/tool error làm thiếu dữ kiện bắt buộc
   -> REQUEST_INFO / FACTUAL_UNKNOWN

2. Confirmed OUTSIDE_POLICY
   -> ESCALATE / OUTSIDE_POLICY

3. Confirmed SUSPICIOUS
   -> ESCALATE / SUSPICIOUS

4. Mandatory FACTUAL_UNKNOWN
   -> REQUEST_INFO / FACTUAL_UNKNOWN

5. Confirmed BEYOND_AUTHORITY
   -> ESCALATE / BEYOND_AUTHORITY

6. Tất cả required rule PASS/NOT_APPLICABLE
   -> AUTO_PROCESS
```

Decision output:

```json
{
  "automation_decision": "REQUEST_INFO",
  "uncertainty_type": "FACTUAL_UNKNOWN",
  "primary_finding_code": "SET_QUALITY_001",
  "target": "EMPLOYEE",
  "question": "Tổng thanh toán trên bill nha_hang.jpg chưa đọc rõ là 2.442.960đ hay giá trị khác. Vui lòng xác nhận số tiền và tải ảnh rõ hơn nếu có.",
  "reason": "Tổng thanh toán là dữ kiện bắt buộc để đối chiếu khoản chi.",
  "source_refs": ["DOC:DOC-001:PAGE:1:BBOX:..."]
}
```

Question không được chứa “confidence thấp”, block ID, schema hay tên model.

## 15. Tab Nhân viên

### 15.1. Chọn hồ sơ

- Chọn “Hoàn ứng/quyết toán”.
- Chọn subtype bằng segmented control.
- Chọn “Điền form điện tử” hoặc “Tải đơn giấy”.

### 15.2. Digital form

- Business context.
- Advance selector khi là `ADVANCE_SETTLEMENT`.
- Expense-item editor có thêm/xóa dòng.
- Upload evidence và gắn vào item.
- Client validation trước submit.

### 15.3. Paper scan

- Upload giấy đề nghị chính.
- Upload nhiều evidence.
- Nhập business context tối thiểu.
- Hiển thị chữ ký bắt buộc theo PolicyConfig.

Sau submit chỉ hiển thị case ID và trạng thái tiếp nhận; không hiển thị “đã được duyệt”.

## 16. Tab Kế toán

Ưu tiên hiển thị cho người xử lý, không tổ chức theo log kỹ thuật.

### 16.1. Hàng đợi

Các filter:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
PROCESSING_ERROR
```

Mỗi dòng: case ID, nhân viên, subtype, số tiền khai báo, action, primary issue, submitted time.

### 16.2. Chi tiết case

1. Tóm tắt action và câu hỏi/chuyển cấp.
2. Business context và advance liên quan.
3. Bảng khoản chi:

| Khoản | Khai báo | Chứng từ | Đề xuất chấp nhận | Trạng thái | Nguồn |
| --- | ---: | ---: | ---: | --- | --- |

4. Settlement preview; ghi rõ chỉ là preview trước approval.
5. Signature/approval timeline.
6. Evidence preview và bbox.
7. Findings theo reason code.
8. Audit timeline.

### 16.3. Human actions

- `CONFIRM_EXTRACTION`: sửa/xác nhận fact và lưu before/after.
- `REQUEST_MORE_INFO`: gửi câu hỏi; cho phép chỉnh wording nhưng giữ finding/source.
- `ESCALATE_CASE`: chọn target và lý do.
- `OVERRIDE_DECISION`: bắt buộc nhập lý do.
- `STOP_PROCESSING`: dừng case.
- `REPROCESS_CASE`: chạy lại từ checkpoint phù hợp.
- `APPROVE_AMOUNTS`: nhập/xác nhận approved amount từng item; đây là human decision.

Delete case chỉ dành cho dữ liệu demo/admin và phải có confirmation; không dùng delete thay audit trong workflow thật.

## 17. Audit model

```python
class AuditEvent(BaseModel):
    event_id: str
    case_id: str
    event_type: str
    actor_type: str
    actor_id: str
    occurred_at: datetime
    correlation_id: str
    input_refs: list[str]
    policy_version: str | None
    model_version: str | None
    prompt_version: str | None
    reason: str | None
    before: dict | None
    after: dict | None
```

Audit append-only. Không sửa event cũ. Hoàn tác là một event mới trỏ `reverts_event_id`.

## 18. Storage artifacts

```text
CASE-.../
  submission.json
  canonical/
    settlement_request.v1.json
  documents/
    source/{document_id}__name.ext
    generated/settlement_request.v1.pdf
  ocr/{document_id}.json
  facts/{document_id}.json
  links.json
  policy_result.json
  decision.json
  processing.json
  audit.jsonl
```

`processing.json` có thể giữ output tương thích trong migration, nhưng `decision.json` là contract Track A mới.

## 19. Module triển khai

| File/module | Trách nhiệm |
| --- | --- |
| `domain/cases.py` | Case type, source type, lifecycle |
| `domain/decisions.py` | Automation decision, uncertainty, decision output |
| `domain/settlement.py` | Item, facts, allocation, computation |
| `domain/audit.py` | Audit event |
| `application/submit_settlement.py` | Validate/persist input |
| `application/process_settlement.py` | UC-03 orchestrator |
| `application/decision_guard.py` | Invariants và action mapping |
| `extraction/settlement_form.py` | Paper form extraction |
| `extraction/expense_document.py` | Evidence extraction |
| `extraction/item_linker.py` | Semantic link proposal |
| `policy/settlement.py` | Rule catalog và calculations |
| `policy/config.py` | Versioned PolicyConfig |
| `storage/case_repository.py` | Canonical case/artifact/audit port |
| `storage/history_repository.py` | Duplicate/advance history port |
| `app/fastapi_app.py` | FastAPI composition root và background worker |
| `app/web/routes.py` | HTML routes và JSON API cho hai workspace |
| `app/templates/employee/` | Employee structured form và trạng thái hồ sơ |
| `app/templates/accounting/` | Queue, detail và human actions |
| `app/static/` | CSS và JavaScript cho upload, mapping, polling |
| `app/templates/verify/` | Verify harness UI |

`CaseProcessingService` hiện tại nên được chuyển thành dispatcher, không tiếp tục chứa toàn bộ logic cho mọi case type.

## 20. Migration quyết định hiện tại

Trong giai đoạn chuyển đổi:

```text
PASS        -> AUTO_PROCESS
NEEDS_HUMAN + mandatory unknown -> REQUEST_INFO
NEEDS_HUMAN + confirmed policy violation -> ESCALATE
NEEDS_HUMAN + amount above authority -> ESCALATE
```

Không ánh xạ mọi `NEEDS_HUMAN` sang `REQUEST_INFO`; phải dựa trên failure class.

Schema mới tăng version và reader vẫn đọc được case `1.0/1.3` cũ.

## 21. Thứ tự triển khai

### Phase 0 - Contract và fixtures

- [ ] Chốt enums, Pydantic models và JSON examples.
- [ ] Tạo PolicyConfig synthetic.
- [ ] Chuẩn bị 15+ fixtures có expected decision.
- [ ] Viết contract tests trước khi đổi UI.

### Phase 1 - Shared case foundation

- [ ] Case type/source type/lifecycle.
- [ ] Decision/uncertainty model.
- [ ] Versioned local case repository.
- [ ] Append-only audit.
- [ ] Dispatcher theo case type.

### Phase 2 - Digital settlement form

- [ ] Form/subtype/expense-item editor.
- [ ] Advance selector synthetic.
- [ ] Direct canonical facts, không OCR.
- [ ] Evidence-item linkage.
- [ ] Submit validation.

### Phase 3 - Paper settlement form

- [ ] Form extraction schema/prompt.
- [ ] Signature presence detection.
- [ ] Confidence critical fields theo document role.
- [ ] Paper form facts -> canonical model.

### Phase 4 - Expense evidence

- [ ] Document classifier/extractor.
- [ ] Duplicate keys/history adapter.
- [ ] Item-evidence exact link.
- [ ] LLM semantic link fallback.
- [ ] Allocation validation.

### Phase 5 - Policy và Decision Guard

- [ ] Rule catalog.
- [ ] Decimal calculations.
- [ ] Proposed eligible amount.
- [ ] Decision precedence/invariants.
- [ ] Human-readable question builder.

### Phase 6 - Accounting UI

- [ ] Queue filters.
- [ ] Item review table.
- [ ] Evidence/source drill-down.
- [ ] Human actions và approved amount.
- [ ] Audit timeline, stop và override.

### Phase 7 - Verify và hardening

- [ ] One-click Verify.
- [ ] Timestamped result table.
- [ ] Offline deterministic fake adapters cho CI.
- [ ] Live-adapter smoke tests tách riêng.
- [ ] Error/retry/idempotency tests.
- [ ] New-input test run.

## 22. Bộ test tối thiểu 15 trường hợp

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| `SET-01` | Advance settlement thường quy, một bill rõ | `AUTO_PROCESS` |
| `SET-02` | Employee reimbursement thường quy | `AUTO_PROCESS` |
| `SET-03` | Nhiều bill hợp lệ, tổng khớp | `AUTO_PROCESS` |
| `SET-04` | Thiếu evidence cho một khoản | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-05` | Tổng thanh toán OCR không rõ | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-06` | Claimed amount khác document amount | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-07` | Thiếu business purpose bắt buộc | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-08` | Đơn giấy thiếu chữ ký kế toán trưởng | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-09` | Exact duplicate lịch sử | `ESCALATE/OUTSIDE_POLICY` |
| `SET-10` | Probable duplicate chưa đủ căn cứ | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-11` | Chi phí cá nhân rõ ràng | `ESCALATE/OUTSIDE_POLICY` |
| `SET-12` | Tổng vượt authority amount | `ESCALATE/BEYOND_AUTHORITY` |
| `SET-13` | Nộp quá submission window | `ESCALATE/OUTSIDE_POLICY` |
| `SET-14` | Một document phân bổ cho hai item hợp lệ | `AUTO_PROCESS` |
| `SET-15` | Allocation vượt document total | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-16` | Quyết toán một phần advance | `AUTO_PROCESS`, giữ remaining balance |
| `SET-17` | OCR API lỗi sau retry | `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `SET-18` | LLM trả JSON sai schema sau retry | `REQUEST_INFO/FACTUAL_UNKNOWN` |

## 23. Verify harness

Nút `Verify -> Escalation` chạy ít nhất năm case qua cùng service:

| Verify ID | Fixture | Expected |
| --- | --- | --- |
| `V-01` | `SET-01` | `AUTO_PROCESS` |
| `V-02` | `SET-02` | `AUTO_PROCESS` |
| `V-03` | `SET-03` | `AUTO_PROCESS` |
| `V-04` | `SET-05` | `REQUEST_INFO` và câu hỏi số tiền cụ thể |
| `V-05` | `SET-12` | `ESCALATE/BEYOND_AUTHORITY` |

Output:

```text
case_id | expected | actual | uncertainty | question/target | duration | timestamp | PASS/FAIL
```

Verify offline dùng recorded OCR/LLM fixtures để ổn định và nhanh. Phải có một smoke mode gọi adapter thật để chứng minh sản phẩm không chỉ hardcode fixture.

## 24. Chỉ số đánh giá

Trên tập test độc lập:

```text
missed_escalation_rate
unnecessary_escalation_rate
decision_accuracy_by_uncertainty_type
field_accuracy_for_critical_fields
median_processing_time
human_review_time
external_call_count_per_case
```

Đo trước/sau với kế toán thật phải ghi phương pháp, số mẫu và hạn chế; không chỉ tuyên bố “nhanh hơn”.

## 25. Definition of Done

- Một digital case và một paper case chạy end-to-end tới tab Kế toán.
- Ba case thường quy tự `AUTO_PROCESS` mà không hỏi thừa.
- Hai case cần người được chuyển đúng loại và có câu hỏi/target cụ thể.
- Không có critical unknown nào `AUTO_PROCESS`.
- Item, số tiền, finding và decision đều truy được về nguồn.
- Kế toán dừng, chạy lại và override được; audit hiển thị before/after/lý do.
- Verify chạy một nút, có timestamp và không phụ thuộc kết quả hardcode.
- Dữ liệu demo, approval mô phỏng và thành phần chưa tích hợp được ghi nhãn rõ.

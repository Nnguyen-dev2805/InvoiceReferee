# UC-02 Implementation Plan - Đề nghị tạm ứng

## 1. Trạng thái và mục tiêu

- Mức ưu tiên: sau UC-03, trước UC-01 nếu cần demo hành trình tạm ứng -> hoàn ứng.
- Vai trò trong cuộc thi: workflow mở rộng.
- Mục tiêu: tiếp nhận form điện tử hoặc đơn giấy, chuẩn hóa cùng schema, kiểm tra policy và chuẩn bị hồ sơ cho chuỗi phê duyệt.
- Không thuộc phạm vi MVP: chữ ký số thật, tích hợp ngân hàng, tự động giải ngân và hạch toán.

## 2. Quyết định thiết kế

1. Form điện tử và đơn giấy là hai ingestion adapter của cùng `ADVANCE_REQUEST`.
2. Canonical JSON là nguồn dữ liệu xử lý; PDF là snapshot trình bày.
3. Đơn giấy thiếu chữ ký phải tải lại phiên bản mới.
4. Chữ ký tay không bao giờ được gắn `VERIFIED` bởi AI.
5. Approval mô phỏng phải ghi rõ `SIMULATED_APPROVAL`.
6. `APPROVED` và `DISBURSED` là hai trạng thái khác nhau.
7. Tab Kế toán là UI ưu tiên; chưa xây portal riêng cho từng chức danh.

## 3. Khoảng cách so với code hiện tại

Code hiện tại chỉ nhận `ClaimDraft(recipient, subject, body)` và file `PRIMARY/SUPPORTING`. Cần bổ sung:

- Chọn `case_type` và `source_type`.
- Structured form thay cho email body khi dùng `DIGITAL_FORM`.
- Schema advance request.
- Document version và hash.
- PDF generator.
- Signature/approval status.
- PolicyConfig và lịch sử tạm ứng giả lập.
- Lifecycle, Track A decision và audit mở rộng.

## 4. Hợp đồng đầu vào

### 4.1. Form điện tử

```json
{
  "case_type": "ADVANCE_REQUEST",
  "source_type": "DIGITAL_FORM",
  "employee": {
    "employee_id": "EMP-DEMO-001",
    "name": "Nguyễn Minh An",
    "department": "Phòng Kinh doanh",
    "position": "Nhân viên"
  },
  "advance_request": {
    "request_date": "2026-10-10",
    "purpose": "Công tác gặp khách hàng tại Hà Nội",
    "requested_amount": "5000000",
    "currency": "VND",
    "amount_in_words": "Năm triệu đồng",
    "activity_start_date": "2026-10-15",
    "activity_end_date": "2026-10-17",
    "settlement_deadline": "2026-10-24",
    "cost_center": "SALES",
    "project_code": "DEMO-2026",
    "estimate_lines": [],
    "notes": null
  }
}
```

`amount_in_words` có thể được sinh từ số tiền cho form điện tử; nhân viên không cần nhập lại nếu hệ thống có converter tiếng Việt được test.

### 4.2. Đơn giấy

```json
{
  "case_type": "ADVANCE_REQUEST",
  "source_type": "PAPER_SCAN",
  "documents": [
    {
      "document_role": "ADVANCE_REQUEST_FORM",
      "file": "giay_de_nghi_tam_ung.pdf"
    }
  ]
}
```

Đơn giấy được kỳ vọng có:

- Đơn vị, bộ phận.
- Ngày và số chứng từ nếu mẫu có.
- Người đề nghị.
- Số tiền bằng số và bằng chữ.
- Lý do tạm ứng.
- Thời hạn thanh toán/hoàn ứng.
- Chữ ký người đề nghị, phụ trách bộ phận, kế toán trưởng và giám đốc theo policy demo.

## 5. Domain model mục tiêu

Tạo `src/invoice_referee/domain/advance.py`:

```python
class SubmissionSourceType(StrEnum):
    DIGITAL_FORM = "DIGITAL_FORM"
    PAPER_SCAN = "PAPER_SCAN"

class SignatureStatus(StrEnum):
    PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
    MISSING = "MISSING"
    UNCLEAR = "UNCLEAR"
    NOT_REQUIRED = "NOT_REQUIRED"
    VERIFIED = "VERIFIED"

class ApprovalMethod(StrEnum):
    WET_SIGNATURE_SCAN = "WET_SIGNATURE_SCAN"
    SIMULATED_APPROVAL = "SIMULATED_APPROVAL"
    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"

class ApprovalRecord(BaseModel):
    role: Literal[
        "REQUESTER",
        "DEPARTMENT_MANAGER",
        "CHIEF_ACCOUNTANT",
        "DIRECTOR",
    ]
    actor_id: str | None
    actor_name: str | None
    method: ApprovalMethod
    status: str
    recorded_at: datetime | None
    document_version: int
    document_hash: str
    source_refs: list[str]
    note: str | None

class AdvanceEstimateLine(BaseModel):
    line_id: str
    category: str
    description: str
    amount: Decimal
    currency: str = "VND"
    source_refs: list[str] = Field(default_factory=list)

class AdvanceRequestData(BaseModel):
    employee_id: str
    requester_name: str
    department: str
    position: str | None
    request_date: date
    purpose: str
    requested_amount: Decimal
    currency: str
    amount_in_words: str | None
    activity_start_date: date | None
    activity_end_date: date | None
    settlement_deadline: date
    cost_center: str | None
    project_code: str | None
    estimate_lines: list[AdvanceEstimateLine]
    approvals: list[ApprovalRecord]
    source_refs: list[str]
```

Tạo `AdvanceBalance` trong adapter lịch sử, không nhúng trực tiếp logic database vào domain:

```python
class AdvanceBalance(BaseModel):
    advance_id: str
    employee_id: str
    disbursed_amount: Decimal
    settled_amount: Decimal
    outstanding_amount: Decimal
    due_date: date
    status: str
```

## 6. Document version và PDF

### 6.1. Nguồn dữ liệu

- Canonical JSON được lưu trước.
- PDF được render từ canonical JSON.
- `document_hash = sha256(pdf_bytes)`.
- Mỗi thay đổi sau submit tạo `document_version + 1`; không ghi đè artifact cũ.

### 6.2. PDF generator

Thêm dependency dự kiến `reportlab>=4,<5`. Dùng font Unicode được nhúng và có giấy phép phù hợp để hiển thị tiếng Việt.

Module:

```text
src/invoice_referee/documents/advance_pdf.py
```

PDF phải chứa:

- Case ID và version ở footer.
- Dữ liệu form.
- Khu vực approval theo đúng chuỗi.
- Nhãn rõ “Bản mô phỏng - không phải chữ ký số thật” trong MVP.

XML chưa triển khai khi chưa có schema tích hợp cụ thể. Không tự đặt một XML format không có consumer.

## 7. Workflow - form điện tử

```text
Nhập structured form
  -> client-side validation
  -> server-side Pydantic validation
  -> business validation
  -> lưu canonical JSON version 1
  -> render PDF + hash
  -> policy checks
  -> tạo approval timeline trạng thái PENDING
  -> Decision Guard
  -> tab Kế toán
```

Form điện tử không gọi OCR, Confidence Agent hoặc extraction LLM. LLM chỉ được dùng để đánh giá purpose quá mơ hồ nếu rule deterministic không đủ; kết quả là đề xuất, không phải quyết định cuối.

## 8. Workflow - đơn giấy

```text
Upload scan
  -> validate file
  -> OCR
  -> Confidence Gate theo ADVANCE_REQUEST_FORM
  -> signature-region detection
  -> extract AdvanceRequestData
  -> Pydantic validation
  -> signature completeness policy
  -> business policy
  -> Decision Guard
  -> tab Kế toán
```

Signature detection nên ưu tiên layout/VLM trên toàn trang, không dựa riêng vào word OCR. Mỗi signature result phải có bbox và source reference.

## 9. Chuỗi phê duyệt

Chuỗi mặc định của PolicyConfig demo:

```text
REQUESTER
-> DEPARTMENT_MANAGER
-> CHIEF_ACCOUNTANT
-> DIRECTOR
```

Nguyên tắc:

- Đơn giấy phải có đầy đủ các vai trò theo policy, bất kể chữ ký Giám đốc xuất hiện trước.
- Form điện tử tạo tất cả approval ở trạng thái `PENDING`.
- MVP chỉ hiển thị timeline ở tab Kế toán và có thể ghi approval mô phỏng để test audit.
- Approval tương lai chỉ hợp lệ khi áp dụng cho đúng `document_hash`.
- Sửa form sau approval làm approval phiên bản cũ không còn áp dụng cho phiên bản mới.

## 10. PolicyConfig demo

```yaml
policy_id: DEMO-ADVANCE-2026
policy_version: "1.0"
data_classification: SYNTHETIC
currency: VND
require_settlement_deadline: true
maximum_days_after_activity: 7
block_if_overdue_advance_exists: true
required_approval_roles:
  - REQUESTER
  - DEPARTMENT_MANAGER
  - CHIEF_ACCOUNTANT
  - DIRECTOR
authority_limits:
  accounting_auto_review: 10000000
  director_required_above: 10000000
prohibited_purposes: []
```

Các giá trị chỉ phục vụ demo và phải hiển thị nhãn synthetic. Không dùng tên công ty thật.

## 11. Policy rules

| Rule ID | Kiểm tra | Failure mapping |
| --- | --- | --- |
| `ADV_INPUT_001` | Đủ trường form bắt buộc | Thiếu -> `REQUEST_INFO` |
| `ADV_QUALITY_001` | Critical field đơn giấy đọc rõ | Không rõ -> `REQUEST_INFO` |
| `ADV_AMOUNT_001` | Số tiền > 0 và currency hỗ trợ | Sai/không rõ -> `REQUEST_INFO` |
| `ADV_WORDS_001` | Số bằng chữ khớp số bằng số nếu có | Không khớp -> `REQUEST_INFO` |
| `ADV_PURPOSE_001` | Purpose cụ thể đủ để hiểu nghiệp vụ | Mơ hồ -> `REQUEST_INFO` |
| `ADV_DEADLINE_001` | Deadline hợp lệ theo policy | Quá/ngoài policy rõ -> `ESCALATE` |
| `ADV_SIGNATURE_001` | Đủ chữ ký tay bắt buộc với paper | Thiếu/mờ -> `REQUEST_INFO` |
| `ADV_HISTORY_001` | Kiểm tra tạm ứng cũ | Tool lỗi -> `REQUEST_INFO`; quá hạn -> theo policy |
| `ADV_AUTH_001` | Amount trong thẩm quyền | Vượt -> `ESCALATE/BEYOND_AUTHORITY` |
| `ADV_CATEGORY_001` | Purpose không thuộc danh mục cấm | Bị cấm rõ -> `ESCALATE/OUTSIDE_POLICY` |

## 12. Decision và lifecycle

Ví dụ:

```text
AUTO_PROCESS + WAITING_FOR_APPROVAL
```

nghĩa là hồ sơ đủ dữ kiện để đi tiếp tới người duyệt; không có nghĩa đã duyệt.

```text
REQUEST_INFO + WAITING_FOR_INFORMATION
```

nghĩa là cần nhân viên bổ sung dữ kiện/chữ ký.

```text
ESCALATE + WAITING_FOR_APPROVAL
```

nghĩa là dữ kiện đã rõ nhưng cần cấp có thẩm quyền hoặc chủ policy quyết định.

Sau approval:

```text
APPROVED
  -> ghi nhận giao dịch thực chi
DISBURSED
  -> tạo advance_id và AdvanceBalance
```

Không tạo `AdvanceBalance` tại thời điểm submit hoặc approval.

## 13. Phân chia hardcode, LLM và tool

| Công việc | Thành phần |
| --- | --- |
| Validate structured form | Pydantic + Python |
| Sinh PDF/hash/version | Python |
| OCR đơn giấy | OCR adapter |
| Đánh giá low-confidence candidate | Confidence LLM, batch/file |
| Trích xuất đơn giấy | Extraction LLM + Pydantic |
| Phát hiện vùng chữ ký | VLM/layout adapter |
| Xác thực chữ ký tay | Không hỗ trợ; con người |
| Xác thực chữ ký số | Chưa triển khai; tương lai dùng signature tool |
| Kiểm tra lịch sử advance | Repository/tool |
| Hạn mức/deadline/amount | Python + PolicyConfig |
| Purpose mơ hồ | Rule trước, LLM hỗ trợ sau |
| Action cuối | Decision Guard |

## 14. UI

### 14.1. Tab Nhân viên

- Chọn `Điền form điện tử` hoặc `Tải đơn giấy đã ký` bằng segmented control.
- Form điện tử hiển thị field có cấu trúc; amount in words được sinh tự động.
- Đơn giấy có một upload zone chính và hướng dẫn các chữ ký bắt buộc.
- Sau submit hiển thị case ID và trạng thái, không tuyên bố “đã được duyệt”.

### 14.2. Tab Kế toán

Thứ tự hiển thị:

1. Người đề nghị, purpose, amount, deadline.
2. Source type và document version.
3. Automation decision và workflow status.
4. Approval/signature timeline.
5. Tạm ứng cũ và authority check.
6. Findings, câu hỏi và target.
7. PDF/scan gốc và bbox.
8. Audit timeline.

Hành động MVP:

- Xác nhận kết quả kiểm tra.
- Yêu cầu bổ sung.
- Chuyển cấp có thẩm quyền.
- Dừng/chạy lại.
- Ghi đè có lý do.
- Ghi approval mô phỏng nếu cần demo audit; phải gắn nhãn mô phỏng.

## 15. Storage và audit

Artifacts:

```text
submission.json
canonical/advance_request.v1.json
documents/advance_request.v1.pdf
documents/source_scan.*
ocr/{document_id}.json
facts/{document_id}.json
decision.json
audit.jsonl
```

Audit events bổ sung:

```text
FORM_VALIDATED
DOCUMENT_VERSION_CREATED
PDF_RENDERED
SIGNATURE_REGION_DETECTED
APPROVAL_STATUS_EVALUATED
APPROVAL_RECORDED
ADVANCE_HISTORY_CHECKED
DISBURSEMENT_RECORDED
```

## 16. Module triển khai

| File/module | Thay đổi |
| --- | --- |
| `domain/advance.py` | Advance schema, approval/signature models |
| `domain/cases.py` | Source type và lifecycle |
| `documents/advance_pdf.py` | PDF generator |
| `application/submit_advance.py` | Hai ingestion paths |
| `application/process_advance.py` | UC-02 orchestrator |
| `extraction/advance_form.py` | Paper extraction schema/prompt |
| `extraction/signature_detection.py` | Signature region adapter |
| `policy/advance.py` | Rules |
| `policy/decision_guard.py` | Action mapping |
| `storage/advance_repository.py` | History/balance port và local fake adapter |
| `app/components/advance_form.py` | Structured form |
| `app/views/accounting_review.py` | Approval timeline và advance summary |

## 17. Thứ tự triển khai

### Phase 1 - Structured form

- [ ] Models và validators.
- [ ] Form UI.
- [ ] Canonical persistence/version/hash.
- [ ] PDF generator.
- [ ] Unit tests tiếng Việt và amount in words.

### Phase 2 - Paper ingestion

- [ ] OCR/Confidence integration.
- [ ] Advance extraction prompt/schema.
- [ ] Signature presence detection.
- [ ] Signature completeness policy.

### Phase 3 - Policy và history

- [ ] PolicyConfig loader.
- [ ] Synthetic advance history adapter.
- [ ] Authority/deadline/purpose rules.
- [ ] Decision Guard mapping.

### Phase 4 - Accounting UI và audit

- [ ] Advance summary.
- [ ] Signature/approval timeline.
- [ ] Findings/source drill-down.
- [ ] Human action, stop, rerun, override.

### Phase 5 - Verify

- [ ] Digital form thường quy.
- [ ] Paper đầy đủ chữ ký.
- [ ] Paper thiếu kế toán trưởng.
- [ ] Vượt hạn mức.
- [ ] Có advance cũ quá hạn.

## 18. Kiểm thử bắt buộc

- Structured form không gọi OCR/LLM.
- Sửa form tạo version/hash mới.
- Approval cũ không tự áp dụng cho hash mới.
- Chữ ký tay luôn `PRESENT_UNVERIFIED`, không `VERIFIED`.
- Thiếu một chữ ký trả câu hỏi nêu đúng vai trò thiếu.
- `APPROVED` không tạo balance; `DISBURSEMENT_RECORDED` mới tạo.
- Tool lịch sử lỗi phải fail closed.
- Amount/deadline dùng timezone và `Decimal` xác định.

## 19. Definition of Done

- Hai kênh đầu vào tạo cùng `AdvanceRequestData`.
- PDF tiếng Việt render đúng và truy vết được về JSON/version/hash.
- Policy demo được đánh dấu synthetic.
- Accounting UI giải thích được vì sao case đi tiếp, cần bổ sung hoặc chuyển cấp.
- Audit tái lập được toàn bộ hành động chính.
- Không có nội dung nào tuyên bố approval mô phỏng là chữ ký số thật.

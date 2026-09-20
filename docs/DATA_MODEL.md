# InvoiceReferee — Mô hình dữ liệu

## 1. Mục đích

Tài liệu này cố định lược đồ chung để các phần tiếp nhận dữ liệu, bộ máy kiểm tra, chính sách, tác tử LLM, giao diện và Verify có thể được phát triển độc lập nhưng vẫn ghép nối được.

Đối tượng trung tâm là **`ReviewCase`**, không phải một tệp hóa đơn riêng lẻ.

```text
RawDocument[]
      ↓
ExtractedDocument[]
      ↓
CanonicalDocument[]
      +
EmployeeClaim / SupportingEvidence[] / Policy
      ↓
ReviewCase
      ↓
CheckResult[] + PolicyContext
      ↓
AgentAssessment
      ↓
Decision
      ↓
AuditEvent[]
```

## 2. Nguyên tắc chung

- Tiền dùng **số nguyên VND**, không dùng số thực.
- Ngày dùng `YYYY-MM-DD`; dấu thời gian dùng ISO 8601.
- Trường chưa biết dùng `null`, không tự suy đoán.
- Cảnh báo/độ tin cậy của quá trình trích xuất phải được giữ đến các bước sau.
- Quy tắc/phép kiểm tra phải có tham chiếu bằng chứng để kiểm toán.
- Giao diện và Verify phải dùng cùng một `ReviewResult` từ dịch vụ `review()` của sản phẩm.

## 3. Kiểu liệt kê

### `document_type`

```text
E_INVOICE
EMPLOYEE_RECEIPT
PAYMENT_PROOF
PURCHASE_ORDER
RECEIVING_PROOF
SERVICE_ACCEPTANCE
EMPLOYEE_CLAIM
OTHER_SUPPORTING_DOC
UNKNOWN
```

### `expense_category`

```text
MEAL_ENTERTAINMENT
TRANSPORTATION
TRAVEL_LODGING
OFFICE_SUPPLIES
OPERATIONS
SERVICE_FEE
PERSONAL
PROHIBITED
UNKNOWN
```

### `decision.action`

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

### `uncertainty.type`

```text
FACTUAL_UNKNOWN
OUTSIDE_POLICY
BEYOND_AUTHORITY
SUSPICIOUS
```

Ánh xạ:

```text
FACTUAL_UNKNOWN  → REQUEST_INFO
OUTSIDE_POLICY   → ESCALATE
BEYOND_AUTHORITY → ESCALATE
SUSPICIOUS       → ESCALATE
```

## 4. `ExtractedDocument`

Mọi bộ chuyển đổi đều phải trả về hợp đồng này trước khi chuẩn hóa.

```json
{
  "document_id": "DOC-001",
  "document_type": "E_INVOICE",
  "source_type": "PDF_TEXT",
  "source_ref": "upload://invoice-001.pdf",
  "extractor": "pdf_text_adapter",
  "fields": {
    "seller_tax_code": "0101234567",
    "buyer_tax_code": "0319999999",
    "invoice_number": "0000123",
    "invoice_date": "2026-09-13",
    "total_amount": 30000000
  },
  "field_confidence": {
    "total_amount": 0.98
  },
  "parse_warnings": []
}
```

Các trường bắt buộc:

- `document_id`
- `document_type`
- `source_type`
- `source_ref`
- `extractor`
- `fields`
- `parse_warnings`

`source_type` có thể là `JSON`, `XML`, `PDF_TEXT`, `OCR`, `IMAGE` hoặc `MANUAL`.

## 5. `CanonicalDocument`

Sau khi chuẩn hóa, mỗi chứng từ đi vào `ReviewCase` dưới một cấu trúc chung.

```json
{
  "document_id": "DOC-001",
  "document_type": "E_INVOICE",
  "issuer_name": "Nhà cung cấp ABC",
  "issuer_tax_code": "0101234567",
  "buyer_name": "Công ty của chúng ta",
  "buyer_tax_code": "0319999999",
  "document_date": "2026-09-13",
  "invoice_template_no": "1",
  "invoice_serial_no": "C26TAA",
  "invoice_number": "0000123",
  "tax_authority_code": null,
  "currency": "VND",
  "items": [
    {
      "item_id": null,
      "description": "Màn hình Dell",
      "item_type": "GOODS",
      "quantity": 10,
      "unit_price": 3000000,
      "line_total": 30000000
    }
  ],
  "subtotal_amount": 30000000,
  "discount_amount": 0,
  "tax_amount": 0,
  "service_charge": 0,
  "total_amount": 30000000,
  "amount_in_words": null,
  "payment_method": "BANK_TRANSFER",
  "expense_category": "OFFICE_SUPPLIES",
  "extraction_warnings": [],
  "source_refs": ["DOC-001"]
}
```

Trường bắt buộc theo loại chứng từ:

- `E_INVOICE`: tên và mã số thuế bên mua/bên bán, ngày, tên hàng hóa/dịch vụ, số lượng với hàng hóa, tổng tiền, mẫu số, ký hiệu và số hóa đơn.
- `EMPLOYEE_RECEIPT`: cửa hàng nếu nhìn thấy, ngày giao dịch nếu nhìn thấy, tổng tiền, phương thức thanh toán/hàng hóa nếu nhìn thấy.
- `PAYMENT_PROOF`: người trả/người nhận nếu nhìn thấy, ngày giao dịch, số tiền và phương thức/mã tham chiếu thanh toán nếu nhìn thấy.

## 6. `EmployeeClaim`

Thông tin thường không có sẵn trên hóa đơn/chứng từ.

```json
{
  "claim_id": "CLM-001",
  "employee_id": "EMP-001",
  "employee_name": "Nguyễn Văn A",
  "business_purpose": "Gặp khách hàng cho Dự án Phoenix",
  "client_or_project": "Dự án Phoenix",
  "expense_category": "MEAL_ENTERTAINMENT",
  "claimed_amount": 1200000,
  "claim_date": "2026-09-14",
  "submitted_at": "2026-09-15T09:00:00+07:00"
}
```

## 7. `SupportingEvidence`

Dùng cho PO, biên bản nhận hàng, nghiệm thu dịch vụ, lịch sử thanh toán và dữ liệu gốc về nhà cung cấp/khách hàng.

```json
{
  "evidence_id": "EV-001",
  "evidence_type": "PURCHASE_ORDER",
  "linked_document_ids": ["DOC-001"],
  "fields": {
    "po_id": "PO-001",
    "approved_total": 30000000,
    "ordered_quantity": 10
  },
  "source_ref": "api://po/PO-001"
}
```

`evidence_type` có thể là:

```text
PURCHASE_ORDER
RECEIVING_PROOF
SERVICE_ACCEPTANCE
PAYMENT_RECORD
PROCESSED_HISTORY
VENDOR_MASTER
COMPANY_PROFILE
POLICY_CONFIG
```

## 8. `ReviewCase`

```json
{
  "case_id": "CASE-001",
  "case_type": "EXPENSE_DOCUMENT_REVIEW",
  "documents": [],
  "employee_claim": null,
  "supporting_evidence": [],
  "company_profile": {
    "company_name": "Công ty của chúng ta",
    "tax_code": "0319999999"
  },
  "checks": [],
  "decision": null,
  "workflow_status": "ACTIVE",
  "created_at": "2026-09-20T10:00:00+07:00",
  "updated_at": "2026-09-20T10:00:00+07:00"
}
```

`case_type`:

```text
E_INVOICE_REVIEW
EMPLOYEE_EXPENSE_CLAIM
PAYMENT_PROOF_REVIEW
MIXED_EVIDENCE_REVIEW
UNKNOWN
```

`workflow_status`:

```text
ACTIVE
STOPPED
```

## 9. `CheckResult`

```json
{
  "check_id": "CHECK_REQUIRED_FIELDS",
  "policy_rule_id": "P01",
  "status": "FAIL",
  "expected": ["buyer_tax_code"],
  "actual": null,
  "reason": "Thiếu mã số thuế bắt buộc của bên mua",
  "evidence_refs": ["DOC-001"]
}
```

`status`:

```text
PASS
FAIL
UNKNOWN
NOT_APPLICABLE
```

`FAIL` không tự động đồng nghĩa với `ESCALATE`; Bộ bảo vệ quyết định phải ánh xạ theo chính sách.

## 10. `PolicyContext`

```json
{
  "scope_status": "IN_SCOPE",
  "authority_threshold_vnd": 50000000,
  "applicable_rule_ids": ["P01", "P05", "P12"],
  "deterministic_uncertainties": ["FACTUAL_UNKNOWN"],
  "suspicious_flags": []
}
```

`scope_status`:

```text
IN_SCOPE
OUTSIDE_POLICY
UNKNOWN
```

## 11. `AgentAssessment`

```json
{
  "proposed_uncertainty_type": "FACTUAL_UNKNOWN",
  "proposed_action": "REQUEST_INFO",
  "primary_check_id": "CHECK_BUSINESS_CONTEXT",
  "explanation": "Chứng từ có tổng tiền nhưng thiếu mục đích kinh doanh và dự án.",
  "question": "Chứng từ 1,2 triệu đồng đã có tổng tiền nhưng chưa có mục đích kinh doanh/dự án. Khoản chi này phục vụ mục đích kinh doanh nào và gắn với khách hàng/dự án nào?",
  "target": "Nhân viên",
  "policy_rule_ids": ["P08"],
  "evidence_refs": ["DOC-002", "CLM-001"],
  "model": "configured-llm",
  "prompt_version": "v1",
  "fallback_used": false
}
```

LLM không được tự tạo/sửa dữ kiện, tự tính tiền/số lượng hoặc bỏ qua thẩm quyền.

## 12. `Decision`

```json
{
  "action": "REQUEST_INFO",
  "reason": "Chứng từ của nhân viên đang thiếu mục đích kinh doanh",
  "uncertainty": {
    "type": "FACTUAL_UNKNOWN",
    "field": "employee_claim.business_purpose"
  },
  "question": "Khoản chi 1,2 triệu đồng này phục vụ mục đích kinh doanh nào và gắn với khách hàng/dự án nào?",
  "target": "Nhân viên",
  "policy_rule_ids": ["P08"],
  "decided_at": "2026-09-20T10:04:00+07:00"
}
```

Quy tắc:

- `AUTO_PROCESS`: `question = null`, `target = null`.
- `REQUEST_INFO`: loại không chắc chắn phải là `FACTUAL_UNKNOWN` và phải có `question`.
- `ESCALATE`: loại không chắc chắn phải là `OUTSIDE_POLICY`, `BEYOND_AUTHORITY` hoặc `SUSPICIOUS`; nên có `target` khi chính sách xác định được.

## 13. `AuditEvent`

```json
{
  "event_id": "AUD-001",
  "case_id": "CASE-001",
  "event_type": "CHECK_COMPLETED",
  "actor": "InvoiceReferee",
  "timestamp": "2026-09-20T10:03:00+07:00",
  "rule_id": "P05",
  "input_refs": ["DOC-001"],
  "result": "PASS",
  "reason": "Mã số thuế bên mua khớp hồ sơ công ty",
  "details": {}
}
```

Các loại sự kiện đề xuất:

```text
CASE_CREATED
DOCUMENT_EXTRACTED
EVIDENCE_ATTACHED
CHECK_COMPLETED
LLM_ASSESSMENT_CREATED
LLM_FALLBACK_USED
DECISION_GUARD_APPLIED
DECISION_MADE
INFO_REQUESTED
ESCALATED
STOPPED
OVERRIDDEN
```

## 14. Kiểm soát của con người

### `HumanStop`

```json
{
  "stop_id": "STOP-001",
  "actor": "accountant@example.com",
  "timestamp": "2026-09-20T10:10:00+07:00",
  "previous_workflow_status": "ACTIVE",
  "new_workflow_status": "STOPPED",
  "reason": "Cần xác minh nhà cung cấp theo cách thủ công"
}
```

### `HumanOverride`

```json
{
  "override_id": "OVR-001",
  "actor": "accountant@example.com",
  "timestamp": "2026-09-20T10:12:00+07:00",
  "original_action": "AUTO_PROCESS",
  "overridden_action": "ESCALATE",
  "reason": "Quản lý tài chính yêu cầu kiểm tra thủ công"
}
```

## 15. `ReviewResult`

```text
ReviewResult
├── review_case
├── extracted_documents
├── canonical_documents
├── checks
├── policy_context
├── agent_assessment
├── decision
└── audit_events
```

Mã sản phẩm, giao diện và Verify không được tự tính lại quyết định; tất cả phải dùng `ReviewResult` từ `review()`.

# InvoiceReferee — Kiến trúc

## 1. Mục tiêu

Kiến trúc Sprint 1 ưu tiên:

- kiểm tra xuyên suốt hóa đơn điện tử và chứng từ của nhân viên;
- tách phần trích xuất khỏi quyết định nghiệp vụ;
- dùng phép kiểm tra tất định cho tiền, số lượng, trùng lặp và ngưỡng;
- có ranh giới quyết định rõ ràng;
- có khả năng kiểm toán;
- giao diện và Verify dùng chung luồng `review()` của sản phẩm;
- các mô-đun độc lập để nhóm có thể phát triển song song.

## 2. Kiến trúc tổng thể

```text
                   ┌──────────────────────┐
                   │  Bằng chứng thô      │
                   │ JSON/XML/PDF/Ảnh     │
                   └──────────┬───────────┘
                              ↓
                  ┌────────────────────┐
                  │ Bộ trích xuất      │
                  │ đọc / OCR / ánh xạ │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Chuẩn hóa          │
                  │ CanonicalDocument  │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Tạo ReviewCase     │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Bộ máy kiểm tra    │
                  │ quy tắc tất định   │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Ràng buộc chính sách│
                  │ phạm vi + thẩm quyền│
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Tác tử LLM         │
                  │ đầu ra có cấu trúc │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Bảo vệ quyết định  │
                  │ cổng tất định      │
                  └────────┬───────────┘
                            ↓
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
    AUTO_PROCESS      REQUEST_INFO        ESCALATE
          └─────────────────┼─────────────────┘
                            ↓
                  ┌────────────────────┐
                  │ Kiểm toán + Kiểm soát│
                  │ của con người      │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Giao diện / Verify │
                  └────────────────────┘
```

## 3. Cấu trúc kho mã nguồn đề xuất

```text
InvoiceReferee/
├── app/
│   └── streamlit_app.py
├── src/
│   └── invoice_referee/
│       ├── domain/
│       │   └── models.py
│       ├── ingestion/
│       │   ├── json_adapter.py
│       │   ├── xml_invoice_adapter.py
│       │   ├── ocr_adapter.py
│       │   └── normalization.py
│       ├── review_case/
│       │   └── builder.py
│       ├── checks/
│       │   ├── engine.py
│       │   ├── required_fields.py
│       │   ├── extraction_quality.py
│       │   ├── identity.py
│       │   ├── arithmetic.py
│       │   ├── duplicate.py
│       │   ├── context.py
│       │   ├── evidence.py
│       │   ├── policy_category.py
│       │   ├── payment.py
│       │   ├── authority.py
│       │   └── anomaly.py
│       ├── policy/
│       │   ├── config.py
│       │   └── engine.py
│       ├── agent/
│       │   ├── llm_client.py
│       │   ├── prompts.py
│       │   └── service.py
│       ├── decision/
│       │   ├── guard.py
│       │   └── fallback_questions.py
│       ├── audit/
│       │   └── store.py
│       └── services/
│           └── reviewer.py
├── verify/
│   └── harness.py
├── tests/
│   ├── fixtures/
│   ├── test_checks.py
│   ├── test_decision.py
│   ├── test_audit.py
│   └── test_verify.py
└── docs/
```

## 4. Trách nhiệm của từng mô-đun

### Miền nghiệp vụ

Chứa các hợp đồng lược đồ trong `DATA_MODEL.md`: `ExtractedDocument`, `CanonicalDocument`, `EmployeeClaim`, `SupportingEvidence`, `ReviewCase`, `CheckResult`, `PolicyContext`, `AgentAssessment`, `Decision`, `ReviewResult`, dữ liệu kiểm toán và kiểm soát của con người.

### Tiếp nhận dữ liệu

Đọc nguồn thô và trả về `ExtractedDocument`.

Các bộ chuyển đổi:

- đầu vào JSON/API có cấu trúc;
- XML hóa đơn điện tử;
- PDF có văn bản;
- OCR/thị giác cho PDF quét hoặc ảnh;
- khai báo thủ công của nhân viên.

Bộ chuyển đổi không kết luận quy tắc nghiệp vụ. Trường không chắc chắn phải giữ cảnh báo/độ tin cậy.

### Bộ tạo `ReviewCase`

Gộp các chứng từ, khai báo của nhân viên, hồ sơ công ty và bằng chứng bổ sung thành một `ReviewCase`.

### Bộ máy kiểm tra

Chạy các phép kiểm tra tất định:

- trường bắt buộc;
- chất lượng trích xuất;
- danh tính công ty/nhà cung cấp;
- ngày/thời hạn nộp;
- số học;
- trùng lặp;
- bối cảnh kinh doanh;
- tính nhất quán giữa đề nghị chi, thanh toán và bằng chứng bổ sung;
- bằng chứng nhận hàng/dịch vụ;
- danh mục chính sách;
- trạng thái thanh toán;
- ngưỡng thẩm quyền;
- bất thường/nghi vấn;
- mức độ sẵn sàng để xuất dữ liệu kế toán.

Bộ máy kiểm tra không tạo quyết định cuối cùng.

### Bộ máy chính sách

Tạo `PolicyContext`: phạm vi, mã quy tắc, ngưỡng, các điểm không chắc chắn và cờ nghi vấn.

### Tác tử LLM

Nhận dữ kiện/phép kiểm tra/chính sách có cấu trúc, trả về `AgentAssessment` gồm giải thích, hành động đề xuất, phép kiểm tra chính, câu hỏi, đối tượng và tham chiếu.

LLM không tính tiền, không sửa kết quả kiểm tra và không tạo chính sách mới.

### Bộ bảo vệ quyết định

Cổng tất định:

```text
FACTUAL_UNKNOWN  → REQUEST_INFO
OUTSIDE_POLICY   → ESCALATE
BEYOND_AUTHORITY → ESCALATE
SUSPICIOUS       → ESCALATE
tất cả đều đạt   → AUTO_PROCESS
```

### Kho kiểm toán

Lưu sự kiện theo kiểu chỉ ghi nối tiếp. Sprint 1 có thể dùng bộ nhớ, phiên làm việc hoặc tệp JSON.

### Dịch vụ kiểm tra

Bộ điều phối duy nhất:

```text
trích xuất → chuẩn hóa → tạo hồ sơ → kiểm tra → chính sách → LLM → bảo vệ → kiểm toán
```

Giao diện và Verify chỉ gọi dịch vụ này.

## 5. Giao diện cốt lõi

```python
extract(raw_evidence) -> list[ExtractedDocument]
normalize(extracted) -> list[CanonicalDocument]
build_review_case(documents, claim, evidence, company_profile) -> ReviewCase
run_checks(review_case) -> list[CheckResult]
build_policy_context(review_case, checks) -> PolicyContext
assess(review_case, checks, policy_context) -> AgentAssessment
guard(assessment, review_case, checks, policy_context) -> Decision
review(input_payload) -> ReviewResult
run_verify(case_ids) -> list[VerifyResult]
```

## 6. Xử lý lỗi

```text
JSON/XML sai định dạng
→ INPUT_ERROR

Hóa đơn hợp lệ về hình thức nhưng thiếu mã số thuế bên mua
→ REQUEST_INFO

Mã số thuế bên mua thuộc công ty khác
→ ESCALATE / OUTSIDE_POLICY
```

Không biến lỗi kỹ thuật thành quyết định nghiệp vụ.

## 7. Các tầng kiểm thử

```text
Kiểm thử đơn vị
  → bộ phân tích / phép kiểm tra / quy tắc quyết định

Kiểm thử tích hợp
  → tải trọng đầu vào → ReviewResult

Kiểm thử Verify
  → bộ Cốt lõi + Challenge A

Kiểm thử đầu vào mới
  → dán/tải lên JSON mới qua dịch vụ kiểm tra
```

## 8. Phạm vi phụ trách của nhóm

| Người | Phạm vi chính |
| --- | --- |
| 1 | `domain/`, `ingestion/`, `review_case/` |
| 2 | `checks/`, dữ liệu mẫu, kiểm thử phép kiểm tra |
| 3 | `policy/`, `decision/`, chất lượng câu hỏi |
| 4 | `agent/`, `services/`, `audit/`, `app/`, tích hợp Verify |

## 9. Ngoài phạm vi

- vi dịch vụ;
- tuyến sự kiện;
- cơ sở dữ liệu véc-tơ/RAG khi chính sách nhỏ và có cấu trúc;
- tích hợp ERP đầy đủ;
- kiểm toán phân tán cấp độ sản xuất;
- bộ máy tuân thủ thuế đầy đủ;
- thanh toán tự động.

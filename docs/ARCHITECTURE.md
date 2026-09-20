# InvoiceReferee — Architecture

## 1. Mục tiêu kiến trúc

Kiến trúc Sprint 1 ưu tiên:

- chạy được end-to-end sớm;
- module độc lập để 4 người code song song;
- deterministic business checks;
- decision boundary rõ;
- audit được;
- dễ test bằng JSON fixtures;
- ít dependency và ít abstraction không cần thiết.

## 2. High-level architecture

```text
                   ┌──────────────────────┐
                   │    Raw Evidence      │
                   │ JSON/XML/PDF/Image   │
                   └──────────┬───────────┘
                              ↓
                  ┌────────────────────┐
                  │ Extraction Adapter │
                  │ parse / OCR / map  │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │    Normalize       │
                  │ canonical fields   │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Transaction Builder│
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │   Check Engine     │
                  │ deterministic rules│
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ Policy Constraints │
                  │ scope + authority  │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │    LLM Agent       │
                  │ structured output  │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │  Decision Guard    │
                  │ deterministic gate │
                  └────────┬───────────┘
                            ↓
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
    AUTO_PROCESS      REQUEST_INFO        ESCALATE
          └─────────────────┼─────────────────┘
                            ↓
                  ┌────────────────────┐
                  │ Audit + Human Ctrl │
                  └────────┬───────────┘
                            ↓
                  ┌────────────────────┐
                  │ UI / Verify Harness│
                  └────────────────────┘
```

## 3. Suggested repository structure

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
│       │   └── normalization.py
│       ├── transaction/
│       │   └── builder.py
│       ├── checks/
│       │   ├── engine.py
│       │   ├── vendor.py
│       │   ├── item.py
│       │   ├── quantity.py
│       │   ├── price.py
│       │   ├── amount.py
│       │   ├── duplicate.py
│       │   ├── payment.py
│       │   └── po_limit.py
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
│   ├── test_builder.py
│   ├── test_checks.py
│   ├── test_decision.py
│   ├── test_audit.py
│   └── test_verify.py
├── docs/
│   ├── BUILD_LOG.md
│   └── Challenge_Brief_OrganizationAI_VN.docx.md
└── README.md
```

## 4. Module responsibilities

### Domain

Chứa schema contract từ `DATA_MODEL.md`. Không chứa business orchestration.

### Ingestion

Ingestion có hai trách nhiệm tách biệt: **extraction** và **normalization**.

```text
Raw source
  ↓
Extraction Adapter
  ↓
Extracted fields + source metadata + parse warnings
  ↓
Normalization
  ↓
PurchaseOrder / GoodsReceipt / SupplierInvoice / PaymentRecord / ApprovalRecord
```

Adapter được chọn theo loại nguồn:

- structured JSON/API → đọc trực tiếp key/value và map sang canonical schema;
- e-invoice XML → XML parser theo field/tag của tài liệu;
- text-based PDF → PDF text extraction rồi map field;
- scanned PDF/image → OCR hoặc vision extraction, sau đó map field.

Mọi adapter phải trả về cùng **canonical field contract** trước khi `Transaction Builder` chạy. Adapter chỉ trích xuất dữ liệu; nó không được quyết định vendor có khớp, amount có hợp lệ, invoice có duplicate hay action cuối cùng là gì.

Contract trung gian này là `ExtractedDocument` trong `DATA_MODEL.md`. Vì vậy khi bổ sung XML/PDF/OCR về sau, chỉ adapter thay đổi; normalization, builder và business pipeline được tái sử dụng.

Nếu một field không đọc được hoặc extraction không chắc chắn, adapter phải giữ `null`/warning và source reference thay vì tự đoán. Critical parse warning phải còn nhìn thấy ở downstream để transaction không bị `AUTO_PROCESS` chỉ vì OCR/parse đã điền một giá trị thiếu căn cứ.

Sprint 1 implementation bắt buộc hỗ trợ structured JSON end-to-end. XML/PDF/OCR là adapter mở rộng sau khi core ổn; chúng không được làm thay đổi schema downstream hay business checks.

### Transaction Builder

Ghép PO, Goods Receipt, Invoice và Payment History vào một `Transaction`.

### Check Engine

Chạy 8 deterministic checks và trả `List[CheckResult]`. Không quyết định `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`.

### Policy Engine

Áp dụng Policy v0 và tạo `PolicyContext`: `scope_status` (`IN_SCOPE`, `OUTSIDE_POLICY`, `UNKNOWN`), authority constraints và các rule liên quan. Policy Engine không giao arithmetic hoặc factual checks cho LLM.

### LLM Agent

Là component chính thức của Sprint 1. Nó nhận `Transaction + CheckResult[] + PolicyContext` đã được chuẩn hóa và trả structured `AgentAssessment` gồm:

- proposed uncertainty type;
- proposed action;
- primary unresolved check cần xử lý trước;
- explanation;
- specific question nếu cần;
- target nếu xác định được;
- policy rule IDs được viện dẫn;
- check/evidence references làm căn cứ.

Giá trị chính của LLM ở Sprint 1 là **triage và communication**: khi nhiều check cùng fail/unknown, nó chọn một vấn đề chính mà con người có thể trả lời ngay, rồi tạo explanation/question dựa trên đúng evidence đã có. LLM không được tự sửa facts, tự tính lại deterministic checks hoặc tạo policy mới.

### Decision Guard

Kiểm tra `AgentAssessment` bằng deterministic constraints trước khi tạo `Decision` cuối cùng. Nếu LLM đề xuất action trái với facts/policy, Guard phải reject/override proposal và ghi mismatch vào audit. Mapping cứng vẫn là:

```text
FACTUAL_UNKNOWN   → REQUEST_INFO
OUTSIDE_POLICY    → ESCALATE
BEYOND_AUTHORITY  → ESCALATE
all required facts/checks clear + in authority → AUTO_PROCESS
```

`scope_status = UNKNOWN` được xử lý như factual uncertainty về transaction type và phải `REQUEST_INFO`; `scope_status = OUTSIDE_POLICY` mới được `ESCALATE` theo P13.

### Fallback Question Generator

Template deterministic chỉ là fallback khi LLM provider lỗi/timeout hoặc output không hợp lệ. Fallback không thay đổi final action; nó giữ hệ thống an toàn và chạy được nhưng có thể cho câu hỏi kém linh hoạt hơn normal LLM path. Audit phải ghi rõ `llm_fallback_used = true`.

### Audit Store

Append audit events và human overrides. Sprint 1 có thể lưu in-memory/session hoặc JSON file cho demo; interface phải cho phép thay backend sau này.

### Reviewer Service

Orchestrator duy nhất gọi builder → checks → policy context → LLM agent → decision guard → audit. UI và Verify gọi service này thay vì tự gọi từng module.

### Verify Harness

Chạy fixtures qua đúng production reviewer service, không dùng logic riêng để “giả pass”.

Harness hỗ trợ `core`, `escalation` và `all`; `all` là judge path một thao tác, còn hai suite riêng phục vụ debug/đối chiếu.

### Demo UI input

Sample selector chỉ để judge thử nhanh. UI phải có thêm paste/upload JSON cho unseen input và gửi dữ liệu đó qua cùng `review()` service.

## 5. Core interfaces

```python
build_transaction(evidence) -> Transaction
run_checks(transaction) -> list[CheckResult]
build_policy_context(transaction, checks) -> PolicyContext
assess(transaction, checks, policy_context) -> AgentAssessment
guard(assessment, transaction, checks, policy_context) -> Decision
review(evidence) -> ReviewResult
run_verify(case_ids) -> list[VerifyResult]
```

`ReviewResult` nên chứa:

```text
transaction
checks
policy_context
agent_assessment
decision
audit_events
```

## 6. Deterministic vs Agent responsibilities

Deterministic logic:

- numeric comparisons;
- identity matching;
- duplicate lookup bằng stable invoice identity;
- payment status;
- cumulative quantity theo item;
- cumulative PO amount;
- authority threshold.

LLM Agent bắt buộc trong normal execution path:

- reason trên structured facts/check results;
- đề xuất uncertainty/action theo policy context;
- chọn primary unresolved check trong số các check hợp lệ đã được hệ thống tạo ra;
- giải thích kết quả cho người dùng;
- tạo câu hỏi cụ thể;
- điều phối follow-up;
- hỗ trợ hiểu narrative input sau khi facts đã structured.

Decision Guard deterministic chịu trách nhiệm chấp nhận hoặc sửa proposal theo policy. LLM không được thay đổi facts, rule result, arithmetic hoặc authority threshold.

## 7. Data storage for Sprint 1

MVP không cần database phức tạp.

Khuyến nghị:

- fixtures/input: JSON files;
- policy: Python constants hoặc JSON config;
- audit demo: session state + exportable JSON;
- transaction history: JSON dataset/in-memory repository.

Chỉ thêm database khi có nhu cầu thật từ integration hoặc deployment.

## 8. Error handling

Không biến lỗi kỹ thuật thành decision nghiệp vụ.

Ví dụ:

```text
Malformed JSON
→ INPUT_ERROR

Missing Goods Receipt
→ valid input, REQUEST_INFO
```

Technical errors phải hiển thị rõ và ghi log; business uncertainty phải đi qua decision engine.

## 9. Team ownership

| Người | Ownership chính |
| --- | --- |
| 1 | `domain/`, `ingestion/`, `transaction/` |
| 2 | `checks/` + check tests + fixtures + Verify harness |
| 3 | `policy/`, `decision/` + decision tests + review expected outcomes/question quality |
| 4 | `services/`, `audit/`, `app/`, deployment + final integration |

Các thành viên chia sẻ `DATA_MODEL.md` như interface contract.

## 10. Integration rule

Đến cuối ngày đầu tiên phải có ít nhất một case chạy end-to-end:

```text
fixture JSON
→ Transaction
→ 8 checks
→ Decision
→ Verify/UI output
```

Không đợi từng module “hoàn hảo” mới tích hợp.

## 11. Testing layers

```text
Unit tests
  → từng parser/check/decision rule

Integration tests
  → evidence → ReviewResult

Verify tests
  → 4 core + 5 Challenge A cases

Unseen tests
  → paste/upload JSON mới qua cùng reviewer service, biến đổi amount/vendor/quantity/transaction type không có trong fixture gốc
```

## 12. Non-goals kiến trúc Sprint 1

- microservices;
- event bus;
- vector database;
- RAG nếu policy nhỏ và structured;
- complex workflow engine;
- multi-agent orchestration không cần thiết;
- full ERP integration;
- production-grade distributed audit storage.

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
                   ┌──────────────────┐
                   │      Input       │
                   │ JSON/XML/PDF/... │
                   └────────┬─────────┘
                            ↓
                  ┌────────────────────┐
                  │ Ingestion/Normalize│
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
                  │ Decision Engine    │
                  │ policy + authority │
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
│       │   ├── json_loader.py
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
│       ├── decision/
│       │   ├── engine.py
│       │   └── questions.py
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
├── README.md
├── RUNBOOK.md
└── BUILD_LOG.md
```

## 4. Module responsibilities

### Domain

Chứa schema contract từ `DATA_MODEL.md`. Không chứa business orchestration.

### Ingestion

Đọc input và normalize thành domain objects. Sprint 1 ưu tiên JSON; XML/PDF/OCR chỉ thêm khi core đã ổn.

### Transaction Builder

Ghép PO, Goods Receipt, Invoice và Payment History vào một `Transaction`.

### Check Engine

Chạy 8 deterministic checks và trả `List[CheckResult]`. Không quyết định `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`.

### Policy Engine

Áp dụng Policy v0, scope và authority threshold.

### Decision Engine

Phân loại uncertainty và trả một `Decision` duy nhất.

### Question Generator

Sinh câu hỏi cụ thể từ structured facts. Sprint 1 có thể dùng deterministic templates để Verify ổn định; LLM adapter có thể bổ sung sau mà không thay decision logic.

### Audit Store

Append audit events và human overrides. Sprint 1 có thể lưu in-memory/session hoặc JSON file cho demo; interface phải cho phép thay backend sau này.

### Reviewer Service

Orchestrator duy nhất gọi builder → checks → decision → audit. UI và Verify gọi service này thay vì tự gọi từng module.

### Verify Harness

Chạy fixtures qua đúng production reviewer service, không dùng logic riêng để “giả pass”.

### Demo UI input

Sample selector chỉ để judge thử nhanh. UI phải có thêm paste/upload JSON cho unseen input và gửi dữ liệu đó qua cùng `review()` service.

## 5. Core interfaces

```python
build_transaction(evidence) -> Transaction
run_checks(transaction) -> list[CheckResult]
decide(transaction, checks, policy) -> Decision
review(evidence) -> ReviewResult
run_verify(case_ids) -> list[VerifyResult]
```

`ReviewResult` nên chứa:

```text
transaction
checks
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

Agent/LLM layer nếu dùng:

- giải thích kết quả;
- tạo câu hỏi tự nhiên;
- điều phối follow-up;
- hỗ trợ classify narrative input sau khi facts đã structured.

LLM không được thay đổi facts hoặc rule result.

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


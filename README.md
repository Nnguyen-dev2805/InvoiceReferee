# InvoiceReferee

**AI Purchase Invoice Review & Escalation Agent**

InvoiceReferee hỗ trợ kế toán bên mua kiểm tra các giao dịch mua hàng có PO và Goods Receipt. Hệ thống gom bằng chứng của cùng một transaction, chạy các kiểm tra deterministic, áp dụng policy và trả một trong ba quyết định:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

`AUTO_PROCESS` chỉ có nghĩa là hồ sơ routine đã đủ căn cứ để đi tiếp sang bước payment review; hệ thống không tự chuyển tiền.

## Sprint 1 scope

```text
Purchase Order
→ Goods Receipt
→ Supplier Invoice
→ Review
→ Payment Review
```

Sprint 1 chỉ bao phủ **PO-based goods purchases có Goods Receipt**.

## Business Workflow

Luồng nghiệp vụ mà InvoiceReferee hỗ trợ:

```text
Purchasing tạo PO đã được phê duyệt
        ↓
Warehouse / Receiver xác nhận hàng đã nhận
        ↓
Supplier gửi invoice
        ↓
Accounts Payable nhận hồ sơ
        ↓
InvoiceReferee review PO + Receipt + Invoice + Payment History
        ↓
┌──────────────────┬──────────────────┬──────────────────┐
│   AUTO_PROCESS   │   REQUEST_INFO   │     ESCALATE     │
│ hồ sơ routine    │ còn thiếu /      │ ngoài policy /   │
│ đủ căn cứ        │ mâu thuẫn fact   │ vượt thẩm quyền  │
└────────┬─────────┴────────┬─────────┴────────┬─────────┘
         ↓                  ↓                  ↓
 Payment Review       Bổ sung evidence     Human decision
```

`AUTO_PROCESS` chỉ đưa hồ sơ sang bước review thanh toán tiếp theo, không tự chuyển tiền.

## System Flow

Luồng xử lý bên trong hệ thống:

```text
Raw Input (JSON baseline; XML/PDF/Image adapters optional)
  ↓
Extraction / Canonical Mapping
  ↓
Normalization
  ↓
Identify Transaction Type
  ↓
Build Transaction
  ↓
Validate Required Evidence
  ↓
Run Deterministic Checks
  ↓
Apply Policy + Authority Constraints
  ↓
LLM Agent Assessment
  ├── reason over structured facts
  ├── propose uncertainty/action
  ├── explain result
  └── generate specific question
  ↓
Deterministic Decision Guard
  ↓
Final Decision
  ├── AUTO_PROCESS
  ├── REQUEST_INFO
  └── ESCALATE
  ↓
Audit Log
  ↓
Human Stop / Override
  ↓
UI / Verify
```

LLM là một component chính thức trong execution path: nó nhận structured facts đã được kiểm chứng để reasoning, chọn vấn đề chưa được giải quyết cần hỏi trước, giải thích và tạo một câu hỏi hành động cụ thể. Các phép so sánh số lượng, số tiền, duplicate, payment status và authority threshold vẫn là deterministic. `Decision Guard` kiểm tra output của LLM với policy trước khi phát hành final decision, nên LLM không thể tự sửa facts hoặc vượt policy.

## Data Flow

Dữ liệu chính đi qua hệ thống như sau:

```text
PurchaseOrder
      +
GoodsReceipt[]
      +
SupplierInvoice
      +
PaymentRecord[]
      +
ApprovalRecord[]
      +
Transaction History
      ↓
Transaction
      ↓
CheckResult[] + PolicyContext
      ↓
AgentAssessment (LLM)
      ↓
Decision Guard
      ↓
Decision
      ↓
AuditEvent[]
      +
HumanStop / HumanOverride
```

`Transaction` là object trung tâm. Invoice không được review tách biệt khi đã có PO, Goods Receipt, payment history hoặc evidence liên quan trong lịch sử giao dịch.

## Core checks

1. Vendor match
2. Item match
3. Quantity match, gồm cumulative quantity theo item
4. Unit price match
5. Amount check
6. Duplicate invoice
7. Payment status
8. Cumulative PO limit

## Documentation

- `docs/CHALLENGE.md` — đề thi yêu cầu gì và judge kiểm tra thế nào
- `docs/PRODUCT_SPEC.md` — sản phẩm Sprint 1 phải làm gì
- `docs/POLICY.md` — decision boundary và policy v0
- `docs/DATA_MODEL.md` — schema contract giữa các module
- `docs/DECISION_FLOW.md` — flow từ input đến decision
- `docs/TEST_CASES.md` — 17 test cases + Verify cases
- `docs/ARCHITECTURE.md` — module, interface và ownership
- `docs/EVALUATION_PLAN.md` — kế hoạch unseen tests, user feedback và đo lường Sprint 2
- `docs/superpowers/specs/2026-09-20-invoice-referee-design.md` — design spec tổng hợp
- `docs/superpowers/plans/2026-09-20-invoice-referee-implementation.md` — implementation plan
- `docs/BUILD_LOG.md` — nhật ký phát triển
- `docs/Challenge_Brief_OrganizationAI_VN.docx.md` — challenge brief gốc


## Run & Verify

> Các lệnh dưới đây đã được chạy end-to-end trên môi trường sạch (Python 3.12): `pytest` xanh (492 passed, 0 failed) và business Verify (core/escalation/all) exit 0.

### Requirements

- Python 3.12+
- Git

### Setup

```bash
git clone <public-repository-url>
cd InvoiceReferee
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

### OCR development setup (tuỳ chọn)

Chỉ review JSON có cấu trúc (mặc định, không cần OCR):

```bash
pip install -e '.[dev]'
```

Trích xuất Supplier Invoice từ PDF/ảnh (PaddleOCR/PP-StructureV3 local):

```bash
pip install -e '.[dev,ocr]'
RUN_OCR_RUNTIME=1 pytest tests/test_ocr_runtime.py -v
```

macOS chạy PaddlePaddle trên CPU. Bản deploy công khai phải cài extra `ocr`
và warm model weights trước khi giám khảo thao tác. Core JSON review vẫn chạy
và test được đầy đủ khi **không** cài extra `ocr`.

### LLM provider (tuỳ chọn, OpenAI-compatible)

LLM Agent dùng chuẩn OpenAI Chat Completions, đổi provider chỉ bằng `base_url` + `model`.
Cấu hình qua `.env` ở thư mục gốc (copy từ `.env.example`):

```bash
cp .env.example .env
# rồi điền LLM_API_KEY
```

```dotenv
LLM_BASE_URL=https://api.xkiro.com/v1   # hoặc DeepSeek/OpenAI/gateway nội bộ
LLM_API_KEY=sk-...
LLM_MODEL=claude-opus-4.8
LLM_TIMEOUT=30
```

Không có `LLM_API_KEY` thì hệ thống chạy **deterministic fallback** — Decision Guard
vẫn quyết định action, nên kết quả luôn policy-correct dù có hay không có LLM.
`.env` đã được `.gitignore`; không commit key.

### Tests

```bash
pytest -v
```

### Full Verify — judge path

Một lệnh chạy cả Core Verify và Challenge A Verify qua đúng production `review()` service:

```bash
python -m verify.harness --suite all
```

UI phải có nút tương đương **Run Full Verify** để giám khảo không cần mở terminal. Kết quả hiển thị suite, case, expected, actual, pass/fail, uncertainty, question/target khi có, LLM/fallback status và timestamp.

### Core Verify

```bash
python -m verify.harness --suite core
```

Expected cases:

```text
TC01 → AUTO_PROCESS
TC07 → REQUEST_INFO
TC13 → ESCALATE
TC14 → ESCALATE
```

### Challenge A Verify

```bash
python -m verify.harness --suite escalation
```

Expected cases:

```text
EV01 → AUTO_PROCESS
EV02 → AUTO_PROCESS
EV03 → AUTO_PROCESS
EV04 → REQUEST_INFO
EV05 → ESCALATE
```

### Run UI

```bash
streamlit run app/streamlit_app.py
```

Homepage phải hướng dẫn judge thao tác đầu tiên, không yêu cầu login, và cho phép paste/upload JSON mới để test unseen input.

### Submission smoke check

Trước demo/deploy cần kiểm tra tối thiểu: routine case, một `REQUEST_INFO`, một `ESCALATE`, audit history, Stop/Override, hai Verify suites và ít nhất hai unseen JSON inputs qua đúng production `review()` path.

### Supplier-Invoice OCR (Sprint 1, tuỳ chọn)

Ngoài JSON có cấu trúc, hệ thống nhận **một Supplier Invoice** dạng PDF/PNG/JPEG,
trích xuất field bằng PaddleOCR/PP-StructureV3 local, cho người xác nhận từng
critical field, rồi đưa evidence đã review qua đúng `review()` production. PO,
Goods Receipt, Payment History vẫn là JSON có cấu trúc.

Nguyên tắc: OCR **chỉ trích fact ứng viên**, không tự ra quyết định. Field thiếu
giữ `None` (không hoá `""`/`0`), mọi field máy trích có provenance (page + bbox +
block IDs), `vendor_id`/`item_id` chỉ resolve khi khớp chính xác tax-code/SKU,
và người phải xác nhận/sửa/đánh-dấu-unknown mọi critical field trước khi review.

```bash
pip install -e '.[dev,ocr]'
# Chẩn đoán opt-in: chạy bộ fixture ghi sẵn qua LLM thật. Không lưu response/ảnh.
python -m verify.semantic_harness --live
```

Trích xuất là **LLM-first và chỉ LLM**: không còn label/layout/fuzzy mapper để rơi
về, nên `LLM_API_KEY` là **bắt buộc** cho đường tài liệu. Thiếu key thì extraction
fail-closed (không field nào) và hồ sơ vào human review — không đoán.

extractor trên ảnh thật.

Trong UI, chọn nguồn **Invoice Document**, upload file, dán JSON PO/GR/payment,
bấm *Process invoice*, xác nhận các field, rồi *Confirm extraction & Review*.

**Chọn engine OCR.** Mặc định dùng PaddleOCR local (offline, riêng tư, không phí).
Để dùng **Mistral Document AI OCR** (hosted, không cần tải model về máy) — hữu ích
để thử kiến trúc end-to-end nhanh — đặt trong `.env`:

```dotenv
OCR_ENGINE=mistral
MISTRAL_API_KEY=...          # https://console.mistral.ai/api-keys
MISTRAL_OCR_MODEL=ocr-4-1    # mặc định; OCR 4.1 cho bbox + confidence theo khối
```

Engine chỉ là adapter sau `OCREngine`; đổi engine không thay đổi validate field,
human confirm, hay business review. Mặc định dùng **OCR 4.1**: adapter bật
`include_blocks` + `confidence_scores_granularity=block`, nên field mang bounding
box và confidence thật (threshold tin cậy hoạt động đúng). Nếu response không có
`blocks` (model cũ), adapter tự lùi về parse Markdown và field vào
`NEEDS_CONFIRMATION` (fail-closed).

## Current state

Sprint 1 đã chạy end-to-end (JSON review + OCR document path). Trạng thái đã kiểm chứng (chạy mới ở revision hiện tại):

- `pytest` — **492 passed, 2 skipped, 0 failed** (2 skip là smoke OCR runtime, bật bằng `RUN_OCR_RUNTIME=1`).
- `python -m verify.harness --suite core` → **4/4** (TC01 AUTO_PROCESS, TC07 REQUEST_INFO, TC13/TC14 ESCALATE).
- `python -m verify.harness --suite escalation` → **5/5** (3 routine AUTO_PROCESS, TC07 REQUEST_INFO, TC13 ESCALATE).
- `python -m verify.harness --suite all` → **9/9** (judge path một thao tác).
- `python -m verify.semantic_harness --live` (opt-in, không lưu response/ảnh) → chẩn đoán LLM trên fixture ghi sẵn: `a.jpg` ra `SUPPLIER_INVOICE` 5 field + 2 line item + total 9.000.000; `b.jpg` ra `TEMPORARY_BILL`, `receipt_number=2627003876`, `total_amount=4035570`, 9 line item.
- Streamlit UI: sample + paste/upload JSON + **Invoice Document** qua đúng `review()`, hiển thị checks/decision/audit, Stop/Override, nút Run Full Verify (kiểm bằng Streamlit `AppTest`). Sau Override, UI hiển thị **effective decision** bên cạnh quyết định gốc được giữ trong audit.

LLM Agent mặc định chạy **deterministic fallback** khi chưa cấu hình provider; Decision Guard luôn quyết định action cuối, nên decision là policy-correct dù có hay không có LLM. Trích xuất tài liệu thì **ngược lại**: nó là LLM-first và chỉ LLM, nên `LLM_API_KEY` bắt buộc cho đường tài liệu — thiếu key thì fail-closed (không field nào) và vào human review.

### Kiến trúc mã nguồn

```text
src/invoice_referee/
├── domain/models.py         # schema contracts (integer VND, tri-state scope, OCR contracts)
├── ingestion/               # json_adapter + normalization (fail-closed)
│   ├── file_validation.py   # magic-byte upload validation
│   ├── document_router.py + pdf_renderer.py + image_preprocessing.py
│   ├── ocr.py               # OCREngine + PaddleOCR adapter
│   ├── semantic_extraction.py + grounding.py
│   ├── field_normalization.py + identity_resolution.py
│   ├── extraction_validation.py + pipeline.py
├── transaction/builder.py   # build_transaction() + evidence_issues
├── checks/                  # 8 deterministic checks + engine (UNKNOWN on absent facts)
├── policy/                  # config (Policy v0) + engine (scope + resolve_action)
├── agent/                   # llm_client + prompts + service (fallback-safe)
├── decision/                # guard + fallback_questions
├── audit/store.py           # append-only audit + extraction/OCR events + Stop/Override
└── services/                # reviewer.review() + extractor.extract_invoice()
verify/                      # harness + manifest + semantic_harness (expected labels tách khỏi review())
app/                         # streamlit_app + presentation + extraction_presentation
tests/fixtures/TC01..TC17    # 17 documented business cases
tests/fixtures_structure/    # recorded block sets (a.jpg invoice, b.jpg receipt) + live recorder
```

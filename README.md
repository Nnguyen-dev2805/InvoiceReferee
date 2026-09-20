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
Input
  ↓
Ingestion / Normalize
  ↓
Identify Transaction Type
  ↓
Build Transaction
  ↓
Validate Required Evidence
  ↓
Run Deterministic Checks
  ↓
Apply Policy + Authority
  ↓
Classify Uncertainty
  ↓
Decision
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

Các phép so sánh số lượng, số tiền, duplicate, payment status và authority threshold được xử lý bằng deterministic logic. Agent/LLM chỉ hỗ trợ điều phối, giải thích và tạo câu hỏi từ facts đã được chuẩn hóa.

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
CheckResult[]
      ↓
Uncertainty
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

> Các lệnh dưới đây là contract dự kiến ở giai đoạn pre-code và phải được kiểm tra lại sau khi implementation hoàn tất.

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

### Tests

```bash
pytest -v
```

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

## Current state

Project đang ở giai đoạn **pre-code specification**. Các tài liệu cốt lõi đã được chốt trước khi bắt đầu implementation.


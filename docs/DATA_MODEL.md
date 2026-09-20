# InvoiceReferee — Data Model

## 1. Mục đích

File này khóa schema dữ liệu chung để các module có thể phát triển độc lập nhưng vẫn ghép được với nhau.

Đối tượng trung tâm của hệ thống là **Transaction**, không phải một file invoice riêng lẻ.

```text
Purchase Order
      +
Goods Receipt
      +
Supplier Invoice
      +
Payment History
      +
Policy
      ↓
Transaction
      ↓
Checks
      ↓
Decision
      ↓
Audit Log
```

---

## 2. Nguyên tắc chung

- Sprint 1 ưu tiên schema đơn giản và rõ ràng.
- Tiền dùng đơn vị **VND integer**, không dùng float.
- Quantity dùng số nguyên trong MVP.
- Date dùng định dạng `YYYY-MM-DD`.
- Timestamp dùng ISO 8601.
- ID phải ổn định và có thể dùng để liên kết các evidence.
- Field chưa biết dùng `null`, không tự điền giá trị đoán.
- Dữ liệu parse chưa chắc chắn phải có flag để downstream biết không được tin tuyệt đối.

---

## 3. PurchaseOrder

```json
{
  "po_id": "PO-001",
  "vendor_id": "VENDOR-ABC",
  "vendor_name": "ABC Company",
  "currency": "VND",
  "order_date": "2026-09-10",
  "items": [
    {
      "item_id": "ITEM-001",
      "description": "Dell Monitor",
      "ordered_quantity": 10,
      "unit_price": 3000000,
      "line_total": 30000000
    }
  ],
  "approved_total": 30000000,
  "status": "APPROVED"
}
```

### Required fields

- `po_id`
- `vendor_id`
- `items`
- `approved_total`
- `status`

---

## 4. GoodsReceipt

```json
{
  "receipt_id": "GR-001",
  "po_id": "PO-001",
  "received_date": "2026-09-12",
  "items": [
    {
      "item_id": "ITEM-001",
      "description": "Dell Monitor",
      "received_quantity": 10
    }
  ],
  "status": "RECEIVED"
}
```

### Required fields

- `receipt_id`
- `po_id`
- `items`
- `received_date`
- `status`

---

## 5. SupplierInvoice

```json
{
  "invoice_id": "INV-001",
  "invoice_number": "0000123",
  "invoice_series": "2C23TTU",
  "invoice_type": "ORIGINAL",
  "related_invoice_number": null,
  "vendor_id": "VENDOR-ABC",
  "vendor_tax_code": "0101234567",
  "vendor_name": "ABC Company",
  "po_id": "PO-001",
  "invoice_date": "2026-09-13",
  "currency": "VND",
  "items": [
    {
      "item_id": "ITEM-001",
      "description": "Dell Monitor",
      "invoiced_quantity": 10,
      "unit_price": 3000000,
      "line_total": 30000000
    }
  ],
  "total_amount": 30000000,
  "source_type": "JSON",
  "confidence": 1.0,
  "flagged": false
}
```

### Required fields

- `invoice_id`
- `invoice_number`
- `invoice_series`
- `invoice_type`
- `vendor_id`
- `vendor_tax_code`
- `po_id`
- `invoice_date`
- `items`
- `total_amount`
- `flagged`

### Notes

`invoice_type` có thể là:

```text
ORIGINAL
ADJUSTMENT
REPLACEMENT
```

Nếu `invoice_type` là `ADJUSTMENT` hoặc `REPLACEMENT`, `related_invoice_number` phải trỏ về invoice gốc nếu dữ liệu nguồn cung cấp được quan hệ đó. Sprint 1 dùng metadata này để liên kết lịch sử và tránh false duplicate; không tự suy diễn toàn bộ tác động kế toán/thuế của hóa đơn điều chỉnh.

Duplicate identity ưu tiên:

```text
vendor_tax_code + invoice_series + invoice_number
```

`source_type` có thể là:

```text
JSON
XML
PDF_TEXT
OCR
```

Trong Sprint 1, JSON có thể là input chính. XML/PDF/OCR chỉ là input adapter bổ sung.

`confidence` chỉ phản ánh độ tin cậy của bước extraction nếu có. Nó không thay thế business rule.

---

## 6. ApprovalRecord

Approval/amendment là evidence riêng, không được suy ra từ việc invoice lệch PO.

```json
{
  "approval_id": "APR-001",
  "po_id": "PO-001",
  "approval_type": "UNIT_PRICE_CHANGE",
  "item_id": "ITEM-001",
  "approved_value": 3500000,
  "approved_amount_delta": 5000000,
  "approved_by": "Finance Manager",
  "approved_at": "2026-09-13T09:00:00+07:00",
  "status": "APPROVED"
}
```

`approval_type` Sprint 1 có thể gồm:

```text
UNIT_PRICE_CHANGE
QUANTITY_CHANGE
AMOUNT_CHANGE
ITEM_CHANGE
VENDOR_CHANGE
```

Chỉ record có `status = APPROVED` mới được dùng để giải thích discrepancy. Không có record thì hệ thống không được tự giả định approval tồn tại.

---

## 7. PaymentRecord

```json
{
  "payment_id": "PAY-001",
  "invoice_id": "INV-001",
  "status": "UNPAID",
  "paid_amount": 0,
  "payment_date": null
}
```

### Payment status

```text
UNPAID
PARTIALLY_PAID
PAID
UNKNOWN
```

`UNKNOWN` phải dẫn tới `REQUEST_INFO` nếu payment status là fact cần thiết để quyết định.

`PARTIALLY_PAID` cũng không được coi là routine `UNPAID`. Hệ thống phải dừng luồng thường quy, hiển thị `paid_amount` và yêu cầu xác nhận phần còn lại trước khi đưa transaction đi tiếp.

---

## 8. Transaction

Đây là object trung tâm mà các module phía sau sử dụng.

```json
{
  "transaction_id": "TX-001",
  "transaction_type": "PO_GOODS_PURCHASE",
  "po": {},
  "goods_receipts": [],
  "invoice": {},
  "payment_history": [],
  "approvals": [],
  "checks": [],
  "decision": null,
  "audit_log": [],
  "workflow_status": "ACTIVE",
  "human_stops": [],
  "human_overrides": [],
  "created_at": "2026-09-20T10:00:00+07:00",
  "updated_at": "2026-09-20T10:00:00+07:00"
}
```

### workflow_status

Trạng thái vận hành của transaction:

```text
ACTIVE
STOPPED
```

`STOPPED` là human-control state, không phải một giá trị của `Decision.action`.

### transaction_type

Sprint 1 chỉ support:

```text
PO_GOODS_PURCHASE
```

Các loại khác phải được nhận diện là outside policy thay vì cố ép vào schema hiện tại.

---

## 9. CheckResult

Mỗi rule/check trả về cùng một schema để Decision Engine không phụ thuộc implementation bên trong từng check.

```json
{
  "check_id": "CHECK_QUANTITY",
  "policy_rule_id": "P05",
  "status": "FAIL",
  "expected": 10,
  "actual": 12,
  "reason": "Invoice quantity exceeds confirmed received quantity",
  "evidence_refs": [
    "PO-001",
    "GR-001",
    "INV-001"
  ]
}
```

### Check status

```text
PASS
FAIL
UNKNOWN
NOT_APPLICABLE
```

Ý nghĩa:

- `PASS`: đủ evidence và rule đạt.
- `FAIL`: đủ evidence và rule không đạt.
- `UNKNOWN`: thiếu hoặc mâu thuẫn evidence để xác định.
- `NOT_APPLICABLE`: check không áp dụng cho transaction hiện tại.

`FAIL` không tự động đồng nghĩa với `ESCALATE`. Decision Engine phải xem failure đó là thiếu fact, outside policy hay beyond authority.

---

## 10. Uncertainty

Khi hệ thống không thể tự quyết, cần biểu diễn rõ loại uncertainty.

```json
{
  "type": "FACTUAL_UNKNOWN",
  "field": "invoice.total_amount",
  "reason": "PO amount and invoice amount differ without adjustment evidence"
}
```

### Uncertainty type

```text
FACTUAL_UNKNOWN
OUTSIDE_POLICY
BEYOND_AUTHORITY
```

Mapping:

```text
FACTUAL_UNKNOWN
    → REQUEST_INFO

OUTSIDE_POLICY
    → ESCALATE

BEYOND_AUTHORITY
    → ESCALATE
```

---

## 11. Decision

```json
{
  "action": "REQUEST_INFO",
  "reason": "Invoice amount exceeds PO amount and no approved adjustment is available",
  "uncertainty": {
    "type": "FACTUAL_UNKNOWN",
    "field": "invoice.total_amount"
  },
  "question": "PO được phê duyệt 30M nhưng invoice là 35M. Có phê duyệt điều chỉnh thêm 5M không?",
  "target": "Purchasing",
  "policy_rule_ids": ["P07"],
  "decided_at": "2026-09-20T10:04:00+07:00"
}
```

### Decision action

Chỉ có 3 giá trị user-facing:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

### Field behavior

#### AUTO_PROCESS

```json
{
  "action": "AUTO_PROCESS",
  "question": null,
  "target": null
}
```

#### REQUEST_INFO

Phải có:

- `reason`
- `uncertainty.type = FACTUAL_UNKNOWN`
- `question`

`target` có thể là role có khả năng cung cấp fact, ví dụ `Purchasing`, `Warehouse`, `Accounting`, hoặc `Supplier`.

#### ESCALATE

Phải có:

- `reason`
- uncertainty là `OUTSIDE_POLICY` hoặc `BEYOND_AUTHORITY`
- `question`
- `target` nếu xác định được từ policy.

---

## 12. AuditEvent

```json
{
  "event_id": "AUD-001",
  "transaction_id": "TX-001",
  "event_type": "CHECK_COMPLETED",
  "actor": "InvoiceReferee",
  "timestamp": "2026-09-20T10:03:00+07:00",
  "rule_id": "P05",
  "input_refs": ["GR-001", "INV-001"],
  "result": "PASS",
  "reason": "Invoiced quantity 10 does not exceed received quantity 10"
}
```

### Suggested event types

```text
TRANSACTION_CREATED
EVIDENCE_ATTACHED
CHECK_COMPLETED
DECISION_MADE
INFO_REQUESTED
ESCALATED
STOPPED
OVERRIDDEN
```

Audit log phải append-only ở mức logic ứng dụng: event cũ không được xóa chỉ vì decision sau đó bị override.

---

## 13. Human Controls

### HumanStop

```json
{
  "stop_id": "STOP-001",
  "actor": "accountant@example.com",
  "timestamp": "2026-09-20T10:10:00+07:00",
  "previous_workflow_status": "ACTIVE",
  "new_workflow_status": "STOPPED",
  "reason": "Supplier bank account changed and requires manual verification"
}
```

Stop chỉ thay đổi `workflow_status`; decision ban đầu của Agent vẫn giữ nguyên trong audit history.

### HumanOverride

```json
{
  "override_id": "OVR-001",
  "actor": "accountant@example.com",
  "timestamp": "2026-09-20T10:12:00+07:00",
  "original_action": "AUTO_PROCESS",
  "overridden_action": "ESCALATE",
  "reason": "Manual finance approval required after external verification"
}
```

`overridden_action` chỉ nhận một trong ba decision user-facing: `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`. Không dùng `STOPPED` làm decision.

---

## 14. Evidence Reference

Các check và audit event không nên copy toàn bộ document vào output. Chúng chỉ cần tham chiếu bằng ID.

Ví dụ:

```json
{
  "evidence_refs": [
    "PO-001",
    "GR-001",
    "INV-001",
    "PAY-001"
  ]
}
```

Điều này giúp trace được quyết định mà không làm object kết quả phình to.

---

## 15. Example — Routine Transaction

```json
{
  "transaction_id": "TX-001",
  "transaction_type": "PO_GOODS_PURCHASE",
  "po": {
    "po_id": "PO-001",
    "vendor_id": "VENDOR-ABC",
    "approved_total": 30000000
  },
  "goods_receipts": [
    {
      "receipt_id": "GR-001",
      "po_id": "PO-001"
    }
  ],
  "invoice": {
    "invoice_id": "INV-001",
    "vendor_id": "VENDOR-ABC",
    "po_id": "PO-001",
    "total_amount": 30000000,
    "flagged": false
  },
  "payment_history": [
    {
      "invoice_id": "INV-001",
      "status": "UNPAID"
    }
  ],
  "checks": [
    {"check_id": "CHECK_VENDOR", "status": "PASS"},
    {"check_id": "CHECK_QUANTITY", "status": "PASS"},
    {"check_id": "CHECK_AMOUNT", "status": "PASS"},
    {"check_id": "CHECK_DUPLICATE", "status": "PASS"},
    {"check_id": "CHECK_PAYMENT", "status": "PASS"}
  ],
  "decision": {
    "action": "AUTO_PROCESS",
    "reason": "Required evidence is consistent and transaction is within authority",
    "question": null,
    "target": null
  }
}
```

---

## 16. Example — Missing Fact

```json
{
  "transaction_id": "TX-002",
  "checks": [
    {
      "check_id": "CHECK_AMOUNT",
      "policy_rule_id": "P07",
      "status": "FAIL",
      "expected": 30000000,
      "actual": 35000000,
      "reason": "Invoice amount exceeds approved PO amount"
    }
  ],
  "decision": {
    "action": "REQUEST_INFO",
    "reason": "No approved adjustment is available",
    "uncertainty": {
      "type": "FACTUAL_UNKNOWN",
      "field": "approved_adjustment"
    },
    "question": "PO được phê duyệt 30M nhưng invoice là 35M. Có phê duyệt điều chỉnh thêm 5M không?",
    "target": "Purchasing"
  }
}
```

---

## 17. Example — Beyond Authority

```json
{
  "transaction_id": "TX-003",
  "invoice": {
    "invoice_id": "INV-003",
    "total_amount": 120000000
  },
  "decision": {
    "action": "ESCALATE",
    "reason": "Transaction exceeds the 50M agent authority threshold",
    "uncertainty": {
      "type": "BEYOND_AUTHORITY",
      "field": "transaction_amount"
    },
    "question": "Giao dịch 120M vượt ngưỡng tự xử lý 50M. Finance Manager có phê duyệt giao dịch này không?",
    "target": "Finance Manager",
    "policy_rule_ids": ["P12"]
  }
}
```

---

## 18. Interface giữa các module

Để 4 người có thể code song song, interface tối thiểu cần khóa như sau:

```text
Input Adapter
    ↓
PurchaseOrder / GoodsReceipt / SupplierInvoice / PaymentRecord / ApprovalRecord
    ↓
Transaction Builder
    ↓
Transaction
    ↓
Check Engine
    ↓
List[CheckResult]
    ↓
Decision Engine
    ↓
Decision
    ↓
Audit / UI / Verify
```

Mỗi module chỉ phụ thuộc schema đầu vào/đầu ra, không phụ thuộc implementation nội bộ của module khác.

---

## 19. Schema cần được xem là contract

Trước khi bắt đầu code, team phải thống nhất và hạn chế thay đổi tùy tiện các object sau:

1. `PurchaseOrder`
2. `GoodsReceipt`
3. `SupplierInvoice`
4. `PaymentRecord`
5. `ApprovalRecord`
6. `Transaction`
7. `CheckResult`
8. `Uncertainty`
9. `Decision`
10. `AuditEvent`
11. `HumanStop`
12. `HumanOverride`

Nếu cần thay schema sau khi code đã được chia cho nhiều người, thay đổi phải được thông báo vì nó có thể phá interface giữa các module.

# InvoiceReferee — Decision Flow

## 1. Mục đích

File này mô tả cách InvoiceReferee đi từ input đến quyết định cuối cùng.

Mục tiêu là để mọi thành viên trong team hiểu giống nhau về thứ tự xử lý:

```text
Input
  ↓
Normalize
  ↓
Build Transaction
  ↓
Validate Evidence
  ↓
Run Checks
  ↓
Classify Uncertainty
  ↓
Apply Policy + Authority
  ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
  ↓
Audit + Human Control
```

---

## 2. Nguyên tắc quyết định

InvoiceReferee tuân theo 4 nguyên tắc:

1. **Không đoán facts.**
2. **Không dùng LLM để thay deterministic checks.**
3. **Không escalate nếu case routine đủ rõ và nằm trong quyền Agent.**
4. **Con người luôn có quyền Stop / Override.**

---

## 3. Step 1 — Nhận input

Input Sprint 1 gồm:

- Purchase Order;
- Goods Receipt;
- Supplier Invoice;
- Payment History;
- Company Policy.

Input có thể đến từ JSON trước. XML/PDF/OCR nếu có chỉ là adapter.

Output của bước này phải là dữ liệu có cấu trúc theo `DATA_MODEL.md`.

---

## 4. Step 2 — Normalize dữ liệu

Mục tiêu là đưa dữ liệu từ nhiều nguồn về schema thống nhất.

Ví dụ:

```text
"30,000,000 VND"
"30000000"
30_000_000
```

đều được normalize thành:

```json
30000000
```

Các field chưa biết phải để `null` hoặc đánh dấu `UNKNOWN`, không tự suy đoán.

Nếu extraction không chắc chắn, phải đặt `flagged = true` hoặc lưu uncertainty tương ứng.

---

## 5. Step 3 — Build Transaction

Các evidence liên quan phải được gom thành một transaction.

```text
PO-001
GR-001
INV-001
PAY-001
   ↓
TX-001
```

Liên kết ưu tiên bằng ID rõ ràng như:

- `po_id`;
- `invoice_id`;
- `vendor_id`;
- document references.

Nếu không thể xác định document nào thuộc cùng transaction, đó là factual uncertainty.

Kết quả:

```text
REQUEST_INFO
```

---

## 6. Step 4 — Xác định scope rồi kiểm tra evidence tối thiểu

Trước hết hệ thống phải xác định `transaction_type`.

```text
transaction_type chưa rõ
→ REQUEST_INFO

transaction_type đã rõ nhưng ngoài PO_GOODS_PURCHASE
→ ESCALATE / OUTSIDE_POLICY

transaction_type = PO_GOODS_PURCHASE
→ mới kiểm tra PO, Goods Receipt, payment và các evidence bắt buộc
```

Điều này ngăn service invoice bị hỏi Goods Receipt chỉ vì đi qua validation của workflow mua hàng hóa.

### PO missing

Nếu chưa tìm thấy PO:

```text
REQUEST_INFO
```

Nếu đã xác nhận transaction thực sự không có PO:

```text
ESCALATE
Reason: OUTSIDE_POLICY
```

### Goods Receipt missing

Trong workflow Sprint 1:

```text
REQUEST_INFO
```

### Suspicious / unreadable field

Ví dụ invoice amount chưa đọc chắc chắn:

```text
REQUEST_INFO
```

Không được chạy tiếp và giả định một giá trị.

---

## 7. Step 5 — Chạy deterministic checks

Khi evidence cần thiết đã có, hệ thống chạy các check chính:

```text
1. Vendor Match
2. Item Match
3. Quantity Match — current + cumulative quantity theo item
4. Unit Price Match
5. Amount Check
6. Duplicate Invoice
7. Payment Status
8. Cumulative PO Limit
```

Mỗi check trả về `CheckResult`:

```json
{
  "check_id": "CHECK_QUANTITY",
  "policy_rule_id": "P05",
  "status": "FAIL",
  "expected": 10,
  "actual": 12,
  "reason": "Invoice quantity exceeds received quantity"
}
```

Check engine **không quyết định** `AUTO_PROCESS`, `REQUEST_INFO` hay `ESCALATE`.

Nó chỉ xác định facts và rule result.

---

## 8. Step 6 — Phân loại uncertainty

Decision Engine nhận `CheckResult[]` và xác định loại uncertainty.

### FACTUAL_UNKNOWN

Sử dụng khi chưa đủ facts để kết luận.

Ví dụ:

```text
PO = 30M
Invoice = 35M
Không biết có approved amendment hay không
```

Kết quả:

```text
REQUEST_INFO
```

### OUTSIDE_POLICY

Facts đã rõ nhưng transaction không thuộc workflow policy hiện tại.

Ví dụ:

```text
Service invoice
No Goods Receipt workflow
```

Kết quả:

```text
ESCALATE
```

### BEYOND_AUTHORITY

Facts đã rõ, transaction nằm trong policy nhưng vượt quyền Agent.

Ví dụ:

```text
Amount = 120M
Agent threshold = 50M
```

Kết quả:

```text
ESCALATE
Target: Finance Manager
```

---

## 9. Step 7 — Decision Priority

Thứ tự bắt buộc:

```text
Transaction type đã xác định?
        │
        ├─ NO → REQUEST_INFO
        │
        └─ YES
             ↓
Transaction type có ngoài policy?
        │
        ├─ YES → ESCALATE
        │
        └─ NO
             ↓
Có fact bắt buộc chưa biết / evidence mâu thuẫn?
        │
        ├─ YES → REQUEST_INFO
        │
        └─ NO
             ↓
Transaction có vượt authority?
        │
        ├─ YES → ESCALATE
        │
        └─ NO
             ↓
Các required checks đều pass?
        │
        ├─ YES → AUTO_PROCESS
        │
        └─ NO → REQUEST_INFO
```

Điểm quan trọng:

> `FAIL` của một business check thường cho biết có discrepancy, nhưng nếu chưa biết discrepancy có approval hợp lệ hay không thì kết quả phải là `REQUEST_INFO`, không phải kết luận sai phạm.

---

## 10. Step 8 — Generate specific question

Nếu decision là `REQUEST_INFO` hoặc `ESCALATE`, hệ thống phải tạo câu hỏi cụ thể.

### REQUEST_INFO example

Input:

```text
PO amount      = 30M
Invoice amount = 35M
```

Không tốt:

> Vui lòng kiểm tra lại invoice.

Tốt:

> PO được phê duyệt 30M nhưng invoice là 35M. Có PO điều chỉnh hoặc phê duyệt tăng thêm 5M không?

### ESCALATE example

Input:

```text
Amount = 120M
Threshold = 50M
```

Câu hỏi:

> Giao dịch 120M vượt ngưỡng tự xử lý 50M. Finance Manager có phê duyệt giao dịch này không?

---

## 11. Step 9 — Ghi audit log

Mỗi bước quan trọng phải tạo audit event.

Ví dụ:

```text
10:01 TRANSACTION_CREATED
10:02 PO_MATCHED
10:02 GOODS_RECEIPT_MATCHED
10:03 CHECK_VENDOR       PASS
10:03 CHECK_QUANTITY     PASS
10:03 CHECK_PAYMENT      PASS
10:04 AUTHORITY_CHECK    PASS
10:04 DECISION_MADE      AUTO_PROCESS
```

Audit phải cho phép trả lời:

- hệ thống đã làm gì;
- lúc nào;
- dùng evidence nào;
- áp dụng rule nào;
- vì sao ra kết quả đó.

---

## 12. Step 10 — Human Stop / Override

Sau decision, human vẫn có quyền can thiệp.

Ví dụ:

```text
Agent:
AUTO_PROCESS

Human phát hiện:
Supplier vừa thay đổi bank account.

Human:
STOP
Reason: Pending bank-account verification
```

Hệ thống phải tách hai thao tác:

- **Stop:** đổi `workflow_status` sang `STOPPED`, giữ nguyên decision của Agent.
- **Override:** lưu `original_action` và `overridden_action`, trong đó action mới vẫn thuộc ba decision hợp lệ.

Cả hai phải lưu actor, timestamp và reason. Không được xóa history cũ.

---

## 13. Routine Case Flow

```text
PO found
   ↓
Goods Receipt found
   ↓
Invoice parsed successfully
   ↓
Vendor PASS
   ↓
Item PASS
   ↓
Quantity PASS
(current + cumulative)
   ↓
Price PASS
   ↓
Amount PASS
   ↓
Duplicate PASS
   ↓
Payment PASS
   ↓
Cumulative PO PASS
   ↓
Inside policy
   ↓
Within 50M authority
   ↓
AUTO_PROCESS
```

---

## 14. Missing Information Flow

Ví dụ invoice cao hơn PO:

```text
PO = 30M
Invoice = 35M
       ↓
Amount check FAIL
       ↓
Có approved adjustment trong evidence?
       │
       ├─ YES → dùng adjustment rồi chạy lại checks
       │
       └─ NO / UNKNOWN
              ↓
       FACTUAL_UNKNOWN
              ↓
       REQUEST_INFO
              ↓
"Có approval tăng thêm 5M không?"
```

Khi người dùng bổ sung evidence, transaction được evaluate lại từ facts mới.

---

## 15. Beyond Authority Flow

```text
All evidence complete
       ↓
All business checks PASS
       ↓
Amount = 120M
       ↓
Authority threshold = 50M
       ↓
BEYOND_AUTHORITY
       ↓
ESCALATE
       ↓
Target: Finance Manager
       ↓
"Finance Manager có phê duyệt giao dịch 120M này không?"
```

---

## 16. Outside Policy Flow

```text
Facts complete
       ↓
Transaction type determined
       ↓
Type not covered by Policy v0
       ↓
OUTSIDE_POLICY
       ↓
ESCALATE
```

Agent không được tự tạo policy mới để xử lý transaction này.

---

## 17. Duplicate Flow

```text
Invoice received
       ↓
Duplicate check
       ↓
Same invoice found in history
       ↓
Is this confirmed as a legitimate new invoice?
       │
       ├─ UNKNOWN → REQUEST_INFO
       │
       └─ confirmed replacement/new identity
              ↓
         update evidence
              ↓
         evaluate again
```

Không được đưa duplicate unresolved trở lại payment flow như invoice mới.

---

## 18. Paid / Partially-paid Flow

```text
Invoice received
       ↓
Payment History
       ↓
Status = PAID
       ↓
STOP routine payment progression
       ↓
REQUEST_INFO
       ↓
"Invoice này đã được thanh toán. Có lý do hợp lệ để đưa lại vào payment review không?"

Status = PARTIALLY_PAID
       ↓
STOP routine payment progression
       ↓
REQUEST_INFO
       ↓
"Nêu paid_amount và hỏi phần còn lại có thực sự đang chờ thanh toán không?"
```

`STOPPED_ALREADY_PAID` / `STOPPED_PARTIAL_PAYMENT` có thể là internal operational state, nhưng user-facing Agent decision vẫn là `REQUEST_INFO`.

---

## 19. Suspicious Input Flow

```text
Invoice parsed
       ↓
Critical field flagged / uncertain
       ↓
Do NOT run a confident final decision
       ↓
FACTUAL_UNKNOWN
       ↓
REQUEST_INFO
```

Ví dụ:

> Số tiền trên invoice chưa xác định chắc chắn là 45M hay 48M. Giá trị chính xác là bao nhiêu?

---

## 20. Re-evaluation after Human Response

`REQUEST_INFO` không phải trạng thái kết thúc.

Khi human cung cấp thêm evidence:

```text
REQUEST_INFO
       ↓
Human answer / new evidence
       ↓
Attach evidence
       ↓
Normalize
       ↓
Re-run affected checks
       ↓
Re-run decision
       ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
```

Decision cũ vẫn phải được giữ trong audit history.

---

## 21. Trách nhiệm của deterministic logic và Agent

### Deterministic logic chịu trách nhiệm

- compare vendor ID;
- compare item ID;
- compare current và cumulative quantity theo item;
- compare unit price;
- tính total và cumulative total;
- duplicate lookup;
- payment-status lookup;
- authority threshold comparison.

### Agent / LLM có thể chịu trách nhiệm

- điều phối workflow;
- diễn giải check results;
- phân loại uncertainty dựa trên structured facts;
- tạo câu hỏi cụ thể;
- giải thích decision cho người dùng.

Agent không được thay đổi output của deterministic checks chỉ để tạo kết quả thuận tiện hơn.

---

## 22. Final Decision Contract

Mọi transaction sau một lần evaluation phải kết thúc bằng đúng một trong ba user-facing action:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

Mỗi decision phải có:

- `action`;
- `reason`;
- relevant policy rule IDs;
- timestamp.

`REQUEST_INFO` phải có `question`.

`ESCALATE` phải có `question` và `target` nếu policy xác định được.

---

## 23. Flow Summary

```text
                 ┌─────────────────┐
                 │      INPUT      │
                 └────────┬────────┘
                          ↓
                 Normalize + Build
                    Transaction
                          ↓
              Transaction type known?
                    │           │
                   NO          YES
                    ↓           ↓
              REQUEST_INFO   In policy?
                                │      │
                               NO     YES
                                ↓      ↓
                           ESCALATE  Evidence complete?
                                     │           │
                                    NO          YES
                                     ↓           ↓
                               REQUEST_INFO   Run Checks
                                                 ↓
                                        Facts unresolved?
                                           │          │
                                          YES        NO
                                           ↓          ↓
                                    REQUEST_INFO   Within
                                                   authority?
                                        │      │
                                       NO     YES
                                        ↓      ↓
                                   ESCALATE  AUTO_PROCESS
                                        \      /
                                         \    /
                                          ↓  ↓
                                      Audit Log
                                          ↓
                                  Human Stop/Override
```

Nguyên tắc cuối cùng:

> **Nếu chưa biết sự thật thì hỏi. Nếu sự thật đã rõ nhưng Agent không có quyền thì chuyển. Chỉ tự xử lý khi evidence đầy đủ, policy rõ và authority cho phép.**

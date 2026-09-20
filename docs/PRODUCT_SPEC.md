# InvoiceReferee — Product Specification

## 1. Product Overview

**InvoiceReferee** là AI Purchase Invoice Review & Escalation Agent dành cho quy trình mua hàng có Purchase Order (PO) và Goods Receipt.

Sản phẩm không cố tự động hóa toàn bộ quy trình kế toán. Vai trò của InvoiceReferee là trả lời một câu hỏi cụ thể:

> **Với những bằng chứng hiện có, giao dịch này đã đủ căn cứ và đủ thẩm quyền để đi tiếp chưa?**

Hệ thống tự xử lý các trường hợp thường quy và chỉ kéo con người vào khi:

- còn thiếu hoặc mâu thuẫn thông tin;
- trường hợp nằm ngoài policy;
- hoặc quyết định vượt thẩm quyền của Agent.

---

## 2. Problem Statement

Trong một giao dịch mua hàng, thông tin cần để kế toán kiểm tra trước khi thanh toán thường nằm rải rác ở nhiều nguồn:

- Purchase Order;
- xác nhận nhận hàng;
- hóa đơn nhà cung cấp;
- lịch sử thanh toán;
- policy nội bộ.

Người xử lý phải tự ghép các nguồn này lại để trả lời các câu hỏi như:

- Nhà cung cấp trên invoice có đúng với PO không?
- Hàng đã được nhận đủ chưa?
- Số lượng và đơn giá invoice có khớp không?
- Tổng tiền invoice có vượt phần đã được phê duyệt không?
- Invoice này đã xuất hiện trước đó chưa?
- Invoice này đã được thanh toán chưa?
- Giao dịch này Agent có quyền cho đi tiếp không?

Nếu dữ liệu bị thiếu hoặc bất thường, người xử lý còn phải xác định nên hỏi ai và hỏi điều gì.

InvoiceReferee gom bằng chứng theo từng transaction, chạy các kiểm tra có thể xác định bằng rule, sau đó đưa ra một trong ba hành động: `AUTO_PROCESS`, `REQUEST_INFO`, hoặc `ESCALATE`.

---

## 3. Target User

### Primary user

**Accounts Payable / Kế toán thanh toán bên mua.**

Người này nhận invoice từ supplier và cần kiểm tra hồ sơ trước khi đưa giao dịch sang bước payment review tiếp theo.

### Supporting roles

- **Purchasing:** cung cấp thông tin đã đặt mua và giá đã được phê duyệt.
- **Warehouse / Receiver:** xác nhận hàng thực tế đã nhận.
- **Finance Manager:** xử lý các trường hợp vượt thẩm quyền của Agent.
- **Supplier:** cung cấp invoice và có thể bổ sung thông tin khi hồ sơ thiếu hoặc sai lệch.

---

## 4. Sprint 1 Scope

Sprint 1 chỉ xử lý:

> **PO-based goods purchases có Goods Receipt.**

Luồng nghiệp vụ mục tiêu:

```text
Purchase Order
      ↓
Goods Received
      ↓
Supplier Invoice
      ↓
InvoiceReferee Review
      ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
      ↓
Payment Review
```

InvoiceReferee không thực hiện chuyển tiền.

---

## 5. Product Goal

Sprint 1 cần chứng minh được 4 khả năng:

1. Ghép bằng chứng của cùng một giao dịch thành một transaction.
2. Tự kiểm tra các điều kiện routine bằng logic xác định được.
3. Phân biệt đúng khi nào được đi tiếp, khi nào cần hỏi thêm và khi nào phải chuyển cho người có quyền.
4. Lưu lại đầy đủ lý do và lịch sử để con người có thể kiểm tra, dừng hoặc ghi đè quyết định.

---

## 6. Input

Một transaction trong Sprint 1 có thể sử dụng các nguồn sau:

### 6.1. Purchase Order

Thông tin tối thiểu cần dùng:

- PO ID;
- vendor;
- item;
- ordered quantity;
- approved unit price;
- approved total amount.

### 6.2. Goods Receipt

Thông tin tối thiểu:

- receipt ID;
- PO ID;
- item;
- received quantity;
- received date.

### 6.3. Supplier Invoice

Thông tin tối thiểu:

- invoice ID / invoice number;
- invoice series / ký hiệu;
- invoice type: original / adjustment / replacement;
- related original invoice nếu có;
- vendor và vendor tax code;
- PO reference;
- item;
- invoiced quantity;
- unit price;
- total amount;
- invoice date.

### 6.4. Payment History

Thông tin tối thiểu:

- invoice ID;
- payment status;
- paid amount;
- payment date nếu có.

### 6.5. Approval / Adjustment Evidence

Nếu invoice lệch PO nhưng có phê duyệt thay đổi hợp lệ, approval phải xuất hiện như một evidence có cấu trúc; Agent không được tự suy đoán approval tồn tại.

### 6.6. Company Policy

Policy xác định:

- phạm vi Agent được phép xử lý;
- rule kiểm tra;
- authority threshold;
- trường hợp nào cần human approval;
- escalation target tương ứng.

Trong Sprint 1, policy và dữ liệu có thể là synthetic nhưng phải được công bố rõ là synthetic.

### 6.7. Input Extraction Strategy

InvoiceReferee tách **đọc tài liệu** khỏi **kiểm tra nghiệp vụ**. Luồng đầu vào chuẩn là:

```text
Raw document / structured data
        ↓
Extraction Adapter
        ↓
Extracted canonical fields
        ↓
Normalization
        ↓
Transaction Builder
```

Chiến lược theo loại nguồn:

- `JSON/API`: đọc trực tiếp các field có cấu trúc; đây là đường chính của Sprint 1.
- `XML e-invoice`: parse XML và map tag sang schema `SupplierInvoice`.
- `PDF có text`: extract text rồi map các trường cần thiết.
- `PDF scan / image`: dùng OCR hoặc vision extraction rồi map về cùng schema.

Extraction layer chỉ có nhiệm vụ lấy dữ liệu như invoice number, vendor tax code, item, quantity, unit price, total amount và date. Nó **không** kết luận dữ liệu có khớp PO hay không và không tạo `AUTO_PROCESS` / `REQUEST_INFO` / `ESCALATE`.

Nếu một field quan trọng không đọc được hoặc có parse warning, hệ thống phải giữ sự bất định đó (`null`/warning/source metadata) để downstream xử lý; không được đoán field còn thiếu.

Trong Sprint 1, PO, Goods Receipt, Payment History và Approval Evidence dùng structured JSON. Supplier Invoice cũng hỗ trợ JSON trong baseline; XML/PDF/OCR là extension adapter nếu còn thời gian. Cách này giữ trọng tâm hackathon ở transaction reasoning, escalation và audit thay vì xây một OCR system hoàn chỉnh.

---

## 7. Transaction as the Core Object

InvoiceReferee không xem một invoice là một file độc lập. Đối tượng chính của hệ thống là **transaction**.

Ví dụ:

```text
Transaction TX-001

PO-001
  approved: 30M

GR-001
  received: 10 / 10

INV-001
  invoiced: 30M

Payment history
  status: UNPAID
```

Điều này cho phép hệ thống kiểm tra lịch sử giao dịch thay vì chỉ đọc nội dung của một invoice riêng lẻ.

---

## 8. Core Checks

Sprint 1 tập trung vào 8 kiểm tra chính.

### Check 1 — Vendor Match

Vendor trên invoice phải khớp vendor được phê duyệt trên PO.

### Check 2 — Item Match

Item trên invoice phải thuộc item đã được đặt mua.

### Check 3 — Quantity Match

So sánh ordered quantity, cumulative received quantity và invoiced quantity theo từng item.

Ngoài invoice hiện tại, hệ thống phải cộng quantity của các invoice trước đó cùng PO/item. Tổng quantity đã invoice không được vượt tổng quantity đã xác nhận nhận hàng nếu chưa có bằng chứng bổ sung.

### Check 4 — Unit Price Match

Unit price trên invoice phải khớp giá đã được phê duyệt hoặc có bằng chứng điều chỉnh hợp lệ.

### Check 5 — Amount Check

Invoice amount phải phù hợp với PO và dữ liệu hàng đã nhận.

### Check 6 — Duplicate Invoice

Phát hiện cùng invoice đã xuất hiện trước đó trong transaction history hoặc payment history. Identity ưu tiên `vendor_tax_code + invoice_series + invoice_number`; amount/date chỉ là tín hiệu hỗ trợ.

Invoice có type `ADJUSTMENT` hoặc `REPLACEMENT` và liên kết rõ với invoice gốc phải được giữ như quan hệ lịch sử, không tự động gắn duplicate.

### Check 7 — Payment Status

Phát hiện invoice đã `PAID`, `PARTIALLY_PAID` hoặc có trạng thái chưa rõ để tránh đưa lại vào routine payment review như một invoice mới.

### Check 8 — Cumulative PO Limit

Tổng giá trị các invoice gắn với cùng PO không được vượt giá trị đã được phê duyệt trên PO, trừ khi có adjustment / approval hợp lệ.

Các phép so sánh số lượng và số tiền phải được thực hiện bằng deterministic logic, không giao cho LLM tự tính toán.

### LLM Agent Layer

Sau khi deterministic checks hoàn tất, LLM Agent nhận structured facts, check results và policy context. LLM phải trả structured assessment thay vì text tự do gồm:

- uncertainty type đề xuất;
- action đề xuất;
- primary check cần xử lý trước nếu có nhiều vấn đề;
- explanation;
- câu hỏi cụ thể nếu cần human;
- target nếu policy xác định được;
- policy rule IDs liên quan;
- check/evidence references được dùng để giải thích.

LLM là phần của normal review flow. Khi có nhiều discrepancy, LLM có nhiệm vụ chọn vấn đề unresolved quan trọng nhất trong tập check đã được xác nhận để tạo một câu hỏi mà người nhận có thể trả lời trực tiếp. LLM không có quyền sửa facts, thay rule result, tự tính số tiền/số lượng hoặc bỏ qua authority constraint. Một deterministic Decision Guard luôn kiểm tra assessment trước final decision.

Nếu LLM lỗi/timeout/output invalid, hệ thống dùng deterministic fallback explanation/question, giữ nguyên policy-correct decision và ghi rõ fallback trong audit. Fallback bảo toàn tính an toàn/vận hành nhưng không được dùng để tuyên bố chất lượng câu hỏi tương đương normal LLM path.

---

## 9. Decision Model

Hệ thống chỉ có 3 quyết định user-facing.

### 9.1. AUTO_PROCESS

Điều kiện:

- bằng chứng đầy đủ;
- các kiểm tra bắt buộc đều đạt;
- transaction nằm trong policy;
- không vượt authority threshold.

Ý nghĩa:

> Routine review đã hoàn thành và transaction có thể đi tiếp sang bước payment review.

`AUTO_PROCESS` không đồng nghĩa với tự động thanh toán.

### 9.2. REQUEST_INFO

Dùng khi một sự thật cần thiết chưa xác định được.

Ví dụ:

```text
PO amount      = 30M
Invoice amount = 35M
```

Hệ thống chưa biết có approval tăng giá hay không.

Kết quả:

```text
REQUEST_INFO
```

Câu hỏi:

> Có PO điều chỉnh hoặc phê duyệt tăng giá từ 30M lên 35M không?

### 9.3. ESCALATE

Dùng khi facts đã rõ nhưng Agent không được quyền tự quyết.

Hai nhóm chính:

#### Outside policy

Trường hợp không nằm trong phạm vi policy hiện tại.

#### Beyond authority

Trường hợp policy đã rõ nhưng cần người có thẩm quyền phê duyệt.

Ví dụ:

```text
Transaction amount = 120M
Policy threshold   = 50M
```

Kết quả:

```text
ESCALATE
Target: Finance Manager
```

---

## 10. Decision Priority

Hệ thống phải xác định transaction type trước khi đòi evidence đặc thù của workflow:

```text
1. Chưa xác định transaction type
      → REQUEST_INFO

2. Transaction type đã rõ và ngoài policy
      → ESCALATE

3. Transaction thuộc scope nhưng thiếu / mâu thuẫn facts
      → REQUEST_INFO

4. Facts đã rõ nhưng vượt authority
      → ESCALATE

5. Đầy đủ + đúng policy + trong authority
      → AUTO_PROCESS
```

Agent không được hỏi Goods Receipt cho một service invoice đã được xác định rõ là outside policy, và không được suy đoán để biến một `REQUEST_INFO` thành `AUTO_PROCESS`.

---

## 11. Specific Question Requirement

Mỗi `REQUEST_INFO` hoặc `ESCALATE` phải tạo câu hỏi cụ thể, dựa trên đúng phần bằng chứng đang thiếu hoặc quyền quyết định đang cần.

Không chấp nhận câu hỏi chung chung như:

> Vui lòng kiểm tra lại hồ sơ.

Ví dụ tốt:

> Hệ thống ghi nhận PO phê duyệt 30M nhưng invoice là 35M. Có phê duyệt điều chỉnh thêm 5M không?

Hoặc:

> Giao dịch 120M vượt ngưỡng 50M của Agent. Finance Manager có phê duyệt giao dịch này không?

---

## 12. Auditability

Mỗi transaction phải có audit trail để người dùng có thể xem lại quá trình Agent xử lý.

Tối thiểu cần lưu:

- action;
- timestamp;
- input / evidence liên quan;
- check hoặc policy rule được áp dụng;
- kết quả;
- reason;
- final decision.

Ví dụ:

```text
10:01  Invoice received
10:02  PO matched
10:02  Goods Receipt matched
10:03  Vendor check       PASS
10:03  Quantity check     PASS
10:03  Duplicate check    PASS
10:04  Authority check    PASS
10:04  Decision           AUTO_PROCESS
```

---

## 13. Human Stop and Override

Con người luôn giữ quyền cuối cùng.

Người dùng phải có khả năng:

- **Stop** một transaction bằng cách đổi workflow status sang `STOPPED`;
- **Override** một quyết định của Agent bằng một decision khác trong ba decision hợp lệ;
- nhập lý do cho mọi human intervention.

Stop không tạo decision thứ tư. Override không được xóa quyết định ban đầu của Agent; audit phải lưu actor, timestamp, quyết định cũ, quyết định mới và lý do.

Ví dụ:

Agent trả `AUTO_PROCESS`, nhưng kế toán phát hiện supplier vừa thay đổi tài khoản ngân hàng và muốn xác minh thủ công.

Kế toán có thể Stop transaction và ghi:

> Pending supplier bank-account verification.

---

## 14. Primary User Flow

```text
1. User chọn hoặc nhập một transaction
       ↓
2. Hệ thống gom PO + Receipt + Invoice + Payment History
       ↓
3. Chạy core checks
       ↓
4. Tạo policy / authority context
       ↓
5. LLM Agent reasoning + explanation + question
       ↓
6. Decision Guard kiểm tra proposal
       ↓
7. Trả final decision
       ↓
   AUTO_PROCESS
   REQUEST_INFO
   ESCALATE
       ↓
8. Hiển thị reason + evidence + question nếu có
       ↓
9. Lưu audit log gồm cả AgentAssessment / fallback state
       ↓
10. Human có thể Stop / Override
```

---

## 15. Expected UI Output

Ngoài sample selector để demo nhanh, UI phải cho phép judge **paste JSON hoặc upload một JSON transaction mới** và chạy qua đúng production review path. Đây là đường vào cho unseen inputs; không yêu cầu sửa code hoặc thêm fixture trước.

Với mỗi transaction, người dùng cần nhìn thấy tối thiểu:

- Transaction ID;
- các document / evidence hiện có;
- kết quả từng check;
- decision hiện tại;
- reason;
- escalation / information question nếu có;
- escalation target nếu có;
- LLM explanation / assessment status;
- audit history;
- Stop / Override controls.

Ví dụ:

```text
Transaction: TX-001

Evidence
PO              ✓
Goods Receipt   ✓
Invoice         ✓
Payment History ✓

Checks
Vendor          PASS
Item            PASS
Quantity        PASS
Price           PASS
Amount          PASS
Duplicate       PASS
Payment         PASS
PO Limit        PASS

Decision
AUTO_PROCESS

Reason
All required evidence is consistent and the transaction is within agent authority.
```

---

## 16. Sprint 1 Success Criteria

Sprint 1 được xem là đạt mục tiêu sản phẩm khi:

- xử lý được ít nhất 17 documented test cases theo policy;
- routine cases được tự xử lý;
- ambiguous cases không bị Agent tự đoán;
- outside-policy và beyond-authority cases được chuyển đúng;
- câu hỏi chuyển tiếp cụ thể;
- input mới có thể được xử lý bằng cùng logic;
- core logic không phụ thuộc vào case ID;
- audit trail truy xuất được quyết định;
- Stop / Override hoạt động;
- Verify harness chạy được các case yêu cầu của Challenge A.

---

## 17. Non-goals

Sprint 1 không nhằm xây dựng:

- hệ thống OCR hoàn chỉnh;
- full e-invoice lifecycle;
- VAT / TNDN compliance engine;
- tax filing;
- automatic accounting entries;
- fraud detection;
- tất cả loại invoice;
- complex service-invoice workflows;
- automatic payment;
- full procurement platform;
- ERP replacement.

OCR, PDF parsing hoặc XML parsing nếu được thêm vào chỉ đóng vai trò **extraction adapter**, output cùng canonical schema như JSON input; chúng không phải giá trị cốt lõi của InvoiceReferee.

---

## 18. Product Principle

Nguyên tắc trung tâm của InvoiceReferee:

> **Rule engine xác định facts có thể kiểm chứng; Agent quyết định bước tiếp theo dựa trên evidence, policy và authority; con người giữ quyền can thiệp cuối cùng.**

InvoiceReferee không cố thay kế toán bằng AI. Sản phẩm tự động hóa những quyết định thường quy có đủ bằng chứng và làm rõ chính xác khi nào con người cần tham gia.

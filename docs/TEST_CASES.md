# InvoiceReferee — Test Cases

## 1. Mục đích

File này là ground truth cho Sprint 1. Implementation chỉ được xem là đúng khi cùng một policy có thể xử lý được các case dưới đây và input mới tương tự mà không hard-code theo case ID.

## 2. Decision labels

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

## 3. Bộ 17 test cases

| ID | Scenario | Facts chính | Expected | Rule |
| --- | --- | --- | --- | --- |
| TC01 | Routine exact match | PO 30M, received 10/10, invoice 30M, unpaid | AUTO_PROCESS | P01–P12 pass |
| TC02 | Routine partial invoice | PO 30M/10 units, received 10, invoice 5 units/15M | AUTO_PROCESS | P05, P07 pass |
| TC03 | Multiple invoices within PO | Received 10; prior invoice 4 units/12M; new invoice 6 units/18M; total 10 units/30M | AUTO_PROCESS | P05, P08 pass |
| TC04 | Missing Goods Receipt | PO + invoice có, GR chưa có | REQUEST_INFO | P04 |
| TC05 | PO chưa xác định | Invoice có PO reference không resolve được | REQUEST_INFO | P01 |
| TC06 | Vendor mismatch | PO vendor ABC, invoice vendor XYZ, chưa có approval | REQUEST_INFO | P02 |
| TC07 | Quantity exceeds receipt | Received 8, invoice 10 | REQUEST_INFO | P05 |
| TC08 | Unit price mismatch | PO 3M/unit, invoice 3.5M/unit | REQUEST_INFO | P06 |
| TC09 | Invoice exceeds PO | PO 30M, invoice 35M, chưa có amendment | REQUEST_INFO | P07 |
| TC10 | Cumulative invoices exceed PO | PO 30M, prior invoices 20M, new invoice 15M | REQUEST_INFO | P08 |
| TC11 | Duplicate invoice | Same vendor tax code + invoice series + invoice number đã tồn tại | REQUEST_INFO | P09 |
| TC12 | Already paid | Payment history = PAID | REQUEST_INFO | P10 |
| TC13 | Beyond authority | Tất cả checks pass, amount 120M, threshold 50M | ESCALATE | P12 |
| TC14 | Outside policy | Service invoice, transaction type rõ, không thuộc PO-goods workflow | ESCALATE | P13 |
| TC15 | Suspicious critical field | Invoice amount đọc không chắc 45M hay 48M | REQUEST_INFO | P15 |
| TC16 | Cumulative quantity exceeds receipt | Received 10; prior invoices 8 units; new invoice 4 units → total 12 | REQUEST_INFO | P05 |
| TC17 | Partially paid | Invoice 30M; payment history = PARTIALLY_PAID, paid 10M | REQUEST_INFO | P10 |

## 4. Expected questions

### TC04 — Missing Goods Receipt

> Chưa có xác nhận nhận hàng cho PO này. Goods Receipt tương ứng ở đâu?

### TC05 — PO chưa xác định

> Không tìm thấy Purchase Order cho invoice này. PO ID hoặc PO liên quan là gì?

### TC06 — Vendor mismatch

> Supplier trên PO là ABC nhưng invoice được phát hành bởi XYZ. Có thay đổi supplier đã được phê duyệt không?

### TC07 — Quantity mismatch

> Goods Receipt xác nhận đã nhận 8 đơn vị nhưng invoice tính 10 đơn vị. Có biên bản nhận bổ sung hoặc điều chỉnh nào chưa được cung cấp không?

### TC08 — Price mismatch

> PO phê duyệt đơn giá 3M nhưng invoice dùng 3.5M. Có phê duyệt điều chỉnh đơn giá không?

### TC09 — Amount mismatch

> PO được phê duyệt 30M nhưng invoice là 35M. Có PO điều chỉnh hoặc phê duyệt tăng thêm 5M không?

### TC10 — Cumulative over PO

> Tổng các invoice cho PO này sẽ đạt 35M, vượt PO 30M. Có PO amendment hoặc phê duyệt bổ sung 5M không?

### TC11 — Duplicate

> Invoice này đã xuất hiện trong lịch sử xử lý. Đây là bản gửi lại của invoice cũ hay một invoice mới hợp lệ?

### TC12 — Already paid

> Payment history cho thấy invoice này đã được thanh toán. Có lý do hợp lệ nào để đưa invoice trở lại payment review không?

### TC13 — Beyond authority

> Giao dịch 120M vượt ngưỡng tự xử lý 50M. Finance Manager có phê duyệt giao dịch này không?

### TC14 — Outside policy

> Transaction này không thuộc workflow PO-based goods purchase mà policy hiện tại bao phủ. Ai là người có thẩm quyền xử lý loại giao dịch này?

### TC15 — Suspicious input

> Số tiền trên invoice chưa xác định chắc chắn là 45M hay 48M. Giá trị chính xác là bao nhiêu?

### TC16 — Cumulative quantity exceeds receipt

> Đã nhận 10 đơn vị. Các invoice trước đã tính 8 đơn vị và invoice mới tính thêm 4, tổng thành 12. Có Goods Receipt bổ sung hoặc điều chỉnh được phê duyệt không?

### TC17 — Partially paid

> Invoice là 30M và đã thanh toán 10M. Có phải phần còn lại 20M vẫn đang chờ thanh toán không?

## 5. Challenge A Verify — 5 cases

Đây là bộ 5 case dành riêng cho bài kiểm tra Escalation Referee.

| Verify ID | Source case | Expected | Nhóm |
| --- | --- | --- | --- |
| EV01 | TC01 | AUTO_PROCESS | Routine |
| EV02 | TC02 | AUTO_PROCESS | Routine |
| EV03 | TC03 | AUTO_PROCESS | Routine |
| EV04 | TC07 | REQUEST_INFO | Factual unknown |
| EV05 | TC13 | ESCALATE | Beyond authority |

Điều kiện pass:

```text
3 routine → AUTO_PROCESS
2 human-involved cases → đúng decision theo uncertainty
```

Hai case cần con người phải hiển thị câu hỏi cụ thể. Verify phải hiển thị `uncertainty_type`; với `ESCALATE` phải hiển thị target nếu policy xác định được. Outside-policy vẫn được kiểm ở bộ Core Verify và toàn bộ evaluation set.

## 6. Core Verify — 4 cases

Để đáp ứng Verify chung của cuộc thi:

| Verify ID | Source case | Expected |
| --- | --- | --- |
| CV01 | TC01 | AUTO_PROCESS |
| CV02 | TC07 | REQUEST_INFO |
| CV03 | TC13 | ESCALATE |
| CV04 | TC14 | ESCALATE |

Verify phải chạy bằng một thao tác và in:

- case ID;
- expected;
- actual;
- pass/fail;
- uncertainty type nếu có;
- question nếu có;
- target nếu có;
- timestamp.

## 7. Judge unseen-input principles

Judge có thể thay đổi vendor, amount, quantity, invoice number hoặc transaction type. Logic phải dựa trên field và policy, không dựa trên các giá trị cụ thể trong test fixture.

Ví dụ unseen case hợp lệ:

```text
PO = 42M
Received = 14
Invoice = 42M
Payment = UNPAID
```

Nếu mọi checks pass và amount <= 50M:

```text
AUTO_PROCESS
```

Ví dụ unseen case vượt quyền:

```text
PO = 75M
All checks pass
```

Expected:

```text
ESCALATE
BEYOND_AUTHORITY
```

## 8. Test fixture rule

Mỗi case nên được lưu dưới dạng JSON input riêng, ví dụ:

```text
tests/fixtures/TC01.json
...
tests/fixtures/TC17.json
```

Expected result được lưu trong test code hoặc một manifest riêng, nhưng production code không được đọc expected result.


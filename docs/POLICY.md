# InvoiceReferee — Policy v0

## 1. Mục đích

File này định nghĩa **ranh giới quyết định của InvoiceReferee trong Sprint 1**.

Policy này là **synthetic policy dùng cho prototype và evaluation**, không phải policy thật của một doanh nghiệp cụ thể.

Mục tiêu của policy là giúp hệ thống phân biệt rõ:

- khi nào được `AUTO_PROCESS`;
- khi nào phải `REQUEST_INFO`;
- khi nào phải `ESCALATE`.

---

## 2. Phạm vi policy

Policy v0 chỉ áp dụng cho:

> **PO-based goods purchases có Goods Receipt.**

Một transaction nằm trong phạm vi khi có thể liên kết được tối thiểu:

- Purchase Order;
- Goods Receipt;
- Supplier Invoice;
- Payment History hoặc trạng thái thanh toán;
- policy / authority rule tương ứng.

Các loại transaction khác không được Agent tự suy diễn theo policy này.

---

## 3. Ba loại quyết định

### AUTO_PROCESS

Chỉ dùng khi:

- facts cần thiết đã đầy đủ;
- các rule bắt buộc đều đạt;
- transaction nằm trong phạm vi policy;
- transaction nằm trong thẩm quyền của Agent.

`AUTO_PROCESS` nghĩa là transaction đã qua routine review và có thể đi tiếp sang payment review.

Nó **không** có nghĩa là tự động thanh toán.

### REQUEST_INFO

Dùng khi Agent **chưa biết đủ sự thật** để áp dụng policy.

Ví dụ:

- thiếu Goods Receipt;
- không tìm thấy PO;
- PO và Invoice lệch số tiền nhưng chưa biết có approval điều chỉnh hay không;
- dữ liệu giữa hai nguồn mâu thuẫn;
- payment status chưa xác định được.

Agent phải hỏi một câu cụ thể để bổ sung đúng phần facts còn thiếu.

### ESCALATE

Dùng khi facts đã rõ nhưng:

- transaction nằm ngoài policy;
- hoặc quyết định vượt thẩm quyền của Agent.

Agent phải nêu rõ:

- lý do chuyển tiếp;
- người/role cần quyết định nếu policy xác định được;
- câu hỏi cụ thể cần được trả lời.

---

## 4. Thứ tự ưu tiên quyết định

Policy/Decision Guard phải xác định **transaction type trước**, rồi mới yêu cầu evidence đặc thù của workflow PO-based goods purchase. Điều này tránh lỗi ví dụ service invoice bị hỏi Goods Receipt dù policy đã xác định rõ loại giao dịch đó nằm ngoài phạm vi.

`PolicyContext.scope_status` phải phân biệt ba trạng thái: `UNKNOWN`, `OUTSIDE_POLICY`, `IN_SCOPE`. Không gộp `UNKNOWN` và `OUTSIDE_POLICY` vào cùng một boolean.

```text
1. Chưa xác định được transaction type
      → REQUEST_INFO

2. Transaction type đã rõ và ngoài phạm vi policy
      → ESCALATE

3. Transaction thuộc phạm vi nhưng facts bắt buộc thiếu / mâu thuẫn
      → REQUEST_INFO

4. Facts đã rõ nhưng vượt thẩm quyền
      → ESCALATE

5. Đủ facts + đúng policy + trong authority
      → AUTO_PROCESS
```

Nguyên tắc quan trọng:

> **Không yêu cầu evidence chỉ áp dụng cho workflow PO-based goods purchase nếu transaction đã được xác định rõ là ngoài policy.**

> **Trong một transaction thuộc scope, không được dùng ESCALATE hoặc AUTO_PROCESS để che một fact bắt buộc còn chưa xác định.**

---

## 5. Policy Rules

### P01 — PO bắt buộc phải xác định được

Nếu transaction thuộc workflow mua hàng có PO nhưng không tìm được PO tương ứng:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Không tìm thấy Purchase Order cho invoice này. PO ID hoặc PO liên quan là gì?

Nếu facts xác nhận rõ transaction thực sự **không sử dụng PO** thì transaction nằm ngoài policy v0:

```text
ESCALATE
```

---

### P02 — Supplier phải khớp PO

Supplier trên invoice phải khớp supplier được phê duyệt trên PO.

Nếu không khớp và chưa có bằng chứng giải thích:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Supplier trên PO là ABC nhưng invoice được phát hành bởi XYZ. Có thay đổi supplier đã được phê duyệt không?

---

### P03 — Item phải thuộc PO

Item trên invoice phải tồn tại trong PO tương ứng.

Nếu invoice chứa item không có trong PO và chưa có amendment/approval:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Invoice có item chưa xuất hiện trong PO. Có PO điều chỉnh hoặc phê duyệt bổ sung item này không?

---

### P04 — Goods Receipt là bằng chứng nhận hàng bắt buộc

Đối với workflow Sprint 1, phải có Goods Receipt hoặc bằng chứng nhận hàng tương đương được policy công nhận.

Nếu Goods Receipt bị thiếu:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Chưa có xác nhận nhận hàng cho PO này. Goods Receipt tương ứng ở đâu?

---

### P05 — Invoice quantity không được vượt received quantity

Điều kiện routine phải kiểm tra cả invoice hiện tại và lịch sử các invoice trước đó theo từng item:

```text
invoiced_quantity <= received_quantity

sum(prior_invoiced_quantity_by_item) + current_invoiced_quantity
    <= cumulative_received_quantity_by_item
```

Nếu invoice hiện tại hoặc tổng quantity đã invoice vượt lượng hàng đã nhận và chưa có approval/bằng chứng nhận bổ sung:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Goods Receipt xác nhận đã nhận 8 đơn vị nhưng invoice tính 10 đơn vị. Có biên bản nhận bổ sung hoặc điều chỉnh nào chưa được cung cấp không?

Ví dụ cumulative:

> Tổng các invoice của ITEM-001 sẽ thành 16 đơn vị trong khi mới xác nhận nhận 10 đơn vị. Có Goods Receipt bổ sung hoặc điều chỉnh đã được phê duyệt không?

---

### P06 — Unit price phải khớp approved price

Điều kiện routine:

```text
invoice_unit_price == approved_unit_price
```

Nếu lệch giá và chưa có approval/amendment:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> PO phê duyệt đơn giá 3M nhưng invoice dùng 3.5M. Có phê duyệt điều chỉnh đơn giá không?

---

### P07 — Invoice total không được vượt phần đã được phê duyệt

Nếu invoice amount vượt giá trị có thể chứng minh từ PO / quantity / approved price và chưa có amendment:

```text
REQUEST_INFO
```

Ví dụ:

```text
PO total      = 30M
Invoice total = 35M
```

Câu hỏi mẫu:

> PO được phê duyệt 30M nhưng invoice là 35M. Có PO điều chỉnh hoặc phê duyệt tăng thêm 5M không?

---

### P08 — Tổng invoice theo PO không được vượt PO

Với nhiều invoice cùng tham chiếu một PO:

```text
sum(valid_invoice_amounts) <= approved_po_amount
```

Nếu tổng invoice vượt PO và chưa có adjustment:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Tổng các invoice cho PO này vượt giá trị đã được phê duyệt. Có PO amendment hoặc phê duyệt bổ sung không?

---

### P09 — Duplicate invoice không được xử lý như invoice mới

Duplicate identity ưu tiên dùng các định danh ổn định:

```text
vendor_tax_code + invoice_series + invoice_number
```

Nếu dữ liệu không có đủ ba trường trên, có thể fallback sang `vendor_id + invoice_number`, nhưng phải coi đây là bằng chứng yếu hơn. `amount` và `invoice_date` chỉ là tín hiệu hỗ trợ, không đủ để tự kết luận duplicate.

Nếu cùng invoice identity đã tồn tại trong lịch sử:

```text
REQUEST_INFO
```

Backend có thể đánh dấu transaction ở trạng thái `STOPPED_DUPLICATE` trong khi chờ người dùng xác nhận.

Câu hỏi mẫu:

> Invoice này đã xuất hiện trong lịch sử xử lý. Đây là bản gửi lại của invoice cũ hay một invoice mới hợp lệ?

Agent không được tiếp tục như một invoice mới khi duplicate chưa được giải thích.

Nếu invoice được khai báo rõ là `ADJUSTMENT` hoặc `REPLACEMENT` và có `related_invoice_number`, hệ thống phải liên kết nó với invoice gốc thay vì tự động coi là duplicate. Sprint 1 chỉ nhận diện và giữ quan hệ này; tác động kế toán/thuế phức tạp của hóa đơn điều chỉnh/thay thế không được tự suy diễn nếu policy chưa mô tả.

---

### P10 — Invoice đã có thanh toán không được quay lại routine payment queue

Nếu payment history xác định invoice đã `PAID`:

```text
REQUEST_INFO
```

Backend có thể đánh dấu `STOPPED_ALREADY_PAID`.

Câu hỏi mẫu:

> Payment history cho thấy invoice này đã được thanh toán. Có lý do hợp lệ nào để đưa invoice trở lại payment review không?

Không được `AUTO_PROCESS` một invoice đã thanh toán như một invoice mới.

Nếu payment history là `PARTIALLY_PAID`, transaction cũng phải dừng routine flow:

```text
REQUEST_INFO
```

Câu hỏi phải nêu rõ số tiền đã trả và số tiền còn lại cần xác minh, ví dụ:

> Invoice 30M đã được thanh toán 10M. Có phải phần còn lại 20M vẫn đang chờ thanh toán không?

---

### P11 — Payment status chưa rõ thì không được suy đoán

Nếu payment history bị thiếu hoặc mâu thuẫn đến mức không xác định được invoice đã thanh toán hay chưa:

```text
REQUEST_INFO
```

Câu hỏi mẫu:

> Chưa xác định được trạng thái thanh toán của invoice này. Invoice hiện là UNPAID, PARTIALLY_PAID hay PAID?

---

### P12 — Authority threshold

Synthetic authority rule cho Sprint 1:

```text
transaction_amount <= 50,000,000 VND
    → Agent có thể AUTO_PROCESS nếu mọi rule khác đều đạt

transaction_amount > 50,000,000 VND
    → Finance Manager approval required
```

Khi transaction vượt 50M và facts đã rõ:

```text
ESCALATE
Target: Finance Manager
```

Câu hỏi mẫu:

> Giao dịch có giá trị 120M, vượt ngưỡng tự xử lý 50M. Finance Manager có phê duyệt giao dịch này không?

Ngưỡng 50M là dữ liệu synthetic phục vụ prototype, không phải quy định pháp lý hay policy thật của một doanh nghiệp cụ thể.

---

### P13 — Outside-policy transaction

Nếu transaction type đã được xác định rõ nhưng không thuộc phạm vi:

- PO-based goods purchase;
- có Goods Receipt;
- và các rule của policy v0;

thì:

```text
ESCALATE
```

Ví dụ:

- service invoice không có Goods Receipt;
- advance-payment workflow;
- tax-only adjustment workflow;
- loại transaction chưa được policy định nghĩa.

Câu hỏi mẫu:

> Transaction này không thuộc workflow PO-based goods purchase mà policy hiện tại bao phủ. Ai là người có thẩm quyền xử lý loại giao dịch này?

---

### P14 — Conflicting evidence

Nếu hai nguồn bằng chứng đáng tin cậy mâu thuẫn nhau và không có rule xác định nguồn nào thắng:

```text
REQUEST_INFO
```

Agent không được chọn một nguồn tùy ý.

Câu hỏi phải chỉ rõ hai facts đang xung đột.

---

### P15 — Suspicious / flagged input

Nếu input đã được gắn cờ nghi vấn, parse không chắc chắn hoặc chứa giá trị không thể xác minh:

```text
REQUEST_INFO
```

Agent không được đưa ra kết luận chắc chắn dựa trên dữ liệu đó.

Ví dụ:

> Số tiền trên invoice chưa đọc chắc chắn là 45M hay 48M. Giá trị chính xác là bao nhiêu?

---

## 6. Điều kiện để AUTO_PROCESS

Một transaction chỉ được `AUTO_PROCESS` khi **tất cả** điều kiện sau đúng:

1. Transaction thuộc phạm vi policy v0.
2. PO được xác định.
3. Goods Receipt được xác định.
4. Supplier match.
5. Item match.
6. Invoice hiện tại và cumulative invoiced quantity theo từng item không vượt cumulative received quantity.
7. Unit price match hoặc đã có approved adjustment.
8. Invoice total hợp lệ.
9. Cumulative invoice total không vượt PO.
10. Không có unresolved duplicate.
11. Invoice có payment status `UNPAID`; không có `PAID`, `PARTIALLY_PAID` hoặc trạng thái chưa rõ.
12. Không có conflicting / suspicious fact chưa giải quyết.
13. Transaction amount không vượt authority threshold hoặc đã có approval phù hợp với workflow sau này.

Nếu bất kỳ fact cần thiết nào chưa rõ, không được `AUTO_PROCESS`.

---

## 7. Escalation Targets

Policy v0 dùng các target sau:

| Tình huống | Target |
| --- | --- |
| Vượt ngưỡng 50M | Finance Manager |
| Outside-policy transaction | Accounting / Finance owner |
| Authority không xác định | Finance Manager |

Các trường hợp thiếu facts không mặc định chuyển cho Finance Manager; trước hết phải `REQUEST_INFO` từ nguồn có thể cung cấp facts cần thiết.

---

## 8. Question Quality Rules

Mọi câu hỏi của Agent phải:

1. Nêu rõ fact nào đang thiếu hoặc rule nào cần quyết định.
2. Đưa số liệu / evidence liên quan nếu có.
3. Có thể được trả lời trực tiếp.
4. Không dùng câu chung chung như "Please review" hoặc "Kiểm tra lại giúp tôi".

Mẫu:

```text
[Fact hiện có]
+ [điểm thiếu / xung đột / vượt quyền]
+ [câu hỏi trực tiếp]
```

Ví dụ:

> PO phê duyệt 30M nhưng invoice là 35M. Có phê duyệt điều chỉnh thêm 5M không?

---

## 9. Human Stop / Override Policy

Con người có hai loại can thiệp khác nhau và hệ thống phải lưu riêng:

### Stop

`STOP` thay đổi trạng thái vận hành của workflow, ví dụ `ACTIVE → STOPPED`. Nó **không phải decision thứ tư của Agent** và không được thay `Decision.action`.

Stop phải lưu actor, timestamp và reason.

### Override

Override thay đổi quyết định hiệu lực của con người sau khi Agent đã đưa ra một trong ba decision hợp lệ.

Override phải lưu:

- original decision;
- overridden decision;
- actor;
- timestamp;
- reason.

`overridden decision` vẫn phải thuộc `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`. Không dùng `STOPPED` làm decision.

Không được xóa hoặc ghi đè mất quyết định ban đầu của Agent.

---

## 10. Audit Requirement

Mỗi rule evaluation phải ghi được tối thiểu:

- rule ID;
- evidence được dùng;
- expected value nếu có;
- actual value nếu có;
- result;
- reason;
- timestamp.

Ví dụ:

```text
Rule: P05_QUANTITY
Expected: received_quantity >= invoiced_quantity
Received: 8
Invoiced: 10
Result: NEEDS_INFO
Reason: Invoice quantity exceeds confirmed received quantity
```

---

## 11. Không dùng LLM để quyết định facts xác định được

Các rule sau phải dùng deterministic logic:

- số lượng lớn hơn / nhỏ hơn;
- giá trị tiền;
- duplicate identity;
- payment status;
- cumulative quantity theo item;
- cumulative PO amount;
- authority threshold.

LLM Agent là component chính thức sau deterministic checks. Nó phải:

- reason trên structured facts và check results;
- đề xuất `uncertainty_type` và action;
- chọn một primary unresolved check trong số check results hiện có khi cần hỏi người;
- giải thích result bằng ngôn ngữ tự nhiên;
- tạo câu hỏi cụ thể từ structured facts;
- xác định target từ policy context khi có;
- trả check/evidence references để explanation có thể trace lại.

Mọi output của LLM phải đi qua deterministic Decision Guard. Guard không chấp nhận proposal trái mapping policy, ví dụ `FACTUAL_UNKNOWN → AUTO_PROCESS` hoặc transaction vượt 50M → `AUTO_PROCESS`.

LLM không được tự tính, tự sửa facts, thay rule result hoặc tạo policy mới để làm transaction pass. Nếu LLM lỗi/timeout/output invalid, hệ thống dùng deterministic fallback và ghi audit event tương ứng.

---

## 12. Policy v0 Summary

```text
Transaction type chưa rõ
        ↓
REQUEST_INFO

Transaction type đã rõ và ngoài policy
        ↓
ESCALATE

Transaction thuộc scope nhưng thiếu / mâu thuẫn bằng chứng
        ↓
REQUEST_INFO

Facts đã rõ nhưng vượt authority
        ↓
ESCALATE

Facts đầy đủ + checks pass + trong policy + trong authority
        ↓
AUTO_PROCESS
```

Policy v0 ưu tiên **không đoán**, nhưng cũng không được **over-escalate** các case routine.

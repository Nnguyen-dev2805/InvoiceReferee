# InvoiceReferee — Challenge Summary

## 1. Challenge đã chọn

**Challenge A — Escalation Referee**

Mục tiêu cốt lõi: hệ thống phải tự xử lý các trường hợp thường quy và biết chính xác khi nào cần dừng để hỏi hoặc chuyển cho con người.

InvoiceReferee không được rơi vào hai cực đoan:
- chuyển mọi trường hợp cho con người;
- hoặc tự xử lý mọi trường hợp dù dữ liệu còn nghi vấn.

---

## 2. Quy trình mà team chọn

InvoiceReferee tập trung vào quy trình mua hàng có PO và xác nhận nhận hàng:

```text
Purchase Order
→ Goods Receipt
→ Supplier Invoice
→ Review
→ Payment Review
```

Trong Sprint 1, InvoiceReferee phụ trách bước **Review**: kiểm tra bằng chứng giao dịch, xác định hồ sơ có đủ căn cứ để đi tiếp hay cần con người can thiệp.

**Phạm vi Sprint 1:** PO-based goods purchases có Goods Receipt.

---

## 3. Ba loại tình huống bắt buộc phải phân biệt

### 3.1. Chưa xác định được thông tin thực tế

Dữ liệu bị thiếu, mâu thuẫn hoặc chưa đủ để kết luận.

Ví dụ:
- PO = 30M
- Invoice = 35M
- Chưa biết có PO điều chỉnh hoặc phê duyệt tăng giá hay không.

Kết quả mong đợi:

```text
REQUEST_INFO
```

Hệ thống phải hỏi một câu cụ thể để bổ sung phần thông tin còn thiếu.

### 3.2. Ngoài phạm vi quy định

Thông tin đã rõ nhưng trường hợp đó không nằm trong policy mà Agent được phép áp dụng.

Ví dụ:
- Policy Sprint 1 chỉ bao phủ giao dịch mua hàng có PO.
- Hệ thống nhận một invoice không có PO và loại giao dịch này không được policy định nghĩa.

Kết quả mong đợi:

```text
ESCALATE
```

### 3.3. Vượt thẩm quyền

Thông tin đã đầy đủ và nhất quán nhưng quyết định cuối cùng vượt quyền của Agent.

Ví dụ:
- PO = 120M
- Receipt = đầy đủ
- Invoice = 120M
- Policy quy định giao dịch trên 50M cần Finance Manager phê duyệt.

Kết quả mong đợi:

```text
ESCALATE
```

---

## 4. Ba hành động chính của hệ thống

### AUTO_PROCESS

Dùng khi:
- dữ liệu cần thiết đầy đủ;
- PO, Goods Receipt và Invoice nhất quán theo policy;
- không phát hiện duplicate invoice;
- invoice chưa được thanh toán trước đó;
- giao dịch nằm trong phạm vi policy;
- giao dịch nằm trong thẩm quyền tự xử lý của Agent.

`AUTO_PROCESS` chỉ có nghĩa là hồ sơ đã qua bước review thường quy và có thể đi tiếp sang bước payment review. Nó **không** có nghĩa là Agent tự chuyển tiền.

### REQUEST_INFO

Dùng khi:
- thiếu dữ liệu;
- dữ liệu mâu thuẫn;
- chưa xác định được sự thật cần thiết để ra quyết định.

Agent phải tạo câu hỏi cụ thể và có thể trả lời trực tiếp.

Ví dụ:

> PO là 30M nhưng invoice là 35M. Có PO điều chỉnh hoặc phê duyệt tăng thêm 5M không?

### ESCALATE

Dùng khi:
- dữ liệu thực tế đã rõ;
- nhưng trường hợp nằm ngoài policy;
- hoặc quyết định vượt thẩm quyền của Agent.

Khi chuyển tiếp, hệ thống phải chỉ rõ lý do và người/role cần quyết định nếu policy xác định được.

---

## 5. Yêu cầu bắt buộc của Sprint 1

- Chọn một workflow thường quy cụ thể và có policy rõ ràng cho workflow đó.
- Có tối thiểu **15 test cases**.
- Test cases phải bao gồm:
  - trường hợp thường quy;
  - trường hợp chưa rõ thông tin;
  - trường hợp ngoài policy;
  - trường hợp vượt thẩm quyền.
- Các trường hợp thường quy phải được tự xử lý hoàn toàn.
- Không được chuyển tiếp tất cả trường hợp cho con người.
- Không được khẳng định kết quả khi input đã bị gắn cờ nghi vấn hoặc chưa đủ bằng chứng.
- Khi cần người xử lý, câu hỏi phải cụ thể và trực tiếp.
- Hệ thống phải xử lý được input mới chưa từng thấy.
- Không được hard-code quyết định theo test-case ID hoặc dữ liệu cố định.

---

## 6. Challenge A Verify

Challenge A yêu cầu **5 trường hợp kiểm thử chuyển tiếp** có thể chạy bằng một thao tác:

- 3 trường hợp thường quy → tự xử lý;
- 2 trường hợp cần con người tham gia.

Hai case cần con người **không bắt buộc cùng mang label `ESCALATE`**. Với decision model của InvoiceReferee, case thiếu fact dùng `REQUEST_INFO`; case outside-policy hoặc beyond-authority dùng `ESCALATE`. Cả hai đều là hành vi dừng tự động hóa để xin thông tin/quyết định từ con người theo tinh thần Challenge A.

Verify phải hiển thị rõ tối thiểu:

| Field | Ý nghĩa |
| --- | --- |
| Case | Tên / mã case |
| Expected | Kết quả mong đợi |
| Actual | Kết quả thực tế |
| Pass/Fail | So sánh Expected và Actual |
| Uncertainty | FACTUAL_UNKNOWN / OUTSIDE_POLICY / BEYOND_AUTHORITY nếu có |
| Question | Câu hỏi chuyển tiếp nếu có |
| Target | Người/role cần trả lời nếu xác định được |
| Timestamp | Thời điểm chạy |

Ngoài Challenge A Verify, bộ Verify chung của cuộc thi còn yêu cầu **4 core test cases** chạy bằng một thao tác và có ít nhất một trường hợp từ chối hoặc chuyển tiếp.

---

## 7. Giám khảo sẽ kiểm tra như thế nào

Trong vòng sơ loại, luồng đánh giá liên quan trực tiếp đến team gồm:

1. Mở **Live URL** và thử thao tác chính.
2. Chạy **Verify harness** bằng một thao tác.
3. Đưa vào **2 input mới** mà team chưa từng thấy.
4. Chạy bài kiểm tra nhanh của **Challenge A**.
5. Kiểm tra Agent có tự xử lý đúng các case thường quy và chuyển đúng các case cần con người hay không.
6. Kiểm tra chất lượng câu hỏi chuyển tiếp.
7. Chọn một hành động để xem **audit log**.
8. Thử chức năng **Stop / Override**.

Trong Challenge A, giám khảo còn có thể nhập một trường hợp không rõ ràng mới dựa trên policy do team công bố.

---

## 8. Deliverables bắt buộc

Team phải chuẩn bị đầy đủ:

- Live URL công khai, không yêu cầu login;
- Public repository với lịch sử commit đầy đủ;
- Verify harness;
- 4 core Verify cases;
- 5 Challenge A escalation cases;
- Runbook từ lúc clone repo sạch đến khi hệ thống chạy;
- đúng 5 slides;
- demo video dưới 3 phút;
- build log 1 trang;
- audit log trong sản phẩm;
- human Stop / Override.

---

## 9. Các điểm liên quan trực tiếp đến scoring

### 9.1. Khả năng vận hành

- Live URL phải chạy thực tế.
- Không yêu cầu giám khảo cài đặt hay đăng nhập.
- Verify phải chạy bằng một thao tác.
- Hệ thống phải xử lý hợp lý dữ liệu mới.

### 9.2. Human-in-the-loop và accountability

- Phải rõ Agent được quyền quyết gì và con người giữ quyền quyết gì.
- Decision boundary trên slide phải khớp với sản phẩm thực tế.
- Audit log phải truy xuất được:
  - hệ thống đã làm gì;
  - khi nào;
  - dựa trên dữ liệu nào;
  - vì sao.
- Người dùng phải Stop / Override được.
- Hệ thống phải giải thích quyết định theo cách người không chuyên kỹ thuật hiểu được.

### 9.3. Challenge A

- Phát hiện đúng case cần chuyển tiếp.
- Không chuyển nhầm các case thường quy.
- Phân loại đúng nguyên nhân không chắc chắn.
- Câu hỏi chuyển tiếp phải đủ cụ thể để người xử lý có thể quyết định trực tiếp.

---

## 10. Dữ liệu

- Dữ liệu synthetic / tự sinh được chấp nhận.
- Team phải công bố rõ phần nào là dữ liệu thật và phần nào là dữ liệu giả lập.
- Slide 4 phải thể hiện rõ sự phân biệt này.
- Hệ thống phải nhận được dữ liệu mới; không được chỉ hoạt động trên bộ dữ liệu cố định.

---

## 11. Non-goals của Sprint 1

Sprint 1 không cố xây dựng:

- full VAT / tax compliance engine;
- TNDN validation;
- tax filing;
- automatic accounting entries;
- fraud detection;
- mọi loại invoice;
- service-invoice workflow phức tạp;
- automatic payment;
- ERP / procurement system hoàn chỉnh.

Mục tiêu Sprint 1 là chứng minh rõ một khả năng:

> **InvoiceReferee tự xử lý các giao dịch mua hàng thường quy khi đủ bằng chứng và biết dừng đúng lúc khi thiếu thông tin, ngoài policy hoặc vượt thẩm quyền.**

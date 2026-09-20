# InvoiceReferee — Evaluation Plan

## 1. Mục tiêu

File này định nghĩa cách chứng minh InvoiceReferee hoạt động trên dữ liệu mới và cách thu thập bằng chứng người dùng thực tế mà không bịa dữ liệu hoặc feedback.

## 2. Sprint 1 — Evaluation kỹ thuật

### Ground truth

- 17 documented cases trong `TEST_CASES.md`.
- Core Verify: 4 case.
- Challenge A Verify: 5 case.
- Production code không được đọc expected labels.

### Unseen-input test

Tạo ít nhất 2 transaction mới không nằm trong fixtures:

1. một routine case với vendor/amount/quantity mới;
2. một abnormal case, ưu tiên factual-unknown hoặc beyond-authority.

Judge/user phải có thể paste hoặc upload JSON vào Streamlit và chạy qua cùng `review()` service.

### Metrics

Ghi tối thiểu:

- expected action vs actual action;
- uncertainty type;
- pass/fail;
- question có cụ thể hay không;
- timestamp.

## 3. Challenge A quality metrics

Khi có tập độc lập lớn hơn, theo dõi:

- **Missed human-intervention rate:** case đáng lẽ cần người nhưng hệ thống lại AUTO_PROCESS.
- **Unnecessary human-intervention rate:** routine case bị REQUEST_INFO/ESCALATE không cần thiết.
- **Routine auto-processing rate:** tỷ lệ routine case đi qua tự động.
- **Question answerability:** người nhận có thể trả lời câu hỏi ngay từ thông tin được nêu hay vẫn phải tự mở lại toàn bộ hồ sơ.

## 4. Sprint 2 — Real-user validation

Không điền tên hoặc quote giả. Chỉ cập nhật khi đã phỏng vấn/test thật.

| Slot | Target role | Evidence cần thu |
| --- | --- | --- |
| U1 | Kế toán thanh toán / Accounts Payable | chức danh, workflow hiện tại, quote nguyên văn, pain point |
| U2 | Purchasing / Procurement | chức danh, cách xử lý mismatch/approval, quote nguyên văn |
| U3 | Finance Manager hoặc người phê duyệt | authority boundary, escalation expectation, quote nguyên văn |

## 5. Before / After measurement

Chọn 5–10 transaction mẫu và đo cùng một nhiệm vụ:

**Before:** người dùng tự đọc PO + receipt + invoice + payment history và quyết định bước tiếp theo.

**After:** người dùng dùng InvoiceReferee rồi xác nhận/override kết quả.

Ghi:

- thời gian xử lý mỗi case;
- số mismatch bị bỏ sót;
- số lần phải mở lại chứng từ;
- số escalation không cần thiết;
- số quyết định Agent bị human override.

## 6. Product change from feedback

Mỗi feedback dùng để thay sản phẩm phải có:

- người/role đưa feedback;
- vấn đề họ gặp;
- thay đổi cụ thể;
- commit hoặc before/after evidence;
- tác động tích cực;
- ít nhất một bất cập hoặc trade-off phát sinh.

Không ghi “không có bất cập”. Nếu chưa quan sát được tác động tiêu cực, ghi rõ là **chưa đủ evidence** và tiếp tục test.

## 7. Evidence discipline

Phân biệt rõ:

- `SYNTHETIC`: policy/data tự sinh để prototype/evaluation;
- `REAL`: dữ liệu hoặc feedback thu từ người dùng thật;
- `UNVERIFIED`: giả thuyết chưa được xác nhận.

Không biến synthetic 50M authority threshold thành claim về policy thật của doanh nghiệp hoặc quy định pháp luật.

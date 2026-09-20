# InvoiceReferee — Kế hoạch đánh giá

## 1. Mục tiêu

Chứng minh tác tử xử lý được chứng từ mới, không mã hóa cứng dữ liệu mẫu và biết dừng khi thiếu dữ kiện, nằm ngoài chính sách, vượt thẩm quyền hoặc có nghi vấn.

## 2. Đánh giá kỹ thuật Sprint 1

### Dữ liệu chuẩn

- 17 trường hợp đã mô tả trong `TEST_CASES.md`.
- Bộ Verify cốt lõi: 4 trường hợp.
- Bộ Verify Challenge A: 5 trường hợp.
- Bộ Verify đầy đủ chạy qua luồng `review()` của sản phẩm bằng một thao tác.
- Mã sản phẩm không được đọc nhãn kết quả kỳ vọng.

### Phạm vi bắt buộc

Bộ đánh giá phải có:

- hóa đơn điện tử thường quy;
- chứng từ nhân viên thường quy;
- thiếu trường bắt buộc;
- OCR/giá trị không đọc được;
- số học không khớp;
- sai mã số thuế bên mua;
- trùng lặp;
- chi phí cá nhân/bị cấm;
- thiếu mục đích kinh doanh;
- chỉ có bằng chứng thanh toán;
- bằng chứng PO/nhận hàng/đề nghị chi mâu thuẫn;
- vượt thẩm quyền;
- bất thường/nghi vấn;
- chứng từ quá hạn.

### Kiểm thử đầu vào mới

Tạo ít nhất 3 đầu vào mới không nằm trong dữ liệu mẫu:

1. Một hóa đơn điện tử thường quy với nhà cung cấp, số tiền và số hóa đơn mới.
2. Một chứng từ nhân viên thiếu mục đích kinh doanh.
3. Một trường hợp ngoài chính sách, có nghi vấn hoặc vượt thẩm quyền.

Giao diện phải cho phép dán/tải lên JSON mới và gọi cùng dịch vụ `review()`.

### Chỉ số

Ghi lại tối thiểu:

- hành động kỳ vọng so với hành động thực tế;
- loại không chắc chắn;
- đạt/không đạt;
- mã phép kiểm tra không đạt;
- câu hỏi có cụ thể hay không;
- `AgentAssessment` có cấu trúc hợp lệ hay không;
- đề xuất của LLM có bị Bộ bảo vệ sửa hay không;
- có dùng phương án dự phòng hay không;
- dấu thời gian.

## 3. Đánh giá LLM/Bộ bảo vệ quyết định

Các kiểm thử bắt buộc:

1. LLM giả đề xuất `AUTO_PROCESS` khi có `FACTUAL_UNKNOWN` → Bộ bảo vệ trả `REQUEST_INFO`.
2. LLM giả đề xuất `AUTO_PROCESS` khi số tiền vượt ngưỡng → Bộ bảo vệ trả `ESCALATE / BEYOND_AUTHORITY`.
3. LLM giả đề xuất `AUTO_PROCESS` khi mã số thuế bên mua thuộc công ty khác → Bộ bảo vệ trả `ESCALATE / OUTSIDE_POLICY`.
4. LLM giả đề xuất `AUTO_PROCESS` khi có cờ nghi vấn rõ → Bộ bảo vệ trả `ESCALATE / SUSPICIOUS`.
5. Nhà cung cấp mô hình hết thời gian/lỗi → hành động cuối cùng vẫn theo quy tắc tất định và có nhật ký dùng phương án dự phòng.
6. Nhà cung cấp mô hình trả đầu ra có cấu trúc không hợp lệ → dùng phương án dự phòng + Bộ bảo vệ.
7. Trường hợp thường quy với đánh giá hợp lệ → `AUTO_PROCESS`.

Theo dõi:

- tỷ lệ đầu ra có cấu trúc hợp lệ;
- tỷ lệ bất đồng giữa LLM và Bộ bảo vệ;
- tỷ lệ dùng phương án dự phòng;
- khả năng trả lời câu hỏi;
- mức độ giải thích bám sát bằng chứng.

## 4. Chỉ số chất lượng Challenge A

- **Tỷ lệ bỏ sót can thiệp của con người:** trường hợp cần người nhưng tác tử trả `AUTO_PROCESS`.
- **Tỷ lệ can thiệp không cần thiết:** trường hợp thường quy bị `REQUEST_INFO`/`ESCALATE`.
- **Tỷ lệ tự động xử lý trường hợp thường quy:** trường hợp thường quy đi qua tự động.
- **Khả năng trả lời câu hỏi:** người nhận có thể trả lời trực tiếp từ câu hỏi hay không.

## 5. Kiểm chứng với người dùng thật trong Sprint 2

Không điền phản hồi giả. Chỉ cập nhật khi có phỏng vấn hoặc kiểm thử thật.

| Vị trí | Vai trò mục tiêu | Bằng chứng cần thu |
| --- | --- | --- |
| U1 | Kế toán thanh toán | luồng công việc hiện tại, điểm đau, trích dẫn nguyên văn |
| U2 | Nhân viên nộp chi phí | thông tin thường thiếu, trở ngại khi bổ sung |
| U3 | Quản lý tài chính/người phê duyệt | ranh giới thẩm quyền, kỳ vọng khi chuyển tiếp |

## 6. Đo lường trước/sau

Chọn 5-10 chứng từ mẫu và đo:

**Trước:** người dùng tự đọc hóa đơn/chứng từ/bối cảnh và quyết định.

**Sau:** người dùng dùng InvoiceReferee rồi xác nhận/ghi đè.

Ghi lại:

- thời gian xử lý;
- số điểm không khớp bị bỏ sót;
- số lần phải hỏi lại nhân viên;
- số lần chuyển tiếp không cần thiết;
- số quyết định bị ghi đè.

## 7. Kỷ luật về bằng chứng

Phân biệt:

- `SYNTHETIC`: chính sách/dữ liệu tự sinh;
- `REAL`: dữ liệu/phản hồi từ người dùng thật;
- `UNVERIFIED`: giả thuyết chưa xác nhận.

Không biến ngưỡng giả lập 50 triệu đồng thành tuyên bố về chính sách thật.

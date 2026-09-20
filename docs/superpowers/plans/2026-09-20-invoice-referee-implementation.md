# Kế hoạch triển khai InvoiceReferee Sprint 1

## Mục tiêu

Xây dựng MVP tác tử kế toán xuyên suốt để kiểm tra hóa đơn điện tử, hóa đơn/chứng từ của nhân viên và bằng chứng bổ sung; trả về `AUTO_PROCESS`, `REQUEST_INFO` hoặc `ESCALATE`, có khả năng kiểm toán và có bộ Verify chạy bằng một thao tác.

## Ràng buộc an toàn

- Các quyết định hiển thị cho người dùng gồm đúng `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`.
- Các loại không chắc chắn nội bộ gồm `FACTUAL_UNKNOWN`, `OUTSIDE_POLICY`, `BEYOND_AUTHORITY`, `SUSPICIOUS`.
- `AUTO_PROCESS` không bao giờ đồng nghĩa với thanh toán tự động.
- Thiếu dữ kiện được chuyển đến `REQUEST_INFO`, không phải `ESCALATE`.
- Trường hợp rõ ràng nằm ngoài chính sách, vượt thẩm quyền hoặc có nghi vấn được chuyển đến `ESCALATE`.
- Đầu ra LLM luôn được Bộ bảo vệ quyết định tất định kiểm tra.

## Cột mốc 1 — Miền nghiệp vụ và dữ liệu mẫu

- [ ] Triển khai các mô hình từ `docs/DATA_MODEL.md`.
- [ ] Tạo danh mục dữ liệu mẫu cho TC01-TC17.
- [ ] Bao gồm ví dụ về hóa đơn điện tử, chứng từ nhân viên, bằng chứng thanh toán, đề nghị chi và bằng chứng bổ sung.
- [ ] Đánh dấu rõ các giá trị chính sách giả lập.

## Cột mốc 2 — Tiếp nhận và chuẩn hóa dữ liệu

- [ ] Triển khai bộ chuyển đổi JSON làm đường cơ sở bắt buộc.
- [ ] Thêm giao diện bộ chuyển đổi dễ mở rộng cho XML/PDF/OCR.
- [ ] Chuẩn hóa tiền, ngày, loại chứng từ và các dòng hàng.
- [ ] Giữ lại cảnh báo trích xuất và tham chiếu nguồn.

## Cột mốc 3 — Bộ tạo `ReviewCase`

- [ ] Tạo `ReviewCase` từ chứng từ chuẩn, đề nghị chi, hồ sơ công ty và bằng chứng bổ sung.
- [ ] Liên kết bằng chứng bằng mã định danh rõ ràng khi có.
- [ ] Giữ các liên kết chưa giải quyết dưới dạng chưa xác định được dữ kiện.

## Cột mốc 4 — Các phép kiểm tra tất định

- [ ] Trường bắt buộc.
- [ ] Chất lượng trích xuất.
- [ ] Danh tính bên mua/công ty.
- [ ] Danh tính bên bán/nhà cung cấp.
- [ ] Ngày/thời hạn nộp.
- [ ] Số học và số tiền bằng chữ.
- [ ] Trùng lặp.
- [ ] Bối cảnh kinh doanh.
- [ ] Tính nhất quán giữa đề nghị chi/thanh toán/bằng chứng.
- [ ] Bằng chứng nhận hàng/dịch vụ khi được yêu cầu.
- [ ] Danh mục chính sách.
- [ ] Trạng thái thanh toán.
- [ ] Ngưỡng thẩm quyền.
- [ ] Bất thường/nghi vấn.
- [ ] Mức độ sẵn sàng để xuất dữ liệu kế toán.

## Cột mốc 5 — Chính sách và Bộ bảo vệ quyết định

- [ ] Triển khai các quy tắc từ `docs/POLICY.md`.
- [ ] Tạo `PolicyContext`.
- [ ] Bắt buộc ánh xạ:

```text
FACTUAL_UNKNOWN  → REQUEST_INFO
OUTSIDE_POLICY   → ESCALATE
BEYOND_AUTHORITY → ESCALATE
SUSPICIOUS       → ESCALATE
tất cả đều đạt   → AUTO_PROCESS
```

- [ ] Thêm kiểm thử trong đó LLM giả đề xuất `AUTO_PROCESS` không an toàn.

## Cột mốc 6 — Tác tử LLM và phương án dự phòng

- [ ] Tạo lược đồ `AgentAssessment` có cấu trúc.
- [ ] Chỉ đưa dữ kiện/phép kiểm tra/chính sách có cấu trúc vào lời nhắc LLM.
- [ ] Kiểm tra tính hợp lệ của đầu ra.
- [ ] Thêm câu hỏi dự phòng tất định.
- [ ] Ghi nhật ký việc sử dụng phương án dự phòng.

## Cột mốc 7 — Dịch vụ kiểm tra, kiểm toán và giao diện

- [ ] Triển khai một bộ điều phối `review()` duy nhất.
- [ ] Ghi nối tiếp sự kiện kiểm toán cho trích xuất, phép kiểm tra, LLM, Bộ bảo vệ và quyết định.
- [ ] Triển khai điều khiển Dừng/Ghi đè.
- [ ] Giao diện Streamlit hỗ trợ chọn mẫu và dán/tải lên JSON.

## Cột mốc 8 — Verify

- [ ] Chạy toàn bộ TC01-TC17 qua `review()` của sản phẩm.
- [ ] Triển khai bộ Verify cốt lõi.
- [ ] Triển khai bộ Verify Challenge A.
- [ ] Triển khai `python -m verify.harness --suite all`.
- [ ] Hiển thị kết quả kỳ vọng, thực tế, đạt/không đạt, loại không chắc chắn, câu hỏi, đối tượng và dấu thời gian.

## Tiêu chí hoàn thành

- Cả 17 trường hợp đã mô tả đều có hành vi đúng kỳ vọng.
- Kiểm thử ít nhất 3 đầu vào mới.
- Giao diện và Verify dùng cùng luồng `review()`.
- Nhật ký kiểm toán hiển thị bằng chứng, quy tắc và lý do.
- Dừng/Ghi đè hoạt động.

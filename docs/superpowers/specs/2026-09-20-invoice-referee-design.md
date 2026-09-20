# Thiết kế InvoiceReferee Sprint 1

## 1. Mục tiêu

Xây dựng một tác tử kế toán hoạt động được để kiểm tra hóa đơn điện tử, hóa đơn/chứng từ của nhân viên và bằng chứng bổ sung. Tác tử phải tự động xử lý trường hợp thường quy và dừng đúng ranh giới khi thiếu dữ kiện, vi phạm chính sách, vượt thẩm quyền hoặc có nghi vấn.

## 2. Quy trình được hỗ trợ

```text
Chứng từ/bằng chứng thô
  → trích xuất
  → ánh xạ chứng từ chuẩn
  → hồ sơ kiểm tra
  → phép kiểm tra tất định
  → bối cảnh chính sách
  → đánh giá của LLM
  → Bộ bảo vệ quyết định tất định
  → AUTO_PROCESS / REQUEST_INFO / ESCALATE
```

Đầu vào được hỗ trợ trong Sprint 1:

- XML/PDF/văn bản/ảnh/JSON của hóa đơn điện tử;
- ảnh hóa đơn/chứng từ của nhân viên hoặc dữ liệu JSON đã trích xuất;
- bằng chứng thanh toán;
- đề nghị chi của nhân viên;
- PO/biên bản nhận hàng/nghiệm thu dịch vụ dưới dạng bằng chứng bổ sung không bắt buộc.

## 3. Mô hình quyết định

Các hành động hiển thị cho người dùng gồm đúng ba loại:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

Ánh xạ loại không chắc chắn nội bộ:

```text
FACTUAL_UNKNOWN  → REQUEST_INFO
OUTSIDE_POLICY   → ESCALATE
BEYOND_AUTHORITY → ESCALATE
SUSPICIOUS       → ESCALATE
```

## 4. Các phép kiểm tra cốt lõi

- trường bắt buộc theo loại chứng từ;
- chất lượng trích xuất;
- danh tính bên mua/công ty;
- danh tính bên bán/nhà cung cấp;
- ngày/thời hạn nộp;
- số học trên dòng và số tiền bằng chữ;
- phát hiện trùng lặp;
- bối cảnh kinh doanh;
- tính nhất quán giữa chứng từ/đề nghị chi/thanh toán/bằng chứng bổ sung;
- bằng chứng nhận hàng/dịch vụ khi được yêu cầu;
- danh mục chính sách;
- trạng thái thanh toán;
- ngưỡng thẩm quyền;
- cờ bất thường/nghi vấn;
- mức độ sẵn sàng để xuất dữ liệu kế toán.

## 5. Hợp đồng dữ liệu

Dùng `DATA_MODEL.md` làm nguồn sự thật duy nhất:

- `ExtractedDocument`
- `CanonicalDocument`
- `EmployeeClaim`
- `SupportingEvidence`
- `ReviewCase`
- `CheckResult`
- `PolicyContext`
- `AgentAssessment`
- `Decision`
- `ReviewResult`
- `AuditEvent`

## 6. Ranh giới của LLM

LLM nằm trong luồng kiểm tra thông thường nhưng chỉ suy luận trên dữ kiện có cấu trúc. Mã tất định chịu trách nhiệm về số học, tra cứu trùng lặp, trạng thái thanh toán, quy tắc ngày, ánh xạ chính sách và ngưỡng thẩm quyền. Bộ bảo vệ quyết định kiểm tra mọi đề xuất của LLM.

## 7. Đánh giá

Dữ liệu chuẩn nằm trong `docs/TEST_CASES.md`:

- 17 trường hợp đã mô tả;
- tối thiểu 15 trường hợp theo yêu cầu sản phẩm;
- bộ Verify Challenge A gồm 3 trường hợp thường quy, 1 trường hợp chưa xác định dữ kiện và 1 trường hợp chuyển tiếp;
- bộ Verify cốt lõi gồm các trường hợp đại diện cho `AUTO_PROCESS`, `REQUEST_INFO` và `ESCALATE`.

## 8. Ngoài phạm vi

- tuân thủ thuế/GTGT/TNDN đầy đủ;
- kê khai thuế;
- bút toán kế toán tự động;
- thanh toán tự động;
- thay thế ERP;
- OCR cấp độ sản xuất;
- bộ máy phát hiện gian lận đầy đủ.

# InvoiceReferee — Tóm tắt thử thách

## 1. Thử thách đã chọn

**Challenge A — Bộ điều phối chuyển tiếp**

Mục tiêu cốt lõi: hệ thống tự xử lý trường hợp thường quy và biết dừng đúng lúc để hỏi hoặc chuyển cho con người.

InvoiceReferee không được:

- chuyển mọi trường hợp cho con người;
- tự xử lý khi dữ liệu còn thiếu, sai chính sách, vượt quyền hoặc có nghi vấn.

## 2. Quy trình nhóm lựa chọn

Nhóm chọn quy trình kế toán chi phí:

```text
Hóa đơn / Chứng từ / Bằng chứng thanh toán
      +
Đề nghị chi của nhân viên / Bằng chứng bổ sung
      ↓
Tác tử kế toán kiểm tra
      ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
      ↓
Chuẩn bị bút toán / Kiểm tra thanh toán / Con người quyết định
```

Sprint 1 bao phủ:

- hóa đơn điện tử;
- hóa đơn/chứng từ do nhân viên chụp;
- bằng chứng thanh toán;
- PO/biên bản nhận hàng/nghiệm thu dịch vụ như bằng chứng bổ sung khi có.

## 3. Các nhóm tình huống bắt buộc

### 3.1. Chưa xác định được dữ kiện

Dữ liệu bị thiếu, không đọc được, mâu thuẫn hoặc chưa đủ bối cảnh kinh doanh.

Kết quả:

```text
REQUEST_INFO
```

Ví dụ: chứng từ có số tiền nhưng thiếu mục đích kinh doanh/dự án.

### 3.2. Ngoài chính sách

Dữ kiện đã rõ nhưng vi phạm hoặc nằm ngoài chính sách.

Kết quả:

```text
ESCALATE
```

Ví dụ: mã số thuế bên mua thuộc công ty khác, trùng lặp rõ ràng, chi phí cá nhân hoặc chứng từ quá hạn.

### 3.3. Vượt thẩm quyền

Dữ kiện đầy đủ và có thể hợp lệ, nhưng số tiền/loại chi vượt quyền của tác tử.

Kết quả:

```text
ESCALATE
```

### 3.4. Nghi vấn

Dữ kiện đọc được nhưng có dấu hiệu bất thường/nghi vấn cần con người kiểm tra.

Kết quả:

```text
ESCALATE
```

## 4. Ba hành động hiển thị cho người dùng

### `AUTO_PROCESS`

Dùng khi bằng chứng đầy đủ, trường bắt buộc hợp lệ, bối cảnh kinh doanh rõ, đúng chính sách, không trùng lặp, không có nghi vấn và trong thẩm quyền.

### `REQUEST_INFO`

Dùng khi chưa biết đủ dữ kiện để quyết định. Tác tử phải hỏi câu cụ thể.

### `ESCALATE`

Dùng khi dữ kiện đã rõ nhưng nằm ngoài chính sách, vượt thẩm quyền hoặc có nghi vấn. Tác tử phải nêu lý do, loại không chắc chắn và đối tượng xử lý nếu chính sách xác định được.

## 5. Yêu cầu tối thiểu của Sprint 1

- Có ít nhất 15 trường hợp kiểm thử.
- Bao gồm trường hợp thường quy, chưa xác định dữ kiện, ngoài chính sách, vượt thẩm quyền và nghi vấn.
- Trường hợp thường quy phải được tự động xử lý.
- Không mã hóa cứng theo mã trường hợp.
- Đầu vào mới phải được xử lý qua cùng luồng của sản phẩm.
- Khi cần con người, câu hỏi phải cụ thể và truy vết được bằng chứng.
- Có nhật ký kiểm toán và thao tác Dừng/Ghi đè của con người.

## 6. Bộ Verify Challenge A

Verify gồm 5 trường hợp:

- 3 trường hợp thường quy → `AUTO_PROCESS`;
- 1 trường hợp chưa xác định dữ kiện → `REQUEST_INFO`;
- 1 trường hợp cần con người quyết định → `ESCALATE`.

Verify phải hiển thị:

| Trường | Ý nghĩa |
| --- | --- |
| Case | Mã trường hợp |
| Expected | Hành động kỳ vọng |
| Actual | Hành động thực tế |
| Pass/Fail | Kết quả so sánh |
| Uncertainty | FACTUAL_UNKNOWN / OUTSIDE_POLICY / BEYOND_AUTHORITY / SUSPICIOUS |
| Question | Câu hỏi bổ sung |
| Target | Vai trò/người cần trả lời |
| Timestamp | Thời gian chạy |

## 7. Luồng đánh giá của giám khảo

Giám khảo có thể:

1. Mở đường dẫn trực tuyến.
2. Chạy Verify bằng một thao tác.
3. Dán/tải lên JSON chưa từng thấy.
4. Xem trường hợp thường quy, yêu cầu bổ sung và chuyển tiếp.
5. Kiểm tra câu hỏi.
6. Xem nhật ký kiểm toán.
7. Thử Dừng/Ghi đè.

## 8. Sản phẩm bàn giao

- đường dẫn trực tuyến;
- kho mã nguồn công khai;
- bộ Verify;
- các trường hợp Verify cốt lõi;
- các trường hợp Verify Challenge A;
- hướng dẫn vận hành;
- 5 trang trình bày;
- video trình diễn dưới 3 phút;
- nhật ký phát triển;
- nhật ký kiểm toán trong sản phẩm;
- Dừng/Ghi đè.

## 9. Ngoài phạm vi

- tuân thủ thuế GTGT/TNDN đầy đủ;
- kê khai thuế;
- thanh toán tự động;
- thay thế ERP;
- OCR cấp độ sản xuất;
- bộ máy phát hiện gian lận đầy đủ.

Mục tiêu Sprint 1:

> InvoiceReferee tự xử lý chứng từ chi phí thường quy khi đủ bằng chứng và biết dừng đúng lúc khi thiếu thông tin, ngoài chính sách, vượt thẩm quyền hoặc có nghi vấn.

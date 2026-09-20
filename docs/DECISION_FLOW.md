# InvoiceReferee — Luồng quyết định

## 1. Mục đích

Tài liệu này mô tả cách InvoiceReferee đi từ đầu vào chứng từ đến quyết định cuối cùng cho hóa đơn điện tử, hóa đơn/chứng từ do nhân viên chụp và bằng chứng bổ sung.

```text
Đầu vào thô
  ↓
Trích xuất
  ↓
Chuẩn hóa thành CanonicalDocument
  ↓
Tạo ReviewCase
  ↓
Kiểm tra dữ kiện/bối cảnh bắt buộc
  ↓
Chạy các phép kiểm tra tất định
  ↓
Tạo PolicyContext
  ↓
Đánh giá của tác tử LLM
  ↓
Bộ bảo vệ quyết định tất định
  ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
  ↓
Kiểm toán + Kiểm soát của con người
```

## 2. Nguyên tắc quyết định

1. Không suy đoán dữ kiện.
2. Không dùng LLM để thay thế phép kiểm tra tất định.
3. Không `AUTO_PROCESS` khi thiếu hoặc chưa chắc chắn về dữ kiện quan trọng.
4. Không `ESCALATE` nếu chỉ thiếu dữ kiện có thể hỏi bổ sung.
5. Con người luôn có quyền Dừng/Ghi đè.

## 3. Bước 1 — Nhận đầu vào

Đầu vào có thể gồm:

- XML/PDF/văn bản/ảnh/JSON của hóa đơn điện tử;
- ảnh hóa đơn/chứng từ của nhân viên;
- bằng chứng thanh toán;
- đề nghị chi của nhân viên;
- PO/biên bản nhận hàng/nghiệm thu dịch vụ;
- lịch sử thanh toán;
- hồ sơ công ty/chính sách.

Đầu vào kỹ thuật sai định dạng trả về `INPUT_ERROR`. Thiếu bằng chứng nghiệp vụ vẫn là đầu vào hợp lệ và được đưa qua bộ máy quyết định.

## 4. Bước 2 — Trích xuất

Bộ chuyển đổi trích xuất chỉ đọc và ánh xạ trường:

```text
Nguồn thô → ExtractedDocument(fields, warnings, confidence)
```

Bộ chuyển đổi không được kết luận về chính sách, trùng lặp, tính hợp lệ của số tiền hoặc hành động cuối cùng. Trường không đọc được phải là `null` hoặc có cảnh báo.

## 5. Bước 3 — Chuẩn hóa

Chuẩn hóa về `CanonicalDocument`:

- tiền thành số nguyên VND;
- ngày thành `YYYY-MM-DD`;
- loại chứng từ thành enum;
- các dòng hàng thành danh sách chung;
- giữ lại tham chiếu nguồn và cảnh báo.

Nếu loại chứng từ chưa rõ:

```text
REQUEST_INFO
```

## 6. Bước 4 — Tạo `ReviewCase`

Gộp chứng từ và bằng chứng bổ sung thành một `ReviewCase`:

```text
Hóa đơn điện tử / chứng từ / bằng chứng thanh toán
    + đề nghị chi của nhân viên
    + PO / nhận hàng / nghiệm thu / lịch sử thanh toán
    + hồ sơ công ty / chính sách
        ↓
ReviewCase
```

Nếu không thể xác định chứng từ/bằng chứng nào liên quan đến hồ sơ:

```text
REQUEST_INFO
```

## 7. Bước 5 — Kiểm tra dữ kiện bắt buộc

Kiểm tra theo loại chứng từ:

- hóa đơn điện tử cần tên và mã số thuế bên mua/bên bán, ngày, số hóa đơn, mẫu số/ký hiệu, hàng hóa/dịch vụ và tổng tiền;
- chứng từ nhân viên cần ngày, số tiền, cửa hàng nếu nhìn thấy, phương thức thanh toán/hàng hóa nếu nhìn thấy;
- đề nghị chi của nhân viên cần người chi, mục đích, khách hàng/dự án khi cần;
- bằng chứng thanh toán cần số tiền, ngày, người trả/người nhận/mã tham chiếu nếu cần đối chiếu.

Cảnh báo trích xuất nghiêm trọng, ảnh mờ hoặc trường bị che:

```text
REQUEST_INFO
```

## 8. Bước 6 — Chạy phép kiểm tra tất định

Các phép kiểm tra cốt lõi:

```text
1. Độ đầy đủ của trường bắt buộc
2. Chất lượng trích xuất
3. Danh tính bên mua/công ty
4. Danh tính bên bán/nhà cung cấp
5. Ngày/thời hạn nộp
6. Số học trên dòng và số tiền bằng chữ
7. Phát hiện trùng lặp
8. Bối cảnh kinh doanh
9. Tính nhất quán giữa chứng từ/đề nghị chi/thanh toán/bằng chứng
10. Bằng chứng nhận hàng/dịch vụ
11. Danh mục chính sách
12. Trạng thái thanh toán
13. Ngưỡng thẩm quyền
14. Bất thường/nghi vấn
15. Mức độ sẵn sàng để xuất dữ liệu kế toán
```

Bộ máy kiểm tra trả về `CheckResult[]`, không tự tạo quyết định cuối cùng.

## 9. Bước 7 — Tạo `PolicyContext`

Bộ máy chính sách tạo:

- `scope_status`: `UNKNOWN`, `OUTSIDE_POLICY`, `IN_SCOPE`;
- mã các quy tắc áp dụng;
- ngưỡng thẩm quyền;
- các điểm không chắc chắn tất định;
- cờ nghi vấn.

`UNKNOWN` là thiếu dữ kiện → `REQUEST_INFO`. `OUTSIDE_POLICY` là dữ kiện đã rõ → `ESCALATE`.

## 10. Bước 8 — Đánh giá của tác tử LLM

LLM nhận:

```text
ReviewCase + CheckResult[] + PolicyContext
```

LLM trả về `AgentAssessment` có cấu trúc: hành động đề xuất, loại không chắc chắn, giải thích, câu hỏi, đối tượng và tham chiếu bằng chứng. LLM có thể giúp chọn vấn đề quan trọng nhất khi nhiều phép kiểm tra không đạt hoặc chưa xác định, nhưng không được sửa dữ kiện.

Nếu LLM lỗi, hết thời gian hoặc đầu ra không hợp lệ, dùng câu hỏi dự phòng tất định và ghi sự kiện `LLM_FALLBACK_USED`.

## 11. Bước 9 — Bộ bảo vệ quyết định

Bộ bảo vệ thực thi thứ tự ưu tiên:

```text
Đầu vào kỹ thuật lỗi?
  → INPUT_ERROR

Không xác định được loại hồ sơ/chứng từ?
  → REQUEST_INFO

Dữ kiện bắt buộc bị thiếu/không đọc được/mâu thuẫn?
  → REQUEST_INFO

Vi phạm ngoài chính sách đã rõ?
  → ESCALATE / OUTSIDE_POLICY

Cờ nghi vấn đủ rõ để con người kiểm tra?
  → ESCALATE / SUSPICIOUS

Số tiền/loại chi vượt thẩm quyền?
  → ESCALATE / BEYOND_AUTHORITY

Tất cả phép kiểm tra bắt buộc đều đạt?
  → AUTO_PROCESS

Trường hợp còn lại
  → REQUEST_INFO
```

Bộ bảo vệ phải từ chối đề xuất của LLM nếu trái chính sách.

## 12. Ví dụ luồng

### Hóa đơn điện tử thường quy

```text
Đọc được hóa đơn điện tử
  ↓
Đủ trường bắt buộc
  ↓
Mã số thuế bên mua khớp công ty
  ↓
Số học + trùng lặp + chính sách + thẩm quyền đều đạt
  ↓
AUTO_PROCESS
```

### Thiếu trường/OCR không đọc được

```text
Tổng tiền không chắc là 45 hay 48 triệu đồng
  ↓
CHECK_EXTRACTION_QUALITY = UNKNOWN
  ↓
FACTUAL_UNKNOWN
  ↓
REQUEST_INFO
```

### Chứng từ nhân viên thiếu mục đích

```text
Chứng từ có ngày + số tiền
Đề nghị chi thiếu mục đích kinh doanh/dự án
  ↓
CHECK_BUSINESS_CONTEXT = FAIL
  ↓
REQUEST_INFO
```

### Mã số thuế bên mua thuộc công ty khác

```text
Mã số thuế bên mua tồn tại và đọc rõ
Mã số thuế bên mua != mã số thuế công ty
  ↓
OUTSIDE_POLICY
  ↓
ESCALATE
```

### Vượt thẩm quyền

```text
Mọi dữ kiện/phép kiểm tra đều đạt
Số tiền = 120 triệu đồng
Ngưỡng = 50 triệu đồng
  ↓
BEYOND_AUTHORITY
  ↓
ESCALATE → Quản lý tài chính
```

### Bất thường/nghi vấn

```text
Chứng từ đọc được và đầy đủ
Mẫu hành vi: cùng nhân viên nộp 5 chứng từ tương tự trong 10 phút
  ↓
SUSPICIOUS
  ↓
ESCALATE → Quản lý tài chính / Kiểm soát nội bộ
```

## 13. Đánh giá lại

`REQUEST_INFO` không phải điểm kết thúc. Khi có bằng chứng mới:

```text
Đính kèm bằng chứng mới
  ↓
Chuẩn hóa
  ↓
Chạy lại các phép kiểm tra bị ảnh hưởng
  ↓
Chạy lại Bộ bảo vệ
  ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
```

Quyết định cũ vẫn được giữ trong nhật ký kiểm toán.

## 14. Hợp đồng đầu ra cuối cùng

Mỗi lượt kiểm tra hợp lệ phải có:

- hành động;
- lý do;
- mã quy tắc chính sách;
- dấu thời gian;
- câu hỏi nếu là `REQUEST_INFO` hoặc `ESCALATE`;
- đối tượng nếu chính sách xác định được.

Nguyên tắc cuối cùng:

> Chưa biết thì hỏi. Biết rõ nhưng sai chính sách, vượt quyền hoặc có nghi vấn thì chuyển. Chỉ tự động xử lý khi bằng chứng đầy đủ, chính sách rõ ràng và thẩm quyền cho phép.

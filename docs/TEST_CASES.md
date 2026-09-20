# InvoiceReferee — Các trường hợp kiểm thử

## 1. Mục đích

Tài liệu này là dữ liệu chuẩn của Sprint 1 cho tác tử kế toán. Việc triển khai được coi là đúng khi cùng một chính sách xử lý được các trường hợp dưới đây và các đầu vào mới tương tự mà không mã hóa cứng theo mã trường hợp.

## 2. Nhãn quyết định

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

`ESCALATE` phải kèm `uncertainty.type`: `OUTSIDE_POLICY`, `BEYOND_AUTHORITY` hoặc `SUSPICIOUS`.

## 3. Tối thiểu 17 trường hợp kiểm thử

| Mã | Tình huống | Dữ kiện chính | Kết quả kỳ vọng | Quy tắc |
| --- | --- | --- | --- | --- |
| TC01 | Hóa đơn điện tử thường quy | Đủ mã số thuế bên mua/bán, số/mẫu số/ký hiệu/ngày hóa đơn, hàng hóa, số tiền 30 triệu; bên mua là công ty mình; chưa thanh toán | AUTO_PROCESS | P01-P15 đạt |
| TC02 | Chứng từ ăn uống thường quy của nhân viên | Hóa đơn nhà hàng 1,2 triệu có ngày, cửa hàng, nhân viên, khách hàng/dự án, mục đích kinh doanh; bằng chứng thanh toán khớp | AUTO_PROCESS | P08, P09 đạt |
| TC03 | Mua hàng nhỏ lẻ thường quy | Hóa đơn văn phòng phẩm 800 nghìn có ngày, hàng hóa, mục đích, nhân viên; không trùng lặp và còn hạn | AUTO_PROCESS | P01, P08, P15 đạt |
| TC04 | Thiếu trường bắt buộc của hóa đơn điện tử | Hóa đơn điện tử thiếu ký hiệu hoặc số hóa đơn | REQUEST_INFO | P01 |
| TC05 | OCR không đọc được số tiền | Ảnh hóa đơn mờ, tổng tiền không chắc là 45 hay 48 triệu | REQUEST_INFO | P02 |
| TC06 | Số học không khớp | Số lượng 10 × đơn giá 3 triệu nhưng thành tiền/tổng tiền là 35 triệu | REQUEST_INFO | P05 |
| TC07 | Số tiền bằng chữ không khớp | Số tiền bằng số là 30 triệu, bằng chữ tương ứng 35 triệu | REQUEST_INFO | P05 |
| TC08 | Thiếu mã số thuế bên mua | Bên mua ghi “khách lẻ” hoặc để trống mã số thuế | REQUEST_INFO | P03 |
| TC09 | Mã số thuế bên mua thuộc công ty khác | Mã số thuế bên mua đọc rõ nhưng khác hồ sơ công ty | ESCALATE / OUTSIDE_POLICY | P03 |
| TC10 | Hóa đơn điện tử trùng lặp | Cùng mã số thuế bên bán + ký hiệu + số hóa đơn đã xử lý | ESCALATE / OUTSIDE_POLICY | P06 |
| TC11 | Chi phí cá nhân/bị cấm | Chứng từ cho chi phí cá nhân hoặc rượu bia bị cấm theo chính sách; dữ kiện rõ | ESCALATE / OUTSIDE_POLICY | P11 |
| TC12 | Thiếu mục đích kinh doanh | Chứng từ nhân viên có số tiền/ngày nhưng đề nghị chi thiếu mục đích/dự án | REQUEST_INFO | P08 |
| TC13 | Chỉ có bằng chứng thanh toán | Chỉ có ảnh chuyển khoản 5 triệu, chưa rõ hàng hóa/dịch vụ, mục đích hoặc hóa đơn | REQUEST_INFO | P08, P09 |
| TC14 | Bằng chứng mâu thuẫn | PO/đề nghị ghi 10 máy tính, biên bản nhận hàng ghi 8 máy | REQUEST_INFO | P09, P10 |
| TC15 | Vượt thẩm quyền | Hóa đơn hợp lệ 120 triệu, ngưỡng 50 triệu | ESCALATE / BEYOND_AUTHORITY | P13 |
| TC16 | Mẫu hành vi đáng ngờ | Cùng nhân viên nộp 5 chứng từ giống nhau trong 10 phút | ESCALATE / SUSPICIOUS | P14 |
| TC17 | Chứng từ quá hạn | Ngày chứng từ rõ, nộp sau 45 ngày trong khi chính sách cho phép 30 ngày | ESCALATE / OUTSIDE_POLICY | P12 |

## 4. Câu hỏi kỳ vọng

### TC04 — Thiếu trường bắt buộc của hóa đơn điện tử

> Hóa đơn đang thiếu số hóa đơn, ký hiệu hoặc mẫu số bắt buộc. Giá trị chính xác trên hóa đơn là gì?

### TC05 — OCR không đọc được số tiền

> Số tiền trên hóa đơn chưa đọc chắc chắn là 45 triệu hay 48 triệu đồng. Giá trị chính xác là bao nhiêu?

### TC06 — Số học không khớp

> Hóa đơn ghi số lượng 10 và đơn giá 3 triệu đồng, nhưng thành tiền là 35 triệu đồng. Số lượng, đơn giá hay thành tiền nào là giá trị đúng?

### TC07 — Số tiền bằng chữ không khớp

> Số tiền bằng số là 30 triệu đồng nhưng số tiền bằng chữ tương ứng 35 triệu đồng. Giá trị nào là giá trị đúng trên hóa đơn?

### TC08 — Thiếu mã số thuế bên mua

> Hóa đơn đang ghi “khách lẻ” hoặc thiếu mã số thuế bên mua. Chứng từ này có phải chi phí của công ty mình không, và mã số thuế bên mua đúng là gì?

### TC09 — Mã số thuế bên mua thuộc công ty khác

> Mã số thuế bên mua trên hóa đơn thuộc công ty khác, không phải công ty mình. Kế toán hoặc người phụ trách thuế có chấp nhận xử lý chứng từ này không?

### TC10 — Trùng lặp

> Hóa đơn này trùng mã số thuế bên bán, ký hiệu và số hóa đơn với chứng từ đã xử lý. Đây là bản gửi lại hay có lý do hợp lệ để tiếp tục xử lý?

### TC11 — Chi phí bị cấm/cá nhân

> Khoản chi thuộc danh mục không được phép theo chính sách. Người phụ trách tài chính có quyết định ngoại lệ cho khoản chi này không?

### TC12 — Thiếu mục đích kinh doanh

> Chứng từ 1,2 triệu đồng này phục vụ mục đích kinh doanh nào và gắn với khách hàng/dự án nào?

### TC13 — Chỉ có bằng chứng thanh toán

> Ảnh chuyển khoản 5 triệu đồng chưa có hóa đơn, hàng hóa/dịch vụ hoặc mục đích kinh doanh. Khoản chi này thanh toán cho hàng hóa/dịch vụ nào và phục vụ mục đích gì?

### TC14 — Bằng chứng mâu thuẫn

> PO/đề nghị ghi 10 máy tính nhưng bằng chứng nhận hàng chỉ ghi 8 máy. Số lượng thực nhận để xử lý là bao nhiêu?

### TC15 — Vượt thẩm quyền

> Giao dịch 120 triệu đồng vượt ngưỡng tự xử lý 50 triệu đồng. Quản lý tài chính có phê duyệt giao dịch này không?

### TC16 — Mẫu hành vi đáng ngờ

> Cùng một nhân viên nộp 5 chứng từ gần giống nhau trong 10 phút. Bộ phận tài chính/kiểm soát nội bộ có cần kiểm tra thủ công mẫu hành vi này không?

### TC17 — Chứng từ quá hạn

> Chứng từ được nộp sau 45 ngày, vượt chính sách 30 ngày. Người phụ trách tài chính có chấp nhận ngoại lệ cho chứng từ quá hạn này không?

## 5. Bộ Verify Challenge A — 5 trường hợp

| Mã Verify | Trường hợp nguồn | Kết quả kỳ vọng | Nhóm |
| --- | --- | --- | --- |
| EV01 | TC01 | AUTO_PROCESS | Hóa đơn điện tử thường quy |
| EV02 | TC02 | AUTO_PROCESS | Chứng từ nhân viên thường quy |
| EV03 | TC03 | AUTO_PROCESS | Mua hàng nhỏ lẻ thường quy |
| EV04 | TC06 | REQUEST_INFO | Chưa xác định được dữ kiện |
| EV05 | TC15 | ESCALATE | Vượt thẩm quyền |

## 6. Bộ Verify cốt lõi — 4 trường hợp

| Mã Verify | Trường hợp nguồn | Kết quả kỳ vọng |
| --- | --- | --- |
| CV01 | TC01 | AUTO_PROCESS |
| CV02 | TC06 | REQUEST_INFO |
| CV03 | TC10 | ESCALATE |
| CV04 | TC11 | ESCALATE |

Verify phải hiển thị:

- mã trường hợp;
- kết quả kỳ vọng;
- kết quả thực tế;
- đạt/không đạt;
- loại không chắc chắn nếu có;
- câu hỏi nếu có;
- đối tượng nếu có;
- dấu thời gian.

## 7. Nguyên tắc với đầu vào mới

Giám khảo có thể đổi nhà cung cấp, số tiền, số lượng, loại chi phí, nhân viên, dự án, loại chứng từ, số hóa đơn hoặc ngưỡng. Logic phải dựa trên trường dữ liệu và chính sách, không dựa trên mã dữ liệu mẫu.

Ví dụ đầu vào thường quy mới:

```text
Chứng từ nhân viên = 950 nghìn đồng
Ngày hợp lệ
Có mục đích/dự án
Bằng chứng thanh toán khớp
Không trùng lặp
```

Kết quả kỳ vọng:

```text
AUTO_PROCESS
```

Ví dụ đầu vào không rõ ràng mới:

```text
Hóa đơn điện tử có tổng tiền nhưng không đọc được mã số thuế bên mua
```

Kết quả kỳ vọng:

```text
REQUEST_INFO
```

Ví dụ đầu vào vượt thẩm quyền mới:

```text
Hóa đơn điện tử hợp lệ, số tiền 75 triệu đồng, ngưỡng 50 triệu đồng
```

Kết quả kỳ vọng:

```text
ESCALATE / BEYOND_AUTHORITY
```

## 8. Quy tắc dữ liệu mẫu

Mỗi trường hợp nên được lưu dưới dạng một tệp đầu vào JSON riêng:

```text
tests/fixtures/TC01.json
...
tests/fixtures/TC17.json
```

Mã sản phẩm không được đọc kết quả kỳ vọng.

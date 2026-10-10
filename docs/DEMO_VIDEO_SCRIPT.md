# Kịch Bản Video Demo InvoiceReferee - 3 Phút

## Chuẩn bị trước khi quay

- Mở sẵn trang **Nhân viên**.
- Chuẩn bị một hồ sơ rõ ràng có kết quả `PASS`.
- Chuẩn bị một hồ sơ có bill và phiếu kiểm kê/report không khớp, có kết quả
  `NEEDS_HUMAN`.
- Mở sẵn trang **Kế toán** với hai hồ sơ trên.

## Bản văn nói liền mạch

> Xin chào Ban tổ chức và Ban giám khảo. Nhóm em xin giới thiệu InvoiceReferee,
> hệ thống hỗ trợ kế toán kiểm tra hồ sơ chi phí.
>
Trong quy trình hoàn ứng, kế toán không chỉ kiểm tra số tiền trên bill. Họ còn phải xác nhận chứng từ có đọc được rõ ràng không, có thiếu thông tin quan trọng không,mục đích chi tiêu và nếu với trường hợp kiểm kê có phiếu nhập kho hoặc biên bản giao nhận thì các tài liệu có mô tả cùng một giao dịch hay không. Nếu kiểm tra toàn bộ hồ sơ thủ công, thời gian xử lý sẽ kéo dài. 
> 
InvoiceReferee không thay kế toán ra quyết định, mà làm bước kiểm tra đầu vào trước. Nhân viên nộp bill, mô tả mục đích chi và tài
> liệu hỗ trợ nếu có. Hệ thống kiểm tra chứng từ có đọc được và trích xuất thông
> tin quan trọng chưa  Với hồ sơ có chứng từ rõ ràng và các thông tin đối chiếu thống nhất, hệ thống trả kết quả PASS để kế toán có thể xử lý nhanh hơn. Nếu thiếu chứng từ, chữ trên bill không đọc chắc chắn, hoặc dữ liệu giữa bill và tài liệu hỗ trợ không khớp, hệ thống dừng lại và trả về lý do cụ thể để kế toán hoặc nhân viên xác nhận. 
>
>
>Tại trang Kế toán, có 2 loại: hồ sơ đã pass và hồ sơ
> cần xử lý đi kèm lý do cụ thể. Mỗi kết quả có chứng từ gốc, lý do, nguồn tham chiếu và thời gian
> xử lý để kế toán truy lại cơ sở của kết luận.


>
> Giá trị của InvoiceReferee là giúp hồ sơ rõ ràng đi nhanh hơn, còn hồ sơ chưa
> chắc chắn được chuyển đến kế toán với lý do cụ thể. Cảm ơn Ban tổ chức và Ban
> giám khảo.

## Thao tác màn hình tương ứng

| Thời lượng | Màn hình cần quay |
| --- | --- |
| 0:00 - 0:35 | Trang Nhân viên và form nộp hồ sơ. |
| 0:35 - 1:05 | Chứng từ chính, nội dung đề nghị và tài liệu hỗ trợ. |
| 1:05 - 1:50 | Mở lần lượt ví dụ `PASS` và `NEEDS_HUMAN`, đồng thời chỉ vào lý do. |
| 1:50 - 2:15 | Phóng to findings/câu hỏi cụ thể của hồ sơ `NEEDS_HUMAN`. |
| 2:15 - 2:40 | Trang Kế toán: hai hàng đợi, chứng từ gốc, findings và nguồn tham chiếu. |
| 2:40 - 3:00 | Tổng quan hai hàng đợi và kết thúc. |

## Lưu ý khi quay

- Đọc với tốc độ vừa phải, khoảng 145 đến 155 từ mỗi phút.
- Không cần mở terminal, khóa API, JSON nội bộ hoặc phần cấu hình.
- Dùng dữ liệu mẫu không nhạy cảm và chọn sẵn hồ sơ có kết quả ổn định.
- Dùng đúng nhãn hiện có trong ứng dụng: `PASS` và `NEEDS_HUMAN`.

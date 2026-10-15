# Kịch bản video demo InvoiceReferee

**Thời lượng mục tiêu:** 2 phút 50 giây, không vượt quá 3 phút  
**Mục tiêu:** Cho thấy một hồ sơ thường quy được xử lý đến yêu cầu thu tiền, rồi một hồ sơ mâu thuẫn bị dừng đúng cách. Quay giao diện ứng dụng thật bằng hai hồ sơ demo đã chuẩn bị; không dựng lại kết quả bằng slide hoặc hình giả.

## Chuẩn bị trước khi quay

1. Chạy trên đúng phiên bản dự định nộp và một database demo cô lập. Dữ liệu nhân viên, công ty, chứng từ và context tài chính đều là dữ liệu tổng hợp.
2. Chuẩn bị TC01 sau khi đã tải và đọc giấy quyết toán, hóa đơn, biên nhận ứng. Để khoản ứng 4.000.000 đ ở trạng thái chờ kế toán xác nhận. Sau thao tác xác nhận, kết quả cần thấy là `COLLECT 760.000 đ`, `READY_TO_EXECUTE`, `execution_state=NOT_STARTED`.
3. Chuẩn bị TC05 đã chạy qua phiên bản có kiểm tra tổng dòng. Kết quả cần thấy: hai dòng 2.000.000 + 1.000.000 đ, tổng in 3.500.000 đ, chênh 500.000 đ, `WAITING`, chưa xác định số tiền và không có lệnh thu/chi. Context ứng 4.000.000 đ của lượt thử này là giả lập.
4. Đối chiếu cả hai hồ sơ với bản đang quay. Nếu phải dùng kết quả đã lưu để tránh chờ OCR/LLM, ghi rõ đó là kết quả của lượt chạy đã lưu; không nói video vừa khởi chạy một lượt LIVE mới.
5. Mở sẵn hai hồ sơ, phóng to chữ đủ đọc, tắt thông báo desktop và giấu terminal/devtools. Dành vài giây trước khi bấm để giám khảo kịp đọc từng kết quả.

## Kịch bản theo thời gian

| Thời gian | Hình ảnh và thao tác | Lời thoại |
|---|---|---|
| 0:00–0:12 | Mở trang làm việc của InvoiceReferee. | “Trong quyết toán, đọc được số tiền chưa đủ. Hệ thống còn phải biết hồ sơ nào đủ căn cứ để xử lý và hồ sơ nào cần dừng lại.” |
| 0:12–0:32 | Mở hồ sơ TC01 đã nộp. Cho thấy giấy quyết toán và hóa đơn trong danh sách nguồn. | “Đây là TC01, hồ sơ demo gồm giấy quyết toán, hóa đơn và chứng từ ứng. Dữ liệu người và chứng từ ở đây là dữ liệu tổng hợp.” |
| 0:32–0:58 | Ở vai trò kế toán, mở biên nhận ứng 4.000.000 đ, xem bên chuyển/người nhận/số tiền, rồi bấm xác nhận ghi nhận. | “Kế toán xác nhận khoản ứng thực nhận từ chứng từ. Đây là ghi nhận tiền đã giao, không phải chỉ lấy con số nhân viên khai trên giấy.” |
| 0:58–1:18 | Cho thấy kết quả đối soát và mở phần căn cứ. Giữ rõ `COLLECT 760.000 đ`, `READY_TO_EXECUTE`, `NOT_STARTED`. | “Chi phí đủ căn cứ là 3.240.000 đồng, ứng thực nhận 4 triệu; hệ thống tạo yêu cầu thu lại 760.000 đồng. Yêu cầu này chưa chuyển tiền: trạng thái thực hiện vẫn là chưa bắt đầu. Có thể mở căn cứ để xem nguồn liên quan.” |
| 1:18–1:28 | Chuyển sang TC05; dừng ở phần tổng hợp hai dòng. | “Tiếp theo là tình huống không được phép tự kết luận tiền.” |
| 1:28–1:55 | Hiển thị hai dòng 2 triệu và 1 triệu cùng tổng in 3,5 triệu; mở finding/câu hỏi có trích dẫn nguồn. | “Hai dòng cộng thành 3 triệu, nhưng giấy ghi tổng 3,5 triệu: lệch 500.000 đồng. Hệ thống nêu đúng hai số cần làm rõ và trỏ về chứng từ.” |
| 1:55–2:16 | Cho thấy `WAITING`, tiền chưa xác minh và danh sách lệnh trống. | “Vì tổng chi đang mâu thuẫn, hồ sơ chuyển sang chờ làm rõ. Số tiền chưa được kết luận và không có yêu cầu thu hay chi nào được phát hành.” |
| 2:16–2:42 | Giữ màn hình TC05; lần lượt chỉ vào câu hỏi, trạng thái và nguồn chứng cứ. | “Đây là ranh giới của hệ thống: mã nguồn kiểm phép tính và quy tắc; nhân viên xử lý câu hỏi về dữ kiện; kế toán xác nhận tiền thực tế. Bản demo không tự chuyển tiền và không kiểm tra giao dịch ngân hàng ngoài chứng từ đã cung cấp. Context ứng trong TC05 là giả lập.” |
| 2:42–2:50 | Màn hình kết thúc với tên sản phẩm và URL demo nếu đã triển khai công khai. | “InvoiceReferee tự xử lý khi đủ căn cứ, và dừng lại khi chứng từ không nhất quán.” |

## Lời thoại liền mạch

> Trong quyết toán, đọc được số tiền chưa đủ. Hệ thống còn phải biết hồ sơ nào đủ căn cứ để xử lý và hồ sơ nào cần dừng lại.
>
> Đây là TC01, hồ sơ demo gồm giấy quyết toán, hóa đơn và chứng từ ứng. Dữ liệu người và chứng từ ở đây là dữ liệu tổng hợp. Kế toán xác nhận khoản ứng thực nhận từ chứng từ. Đây là ghi nhận tiền đã giao, không phải chỉ lấy con số nhân viên khai trên giấy.
>
> Chi phí đủ căn cứ là 3.240.000 đồng, ứng thực nhận 4 triệu; hệ thống tạo yêu cầu thu lại 760.000 đồng. Yêu cầu này chưa chuyển tiền: trạng thái thực hiện vẫn là chưa bắt đầu. Có thể mở căn cứ để xem nguồn liên quan.
>
> Tiếp theo là tình huống không được phép tự kết luận tiền. Hai dòng cộng thành 3 triệu, nhưng giấy ghi tổng 3,5 triệu: lệch 500.000 đồng. Hệ thống nêu đúng hai số cần làm rõ và trỏ về chứng từ. Vì tổng chi đang mâu thuẫn, hồ sơ chuyển sang chờ làm rõ. Số tiền chưa được kết luận và không có yêu cầu thu hay chi nào được phát hành.
>
> Đây là ranh giới của hệ thống: mã nguồn kiểm phép tính và quy tắc; nhân viên xử lý câu hỏi về dữ kiện; kế toán xác nhận tiền thực tế. Bản demo không tự chuyển tiền và không kiểm tra giao dịch ngân hàng ngoài chứng từ đã cung cấp. Context ứng trong TC05 là giả lập. InvoiceReferee tự xử lý khi đủ căn cứ, và dừng lại khi chứng từ không nhất quán.

## Trước khi xuất video

- Quay thử một lượt có thao tác thật và bấm giờ; giữ bản cuối dưới 3 phút, mục tiêu 2:50 để còn khoảng đệm.
- Không nói TC01 đã thu tiền hoặc hồ sơ đã đóng: kết quả được trình bày ở đây là yêu cầu `COLLECT 760.000 đ`, chưa thực hiện.
- Không gọi TC05 là lỗi OCR: các số đọc được; lỗi trước đây là thiếu quy tắc so tổng dòng với tổng in trên giấy. Trong phiên bản hiện tại, mismatch được chặn.
- Ghi rõ dữ liệu giả lập trên màn hình hoặc lời thoại. Không gọi localhost là URL công khai.
- Nếu kết quả trên UI khác các trạng thái ghi trong kịch bản, dừng quay và cập nhật kịch bản theo kết quả thực tế; không diễn lại bằng cách sửa số trên giao diện.

## Căn cứ nội bộ

- Yêu cầu video tối đa 3 phút và khuyến nghị quay màn hình thật: `docs/Challenge_Brief_OrganizationAI_VN.docx.md`.
- TC05 sau sửa, fresh LIVE với context ứng giả lập: `docs/final/reviews/2026-10-15-tc05-live-arithmetic-fix.md`.
- TC01, khoản ứng 4 triệu → yêu cầu thu 760.000 đ; không thực hiện tiền trong lượt đó: `docs/final/IMPLEMENTATION_STATUS.md`.
- Runbook hiện ghi chưa có hosting công khai: `docs/final/RUNBOOK.md`. Video không thay thế yêu cầu nộp live URL; nếu vẫn chưa có URL khi quay, ghi hình bản chạy cục bộ và không giới thiệu là bản công khai.

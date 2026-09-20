# InvoiceReferee — Nhật ký phát triển

> Tài liệu này được chủ ý giữ gọn trong một trang. Hãy cập nhật bằng chứng thực tế trong suốt sprint; không tự tạo dữ liệu sử dụng hoặc kết quả.

## Dự án

**InvoiceReferee — Tác tử kế toán kiểm tra hóa đơn, biên lai và chứng từ chi phí**

Thử thách: OrganizationAI — Challenge A, Bộ điều phối chuyển tiếp.

## Giai đoạn hiện tại

Thiết kế và đặc tả trước khi viết mã.

Các tài liệu lập kế hoạch đã hoàn thành:

- bản tóm tắt yêu cầu tác tử kế toán;
- bản tóm tắt thử thách;
- đặc tả sản phẩm;
- Chính sách v0 giả lập;
- hợp đồng mô hình dữ liệu;
- luồng quyết định;
- bộ đánh giá 17 trường hợp;
- kế hoạch đánh giá đầu vào mới và kiểm chứng với người dùng thật;
- kiến trúc và kế hoạch triển khai.

## Công cụ AI đã sử dụng

Chỉ ghi các công cụ thực tế mà nhóm dùng trong quá trình triển khai.

Việc sử dụng ở giai đoạn lập kế hoạch hiện tại:

- trợ lý lập trình AI được dùng để hỗ trợ tái cấu trúc đặc tả, trường hợp chính sách, hợp đồng lược đồ và kế hoạch triển khai.

Trước khi nộp bài, thay phần này bằng tên công cụ/mô hình chính xác và mục đích sử dụng của từng công cụ.

## AI đã hỗ trợ ở đâu

Các quan sát trong giai đoạn lập kế hoạch:

- chuyển yêu cầu kế toán rộng thành tài liệu hướng đến triển khai;
- làm rõ khác biệt giữa thiếu dữ kiện, ngoài chính sách, vượt thẩm quyền và có nghi vấn;
- mở rộng phạm vi từ kiểm tra hóa đơn chỉ dựa trên PO sang hóa đơn điện tử + chứng từ nhân viên + bằng chứng bổ sung;
- chuẩn hóa giao diện để các mô-đun có thể được phát triển song song;
- định nghĩa chuỗi phép kiểm tra tất định → bối cảnh chính sách → đánh giá của LLM → Bộ bảo vệ quyết định tất định.

## Chi phí/rủi ro do AI tạo ra

Các rủi ro nhóm phải chủ động kiểm tra khi triển khai:

- AI có thể diễn đạt quy tắc nghiệp vụ giả lập như chính sách thật của công ty;
- AI có thể làm mờ ranh giới giữa `REQUEST_INFO` và `ESCALATE` nếu Bộ bảo vệ không nghiêm ngặt;
- câu hỏi được tạo có thể trôi chảy nhưng quá chung chung;
- đầu ra OCR/thị giác có thể trông đáng tin dù vẫn sai;
- mã do AI tạo không được thay thế việc kiểm chứng bằng giả định.

Mọi giá trị chính sách giả lập, đặc biệt ngưỡng thẩm quyền 50 triệu đồng và thời hạn nộp 30 ngày, phải được gắn nhãn là giả lập.

## Tính năng lớn nhất bị cắt

Sprint 1 chủ động cắt **tự động hóa thuế/kế toán đầy đủ và OCR cấp độ sản xuất**.

Sản phẩm tập trung vào một ranh giới kiểm tra có thể kiểm thử cho hóa đơn điện tử, chứng từ của nhân viên và bằng chứng bổ sung. Kiểm tra GTGT/TNDN, kê khai thuế, bút toán tự động, thanh toán tự động, tích hợp ERP và bộ máy phát hiện gian lận đầy đủ nằm ngoài Sprint 1.

Lý do: cuộc thi đánh giá cao một ranh giới quyết định hoạt động được và có thể kiểm thử hơn một tập tính năng rộng nhưng thiếu tin cậy.

## Bằng chứng cần bổ sung trước khi nộp

- các commit thực tế và quyết định triển khai quan trọng;
- công cụ/mô hình AI thực tế đã dùng;
- một nơi cụ thể AI giúp tiết kiệm thời gian;
- một nơi cụ thể AI gây làm lại hoặc phát sinh chi phí;
- tính năng thực tế bị cắt nếu có thay đổi;
- phản hồi người dùng và thay đổi sản phẩm tương ứng nếu có;
- tác động tiêu cực/ngoài ý muốn phát hiện trong kiểm thử.

# Yêu cầu đối với tác tử kế toán

## 1. Tóm tắt bài toán

Tác tử kế toán hỗ trợ kiểm tra hóa đơn điện tử, hóa đơn/chứng từ do nhân viên chụp và các bằng chứng thanh toán. Tác tử không chỉ nhận dạng ký tự; hệ thống phải trích xuất dữ liệu có cấu trúc, đối chiếu với chính sách, dữ liệu nội bộ và hệ thống, đồng thời phát hiện thông tin thiếu, sai quy định, vượt thẩm quyền hoặc bất thường.

Đầu ra cần có:

- dữ liệu chuẩn hóa để nhập/xuất kế toán;
- kết quả từng quy tắc/phép kiểm tra rõ ràng;
- hành động cuối cùng: `AUTO_PROCESS`, `REQUEST_INFO` hoặc `ESCALATE`;
- lý do, câu hỏi cần bổ sung, đối tượng xử lý và nhật ký kiểm toán.

## 2. Nhóm chứng từ

### 2.1. Hóa đơn điện tử

Các trường có thể có:

- mã cơ quan thuế, không bắt buộc;
- tên công ty bên mua, bắt buộc;
- mã số thuế bên mua, bắt buộc;
- người liên hệ/đại diện bên mua, không bắt buộc;
- địa chỉ bên mua, không bắt buộc;
- tên công ty bên bán, bắt buộc;
- mã số thuế bên bán, bắt buộc;
- người liên hệ/đại diện bên bán, không bắt buộc;
- địa chỉ bên bán, không bắt buộc;
- ngày lập hóa đơn, bắt buộc;
- tên hàng hóa/dịch vụ, bắt buộc;
- số lượng, bắt buộc với hàng hóa và không bắt buộc với dịch vụ;
- tổng tiền, bắt buộc;
- mẫu số, bắt buộc;
- ký hiệu, bắt buộc;
- số hóa đơn, bắt buộc.

### 2.2. Hóa đơn/chứng từ do nhân viên chụp

Các loại thường gặp:

- ăn uống/tiếp khách: nhà hàng, quán ăn, cà phê, biên lai POS;
- di chuyển: taxi, Grab/be, máy bay, xe khách, tàu;
- công tác: khách sạn và dịch vụ liên quan;
- mua hàng nhỏ lẻ: văn phòng phẩm, dây cáp, vật tư nhỏ, đồng phục;
- chi phí vận hành: in ấn, phí dịch vụ, sửa chữa;
- chứng từ bổ sung: phiếu thu, ảnh giao dịch ngân hàng/ví điện tử.

Các trường có thể trích xuất:

- cửa hàng/nhà cung cấp;
- ngày giờ giao dịch;
- hàng hóa/dịch vụ, số lượng, đơn giá và thành tiền từng dòng;
- tổng số tiền;
- chiết khấu;
- thuế/phí dịch vụ;
- phương thức thanh toán.

Bối cảnh thường phải lấy thêm từ nhân viên hoặc hệ thống:

- người chi/nhân viên;
- mục đích kinh doanh;
- khách hàng/dự án;
- mã chuyến đi/sự kiện/đơn hàng;
- bằng chứng đã nhận hàng/dịch vụ nếu cần.

## 3. Nhóm quyết định

### `AUTO_PROCESS`

Dùng khi chứng từ đọc được, đủ trường bắt buộc, số liệu nhất quán, đúng công ty, đúng chính sách, không trùng lặp, có bối cảnh kinh doanh, không còn bất thường chưa giải quyết và nằm trong hạn mức của tác tử.

### `REQUEST_INFO`

Dùng khi tác tử chưa đủ căn cứ để kết luận đúng/sai:

- thiếu một hoặc nhiều trường bắt buộc;
- ảnh mờ, bị che hoặc OCR/bộ phân tích bị lỗi;
- số lượng × đơn giá khác thành tiền;
- số tiền bằng chữ khác số tiền bằng số;
- bên mua ghi “khách lẻ” hoặc chưa rõ có phải công ty mình;
- chưa đủ bằng chứng đã nhận hàng/dịch vụ;
- hai nguồn dữ liệu mâu thuẫn, ví dụ PO ghi 10 máy tính nhưng phiếu nhận hàng ghi 8 máy;
- hóa đơn không có ngày giao dịch;
- chưa rõ bối cảnh kinh doanh;
- hóa đơn và khai báo của nhân viên khác nhau;
- chỉ có ảnh chuyển khoản nhưng chưa rõ hàng hóa/dịch vụ và mục đích.

### `ESCALATE / OUTSIDE_POLICY`

Dùng khi thông tin đã rõ nhưng vi phạm quy định:

- mã số thuế bên mua thuộc công ty khác;
- chứng từ trùng số hóa đơn + mã số thuế bên bán + số tiền với chứng từ đã xử lý;
- chi phí cá nhân;
- rượu bia hoặc danh mục bị cấm theo chính sách;
- thiếu mục đích kinh doanh sau khi đã đủ dữ kiện để xác định là không hợp lệ;
- chứng từ được nộp quá hạn theo chính sách.

### `ESCALATE / BEYOND_AUTHORITY`

Dùng khi chứng từ có thể hợp lệ nhưng vượt thẩm quyền tự động:

- số tiền vượt ngưỡng của tác tử/cấp hiện tại;
- khoản chi đặc biệt cần cấp cao hơn phê duyệt.

### `ESCALATE / SUSPICIOUS`

Dùng khi có tín hiệu bất thường/nghi vấn cần con người kiểm tra:

- số tiền bất thường so với lịch sử;
- nhà cung cấp mới hoặc lạ;
- nhiều chứng từ giống nhau;
- giao dịch ngoài giờ hoặc ngày nghỉ;
- nhân viên nộp nhiều chứng từ sát nhau;
- mục đích kinh doanh không tương xứng với hàng hóa/dịch vụ;
- ảnh có dấu hiệu chỉnh sửa;
- mẫu trùng lặp yếu, chưa đủ căn cứ để kết luận bằng quy tắc tất định.

## 4. Phạm vi kiểm thử tối thiểu

Bộ kiểm thử Sprint 1 phải có ít nhất 15 trường hợp và bao phủ:

- hóa đơn điện tử hợp lệ;
- chứng từ nhân viên hợp lệ;
- thiếu trường bắt buộc;
- OCR/ảnh mờ;
- số học không khớp;
- sai mã số thuế bên mua;
- trùng lặp;
- chi phí cá nhân hoặc bị cấm;
- thiếu mục đích/bối cảnh kinh doanh;
- bằng chứng mâu thuẫn;
- chỉ có bằng chứng thanh toán;
- thiếu bằng chứng nhận hàng/dịch vụ;
- vượt thẩm quyền;
- bất thường/nghi vấn;
- chứng từ quá hạn.

## 5. Nguyên tắc

Nếu chưa biết dữ kiện thì hỏi. Nếu dữ kiện đã rõ nhưng sai chính sách, vượt quyền hoặc có nghi vấn thì chuyển cho con người. Chỉ tự động xử lý khi bằng chứng đầy đủ, chính sách rõ ràng và thẩm quyền cho phép.

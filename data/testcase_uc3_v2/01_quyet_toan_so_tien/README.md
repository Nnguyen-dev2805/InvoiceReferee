# Quyết toán và số tiền

Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.

| Case | Tình huống | Kết quả kỳ vọng | Rule chính |
| --- | --- | --- | --- |
| 01_quyet_toan_so_tien-TC01 | Hợp lệ - nhân viên hoàn trả tiền thừa | READY_FOR_APPROVAL | - |
| 01_quyet_toan_so_tien-TC02 | Hợp lệ - công ty thanh toán thêm | READY_FOR_APPROVAL | - |
| 01_quyet_toan_so_tien-TC03 | Hợp lệ - không phát sinh chênh lệch | READY_FOR_APPROVAL | - |
| 01_quyet_toan_so_tien-TC04 | Hợp lệ - nhiều dòng chi trong một báo cáo | READY_FOR_APPROVAL | - |
| 01_quyet_toan_so_tien-TC05 | Không hợp lệ - tổng dòng không khớp tổng cộng | REQUEST_INFO | SET_PAPER_TOTAL_001 |
| 01_quyet_toan_so_tien-TC06 | Không hợp lệ - số tiền quyết toán chênh lệch ghi sai | REQUEST_INFO | SET_SETTLEMENT_DIFF_001 |
| 01_quyet_toan_so_tien-TC07 | Không hợp lệ - số tiền bằng chữ không khớp | REQUEST_INFO | SET_PAPER_CONSISTENCY_001 |
| 01_quyet_toan_so_tien-TC08 | Không hợp lệ - đơn quyết toán thiếu số tiền tạm ứng | REQUEST_INFO | SET_ADV_AMOUNT_001 |
| 01_quyet_toan_so_tien-TC09 | Không hợp lệ - không đọc được tổng cộng trên đơn | REQUEST_INFO | SET_PAPER_TOTAL_001 |
| 01_quyet_toan_so_tien-TC10 | Vượt thẩm quyền - tổng hồ sơ trên 100 triệu | ESCALATE | SET_AUTH_001 |

# Hồ sơ hoàn ứng phức hợp

Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.

| Case | Tình huống | Kết quả kỳ vọng | Rule chính |
| --- | --- | --- | --- |
| 05_ho_so_phuc_hop-TC01 | Hợp lệ - ba hóa đơn cho một chuyến công tác | READY_FOR_APPROVAL | - |
| 05_ho_so_phuc_hop-TC02 | Hợp lệ - một hóa đơn phân bổ đúng cho hai dòng | READY_FOR_APPROVAL | - |
| 05_ho_so_phuc_hop-TC03 | Không hợp lệ - một hóa đơn bị phân bổ vượt giá trị | REQUEST_INFO | SET_EVIDENCE_REUSE_001 |
| 05_ho_so_phuc_hop-TC04 | Hợp lệ - một dòng dùng hai hóa đơn gốc | READY_FOR_APPROVAL | - |
| 05_ho_so_phuc_hop-TC05 | Hợp lệ - hóa đơn gốc kèm bằng chứng thanh toán | READY_FOR_APPROVAL | - |
| 05_ho_so_phuc_hop-TC06 | Không hợp lệ - hóa đơn trùng định danh hồ sơ trước | RECOMMEND_REJECT | SET_DUPLICATE_001 |
| 05_ho_so_phuc_hop-TC07 | Không hợp lệ - file đổi tên nhưng nội dung hóa đơn trùng | RECOMMEND_REJECT | SET_DUPLICATE_001 |
| 05_ho_so_phuc_hop-TC08 | Ngoại lệ - hồ sơ có chứng từ gốc, thay thế và không chứng từ | ACCOUNTANT_REVIEW | SET_PAPER_EVIDENCE_EXCEPTION |
| 05_ho_so_phuc_hop-TC09 | Không hợp lệ - có chứng từ dư chưa được khai trong báo cáo | REQUEST_INFO | SET_PAPER_UNMATCHED_001 |
| 05_ho_so_phuc_hop-TC10 | Không hợp lệ - MST người mua sai đồng thời lệch số tiền | RECOMMEND_REJECT | SET_BUYER_IDENTITY_001 |

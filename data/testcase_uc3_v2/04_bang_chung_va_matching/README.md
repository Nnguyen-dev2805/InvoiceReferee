# Bằng chứng và ghép dòng chi

Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.

| Case | Tình huống | Kết quả kỳ vọng | Rule chính |
| --- | --- | --- | --- |
| 04_bang_chung_va_matching-TC01 | Hợp lệ - số hóa đơn và số tiền khớp | READY_FOR_APPROVAL | - |
| 04_bang_chung_va_matching-TC02 | Không hợp lệ - cùng số tiền nhưng sai nội dung | REQUEST_INFO | SET_PAPER_MATCH_001 |
| 04_bang_chung_va_matching-TC03 | Không hợp lệ - số hóa đơn khớp nhưng số tiền lệch | REQUEST_INFO | SET_PAPER_AMOUNT_001 |
| 04_bang_chung_va_matching-TC04 | Không hợp lệ - dòng ghi đính kèm nhưng thiếu chứng từ | REQUEST_INFO | SET_PAPER_EVIDENCE_REQUIRED |
| 04_bang_chung_va_matching-TC05 | Ngoại lệ - không có chứng từ nhưng có giải trình | ACCOUNTANT_REVIEW | SET_PAPER_EVIDENCE_EXCEPTION |
| 04_bang_chung_va_matching-TC06 | Ngoại lệ - dùng chứng từ chuyển khoản thay thế | ACCOUNTANT_REVIEW | SET_PAPER_EVIDENCE_EXCEPTION |
| 04_bang_chung_va_matching-TC07 | Hợp lệ - vé điện tử thay thế hóa đơn | READY_FOR_APPROVAL | - |
| 04_bang_chung_va_matching-TC08 | Không hợp lệ - chứng từ đính kèm không thuộc dòng nào | REQUEST_INFO | SET_PAPER_UNMATCHED_001 |
| 04_bang_chung_va_matching-TC09 | Không hợp lệ - khai báo hóa đơn nhưng không đính kèm file | REQUEST_INFO | SET_PAPER_EVIDENCE_REQUIRED |
| 04_bang_chung_va_matching-TC10 | Cần xác nhận - evidence gần phù hợp nhưng chưa đủ chắc chắn | REQUEST_INFO | SET_PAPER_MATCH_001 |

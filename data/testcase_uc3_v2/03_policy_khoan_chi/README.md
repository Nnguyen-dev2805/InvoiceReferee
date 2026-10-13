# Policy khoản chi và thẩm quyền

Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.

| Case | Tình huống | Kết quả kỳ vọng | Rule chính |
| --- | --- | --- | --- |
| 03_policy_khoan_chi-TC01 | Hợp lệ - taxi trong hạn mức | READY_FOR_APPROVAL | - |
| 03_policy_khoan_chi-TC02 | Vượt policy - taxi trên hạn mức | ESCALATE | SET_LIMIT_001 |
| 03_policy_khoan_chi-TC03 | Hợp lệ - tiếp khách trong hạn mức | READY_FOR_APPROVAL | - |
| 03_policy_khoan_chi-TC04 | Vượt policy - tiếp khách trên hạn mức | ESCALATE | SET_LIMIT_001 |
| 03_policy_khoan_chi-TC05 | Không hợp lệ - khoản chi cá nhân | RECOMMEND_REJECT | SET_CATEGORY_001 |
| 03_policy_khoan_chi-TC06 | Ngoại lệ policy - rượu bia tiếp khách | ACCOUNTANT_REVIEW | SET_PROHIBITED_ITEM_001 |
| 03_policy_khoan_chi-TC07 | Hợp lệ - khoản chi đúng hạn 30 ngày | READY_FOR_APPROVAL | - |
| 03_policy_khoan_chi-TC08 | Ngoại lệ policy - nộp hồ sơ quá 30 ngày | ACCOUNTANT_REVIEW | SET_DEADLINE_001 |
| 03_policy_khoan_chi-TC09 | Không hợp lệ - chưa xác định ngày chi | REQUEST_INFO | SET_EXPENSE_DATE_001 |
| 03_policy_khoan_chi-TC10 | Không hợp lệ - chưa xác định danh mục khoản chi | REQUEST_INFO | SET_CATEGORY_UNKNOWN_001 |

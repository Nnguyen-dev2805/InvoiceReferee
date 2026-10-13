---
status: accepted
date: 2026-10-13
---

# Xây lại InvoiceReferee từ đầu trên nhánh final

Người dùng quyết định xây lại từ đầu trên nhánh `final`, theo các quyết định mới
về bài toán và đánh giá, thay vì dùng code cũ làm giới hạn thiết kế. Đổi lại,
bản mới phải tự chứng minh các bất biến và chất lượng; kết quả kiểm thử hoặc
baseline của bản cũ không mặc nhiên chứng minh bản mới. Quyết định này không
cho phép rewrite Git history hoặc coi những lựa chọn công nghệ chưa duyệt là đã chốt.


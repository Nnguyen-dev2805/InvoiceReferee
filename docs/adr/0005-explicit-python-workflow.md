---
status: accepted
date: 2026-10-13
---

# Điều phối bằng workflow Python tường minh

Người dùng duyệt Q8: backend Python điều phối các bước phụ thuộc, lưu trạng thái,
chờ người và phục hồi; chưa dùng LangGraph trong bản đầu. Lựa chọn này giữ luồng
nghiệp vụ và kiểm soát transaction rõ, với trách nhiệm tự kiểm retry/idempotency,
Stop và phục hồi. LangGraph có checkpoint/interrupt hữu ích khi nhu cầu tăng,
nhưng chúng không thay quyền, căn cứ hoặc chống ghi trùng tiền; một node chạy lại
cũng cần kiểm side effects. Tracing/evaluation có thể tích hợp riêng, không quyết
định framework điều phối. Đây là quyết định thiết kế, chưa có runtime được kiểm.

# InvoiceReferee — Build Log

## 04/10/2026 — Bắt đầu nhánh rebuild

- Người phát triển đã vượt qua Sprint 1 và yêu cầu viết lại từ đầu để chuẩn bị
  chung kết; tên nhánh được yêu cầu là `rebuild`.
- Tạo nhánh `rebuild` từ `196e266541526123844a60820737f400e09b3a36` trên `main`.
- Dùng Codex để kiểm tra trạng thái Git, sao lưu code và file chưa theo dõi,
  dọn implementation cũ và cập nhật mô tả hiện trạng.
- Lưu snapshot tại `data/rebuild_backups/20261004T123014+0700/`; đối chiếu
  SHA-256 nội dung 80 file với archive trước khi dọn.
- Giữ nguyên đề bài cuộc thi, dữ liệu chứng từ/testcase, `.env` và môi trường
  Python local. Giữ phân tích khoảng cách như tài liệu tham khảo bản Sprint 1.
- Xóa source, test, notebook, script, dependency manifest và cấu hình Streamlit
  cũ khỏi working tree; hướng dẫn cũ nằm trong Git và snapshot local.
- Nhánh mới chưa có implementation. Chưa chạy test, provider hoặc deployment;
  không dùng kết quả test của bản cũ để chứng minh bản mới.
- Chưa stage, commit hoặc push thay đổi dọn code.

Build log Sprint 1 trước lần dọn được lưu trong snapshot và commit gốc. Các
ghi nhận tiếp theo phải phân biệt điều đã triển khai, kiểm chứng, chưa chứng
minh và mới đề xuất.

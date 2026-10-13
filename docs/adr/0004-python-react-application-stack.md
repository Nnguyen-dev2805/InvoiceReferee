---
status: accepted
date: 2026-10-13
---

# Nền ứng dụng Python và React cho pilot

Người dùng duyệt Q4: Python/FastAPI cho backend, Pydantic cho hợp đồng dữ liệu,
SQLite và thư mục chứng từ cho lưu trữ, React/TypeScript/Vite cho giao diện;
Mistral OCR và xkiro qua adapter SDK hoặc HTTP được kiểm chứng.
Nền này giữ xử lý nghiệp vụ ở backend và phù hợp pilot nhỏ mà không mở hạ tầng
phân tán. Q8 sau đó chốt workflow Python tường minh tại ADR005. Model, phiên bản
dependency và deployment cụ thể còn mở; validation schema không thay xác minh tiền/căn cứ.

# Bộ testcase UC-03 v2

Bộ dữ liệu giả lập cho luồng hoàn ứng/quyết toán tạm ứng. Không dùng cho nghiệp vụ thật.

## Cách chạy một case

1. Vào thư mục case.
2. Tải `request_form.pdf` làm đơn giấy chính.
3. Tải toàn bộ PDF còn lại làm chứng từ chi phí/evidence.
4. Không tải `expected.json`; file này là oracle cho kiểm thử.

## Nhóm nghiệp vụ

| Nhóm | Số case | Mục tiêu |
| --- | ---: | --- |
| `01_quyet_toan_so_tien` | 10 | Quyết toán và số tiền |
| `02_hop_le_chung_tu` | 10 | Hợp lệ chứng từ trước đối chiếu |
| `03_policy_khoan_chi` | 10 | Policy khoản chi và thẩm quyền |
| `04_bang_chung_va_matching` | 10 | Bằng chứng và ghép dòng chi |
| `05_ho_so_phuc_hop` | 10 | Hồ sơ hoàn ứng phức hợp |

`COVERED` là rule đã có trong Rule Engine; `PLANNED` là regression specification cho rule chưa triển khai đủ. Tên file không được dùng làm định danh chứng từ; định danh dựa trên nội dung OCR và trường chứng từ.

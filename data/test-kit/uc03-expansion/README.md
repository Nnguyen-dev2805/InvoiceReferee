# Mẫu giấy quyết toán chi phí chung

Mẫu PDF minh họa bố cục Hoangha kết hợp với final; không phải packet test đầy đủ
và không có kết quả runtime đã chạy. Nội dung synthetic, thuộc tiếp khách tại
địa phương, không thêm địa điểm/ngày công tác giả.

- Bảng5cột, tổng tiền, lời khai ứng/chênh lệch và3vị trí ký ngang.
- Không thêm câu tổng hợp tài liệu kèm theo hoặc đoạn xác nhận thanh toán dài.
- Kế toán/người duyệt để trống vì mẫu thể hiện lúc nhân viên nộp; các tên ký
  trong chứng từ demo không tự cấp quyền hoặc xác lập giao dịch tiền.
- Cần hóa đơn/context tương ứng và gold độc lập khi biến mẫu thành một case chạy.

Đặc tả policy/form:
[general-expense-policy-and-form](../../../docs/superpowers/specs/2026-10-14-general-expense-policy-and-form.md).

Script authoring của lượt này ở `.runtime/uc03-expansion-prototype/render.py`;
việc tích hợp renderer vào generator portable hiện có thuộc task triển khai sau,
không sửa `scripts/sinh_uc03_pilot.py` khi agent khác đang sở hữu file đó.

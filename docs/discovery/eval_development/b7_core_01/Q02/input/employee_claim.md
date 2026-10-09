# Nguồn giả lập — Bảng kê và lời khai nhân viên

Nhân viên NV-DEMO-02, công việc CT-DEMO-02, tổ chức ORG-DEMO-01; tất cả synthetic. Công tác Hà Nội05–06/10 để trao đổi dự án PARTNER-DEMO-02. Đề nghị xử lý toàn chi phí công việc tới08/10/2026 18:00 +07:00; nguồn [quyết định](authority_and_pretrip.md#pretrip-decision).

## expense-list

| Ref nguồn | Nội dung | VND | Khai báo payer |
| --- | --- | ---: | --- |
| INV-AIR-02 / BOOK-DEMO-02 | Vé phục vụ công tác | 3.000.000 | Công ty, để đối chiếu, không yêu cầu hoàn phần này |
| INV-HOTEL-02 | Lưu trú05–06/10 | 3.000.000 | Nhân viên chuyển khoản |
| RCPT-MEAL-02 | Ăn phục vụ công việc06/10 | 1.000.000 | Nhân viên tiền mặt |
| RCPT-GROUND-02 | Di chuyển phục vụ công việc05–06/10 | 1.000.000 | Nhân viên tiền mặt |

Đây là khai báo cần đối chiếu, không final outcome. [Original synthetic sources](expense_and_payment_sources.md) có giá trị và receipt theo từng khoản; nhân viên không khai thay lịch sử công ty.

## cash-attestation

NV-DEMO-02 xác nhận trực tiếp trả 1.000.000 VND tiền mặt cho VENDOR-MEAL-02 lúc12:30 ngày06/10/2026, đúng RCPT-MEAL-02, cho bữa ăn công việc CT-DEMO-02. Anonymous paid receipt và statement này liên kết bằng receipt ref/vendor/amount/time/purpose, không một checkbox PERSONAL. Không dùng nó làm receipt tiền ứng/return.

## employee-scope

Employee-side sources và lời xác nhận có scope phủ cash/tài khoản cá nhân được dùng cho công việc tới mốc xét. Không chi phí khác hoặc vendorrefund phía nhân viên trong phạm vi công việc. Nhân viên không nhận ứng và không nhận hoàn chi phí cho công việc này tới mốc xét, trong phạm vi tiền mặt/tài khoản cá nhân liên quan. Source phía công ty cần đọc riêng, lời khai này không thay company coverage. Không khẳng định thay company-side source/absence.

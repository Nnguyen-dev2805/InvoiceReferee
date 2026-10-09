# Nguồn giả lập — Đề nghị và bảng kê nhân viên

Đây là tài liệu synthetic do nhân viên giả lập `NV-DEMO-01` cung cấp cho công việc `CT-DEMO-01`, tổ chức `ORG-DEMO-01`. Không chứa đáp án quyết toán.

## Công việc

Đi Hà Nội ngày05–06/10/2026 để trao đổi yêu cầu dự án với đối tác giả lập `PARTNER-DEMO-01`. Hồ sơ đang nộp giải quyết toàn bộ chi phí công việc tới mốc M1. Nguồn quyết định trước chi: [quyết định](authority_and_pretrip.md#pretrip-decision).

## Bảng kê

| Ref trên nguồn | Nội dung | Giá trị VND | Khai báo người trả |
| --- | --- | ---: | --- |
| INV-AIR-001 / BOOK-DEMO-01 | Vé phục vụ hành trình công việc | 3.000.000 | Công ty; đưa để đối chiếu, không đề nghị hoàn lại phần này |
| INV-HOTEL-001 | Dịch vụ lưu trú05–06/10 | 3.000.000 | Nhân viên chuyển khoản |
| RCPT-MEAL-001 | Ăn trong thời gian làm việc ngày06/10 | 1.000.000 | Nhân viên trả tiền mặt |
| RCPT-GROUND-001 | Di chuyển phục vụ công việc05–06/10 | 1.000.000 | Nhân viên trả tiền mặt |

Mục đích các khoản khai báo thuộc công việc ở trên. Chứng từ và nguồn thanh toán tại [packet chứng từ](expense_and_payment_sources.md). Số khai báo này cần đối chiếu, không là proof independent. Nhân viên không khai thay lịch sử companydirect/hoàn trả của công ty hoặc tự tính số cuối.

## cash-attestation

Nhân viên giả lập xác nhận đã trực tiếp trả1.000.000VND tiền mặt cho `VENDOR-MEAL-01` lúc12:30 ngày06/10/2026, đúng khoản `RCPT-MEAL-001`, dùng cho bữa ăn trong công việc `CT-DEMO-01`. Biên nhận không ghi tên người trả; statement gắn đúng khoản/phương thức/thời điểm/phạm vi này. Không dùng statement này để xác nhận đã nhận ứng hoặc công ty đã nhận tiền trả lại.

## employee-scope

Nguồn phía nhân viên về expensepayment và vendorrefund thuộc công việc phủ tới08/10 18:00: hotel/meal/ground và cash attestation theo các source trong packet, không expense/refund khác phía mình trong scope. Không có hoàn chi phí nhận trước trong scope. Đối với lệnh TX-ADV-001, packet chưa có receiver-side receipt hoặc xác nhận actualcredit; statement này không xác nhận đã nhận hay chưa nhận2triệu. Không có ứng khác ngoài sự kiện đang đối chiếu theo nguồn company. Không khai thay company-side fact.

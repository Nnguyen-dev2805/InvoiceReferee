---
status: accepted
date: 2026-10-14
---

# Căn cứ lời xác nhận của nhân viên cho khoản nhân viên đã trả

Người dùng chốt (Q32, 14/10/2026): **lời xác nhận chịu trách nhiệm của nhân viên**
rằng mình đã trả một khoản chi, cùng **chứng từ dịch vụ**, được chấp nhận làm căn
cứ để hệ thống tự phát hành yêu cầu chi/thu routine khi các điều kiện khác đủ và
không có mâu thuẫn trọng yếu. Đây là thay đổi so với yêu cầu căn cứ tiền đã xác
minh ở design §3 / contracts §3 trước đó (chỉ nhận payment proof hoặc confirmation
tài chính).

## Ranh giới và điều kiện

- **Ngưỡng (đề xuất của lead, chờ người dùng review):** chỉ áp dụng trong giới hạn
  tự xử lý hiện có — `E <= 8.000.000 đ` và `abs(S) <= 4.000.000 đ`. Vượt ngưỡng vẫn
  là AUTHORITY, không tự phát hành. Không tạo hạn mức mới; tái dùng ranh giới 8/4
  triệu của design §2.
- **Mức căn cứ hiển thị đúng:** nguồn tiền là "lời xác nhận của nhân viên", không
  được gọi là giao dịch ngân hàng đã xác minh, không tạo `Fact.KNOWN` giống như
  chứng từ độc lập. Trường `verified_by`/provenance phản ánh actor là nhân viên.
- **Không suy diễn từ chứng từ dịch vụ:** tên/chữ ký/`TM-CK` trên hóa đơn không tự
  chứng minh người trả hoặc việc đã thanh toán (giữ nguyên contracts §3).
- **Mâu thuẫn trọng yếu** giữa lời khai và chứng từ vẫn `UNKNOWN`/`CONFLICT`; không
  tự công nhận.
- **Chứng từ dịch vụ vẫn bắt buộc** cho khoản chi. Bỏ yêu cầu upload file chứng
  minh thanh toán riêng **không** đồng nghĩa tự công nhận lời khai là đủ căn cứ;
  đây là hai quyết định khác nhau (xem ADR0006).

## Rủi ro được giữ lại

Không phát hiện được lời khai sai khi không có dấu hiệu. Phạm vi số tiền và metric
(false-known trên gold độc lập) phải được chốt và đo trước khi claim chất lượng.
Các quyết định tài chính/policy chi tiết vẫn thuộc plan finance/admissibility, không
nằm trong pipeline chứng cứ (design §15, contracts §12).

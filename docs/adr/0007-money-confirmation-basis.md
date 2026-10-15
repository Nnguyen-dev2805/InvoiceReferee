---
status: accepted
date: 2026-10-14
---

# Căn cứ khoản nhân viên đã trả

## Chốt vòng 14/10/2026 (hóa đơn là căn cứ, thay lời xác nhận riêng)

Người dùng chốt lại căn cứ cho khoản nhân viên đã trả trong **policy demo**:

1. Chỉ hỗ trợ nhân viên tự thanh toán nhà cung cấp; không triển khai công ty thanh
   toán trực tiếp nhà cung cấp.
2. Trong policy demo này, **hóa đơn hợp lệ, gắn đúng nhân viên và hồ sơ, được chấp
   nhận làm căn cứ khoản chi nhân viên đã thanh toán**.
3. **Không** yêu cầu giấy xác nhận thanh toán riêng hoặc lời xác nhận thanh toán dài
   trên giấy quyết toán.
4. Quy ước (2) là **giả định nghiệp vụ cho demo**: không trình bày như xác minh ngân
   hàng, không tạo giao dịch ngân hàng giả hoặc confirmation giả. Mức căn cứ là
   `EMPLOYEE_PAID_INVOICE` (policy demo), view ghi rõ "căn cứ theo policy demo", không
   "đã xác minh ngân hàng".
5. Khoản **ứng thực nhận** vẫn cần **bản ghi/căn cứ riêng của công ty**; đã duyệt ứng
   không tự thành đã nhận. Kế toán ghi nhận `ADVANCE_RECEIVED` từ chứng từ ứng.
6. Chữ ký demo dùng văn bản "Ký bởi: …" và ngày ký; chưa kiểm tra chứng thư số, ảnh
   chữ ký hoặc mật mã.
7. Giữ nguyên các quy tắc khác về thẩm quyền, scope, lịch sử tiền, số học,
   Stop/Resume và chống trùng. Ngân sách B được đưa ra ngoài phạm vi bởi
   [ADR0009](0009-activity-budget-out-of-scope.md); căn cứ nhân viên đã trả ở đây
   không thay đổi. Không mở rộng policy ngoài các điểm đã chốt.

**Hệ quả code:** `PaymentBasisKind` thêm `EMPLOYEE_PAID_INVOICE`. `admit_evidence`
tạo phần nhân viên đã trả từ một hóa đơn gốc có `profile_status=CLEAR`, có
`total_amount` và có người mua (nếu có) gắn đúng nhân viên hồ sơ. Bên mua là công ty
**không** được coi là công ty trả trực tiếp (không tạo C). Lệch người/sai hồ sơ/số
tiền mâu thuẫn/tài liệu chưa đọc rõ vẫn là FACT đúng chỗ. Đường Q32
(`EMPLOYEE_DECLARATION_Q32`) vẫn tồn tại cho hồ sơ cần lời xác nhận có ngưỡng, nhưng
không còn là đường bắt buộc mặc định của hồ sơ routine.

## Lịch sử (chốt Q32 14/10/2026)

Trước đó người dùng chốt (Q32): **lời xác nhận chịu trách nhiệm của nhân viên** rằng
mình đã trả một khoản chi, cùng **chứng từ dịch vụ**, được chấp nhận làm căn cứ. Chốt
mới thay đường mặc định bằng hóa đơn gắn đúng nhân viên; lời xác nhận có ngưỡng vẫn
giữ như đường phụ.

## Ranh giới và điều kiện (đường Q32)

- **Ngưỡng:** `E <= 8.000.000 đ` và `abs(S) <= 4.000.000 đ`. Vượt ngưỡng là AUTHORITY.
- **Mức căn cứ hiển thị đúng:** "lời xác nhận của nhân viên", không gọi là giao dịch
  ngân hàng đã xác minh.
- **Mâu thuẫn trọng yếu** giữa lời khai và chứng từ vẫn `UNKNOWN`/`CONFLICT`.
- **Chứng từ dịch vụ vẫn bắt buộc** cho khoản chi (ADR0006).

## Rủi ro được giữ lại

Không phát hiện được lời khai/hóa đơn sai khi không có dấu hiệu. Phạm vi số tiền và
metric (false-known trên gold độc lập) phải được đo trước khi claim chất lượng. Các
quyết định tài chính/policy chi tiết thuộc plan finance/admissibility (design §15,
contracts §12).

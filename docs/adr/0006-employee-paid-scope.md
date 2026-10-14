---
status: accepted
date: 2026-10-13
---

# Thu hẹp bản đầu vào khoản nhân viên trực tiếp thanh toán

Người dùng chốt thu hẹp quy trình quyết toán vào các khoản nhân viên trực tiếp
thanh toán cho hoạt động công việc. Công ty thanh toán trực tiếp nhà cung cấp
nằm ngoài bản đầu; công ty tạm ứng cho nhân viên, hoàn tiền cho nhân viên và nhận
tiền nhân viên hoàn lại vẫn trong phạm vi. Quyết định này thay phần hỗ trợ
company-direct ở thiết kế trước để đơn giản hóa hồ sơ, giao diện và kiểm thử.

Nhân viên nộp đề nghị/bảng kê và chứng từ dịch vụ. Trước mắt không bắt nộp file
thanh toán riêng. Điều kiện dùng lời xác nhận của nhân viên để tự tạo yêu cầu
chi/thu chưa được chốt; không suy ra tên/chữ ký trên hóa đơn là xác nhận giao dịch.

Người dùng yêu cầu ghi phần giải trình khi thiếu chứng từ để phát triển sau.
Phạm vi hoãn so với cơ chế câu hỏi/chuyển tiếp bắt buộc của đề thi đang được
grill tại thiết kế §14. Chưa có yêu cầu xóa đường AnswerIssue đã tồn tại.

## Chốt vòng 14/10/2026

Người dùng chốt tiếp ba câu còn mở của design §14:

- **Q33 — Giải trình (hoãn form, giữ câu hỏi):** hoãn form giải trình tự do; giữ
  khả năng nêu vấn đề/câu hỏi cụ thể, đúng người xử lý, cho sửa khai báo/bổ sung
  nguồn và kiểm lại. Không tự kết luận đủ điều kiện cho nguồn thiếu/mâu thuẫn
  trọng yếu. Đường `AnswerIssue` hiện có vẫn giữ.
- **Q34 — Nguồn ngoài phạm vi employee-paid:** khi tài liệu cho thấy công ty trả
  trực tiếp hoặc người trả thuộc bên khác, **giữ nguồn và báo phần ngoài phạm vi**;
  không ép thành khoản nhân viên đã trả, không bỏ phần vật chất để kết luận tiền.
  Hệ quả: giữ trường `C` (company-direct) như dữ kiện chi phí để đối chiếu và báo
  ngoài phạm vi, nhưng **không** đưa vào phép tính hoàn trả cho nhân viên.
- **Q32 — Căn cứ lời xác nhận:** xem [ADR0007](0007-money-confirmation-basis.md).

Trạng thái: **ACCEPTED**. Các quyết định thiết kế đã chốt; code, contracts, bộ dữ
liệu và gold vẫn **chưa** được chuyển đổi theo phạm vi mới. Việc chuyển đổi do plan
Hoangha-evidence (E0) và plan finance/admissibility kế tiếp sở hữu; không coi các
kết quả kiểm thử trước đây là đã chứng minh phạm vi mới.

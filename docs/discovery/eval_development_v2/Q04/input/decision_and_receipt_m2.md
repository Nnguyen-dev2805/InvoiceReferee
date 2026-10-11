# Nguồn mới giả lập — Chỉ dùng tại M2

Tài liệu không thuộc input M1. M2 là09/10/2026 10:00 +07:00. Không có nguồn thật hoặc thanh toán thật đã thực hiện.

## final-decision

`DEC-SETTLE-DEMO-01`, người quyết định `APR-DEMO-01`, lúc09:00 ngày09/10/2026, công việc `CT-DEMO-01`/employee `NV-DEMO-01`. Dựa trên report đúng scope M1 đã được kế toán rà soát, quyết định chấp nhận chi phí công việc tổng8.000.000VND: companydirect3.000.000, phần employee5.000.000; giữ ứng thực nhận2.000.000 và history M1. Phê duyệt công ty hoàn thêm3.000.000VND cho employee. Không ngoại lệ/phần trả chậm/đổi source hoặc thayB.

Nguồn [quyền](authority_and_pretrip.md#authority) bao phủ nội dung này. Đây là quyết định thực trong câu chuyện synthetic, không nhãn gold hoặc kết quả của pipeline. Trước source receipt dưới đây, quyết định chưa là tiền đã nhận.

## reimbursement-receipt

Gross event `TX-REIMB-001`, company ledger row mới `FIN-ROW-003`. Company `ORG-DEMO-01` chuyển3.000.000VND tới `NV-DEMO-01` theo `DEC-SETTLE-DEMO-01` lúc09:30 ngày09/10. Nguồn receipt phía employee synthetic `RCV-REIMB-001` xác định đã nhận đúng amount/beneficiary/purpose đó; không chỉ lệnh hoặc bank debit. Hợp nhất nguồn cùng event đúng ref, không cộng một row và một receipt thành hai lần nhận.

## coverage-m2

Nguồn công ty/employee ở M1 cập nhật tới M2 theo cùng phạm vi/owner/phương thức; sự kiện mới duy nhất là `TX-REIMB-001`, cùng quyết định trên. Không advance/returns/vendorrefund/chi phí khác, pending, overpayment, wrongrecipient, Stop hoặc sửa source/authority/decision ảnh hưởng. Kế toán quan sát đủ các nhóm/phía company; receipt và scope phía employee phủ actualreceipt mới, không chỉ suy từ statement company. Mốc mới không overwrite scope M1.

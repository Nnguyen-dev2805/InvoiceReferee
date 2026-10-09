# Nguồn giả lập — Phạm vi tập dữ liệu tới M1

Source `COV-DEMO-M1`, issuer `ORG-DEMO-01`, uploader/owner kế toán giả lập `ACC-DEMO-01`. Coverage03/10/2026 tới08/10/2026 18:00 +07:00, đúng `CT-DEMO-01`/`NV-DEMO-01` và nguồn liên quan trong công ty giả lập. Tất cả nội dung là synthetic statement cho walkthrough, không chứng minh nguồn công ty thật đầy đủ.

## Phạm vi quan sát

Trong thế giới giả lập này kế toán có đủ sổ ngân hàng/thẻ/tiền mặt của công ty, các nguồn actualreceipt liên quan phía nhận, sổ đề nghị/approval/paymentattempt và lịch sử claim để quan sát đúng nhóm/phương thức/phía tiền trên tới M1. Không chỉ một bankaccount hoặc các dòng đang hiển thị. Employee-side expensepayment và vendorrefund dùng thêm nguồn/statement phía nhân viên, không được xác nhận thay bằng role kế toán.

- [Ledger M1](financial_events_m1.csv) gồm mọi company money events thuộc công việc/người tới M1: một companydirect và một advance. Status SETTLED chỉ rawstatus; kết luận receipt dựa source được row tham chiếu có beneficiary/amount/purpose rõ.
- Không companydirect khác thuộc công việc; không company payment cho hotel/meal/ground trong scope.
- Không hoàn chi phí cho nhân viên, không hoàn ứng/return reimbursement company thực nhận trong scope; không vendorrefund về phía công ty.
- Không request/attempt/pending còn hiệu lực, sự cố payment/overpayment hoặc nghĩa vụ ngoài nhóm routine liên quan.
- Lịch sử hồ sơ/nghĩa vụ do công ty quản lý tới M1 không có claim khác đã hoàn trả/pending cho cùng invoice/receipt/booking/phần đang xét. Không có copyevent khác bị bỏ khỏi ledger, sửa/hủy quyết định trướcchi hoặc Stop cóhiệu lực. Sourcequyền duyệtquyếttoán hiện tại đọcriêng tại approval_assignment.md; statementfinancialcoverage này không xácnhận thay nó.

Đây là absenceconfirmation có owner/phạm vi/căn cứ quan sát synthetic rõ, không tạo các giao dịch0. Không sử dụng để xác nhận ngoài03–08/10 hoặc người/công việc/nguồn không được nêu. Input đến muộn làm kết luận cần kiểm tra lại theo version, không sửa âm thầm quyết định trước.

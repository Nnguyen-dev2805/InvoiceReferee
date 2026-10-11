# B5 — Ghi tiền ứng thực nhận và chờ quyết toán

Ngày11/10/2026. **PLANNED**, chưa runtime đã nghiệm thu. Tiếp nối
[B3 approval](2026-10-11-b3-present-and-approve-design.md), theo
[Rulebook R4–R10](../../settlement/RULEBOOK.md). Phạm vi pilot khoảng5 người.

## 1. Công việc và ranh giới

Con người thực hiện chi bên ngoài app. Kế toán được phân công ghi sự kiện
và căn cứ nguồn, chương trình đối chiếu với B3 decision. Không tạo lệnh chi,
chuyển ngân hàng, lịch chi, tự retry hoặc tự thu hồi phần vượt.

Đầu ra: lịch sử sự kiện tiền bất biến, tổng đã ghi nhận trong phạm vi quyết
định, phần thực hiện hợp lệ/còn lại, pending/unknown/incidents và stage.
APPROVED/RECEIVED/FULFILLED là ba nghĩa khác nhau. Bank debit/Submitted hoặc
Paid generic không tự là nhân viên đã nhận.

AI không quyết định tiền đã tới. Trong slice này proof là
HUMAN_SOURCE_REVIEW: kế toán đọc retained sources và lưu xác nhận đọc từng
field kèm source/locator/raw/value. Đây là nhập có căn cứ bởi người, không
OCR/LLM/bank verification hoặc forensic authenticity guarantee. Công sức
đọc/nhập được đo; AI prefill và bank integration không thuộc deliverable.

## 2. Hai thao tác

1. Đính kèm chứng từ ứng bằng route B5 riêng: bank receiver receipt/outcome
   phù hợp, hoặc biên nhận cash có bên giao/nhận. Lưu originals/hash/provenance.
2. Ghi sự kiện: quyết định liên quan (nếu đã có), namespace/ref giao dịch,
   phương thức, số tiền được nguồn mô tả, bên trả/bên nhận, event_at và outcome.
   Tách thời gian giao dịch với thời gian ghi/nhận nguồn.

Không cho nhân viên/approver tự ghi thay company-side actual. Role ACCOUNTANT
phải đúng persona/route trong context, không chỉ đổi dropdown. Employee có
thể cung cấp nguồn nhưng kế toán xử lý fact theo nguồn; không PERSONAL checkbox.

RECEIVED đủ dùng cần source đọc được về amount/VND, actual payer-side COMPANY,
actual payee đúng employee hoặc identity mapping có căn cứ, event/time/scope,
receiver receipt semantics và economic event identity. Số tiền mờ/recipient
chỉ suy từ form/không có outcome nguồn ⇒ giữ UNCONFIRMED, không cộng vào tiền
đã nhận. Reading confirmation chỉ khi người thực đọc được; không gõ số đoán
để bỏ quality gate. Chứng từ cash phải xác định tiền đã giao/nhận, không phiếu
xin chi. Nguồn không readable cần bổ sung nguồn khác; không chế confidence.

Nhân viên dự kiến nhận hiển thị readonly để đối chiếu; actual payee không
được mặc định từ employee_ref. Source quote của sender debit không thay
receiver outcome. Nguồn chỉ ghi ngoại tệ giữ raw và unresolved, không đổi VND.

## 3. Outcome và cập nhật bất biến

| Outcome nguồn | Hành vi |
| --- | --- |
| RECEIVED | Tiền đã tới actual recipient có căn cứ; kiểm scope/dedup rồi ghi actual. Không đồng nghĩa thực hiện đúng approval. |
| PENDING | Có bằng chứng lệnh đang chờ; chưa actual receipt. |
| FAILED/CANCELLED | Có outcome xác định, chưa receipt; giữ số lệnh/raw; không tự retry hoặc tạo advance0. |
| UNCONFIRMED | Chưa đủ thông tin outcome/amount/recipient/identity; giữ claim/source, không đoán0 hoặc pending. |

Pending/unknown có source mới: append record supersedes_event_id trỏ record
cùng case/decision/economic event, không overwrite. Chỉ nonfinal→final hợp
lệ mới supersede; hai confirmed outcomes mâu thuẫn phải giữ cả hai và issue,
không chọn mới nhất. RECEIVED rồi trả/reversal không là FAILED trước receipt;
giữ gross và chuyển resolution, ngoài slice hoàn ứng/return.

Một economic event một lần: namespace+ref thực theo nguồn/register có căn
cứ, không chỉ amount/date hoặc filename. Source copies/aliases không tạo
thêm tiền; same-key replay idempotent. Cùng event đã dùng ở case/work khác
cần phát hiện allocation conflict, không cộng lần hai. Thiếu identity có
thể giữ raw receipt, nhưng chưa aggregate chắc chắn. Không tự sinh mã ngân
hàng giả; ID nội bộ record khác event_ref ngoài nguồn.

## 4. Đối chiếu với số ứng đã duyệt

Ví dụ duyệt2triệu:

| Tiền/nguồn | Kết quả |
| --- | --- |
| Đúng người/decision, receipt2triệu, không pending/incident | Fulfilled2, remaining0; chờ quyết toán sau công việc. |
| Receipt1triệu đúng, không ambiguity/pending | Giữ approved2/recorded1/fulfilled1/remaining1; chưa cấp đủ, không bắt duyệt lại hoặc tự chi phần còn. |
| Một pending/unknown event ảnh hưởng tổng | Giữ confirmed subtotal, total/remaining chưa chắc phải null; không cộng pending hoặc suy absence0. |
| Receipt3triệu đúng người, approved2 | Giữ actual3, fulfilled obligation2/remaining0 và OVERPAY1; chuyển xử lý vướng mắc, không clip actual2 hoặc tự tạo yêu cầu thu1. |
| Tiền tới người khác | Giữ raw actual payee/gross; không employee received/fulfillment; incident, không tự chi bù. |
| Receipt có thật nhưng approval stale/refused/không tìm được | Giữ actual facts/source; UNAUTHORIZED_OR_UNALLOCATED incident, chưa gọi fulfillment hợp lệ. |

Chưa có receipt: recorded_received_vnd=null, không0. Nếu known subtotal0 từ
các event không trả employee, vẫn không suy toàn A=0. Summary scope là decision
này và managed events, không lịch sử toàn công ty/whole-work A đã complete.
Coverage/absence cần cho B7 vẫn phải đối chiếu ở chặng quyết toán.

## 5. Stop, basis và sources

Ghi actual xảy ra được phép khi Stop hoặc basis cần kiểm lại; không tạo
quyền chi mới. Con người vẫn chịu trách nhiệm thao tác ngoài app. Stage không
tự tiến qua Stop; receipt facts được lưu, sau resume/recheck mới xét tiến độ.
Approval hết hiệu lực hôm nay không xóa receipt lịch sử; kiểm căn cứ/hiệu lực
tại event time nếu xét fulfillment, lưu mọi uncertainty/material changes.

Route upload B5 gắn source-use backend `B3_ADVANCE_PROOF`, chỉ kế toán đúng
route được dùng; generic upload không được tự gắn reserved metadata. Nguồn
proof lưu cùng sources/artifacts, nhưng không tăng proposal input_revision
hoặc trở thành giấy đề nghị/dự toán trong Reader B3. Nó tăng case_version và
audit. Không sửa signature của decision cũ.

Chỉ sử dụng như proof không miễn material facts: nếu nguồn mang sửa công việc/
budget/quyền hoặc mâu thuẫn critical basis, kế toán phải đánh dấu cần kiểm
lại và đưa qua source-intake thường; không dùng funding role để giấu thay
đổi. Unknown/mismatch receipt vẫn là issue. Đây là nguồn purpose có người
phụ trách đọc, không hệ thống tự xác thực toàn bộ nội dung file.

## 6. Persistence, trạng thái và liên kết sau

Reuse money_events typed JSON kind ADVANCE_TO_EMPLOYEE và audit operation
B3_ADVANCE_EVENT; không sửa schema.sql hoặc B7 ReportedStatus. B7 projection
lọc PAYMENT_TO_EMPLOYEE/PAYMENT_FROM_EMPLOYEE trước mọi count/sum/pending,
để advance không thành reimbursement. B3 chỉ dùng events của B3 scope.

B3WorkflowView thêm funding summary và events; B3Approval panel:
- Chờ/nhận một phần: AWAITING_MONEY.
- Đã thực hiện đủ, decision đúng, không Stop/pending/unknown/incident:
  AWAITING_WORK_SETTLEMENT, “Đã ghi nhận ứng — chờ quyết toán”.
- Wrong/overpaid/conflicting/unauthorized: RESOLVING_OBLIGATIONS và vấn đề rõ.
Giữ b3 decision/status riêng để không mất work/B/advance đã duyệt.

Không đóng hồ sơ khi nhận ứng đủ. B5 không tạo B7 case tự động hoặc thay đổi
job B3→B7. Event/history phải lưu employee/work/decision/as-of/source refs
để chặng liên kết B7 dùng lại; không mặc định RA/P/RP0 từ sổ B5.

## 7. Nghiệm thu

Happy2; partial1+1; pending→receipt cùng event không nhân đôi; unknown;
failed/cancelled; wrong recipient; overpay3; aliases/cross-case duplicate;
confirmed conflict; malformed source refs; Stop/stale vẫn lưu actual nhưng
không mở chi; proof upload không phá basis chỉ vì là fulfillment; material
source vẫn cần recheck; dates sau cutoff không backdate; restart/same-key/
version races; B7 money isolation; không closure/bank action.

Fake unit/API và UI cùng application path; HUMAN_SOURCE_REVIEW không phải
AI extraction benchmark hoặc professional trial. [Plan](../plans/2026-10-11-b5-advance-receipts.md).

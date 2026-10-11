# B6 → B7 — Nộp quyết toán liên kết công việc

Ngày11/10/2026. **PLANNED**, chưa năng lực runtime đã nghiệm thu. Tiếp nối
[B5](2026-10-11-b5-advance-receipts-design.md), theo
[Product](../../settlement/PRODUCT.md), [Rulebook](../../settlement/RULEBOOK.md)
và [Evaluation](../../settlement/EVALUATION.md).

## 1. Phạm vi

Nhân viên mở công việc B3 hiện có, chuẩn bị hồ sơ B7 riêng, nhập chi phí
thực tế/tải chứng từ, xác nhận nộp, rồi chạy cùng pipeline đối soát B7.
Giữ B3/B5 nguyên lịch sử, cùng employee_ref/work_ref và link origin rõ.
Không đổi job của case B3 thành B7, không tạo mã công việc mới.

Lát cắt kết thúc ở report/câu hỏi/kế toán rà soát. Không mở thêm B8 approval,
B9 chi/thu/closure hoặc claim toàn quy trình đã hoàn tất. B7 không có B3
(tự chi) vẫn là đường riêng, không ép tạo tạm ứng0 để dùng feature này.

## 2. Hai loại thông tin

| Nguồn server dùng lại | Nhân viên khai sau công việc |
| --- | --- |
| Nhân viên, work, trip/purpose và decision B3 có căn cứ | Khoản chi thực tế: nội dung, ngày, số khai, mục đích/phạm vi |
| Work permission/ngân sách **được quyết định**, không forecast | Invoice/receipt/ticket và nguồn thanh toán phía mình |
| B5 canonical actual events có source/scope/time, không số duyệt | Payer declaration/giải thích hoặc bounded cash statement khi cần |
| Pending/unknown/incidents và các giới hạn coverage | Không nhập lại B/A hoặc xác nhận absence thay công ty |

Forecast3triệu không là actual expense3; company dự kiến trả vé3 không là
actual company-direct3. Source company cần chứng từ/receipt/quan hệ riêng.
Khai PERSONAL không là payment fact; có company-paid source thì đối chiếu,
không bỏ source hoặc tự gọi fraud.

## 3. Tạo draft và nộp

“Chuẩn bị hồ sơ quyết toán” tạo/reuse một active B7 trong employee/work scope.
Draft cho phép sửa rows và upload nguồn; confirmed=false không chạy routine
report chính thức. “Xác nhận nộp và đối soát” xác nhận khai báo rồi Start Run.
Nếu Start thất bại sau confirm, giữ đã nộp và cho chạy lại; không tạo case mới.

Row declaration giữ namespace riêng. Chỉ purpose/context được dùng theo
Rulebook cho phép; declared_amount/declared_payer không tự expense/payment
USABLE. Nguồn và khai báo khác nhau phải nêu cả hai và hỏi cụ thể khi material.
MVP form WEB; import bill vẫn được, nhưng chưa auto-import bảng kê thành form.

Missing receipt/advance unknown/parent funding chưa đủ không ngăn intake.
Hồ sơ vẫn được kiểm phần đã rõ và chuyển đúng owner; không buộc nhập giả2
hoặc0 để Run. Parent unconfirmed scope chưa đủ thì cần xác nhận scope trước
liên kết, không phỏng đoán đó là cùng chuyến đi.

## 4. Context liên kết có căn cứ

Server tạo retained snapshot source JSON trong B7, gồm origin/decision refs,
parent versions/signatures, actual event identities/evidence refs và
provisional facts. Parent proof/basis cần thiết được copy bytes sang artifact
child có provenance để link mở được và không phụ thuộc xóa parent folder.
Basis/forecast copies chỉ là tham chiếu, không vào Reader như actual bills.

Context source được audit backend-owned. Python chuyển các typed persisted
decisions/events thành observations có nguồn; không nhờ LLM đọc lại số đã
được ghi. Originals nhân viên/company bills vẫn qua Reader/matcher bình thường.
Report công bố financial imports/HUMAN_SOURCE_REVIEW, không gọi toàn bộ đầu
vào là AI tự trích xuất hoặc preparation effort0.

B5 summary chỉ decision+managed events. Để chốt whole-work A/RA/P/RP và
company-direct/duplicate checks cần company coverage tới mốc quyết toán:
owner đúng, scope/người/work/phương thức/event groups/opening balances và
missing ranges có căn cứ. Kế toán cung cấp nguồn/structured source-backed
company packet; employee không chỉnh. Vắng rows không tự zero.

Canonical B5 events và company ledger cùng namespace/ref/source alias chỉ
count một lần. Extra received event được cộng đúng scope; pending/unknown
hoặc contradiction giữ trạng thái và câu hỏi, không dùng known subtotal làm
whole A. A là gross thực nhận, không fulfilled cap2 khi actual3. Returns,
reimbursement history và incidents được giữ riêng, không normalize mất nghĩa.

Quyền settlement cần config B7 riêng. Không chuyển max_budget/max_advance
của B3Grant thành max employee-cost/net/exception của B7. Thiếu B7 rights
vẫn nhận hồ sơ/tính phần rõ rồi hỏi quyền, không fallback P-DEMO100triệu.

## 5. Đối chiếu claims và nguồn

Form rows ↔ actual expense dùng quan hệ CLAIM_EXPENSE có source support,
khác EXPENSE_PAYMENT hoặc SAME_EVENT. Row/file selection chỉ hint, không
tự ESTABLISHED. Source inventory và actual expense scope phải đủ; source
ngoài work không được cộng dù cùng amount/date. Money events không expense.

MVP một claimed row đối chiếu một expense; nhiều ảnh/trang/source cho một
expense được dùng. Một invoice cần phân bổ nhiều rows/parts mà chưa đủ căn
cứ giữ issue, không nhân đôi invoice hoặc tự chia tiền. Có thể khai một row
cho toàn dịch vụ cùng scope nếu phù hợp; không thêm category caps.

Date/purpose/ref cần theo applicability. Source date tương lai/mâu thuẫn
scope không tự pass; unknown chỉ hỏi khi field ảnh hưởng check. Claims
sum chỉ là tổng khai; T/E từ facts/parts đủ căn cứ, không từ sum form.

## 6. Context changes, Stop và clocks

Snapshot lưu tại draft/refresh. Run phải thấy snapshot current hoặc yêu cầu
refresh/recheck; publish và financial actions kiểm dependency origin/context
để parent/source/money thay đổi giữa Run không tạo current output sai.
Raw intake/source vẫn nhận khi parent Stop; linked managed Run/current output
và action giữ Stop dependency tới khi resume/recheck. Không broadcast tới
công việc không liên quan hoặc hứa bank/provider cancel.

Money/knowledge clocks backend cấp, giấu khỏi form chính. Real dùng server
time; demo chỉ có clock settlement riêng trong activated synthetic B7 config,
không dùng clock10/10 trước chuyến đi như cutoff quyết toán14/10.
Refresh source tới muộn cập nhật knowledge, không tự backdate event. New
event sau money cutoff cần mở rộng mốc có ghi version cho quyết toán current;
run lịch sử giữ nguyên. Không đánh giá source ngoài mốc rồi gán zero.

Parent/context refresh không sửa original decisions/events hoặc silently
đổi approval budget. Snapshot mới supersedes source cũ, giữ outputs/history;
không bắt nhân viên confirm lại nếu declarations không thay.

## 7. UI kết quả và ranh giới

Ba vùng: thông tin công việc/B3/B5 readonly; bảng khai thực tế+source; kết quả
đối soát/questions. Kế toán có vùng company packet/coverage và owner issues;
employee chỉ thấy phần cần bổ sung của mình, không gánh company absence.

Ví dụ đủ nguồn: actual company flight3 + employee hotel3/meal1/ground1,
B8, A2, RA=P=RP0 theo coverage => T8/E5/S+3. Chưa financial approval/chi.
Case actual hotel2,5 => T7,5/E4,5/S+2,5; không giữ forecast hotel3.
Budget exceeded => POLICY/conditional, rights thiếu => AUTHORITY riêng.

B5 incident/pending liên quan giữ blocker; không chốt proposal chi mới dù
net có thể tính một phần. S0 không close. Một active B7 trong scope tránh
hai reports thành hai nghĩa vụ; closed adjustment là chặng sau.

## 8. Bằng chứng và bàn giao

Test native/fake pipeline có gold source-first; live originals chỉ chạy với
authorization, cùng rules/path. Phải chấm facts/claims/links/money/questions/
states; không chỉ net. Input/oracle tách, không IDs/file names làm đáp án.
Prep company context/manual records vẫn được đo; không claim3 participants.

Link draft/confirm/upload, source-backed context, canonical history và
claim checks được giao tuần tự ở [plan](../plans/2026-10-11-b6-linked-settlement.md).
Không thêm auth/ERP/queue/general allocation engine hoặc bank transfer.

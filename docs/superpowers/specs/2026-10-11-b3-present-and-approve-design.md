# B3 — Trình duyệt và quyết định tạm ứng

Ngày11/10/2026. **PLANNED** — thiết kế cho lát cắt được chủ dự án yêu cầu:
kế toán trình duyệt → người có quyền APPROVE/RETURN/REFUSE → chờ chi ứng.
Chưa là năng lực runtime đã nghiệm thu. Đọc cùng Product P2a/P3 và Rulebook
R6/R8/R10; không thay quyết toán B7 bằng duyệt tạm ứng.

## 1. Phạm vi và cách làm

Dùng B3 intake đã có, cùng case/work/employee, ba vai demo và company context
backend. Mở đúng nhánh khởi tạo công tác bằng lời: chưa có quyết định công
việc/ngân sách/ứng cho đề nghị này. Căn cứ cho phép công việc được tạo bởi
quyết định của người đủ quyền trên app; không yêu cầu nhân viên upload quyết
định mà họ đang xin. Trường hợp reuse external decision/ứng thêm/đã nhận tiền
không tự chuyển thành hồ sơ initial; giữ nguồn và đưa xử lý riêng.

Một lần duyệt có ba nội dung riêng: work_allowed, budget_vnd, advance_vnd.
Không tạo approval từ chữ “chấp thuận” trong review. Không tạo thực nhận,
money event, request chi ngân hàng, handoff hoặc closure trong lát cắt này.

So với chỉ thêm nút frontend, lựa chọn này có persisted presentation và
typed B3 decision, kiểm quyền/current basis và chống lặp. Giữ SQLite/audit
hiện tại; không thêm workflow framework hoặc hệ thống tài khoản.

## 2. Trình duyệt

Kế toán được cấu hình cho nhân viên thực hiện. Người/vai phải đúng company
context, không chỉ dựa role picker. Cần bản khai confirmed, report B3 hiện
hành SUCCEEDED/COMPLETE, readiness READY_FOR_ACCOUNTANT_REVIEW, không material
issue/câu hỏi còn mở, Stop/run active hoặc company context chưa active.

Endpoint nhận một trong hai nguồn review:
- Review mới: note + refs + report_id, lưu review và presentation trong cùng
  transaction; UI “Lưu rà soát và trình duyệt”.
- Review đã lưu: review_id thuộc đúng case/current report/kế toán được phân
  công; UI “Trình người duyệt”. Không bắt lưu note cũ lần thứ hai.

Presentation lưu review/report refs, employee/work, input revision/control
epoch, signature của basis, company context/policy identity, accountant và
approver route, thời điểm. Route do backend chọn. Stage AWAITING_DECISION.
Không cho frontend gửi reviewer/approver/grants để cấp quyền.

Trình lần nữa với key cũ trả record cũ. Với key mới và cùng basis đã pending:
trả record hiện có, không tạo hai hồ sơ chờ song song. Sau RETURN hoặc stale,
presentation mới chỉ sau kiểm lại và review còn đúng/new; giữ bản cũ lịch sử.

## 3. Màn người duyệt và ba kết quả

Người duyệt thấy trip/purpose/date/deadline, số xin, bảng dự toán company–
employee, tổng, checks/issues/refs và review gắn đúng presentation. Không
lấy “review mới nhất bất kỳ” hoặc report của case khác làm căn cứ.

| Outcome | Nội dung lưu và tác động |
| --- | --- |
| APPROVE | work_allowed=true, budget_vnd>0, advance_vnd>0; ngân sách và số ứng đã duyệt giữ riêng số nhân viên đề nghị. Stage AWAITING_MONEY, chưa thực nhận. |
| RETURN | Lý do và nội dung cần sửa; ba approved fields null. Status RETURNED, stage CHECKING; nhân viên sửa/xác nhận lại, Run lại, kế toán trình lại. Không ghi refusal hoặc money0. |
| REFUSE | Lý do; ba approved fields null. Phạm vi từ chối là đề nghị tạm ứng này; không suy công tác bị cấm, không hủy B/quyết định ngoài app hoặc xóa tiền đã có. Status REFUSED. |

APPROVE dùng tổng forecast8triệu đề xuất budget8triệu và số xin2triệu làm
gợi ý, không tự cấp duyệt khi mở trang. Có thể duyệt ứng1,5triệu cho số xin2
với lý do; giữ số xin2. Không tự tạo đề nghị mới cho phần chưa duyệt0,5.

MVP này không nhận conditional approval còn điều kiện chưa giải quyết.
APPROVE budget thấp hơn tổng forecast hiện tại hoặc advance cao hơn số xin/
phần employee forecast phải RETURN để sửa và kiểm lại. Đây là giới hạn của
form quyết định initial này, không khẳng định mọi công ty phải làm như vậy.
Budget bằng hoặc cao hơn forecast phải trong quyền; mọi khác biệt với đề
nghị có lý do. Không tự sửa forecast thành approved budget để che khác biệt.

REFUSE không tự close settlement. Thêm stage ADVANCE_REQUEST_REFUSED, không
đưa vào _CLOSED_STAGES; giữ tiếp nhận nguồn và lịch sử. Không cho sửa rồi
trình lại để vượt refusal còn hiệu lực. Reopen/replacement refusal là hành
động cần quyền riêng ngoài lát cắt này; UI ghi rõ chưa có đường mở lại.

## 4. Quyền và basis

Dùng B3Grant hiện có, không dùng B7 AuthorityGrant/P-DEMO. APPROVE cần cùng
một grant đúng actor/person/work/hiệu lực: allow_work=true, budget≤max_budget,
advance≤max_advance; missing limit không unlimited. Không cộng quyền của hai
grant để tạo quyền mới. RETURN/REFUSE cần route approver và grant cho đúng
scope xét đề nghị ứng (max_advance không null và cover số đang xin), không
được dùng từ chối để né kiểm scope. Khi chưa đủ quyền, giữ pending và nêu
lý do, không tự thay người duyệt hoặc giảm tiền để lọt quyền.

Thời điểm xét quyền: giờ server, hoặc demo_clock chỉ khi activated+synthetic.
Lưu effective_at mô phỏng tách created_at thật; không lấy money_as_of cũ làm
quyền hiện tại trên dữ liệu thật. Context đang áp dụng phải được snapshot/hash.

Transaction ghi mutation kiểm expected_case_version, current report thuộc
case/current revision/epoch, readiness/issues, review source refs, pending
presentation và context/basis signature; Stop và quyền được kiểm trước write
trong cùng persisted mutation. Audit giữ body/result/actor/basis/grant refs.

Basis signature không lấy run ID/timestamp/token counts làm business facts:
hash submission form+scope, active source hashes, policy/context identity và
critical proposal/check states ảnh hưởng quyết định. Pending presentation
bị stale khi input/source/epoch/context/report basis đổi; phải Run và trình
lại. Source material sau APPROVE làm decision validity RECHECK_REQUIRED và
không tạo quyết định/chi mới. Rerun cùng business basis không bắt duyệt lại.
Stop chặn act; resume phải Run kiểm lại, không tự mở khả năng chi.

Sau APPROVE không sửa trực tiếp form thành đề nghị khác; yêu cầu adjustment
riêng ngoài slice. ADD_SOURCE và actual evidence không bị xóa; thêm nguồn
có thể khiến căn cứ phải kiểm lại. Không cho một pending presentation có hai
outcomes; same-key retry idempotent, new-key second outcome bị conflict.

## 5. Persistence và API

Không đổi schema.sql. Review dùng interactions kind REVIEW. Presentation
dùng audit_events kind B3_PRESENTED, payload typed. Decision dùng decisions
JSON kind B3_ADVANCE, outcome ba loại; audit kind B3_DECISION_RECORDED.
Không thêm kind mới vào CHECK của interactions. Trạng thái current được
xác định từ records/basis, không client PATCH stage.

CaseView bổ sung b3_workflow nullable chứa status, presentation, decision,
basis_current, decision_validity và blocked_reason. UI ưu tiên projection
này; không suy pending/approved từ free text hoặc slice(-1) mọi decision.
CaseSummary.stage/list filters cùng projection, không danh sách nói checking
trong khi detail nói chờ duyệt. B7 latest-decision/money/handoff chỉ đọc kind
SETTLEMENT; B3_ADVANCE không trở thành nghĩa vụ reimbursement B7.

API mới:
- POST /api/cases/{id}/b3-presentations
- POST /api/cases/{id}/b3-decisions

Giữ actor/demo_role/expected_case_version/Idempotency-Key envelope như API
hiện tại. Generic SETTLEMENT decision/money/handoff/closure vẫn chặn B3.

## 6. UI và test phải thấy được

Kế toán: note/refs + trình hoặc reuse review còn đúng; trả lại nhân viên là
issue/bổ sung hiện có, không giả thành quyết định tài chính. Người duyệt:
APPROVE/RETURN/REFUSE với summary/basis; nhãn quyền từ backend/context, không
“APPROVER hợp lệ” chỉ vì role picker. Nhân viên: thấy outcome/lý do/số đã
duyệt; sau RETURN được sửa, sau REFUSE không thể resubmit âm thầm.

APPROVE hiển thị “Đã duyệt tạm ứng2.000.000 đ — chờ chi ứng”. Dòng thực nhận:
“Chưa ghi nhận”, không0 hoặc “Đã chi”. Chưa có nút thực hiện chi ở slice này.

Nghiệm thu: happy2triệu, duyệt thấp hơn1,5triệu, RETURN→sửa→recheck→trình,
REFUSE không hủy work/tiền, wrong role/actor/scope/time/limit, stale/source
change/Stop, retry/double click/conflicting outcomes, cross-case review/run,
restart persistence, B3 không lọt B7 money/handoff/closure. Fake xác minh
lifecycle; UI phải thao tác hoặc ghi chưa chạy; không gọi đây là trial thật.

## 7. Giới hạn và giao việc

Một writer sở hữu models/service/store/API contracts. Backend B7 đang dirty:
đợi writer đó ổn định hoặc tích hợp tuần tự; không reset/overwrite. Frontend
nhận contract mới sau backend; không viết song song trên shared files.

Không chỉnh dataset/oracle B7, không gọi LIVE/Git/publish trong plan mặc định.
Nhánh ghi tiền B5 và liên kết nhập B7 là kế hoạch sau, không capability của
quyết định B3 này. [Plan triển khai](../plans/2026-10-11-b3-present-and-approve.md).

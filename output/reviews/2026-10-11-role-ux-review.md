# InvoiceReferee — Review UI/UX theo ba vai

Ngày11/10/2026. Review bằng3 subagent theo vai Senior Product Designer/UX Researcher
cho phần mềm kế toán nội bộ, cùng review tích hợp của lead. **Không phải thử nghiệm
với3 chuyên viên nghiệp vụ thật.** Không sửa application/test/docs canonical,
không chạy app/provider, không commit.

## 1. Phạm vi và verdict

Checkout `rebuild`, HEAD `5ffd939fbab971a876721c16a695fa752e758d79`; đọc source
dirty trên disk. Active root main.tsx dùng settlement/App.tsx, không legacy App.
CodeGraph lỗi `statInode is not a function` hai lần; dừng theo tool instructions.
Generation/index_status/check_index_coverage không expose; fallback đọc source
đúng phạm vi. Không claim audit toàn repo. Browser localhost trước đó bị từ chối
quyền: không mở lại hoặc dùng workaround. Visual/focus/accessibility/user trial
**INCONCLUSIVE**; observations **VERIFIED(source)**, hệ quả UX là suy luận,
recommendations **PLANNED**. Không chấm điểm UX bằng số khi chưa đo.

**Verdict: cần thay đổi đáng kể trước khi nghiệm thu UX theo vai.**
UI đã tách một phần action của nhân viên bằng điều kiện role, nhưng phần lớn
navigation, report và editor dùng cùng một thứ tự. Kế toán/người duyệt còn thấy
form việc của nhau. Các chỉnh chữ/bố cục trước đây chưa tạo workspace theo nhiệm vụ.

Reviewer:
- Fermat: nhân viên — nộp, bản nháp, bổ sung, theo dõi.
- Copernicus: kế toán — vướng mắc, đối chiếu nguồn, review, receipts.
- Ohm: người duyệt — gói trình, basis/quyền/chiều tiền, làm rõ/outcome.
- Lead: kiểm liên kết role/action với service/store và phân loại scope cải thiện.

Authority: PRODUCT P3/P6; RULEBOOK R8/R9; SYSTEM S6. Approval khác review/actual/
closure. B3 v1 hiện report-only; B7 có quyết định quyết toán, tiền/handoff/closure.
Đổi role demo không authentication hoặc grant. Pilot~5users, không đề xuất3apps,
enterprise RBAC/auth/queues hoặc money execution.

## 2. Findings — Nhân viên

| ID | Ưu tiên | Bằng chứng source | Tác động cụ thể / cải thiện |
| --- | --- | --- | --- |
| EMP01 | P1 | App.tsx104 filteredCases theo từ khóa;360 sửa B3 dùng b3PersonaRef;414 trả lời dùng actorId | Người đang xem, người nộp và người ghi hành động có thể lệch. Hiện rõ hai danh tính, lọc hồ sơ theo persona cho demo, guard chống sửa nhầm. UI-only chống nhầm; bảo đảm ownership thực cần backend contract |
| EMP02 | P1 | App.tsx1013 summary CTA luôn Kiểm tra bản nháp; querySelector(primaryTarget) cho issues/run-check | Nút không khớp nhiệm vụ và đích tab. Dùng Xem việc cần bổ sung/Kiểm tra lại/Rà soát bản nháp; điều hướng explicit, giữ canStartRun |
| EMP03 | P1 | App.tsx860 tạo draft không files;1229 chỉ !confirmed đã nói AI trích xuất | Tạo nháp rỗng có thể bị hiểu AI đọc thiếu. Phân biệt chưa có file, đã lưu chưa đọc, đang đọc, bản nháp chưa nộp; không lấy unconfirmed làm proof đã đọc |
| EMP04 | P2 | App.tsx192/977 dùng qs.length;Questions.tsx79 OPEN khác owner vẫn form | Lịch sử/việc người khác thành việc employee cần làm. Tách việc của bạn, chờ người khác, đã trả lời chờ recheck, lịch sử resolved |
| EMP05 | P2 | B3Intake.tsx208 dự kiến trả,287 tổng ghi Đối soát tự động/Công ty chi trả | Tổng từ khai báo dễ bị hiểu verified payment. Giữ chữ Dự kiến, phân biệt tính tổng với đối soát; chưa duyệt/chưa actual |
| EMP06 | P2 | App.tsx304 tạo case rồi uploads tuần tự;337 lỗi chung;854 không pending guard | Upload một phần rồi lỗi dễ tạo hồ sơ/trùng file mới. Báo kết quả từng file, reload sources đã lưu, tiếp tục cùng case, chống double submit |

Bố cục đề xuất: **Hồ sơ của nhân viên → tình trạng và việc của bạn → thông tin
đề nghị/bản nháp → tài liệu → bổ sung**. Report/lịch sử vẫn mở được; không lấy
traces/Verify/bảng tiền rỗng làm trọng tâm. Demo filter không có nghĩa bảo mật.

## 3. Findings — Kế toán

| ID | Ưu tiên | Bằng chứng source | Tác động cụ thể / cải thiện |
| --- | --- | --- | --- |
| KT01 | P1 | App.tsx455 decisionId từ DECISION_RECORDED gần nhất;Actions.tsx49 defaults chi/RECEIVED;240/244 dùng ID đó và refs=[] | Ghi receipt chưa thấy rõ basis/chiều/căn cứ. Trước form hiện decision/bên nhận/approved/received/remaining, chọn tài liệu receipt. Validity của decision không suy từ latest; cần backend xác nhận |
| KT02 | P2 | Actions.tsx127 render decision với cảnh báo sai role,178 mới đến review | Giao diện kế toán dẫn sang việc phê duyệt. Ưu tiên review có refs, trạng thái/next owner; ẩn form decision. Persist trình duyệt khác chỉ display và cần contract |
| KT03 | P2 | EvidenceLinks.tsx58 gom subrefs;Report.tsx297 reason không render check.refs | Mở đúng file vẫn phải tìm lại căn cứ. Cho refs theo từng check, mở rộng subrefs/locator thật; không invent page/bbox khi API không có |
| KT04 | P2 | App.tsx104/621 list theo mã/stage;CaseSummary thiếu owner/blockers/Stop | Cần mở từng case để biết việc kế toán. Stage filters làm ngay; assignment/blocker counts chính xác cần dữ liệu bổ sung, không đoán |
| KT05 | P2 | Report.tsx187 toàn facts trước issues308;294 mọi nonPASS/FAIL gọi CHỜ XỬ LÝ | Vướng mắc chìm, NOT_APPLICABLE thành việc tồn đọng. Đưa blockers/owner lên đầu, các facts rõ thu gọn nhưng truy được; Không áp dụng riêng |
| KT06 | P2 | App.tsx192/987 count mọi question;Questions render tất cả owner/status | Đã giải quyết vẫn dẫn sang giải trình. Nhóm kế toán cần trả lời/chờ recheck/chờ người khác/lịch sử; không coi ANSWERED là resolved |

Bố cục đề xuất: **Việc cần rà soát → vướng mắc → bảng đối chiếu có nguồn → review
và gói trình**. Sau decision B7: **decision áp dụng → receipts → phần còn lại**.
Tập trung giảm tìm/ghép/đọc lại, không thêm form để đạt số lượng màn hình.

## 4. Findings — Người duyệt

| ID | Ưu tiên | Bằng chứng source | Tác động cụ thể / cải thiện |
| --- | --- | --- | --- |
| AP01 | P1 | Actions.tsx43 PAY_EMPLOYEE mặc định,134 amount/direction nhập riêng;App1195 chỉ truyền reportReady | S âm vẫn bắt đầu Duyệt chi; người duyệt tự chép tiền. Hiện yêu cầu/E trước bù trừ/số đề xuất/chiều/basis/refs cạnh decision; không sửa authoritative amount ở frontend |
| AP02 | P1 | App527 role chỉ setRole;Actions63 canDecide không check actor grant;168 conditions=[] | Thấy nút không biết quyền/phạm vi/điều kiện. Hiển thị quyền đã kiểm khi backend có; không grant theo role label; conditions cần semantics thật, không biến reason thành điều kiện máy kiểm |
| AP03 | P2 | Actions178 review form chung;App1455 audit detail JSON | Người duyệt không biết kế toán đã review report nào. Hiện ai/khi nào/nội dung/basis; phân biệt review hiện hành/cũ/chưa có. Không thêm gate bắt buộc review nếu contract chưa yêu cầu |
| AP04 | P2 | App104/600 list chung;uiState146 nói phê duyệt trong khi Actions119 B3_REPORT_ONLY | Không có danh sách việc rõ và B3 gây kỳ vọng giả. Lọc theo stage, B3 xem report khác B7 quyết định; chưa có assignment thì không gọi Cần tôi duyệt |
| AP05 | P2 | Actions134 chỉ chi/thu/refuse;Questions trả lời danh sách có sẵn | Chưa có thao tác human khởi tạo yêu cầu làm rõ trong slice đã đọc. Thao tác này cần lưu owner/refs/status/recheck, không thêm nút giả hoặc dùng REFUSE thay |
| AP06 | P2 | uiState166 summary dựa checks;Actions77 tiền riêng;App454 latest decision | Theo dõi xong kiểm tra không nói quyết định đang chờ ai/thực hiện bao nhiêu. Thẻ outcome decision/direction/remaining/pending/incidents; validity từ backend |

Bố cục đề xuất: **Hồ sơ cần xem xét → yêu cầu/phạm vi → tóm tắt tiền → review
kế toán → quyền và điểm cần quyết → decision/làm rõ → kết quả thực hiện**.
Nguồn/report đầy đủ và history vẫn truy cập được, không bắt người duyệt mở toàn
bộ facts trước khi hiểu đang xin quyết định gì.

## 5. Review tích hợp của lead

### 5.1 Các phát hiện quan trọng đã kiểm tra lại

- App527 đổi role không đổi actor; App245 chọn persona B3 còn đặt role EMPLOYEE.
  Đây là context demo không đồng bộ, không bằng chứng có authentication thật.
- Actions110 chỉ tách employee bằng notice; accountant/approver chung nhánh.
  Form decision có cảnh báo không APPROVER, review form cũng hiện cho APPROVER.
- Service.review391 chỉ cho ACCOUNTANT; decide346/358 cần APPROVER+grant và
  chặn B3 v1. UI thấy form không nghĩa có quyền thực hiện; bấm rồi403 là chi phí
  thao tác có thể tránh, chưa phải bằng chứng vượt được backend.
- Report294 thật sự gọi NOT_APPLICABLE là CHỜ XỬ LÝ,297 không mở check.refs.
  Đây là lỗi biểu đạt, sửa riêng với calculation/eligibility logic.
- Store.record_review934–966 chỉ ghi review/report/note/refs, tăng version và audit;
  bản ghi review không tự có nghĩa đã trình hoặc đã duyệt. Đề xuất nút Trình duyệt
  cần xác định hiệu ứng/persistence, không chỉ đổi tên Lưu review.
- B7 runtime default grant ở api/settlement.py62 là actor P-DEMO; persona B3
  APR-DEMO-01 và B3 rights context là cơ chế khác. Không tự gán đủ quyền B7 vì
  dropdown hiện tên người duyệt B3; profile demo phải phù hợp grant job hiện tại.

### 5.2 Biện luận độc lập

**Đồng ý** đổi theo nhiệm vụ từng vai; **không đề xuất3ứng dụng/3backend**.
Một dossier, một nguồn dữ liệu, shared sources/history/controls; ba góc nhìn
khác về ưu tiên, navigation và hành động. Style/component dùng chung vẫn hợp lý.
Ẩn vài nút mới giải quyết một phần, không thay thế thông tin riêng cho mỗi vai.

Không phải mọi vấn đề đều UI-only. Điều hướng CTA, nhãn/trạng thái, nhóm câu hỏi,
show đúng action, thu gọn kỹ thuật có thể làm trước. Assignment chính xác, trình
duyệt bền vững, human request-for-clarification và current decision validity có
thể cần contract/backend nhỏ. Không thêm queues, notification services hoặc RBAC.

Vai duyệt B3 hiện thiếu capability tài chính thật. Một trang đẹp không hoàn thiện
được nhánh đó. Thiết kế hiện tại phải trung thực là xem report; nếu muốn approve
work/B/advance trong app, cần thiết kế action/basis/authority/audit/gates riêng.

Không lấy quyết định gần nhất làm đang áp dụng, không biến review thành approval,
hoặc chữ Dự kiến thành actual. Giảm chỗ hiển thị không được giấu dữ kiện trái nhau,
nguồn chưa rõ hay receipt một phần.

## 6. Cấu trúc ưu tiên đề xuất

| Vai | Danh sách mặc định | Màn chi tiết mở đầu | Hành động chính |
| --- | --- | --- | --- |
| Nhân viên | Hồ sơ mình nộp theo demo persona | Đang ở đâu, mình cần làm gì, bản nháp/đề nghị | Nộp, xác nhận, bổ sung, trả lời việc mình |
| Kế toán | Theo stage: rà soát/chờ decision/đối chiếu tiền | Blockers/owner, khoản chi và nguồn, review hiện tại | Đối chiếu, xử lý facts, lưu review; ghi receipts đúng decision |
| Người duyệt | Hồ sơ cần xem xét theo stage, không giả assignment | Đang xin gì, tiền/chiều, review, basis/quyền | B7 quyết định trong quyền; B3 xem report đến khi có capability thật |

Role context phía trên: người thao tác+vai, người nộp hồ sơ riêng. Dùng roster
demo có sẵn, không field role đổi độc lập rồi kỳ vọng actor/grant cũng đổi.
Các phép chọn persona/filter chỉ quản lý trải nghiệm, không quảng cáo security.

## 7. Thứ tự cải thiện và tiêu chí nghiệm thu đề xuất

1. Khóa nhầm context/actions: actor/role nhất quán, form đúng vai, CTA đúng tab/
   state; chữ chưa upload/chưa đọc/chưa nộp/chưa duyệt đúng record.
2. Ba ưu tiên màn chính: hồ sơ/việc nhân viên; ngoại lệ/căn cứ/review kế toán;
   gói trình/basis/decision/outcome người duyệt. Dùng shared dossier/components.
3. Review contract cho phần chưa có dữ liệu/capability; tách task thật khỏi UI-only.
4. Fake/RTL kiểm states/actions/payload rồi browser/user walkthrough khi có quyền.

| Case | Điều cần kiểm, chưa chạy trong review này |
| --- | --- |
| Demo đổi EMPLOYEE→ACCOUNTANT→APPROVER | Danh tính thao tác rõ và đúng config, employee owner không đổi theo role |
| Nháp chưa có file / đã lưu chưa đọc / đọc lỗi / có report | Không trạng thái thành công giả; CTA mỗi state làm đúng một việc |
| Questions OPENNV/OPENKT/ANSWERED/RESOLVED | Đếm theo owner/status, không buộc giải trình việc đã xong hoặc của người khác |
| Hai files, file2 lỗi | Cùng case còn file1, có retry bổ sung phần thiếu, không duplicate case |
| Kế toán có1conflict trong nhiều facts rõ | Tìm được blocker/nguồn từ màn chính; NOT_APPLICABLE không thành việc chờ |
| Người duyệt B7 net âm, review basis cũ | Chiều tiền/basis rõ, review cũ không được gọi là review hiện tại |
| B7 duyệt3M thực nhận2M | Approved3/received2/remaining1, không auto đóng hoặc chỉnh tiền |
| Người duyệt B3 report-only | Không nút fake approve; capability hiện hành rõ, không mặc định grant B7 từ B3 |

Đo với chủ dự án rồi người làm nghiệp vụ thật: thời gian tìm việc phải làm, tìm
đúng nguồn, số click/lần phải giải thích, thao tác nhầm vai và nhầm trạng thái.
Subagents không thay professional-user trial; screenshots/code không prove giảm
công sức nếu chưa có đối chứng.

## 8. Giới hạn và handoff

Không thực hiện các cải thiện. Các line numbers là source on disk tại lượt review,
refresh trước coding vì còn user edits. Khuyến nghị là cơ sở để cùng chủ dự án
chốt role workflow rồi viết plan tiếp; không tự thực hiện plan UX cũ bằng review này.
Không tạo layer auth/task queue/framework. Không tests/live calls/commits ở lượt này.

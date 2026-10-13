# Tổng hợp và phản biện của lead — review final 13/10/2026

## 1. Verdict cập nhật và phạm vi

**Giữ hướng đề A và kiến trúc chính; chưa giao bản hiện tại như contract đã khóa cho coding agent.**
Ba review mới trên cùng snapshot đưa ra 41 findings (12 + 15 + 14). Đây không là
41 bug được chạy lại: có finding trùng nhau, thiếu cụ thể hóa contract, công việc
triển khai đã công bố, và bằng chứng bên ngoài chưa có. Không dùng số reviewer
đồng ý hay độ dài báo cáo để chứng minh kết luận.

Tôi điều chỉnh cách nói “đủ lập plan” ở vòng trước: framing và lựa chọn chính
đã đủ vững, nhưng vẫn cần khóa một số ngữ nghĩa/acceptance hữu hạn để tránh hai
implementer làm ra hai kết quả tài chính khác nhau. M0, code, gold, public demo,
trials là tasks của plan, không phải điều kiện phải hoàn thành trước khi được lập plan.

Các reviewer đều GPT6 Web High, context riêng, không hạn số từ/findings:
- [Ramanujan — đề thi và nghiệp vụ](contest.md): 12 findings.
- [Mencius — kiến trúc và tiền](architecture.md): 15 findings + 16 counterexample scenarios.
- [Hegel — evaluation](evaluation.md): 14 findings.
- [Phản biện tiếp/đính chính của Mencius](architecture-addendum.md): giữ nguyên văn
  phản hồi sau ba counterarguments của lead. Báo cáo đầu không bị sửa mất.

Nguồn thiết kế/đề/glossary giữ nguyên trong vòng review, hash tại [README](README.md).
Các báo cáo không tự thay Q1–Q30 hoặc trở thành policy hiệu lực. Đây là review
thiết kế, không chạy OCR/model ứng dụng, code/unit/UI/Verify/LIVE hoặc practitioner trials.

## 2. Các vấn đề thực sự cần sửa

### 2.1. Financial reality, authority và fulfillment phải là ba lớp

[A02/A03/A11](architecture.md) phát hiện nguy cơ gộp tiền đã xảy ra với request và
quyền. Tôi nhận nhu cầu phân lớp, nhưng bác việc loại tiền thật khỏi phép tính
chỉ vì không thấy grant lịch sử. Reviewer đã rút lại cách diễn đạt đó trong
[đính chính](architecture-addendum.md).

Ví dụ E8/A0/P5/R0: claimant đã nhận P5 đúng scope thì S3, không S8, dù giao dịch
có bằng chứng trái quyền. Lỗi quy trình có thể chặn action tiếp theo, không xóa P.
Nếu chưa xác minh đã nhận thì P unknown, không P0/P5 mặc định. Thiếu hồ sơ grant
khác chứng minh giao dịch trái quyền; không ép duyệt lại mọi historical payment.

Actual overpayment cũng phải giữ đủ: instruction4, received5 thì actual P5 và
valid fulfillment tối đa4; phần thừa1 là issue cần đối chiếu. Không dùng phần
fulfillment hợp lệ4 để che số thật5. Bank reversal phải liên kết event gốc và
chỉ sửa net effect có căn cứ, không biến thành R của nhân viên nếu ngân hàng là
bên trả lại. Chuyển nhầm người giữ actual audit nhưng không credit vào P claimant.

Acceptance phải pin được: I4 đã trả2 thì còn một nghĩa vụ2, không vừa I.remaining2
vừa I2 mới cho2; same transaction qua command IDs khác không double count; Stop/
basis change không tự giải phóng phần đã bàn giao mà execution còn unknown.

### 2.2. Phạm vi ngân sách cần root ổn định, không budget reservation phình to

[A01](architecture.md) đúng ở nguy cơ hai dossier của cùng hoạt động mỗi cái kiểm
T4 <= B6 nhưng tổng8 vượt6. Tuy nhiên hủy reimbursement không hủy chi phí nhân viên
đã trả. Tôi bác giải pháp giải phóng T chỉ vì instruction bị hủy; reviewer đồng ý.

Phương án nhỏ đề xuất: một hồ sơ quyết toán gốc cho cặp tổ chức/claimant/activity;
nộp thêm là revision, uniqueness trong DB; assessment đọc toàn expense set hiện
hành. Cùng invoice qua ảnh/PDF/revision/profile vẫn cần economic identity/usage,
không chỉ case uniqueness. Reservation chỉ chống cover cùng nghĩa vụ hai lần,
không làm nguồn xác định T. Nếu mở nhiều claimant/activity sau này mới xét thêm
aggregation/budget reservation rộng.

Đây là cụ thể hóa scope đã chốt, không đề xuất IAM, ERP, queue hoặc event-sourcing
framework. Cần xác định activity identity có căn cứ, không auto merge hai chuyến
chỉ vì cùng người/địa điểm/số tiền.

### 2.3. Nguồn hỗ trợ fact phải thành bảng điều kiện cụ thể

[A04/A05/A06/A09](architecture.md) và [EV-06](evaluation.md) cần chuyển thành:
- Bảng fact/relation -> loại căn cứ được nhận, scope/actor/effective time/locator.
- Tách document, expense, payment transaction và reimbursement usage identity.
- PDF container có các evidence units trang/đoạn; một file chứa nhiều role.
- History coverage đúng người/hoạt động/quỹ/loại dòng tiền, mốc và opening balance.

Ref tồn tại không chứng minh guest trên invoice là payer. Invoice total không
chứng minh actual received. Amount/date bằng nhau không chứng minh giao dịch trả
đúng invoice. Human sửa draft không tự biến declaration thành chứng cứ tiền.

Nhận C03 về nguy cơ hỏi kế toán mọi routine, nhưng không kết luận mọi case thiếu
ledger là “chuyển thừa”: nếu contract yêu cầu history mà input thực thiếu thì FACT
đúng. Phải đo thêm tỷ lệ dữ liệu tổ chức đã sẵn và effort bổ sung context. Org-context
demo có closed-world boundary/ledger/grants được công bố, không tự phát minh zero
theo tên case. Routine mới với đủ context phải tự chạy; bỏ coverage phải hỏi đúng.

### 2.4. Metric hiện tại bỏ lọt kết luận sai không tạo yêu cầu

Tôi nhận [EV-05](evaluation.md) là lỗi thực chất trong định nghĩa phép đo ở
[thiết kế:322](../../ARCHITECTURE_AND_EVALUATION.md#8-đánh-giá-độc-lập-và-verify).
Tử số chỉ đếm human-required bị tự phát hành action quá hẹp.

Gold yêu cầu FACT vì thiếu coverage, app chốt “cân bằng S0” nhưng không có
instruction: vẫn là false-pass nguy hiểm. Cần separate unsafe action và unsafe
affirmative conclusion, union theo dossier không đếm hai lần; thêm route missing/
wrong owner, unresolved không có câu hỏi actionable và technical failure riêng.
Completion denominator gồm toàn bộ submissions; technical abstention không là
escalation đúng hoặc an toàn đã chứng minh bằng rate0.

Ba đơn vị: dossier outcome, issue-stage theo revision/dependencies, recovery
opportunity trước chọn bước. Tách raw unassisted extraction, draft corrections,
business outcome sau nộp và assisted resolution; không che lỗi initial bằng kết
quả sau người đã bổ sung thông tin/ngoại lệ.

### 2.5. Adaptive threshold cần đối chứng đúng, không thêm calls rồi gọi “học”

Nhận [EV-01/02/03/04](evaluation.md). Feedback của nhánh H đã chọn không cho biết
R bị bỏ qua sẽ đọc được hay không; success trên các case đã chọn R dễ không thể
suy ra success cho case khó. Chỉ giảm threshold hoặc tăng calls chưa đáp ứng proof.

Phương pháp nhỏ đề xuất:
1. Freeze snapshot trước decision, features quan sát trước chọn bước, candidate
   action R/H và budget; facts/rights guard không đổi.
2. Trên packet được kiểm/gold độc lập, chạy paired H và R offline; nguồn mới do
   người bổ sung không được lọt vào snapshot initial của R.
3. Select threshold trên feedback/development đã kiểm; validation khác, phải có
   case thật đổi action, có nhóm recovered/irrecoverable và gần boundary.
4. Gates theo thứ tự safety -> đúng routing/completion -> resources. Thiếu support,
   không có flip hoặc có critical false-pass thì không activate.
5. Log scores/threshold/version/action/evidence/outcome/feedback/selection/validation/
   activation/rollback. Holdout cuối không chọn model/threshold.

Đây là cách bảo vệ requirement bằng changed end-to-end routing, không sự xác nhận
BTC đã chấp nhận mọi cách diễn giải recovery threshold. Không cần bandit/classifier
training hoặc platform ML khác. Giá trị N/margin/buckets là lựa chọn kỹ thuật phải
công bố trước đo, không lấy một con số tùy ý làm bảo đảm thống kê.

### 2.6. Gold/15 cases/20 holdout phải khác bảng inventory

Nhận [C07](contest.md), [EV-06/08/09/10/14](evaluation.md):
- Gold ba lớp: latent synthetic truth; facts/relations có thể biết từ raw/context;
  hành vi được phép theo policy/grant/revision.
- Giữ latent amount450 nhưng làm mờ raw450/480: FACT đúng, đoán450 không được thưởng
  như auto đúng. Provider/expected không được nhìn latent truth/oracle.
- >=15 packets của profile đang claim trước gate mở rộng; negative/outside scope
  là cases có lý do, không cộng profile chưa mở hoặc clone để đủ số.
- 20 holdout10/10 freeze/split theo nghĩa vụ gốc; source family/layout/issuer là
  axes cần công bố, không giả mọi tài liệu đổi số cùng template đều độc lập.
- Paired metamorphic variants kiểm E/S/B/grant/scope/time/payer/coverage/refs không
  cộng thêm vào denominator unique dossiers.

0/10 misses không là 0% rủi ro production. Tính minh họa dưới giả định iid Bernoulli:
upper bound một phía95% khi0/10 khoảng25,89%; khi0/20 khoảng13,91%. Giả định iid/
representativeness chưa được thiết lập cho synthetic purposive set, nên những số
đó không là CI production của dự án. Giữ count/denominator/strata và scope claims.

### 2.7. Handoff và câu hỏi phải được người dùng sử dụng được

Nhận [C02/C04/C06](contest.md), [EV-07/11/12](evaluation.md):
- Instruction đủ người/chiều/số tiền/căn cứ/hiệu lực và thông tin thực hiện đúng
  phương thức demo; không bắt eligibility review/tính lại routine.
- Card hiện known facts/crop hoặc excerpt/policy/action/impact/owner; một response
  giải đúng issue, không phải mọi vấn đề của toàn hồ sơ.
- Public có đường thử raw mới trong org-context mẫu và đường thiếu context với
  câu hỏi cụ thể; không hardcode zero/B/grant để làm máy chạy.
- Trial >=3 professionals đo cả effort draft/context/kiểm tra/sửa/câu hỏi/chờ và
  công việc được chuyển sang actor khác. Tách hands-on, machine wait, elapsed và
  tác động onboarding/overreliance/gián đoạn phối hợp, không chỉ tốc độ OCR.

M0/Verify/Public runtime/professional evidence chưa có là work items/gates của
plan, không phải bằng chứng thiết kế không thể được lập plan. Điều kiện dự thi/
lịch sử/Sprint2 là external fact cần xác minh; không suy đội đã bị loại từ việc
source không chứa thông tin đó. Không liên hệ BTC/người khác trong vòng review này.

## 3. Một quyết định domain cần user: Q31

[A08](architecture.md) ban đầu mặc định T theo paid-cash. Sau phản biện, reviewer
rút lại và đánh dấu cần chốt domain trong [addendum](architecture-addendum.md).

Counterexample: dịch vụ10 triệu đã cung cấp và toàn nghĩa vụ được xác minh;
employee trả5, company trả3, còn chưa trả2; B8.
- Kiểm theo đã thanh toán: T8, chưa vượt B tại thời điểm kiểm.
- Kiểm theo chi phí đã phát sinh: T10, POLICY vượt B2.
- E vẫn5 nếu đủ điều kiện; C vẫn3; không tự cộng unpaid2 vào E/C.

Tôi đề xuất kiểm B theo **chi phí công việc đã phát sinh được xác minh**, không
theo cash đã chuyển. Không coi face value invoice là incurred amount tự động nếu
nguồn thể hiện tranh chấp/giảm giá/chưa nhận dịch vụ. Không thêm vendor payment/
accounts payable workflow. Rule này ảnh hưởng gold và eligibility nên không để
builder tự chọn hoặc tự coi Q29 đã chốt ý nghĩa này.

**Q31 đã chốt trong turn này:** người dùng chọn “Chi phí đã phát sinh (Đề xuất)”.
T tính chi phí công việc đã phát sinh và được xác minh cho kiểm B. E/C và S vẫn
theo actual paid/received đúng scope. Bổ sung được ghi sau snapshot review, không
tự nhận toàn bộ các đề xuất kỹ thuật khác đã được áp dụng hoặc đã chạy.

## 4. Disposition từng finding

“Nhận” là lead nhận hướng sửa/acceptance cho bước sau, không có nghĩa đã sửa app.
“Builder task” không là blocker phải đo xong rồi mới được viết plan.
“Nhận một phần” phải đọc addendum/counterargument, không chép báo cáo đầu vào spec.

| ID | Disposition lead | Việc cần đưa vào contract/plan |
| --- | --- | --- |
| C01 | External unknown; không suy loại thi | Preflight quyền/vòng/lịch nộp/repo khi claim eligible |
| C02 | Nhận | Executable instruction và test người thực hiện không suy lại eligibility |
| C03 | Nhận có phân biệt denominator | Org-context/coverage đủ vs thật thiếu; effort cung cấp nguồn riêng |
| C04 | Nhận | Answerable-from-card rubric + đúng owner/nguồn/impact |
| C05 | Nhận | Decision table thiếu B/không B/ngoại lệ/cấm/unsupported |
| C06 | Nhận | Hai tuyến public input mới, context mẫu vs missing, không bịa context |
| C07 | Nhận checklist | >=15 raw packets cho profile thực mở; tránh inventory/clone counts |
| C08 | Builder/runtime gate | Public Core4/Esc5/latency/audit/control thực đo |
| C09 | Nhận protocol; evidence external thiếu | >=3 practitioners + paired comparable tasks/total human effort/negative effect |
| C10 | Giữ quyết định; thêm probes | Synthetic8/4/20, cross-boundary và scope/time, không chuẩn ngành |
| C11 | Nhận | Applicability material/unrelated/unknown, không blanket block và không bỏ tiền |
| C12 | Builder task đã thuộc scope | Server persona/sandbox/audit, không claim identity pháp lý |
| A01 | Nhận sau thu gọn; bác release actual T | Canonical dossier+revisions/DB unique, toàn expense set; no budget-reservation engine |
| A02 | Nhận sau sửa nghĩa “hợp lệ” | Actual confirmed đúng scope vào S; authority compliance riêng; linked reversal |
| A03 | Nhận | Obligation vs instruction coverage vs actual fulfillment; no duplicate remainder |
| A04 | Nhận | Doc/expense/payment/use identity riêng, company+employee portions, uncertain FACT |
| A05 | Nhận | Critical fact/relation admissibility table, ref support không chỉ existence |
| A06 | Nhận | Negative coverage quỹ/kỳ/opening/scope/owner/provenance |
| A07 | Nhận | Policy/cost effective time khác grant/commit time, explicit retroactivity |
| A08 | Q31 đã chốt; bác mặc định cash | T chi phí đã phát sinh cho kiểm B, không mở vendor AP |
| A09 | Nhận | Evidence units page/segment trong PDF mixed roles |
| A10 | Nhận | State transition/predicate table, late/stale/Stop/handed-off/replay |
| A11 | Nhận sau đính chính; bác xóa P | Actual/history khác proven governance incident; full obligation guard, no mandatory historic reapprove |
| A12 | Nhận | Permissions per action và exact exception effect, recheck issue còn lại |
| A13 | Builder contract | AssessmentInput immutable/read-set versions/Result, pure Reconciler |
| A14 | Builder task đã thuộc scope | Server-issued session/actor/grants, isolation/reset scope |
| A15 | Builder/M0 task | Finite ceilings/read coverage NOT_READ khác missing, no fake business escalation |
| EV-01 | Nhận | Unit recovery opportunity, real routing flip và supported completion |
| EV-02 | Nhận | Paired offline R/H, selection bias/uncobserved branch không label giả |
| EV-03 | Nhận | Verified label protocol, raw/draft/business/assisted tách, routine audit coverage |
| EV-04 | Nhận | Preregistered activation/support/validation/flip/gate/version/rollback |
| EV-05 | Nhận lỗi phép đo | Unsafe action + unsafe conclusion union, no false safety via S0 |
| EV-06 | Nhận | Latent/observable/allowed gold và independence/provenance |
| EV-07 | Nhận | One-response card rubric, actor test, judge false-pass probes |
| EV-08 | Nhận với scope thống kê | Strata/split/counts; balanced20 không risk/ROI production |
| EV-09 | Nhận checklist | Raw distinct packets/active profile, variant không unique count |
| EV-10 | Nhận | Dossier/issue-stage/opportunity units, multi-label dependencies, technical + assistance |
| EV-11 | Nhận protocol | Before-after job endpoint/total human work/negative burden/consent |
| EV-12 | Builder/runtime gate | Same raw application path + modes + timestamps/DB outcomes |
| EV-13 | Builder/M0 task | All attempted/failures/config/time/usage, fair model comparison |
| EV-14 | Nhận | Metamorphic boundaries và independent literal oracle, không Cartesian explosion |

## 5. Thứ tự xử lý đề xuất

1. Áp dụng Q31 đã chốt và bổ sung bảng contract nhỏ: canonical scope; fact/coverage/admissibility;
   actual/fulfillment/reversal; permission/effective time; state transition.
2. Khóa evaluation contract: gold3 lớp, metrics/denominators/stages, question rubric,
   paired threshold validation, manifest/split/professional protocol.
3. Từ contract lập implementation plan có tests phản ví dụ cụ thể, mỗi milestone
   có kiểm trên UI. Không chép nguyên 41 findings thành 41 features hoặc files.
4. Tạo raw/gold, code fixed baseline/M0 và Verify, rồi đo model/limits/public
   runtime. Feedback/trials là nhánh evidence thật, không dựng giả hoặc bỏ khỏi report.
5. Chỉ claim adaptation/quality/impact trong đúng dataset/mode/version và người
   đã thực tham gia. Không dùng slide/trace xanh/reviewer đồng thuận thay kết quả.

Chưa thay kiến trúc chính, mở refund/FX/multi-claimant, gọi pipeline live hoặc code
ứng dụng. Không coi việc đã đồng ý Q1–Q30 là miễn cụ thể hóa các contracts cần thiết.

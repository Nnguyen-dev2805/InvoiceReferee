# Independent plan review — architecture, financial contracts, execution (Galileo)

**Ngày:** 13/10/2026 · **Vai trò:** independent reviewer, document-only Verify tier · **Phạm vi chính:** T1–T8, giao diện liên task, tiền/quyền/trạng thái/atomicity; chỉ xem T9–T13 khi là consumer của giao diện đó.

**VERDICT DUY NHẤT: CHANGES REQUIRED BEFORE INDEPENDENT IMPLEMENTATION OF THE FINANCIAL WORKFLOW.** Kiến trúc một FastAPI app + SQLite + Reconciler pure + CaseWorkflow transactional **đủ hợp lý để giữ nguyên**. Tuy nhiên, plan/contract hiện còn một số lựa chọn có thể khiến hai coding agent độc lập ghi nhận *hai nghĩa vụ tiền hoặc hai trạng thái* khác nhau trên cùng sự kiện. Cần sửa hữu hạn các hợp đồng giao nhau bên dưới trước khi giao riêng T3/T6/T7/T8. T1, phần nền T2 và việc chuẩn bị raw packets **có thể bắt đầu**; verdict này **không đòi** phải chạy M0, có app hoàn thiện, có gold/trials, hay đạt runtime tests trước khi cho phép lập/sửa plan.

## Snapshot, căn cứ và mức độ chứng minh

Hai file đã đọc trực tiếp, SHA-256 **khớp chính xác** snapshot giao review:

- **P** = [`docs/superpowers/plans/2026-10-13-invoice-referee-final.md`](../../../superpowers/plans/2026-10-13-invoice-referee-final.md), `5656076bbe90c5ef138ef2672b82a3576b4f960d2468ade6744f143865f59637`.
- **C** = [`docs/final/IMPLEMENTATION_CONTRACTS.md`](../../IMPLEMENTATION_CONTRACTS.md), `b459b1a99df2a019527da5cfc75b58c5f4a386f5c5ec33bf5451e11ac44a0893`.
- **Q** = [`docs/final/ARCHITECTURE_AND_EVALUATION.md`](../../ARCHITECTURE_AND_EVALUATION.md), Q1–Q31, nhất là **L79–112, L114–144, L198–233, L432–442**.
- **D** = [`docs/final/reviews/2026-10-13/SYNTHESIS.md`](../2026-10-13/SYNTHESIS.md), nhất là **L27–84, L192–220**. Disposition của lead là ngữ cảnh quyết định, **không** tự chứng minh plan đúng.
- **B** = [`docs/Challenge_Brief_OrganizationAI_VN.docx.md`](../../../Challenge_Brief_OrganizationAI_VN.docx.md), nhất là **L41–83, L191–206**. [`GLOSSARY.md`](../../../../GLOSSARY.md) được dùng để kiểm tra nghĩa “chi phí nhân viên đã thanh toán” và “cân bằng nghĩa vụ tiền”.

`L` dưới đây là **số dòng trong file** trên snapshot đã kiểm, không phải dòng code chạy. Parent đã báo CodeGraph dự án chưa có index; không có graph generation/coverage có thể xác nhận, và các công cụ graph coverage không sẵn dùng trong dispatch. Tôi chỉ đọc văn bản non-code; không kiểm code, call-chain, Git history, OCR/model, server, test, performance hay API thật. Không suy phủ định về runtime từ việc tài liệu chưa ghi một chi tiết. “Blocker” ở đây có nghĩa **hợp đồng giao agent còn thiếu/ngược nhau**, chưa phải bug đã tái hiện.

## Những lựa chọn nên giữ

1. **Bounded autonomy đúng trọng tâm.** Q L12–17, L186–196, P L5–19, C L43–60 giữ AI ở khâu đọc/đề xuất, còn kiểm fact/quyền/tiền và commit là deterministic; routine không mặc định bị chuyển kế toán. Không cần LangGraph, microservices, IAM thật hay ERP để đạt mục tiêu pilot.
2. **Ba lớp tài chính đã tách đúng.** Q L81–105, D L29–49, C L72–114 phân biệt **T incurred**, **E/C paid portions**, **A/P/R actual received**, **instruction và fulfillment**. Tiền đã xác minh không biến mất chỉ vì thiếu grant lịch sử; tiền chưa xác minh vẫn unknown. Đây là cải thiện thiết kế quan trọng, nên giữ.
3. **Q31 được bảo toàn ở contract gốc.** T dùng *chi phí công việc đã phát sinh có căn cứ*, không cắt theo B và không đồng nhất hóa đơn với dịch vụ đã phát sinh (Q L432–442; C L72–77); không mở vendor payable.
4. **Có điểm chặn atomicity đúng.** C L147–183 đặt read-set, epoch, persistent jobs, provider I/O ngoài transaction, idempotency event khác command ID. P L204–221 có race/restart checks. SQLite + một process/2 workers là đủ làm giả định pilot kiểm được nếu implement đúng transaction boundary.
5. **Tests nêu nhiều counterexample thực.** P L107–125, L165–221 có payer unknown, thiếu lịch sử, overpay, reversal, stale/Stop, supplementary expense; P L145–163 có mixed-role PDF/NOT_READ. M0 là việc phải *thực hiện rồi đo*, không phải một kết quả đã được plan chứng minh.

## Findings chặn giao độc lập T3/T6/T7/T8

### AR-01 · P1 BLOCKER — `S` hiện tại và instruction đã phát hành chưa có quy tắc phân bổ nghĩa vụ còn lại

**Nguồn:** C **L32–35, L96–114, L247–270**; P **L165–183, L185–202**; Q **L139–144, L209–216**. `AssessmentResult.allowed_effect` chứa đề nghị thu/chi theo projection S, trong khi CaseWorkflow giữ instruction đã phát hành và số fulfilled. Tài liệu nói “một active Instruction cover toàn uncovered S”, “không I2 trùng” và cho phép supplemental portions, nhưng không định nghĩa cách tính **chưa được instruction nào cover** khi S thay đổi.

**Phản ví dụ:** Tại t0, `E6, A2, P0, R0 → S4`, issue **I4**, chưa thực hiện. Retry/Submit/Resume ở t1 vẫn `S4`: `Reconciler` pure hoàn toàn có thể trả `allowed_effect=PAY4` lần nữa. Nếu workflow chỉ so command ID thì tạo I4 thứ hai ở command mới. Tại t2 nhận thực P2, `S2`, I4 `remaining2`: nếu tạo `I2` từ S mới sẽ đòi thêm tổng 4 thay vì 2. Tại t3 nhận chứng từ hợp lệ làm E tăng 2, `S4`, I4 `remaining2`: số phát sinh mới đúng 2 **có thật**, nhưng quy tắc “một active instruction” không nói amend/supersede I4 hay phát hành delta2. Nếu I đã bàn giao ngoài app và execution chưa rõ thì không được âm thầm thay thế.

**Sửa tối thiểu:** Khóa contract *obligation coverage* tại ranh T3→T6→T7, bao gồm hướng và basis; định nghĩa chính xác (a) số nợ thực theo S hiện tại, (b) phần đã giao bởi active/handed-off instruction, (c) phần eligible để issue mới, (d) khi nào suspend/supersede và nối `supersedes_id`, (e) hành vi khi handoff `EXECUTION_UNKNOWN`. `allowed_effect` là pure proposal, **workflow** phải có quy tắc trừ coverage trước commit dưới cùng khóa/read-set. Nếu chính sách một-active/root vẫn giữ, plan phải quy định cụ thể phương thức thay thế instruction khi phát sinh legitimate delta, bảo toàn bản đã trả/đang trả và audit.

**Acceptance bắt buộc:** 4 mốc trên chạy cùng root/DB; sau t1 đúng **một I4**; sau t2 **I4 còn 2, không I2**; sau t3 tổng nghĩa vụ chưa thực hiện là **4**, không bỏ delta2 hay đòi trùng; nếu handoff chưa xác minh thì không release/supersede tự động. Hai worker/command IDs khác nhau cho kết quả tương đương. **Không phải user business choice mới** nếu chỉ chốt representation/commit; nếu muốn đổi nguyên tắc “một active instruction” đã được chọn thì cần ghi riêng để người dùng quyết định.

### AR-02 · P1 BLOCKER — Reversal phải điều chỉnh *net fulfillment* cùng với money projection

**Nguồn:** C **L79–89, L100–111, L151–168**; P **L185–202**; D **L36–49**; Q **L214–226**. Đã có linked REVERSAL và khẳng định “bank refund P giảm P, không tạo R”. Nhưng `Instruction.fulfilled_amount`/`remaining` chưa nói là gross hay *net of reversed receipt*, và test T7 chỉ kiểm reversal **không thành R**, chưa kiểm instruction sau reversal.

**Phản ví dụ:** `I4`; ghi P2 bằng event k1 ⇒ I fulfilled2/remaining2. Ngân hàng reversal k1 toàn phần2 ⇒ `P=0`, `R=0`. Nếu fulfilled vẫn 2, app chỉ chờ 2 trong khi thực tế chưa trả được đồng nào; nếu tạo một instruction I2 mới, lại trùng coverage I4. Trường hợp I4 đã FULFILLED rồi bị reversal cũng phải mở lại nghĩa vụ thay vì giữ SETTLED.

**Sửa tối thiểu:** Giữ append-only gross history và linked reversal nhưng xác định *effective net confirmed receipt* dùng riêng cho P/R và *effective net fulfillment* gắn từng instruction. Định nghĩa reversal một phần, nhiều reversal không vượt outstanding gốc, cùng source duplicate, và trạng thái `FULFILLED → PARTIAL/ISSUED` sau confirmed reversal; nếu execution chưa chắc, ghi `EXECUTION_UNKNOWN` và không issue mới. Không biến bank reversal thành nhân viên hoàn tiền.

**Acceptance:** I4→P2→reverse2 ⇒ P0/R0, I.remaining4, đúng một instruction còn hiệu lực và audit đủ ba sự kiện; I4→P4→reverse1 ⇒ P3, remaining1, không SETTLED; double reversal hoặc reverse quá gốc bị từ chối có giải thích. Chạy cả reversed A/R để tránh đổi nhầm chiều.

### AR-03 · P1 BLOCKER — `economic_key` và `usage_version` chưa thành quy tắc chống claim qua **hai roots**

**Nguồn:** C **L10–14, L31–34, L155–162**; P **L87–105, L111–125, L204–220, L283–290**; Q **L209–212**; D **L51–66**. Unique `(organization, employee, activity)` giải quyết **hai dossiers cùng root**, nhưng không giải quyết cùng invoice được đưa vào **hai activities** của một nhân viên. Contract có `Expense.economic_key`, `ReadSet.usage_version` mà thiếu format/namespace/lifecycle của usage, xử lý `MATCH/UNKNOWN/CONFLICT`, atomic ownership và liên hệ invoice ↔ paid portions.

**Phản ví dụ:** Tại root activity A, nhân viên nhận reimbursement E3 theo invoice X. Tại activity B, cùng invoice X dưới ảnh crop/PDF scan khác digest và tên file khác: nếu chỉ unique root hoặc sha256 source, B có thể nhận thêm E3. Tương tự, invoice X có hai payment portions thật trong cùng root không được blanket từ chối như duplicate invoice.

**Sửa tối thiểu:** Định nghĩa một *tenant-scoped usage ledger/registry* hẹp, không cần budget reservation engine: key kinh tế được xác minh từ issuer/invoice identity/expense scope và các payment portions; claim ownership/eligible portions, source refs, status và usage version. Candidate trùng nhưng identity chưa đủ ⇒ FACT, không tự “merge” bằng amount/date. Khi chứng minh cùng nghĩa vụ ở root khác, chặn hai active money instructions; khi cùng root thêm **portion mới** có proof, cho tăng E một lần. Kiểm usage + ghi hiệu lực atomically ở T6, race T8; test trước T13 chứ không đợi mở local-meeting.

**Acceptance:** two different activities in **same tenant DB**, same invoice via hai formats ⇒ không được issue hai lần; two actors submit đồng thời ⇒ tối đa một accepted usage; cùng invoice/cùng root có portion mới2 có chứng cứ ⇒ không tăng T hai lần, có thể tăng E hợp lệ; chỉ giống amount/date ⇒ giữ FACT thay vì xác nhận trùng sai.

### AR-04 · P1 BLOCKER — Ranh giới tái sử dụng eligibility sau *payment portion mới* chưa khóa đủ

**Nguồn:** C **L32–35, L106–114, L120–134**; P **L107–125, L185–201**; Q **L47–60, L81–105**. `EligibilityDecision(E,cost_basis,...)` được reuse nếu unchanged cost basis; song E phụ thuộc **payer/received/payment portions** và ngưỡng 8m, còn P/A/R receipt theo khác basis. Plan kiểm E5→E7 trong cùng invoice nhưng chưa chứng minh sau supplement phải áp lại quyền công nhận E tổng mới, đồng thời receipt P thuần túy không bắt reapprove E.

**Phản ví dụ:** E8 đã được hệ thống công nhận trong quyền 8m; sau đó thêm chứng từ cho **portion employee-paid** 1m cùng invoice (T vẫn giữ nguyên vì expense đã incurred toàn phần). Nếu chỉ so invoice/cost immutable ID, có thể reuse eligibility E8 và cộng E1 ⇒ E9 được tự kết luận vượt quyền. Ngược lại ghi thêm **P1 đã nhận** mà ép người duyệt lại E8 sẽ hỏi thừa, trái Q L139–144.

**Sửa tối thiểu:** Pin contents của `cost_basis`/`money_basis` và eligibility coverage: mọi thay đổi incurred/eligible portion, payer binding, relationship, policy applicability làm invalid eligibility basis cho **phần ảnh hưởng và E total threshold**; A/P/R actual hoàn tất đúng scope chỉ đổi money basis. Chốt trong T3/T7 không dựa đơn thuần source digest hoặc case revision chung.

**Acceptance:** E8→E9 từ new employee payment ⇒ AUTHORITY trước issue; E5→E7 trong B/quyền ⇒ quyết định mới phù hợp, T không đếm lại; E8 + confirmed P1 ⇒ E8 eligibility còn hiệu lực, S giảm1, không bắt human re-approve E.

### AR-05 · P1 BLOCKER — Chưa có persisted **affirmative settlement decision** và predicate `SETTLED`

**Nguồn:** C **L30–35, L96–101, L147–166**; P **L165–183, L204–221**; Q **L129–144, L200–233**; B **L17–19**. DTO mô tả `EligibilityDecision` và `Instruction` nhưng chưa mô tả **record quyết định cân bằng S0** có basis/history/quyền; `CaseView` chỉ có state/summary/issues/instructions/actual_money/audit. `allowed_effect=None` dùng cho cả **đủ căn cứ S0** và **đang bị fact/rights gate chặn**. State `SETTLED` được nêu tên, chưa có predicate priority khi đồng thời processing/STOP/unsupported/handed-off.

**Phản ví dụ:** `E2,A2,P0,R0`, coverage đủ, không issue ⇒ thực sự balanced; hồ sơ khác `E2,A?` và thiếu opening balance cũng không issue. Nếu builder lấy “no active instruction” làm đủ để SETTLED, case thứ hai thành kết luận tiền sai không có instruction; nếu builder coi mọi `allowed_effect=None` là WAITING, routine balanced không tự hoàn tất.

**Sửa tối thiểu:** Định nghĩa một persisted *settlement/conclusion record* có `status` (verified balanced / awaiting facts-rights / outstanding instruction / blocked processing), T/E/C/A/P/R/S, basis/read-set, audit/refs, thời điểm/actor-or-system. Có thể là một trường typed trong decision đã có, không bắt tạo service/framework mới. Pin bảng state-derivation và priority: `SETTLED` chỉ khi coverage/rights/relations đủ, effective net `S=0`, không issue/issue chưa fulfilled/execution unknown, không material problem, không STOP cần giải quyết. `READY_TO_EXECUTE` nghĩa issued actionable instruction, **chưa** settled.

**Acceptance:** Hai hồ sơ phản ví dụ có trạng thái/conclusion khác nhau và reviewer nhìn thấy source basis; `I4` issued/partial ≠ SETTLED; I4 fulfilled confirmed ⇒ SETTLED khi mọi gate khác đủ; Stop và late provider không ghi conclusion mới; revoked/reversed receipt làm phiên bản trạng thái thay đổi có audit.

### AR-06 · P1 BLOCKER — `UNSUPPORTED/TECHNICAL/LIMIT` có đường vào Reconciler nhưng thiếu giao diện trạng thái/gate ra người dùng

**Nguồn:** C **L32–35, L38–40, L62–66, L137–152**; P **L107–125, L145–163, L165–183**; Q **L28–37, L186–194, L198–202**. `AssessmentResult.problems` và `ProcessingProblem` có `affected_fields`, nhưng `CaseView` không nêu `problems`, và state chỉ gồm `WAITING/TECHNICAL_ERROR/…`. Design yêu cầu material unsupported block *affected* money, known unrelated được quarantine, partial NOT_READ ≠ confirmed MISSING; các predicate đó chưa được nối thành một bảng outcome cụ thể cho T3/T5/T6 và UI.

**Phản ví dụ:** Một receipt FX ngoài phạm vi có liên hệ chưa rõ đến A của activity, trong khi E2 đã rõ. Nếu người viết T3 coi FX là notification và T6 không thấy `ProcessingProblem`, app có thể phát hành PAY2 dựa `A=0`. Người khác có thể blanket-block mọi case chứa tệp FX dù tài liệu đã được chứng minh không liên quan. Cả hai đều không đạt requirement scope-specific.

**Sửa tối thiểu:** Pin `CaseView.problems` hoặc projection/view tương đương dạng typed, `affected_conclusion`/`affected_fields`, `blocking` computed theo materiality, và mapping `processing incomplete/unsupported unrelated/unsupported related/FACT/business issue` → state, next actor/action, có/không cho affirmative conclusion. Không tạo nhãn business giả cho lỗi provider.

**Acceptance:** material unknown FX liên quan A ⇒ không issue/không S0, hiển thị UNSUPPORTED + owner/next step; tệp FX chứng minh unrelated ⇒ không blanket-block case bình thường; page NOT_READ ⇒ TECHNICAL và không tính absence; UI xem được khác biệt từ CaseWorkflow.view, không phải test-only component.

### AR-07 · P1 BLOCKER — Scope version của policy/grants/B/exception chưa được pin khi commit

**Nguồn:** C **L18–24, L33–35, L67–68, L116–134, L153–168**; P **L107–125, L179–183, L204–221**; Q **L59–66, L200–207, L231–233**. ReadSet có `context_version,ledger_version,usage_version` nhưng không khẳng định `context_version` bao trùm **mọi sửa policy/grant/budget/exception và explicit revocation**, kể cả authoritative record cập nhật từ ngoài session. “Check all read-set/grants” là ý định đúng nhưng còn hai cách thực thi: kiểm grants hiện tại hoặc kiểm đúng snapshot basis đã dùng rồi kiểm effective grant hiện tại. Hai cách có thể khác khi policy hoặc budget đổi trong lúc provider đang đọc.

**Phản ví dụ:** B14 valid tại snapshot t0, chi T12 dự kiến auto. Trong lúc OCR đọc, người có quyền sửa B xuống8 có hiệu lực cho hoạt động và revoke action grant; nếu context_version chỉ tăng khi context.json thay đổi còn grant/B ở bảng khác, commit theo basis t0 có thể issue dù policy/B/grant t1 không cho phép. Ngược lại sau issue hợp lệ, grant hết hạn ở t2 **không** làm giao dịch đã nhận trước đó biến mất hoặc bắt duyệt lại receipt.

**Sửa tối thiểu:** Chốt `context_version` như aggregate authority version **hoặc** mở read-set bằng versions riêng, nêu chính xác bảng nào increment khi policy/grant/B/exception/import/revoke; tại `BEGIN IMMEDIATE` kiểm basis hash + relevant versions + actual effective rights/current control trước *new action*. Persist historical snapshot/hash cho audit; sau issue, expiry vs explicit revocation theo C L109–111 và P L208, không retroactive rewrite tiền.

**Acceptance:** barrier t0 snapshot→update grant/B→release worker ⇒ no stale financial commit, recheck POLICY/AUTHORITY đúng; grant hết hạn sau valid issue nhưng actual confirmed đúng ⇒ vẫn fulfill; explicit revoke pending instruction ⇒ suspend/audit và không issue tự động.

### AR-08 · P1 BLOCKER — Preview đang chạy và Submit cùng root có thể mất công việc hoặc nhân đôi lượt đọc

**Nguồn:** P **L87–105, L145–163, L165–180, L204–219**; C **L158–183, L249–264**. T5 tạo preview **persistent job không financial effect**, T6 Submit mới kích reconcile, đồng thời giới hạn **one active job/root** và preview→submit cùng material basis phải reuse reads/counters. Chưa có transition/ownership khi Submit đến **trước khi preview hoàn tất**.

**Phản ví dụ:** nhân viên upload, preview OCR RUNNING; bấm Submit sau xác nhận fields vẫn unknown. Worker T5 ghi draft rồi complete (theo job owner preview), trong khi T6 thấy already-active job nên không thể enqueue reconcile; hồ sơ vĩnh viễn PROCESSING/WAITING. Nếu Submit tạo job khác, có thể gọi OCR hai lần/reset shared recovery hoặc hai worker cùng cạnh tranh commit.

**Sửa tối thiểu:** Pin job identity theo root+material basis, phases `PREVIEW_READ → SUBMITTED_RECONCILE` hoặc hậu tố `submit_requested` persisted; rule enqueue/attach/schedule successor cho Submit khi preview RUNNING/FAILED/DONE; counters keyed work/basis và recovery key; source, input/control version recheck ở commit. Không cần queue ngoài hay job platform mới.

**Acceptance:** HTTP preview delayed barrier; Submit ngay khi preview RUNNING ⇒ sau release có **một final assessment** và không missed submission; cached read/attempt counters không bị reset; Stop trong lúc đó ⇒ late worker không financial commit; restart giữa hai phase phục hồi đúng một job/root.

## Findings cần khóa ở handoff, có thể sửa cùng đợt với blockers

### AR-09 · P2 HANDOFF — Override/cancel chưa thống nhất thành tagged command được định nghĩa

**Nguồn:** C **L35, L126–127, L149–168, L253–264**; P **L47–51, L204–220**; Q **L218–230**. C §9 liệt kê `CaseCommand` union gồm `CreateDraft/AttachSources/ReviseDeclaration/Submit/AnswerIssue/Decide/RecordActual/Control` nhưng **không có Override**. P T8 yêu cầu `execute(Control/override)`, kiểm `valid/deniedOverride`; C §6 quy định Override tạo decision mới có reason/scope và retain original. `Decide` có thể chứa override action, nhưng tài liệu chưa nói rõ tag hoặc phép kiểm grant cụ thể. T8 còn mô tả “CancelCHI4” trong khi instruction statuses không có `CANCELLED` và không có cancel command.

**Phản ví dụ:** agent T1 chỉ định nghĩa union theo C §9; agent T8 muốn gọi `execute(Override(...))` thì phải tự thêm DTO/API, hoặc lén dùng `DecisionCommand(actions=['OVERRIDE'])`, không có exact stale/readset/permission semantics. “Cancel” không biết phải chuyển `SUSPENDED` hay `SUPERSEDED` và liệu có cần xác minh execution.

**Sửa tối thiểu:** Chọn **một** representation: typed `Override` variant hoặc `Decide(kind='OVERRIDE', supersedes_decision_id, ...scope,refs,reason)` và pin method/permission/audit/state transition. Đặt nghĩa `cancel` chỉ là suspend/supersede request, không xóa actual T/P, đặc biệt khi handoff unknown. Test từ API qua `CaseWorkflow.execute` với allowed/denied grant.

**Acceptance:** T1 DTO và T8 API cùng compile theo contract; authorized override lưu old/new basis/reason, unauthorized/stale không làm hiệu lực; instruction handed-off không bị coi là chưa thực hiện chỉ vì cancel/suspend.

### AR-10 · P2 HANDOFF — Idempotency của command cần *scope* và *payload fingerprint*

**Nguồn:** C **L10–14, L158–168, L253–264**; P **L87–105, L185–202, L204–220**. Đã tách command ID và bank external key (đúng). Nhưng “same command ID same result” chưa nói unique ở tenant/session/root/actor và phải xử lý **same ID, different payload**. T2 có session isolation, nhưng test bank key payload conflict của T7 không tự đảm bảo idempotent HTTP commands được tenant-scope.

**Phản ví dụ:** client bị mất response, retry command id `abc` cùng payload và scope ⇒ trả cùng result (đúng). Một tab khác/case khác hoặc actor khác dùng `abc` với `RecordActual(amount=5)` sau khi id đó gắn với `amount=4`: nếu replay vô điều kiện, trả kết quả cũ và che hành động mới; nếu execute lại, có thể duplicate effect hoặc trả `CaseView` thuộc tenant khác.

**Sửa tối thiểu:** Định nghĩa durable command identity `(tenant, actor/session scope, command_id)` cộng canonical request fingerprint gồm root/kind/meaningful payload; identical ⇒ replay nguyên effect/result/audit ID, divergent ⇒ deterministic conflict; tenant khác độc lập; external `(origin_namespace,transaction_ref)` unique đúng tenant giữ rule riêng. Response snapshot historical hay view refreshed phải chọn một (đề xuất historical result + separate fresh `view`).

**Acceptance:** two retries after commit/crash same identity/payload ⇒ một effect, same response marker; same ID changed amount/root/action ⇒ 409 conflict; same ID other tenant không leak; same bank key different **command IDs** vẫn một actual, payload changed ⇒ conflict.

### AR-11 · P2 FINANCIAL SEMANTICS — `T−E−C` không tự động là unpaid; “exclude cost” phải rõ thuộc T hay E

**Nguồn:** C **L32, L70–77, L137–144**; P **L107–125, L185–201**; Q **L81–105, L432–442**; [`GLOSSARY.md`](../../../../GLOSSARY.md) phần “Tổng chi công việc”, “Chi phí nhân viên được chấp nhận”. `Projection.unpaid` đã được khai báo, nhưng không có thuật toán/nguồn riêng cho unpaid. C L142 ghi “Cấm rõ không exception | Exclude cost with refs” mà không xác định cost bị exclude khỏi **E**, **T**, hay cả hai.

**Phản ví dụ 1:** T10 là chi công việc thực sự đã phát sinh; employee **đã trả7** nhưng chỉ **E5** được công nhận, company-direct C3, không còn payable vendor ⇒ unpaid0. Phép suy `T−E−C` sẽ cho unpaid2 (sai). **Phản ví dụ 2:** đã chứng minh một chi phí công việc T3 nhưng loại khỏi E do policy; nếu implementation xóa luôn khỏi T thì budget B kiểm thấp hơn Q31. Chi cá nhân thực sự không phục vụ công việc thì không vào T hoặc E, nhưng ứng A liên quan vẫn phải đối chiếu.

**Sửa tối thiểu:** Pin `unpaid` từ gross paid portions + outstanding obligations *đã xác minh*, không suy từ eligible E. Định nghĩa rõ “exclude cost” trong C L142: khoản *công việc incurred nhưng không eligible* có ở T và không ở E; khoản *personal không phải công việc* không thuộc T/E; giữ A/P/R như thực tế. Nếu rulebook mong khoản công việc bị cấm hoàn toàn **không tính vào B**, đó là **thay đổi business rule ảnh hưởng Q31** cần hỏi user, không để agent tự quyết.

**Acceptance:** T10/employee paid7/eligible5/C3/unpaid0 ⇒ unpaid0; T10/employee paid5/C3/confirmed outstanding vendor2 ⇒ unpaid2, không tạo vendor instruction; personal E excluded/A2 ⇒ THU2 nếu history/quyền khác đủ; cost work bị loại E vẫn không bị âm thầm biến mất khỏi T.

### AR-12 · P2 HANDOFF — Activity identity cho demo new-input chưa có life-cycle tạo/ủy quyền đủ cụ thể

**Nguồn:** C **L10–14, L118–135, L256–264**; P **L87–105, L241–252**; Q **L19–26, L125–128, L363–378**. C yêu cầu activity ID từ org context hoặc quyết định tạo đúng quyền; T2 UI cho select/create mà không cho nhập employee/operator/work ID, và server fixture chỉ seeded travel B8. Chưa rõ new-input của judge trên activity khác được tạo bằng workflow được cấp quyền nào, và làm sao tránh vô tình dồn hai **hoạt động khác nhau** vào cùng một root seeded.

**Phản ví dụ:** hai chuyến công tác khác ngày/căn cứ cùng employee; UI chỉ có travel-A mẫu và `CreateDraft` thứ hai trả lại root A. Reviewer muốn chạy hai hồ sơ mới độc lập nhưng uploads bị trộn, budget B8 của root A bị dùng nhầm. Ngược lại cho client gửi arbitrary activity_id + B/grants sẽ phá giới hạn quyền.

**Sửa tối thiểu:** T2 chốt server-owned activity catalog/authorized creation command (hoặc scoped demo import context) với **stable activity ID**, actor allowed, effective budget/grant provenance, UI label rõ; user không tự cấp B/grant. Một activity reuse root, hai activity hợp lệ create hai roots. T10 smoke input mới dùng đường đó.

**Acceptance:** same activity concurrent create cùng root; two legitimate activities separate roots/cost/ledger/budget; forged client actor/B/ID không tự cấp quyền; new input không cần sao chép gold/precomputed outcome.

### AR-13 · P2 DELIVERY RISK — Task interfaces còn shorthand file paths và các gates khó chạy song song

**Nguồn:** P **L35–60, L62–68, L70–105, L165–221, L241–281, L295–309**; C **L247–287**; B **L231–244**. Kích cỡ thiết kế hợp lý với một pilot nghiêm túc nhưng để giao independent agents cần mốc contract nhỏ hơn. Ví dụ T7 ghi `commands/finance` dù file map chỉ có `domain/commands.py`; T8 ghi “jobs/service/db/snapshots” không phải exact files theo prefix map. P đặt M0/T4/T9/clean-clone/public/trials/adaptation/holdout nối tiếp nhau trong lịch khóa brief **15/10** (B L238–244): đó là **execution exposure**, không phải bằng chứng plan sai hay lý do bắt project mở rộng microservices.

**Sửa tối thiểu:** Mỗi task T1/T2/T3/T5/T6/T7/T8 pin chính xác **owned paths** và producer/consumer types trong 5–10 dòng `Interfaces`; không yêu cầu agent đọc toàn bộ plan để đoán file; giữ cụm workflow DB/transaction thuộc **một integrator** hoặc review gate rõ trước khi hai agent chạm cùng files. Chia milestone theo release gates: minimum demonstrable raw→routine/FACT→real instruction/control/audit→Verify/public; adaptation/local-meeting chỉ sau gates tương ứng, còn người dùng/trial preparation bắt đầu song song từ T2. Nếu brief deadline thực áp dụng, báo kịp/không kịp theo evidence; không tự thay scope đã chốt.

**Acceptance:** T7 target file chỉ có một cách hiểu; T8 biết chính xác nơi thêm schema/transaction/job; mỗi merge gate có hai-task replay scenario qua same DB; release checklist phân biệt planned vs measured vs blocked external.

## Handoff contract cần đặt chủ sở hữu trước khi dispatch

| Boundary | Producer → Consumer | Artifact/decision phải khóa | Owner đề xuất |
| --- | --- | --- | --- |
| Expense identity | T1 DTO → T3 classifier → T6/7 commit | `economic_key`, paid portions, tenant usage owner/version, ambiguity→FACT (AR-03, AR-11) | Workflow integrator cho DB/atomic usage; Reconciler sở hữu pure predicate |
| Cost vs money basis | T3 → T6/T7 | eligible covered portions, E threshold, policy effective time; independent A/P/R net & money basis (AR-04) | Reconciler contract; T7 chỉ cung cấp verified events |
| Obligation coverage | T3 proposal → T6 issue → T7 actual → T8 recovery | net S, issuance coverage, remaining, supersession, reversal, execution unknown (AR-01/02) | **Một** workflow integrator chịu trách nhiệm invariant xuyên các tasks |
| Case decision & state | T3 result → T6 commit → T8 view | persisted balanced decision, issue/problem scope, SETTLED priority (AR-05/06) | T6 quyết định persisted; T8 chỉ enforce concurrency/control |
| Authority/read-set | T2 context, T3 gate → T6/T8 atomic commit | authoritative update versions, grant action/time, budget effects, revocation (AR-07) | T2/C config contract, T8 validate transaction |
| Job lifecycle | T5 preview → T6 submitted work → T8 restart | in-flight submit, bounded counters, ownership across Stop/Resume (AR-08) | Workflow jobs integrator |
| Mutating commands | T1 union → T2 HTTP → T7/T8 | Override/cancel tags, command identity/fingerprint, actor/tenant scope (AR-09/10) | T1 public DTO; T8 atomic implementation |

Đây là **handoff contract** để các nhóm code độc lập thống nhất hành vi, không phải yêu cầu thêm 7 framework hay 7 services. Nên ưu tiên test một chuỗi **root→Submit→I4→P2→REVERSAL→supplement→Stop/Resume** với thực DB, bởi nhiều invariants chỉ bộc lộ khi kết hợp actions; unit test toán tiền đơn lẻ không đủ. Bổ sung một test hai roots dùng cùng economic expense trong *shared DB*; test isolated cases không bắt được race usage này.

## Tách rõ ba loại vấn đề khi lead disposition

**(1) Plan/contract blockers để sửa trong Markdown trước khi split ownership:** AR-01 đến AR-08; AR-09/10 có thể chốt đồng thời T1 vì public DTO ảnh hưởng các tasks khác. Không cần thêm policy lớn hoặc triển khai phần mềm để đóng những findings đó. Chấp nhận sửa một bộ bảng state/transaction + 5–8 boundary tests trong task chủ; tránh biến mỗi finding thành một module.

**(2) Builder/runtime evidence tasks, không phải lý do bác plan:** M0 xác nhận Mistral/xkiro effective versions, PDF native/scan/hybrid và quality; SQLite race/lock contention thực tế, command crash/restart, usage cache, UI/Verify, `SETTLED` transitions; demo public mới, processor timeout và actual wall time; Core4/Escalation5/holdout. P **L145–163, L204–252** đã giao việc này. Từ tài liệu không thể biết chúng PASS hay FAIL; giữ gates có test thực, không yêu cầu chúng xảy ra trước khi chỉnh plan.

**(3) External unknown:** availability/credentials/model pricing/version, hosting public, team eligibility/sprint deadline exception, nguồn lực recruit >=3 professionals và feedback/provenance thật. Q **L380–407**, D **L159–162**, B **L231–260**. Không ghi chúng là lỗi coding/kiến trúc đã chứng minh; nếu chưa có thì ghi release evidence **unmet**. Đặc biệt không dùng reviewer consensus hoặc “green suite” để suy output pháp lý/financial correctness ngoài input/gold được kiểm.

**Business choice có khả năng phải xin người dùng:** Với AR-11, nếu lead muốn **loại hoàn toàn một incurred business cost bị policy cấm khỏi T/B**, đây là khác với cách đọc Q31 hiện tại; cần đưa ví dụ số T/B và xin quyết định nghiệp vụ trước khi đổi. Với overpay ở AR-01/02, default an toàn là giữ incident/pending verification và không tự phát hành thu đảo chiều khi nguồn/authority unresolved; nếu muốn tự phát lệnh THU sau khi xác nhận overpay, cần explicit action/right rule. Không tự đổi 8/4/20, Q31, “actual đúng scope dù sai grant”, hay phạm vi không có vendor payable.

## Điều kiện để đổi verdict

Tôi sẽ coi plan **READY FOR INDEPENDENT TASK IMPLEMENTATION** khi bản sửa đạt các tiêu chí văn bản sau (không yêu cầu chạy app): một thuật toán obligation/coverage nhất quán cho retry/partial/supplement/reversal; tenant-wide usage atomic với ambiguity route; cost-vs-money basis/eligibility grant lại khi E đổi; settlement/conclusion + problem visibility + derived state predicates; versioned current authority checks; preview/submit handoff; union Override/cancel và command idempotency scope. Tất cả được gắn owning task, minimal counterexample, test assertion và exact interface. AR-11–13 có thể sửa cùng bước nhưng không nên biến thành mở rộng sản phẩm.

**Giới hạn cuối:** Đây là nhận định độc lập từ hợp đồng tài liệu đúng snapshot, không phải chứng nhận các lỗi đã tồn tại trong code hoặc các sửa chữa sẽ luôn chạy đúng. Chỉ báo cáo review này được ghi; không đổi plan, contracts, source, test, provider, Git hay môi trường.

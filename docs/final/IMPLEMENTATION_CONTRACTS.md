# InvoiceReferee final — Implementation contracts

Ngày13/10/2026. Companion của implementation plan; cụ thể hóa Q1–Q31 và
[disposition review](reviews/2026-10-13/SYNTHESIS.md), không dùng rebuild.
Đây là contract thiết kế, không phải code hoặc proof runtime. Các lựa chọn của
lead (cấu trúc DTO, enum, giới hạn pilot, thuật toán threshold) được ghi rõ bên dưới.
§10 khóa chi tiết sau review; khi shorthand ở các mục trước chưa đủ, executor dùng
§10, không tự mở nghiệp vụ hoặc suy đã đạt runtime từ contract.

## 1. Scope và scalar types

Root unique trong một sandbox: (organization_id, employee_id, activity_id).
Một root có nhiều revisions, không nhiều hồ sơ độc lập tiêu lại cùng ngân sách.
DB unique bảo vệ tạo đồng thời; activity identity từ context tổ chức hoặc quyết
định tạo hoạt động đúng quyền, không ghép từ tên/địa điểm/amount giống nhau.
Expense economic identity khác document hash và money transaction identity.

Python3.12, Node24 là lựa chọn lead; package versions được resolve, khóa uv.lock/
package-lock.json và smoke trước use. Domain types Pydantic strict extra=forbid:
Id=str, Vnd=StrictInt >=0 cho base amounts; signed S/delta là StrictInt.
Datetime có timezone, normalized UTC; view hiển thị Asia/Ho_Chi_Minh.
Fact[T]: key, value:T|None, state(KNOWN/UNKNOWN/CONFLICT), refs:tuple[EvidenceRef,...],
verified_by:Id|None. UNKNOWN/CONFLICT không có aggregate value; observations
cạnh tranh còn nguyên. Boolean không được nhận thành số tiền1.
EvidenceRef: source_id, source_sha256, page (1-based) hoặc record_key, exact_quote,
optional bbox. Model không được sinh file URL/path hay tự cấp Fact.KNOWN.

## 2. DTO và nơi định nghĩa

| File sẽ tạo | Types và fields bắt buộc |
| --- | --- |
| domain/common.py | Id/Vnd, KnownAmount(value:Vnd,currency:Literal["VND"]), Fact[T], EvidenceRef; money formatting nằm frontend |
| domain/evidence.py | SourceRef(id,digest,tenant,media,storage_key); EvidenceUnit(source,page_range,role); Observation(field,raw,normalized,read_state,ref); Relation(kind,from_id,to_id,state,refs); Confirmation(fact_key,value,actor,scope,refs,reason,observed_at); ReadResult(units,observations,relations,page_coverage,problems,trace_refs) |
| domain/finance.py | Expense(id,economic_key,activity,incurred:Fact[Vnd],incurred_at,payments,eligibility,refs); ExpensePayment(external_key,payer,payee,amount,expense_id,received_state,refs); RecordMoneyInput(external_key,claimed_kind,claimed_scope,payer,payee,amount,event_at,completion_claim,reverses_event_id,refs,reason); MoneyEvent(id,external_key,kind,scope,payer,payee,amount,event_at,recorded_at,verification_state,allocation_state,reverses_event_id,refs); Projection(T/E/C/A/P/R/unpaid:Fact[Vnd],S:Fact[StrictInt],issues) |
| domain/policy.py | PolicyVersion(id,version,effective_from/to,profile,rules); Grant(id,version,actor,actions,scope,max_amount,effective_from/to); BudgetDecision(id,activity,amount,effect_range,actor,grant_ref,refs); ExceptionDecision(rule_id,expense_ids,activity,max_effect,actions,actor,grant_ref,decided_at,effect_range,refs,reason) |
| domain/case.py | CaseScope(tenant,employee,activity,profile); ReadSet(input_revision,control_epoch,context_version,ledger_version,usage_version); AssessmentInput(scope,expense_facts,observations,relations,confirmations,ledger,coverage,policy,grants,budget,exceptions,previous_eligibility,read_set,as_of); FinancialEffect(direction:PAY/COLLECT,amount:Vnd,employee,activity,basis); AssessmentResult(projection,issues,problems,required_authorizations,allowed_effect:FinancialEffect\|None,cost_basis,money_basis); CommandContext(session_id,actor_id,command_id,expected_case_version); EligibilityDecision(E,cost_basis,actor_or_system,grant_refs,refs); SettlementConclusion(status,projection,expense_dispositions,read_set,basis,refs,actor_or_system,decided_at); Instruction(id,root_id,direction,amount,status,basis,authority_refs,supersedes_id,fulfilled_amount:Vnd,remaining:Vnd,execution_state:NOT_STARTED/OPEN/CLOSED_CONFIRMED/UNKNOWN); CaseView(id,version,state,summary,sources,issues,problems,conclusion,instructions,actual_money:Projection,audit) |
| domain/issues.py | BusinessIssue(id,kind FACT/POLICY/AUTHORITY,field_or_rule,owner,depends_on,status,basis,refs,question); ProcessingProblem(kind TECHNICAL/LIMIT/UNSUPPORTED,affected_fields,message); QuestionCard(issue_id,known_facts,excerpt_refs,required_answer,effects,owner); Answer(issue_id,basis_id,answer_kind,value,refs,reason); DecisionCommand(issue_ids,basis_id,actions,effect_scope,amount,reason,refs) |
| adaptation/models.py | Opportunity(id,root_id,initial_basis,field,eligible_steps,features,score,threshold_version); Feedback(id,initial_basis,observed_action,correction,new_fact,exception,question_needed,final_correct,origin,data_origin,verification,verifier,refs); ThresholdVersion(id,threshold,selection_ids,validation_ids,activated_at,previous_id) |

Read states CLEAR/MISSING/UNREADABLE/NOT_READ/ERROR là observation, không Fact.KNOWN.
Relation states SUPPORTED/DISPROVED/UNKNOWN/CONFLICT. Source role ở evidence unit,
PDF có nhiều role; không conflict chỉ vì request và receipt cùng tồn tại.
DTO có thể có nested types nội bộ, không phải mỗi type/file/service riêng.

## 3. Nguồn được chấp nhận và coverage

| Claim | Căn cứ được nhận | Không đủ riêng lẻ |
| --- | --- | --- |
| Incurred expense/T | Final expense document và evidence service/activity incurred hoặc confirmation đúng trách nhiệm | Forecast/request/face value đang tranh chấp |
| Employee-paid/E candidate | **Policy demo (chốt 14/10/2026): hóa đơn gốc hợp lệ, gắn đúng nhân viên và hồ sơ, là căn cứ khoản nhân viên đã trả** (`EMPLOYEE_PAID_INVOICE`), không cần giấy xác nhận thanh toán riêng. Hóa đơn **chỉ ghi công ty mua** vẫn bind được bằng **composite**: người đề nghị trên giấy khớp nhân viên, dòng giấy tham chiếu hóa đơn, công ty mua khớp tổ chức scope, không có nguồn trái chiều (T2). Nếu hóa đơn ghi tên người mua khác hoặc nguồn ghi người trả khác → FACT/ngoài scope, không bịa confirmation. Hoặc payment proof ghi payer/amount/expense; hoặc confirmation tài chính hợp lệ; hoặc **lời xác nhận chịu trách nhiệm của nhân viên + chứng từ dịch vụ** trong ngưỡng tự xử lý E<=8tr, abs(S)<=4tr (Q32/ADR007) | Guest/buyer công ty trên invoice không phải người trả; tên/chữ ký/`TM-CK` trên hóa đơn tự nó; lời khai chi tiền ngoài ngưỡng |
| Company-direct/C | Company supplier payment có binding expense + actor/context đúng scope | Tên công ty trên hóa đơn |
| A/P/R/received | Confirmed completed transfer/cash receipt/ledger có payer/payee/scope; reversal phải có event gốc | Requested/approved/debit-only/pending |
| Activity purpose/link | Employee declaration được policy nhận + context compatible, không contradiction | Amount/date giống nhau hoặc opaque LLM confidence |
| B/grant/exception | Immutable organization record hoặc command đúng quyền | Model output, client role, ảnh chữ ký/name match |
| Zero flows | Coverage đủ scope/time/opening balances/kinds/nguồn quỹ, known set empty | Thiếu file, chỉ xem tài khoản A hoặc tháng hiện tại |

Confirmed actor lấy từ server session/grant. Confirmation tiền chứa field/value,
nguồn đã kiểm, scope/time/loại money, reason và verifier, không approval chung.
Model output chỉ là observation/proposal; admissibility kiểm source role, positive
predicate, binding, quality/conflicts và literal locator. Exact quote có thật
chưa tự chứng minh payer/received. Không xây generic semantic-proof engine; viết
predicate tests cho bảng trên và đo false-known raw với gold độc lập.

Coverage record: employee/activity (hoặc all-activity rõ), start/as_of, fund set,
flow kinds, opening balance, ledger_version, witness/source_refs. Unallocated
material money/source không được bị bỏ rồi kết luận zero. Known unrelated sources
được quarantine có lý do; unknown relevance là FACT; material unsupported blocks
affected conclusion. Source encrypted/corrupt/over-limit là processing problem.
Policy/grant/B có effective interval; policy eligibility theo expense time,
grant hành động theo decision/commit time; retroactive effect phải explicit.

### 3a. Phạm vi chi phí mở rộng (chốt 14/10/2026, plan general-expense)

Một quy trình quyết toán chi phí công việc do nhân viên trả (có ứng hoặc đã xác
minh không ứng), gồm công tác, tiếp khách tại chỗ, mua văn phòng phẩm/thiết bị nhỏ
và dịch vụ vận hành nhỏ. Giữ nguyên 8/4/20 và B độc lập; không mang hạn mức 100tr
của Hoangha, không bắt routine chờ kế toán duyệt.

- **Hồ sơ hoạt động do server/context sở hữu** (`TRAVEL` hoặc `WORK_EXPENSE`); giấy
  quyết toán dùng chung (định danh/mục đích/tổng/số bằng chữ) + refinement công tác.
  Giấy ngoài công tác **không** bị ép khai `trip_*` (T1).
- **Hạn mức theo loại khoản (mỗi khoản canonical):** tiếp khách/bữa ăn ≤5.000.000 đ;
  taxi/đi lại ≤2.000.000 đ; **hạn nộp 30 ngày** từ ngày phát sinh có căn cứ; chi cá
  nhân bị loại khỏi chi phí công việc. Loại không có hạn riêng vẫn qua B/8/4/20 và
  căn cứ; **không** là PASS vô hạn (T3). Ngày nguồn thiếu là FACT, không thay bằng
  ngày nộp.
- **Phân bổ nhiều dòng một chứng từ:** tổng phân bổ không vượt tổng nguồn; chứng từ
  hỗ trợ (payment proof/acceptance) **không** thành expense thứ hai; nguồn thừa chưa
  tham chiếu là FACT relevance (T4).
- **Thiếu chứng từ có lý do (TC20):** FACT trước (dịch vụ/số tiền/người trả chưa
  xác lập), rồi POLICY đúng rule `expense:missing_required_evidence`; chỉ actor có
  grant `EXCEPT_POLICY` đúng rule/khoản/scope/effect mới duyệt; từ chối cho
  disposition loại trừ đã biết. Không màn hình giải trình riêng (T5).
- **Điểm tự xử lý cuối:** E vượt 8tr là AUTHORITY; |S| vượt 4tr là AUTHORITY; TC14
  E~121tr/S1tr vượt demo 20tr; TC13 loại chi cá nhân nhưng vẫn quyết toán ứng (T3/T5).

### 3b. Luồng nộp hồ sơ trên web (chốt 14/10/2026, plan TC01 web fix)

Luồng: upload → **Đọc chứng từ** → kiểm tra bản nháp → **Xác nhận và nộp hồ sơ**.

- **Một pipeline OCR cho cả bản nháp và đối soát.** Bản nháp (`POST
  /cases/{id}/settlement/draft`) đọc qua đúng pipeline §12 (OCR → phân loại → trích
  xuất → validate → match); **không** còn đường `pypdf.extract_text` + regex. PDF có
  text, PDF scan và PNG/JPEG đều đi qua OCR. Bản nháp mang source refs + trạng thái
  trường.
- **Dùng lại kết quả đọc khi nộp.** Bản đọc được persist kèm `input_basis_json`
  (tập digest nguồn + version). Khi nộp với đúng nguồn đó, hệ thống **không gọi lại
  OCR/LLM**; đổi nguồn thì vô hiệu hoá bản đọc. Một workflow, không pipeline song song.
- **Không dữ liệu mẫu.** Không tự điền số/người/hoạt động khi đọc lỗi; trường chưa
  đọc được giữ `null`/UNKNOWN, không thành 0; không hiện "Cân bằng" khi số chưa biết.
  Lỗi đọc hiển thị lỗi + giữ tệp + cho thử lại; không báo "Đã trích xuất" giả.
- **Gắn hoạt động do server kiểm.** Hồ sơ nháp tạo trước khi biết hoạt động (không
  bịa PROPOSED có ngày hiện tại). Nhân viên chọn hoạt động **theo tên** trong danh
  mục; khi nộp, server rebind hồ sơ nháp sang hoạt động AUTHORIZED đúng (hoặc từ
  chối nếu không có trong danh mục). Profile/ngân sách/quyền/lịch sử lấy theo scope
  hoạt động đã gắn; không mượn context hoạt động khác.
- **Lưu bản nháp đã xác nhận.** `Declaration` mang giá trị nhân viên xác nhận +
  `original_declared_advance`; server lưu `case_declarations.draft_json` (confirmed +
  original + `corrected_fields` + actor + thời điểm). Sửa ứng kê khai (vd 4tr→4,5tr)
  là **declaration/correction**, không ghi đè ledger A thực nhận của công ty; đối
  soát so khai báo với lịch sử và xử lý mâu thuẫn. Enforce owner/expected version.
- **Cập nhật bất đồng bộ.** Sau nộp, UI polling có giới hạn tới khi hồ sơ rời
  PROCESSING hoặc cần người; dừng khi rời trang. Version/state do server quyết định.
- **Nhãn tiền đúng mức.** Bản nháp gọi số nhân viên nhập là **"Ứng nhân viên kê
  khai"** và **"Tổng chi phí kê khai"**, chênh lệch là **"Chênh lệch kê khai dự
  kiến"**; A/E/S chính thức chỉ từ projection sau đối soát.

## 4. Tiền, event và instruction

T=sum incurred costs đã xác minh, không cắt về B; E=sum eligible employee-paid
portions đã xác minh; C=company-direct actual portions; unpaid không tự vào E/C.
S=E-A-P+R, không float. B8/invoice-incurred10/paid employee5/company3/unpaid2:
T10, E candidate5, C3, POLICY; không create vendor instruction.
Nếu unpaid đã biết không đổi quyền lợi employee hoặc phép kiểm B, chỉ notice
“ngoài việc thực hiện tiền của hồ sơ”, không giả toàn invoice đã thanh toán.

Cập nhật phạm vi 14/10/2026 (§14/§15, ADR006/ADR007):
- **C (Q34):** khi nguồn cho thấy công ty trả trực tiếp/người trả khác, giữ C như
  dữ kiện để đối chiếu và báo phần ngoài phạm vi employee-paid; **không** đưa C vào
  phép tính hoàn trả nhân viên và không bỏ phần vật chất để kết luận tiền. `S` cho
  phạm vi employee-paid không cộng C.
- **Căn cứ hóa đơn (chốt 14/10/2026, thay đường mặc định):** trong policy demo, một
  hóa đơn gốc hợp lệ (`profile_status=CLEAR`, có `total_amount`) gắn đúng nhân viên
  và hồ sơ là căn cứ khoản nhân viên đã trả (`EMPLOYEE_PAID_INVOICE`); **không** cần
  giấy xác nhận thanh toán riêng và **không** cần câu xác nhận dài trên giấy quyết
  toán. Đây là giả định nghiệp vụ cho demo, **không** là xác minh ngân hàng; hệ thống
  không tạo giao dịch ngân hàng giả. Hóa đơn có `buyer_person_name` là khóa gắn với
  nhân viên; **bên mua là công ty không phải người trả** (không tạo C). Lệch người,
  sai hồ sơ, số tiền mâu thuẫn hoặc tài liệu chưa đọc rõ vẫn là FACT đúng chỗ. Khoản
  ứng thực nhận vẫn cần bản ghi riêng của công ty (mục D dưới).
- **Lời xác nhận (Q32, đường phụ):** một khoản E cũng có thể dựa trên lời xác nhận
  chịu trách nhiệm của nhân viên + chứng từ dịch vụ, chỉ trong ngưỡng `E<=8tr`,
  `abs(S)<=4tr`, khi không mâu thuẫn trọng yếu; provenance/`verified_by` phản ánh actor
  là nhân viên và view ghi rõ mức căn cứ là "lời xác nhận", không phải giao dịch ngân
  hàng đã xác minh.
  Mức căn cứ là enum đóng `PaymentBasisKind` = `INDEPENDENT_PAYMENT` /
  `FINANCIAL_CONFIRMATION` / `EMPLOYEE_PAID_INVOICE` / `EMPLOYEE_DECLARATION_Q32` /
  `UNSPECIFIED_LEGACY` (A0 + chốt 14/10). `ExpensePayment` mang `basis_kind` (mặc
  định `UNSPECIFIED_LEGACY` cho constructor STUB/test) và `responsible_actor`;
  admission LIVE/REPLAY không nhận `UNSPECIFIED_LEGACY`. `PaymentBasisView(expense_id,
  kind, actor, refs, rule_id)` là view dẫn xuất, không tạo ledger event. Client khai
  báo khoản đã trả qua `EmployeePaidClaim(invoice_reference, amount, refs, reason)`
  (amount là VND integer; client **không** cấp actor/verifier/known); server suy
  actor/scope/time. Hóa đơn đủ điều kiện không bắt client nhập lại invoice/amount hoặc
  xác nhận payer riêng.
- **Ứng thực nhận (mục D):** kế toán ghi nhận `ADVANCE_RECEIVED` từ chứng từ ứng đã
  đọc (chuyển khoản/tiền mặt) qua `RecordActual`; `RecordMoneyInput` mang
  `instrument_method` (TRANSFER/CASH), `instrument_status` (COMPLETED/PENDING/FAILED/
  UNKNOWN) và `instrument_reference`. **Trạng thái nguồn khác COMPLETED không bao giờ
  thành CONFIRMED**; upload chưa tự thành received. `external_key` chống trùng theo
  (giao dịch/số phiếu); scope/actor do server kiểm. Một hồ sơ bị chặn ghi vào hoạt
  động khác (`claimed_scope` phải khớp root).

MoneyEvent kinds ADVANCE_RECEIVED/REIMBURSEMENT_RECEIVED/EMPLOYEE_RETURN/
REVERSAL/OBSERVED_UNALLOCATED; external_key=(origin_namespace,transaction_ref)
duy nhất trong tenant. Expense payment/financial movement của cùng transaction
không được được tính hai lần. Same cash receipt issuer+number là key; thiếu
identity cần confirmation, không hash amount/date thành transaction thật.
Company money đã confirmed đúng employee/activity vào A/P/R dù trái quyền.
Governance incident riêng chỉ khi có căn cứ; thiếu historic grant không chứng
minh trái quyền hoặc làm mất P. Unknown completion/payee/scope giữ unknown.
Linked reversal không xóa event; amount reversed <= unreversed original;
bank refund của P giảm P, không tạo R giả. Record facts không bị business cap20
làm mất tiền thật; actor cần quyền record, oversized/out-of-scope observed giữ audit.

Projection không được giả zero cho breakdown chưa rõ. Bản đầu yêu cầu phân loại
A/P có căn cứ trước khi tự kết luận S; nếu chỉ biết tiền công ty chuyển cho nhân
viên, giữ FACT về loại/scope, không coi đó là ứng hoặc hoàn trả. Không xây thêm
aggregate funding/symbolic arithmetic khi chưa có consumer trong scope đã chốt.

allowed_effect là đề xuất pure để workflow kiểm lại và commit, không phải
instruction đã phát hành. Nó bằng None khi S=0 đủ căn cứ hoặc bất kỳ gate tiền/
quyền trọng yếu còn thiếu. Hai trường hợp này phân biệt bằng projection/issue/state.
required_authorizations là các hành động còn thiếu grant, không phải side effects.
Instruction.remaining=max(amount-fulfilled_amount,0); fulfillment chỉ cấp cho đúng
instruction, không cắt actual projection theo amount của instruction.
RecordMoneyInput không có verification_state/allocation_state/verifier/recorded_at;
server xác minh chứng cứ, actor/grant và binding rồi mới tạo MoneyEvent. Xác nhận
đã nhận, gắn đúng scope và fulfill instruction là ba kiểm riêng.

Một active Instruction cover toàn uncovered S tại lúc issue, không cắt S8 thành
hai instructions4 để né grant4. Partial execution I4/P2: same I remaining2,
không I2 mới. Actual P5 vào Projection, fulfillment của I4 tối đa4, overpay1
issue. Source chỉ fulfill I đúng không invalidates eligibility. Source đổi
cost/payer/policy relation thì re-assess cost. Previous EligibilityDecision chỉ
reuse nếu cost_basis chưa đổi và còn hợp lệ; receipt không bắt re-approve E.
Case settled được bổ sung evidence/event tạo revision/reconciliation mới, không
xóa actual. Một invoice cùng root có paid portion mới hợp lệ có thể tăng E;
usage không cấm legitimate supplementation nhưng cấm claim root khác.

## 5. Quyền và ngã rẽ

| Action | System | Employee | Accountant | Approver demo |
| --- | --- | --- | --- | --- |
| SUBMIT/DECLARE_PURPOSE | Orchestrate | Own scope | Không mặc định | Không mặc định |
| CONFIRM_FINANCIAL_FACT/RECORD_ACTUAL | Không tự tạo fact | Không tự nâng declaration | Granted scope | Chỉ nếu có grant riêng |
| AUTHORIZE_ACTIVITY/SET_BUDGET | Chỉ dùng record đã có | Không | Không | <=20m và effect scope |
| RECOGNIZE_COST | E<=8m | Không | Không | <=20m |
| EXCEPT_POLICY | Không | Không | Không | Exact rule/scope/max_effect, <=20m |
| ISSUE_PAYMENT/COLLECTION | abs(S)<=4m | Không | Execution đúng instruction | <=20m |
| STOP/RESUME | Backend enforces | Không mặc định | Granted root | Granted root |
| OVERRIDE | Không waive facts | Không | Không mặc định | Granted actions/scope/reason |

Default server fixture cho employee submit/answer purpose; accountant financial
confirm/record + stop/resume; approver actions bảng và stop/resume. System grant
recognize/issue explicit scope/profile/time. One compound decision có thể approve
nhiều actions khi actor có đủ grants, không nhiều clicks bắt buộc, không free-form
“đồng ý” resolve all. Mỗi action20m theo đúng dimension (B/E/request), không role
MANAGER unlimited. Không quyền demo thì explanation needs higher authority, không
hứa xử lý trong app.

| Data state | Expected issue/outcome |
| --- | --- |
| B chưa tìm thấy, có thể đã có | FACT org-data owner tìm căn cứ |
| Đã xác minh chưa cấp B, policy cho cấp | AUTHORITY approver tạo B/activity decision |
| B valid, T>B và có exception path | POLICY, giữ T |
| Cấm rõ không exception | Exclude cost with refs; vẫn đối soát advance obligation |
| Missing payer và E maybe above8 | FACT trước, AUTHORITY nếu sau xác minh E>8 |
| Material FX/vendor refund/multi-claim flow | UNSUPPORTED affected money, không company-policy “cấm chi” |
| Provider fails/page NOT_READ | TECHNICAL incomplete, không pretend business escalation |

## 6. State/read-set/transaction

Case derived states DRAFT/PROCESSING/EVIDENCE_READY/WAITING/TECHNICAL_ERROR/
READY_TO_EXECUTE/SETTLED/STOPPED; EVIDENCE_READY (mới, §12.5) nghĩa "đọc chứng cứ
xong, chưa nối admission"; WAITING hiện issue set + dependencies, không một nhãn che issues.
Job QUEUED/RUNNING/WAITING_HUMAN/COMPLETED/FAILED/CANCELLED; instruction ISSUED/
PARTIAL/FULFILLED/SUSPENDED/SUPERSEDED/EXECUTION_UNKNOWN.
Input revision tăng material changes; control_epoch tăng Stop/Resume; case_version
tăng user/financial mutation, không bị mỗi provider progress increment.
Context/ledger/usage versions nằm read-set; cached read keyed tenant+source digest+
reader model/prompt/schema/representation/requested_fields, không cached decision.

| Command/event | Precondition và effect |
| --- | --- |
| create/submit | Session actor/scope valid; unique root; immutable revision; enqueue one active job/root |
| provider result | Source digest/input/control match; persist read only; no direct financial commit |
| commit decision/instruction | Check all read-set/grants/current control; transaction decision+instruction+usage+audit |
| answer | Owner/answer_kind+basis exact; response stale lưu history nhưng không apply; recheck |
| record actual | Permission/proof/external identity; preserve observed even violation, project separate fulfillment |
| Stop | Atomic epoch++; prevent new commits; suspend pending, handed-off => execution unknown until checked |
| Resume | Epoch++; current basis/reconcile first, no restart old instruction blind |
| Override | New scoped decision, retain old; no money/fact rewrite |
| crash/retry | Command-id same result; unique external transaction independent command-id; recover job from DB |

Provider I/O outside transaction. SQLite WAL/busy timeout, one Uvicorn process,
2 bounded workers; short BEGIN IMMEDIATE for mutations. Persistent jobs/retry
counters/read cache; restart takes incomplete jobs, no automatic duplicate effects.
Parser/render helper subprocess timeout5s/memory512MiB for public untrusted PDFs;
generated storage keys and no following URLs/scripts from source. HTTP call retries
once within global counters; outcome unknown calls don't become success or usage0.

Pilot ceilings lead-chosen before M0:8files,20pages/case,20MiB/file,40MiB total,
20MP/image,12LLM attempts/10OCR attempts/job,HTTP timeout20s,processing deadline90s,
2global jobs,1active job/root. Human waiting outside processing deadline.
Recovery key=(root,material_input_basis,field_or_relation,source_set_digest), không
đổi khi model viết lại issue ID. Preview/submission cùng basis reuse reads/counters;
Resume hoặc câu trả lời không thêm nguồn không reset quyền recovery. Nguồn mới
material có basis mới và ngân sách xử lý mới; lịch sử attempts vẫn được giữ.
M0 reports measured p50/p95/N; change technical ceilings only versioned on dev
evidence before holdout/publicfreeze. Core4 sequential, Esc5 max2 independent
scenarios concurrent; measured target <=120s/core and <=90s/esc, no guarantee by
design. Fixed ceilings low may reject valid documents: show LIMIT, don't fake pass.

## 7. Evaluation packet/outcome/learning contract

Packet directory input/ (raw + organization.json + submission.json), gold/
(latent.json + observable.json + allowed.json), manifest.json (digests/root/family/
split/profile). App only receives input; hidden oracle loaded by scorer afterward.
Organization input contains genuine simulated observable ledger/context, not E/S
expected/forced routing. Expense estimates and declaration are not verified payment.
Development>=15 distinct travel roots first; local meeting gate adds new cases;
mutations/clones don't inflate count. Holdout20 roots10routine/10human, group split,
strata before run. Calibration10+validation10 distinct eligible root opportunities
separate from holdout; origin labels determine real vs simulated evidence.

Dossier metrics unsafe_action, unsafe_affirmative_conclusion, union_dangerous_miss,
unnecessary_question, correct_auto_completion, technical_failure/all_submissions.
Issue-stage gold set/dependencies/owner/question; opportunity log before R/H.
Draft raw extraction, corrected draft, initial submitted decision and assisted
resolution distinct. No current source gold guesses rewarded because latent truth
happens to equal hallucination. Source-read errors aren't MISSING or zero.
Question rubric: owner/group/scope, known facts, crop/excerpt/refs, exact decision/
missing field/impact, one valid response from card. “Chưa xác minh” stays pending.

Lead algorithm: no model retraining. Fixed feature score before R/H:1 alternate
native text;0.75 native repr of current source available;0.5 alternate image;
0.25 same-page targeted reread; no eligible step => H independent threshold.
These are routing heuristics, NOT confidence of monetary truth. Fixed threshold
0.75, candidate grid0.25/0.5/0.75/1. R=one eligible extra read, H=ask owner;
one step/issue + job cap, no second recovery loop by changing issue IDs.
Paired offline H/R same initial snapshots, recorded/live modes disclosed. Select
one threshold on10 distinct verified-feedback roots (all4 buckets represented);
validation10 different roots, >=3 recoverable, >=3 irrecoverable, >=1 action flip.
Activate only zero unsafe union, no more unnecessary questions, >=1 extra correct
unassisted completion (or >=1 fewer unnecessary questions), within processing
deadline and mean additional provider calls <=2 per changed opportunity. Report
resource trade-off; recovery naturally can cost more than asking immediately.
N10 is pilot support floor, NOT CI or
production guarantee. If support/gain absent retain fixed and record unmet adaptation.
Validation used to tune becomes development; final20 holdout never candidate selection.
Simulation can test mechanism in isolated namespace only, not activate claimed
human-feedback adaptation. Verification records real human attribution separately
from economic data_origin SYNTHETIC. Public feedback pending/unverified by default;
offline human verifier adduces source/basis/trial provenance; API cannot set verified.
Gold-scoring alone is not real feedback. Label IDs/version/buckets/activation/
rollback persisted. Rollback on critical invariant failure on changed route.
Exact counterfactual outcomes not inferred from observed branch feedback.

## 8. Sources for technical calls, not runtime proof

[pypdf native-vs-scan limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
[pypdfium2 render](https://pypdfium2.readthedocs.io/en/stable/python_api.html),
[ReportLab](https://docs.reportlab.com/reportlab/userguide/ch1_intro/),
[Vite](https://vite.dev/guide/),
[Mistral OCR](https://docs.mistral.ai/studio/document-processing/basic_ocr),
[xkiro structured output](https://docs.xkiro.com/guides/structured-output/).
Native text presence alone doesn't prove OCRed PDF visual truth; detect scan/hybrid
and use OCR/compare representation when material. JSON schema validity isn't
fact/rights validation; pin effective configurations at M0, record alias/version
uncertainty if provider cannot resolve a snapshot, don't fake exact reproducibility.

## 9. Interface names cho các tasks

- EvidenceReader.read(source:SourceRef, budget:RunBudget) -> OcrSourceResult là async
  OCR-only (mọi trang, không native-text bypass; xem §12). `read_root(sources, reader,
  llm, budget, provider_mode) -> ReadResult` là async, ghép OCR→confidence→classify→
  extract→validate→match; mọi call X-Kiro là async/budgeted, validation/matching thuần
  sync. Proposals không có financial effect; LIVE/RECORDED_REPLAY không vào Reconciler
  cho tới khi có adapter admission riêng.
- Reconciler.assess(input:AssessmentInput) -> AssessmentResult là pure sync;
  snapshot chứa observations/relations, không thêm positional parameters khác.
- CaseWorkflow.execute(ctx:CommandContext, command:CaseCommand) -> CommandResult
  là async; CaseWorkflow.view(ctx:CommandContext, root_id:Id) -> CaseView là sync.
  run_job(job_id:Id) là async internal worker entry, không public LLM tool.
- CaseCommand tagged union trong domain/commands.py: CreateDraft(activity_data),
  AttachSources(root_id,uploads), ReviseDeclaration(root_id,declaration),
  Submit(root_id,declaration), AnswerIssue(root_id,Answer), Decide(root_id,DecisionCommand),
  RecordActual(root_id,RecordMoneyInput), Control(root_id,STOP/RESUME,reason),
  Override(root_id,supersedes_decision_id,DecisionCommand),
  MarkExecution(root_id,instruction_id,OPEN/CLOSED_CONFIRMED/UNKNOWN,refs,reason).
- CommandResult(case_view,job_id:Id|None,duplicate_command:bool). Client mutations
  dùng expected_case_version; STOP là control signal được phép áp trên version mới
  nhất sau kiểm actor/idempotency, không fail chỉ vì financial commit vừa tăng version.
  RESUME và edit vẫn guard version/basis; actual event trong STOP được ghi, không
  tự process/issue tiền đến khi resume.
- EvaluationRunner.run(packet:PacketInput, mode:ProviderMode) -> ActualResult
  là async; chỉ nhận input, không gold. IndependentScorer.score(actual:ActualResult,
  gold:GoldPacket) -> ScoreRow là pure sync. CLI/package entry main(argv:list[str]) -> int.
- Snapshot builder nằm workflow/snapshots.py; eligibility basis và money basis
  khác nhau. AllowedStep(kind READ_FIELDS/CROSS_CHECK/ASK_OWNER,issue_id,source_ids,
  fields,reason) chỉ nguồn thuộc root/session, no URL/policy/SQL/record-money actions.
- M0 RunBudget/RunManifest ở evidence/trace.py: caps,counters/deadline,mode,
  requested/returned/resolved model, prompt/schema versions, trace refs/usage unknown.

Test helpers tests/factories.py là unit-only: snapshot(T:int,E:int,C:int,A:int,
P:int,R:int,B:int,coverage:bool=True,**overrides) -> AssessmentInput, với verified
evidence literals được tạo trực tiếp; không mô phỏng chất lượng OCR. app_fixture
pytest fixture tạo tenant/context/tmp DB + injected Reader, root(ctx) -> Id;
execute(ctx,command) và view(ctx,id) luôn qua cùng CaseWorkflow. Không dùng test
helpers/expected gold trong app runtime hoặc live eval path.

Các fixture helpers của plan được định nghĩa ngay trong owning test task:
app_fixture.submit_packet(name,mode) qua load_input -> preview -> Submit -> job -> view;
record_received(instruction_amount,received) tạo instruction/evidence literal rồi
execute RecordActual, không update SQL tắt; hold_reader/release_reader dùng async
barrier để tạo race thực. reader_fixture có HTTP fake và side-effect spy; paired_validation
là literal independent pairs. write_test_packet, actual_affirmed_zero_without_coverage,
gold_requires_fact và candidate_threshold chỉ tạo DTO literals, không gọi Reconciler.

## 10. Các hợp đồng giao nhau đã khóa sau review plan

### 10.1. Obligation coverage, reversal và supplementation

Reconciler trả S có căn cứ và proposal, không tự phát hành tiền. Workflow xử lý
coverage trong transaction: chỉ một instruction actionable/root. remaining là
**net** amount chưa fulfilled sau linked reversal; instruction cũ/actual luôn giữ.

| Current state | Effect tại commit sau mọi fact/policy/grant gates |
| --- | --- |
| Không active instruction, S khác 0 | Issue abs(S), direction theo dấu S |
| Active remainder cùng chiều/abs(S), material instruction basis không đổi và authority/coverage còn hợp lệ | Giữ instruction; retry/new command không issue nữa |
| S/chiều hoặc material instruction basis đổi, kể cả S bằng nhau; execution NOT_STARTED hoặc CLOSED_CONFIRMED có chứng cứ | Supersede phần chưa thực hiện của instruction cũ, issue toàn abs(S) hiện tại sau mọi gates; không issue delta song song |
| Execution OPEN/UNKNOWN, S/chiều/basis đổi | Suspend/EXECUTION_UNKNOWN; xác minh ngoài app trước replacement; không tự giải phóng coverage |
| S=0, execution đã xác minh xong, mọi gates sạch | Lưu conclusion BALANCED; không instruction số 0 |
| Overpay/wrong payee/material unresolved | Giữ actual/incident; chặn action mới cho tới giải quyết đúng owner/basis |

Ưu tiên: Stop/revoke/incident/material gates trước; tiếp theo execution OPEN/UNKNOWN
khi basis/S đổi; sau đó changed-basis/amount replacement; retain chỉ khi conditions
đều đúng. S0 còn OPEN/UNKNOWN không tự đóng. material instruction basis gồm cost/
eligibility/beneficiary/activity/authorization và rule/usage liên quan; pure confirmed
receipt làm S và net remaining cùng giảm không đổi cost instruction basis. Không
so equality của cả money_basis để bắt replacement mỗi receipt.

Ví dụ cùng root: E6/A2/P0 ⇒ I4; command mới vẫn I4. Nhận P2 ⇒ S2,
I4 remaining2. Đóng đợt thực hiện có căn cứ rồi thêm eligible employee-paid2 ⇒
S4; supersede remainder2 cũ, new I4 là instruction duy nhất actionable. Old fulfilled2
giữ nguyên, không được cộng hai remainder hoặc hoàn lại cùng phần đã trả.
MarkExecution thuộc kế toán đúng grant/scope; mở trước khi thực hiện ngoài app,
đóng phải có confirmation/proof về đợt giao, không default CLOSE khi chưa thấy tiền.
App không bảo đảm chặn một khoản chuyển tiền ngoài app chưa được khai báo.

Reversal linked P2 làm net P0 và net fulfillment0: cùng I4 remaining4, không tạo R.
I4 đã fulfilled4 rồi reverse1 ⇒ net P3, remaining1; SETTLED hết hiệu lực. Nếu
instruction gốc đã SUPERSEDED, không tái kích hoạt nó song song: reconcile current S
với active coverage theo bảng. Duplicate/over-reversal bị chặn; audit gross giữ đủ.
Predecessor I4 fulfilled2 đã supersede thành new I4, rồi reverse old P2 ⇒ S6.
Default grant4 không cho auto I6: suspend stale coverage, AUTHORITY trước; chỉ
issue I6 sau exact authorized decision6. Current active OPEN/UNKNOWN thì còn phải
xác minh execution, không tái kích hoạt predecessor.
Reversal A/P/R giảm đúng loại gốc; đảo payment portion employee/company làm cost_basis
đổi và recheck E/C. Không mặc định mọi bank reversal là employee return.

### 10.2. Economic usage và basis

Economic key verified=(tenant,issuer_identity,document_number,document_date) cho
invoice có định danh đủ; expense/payment portions có IDs riêng. Source digest chỉ
dedup bytes. Cash/no-number expense dùng binding/financial confirmation có trách
nhiệm để xác lập key; không tạo identity từ amount/date/name giống nhau. Candidate
match chưa đủ định danh hoặc relation chưa rõ ⇒ FACT, không false duplicate.

Tenant usage registry trong workflow/schema.sql: economic_key, owner_root,
expense_id, verified payment_portion keys, evidence refs, version. Một expense
scope chỉ có một owner root; payment portions mới cùng owner thêm một lần. Hai
roots khác activities nhận cùng verified obligation không được tạo hai eligibility/
instructions; route conflict để trả về canonical owner, không trộn hai chuyến.
Ghi usage/eligibility/instruction atomically; financial money thật vẫn được ghi
nếu vi phạm; hủy/supersede instruction không xóa incurred expense hoặc usage owner.

cost_basis hash chứa expense identity/incurred/time, eligible paid portions/payer/
binding, activity purpose/relations, expense-time policy/B/exception scope và
eligibility authorization. Thay đổi các trường đó phải reassess E **tổng**, không
reuse grant8 rồi cộng portion mới để thành E9. money_basis chứa A/P/R net scoped
events/coverage/ledger; receipt P đúng scope không đổi cost_basis. Khi có explicit
revocation, new action/current authority phải kiểm lại; expiry không xóa actual.
unpaid từ outstanding đã xác minh và **gross paid**, không T−E−C. T10/employee paid7/
eligible5/company paid3 ⇒ unpaid0. Business-incurred bị loại khỏi E vẫn trong T;
personal không phục vụ hoạt động ngoài T/E; A/P/R giữ thực tế.

### 10.3. Conclusion, state, context và commands

SettlementConclusion lưu BALANCED/OUTSTANDING/BLOCKED cùng projection, refs/read-set
và disposition từng khoản (ACCEPTED/EXCLUDED/UNRESOLVED, amount/rule/reason/refs).
Không có instruction không chứng minh balanced. Priority CaseView: STOPPED >
PROCESSING current job > TECHNICAL_ERROR material processing/unsupported/limit >
EVIDENCE_READY (đọc xong, chưa nối admission) > WAITING business issue/unknown execution
> READY_TO_EXECUTE actionable instruction > SETTLED. DRAFT áp dụng trước submit. SETTLED chỉ khi S known0, relations/coverage/
rights đủ, không material problems/active issue/remaining/pending/unknown execution.
No extra human approval để kết thúc routine. Facts unresolved không được lưu
affirmative conclusion BALANCED; historical conclusion còn audit nhưng superseded.

ProcessingProblem trong view có affected_fields, relevance, blocking, next_action.
UNKNOWN relevance hoặc material related ⇒ chặn affected conclusion, hiện lỗi xử
lý/ngoài khả năng hỗ trợ; proven unrelated ⇒ quarantine refs/reason, không blanket
block. NOT_READ không MISSING; không đếm TECHNICAL như business escalation đúng.

context_version aggregate tăng khi bất kỳ policy/grant/B/activity authorization/
exception/revocation authoritative record đổi qua validated command/import. File
ngoài DB chỉ thành authority sau import có version/hash; runtime không đọc mutable
file như quyền hiệu lực. Snapshot giữ bản cũ; commit transaction kiểm aggregate
version, ledger/usage/input/control và grant hiệu lực hiện tại. Explicit revoke
suspend pending instruction; expiry sau issue không tự bắt reapprove receipt.

Command identity=(tenant,actor_id,command_id) + canonical fingerprint(kind,root,
meaningful payload,expected version). Same identity/fingerprint replay stored
historical CommandResult, view mới dùng endpoint view. Same identity khác payload
⇒409 IDEMPOTENCY_CONFLICT; tenant khác độc lập. Physical transaction unique riêng.
Override là tagged command với exact grant/scope/basis/reason, không free-text
approval hoặc rewrite facts. “Cancel” trong UI chỉ suspend/supersede instruction,
không xóa cost/actual; handed-off unknown không coi là chưa thực hiện.

### 10.4. Preview/Submit và activity mới

Một work item/root/material basis có submit_requested và phases READING/ASSESSING/
DONE; preview chỉ đọc, chưa có financial effect. Submit lúc preview RUNNING lưu
submit_requested; sau read worker assess một lần nếu basis/control còn đúng.
Preview DONE dùng cached reads để assess; FAILED giữ lỗi xử lý và bounded counters,
không silently success. Material basis mới supersede work cũ, enqueue successor
sau worker cũ thoát; late result chỉ cache/audit an toàn, không commit basis mới.
Restart phục hồi submit_requested/counters; one active worker/root. Recovery key
field/source/representation không reset bởi declaration edit không thêm chứng cứ
cho field; basis digest và remaining RunBudget được lưu trước chọn R/H.

Activity catalog do server/context giữ, UI chọn tên/ngày. CreateDraft có thể chọn
existing authorized activity hoặc tạo ProposedActivity với server-generated ID;
draft creation **không** cấp quyền hoạt động/B. ProposedActivity chưa có context
hiện FACT tìm record hoặc AUTHORITY khi đã xác minh chưa cấp; Decide đúng grant
AUTHORIZE_ACTIVITY/SET_BUDGET tạo record. Same activity→same root, two activities→
two roots. Demo context import chỉ synthetic validated input trong sandbox và
audit import origin; không cho raw client role/B tự thành corporate authority.

### 10.5. Recovery selection và activation attribution

Freeze OpportunitySnapshot trước route: read_set, sources/representations/page/
fields, issue/dependencies, eligible steps, config/prompt/model/policy, counters,
remaining budget/recovery keys và remaining processing time. Cả H/R fork y hệt
snapshot digest; waiting human ngoài deadline nhưng không cấp R quota mới.
H-added source không xuất hiện trong paired initial R. Replay dùng actual recorded
read outcomes keyed representation/config; không dùng gold làm read output.

Eligible step phải readonly, nguồn thuộc root, còn quota/time, chưa thử cùng
recovery key. Step score giữ 1/.75/.5/.25 ở §7; chọn max score, tie theo estimated
provider calls tăng dần rồi stable(source_id,page,fields,representation_id).
Không đủ eligible steps ⇒ H. R khi selected score >= threshold; bước đã đọc
chỉ eligible targeted reread nếu representation/field chưa thử và còn one recovery.
Conflict đọc thêm vẫn FACT; score không là quality/confidence tiền.

Selection calibration10 roots, validation10 roots khác, final holdout riêng.
Pin selected candidate trước validation; nếu sửa vì validation thì tập đó thành
development, tạo validation mới. Activation phải có ≥1 **changed opportunity**
beneficial an toàn với căn cứ: H→R thật sự đọc được proof và tránh câu hỏi. R→H
chỉ tiết kiệm calls không đủ gain đã yêu cầu ở §7. Aggregate gain
do noise ở unchanged route không đạt. Unnecessary H chỉ khi eligible paired R đã
chứng minh đủ proof/quota; không dùng latent truth để gọi câu hỏi initial là thừa.
Giữ zero unsafe union/no increased dossier unnecessary và bounded resource gates;
report changed vs unchanged counts, paired support/refs/budget và origin nhãn thật.
Release fail nếu unsafe_action OR unsafe_affirmative_conclusion union theo dossier
>0, không chỉ khi đã issue tiền. N0 không chứng minh an toàn.

## 11. Precision gates của scorer/replay

Opportunity ID=(root,material basis,issue/stage,pre-route digest) dùng flip/cost/
support; root distinct dùng unsafe/completion/unnecessary-dossier rate; card ID
dùng avoided-question count. Một root hai issues, R giải FACT nhưng POLICY còn
manager ⇒ changed_beneficial1/avoided_cards1/additional_auto_completion0/roots1.
Không lấy successful field read làm whole dossier completion; activation giữ
positive completion **hoặc** avoided-card gain và các gates §7/§10.5, báo unit/N riêng.

Paired R chưa có actual matching recording ⇒ UNOBSERVED, không proof/gain. Muốn
chấm phải chạy bounded LIVE R từ frozen snapshot và giữ raw response/attempts/refs/
mode/time; replay đúng source/page/fields/representation/config. Gold không lấp
read output thiếu. Validation gold độc lập không phải human-feedback label giả.

Grouping axes được ghi trước selection: root/economic/source clone bắt buộc;
family/template/layout/issuer dùng khi ảnh hưởng độc lập, font/A4 chung không đủ
để gộp. Nếu family overlap không tách được, root-heldout chỉ chứng minh trong các
families đã khai báo, không claim unseen-family; gần trùng cùng nghĩa vụ vẫn fail.

## 12. Pipeline chứng cứ — DTO và interface (chốt 14/10/2026)

Nguồn: [design §15](ARCHITECTURE_AND_EVALUATION.md) và
[plan Hoangha-evidence](../superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md).
§12 cụ thể hóa DTO/interface; khi shorthand ở §3/§9 chưa đủ, dùng §12. Đây là
contract thiết kế, chưa phải code hay proof runtime. **Ranh giới:** mọi type dưới
đây là proposal/evidence, không phải `Fact.KNOWN`; không đổi T/E/A/P/R/S, policy,
authority hay ghi tiền.

### 12.1. OCR types

- `OcrWord(text:str, block_start:int|None, block_end:int|None, confidence:float|None)`;
  offset block-local.
- `OcrBlock(id:str, kind:str, content:str, bbox:BBox|None, words:tuple[OcrWord,...])`.
- `OcrPage(page:int, markdown:str, blocks:tuple[OcrBlock,...])`.
- `OcrSourceResult(source_id:Id, source_digest:str, provider:str, model:str,
  pages:tuple[OcrPage,...], raw_artifact_ref:str)`.
- `BBox` = bốn toạ độ `top_left_x/top_left_y/bottom_right_x/bottom_right_y` float hữu hạn.
- `PageCoverage(source_id:Id, page:int, state:OCR_COMPLETE|NOT_READ|ERROR,
  artifact_ref:str|None, problem:str|None)`.
- `async MistralOcrClient.ocr_file(source:SourceRef, *, budget:RunBudget)
  -> OcrSourceResult`: PDF dùng document payload, ảnh dùng image payload,
  `include_blocks=true`, word confidence, không trả base64; thiếu page ⇒ problem,
  không empty-success.

### 12.2. Phân loại và vai trò

- `DocumentType` = strict enum 17 giá trị: 16 `ExpenseDocumentType` của Hoangha
  (`E_INVOICE, PAPER_RECEIPT, CARD_SLIP, PAYMENT_PROOF, TRANSPORT_TICKET,
  HOTEL_RECEIPT, COLLECTION_RECEIPT, CONTRACT, QUOTATION, PURCHASE_ORDER,
  ACCEPTANCE_RECORD, DELIVERY_NOTE, GOODS_RECEIPT, SUPPLIER_CONFIRMATION, OTHER,
  UNKNOWN`) + `SETTLEMENT_FORM`.
- `DocumentEvidenceRole` = strict enum `SETTLEMENT_DECLARATION,
  ORIGINAL_EXPENSE_EVIDENCE, PAYMENT_EVIDENCE, SUPPORTING_DOCUMENT, UNKNOWN`; **tách**
  khỏi page-level `EvidenceRole` của §2.
- `DocumentClassification(document_id:Id, source_id:Id, page_range:tuple[int,int],
  block_ids:tuple[str,...], document_type:DocumentType,
  roles:tuple[DocumentEvidenceRole,...],
  role_refs:Mapping[DocumentEvidenceRole,tuple[EvidenceRef,...]],
  alternative_document_types:tuple[DocumentType,...], classification_confidence:float|None,
  signals:tuple[str,...], refs:tuple[EvidenceRef,...])`. Model đề xuất range; code
  validate bounds và tạo unit ID tất định. Unit trùng/chồng không tương thích ⇒ unresolved;
  nhiều loại khác range trong một PDF không phải conflict.
- Map mặc định do code sở hữu: original = `E_INVOICE, PAPER_RECEIPT,
  TRANSPORT_TICKET, HOTEL_RECEIPT, COLLECTION_RECEIPT`; supporting = `CARD_SLIP,
  PAYMENT_PROOF, CONTRACT, QUOTATION, PURCHASE_ORDER, ACCEPTANCE_RECORD, DELIVERY_NOTE,
  GOODS_RECEIPT, SUPPLIER_CONFIRMATION`; `OTHER` supporting; `UNKNOWN` unknown;
  `SETTLEMENT_FORM` declaration. `PAYMENT_EVIDENCE` chỉ thêm khi nguồn tự thể hiện
  payer/payee/amount/identity/status với refs riêng.
- `async classify_documents(ocr, *, llm, budget) -> tuple[DocumentClassification,...]`:
  một batch/root; `UNKNOWN` không chọn schema đoán.
- Bảng compatibility type↔role (code sở hữu; model không tự đổi):

| `DocumentType` | Role mặc định | Ghi chú |
| --- | --- | --- |
| `SETTLEMENT_FORM` | `SETTLEMENT_DECLARATION` | nguồn của matching |
| `E_INVOICE`, `PAPER_RECEIPT`, `TRANSPORT_TICKET`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT` | `ORIGINAL_EXPENSE_EVIDENCE` | có thể thêm `PAYMENT_EVIDENCE` nếu nguồn tự thể hiện payer/payee/amount/identity/status |
| `CARD_SLIP`, `PAYMENT_PROOF` | `SUPPORTING_DOCUMENT` | thêm `PAYMENT_EVIDENCE` chỉ khi có đủ payer/payee/amount/identity/status với refs riêng |
| `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION`, `OTHER` | `SUPPORTING_DOCUMENT` | `OTHER` chỉ schema chung |
| `UNKNOWN` | `UNKNOWN` | không extraction đoán |

Schema trường theo từng loại (field chung, field riêng, line shape) do
[plan Hoangha-evidence](../superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md#schema-field-names-and-validation-ownership)
giữ và E0 pin; profile/critical-field matrix pin tại Hoangha revision `1ee33487…`
(`policy/document_validity.py`).

### 12.3. Trích xuất và trạng thái trường

- `FieldState = Literal["FOUND","NOT_PRESENT","UNREADABLE","AMBIGUOUS","NOT_APPLICABLE"]`.
- `CandidateValue = str|int|Decimal|bool|tuple[str,...]` (list chỉ cho trường nguồn
  nêu như `invoice_refs`, không cho amount).
- `ValueAlternative(value:CandidateValue, refs:tuple[EvidenceRef,...])`.
- `FieldCandidate(field:str, state:FieldState, value:CandidateValue|None,
  alternatives:tuple[ValueAlternative,...], refs:tuple[EvidenceRef,...])`: `FOUND`
  cần value+ref; `AMBIGUOUS` giữ ≥2 alternative có nguồn và không value tổng; các
  state khác không value. Không thêm generic confidence.
- `DocumentLine(id:Id, fields:tuple[FieldCandidate,...], refs:tuple[EvidenceRef,...])`;
  code cấp id sau validate (bỏ id do model tạo).
- `DocumentProfileIssue(code:str, field:str|None, status:UNRESOLVED|INVALID,
  message:str, refs:tuple[EvidenceRef,...], blocking:bool)` — chỉ validity của
  profile/extraction, không policy.
- `DocumentAnalysis(source_id, document_type, roles, classification_confidence,
  alternative_document_types, classification_refs, fields, line_items,
  confidence_status:ASSESSED|SKIPPED_NO_NUMERIC_CANDIDATES|UNRESOLVED, confidence_refs,
  profile_status:CLEAR|NEEDS_HUMAN|UNKNOWN, profile_findings, refs, warnings)` +
  `document_id, page_range, block_ids, role_refs` từ classification đã validate.
- `async extract_document(ocr, classification, *, llm, budget) -> DocumentAnalysis`:
  một call/tài liệu.
- `validate_document(analysis, ocr, quality) -> DocumentAnalysis` pure sync: validate
  ownership source/page/block, quote chuẩn hoá khớp, schema, nhất quán state/value,
  required field và compatibility type/role.
- Confidence: `collect_low_confidence_blocks(ocr, threshold=0.85)` tạo candidate;
  `async review_ocr_quality(candidates, *, llm, budget) -> ConfidenceReview` một batch;
  `ConfidenceReview(status:ASSESSED|SKIPPED_NO_NUMERIC_CANDIDATES|TECHNICAL_ERROR,
  block_assessments)` với `BlockAssessment` có `importance/quality_state/review_action/
  canonical_fields/observed_text/reason/...`. `SKIPPED_NO_NUMERIC_CANDIDATES` **không**
  phải PASS. Model chỉ đánh giá readability; không thay text/thay value.
- Sửa schema: tối đa **một** repair call/root; sau đó giữ lỗi kỹ thuật + unresolved.
- Cap X-Kiro: `MAX_LLM_INPUT_CHARS=120_000`, `MAX_OUTPUT_CHARS=20_000` (giới hạn
  pilot, không phải context window); ghi vào `RunManifest` (`max_llm_input_chars`,
  `max_llm_output_chars`, `limit_version`, `limit_origin`).
- **Criticality matrix `SETTLEMENT_FORM`:** Hoangha không có loại này; E0 pin ma trận
  critical/required cho `SETTLEMENT_FORM` trong `document_profiles.py` (field trọng yếu
  tối thiểu: `declared_name`, `trip_*`, các `printed_*`, `amount_words`, và per-row
  `amount`/`invoice_refs`). Đây là quyết định của lead, phải có test cho từng field
  trọng yếu trước khi E3/E5 dùng. Field critical thiếu confidence ⇒ unresolved, không PASS.

### 12.4. Matching

- `EvidenceLink(item_id, source_id, document_id, status:AUTO_LINK|SUGGEST_LINK,
  method:INVOICE_NUMBER_EXACT|AMOUNT_AND_CONTENT|LLM_RESOLVED, score:Decimal,
  allocated_amount:Decimal|None, explanation:str, refs)`.
- `DocumentRowMatch(item_id, paper_amount:Decimal|None, category_candidate,
  evidence_status:ORIGINAL_EVIDENCE|ALTERNATIVE_EVIDENCE|NO_EVIDENCE,
  alternative_evidence_type, matched_document_date, original_total:Decimal|None,
  allocated_total:Decimal|None, no_evidence_reason:str|None, refs)`.
- `EvidenceMatchFinding(code, status:PASS|UNRESOLVED, message, refs)`;
  `EvidenceMatchingResult(links, rows, findings, unmatched_source_ids)`.
- `match_paper_evidence(paper, documents) -> EvidenceMatchingResult` pure sync; yêu cầu
  `paper.document_type == SETTLEMENT_FORM` (giấy quyết toán upload). Không có form ⇒
  không gọi hàm này; report ghi finding `SETTLEMENT_FORM_MISSING`. Port core Hoangha revision `1ee33487…`
  (`application/paper_evidence_matching.py`): exact invoice ref → `AUTO_LINK`/1.0;
  ngược lại amount 0.60 (≤1 VND) + semantic ≤0.30 + party 0.12/0.20 + non-original
  +0.10, cap 1.0; `<0.50` bỏ, `[0.50,0.75)` suggestion, `>=0.75` auto; tie theo thứ
  tự gắn nguồn.
- `async resolve_evidence_suggestions(result, documents, *, llm, budget)` một batch khi
  có suggestion; model chỉ promote cặp có sẵn ở `>=0.90`, không tạo cặp mới.
- Cardinality: một nguồn auto-link cho dòng khác mặc định chỉ suggestion; phân bổ
  nhiều dòng chỉ khi mỗi dòng lặp `invoice_ref` chuẩn hoá + amount, tổng ≤ giá trị
  chứng từ. Chứng từ hỗ trợ không tính là chứng từ gốc; `original_total` chỉ cộng
  chứng từ gốc/phần phân bổ gốc; amount thiếu giữ `None`.

### 12.5. ReadResult và consumer boundary

- `async read_root(sources, *, reader, llm, budget, provider_mode) -> ReadResult`:
  OCR mọi nguồn → confidence batch có điều kiện → classification batch → extraction
  mỗi tài liệu → validate → match → suggestion batch tuỳ chọn; dừng trước reconciliation/
  policy/tiền.
- `ReadResult(provider_mode, data_origin:LIVE_READ|RECORDED_REPLAY|STUB_TRANSCRIPTION,
  documents, links, row_matches, match_findings, page_coverage, problems, trace_refs)`
  + giữ `units/observations/relations` cũ.
- `CaseView` expose `ReadResult` như evidence report. Trong LIVE/RECORDED_REPLAY,
  job đọc xong ⇒ **trạng thái riêng `EVIDENCE_READY`** (thêm vào `CaseState`; khác
  `WAITING` vốn nghĩa "business issue/execution chưa rõ"), `conclusion=None`, không
  instruction; `assessment_ready=false`,
  `assessment_blocker=EVIDENCE_ASSESSMENT_PENDING` (plan A5 releases the earlier
  `EVIDENCE_ADMISSION_NOT_CONNECTED` guard once the typed admission consumer is
  wired). Ưu tiên `CaseView` chèn
  `EVIDENCE_READY` ngay dưới `TECHNICAL_ERROR`, trên `WAITING`; không tạo question
  card. Sau khi consumer typed chạy, `CaseView` hiển thị conclusion/instruction
  thật (EVIDENCE_READY chỉ còn khi report đã publish nhưng chưa assess). Guard
  trong `_build_assessment_input` (không chỉ `_submit`) để Answer/Resume/Decide
  không rơi lại transcription STUB. STUB giữ nguyên đường assessment hiện có.
- **`SETTLEMENT_FORM` là giấy quyết toán upload** (paper). Nếu root không có
  `SETTLEMENT_FORM`, pipeline vẫn OCR/phân loại/trích xuất chứng từ nhưng **bỏ qua
  matching** và ghi finding `SETTLEMENT_FORM_MISSING` (evidence-only, không chặn nộp,
  không phải business issue). Khai báo in-app không phải `SETTLEMENT_FORM`.
- **Q34 hoãn:** §12/report **không** phát hiện/báo nguồn ngoài phạm vi employee-paid
  trong plan này; đây là **lỗ đã biết** (report im lặng với case company-direct/
  other-payer) do plan finance kế tiếp sở hữu.
- Cache/artifact identity: `(tenant, root_id, source_id, source_digest, reader_config)`;
  `reader_config` gồm model/prompt/schema/profile/representation/requested-fields version.
  Artifact private dưới `uploads_dir.parent/"artifacts"`, cùng vòng đời nguồn, trần
  20 MiB/source, 40 MiB/root.
- Worker: `async CaseWorkflow.run_evidence_job(job_id) -> None` →
  `workflow/evidence_jobs.py::run_evidence_job`; `drain_evidence_jobs(workflow, stop)`
  claim QUEUED transactionally, chạy một job một lúc; FastAPI lifespan sở hữu task.
  Persist `jobs.input_basis_json` (additive migration) + `attempts_json`.

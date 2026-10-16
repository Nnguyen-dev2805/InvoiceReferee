# InvoiceReferee final — Implementation contracts

Ngày13/10/2026. Companion của implementation plan; cụ thể hóa Q1–Q31 và
[disposition review](reviews/2026-10-13/SYNTHESIS.md), không dùng rebuild.
Đây là contract thiết kế, không phải code hoặc proof runtime. Các lựa chọn của
lead (cấu trúc DTO, enum, giới hạn pilot, thuật toán threshold) được ghi rõ bên dưới.
§10 khóa chi tiết sau review; khi shorthand ở các mục trước chưa đủ, executor dùng
§10, không tự mở nghiệp vụ hoặc suy đã đạt runtime từ contract.
**Cập nhật 15/10/2026:** activity budget B là dữ liệu legacy, không phải gate; xem
[ADR0009](../adr/0009-activity-budget-out-of-scope.md) và §16 của design.

## 1. Scope và scalar types

Root unique trong một sandbox: (organization_id, employee_id, activity_id).
Một root có nhiều revisions, không nhiều hồ sơ độc lập đếm lặp cùng nghĩa vụ tiền.
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
| domain/policy.py | PolicyVersion(id,version,effective_from/to,profile,rules); Grant(id,version,actor,actions,scope,max_amount,effective_from/to); BudgetDecision legacy record (accepted for old-context compatibility, not a current decision input); ExceptionDecision(rule_id,expense_ids,activity,max_effect,actions,actor,grant_ref,decided_at,effect_range,refs,reason) |
| domain/case.py | CaseScope(tenant,employee,activity,profile); ReadSet(input_revision,control_epoch,context_version,ledger_version,usage_version); AssessmentInput(scope,expense_facts,observations,relations,confirmations,ledger,coverage,policy,grants,budget (legacy, ignored),exceptions,previous_eligibility,read_set,as_of); FinancialEffect(direction:PAY/COLLECT,amount:Vnd,employee,activity,basis); AssessmentResult(projection,issues,problems,required_authorizations,allowed_effect:FinancialEffect\|None,cost_basis,money_basis); CommandContext(session_id,actor_id,command_id,expected_case_version); EligibilityDecision(E,cost_basis,actor_or_system,grant_refs,refs); SettlementConclusion(status,projection,expense_dispositions,read_set,basis,refs,actor_or_system,decided_at); Instruction(id,root_id,direction,amount,status,basis,authority_refs,supersedes_id,fulfilled_amount:Vnd,remaining:Vnd,execution_state:NOT_STARTED/OPEN/CLOSED_CONFIRMED/UNKNOWN); CaseView(id,version,state,summary,sources,issues,problems,conclusion,instructions,actual_money:Projection,audit) |
| domain/issues.py | BusinessIssue(id,kind FACT/POLICY/AUTHORITY,field_or_rule,owner,depends_on,status,basis,refs,question); ProcessingProblem(kind TECHNICAL/LIMIT/UNSUPPORTED,affected_fields,message); QuestionCard(issue_id,known_facts,excerpt_refs,required_answer,effects,owner); Answer(issue_id,basis_id,answer_kind,value,refs,reason); DecisionCommand(issue_ids,basis_id,actions,effect_scope,amount,reason,refs) |
| domain/commands.py (S6) | DigitalExpenseLine(item_id ổn định,description,category?,expense_date,amount:int,evidence_status ORIGINAL/ALTERNATIVE/NO_EVIDENCE,alternative_type?,exception_reason?,note?,source_ids); Declaration += settlement_type ADVANCE_SETTLEMENT/EMPLOYEE_REIMBURSEMENT (default ADVANCE_SETTLEMENT), submission_source PAPER_SCAN/DIGITAL_FORM (default PAPER_SCAN), digital_lines, no_advance_asserted + no_advance_reason. Server validate toàn bộ + resolve source_ids trên attached sources; submit digital yêu cầu cùng canonical hash với bản đọc. |
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
| Grant/exception | Immutable organization record hoặc command đúng quyền | Model output, client role, ảnh chữ ký/name match |
| Dòng tiền trong hồ sơ | `DOSSIER_RECORDS`: tổng các giao dịch đã xác nhận trong scope của hồ sơ; hoặc coverage legacy hợp lệ | Upload chưa xác nhận, số ứng/hoàn chỉ kê khai, khẳng định đã kiểm tra toàn bộ ngân hàng |

Confirmed actor lấy từ server session/grant. Confirmation tiền chứa field/value,
nguồn đã kiểm, scope/time/loại money, reason và verifier, không approval chung.
Model output chỉ là observation/proposal; admissibility kiểm source role, positive
predicate, binding, quality/conflicts và literal locator. Exact quote có thật
chưa tự chứng minh payer/received. Không xây generic semantic-proof engine; viết
predicate tests cho bảng trên và đo false-known raw với gold độc lập.

Context demo 16/10/2026 có `company_tax_id` tùy chọn để lưu MST chuẩn tổ chức và
giữ qua snapshot/scoped loader. Trường này là dữ kiện định danh; chỉ việc lưu
trường không chứng minh predicate đối chiếu MST bên mua đã được triển khai.
Danh mục mặc định và context riêng TC01–TC25 ở `data/demo/manifest.json`; các
transcription/hoạt động demo cũ được tách thành fixture chỉ dành cho hồi quy.
Theo yêu cầu chạy chung TC01–TC25, context mặc định chứa25 khoản ứng và
`coverages` riêng theo activity. Scoped loader chỉ cung cấp đúng một khoản ứng
và history của activity đang xét dưới `ledger`/`coverage`; các context một case
cũ vẫn dùng `coverage` như trước. Không dùng lịch sử của case khác để xác lập0.

**Luồng UI hiện hành — sửa theo quyết định tiếp theo ngày 15/10/2026:** không có
checkbox/nút “Xác nhận lịch sử ban đầu”. Kế toán kiểm chứng từ ứng và bấm
**Xác nhận ghi nhận** đúng một lần. Sau source/binding/party/completion guards,
backend ghi A và tạo `DOSSIER_RECORDS` để đối soát các giao dịch đã ghi nhận cho
đúng employee/activity. Không coi đây là lời kế toán xác nhận toàn bộ sổ ngân
hàng, không tạo opening_balance=0 hoặc trích dẫn chứng minh không có khoản khác.
Các loại chưa có giao dịch được phản ánh là chưa phát sinh **trong phạm vi sổ
hồ sơ**, không phải khẳng định toàn bộ thực tế ngoài hệ thống bằng0.

Chỉ dữ kiện được xác nhận vào A/P/R. Unknown/unallocated/conflicting events vẫn
chặn đối soát; ứng kê khai thiếu bản ghi không tự thành A=0. Nhân viên upload
bằng chứng hoàn chỉ tạo draft chờ kế toán; accountant xác nhận thực nhận theo
đúng COLLECT mới tăng R. P/R đúng lệnh/source cập nhật trạng thái theo dõi trong
transaction và audit. Bản ghi ứng import có thể bắt đầu theo dõi dossier khi
xác nhận thực hiện đúng lệnh P/R, không bắt tạo thêm một khoản ứng.

Mã giao dịch chống trùng, version/scope/role guards và giới hạn quyền giữ nguyên.
Bổ sung quá khứ/ngoài luồng, đảo, unknown và context ledger thay đổi được kiểm
lại; không có thao tác xác nhận lịch sử chung trên UI để bỏ qua vấn đề cụ thể.
S6: khi checkpoint `DOSSIER_RECORDS` đã tồn tại nhưng không còn current, kế toán
có grant `RECORD_ACTUAL` đúng scope/profile có thể dùng
`RecheckDossierHistory(root_id,reason)` sau khi đối chiếu các khoản đã ghi.
Lệnh versioned/idempotent này chỉ làm mới checkpoint dossier, giữ source
`DOSSIER_RECORDS`, không tạo opening balance0 hoặc xác nhận toàn bộ ngân hàng;
không có checkpoint, có giao dịch chưa xác minh/chưa phân bổ/mâu thuẫn thì từ chối.
Không dùng thao tác này để tự đóng một vấn đề dữ kiện cụ thể.

Legacy API `ConfirmMoneyHistory` / `MANAGED_HISTORY` giữ cho dữ liệu/caller cũ,
nhưng UI không gọi và không yêu cầu người dùng thực hiện. Xác nhận lại một biên
nhận ứng đã ghi có thể thiết lập dossier tracking mà không cộng A lần nữa.

Coverage cấu trúc legacy (`CONTEXT` / `ACCOUNTANT_CONFIRMATION`) vẫn đọc được
và giữ quy tắc cũ: scope/time/funds/kinds/opening/witness; xác nhận kế toán theo
ngày và version sổ. Không tự chuyển legacy sang managed. Upload chứng từ hoặc
trả lời `ledger:coverage` bằng văn bản không tạo checkpoint. Known unrelated sources được quarantine có lý do; unknown
relevance is FACT; material unsupported evidence blocks the affected conclusion.
Source encrypted/corrupt/over-limit là processing problem.

`ActivityAcceptance` records an accountant's source-bound confirmation that a
completed advance voucher belongs to the dossier's employee and work. It includes
actor, time, transaction key, reason and refs. It is a work-acceptance fact only:
the activity remains PROPOSED and no grant, expense eligibility, or payment action
is created (ADR0010).
Policy/grant có effective interval; policy eligibility theo expense time,
grant hành động theo decision/commit time; retroactive effect phải explicit.
Legacy B có thể còn trong context nhưng không tham gia quyết định hiện tại (ADR0009).

### 3a. Phạm vi chi phí mở rộng (chốt 14/10/2026, plan general-expense)

Một quy trình quyết toán chi phí công việc do nhân viên trả (có ứng hoặc đã xác
minh không ứng), gồm công tác, tiếp khách tại chỗ, mua văn phòng phẩm/thiết bị nhỏ
và dịch vụ vận hành nhỏ. Giữ nguyên 8/4/20; B ngoài phạm vi quyết định hiện tại. Không mang hạn mức 100tr
của Hoangha, không bắt routine chờ kế toán duyệt.

- **Hồ sơ hoạt động do server/context sở hữu** (`TRAVEL` hoặc `WORK_EXPENSE`); giấy
  quyết toán dùng chung (định danh/mục đích/tổng/số bằng chữ) + refinement công tác.
  Giấy ngoài công tác **không** bị ép khai `trip_*` (T1).
- **Hạn mức theo loại khoản (mỗi khoản canonical):** tiếp khách/bữa ăn ≤5.000.000 đ;
  taxi/đi lại ≤2.000.000 đ; **hạn nộp 30 ngày** từ ngày phát sinh có căn cứ; chi cá
  nhân bị loại khỏi chi phí công việc. Loại không có hạn riêng vẫn qua
  policy/evidence/authority và 8/4/20; B legacy không gate quyết định; **không** là
  PASS vô hạn (T3). Ngày nguồn thiếu là FACT, không thay bằng
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
  chối nếu không có trong danh mục). Profile/policy/quyền/lịch sử lấy theo scope
  hoạt động đã gắn; không mượn context hoạt động khác.
- **Tự liên kết hồ sơ (chốt 14/10/2026, ADR0008).** Nhân viên không chọn hoạt động
  thường trực trong luồng thông thường: backend tự liên kết quyết toán với hồ sơ
  tạm ứng/công việc (`reconciliation/linking.py` + `settlement_link.py`, pure;
  `Declaration.activity_id` optional, `confirmed_activity_id` cho xác nhận).
  Bốn kết quả `LINKED`/`NEEDS_CONFIRMATION`/`NOT_FOUND`/`CONFLICT`; UI chỉ hỏi
  ("Hồ sơ này quyết toán cho khoản tạm ứng nào?") khi mơ hồ, hiển thị ứng viên
  kèm số hồ sơ/ngày/nhân viên/số tiền; chưa tìm thấy thì tiếp nhận độc lập, không
  ép chọn hoạt động không tồn tại; không tạm ứng thì tiếp tục luồng đề nghị thanh
  toán. Hai ô "Nội dung hoạt động"/"Mục đích" gộp thành một ô "Nội dung đề nghị
  quyết toán"; địa điểm/ngày công tác giữ trường riêng, không gửi nội dung đề nghị
  vào destination. Rebind trùng hồ sơ đã tồn tại là conflict (tiếp tục hồ sơ đó);
  không ghi đè/xóa/chuyển sources/ledger ngầm; ngày chưa biết giữ chưa biết.
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

T=sum incurred costs đã xác minh; E=sum eligible employee-paid portions đã xác
minh; C=company-direct actual portions; unpaid không tự vào E/C. B legacy không
giới hạn T và không tham gia eligibility hay instruction.
S=E-A-P+R, không float. Invoice-incurred10/paid employee5/company3/unpaid2:
T10, E candidate5, C3; không create vendor instruction chỉ từ unpaid.
Nếu unpaid đã biết không đổi quyền lợi employee, chỉ notice
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
- Voucher PDF/ảnh được lưu làm `case_sources` trước OCR; draft/report giữ đúng root,
  source và digest. Ghi nhận thực tế phải trỏ tới draft đã lưu. Reference trùng với
  giấy quyết toán và duy nhất là căn cứ mạnh. Reference mâu thuẫn là conflict;
  reference chỉ có trên voucher nhưng chưa đăng ký vẫn được xét riêng bằng
  `MULTI_FIELD_MATCH`: danh tính nhân viên duy nhất, bên chuyển thuộc nguồn tổ chức,
  mục đích cụ thể khớp, tiền thực nhận bằng **tiền ứng khai trên giấy** (không phải
  tổng chi phí), thứ tự ngày hợp lý, mã giao dịch chưa bị hồ sơ khác giữ và chỉ có
  một hồ sơ phù hợp trong tenant. Quote/source refs của từng tín hiệu được lưu cùng
  acceptance. Thiếu/đọc mâu thuẫn hoặc có ứng viên cạnh tranh thì kế toán xác nhận;
  sai người/công ty, mã trỏ hồ sơ khác hoặc giao dịch đã thuộc root khác là conflict.
  Liên kết tự động không ghi tiền; kế toán vẫn xác nhận bản nháp để tạo đúng một
  money event. Nó không tạo coverage, grant hay authority.
- **Xác nhận ứng bằng thao tác (15/10/2026):** với bản nháp có nguồn đã đọc rõ,
  dữ kiện đầy đủ và liên kết hiện hành hợp lệ, command `RecordActual` có
  `advance_draft_id` từ phiên kế toán là xác nhận có trách nhiệm. Không bắt nhập lại
  câu xác nhận bằng chữ. Server kiểm lại nguồn/phạm vi/trạng thái/liên kết, tạo
  lời xác nhận và lưu actor/time/draft/refs trong event/audit. Khi bổ sung dữ liệu
  OCR thiếu phải có giải thích; liên kết thủ công dùng lý do liên kết có sẵn, không
  nhập hai lần. Giải thích không vượt qua conflict hay chứng từ chưa giải quyết.
  Nguồn pending/failed không thành received. Các đường ghi tiền khác giữ hợp đồng
  xác nhận riêng; đây không phải mặc định mọi command tiền đều đã xác minh.
- **Định danh và kiểm bên giao dịch (chốt 14/10/2026, ADR0008,
  `reconciliation/advance_identity.py` pure):** giữ `event_at` chứng từ,
  `recorded_at` là giờ máy chủ; người nhận phải là nhân viên hồ sơ (id hoặc tên
  hiển thị), bên chi phải là nguồn quỹ công ty đã cấu hình (tên tổ chức trong
  context hoặc id `company:*`) — không hard-code, không tự thay người nhận rồi
  coi đã khớp; tên/tài khoản chưa rõ giữ unresolved cho kế toán. `external_key`
  phải có namespace (`<namespace>:<reference>`); thiếu thì giữ chưa giải quyết,
  không bịa UUID. Cùng key tải lại là idempotent; cùng key khác payload trọng yếu
  (kind/amount/payer/payee/scope) là conflict; khác namespace là giao dịch khác.
  Voucher payee lệch nhân viên, payer lệch nguồn, hoặc thiếu định danh → giữ
  OBSERVED/unresolved, không thành A đã xác minh.

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

**Instruction-bound P/R (15/10/2026):** each new company supplementary payment
(`REIMBURSEMENT_RECEIVED`, projected as P) names the active same-root PAY
instruction and attached source refs. Each employee return (projected as R) must
come from a durable employee-uploaded source/read draft attached to the active
same-root COLLECT instruction; upload/OCR creates no money event. The accountant
confirms the saved draft, and the server rechecks parties, amount, reference,
date, completion, source digest and current instruction before recording R.
Partial movements fulfill only that instruction; overpayment remains a blocker.
Retries with the same transaction key are idempotent, while a different movement
cannot reuse a fulfilled or foreign instruction. Legacy events without an
instruction remain readable but cannot be submitted as new P/R commands.

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
| AUTHORIZE_ACTIVITY | Chỉ dùng record đã có | Không | Không | <=20m và effect scope |
| RECOGNIZE_COST | E<=8m | Không | Không | <=20m |
| EXCEPT_POLICY | Không | Không | Không | Exact rule/scope/max_effect, <=20m |
| ISSUE_PAYMENT/COLLECTION | abs(S)<=4m | Không | Execution đúng instruction | <=20m |
| STOP/RESUME | Backend enforces | Không mặc định | Granted root | Granted root |
| OVERRIDE | Không waive facts | Không | Không mặc định | Granted actions/scope/reason |

Default server fixture cho employee submit/answer purpose; accountant financial
confirm/record + stop/resume; approver actions bảng và stop/resume. System grant
recognize/issue explicit scope/profile/time. One compound decision có thể approve
Mỗi action20m theo đúng dimension (E hoặc request), đúng action/scope/time.
B và `SET_BUDGET` không là action/workflow trong phạm vi hiện tại.
Một compound decision có thể approve nhiều actions khi actor có đủ grants, không
nhiều clicks bắt buộc, không free-form “đồng ý” resolve all. Không role
MANAGER unlimited. Không quyền demo thì explanation needs higher authority, không
hứa xử lý trong app.

| Data state | Expected issue/outcome |
| --- | --- |
| B legacy thiếu/thấp/cao | Không issue và không đổi kết quả; dữ liệu B không là điều kiện quyết toán |
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
  RefuseException(root_id,issue_ids,reason) (S6: accountant/approver từ chối ngoại lệ;
  audit + REFUSED, issues giữ OPEN),
  RecordActual(root_id,RecordMoneyInput), Control(root_id,STOP/RESUME,reason),
  Override(root_id,supersedes_decision_id,DecisionCommand),
  MarkExecution(root_id,instruction_id,OPEN/CLOSED_CONFIRMED/UNKNOWN,refs,reason).
  S6 bổ sung RecheckDossierHistory(root_id,reason), route
  `/cases/{id}/money-history/recheck` (version + command-id bắt buộc).
  MarkExecution route `/cases/{id}/mark-execution`: kiểm RECORD_ACTUAL grant
  đúng actor/activity/profile/full instruction amount/time; lệnh phải thuộc root,
  nguồn phải thuộc tenant/root/digest, đóng cần page/quote + reason, audit và
  reassess cùng transaction. FULFILLED còn OPEN/UNKNOWN không được SETTLED.
- Chấp nhận ngoại lệ thiếu chứng từ (S6): Decide với actions=[EXCEPT_POLICY] trên
  issue `expense:<n>:missing_evidence`, kèm amount (số khai dòng, server tự lấy)
  và reason; grant EXCEPT_POLICY đúng scope/effect/hạn mức được kiểm ở workflow
  boundary; quyết định persist vào `case_exception_decisions` (ACCEPTED) và được
  nạp vào AssessmentInput.exceptions ở mọi lần reassess — không resurrect issues.
  Từ chối persist REFUSED và đổi nothing.
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

### 9a. Tracing operation/step (chốt 14/10/2026)

- `TraceRecorder` (`evidence/telemetry.py`): `operation(name, *, run_id, metadata,
  tags)` mở một **root span** cho MỘT operation thật; `step(name, *, operation,
  metadata, inputs)` mở **child span** dưới root. Mỗi span có ID riêng;
  child mang `parent_run_id` = root. Span được buffer local, chỉ flush khi
  operation thoát (ngoài transaction). Module-level `step()` gắn vào operation
  đang chạy qua contextvar, cho helper lồng nhau (read_root) ghi step mà không
  phải truyền recorder.
- Operation roots: `command:<kind>` (create/attach/submit/answer/decide/
  record_actual/mark_execution/control/override), `settlement-draft-read`,
  `advance-draft-read`, `evidence-job`. Không giữ một root span mở qua toàn vòng
  đời hồ sơ; liên kết bằng metadata (root_id/job_id/command_id, read-set
  versions, basis, provider_mode, code_revision).
- Processing steps trong `read_root`: `ocr:<file>`, `confidence-review`,
  `classify`, `extract:<type>`, `validate:<type>`, `match`; trong assessment:
  `admission`, `reconcile`, `commit`. Bước bỏ qua ghi `skipped` reason (không ghi
  thành provider call thành công).
- `TraceSpan` mang `parent_run_id`, `run_type`, `inputs/outputs/error/metadata`,
  `started_at/ended_at` thực. Sink LangSmith dùng thời gian thật; span không có
  end giữ mở (không đặt `start==end==now` tạo latency 0 giả). `filter_payload`
  bỏ secret/private content nhưng GIỮ metric số (`token_count`, `total_tokens`).
- `build_trace(settings)` tắt khi chưa bật/thiếu key; sink local luôn giữ span;
  lỗi export ghi vào `export_errors` (không silently swallow) và không đổi kết
  quả nghiệp vụ. `CaseView.trace_refs` là tham chiếu kỹ thuật (debug), không phải
  trường nghiệp vụ. `/health` phân biệt `langsmith_ready` (cấu hình) với
  `langsmith_enabled`/`langsmith_export_errors` (trạng thái export thực tế).

Test helpers tests/factories.py là unit-only: snapshot(T:int,E:int,C:int,A:int,
P:int,R:int,B:int,coverage:bool=True,**overrides) -> AssessmentInput; B is a legacy
compatibility field ignored by decisions, với verified
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

Identity của một khoản chi lấy từ **document thực sự bound vào khoản đó** (issuer +
document_number), không lấy invoice đầu tiên của report và không dùng thứ tự
file/row (TC23): hai dòng cùng một hóa đơn dùng chung canonical identity, hóa đơn
khác có identity riêng. Khoản không có chứng từ bound dùng marker theo dòng. Identity
này được persist trong `AssessmentResult.economic_keys` (trong
`case_conclusions.payload_json`) để consumer usage/anti-duplicate đọc đúng identity
mà admission đã dùng — cả đường LIVE/REPLAY lẫn STUB.

Một khoản chi có nguồn bị phân bổ vượt (over-allocation) là **đang tranh chấp**
(TC08): `incurred`/`eligibility` UNKNOWN, không có payment portion, FACT giữ cả số
kê khai, số chứng từ và sai lệch (owner employee). Không nâng khoản tranh chấp thành
verified/ELIGIBLE money; không âm thầm cắt về số chứng từ hoặc lấy số kê khai. Lịch
sử đã xác minh (A/P/R) vẫn giữ. Approval/EXCEPT_POLICY chung không waive FACT; chỉ
correction/nguồn mới hợp lệ ở revision mới mới giải quyết. Khi mọi khoản đều đang
tranh chấp, không thêm câu hỏi `expense:payer` giả (căn cứ người trả đã rõ, chỉ số
tiền chưa rõ).

Tenant usage registry trong workflow/schema.sql: economic_key, owner_root,
expense_id, verified payment_portion keys, evidence refs, version. Một expense
scope chỉ có một owner root; payment portions mới cùng owner thêm một lần. Hai
roots khác activities nhận cùng verified obligation không được tạo hai eligibility/
instructions; route conflict để trả về canonical owner, không trộn hai chuyến.
Ghi usage/eligibility/instruction atomically; financial money thật vẫn được ghi
nếu vi phạm; hủy/supersede instruction không xóa incurred expense hoặc usage owner.

cost_basis hash chứa expense identity/incurred/time, eligible paid portions/payer/
binding, activity purpose/relations, expense-time policy/exception scope và
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

context_version aggregate tăng khi context được import/đổi. Thay B legacy có thể
khiến tác vụ đang chạy phải đọc lại theo optimistic concurrency, nhưng không đổi
cost_basis hay outcome nghiệp vụ. Policy/grant/activity authorization/exception/
revocation thay đổi vẫn là authoritative changes. File
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
draft creation **không** cấp quyền hoạt động hay grant. ProposedActivity giữ
activity identity làm scope. Tenant snapshot cung cấp danh tính tổ chức, nhân viên,
policy và grants; ledger, references và coverage chỉ được ghép cho đúng activity.
Một `ActivityAcceptance` theo chứng từ ứng có thể đáp ứng FACT “công việc đã được
công ty chấp nhận” nhưng không đổi status, không cấp `AUTHORIZE_ACTIVITY` hay grant.
Chi phí/effect vẫn phải qua evidence, policy, coverage và action/scope authority.
Không tạo một budget/authorization FACT chỉ vì thiếu B. `SET_BUDGET` không là
action/workflow hiện hành.
Same activity→same root, two activities→
two roots. Demo context import chỉ synthetic validated input trong sandbox và
audit import origin; không cho raw client role/action tự thành corporate authority.

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
- Provenance cho text value được phép chuẩn hoá **chỉ whitespace** khi so với quote:
  value một dòng có thể khớp quote nguồn nhiều dòng nếu chỉ khác dấu cách/newline.
  `EvidenceRef.exact_quote` vẫn giữ nguyên chuỗi quote gốc; không bỏ dấu, sửa chính
  tả, bỏ từ, fuzzy-match hay chấp nhận tên không được quote hỗ trợ.
- Ngày nguồn dùng chung bộ chuẩn hoá lịch: ISO, DD/MM/YYYY (hoặc dấu `-`, `.`),
  và `ngày DD tháng MM năm YYYY`. Extraction prompt v2 yêu cầu value ngày ở dạng
  ISO, giữ nguyên quote; code vẫn nhận ngày chữ từ bản đọc cũ. Không đoán năm,
  không lấy ngày lập giấy/hóa đơn làm ngày công việc. Kiểm chứng phải khớp đúng
  thứ tự ngày/tháng/năm và ngày có tồn tại; không dùng tập hợp chữ số. Quote nhiều
  ngày chỉ chọn đầu/cuối khi field `trip_start`/`trip_end` gắn khoảng `từ … đến …`
  rõ ràng. Timestamp không được thêm giờ/offset mà nguồn không hỗ trợ.
- Kế toán có thể GET lại bản nháp ứng đã lưu để tính lại liên kết theo nguồn và
  trạng thái hiện hành, không gọi OCR/LLM, không đổi version, không ghi tiền hay
  coverage. Xác nhận ghi tiền vẫn kiểm lại căn cứ trong transaction.
- Confidence: `collect_low_confidence_blocks(ocr, threshold=0.85)` tạo candidate;
  `async review_ocr_quality(candidates, *, llm, budget, sources=()) -> ConfidenceReview` một batch;
  `ConfidenceReview(status:ASSESSED|SKIPPED_NO_NUMERIC_CANDIDATES|TECHNICAL_ERROR,
  block_assessments)` với `BlockAssessment` có `importance/quality_state/review_action/
  canonical_fields/observed_text/reason/...`. `SKIPPED_NO_NUMERIC_CANDIDATES` **không**
  phải PASS. Model chỉ đánh giá readability; không thay text/thay value.
- Adapter nối word confidence cấp trang của Mistral về block bằng offset và text
  khớp chính xác; không bịa score khi thiếu. Quote qua các block liền nhau giữ
  liên kết tới words của từng block trên đúng trang. Tiền critical phải có score
  bao phủ token giá trị; score của nhãn/thuế suất không xác minh số tiền khác.
  `SETTLEMENT_FORM` row `invoice_refs` chịu cùng guard critical như row amount.
- Sửa schema: tối đa **một** repair call/root; sau đó giữ lỗi kỹ thuật + unresolved.
  Refinement 16/10: quota chia sẻ trong `RunBudget` cho một read pass, có phản hồi
  trước/diagnostic giới hạn kích thước; transport/provenance/số học không phải schema
  repair. Không cắt nguồn hoặc tăng input/output cap để gọi sửa.
- Refinement prompt 16/10: classification-v2, extraction-v3, confidence-review-v2,
  suggestion-resolution-v2; hướng dẫn theo loại nằm trong `evidence/prompts.py`.
  Confidence assessment phải khai đủ trường, bool/enum/ID/coverage được kiểm;
  model NON_CRITICAL không được miễn giá trị critical đang UNCERTAIN/UNREADABLE.
  Quote có offsets tin cậy chỉ bị ảnh hưởng bởi words chồng lên nó; thiếu offset
  giữ fallback thận trọng. Chữ mờ ở block khác không làm mọi field hỏng.
- `invoice_refs` là tuple/list mã nguồn; chuỗi chứa JSON array được decode có giới
  hạn, từng phần tử vẫn phải được quote hỗ trợ, không duyệt chuỗi như từng ký tự.
  Riêng `transaction_status`, code được phép đối chiếu enum chuẩn với toàn bộ nhãn
  trạng thái tiếng Việt/Anh đã biết (sau bỏ label), giữ quote nguyên bản. Không
  substring/fuzzy để biến "không thành công" hoặc "đang xử lý" thành COMPLETED.
  Consumer ứng/hoàn cũng dùng whole-status recognition; trạng thái nguồn phủ định
  hoặc chưa biết không được fallback substring thành hoàn tất.
- Classification phải bao phủ mọi source/page đã OCR; thiếu range dùng chung
  schema repair slot rồi giữ technical/unresolved nếu vẫn thiếu. Confidence thiếu,
  không hữu hạn/ngoài [0,1] hoặc <0.5 giữ UNKNOWN với alternative, không chọn schema
  đoán (ngưỡng kỹ thuật bảo thủ của implementation, không đo độ đúng dữ kiện tiền).
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
  serial-only reference may match the suffix of a series-prefixed invoice number
  only at a non-digit boundary and only when it identifies one candidate document;
  duplicate serials remain suggestions for human selection;
  ngược lại amount 0.60 (≤1 VND) + semantic ≤0.30 + party 0.12/0.20 + non-original
  +0.10, cap 1.0; `<0.50` bỏ, `[0.50,0.75)` suggestion, `>=0.75` auto; tie theo thứ
  tự gắn nguồn.
- `async resolve_evidence_suggestions(result, documents, *, paper, llm, budget)` một batch khi
  có suggestion; model chỉ promote cặp có sẵn ở `>=0.90`, không tạo cặp mới.
  Payload gồm structured row/document facts; confidence hữu hạn [0,1] và căn cứ
  amount + định danh/dịch vụ. ISSUER/SERVICE vẫn là nhận định ngữ nghĩa của model,
  không phải xác minh độc lập. Không ghi đè số chứng từ mâu thuẫn, chọn bừa giữa
  nhiều candidate, hoặc vượt allocation/cardinality. Cặp cạnh tranh chưa có căn
  cứ phân biệt tiếp tục unresolved.
- Cardinality: một nguồn auto-link cho dòng khác mặc định chỉ suggestion; phân bổ
  nhiều dòng chỉ khi mỗi dòng lặp `invoice_ref` chuẩn hoá + amount, tổng ≤ giá trị
  chứng từ. Chứng từ hỗ trợ không tính là chứng từ gốc; `original_total` chỉ cộng
  chứng từ gốc/phần phân bổ gốc; amount thiếu giữ `None`.
- Projection matching chung dựng lại links/rows/findings/unmatched/allocation sau
  rule và promotion; tổng phần chứng từ gốc của một dòng không được nhân đôi số
  kê khai. Admission nhận mapping hợp lệ đó, giữ raw allocation assertion để
  không mất FACT khi link quá mức bị từ chối. Mapping không tự xác minh payer;
  các điều kiện invoice binding/actual money/authority hiện hành vẫn độc lập.

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
  Refinement 16/10: active report basis có reader_identity; report cũ thiếu identity
  không được reuse như đọc bằng prompt mới. Direct settlement draft giữ identity
  trước I/O và kiểm lại trước lưu, job kiểm trước publish. Không tự sửa quyết định
  hoặc money của hồ sơ đã đóng khi nâng prompt.
  Artifact private dưới `uploads_dir.parent/"artifacts"`, cùng vòng đời nguồn, trần
  20 MiB/source, 40 MiB/root.
- Worker: `async CaseWorkflow.run_evidence_job(job_id) -> None` →
  `workflow/evidence_jobs.py::run_evidence_job`; `drain_evidence_jobs(workflow, stop)`
  claim QUEUED transactionally, chạy một job một lúc; FastAPI lifespan sở hữu task.
  Persist `jobs.input_basis_json` (additive migration) + `attempts_json`.

### 12.6. Gate số học tài liệu và numeric provenance (chốt 14/10/2026)

- `check_document_arithmetic(document) -> tuple[ArithmeticFinding,...]` pure sync
  (`reconciliation/document_arithmetic.py`). `ArithmeticFinding(code, field_or_rule,
  basis, question, refs)`.
- Kiểm theo **loại tài liệu** và các field đã có căn cứ:
  - `SETTLEMENT_FORM`: `max(declared_advance − printed_total, 0)` phải bằng
    `printed_return` (`code=settlement-return`); `max(printed_total − declared_advance, 0)`
    phải bằng `printed_reimbursement` (`code=settlement-reimburse`). Chỉ một chiều áp
    dụng; chiều không áp dụng là zero có căn cứ (F02 ứng 5m < chi 5.4m ⇒ hoàn lại 0,
    đề nghị chi thêm 400k — không phải mâu thuẫn).
  - `E_INVOICE`: `subtotal + tax + service_charge − discount` phải bằng `total_amount`
    (`code=invoice-total`). Ticket/receipt không bị bắt có VAT fields.
- Thành phần trọng yếu (`tax`/`discount`/`service_charge`) ở trạng thái `UNREADABLE`/
  `AMBIGUOUS` ⇒ `code=invoice-components-unread`, **không** mặc định bằng 0. `NOT_PRESENT`
  là không áp dụng. Số nguồn nguyên bản được giữ; số tính lại chỉ để đối chiếu trong
  `basis`/`question`, không ghi đè tổng.
- Dùng integer VND/`parse_vnd`, không float/dung sai tuỳ ý: lệch 60k/100k phải là FACT.
- `SETTLEMENT_FORM`: khi chứng từ có `printed_total` và các dòng chi được biểu diễn,
  tổng các dòng chi có mô tả và số tiền đọc được phải bằng `printed_total`
  (`code=settlement-line-total`). Dòng `total`/`subtotal` không phải khoản chi và
  không được cộng lần hai. Dòng chi được biểu diễn nhưng thiếu/không đọc rõ mô tả,
  số tiền, hoặc tổng in trên giấy không đọc rõ ⇒ finding unresolved; không thay
  bằng zero, không cộng riêng phần đọc được. Nếu `printed_total=NOT_PRESENT`/
  `NOT_APPLICABLE`, không tự tạo quan hệ với zero. Không suy ra VAT, phí dịch vụ,
  chiết khấu hay khoản thiếu để làm hai phía bằng nhau.
- Cùng finding và căn cứ nguồn phải xuất hiện trong employee draft và admission.
  Khi mismatch/unresolved ảnh hưởng các khoản chi, chi phí đủ điều kiện và T giữ
  `UNKNOWN`, không ghi nhận payment basis hay instruction. Tách biệt với phép tính
  S hiện hành và với việc liên kết dòng chi ↔ hóa đơn: liên kết số hóa đơn chỉ
  chứng minh quan hệ tham chiếu, không xác nhận dịch vụ đã thực hiện.
- `admit_evidence` biến mỗi finding thành `BusinessIssue(kind=FACT, owner=employee,
  field_or_rule=expense:arithmetic:*)`; Reconciler đặt `allowed_effect=None` khi có FACT
  này, và `_commit_assessment` không phát hành instruction. Approval/EXCEPT_POLICY chung
  **không** waive FACT này. Cùng kết quả cho draft (`build_settlement_draft` phơi
  `arithmetic_findings`/`warnings`) và submit.
- **Numeric provenance** (`evidence/extraction.py::_value_supported`): giá trị money
  phải là token số độc lập của quote; `8%` (rate) và digit-run dính chữ (`IR26E`) không
  phải money. Giá trị có chữ (số chứng từ) bind theo skeleton alphanumeric hoặc theo
  run số dài nhất của chính nó, nên số serial-prefix (`IR26E00000101`) khớp đúng phần
  của nó và số sai bị từ chối.

# B6 → B7 Linked Settlement — Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, tuần tự bốn task có tests và UI checkpoint. Không tự subagent/Git/LIVE/publish; một writer giữ shared contracts.

**Goal:** Từ công việc B3/B5 tạo hồ sơ B7 có liên kết, nộp khai báo chi phí thực tế và sources, nhập company context có căn cứ, chạy pipeline B7 đến report/questions/accountant review.

**Architecture:** Giữ B3 và tạo B7 riêng cùng employee/work. Link/snapshots lưu trong typed submission JSON, audit và retained system-source artifacts hiện tại. Python import persisted financial facts; Reader/matcher xử lý originals của chi phí. Chưa mở B8/B9 cho linked slice.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite/pytest, React/TypeScript/Vite/Vitest hiện có. Không thêm dependencies/tables/ERP/queue/workflow framework.

**Spec:** [B6 linked settlement design](../specs/2026-10-11-b6-linked-settlement-design.md).

**Status:** IMPLEMENTED (fake/replay + HUMAN_SOURCE_REVIEW, 2026-10-11); chưa nghiệm thu LIVE/UI.

## Evidence (2026-10-11)

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**; không LIVE/Git/publish.
Commands/exit/count actual:

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked.py -q          # 12 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked_context.py -q  # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_claim_links.py -q     # 3 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                            # 370 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                       # 790 passed
.venv/bin/python -m pip check                                                                            # No broken requirements found
npm --prefix frontend run test -- --run                                                                  # 122 passed (21 files)
npm --prefix frontend run build                                                                          # tsc --noEmit + vite build OK
```

Artifacts: `src/invoice_referee/settlement/b7_linked.py` (mới), models/service/
store/pipeline/API linked, `frontend/src/settlement/B7Intake.tsx` +
`B7CompanyContext.tsx` (+tests), docs `docs/testing/B6_B7_LINKED_WALKTHROUGH.md`,
`PRODUCT.md`, `SYSTEM.md`. Breaking expectation (source-justified): linked B7 run
dùng **B7 rights riêng** (b7_context grants), không kế thừa generic `authority`
(P-DEMO); `RelationKind` thêm `CLAIM_EXPENSE`; `Report.claim_comparisons` mới.

**Chưa kiểm (honest limits):** UI walkthrough `USER_UI_UNEXECUTED`; LIVE/OCR/LLM
quality PLANNED; chưa B8/B9/handoff/closure/tạo B7 tự động/import bảng kê.

## Global Constraints

- employee_ref/work_ref/link/clocks là backend-owned; không đổi B3 job thành B7 hoặc tạo advance0 cho tự chi.
- Expense rows là declarations, không payment facts; forecast/approved amount không actual expense/received.
- Source/policy/context/grants/imported money có refs và snapshot; no expected/test labels trong prompts.
- Whole-work A/RA/P/RP cần coverage đúng scope/owner/as-of; vắng dòng không0; B5 subtotal không whole-history truth.
- Integer VND, unknown null; pending/incidents/aliases giữ riêng, không clip raw actual hoặc đếm lại event.
- B7 rights riêng B3Grant; linked run không fallback broad P-DEMO grant hoặc dùng role picker làm quyền.
- Intake được nhận dù thiếu money/receipt; Stop/stale ngăn current managed output/actions, không xóa nguồn/facts.
- Lát cắt report-only: không new B8 decision, payment/handoff/closure/bank transfer hoặc parent close.
- Giữ generic legacy B7/corpus v1/v2; update evaluator chỉ để dùng application path mới, không đổi gold theo output.
- Không reset existing work; hiện workspace sạch tại lúc viết plan, executor kiểm lại trước sửa.

## Task 1 — Linked draft, declarations và UI nộp

**Files**
- Create: `src/invoice_referee/settlement/b7_linked.py`.
- Modify: `settlement/models.py`, `service.py`, `store.py`, `api/settlement.py`.
- Create: `frontend/src/settlement/B7Intake.tsx`, `B7Intake.test.tsx`.
- Modify: `frontend/src/settlement/types.ts`, `api.ts`, `App.tsx`, `B3Funding.tsx`, `uiCopy.ts`.
- Create: `tests/settlement/test_b7_linked.py`, `test_b7_linked_api.py`.

**Interfaces**
- `B7OriginLink`: origin_case_id:str; employee_ref:str; work_ref:str; created_at:AwareDatetime. Server immutable.
- `B7ClaimRow`: claim_id:str; description:str; expense_date:date|None; declared_amount_vnd:StrictInt|None; purpose:str; declared_payer Literal[PERSONAL,COMPANY,UNKNOWN]; source_ids:list[str]=[]; payment_statement:str|None=None. Không negative/bool/float; unknown null. IDs là namespace claim, không invoice/payment ID.
- `B7LinkedIntake`: schema_version Literal[b7-linked-intake-v1]; confirmed:bool=False; expense_rows:list[B7ClaimRow]=[]; note:str|None=None. Origin link do server append ngoài client-editable intake.
- `LinkedB7View`: origin:B7OriginLink; context_source_id:str|None; context_current:bool; blocked_reasons:list[str]; managed_advance_subtotal_vnd:StrictInt|None. CaseView.linked_b7:LinkedB7View|None=None.
- `Service.prepare_linked_b7(origin_case_id:str,command:Command)->CaseView`.
- `Service.revise_linked_b7(case_id:str,intake:B7LinkedIntake,command:Command)->CaseView`.
- `POST /api/cases/{b3_id}/settlements`: actor/demo_role/expected_case_version của **parent**, Idempotency-Key; tạo draft child201/reuse200.
- `PUT /api/cases/{b7_id}/settlement-submission`: actor/demo_role/expected_case_version child + intake,200.

- [x] **1.1 Tests failing liên kết bất biến**

Fixtures có thật dùng lại, method mới chưa tồn tại nên tests ban đầu đỏ:

```python
import pytest
from invoice_referee.domain.models import DomainError
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3

def test_link_keeps_employee_work_and_parent(approved_b3):
    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    assert child.job == "B7"
    assert child.submission.employee_ref == parent.submission.employee_ref
    assert child.submission.work_ref == parent.submission.work_ref
    assert child.linked_b7.origin.origin_case_id == parent.id
    assert svc.get_case(parent.id).job == "B3"
    assert child.submission.form["confirmed"] is False

def test_prepare_retry_does_not_create_second_child(approved_b3):
    svc, parent, decision = approved_b3
    cmd = command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version)
    first = svc.prepare_linked_b7(parent.id, cmd)
    second = svc.prepare_linked_b7(parent.id, cmd)
    assert first.id == second.id
```

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked.py -q`.

- [x] **1.2 Implement create/revise transaction**

Actor phải EMPLOYEE và đúng parent employee/persona; parent B3 intake confirmed
scope tồn tại. Không yêu cầu B5 fulfilled hoặc report B7 đủ nguồn mới cho intake.
Tạo/reuse một active B7 cùng employee/work, kiểm cả active legacy B7 scope đó
để không tạo duplicate obligations. Legacy existing không auto migrate; trả
conflict với case ref/hướng xử lý. Closed adjustment chưa mở.

Use case_revisions/submission/audit JSON, không schema mới. Parent version
kiểm cho create; child commands kiểm child version. Same-key replay không
create lại; changed-body409. New key khi đã linked active child trả child hiện
có sau owner/scope guard. SQLite write transaction chống hai child đồng thời.

Service.submit generic từ chối client giả schema linked/link; Service.revise
generic không được xóa/đổi link, employee/work/clocks hoặc reset bằng form
purpose/scope cũ. Branch dedicated xác nhận rows unique, typed amount và refs
own child. confirmed=true có ít nhất một khai báo row; thiếu source/amount
vẫn vào needs-resolution, không bắt nhân viên đoán. Draft save không Run.

Real clocks cấp server hiện tại; metadata details không form debug. Task2
định nghĩa synthetic settlement clock riêng; không parent pretrip clock10/10.
Xác nhận intake rồi Start hai commands có idempotency; nếu Start lỗi sau
confirm, UI nói đã nộp/chưa chạy, giữ child để retry.

- [x] **1.3 UI checkpoint nộp draft**

From B3 “Chuẩn bị hồ sơ quyết toán”/“Mở hồ sơ quyết toán” cho employee, kể
cả partial/unknown thì show caveat cần đối chiếu. Readonly người/work/trip/
ngân sách có căn cứ/ứng đã ghi và giới hạn scope. Không nhập lại B/A.
Form rows thực tế, date/amount/purpose/payer declaration/source association;
không prefill giá forecast thành actual. Người dùng có thể thêm/xóa rows,
tải receipts bằng source API existing, lưu draft, confirm+Run.

API helpers `prepareLinkedB7`, `reviseLinkedB7`; types mirror records. App
mount B7Intake theo public schema version, giữ legacy form. Claim source picker
chỉ hint association, không tạo established payment. Date/amount blank không0.
Employee không company coverage editor. Reload/đổi vai vẫn cùng child link.

Tests wrong actor, spoof link/body, concurrent create, generic revise wipe,
parent vs child version, unknown money intake, draft not auto Run, retry UI
giữ child, declaredPERSONAL không success payment badge.

## Task 2 — Snapshot tài chính, coverage và quyền B7

**Files**
- Modify: models.py/b7_linked.py/Service/Store/API và factory config.
- Create: `frontend/src/settlement/B7CompanyContext.tsx`, `B7CompanyContext.test.tsx`.
- Modify: frontend types/api/App và linked context readonly card.
- Test: test_b7_linked.py/test_b7_linked_api.py; new `test_b7_linked_context.py`.

**Interfaces**
- `B7CompanyConfig`: schema_version Literal[b7-company-config-v1]; version:str; activated:bool; synthetic:bool; demo_clock:AwareDatetime|None; grants:list[AuthorityGrant]; ref:str. Define trong models để không circular import. Loader `load_b7_company_config(path:Path)->B7CompanyConfig` trong b7_linked.py.
- ServiceConfig.b7_context:B7CompanyConfig|None; factory `SETTLEMENT_B7_CONTEXT_PATH` optional. Không configured => linked grants=[], clocks server, owner issues; không auto inherit B3 limits hoặc legacy DEMO_AUTHORITY.
- `B7CompanyEvent`: event_namespace/event_ref:str; kind Literal[ADVANCE_RECEIVED,ADVANCE_RETURN,REIMBURSEMENT_RECEIVED,REIMBURSEMENT_RETURN,COMPANY_DIRECT]; amount_vnd:StrictInt|None; payer_ref/payee_ref:str|None; outcome Literal[RECEIVED,PENDING,FAILED,CANCELLED,UNKNOWN]; event_at:AwareDatetime|None; refs:list[str]. Semantic actual receipt source và scope, không status string đơn lẻ.
- `B7CompanyExpense`: expense_ref:str; issuer_ref:str; document_ref:str; amount_vnd:StrictInt|None; purpose Literal[BUSINESS,PERSONAL,UNKNOWN]; expense_date:date|None; refs:list[str]; payment_event_refs:list[str]. Expense không là money event; forecast không field ở model.
- `B7CompanyPacket`: coverage:B3Coverage (scope/time/methods/groups/opening/missing/owner/origin/ref hiện có); events:list[B7CompanyEvent]; expenses:list[B7CompanyExpense]; refs:list[str]; reading_note:str. Validate event identity/ref/type/scope, source support; owner_ref do command actor xác định, client không cấp quyền. Groups canonical là bốn history kinds + COMPANY_DIRECT + DUPLICATE_CLAIMS.
- `LinkedB7ContextSnapshot`: origin/parent dependency fingerprint, linked decision/managed actual records refs, company packet/version, policy/B7 authority version; history dict a/ra/p/rp nullable + known subtotal; company expenses/payments/links có nguồn; issues:list[Issue]; money_as_of/knowledge_cutoff. Không final S/expected outcome.
- `Service.record_b7_company_packet(case_id,payload:dict,command:Command)->CaseView`;
  `Service.refresh_linked_b7_context(case_id,command:Command)->CaseView`.
- POST `/api/cases/{id}/settlement-company-context` (ACCOUNTANT) và POST
  `/api/cases/{id}/settlement-context/refresh` (employee đúng owner hoặc accountant đúng route; body không override facts).

- [x] **2.1 Tests đỏ coverage và actual vs approved**

1. Parent approval2, actual receipt1: imported managed subtotal1, không A2.
2. No current whole-work coverage: history A/RA/P/RP final unknown dù subtotal
   A2; không biết RA/P/RP không trở thành0.
3. Coverage đủ + one canonical receipt2 + explicit no returns/reimbursements:
   A2/RA0/P0/RP0 với refs; same TX thêm ledger row không thành A4.
4. Company actual flight missing: không lấy forecast flight3 làm T/company cost.
5. Coverage tới10/10, cutoff14/10 hoặc thiếu CASH/opening balance: missing
   groups unknown và FACT cho accountant, không employee phải nhập lịch sử.
6. Extra actual advance1 cùng scope có nguồn => A3, không cap2; unknown/
   pending ảnh hưởng giữ subtotal và chưa final. Foreign work không cộng.
7. Grant B3 đủ nhưng b7_context absent: B7 authority unresolved, không P-DEMO.

Negative source refs/payer semantics/allocated namespace collision không pass
chỉ vì owner chọn ACCOUNTANT. Source-backed manual company packet ghi origin
HUMAN_SOURCE_REVIEW/observability, không coi là bank authenticated/OCR success.

- [x] **2.2 Implement snapshots và source refs**

Lưu system context source JSON trong child có source-use backend
LINKED_B7_CONTEXT và audit operation B7_CONTEXT_REFRESH. Python build từ typed
parent records/validated company packet, không expected/prompt answers.
Context refresh identical hash => reuse; changed snapshot supersedes old,
tăng child input_revision/case_version và giữ old run/source. Không reset
confirmed nếu declarations không đổi. Không rewrite parent receipts/budget.

Copy **selected** raw proof/basis source bytes sang child artifacts có origin
case/source/hash provenance; parent copies readonly, original unchanged.
Không feed forecast/request/proof ứng vào expense Reader. Copy snapshots
độc lập file để parent deletion không khiến child evidence mất; đồng thời
delete parent có active linked child phải refuse409 LINKED_CASE_EXISTS hoặc
archive theo scope riêng, không user delete mất dependency. No blanket copy
all parent files. Parent references/decision rows retained JSON source để mở.

Scope company packet matching employee/work/cutoff, groups/methods/opening
và issuer/owner observability theo Rulebook R5. Complete checkbox thiếu căn
cứ không zero. Full coverage group cho phép derive zero từ source; absence
company direct chỉ accountant nguồn đúng scope. Dedup canonical B5+company
event namespace/ref; aliases cần source link, không amount/date heuristic.
B5 pending/incidents/cross-case conflicts được import issues, không silently
chọn confirmed subtotal làm whole A hoặc drop extra event.

B7 config activated/synthetic có thể clock14/10 để test sau chuyến đi; flag
và clock public details, created_at audit giờ thật. Config thật không
accept demo_clock. Demo grant **explicit riêng** APR-DEMO-01 cho NV-DEMO-01,
work scope được cấu hình, E≤8triệu/net≤8triệu, effective01–31/10; exception
limit chỉ khi nguồn config chủ ý cấp. Không default cap từ forecast8.
Test dùng literals config; không tăng quyền để output xanh. Source config
version/ref lưu cùng snapshot, corporate data fixture không credentials.

- [x] **2.3 UI checkpoint company data**

Employee card: budget8 từ decision, “ứng đã ghi nhận2 — chờ coverage” khi
chưa whole A, không editable. Accountant panel nhập/import company packet
source-backed (phạm vi/group/method/time/refs và các event/expense thực tế),
coverage missing chỉ rõ, không ngân sách/rights editable qua form này.
Native inputs/JSON preview có nhãn nghiệp vụ; JSON import chỉ là phương thức
cho demo, không main UI toàn debug. Backend role/route guards thật.

After company snapshot, mọi vai mở source/parent refs được; origin fact có
label “Dùng lại quyết định / tiền đã ghi nhận / nguồn kế toán”, không AI đã
xác thực tất cả. Generic upload/client metadata không được giả system source.

## Task 3 — Claim ↔ expense, same B7 pipeline, report

**Files**
- Modify: models.py/pipeline.py/reader.py/rules.py/b7_linked.py/Service/Store.
- Modify: `src/invoice_referee/extraction/prompts/settlement-extract.txt`, `settlement-match.txt` (bounded linked declarations/claim links, không full-report generation).
- Modify: frontend `Report.tsx`, `Report.test.tsx`, `B7Intake.tsx`, `Actions.tsx`, `types.ts`, `uiCopy.ts`.
- Test: test_b7_linked.py, new `tests/settlement/test_b7_claim_links.py`, test_readers.py/test_rules.py/test_questions.py/test_report_api.py.

**Interfaces**
- Extend RelationKind/TS kind with CLAIM_EXPENSE. from_id=claim_id của confirmed
  form, to_id=actual expense ID; payment kinds hiện có không thay nghĩa.
- `_validate_relations(..., claim_ids:set[str]|None=None)` kiểm từng kind
  against namespaces riêng; fake/extra/duplicate IDs fail trước aggregation.
- `linked_context_observations(snapshot:LinkedB7ContextSnapshot,source_id:str)->tuple[list[Observation],list[Relation],list[Issue]]` Python trong b7_linked.py. Observation fact IDs qualified theo context-source, value/quality/refs origin typed; không input employee rows thành expense/payment known.
- `apply_linked_financial_gate(snapshot:LinkedB7ContextSnapshot,observations:list[Observation])->tuple[list[Observation],list[Issue]]` trong b7_linked.py trước evaluate: history/budget canonical chỉ từ reviewed context đủ coverage; originals financial assertions vẫn được lưu như candidates và kiểm source semantics. Employee statement/forecast không trở thành received/budget, genuine conflicting financial source tạo issue cùng refs, không company-wins hoặc drop source. Unknown whole-history group không được fill bằng partial receipt hoặc một dòng trên giấy; nguyên nhân/candidate còn hiện để accountant cập nhật packet/recheck.
- Report thêm `claim_comparisons:list[B7ClaimComparison]=[]`: claim_id,
  expense_id:str|None, declared_amount_vnd/verified_amount_vnd nullable,
  payer_declaration/verified_payer nullable, status Literal[MATCHED,CONFLICT,
  UNRESOLVED], refs:list[str], reason:str. Giữ existing components/rows/net.

- [x] **3.1 Tests failing actual vs forecast và declarations**

Expected literals source-first: actual company flight3, employee hotel3/meal1/
ground1, B8/A2/RA=P=RP0 theo packet => T8/E5/S+3. Actual hotel2,5 với khai2,5
=> T7,5/E4,5/S+2,5. Khaihotel3 nhưng invoice2,5 => CONFLICT/câu hỏi, không
dùng forecast3 hoặc auto sửa claim. Company-paid flight bị khaiPERSONAL
=> source-form contradiction cần làm rõ; PERSONAL không payment evidence.

Test raw company's payment2 và employee3 cùng invoice5 có proper split nếu
profile supported; source duplicate không double. Nếu multi-claim partial
allocation chưa trong MVP, assert UNRESOLVED thay vì guessed portions.

Fake input employee source format existing structured ledger + relations
CLAIM_EXPENSE (parse bổ sung); no real providers. Gold literals independent
production output, không expected-as-input. Five-quality negatives: missing
receipt, unreadable amount, wrong link same amount/date, extra scope source,
cash claim thiếu bounded attestation/coverage không full receipt.

- [x] **3.2 Compose facts và match một lần**

Run đọc current protected context source với Python adapter, không LLM;
regular originals qua Reader như hiện tại. Match payload thêm confirmed
claims (descriptions/declared values/source hints) được đánh dấu declarations,
không gold/budget answer. Match trả ba kinds, source support và ESTABLISHED/
PROPOSED/UNCLEAR; no repeat whole dossier report generation.

Claims form không vào expense namespace. Purpose được dùng chỉ theo policy
cho phép, payment proof bắt buộc theo R4. Một claim một expense cho MVP;
nhiều sources/pages cùng expense giữ aliases/provenance. Không nhân đôi bill
để đạt số rows; unsupported many-to-many giữ FACT. Company-only expenses
được tính T nhưng không E, không bắt employee khai lại flight đã có nguồn.

CLAIM_EXPENSE validation không trộn payment canonicalization: dedup/portion
overflow/SAME_EVENT vẫn đúng. Check claimed amount/payer/date/ref với source
state; material discrepancy tạo owner EMPLOYEE question có cả values/refs.
Every claimed row phải được mapped hoặc issue; every included expense phải
có work scope/eligibility, không count arbitrary foreign bill.

Reader.match hiện chỉ gửi work/employee/candidates: thêm confirmed claims vào
payload và accepted-kind/entity-ID validation, không chỉ sửa prompt. Context
relations và Reader relations namespace riêng; merge loại bỏ exact alias có
căn cứ, reject ID collisions trước overwrite. Source dates có nghĩa khác nhau:
invoice issue date không tự là service/payment date; không báo conflict vì
hai loại ngày khác nhau. So thời gian với cutoff theo field semantics, không
thêm quy định công tác/ngày chi mới ngoài Rulebook.

Temporal check date cần dùng: future source so money cutoff hoặc lệch trip
scope giữ issue; unknown date không block khi applicability không cần. Pending/
unknown history giữ raw trạng thái và whole groups nullable; zero chỉ valid
coverage. Imports/incidents đưa vào same evaluate path, không Report COMPLETE
chỉ vì main rules không biết linked blockers. Conditional/authority/phạm vi
được chấm như Rulebook; hard unresolved linked money không final proposal.

- [x] **3.3 Report/UI checkpoint**

Header “Quyết toán — Nguyễn An”, origin công việc, source-mode/context-current.
Main table khai / nguồn đã đọc / trạng thái / căn cứ, company vs employee
actual riêng; tổng khai không T/E. Summary “Kết quả đối soát đề xuất3triệu —
chưa phê duyệt”, unknown nói chưa chốt vì issue cụ thể. Technical facts/clocks
ở details; accountant/company-owned questions đúng owner, không employee
nhập lại A/B cho PASS. Generic ReportPanel không tự tính lại tiền.

Linked case chỉ REVIEW/questions, chưa DECIDE/record_money/handoff/closure.
Store guard LINKED_B7_REPORT_ONLY trên generic financial endpoints cho schema
này; frontend hide capability nhưng backend mới là guard. Legacy B7 không
bị đổi. Accountant review cũng kiểm current report/dependency/actor route,
không dùng review note làm approval B8.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked.py tests/settlement/test_b7_linked_context.py tests/settlement/test_b7_claim_links.py tests/settlement/test_readers.py tests/settlement/test_rules.py tests/settlement/test_questions.py -q
rtk proxy npm --prefix frontend run test -- --run src/settlement/B7Intake.test.tsx src/settlement/B7CompanyContext.test.tsx src/settlement/Report.test.tsx
```

## Task 4 — Dependency guards, end-to-end UI và chứng cứ

**Files:** Service/Store/b7_linked.py and tests linked/control/closure/evaluation;
frontend App/Actions copy; docs Product/System/Evaluation;
Create `docs/testing/B6_B7_LINKED_WALKTHROUGH.md`.

**Interfaces:** `Store.linked_b7_dependency_fingerprint(child_id)->str`
đọc parent case/decision/canonical money/source/context dependencies.
Run snapshot chứa fingerprint + context source id/hash. Run checkpoint,
publish và review kiểm lại, đổi dependency => STALE_INPUT/SUPERSEDED; parent
Stop => ORIGIN_STOP_ACTIVE/STOPPED. Service/API map error rõ, không technical
fact issue giả. CaseView.context_current và action reasons do server.

- [x] **4.1 Negative/integration tests**

Parent receipt thêm sau child snapshot: old Run không final current, refresh
snapshot rồi rerun uses actual mới; same TX added ledger not double. Parent
decision/source materially đổi/Stop giữa provider call và publish: output
late không current, no review/action. Actor wrong scope/company owner/child
link tamper không write. Two concurrent prepares một active child, same-key
idempotent, changed-body conflict; rerun không case/entitlement mới.

Source tới muộn về event trước cutoff: knowledge update và rerun; event sau
money cutoff không vào old math. Muốn current settlement mở cutoff rõ,
version mới; historical Run không rewrite. Parent proof copies còn readable;
delete linked parent guarded, child doesn't erase parent sources on delete.

B7 has expense data before source completeness phải INCOMPLETE/partial,
không A0/Bforecast/S0/close. B7 rights absent fails authority even B3 approval
valid. Existing ordinary B7/evaluator/control suites không bị weakened.

- [x] **4.2 Run required checks**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy .venv/bin/python -m pip check
```

Ghi exit/count/mode thật; không dự đoán số tests hoặc gọi worker green là
acceptance. Dataset source-first/new expected có provenance và file hashes;
không sửa frozen corpus để đạt suite.

- [x] **4.3 UI walkthrough incremental**

Fake provider/B3 company fixture/B7 config activated synthetic clock14/10,
DB/artifacts riêng/backend8010/frontend5174 theo guide B5. B7 rights file
source/model contract mới phải tạo trước commands; không cho user nhập clock
ở form hoặc ghi synthetic như tiền thực tế.

1. B3 approve8/advance2; B5 receipt2; mở linked child từ parent.
2. Employee khai actual hotel3/meal1/ground1, upload nguồn giá trị/payer đúng;
   save draft/reload giữ work và link, không copied forecast actual.
3. Run sau confirm: chưa company coverage thì questions ACCOUNTANT, không
   bắt employee khai RA/P/RP0.
4. Accountant cung cấp actual flight3 + payment vendor receipt, whole-work
   coverage đúng tới14/10, canonical advance alias và absence groups theo
   nguồn; refresh context/rerun => T8/E5/A2/S+3, chưa duyệt/chi/close.
5. Cases khác: actualhotel2,5; claim3 vs bill2,5; companyPaid nhưng PERSONAL;
   unknown history; money pending/incident; insufficient B7 rights; parentStop.
6. Parent cash/payment update sau snapshot show stale/refresh, no duplicate
   child or payable. Evidence links mở đúng child snapshot/origin records.

Đây là test UI với fake/structured originals; live invoices cần authorization
và cùng composition app, không hard-code outputs theo tên file. Prep/export/
manual-context/claim association effort phải ghi. Không browser workaround
khi đã denial; chưa thao tác => USER_UI_UNEXECUTED, không professional trial.

- [x] **4.4 Docs và self-review**

Update đúng capability: linked intake/snapshots/report/questions/review;
chưa B8/B9 linkage or auto payment/closure. EVALUATION phân biệt imports/
HUMAN_SOURCE_REVIEW với AI originals, claim/link/fact/whole-history axes và
technical/capability failures. Ranh giới routine-report theo đề A vẫn cần
bằng chứng và lập luận, không nâng compliance từ feature count.

## Acceptance

- [x] Parent/child/work/employee immutable; một active B7, draft/confirm/retry rõ.
- [x] Actual nguồn khác forecast; payer declaration không payment fact.
- [x] A gross canonical + coverage; no double event/false absence/missing-as-zero.
- [x] B budget từ decision, B7 rights riêng; company context chỉ đúng owner.
- [x] Claims/expenses/payments linked đúng, every missing row có issue/refs.
- [x] Parent/context changes/Stop/version guards giữ current reports an toàn.
- [x] UI source/state/owner readable, review chưa financial approval, no B8/B9 action.
- [x] Fake/LIVE/manual import/trial bằng chứng tách, chưa chạy ghi limitation.

## Prompt gửi coding agent

“Triển khai từng task của `docs/superpowers/plans/2026-10-11-b6-linked-settlement.md` cùng spec ở đầu. Giữ B3/B5 lịch sử và baseline datasets; một writer shared contracts. Tạo B7 riêng cùng work/employee, không mutate B3 job. Vừa code vừa có UI checkpoint. Company coverage/actual events và B7 rights phải riêng, không copied forecast/approved advance/PERSONAL thành fact. Claims↔expense↔payment và economic aliases phải có source support; no expected labels trong prompt. Intake thiếu vẫn nhận, final unresolved không PASS. Parent/context stale/Stop kiểm lúc publish/review. Linked slice report-only, chưa B8/B9. Dùng fake trước, không tự LIVE/Git/publish; báo actual checks/evidence và UI chưa kiểm.”

# B9 — Settlement Fulfillment & Closure Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, tuần tự bốn task có fake/API tests và UI checkpoints. Một writer shared contracts. Không tự subagent/Git/LIVE/publish. Thực hiện sau B8 acceptance, không shortcut bằng generic W05.

**Goal:** Bàn giao căn cứ chi/thu theo quyết định B8, ghi nhận và đối chiếu tiền thực tế, đóng quyết toán khi mọi nghĩa vụ và căn cứ đã đủ; giữ lịch sử điều chỉnh sau đóng.

**Architecture:** Tái sử dụng source artifacts, money_events, decisions, audit và SQLite transaction hiện có. Typed B7 events/projections tách whole-work reconciliation và fulfillment của một decision; Python giữ arithmetic/rights/controls. Handoff chỉ audit/reference, không payment-request entity và không bank execution.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite/pytest; React/TypeScript/Vite/Vitest hiện có. Không thêm dependency/table/queue/auth/workflow engine.

**Spec:** [B9 design](../specs/2026-10-11-b9-settlement-fulfillment-design.md);
**Prerequisite:** [B8 plan](2026-10-11-b8-settlement-decision.md) và [B8 spec](../specs/2026-10-11-b8-settlement-decision-design.md).

**Status:** IMPLEMENTED (fake/replay + HUMAN_SOURCE_REVIEW, 2026-10-11); chưa nghiệm thu LIVE/UI.

## Evidence (2026-10-11)

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**; không LIVE/Git/publish.
Prerequisite B6–B8 chứng minh bằng pipeline thật (`make_ready_linked`), không mock.
Commands/exit/count actual:

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment.py -q        # 26 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment_api.py -q    # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_money_revalidation.py -q # 3 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_closure.py -q           # 17 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_adjustment.py -q         # 7 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                              # 464 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                         # 884 passed
.venv/bin/python -m pip check                                                                              # No broken requirements found
npm --prefix frontend run test -- --run                                                                    # 139 passed (23 files)
npm --prefix frontend run build                                                                            # tsc --noEmit + vite build OK
```

Artifacts: `src/invoice_referee/settlement/b7_fulfillment.py` (mới),
models/service/store/API B9, `frontend/src/settlement/B7Funding.tsx` (+test),
`tests/settlement/test_b7_fulfillment.py`, `test_b7_fulfillment_api.py`,
`test_b7_money_revalidation.py`, `test_b7_closure.py`, `test_b7_adjustment.py`,
docs `docs/testing/B9_SETTLEMENT_FULFILLMENT_WALKTHROUGH.md`, `PRODUCT.md`,
`SYSTEM.md`. Breaking (source-justified): `B7CompanyConfig.company_ref` mới
(nullable); `B7OriginLink.adjustment_of_case_id` mới (nullable); linked-context
source id gộp cả packet-refresh và money-refresh (start loại **tất cả**); kind
`B7_SETTLEMENT_EVENT` mới trong `money_events`; `B7WorkflowView` thêm
fulfillment/revalidation/current_handoff/closure.

**Chưa kiểm (honest limits):** UI walkthrough `USER_UI_UNEXECUTED`; LIVE/OCR/LLM
quality PLANNED; chưa bank transfer/payment-request entity, mở lại refusal,
override ngoại lệ, tự tăng B, vendor-refund phức tạp, professional-user trial.

## Global Constraints

- Baseline A: handoff refs/report/decision/audit; không tạo yêu cầu chi/thu entity Stage B, không gửi ngân hàng.
- Approval≠receipt≠closure. Gross không clip; unknown/pending/coverage thiếu không0; no money event0.
- Đúng receiver COMPANY/NV trong scope bằng sources, không status/PERSONAL checkbox hoặc payee!=employee tự pass.
- Collection phân biệt RA/RP; một economic event tính một lần, không both full amounts hoặc vendor refund thành RA.
- B9 events thuộc decision/scope cụ thể; B5 advance không reimbursement/fulfillment B8.
- Partial receipt đúng giữ approved gốc, giảm remaining; reversal/overpay/sai người giữ incident, không auto chi/thu bù.
- Clocks/time/cutoff/known-at explicit; managed subtotal không whole history coverage. Không backdate để đóng.
- Parent/child Stop chặn managed action/closure, vẫn nhận source/actual fact; resume không auto retry.
- Guards đúng trong persisted transaction; fresh state/expected version/idempotency before mutations, no new framework.
- HUMAN_SOURCE_REVIEW ghi rõ công sức đọc/ghép; không claim bank authentication/OCR quality.
- Giữ legacy/B3 behavior; dedicated linked paths không bypass generic financial block.
- Không LIVE, Git, publish, outbound reminders hay professional-user trial giả lập. UI không thao tác ghi USER_UI_UNEXECUTED.

## B8 interfaces được dùng nguyên tên

`CaseView.b7_workflow`, `B7DecisionView.target/history_baseline/business_signature/
authority_signature/effective_at`, `B7DecisionTarget`, `effective_b7_time`,
`b7_business_signature`, `b7_cost_signature`, `b7_configuration_signature`, Service.decide_b7 và
Store.record_b7_decision. Trước khi code kiểm chúng đã wired/verified; nếu B8
chưa có thì thực hiện B8 trước, không viết fallback latest generic decision.

## Task 1 — Nguồn thực nhận và typed B7 actual events

**Files**
- Create: `src/invoice_referee/settlement/b7_fulfillment.py` (classification/project/revalidation helpers).
- Modify: models.py/service.py/store.py/`src/invoice_referee/api/settlement.py`.
- Test: new `tests/settlement/test_b7_fulfillment.py`, `test_b7_fulfillment_api.py`.
- Consume test fixture Task2 B8 `ready_linked_b7`; import chain `command/ready_b3/presented_b3/approved_b3` explicit tại module cần fixtures, không assume pytest tự discover.

**Interfaces**
- B7CompanyConfig.company_ref:str|None defaultNone, backend-owned; B9 collection không normalize unknown payee thành COMPANY. Seed synthetic config company_ref=`COMPANY-INVREF`; old config không auto grant identity.
- `B7MoneyFieldEvidence`: field Literal[amount_vnd,currency,payer_ref,payee_ref,event_at,receiver_outcome,event_namespace,event_ref,method,purpose,work_ref]; source_id/locator/raw:str; value:StrictInt|str|None; read_state Literal[READ,UNCERTAIN,MISSING]; origin Literal[HUMAN_SOURCE_REVIEW]. Structure giống B3 evidence, không unrelated refactor B3.
- `B7MoneyEventPayload`: decision_id:str|None; event_namespace/event_ref:str|None; method Literal[BANK_TRANSFER,CASH]; gross_vnd:StrictInt|None; payer_ref/payee_ref:str|None; event_at:AwareDatetime|None; reported_status Literal[RECEIVED,PENDING,FAILED,CANCELLED,UNCONFIRMED]; purpose Literal[REIMBURSEMENT_RECEIVED,ADVANCE_RETURN,REIMBURSEMENT_RETURN,UNKNOWN]; evidence:list[B7MoneyFieldEvidence]; allocation_note:str nonblank; supersedes_event_id:str|None. No client classification, employee/work from case.
- `B7MoneyIncident`: code Literal[WRONG_RECIPIENT,WRONG_PAYER,OVERPAY,CONFLICTING_EVENT,UNALLOCATED,REVERSAL,AFTER_CUTOFF,SOURCE_UNRESOLVED]; event_ids:list[str]; excess_vnd:StrictInt|None; refs:list[str]; reason:str.
- `B7MoneyEventView`: payload fields + id/case_id/kind Literal[B7_SETTLEMENT_EVENT]/employee_ref/work_ref/actor_id, created_at/known_at, classification Literal[CONFIRMED_RECEIPT,PENDING,FAILED,CANCELLED,UNCONFIRMED,INCIDENT], refs/source-use metadata, after_cutoff:bool, incidents:list[B7MoneyIncident]. Nullable raw fields remain nullable.
- `classify_b7_money(payload:B7MoneyEventPayload,*,employee_ref:str,work_ref:str,company_ref:str|None,sources:list[SourceRecord],effective_at:datetime)->tuple[str,list[B7MoneyIncident]]` (deterministic).
- `Service.add_b7_settlement_proof(case_id:str,upload:Upload,command:Command)->SourceRecord`;
  `Service.record_b7_settlement_money(case_id:str,payload:dict,command:Command)->B7MoneyEventView`.
- Store counterparts `record_b7_money(case_id,payload,command,b7,b3,policy)`; proof Store.add_source backend source_use=B7_SETTLEMENT_PROOF with accountant route/source bounds.
- POST `/api/cases/{id}/settlement-money-proofs` multipart; POST
  `/api/cases/{id}/settlement-money-events` typed envelope. Operation B7_RECORD_MONEY; use existing money_events table, generic MoneyEventView never parse this kind.

- [x] **1.1 Tests đỏ proof/outcome/rights**
Define test-only `money_payload(source_id,decision_id,*,amount=2_000_000,
purpose="REIMBURSEMENT_RECEIVED",status="RECEIVED",payee="NV-DEMO-01",
event_ref="TX-SET-01")` trong test_b7_fulfillment.py bằng literal source fields
theo B3 `receipt_payload` pattern; đủ11 fields trừ optional unknown. Source text
giữ actual amount/currency/parties/namespace/ref/work/method/outcome/time và
allocation, không chứa expected PASS/remaining. Define `upload_money_proof`
gọi dedicated API/service với actual child.version; không upload source trống.

Core param test phải đặt ở classifier unit với SourceRecord từ temp retained
artifact (not fake path), và service integration cùng ready linked fixture:

| Source/payload | Expected |
| --- | --- |
| Receipt2 đúng NV/company/work/currency/time | CONFIRMED_RECEIPT; chưa tự close |
| Bank debit/SUBMITTED chỉ payer view | UNCONFIRMED/PENDING, không actual receipt |
| Cash signed receiver receipt đúng scope | CONFIRMED_RECEIPT, không đòi bank source |
| Company nhận RA đúng company_ref | RA eligible, không P |
| Payee công ty khác hoặc NV tự nhận collection | WRONG_RECIPIENT, không fulfillment |
| Thiếu source/amount/locator/time/ref/currency | Giữ raw nullable + SOURCE_UNRESOLVED |
| Vendor refund/mixedRA-RP/mismatchpurpose | UNALLOCATED; không auto RA |
| Employee/wrong accountant gọi event endpoint | 403; no event |
| Child/parent Stop hoặc stale decision | Vẫn lưu đã xảy ra; không tự mở action |
| Amount0/negative/float | 422; không zero-money record |

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment.py tests/settlement/test_b7_fulfillment_api.py -q
```
Expected đỏ trước methods/models có; cần behavioral assertion failure sau setup.

- [x] **1.2 Implement source-backed classifier + append-only identity**
Reuse source upload limits/artifact atomic write/B3 evidence validation
patterns, không copy toàn engine. Accountant reads source: normalized values
must keep raw/locator/ref and agree with payload; no assurance of document
authenticity. Source mismatch không “model confidence0.99” override.
BANK receipt needs receiver-outcome support; CASH needs receiver receipt per
Rulebook. Wrong-party/source contradictions giữ incident, no RECEIVED shortcut.
Validate explicit same-work allocation; intent declaration alone không payer fact.

Event identity economic namespace/ref shared with B5/company ledger; same
command replay first; new key exact alias same event returns canonical record
or linked observation without double contribution; differing same identity
preserve both observations + CONFLICTING_EVENT. Do not block receiving raw
contradiction by pretending duplicate means harmless. Preserve raw signed
proofs for mismatched recipient/time, no clipping/auto compensation.
PENDING→final with same identity+supersedes + source outcome allowed; final
receipt→return uses new event identity, not rewrite old event. Wrong final
amount correction is linked new source/correction record + recheck; no auto
final-wins. After-cutoff stored even when not in current report.

- [x] **1.3 Guards + history integration separation**
Proof upload increments case_version only, backend source-use excludes it
from Reader expense input. Record event classification increments version;
audit flags pending recheck/money dependency, not direct input facts override.
No new entity payment request. Direct Store also validates route/source/type;
special generic guard remains. At closed child, 409
B7_CLOSED_ADJUSTMENT_REQUIRED with adjustment route, no mutation old closure.
Generic `_money_summary` skips new event kind before enum fields access; never
accidentally counts it twice or crashes CaseView while B9 projection absent.

UI checkpoint later Task4: upload proof/record actual2, approved still3,
no false message “đã chuyển qua ngân hàng”.

## Task 2 — Fulfillment projection, cumulative history và revalidation

**Files**
- Modify: b7_fulfillment.py/models.py/service.py/store.py/b7_linked.py/pipeline.py.
- Test: test_b7_fulfillment.py/test_b7_fulfillment_api.py/test_b7_linked_context.py;
  new `tests/settlement/test_b7_money_revalidation.py`.

**Interfaces**
- `B7FulfillmentReceipt`: backend-only model, event_id/canonical_id/decision_id:str;
  amount_vnd:StrictInt|None; state Literal[CONFIRMED,PENDING,UNKNOWN,FAILED,CANCELLED];
  qualifying:bool; after_cutoff:bool; incidents:list[B7MoneyIncident] default[].
  Qualifying derived from Task1 evidence/parties/purpose/work/baseline/allocation,
  never request field. canonical_id from validated economic identity/alias.
- `B7FulfillmentSummary`: decision_id:str; direction (B8 target direction);
  approved_vnd:StrictInt; recorded_received_vnd:StrictInt|None; fulfilled_vnd:StrictInt;
  remaining_vnd/known_remaining_vnd:StrictInt|None; pending_count/unknown_count:StrictInt;
  incidents:list[B7MoneyIncident]; status Literal[WAITING,PARTIAL,FULFILLED,BLOCKED,BALANCED];
  managed_scope:str; as_of/knowledge_cutoff:AwareDatetime.
- `project_b7_fulfillment(decision_id:str,approved_vnd:int,direction:str,
  receipts:list[B7FulfillmentReceipt],*,as_of:datetime,knowledge_cutoff:datetime)->B7FulfillmentSummary`.
- `B7RevalidationView`: original_decision_id/current_report_id:str; status Literal[VALID,NEEDS_RECHECK];
  cost_signature/receipt_history_signature:str; qualifying_event_ids:list[str];
  blocked_reasons:list[str]; refs:list[str]; created_at:AwareDatetime.
- `revalidate_b7_decision(decision:B7DecisionView,current_report:Report,
  canonical_history:dict,qualifying_events:list[B7MoneyEventView],current_cost_signature:str)->B7RevalidationView`.
- `Service.refresh_b7_money_context(case_id:str,command:Command)->CaseView`;
  POST `/api/cases/{id}/settlement-money-context/refresh`, accountant-only,
  server clocks; audit B7_MONEY_CONTEXT_REFRESH. Sets new snapshot as-of/known
  cutoff from effective_b7_time, rebuilds canonical whole history; no provider
  call inside mutation. Start Run afterwards via existing endpoint/command.
- `Service.revalidate_b7(case_id:str,command:Command)->B7RevalidationView`;
  POST `/api/cases/{id}/settlement-revalidations`, accountant-only, after current Run;
  audit B7_REVALIDATE persisted; no new approval, no provider calls.
- B7WorkflowView adds fulfillment:B7FulfillmentSummary|None, revalidation:B7RevalidationView|None;
  Store dedicated projection validates sources/classification, config/parent/Stop dependencies.

- [x] **2.1 Pure projection tests đỏ có literal expected**

```python
from datetime import datetime, timezone
from invoice_referee.settlement.models import B7FulfillmentReceipt
from invoice_referee.settlement.b7_fulfillment import project_b7_fulfillment

def test_partial_receipt_does_not_change_approved_amount():
    at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    receipt = B7FulfillmentReceipt(event_id="M-1", canonical_id="BANK:C:TX-1",
        decision_id="D-1", amount_vnd=2_000_000, state="CONFIRMED",
        qualifying=True, after_cutoff=False)
    result = project_b7_fulfillment("D-1", 3_000_000, "PAY_EMPLOYEE", [receipt],
        as_of=at, knowledge_cutoff=at)
    assert result.approved_vnd == 3_000_000
    assert result.recorded_received_vnd == 2_000_000
    assert result.fulfilled_vnd == 2_000_000
    assert result.remaining_vnd == 1_000_000
    assert result.status == "PARTIAL"

def test_pending_keeps_known_subtotal_but_not_executable_remaining():
    at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    receipt = B7FulfillmentReceipt(event_id="M-1", canonical_id="BANK:C:TX-1",
        decision_id="D-1", amount_vnd=1_000_000, state="PENDING",
        qualifying=True, after_cutoff=False)
    result = project_b7_fulfillment("D-1", 3_000_000, "PAY_EMPLOYEE", [receipt],
        as_of=at, knowledge_cutoff=at)
    assert result.recorded_received_vnd is None
    assert result.remaining_vnd is None
    assert result.pending_count == 1
    assert result.status == "BLOCKED"
```

Add literal assertions: overpay4→raw4/fulfilled3/excess1/BLOCKED, wrong
decision receipt doesn't count, canonical duplicate2+2=>2, old pending
supersededreceived not pending+received, failed/cancelled not receipt,
qualifying=False incident not ignored, BALANCED no event0, future event
excludedcurrent receipt with blocker. Pure test isn't integration/evidence validation.

- [x] **2.2 Implement projection and canonical whole-history merge**
Filter by typed event/work/decision and proof support before sums. Receipts
already included in B8 baseline P/RA not new fulfillment; newly discovered
pre-baseline source not guessed “post-decision execution”. Whole history uses
same canonical identities from B5/B9/company packet; unify exact aliases with
sources, preserve contradiction/unknown. Add named namespace records, no
legacy generic event_ref-only dict collision. Never whole-history average/sum
of precomputed old subtotal plus each duplicate ledger row.

Projection uses eligible positive raw actuals; gross overapproved preserves
raw then fulfilled capped, adds incident. Pending/unknown/materialincident
remaining null, known_remaining optional labelled estimate, no green ready.
Managed no events may fulfilled0/remainingapproved only after explicitly
checking managed registry scope; whole P/RA still from coverage. Refusal not
approval target; returns/reversals do not reactivate permission to pay.

`refresh_b7_money_context` advances cutoff server-side, creates retained
current system source with real childsource refs and canonical B9 events,
keeps packet coverage unchanged until accountant supplies source-backed
extension. If coverage not to newasof preserve unknown/issues, not autoextend.
Child/parent Stop allows source/fact intake, not current usable action output.
Receipt evidence bits imported as named history events, never invoice
expense. Store.snapshot/RunInput includes current money dependency signatures;
checkpoint/publish detects changes mid-run before current report accepted.

- [x] **2.3 Revalidate exactly correct fulfillment without reapproval**
Cost basis E/T/B, expense/payer/eligibility/relations/policy/conditions unchanged;
history_delta equals canonical qualifying receipts of approved decision;
no extra advance/contradiction/refund/unknown, same scoped route/decision.
Then VALID revalidation olddecision↔newreport +receiptids retains original3
and remaining1/0. The current report S1/0 does not become new approved amount.
Do not compare original entire signature including P to updated one as equal;
do not drop every financial change from signature either.

Material history/source change→NEEDS_RECHECK, no action/close. Rights at
new handoff require current active grant; original decision authority snapshot
remains. Config change/revocation blocks new action for recheck, expired grant
after a valid completed action does not erase actuals or force ritual approval
to close already-valid fulfillment. Revalidation+guard must be reevaluated
in closure/action transaction; recorded VALID badge is not sufficient.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment.py tests/settlement/test_b7_money_revalidation.py tests/settlement/test_b7_linked_context.py -q
```
Integration trace: approved3→actual2→new coverage/context/run S1→revalidation
VALID remaining1→actual1→new coverage/context/run S0→revalidation VALID,
same original decision. Each step asserts source refs/money event count/history.

## Task 3 — Gói bàn giao đúng remaining và đóng có căn cứ

**Files**
- Modify: models.py/b7_fulfillment.py/service.py/store.py/API.
- Test: new `tests/settlement/test_b7_closure.py`; test_b7_fulfillment_api.py,
  test_b7_money_revalidation.py; regression test_controls.py/test_b7_linked.py.

**Interfaces**
- `B7HandoffPayload`: decision_id:str, reason:str nonblank; extra forbid.
- `B7HandoffView`: id/case_id/decision_id/report_id/employee_ref/work_ref/actor_id:str;
  direction:str; remaining_vnd:StrictInt; obligation_signature/business_signature/receipt_history_signature:str;
  refs:list[str]; created_at:AwareDatetime; valid_until:AwareDatetime|None (grant end, not invented TTL).
- `B7ClosurePayload`: decision_id:str, current_report_id:str, reason:str nonblank; no client amount/closing cutoff/source trust.
- `B7ClosureView`: id/case_id/decision_id/current_report_id/actor_id:str;
  kind Literal[SETTLEMENT_COMPLETE]; employee_ref/work_ref:str; close_as_of/knowledge_cutoff/created_at:AwareDatetime;
  input_revision/control_epoch:StrictInt; business_signature/receipt_history_signature/parent_fingerprint:str;
  source_refs/event_ids:list[str]; original_decision_id:str; revalidation_ref:str|None; reason:str.
- `b7_closure_blockers(*,report:Report,decision:B7DecisionView|None,
  fulfillment:B7FulfillmentSummary|None,revalidation:B7RevalidationView|None,
  scope_current:bool,coverage_current:bool,stop_active:bool,open_question_count:int)->list[str]`.
- `Service.handoff_b7(case_id:str,payload:dict,command:Command)->B7HandoffView`;
  `Service.close_b7(case_id:str,payload:dict,command:Command)->B7ClosureView`.
- Store counterparts same config/policy parameters as B8; POST `/api/cases/{id}/settlement-handoffs`,
  POST `/api/cases/{id}/settlement-closures`. Operations B7_HANDOFF/B7_CLOSE; audit only for handoff/closure, no new table.
- CaseView.b7_workflow current_handoff:B7HandoffView|None, closure:B7ClosureView|None;
  allowed_actions HANDOFF_B7/CLOSE_B7 with concrete reasons from same transaction-grade helpers.

- [x] **3.1 Tests đỏ no basis/no decision/no whole coverage**

Add unit blocker test to distinguish S0 from approval, independent raw fixture:

```python
from invoice_referee.settlement.b7_fulfillment import b7_closure_blockers
from tests.settlement.b7_workflow_builders import report_from_values

def test_zero_net_alone_cannot_close():
    report = report_from_values(2_000_000, 2_000_000)
    blockers = b7_closure_blockers(report=report, decision=None,
        fulfillment=None, revalidation=None, scope_current=True,
        coverage_current=True, stop_active=False, open_question_count=0)
    assert blockers
    assert any("quyết định" in reason.lower() for reason in blockers)
```

Service/API tests: duyệt chi3, hai receipt2+1 rồi đủ căn cứ mới đóng; duyệt
thu0.7, công ty nhận RA0.7 rồi S0 mới đóng; BALANCED đủ căn cứ đóng mà không
tăng money_events. Thiếu decision, chỉ có rawS0, REFUSE còn A2, receipt một
phần, pending/incident/câu hỏi trọng yếu, coverage thiếu, sai scope, stale
clock hoặc parent Stop đều không đóng. Nhân viên/người duyệt/kế toán sai route
không có quyền đóng. Same-key replay trả closure gốc kể cả expected version
cũ; payload khác không thay closure.

- [x] **3.2 Implement handoff transaction guards**
Đọc original decision, current cost/report, receipts/revalidation, current
config/route/parent. Một current handoff cho cùng obligation signature; key
mới cùng signature reuse, payload conflict409. Receipt2 làm remaining1, số
duyệt vẫn3; handoff3 cũ giữ trong history và không còn executable. Chặn khi
pending/unknown/incident/Stop hoặc quyền cho hành động mới đã hết hiệu lực;
BALANCED không handoff tiền. Fact intake không yêu cầu phải có handoff trước:
tiền đã xảy ra bên ngoài vẫn cần ghi nhận, nhưng không biến event chưa được
duyệt thành hành động thực hiện tự động.

- [x] **3.3 Implement closure transaction guards and exact snapshot**
Mọi gate ở spec§6 nằm trong `_write` trước khi ghi audit/stage: server sources,
history coverage/component states, S0, target fulfillment/revalidation, quyền
tại decision/action, câu hỏi trọng yếu và parent/child control. Cutoff cũ
không được che receipt đến muộn; unknown slot là blocker. Closure reason là
ghi chú, không proof. Chỉ chuyển SETTLEMENT_CLOSED khi tất cả gate đạt; không
event0, không đổi job parent. Parent UI chỉ đọc trạng thái child đã đóng.

Race tests with barriers/two SQLite writers: close-vs-source, close-vs-Stop,
close-vs-money/context and handoff-vs-receipt; exactly one accepted mutation
or stale gate conflict, no closure timestamp before failed transaction.
Protect get_case/history parsing cho typed kind/audit closure mới. Generic
REJECTED_REQUEST_ENDED/closures/handoffs remains blocked linked; direct
Store generic cannot bypass. Raw actual nhận khi Stop vẫn được lưu.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_closure.py tests/settlement/test_b7_fulfillment_api.py tests/settlement/test_b7_money_revalidation.py tests/settlement/test_controls.py -q
```

## Task 4 — Điều chỉnh sau đóng, UI theo vai và end-to-end checkpoint

**Files**
- Modify: models.py/service.py/store.py/b7_linked.py/API; tests test_b7_closure.py;
  new `tests/settlement/test_b7_adjustment.py`.
- Create: `frontend/src/settlement/B7Funding.tsx`, `B7Funding.test.tsx`.
- Modify: types.ts/api.ts/Actions.tsx/App.tsx/B7Intake.tsx/B7CompanyContext.tsx/B7Approval.tsx/uiCopy.ts/stylesheet in use.
- Docs after implementation: PRODUCT.md/SYSTEM.md/EVALUATION.md capability/evidence sections only;
  new `docs/testing/B9_SETTLEMENT_FULFILLMENT_WALKTHROUGH.md`.

**Interfaces**
- B7OriginLink adds adjustment_of_case_id:str|None defaultNone server-owned;
  form cũ thiếu field vẫn valid. Generic revise cannot wipe/spoof.
- `B7AdjustmentPayload`: reason:str nonblank; no employee/work/money/basis overrides.
- `Service.prepare_b7_adjustment(closed_case_id:str,payload:dict,command:Command)->CaseView`;
  Store counterpart `prepare_b7_adjustment(closed_case_id,payload,command,b7,b3,policy)`.
- POST `/api/cases/{id}/settlement-adjustments`, accountant right route;
  expected_version của closed case, audit B7_ADJUSTMENT_PREPARED; một active
  settlement cho employee/work, tính cả hồ sơ thường và adjustment.
- TS mirror B9 models, api `uploadB7Proof`, `recordB7Money`, `refreshB7MoneyContext`,
  `revalidateB7`, `handoffB7`, `closeB7`, `prepareB7Adjustment` using command envelope.
- `B7FundingPanel({view,onChanged,onError})` cùng callback conventions B3Funding;
  dùng backend workflow/allowed_actions, UI không tự tính formula hoặc quyền.

- [x] **4.1 Adjustment tests đỏ rồi implement minimal linked draft**
Closure cũ giữ byte-identical/as-of immutable. Draft mới cùng employee/work/B3,
link adjustment do server cấp, origin được bảo vệ, giữ cumulative money history
và copies/refs của originals cần thiết. Nguồn cũ không tạo quyền nhận tiền lần
nữa. Retry cùng command reuse child; hai key đồng thời không tạo hai active
cases. Sai công ty/scope/actor không tạo adjustment. Upload vào hồ sơ đóng
trả lỗi cùng route adjustment, không bỏ nguồn âm thầm hay reopen closure cũ.
Sau khi thêm nguồn vào draft mới, thực hiện B6/B7/B8 bình thường.

Expected độc lập: hồ sơ cũ E5/A2/P3⇒S0 đã đóng; thêm khoản chi nhân viên0.5 có
nguồn ⇒ E5.5/A2/P3/calculatedS0.5. Nếu T8/B8 thành T8.5 thì POLICY unresolved,
không tự approved0.5. Một scope khác đã có B10 và đủ quyền có thể propose0.5,
vẫn cần B8 mới; không chi3.5 lại. Alias receipt cũ trong packet mới vẫn P3,
không P6; A2 không reset0. Vendor refund/return phức tạp giữ material incident,
không fabricate RA/RP. Rerun/exact copy không auto adjustment. Tạo draft có
reason không phải tạo entitlement; receipt được biết sau đóng vào history
của adjustment, không sửa closure cũ.

- [x] **4.2 UI tests và role surfaces**
ACCOUNTANT: **Đã duyệt3 / Đã đối chiếu thực nhận2 / Còn phải chi1**, proof file,
method/parties/namespace/ref/date/outcome/purpose/evidence. Collection dùng nhãn
**Công ty đã nhận**; lời khai “nhân viên đã trả” không đủ. Party profile readonly
khi đã rõ, proof chưa rõ giữ blank. Fields kỹ thuật/locators vào vùng chi tiết
rà soát, không nằm ở màn mặc định. Hiển thị tên người/công ty thay raw IDs.

Hiển thị remaining/source/incident card, **Xem gói bàn giao**, **Ghi nhận kết quả
thực tế**, **Cập nhật đối chiếu tiền và kiểm tra lại**, **Đóng hồ sơ quyết toán**.
Refresh context + Start Run là hai idempotent commands; sau run thành công
gọi revalidation theo điều kiện backend, thất bại hiển thị chờ xử lý. Không
silent approve. Nút disabled nói gate cụ thể; đóng là thao tác chủ động, không
auto-close sau record. Incident không có checkbox clear; sửa nguồn/status
revision có refs. Mixed return allocation nói cần làm rõ, không mở freeform
fields để người dùng tự net tiền không có căn cứ.

EMPLOYEE: readonly decision/số cần nhận hoặc hoàn/tiến độ; tải proof phía mình
qua source intake, không classify RECEIVED hoặc ghi financial events/close.
APPROVER: xem decision/outcome/history, không money-entry form. Closed banner
có reason/as-of và nút accountant **Tạo hồ sơ điều chỉnh**. Adjustment ghi rõ
liên kết closure cũ; không reset report hoặc tự nói closure cũ sai ở mốc cũ.

- [x] **4.3 API/restart/UI end-to-end matrix**

| Case | Các thao tác và expected literal |
| --- | --- |
| PAY-01 | B3 B8/ứng2 → B5 nhận2 → B7 E5/S3 → B8 duyệt3 → B9 nhận2/còn1 → nhận1 → coverage/context/rerun S0 → revalidate cùng approval → đóng |
| COLLECT-01 | E1.3/A2/RA0/P0/RP0 → S−0.7 → duyệt thu0.7 → công ty nhận RA0.7 → rerun S0 → đóng |
| BALANCE-01 | E2/A2/RA0/P0/RP0 → BALANCED → mọi gate sạch mới đóng; money_events không tăng |
| PEND-01 | Submitted1 chưa có receiver proof → không actual/handoff/close; status được xác minh cùng identity, không cộng hai lần |
| WRONG-01 | Chi2 cho NV khác hoặc thu0.7 vào công ty khác → raw còn nguyên/incident/không tự chi lại |
| OVER-01 | Duyệt3, actual4 → gross4/fulfilled3/excess1 incident; không đóng hoặc tự quyết thu1 |
| DUP-01 | Một TX xuất hiện ở managed events/company ledger, alias có căn cứ → tính một lần; cùng amount nhưng TX khác không dedup |
| CLOCK-01 | Receipt vượt cutoff cũ → lưu history/không sửa report cũ; không auto mở rộng external coverage; cần run mới |
| CONTROL-01 | Parent/child Stop → handoff/close blocked/raw receipt vẫn nhận; resume cần recheck, không bank retry |
| ADJUST-01 | Hồ sơ cũ S0/P3 đã đóng → chi phí mới0.5 → calculatedS0.5 + POLICY nếu T>B; giữ closure cũ/không chi3 lại |

Mỗi case dùng scope/DB riêng hoặc opening history literal đúng ý nghĩa, không
dồn thí nghiệm khác nhau vào cùng work demo. Restart giữ decision/event/
canonical IDs/revalidation/closure; double click và các request đồng thời
không double fulfillment. So sánh DB records + report + UI, không chỉ status code.

- [x] **4.4 Required checks và evidence report**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Chạy focused tests mỗi task trước, broader checks bắt buộc một lượt cuối;
chỉ lặp khi có thay đổi hoặc failure mới. Walkthrough cho exact fake fixture paths/personas,
env SETTLEMENT_B3_CONTEXT_PATH + SETTLEMENT_B7_CONTEXT_PATH (company_ref/right
limits/clock), temp DB/artifact root/cổng8010&5174 riêng. Dùng current factory
`invoice_referee.api.settlement:create_runtime_app`, no legacy API. Two shell
commands startup dưới rtk proxy env, không LIVE hoặc secret logging từ .env.
Ghi công sức chuẩn bị/rà soát và HUMAN_SOURCE_REVIEW, không fraud/authentication
guarantee. UI thực hiện bằng tool được phép hoặc người dùng: ghi thao tác/ảnh;
nếu chưa làm ghi USER_UI_UNEXECUTED. Test evidence là exit/count/mode actual,
không dùng lại counts cũ của B6.

## Acceptance coverage map

| Design | Plan |
| --- | --- |
| §1/§5 handoff/current remaining/Stop | Task3; Task4 CONTROL/PAY/UI |
| §2 receipt proof/RA-P-RP/party/outcome | Task1; Task4 COLLECT/PEND/WRONG |
| §3 identity/corrections/overpay | Task1+Task2; Task4 DUP/OVER |
| §4 whole history vs obligation/cutoff/revalidation | Task2; Task4 CLOCK/PAY |
| §6 closure/no zero/no refusal shortcut | Task3; Task4 BALANCE/API race |
| §7 post-close adjustment | Task4.1/ADJUST |
| §8 roleUI/evidence | Task4.2–4.4 |

## Prompt giao coding agent cả B8 và B9

```text
Đọc AGENTS.md. Triển khai tuần tự hai plan:
docs/superpowers/plans/2026-10-11-b8-settlement-decision.md
docs/superpowers/plans/2026-10-11-b9-settlement-fulfillment.md
và hai design liên kết. B8 phải pass prerequisites B6/B7 + guards/UI trước B9.
Không mở generic LINKED_B7_REPORT_ONLY bằng xóa guard: dùng dedicated routes,
Store transaction checks và typed B7 lifecycle trong tám bảng hiện có.
E/net do server xác định, một B7 grant đủ quyền; APPROVE/RETURN/REFUSE không fake receipts.
B9 là baseline A: handoff refs, nguồn actual chi/thu, phân biệt P/RA/RP,
canonical identity dedup, partial fulfillment giữ approved, unknown/incident không0.
Correct receipt giảm remaining không hủy approval; whole history/current coverage
vẫn phải recheck trước close. S0/receipt0 hoặc refusal không shortcut close.
Giữ postclosure adjustment/source/history, không pay lại baseline receipts.
Làm UI theo nhân viên/kế toán/người duyệt từng checkpoint, cùng backend logic.
Dùng fake mặc định. Không LIVE/Git/publish/bank/enterprise infrastructure.
Ghi actual evidence commands/exit/count/mode, UI/LIVE chưa kiểm. Nếu browser
bị denial không bypass. Không mock report COMPLETE hoặc nới gold để pass.
```

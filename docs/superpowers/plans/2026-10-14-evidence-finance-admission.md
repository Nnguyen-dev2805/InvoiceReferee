# Evidence-to-Finance Admission Implementation Plan

> **For agentic workers:** Thực hiện từng task theo AGENTS.md, một integrator sở hữu
> workflow/schema/commands. Người dùng yêu cầu **không gọi subagent review**; implementer
> tự review và ghi bằng chứng. Các bước dùng checkbox. Không commit/push nếu chưa có
> ủy quyền Git riêng.

**Goal:** Nối typed OCR evidence report vào nghiệp vụ employee-paid của final để
routine tạo đúng yêu cầu chi/thu hoặc cân bằng; thiếu căn cứ chuyển đúng FACT/POLICY/
AUTHORITY, không biến model output thành tiền đã xác minh.

**Architecture:** Giữ một CaseWorkflow/DB/job/audit. Thêm pure admission mapper từ
ReadResult + organization snapshot + scoped confirmations sang AssessmentInput;
Reconciler/policy vẫn quyết định effects và CaseWorkflow recheck read-set rồi commit.
Context được persist đủ, declaration Q32 mang mức căn cứ riêng, actual money vẫn
qua ledger và RecordActual. Không transplant lifecycle Hoangha hoặc dùng STUB
transcription để “nối” LIVE.

**Tech Stack:** Python3.12/uv, FastAPI/Pydantic/SQLite, các provider Mistral/X-Kiro hiện
có, React/TypeScript chỉ cho command/view compatibility. Không thêm broker/framework.

**Spec:** [design §§1–5/14–15](../../final/ARCHITECTURE_AND_EVALUATION.md),
[contracts §§2–6/10/12](../../final/IMPLEMENTATION_CONTRACTS.md),
[ADR007](../../adr/0007-money-confirmation-basis.md),
[mapping25](../../../data/tham-khao/uc-03/CASE_MAPPING_FINAL.md),
[pilot inputs/gold](../../../data/test-kit/uc03-pilot/README.md).

## Global Constraints

- Một claimant/một hoạt động, VND; công tác nội địa. Company-direct/other-payer giữ
  nguồn và báo ngoài scope, không cộng C vào hoàn trả nhân viên hoặc silently drop.
- Mọi PDF/JPG/JPEG/PNG/page qua OCR; UNKNOWN/conflict/missing score trọng yếu không
  thành zero/known. Không đổi exact-ref1.0/weights/.50/.75/.90 matcher đã accepted.
- Q32: responsible employee confirmation + service evidence chỉ trong E<=8.000.000
  và abs(S)<=4.000.000, không material conflict. Ngoài ngưỡng: FACT paid basis trước,
  AUTHORITY sau khi E known; không dùng approval để waive factual truth.
- A/P/R cần completed money/witness đúng trách nhiệm/scope; zero cần coverage đủ
  funds/kinds/opening balances/as_of. Paper printed totals/advance/return không là events.
- B độc lập; system recognition8tr/issue4tr, approver20tr/action đúng scope/profile/time.
  Không cấp quyền bằng client role, model, chữ ký mock hoặc sửa fixture để ép PASS.
- Typed admission có source/digest/quote/ownership, giữ unresolved expense thay vì
  chỉ cộng phần đọc được. Supporting proof không tính như một expense thứ hai.
- Routine đủ gates không có câu hỏi/approval mặc định. Execution actor khác issue owner.
- Gold/provenance/expected không được app/model đọc. Pilot3 là development cùng
  family, không independent holdout. STUB/RECORDED/LIVE phải ghi đúng origin.
- I/O provider ngoài transaction; commit chỉ current input/control/context/ledger/usage
  versions. Stop/stale/duplicate không tạo late or duplicate instruction.
- Pilot snapshot/gold initial as_of=2026-10-10T18:00:00+07:00. Inject a controlled clock
  in the integration harness (CaseWorkflow default remains real UTC); use the same
  clock for assessment and commit-time grant checks. Interactive UI on today's date
  needs a responsible refreshed coverage through decision time, not a silently
  backdated assessment or extended witness. Test stale coverage as FACT/no instruction.
- EVIDENCE_READY guard giữ cho tới A5 gate. Không để Answer/Decide/Resume/RecordActual
  rơi lại `_transcription_for` trong LIVE/REPLAY. Dữ liệu legacy STUB test tách riêng.

## Current evidence and known gaps

Snapshot đọc: final `a68a8900...`, có chỉnh sửa cùng workspace được giữ. CodeGraph
Verify, index báo fresh nhưng earlier-engine warning; generation/coverage tool không
expose ⇒ UNKNOWN. Các material ranges được đọc source fallback, không re-index.

- `workflow/service.py::_publish_evidence_report` publish EVIDENCE_READY; `_assess_and_commit`
  return khi reader wired. Đây là guard có chủ đích, không lỗi cần xóa riêng lẻ.
- `import_company_context` hiện chỉ persist activity/people/grants/witnesses/import log;
  bỏ `policies/ledger/coverage`, mất metadata budget. `snapshots.py` dùng transcription
  để dựng expense/money/coverage, policy/read-set có fallback hard-coded. Cần thay LIVE
  consumer bằng snapshot thật, không gán tạm field values để nhận kết quả pilot.
- Submit hiện không có typed Q32 claim; generic payer confirmation không đủ biểu đạt
  per-expense amount/refs và basis tier. Actual ledger root-bound nhưng context trước
  tạo root cần activity/employee scope; không ép context ledger vào root giả.
- Profile SETTLEMENT_FORM `amount_words` đang NON_CRITICAL trái contracts §12.3.
  Khôi phục contract trong A0, không mở lại quyết định chỉ để match current code.
- Pytest lượt tạo pilot: **352 passed / 11 failed** do `data/kiem-thu` bị xóa trước
  đây (ledger tên failures trong [evidence](../../final/reviews/2026-10-14-uc03-pilot-evidence.md)).
  Không claim suite GREEN, không restore legacy corpus vào repo để che mismatch scope.

## Review Focus

1. Hóa đơn đúng nhưng thiếu paid claim/history: giữ E/A/P/R UNKNOWN, không E=0/zero return.
2. Q32 đủ nhưng ngoài8/4 hoặc source nói company paid: đúng basis/owner/scope, không bank fact giả.
3. Corrected declaration/model link conflict với paper/invoice: giữ hai nguồn; không chọn bằng confidence.
4. Stop/basis change trong lúc read hoặc confirm: không late instruction, không reset execution unknown.
5. RecordActual/reversal và duplicate economic usage: actual gross giữ, net S đúng, không order lần hai.

## File map and interfaces

Lead implementation calls (không đổi nghiệp vụ):

- Create `domain/organization.py`: di chuyển OrganizationContext hiện tại về domain;
  evaluation/models re-export để compatibility. Một DTO, không duplicate schema.
- Modify `domain/finance.py`: `PaymentBasisKind` = INDEPENDENT_PAYMENT /
  FINANCIAL_CONFIRMATION / EMPLOYEE_DECLARATION_Q32 / UNSPECIFIED_LEGACY;
  ExpensePayment thêm `basis_kind` (default UNSPECIFIED_LEGACY cho STUB compatibility)
  và `responsible_actor`. LIVE admission không nhận UNSPECIFIED_LEGACY.
- Define `PaymentBasisView(expense_id:Id, kind:PaymentBasisKind, actor:Id|None,
  refs:tuple[EvidenceRef,...], rule_id:str|None)` in that same file. No separate
  ledger event is created for this view. `SettlementConclusion.payment_basis` and
  `CaseView.payment_basis` are tuples of this type (default empty for compatibility).
- Modify `domain/case.py`: AssessmentInput thêm `admission_issues`,
  `admission_problems`, `expense_set_complete:bool=False` (server-owned, không client field);
  conclusion/view expose per-expense payment basis/actor/refs.
  Numeric E policy-admitted dùng được cho arithmetic, nhưng view không gọi Q32 là
  independently verified bank fact; A/P/R không bao giờ tạo từ Q32.
- Create `workflow/context_records.py`: immutable organization snapshots; typed
  policies/budgets/ledger/coverage, refs từ context digest+record key. Không parser cue.
- Create `reconciliation/admission.py`: pure `admit_evidence(...) -> AssessmentInput`.
- Create `workflow/evidence_assessment.py`: assemble from current DB/read-set/context,
  gọi admission + existing Reconciler; CaseWorkflow vẫn sở hữu atomic commit.
- Modify existing shared `service.py/snapshots.py/schema.sql/jobs.py`, commands,
  API DTO/view, evaluation loader/runner/scorer và frontend typed confirmation/basis.
  Không refactor cả service chỉ vì số dòng lớn; seam mới theo trách nhiệm admission.

Signatures cần giữ giữa tasks:

```text
persist_context(cx, context:OrganizationContext, origin:str) -> str  # digest
load_context(cx, tenant:str, activity:str, as_of:datetime) -> OrganizationContext
admit_evidence(report:ReadResult, *, scope:CaseScope,
  organization:OrganizationContext, confirmations:tuple[Confirmation,...],
  ledger:tuple[MoneyEvent,...], coverage:CoverageRecord|None,
  read_set:ReadSet, as_of:datetime) -> AssessmentInput
build_evidence_assessment_input(cx, *, tenant:str, root_id:str,
  report:ReadResult, as_of:datetime) -> AssessmentInput
```

`context_snapshots(tenant,digest,version,payload_json,origin,imported_at)` là additive
migration mới, payload immutable; giữ relational activity/grant/people projection
để các command hiện có kiểm quyền. Không overwriting old snapshot. Budget/authorization
actor/grant/effect_range/refs từ payload, không lấy employee:approver hard-coded.

## A0 — Freeze admission/basis and repair contract drift

**Files:** domain/finance.py, domain/case.py, domain/commands.py,
evidence/document_profiles.py, IMPLEMENTATION_CONTRACTS.md refinement;
tests/unit/test_admission_contracts.py.

**Produces:** payment basis enum/actor and per-expense paid-claim DTO.
Define `EmployeePaidClaim(invoice_reference:str, amount:Vnd, refs:tuple[EvidenceRef,...],
reason:str)` in commands.py; no actor/verifier/state from client.
`Submit.employee_paid_claims:tuple[EmployeePaidClaim,...]=()`.
Server derives actor/scope/time; fixture `employee-confirmation.json` is authoring input
mapped to this DTO after uploaded SourceRefs resolve by filename+digest.

- [ ] Write RED: bool/float money rejected; client actor/verifier/known fields rejected;
  Q32 basis retained as employee declaration, not INDEPENDENT_PAYMENT; `amount_words`
  critical; compatibility constructors STUB explicitly UNSPECIFIED_LEGACY.
- [ ] Run `rtk proxy uv run --no-sync pytest tests/unit/test_admission_contracts.py`;
  observe intended failures before modifying code.
- [ ] Implement DTO/refinement above; no financial action yet. Add conditional
  admission issues/problems to AssessmentInput; preserve existing strict DTO behavior.
- [ ] Update `_case_view` to derive PaymentBasisView from current admitted expenses
  and persist the same tuple on the conclusion. Future frontend field names are
  `payment_basis[].kind/actor/refs/rule_id`, not a generic confidence label.
- [ ] GREEN same command; record source/type contracts and update assigned checkbox.

## A1 — Import and load complete scoped organization context

**Files:** new domain/organization.py + workflow/context_records.py;
evaluation/models.py alias, service importer, schema.sql/db additive migration;
tests/integration/test_organization_context_records.py.

**Consumes:** current context JSON including pilot ledger/coverage/policies.
**Produces:** persist_context/load_context signatures above; full metadata survives restart.

- [ ] RED: import pilot→restart→ledger amount A and coverage/opening/funds/as_of preserved;
  policy/budget end/actor/grant retained; context without coverage does not imply P/R0;
  wrong tenant/activity/grant rejected; older snapshot retained after version update.
- [ ] Run focused tests and observe failure from fields currently dropped.
- [ ] Persist validated payload/digest/version atomically with relational projections,
  import log/audit; validate record IDs/types/party/scope/witness keys and grant semantics.
  Make EvidenceRefs use actual context digest/record quote, not fake PDF page.
- [ ] Merge context ledger with actual-money events scoped by tenant+employee+activity.
  Deduplicate same external key; conflicting copies remain FACT, no doubled A.
  Context import cannot edit existing confirmed actual event/reversal history.
- [ ] GREEN focused tests; migration checked against an old DB, no delete/reset required.

## A2 — Accept responsible Q32 claims through real command boundary

**Files:** domain/commands.py, service Submit/Revise/Answer handlers, API routes/views;
tests/integration/test_employee_paid_claims.py.

**Consumes:** EmployeePaidClaim and server session; references to uploaded bytes.
**Produces:** scoped Confirmation records with actor/observed_at/source binding.

- [ ] RED: employee own scope can confirm own invoice; another employee/client role
  cannot; digest stale/ref not root rejected; repeated command id idempotent; case
  version stale yields conflict without partial write. Submit with complete claim
  creates no fake FACT card merely to collect the same confirmation again.
- [ ] Run focused RED; extend Submit/API typed payload, resolve file refs to SourceRef
  and derive actor/scope/time server-side. Keep revisions/confirmations auditable.
- [ ] AnswerIssue updates only the fact key/basis addressed, preserving dependencies.
  Do not use generic `expense:payer` to pay every invoice in a multi-row root.
- [ ] GREEN focused tests; tests mutate amount/source after confirmation and require recheck.

## A3 — Pure evidence admission, without a second policy engine

**Files:** new reconciliation/admission.py; domain/case.py;
tests/unit/test_evidence_admission.py.

**Consumes/Produces:** `admit_evidence` signature above → AssessmentInput.

- [ ] RED: pilot clear fields+ctx+claim yields separate Expense records with source refs;
  missing/unreadable/conflict money stays UNKNOWN; invoice signature/payment wording
  alone never creates ExpensePayment or A/P/R. Missing coverage stays unknown.
- [ ] RED: empty/unknown-only report or unclassified material source never implies
  T=E=0; `expense_set_complete=false` preserves UNKNOWN totals even with no parsed
  Expense rows. Known personal-only exclusion retains gross source amount/refs but
  verified business T/E0; missing expense must not follow the personal-exclusion path.
- [ ] RED: covered_as_of10/10 does not prove zero flows at a later14/10 decision;
  initial pilot runs under10/10 controlled clock; refreshed responsible context
  restores valid zero facts without changing historical coverage/source bytes.
- [ ] RED: 10.260.000 with employee-only claim gives FACT paid-basis before recognition
  AUTHORITY; known personal cost excluded but A retained; company-direct preserves
  source/C and UNSUPPORTED affected scope, no vendor-payment instruction.
- [ ] RED: invoice+bank+acceptance supports one expense, no doubled total; allocations
  bounded by source; exact-ref1.0/LLM_RESOLVED link cannot waive cost/payer/activity
  conflicts. Wrong buyer identity is binding FACT, no blanket tax-law rule.
- [ ] Run focused RED, implement pure mapper. Admit service occurrence and activity link
  from source+compatible responsible context; source state FOUND is necessary but not
  sufficient. Canonical cost identity uses issuer/document identity, not amount/date/hash
  alone. Missing identity requires scoped confirmation; no fabricated bank txn key.
- [ ] For Q32, create ExpensePayment with declaration basis/actor and confirmation key
  (labelled confirmation identity, not a bank transaction). Only inside both8/4 with
  service evidence and no material conflict. Unknown S cannot be treated as within4;
  ask for missing money facts before accepting the bounded path.
- [ ] Preserve every unresolved/material row/source in snapshot; build owner-specific
  admission issues with known values/excerpts/dependencies. READ_ERROR/LIMIT is a
  ProcessingProblem, not an accountant business question.
- [ ] GREEN focused tests; assert no mutation of ReadResult/raw artifacts and no model calls.

## A4 — Reconciler honors admitted basis, issues and policy conditions

**Files:** reconciliation/service.py, finance.py, policy.py;
tests/unit/test_admitted_finance.py + existing finance/policy tests.

**Consumes:** Admission AssessmentInput, existing pure policy/grants.
**Produces:** AssessmentResult; allowed_effect None while gates unresolved.

- [ ] RED literal pilot: F01 S=-760000/COLLECT760000; F02 S=400000/PAY400000;
  F03 S0/BALANCED/no effect. Basis Q32 visible and no actual ledger event invented.
- [ ] RED boundaries E8m/8m+1, abs(S)4m/4m+1, approver20m/20m+1, budget/time/scope
  mismatch. FACT dependencies precede authority where needed; known facts do not
  create duplicate questions. Small S does not waive E recognition authority.
- [ ] Run RED. Merge admission issues/problems into existing policy result; unresolved
  material conditions suppress effects/affirmative conclusion. Keep partial facts,
  not a partial financial approval. Compute integer VND with no float/default0.
- [ ] Per-expense basis/refs/actor survive projection and conclusion. A/P/R and zero
  claims derive scoped ledger/coverage, not printed/declaration totals. No policy caps
  or deadline copied from Hoangha; live config uses accepted rulebook.
- [ ] Pass `expense_set_complete` explicitly to project_finance; if false, T/E and
  affected S remain UNKNOWN, not sum(empty)=0. Legacy default compatibility is only
  for explicitly tagged STUB/test snapshots whose builder/factory sets True; every typed LIVE/REPLAY admission sets
  completeness from validated rows/material-source coverage. Test the empty-set trap.
- [ ] GREEN focused + existing finance/policy tests; STUB compatibility remains clearly simulated.

## A5 — Wire the consumer with atomic version/Stop protection

**Files:** new workflow/evidence_assessment.py, snapshots.py, service.py,
evidence_jobs.py, controls.py as required; tests/integration/test_evidence_finance_workflow.py.

**Consumes:** build_evidence_assessment_input signature and existing Reconciler.
**Produces:** real LIVE/REPLAY financial branch after all prior gates pass.

- [ ] RED: submit enqueues/reads without provider I/O in SQLite transaction; after report
  published and data valid, pilots reach exact states/effects. Missing report/admission
  not implemented still EVIDENCE_READY, never seeded transcription in LIVE/REPLAY.
- [ ] RED: Stop or input/context/ledger/usage epoch change during read/confirm prevents
  stale commit; Resume recomputes current basis; replay Submit/Answer/Decide no duplicate
  instruction, existing OPEN/UNKNOWN execution retained as unknown.
- [ ] Run RED. Build snapshot from current organization payload/ledger/confirmations and
  stored report. Use **real** ReadSet counters, not constants1/0 from STUB builder.
- [ ] Change `_assess_and_commit` only to dispatch the fully wired typed consumer;
  never just remove the early-return. Same consumer covers Submit/Answer/Decide/Resume/
  RecordActual. Recheck captured input/control/context/ledger/usage before commit and
  reserve economic usage with eligibility/issue atomically.
- [ ] GREEN integration; context updates invalidate affected cost/money basis; unknown
  source relevance blocks affected conclusion until responsibly quarantined.

## A6 — Actual execution, coverage changes and loop closure

**Files:** service RecordActual/MarkExecution, instructions.py, snapshots.py;
tests/integration/test_pilot_money_execution.py.

- [ ] RED: initial instruction is not money received. F01 completed return760000 makes
  R760000/S0; F02 completed reimbursement400000 makes P400000/S0. F03 never issues zero.
  Pending/failed/wrong payee/wrong kind/scope don't settle. Repeat key doesn't double count.
- [ ] RED: partials, reversal, overpay and OPEN/UNKNOWN execution preserve gross actuals/
  incidents and don't silently close or reissue; source/authority changes invalidate
  pending remainder while retaining history and old execution state.
- [ ] Run RED, bind responsible money confirmation+source to the original instruction;
  real timestamp/verifier server-derived. Validate event against updated coverage/as_of;
  do not mutate historical coverage quote or keep old known-zero after a new flow.
- [ ] GREEN focused + existing actual-money/controls tests; read audit records for actor,
  amount, source refs, reason, basis and effect. App still does not transfer bank money.

## A7 — Packet loading, scoring and baseline-test cleanup

**Files:** evaluation/packets.py, runner.py, scorer.py/suites.py;
tests/integration/test_uc03_pilot_workflow.py; legacy raw/data_publish/verify tests.

- [ ] RED: load pilot input without reading gold, submit claims with resolved refs,
  import all context; changing gold cannot change actual result. Score actual state/
  direction/amount/basis separately from expected. Report current guard outcome as
  incomplete, never a pass on future-finance gold.
- [ ] Add literal pilot allowed/evidence adapter; keep actual model confidence/blockIDs
  absent until real recording exists. Hand source checks can seed STUB tests only;
  do not fake RECORDED_REPLAY captures from gold or native text.
- [ ] Repair the11 stale baseline tests by temporary **legacy STUB fixtures** or explicit
  replacement tests for new contract; preserve their concrete money/control assertions.
  No `skip`/weakened assertion just to green suite, no restoring discarded corpus to
  repo or running old company-direct gold as accepted LIVE product behavior.
- [ ] Add development variants with FACT and known-paid AUTHORITY for Core4/Escalation5;
  routine F01/F02/F03 plus appropriate issues. Keep25 reference cases/evidence lanes
  separate; don't label3pilot as full contest coverage or independent holdout.
- [ ] Run targeted evaluation tests then `rtk proxy uv run --no-sync pytest`;
  gate all pass or report exact blockers before advance. REAL provider quality remains
  separate authorized LIVE gate with raw trace/capture and independent held-out inputs.

## A8 — UI confirmation and basis transparency; release evidence

**Files:** frontend types/api/intake/dossier and corresponding tests; API views;
docs/final/RUNBOOK.md/IMPLEMENTATION_STATUS.md, pilot checklist.

- [ ] RED UI/API: employee confirms paid invoices without entering backend actor IDs;
  accountant execution follows actual instruction; approver only sees required decisions.
  Q32 shows “Lời xác nhận của nhân viên”, not bank-confirmed; unknown/history/cash
  distinctions remain clear. Runtime server owns role/grant/version/command checks.
- [ ] Implement typed confirmation submit/view fields without UI redesign or new framework.
  Backend issue cards carry known facts, exact source/quote, requested answer and effect;
  technical failure card separate. Update current contract labels consistently.
- [ ] Resolve Node24 and verify node + npm's own Node in the same environment; run
  package-defined component/build/browser tests. UI NOT_RUN if only components checked.
- [ ] Manually exercise F01/F02/F03 from upload through recorded completion (after A5/A6),
  then Stop/stale/duplicate and FACT/AUTHORITY follow-up. Record mode, revision, commands,
  outputs, source/model/prompt versions and limits. Do not claim LIVE when using fake.
- [ ] Update status/evidence/checklists only from results; keep public deployment/practitioner
  feedback/adaptation/holdout gaps explicit. No claims about winning the contest from
  these3case results alone.

## Self-review and execution handoff

Self-review performed by lead (no subagent per user): scope/Q32/Q34, types/signatures,
provider isolation, source/zero semantics, issue ownership, math, Stop/read-set, data
privacy, current importer gaps and all5 Review Focus rows mapped to tests. Pilot data
is generated and checked now; **A0–A8 source implementation is not executed**.

Plan uses native execution with one integrator, following the user's no-subagent
direction. Review this concrete plan before code work; if implemented, use
executing-plans and meaningful RED/GREEN gates above. Commit/push authorization is
separate. Keep unrelated working-tree changes, including app-restore test, intact.

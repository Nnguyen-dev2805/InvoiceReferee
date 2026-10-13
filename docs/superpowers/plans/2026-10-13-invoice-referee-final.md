# InvoiceReferee Final Implementation Plan

> **For agentic workers:** Follow the portable [task workflow in AGENTS.md](../../../AGENTS.md#execute-and-hand-off). Execute only the tasks authorized by the user, with their stated gates. Native/Subagent-driven skills may assist when installed; the core workflow does not require machine-local skill files. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution adapter:** Local helper instructions to continue, make rulings, commit or clean up apply only within the user-authorized scope under AGENTS.md. An accepted scope/financial-rule/authority conflict needs a concrete human decision; in-scope implementation choices remain the implementer's responsibility. A helper cannot turn T1-only or no-commit authorization into all-task or Git authorization.

**Goal:** Xây mới trên final một hệ thống quyết toán chi phí nhân viên tự hoàn tất routine có căn cứ, chuyển tiếp đúng và chứng minh được hành vi bằng UI/Verify/gold độc lập.
**Architecture:** Một FastAPI app, SQLite/local artifacts, React/Vite. EvidenceReader tạo observations; Reconciler pure kiểm dữ kiện/quyền/tiền; CaseWorkflow sở hữu commands/jobs/snapshots/transaction; EvaluationRunner cùng workflow, scorer độc lập. Một root per employee/activity, revisions thay cho budget reservation engine.
**Tech Stack:** Python3.12/FastAPI/Pydantic/httpx/SQLite/uvicorn, React/TypeScript/Vite/Node24; pypdf/pypdfium2/Pillow; Mistral OCR/xkiro HTTP, LangSmith opt-in; pytest/Vitest/Testing Library/Playwright; ReportLab/NotoSans.
**Spec:** [Q1–Q31](../../final/ARCHITECTURE_AND_EVALUATION.md), [contracts](../../final/IMPLEMENTATION_CONTRACTS.md), [disposition](../../final/reviews/2026-10-13/SYNTHESIS.md). Executor đọc spec+contracts+plan; review archive không cần nạp toàn bộ như instructions.

## Global Constraints

- Scope employee/activity/VND; travel trước, local meeting sau gate. Không restore code/context rebuild hoặc B3/B7/legacy env names.
- T incurred business cost xác minh (Q31); E eligible employee-paid; C company-direct không hoàn nhân viên; S=E−A−P+R. Missing proof không zero.
- E<=8.000.000 đ, abs(S)<=4.000.000 đ auto; approver20.000.000 đ per-action/scope/time. Không per-category cap mặc định.
- Routine tự kết luận+instruction; người execute tiền/exceptions. Không bank integration/ký số/FX/vendor refund/multi-claim allocation.
- Real received đúng scope vào phép tính dù trái quyền; incident riêng. PDF evidence units/page/quote support, không ref-id existence là đủ.
- One extra recovery/issue+job budget; stale/Stop/late không commit; command và physical transaction idempotency khác nhau.
- >=15 development travel roots; holdout20(10routine/10human); Core4/Escalation5(3auto/2human) cùng workflow.
- Gold latent/observable/allowed riêng; expected không vào app/model. Unsupported affirmative S0 vẫn dangerous miss.
- Verified real feedback khác simulated; insufficient support giữ fixed. >=3 actual practitioners mới claim Sprint2/impact.
- Public no-signup/server personas/session isolation; LIVE/RECORDED_REPLAY/STUB explicit; thiếu key không AI thật giả.
- Không code/install/LIVE/publish/Git trong planning turn. Commit steps chỉ khi execution/Git đã được ủy quyền, exact task paths, no squash/force-push.
- Exact package locks; pilot ceilings của lead được versioned theo M0, không measured guarantees.
- Contracts §10 khóa obligation coverage/state/jobs/paired evaluation sau review; không dùng shorthand cũ để chọn hành vi khác.
- UI chính dùng tiếng Việt: người/hoạt động/số tiền/việc cần làm/căn cứ. Enum/run/epoch/model ở Debug. Nhân viên nộp/trả lời, kế toán xác minh/thực hiện, người có quyền quyết định đúng issue; không chung một form hành động cho ba vai trò.
- Một workflow integrator (agent triển khai chính do người dùng chọn lúc handoff) sở hữu và tuần tự hợp nhất workflow/{db.py,schema.sql,service.py,jobs.py,snapshots.py,money.py,controls.py} và domain/{commands.py,case.py}. Agents T2/T5/T6/T7/T8 không chỉnh đồng thời các shared files trên nhánh merge độc lập; gửi change set theo task gate. Dispatch ghi owner thực tế và exact paths. Reviewers đọc độc lập; không trở thành người triển khai chính của phần mình review.

## Review Focus

1. Corporate personal charge material có thể tạo obligation ngoài công thức: không bỏ rồi S0; proven unrelated không blanket-block — T3/T5.
2. PDF hidden OCR text khác ảnh/mixed roles: không blind native/whole-file role — T5.
3. Partial/reversal/overpay/cancel: actual khác fulfillment, no duplicate remainder/release actual T — T7/T8.
4. Human draft correction/manager exception: assisted final không che initial error — T9/T11.
5. Expiry sau valid issue: thời điểm đúng, fulfill không re-approve routine; explicit revocation suspend — T3/T8.

---

## File Map

Tạo tệp khi task cần, không empty framework/services. Python paths sau đều dưới
src/invoice_referee/; frontend feature paths dưới frontend/src/features/.
Trong một hàng, tên file rút gọn là sibling của thư mục đầu tiên: ví dụ domain/
evidence.py và workflow/schema.sql, không phải src/invoice_referee/evidence.py.
Paths bắt đầu frontend/, tests/, scripts/, assets/, data/, docs/ hoặc tên file
root không nhận prefix Python. Khi thực hiện, ghi đầy đủ paths trong checkpoint.

| Group | Exact paths | Responsibility |
| --- | --- | --- |
| Foundation | pyproject.toml, uv.lock, .python-version, .node-version, .env.example, .gitignore; __init__.py, config.py, cli.py | Named config/entry/locks |
| Domain | domain/common.py, evidence.py, finance.py, policy.py, case.py, issues.py, commands.py | Strict DTO/contracts |
| Reconciliation | reconciliation/admissibility.py, finance.py, policy.py, service.py | Pure predicates/projection/rights/assessment |
| Workflow | workflow/db.py, schema.sql, snapshots.py, service.py, jobs.py, money.py, controls.py | Transactions/commands/jobs/actual/audit |
| Evidence | evidence/pdf.py, reader.py, mistral.py, xkiro.py, replay.py, planning.py, trace.py | Bounded adapters/read-only proposals/cache |
| HTTP | api/app.py, routes.py, views.py | Delegates commands, no SQL/math duplication |
| Frontend | frontend/package.json, package-lock.json, vite.config.ts, tsconfig.json, playwright.config.ts; frontend/src/App.tsx, api.ts, types.ts, styles.css; features/intake.tsx,dossier.tsx,questions.tsx,execution.tsx,approval.tsx,verify.tsx | Three role workspaces |
| Eval/adaptation | evaluation/models.py,packets.py,scorer.py,runner.py,reports.py; adaptation/models.py,policy.py,feedback.py,calibration.py | Isolated app runs/gold scoring/update |
| Data/scripts | data/demo/company-context.json; data/evaluation/{development,calibration,validation,holdout}/manifest.json; scripts/build_packets.py,dev.py; assets/fonts/NotoSans-Regular.ttf,OFL.txt | Raw/input/gold/portable generator |
| Tests/docs/deploy | tests/factories.py,unit/,integration/; frontend/tests/,frontend/e2e/; docs/final/{RUNBOOK,USER_TRIAL_PROTOCOL,RELEASE_EVIDENCE}.md; Dockerfile,compose.yaml | Proof/repro/release |

CaseWorkflow.execute/view and Reader/Reconciler interfaces use contracts §9.
Domain doesn't import SQL/LLM/UI. Focused helpers stay inside logical Module,
not generic repository/DI/event bus. Append fixture helper methods only to
tests/factories.py; LIVE never imports test helpers.

## Sequence

T1→T2→T3→T4→T5→T6→T7→T8→T9→T10→T11→T12→T13.
T4 authoring continues alongside T5, but baseline requires complete matrix.
Participant protocol/preparation starts T2, not after all code. UI from T2;
T3/T5/T6/T7/T8/T9 have browser checkpoints. M0 before baseline; public pilot T10
before adaptation. Travel15 required before profile gate T13.

### T1 — Strict domain and test context

**Files:** Create foundation/domain group, tests/factories.py, tests/unit/test_contracts.py.
**Interfaces:** DTO contracts §2/§9; snapshot(T,E,C,A,P,R,B,coverage=True,**overrides)->AssessmentInput, unit-only literal evidence.
- [ ] Write test_money_rejects_bool_float_and_currency, test_unknown_has_no_value, test_ref_needs_digest_locator, test_extra_fields_rejected.
```python
def test_money_rejects_bool_float_and_currency():
    for value in (True, 1.25, "USD 3"):
        with pytest.raises(ValidationError):
            KnownAmount(value=value, currency="VND")
```
  KnownAmount in domain/common.py is strict known VND; unknown uses Fact.
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_contracts.py -q`; missing module/required validation before body, environment error isn't valid RED.
- [ ] Implement DTO/config; pydantic-settings .env, explicit missing settings. .env.example MISTRAL_API_KEY/MISTRAL_OCR_MODEL/XKIRO_API_KEY/XKIRO_BASE_URL/INVOICE_REFEREE_LLM_MODEL blank, no generated company grants.
- [ ] GREEN same tests, uv lock compatible Python3.12. Commit checkpoint "feat: define final domain contracts".
**Gate:** Strict types, no expected/oracle fields accepted by application.

### T2 — Canonical root, demo server and first UI

**Files:** Create workflow/db.py,schema.sql,service.py; api/app.py,routes.py,views.py; frontend foundation/intake/dossier; scripts/dev.py; data/demo/company-context.json; docs/final/USER_TRIAL_PROTOCOL.md; tests/integration/test_root_session.py; frontend/e2e/intake.spec.ts.
**Consumes:** T1 CaseCommand/CommandContext/CaseView.
**Produces:** create_app(workflow:CaseWorkflow)->FastAPI; execute(CreateDraft/AttachSources/ReviseDeclaration)->CommandResult; view(ctx,id)->CaseView; frontend request<T>(path,body,commandId,version)->Promise<T>.
- [ ] Tests root unique, concurrent create, client role cannot grant, tenantB no view/reset tenantA, source bad media/size clear error no financial mutation.
```python
async def test_same_activity_has_one_root(app_fixture):
    a = await app_fixture.create(employee="employee:a", activity="activity:travel-a")
    b = await app_fixture.create(employee="employee:a", activity="activity:travel-a")
    assert a.case_view.id == b.case_view.id
```
- [ ] RED: `rtk proxy uv run pytest tests/integration/test_root_session.py -q`.
- [ ] Implement SQLite WAL/DB unique, HttpOnly demo cookie/persona switch audit. API /api/demo/session,/api/demo/persona,/api/cases,/api/cases/{id},/api/cases/{id}/sources. User sees names/activity/date, no employee/operator/work ID entry.
- [ ] Activity catalog/server-generated proposed IDs theo contracts §10.4: same activity trả cùng root; hai activity có hai roots. Draft mới không tự cấp B/quyền; Decide đúng quyền hoặc synthetic context import có audit. Client tự gửi role/B không thành authority.
- [ ] Committed observable seed: travel B8, system8/4, approver20 per-action, ledger/opening/coverage witness refs. No E/S/forced outcome from gold. Missing-context activity doesn't auto zero. Doc metadata/data_origin SIMULATED, not true corporate auth.
- [ ] Protocol/blank private study sheets: user recruits >=3 practitioners; matched manual/app tasks and order, whole human effort/draft/wait/onboarding/adverse effect, real written feedback/consent. Agent doesn't send/invent participants.
- [ ] GREEN tests + `rtk proxy npm --prefix frontend run build`. UI `rtk proxy uv run python scripts/dev.py --mode stub`: select/create twice/attach/list sources; accessible labels/keyboard/screenshot and mode/config diagnostics.
- [ ] Before npm/build/browser commands, resolve Node24 and verify `node --version` plus `npm --loglevel=verbose --version` show Node24 in the same scoped environment; record the exact selector/lockfile/command/exit. A green Node26 build does not satisfy the runtime pin.
- [ ] Commit checkpoint "feat: add canonical demo intake".
**Gate:** UI available, tenant/version/source checks; trial owner/preparation explicit.

### T3 — Admissibility, finance and policy core

**Files:** Create reconciliation group; tests/unit/test_admissibility.py,test_finance.py,test_policy.py; modify api/views.py/dossier.
**Consumes:** AssessmentInput and unit literals.
**Produces:** Reconciler.assess(input)->AssessmentResult; confirm_admissibility(observation,unit,context)->Fact; project_finance(expenses,ledger,coverage)->Projection; evaluate_policy(input,projection)->tuple[BusinessIssue,...].
- [ ] Tests T10/E5/C3/unpaid2/B8 POLICY; personal E excluded but A2 debt2; material corporate personal charge unsupported/no finalS0; guest≠payer; missing opening/fund coverage unknown; grants wrong action/time; E12/A11/B14 AUTH; E8/S4 inclusive and +1đ.
```python
def test_incurred_budget_not_paid_budget():
    r = Reconciler().assess(snapshot(T=10_000_000,E=5_000_000,C=3_000_000,A=2_000_000,P=0,R=0,B=8_000_000))
    assert r.projection.T.value == 10_000_000
    assert any(i.kind == "POLICY" for i in r.issues)
    assert r.allowed_effect is None
```
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_admissibility.py tests/unit/test_finance.py tests/unit/test_policy.py -q`.
- [ ] Implement source predicates/coverage, E/T/S and independent governance incident, grant20 per action, policy expense-time/current commit authority, scoped exception. Unknown affecting money/rights no auto; chưa phân loại A/P có căn cứ phải FACT, không tự gán tiền chuyển thành ứng.
- [ ] Prior eligibility reused only unchanged valid cost_basis. Issuer expiry doesn't erase issued decisions; explicit revocation/new action rights checked. Partial temporal budgets not covering activity need scope clarification, not latest B blind.
- [ ] Pin tests test_paid_ineligible_is_not_unpaid: T10/employee paid7/E5/C3 ⇒ unpaid0; business-incurred excluded E vẫn giữ T. test_new_paid_portion_requires_total_authority: E8→E9 ⇒ AUTHORITY; E8+P1 không đổi eligibility basis. CaseView.problems và SettlementConclusion theo contracts §10.2–3.
- [ ] GREEN unit suite. Kiểm component dossier bằng literal view fixture trong frontend/tests/dossier.test.tsx: known/unknown/rule/effect hiển thị tiếng Việt. Đây là component test; UI qua workflow thực được kiểm ở T5/T6, không tạo endpoint giả assessment trong production.
- [ ] Commit checkpoint "feat: reconcile evidence money and authority".
**Gate:** Literal oracle independent; approval can't resolve missing fact.

### T4 — Raw packets and gold before model baseline

**Files:** scripts/build_packets.py, fonts/licenses, data/evaluation/development,holdout; evaluation/models.py,packets.py; tests/unit/test_packet_inventory.py.
**Interfaces:** load_input(dir:Path)->PacketInput; load_gold(dir:Path)->GoldPacket scorer-only; validate_inventory(manifest:Path)->InventoryReport.
- [ ] Tests input excludes gold; root/economic/source clone overlap fail trước model selection. Pin grouping axes family/template/layout/issuer có lý do theo contracts §11; shared font/A4 không là leakage. Family overlap phải group hoặc disclosure within-family, không claim unseen-family. Travel15/holdout10+10, filenames không leak latent, embedded Vietnamese font/page refs.
```python
def test_packet_input_excludes_gold(tmp_path):
    p = load_input(write_test_packet(tmp_path))
    assert "latent" not in p.model_dump() and "expected" not in p.model_dump()
```
  write_test_packet in tests/factories.py creates input/separate literal gold.
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_packet_inventory.py -q`.
- [ ] Generate PDFs ReportLab+NotoSans; render scans pypdfium2. Mask/low-contrast source drawings then image-only PDF strips hidden numeric text. No seed truth in image metadata/filename; visually adjudicate observable gold, not generator claim of readability.
- [ ] Travel15: cleanCHI/THU/BALANCE, payer unknown, relation conflict, overB, cost/action authority, missing history/opening, duplicate, personal, material unsupported, pending bank, mixed PDF, amount conflict, supplementary costs. Independent roots/sources; mutations don't count15.
- [ ] Freeze holdout20 roots: routine10 varied source/money; human10 main strata FACT4/POLICY3/AUTHORITY3 with co-occurrence/stages documented. Don't force single label; actor/context/gold before run.
- [ ] GREEN inventory + native extract/render/manual check with PDF skill when creating actual artifacts. Store fonts/license once, no host font dependency; source provenance/data synthetic. Commit "test: add independent raw evaluation packets".
**Gate:** Actual files/input/context/gold3 layers, not15 table rows. Baseline waits complete matrix.

### T5 — LIVE EvidenceReader, readonly proposals and M0

**Files:** src/invoice_referee/evidence/{pdf.py,reader.py,mistral.py,xkiro.py,replay.py,planning.py,trace.py}; src/invoice_referee/workflow/jobs.py; src/invoice_referee/api/{routes.py,views.py}; tests/unit/test_provider_contracts.py; tests/integration/test_reader_source_support.py; frontend/e2e/source-preview.spec.ts. Shared workflow/API edits qua integrator theo Global Constraints.
**Consumes:** Current root sources/fields and RunBudget.
**Produces:** async read(...)->ReadResult; propose_step(Opportunity,RunBudget)->AllowedStep; CLI m0 --input --output.
- [ ] Tests mixed PDF units REQUEST/PAYMENT/RECEIVED, hidden text450/image480 conflict, false page/ref/tool grant reject, image/PDF payload, auxiliary nested usage no finance schema error, partial timeout NOT_READ not MISSING, bounded parsing.
```python
async def test_model_cannot_record_money(reader_fixture):
    s = await reader_fixture.propose(model_action="RECORD_ACTUAL")
    assert s.rejected and reader_fixture.money_side_effects == []
```
  HTTP mocks/read-only dependency, no expected financial outputs.
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_provider_contracts.py tests/integration/test_reader_source_support.py -q`.
- [ ] Implement native pypdf/preview PDFium bounded helper, scan/hybrid Mistral HTTP correct payload, xkiro validation/truncation/error branch. Source instructions aren't prompts/permissions. STUB hand-transcriptions vs RECORDED_REPLAY real read outputs tagged.
- [ ] Preview persistent job no financial effect; employee can submit unknown. Source/config/requested-fields cache reuse, new refs correct tenant, upstream/cached count explicit.
- [ ] GREEN offline; at authorized execution run M0 4 text/clear scan/unclear/non-doc raw packets with finite ceilings before calls, actual available OCR version/baseline xkiro model; compare one available candidate same dev/protocol.
- [ ] Record .runtime/evidence/m0 manifest/read_recordings/config: all attempts/errors/refs/source support/usage/time. Effective alias unresolved disclosed. Version technical caps from measurements before bulk eval/publicfreeze. evidence/trace.py có adapter LangSmith opt-in: spans đọc/trích/đối chiếu/recovery gắn run/basis/prompt/model; lọc payload trước gửi, audit local không phụ thuộc telemetry.
- [ ] UI scan -> source/draft/correction(original stays)/unknown/error next action. Commit "feat: read evidence with bounded live providers".
**Gate:** M0 genuinely run, no usable model remains reported technical gap.

### T6 — Routine submission and actionable human path

**Files:** src/invoice_referee/workflow/{service.py,snapshots.py,jobs.py,db.py,schema.sql}; src/invoice_referee/api/{routes.py,views.py}; frontend/src/features/{questions.tsx,approval.tsx,dossier.tsx}; tests/integration/test_submit_handoff.py; frontend/e2e/routine-and-fact.spec.ts. Integrator sở hữu transaction/schema boundary.
**Consumes:** Reader/Reconciler + immutable read-set.
**Produces:** execute(Submit/AnswerIssue/Decide)->CommandResult; atomic eligibility+FinancialEffect; QuestionCard.
- [ ] Tests T8/E5/C3/A2/B8 CHI3 once; missing payer card owner; incomplete funds noS0; stale/wrongowner/unproved approval no resolve; future B doesn't cover past without effect scope.
```python
async def test_routine_issues_one_payment(app_fixture):
    v = await app_fixture.submit_packet("travel-clean", mode="STUB")
    assert len(v.instructions) == 1 and v.instructions[0].amount == 3_000_000
    assert v.state == "READY_TO_EXECUTE"
```
  Packet name selects input for test only, never app decision.
- [ ] RED: `rtk proxy uv run pytest tests/integration/test_submit_handoff.py -q`.
- [ ] Implement admission/snapshot process, stable issue IDs, one useful permitted recovery or ask; no source/no permission doesn't loop model; guard budget across attempts. Tests preview→submit/resume cùng basis không reset counters; recovery key theo field/relation/source, không tên issue do model đặt.
- [ ] Job submit_requested/READING→ASSESSING theo contracts §10.4. test_submit_while_preview_running delayed read→Submit→release: một final assessment, cùng cached reads/counters; Stop/restart giữa phases không lost submit/late financial commit.
- [ ] test_existing_instruction_covers_obligation: E6/A2⇒I4; retry/new command giữ I4; P2⇒same remaining2; closed execution rồi E+2⇒supersede old remainder, new I4 duy nhất actionable. test_same_invoice_two_roots_same_tenant dùng ảnh/PDF X ở hai activities trong shared DB: không issue hai lần; chưa đủ identity ⇒ FACT. Atomic usage/conclusion/instruction cùng transaction.
- [ ] test_same_amount_changed_basis: I4 basisX→verified replacement expenseY, S4 vẫn giữ; NOT_STARTED⇒supersedeX/newY duy nhất, OPEN/UNKNOWN⇒suspend/no replacement. test_same_root_semantic_duplicate: cùng economic invoice và cùng paid portion qua scan/PDF ⇒T3/E3 một lần; phần mới verified khác key tăng E, không T.
- [ ] test_submit_after_preview_failure: submit_requested còn sau timeout/restart, TECHNICAL_ERROR/counters giữ đúng; không lost submit/reset quota/false BALANCED.
- [ ] Answer/compound decision exact basis/action/scope/refs; dependent FACT before amount approval, independent questions grouped/simultaneous allowed. Idempotent financial commit checks read-set/control/usage/grant.
- [ ] GREEN integration + `rtk proxy npm --prefix frontend exec playwright test e2e/routine-and-fact.spec.ts --headed`. Cleanroutine andFACT through UI; card/crop enough one answer, no accounting eligibility signoff.
- [ ] Commit "feat: complete routine and human recheck workflow".
**Gate:** Actual persisted workflow handoff, instruction≠received.

### T7 — Actual money, fulfillment and supplemental portions

**Files:** src/invoice_referee/workflow/money.py,service.py,schema.sql; src/invoice_referee/domain/commands.py,finance.py,case.py; frontend/src/features/execution.tsx; tests/integration/test_money_execution.py; frontend/e2e/execution.spec.ts. Tất cả sibling Python paths nằm trong thư mục ghi đầu mỗi group.
**Consumes:** RecordActual evidence request, server financial confirmation, ledger/instruction.
**Produces:** Actual projections/remaining/incident/audit through execute.
- [ ] Tests I4/pay2 one remainder2; different command same bank key noP4; changed payload same key conflict; pay5=>P5/fulfill4/incident1; wrongpayee notP; bankreversal notR; P5 received missinghistoric grant keepsS3; proven violation blocks new action only.
```python
async def test_actual_overpay_not_clipped(app_fixture):
    v = await app_fixture.record_received(instruction_amount=4_000_000, received=5_000_000)
    assert v.actual_money.P.value == 5_000_000
    assert v.instructions[0].fulfilled_amount == 4_000_000 and v.issues
```
- [ ] RED: `rtk proxy uv run pytest tests/integration/test_money_execution.py -q`.
- [ ] Implement append-only observed/confirmed/allocated/fulfilled, linked reversals. Client cannot set verified/origin/net effect. STOP retains actual, no auto effects; pending completion unknown. Existing I covers remaining, no I2 duplicate.
- [ ] Same invoice supplemental employee2 after incurred10/E5/C3/unpaid2 => T10/E7/C3. Keep A/P/R and usage owned canonical root; valid new payment portion allowed, no duplicate original reimbursement.
- [ ] test_reversal_reopens_net_remaining: I4→P2→reverse2 ⇒ P0/R0/remaining4; I4→P4→reverse1 ⇒ P3/remaining1, không SETTLED. Reverse A/R đúng loại, over/duplicate reversal reject. Superseded instruction không reopen song song với active successor.
- [ ] test_reversal_of_superseded_receipt: old I4 fulfilled2→supersede/new I4→reverse old P2 ⇒ currentS6, predecessor không actionable. Default grant4⇒AUTHORITY/no I6; authorized decision6 + NOT_STARTED⇒một I6; OPEN/UNKNOWN còn phải xác minh execution.
- [ ] MarkExecution OPEN trước thực hiện ngoài app; CLOSED_CONFIRMED có refs/confirmation. OPEN/UNKNOWN khi basis đổi không tự replacement. Overpay chưa làm rõ giữ incident, không tự tạo lệnh thu bù.
- [ ] GREEN + UI bank/cash evidence -> preview/confirmation -> record -> actual/remaining; knownreceived no grant≠no money. Employee settled separate from vendor fully paid.
- [ ] Commit "feat: record actual money without duplicate fulfillment".
**Gate:** Actual never erased by caps/denial, no wrongperson/duplicatefulfillment.

### T8 — Durable jobs, controls and immutable audit

**Files:** src/invoice_referee/workflow/controls.py,jobs.py,service.py,db.py,snapshots.py,schema.sql; src/invoice_referee/domain/commands.py,case.py; src/invoice_referee/api/routes.py,views.py; tests/integration/test_controls_races.py,test_restart.py; frontend/e2e/controls-audit.spec.ts.
**Produces:** execute(Control/override), persistent recovery/audit.
- [ ] Tests Stop-before-lateworker noinstruction, stale-view STOP accepted, stale answer doesn't overwrite A, crash-aftercommit duplicate result, shared ledger/context/usage versions stale, handed-off unknown resume not reissue, issuer expiry fulfill no re-approve but revoke suspend, source after settled revision retains actual.
```python
async def test_stop_wins_over_late_worker(app_fixture):
    await app_fixture.hold_reader()
    await app_fixture.stop()
    await app_fixture.release_reader()
    assert app_fixture.current_instructions() == []
```
- [ ] RED: `rtk proxy uv run pytest tests/integration/test_controls_races.py tests/integration/test_restart.py -q`.
- [ ] Atomic epoch/read-set/transitions, no provider I/O in transaction; persisted leases/retry counters,1active/root/2workers. Restart source cache, not financialeffects. Late result inactive audit only.
- [ ] Snapshot policy/grant/input by value/hash/version, oldbasis remainsafterchanges. CancelCHI4 leavesincurredT4, noactualcost release.
- [ ] test_authority_update_invalidates_read_set: snapshot B14/grant→barrier→B8/revoke import tăng context_version→worker release: không stale commit. test_command_payload_conflict: same tenant/actor/command, payload đổi amount/root ⇒409; same payload replay một historical result; tenant khác không leak.
- [ ] Override tagged DTO/API theo §9/§10.3; cancel chỉ suspend/supersede, không xóa actual. test_balanced_requires_all_gates: known E2/A2/coverage sạch ⇒ persisted BALANCED/SETTLED; unknown A không instruction vẫn WAITING; processing problem material không affirmative; unrelated source không blanket block.
- [ ] GREEN + backend restart mid-job and headed Stop/Resume/valid/deniedOverride audit actor/time/input/why/before-after.
- [ ] Commit "feat: enforce durable control and immutable audit".
**Gate:** Actual injected race/crash behavior, not just UI button labels.

### T9 — Independent scoring, baseline and Verify

**Files:** evaluation/scorer.py,runner.py,reports.py; frontend/verify.tsx; tests/unit/test_scoring.py,test_eval_visibility.py; tests/integration/test_verify.py; frontend/e2e/verify.spec.ts.
**Produces:** async run(input,mode)->ActualResult; score(actual,gold)->ScoreRow; run_suite(core|escalation|development,mode)->SuiteReport.
- [ ] Tests falseaffirmS0/noinstruction dangerous; technical isn't trueesc; human-fixed final doesn't rescue initial; wrongref/owner evenrightmoney fails; app cannot accessgold until actualresult.
- [ ] test_union_release_gate: 10 human roots/one false S0/no instruction ⇒ action-miss0, affirmative-miss1, union1, releaseFAIL; cùng root action+conclusion sai union1. test_lucky_latent_guess: blurred450/observable ambiguous, output known450 ⇒FAIL; grounded FACT card450/480 ⇒PASS.
- [ ] test_issue_stage_progression: initial payer UNKNOWN ⇒FACT enabled/AUTH dependent; verified E9 ⇒AUTHORITY enabled; final assisted grant không che initial route/card error hoặc tăng independent dossier count.
```python
def test_balanced_false_claim_is_dangerous():
    s = IndependentScorer().score(actual_affirmed_zero_without_coverage(), gold_requires_fact())
    assert s.unsafe_affirmative_conclusion == 1 and s.union_dangerous_miss == 1
```
  Literal factories, no Reconciler-generated oracle.
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_scoring.py tests/unit/test_eval_visibility.py tests/integration/test_verify.py -q`.
- [ ] Scorer dossier/issue-stage/opportunity, dependency sets/timelines, raw/draft/initial/assisted. LIVE runner input->preview->explicit employee fixture submission(no gold corrections)->decision/card->DB; no injected observations.
- [ ] Core4 three variedroutine+personal/noadvance rejection; Esc5 CHI multisource/THU/BALANCE+FACT payer/AUTH cost travel. POLICY/unsupported/technical separate. Core sequential, Esc2independent scenarios concurrent, intentionalshared scenario internallyserialized.
- [ ] Core case4 phải có persisted expense EXCLUDED/reason/rule/refs (personal, A=P=R0 verified), không lấy S0 hoặc tên case để gọi REJECT. Legitimate balanced khác case refusal. Ba card-only browser scenarios FACT/POLICY/AUTHORITY: đủ field/rule/amount/action/scope/impact/excerpt, một response hợp lệ xử lý issue đó; wrong owner/grant không resolve. POLICY không thêm vào Esc5 để phá 3+2.
- [ ] GREEN; `rtk proxy uv run invoice-referee evaluate --suite development --mode live --output .runtime/evidence/baseline` with configuredsource/credentials, keep failures. UI modes/times/expectedactual/refs/DB, newraw withorgctx and missingctx paths.
- [ ] Headed Verify + actualhosting walltime targetCore120/Esc90 measured, no testfake latency. Commit "feat: verify the real workflow with independent gold".
**Gate:** Raw baseline before improvements, truthful modes/errors.

### T10 — Clean clone and early public pilot

**Files:** Dockerfile,compose.yaml,docs/final/RUNBOOK.md; config/cli/dev/UI; tests/integration/test_config_storage.py; frontend/e2e/public-smoke.spec.ts.
**Produces:** oneentry `rtk proxy uv run python scripts/dev.py --mode live`, singleprocesscontainer/staticUI/persistentvolume.
- [ ] Tests missingkey/model/context diagnostics nofake; pathsindependentcwd; sessions/Verify/reset isolation; LangSmith failure nofinancialchange; boundedparserLIMIT.
- [ ] RED: `rtk proxy uv run pytest tests/integration/test_config_storage.py -q`.
- [ ] Implement prerequisite/lockedinstall/runbook, launcher/health/redactedversions, staticfrontendFastAPI. Ignore .runtime/private/uploads/DB/secrets, commit syntheticfixtures/config/fonts.
- [ ] Fresh tempclone snapshot, installlocked/startSTUB thenLIVE explicit. Verify dependencies shippednotignoredlocal; volume persists restart, scopedTTL/reset.
- [ ] Deploy lên hosting đã được cung cấp/ủy quyền nếu có; nếu thiếu thì bàn giao image/runbook và hỏi đúng thông tin hạ tầng còn thiếu. Kiểm trên browser sạch: thao tác chính tìm được trong <1 phút; Core/Esc/2 input mới/control/audit. Không dùng localhost để claim public URL.
- [ ] Chạy pilot đầu với practitioners do người dùng mời; áp protocol T2 và lưu feedback pending/căn cứ thực. Thu nhãn đủ điều kiện cho T11 từ hồ sơ calibration/validation riêng, không lấy holdout. T12 tổng hợp before/after trên phiên bản đã khóa; không chờ T12 mới bắt đầu tìm người.
- [ ] Author/freeze calibration10 và validation10 raw/context/gold theo T4 packet schema trước chọn threshold; group split với development/holdout và map feedback→initial opportunity. 20 clicks/4 roots không đủ20. Người nội bộ xác minh thật có origin riêng; không giả thành practitioners.
- [ ] Commit "build: make the public pilot reproducible".
**Gate:** Publicruntime/cleancloneproof, not localhostscreenshot claim.

### T11 — Verified feedback and paired adaptive threshold

**Files:** adaptationgroup; evalmodels/runner/reports; tests/unit/test_feedback.py,test_calibration.py; tests/integration/test_adaptive_guard.py.
**Consumes:** Frozen opportunityinitialreadset/available sources, independentgold, verifiedfeedback.
**Produces:** choose_action(opportunity,version)->AllowedStep; adjudicate_feedback(feedback,record)->VerifiedFeedback; select_threshold(calibration,grid)->ThresholdVersion; validate_candidate(candidate,validation)->ActivationResult; activate(accepted)->None.
- [ ] Tests click/exception/unverified/automationnotrealfeedback; newsource afterhuman notinitialR; insufficientN/noflip/criticalerror noactivate; beneficialextraread canincreasecalls bounded; correctionsnottruthrewrite.
```python
def test_candidate_with_false_balance_never_activates(paired_validation):
    r = validate_candidate(candidate_threshold(.5), paired_validation.with_unsafe_conclusion())
    assert r.activate is False
```
- [ ] RED: `rtk proxy uv run pytest tests/unit/test_feedback.py tests/unit/test_calibration.py tests/integration/test_adaptive_guard.py -q`.
- [ ] Fixed observable score/grid/threshold0.75 contracts§7, stableissues. Publicfeedbackpending; realorigin/verifiernotclientspoof. Human coordinator verifies private provenance; dataSYNTHETIC and humanfeedbackorigin distinct.
- [ ] choose_action deterministic theo contracts §10.5: eligible step set đã freeze, max score, tie costs/stable identity, comparator >=; tests equality/multi-step/tie/quota exhausted. Conflicting450/480 sau R vẫn FACT, không nâng quality bằng score.
- [ ] PairedH/R sameinitialsnapshot,sandbox; Hcard nofakehumanresolution, Ronepermittedread; scoreindependent. Frozenlive recordings forpolicy-only comparison, stochastic/livevariance disclosed. Cal10roots/Val10separate,4buckets/recovered+irrecoverable/flips,gatesnoholdout.
- [ ] OpportunitySnapshot còn counters/remaining deadline/recovery-key/config; test_exhausted_preview_cannot_recover_in_pair giữ R ineligible real/replay; H-added source không lọt vào initial R. test_unchanged_route_noise_cannot_activate: một flip vô ích + gain do unchanged-route provider noise ⇒reject. Candidate phải có ≥1 changed H→R an toàn/source-supported/gain thật; resource saving đơn thuần không thay gain.
- [ ] test_opportunity_gain_not_dossier_completion: một root hai issues, R giải FACT/POLICY còn manager ⇒ beneficial1/avoided_cards1/additional_auto_completion0/distinct_roots1. test_pair_missing_recording: UNOBSERVED R không pass proof/gain; muốn chấm cần actual bounded LIVE read giữ response/refs/calls/config. Báo opportunity/card/root units riêng theo contracts §11.
- [ ] GREEN; simulatedmechanism separate labelednamespace. Realverifiedsupport passes=>automaticactivation/version; absent=>fixed/unmetSprint2 evidence. Criticalguardfailure inchangedroutes=>rollbackaudit.
- [ ] Commit "feat: adapt escalation with verified paired evidence".
**Gate:** Real changedrouting/validsupport, not just calls; no fictionalpractitioner evidence.

### T12 — Frozen final test and practitioner pilot

**Files:** docs/final/RELEASE_EVIDENCE.md, USER_TRIAL_PROTOCOL.md; ignoredprivate/results; tests/unit/test_holdout_freeze.py.
**Produces:** Frozenconfig/prompt/model/datasetmanifest, holdoutreport, realprivate trials/publicredactedsummary.
- [ ] Test root/invoice/familycross-split contamination and digest/access-to-tune invalidatesindependence. RED/GREEN `rtk proxy uv run pytest tests/unit/test_holdout_freeze.py -q`.
- [ ] Lock config rồi một lần `rtk proxy uv run invoice-referee evaluate --suite holdout --mode live --output .runtime/evidence/holdout`; target dangerous union0/10 human-required + unnecessary0/10 routine, đúng tiền/refs/owner/conclusion/action. Báo action-miss và affirmative-miss riêng, technical failures trong all-submissions. Giữ attempts/errors/N; fix bằng holdout ⇒ chuyển thành dev, tập mới mới được claim độc lập.
- [ ] User recruits3 actual practitioners/consent. Matchedmanual/app/counterbalanced tasks, card-onlyactor rubric. Measureeveryactor hands-on/elapsed/machine/wait/draft/context/rework/onboarding/overreliance/interrupts, actualwrittenquotes private, no PIIpublish withoutpermission.
- [ ] Atleastone scopedchangefromfeedback/version/commit/adverseeffect andbeforafter. Recheckrelevantdev/regression, not repeatedknownholdout asnew.
- [ ] Commit "docs: record measured evidence and limitations" onlyredactedpublicassets. Missingparticipants/unverifiedfeedback remainsunmet, not guessed.
**Gate:** Evidenceonactualversion/mode/users, no zerorisk/universalROI.

### T13 — Conditional local meeting and final contest handoff

**Files:** Extendprofile/context/packets/API/UI asneeded; tests/integration/test_local_meeting.py; frontend/e2e/local-meeting.spec.ts; RUNBOOK/RELEASE_EVIDENCE; submission5slides/video/buildlog.
**Consumes:** Travelgates/sharedinvariants.
**Produces:** LOCAL_MEETING enabled afterraw/gold/routine/FACT/POLICY/AUTHORITY andtravelregression.
- [ ] Tests purpose/date/groupdecl+verifiedpaid0.7/noadvanceproof=>CHI0.7; noitinerary/customerregistry/perheadcap; missingpurposeFACT; overBPOLICY; travelonlygrantAUTH; sameexpensecrossprofile no doublepay.
- [ ] RED/GREEN `rtk proxy uv run pytest tests/integration/test_local_meeting.py -q`; serverflag onlyafterrawLIVE/roleUI/testsgate, notlabelrename. Extraindependentdata/splits ordisclosetravel-onlyholdout.
- [ ] Freshreviewer fiveReviewFocus cases+Core/Esc/2unseenraw/control/audit; no unsupportedaffirm/refusal oncriticalunknown.
- [ ] Contestpreflight actualround/eligibility/publichistoryfromuser; no assumeexcluded/deadlineextended. Exactly5slides,<=3minvideo,1pagelog,4casetable/runbook/publichistory; real/synthetic andpractitioner/Sprint2gaps clear.
- [ ] Finaltests/build/UI/rawresults/digests/limits/cleanclone/secretscheck; onlyauthorizedcommit/publish, no squash/forcepush.
**Gate:** Unverifiedprofile remainsroadmap, no fullrequirementsclaim beforeproof.

## Self-review của người viết plan

- Coverage: spec§1–4/Q31→T1–T4/T6/T7/T13; architectureAI§5→T2/T5/T6; controls§6→T7/T8;
  feedback§7→T2/T11; eval§8/9→T4/T5/T9/T11/T12; setup/contest§10/11→T2/T10/T12/T13.
- Step scan: concretepaths/commands/signatures/numericassertions; no currentPASS. Actualmodel/version/hosting discovery is a workstep, not undisclosedproductchoice.
- Types: execute/view/read/assess/run/score matchcontracts§9; input vs gold andasync vs pure separate.
- FiveReviewFocus mapped to namedbehavioral tests. Implementationbodies delegated; logicalModules stayfew; not41features from41findings.
- Independentreview occurs afterthis self-review; in-scopefix verified/challenged, scope/right changes askuser.

## Execution handoff

Plan checks are not runtime proof. Before implementation, the user reviews the
plan and selects Native (one integrator implements, independent final review) or
Subagent-driven (isolated task workers, independent task/final reviews), within
the authorized task range. [AGENTS.md](../../../AGENTS.md#execute-and-hand-off)
defines the portable process; installed local execution skills are optional helpers
subject to the adapter above. Keep milestone review at T3/T7/T8/T9/T11 regardless
of method. No application implementation occurred in the planning/setup turns.

# InvoiceReferee Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nối lõi vào workflow submit → facts → decision → human response → payment request, có Stop/Override và UI sử dụng được.

**Architecture:** Một CaseService cho API/Verify, một thread executor, persisted guards trong Repository. React chỉ hiển thị workflow và gửi human actions; evaluators thuộc Python. T06–T10 nối trực tiếp public contracts trong master.

**Tech Stack:** Python/FastAPI, SQLite/stdlb threading; React/TypeScript/Vite, Vitest/Testing Library; native controls/CSS.

**Spec:** [Master/contracts/global constraints](2026-10-04-invoice-referee.md), [Core](2026-10-04-invoice-referee-01-core.md), [Product](../../specs/B1_PRODUCT_SPEC.md), [Rulebook](../../specs/B1_RULEBOOK.md), [System](../../specs/B1_SYSTEM_SPEC.md), [Evaluation](../../specs/B1_EVALUATION_SPEC.md).

## Global Constraints

Toàn bộ master constraints áp dụng. Một active run/process; Stop acknowledgement persisted trước reply; late output không tạo request. Human input/approval/override khi busy trả RUN_BUSY. Không trả trạng thái đã chi tiền, không auto fallback fake/live, không xác thực doanh nghiệp hay workflow engine.

---

## T06 — Production pipeline và vertical slice

**Dependencies:** T03/T04/T05. **Files create:** `src/invoice_referee/application/{__init__,pipeline}.py`, `tests/integration/test_pipeline.py`. **Interfaces:** Consumes `Providers`, `evaluate`, `derive_fact`, snapshot/bundle và checkpoint/writer; produces `preflight(snapshot) -> Decision|None`, `process(snapshot, providers, checkpoint, artifact_writer) -> PipelineResult`. Không insert payment request trong pipeline; Repository.finalize_run là writer ở T08. Capture phần Providers.identities phát sinh trong run vào PipelineResult.identities; finalize lưu cùng RunRecord, kể cả repair identities.

- [ ] **1. RED preflight no-provider và refusal khác technical.**

```python
from invoice_referee.application.pipeline import process
from invoice_referee.extraction.providers import FakeProviders
from tests.builders import routine_snapshot

def test_missing_primary_does_not_call_provider(tmp_path):
    snapshot = routine_snapshot().model_copy(update={'evidence': []})
    providers = FakeProviders(documents={}, registries={})
    result = process(snapshot, providers, lambda stage: None,
                     lambda name, data: tmp_path/name)
    assert result.decision.action == 'REQUEST_INFO'
    assert result.decision.issues[0].owner_mode == 'EMPLOYEE'
    assert providers.calls == []
```

Writer chưa được gọi trong missing-primary preflight; provider `.calls` từ T05. Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_pipeline.py -q`; expectedRED import/missing function.

- [ ] **2. Preflight và per-document evidence path.** Config chưa active/version thiếu tạo technical NONE. Payer hoặc purpose đã đủ căn cứ từ chối thì REJECT; thiếu primary tạo SRC-01, không gọi providers. Nhiều primary/multi-bill cần tách hoặc làm rõ, không chọn file đầu. Các hồ sơ còn lại xử lý evidence cần thiết, lưu raw OCR/model/parsed/registry. Context file không tự trở thành goods receipt.

```python
def guarded_call(checkpoint, stage, call):
    checkpoint(f'{stage}:before')
    value = call()
    checkpoint(f'{stage}:after')
    return value
```

`process` đi qua OCR → registry → AnalyzeDocument → contract validation → normalization/derived quality → artifacts. Kiểm checkpoint trước/sau từng SDK call, trước áp dụng facts, trước evaluate và trước trả result. Raw output muộn có thể lưu diagnostic với stopped identity; không áp dụng effective facts/business action. Empty OCR/missing scores tạo factual blockers; malformed structure/invalid output là technical. Transport/contract errors trả NONE với technical_code; StoppedRun phải tới executor để thành STOPPED. Không dùng employee prose điền invoice facts.

Required evidence phải xử lý đầy đủ; provided CONTEXT cũng được phân tích cho facts/conflicts liên quan payer/purpose khi có, với required-field hints riêng. Không bắt context file có total/items như bill, nhưng không bỏ qua một nguồn đã nộp chứa mâu thuẫn company-paid chỉ vì profile không có inventory. Required/optional applicability vẫn do code/rulebook, không do model tự miễn check.

Sau nhận document kind/currency, nhận diện FX/credit/refund scope trước khi áp dụng purchase numeric/arithmetic gates; không biến unsupported signed document thành normal purchase bằng cách đổi dấu. Human confirmation có thể xác nhận value từ ảnh gốc khác raw OCR: giữ raw OCR/ref gốc, ghi corrected value+reason/normalization riêng; không yêu cầu sửa OCR cho khớp để vượt validator.

- [ ] **3. Cross-source theo profile, rồi pure decision.** WORK_PURCHASE chỉ đối chiếu khi required facts của primary/formal receipt usable. Tên chuẩn hóa khớp duy nhất một-một có thể mapping bằng code; ngữ nghĩa chưa rõ dùng cross_source với facts+refs. Code kiểm IDs, full coverage, units và conflicts. Thiếu receipt hoặc quality chưa đủ vẫn chạy các checks độc lập; không dùng cross call để bù dữ kiện thiếu. Inventory N/A ở TRAVEL/MEAL vẫn phải qua eligibility/amount/authority. B1 chưa cache providers; reevaluation giữ stage identities và gọi lại. Reuse sau benchmark chỉ hợp lệ khi full request hash trùng.

```python
from invoice_referee.policy.decision import evaluate

# Sau các source/normalization gates và confirmations hợp lệ đã áp dụng:
decision = evaluate(snapshot, bundle)
```

Snippet dùng snapshot/bundle trong process. Record provider calls, repairs, durations, prompt/schema/model identities cùng run. Production và prompts không nhận expected labels hay testcase names.

- [ ] **4. GREEN vertical slice và profiles.** Kiểm routine 1,2m→CREATE; thiếu primary→REQUEST_INFO; 2.000.001→ESCALATE approver; company-paid/personal purpose→REJECT không gọi providers; inactive config/timeout/invalid schema→technical NONE. WORK_PURCHASE phải chạy inventory, numeric uncertain hỏi REVIEWER, payer conflict tạo MODE-02. Chạy command bước 1, expected PASS. Đây là fake-pipeline evidence, chưa chứng minh live quality.

T06 tạo `docs/PRODUCT.md` và `docs/ARCHITECTURE.md` với actual pipeline/wiring/provider mode/limitations; controls chưa có vẫn PLANNED. T08 cập nhật human/executor semantics và tạo `docs/TESTING.md` chứa commands/test scope, fake-vs-live evidence boundaries. Current-state docs không chép toàn bộ target architecture trước khi source đã nối.

## T07 — Human action validation, closure và input revision

**Dependencies:** T06. **Files create:** `src/invoice_referee/application/human.py`, `tests/unit/test_human_actions.py`. **Modify:** `src/invoice_referee/storage/repository.py` bổ sung apply_human_action/invalidation sau T04. **Interfaces:** `validate_human_action(action: HumanAction, snapshot: CaseSnapshot, decision: Decision) -> HumanAction`; repo chỉ áp dụng action đã được service validate. Consumes open issues/current decision và refs/bounds T02; produces version/authorization/confirmation mới, không sửa original decision. Full service closure tests thuộc writer T08.

**Payload schema chính xác** (extra keys reject):

| Kind | Payload | Mode/semantics |
| --- | --- | --- |
| SUPPLY_DECLARATION | `changes: dict` subset Claim fields | EMPLOYEE; profile classification OTHER→supported chỉ POLICY_OWNER bằng OVERRIDE classify |
| ADD_EVIDENCE | `evidence_ids: list[str]` staged backend uploads | EMPLOYEE; action endpoint multipart nhậnfiles ở T09, service resolves IDs, không arbitraryclientpath |
| PROPOSE_CORRECTION | `field, value, refs` | EMPLOYEE; proposal chưa là effective fact |
| CONFIRM_FIELD | `field, value, refs` | REVIEWER; owned resolvable refs, meaningfulreason, canonicalnormalization |
| CONFIRM_MAPPING | `pairs, refs` | REVIEWER; ownedIDs/full coverage/nonambiguous units |
| GRANT_POLICY_EXCEPTION | `amount_vnd, profile, purpose, policy_version` | POLICY_OWNER; amount+case scope, chỉ LIM01exception, không FXcapability |
| APPROVE_AMOUNT | `amount_vnd, profile, purpose, policy_version` | APPROVER <=5m; POLICY_OWNER >5m only có matchingexception |
| DENY | `issue_id` | Issueownermode; case REJECTED giữ lýdo, không delete |
| OVERRIDE | `operation, values` | operation CONFIRM_FIELD/CONFIRM_MAPPING/CLASSIFY_PROFILE/GRANT_POLICY_EXCEPTION/APPROVE_AMOUNT/DENY; kiểm underlying role/scope, record wrapper+originalrun |
| STOP | `run_id` | Dedicatedstoproute có quyền mode demo, cùng persisted guard; không đổi caseversion |

CONFIRM dùng field path `evidence_id.fields.total` hoặc `evidence_id.items.item_id.quantity`; refs serialize SourceRef. Partial allocation cần phân tách có căn cứ; B1 chưa hỗ trợ allocation tự do thì hỏi tách case, không tạo amount Override tùy ý. CLASSIFY_PROFILE chỉ OTHER→TRAVEL/CLIENT_MEAL/WORK_PURCHASE và vẫn kiểm requirements của profile mới.

- [ ] **1. RED wrong role/scope.**

```python
import pytest
from invoice_referee.application.human import validate_human_action
from invoice_referee.policy.decision import evaluate
from invoice_referee.domain.models import DomainError
from tests.builders import routine_snapshot, resolved_bundle, human_action

def test_employee_cannot_approve_amount():
    snapshot = routine_snapshot(2_000_001)
    decision = evaluate(snapshot, resolved_bundle('2000001'))
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='EMPLOYEE', payload={
        'amount_vnd': 2_000_001, 'profile': 'TRAVEL',
        'purpose': snapshot.claim.purpose, 'policy_version': snapshot.policy.version,
    })
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'
```

Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_human_actions.py -q`; expected RED thiếu validator, rồi kiểm wrong-mode guard. Không chạy service tests chưa tồn tại ở T07.

- [ ] **2. Implement discriminated payload validation, ownership và revision.** Kiểm kind/keyset/mode/reason, current case version, open issue/scope và giá trị có nguồn. Không có approve-all boolean. Employee proposal chưa là effective fact; reviewer confirmation không sửa raw OCR. Declaration/evidence/confirmed facts đổi data version; approval/exception chỉ đổi active action IDs/input hash. MVP có thể invalidate toàn bộ authorizations khi data revision thay đổi; policy change cũng phải được kiểm scope/version. Lưu original issues/decision, đóng issue qua reevaluation theo stable_key.

```python
def authorization_matches(auth, snapshot, amount: int) -> bool:
    return (
        auth.case_version == snapshot.case_version
        and auth.policy_version == snapshot.policy.version
        and auth.profile == snapshot.claim.profile
        and auth.purpose == snapshot.claim.purpose
        and auth.amount_vnd == amount
    )
```

Repository áp dụng một transaction: append action/event, cập nhật effective input/confirmation và version khi cần, revoke request bị ảnh hưởng, giữ old run. T08 chặn busy trước mutation; repo kiểm version trong transaction. ADD_EVIDENCE validate uploads và liên kết all-or-nothing. OVERRIDE tạo evaluation mới qua luồng chuẩn, không patch payment request trực tiếp.

- [ ] **3. Human sequence tests và GREEN.** TC05 reviewer xác nhận nguồn→đóng SRC-02 sau rerun; employee correction chưa có nguồn→issue còn mở; 2m+1 được approver duyệt→một HUMAN_AUTHORIZED request. 5m+1 grant exception riêng vẫn cần amount approval; dữ liệu đổi làm approval mất hiệu lực/request cũ revoked. Kiểm wrong mode/scope/ref, classify OTHER vẫn qua normal checks, DENY giữ audit. T07 kiểm validator/repository; T08 mới nghiệm thu full service closure. Chạy command bước 1, expected PASS ở scope T07; evidence phân biệt hai mức.

## T08 — One-process executor, atomic action và Stop/Override tests

**Dependencies:** T07/T04. **Files create:** `src/invoice_referee/application/{service,executor}.py`, `tests/integration/{conftest,test_execution_controls,test_human_closure}.py`. **Interfaces:** CaseService methods đúng master; consumes Repository/process/validate_human_action. `set_policy(policy)` chỉ khi idle, persist config+event qua Repository rồi cập nhật active config. Startup dùng persisted active config nếu có, otherwise file config chưa activate. `wait` phục vụ tests/CLI, UI polling; timeout không đổi execution status thành SUCCEEDED.

`tests/integration/support.py` từ T04 supplies `seed_case(repo, amount=1_200_000, profile='TRAVEL') -> tuple[CaseRecord,EvidenceBundle]`. FakeProviders nhận đúng seeded IDs. Fixture `runtime` trong conftest có `.service`, `.repo`, `.providers`, `.case_id`, `.entered`, `.release`; OCR chờ threading.Event barrier. Teardown luôn release barrier và close service kể cả test thất bại, tránh worker treo. API tests reuse fixture này.

- [ ] **1. RED persistedStop vslateprovider.**

```python
def test_acknowledged_stop_blocks_late_payment(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    reply = runtime.service.stop(run.id)
    assert reply.status == 'STOP_REQUESTED'
    assert runtime.repo.get_run(run.id).stop_requested is True
    runtime.release.set()
    ended = runtime.service.wait(run.id, timeout_seconds=5)
    assert ended.status == 'STOPPED'
    assert runtime.repo.get_payment_request(runtime.case_id) is None
    assert any(e.kind == 'STOP_REQUESTED' for e in runtime.repo.history(runtime.case_id))
```

Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_execution_controls.py -q`; expectedRED absentservice/executor; afterfixtureimplementation stops on guardfailure, notfixtureerror.

- [ ] **2. Implement service orchestration và lifetime slot.** ThreadPoolExecutor(max_workers=1) và lock chặn queue run thứ hai; SQLite connection riêng mỗi transaction. start_run chụp snapshot/policy và persist run dưới lock, trả ngay; worker process với persisted checkpoints rồi finalize transaction. StoppedRun→STOPPED, exception khác→FAILED/NONE có technical event. Chỉ giải phóng slot sau worker kết thúc. Actions/start khi busy trả RUN_BUSY; Stop persist flag/event trước acknowledgement. Startup đánh dấu run bị gián đoạn; shutdown close executor.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

executor = ThreadPoolExecutor(max_workers=1)
slot_lock = Lock()
# ponytail: one active run in one process; throughput work belongs outside this MVP.
```

Resources trong snippet thuộc từng CaseService, không global cho nhiều app instances. Checkpoint kiểm assert_run_current rồi ghi stage; final transaction vẫn là guard cuối. STOP_REQUESTED không bị rerun hủy bỏ; new run đợi worker cũ kết thúc. Public error không lộ credentials; trace chi tiết lưu diagnostics local.

`act` giữ slot lock khi validate và persist, rồi khởi động reevaluation bằng đường start dùng cùng lock; không release giữa mutation và run mới để hai requests chen vào. Trả CaseRecord có current_run_id mới để UI poll; không cần người dùng bấm thêm Run để đóng issue. DENY tạo run/decision REJECT có human reason và active action ID trong snapshot hash, không gọi providers và không gán một lỗi kinh tế bịa đặt. T07 repository-only checks và T08 full service tests được ghi riêng.

`set_policy` nhận actor_mode/reason theo master. POLICY_OWNER dùng explicit demo activation/rollback; SYSTEM chỉ đổi word_review_threshold/threshold_version của config đang active, còn activation ID/business version/limits/authority/currency giữ nguyên. Audit phân biệt automatic adaptation với human approval. API T09 truyền actor_mode=POLICY_OWNER và reason vào service khi activate; T13 truyền SYSTEM/report identity khi auto-adapt.

- [ ] **3. Add integration controls và human closure.** Dùng barriers cho hai thứ tự Stop/final commit, double click, busy mutation, delayed response, stale run, provider exception và restart. Các sequences T07 chạy qua CaseService và kiểm actual current/history request counts. Override giữ original run/decision; refusal/input mới revoke request cũ, không waive hard gates. DENY phải persist quyết định, không chỉ đổi UI badge. Slot còn busy cho đến khi release barrier; repeated Stop idempotent; completed run trả ALREADY_COMPLETED.

- [ ] **4. GREEN and gate SYS05/06/07.** Run controls+humanclosure+repository:

```bash
rtk proxy .venv/bin/python -m pytest tests/integration/test_execution_controls.py tests/integration/test_human_closure.py tests/integration/test_repository.py -q
```

Expected PASS với actual SQLite request counts. Evidence T08 ghi persisted stop flag/event/zero request và original Override history. Fake-provider tests không chứng minh provider đã hủy inference từ xa.

## T09 — FastAPI composition và contract responses

**Dependencies:** T08. **Files create:** `src/invoice_referee/api/{__init__,app}.py`, `tests/integration/test_api.py`. **Interfaces:** `create_app(service: CaseService) -> FastAPI`; không có decision logic khác. Tạo `create_runtime_app() -> FastAPI` làm factory startup `invoice_referee.api.app:create_runtime_app`; composition root tạo repo/providers/policy/service một lần. Config PROVIDER_MODE explicit fake/live; tests inject FakeProviders.

Routes (pathprefix `/api` in deployment; specpaths belowrelative): POST/GET `/cases`; POST `/cases/{id}/runs`; GET `/runs/{id}`; POST `/cases/{id}/actions`; POST `/runs/{id}/stop`; GET `/cases/{id}/history`, `/payment-request`; GET `/cases/{id}/evidence/{evidence_id}` ownedfilesonly; GET `/policy`, POST `/policy/activate` explicitdemoactivation. GET`/health` readinessmode+confignotsecret. VerifyroutesaddedT11. Case listGET/cases forfindinglocalcurrent, no tenancy.

- [ ] **1. RED validation/error and end-to-end API.**

```python
from fastapi.testclient import TestClient
from invoice_referee.api.app import create_app

def test_api_preserves_business_and_execution_status(runtime):
    client = TestClient(create_app(runtime.service))
    started = client.post(f'/api/cases/{runtime.case_id}/runs')
    assert started.status_code == 202
    runtime.release.set()
    runtime.service.wait(started.json()['id'], timeout_seconds=5)
    response = client.get(f"/api/runs/{started.json()['id']}")
    assert response.json()['status'] == 'SUCCEEDED'
    assert response.json()['result']['decision']['action'] == 'CREATE_PAYMENT_REQUEST'
```

runtime reusefixture exported `tests/integration/conftest.py` ownedT08, notcopy providers again. Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_api.py -q`; expectedRED createapp missing.

- [ ] **2. Implement DTO mapping, limits và action dispatch.** POST case multipart nhận claim_json, files và matching roles JSON list; strict Claim và storage limits, không nhận stored_path. Non-file actions dùng JSON; ADD_EVIDENCE dùng multipart action_json+files. Response theo ledger. Error envelope {code,message}: 422 invalid input/action, 404 missing, 409 busy/stale, 503 configuration/provider unavailable trước start. Nếu execution đã nhận thì failure nằm ở RunRecord FAILED/NONE. Evidence endpoint kiểm case ownership; không trả secrets/local absolute artifact paths.

```python
HTTP_CODES = {'INVALID_INPUT': 422, 'NOT_FOUND': 404, 'RUN_BUSY': 409,
              'STALE_VERSION': 409, 'INVALID_ACTION': 422,
              'CONFIG_NOT_ACTIVE': 503, 'PROVIDER_FAILED': 503,
              'INVALID_ANALYSIS': 422, 'OUT_OF_DOMAIN': 422}
```

Stop trả record thật cho requested/stopped/already-completed. Policy activation kiểm mode POLICY_OWNER/reason, dùng activate_demo_policy rồi service.set_policy khi idle; persist config và global event. Runtime ban đầu inactive, tests có fixture active riêng. GET policy hiển thị version/limits/threshold/origin là demo policy. Health phân biệt liveness/readiness và mode, không secrets. Raw diagnostics không public mặc định; business reasons/refs vẫn xem được.

- [ ] **3. GREEN và OpenAPI snapshot.** Kiểm business REQUEST_INFO khác invalid amount 422; empty form không tạo case; upload limits, busy 409, wrong role, owned evidence/404, persisted Stop và inactive config. T10 lấy types từ OpenAPI schema, lưu schema hash ở evidence T09. API tests expected PASS; Verify sẽ kiểm same-service wiring ở T11.

## T10 — React product surfaces, human forms và controls

**Dependencies:** T09; skeleton có thể sau contractfreeze nhưng integrationgate sau T09. **Files create:** `frontend/{package.json,package-lock.json,index.html,tsconfig.json,vite.config.ts}`, `frontend/src/{main.tsx,api.ts,types.ts,App.tsx,CaseForm.tsx,CaseDetail.tsx,HumanActions.tsx,VerifyPanel.tsx,styles.css}`, `frontend/src/{CaseDetail,HumanActions}.test.tsx`. **Interfaces:** UsesAPI responsesliteraltypes/recordfields master, no localdecider. `api.ts` exports `createCase(form:FormData):Promise<CaseRecord>`, `getCase(id:string):Promise<CaseRecord>`, `startRun(id:string):Promise<RunRecord>`, `getRun(id:string):Promise<RunRecord>`, `sendAction(id:string,action:HumanAction):Promise<CaseRecord>`, `stopRun(id:string):Promise<StopReply>`; `ApiError` fields code/message. `types.ts` generatedorcheckedagainstOpenAPI, notmade-upresponse.

- [ ] **1. Set up React/TS/Vite có package lock; RED rendering quan trọng.** Kiểm official package docs/Node compatibility khi execution, khóa versions. Một workspace chưa cần chart/state/router framework. Vitest+Testing Library kiểm business copy/control behavior. Props: `CaseDetail({run,onStop}:{run:RunRecord,onStop:()=>Promise<StopReply>})`; `HumanActions({caseRecord,decision,onAction}:{caseRecord:CaseRecord,decision:Decision,onAction:(action:HumanAction)=>Promise<void>})`.

```tsx
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { CaseDetail } from './CaseDetail';
import { completedRun } from './testBuilders';

it('shows request creation separately from transfer', () => {
  render(<CaseDetail run={completedRun()} onStop={vi.fn()} />);
  expect(screen.getByText('Đã tạo đề nghị chi trả')).toBeTruthy();
  expect(screen.queryByText('Đã chuyển tiền')).toBeNull();
});
```

T10 tạo `frontend/src/testBuilders.ts` với `completedRun():RunRecord`: full synthetic ledger record, decision CREATE 1,2m/ROUTINE_AUTO và execution SUCCEEDED, không gọi API để dựng expected. Chạy `rtk proxy npm --prefix frontend run test -- --run`; expected RED do component thiếu, không do test setup hỏng.

- [ ] **2. Implement form → submit → run → polling.** Native inputs cho profile/payer/purpose, amount text thay floating arithmetic. Chuyển sang JSON integer sau Number.isSafeInteger/positive validation; domain 15 digits nằm trong JS safe range. Chọn role từng file, lỗi hiển thị đúng trường. Poll 1000ms khi QUEUED/RUNNING/STOP_REQUESTED; cleanup timer khi unmount; chỉ show STOPPED khi server xác nhận. Busy disable chỉ hỗ trợ UX, backend guard quyết định. FAILED, REJECT và human issues hiển thị riêng. CSS responsive, labels/focus/keyboard/aria status.

```tsx
const canStop = run.status === 'QUEUED' || run.status === 'RUNNING';
const decision = run.result?.decision;
const needsHuman = decision?.action === 'REQUEST_INFO' || decision?.action === 'ESCALATE';
```

Snippet chỉ phục vụ display, không quyết định eligibility. Hiển thị reasons/checks, accepted amount/basis, raw/normalized facts và source links, issue class/owner/question. User flow bằng tiếng Việt, raw JSON ở Diagnostics. Công bố demo modes và version/activation; không để SDK settings trong employee form.

- [ ] **3. Human forms đúng owner/scope; Stop/Override/audit.** Employee bổ sung declaration/upload/proposal; reviewer chọn source/value/reason/mapping; approver duyệt đúng amount/purpose; policy owner có hai action exception và amount approval riêng. Override chỉ underlying operation có quyền, giữ original run và result mới. Sau sendAction, poll current_run_id mới do service tự reevaluate. Stop chờ acknowledgement, show pending cho tới STOPPED; ALREADY_COMPLETED hiển thị request thực. Reviewer xem ảnh/page trước confirmation; approval cũ không tự reuse. History/request revoked hiển thị. VerifyPanel shell chưa có simulated PASS; T11 nối runner.

- [ ] **4. GREEN test/build/manual paths.** Component tests kiểm owner controls, reason bắt buộc, pending/STOPPED, FAILED khác REJECT, approval basis và câu hỏi dữ kiện thiếu. Chạy các commands dưới đây.

```bash
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy .venv/bin/python -m pytest tests/integration/test_api.py -q
```

Expected PASS/build success. Manual browser kiểm routine 1,2m; numeric uncertain→reviewer; 2m+1→approval; 5m+1→exception rồi approval; delayed-provider Stop; Override timeline. Capture actual screens/results trong T10. Test xanh không thay evidence cho các manual paths; public deploy thuộc T15.

# B3 Trình duyệt và Quyết định tạm ứng — Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, triển khai tuần tự theo task. Chỉ phối hợp subagent khi chủ dự án yêu cầu. Checkboxes ghi bằng chứng thực, không tự commit hoặc chạy LIVE.

**Goal:** Đi được từ review kế toán hiện có đến presentation được lưu, quyết định APPROVE/RETURN/REFUSE đúng quyền và trạng thái chờ chi ứng; chưa tạo tiền thực nhận.

**Architecture:** Dùng Service/Store/SQLite và B3CompanyContext/B3Grant hiện có. Presentation lưu audit, review lưu interactions, B3 decision lưu typed JSON trong decisions; API chuyên biệt và một panel B3 mới. Giữ đường SETTLEMENT/B7 riêng, không mở generic money/handoff/closure cho B3.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite/pytest và React/TypeScript/Vite/Vitest hiện có. Không dependency mới.

**Spec:** [B3 present-and-approve design](../specs/2026-10-11-b3-present-and-approve-design.md).

**Status:** IMPLEMENTED (fake/replay, 2026-10-11); chưa nghiệm thu LIVE/UI.

## Evidence (2026-10-11)

Mode **PIPELINE_FAKE_OR_REPLAY** (fake reader + packet-literal context); không
LIVE/Git/publish. Commands/exit/count actual:

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_workflow.py -q      # 17 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_workflow_api.py -q  # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                          # 322 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                     # 742 passed
.venv/bin/python -m pip check                                                                          # No broken requirements found
npm --prefix frontend run test -- --run                                                                # 105 passed (18 files)
npm --prefix frontend run build                                                                        # tsc --noEmit + vite build OK
```

Artifacts: `src/invoice_referee/settlement/b3_workflow.py` (mới), models/service/
store/API B3 workflow, `frontend/src/settlement/B3Approval.tsx` (+ test), docs
`docs/testing/B3_APPROVAL_WALKTHROUGH.md`, `PRODUCT.md` P2a, `SYSTEM.md` S10.
Breaking expectations (source-justified): `CaseStage` thêm `ADVANCE_REQUEST_REFUSED`
(không vào `_CLOSED_STAGES`); B7 `_latest_decision_payload` chỉ đọc kind
`SETTLEMENT`; 3 test Actions.tsx cũ mô tả UI report-only được thay bằng hành vi
trình/quyết định mới.

**Chưa kiểm (honest limits):** UI walkthrough `USER_UI_UNEXECUTED` (browser chưa
thao tác trong phiên); LIVE/OCR/LLM quality PLANNED; chưa ghi tiền actual, chi
ngân hàng, handoff/closure, mở lại refusal, B3→B7.

## Global Constraints

- Nhánh initial verbal assignment; employee confirmed và current report đủ kiểm tra. Không đòi quyết định đang xin là tài liệu nhân viên phải nộp.
- Một decision có ba nội dung work/budget/advance; review note không approval; approval không receipt hoặc closure.
- Strict integer VND, limits missing không unlimited; company context/grants/route do backend cấp.
- Dùng B3Grant cho B3, không B7 AuthorityGrant/P-DEMO. Demo role không authentication.
- STOP/stale/idempotency/current basis và quyền được kiểm cùng persisted mutation; giữ source/history.
- Không bank/request/money/handoff/closure, không điều kiện approval chưa giải quyết, không reopening refusal hoặc adjustment sau approval trong slice này.
- Một writer cho shared backend contracts; không ghi đè B7 dirty work. Frontend tích hợp sau backend ổn định; không hai writer cùng App/Actions/types.
- Không đổi corpus/gold B7, không refactor schema/store toàn repo, không auth/queues/framework workflow.
- Không Git mutation/LIVE/publish. User UI tự test được; ghi chưa kiểm nếu chưa thao tác, không bypass browser denial của phiên hiện tại.

## Deliverables và file ownership

1. Models/Service/Store/API + panel trình duyệt (test được trên UI).
2. Quyết định ba nhánh + panel người duyệt/nhân viên (test được trên UI).
3. Controls/basis/authority isolation, regression và walkthrough.

Một file mới `b3_workflow.py` chứa các hàm B3 workflow đã nêu dưới đây; không
nhét lifecycle vào Reader hay dùng LLM cho quyết định/phép cộng/quyền.

## Task 1 — Lưu rà soát và trình duyệt

**Files**
- Create: `src/invoice_referee/settlement/b3_workflow.py`.
- Modify: `src/invoice_referee/settlement/models.py`, `service.py`, `store.py`.
- Modify: `src/invoice_referee/api/settlement.py`.
- Create: `frontend/src/settlement/B3Approval.tsx`, `B3Approval.test.tsx`.
- Modify: `frontend/src/settlement/types.ts`, `api.ts`, `Actions.tsx`, `App.tsx`, `uiCopy.ts` (chỉ wiring/projection B3).
- Create: `tests/settlement/test_b3_workflow.py`, `test_b3_workflow_api.py`.

**Interfaces được tạo**
- `B3PresentPayload`: basis_report_id:str; review_id:str|None=None; review:ReviewPayload|None=None. Validator yêu cầu đúng một review_id hoặc review; review.report_id bằng basis_report_id, note không trắng, refs hợp lệ.
- `B3PresentationView`: id, case_id, basis_report_id, review_id, employee_ref, work_ref, accountant_ref, approver_ref, basis_input_revision:int, basis_control_epoch:int, basis_signature:str, context_signature:str, created_at:AwareDatetime, idempotent_replay:bool=False.
- `B3WorkflowView`: status Literal[NOT_PRESENTED,PENDING,RETURNED,REFUSED,APPROVED,NEEDS_RECHECK]; presentation:B3PresentationView|None; decision:B3DecisionView|None; basis_current:bool; decision_validity:Literal[VALID,RECHECK_REQUIRED]|None; blocked_reason:str|None; accountant_ref/approver_ref:str|None.
- Khai báo `B3DecisionPayload` và `B3DecisionView` ngay Task1 để projection có kiểu đầy đủ, dù endpoint quyết định chỉ mở Task2. Payload: presentation_id:str; outcome Literal[APPROVE,RETURN,REFUSE]; reason:str; work_allowed:StrictBool|None; budget_vnd:StrictInt|None; advance_vnd:StrictInt|None. View thêm id/case_id/kind Literal[B3_ADVANCE], basis_report_id/basis_review_id/basis_input_revision/basis_control_epoch/basis_signature/context_signature, employee_ref/work_ref/actor_id/grant_ref/effective_at/created_at/idempotent_replay. Tất cả optional payload fields default None, idempotent_replay default False.
- CaseView.b3_workflow:B3WorkflowView|None=None. Pydantic forward-reference resolve trong models sau khi cả hai classes được định nghĩa; không circular import models↔b3_workflow.
- `effective_b3_time(context:B3CompanyContext)->datetime`: context.demo_clock chỉ khi activated+synthetic, còn lại server UTC. Context hash gồm version/activation/grants/route/coverage/history; audit actual time giữ riêng.
- `b3_basis_signature(submission:Submission, sources:list[SourceRecord], report:Report, policy:dict, context:B3CompanyContext)->str`: deterministic fingerprint của scope/form/revision, active source hashes, policy/context và proposal-critical values/check states. Bỏ run ID/timestamps/tokens/messages thuần copy.
- `Service.present_b3(case_id:str,payload:dict,command:Command)->B3PresentationView`.
- `Store.record_b3_presentation(case_id:str,payload:B3PresentPayload,command:Command,context:B3CompanyContext,policy:dict)->B3PresentationView`.
- `POST /api/cases/{id}/b3-presentations`: actor_id/demo_role/expected_case_version + payload fields; Idempotency-Key; response201 mới,200 replay.

- [x] **1.1 Viết fixtures/tests failing**

Fixture sau được tạo trong `test_b3_workflow.py`; copy vào API test hoặc import
fixture module test qua pytest_plugins có phạm vi tests này. Không database thật.

```python
import pytest
from invoice_referee.settlement.b3 import B3CompanyContext, B3Intake
from invoice_referee.settlement.models import Command
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM

def command(key, actor, role, version):
    return Command(key=key, actor_id=actor, demo_role=role,
                   expected_case_version=version, body={})

@pytest.fixture
def ready_b3(tmp_path):
    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    svc = Service(store, StructuredLedgerReader(store.artifact_root),
                  config=ServiceConfig(authority=[], b3_context=
                      B3CompanyContext.model_validate(CONTEXT)))
    case = svc.submit_b3("NV-DEMO-01", B3Intake.model_validate(NATIVE_FORM),
        command("create", "NV-DEMO-01", "EMPLOYEE", None))
    run = svc.start(case.id,
        command("run", "NV-DEMO-01", "EMPLOYEE", case.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    assert svc.report(run.id).completion == "COMPLETE"
    yield svc, svc.get_case(case.id), run.id

def test_present_stores_review_and_pending_atomically(ready_b3):
    svc, case, report_id = ready_b3
    result = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id,
                   "note": "Đã kiểm khai báo và dự toán", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    view = svc.get_case(case.id)
    assert view.stage == "AWAITING_DECISION"
    assert view.b3_workflow.presentation.id == result.id
    assert view.b3_workflow.status == "PENDING"
    assert view.money_summary["received_vnd"] is None
    assert not svc.closed(case.id)
```

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_workflow.py -q`; trước implement FAIL vì chưa có present_b3.

- [x] **1.2 Implement transaction và projection tối thiểu**

Reuse _write/_check_version/_lookup_command/_record_command. Operation B3_PRESENT,
audit kind B3_PRESENTED chứa typed presentation và review liên quan. Không thêm
CHECK kind cho interactions; insert REVIEW bình thường nếu review mới.

Một transaction kiểm: case B3 b3-intake-v1/open, confirmed, current run đúng
case/SUCCEEDED/revision/epoch, Report COMPLETE/readiness, không issue/câu hỏi
OPEN/ANSWERED chưa recheck, không Stop/run active; context active/current,
actor ACCOUNTANT và đúng route.accountant_ref. Review_id phải thuộc cùng
case/report/accountant, refs phải resolve nguồn/form của basis. Report của
case khác, stale review hoặc metadata route do client nhập đều bị từ chối.

Nếu review_id hợp lệ, reuse record; không tạo review khác. Nếu review mới,
lưu review cùng presentation; bất kỳ fail không có write một nửa. Lưu
AWAITING_DECISION và tăng case_version, không tăng input_revision chỉ vì trình.

Presentation pending cùng signature: same key idempotent; key mới trả record
pending cũ sau version guard, không tạo thêm. RETURN/stale cho trình mới
chỉ sau Run/review mới phù hợp. REFUSED hoặc APPROVED không nhận presentation
mới để vượt decision hiện hành. Kiểm same employee/work có decision ứng
active ở các records đã quản lý, không chỉ trong một case; không đoán cùng
work từ purpose trùng hoặc filename. Không claim dedup được ngoài dataset.

Service.get_case bổ sung b3_workflow từ records/basis; CaseSummary.stage và
detail nhất quán. Backend allowed_actions thêm B3_PRESENT khi basis đủ.
Chưa trình thì NOT_PRESENTED; không suy pending chỉ vì đã có review note.

Errors: INVALID_PAYLOAD400, BEYOND_AUTHORITY403, BASIS_MISMATCH400,
BASIS_STALE409, STOP_ACTIVE409, B3_WORKFLOW_BLOCKED409. Áp envelope hiện có.

- [x] **1.3 API tests và panel kế toán**

HTTP tests: actor employee/approver không trình; accountant sai route; draft;
report incomplete; review khác case; same-key retry; changed-body same key;
existing-review reuse; DB restart vẫn pending; pending double-key một record.

`B3ApprovalPanel` props: view:CaseView, report:Report|null, history:AuditEntry[],
role:DemoRole, actorId:string, onAction:(label:string,run:()=>Promise<unknown>)=>Promise<void>.
Types/API mirror backend; `api.presentB3(caseId,payload)->Promise<B3PresentationView>`.
Component không tự quyết quyền; role/route chỉ chọn cách render, backend
allowed_actions và error là authoritative. Với current review hợp lệ dùng
review_id; còn lại note/refs và “Lưu rà soát và trình duyệt”. Không chọn
slice(-1) mọi review; phải khớp case/report và được backend kiểm lại.

Actions.tsx mount panel chỉ B3 intake-v1 và thay đoạn report-only cũ, không
xóa branch B7. App header/summary dùng b3_workflow PENDING→“Chờ người duyệt
tạm ứng”; bỏ banner “Đủ để kế toán rà soát” sau khi trình. Render pending
readonly và người nhận; đổi role rồi vẫn thấy record sau reload.

Test React: accountant có button, employee không có; review đã lưu không
bắt nhập note lại; pending không submit lần hai; failed API giữ form và
thông báo cụ thể, không optimistic pending giả. Button disabled/in-flight
và helper reason; keyboard/label dùng native controls, styles hiện có.

- [x] **1.4 Chạy focused tests và UI checkpoint**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_workflow.py tests/settlement/test_b3_workflow_api.py tests/settlement/test_b3_api.py -q
rtk proxy npm --prefix frontend run test -- --run src/settlement/B3Approval.test.tsx src/settlement/Actions.test.tsx src/settlement/App.test.tsx
```

UI sau Task1: tạo B3 WEB fixture2triệu/forecast8, Run→kế toán trình→reload
thấy chờ duyệt; existing review ở hồ sơ người dùng cũng có thể trình nếu
basis còn current. Nếu không current phải Run/review lại, không sửa DB để bypass.

## Task 2 — Người có quyền APPROVE/RETURN/REFUSE

**Files**
- Modify: `models.py`, `b3_workflow.py`, `service.py`, `store.py`, `api/settlement.py`.
- Modify: `frontend/src/settlement/B3Approval.tsx`, `types.ts`, `api.ts`, `App.tsx`, `uiCopy.ts`.
- Test: `tests/settlement/test_b3_workflow.py`, `test_b3_workflow_api.py`; `B3Approval.test.tsx`, `App.test.tsx`.

**Interfaces**
- `B3DecisionPayload`: presentation_id:str; outcome Literal[APPROVE,RETURN,REFUSE]; reason:str; work_allowed:StrictBool|None=None; budget_vnd:StrictInt|None=None; advance_vnd:StrictInt|None=None. APPROVE requires work_allowed=true và hai tiền>0; RETURN/REFUSE yêu cầu cả ba null. Reason không trắng; không extra conditions/actor/rights.
- `B3DecisionView`: id/case_id/kind Literal[B3_ADVANCE], payload fields, basis_report_id, basis_review_id, basis_input_revision, basis_control_epoch, basis_signature, context_signature, employee_ref, work_ref, actor_id, grant_ref, effective_at, created_at, idempotent_replay. Reason/approved values bất biến; sửa là record mới có quyền, không update JSON cũ.
- `authorize_b3_decision(context:B3CompanyContext,case:CaseView,proposal:B3Proposal,payload:B3DecisionPayload,actor_id:str,demo_role:DemoRole,effective_at:datetime)->B3Grant`. Không dict do client làm nguồn quyền.
- `Service.decide_b3(case_id:str,payload:dict,command:Command)->B3DecisionView` và `Store.record_b3_decision(case_id,payload:B3DecisionPayload,command:Command,context:B3CompanyContext,policy:dict)->B3DecisionView`.
- POST /api/cases/{id}/b3-decisions có envelope hiện tại + payload;201 mới/200 replay.
- `api.decideB3(caseId,payload)->Promise<B3DecisionView>`; không gọi api.decide/SETTLEMENT.

- [x] **2.1 Viết tests failing ba outcomes**

Thêm fixture `presented_b3` dùng ready_b3 và present_b3 ở Task1; function đầy
đủ dưới đây, không helper chưa định nghĩa:

```python
@pytest.fixture
def presented_b3(ready_b3):
    svc, case, report_id = ready_b3
    presentation = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id, "note": "Đủ để trình", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    return svc, svc.get_case(case.id), presentation

def test_approve_is_not_received_money(presented_b3):
    svc, case, presentation = presented_b3
    decision = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo đề nghị và dự toán", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command("approve", "APR-DEMO-01", "APPROVER", case.case_version))
    view = svc.get_case(case.id)
    assert decision.kind == "B3_ADVANCE"
    assert view.stage == "AWAITING_MONEY"
    assert view.b3_workflow.decision.advance_vnd == 2_000_000
    assert view.money_summary["approved_vnd"] is None  # B7 summary stays separate
    assert view.money_summary["received_vnd"] is None
    assert not svc.closed(case.id)

@pytest.mark.parametrize("outcome", ["RETURN", "REFUSE"])
def test_return_refuse_do_not_create_approved_amount(presented_b3, outcome):
    svc, case, presentation = presented_b3
    decision = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": outcome,
        "reason": "Cần sửa dự toán" if outcome == "RETURN" else "Chưa cấp ứng"},
        command(outcome, "APR-DEMO-01", "APPROVER", case.case_version))
    assert decision.budget_vnd is None and decision.advance_vnd is None
    assert svc.get_case(case.id).b3_workflow.status == (
        "RETURNED" if outcome == "RETURN" else "REFUSED")
    assert not svc.closed(case.id)
```

- [x] **2.2 Implement quyền và transaction**

Transaction mới dùng operation B3_DECIDE/kind B3_DECISION_RECORDED và decision
JSON kind B3_ADVANCE. Reuse command/version/Stop guards; load presentation
của case, còn pending/current, review/report/scope đều đúng. Re-check với
current trusted context, không report từng có authority PASS là đủ.

APPROVE một grant covers allow_work/budget/advance/employee/work/time và
actor route. Required limits null hoặc actor chỉ chọn role APPROVER không
đủ. Budget≥forecast_total; advance≤request và forecast_employee; trong grant.
Khác số đề nghị cần reason. Không chỉnh form/forecast để bằng số duyệt.
RETURN/REFUSE đúng route và grant scope xét số xin; không waive numeric
unknown bằng refuse/approve. Không có grant thì403, pending vẫn giữ nguyên.

Created_at giờ thật; effective_at dùng effective_b3_time, synthetic clock
hiển thị rõ ở details. Policy/context signature đổi thì BASIS_STALE hoặc
quyền hiện tại không đủ; không merge hai grant một người để đạt cả ba quyền.

APPROVE stage AWAITING_MONEY. RETURN stage CHECKING, employee phải sửa/
confirm và Run lại; presentation cũ không còn pending, re-present mới.
REFUSE thêm CaseStage ADVANCE_REQUEST_REFUSED nhưng không _CLOSED_STAGES.
Từ chối có hiệu lực chặn revise/present bypass; ADD_SOURCE vẫn nhận và giữ
nghĩa vụ đã có, UI chỉ đọc/refusal reason. Không gọi close_case hoặc suy
work_allowed=false. Nếu phát hiện money/duties ngoài initial, giữ resolution
need; không mở financial execution trong slice này.

Pending presentation một outcome: same-key replay200; changed body cùng
key conflict; new key second decision409 B3_DECISION_EXISTS. Current approval
cùng employee/work chặn xin/trình mới như first advance; điều chỉnh/quyết
định thay thế chưa hỗ trợ. Không áp limit vào actual money vì chưa ghi money.

Sửa `_latest_decision_payload` B7 chỉ đọc kind SETTLEMENT; handoff/closure
không nhận B3_ADVANCE như final settlement. Giữ B3_REPORT_ONLY chặn generic
SETTLEMENT/record_money/handoff/closure; không xóa guard để nút approve chạy.

- [x] **2.3 UI người duyệt và nhân viên**

Summary lấy presentation basis, không latest report/review sai. Input
budget gợi ý forecast_total, advance gợi ý request; checkbox xác nhận cho
phép công việc do người duyệt chọn, không submit auto. Three buttons nhãn
Phê duyệt tạm ứng/Yêu cầu bổ sung/Từ chối đề nghị, lý do rõ. Return/refuse
không gửi approved fields. Backend errors hiển thị; không badge “APPROVER
hợp lệ” từ role picker, không frontend tự đánh giá scope/limits.

Sau approve show work đã phép, B8triệu, số xin2/số duyệt2 (hoặc1,5), “Đã duyệt
tạm ứng — chờ chi ứng”, “Thực nhận: Chưa ghi nhận”. Không show nút money0,
chi ngân hàng hoặc close. Sau return employee sửa được cùng case/work,
không tạo hồ sơ/mã công việc mới. Sau refuse readonly+reason, không âm thầm
form submit mở lại. APPROVER/ACCOUNTANT/EMPLOYEE thấy trạng thái thống nhất.

Tests UI: pending không có financial action cho accountant/employee; correct
role submit request rõ; lower advance1,5 giữ request2; unknown/invalid input
không Number('')→0; retry không double; after return edit/recheck/represent;
after refuse không present; change role refresh vẫn state từ server.

- [x] **2.4 Run focused tests + UI checkpoint**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_workflow.py tests/settlement/test_b3_workflow_api.py tests/settlement/test_decisions.py tests/settlement/test_b3_api.py -q
rtk proxy npm --prefix frontend run test -- --run src/settlement/B3Approval.test.tsx src/settlement/App.test.tsx src/settlement/Actions.test.tsx
```

UI checkapprove2, approve1,5, RETURN rồi sửa, REFUSE trên bốn fresh cases.
Không overwrite case vừa approve để test outcome khác.

## Task 3 — Basis, Stop, lịch sử và nghiệm thu

**Files**
- Modify: `b3_workflow.py`, `service.py`, `store.py` (chỉ basis/projection guards), `b3.py` (targeted prior-decision checks, không refactor extraction/intake).
- Modify: `frontend/src/settlement/B3Approval.tsx`, `App.tsx`, `uiCopy.ts` (copy/gates khi stale).
- Test: `tests/settlement/test_b3_workflow.py`, `test_b3_workflow_api.py`, `test_b3_proposal.py`, `test_controls.py`, `test_closure.py`, `test_money.py`.
- Create: `docs/testing/B3_APPROVAL_WALKTHROUGH.md`.
- Modify: `docs/settlement/PRODUCT.md`, `SYSTEM.md` (capability đúng); giữ Rulebook không tự đổi policy.

**Interfaces**
- Shared Store guard `_b3_current_basis(conn,case_id,basis_report_id,context,policy)->tuple` được dùng ở cả presentation/decision; kiểm DB current case/run và Report/RunInput snapshot trong transaction.
- `Store._b3_workflow(conn,case_id)->B3WorkflowView` đọc B3 audit/decisions;
  Service.get_case bổ sung validity theo current context. List/detail cùng
  derivation, không lấy rowid cuối cùng mọi decision làm validity proof.
- No new ledger/history source từ client: `Service.start` hợp nhất typed B3
  approval/refusal đã quản lý vào company history đúng scope với refs audit,
  không biến approved thành ADVANCE RECEIVED. Record đã xử lý trong workflow
  không tự sinh câu hỏi “approval trước chưa xử lý” để buộc duyệt lại.
- RunInput.config lưu `b3_current_decision_ref` chỉ khi Store xác minh decision
  B3_ADVANCE của chính case/scope còn đúng basis; snapshot giữ ref đó. B3 prior
  state check phân biệt đang kiểm lại chính đề nghị đã quyết với đề nghị mới:
  không tạo duplicate-approval issue cho record đã được xác minh của chính
  đề nghị. Không bỏ money history/foreign approval/refusal/contradiction; ref
  client nhập hoặc chỉ khớp tiền/ngày không được miễn check. Test own decision
  rerun và foreign decision cùng scope phải cho hành vi khác nhau.

- [x] **3.1 Regression matrix trước code**

1. Run/review/presentation khác case: không write.
2. Revision/source thêm sau trình: decision cũ rejected BASIS_STALE; old
   presentation giữ history, Run/review/present mới mới được quyết định.
3. Stop ack trước mutation/late provider: không new presentation/decision.
4. Resume đổi epoch: Run lại, pending cũ không tự current. Approval đã lưu
   chỉ valid trở lại sau recheck cùng business basis, không mặc định resume.
5. Grant hết hạn/revoke/context version đổi trước quyết định: reject dù
   report trước COMPLETE. Real data xét giờ hiện tại, không date cũ client.
6. Sau APPROVE rerun cùng basis: decision giữ history, không new approval;
   material source đổi: validity RECHECK_REQUIRED và UI nói rõ.
7. Direct form edit sau APPROVE cần adjustment riêng; không tạo request mới.
8. Refusal active không bypass bằng same-work case mới/revision; source vẫn
   retained, không xóa existing money/nguồn hoặc gọi whole-case closed.
9. Hai quyết định cạnh tranh: một persisted outcome; same-key retry một record.
10. B3 decision không làm B7 money_summary/closure/handoff hợp lệ; generic
    endpoints vẫn chặn B3. Wrong demo actor không được cấp quyền từ role.

Mỗi test assertions trên records/history/stage, không chỉ HTTP status.
Races dùng hai commands expected version giống nhau trên tmp SQLite; outcomes
phải chỉ một success, conflict409 còn lại; không cần threading infrastructure.

- [x] **3.2 Implement invalidation và derived stage**

Thêm source/revise/Stop/publish recheck các dấu current B3. Signature
business giống khi rerun không tự mất approval; pending new decision vẫn
cần presentation đúng report/revision/epoch. Source/hash/policy/context
material khác khiến RECHECK_REQUIRED, giữ giá trị approved cũ rõ “cần kiểm
lại”, không tự annul work hoặc đánh received0. Điều chỉnh approval sau
material change là capability chưa mở, không auto approve bản mới.

Company history merged từ B3 decisions cần eventref namespace b3decision:id,
effective/known times, WORK_DECISION/BUDGET_DECISION/ADVANCE_APPROVAL hoặc
REFUSED đúng content. APPROVE joint tạo nội dung có refs cùng một quyết định,
không ba quyết định mất liên kết; không money event. Không đọc RETURN như
refusal. Không filter/drop contradiction thật với external history.

Nếu current approval/history khiến proposal evaluator chưa hiểu postdecision
readiness, stage/capability projection phải nói financial state riêng và
không tạo question giả cho chính approval đã có. Không sửa dataset expected
để che integration gap; bổ sung B3 rerun test thật qua Service.

- [x] **3.3 Kiểm tổng thể và UI walkthrough**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy .venv/bin/python -m pip check
```

Ghi exit/count/mode actual. File B7 đang dirty thì tích hợp tuần tự với owner;
không reset hoặc chữa ngoài scope. Không coi tests xanh là UI đã chạy.

Walkthrough gồm commands hai terminal từ runbook hiện tại, với fake reader,
SETTLEMENT_B3_CONTEXT_PATH trỏ fixture đã activated/synthetic, DB/artifacts
riêng và backend8010/frontend5174. Không sửa file context để tăng quyền cho
happy test; giới hạn khác dùng bản sao negative fixture có provenance.

Các bước UI:
1. Employee tạo WEB proposal Hà Nội12–13/10, deadline16/10, request2, forecast
   company flight3/employee hotel3+ground1+meal1; Run đọc form/fake.
2. Accountant lưu+trình, hoặc reuse review còn current; reload thấy pending.
3. Approver xem basis và review, chọn work permission/budget8/advance2/reason,
   approve; ba vai đều thấy chờ chi, chưa actual money.
4. Cases khác: approve1,5; return rồi employee sửa/recheck/accountant trình;
   refuse và không mở lại qua form. Kiểm history từng bước.
5. Thay source/Stop trước approve phải bị chặn; pending stale hiển thị reason.
6. Kiểm generic money/handoff/closure vẫn unavailable; không chốt received0.

Hồ sơ IMPORT/LIVE hiện có có thể reuse report/review nếu current, không cần
gọi model lại chỉ để test quyết định. LIVE rerun chỉ với authorization; chưa
thao tác browser thì USER_UI_UNEXECUTED, không dùng workaround denial.

- [x] **3.4 Docs và self-review**

Product P2a bỏ mô tả toàn bộ B3 report-only chỉ khi ba tasks wired và checked;
nêu rõ mới hỗ trợ trình/decision, chưa money/hand-off/closure/B3→B7 import.
System/API routes/contracts/error codes cập nhật tương ứng. Plan ghi command
và artifact/mode/status; không ghi biến động vào AGENTS.md hoặc memory.

Đối chiếu spec từng section với test/UI evidence; scan placeholder,
case/ref namespaces, type imports và mapping stages. Không tự commit/publish.

## Acceptance

- [x] Current review reuse hoặc save+present atomic; pending survives reload/restart.
- [x] APPROVE work/B/advance đúng grant/time/scope; requested khác approved/received.
- [x] RETURN có vòng sửa/recheck/review/present; REFUSE có reason và không bypass.
- [x] Cross-case/stale/Stop/expiry/same-key/double-key/race không tạo quyết định sai.
- [x] B3_ADVANCE không lọt B7 summary/action/closure; money/handoff B3 vẫn chặn.
- [x] User nhìn thấy bước tiếp theo trên cả ba vai, không chồng banner checking/reviewed/pending.
- [x] UI execution evidence hoặc limitation rõ; không tự claim professional trial/AI LIVE quality.

## Prompt giao coding agent

“Triển khai `docs/superpowers/plans/2026-10-11-b3-present-and-approve.md` cùng spec ở đầu plan, theo ba task tuần tự. Kiểm dirty work; phối hợp owner B7 trước sửa models/service/store/API. Một writer sở hữu contracts, không reset user work. Task1 phải có UI trình duyệt, Task2 có ba outcomes, Task3 kiểm authority/basis/Stop và regression. Dùng fake providers; không tự LIVE/Git/publish. Giữ B3Grant riêng B7, không bỏ B3_REPORT_ONLY cho generic financial endpoints. Không biến review/approval thành receipt. Báo actual tests/evidence và UI chưa chạy; không sửa gold B7. Đây là slice tới chờ chi ứng, chưa triển khai ghi tiền.”

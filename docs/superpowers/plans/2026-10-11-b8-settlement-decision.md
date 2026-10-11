# B8 — Settlement Decision Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, tuần tự bốn task có tests và UI checkpoints. Một writer giữ shared contracts; không tự dispatch subagent/Git/LIVE/publish. User hiện yêu cầu viết plan, chưa yêu cầu agent tác giả plan sửa app.

**Goal:** Kế toán trình kết quả quyết toán liên kết có căn cứ; người có quyền phê duyệt toàn bộ, trả lại hoặc từ chối trên đúng basis.

**Architecture:** Dedicated linked-B7 workflow dùng models, Service/Store/API, decisions/interactions/audit hiện có. Financial target và authority bằng Python, UI chỉ hiển thị/thao tác. Generic W05 tiếp tục bị chặn trên linked B7; không xóa guard để mở toàn bộ lifecycle.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite/pytest; React/TypeScript/Vite/Vitest hiện có. Không thêm dependency, table, queue, auth hoặc workflow engine.

**Spec:** [B8 design](../specs/2026-10-11-b8-settlement-decision-design.md).

**Status:** IMPLEMENTED (fake/replay + HUMAN_SOURCE_REVIEW, 2026-10-11); chưa nghiệm thu LIVE/UI.

## Evidence (2026-10-11)

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**; không LIVE/Git/publish.
Prerequisite B6–B7 chứng minh bằng pipeline thật (`make_ready_linked`), không mock.
Commands/exit/count actual:

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py -q      # 24 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow_api.py -q  # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                          # 405 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                     # 825 passed
.venv/bin/python -m pip check                                                                          # No broken requirements found
npm --prefix frontend run test -- --run                                                                # 129 passed (22 files)
npm --prefix frontend run build                                                                        # tsc --noEmit + vite build OK
```

Artifacts: `src/invoice_referee/settlement/b7_workflow.py` (mới), models/service/
store/pipeline/API B8, `frontend/src/settlement/B7Approval.tsx` (+test),
`tests/settlement/b7_workflow_builders.py`, docs
`docs/testing/B8_SETTLEMENT_DECISION_WALKTHROUGH.md`, `PRODUCT.md`, `SYSTEM.md`.
Breaking expectations (source-justified): `CaseStage` thêm `SETTLEMENT_REQUEST_REFUSED`
+ `READY_TO_CLOSE`; `B7CompanyEvent` thêm employee_ref/work_ref/known_at; linked
context source không đưa vào Reader; linked B7 run dùng B7 rights riêng.

**Chưa kiểm (honest limits):** UI walkthrough `USER_UI_UNEXECUTED`; LIVE/OCR/LLM
quality PLANNED; chưa B9 chi/thu, handoff/closure, override ngoại lệ.

## Global Constraints

- Scope `b7-linked-intake-v1`; không đổi B3 job, không lấy B3_ADVANCE thành settlement decision.
- Routine APPROVE chỉ khi current COMPLETE report, facts/relations/coverage/source refs và route đã đủ; unknown không0.
- Client không nhập/override E/S/direction/amount/rights. Server derive từ report, one scoped B7 grant xét E và abs(S).
- Phê duyệt toàn kết quả; partial execution thuộc B9. BALANCED có decision0, không money event0.
- RETURN/REFUSE giữ nghĩa vụ tiền; không đóng, không tự thu all advance, không sửa E0.
- Quyết định/presentation immutable, currentness/Stop/version/idempotency kiểm transaction; đúng fulfillment B9 không tự làm stale approval.
- Route kế thừa phân công company B3; quyền B7 riêng. Demo role không authenticated identity.
- Unresolved policy exception giữ blocked; không mở override/auto-budget-increase trong slice này.
- Legacy W05 không được dùng làm fixture chứng minh linked guards, không refactor unrelated legacy flow.
- Fake/replay và HUMAN_SOURCE_REVIEW không chứng minh LIVE quality, ngân hàng hoặc professional-user trials.
- Không LIVE-provider spending, Git mutations, publish, bank API. UI bị tool denial ghi USER_UI_UNEXECUTED, không bypass bằng tool khác.

## Evidence map và prerequisite

Graph MCP phiên này chỉ expose CodeGraph; lần trước `codegraph_explore` đã
lỗi `(0 , directory_1.statInode) is not a function`. Không có index_status/
check_index_coverage để xác minh generation/ranges; không claim graph verified.
Map sau từ targeted current-source fallback, không whole-repo audit:

| Điểm | Source hiện có | B8 cần thay đổi |
| --- | --- | --- |
| Link/context | `settlement/b7_linked.py:build_linked_context`, `linked_context_observations` | Prove coverage/canonical history/refs; không chỉ complete flag |
| Generic authority | `Service._grant_for` đọc generic authority, employee_cost=None | Không dùng cho linked approval; use B7 config + E/net |
| Generic decision | `Store.record_decision` | Không đủ report completeness/target/review để reuse trực tiếp |
| Generic money/closure | `Store._money_summary`, `_closure_blockers` | Không mở qua guard; dedicated B9 tính scope đầy đủ |
| Current link | `Store.linked_b7_dependency_fingerprint`, `_linked_b7_view` | Kiểm parent/current context trong transaction |
| UI | `frontend/src/settlement/Actions.tsx` | Dedicated B7 panel thay generic role forms cho linked |

Đầu việc này không phải review nghiệm thu toàn B6/B7. Task1 xác minh đúng
các prerequisite dùng bởi B8; phát hiện gap thì sửa phạm vi đó trước khi mở
APPROVE, không đánh dấu COMPLETE bằng fixture/test label.

## Task 1 — Khóa financial basis và prerequisite B6–B7

**Files**
- Create: `src/invoice_referee/settlement/b7_workflow.py` (target/basis/authority helpers).
- Modify: `src/invoice_referee/settlement/models.py`, `b7_linked.py`, `pipeline.py`, `reader.py`, `service.py`, `store.py` chỉ integration/gaps của prerequisite.
- Test: new `tests/settlement/test_b7_workflow.py`, modify `test_b7_linked_context.py`, `test_b7_claim_links.py`.
- Create: `tests/settlement/b7_workflow_builders.py` (test-only literal builders, không production helper).

**Interfaces**
- `B7DecisionTarget`: frozen extra-forbid, employee_cost_vnd:StrictInt, total_work_cost_vnd:StrictInt, budget_vnd:StrictInt, signed_net_vnd:StrictInt, direction:Literal[PAY_EMPLOYEE,COLLECT_FROM_EMPLOYEE,BALANCED], amount_vnd:StrictInt.
- `settlement_target(report:Report)->B7DecisionTarget` trong b7_workflow.py.
- `b7_business_signature(submission:Submission, sources:list[SourceRecord], report:Report, policy:dict, linked_context:LinkedB7ContextSnapshot)->str`.
- `b7_cost_signature(submission:Submission, sources:list[SourceRecord], report:Report, policy:dict, linked_context:LinkedB7ContextSnapshot)->str`: scope/E/T/B/eligibility/payer/expense relations/policy và nguồn gốc cost facts; không chứa A/RA/P/RP, generated context-source ID, run ID hoặc usage. Whole business signature vẫn giữ history baseline; B9 dùng cả hai.
- `b7_configuration_signature(b7:B7CompanyConfig,b3:B3CompanyContext,policy:dict)->str`.
- `effective_b7_time(config:B7CompanyConfig)->datetime` dùng activated+synthetic demo_clock hoặc server UTC.
- Mở rộng `build_linked_context` hiện có để giữ issues/canonical identities/source support; thêm arguments `submission:Submission`, `source_records:list[SourceRecord]` tại mọi caller, không tạo validation registry. B7CompanyEvent thêm employee_ref/work_ref và known_at nullable để biểu diễn scope/time khi nguồn có; không đoán từ coverage rộng. Thiếu trường material phải đối chiếu nguồn hoặc giữ issue. known_at dùng thời điểm công ty/hệ thống thực sự biết, không client backdate tự cấp knowledge.
- Test builder `report_from_values(e,a,ra=0,p=0,rp=0,t=8_000_000,b=8_000_000)->Report` code dưới; integration builder `make_ready_linked(svc,parent,monkeypatch,*,employee_cost_vnd=5_000_000)->tuple[CaseView,Report]` phải chạy Service/pipeline thật với StructuredLedgerReader.

- [x] **1.1 Viết unit target tests đỏ**

Trong test builder, dùng literal components (không gọi target để xây expected):

```python
from datetime import datetime, timezone
from invoice_referee.settlement.models import CheckResult, ComponentSlot, Report, ReportComponents

def report_from_values(e, a, ra=0, p=0, rp=0, t=8_000_000, b=8_000_000):
    amounts = dict(t=t, b=b, e=e, a=a, ra=ra, p=p, rp=rp)
    slots = {key: ComponentSlot(value=value,
        state="UNKNOWN" if value is None else "KNOWN", refs=[f"source:{key}"])
        for key, value in amounts.items()}
    net = None if any(amounts[k] is None for k in ("e", "a", "ra", "p", "rp")) \
        else e - (a - ra) - (p - rp)
    return Report(run_id="R-unit", job="B7", mode="PIPELINE_FAKE_OR_REPLAY",
        generated_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        completion="INCOMPLETE" if net is None else "COMPLETE",
        components=ReportComponents(**slots), calculated_net_vnd=net,
        proposed_net_vnd=net,
        checks=[CheckResult(rule=rule, status="PASS", reason="Unit input: sourced check",
            refs=["source:unit"]) for rule in ("relation_status", "duplicate_events",
            "eligibility", "payer_parts", "history_coverage", "budget", "authority")],
        source_refs=["source:unit"])
```

```python
import pytest
from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b7_workflow import settlement_target
from tests.settlement.b7_workflow_builders import report_from_values

@pytest.mark.parametrize("e,expected", [
    (5_000_000, ("PAY_EMPLOYEE", 3_000_000)),
    (1_300_000, ("COLLECT_FROM_EMPLOYEE", 700_000)),
    (2_000_000, ("BALANCED", 0)),
])
def test_target_preserves_accepted_cost_before_offset(e, expected):
    target = settlement_target(report_from_values(e, 2_000_000))
    assert (target.direction, target.amount_vnd) == expected
    assert target.employee_cost_vnd == e

def test_unknown_advance_has_no_decision_target():
    with pytest.raises(DomainError) as error:
        settlement_target(report_from_values(5_000_000, None))
    assert error.value.code == "B7_WORKFLOW_BLOCKED"
```

Run:
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py -q
```
Expected đỏ trước khi module/target có; không coi collection error là assertion chứng minh quality gate.

- [x] **1.2 Implement minimal target + signatures**

Target reject job!=B7, completion!=COMPLETE, unresolved material issues,
claim CONFLICT/UNRESOLVED, required checks thiếu hoặc FAIL/UNRESOLVED, component không
KNOWN/int/source, proposed None hoặc không bằng công thức/calculated.
T/B phải đủ cho budget/authority. Không dùng first-non-null conditional net.
Direction derive bằng dấu; amount=abs(net); bound strict integers.
Required routine B7 checks là relation_status/duplicate_events/eligibility/
payer_parts/history_coverage/budget/authority; không `all([])` tự pass. Check
khác có material failure vẫn chặn; N/A cần applicability reason, không waive
required facts/quyền. Unit builder trên chỉ chấm target, không source authenticity.
Signature gồm expense rows/eligibility/payer/relations, source hashes đúng
use, component baseline, employee/work/policy/budget; không usage/run ID/note.
Không bỏ history khỏi signature: B9 revalidation sẽ phân biệt fulfillment delta.
Cost signature resolve owning original-document hash cho từng cost fact/link,
không hash toàn generated context JSON vì context đó đổi khi receipt mới đến.
Configuration signature giữ activation/version/grants/routes/policy, còn
demo_clock/cutoff được kiểm riêng: đổi mốc đối chiếu receipt không tự thành
thu hồi quyền. B9 revalidation vẫn xét thay đổi config/authority có ảnh hưởng.

- [x] **1.3 Viết integration builder và prerequisite assertions**

`make_ready_linked` dùng fixture chain **hiện có**:
`test_b3_workflow.command/ready_b3/presented_b3`, `test_b3_funding.approved_b3`,
`upload_receipt/receipt_payload`. Ghi B5 receipt2 trước, tạo child, cấu hình
B7 grant APR-DEMO-01/NV-DEMO-01/work cụ thể E/net≤8M effective10–31Oct,
synthetic clock14Oct09h+07 và đồng bộ child server clocks qua monkeypatch
`invoice_referee.settlement.store.utcnow` tại prepare.

Tạo nguồn fake **facts**, không expected S/labels: employee expense5, BUSINESS,
payment5 payer EMPLOYEE/RECEIVED, EXPENSE_PAYMENT, CLAIM_EXPENSE CL-EMP→EXP-EMP;
company flight expense3, COMPANY payer/RECEIVED với economic ref riêng. Rows
confirmed CL-EMP declared5. Company packet coverage employee/work đúng,
opening/methods/all groups/from1Oct→14Oct09h, events ADVANCE_RECEIVED2 cùng
identity B5, COMPANY_DIRECT3, không returns/reimbursement và source-backed
absence. Upload company register/receipts trong child và giữ refs mở được;
không dùng `company:fake` tự thành source. Run→wait→report từ pipeline; assert
T8/E5/A2/RA0/P0/RP0/S3/COMPLETE literal; failure phải sửa path, không mock report.

Negative variants phải assert slot/issue, không chỉ HTTP200:

| Input thay đổi | Expected |
| --- | --- |
| B5 actual2, packet bỏ receipt hoặc alias lại cùng TX | Không A0/A4; hợp nhất canonical2 nếu coverage đủ; thiếu linkage giữ issue |
| Coverage wrong employee/work/expired/missing CASH/opening/group | History liên quan UNKNOWN, no executable target |
| Event ngoài event_at/known_at cutoff hoặc payer/payee sai | Không cộng vào A/RA/P/RP; giữ raw/reason |
| PENDING/UNKNOWN advance trong scope | Không ignore thành known subtotal/0 |
| Thiếu actual company flight | Không forecast3 thành T8 |
| Declaration PERSONAL nhưng company payment | Không E lấy từ declaration; issue/đúng payer |
| Context source refs/EXPENSE_PAYMENT không resolve hoặc ID trùng | Không established/COMPLETE |
| Claimed row chưa matched, unrelated same amount | Không coi reconciled chỉ từ sum |

Resolver source-use/known-time và alias phải chạy trước evaluate. Pipeline
hiện dùng synthetic `linkedctx:{parent}`: thay bằng retained context source ID
thật của child, ghi observation locators và supporting refs mở được. Company
expense/payment matcher nhìn thấy context candidates hoặc dùng links typed
đã xác minh; không tạo arbitrary ESTABLISHED vì một string event_ref.

- [x] **1.4 Verify prerequisite**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py tests/settlement/test_b7_linked_context.py tests/settlement/test_b7_claim_links.py -q
```
UI checkpoint: đối chiếu E5/A2/S3 và nguồn thật trong child; chưa APPROVE.

## Task 2 — Lưu rà soát và trình quyết toán atomic

**Files**
- Modify: models.py, b7_workflow.py, service.py, store.py, `src/invoice_referee/api/settlement.py`.
- Test: test_b7_workflow.py; new `tests/settlement/test_b7_workflow_api.py`.

**Interfaces**
- `B7PresentPayload`: basis_report_id:str; review_id:str|None; review:ReviewPayload|None; supersedes_decision_id:str|None. Exactly one review source; nonblank note; same report.
- `B7PresentationView`: id/case_id/employee_ref/work_ref/basis_report_id/basis_review_id/accountant_ref/approver_ref:str; basis_input_revision/control_epoch:StrictInt; business_signature/parent_fingerprint/config_signature:str; target:B7DecisionTarget; created_at:AwareDatetime.
- Define shared `B7DecisionView` schema ngay task này để CaseView/Pydantic compile độc lập: id/case_id/kind Literal[B7_SETTLEMENT]; outcome Literal[APPROVE,RETURN,REFUSE]/reason; presentation_id/basis_report_id/basis_review_id; employee_ref/work_ref/actor_id; effective_at/created_at; basis_input_revision/control_epoch; business_signature/parent_fingerprint/config_signature/authority_signature; target:B7DecisionTarget|None; history_baseline:MoneyComponents|None; supersedes_decision_id:str|None. IDs/signatures là str, times AwareDatetime, revisions StrictInt. Task3 mới ghi decision.
- `B7WorkflowView`: status Literal[NOT_PRESENTED,PENDING,RETURNED,REFUSED,APPROVED,NEEDS_RECHECK]; presentation:B7PresentationView|None; decision:B7DecisionView|None defaultNone; basis_current:bool; blocked_reasons:list[str]; accountant_ref/approver_ref:str|None. CaseView.b7_workflow optional defaultNone.
- `Service.present_b7(case_id:str,payload:dict,command:Command)->B7PresentationView`.
- `Store.record_b7_presentation(case_id:str,payload:B7PresentPayload,command:Command,b7:B7CompanyConfig,b3:B3CompanyContext,policy:dict)->B7PresentationView`.
- POST `/api/cases/{id}/settlement-presentations`, same actor/version/idempotency envelope; audit operation B7_PRESENT. No new interactions kind/table.

- [x] **2.1 Tests đỏ trên ready linked fixture**
Define `ready_linked_b7(approved_b3,monkeypatch)` trong test_b7_workflow.py:
returns `(svc, child, report)` using Task1 builder. Test pattern:

```python
from tests.settlement.test_b3_workflow import command, ready_b3, presented_b3
from tests.settlement.test_b3_funding import approved_b3
from tests.settlement.b7_workflow_builders import make_ready_linked

@pytest.fixture
def ready_linked_b7(approved_b3, monkeypatch):
    svc, parent, _ = approved_b3
    child, report = make_ready_linked(svc, parent, monkeypatch)
    return svc, child, report

def test_present_is_review_and_route_not_financial_approval(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ căn cứ để trình", "refs": report.source_refs}},
        command("b7-present", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    view = svc.get_case(child.id)
    assert view.b7_workflow.presentation.id == presentation.id
    assert view.b7_workflow.status == "PENDING"
    assert view.b7_workflow.decision is None
    assert not svc.closed(child.id)
```

Negative: foreign/stale review/report, employee/other accountant, unconfirmed
draft, incomplete context, both/no review source, malformed refs, parent Stop,
signature change at commit, key conflict. No leftover REVIEW if presentation
fails; all inside one transaction. Duplicate present same current basis reuse
instead of creating multiple pending presentations. Existing current review
does not go stale solely from harmless case_version changes.

- [x] **2.2 Implement transaction path and CaseView projection**
Store re-read case/run/review/context/dependency/route inside `_write`;
service passes immutable backend config snapshot, never client grants. Use
`settlement_target` only after freshness/source checks. Audit + optional new
REVIEW + presentation + case_version/stage AWAITING_DECISION atomically.
Record protected signatures and effective config version. Same-key replay
first, historical result not promise of current validity. New action checks
still apply separately. Direct Store call must not bypass route/quality.

- [x] **2.3 API checks**
Add typed request/error mapping: 403 BEYOND_AUTHORITY; 409 B7_WORKFLOW_BLOCKED,
BASIS_STALE, ORIGIN_STOP_ACTIVE/B7_ALREADY_DECIDED; 422 INVALID_PAYLOAD/unknown fields.
Test app factory uses same Service, request actor/version/Idempotency-Key,
response201 new/200 replay; reload persistent presentation/review/source refs.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py tests/settlement/test_b7_workflow_api.py -q
```

## Task 3 — APPROVE / RETURN / REFUSE với B7 rights

**Files**
- Modify: models.py/b7_workflow.py/service.py/store.py/API; test_b7_workflow.py/test_b7_workflow_api.py.

**Interfaces**
- `B7DecisionPayload`: presentation_id:str, outcome Literal[APPROVE,RETURN,REFUSE], reason:str nonblank; extra forbid; no client amount.
- `B7DecisionView`: id/case_id/kind Literal[B7_SETTLEMENT]; outcome/reason; presentation_id/basis_report_id/basis_review_id; employee/work/actor refs; effective_at/created_at; basis_input_revision/control_epoch; business_signature/parent_fingerprint/config_signature/authority_signature; target:B7DecisionTarget|None (APPROVE only); history_baseline:MoneyComponents|None; supersedes_decision_id:str|None backend from presentation.
- `authorize_b7_decision(config:B7CompanyConfig,employee_ref:str,work_ref:str,actor_ref:str,effective_at:datetime,target:B7DecisionTarget|None)->AuthorityGrant`.
- `Service.decide_b7(case_id:str,payload:dict,command:Command)->B7DecisionView`;
  `Store.record_b7_decision(case_id:str,payload:B7DecisionPayload,command:Command,b7:B7CompanyConfig,b3:B3CompanyContext,policy:dict)->B7DecisionView`.
- POST `/api/cases/{id}/settlement-decisions`; operation B7_DECIDE; generic DECIDE stays blocked linked.

- [x] **3.1 Tests đỏ phê duyệt không thực nhận**
Use Task2 ready fixture and present call; then:

```python
decision = svc.decide_b7(child.id, {
    "presentation_id": presentation.id, "outcome": "APPROVE", "reason": "Duyệt theo kết quả đã rà soát"},
    command("b7-approve", "APR-DEMO-01", "APPROVER", svc.get_case(child.id).case_version))
assert decision.kind == "B7_SETTLEMENT"
assert decision.target.employee_cost_vnd == 5_000_000
assert decision.target.signed_net_vnd == 3_000_000
assert decision.target.amount_vnd == 3_000_000
assert not svc.closed(child.id)
```
Snippet đặt trong test sau setup Task2; không gửi client target. Add collection/
BALANCED tests literal và assert money_events không có record do APPROVE.
Authority E4/net10 reject E5/net3; B3 grants/generic P-DEMO cannot substitute;
actor correct role but wrong route/scoped work/time reject; two partial grants
cannot combine; client overrides422. Return/refuse target/historybaselineNone
và A2 vẫn giữ trong sources/context; no closure/no collection action.

- [x] **3.2 Implement target and scoped single grant checks**
APPROVE uses covering_grant với E/net/T đầy đủ, current effective time, actor
filter/B7 config activated và route. Policy unresolved vẫn blocked, không
passing exception_of string. RETURN/REFUSE needs scoped effective actor grant,
không financial acceptance. Revalidate at transaction read/commit; idempotent
same-key result trước version; new key same presentation409; supersede chỉ
RETURN/REFUSE reopening đã nêu, reason+fresh report/current review.
Stages APPROVE nonzero→AWAITING_MONEY; BALANCED→READY_TO_CLOSE (extend CaseStage
và UI copy); RETURN→CHECKING; REFUSE→SETTLEMENT_REQUEST_REFUSED (không closed).
Projection exposes currentness/reasons; no generic MoneySummary from new kind.

- [x] **3.3 Regression kiểm bypass và stale windows**
Use two Store instances/SQLite writers và barrier trước commit; source mới,
parent funding/Stop, policy/config route/grant switch invalidates relevant
action; no decision persisted on reject. Config ở startup immutable; tests
simulate replacement/restart, không thêm hot-reload service/framework.
Re-run cùng business facts không tạo second entitlement; đang chờ B9 vẫn giữ
decision record, không dùng current_run_id alone phủ nhận history.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py tests/settlement/test_b7_workflow_api.py tests/settlement/test_b7_linked.py -q
```

## Task 4 — UI theo vai, checkpoint và bàn giao sang B9

**Files**
- Create: `frontend/src/settlement/B7Approval.tsx`, `B7Approval.test.tsx`.
- Modify: `frontend/src/settlement/types.ts`, `api.ts`, `Actions.tsx`, `App.tsx`, `uiCopy.ts` và stylesheet đang dùng chỉ styles mới cần thiết.
- Docs after implementation: `docs/settlement/PRODUCT.md`, `SYSTEM.md`; new `docs/testing/B8_SETTLEMENT_DECISION_WALKTHROUGH.md`.

**Interfaces**
- TS mirror typed B7PresentPayload/B7DecisionPayload/Workflow/Target/Decision.
- api `presentB7(caseId,payload)`, `decideB7(caseId,payload)` nhận existing command envelope.
- `B7ApprovalPanel({view,onChanged,onError})` theo prop callback pattern B3Approval;
  uses backend b7_workflow + allowed_actions, not UI-calculated net/rights.
- AllowedAction literals thêm PRESENT_B7/DECIDE_B7 nếu chưa có; reasons từ cùng guards.

- [x] **4.1 UI tests trước component**
ACCOUNTANT thấy review/trình, không form quyết định; APPROVER thấy current
presentation/summary/readonly target và ba outcomes; EMPLOYEE thấy tiến độ/lý
do, không financial controls. Show E5/ứng2/chi thêm3; COLLECTION wording công
ty nhận; BALANCED không “đã chi0”. Stale/Stop/missing rights disable với reason.
Double click in-flight chặn locally, API idempotency vẫn là authority.
RETURN nhập reason→state; APPROVE không hiển thị actual đã nhận, không nút close B8.

- [x] **4.2 Wire dedicated panel**
Linked B7 không render generic W05 decision/money/closure widgets. Accountants
reuse current review by id hoặc submit review+presentation một lần, không
checkbox phải mở mọi source. Run IDs/revision/epoch/raw JSON để details.
Invalidate fetch/refetch on accepted action; stale409 tải state mới, không
silent retry financial POST với key mới. Render effective grant scope chỉ
để giải thích, không cho edit. Header “Chờ duyệt / Đã duyệt — chờ chi/thu /
Yêu cầu làm rõ / Từ chối đề nghị” riêng report completion.

Phần summary chỉ render target do backend cấp; ví dụ trong B7Approval.tsx
(import B7DecisionTarget từ types.ts), không tự derive amount từ net:

```tsx
function B7DecisionSummary({ target }: { target: B7DecisionTarget | null }) {
  if (!target) return <p>Chưa có quyết định phê duyệt.</p>;
  const money = new Intl.NumberFormat('vi-VN').format(target.amount_vnd);
  const label = {
    PAY_EMPLOYEE: 'Số tiền công ty cần trả thêm',
    COLLECT_FROM_EMPLOYEE: 'Số tiền nhân viên cần hoàn lại',
    BALANCED: 'Quyết toán cân bằng — không cần chi hoặc thu',
  }[target.direction];
  return <p>{label}{target.direction === 'BALANCED' ? '' : `: ${money} đ`}</p>;
}
```

- [x] **4.3 Verify và manual UI checkpoint**
```bash
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy .venv/bin/python -m pip check
```
Walkthrough ghi exact synthetic sources, persona/role, report5/2/+3, present,
approve, reload, return/refuse separate fresh scopes, negative authority,
BALANCED. Chụp/read UI nếu quyền có; nếu không USER_UI_UNEXECUTED. Chỉ khi fresh
commands có output mới ghi VERIFIED mode/count/exit; worker report không tự nghiệm thu.

## B8 → B9 contract

B9 dùng immutable B7DecisionView.target/history_baseline/signatures, không
generic latest SETTLEMENT. Không mở chi/thu nếu B8 tests chưa đạt. B9 không sửa
accepted E để khớp actual; correct receipts đối chiếu fulfillment riêng.
No B9 action trong checkpoint chỉ triển khai B8. User đã yêu cầu cả hai plan;
coding agent được giao cả hai có thể tiếp [B9 plan](2026-10-11-b9-settlement-fulfillment.md)
sau acceptance B8, không cần hỏi permission lại cho local implementation đã giao.

## Acceptance coverage map

| Design | Plan |
| --- | --- |
| §1/§2 typed path và prerequisites | Task1; generic bypass regression Task3 |
| §3 review/presentation/outcomes | Task2–3 |
| §4 E/net/grant/BALANCED/partial prohibition | Task1+Task3 |
| §5 versions/currentness/idempotency/Stop | Task2–3; B9 revalidation contract |
| §6 role UI/copy | Task4 |
| §7 evidence limits và acceptance | Mỗi task; final checks Task4.3 |

## Prompt giao coding agent

```text
Đọc AGENTS.md và thực hiện docs/superpowers/plans/2026-10-11-b8-settlement-decision.md
cùng spec liên kết, tuần tự task1–4. Chỉ đọc sections canonical được chỉ định.
Trước khi mở APPROVE phải chứng minh/sửa prerequisite B6–B7 coverage/canonical
history/source refs bằng pipeline fake thực, không mock COMPLETE/gold để pass.
Dùng dedicated linked-B7 routes/Store guards, quyền B7 xét E và abs(S), target
server-derived, presentation đúng current review. RETURN/REFUSE không xóa nghĩa vụ.
Làm UI theo ba vai cùng backend; kiểm fake/API/regression/build và UI nếu tool
được phép. Không LIVE, không Git/publish, không bank/enterprise infrastructure.
Ghi evidence actual commands/exit/count/mode và các phần UI/LIVE chưa kiểm.
Nếu được giao cả B9 thì sau B8 acceptance tiếp plan B9; không mở generic guard
để shortcut. Không claim end-to-end nghiệp vụ đã hoàn tất từ green unit suite.
```

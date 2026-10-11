# B5 Advance Receipt — Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, từng task có tests và UI checkpoint. Chỉ dùng subagent khi chủ dự án yêu cầu. Không tự Git/LIVE/publish.

**Goal:** Kế toán lưu chứng từ/sự kiện tiền ứng có căn cứ, chương trình đối chiếu actual với B3 decision và giữ pending/unknown/incidents; đủ ứng mới chờ quyết toán.

**Architecture:** Reuse Service/Store/sources/money_events/audit. Adapter nghiệp vụ `b3_funding.py` tách advance khỏi B7 reimbursement. Route proof upload riêng tránh làm stale approval chỉ do bổ sung fulfillment; người đọc nguồn xác nhận fields, không LLM quyết tiền thực nhận.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite/pytest và React/TypeScript/Vitest/Vite hiện có; không dependency mới.

**Spec:** [B5 advance receipts](../specs/2026-10-11-b5-advance-receipts-design.md).

**Status:** PLANNED — các methods/models/routes/tests bên dưới chưa triển khai ở lượt viết plan.

## Global Constraints

- Approval không receipt; unknown không0; bank request/debit/Paid generic không receiver outcome.
- Tiền strict integer VND; actual gross không clip xuống số duyệt. Sai recipient/overpaid giữ raw và incident.
- HUMAN_SOURCE_REVIEW là xác nhận đọc có nguồn của kế toán, không bank authentication/OCR/LLM quality claim.
- Không chuyển tiền, retry bank, tự thu hồi, scheduler, B7 case tự sinh hoặc closure.
- Ghi sự kiện đã xảy ra được phép dưới Stop/stale; không tự cấp quyền chi hoặc tiến stage dưới Stop.
- Source_use backend-owned và audit-backed; client không được dùng metadata để giấu source material khỏi basis.
- Same economic event không count hai lần; pending→final append, không overwrite hoặc chọn latest khi confirmed conflict.
- Summary phạm vi decision/managed events; không suy cả A/RA/P/RP toàn công việc từ B5 ledger.
- Không đổi schema.sql/B7 ReportedStatus hoặc dataset gold B7; một writer sở hữu shared models/Store/Service/API.
- Giữ dirty work B3 hiện tại; kiểm status/branch trước sửa, phối hợp owner, không reset hoặc overwrite.

## Task 1 — Chứng từ và actual receipt trên UI

**Files**
- Create: `src/invoice_referee/settlement/b3_funding.py`, `tests/settlement/test_b3_funding.py`, `test_b3_funding_api.py`.
- Modify: `models.py`, `service.py`, `store.py`, `api/settlement.py` trong package invoice_referee hiện tại.
- Create: `frontend/src/settlement/B3Funding.tsx`, `B3Funding.test.tsx`.
- Modify: `frontend/src/settlement/types.ts`, `api.ts`, `B3Approval.tsx`, `App.tsx`, `uiCopy.ts` (B5 wiring/copy, giữ B7).

**Contracts**
- `B3MoneyFieldEvidence`: field Literal[amount_vnd,currency,payer_side,payee_ref,event_at,receiver_outcome,event_namespace,event_ref,method]; source_id:str; locator:str; raw:str|None; value:StrictInt|str|None; read_state Literal[READ,UNCLEAR,NOT_FOUND]; origin Literal[HUMAN_SOURCE_REVIEW]. Numeric/currency/recipient/event identity semantics rõ và resolve nguồn cùng case.
- `B3AdvanceEventPayload`: decision_id:str|None; event_namespace:str|None; event_ref:str|None; method Literal[BANK_TRANSFER,CASH]; gross_vnd:StrictInt|None; payer_side Literal[COMPANY,EMPLOYEE,OTHER,UNKNOWN]; payee_ref:str|None; event_at:AwareDatetime|None; reported_status Literal[RECEIVED,PENDING,FAILED,CANCELLED,UNCONFIRMED]; evidence:list[B3MoneyFieldEvidence]; allocation_note:str; supersedes_event_id:str|None=None. Known gross>0, không float/bool; unknown null. Note không trắng; refs được derive từ evidence, không client override.
- `B3AdvanceEventView`: payload fields + id/case_id/kind Literal[ADVANCE_TO_EMPLOYEE], employee_ref/work_ref, classification Literal[CONFIRMED_RECEIPT,PENDING,NO_RECEIPT,UNCONFIRMED,CONFLICT], actor_id, created_at, after_money_cutoff:bool, incidents:list[B3FundingIncident], idempotent_replay:bool=False. Reported status và derived classification giữ riêng.
- `B3FundingIncident`: kind Literal[OVERPAY,WRONG_RECIPIENT,UNAUTHORIZED_OR_UNALLOCATED,AMBIGUOUS_EVENT_REF,CONFLICTING_OUTCOME]; event_ids:list[str]; refs:list[str]; amount_vnd:StrictInt|None; reason:str.
- `B3FundingSummary`: decision_id:str|None; approved_vnd:StrictInt|None; recorded_received_vnd:StrictInt|None; fulfilled_vnd:StrictInt|None; remaining_vnd:StrictInt|None; pending_count:int; unknown_count:int; incidents:list[B3FundingIncident]; status Literal[NOT_RECORDED,PARTIAL,PENDING,UNCONFIRMED,FULFILLED,NEEDS_RESOLUTION]; scope:str; as_of:AwareDatetime|None. B3WorkflowView thêm funding:B3FundingSummary|None và advance_events:list[B3AdvanceEventView]=[].
- `Service.add_b3_advance_proof(case_id:str,upload:Upload,command:Command)->SourceRecord` và `Service.record_b3_advance(case_id:str,payload:dict,command:Command)->B3AdvanceEventView`.
- `Store.add_source(..., *, source_use:Literal[PROPOSAL,B3_ADVANCE_PROOF]="PROPOSAL")` internal keyword; generic API không truyền source_use. Proof branch dùng audit operation B3_ADD_ADVANCE_PROOF và source_id/hash, tăng case_version nhưng không proposal input_revision.
- `Store.record_b3_advance(case_id:str,payload:B3AdvanceEventPayload,command:Command,context:B3CompanyContext)->B3AdvanceEventView`.
- POST `/api/cases/{id}/b3-advance-proofs`: multipart file + actor_id/demo_role/expected_case_version, Idempotency-Key, SourceView response.
- POST `/api/cases/{id}/b3-advance-events`: actor/demo_role/expected_case_version + event payload, Idempotency-Key, typed view201/200 replay.

- [ ] **1.1 Viết failing test cho receipt không do approval sinh ra**

Trong file mới import các fixtures/helpers thật của B3 tests; fixture approved
được định nghĩa đầy đủ dưới đây. Event evidence literal là nguồn synthetic
cho test lifecycle, không OCR/LLM outputs hoặc independent gold.

```python
from datetime import timedelta
import pytest
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3, _approve,
)
from invoice_referee.settlement.models import Upload

@pytest.fixture
def approved_b3(presented_b3):
    svc, case, presentation = presented_b3
    decision = _approve(svc, case, presentation)
    return svc, svc.get_case(case.id), decision

def receipt_payload(source_id, decision, *, amount=2_000_000,
                    payee="NV-DEMO-01", event_ref="TX-ADV-01"):
    event_at = decision.effective_at + timedelta(hours=1)
    values = {"amount_vnd": amount, "currency": "VND",
              "payer_side": "COMPANY", "payee_ref": payee,
              "event_at": event_at.isoformat(), "receiver_outcome": "RECEIVED",
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": event_ref,
              "method": "BANK_TRANSFER"}
    return {
        "decision_id": decision.id, "event_namespace": "BANK:DEMO-ACCOUNT",
        "event_ref": event_ref, "method": "BANK_TRANSFER", "gross_vnd": amount,
        "payer_side": "COMPANY", "payee_ref": payee,
        "event_at": event_at.isoformat(), "reported_status": "RECEIVED",
        "allocation_note": "Đối chiếu giao dịch với đúng quyết định/công việc",
        "evidence": [{"field": k, "source_id": source_id, "locator": k,
            "raw": str(v), "value": v, "read_state": "READ",
            "origin": "HUMAN_SOURCE_REVIEW"} for k,v in values.items()]}

def upload_receipt(svc, case, decision, amount=2_000_000,
                   payee="NV-DEMO-01", key="proof", event_ref="TX-ADV-01"):
    at = decision.effective_at + timedelta(hours=1)
    text = (f"amount_vnd={amount}\ncurrency=VND\npayer_side=COMPANY\n"
            f"payee_ref={payee}\nevent_at={at.isoformat()}\n"
            "receiver_outcome=RECEIVED\n"
            f"event_namespace=BANK:DEMO-ACCOUNT\nevent_ref={event_ref}\n"
            "method=BANK_TRANSFER\n")
    return svc.add_b3_advance_proof(case.id,
        Upload(filename="receiver-receipt.txt", content=text.encode()),
        command(key, "ACC-DEMO-01", "ACCOUNTANT", case.case_version))

def test_receipt_fulfills_advance_not_closes_case(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    after_proof = svc.get_case(case.id)
    assert after_proof.input_revision == case.input_revision
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("receipt", "ACC-DEMO-01", "ACCOUNTANT", after_proof.case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.b3_workflow.funding.remaining_vnd == 0
    assert view.stage == "AWAITING_WORK_SETTLEMENT"
    assert view.money_summary["received_vnd"] is None  # B7 không thành reimbursement
    assert not svc.closed(case.id)
```

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_funding.py -q`. Trước code FAIL vì methods chưa tồn tại.

- [ ] **1.2 Proof upload và reading confirmation**

Reuse file validation/limits/artifact rollback từ add_source, không clone
Store hoặc schema. source_use chỉ từ Service B5, ACCOUNTANT đúng route/persona;
actor employee/approver sai không upload qua route này. Generic metadata
reserved bị loại/reject; proof role chỉ trusted khi audit operation/source
id đúng, không chỉ provenance string từ client hoặc filename.

B3 proposal snapshots/signatures lọc proof sources trusted; CaseView.sources
vẫn thấy tất cả để truy vết. Upload proof không khiến approved proposal stale
chỉ vì có receipt. Không đổi input_revision hoặc decision signature.
Nếu receipt chứa sửa authorization hoặc context mâu thuẫn, lưu issue và
yêu cầu intake/recheck; không dùng proof route để waive material changes.

Receiver evidence được đọc bởi kế toán, không chỉ nút “đã thanh toán”.
Backend validate mỗi field/source/locator/read state/typed value cùng payload,
allocation context và retained source; ambiguity không thành actual. Text
fixture có thể kiểm raw quote; ảnh/scan dựa human-source reading policy,
không giả đã machine-verified quote. Nguồn mờ phải giữ UNCLEAR/bổ sung nguồn
khác; giá trị typed unsupported không tự USABLE. Audit giữ người/fields/note.

RECEIVED thiếu proof/core fields hoặc có mâu thuẫn: lưu reported facts và
classification UNCONFIRMED/CONFLICT, không aggregate. Malformed types/ref
khác case/missing file:400, không write. Proof mismatch với approved amount
khác mismatch với nguồn: actual3 có source3 được giữ dù approved2; gõ3 trên
source2 không được confirmed3. Không fabricate confidence/auth bank result.

- [ ] **1.3 Lưu actual và summary**

Event operation B3_RECORD_ADVANCE; money_events JSON kind ADVANCE_TO_EMPLOYEE,
audit B3_ADVANCE_EVENT_RECORDED. Không thay generic B7 API hoặc ReportedStatus.
Context route và case_version kiểm trong transaction. decision_id nếu có
phải thuộc case/employee/work; thiếu/không valid không xóa actual report,
giữ UNAUTHORIZED_OR_UNALLOCATED. Không đòi approval còn executable để lưu
tiền đã xảy ra; classification fulfillment là phép kiểm riêng.

Thêm hàm `project_b3_funding(decision:B3DecisionView|None,
events:list[B3AdvanceEventView],stop_active:bool)->B3FundingSummary` trong
b3_funding.py. Chỉ sum canonical confirmed RECEIVED đến đúng employee,
payer company và allocation đúng scope. Final gross giữ nguyên; nếu overpaid
rawsum3/approved2, fulfilled2/remaining0 với incident1, không clip rawsum.
Unknown/pending ảnh hưởng tổng khiến remaining null, giữ known subtotal.
Chưa record không received0. Summary scope=`decision:<id>` hoặc unallocated;
không gọi là whole-work A coverage complete.

Stage AWAITING_WORK_SETTLEMENT chỉ khi đúng approval/basis, fulfilled đủ,
không Stop/pending/unknown/incidents. Partial chờ, incident resolution. Stop
giữ dữ liệu mới nhưng không auto advance stage/can-instruct-payment.
Record có event_at sau money_as_of: after_money_cutoff=true, không sửa mốc
proposal hoặc đưa vào old run. Future date không có căn cứ giữ unresolved;
created_at/known_at thật khác event_at/effective_at mô phỏng.

- [ ] **1.4 UI checkpoint**

`B3FundingPanel` props view:CaseView, role:DemoRole, actorId:string,
onAction:(label:string,run:()=>Promise<unknown>)=>Promise<void>.
Types/API add uploadB3AdvanceProof/recordB3Advance; actual recipient là field
đọc từ nguồn, không prefill từ employee_ref. Expected recipient readonly.
Amount/method/outcome/ref/time/source locator + reading note; blank/unclear
không Number('')→0. Form không default RECEIVED. Phê duyệt2 readonly; actual
inputs riêng. Button “Ghi nhận sự kiện ứng”, không “Chuyển tiền”.

Sau record show summary/sources/time; funded2 “Đã ghi nhận ứng — chờ quyết
toán”, không close. Employee/approver xem readonly. Source-role caveat và
backend errors rõ. API không thành công giữ form, không success optimistic.
Test keyboard labels và disable khi in-flight, source proof selection,
nhận đủ2 đổi state, refresh/đổi vai vẫn state persisted.

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_funding.py tests/settlement/test_b3_funding_api.py tests/settlement/test_b3_workflow.py -q
rtk proxy npm --prefix frontend run test -- --run src/settlement/B3Funding.test.tsx src/settlement/B3Approval.test.tsx
```

## Task 2 — Partial/outcomes/dedup và sự cố

**Files:** b3_funding.py, models.py, Service/Store/API cùng Task1;
B3Funding.tsx/uiCopy.ts; tests B3 funding/API và test_money.py.

**Interfaces:** `supersedes_event_id` chỉ nonfinal→final cùng identity/scope;
incident derived, không endpoint override số. Pending outcome requests dùng
API event mới và giữ record cũ; không UPDATE old money JSON.

- [ ] **2.1 Tests failing cho partial và raw overpayment**

```python
def test_partial_receipt_preserves_approved_amount(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, amount=1_000_000)
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, amount=1_000_000),
        command("partial", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.decision.advance_vnd == 2_000_000
    assert view.b3_workflow.funding.recorded_received_vnd == 1_000_000
    assert view.b3_workflow.funding.remaining_vnd == 1_000_000
    assert view.stage == "AWAITING_MONEY"

def test_overpay_keeps_actual_three_million(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, amount=3_000_000)
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, amount=3_000_000),
        command("overpay", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 3_000_000
    assert any(i.kind == "OVERPAY" and i.amount_vnd == 1_000_000
               for i in view.b3_workflow.funding.incidents)
    assert view.stage == "RESOLVING_OBLIGATIONS"
    assert not svc.closed(case.id)
```

- [ ] **2.2 Implement append transitions và economic identity**

Identity `(event_namespace,event_ref)` từ nguồn/company register; case_id
không làm cùng giao dịch thành hai event. SAME_EVENT alias cần source-linked
confirmation, không guessed amount/date. Thiếu ref giữ raw UNCONFIRMED/
ambiguity, không internal generated ID giả làm bank ref. Namespace account/
issuer/channel rõ; cash nhận dạng theo số bàn giao/register có căn cứ.

Same-key/same body trả view cũ; changed body409. Same economic event/same
actual facts key mới: record supporting evidence/audit nhưng không money
contribution mới. Event đã allocated case/work khác: allocation conflict,
không tăng A lần hai. Không silently drop source copy hoặc mới khẳng định
received khác source cũ. Một record parent nonfinal chỉ một active outcome;
race expected version chặn hai final outcomes đồng thời.

PENDING/UNCONFIRMED→RECEIVED/FAILED/CANCELLED append supersedes. New actual
receipt1 thay requested pending2 không sửa requested oldraw; fulfilled1,
remaining1. Hai confirmed amounts/recipients/outcomes khác nhau giữ raw,
CONFLICTING_OUTCOME, totals ảnh hưởng null, không dùng latest hoặc min.
Return/reversal sau RECEIVED không đổi old RECEIVED thành FAILED; giữ incident
và bổ sung nguồn resolution, không khôi phục quyền chi.

Wrong recipient giữ raw but no expected employee fulfillment; unknown amount
hoặc payer không company không count. RECEIVED khi approval cần recheck vẫn
ghi actual rõ nếu proof đủ, fulfillment chưa được gọi hợp lệ; incident chặn
next action. Không reject actual chỉ vì vượt duyệt/Stop/stale, không automatic
bank retry/thu hồi/chi bù. Existing record/state/history audit còn đọc được.

Tests: partial1+1 hai TX; pending→received cùng TX chỉ2; failed/cancelled
không receipt; wrong recipient; ambiguous event ref; alias proof; cross-case
reuse; unsupported/read_stateUNCLEAR; conflictedconfirmed; typed float/bool;
revision/same-key/double-key/restart. Assertions sums, raw records, incidents,
timestamps và stages, không chỉ HTTP status.

- [ ] **2.3 UI checkpoint**

Hiển thị từng event/outcome, nguồn, original requested vs actual receipt và
record nối tiếp. “Bổ sung kết quả giao dịch” chọn nonfinal record, không mở
edit gross của receipt đã confirmed. Pending/unknown show known subtotal
và phần chưa rõ, không gọi “còn phải chi1” khi tổng chưa xác định.

Overpay/wrong recipient/duplicate show case vấn đề, cần kế toán xử lý;
không tự bật nút thu hồi/chi bù hoặc success “đã cấp đủ”. Test mỗi scenario
trên fresh case; không sửa case happy để test outcome khác.

## Task 3 — Basis/Stop/B7 isolation và bàn giao

**Files:** b3_workflow.py/b3_funding.py, service.py/store.py/b3.py (chỉ source
purpose/history); frontend App/B3Approval/B3Funding/uiCopy; tests funding,
controls/closure/money/b3 workflow; docs Product/System/Evaluation;
Create `docs/testing/B5_ADVANCE_RECEIPTS_WALKTHROUGH.md`.

**Interfaces:** B3 funding projection trong CaseView và CaseSummary.stage;
Service.start B3 đọc proposal sources, history events theo event/knowledge
cutoff; giữ B7 full financial source intake ở chặng linked settlement riêng.

- [ ] **3.1 Tests âm trước integration**

1. Proof upload alone không stale decision/cần approve lại, không receipt.
2. Generic source thêm/mang material change vẫn stale/recheck, không lấy
   source_use client nhập để miễn signature. Old decision không rewrite.
3. Stop rồi record actual vẫn lưu, không advance stage/closure; resume và
   recheck basis mới xét trạng thái, không auto tạo chi.
4. Stale/revoked decision vẫn giữ actual, không fulfillment hợp lệ tự động;
   historical receipt không bị xóa vì grant expired sau event.
5. Event sau cutoff không vào old history; source tới muộn giữ known_at;
   proposal immutable clocks không bị client backdate.
6. B7 `_money_summary` lọc kind trước sum **và pending count**. Advance2
   không reimbursement P2, pending advance không pending B7 obligation.
7. Generic B3 SETTLEMENT/handoff/closure vẫn chặn; new record API không tạo
   bank/request/decision. B5 received2 không whole case closed.
8. Source/event refs wrong case, actor wrong route, expiry/unreadable proof,
   concurrent version command không corrupt sums/history.

- [ ] **3.2 Shared projection/history checks**

Backend-owned proof records có audit source_use được lọc khỏi proposal
Reader/basis. Sources view vẫn mở đủ. Không lọc arbitrary files theo tên
hoặc lời khai uploader. Nếu evidence có material conflict thì issue/basis
recheck rõ; không phục hồi validity chỉ vì posted reading bool/note.

Correct fulfillment giảm remaining không hủy/duyệt lại original amount. B3
workflow status APPROVED và funding status tách nhau; no extra presentation
do thêm receipt. Data nằm trong same case/work/employee/decision namespace.

Confirmed advance events merge into B3HistoryRecord ADVANCE/RECEIVED với
gross, ref và event_at/known_at; chỉ applicable cutoff. Pending riêng,
unknown không fake ADVANCE0. Dedup managed records với imported company event
cần cùng event/source links; không cộng source alias hai lần hoặc coi absence
ở ledger B5 là coverage toàn công ty. B7 chưa auto import; save đủ refs/times
cho plan liên kết sau. Incident resolution/returns chưa mở: giữ blockers.

- [ ] **3.3 Verification commands và UI guide**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy .venv/bin/python -m pip check
```

Guide dùng runbook B3 approval hiện có với fake provider, activated synthetic
company context, DB/artifacts riêng và backend8010/frontend5174. Existing
user-approved case có thể ghi proof nếu căn cứ đủ; không cần gọi LIVE để
test bookkeeping. Provider gọi chỉ với authorization tương ứng.

UI: approve2 → accountant attach receiver proof → đọc fields/record2 → mọi
vai thấy funded/chờ quyết toán; case khác record1 rồi1; pending rồi source
outcome final; wrong/overpay/unknown giữ vấn đề; Stop record actual; refresh/
restart; generic sources không làm proof backend. Ghi thời gian nhập/source
reading để đánh giá effort, không chỉ latency server.

Không browser workaround của denial; chưa thao tác ghi USER_UI_UNEXECUTED.
Không claim AI extraction quality hoặc professional trial từ fake/human
fixture. Báo actual commands/exit/count/artifacts, failures đầy đủ.

- [ ] **3.4 Docs/self-review**

Product/System nêu actual B5 implemented khi wired+tested, vẫn không bank/
closure/B3→B7 tự động. Evaluation thêm mode HUMAN_SOURCE_REVIEW và effort;
không tự freeze baseline/holdout. Scan contracts/nullable totals/source
purposes/bank aliases/type imports và check acceptance dưới đây.

## Acceptance

- [ ] Source retained/read evidence đúng actor/scope; approval/request không thành receipt.
- [ ] Happy2 chờ quyết toán; partial1+1 giữ approved2; unknown/pending không0.
- [ ] Actual3/sai người giữ raw và incident; không tự clip/recover/pay again.
- [ ] Same TX/status updates/aliases/retries/cross-case không double count.
- [ ] Stop/stale giữ actual facts nhưng không cho managed act/closure sai.
- [ ] Proof fulfillment không phá approval vô cớ; material source vẫn recheck.
- [ ] B7 summaries/history không lẫn advance/reimbursement hoặc false absence.
- [ ] UI verified hoặc limitation rõ; bank/LIVE/whole history/B7 linkage chưa claim.

## Prompt gửi coding agent

“Triển khai từng task của `docs/superpowers/plans/2026-10-11-b5-advance-receipts.md` cùng spec được link. Giữ B3/B7 dirty work, một writer shared contracts. B5 là bookkeeping có căn cứ HUMAN_SOURCE_REVIEW, không chuyển tiền hoặc AI xác thực bank. Test failing trước, vừa wired backend vừa có panel UI từng task. Không biến approved/pending thành actual0; raw overpay/wrong recipient giữ incident; economic event không đếm đôi. Stop/stale vẫn nhận fact đã xảy ra nhưng không mở chi. Generic B3/B7 financial guards giữ đúng, không sửa gold. Không tự LIVE/Git/publish; báo command/exit/count, evidence và UI chưa kiểm. Dừng slice ở chờ quyết toán, chưa tạo B7/closure.”

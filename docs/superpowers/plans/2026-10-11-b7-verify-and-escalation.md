# B7 Verify và chuyển tiếp có căn cứ — Implementation Plan

> **For agentic workers:** Dùng `executing-plans` để triển khai từng task; chỉ dùng `subagent-driven-development` khi chủ dự án yêu cầu phối hợp agent. Các bước dùng checkbox để theo dõi. Không tự commit, gọi provider hoặc publish.

**Goal:** Có suite B7 development phiên bản mới chấm được năm initial cases (ba routine, một FACT, một POLICY), một followup FACT, các test âm và câu hỏi cụ thể qua application path hiện tại; trình bày trung thực giới hạn replay so với AI LIVE.

**Architecture:** Giữ một Service, pipeline/rules/store hiện tại. Chuẩn hóa packet context và expected riêng; dùng adapter replay chỉ dành Verify để đưa observations/relations đã đối chiếu nguồn vào cùng pipeline. Sửa có giới hạn quyền/rules/question và evaluator; không đưa đáp án, case label hoặc replay vào model prompt.

**Tech Stack:** Python hiện có trong `.venv`, Pydantic hiện có, pytest, SQLite, Reader protocol hiện có; FastAPI/UI hiện tại để kiểm tra kết quả. Không thêm dependency.

**Spec:** [B7 routine completion](../specs/2026-10-11-b7-routine-completion-design.md). [Review bước 2](../../../output/reviews/2026-10-11-b7-step2-review.md) là bằng chứng gap, không thay Product/Rulebook/Evaluation.

**Status:** PLANNED. Chủ dự án đã cho tiếp tục viết plan sau bước2; không
phải implementation hoặc kết quả chạy v2. Plan chốt cách biểu diễn quyền,
context và final/conditional bên dưới để executor có thể làm; không tự nâng
baseline hoặc claim BTC đã xác nhận ranh giới report.

## Global Constraints

- Giữ nguyên bytes và hash corpus `docs/discovery/eval_development`; không sửa oracle theo output để xanh.
- Chỉ dữ liệu synthetic; không dùng credentials, local case database hoặc uploads thật làm fixture/Git input.
- Tiền strict integer VND; unknown khác0; approval khác received khác closed.
- `POLICY_REPLAY` chỉ kiểm rules/application với facts/links đã chuẩn bị; không chứng minh AI extraction/linking.
- FACT/POLICY/AUTHORITY/TECHNICAL là các nguyên nhân riêng; không đưa mọi case cho người hoặc ép đủ tỷ lệ theo IDs.
- Report không tự tạo quyết định, money event, request hoặc closure. E_final/S_final chưa đủ căn cứ phải null.
- Không bỏ Stop/stale/idempotency/authority/quality gates; không tạo fallback LIVE→replay.
- Không auth/tenancy/ERP/queue/microservices, không mở B3 approvals, không bank transfer.
- Kiểm `git status --short`/branch đầu và cuối; giữ mọi dirty/untracked work có sẵn.
- Frontend/B3 đang có writer khác: không sửa App/Report/Actions/Questions/EvidenceLinks/styles/b3.py trong plan này. Nếu cần UI contract đổi, ghi gap và chuyển owner UI, không tự sửa đồng thời.
- Đây là development suite, không holdout/gold chuyên môn độc lập hoặc bằng chứng ba người dùng thật.

## Scope và thứ tự

1. Packet/oracle/context phiên bản mới và contract quyền hẹp.
2. Evaluator/replay source mapping, negatives và honest metrics.
3. B7 policy/authority/conditional/empty-source và câu hỏi FACT/POLICY.
4. Integration, runbook/UI walkthrough, ghi kết quả; không tự chạy LIVE.

Hai nhánh accept_all/accept_part Q13: kiểm integrity/isolation và ghi
NOT_EXECUTED đối với lifecycle tài chính; chưa triển khai approve exception
hoặc nhập external decision để đóng hồ sơ. Năm initial + followup Q11 là
deliverable hữu hạn. Test AUTHORITY bổ trợ vẫn bắt buộc dù không trong năm demo.

## Task 1 — Packet v2, oracle và quyền theo nguồn

**Files**
- Create: `docs/discovery/eval_development_v2/README.md`, `CORRECTIONS.md`, năm thư mục `Q01`, `Q03`, `Q04`, `Q11`, `Q13`.
- Trong mỗi packet: `manifest.json`, `context.json`, `input/` bản sao nguồn cũ nguyên bytes, `expected/initial.json`, `replay/observations.json`, `replay/relations.json`.
- Q11 thêm `followup/resolution.md`, `expected/after.json`, `replay/observations-after.json`, `replay/relations-after.json`.
- Q13 giữ bản sao hai nguồn followup và hai expected branch, chỉ để audit, không trộn vào initial.
- Policy bundles copy từ snapshot_path trong manifest cũ, giữ hash; thêm `policy/runtime-context.json` biểu diễn typed config từ snapshot, ghi rõ synthetic/activated/version và mapping.
- Modify: `src/invoice_referee/settlement/models.py` (AuthorityGrant).
- Modify: `src/invoice_referee/settlement/evaluation.py` (v2 packet models/loader).
- Test: `tests/settlement/test_evaluation_v2.py`, `tests/settlement/test_manifest_separation.py`.

**Interfaces**
- `AuthorityGrant` giữ actor_ref/work_ref/max_settlement_vnd; thêm employee_ref, max_employee_cost_vnd, max_exception_work_cost_vnd, effective_from, effective_until. Tiền dùng StrictInt, thời gian AwareDatetime. Không suy missing employee-cost/exception limit thành unlimited.
- work_ref/employee_ref null nghĩa scope mọi work/person chỉ khi cấu hình trusted cố ý cấp; packet v2 phải có cả hai ref cụ thể và khoảng hiệu lực. Q01/Q04/Q11/Q13 là CT-DEMO-01/NV-DEMO-01; Q03 là CT-DEMO-03/NV-DEMO-03.
- `PacketContextV2`: submission: Submission; policy: dict; authority: list[AuthorityGrant]; synthetic: Literal[True]; policy_files: list chứa path/sha256; context_refs: list[str]. `ConfigDict(extra="forbid")`.
- `ExpectedV2`: completion: Literal["COMPLETE","INCOMPLETE"]; components: dict chứa đúng t/b/e/a/ra/p/rp; calculated_net_vnd/proposed_net_vnd: StrictInt|None; direction: report direction hoặc None; critical_facts: dict[str, StrictInt|str|None]; expected_relations: list[dict]; issues: list gồm type/owner/blocked/required_context/refs; forbidden_actions: list[str]; external_basis_present: bool; gold_status: Literal["SOURCE_REVIEWED_DEVELOPMENT_NOT_INDEPENDENT"]. Không dùng close_allowed để suy đã đóng.
- `load_packet(packet_dir: Path) -> Packet` dispatch bằng schema_version trong manifest; schema v1 giữ khả năng đọc nhưng notes nói hạn chế, không silently nâng gold.
- Dataclass `Packet` thêm `context: PacketContextV2|None=None`, `expected_v2: ExpectedV2|None=None`, `replay_observations: Path|None=None`, `replay_relations: Path|None=None`; v2 expected_initial là dump của expected_v2 để callers giữ khả năng truy cập dictionary.
- Manifest schema_version=`settlement-packet-v2`; các file-entry gồm path/sha256: context_file, replay_observations_file, replay_relations_file; expected_path/expected_sha256 và initial_input_files giữ dạng loader cũ. Q11 có followup_context_file, followup_replay_observations_file, followup_replay_relations_file cùng followup_input_files/expected_files (initial.json/after.json). Loader v2 dùng tên initial.json, không giả tên before.json của v1. Context sau cũng validate/hash, không đọc từ expected.

- [ ] **1.1 Viết test trước và xác nhận FAIL**

```python
import json
from pathlib import Path
import pytest
from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.evaluation import load_packet

V2 = Path("docs/discovery/eval_development_v2")

def test_v2_has_three_routine_two_resolution_cases():
    packets = [load_packet(V2 / name)
               for name in ("Q01", "Q03", "Q04", "Q11", "Q13")]
    assert [p.expected_initial["completion"] for p in packets] == [
        "COMPLETE", "COMPLETE", "COMPLETE", "INCOMPLETE", "INCOMPLETE"]
    assert all(p.context.submission.form.get("purpose") for p in packets)
    assert all(p.context.authority[0].work_ref ==
               p.context.submission.work_ref for p in packets)

def test_q03_total_includes_company_airfare():
    p = load_packet(V2 / "Q03")
    assert p.expected_initial["components"]["t"] == 6_300_000
    assert p.expected_initial["components"]["e"] == 3_300_000
    assert p.expected_initial["calculated_net_vnd"] == -700_000

def test_q04_current_reimbursement_is_three_million():
    p = load_packet(V2 / "Q04")
    assert p.expected_initial["components"]["p"] == 3_000_000
    assert p.expected_initial["external_basis_present"] is True
    assert "CREATE_DECISION" in p.expected_initial["forbidden_actions"]
    assert "CLOSE_CASE" in p.expected_initial["forbidden_actions"]
```

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_evaluation_v2.py -q`.

- [ ] **1.2 Tạo v2 và ghi correction theo nguồn, trước output engine**

Giữ Q01 T8/B8/E5/A2/RA0/P0/RP0/S+3; Q03 T6,3/B8/E3,3/A4/S−0,7; Q04 T8/B8/E5/A2/P3/S0; Q11 T8/B8/E5/A unknown/S unknown; Q13 T9/B8/employee paid6/A2 nhưng E_final/S_final/proposed/direction final đều null, conditional S+4 có điều kiện riêng.

Q04 bỏ P0 khỏi current critical facts, giữ provenance M1 trong historical notes; RA/RP0 cần coverage M2. Q03 RA/RP0 trỏ company coverage. Q11 unknown A trỏ payment_attempts/coverage, không anchor bị xóa. Q13 type POLICY/owner APPROVER, không OUTSIDE/AUTHORIZED_APPROVER enum tự phát.

Context employee/work/purpose/money_as_of/knowledge_cutoff lấy từ nguồn và input metadata, không expected; không đưa Q ID hoặc phase label vào purpose. Q11 followup giữ money cutoff08/10 18:00, knowledge cutoff09/10 09:00 +07:00; source received_at giả lập phải công bố, audit timestamp máy thật không sửa.

Quyền lấy từ authority source: APR-DEMO-01, effective03–10/10, routine employee cost ≤8triệu và settlement amount ≤8triệu trong đúng scope. Chỉ Q13 có exception total-work-cost ≤9triệu. Các con số này là biểu diễn quyền của scenario, không default policy toàn app. Trong CORRECTIONS ghi cách diễn giải nội dung quyền; không tự mở rộng quyền ngoài source.

Manifest v2 khai báo context/hash, input/hash, policy/hash, expected/hash,
replay/hash và origin_manifest/hash; false expected_is_input và followup_is_initial_input.
author_hints_removed=false cho bản sao narrative cũ: không được bật LIVE bằng nhãn mới.

- [ ] **1.3 Loader strict và tests âm**

V2 context/policy/replay/expected chỉ có vai trò tương ứng. Validate hash mọi file đã khai báo, local refs và anchors, key fact hiện tại không bị trùng, scope/time, bounds không âm, expected enum; lỗi dùng DomainError DATASET_HASH_MISMATCH/EXPECTED_SHAPE_UNKNOWN/DATASET_CONTEXT_INVALID. Dùng json object_pairs_hook để phát hiện duplicate JSON keys trước khi dict overwrite. Replay observations phải có source hash/locator/raw/source support; không được lấy expected để sinh replay.

Ví dụ negative test có thể chạy, mutation chỉ trên tmp copy:

```python
import shutil

def test_policy_tamper_is_refused(tmp_path):
    target = tmp_path / "Q01"
    shutil.copytree(V2 / "Q01", target)
    policy = target / "policy" / "runtime-context.json"
    policy.write_text(policy.read_text() + " ", encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "DATASET_HASH_MISMATCH"
```

Thêm tests cùng cách tmp-copy: context tamper; duplicate fact keys trong JSON (phát hiện trước dict overwrite); orphan anchor; expected_is_input true; followup trộn initial; quyền sai employee/work hoặc hết hiệu lực không được coi covering. Dữ liệu các test cần hash lại khi chủ đích kiểm semantic, giữ original files nguyên.

- [ ] **1.4 Chạy test và review diff/data provenance**

Không freeze B1; expected status vẫn development source-reviewed, chưa independent professional gold. Không đưa replay/template author explanations vào provider input.

## Task 2 — Replay đúng nguồn, evaluator chấm đủ

**Files**
- Create: `src/invoice_referee/verify/settlement_replay.py`.
- Modify: `src/invoice_referee/settlement/evaluation.py`.
- Modify: `src/invoice_referee/verify/settlement_cli.py`.
- Modify: `src/invoice_referee/api/settlement.py` (chỉ Verify composition và cấu hình quyền demo; giữ B3 routes).
- Test: `tests/settlement/test_evaluation_v2.py`, `tests/settlement/test_report_api.py`, `tests/settlement/test_evaluation.py`.

**Interfaces**
- `SourcedReplayReader(artifact_root: Path, observations_path: Path, relations_path: Path)` thực hiện Reader.read/match hiện có; mode=`POLICY_REPLAY`.
- Replay observations chứa source_sha256 cùng payload Observation chưa có runtime source_id; bind bằng bytes hash của source đã upload, không filename/case_id/expected. Fact IDs giữ namespace source để không collision. Relation supporting refs remap tương tự; logical entity refs phải bám invoice/event refs trong nguồn.
- Replay field `basis` ghi SOURCE_QUOTE hoặc DERIVED_WITH_POLICY kèm refs/derivation. Raw quote phải tìm được trong nguồn tương ứng; zero/history totals được derive từ coverage/events đã review và giữ derivation. Không fabricated confidence. SourcedReplayReader không mở expected và không gọi mạng.
- `run_suite(corpus_dir: Path, service: Service, packet_ids: list[str]|None=None, *, execution_mode: Literal["configured","policy-replay"]="configured") -> SuiteReport` thêm keyword-only parameter, giữ compatibility ba arguments cũ. V2 tạo Service cho packet dùng cùng store/application với typed context và replay reader khi execution_mode=policy-replay; không sửa service.policy/config toàn cục trong lúc worker chạy. Configured LIVE dùng reader thật, không replay sidecars.
- CLI thêm `--mode policy-replay|configured` (default configured), truyền execution_mode vào run_suite. `VerifyRunRequest` thêm `mode: Literal["configured","policy-replay"]|None=None`; route lấy request.mode hoặc env `SETTLEMENT_EVAL_MODE`, default configured, validate value. Nhờ env UI hiện tại không cần sửa body. Không cho mode ép output/answer, không nhập replay vào đường upload sản phẩm thông thường. API tests xác minh explicit request override/env fallback/invalid mode.
- `CaseResult` thêm `capability_unavailable: bool=False`; metrics giữ u_routine/u_needs cho technical như v1, thêm u_capability_routine/u_capability_needs và u_total_routine/u_total_needs (union, không đếm đôi). Khoảng FN/FP bảo thủ dùng u_total; không gán capability thành business FP/FN. Tất cả failed/missing axes phải hiện, không silently skip.
- SuiteReport thêm execution_id (UUID); namespace idempotency commands theo execution_id/case/phase/action. Một suite chạy mới không reuse run cũ rồi báo là đo mới. UUID/case labels chỉ ở harness/store commands, không purpose/provider prompt. Test hai lượt suite có run IDs mới; retry cùng command vẫn idempotent, không tạo hành động tài chính.

- [ ] **2.1 Tests failing cho chấm beyond-net**

```python
from invoice_referee.settlement.evaluation import compare_money

def test_unknown_final_must_not_accept_conditional_number():
    assert compare_money({"calculated_net_vnd": None},
                         {"calculated_net_vnd": 4_000_000}) == "FAIL"
```

Trong tests v2 dùng tmp Store và Service; dựng fixture `v2_service` trong file test với StructuredLedgerReader và ServiceConfig, không runtime DB. Với Q01 replay, mutate riêng observations/payment payer COMPANY→EMPLOYEE và số tương ứng giữ net trùng nếu cần; expected không đổi: verdict FAIL ở facts/relations/rows kể cả net tình cờ đúng. Với relations, bỏ một required link hoặc thêm sai payment pair: FAIL. Nhân đôi source bytes không được nhân đôi expense/event hoặc tăng S.

- [ ] **2.2 Implement contract/mapping của v2**

Chấm components và calculated/proposed/direction, từng critical fact value/state/ref/locator support, từng required relation kind/endpoints/portion/status và extra wrong links. Unknown phải có actual null, không chọn giá trị first-non-null. Không dùng source_refs chứa tất cả uploaded files làm proof evidence support.

Canonical refs trong five packets dùng business refs có thật (INV-AIR-001, PAY-HOTEL-001, TX-ADV-001…); mapping chỉ dựa nguồn, không bảng đáp án theo Q ID. Nếu reader trả ID khác, map bằng business ref và source support; ambiguity => INCONCLUSIVE/FAIL, không fuzzy choose để xanh. Quan hệ alias phải giữ provenance SAME_EVENT trước dedup.

Compare issues theo type/owner/blocked và required_context/refs, không exact sentence. Q11 phải có event TX-ADV-001, employee NV-DEMO-01, tiền xin2triệu, cutoff08/10 18:00, nguồn outcome cần; Q13 phải có T9/B8/vượt1, chi phí employee6 và quyền ngoại lệ còn cần quyết định.

State chấm record delta trước/sau Run: không decision/money/request/closure mới. `external_basis_present` chỉ mô tả nguồn, không assertion rằng Store đã có decision. Q04 external approval không khiến evaluator tự fail vì đã có căn cứ bên ngoài; không tự nhập nó thành current authorized action. Closure eligibility import ngoài scope này vẫn NOT_EXECUTED.

Q11 followup upload sau initial, cập nhật submission.knowledge_cutoff bằng Service.revise và preserve money_as_of; version/idempotency đúng. Record response owner ACCOUNTANT với retained source, re-run; initial vẫn needs, after assisted. V2 source business received_at theo context nếu mô phỏng; audit giữ timestamp thật.

Hash/validate Q13 branches và giữ selector metadata riêng. Runner hiện không thực hiện decision branches: in rõ NOT_EXECUTED; không biến chúng thành routine thứ tư/năm hoặc tự chọn theo expected.

- [ ] **2.3 Verify negatives và mode isolation**

Tests: malformed replay/ref/duplicate IDs fail closed; expected mutation chỉ đổi verdict không đổi reader input; đổi packet folder/tên file nhưng giữ source bytes không đổi replay outcome; live guard vẫn từ chối author hints; không mạng khi mode policy-replay; structured reader trên narrative được ghi capability unsupported, không reported AI accuracy.

SourcedReplayReader adapter chỉ phục vụ tests/Verify. Production factory không tự chọn nó từ filename hoặc khi provider thất bại. Mọi configuration hash chứa mode/context/replay source hashes; source hash chỉ inventory selected set và ghi dataset role.

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_evaluation_v2.py tests/settlement/test_evaluation.py tests/settlement/test_manifest_separation.py -q`.

## Task 3 — B7 quyền, policy và câu hỏi cụ thể

**Files**
- Modify: `src/invoice_referee/settlement/rules.py`, `pipeline.py`, `reader.py`, `service.py`.
- Modify: `src/invoice_referee/settlement/models.py` nếu validation grant ở Task1 cần hoàn thiện.
- Modify: `src/invoice_referee/api/settlement.py` (DEMO_AUTHORITY explicit employee-cost limit, không đổi grant B3).
- Test: `tests/settlement/test_rules.py`, `test_engine_quality.py`, `test_questions.py`, `test_decisions.py`, `builders.py`.

**Interfaces**
- Thêm `covering_grant(authority: list[AuthorityGrant], employee_ref: str, work_ref: str, effective_at: datetime, employee_cost_vnd: int, settlement_vnd: int, total_work_cost_vnd: int, exception_required: bool=False) -> AuthorityGrant|None` trong rules.py. Service._grant_for dùng cùng hàm cho nội dung quyết định, không chỉ tự so payload amount.
- Grant cần đúng actor khi quyết định; E trước đối trừ ≤ max_employee_cost_vnd; abs(chi/thu) ≤ max_settlement_vnd; đúng scope/time; nếu đang xét exception thì T ≤ max_exception_work_cost_vnd và limit không null. Không suy thiếu limit thành vô hạn hoặc nới bằng payload người duyệt tự giảm.
- Reader B7 thêm metadata có nguồn: `history.advance_event.<event_ref>.amount`, `.receiver_ref`, `.decision_ref`, `.outcome` (UNCONFIRMED/RECEIVED/FAILED/PENDING), `.event_at`. Không dùng metadata requested amount như history.advance.received. Các keys này không tạo thêm expense hoặc history tổng.
- Giữ Report schema đang có; tận dụng conditional_results, component slots null, Issue.message/refs; không cần frontend contract mới.

- [ ] **3.1 Tests failing cho POLICY và conditional vs final**

Code bên dưới dùng builders thật đã có; thêm import evaluate và AuthorityGrant.

```python
from invoice_referee.settlement.rules import evaluate
from tests.settlement.builders import (
    expense_facts, payment_facts, history_facts, budget_fact,
    expense_payment, run_input,
)

def test_budget_exception_keeps_final_amount_unknown():
    facts = (expense_facts("HOTEL", 9_000_000)
             + payment_facts("HOTELPAY", 9_000_000)
             + history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [budget_fact(8_000_000)])
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L-HOTEL", "HOTEL", "HOTELPAY")])
    report = evaluate(ri, obs, rels, run_id="R-TEST", mode="FAKE_OR_REPLAY")
    assert report.completion == "INCOMPLETE"
    assert any(i.type == "POLICY" for i in report.issues)
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    assert report.direction is None
    assert report.conditional_results[0].net_vnd == 7_000_000

def test_no_expenses_is_not_verified_zero():
    facts = history_facts(a=0, ra=0, p=0, rp=0) + [budget_fact(8_000_000)]
    ri, obs, rels = run_input(facts=facts)
    report = evaluate(ri, obs, rels, run_id="R-EMPTY", mode="FAKE_OR_REPLAY")
    assert report.components.t.value is None
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert report.completion == "INCOMPLETE"
```

Thêm tests scope/expiry/E-cap trước offset: E5, A5 => S0 vẫn vượt E-cap4; E5/A4 => S1 cũng vượt E-cap4; quyền E8/S8 đúng scope đạt routine; wrong employee/work/time không covering. Grant exception9 chỉ cho phép route xem xét T9, không tự chấp nhận chi phí9.

Builders và explicit DEMO_AUTHORITY phải khai báo employee-cost limit theo mục đích fixture. Grants cũ thiếu thông tin cần được giữ thiếu/không covering, không tự thêm unlimited. Old snapshots vẫn decode nếu các fields mới optional, nhưng không được coi full authority verified. Khi thay config demo, ghi version/source; không đổi limit vì muốn test xanh.

- [ ] **3.2 Implement business changes tối thiểu**

T>B tạo POLICY với T/B/vượt/refs. AUTHORITY chỉ thêm khi thực sự không có grant cho nội dung cần quyết định; bỏ điều kiện t<=b trong phép xét quyền vì đó là policy check khác. Không dùng raw grant đã cover net như bằng chứng quyền cover E/exception.

Trong budget unresolved/exception chưa quyết: giữ actual T/B, expense/payment raw và amount paid; final E/calculated/proposed/direction null. conditional_results ghi giả định chấp nhận toàn bộ và nguồn. Không clip T/B hoặc tiền thực chi. Các facts/rows đủ nguồn giữ được; lý do row không gọi là financial approval.

Không có expense entries không thành T/E KNOWN0 hoặc eligibility PASS. Tạo FACT thiếu căn cứ/inventory với refs nguồn có thật. Known employee expense0 khi có expenses company-paid đủ căn cứ vẫn được xét routine. Hồ sơ hủy không chi nào cần nguồn và protocol riêng; chưa có không tự suy0.

- [ ] **3.3 Câu hỏi Q11 và Q13 bằng dữ liệu nguồn**

Q11 message tối thiểu: “Lệnh ứng TX-ADV-001, số đề nghị2.000.000 đ cho NV-DEMO-01 theo DEC-PRE-DEMO-01, chưa xác định tiền đã tới người nhận trước08/10/2026 18:00. Vui lòng bổ sung biên nhận phía nhận hoặc kết quả đối chiếu xác định số thực nhận/trạng thái cuối.” refs là SourceRecord.id + fact IDs/locator liên quan, không chỉ string history.advance.received.

Q13 message tối thiểu: “Tổng chi9.000.000 đ vượt ngân sách8.000.000 đ là1.000.000 đ. Phần nhân viên đã trả6.000.000 đ, đã nhận ứng2.000.000 đ. Cần quyết định khoản/phần được chấp nhận, lý do và phạm vi ngoại lệ; nếu chấp nhận toàn bộ thì kết quả dự kiến trả thêm4.000.000 đ.” Chỉ nói APR-DEMO-01 có quyền nếu covering_grant đủ; không tự kết luận phải loại hotel1 nếu nguồn không quyết.

Tests kiểm meaning/owner/ref, không exact punctuation. Nếu metadata event chưa đọc được: hỏi rõ trường/source còn thiếu, không bịa TX/actor/time. Nếu không retained source nào thì refs rỗng hợp lệ cùng lý do thiếu, không tạo link giả.

Reader prompt keys/meta tests fake: amount requested không biến thành actual A; unsupported/missing metadata không bị guess. _sync_questions giữ vấn đề thật, owner sai không resolve, nguồn đủ+recheck mới resolve. Không gọi LLM viết lại toàn report để làm câu hỏi.

- [ ] **3.4 Run regression**

`rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_rules.py tests/settlement/test_engine_quality.py tests/settlement/test_questions.py tests/settlement/test_decisions.py tests/settlement/test_controls.py tests/settlement/test_closure.py -q`.

Đối chiếu các caller _grant_for/covering_grant và money/closure guards. Không bypass authority v1 ở quyết định để giữ test cũ xanh; báo breaking expectation nào do sửa demonstrated bug và nguồn contract.

## Task 4 — Integration và người dùng kiểm UI

**Files**
- Modify: `docs/settlement/EVALUATION.md` (chỉ capability/mode/path mới, không tự ghi chất lượng đã đạt).
- Create: `docs/testing/B7_VERIFY_V2_WALKTHROUGH.md`.
- Create evidence local: `data/settlement/verify/b7-v2/` (Git ignored).
- Test: `tests/settlement/test_evaluation_v2.py`, `test_report_api.py`.

**Interfaces**
- CLI và `/api/verify/settlement/run` gọi cùng run_suite/application; schema_version2, mode/context/config hash, expected/actual/verdict/time/phase và axes đủ.
- Vì UI đang có writer khác, không thêm component hoặc sửa styles. Verify panel hiện tại phải nhận được response; nếu không hiện axes/mode, ghi gap và đưa request UI riêng với contract này.

- [ ] **4.1 Chạy five-case replay và kiểm kết quả thực**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m invoice_referee.verify.settlement_cli --corpus docs/discovery/eval_development_v2 --mode policy-replay --packets Q01,Q03,Q04,Q11,Q13 --out-dir data/settlement/verify/b7-v2
```

Expected sau implementation: năm initial rows PASS, trong đó completion3 COMPLETE/2 INCOMPLETE; Q11 after row PASS nhưng assisted. Đây là kỳ vọng, không kết quả đã chạy. Q13 decision branches NOT_EXECUTED. Không coi exit0 là cases PASS; giữ failures nếu khác expected.

Authority negative +wrong payer/link/fact/ref+missing source+Stop/stale+duplicate tests phải PASS bằng cách từ chối đúng. Suite raw v1 còn FAIL không sửa cho xanh; notes chỉ rõ capability cũ.

- [ ] **4.2 Chạy checks cần thiết**

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```

Chạy frontend checks sau khi writer UI ổn định; nếu đang đổi files, ghi revision/worktree dirty evidence, không sửa file của họ để chữa lỗi. Báo command/exit/count thật, không dự đoán số tests. Không cần install dependency mới.

- [ ] **4.3 Viết UI walkthrough có các bước cụ thể**

Commands dự kiến sau implementation, dùng DB/Verify store riêng và cổng riêng:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake SETTLEMENT_EVAL_MODE=policy-replay SETTLEMENT_EVAL_CORPUS=docs/discovery/eval_development_v2 SETTLEMENT_VERIFY_DIR=data/settlement/verify/b7-v2-ui SETTLEMENT_DB_PATH=data/settlement/b7-v2-ui/cases.sqlite SETTLEMENT_ARTIFACT_ROOT=data/settlement/b7-v2-ui/artifacts .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app --factory --host 127.0.0.1 --port 8010
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Hai commands chạy ở hai terminal. Trang http://127.0.0.1:5174. Không dùng
DB đang có hồ sơ của người dùng. `SETTLEMENT_EVAL_MODE` là biến mới của Task2,
chưa được coi đã hỗ trợ trước khi implement.

1. Khởi động backend factory/frontend bằng runbook hiện có, với corpus v2 và mode Verify policy-replay; banner/notes phải nói dữ liệu giả lập và chưa dùng AI LIVE.
2. Chọn Verify, năm Q cases, chạy một lần. Kiểm 3 routine/2 resolution, mode, từng axis và nguồn mở được; câu hỏi Q11/Q13 có context cụ thể.
3. Q03 phải thấy đề xuất nhân viên hoàn700.000 đ, không nhãn công ty trả. Q04 cân bằng0, không tự close/chi.
4. Q11 giữ A/S chưa rõ; trả lời đúng owner với source receipt retained, chạy lại; kết quả3triệu nhưng initial vẫn needs. Sai owner/gõ2triệu không source phải không resolve.
5. Q13 chỉ conditional4triệu; final còn chưa quyết, người có quyền không tự bị gắn beyond-authority vì T>B. Không bấm approve exception chưa triển khai.
6. Kiểm history sau Run không thêm decision/money/closure. Run rồi Stop/revision thay đổi: output late không trở thành current.

Nếu Verify cases ở store riêng không xuất hiện trong case workspace, walkthrough phải nêu rõ; dùng API test cùng records để kiểm composition và người dùng xem Verify results. Không hứa click vào case workspace nếu route chưa có. Fixture replay không được mở ở upload sản phẩm thông thường; UI kiểm với originals cần LIVE authorization/dataset sạch ở chặng sau.

User thực hiện UI hoặc agent dùng công cụ browser được phép. Phiên hiện tại đã có browser denial: không dùng CDP/HTTP-DOM hoặc công cụ khác để vượt chặn. Ghi USER_UI_UNEXECUTED nếu chưa thao tác, không coi screenshot/code/test là trial.

- [ ] **4.4 Tự review và ghi evidence**

Điền bảng: contract→test→output artifact→mode→status. Stage labels:
IMPLEMENTED wired path; VERIFIED với mode/scope thật; INCONCLUSIVE cho UI/LIVE/grant semantics chưa establish; PLANNED cho dataset LIVE, Q13 lifecycle, holdout/adaptation/trial.

Không tự publish/commit/freeze baseline. Báo các sửa oracle theo nguồn, giới
hạn replay có handmatching, prep effort và những việc cần chặng AI tiếp theo.

## Acceptance cuối plan

- [ ] Five initial + Q11 followup được chấm money/facts/relations/issues/state bằng v2; mode đúng.
- [ ] Không source/expected/policy cũ nào bị rewrite; mọi correction có provenance.
- [ ] Không expected/case label/replay answer vào provider input; LIVE guard còn hiệu lực.
- [ ] Routine3 tự complete trong POLICY_REPLAY; needs2 có câu hỏi đúng owner/context, không final amount sai.
- [ ] Wrong payer/link/source/rights/E-cap và empty extraction không được pass tình cờ nhờ net.
- [ ] Không tự approval/payment/closure; controls và persisted state regression còn đúng.
- [ ] UI đã kiểm hoặc ghi rõ chưa kiểm; LIVE/OCR/LLM/user trials không bị báo đã đạt.

## Prompt giao agent coding

“Triển khai từng task trong `docs/superpowers/plans/2026-10-11-b7-verify-and-escalation.md` cùng spec được link ở đầu. Đọc review bước2 và phần contract cần thiết. Giữ corpus v1 và dirty edits, tránh frontend/B3 đang có writer khác. Bắt đầu Task1, test failing trước; không tự chạy LIVE/Git/publish. Một writer sở hữu contract models/evaluation; nếu chia việc chỉ khi tôi yêu cầu. Không sửa expected để hợp output. Báo actual command/exit/count, artifacts, replay limitations và UI/LIVE chưa kiểm. Sau mỗi task tiếp tục task kế nếu contract/checks đã rõ và đạt, ghi blocker cụ thể nếu có.”

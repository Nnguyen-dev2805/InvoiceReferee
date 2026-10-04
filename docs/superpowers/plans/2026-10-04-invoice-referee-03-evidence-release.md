# InvoiceReferee Evidence và Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Có Verify và baseline B1 tái lập được, B2 tự điều chỉnh từ feedback và được chấm độc lập, cùng bằng chứng người dùng và gói bài nộp thật.

**Architecture:** Verify gọi CaseService; expected labels thuộc runner. B1 artifacts khóa trước adaptation; threshold update chỉ giữa runs, không thay business policy hoặc hard gates. User trial/deployment/submission là các gate thực tế tách khỏi unit tests.

**Tech Stack:** Python CLI/pytest/JSON+SHA256; React VerifyPanel; bounded threshold grid, SQLite feedback/versions; Docker một app phục vụ API/static UI.

**Spec:** [Master/contracts/global constraints](2026-10-04-invoice-referee.md), [Workflow](2026-10-04-invoice-referee-02-workflow.md), [Evaluation](../../specs/B1_EVALUATION_SPEC.md), [Rulebook](../../specs/B1_RULEBOOK.md), [Competition](../../COMPETITION_REQUIREMENTS.md), [Roadmap](../../ROADMAP_V2.md).

## Global Constraints

Toàn bộ master constraints áp dụng. Development >=15; calibration 12; holdout 20 distinct documents, khóa trước tuning. Fake/replay/live được công bố riêng; expected verdict không nhập production. B2 chỉ đổi word review threshold, không limits/authority/source/normalization. Người dùng thực, live URL, public repo, video/slides chỉ VERIFIED sau bằng chứng thật; agent simulation không thay 3 nhân sự.

---

## T11 — Corpus có gold độc lập và Verify qua production service

**Dependencies:** T08 cho execution; T10 cho UI integration. Chuẩn bị source/gold sau T01, không đợi T10. **Files create:** `scripts/make_synthetic_evidence.py`, `tests/fixtures/{development,calibration,holdout}/manifest.json`, `tests/fixtures/development/{documents,ocr,analysis,gold}/`, các folders tương ứng cho hai tập còn lại; `src/invoice_referee/verify/{__init__,manifest,runner,metrics,__main__}.py`, `tests/integration/test_verify.py`. **Modify:** `api/app.py`, `frontend/src/{api.ts,types.ts,VerifyPanel.tsx}` tuần tự sau writer T09/T10. Optional tooling-only deps reportlab/Pillow để tạo PDF/images, khóa riêng trong `pyproject.toml` nhóm fixtures; không thêm vào runtime.

**Interfaces produced:**

| Type/interface | Shape/signature |
| --- | --- |
| `VerifyCase` | `id, description, provenance: str`, `claim: Claim`, `uploads: list[FixtureUpload]`, `mode: EvaluationMode`, `policy_version: str`, `expected: ExpectedOutcome`, `reference_date: date`, `raw_ground_truth_path: str`, `replay_artifacts: dict[str,str]` |
| `FixtureUpload` | `path, sha256, role, mime: str` |
| `EvaluationMode` | POLICY_REPLAY/PIPELINE_FAKE_OR_REPLAY/LIVE_END_TO_END |
| `ExpectedOutcome` | `execution_status, action: str`, `completion_basis: str\|None`, `issue_classes, owners, required_rules: list[str]`, `amount_vnd: int\|None`, `request_count: int`, `reason: str` |
| `VerifyManifest` | `version, suite, mode, policy_version: str`, `cases: list[VerifyCase]`, `sha256: str`; serialized hash excludes itself |
| `VerifyResult` | `case_id: str`, `run_id, input_hash: str\|None`, `timestamp: datetime`, `expected: ExpectedOutcome`, `actual: dict`, `verdict: PASS/FAIL/INCONCLUSIVE`, `mode: EvaluationMode`, `elapsed_ms: int`, `trace_path: str\|None`; chưa chạy không có fake run ID/trace |
| `VerifyReport` | `id, manifest_hash, policy_version, threshold_version: str`, `mode: EvaluationMode`, `results: list[VerifyResult]`, `metrics: dict`, `started_at, finished_at: datetime` |
| `VerifyJob` | `id: str`, `status: ExecutionStatus`, `completed_count, total_count: int`, `report: VerifyReport\|None`; GET job trả progress/report, không giả report đã hoàn tất |
| Runner | `VerifyRunner(service: CaseService, result_root: Path).run(manifest: VerifyManifest) -> VerifyReport`; `summarize(results: list[VerifyResult]) -> dict`; CLI `python -m invoice_referee.verify --suite core\|escalation\|all --mode replay\|live --output PATH` |

Runner dùng CaseService submit/start/wait; không có evaluate thứ hai. POLICY_REPLAY gọi cùng evaluate nhưng công bố không kiểm providers/storage. Replay chọn artifacts bằng evidence hashes/request identities, không outcome theo case ID/tên file. Runner remap source IDs về backend IDs và kiểm hash/ownership; expected action không được đưa vào application.

- [ ] **1. Viết chứng từ/gold trước actual results.** Development đúng TC01–TC15 của Evaluation; gold gồm amount/merchant/date/currency/items/claim expectations, refs và lý do từ rulebook. Synthetic PDF/image phải nhìn thấy số/ngày/đơn vị, không chỉ JSON. Script fixed seed/reference date, documents/layouts/hashes khác nhau. Calibration 12 phân bố 4/4/2/2, holdout 20 phân bố 6/6/4/4; không đổi tên cùng file để gọi independent.

```json
{
  "id": "TC06", "description": "Bill và đề nghị lệch 200.000đ",
  "provenance": "synthetic", "mode": "PIPELINE_FAKE_OR_REPLAY",
  "expected": {
    "execution_status": "SUCCEEDED", "action": "REQUEST_INFO",
    "completion_basis": null, "issue_classes": ["FACTUAL_UNKNOWN"],
    "owners": ["EMPLOYEE"], "required_rules": ["AMT-01"],
    "amount_vnd": null, "request_count": 0,
    "reason": "Requested 1480000 khác sourced total 1280000, không chọn min/max"
  }
}
```

JSON trên là expectation; full manifest bổ sung Claim, upload path/hash/role và replay paths. Blocked accepted amount là None, không gọi bill total là đã được duyệt. TC05/TC15 là quality/invalid-output contract cases ở fake/replay; không ép live output phải lỗi theo filename. Live corpus có gold nghiệp vụ riêng và actual quality observations. Freeze toàn bộ document/OCR/gold/replay/manifest hashes trước tuning; evaluator giữ holdout labels riêng, tuning worker không dùng chúng.

- [ ] **2. RED correct human still testcase PASS.**

```python
from invoice_referee.verify.runner import VerifyRunner

def test_core_correct_human_case_is_test_pass(verify_service, core_manifest, tmp_path):
    report = VerifyRunner(verify_service, tmp_path).run(core_manifest)
    assert len(report.results) == 4
    row = next(r for r in report.results if r.case_id == 'TC04')
    assert row.actual['action'] == 'REQUEST_INFO'
    assert row.actual['request_count'] == 0
    assert row.verdict == 'PASS'
    assert row.timestamp and row.run_id and row.trace_path
```

T11 test file creates fixtures `verify_service` (realrepo+fake/replayproviders), `core_manifest` from trackedmanifest, no network. Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_verify.py -q`; expectedRED runner absent.

- [ ] **3. Implement sequential runner/results và metrics.** Core TC01/03/04/11; Escalation TC01/02/03/06/11; all >=15 cùng regressions. Submit synthetic cases qua service, đợi terminal, so execution/action/amount/request count/checks/classes/owners. Mỗi row có UTC timestamp/run/input/policy/threshold/provider/prompt/schema/trace. Reports theo ID mới, không ghi đè. Unexpected technical failure→FAIL; intentional TC15 có thể PASS. Mode thiếu prerequisite→INCONCLUSIVE và reason; giữ tổng attempts/completion coverage.

```python
def ratio(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}
```

`metrics.py` báo wrong routine automation/total routine requests; missed human/expected human; unnecessary human/expected routine; class-owner correctness/labelled human; correct amount/requests; correct source/checked required facts; closure/sequences; technical failed/all attempts; stage runtime/calls/cost và mode. HUMAN_AUTHORIZED request không tính routine auto. Denominator 0→None. Technical errors vẫn nằm ở all-attempt success/coverage; gold không lấy từ evaluate.

- [ ] **4. Integrate Verify API/UI without blocking Stop.** POST `/api/verify-runs` với suite+mode trả 202/report job ID; GET `/api/verify-runs/{id}` đọc status/results. T11 thêm `CaseService.reserve(owner_id)` và `release_reservation(owner_id)` theo master. Runner giữ reservation toàn suite, truyền owner_id vào start_run; interactive run/action/policy update bị chặn giữa các case. Runner orchestration chạy một background thread gọi service và wait; provider execution vẫn do executor duy nhất của service. Không chạy runner bên trong chính worker rồi wait chính worker đó. Stop current run vẫn hoạt động; Stop suite đánh dấu phần chưa chạy INCONCLUSIVE và release reservation sau worker kết thúc. Bổ sung POST `/api/verify-runs/{id}/stop` để dừng suite. Frontend có một button Core/Escalation, rows expected/actual/verdict/timestamp/mode/source/owner/question; business human khác testcase PASS.

- [ ] **5. GREEN với regressions và novelty.** Bao phủ B0 probes: numeric/IDs/block refs/unit basis/N/A/arithmetic/contradiction/signed-FX và T07/T08 sequences. Đổi file names/opaque IDs với cùng bytes phải giữ business result; unseen layout/amount chạy cùng path. Service spy chứng minh API và runner gọi cùng CaseService, không chỉ import cùng package.

```bash
rtk proxy .venv/bin/python -m pytest tests/integration/test_verify.py -q
rtk proxy .venv/bin/python -m invoice_referee.verify --suite core --mode replay --output data/verify
rtk proxy .venv/bin/python -m invoice_referee.verify --suite escalation --mode replay --output data/verify
rtk proxy .venv/bin/python -m invoice_referee.verify --suite all --mode replay --output data/verify
rtk proxy npm --prefix frontend run test -- --run
```

Expected fixed cases/regressions PASS, đúng Core 4/Escalation 5, zero unintended requests trên safety corpus. Record actual counts; CLI exit dựa test verdicts, không business auto badge. Chỉ nghiệm thu >=15 khi có đủ assets, gold và execution results.

## T12 — B1 acceptance, frozen artifacts và comparison contract

**Dependencies:** T10/T11 all gates. **Files create:** `docs/evidence/B1_BASELINE.md`, `docs/evidence/b1/{freeze.json,acceptance.json,metrics.json}`, `scripts/freeze_baseline.py`, `tests/unit/test_freeze_manifest.py`. **Interfaces:** Consumes VerifyReport/corpus/model/config/lock hashes; produces `freeze.json` versioned contenthash inventory. `freeze_baseline(root: Path, files: list[Path], output: Path) -> dict` trong script; exclude output file itself; no mutableGitHEAD-only identity when uncommitted changes exist.

- [ ] **1. RED snapshot tampering.**

```python
import hashlib
from scripts.freeze_baseline import freeze_baseline

def test_freeze_pins_actual_file_bytes(tmp_path):
    file = tmp_path/'policy.json'
    file.write_text('{"version":"b1"}', encoding='utf-8')
    result = freeze_baseline(tmp_path, [file], tmp_path/'freeze.json')
    assert result['files']['policy.json'] == hashlib.sha256(file.read_bytes()).hexdigest()
    file.write_text('{"version":"changed"}', encoding='utf-8')
    assert result['files']['policy.json'] != hashlib.sha256(file.read_bytes()).hexdigest()
```

T12 adds `scripts/__init__.py` forimport. Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_freeze_manifest.py -q`; expectedRED missing script.

- [ ] **2. Aggregate acceptance từ fresh evidence rồi freeze.** Chạy backend tests/pip check/frontend tests/build/Verify all. Inspect wiring UI/API/runner→CaseService→process→evaluate→finalization. Acceptance từng SYS/rule gồm amount/count, known refusal, technical errors, Stop race và original Override. acceptance.json ghi status/command/evidence path/hash cho từng AC; thiếu proof→INCONCLUSIVE. Public reports chỉ synthetic/redacted, không sensitive uploads.

```bash
rtk proxy .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk proxy .venv/bin/python -m invoice_referee.verify --suite all --mode replay --output data/verify
```

Freeze exact source/config/rulebook/prompts/locks/corpus/report hashes, Git revision+dirty diff identity, runtime versions/mode/timestamp. B1 chỉ thành baseline sau core gates; live providers/users/public URL có trạng thái riêng, không suy fake benchmark thành competition complete. Capture B1 outputs trên holdout trước B2, evaluator giữ gold kín; so B1/B2 cùng inputs/ground truth/mode, pin policy/threshold mỗi run.

- [ ] **3. B0 comparison chỉ common capabilities; GREEN freeze check.** Dùng probes đã ghi trong docs/reviews/main-baseline-196e266/evidence, không reset checkout. So inventory/quality/units trong scope chung; không coi B0 thiếu eligibility/payment request là regression. Tách bảng B0 bug closure, B1 mới, B2 common metrics. Recompute hashes và báo fail nếu source/report đổi; baseline timestamp/hash từ actual artifacts.

## T13 — Feedback adaptation và independent evaluation B2

**Dependencies:** T12 frozen B1; calibration gold/holdout hash T11. **Files create:** `src/invoice_referee/adaptation/{__init__,feedback,tune,__main__}.py`, `tests/unit/test_adaptation.py`, `tests/integration/test_adaptation_evaluation.py`, `docs/evidence/B2_COMPARISON.md`. **Modify:** `src/invoice_referee/storage/schema.sql` thêm feedback, `src/invoice_referee/application/service.py` thêm automatic adaptation trigger, `src/invoice_referee/api/app.py` thêm feedback/report/rollback routes. Ownership tuần tự; dùng policy_versions/set_policy có từ T04/T08. **Consumes:** PolicyConfig, source traces/feedback gold, VerifyRunner. **Produces:** adapt và persisted threshold version mới khi idle.

**B2 experiment cụ thể:** Chỉ tune word_review_threshold trên grid **0.80, 0.85, 0.90, 0.95**. Missing scores/source, bad normalization, contradictions, arithmetic/policy/authority vẫn là hard gates. Không đổi amount limits, date gap, approval rules, prompts hoặc labels trong cùng experiment; thay đổi khác cần version/protocol riêng.

| Record | Fields |
| --- | --- |
| `FeedbackRecord` | `id, case_id, run_id, input_hash, dataset_split, provenance, labelled_by, reason: str`, `minimum_required_numeric_score: str\|None`, `requires_human_by_gold: bool`, `non_quality_blocker: bool`, `hard_gates_passed: bool`, `created_at: datetime`; split CALIBRATION only for adapt |
| `AdaptationReport` | `id, feedback_hash, baseline_threshold, selected_threshold, new_threshold_version: str`, `candidates: list[dict]`, `changed: bool`, `reason: str`; candidate wrongautomation/missed/unnecessary counts+denominators |

Feedback labels lấy từ gold độc lập và reviewer xem chứng từ gốc, không từ model tự chấm hoặc decision hiện tại. Non-quality blockers vẫn đòi human cho authority/outside-policy/factual thật. Technical failure báo riêng, không tự gắn thành human ground truth. Calibration có thể dùng synthetic labels và phải công bố; real user feedback thuộc T14. Chỉ auto-activate sau ít nhất 12 calibration cases có nhãn/provenance và input hashes khác nhau; thiếu dữ liệu thì báo insufficient feedback, không giả update.

- [ ] **1. RED automatic update, no holdout leakage.**

```python
import pytest
from invoice_referee.adaptation.tune import adapt
from invoice_referee.domain.models import DomainError
from tests.builders import demo_policy

def test_calibration_updates_threshold_automatically(calibration_feedback):
    report = adapt(calibration_feedback, demo_policy())
    assert report.changed
    assert report.selected_threshold == '0.80'
    assert report.feedback_hash and report.new_threshold_version

def test_holdout_is_rejected_as_feedback(holdout_feedback):
    with pytest.raises(DomainError) as exc:
        adapt(holdout_feedback, demo_policy())
    assert exc.value.code == 'INVALID_INPUT'
```

Fixtures trong T13 test file: calibration 12 có phân bố 4/4/2/2; bốn routine scores 0.82/0.83/0.84/0.99 và nguồn hợp lệ; factual/outside/authority có non_quality_blocker=True. Twelve input hashes/gold độc lập; grid 0.80 giảm ba unnecessary escalations trong fixture kiểm thuật toán. Đây là controlled test, chưa phải quality measurement. Holdout fixture có split HOLDOUT. Chạy `rtk proxy .venv/bin/python -m pytest tests/unit/test_adaptation.py -q`; expected RED trước module.

- [ ] **2. Implement candidate scoring/objective/provenance và atomic activation.** Predicted routine cần score >=threshold, hard gates pass và không non-quality blocker; so với gold requires_human. Reject feedback thiếu label reason/source identity hoặc trùng input. Candidate chỉ feasible khi wrong auto=0 và missed=0 trên calibration; chọn least unnecessary, tie gần baseline rồi threshold cao hơn. Nếu không feasible, giữ baseline và ghi reason. Constraint trên fixed sample không chứng minh zero future risk.

T13 API: POST `/api/feedback` nhận FeedbackRecord (CALIBRATION, provenance/gold/source hash); GET `/api/adaptation-reports/{id}`; POST `/api/policy/rollback` với threshold_version/reason/mode POLICY_OWNER. Automatic trigger chạy khi nhận batch đủ nhãn, defer đến idle nếu busy; rollback cũng persist event/version qua service.set_policy. Report/config activation là kết quả hệ thống từ feedback, không yêu cầu operator tự nhập threshold đã chọn để giả adaptation.

```python
from decimal import Decimal

def candidate_routine(row, threshold: Decimal) -> bool:
    return (row.hard_gates_passed and not row.non_quality_blocker
            and row.minimum_required_numeric_score is not None
            and Decimal(row.minimum_required_numeric_score) >= threshold)
```

Khi đủ 12 valid calibration labels/new approved batch, system tự chạy adapt, lưu report/version kể cả không đổi. Chỉ activate giữa runs; audit before/after/feedback hash/objective. set_policy trả RUN_BUSY khi run/Verify reserved; runs cũ giữ threshold cũ. Rollback có version/event, không ghi đè B1. Reject HOLDOUT và overlap evidence hashes, không chỉ kiểm tên split.

- [ ] **3. GREEN adaptation và hai sealed evaluation runs.** Chạy actual calibration cases qua service cho candidate để kiểm simplified scoring khớp full pipeline; khác kết quả thì không activate và ghi reason. Independent evaluator chấm B1/B2 trên cùng 20 holdout inputs/mode/gold. Báo numerator/denominator, all attempts/technical/coverage/amount/owner/source/closure/runtime/cost; improvement không được đặt trước. Nếu lỗi holdout được dùng sửa hệ thống thì tập đó thành development, cần holdout mới.

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_adaptation.py tests/integration/test_adaptation_evaluation.py -q
rtk proxy .venv/bin/python -m invoice_referee.adaptation --feedback data/calibration-feedback.json --output data/adaptation
```

CLI trả report/config candidate; integration test mới chứng minh automatic activation trigger S01. Gate yêu cầu feedback gây version update và hai reports đủ 20 attempts hoặc disclose gap. Chỉ gọi cải tiến là tốt hơn khi actual measurement hỗ trợ.

## T14 — 3 nhân sự nghiệp vụ, feedback và cải tiến có bằng chứng

**Dependencies:** Chuẩn bị recruitment ngay; trial chạy sau T10, comparison sau T12/T13 khi có. **Files create:** docs/user-study/{protocol,invitation,consent,session-template,findings}.md; raw sessions trong ignored data/user-study; redacted docs/evidence/USER_STUDY.md. **Interfaces:** Consumes runnable workflow; produces actual role/consent/observations, linked change IDs và before/after measurements. Private identity/consent riêng, public ledger dùng anonymous IDs.

- [ ] **1. Chuẩn bị recruiting/trial artifacts trước khi gửi.** Target nhân viên từng nộp chi phí, kế toán/reviewer hoặc approver/finance; ít nhất ba người thực trực tiếp làm nghiệp vụ. Invitation cho trial 15–20 phút bằng synthetic files; không yêu cầu company secrets. Chuẩn bị draft không đồng nghĩa đã gửi; outbound messaging cần authorization cụ thể. Người dùng chưa có contacts: chuẩn bị kênh cộng đồng kế toán/alumni/giới thiệu và lời mời, không invent người đã tiếp cận.

```text
Mình đang thử MVP hỗ trợ hồ sơ hoàn ứng cho cuộc thi OrganizationAI.
Bạn đã từng nộp, kiểm tra hoặc phê duyệt chi phí công ty có thể thử 15–20 phút?
Dùng chứng từ mô phỏng; không cần đưa dữ liệu công ty. Mình muốn ghi lại
chỗ khó hiểu, lỗi và thời gian thao tác để cải thiện; bạn có thể dừng bất cứ lúc nào.
```

- [ ] **2. Chạy protocol có consent, giữ feedback gốc.** Tasks: routine travel, meal thiếu attendees, amount mismatch, reviewer confirmation, approval, Stop/Override. Hướng dẫn tối thiểu rồi quan sát; ghi active work riêng với provider wait, errors/questions/unclear reasons/new burden. Hỏi quy trình công ty thực và rework; không gọi trial synthetic là company deployment. Giữ quotes/timestamps, anonymous P01/P02/P03, actual professional role self-report, product/dataset versions và consent scope.

Session template có participant ID/role/date/consent; task/input hash/version; start/end/active/wait; outcome/intervention/errors; exact feedback/suggestion/redaction status. Không dựng thời gian tiết kiệm.

- [ ] **3. Chuyển feedback thành focused fix và rerun evidence.** Ưu tiên correctness, question clarity và effort. Ít nhất một improvement truy từ raw feedback→spec change→diff→focused tests→task rerun, với cùng participant nếu có thể. Không nới approval policy chỉ vì người dùng muốn ít prompts; threshold adaptation thuộc T13. Báo before/after comparable task, new burden và feedback chưa giải quyết. Fix có version B2 mới, không sửa im lặng frozen B1.

- [ ] **4. Real-user gate.** Cần ba actual sessions/roles/consent/feedback và một implemented change có evidence. Nếu chưa đủ ba, ghi S03 INCONCLUSIVE cùng actual count; technical simulation có thể tiếp tục nhưng không đóng user gate. Agent report/test command không thay con người.

## T15 — Single-app deploy và clean-clone runbook

**Dependencies:** T09/T10 packaging, T11 Verify smoke. **Files create:** Dockerfile, compose.yaml, .dockerignore, docs/RUNBOOK_V2.md, docs/evidence/DEPLOYMENT.md, tests/integration/test_static_serving.py. **Modify:** src/invoice_referee/api/app.py thêm static fallback; .env.example có provider/model values khóa ở T05. **Interfaces:** Backend phục vụ built frontend và /api, mounted persistent local data. Uvicorn **one worker**, không reload trên deploy; nhiều workers phá invariant một executor.

- [ ] **1. RED staticSPA fallback doesn't hide API404.**

```python
from fastapi.testclient import TestClient
from invoice_referee.api.app import create_app

def test_api_missing_route_is_json_404(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.get('/api/does-not-exist')
    assert response.status_code == 404
    assert 'application/json' in response.headers['content-type']
```

Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_static_serving.py -q`. API 404 test có thể đã PASS; thêm SPA asset/fallback test thực sự RED trước static serving, không claim TDD RED từ test không đổi.

- [ ] **2. Build image/mount và kiểm clean-clone instructions.** Node stage npm ci/build; Python runtime từ requirements.lock và source, env secrets lúc run; copy frontend dist. /health hiển thị mode/readiness; mounted /app/data giữ SQLite/artifacts. Không bundle credentials/uploads. Một process/finite SDK timeouts, restart marks interrupted. Host cần persistent disk/TLS URL/secrets env; chọn destination khi available. Chuẩn bị local Docker bundle reviewable trước publish.

```bash
rtk proxy docker compose build
rtk proxy docker compose up -d
rtk proxy docker compose logs --tail 80
```

Runbook clean clone phải chạy trên tracked/public tree sau authorized Git publication. Export source copy có hash kiểm local packaging trước đó, chưa chứng minh public clone. Dùng exact lock install rồi editable package --no-deps, npm ci/build, start commands/config paths/ports/volume, demo policy activation và input mới/Verify/Stop. Offline fake mode và live mode công bố riêng.

- [ ] **3. Live smoke có authorization/evidence.** Ba synthetic documents mới thuộc TRAVEL/MEAL/PURCHASE, không fixture name lookup. Inspect actual provider response/coverage/refs/decision/questions; live Core/Escalation chỉ khi gold/mode phù hợp. Missing numeric scores đi reviewer flow, không dựng confidence. Ghi actual provider/model/prompt/hash/runtime/calls; thiếu credentials→INCONCLUSIVE, không fake fallback. Public no-signup URL kiểm từ browser mới, input mới, controls và persistence sau restart; demo data an toàn.

Live gate A02 cần ít nhất một routine case từ evidence thật qua live adapters tạo request tự động mà không có reviewer approval/confirmation từng case. Nếu mọi case đều phải xác nhận vì OCR thiếu native quality signal, chỉ human-assisted path được VERIFIED; routine auto vẫn chưa đạt. Update README/PRODUCT/ARCHITECTURE/TESTING/RUNBOOK theo actual evidence, không giấu gap này bằng replay results.

- [ ] **4. Gate local/live/public riêng.** Static tests, build, clean clone, live providers và public accessibility có từng evidence row/mode/timestamp. Publish dùng destination và authorization của user; không auto-create account/paid plan. Dockerfile tồn tại không chứng minh deployment. C01/C04 VERIFIED sau đúng checks tương ứng.

## T16 — Gói bài nộp, history và diễn tập 17/10

**Dependencies:** T12/T13/T14/T15 evidence; chuẩn bị outlines song song. **Files create:** docs/submission/{requirements-ledger,evidence-index,demo-script,defense-notes,slide-outline,video-script,build-log-one-page}.md, docs/submission/release-manifest.json và exported slides/video thực. **Interfaces:** Consumes versioned reports/source/provenance/URL; produces submission package có files thật. Dùng presentation/document/media skills khi xuất artifact, không lấy outline làm completed slide/video.

- [ ] **1. Assemble evidence/gap ledger.** Mỗi A/S/C row có status/link/hash/timestamp/mode; B0 bug closure, B1 baseline, B2 comparison, user feedback/change và limitations. BUILD_LOG_V2 cấp facts cho one-page log, không phục hồi build log bị xóa. Inspect secret/data/history trước public repo; commit/push/public setting chỉ khi user yêu cầu. Giữ full history, không squash/force-push.

- [ ] **2. Tạo đúng 5 slides và video dưới 3 phút.** Slide 1 pain/scope; 2 flow/routine outcome; 3 human classes/questions/Stop/Override; 4 actual Verify+B1/B2+users/impact; 5 limits/URL/reproducibility. Metrics lấy từ reports. Video target 2m45s: routine request, human question/response, Verify, Stop/Override/audit, evidence/limits. Kiểm actual file <180s, không chỉ script estimate. One-page build log kiểm rendered page count. Assets synthetic/consented/redacted.

- [ ] **3. Diễn tập input mới/phản biện trên frozen build.** Ít nhất 5 unseen inputs khác profile/amount/quality/authority; câu hỏi từ actual values. Chọn run bất kỳ giải thích input/ref/rule/version/reason; thử Stop lúc chờ và Override history. Giải thích N/A, model/Python boundary, quality gates, authority, no bank transfer, real users và independent eval/sample limits. Đối chiếu brief weights 45 demo/35 defense/20 challenge, challenge 8 escalation/6 routine/6 question.

- [ ] **4. Freeze submission trước 15/10, kiểm files thật.** Hash source/config/locks/fixtures/reports/slides/video/log; version/URL/repo/build identity. Kiểm exact 5 slides, video <180s, one-page log, >=15 cases, Core 4/Escalation 5, controls/questions, adaptation và real-user proof. Unmet gates ghi ledger, không claim full Sprint 2. 16–17/10 diễn tập bản đã khóa; nếu BTC đổi deadline, xác minh announcement trước sửa plan.

Checkbox không thay runtime proof. Release gate cần artifact và evidence thật; plan này chưa phải bài nộp đã hoàn tất.

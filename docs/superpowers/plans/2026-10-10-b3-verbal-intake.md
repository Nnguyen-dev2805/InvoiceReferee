# B3 verbal assignment intake/report Implementation Plan

> **For agentic workers:** dùng skill `executing-plans` để triển khai theo task;
> nếu được phép chia việc, dùng `subagent-driven-development`, một writer cho
> contracts. Checkbox dưới đây chỉ đánh dấu bằng execution evidence.

**Goal:** nhân viên nộp đề nghị ứng + dự toán bằng form hoặc hồ sơ ngoài, nhận
report B3 đúng nghĩa trước khi có văn bản công tác/phê duyệt ngân sách.

**Architecture:** giữ FastAPI/SQLite/Service/process hiện hành. Form là lời khai;
import dùng Reader hiện có để đề xuất dữ liệu có nguồn rồi người nộp xác nhận.
Python kiểm số liệu, mâu thuẫn, company context và tuyến quyền. Chỉ thêm hợp đồng
B3 intake/report và fixture công ty cục bộ; không thay B7 hoặc dựng workflow engine.

**Tech Stack:** Python/Pydantic/FastAPI/SQLite, React/TypeScript/Vitest;
Mistral OCR + xkiro LLM qua adapter hiện có; fake providers cho development tests.

**Spec:** [Product P2a](../../settlement/PRODUCT.md#p2a-b3-khởi-tạo-khi-giao-công-tác-bằng-lời-chốt-ngày-10102026),
[Rulebook R1/R2/R5/R6/R8/R11](../../settlement/RULEBOOK.md),
[System S2/S4/S6](../../settlement/SYSTEM.md). Hợp đồng cụ thể dưới đây là phần
triển khai thiết kế B3 đã chốt; không thay luật quyết toán B7.

## Global Constraints

- MVP khoảng 5 người; không auth/tenancy/queues/microservices/ERP/bank transfers.
- Ba vai demo EMPLOYEE/ACCOUNTANT/APPROVER; persona không xác thực danh tính thật.
- Không category caps. VND integer strict; null khác 0; không clipping.
- Initial request không cần upload approval đang xin; request/forecast/approved/actual riêng.
- Dữ liệu công ty không do nhân viên xác nhận thay; fixture explicit version/activation.
- Mọi số/check truy được form revision hoặc source locator/context snapshot.
- Giữ version/idempotency/Stop/revision guards, reader PNG MIME/page/observation-ID fixes.
- Không sửa frozen corpus/gold để suite xanh; không đưa expected vào prompt.
- Không stage/commit/push nếu người dùng chưa yêu cầu. Giữ toàn bộ dirty/untracked work.
- Không gọi LIVE chỉ để kiểm tra unit/API/UI; live quality là bước riêng có authorization.

## 0. Điểm xuất phát và phạm vi bàn giao

Scout/Verify có giới hạn: CodeGraph đã truy `Service.start → process → evaluate`
và `_evaluate_b3`, models/Store; có overload trùng legacy và sections bị trim.
MCP generation/index_status/check_index_coverage không được expose trong phiên
soạn plan; phần material bị thiếu đã đọc trực tiếp. Đây không phải audit toàn repo.
Agent thực hiện phải refresh graph/source phần mình sửa theo AGENTS.md.

Source được kiểm tại branch `rebuild`, HEAD `2a3613e952fed63e8a6f1883f56b2f49deedc152`:

| Hiện có | Thay đổi cần làm |
| --- | --- |
| Active `frontend/src/main.tsx` dùng `settlement/App.tsx` | Chỉ sửa cây settlement, không legacy App/API |
| Form B3 chỉ request/forecast, employee/work/clocks nhập tay | Profile + trip + estimate rows + route, clocks details |
| `handleRevise` tái tạo form chỉ purpose/scope | Giữ đầy đủ B3 fields khi sửa, revision mới |
| `Service.start`: coverage=None; authority max_settlement chung | Company B3 context riêng, immutable run snapshot |
| `_evaluate_b3`: luôn đòi budget.approved; form override observation | Pending current decision hợp lệ; giữ source/form conflict |
| `Report.tsx` dùng S-components cho cả B3 | Section proposal B3; B7 giữ bảng S |
| API decision chỉ `SETTLEMENT` | Không dùng nó để giả approve ứng |

**Kết thúc plan:** intake + preview/confirmation + sourced report + accounting review
và nội dung cần trình người duyệt. **Chưa xây action duyệt work/B/advance, chi ứng,
liên kết B3→B7 hoặc đóng cả lifecycle.** UI phải nói rõ giới hạn này; đây không phải
full end-to-end tạm ứng. Giữ B7 và B3 legacy không schema_version đọc được; không
âm thầm di trú hồ sơ cũ sang case mới. Không tiếp tục B3 mới bằng SETTLEMENT action.

## 1. Bộ mẫu và business oracle

`data/settlement/b3-verbal-v2/` và ZIP cùng tên (local/ignored):

| Partition | Chức năng |
| --- | --- |
| employee-input/ | Hai PDF lẻ, hai PNG hoặc một PDF scan 2 trang; chỉ chọn một bộ |
| forms/native-form.json | Form contract dự kiến, không phải request legacy |
| company-context/context.json | Synthetic backend fixture, không employee upload |
| expected/business-oracle.json | Oracle tác giả độc lập với model; chưa là measured gold |
| manifest.json, README.md | Hashes, cách nộp và giới hạn bằng chứng |

Case: Nguyễn An `NV-DEMO-01`, Kinh doanh; Hà Nội 12–13/10/2026; mục đích khảo sát
yêu cầu/thống nhất phạm vi dự án. Xin ứng 2.000.000; hạn quyết toán 16/10/2026.
Vé công ty dự kiến 3M; nhân viên dự kiến khách sạn 3M, di chuyển 1M, bữa ăn 1M.
Tổng forecast 8M = company 3M + employee 5M; không phải T/E/B đã chấp nhận.

Fixture riêng: kế toán Trần Bình `ACC-DEMO-01`; người duyệt Lê Chi `APR-DEMO-01`,
được phép work, budget ≤10M, advance ≤5M cho đúng nhân viên trong tháng 10.
Đây là **grant**, chưa là decision. History rỗng + coverage đầy đủ đúng scope/as-of
cho phép A/RA=0; history rỗng đơn lẻ không cho phép zero. Clock mô phỏng
`2026-10-10T09:00:00+07:00`, không tuyên bố coverage tới giờ thực khi chạy muộn.

Kết quả cơ bản: READY_FOR_ACCOUNTANT_REVIEW; đủ để trình work/B/advance cùng
người đủ quyền. Work_permission/advance_approval=PENDING_DECISION; B=null.
Không hỏi nhân viên giấy lệnh công tác/Q01/U04. Không duyệt, chi, ghi received hoặc đóng.

### 1.1 Nội dung mẫu cuối cùng đã chốt

Gói v2 thay v1 cho coding/UI trial mới; v1 giữ làm lịch sử, không upload cả hai.
Giấy đề nghị ghi Công ty InvoiceReferee/bộ phận, tên Nguyễn An, số xin 2.000.000 đ,
bằng chữ Hai triệu đồng, lý do gồm nơi/ngày/mục đích và hạn thanh toán16/10/2026.
Không in Mẫu số03-TT, số DN giả định, mã nhân viên, địa chỉ, thông tin giao việc,
tài liệu kèm theo, trạng thái hoặc nhãn thử nghiệm. Tiền trong dự toán có hậu tố đ;
không dòng Đơn vị tính. Dự toán gộp địa điểm/ngày/mục đích vào Nội dung công tác,
giữ rows+cơ sở dự toán+split+total; số xin chỉ 2.000.000 đ, không thêm lời giải thích.
Chữ ký để trống, chỉ tên người đề nghị in sẵn; bốn vị trí ký trên giấy không tạo
bốn role hoặc bắt bốn lượt approval trong hệ thống. Metadata/manifest/README vẫn
nhận diện synthetic, không để nhãn này quyết định checks hoặc trả lời provider.

Web giữ place/start/end/purpose riêng để validation và tạo đoạn khi xuất/hiển thị;
không bắt người dùng nhập số giấy. Dùng mã hồ sơ hệ thống cấp để tra cứu ở MVP,
work_ref backend vẫn khác vai trò mã hồ sơ. Giấy ngoài có số thì giữ optional
source fact, không dùng thay internal key hoặc bắt mọi giấy phải có số.

Giấy v2 chỉ có tên/bộ phận, không employee_ref/work_ref hoặc ref DN↔DT sẵn.
Import kiểm tên so với persona được chọn và các trip fields giữa hai giấy; giữ
liên kết là lời khai dossier của persona, không tuyên bố định danh được xác thực.
Tên trùng/khác người/nhiều chuyến chưa phân biệt phải hỏi, không suy mã nhân viên
chỉ từ tên. Không bắt upload mã nội bộ mới để làm bộ sample dễ đọc hơn.
Lời khai giao việc không bắt buộc; chữ ký trống/không có dòng trạng thái không
chứng minh tuyệt đối chưa duyệt. Current decision của initial flow chờ xem xét;
prior decisions/refusal/pending phải kiểm riêng ở company snapshot.

## 2. Contracts chung (task 1 sở hữu; các task sau tiêu thụ)

### 2.1 Form và draft

Giữ `Submission.form: dict` để tương thích; ở đường B3 mới parse bằng Pydantic
`B3Intake` (new `settlement/b3.py`). Extra fields forbid, frozen; tiền StrictInt.

```python
class B3EstimateRow(BaseModel):
    row_id: str
    description: str
    basis: str | None = None
    company_vnd: StrictInt | None
    employee_vnd: StrictInt | None

class B3Intake(BaseModel):
    schema_version: Literal['b3-intake-v1']
    intake_method: Literal['WEB', 'IMPORT']
    confirmed: bool
    destination: str | None = None
    trip_start: date | None = None
    trip_end: date | None = None
    purpose: str | None = None
    assignment_note: str | None = None
    request_amount_vnd: StrictInt | None = None
    settlement_due: date | None = None
    estimate_rows: list[B3EstimateRow] = Field(default_factory=list)
```

Null row amount giữ unknown, không sum thành 0. Duplicate row_id bị reject.
Không tin client totals/profile/rights/company flags. Confirmed WEB/IMPORT phải
đủ destination/purpose/dates/positive request/deadline/ít nhất một row, row amount
không âm; trip_start≤trip_end≤settlement_due. Không so trip với thời điểm máy thực
trong fixture mô phỏng. Draft IMPORT được thiếu fields; lỗi đọc vẫn là null+issue.
Điều kiện request≤employee forecast là business check, không validate rồi clip.

Nguồn tham chiếu form: `form:<input_revision>:<field-path>`; không gọi lời khai
“đã đọc rõ từ hóa đơn”. Import phải giữ liên kết draft field→Observation refs trong
report; form confirm không tự nâng chất lượng nguồn hoặc xóa contradiction.

### 2.2 Company context và snapshot

`B3CompanyContext` (Pydantic trong b3.py) đúng cấu trúc JSON packet:
schema_version/version/activated/synthetic/demo_clock; people/routes/grants/coverage/history.
Dates aware. money strict. Dùng submodels cho từng record; không engine config tổng quát.

- people: actor_ref, role, name, department. routes: employee_ref/accountant_ref/approver_ref.
- grants: actor_ref, employee_ref, work_ref optional, allow_work,
  max_budget_vnd, max_advance_vnd, effective_from/effective_to, ref.
- coverage: employee_ref, work_ref optional, from/to, complete_prior_history,
  groups/methods/missing_ranges, owner_ref, origin, ref.
- history: `B3HistoryRecord(event_ref, employee_ref, work_ref, kind, amount_vnd,
  event_at, known_at, status, ref)`; kind là ADVANCE/ADVANCE_RETURN/ADVANCE_APPROVAL/
  PENDING_ADVANCE/WORK_DECISION/BUDGET_DECISION. amount optional chỉ cho work decision;
  receipt amount >0. status RECEIVED/PENDING/APPROVED/REFUSED/CANCELLED;
  validate kind/status phù hợp, không APPROVED→RECEIVED.

`work_ref=None` trong grants/coverage có nghĩa **mọi work của employee cụ thể**;
history record luôn work_ref cụ thể. Sum money đúng employee+work, event_at≤money_as_of,
known_at≤knowledge_cutoff. Coverage null work bao gồm mở sổ/tồn trước kỳ nếu
complete_prior_history=True; không suy số dư đầu kỳ bằng 0 nếu cờ không có.
Event không rõ/decision cũ/pending không thuộc routine initial case: giữ raw refs,
route ACCOUNTANT/APPROVER đúng loại; không tự reuse quyết định chỉ từ status/amount.

Thêm `ServiceConfig.b3_context: B3CompanyContext | None = None` và
`RunInput.b3_context: B3CompanyContext | None = None`. Chỉ config backend được cấp
context; POST/PATCH employee gửi context/grants phải reject, không merge.
File env **mới** `SETTLEMENT_B3_CONTEXT_PATH`; absent => None/unknown;
malformed configured file => startup error rõ, không fallback quyền 100M.
Clock cố định chỉ accepted khi activated=True và synthetic=True, UI hiển thị mô phỏng.
Context thật demo_clock=None dùng server time; missing/expired coverage vẫn unknown.

Clock mô phỏng là mốc business/knowledge của fixture, không thay timestamp audit
nhận file thực. Với synthetic context, RunInput.config ghi `simulation_clock` và
map `source_known_at` các nguồn tham gia snapshot sang clock mô phỏng; UI công bố
đây là nguồn được đưa vào kịch bản tại mốc đó. SourceRecord.received_at và audit
vẫn timestamp máy thật. Ngoài simulation không backdate nguồn hoặc future absence.

Hash run snapshot gồm submission/sources/revision/epoch + policy + authority +
b3_context + reader config. Context được persist cùng RunInput; thay config sau run
không sửa report/basis cũ. Snapshot history/coverage/grants đọc được tại endpoint bên dưới.

### 2.3 Report/API

Thêm `Report.b3: B3Proposal | None = None`, không đổi required fields B7.
`B3Proposal` gồm:

```python
readiness: Literal['DRAFT_CONFIRMATION_REQUIRED', 'NEEDS_INFORMATION',
                   'NEEDS_AUTHORIZED_REVIEW', 'READY_FOR_ACCOUNTANT_REVIEW']
intake: B3Intake
forecast_company_vnd: StrictInt | None
forecast_employee_vnd: StrictInt | None
forecast_total_vnd: StrictInt | None
work_permission: Literal['PENDING_DECISION', 'NEEDS_REVIEW']
advance_approval: Literal['PENDING_DECISION', 'NEEDS_REVIEW']
accountant_ref: str | None
approver_ref: str | None
field_refs: dict[str, list[str]]
```

Giữ components.a/ra cho history actual, b cho existing approved budget nếu đủ
căn cứ (initial null); t/e/p/rp NOT_APPLICABLE ở report B3 mới. calculated/proposed
net và direction đều null. COMPLETE nghĩa checks tiền/source/history/routing đủ,
không nghĩa APPROVED. Current work/B/advance pending là next_decisions, không
unresolved issue; history/grants/quality/conflicts cần làm rõ vẫn issue thực.
Draft luôn INCOMPLETE/DRAFT_CONFIRMATION_REQUIRED; không accounting review submitted.

API **mới**, chỉ dùng B3 v1:

```text
GET /api/demo-context
  {version, synthetic, demo_clock, people, routes}; không cấp quyền do client nhập.
POST /api/b3-cases
  {actor_id, intake: B3Intake}; header Idempotency-Key.
  employee_ref/role từ persona config; work_ref backend WORK-<uuid12>.
  submission job=B3, clocks từ server/demo clock, form=intake model_dump.
  response CaseView. Không cho chọn existing-work trong slice này.
PATCH /api/cases/{id}/submission
  dùng route hiện có, validate B3Intake và giữ employee/work immutable cho B3 v1.
  actor/role/version/reason như hiện hành; client không sửa clocks/history/quyền.
GET /api/runs/{run_id}/b3-context
  snapshot {version, synthetic, demo_clock, grants, coverage, history}; chỉ context
  đã dùng trong run đó, refs company:<...> mở tới record tương ứng.
```

`Store.get_run_input(run_id: str) -> RunInput` mới, đọc stored snapshot JSON có sẵn;
không bảng/config store mới. Endpoint unknown run trả lỗi như get_run hiện tại.
Submit/confirm/revise tiếp dùng command guards. Tạo work id phải idempotent:
backend kiểm replay key **trước** phát id mới hoặc lấy lại Submission đã persist.
Chỉ gọi create_case với payload fingerprint ổn định cho cùng user request; đổi
request cùng key phải conflict. Cấm lấy UUID mới vào fingerprint mỗi retry.

IMPORT: tạo draft bằng POST b3-cases với confirmed=False; upload sources hiện có;
run preview; UI điền từ report.b3.intake, mở refs; confirm PATCH confirmed=True
(full fields) + expected version + reason; START_RUN lại. Reread hai tài liệu ở lần
confirm được chấp nhận cho MVP, ghi chi phí thật; không bắt xây cache/queue mới.
Edit trong draft không silently supersede originals. File employee “grant” hoặc
“zero company history” không cấp B3 rights/absence; giữ source nhưng không trust.

### 2.4 Reader keys và checks

Giữ Reader.read/Observation contract; B3 v1 dùng danh sách/grammar rõ, không nói
prefix phải khớp “exact one key” rồi reject mọi output. Keys:

```text
document.role = ADVANCE_REQUEST | FORECAST | SUPPORTING
person.employee_ref; person.name
trip.destination; trip.start; trip.end; trip.purpose
advance.request.amount; advance.request.amount_words
advance.request.amount_words_value; advance.settlement_due
forecast.company; forecast.employee; forecast.total
forecast.row.<row_id>.description
forecast.row.<row_id>.basis
forecast.row.<row_id>.company; forecast.row.<row_id>.employee
```

row_id là document-local, namespace backend theo source/page; giữ READ/UNCLEAR/
NOT_FOUND, quote/locator thật, số strict. LLM có thể đề xuất diễn giải số bằng chữ
vào amount_words_value với quote gốc; Python so với số, không LLM kết luận check.
Không rõ diễn giải => UNRESOLVED, không đoán số. Native web không có words =>
NOT_APPLICABLE. Quality vẫn phải đo bằng critical-fact gold, không tự gọi “chắc chắn”.
Phải xác định bảng đủ rows/trang không cắt trước sum; chỗ bị che/thiếu giữ null.

B3 v1 **không gọi generic payment matcher B7**. B3 helper dựng quan hệ request↔
forecast dựa ref/person/dates/place; thiếu identity hoặc mâu thuẫn => unresolved,
không `relations=[]` rồi PASS “tất cả đã ghép”. Reference gộp trang vẫn source/page đúng.
Hai bản forecast cùng nội dung không cộng hai lần; khác nội dung giữ conflict.
Đừng fuzzy-join chỉ vì hai tổng tiền bằng nhau.

Rule IDs: `trip_context`, `request_positive`, `amount_words_consistency`,
`estimate_arithmetic`, `request_forecast_consistency`, `proposal_relation`,
`source_form_consistency`, `history_coverage`, `prior_advance_state`, `decision_route`.
Giữ source checks có refs; web arithmetic có form refs. Không fill row null thành 0;
không lấy approved ngân sách hay quyền từ estimate.

## Task 1: Form/context/report contracts và fixture builders

**Files:** Create `src/invoice_referee/settlement/b3.py` (models và helpers B3);
Modify `models.py` (RunInput/Report optional b3 fields), `service.py` (config);
Create `tests/settlement/test_b3_intake.py`, `tests/settlement/b3_builders.py`.

**Consumes:** §2 contracts và hai JSON packet.
**Produces:** B3Intake/B3CompanyContext/B3Proposal;
`make_b3_run(*, form: dict | None = None, context: dict | None = None) -> RunInput`,
`make_b3_observations() -> list[Observation]` trong test builder. Builders literal
2M/3M/5M/8M và independent refs, không dùng evaluator tính expected.

- [x] Viết validation regression: float/bool money, negative row, duplicate row,
  end<start/deadline<end bị reject; IMPORT draft null hợp lệ; confirmed missing invalid.

```python
def test_import_draft_can_be_empty():
    draft = B3Intake(schema_version='b3-intake-v1', intake_method='IMPORT', confirmed=False)
    assert draft.request_amount_vnd is None

def test_native_expected_split():
    r = make_b3_run()
    f = B3Intake.model_validate(r.submission.form)
    assert sum(row.employee_vnd for row in f.estimate_rows) == 5_000_000
    assert f.request_amount_vnd == 2_000_000
```

- [x] Run red: `rtk proxy .venv/bin/python -m pytest tests/settlement/test_b3_intake.py -q`.
- [x] Thêm typed models §2; validators cho confirmed; default optional fields giữ
  B7 deserialization. Test builder không đọc expected vào Reader.
- [x] Run green cùng command; test B7 serialized Report không cần b3 field.

## Task 2: Company context, persona và intake API có snapshot

**Files:** Modify `service.py`, `store.py`, `api/settlement.py`;
Create `tests/settlement/test_b3_api.py`; Modify `tests/settlement/test_controls.py`.

**Consumes:** Task1 models/builders. **Produces:** endpoints §2.3;
`load_b3_context(path: Path) -> B3CompanyContext` trong b3.py;
`Store.get_run_input(run_id: str) -> RunInput` và context persist/hash;
pytest fixture `b3_client` là FastAPI TestClient với temp SQLite/Reader fake và
ServiceConfig.b3_context literal từ packet. Test không phụ thuộc DB hoặc .env thật.

- [x] Viết test POST web auto profile/work/clock; retry cùng key trả cùng case/work;
  changed payload/key conflict; fake actor reject; context từ employee reject.
  PATCH preserve B3 fields, actor/work/clocks cannot mutate; version stale reject.

```python
def test_create_retry_keeps_generated_work(b3_client):
    payload = {'actor_id': 'NV-DEMO-01',
               'intake': make_b3_run().submission.form}
    headers = {'Idempotency-Key': 'same-command'}
    first = b3_client.post('/api/b3-cases', json=payload, headers=headers)
    second = b3_client.post('/api/b3-cases', json=payload, headers=headers)
    assert first.status_code < 300 and second.status_code < 300
    assert first.json()['id'] == second.json()['id']
    assert first.json()['submission']['work_ref'] == second.json()['submission']['work_ref']
```

- [x] Run red: `rtk proxy .venv/bin/python -m pytest tests/settlement/test_b3_api.py tests/settlement/test_controls.py -q`.
- [x] Dùng JSON fixture load explicit trong runtime factory, không chạm `.env`
  hoặc log secrets. `Service.submit` B3v1 tra persona, cấp work id idempotently;
  dùng existing audit transaction, clock backend; native store vẫn lưu form.
  Hash capture đủ context/policy/rights/config; persist theo create_run hiện có.
- [x] Reject mọi B3v1 settlement decision/money/handoff/closure bằng backend code
  `B3_REPORT_ONLY` ở transaction guard, không chỉ hide UI. Accounting review report
  submitted vẫn có thể record bằng action hiện có. Draft không cho financial/review.
  Allowed_actions không quảng cáo những action chưa hỗ trợ.
- [x] Run green; guards Stop/stale vẫn fail như cũ; B7 actions giữ nguyên.

## Task 3: Reading và evaluator cho initial B3 proposal

**Files:** Modify `reader.py` (B3 key grammar/prompt), `pipeline.py` (branch job);
Modify `rules.py` (dispatch B3 v1); implement helpers trong `b3.py`;
Create `tests/settlement/test_b3_proposal.py`; Modify `test_readers.py`, `test_pipeline.py`.

**Consumes:** RunInput.b3_context, typed form, list[Observation] và technical issues.
**Produces:**
`evaluate_b3_proposal(run_input: RunInput, observations: list[Observation], *,
run_id: str, mode: str, technical_issues: list[Issue]) -> Report` trong b3.py;
rules dispatch schema_version, không fixture ID/name. Draft proposal và check refs §2.

- [x] Viết test red cho case initial: hiện tại đòi B dù đang xin, override form/source,
  empty relations PASS. Test assert số/refs/state/owner, không chỉ completion string.

```python
def test_initial_request_does_not_require_current_approvals():
    report = evaluate_b3_proposal(make_b3_run(), [], run_id='R-T',
                                  mode='FAKE_OR_REPLAY', technical_issues=[])
    assert report.b3.readiness == 'READY_FOR_ACCOUNTANT_REVIEW'
    assert report.b3.forecast_total_vnd == 8_000_000
    assert report.components.b.value is None
    assert report.components.a.value == 0
    assert report.b3.work_permission == 'PENDING_DECISION'
    assert report.calculated_net_vnd is None
    assert not report.issues
```

- [x] Run red: `rtk proxy .venv/bin/python -m pytest tests/settlement/test_b3_proposal.py tests/settlement/test_pipeline.py tests/settlement/test_readers.py -q`.
- [x] Implement numeric sums with null propagation; observed total vs summed rows
  check; compare paper numeric/word proposal; validate identity/source-role/row-table
  completeness. Form/source khác thì show cả hai, không silently chọn form/latest.
  Giữ source quality gate; confirmed form không biến source mờ thành READ.
  Khi đối chiếu rows form/paper: chỉ ghép description sau normalize case/whitespace
  nếu duy nhất và các fields không mâu thuẫn; không chắc quan hệ thì unresolved.
  Tách refs mọi row; hai allocation khác nhau dù tổng bằng nhau vẫn conflict.
- [x] Derive actual A/RA từ context RECEIVED đúng scope/cutoffs, zero chỉ đủ coverage;
  checks pending/prior approval/refusal và routing work/B/advance riêng. Initial B
  missing current approval → pending, không missing upload. Budget limit kiểm
  **forecast total 8M**, advance limit kiểm **request 2M**, không net hoặc employee total.
  Grant actor đúng scope/time, role label không tự cấp quyền. Unknown → đúng owner.
- [x] Pipeline skip generic match chỉ B3v1; preserve B7/legacy. No sources native
  form hợp lệ, không OCR cho form. Import dùng source evidence, 2 pages độc lập;
  parser giữ observation IDs namespace backend, gọi providers không tăng output thừa.
- [x] Run green; thêm parameterized regressions T01–T15 ở §3, technical failure
  INCOMPLETE nhưng giữ phần rõ, không fake success. Dùng shuffled source order.

## Task 4: UI hai đường nộp và report nghiệp vụ

**Files:** Modify `frontend/src/settlement/{App.tsx,api.ts,types.ts,Report.tsx}`,
`frontend/src/styles.css`; Create `B3Intake.tsx`, `B3Intake.test.tsx`, `App.test.tsx`;
Modify `Report.test.tsx`. Không thêm component library/dependency.

**Consumes:** demo-context/b3-cases/current PATCH/upload/run API; Report.b3 contracts.
**Produces:** `B3IntakeForm` trong B3Intake.tsx với props
`{value:B3Intake,onChange:(next:B3Intake)=>void,disabled:boolean}`;
type B3Intake/B3Proposal/B3DemoContext tương ứng §2 trong types.ts;
`getDemoContext(): Promise<B3DemoContext>`,
`createB3Case(actorId:string,intake:B3Intake): Promise<CaseView>`,
`getB3RunContext(runId:string): Promise<B3CompanyContext>` trong api.ts.

- [x] Write red RTL tests: persona readonly profile, no approver dropdown/work-id/
  clock inputs trong B3; estimate totals display; IMPORT cannot submit before confirm;
  source links present; pending approval không warning “thiếu B”. B7 report không đổi.

```tsx
// Report test fixture has job B3, report.b3 per §2 and components A=0/B=null.
render(<ReportPanel report={report} />);
expect(screen.queryByText(/S = E/)).not.toBeInTheDocument();
expect(screen.getByText(/Đang chờ quyết định/)).toBeInTheDocument();
expect(screen.getByText(/2[.,]000[.,]000/)).toBeInTheDocument();
```

- [x] Run red `rtk proxy npm --prefix frontend run test -- --run`.
- [x] App load demo-context, choose persona once; if context absent explain configure
  company fixture, không generate fake profile/quyền. Persona sets actor+role;
  người duyệt là readonly route, không nhập kính gửi/địa chỉ như nghiệp vụ bắt buộc.
- [x] Form native: destination/date/purpose/request/deadline + estimate
  rows (description/basis/company/employee; assignment_note optional ở details). Client sums chỉ preview; backend rechecks. Submit createB3Case WEB confirmed.
  Request sửa dùng full typed form, preserve amounts/rows/dates; không reuse legacy
  handleRevise rút form còn purpose/scope. Technical fields trong details, fixed clock
  ghi rõ “Mô phỏng” trên màn demo.
- [x] Import: draft create → upload → “Đọc hồ sơ thành bản nháp” → preview facts/refs
  và issues → edit/confirm PATCH → “Gửi kiểm tra B3”. Không đánh dấu submitted sau
  preview; request form và source khác vẫn contradiction. Cần supplement thì nộp
  revision/new source rõ, không xóa paper cũ vì user đổi số.
- [x] Report B3: proposal summary, estimate split, checks+refs, issue owner/next step,
  trạng thái current approvals pending; company history/context panel. Form refs mở
  lưu declaration revision; source refs mở đúng PDF page/quote; company refs mở run
  context endpoint. “Ghi chú nguồn” thay “provenance”, giải thích đây là người nộp
  nói lấy file từ đâu, không tự xác thực issuer.
- [x] Readiness UI không nút giả “đã duyệt ứng/đã chi”; chỉ review/handoff nội dung
  cần quyết định bằng report, chưa financial handoff action. Debug allowed actions,
  revision/epoch/provider traces trong details; run FAILED hiển thị lỗi rõ.
- [x] Run green test + `rtk proxy npm --prefix frontend run build`.

## Task 5: Integration và UI evidence để bàn giao người dùng

**Files:** Modify `tests/settlement/test_b3_api.py`, `test_b3_proposal.py`;
Update canonical `SYSTEM.md` B3 contracts, `EVALUATION.md` new synthetic test scope;
append riêng nhánh mới trong `docs/testing/SETTLEMENT_MANUAL_TEST_GUIDE.md`.
Không đổi B7 checklist hoặc gọi corpus mới là B1 frozen.

**Consumes:** Task1–4 paths, packet manifest và oracle **chỉ ở test assertions**.
**Produces:** `output/b3-verbal-v2-test-evidence/` với test commands/results,
UI screenshots web/import/report/error, actual-vs-expected table và unexecuted limits.

- [x] API fake integration: native submitted → run → correct Report; import upload
  original → preview unconfirmed → confirm revision → rerun with original refs.
  Test `reader.match` spy không gọi B3v1, vẫn gọi B7. No direct evaluator-only substitute.
- [x] API negative tests company-context tamper, grant expired, changing context,
  Stop/revise during run, B3 financial actions forced POST rejected, retry create.
- [x] Run focused suite then required release checks once:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```

- [x] Start existing dev/API commands (inspect current README/scripts; no new server
  framework), env SETTLEMENT_B3_CONTEXT_PATH points at packet context, fake mode.
  Native U01/nhánh native của U04/U05/U06 chạy trên actual UI/API fake; screenshot/log versions/owners.
  Fake Reader hiện có không chứng minh đọc hai PDF/PNG mới. Import success U02/U03
  kiểm bằng injected Reader trong API tests và mocked responses trong RTL, ghi đúng
  PIPELINE_FAKE_OR_REPLAY. Không thêm production branch theo fixture tên/hash để
  fake đọc được PDF. UI import với file thật chưa gọi LIVE ghi USER_LIVE_UNEXECUTED;
  cung cấp checklist cho chủ dự án chạy sau khi coding. Nếu không có browser access,
  UI check tương ứng INCONCLUSIVE, không biến mock thành actual UI evidence.
- [ ] User LIVE trial later: same packet/clock/policy/version; upload employee inputs
  only. Record each source/page/usage/provider failure/latency/manual correction;
  compare critical facts/links/checks with oracle. A single happy sample is not baseline.
- [x] Update plan evidence with IMPLEMENTED/VERIFIED/INCONCLUSIVE by mode; preserve
  all existing reader fixes/dirty docs, report git diff/status. No commit by default.

## 3. Acceptance matrix: observable regression cases

| ID | Mutation/trigger | Required behavior |
| --- | --- | --- |
| T01 | Native, activated context, no official document | 2M; forecast3/5/8M; A/RA0 via coverage; Bnull; ready accounting; current decisions pending |
| T02 | Import same two documents | Draft confirmation required; after confirm same business result; fields carry source/page refs |
| T03 | Paper words “Ba triệu đồng”, number2M | amount_words_consistency FAIL; EMPLOYEE issue; no ready/clip |
| T04 | Forecast printed employee total4M, rows sum5M | estimate_arithmetic FAIL with both amounts/refs; no using printed/sum silently |
| T05 | Request6M vs employee forecast5M | NEEDS_AUTHORIZED_REVIEW; APPROVER; amount6M retained; fixture advance limit5M separate issue |
| T06 | Source request2M, confirmed form3M | source_form_consistency conflict, both refs retained; not form-wins |
| T07 | Hotel employee amount UNCLEAR | employee/total null; quality issue EMPLOYEE with locator; no partial-sum PASS |
| T08 | Drop company coverage | A/RA unknown, ACCOUNTANT, not zero; initial B still pending rather than upload demand |
| T09 | As-of after coverage.to or employee different | missing scope/time coverage; cannot report known zero |
| T10 | Prior pending2M / actual1M / refused approval same work | retain separate status/amount; owner-specific review; no auto new advance/closure |
| T11 | Budget grant7M, advance5M, work right true | forecast total8M exceeds budget authority even request2M fits; APPROVER route insufficient |
| T12 | Employee fake Q01/historyzero file; wrong/expired grant | file not trusted rights/coverage; cannot ready from uploader declaration |
| T13 | Two forecasts different employee/trip/ref; duplicate source | unknown/conflict relation; do not sum; exact copy not second expense/forecast |
| T14 | Provider fails / Stop or revise during run / forced finance action | technical partial or controlled run; no stale publish/financial actions; actual receipts not fabricated |

| T15 | V2 chỉ tên/department, gộp trip text, tiền đ, không số/mã/state | Parse2M/3M/5M/8M và trip dates, declaration identity rõ; không hỏi employee_ref/DN; ambiguity giữ question, blank signature không actual/approval |

U01: chọn Nguyễn An → WEB nhập fixture → submit → report T01, mở form refs.
U02: Nguyễn An → IMPORT → tải hai PDF lẻ → preview → mở giấy và amount → confirm → report T02.
U03: tạo IMPORT khác chỉ tải scan2pages → source/page1request/page2estimate refs đúng;
không nộp cả scan và PDF lẻ trong basic run. Log reread/calls nếu LIVE.
U04: native sửa request3M sau report2M → revision tăng, rerun → request3M, giữ
đủ rows/dates; không hiện old report là current basis. IMPORT sửa3M khi paper2M
vẫn active → T06 còn contradiction, không gán form-wins.
U05: tắt coverage config → **new run** → T08; old run context vẫn đủ và immutable.
U06: thử direct API decision/money/closure cho B3v1 → B3_REPORT_ONLY; chuyển B7
và kiểm report S/actions regression hiện hành vẫn hoạt động.

U02/U03 bản thật cần Reader LIVE đã cấu hình Mistral/xkiro và authorization của chủ
dự án. Các bước này là checklist nghiệm thu của người dùng, không permission để
agent coding tự gọi provider. Nếu LIVE fail phải phân biệt lỗi provider/schema và
issue nghiệp vụ, giữ trace; không kết luận sample giấy sai vì technical failure.

## 4. Handoff prompt (copy cho coding agent)

```text
Đọc AGENTS.md và dùng skills đúng task. Triển khai
docs/superpowers/plans/2026-10-10-b3-verbal-intake.md theo Task1→5.
Đọc Product P2a, Rulebook R1/R2/R5/R6/R8/R11 và System phần liên quan;
không load archive/toàn bộ markdown. Đây là B3 intake/report trước approval,
không full advance financial lifecycle. Dùng packet data/settlement/b3-verbal-v2
hoặc ZIP tương ứng; expected chỉ assertion, không đưa vào Reader/provider prompt.
Preserve uncommitted reader fixes và docs/user work. Giữ B7/legacy cases compatible.
Backend nhẹ; không enterprise auth/workflow engine/new dependencies nếu không cần.
Code từng task với fake regression/API tests và UI hoạt động để chủ dự án test.
Đừng gọi LIVE hoặc stage/commit/push. Bàn giao commands, screenshots, actual-vs-expected,
những bước chưa verify; đừng gọi happy synthetic packet là measured baseline.
```

## 5. Review của người viết / execution status

- Thiết kế đã chốt với chủ dự án; plan chưa execution. Tất cả task unchecked.
- Bao phủ native/import/profile/routing/clocks/company history/math/conflict/quality/refs.
- Tradeoff: import reread khi confirm làm tăng calls; chấp nhận MVP, phải đo, không giấu.
- Khác mockup cũ: không approver dropdown, không bắt employee nhập tên/mã/bộ phận.
- Model chưa prove live extraction/quality. Packet oracle single-author không independent gold.
- Approval ứng và kết nối B3→B7 là gap có tên, không nghiệm thu ngầm qua report green.
- Canonical rule đã cho initial check trước current approvals; plan sửa implementation
  để theo rule, không bỏ history/rights/quality vì demo.

## 6. Execution status (bàn giao 2026-10-10)

- Task 1–4: **IMPLEMENTED + VERIFIED (FAKE_OR_REPLAY)** — records/evaluator/API/
  UI đều chạy trên application path thật (Store/SQLite + Service + pipeline);
  658 backend tests + 58 frontend tests xanh, build/typecheck sạch. Regressions
  T01–T15 trong `tests/settlement/test_b3_proposal.py`; guards B3_REPORT_ONLY có
  test transaction thật; pipeline bỏ matcher B7 cho B3 v1 (spy), B7 giữ nguyên.
- UI E2E (Playwright, fake mode, ảnh tại `output/b3-verbal-v2-test-evidence/`):
  U01 **VERIFIED**, U02 (ledger giả lập thay PDF — xem giới hạn) **VERIFIED
  FAKE**, U04 **VERIFIED**, U05 **VERIFIED** (kể cả snapshot context cũ
  immutable), U06 **VERIFIED** (409 B3_REPORT_ONLY qua API).
- U02/U03 với PDF/PNG thật: **USER_LIVE_UNEXECUTED** — cần chủ dự án bật
  `SETTLEMENT_PROVIDER_MODE=live` (chi phí API) và chạy theo phụ lục B3 trong
  `docs/testing/SETTLEMENT_MANUAL_TEST_GUIDE.md`.
- Live OCR/LLM quality, trial ≥3 người thật, B3→B7 lifecycle và duyệt
  work/B/advance: **INCONCLUSIVE/chưa triển khai theo phạm vi plan**.
- Gói b3-verbal-v2 + oracle là synthetic single-author, không phải measured
  baseline; không dùng kết quả fake ở trên làm baseline chất lượng.

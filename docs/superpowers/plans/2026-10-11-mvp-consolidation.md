# Hợp nhất MVP — UI, code và dữ liệu

> **For agentic workers:** Dùng `executing-plans`, tuần tự bốn task; một writer giữ shared contracts. Không tự subagent/Git/LIVE/publish. Mỗi task phải có checkpoint chạy được trước khi sang task tiếp.

**Goal:** Người dùng đi đúng luồng tạm ứng→quyết toán và hiểu trạng thái/hành động; coding agent tìm được đúng nghiệp vụ/tài liệu/dữ liệu mà không cần đọc cả repo.

**Architecture:** Giữ application/policy path, SQLite và các contracts tiền hiện hành. Sửa projection/copy/navigation, tách persistence theo nghiệp vụ trong cùng transaction, đổi tên module nội bộ và hợp nhất điểm hướng dẫn. Không rebuild hoặc tạo framework mới.

**Tech Stack:** React/TypeScript/Vitest; Python/Pydantic/FastAPI/SQLite/pytest và stdlib hiện có.

**Spec:** Thiết kế giới hạn ngay trong plan này; [Product](../../settlement/PRODUCT.md), [Rulebook](../../settlement/RULEBOOK.md), [System](../../settlement/SYSTEM.md), [Evaluation](../../settlement/EVALUATION.md) giữ thẩm quyền nghiệp vụ. Không tạo thêm spec/review Markdown.

**Status:** IMPLEMENTED, 12/10/2026 (Task 1–4). Không là nghiệm thu B3–B9/LIVE.
Nhánh rebuild; kiểm lại status/diff trước execution và giữ mọi thay đổi của người khác.

**Evidence (fake mode, không LIVE/Git/publish):**

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q   # 891 passed
.venv/bin/python -m pip check                                       # No broken requirements found
npm --prefix frontend run test -- --run                             # 157 passed (25 files)
npm --prefix frontend run build                                     # tsc --noEmit + vite build OK
```

Regression đỏ→xanh “đã nhận ứng nhưng UI báo chưa phê duyệt” trong
`frontend/src/settlement/uiState.test.ts`. Store façade 3809→1997 dòng; SQL
lifecycle tách sang `sqlite_records.py`/`advance_records.py`/
`linked_context_records.py`/`settlement_records.py` (cùng transaction, không
mở connection riêng). Rename module nội bộ; wire values/persisted codes/DB/
API path giữ nguyên. Demo recipe `data/settlement/travel-demo-v1/` sinh bởi
`scripts/build_travel_demo.py` (input/company/followup/expected tách riêng).
Inventory: `output/maintenance/consolidation-inventory.json` (ignored).
**UI walkthrough: USER_UI_UNEXECUTED** — phiên agent chưa thao tác browser.
Frozen corpus/gold/DB/uploaded originals không đổi.

## Global constraints

- Không thêm nghiệp vụ, login, quyền/hạn mức, payment request, ngân hàng, microservice hoặc dependency.
- Không thay formula, unknown/pending-as-null, evidence/authority/Stop/stale/duplicate/closure gates để làm UI đơn giản.
- CaseView workflow là tiến độ hiện hành; Report là kết quả một snapshot; Run là execution. Không lấy READY/COMPLETE làm approval/receipt/closure.
- UI không tính quyền hoặc net; action navigation không cấp quyền, endpoint kiểm lại khi ghi.
- Không đổi giá trị Job/schema/API/DB/audit/persisted IDs vì đổi tên file. Legacy backend giữ cho đến khi xác minh caller và tương thích.
- Persistence helpers không mở connection/commit riêng; mọi financial checks + writes tiếp tục atomic trong một `BEGIN IMMEDIATE`.
- Không xóa DB, uploaded originals, frozen corpus/gold/policy snapshots hoặc run artifacts trong plan này. Bản sao muốn bỏ cần chứng minh generator/references/retention trước.
- Không chạy LIVE/publish/Git. Fake tests khác chất lượng AI; UI chưa thao tác ghi USER_UI_UNEXECUTED, không bypass browser denial.
- Một plan này là đủ. Cập nhật README/canonical docs hiện có; inventories/evidence dùng JSON/CSV dưới output/data ignored, không thêm các lớp Markdown.

## Thiết kế UI được triển khai

**Màn mặc định:** tên hồ sơ/người/công việc → một trạng thái hiện hành + owner → số tiền đúng nghĩa → một hành động phù hợp vai → đối chiếu/vướng mắc → nguồn/lịch sử. Thông tin kỹ thuật nằm trong vùng mở rộng. Nhãn mô phỏng/replay vẫn hiện rõ khi áp dụng, không lặp raw mode ở ba nơi.

| Trạng thái có căn cứ | Nhân viên | Kế toán | Người duyệt |
| --- | --- | --- | --- |
| Draft | Kiểm tra và gửi | Xem tiến độ | Xem tiến độ |
| Report current đủ, chưa trình | Chờ kế toán | Rà soát và trình | Chờ kế toán trình |
| Đã trình, chờ quyết định | Chờ người duyệt | Theo dõi hồ sơ | Xem và quyết định |
| Ứng đã duyệt, chưa ghi nhận nhận đủ | Xem tiến độ nhận tiền | Ghi nhận tiền thực tế | Xem quyết định |
| Đã nhận ứng, chờ quyết toán | Chuẩn bị hồ sơ quyết toán | Chờ chứng từ | Xem tiến độ |
| Quyết toán đã duyệt | Xem số cần nhận/hoàn | Đối chiếu chi/thu | Xem quyết định |
| Đã đóng | Xem lịch sử | Xem lịch sử/điều chỉnh theo quyền | Xem lịch sử |
| Stop/stale/incident/thiếu nguồn | Nêu đúng vướng mắc/owner, không dùng lời chung “nhân viên bổ sung” cho mọi lỗi | Xử lý phần thuộc mình | Xử lý phần thuộc mình |

Số xin ứng, dự toán, ngân sách được duyệt, actual và remaining có nhãn riêng; null ghi “Chưa xác định/chưa ghi nhận” đúng ngữ cảnh, không0. Link căn cứ đặt ở bảng đối chiếu hoặc nút “Xem căn cứ”, không chen vào chữ số KPI. Report lịch sử ghi thời điểm/snapshot, không tuyên bố tiến độ hiện hành.

## Task 1 — Sửa trạng thái và điều hướng trước khi trang trí

**Files:** Modify `frontend/src/settlement/uiState.ts`, `uiCopy.ts`, `App.tsx`, `Actions.tsx`, `Report.tsx`, `B7Intake.tsx`; tests `uiState.test.ts`, `uiCopy.test.ts`, `App.test.tsx`, `Actions.test.tsx`, `Report.test.tsx`, `B7Intake.test.tsx`.

**Interfaces:** Mở rộng `summarizeCase(view,run,report,context?:{role:DemoRole;actorId:string}):UiSummary` hiện có; giữ three-argument callers cho tới khi migrate. UiSummary thêm `nextOwner:DemoRole|null`, `primaryLabel:string|null`; mở primaryTarget union hiện có với `sources`, `accountant-review`, `advance-decision`, `advance-receipt`, `prepare-settlement`, `settlement-intake`, `settlement-decision`, `settlement-receipt`, `case-history`. Target chỉ điều hướng/focus, không POST. Không thêm second state engine.

- [x] **1.1 Regression đỏ cho trạng thái trái nghiệp vụ**
Đặt test dưới trong uiState.test.ts, dùng builders `createCase/createRun/createReport` đã có cùng file:
```ts
test('đã nhận ứng không bị report cũ đưa về chưa phê duyệt', () => {
  const base = createCase();
  const view = createCase({
    stage: 'AWAITING_WORK_SETTLEMENT',
    submission: { ...base.submission, form: { ...base.submission.form, confirmed: true } },
  });
  const baseReport = createReport();
  const report = createReport({ b3: { ...baseReport.b3!,
    intake: { ...baseReport.b3!.intake, confirmed: true } } });
  const summary = summarizeCase(view, createRun(), report,
    { role: 'EMPLOYEE', actorId: 'NV-01' });
  expect(summary.title).toBe('Đã nhận ứng — chờ nộp quyết toán');
  expect(summary.description).not.toContain('chưa phê duyệt');
  expect(summary.primaryTarget).toBe('prepare-settlement');
});
```
Nguồn bằng chứng: pure synthetic UI probe của hàm hiện tại trả “Đủ thông tin để kế toán rà soát; chưa phê duyệt và chưa chi ứng” với stage AWAITING_WORK_SETTLEMENT/workflow APPROVED/funding FULFILLED. Không là UI/browser test.

- [x] **1.2 Sửa projection từ workflow, không sửa backend facts**
Closed/Stop/material blockers ưu tiên; sau đó dùng b3_workflow/b7_workflow, fulfillment/revalidation/linked context, stage là fallback khi projection thiếu. Report/run chỉ được coi current khi IDs/case/input_revision/control_epoch khớp. Rerun cùng facts không reset approval; raw FAILED của run cũ không xóa receipt/quyết định hiện hành. Chỉ unresolved issues còn áp dụng mới tạo vướng mắc. Role/actor quyết định hành động điều hướng phù hợp; không quyết định quyền tài chính.
Tests thêm: approved nhưng chưa receipt; nhận một phần/pending; REFUSE giữ nghĩa vụ; B7 approved/BALANCED/closed; parent Stop/context stale; historical report không tạo current-success; resolved issue không giữ hồ sơ chờ; actor khác owner không có CTA thao tác; missing workflow fallback không giả actual.

- [x] **1.3 Làm rõ report và mở đúng linked child**
Chuyển Run ID/status/stage/usage vào details “Thông tin xử lý”; giữ một nhãn mô phỏng dễ thấy. Bỏ raw readiness và thuật ngữ actual payer khỏi màn mặc định. Đổi tiêu đề chung “Thẩm định tài chính” thành kiểm tra đề nghị/đối chiếu quyết toán phù hợp job. Bỏ duplicate success/amount blocks, giữ nguồn và con số chưa rõ. Unknown backend code vẫn lưu trong details, không render raw làm tiêu đề người dùng.
App nhận kết quả `prepareLinkedB7` và mở child.id, refetch list; không reload parent rồi bắt người dùng tìm child. App/Actions thêm callback dedicated `onPrepareSettlement():Promise<void>`; không đoán child ID từ tên hoặc amount. Existing `onAction` giữ cho mutations khác. Button confirm của B7Intake hiện chỉ save: đổi nhãn “Xác nhận nộp” và đặt chạy kiểm tra kế bên, không hứa auto-run chưa có.
Các target navigation được App map sang caseTab tương ứng và ID panel thực; bổ sung ID ở B3Approval/B3Funding/B7Approval/B7Funding nếu cần. `sources` mở tab nguồn, `prepare-settlement` mở phần chuẩn bị ở parent, các review/decision/receipt target mở panel của đúng vai; không đưa tên enum thẳng vào querySelector và im lặng khi không tìm thấy element. CTA mở panel, financial POST vẫn là thao tác có guards riêng.
Normal creation là B3 hoặc tiếp tục B7 từ công việc; generic legacy form nằm trong vùng công cụ mở rộng, giữ chức năng nhưng không quảng bá như intake chuẩn cho tự chi. Không tự tạo fake B3 ứng0. Nguồn chứng từ có đường điều hướng rõ ngay trong intake/summary.

- [x] **1.4 Verify và UI checkpoint ba vai**
```bash
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Test default screen không có raw readiness/SUCCEEDED/publishing; mở details vẫn truy vết được. Case run lỗi, source mâu thuẫn và action blocked vẫn có thông tin thực chất. Trên UI: B3 submit→review→approve→receipt→prepare child→upload→confirm B7; accountant/approver không thấy form employee edit; next-step navigation mở đúng panel/case. Không claim UI VERIFIED từ render tests. Không cần backend refactor để hoàn thành task1.

## Task 2 — Tách trách nhiệm code và đặt tên theo nghiệp vụ

**Files:** Modify `src/invoice_referee/settlement/store.py`, `service.py`, imports/callers/tests trực tiếp; create `sqlite_records.py`, `advance_records.py`, `linked_context_records.py`, `settlement_records.py`. Rename `b3_funding.py→advance_reconciliation.py`, `b3_workflow.py→advance_workflow.py`, `b7_linked.py→linked_context.py`, `b7_workflow.py→settlement_workflow.py`, `b7_fulfillment.py→settlement_reconciliation.py`; TS `B3Funding.tsx→AdvanceReceiptPanel.tsx`, `B7Funding.tsx→SettlementReceiptPanel.tsx` cùng export/import/test names. Không đổi B3/B7 models/Job/schema. Không chia models/types chỉ để giảm số dòng ở lượt này.

**Boundaries:** Store là public façade giữ signatures đang được Service/API/tests dùng và owns connection/transaction. SQL lifecycle functions nhận `conn:sqlite3.Connection`, không Store/callback quay lại façade, không tự `_write`/commit. Pure reconciliation/workflow modules giữ tính toán/basis/grants, không SQL. Không mixins/base repository/plugin registry.

**Interfaces mới:**
- sqlite_records chuyển private common helpers hiện có thành module functions: `case_row(conn,case_id)->sqlite3.Row`, `run_row(conn,run_id)->sqlite3.Row`, `source_records(conn,case_id)->list[SourceRecord]`, `lookup_command(conn,operation,command,scope_key)->sqlite3.Row|None`, `check_replay(row,payload_fp)->None`, `check_version(case,command)->None`, `check_open(case)->None`, `record_command(conn,case_id,scope_key,kind,operation,command,payload_fp,detail,now)->None`. Chuyển SQL/serialization nguyên semantics; không helper này đọc financial policy.
- advance_records: `workflow_view(conn,case_id)->B3WorkflowView|None`, `advance_events(conn,case_id)->list[B3AdvanceEventView]`, `record_presentation(conn,case_id,payload,command,context,policy)->B3PresentationView`, `record_decision(conn,case_id,payload,command,context,policy,grant_ref,effective_at)->B3DecisionView`, `record_receipt(conn,case_id,payload,command,context)->B3AdvanceEventView`. Types theo Store public signatures hiện có.
- linked_context_records nhận conn + artifact_root:Path cho prepare/revise/company packet/context source/parent fingerprint. Case mutations trả `(case_id:str,idempotent_replay:bool)`; Store dựng `_case_view` trong cùng transaction. Context read trả LinkedB7ContextSnapshot/SourceRecord như hiện có, không mở connection thứ hai.
- settlement_records chứa B7 presentation/decision/receipt/revalidation/handoff/closure/adjustment và read projections. Các hàm giữ tên/public args/return types của Store tương ứng, thêm conn và artifact_root khi cần file; bỏ self. Shared parent/B3 reads gọi advance_records, context gọi linked_context_records. CaseView update returns tuple như trên; typed record actions trả View hiện có. Không dependencies ngược từ advance_records sang settlement_records.

- [x] **2.1 Baseline regression trước chuyển code**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
```
Ghi actual failures/count, không dùng counts walkthrough cũ. Bổ sung regression cần thiết nếu chưa có: rollback presentation giữ REVIEW count; receipt đúng không mất approval; pending/overpay/wrong recipient không đóng; Stop/stale giữa read/commit; idempotent replay trước version; same-event aliases không double count. Scope assertions trên DB/audit và View, không chỉ HTTP.

- [x] **2.2 Extract lần lượt advance→linked context→settlement**
Mỗi nhóm move cùng read helpers/callers; Store wrapper mở transaction một lần. Ví dụ wrapper sau khi chuyển nguyên receipt guards vào advance_records:
```python
def record_b3_advance(self, case_id, payload, command, context):
    with self._write() as conn:
        return advance_records.record_receipt(conn, case_id, payload, command, context)
```
Không chẻ checks ra ngoài transaction. Các lookup/fingerprint/source/write/order/unknown semantics giữ nguyên. Không sửa bug nghiệp vụ mới lẫn mechanical extraction: phát hiện thì ghi vấn đề riêng, không đổi oracle để pass. Thin façade wrappers có consumer thật Service/API nên giữ; không nhân thêm façade song song.
Chạy focused B3 tests sau nhóm advance; linked tests sau context; B7 workflow/fulfillment/revalidation/closure/adjustment sau settlement. Sửa direct Store callers và signatures trong cùng nhóm, không để đoạn code dead hoặc dual writers. Các operations generic cũ ở Store giữ guard và đánh dấu internal legacy; chưa xóa khi chưa xác minh consumers.

- [x] **2.3 Extract frontend theo việc người dùng**
Create `SourceUploadPanel.tsx` (queue/upload/provenance/progress/error) và `ProcessingDetails.tsx` (run trace/debug); move trạng thái/handlers tương ứng ra khỏi App. SourceUploadPanel props `{view,role,actorId,onChanged:(caseId:string)=>Promise<void>,onError:(message:string)=>void}`; giữ multi-upload đã có, sequential versions/idempotency/partial failures. Case đổi reset queue; upload thành công một phần phải giữ file chưa upload, không để refetch làm mất queue. Không dedup theo name+size rồi bỏ file khác bytes; muốn skip file phải có căn cứ hoặc người dùng chủ động bỏ.
ProcessingDetails props `{run:RunView|null,report:Report|null}`; không fetch/provider side effects. App giữ selected case/loading/navigation/persona, không toàn bộ source workflow. Các panel nghiệp vụ đang có tiếp tục dùng, không làm component framework/schema-driven form. Đổi tên tiền ứng/quyết toán trong imports/copy theo scope, không rename wire values.

- [x] **2.4 Integration checks và checkpoint**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Test mixed upload success/failure/retry/reload/case switch. Run B3→B9 fake qua same Service/Store/API, compare money/stages/records trước-sau; không snapshot expected từ engine. Báo responsibility đã chuyển, số dòng/call dependencies trước-sau, không đặt tùy tiện mọi file phải <300 dòng. File nhỏ nhưng cyclic imports/transaction bị phá là FAIL.

## Task 3 — Một điểm hướng dẫn và một recipe demo nhất quán

**Files:** Update README.md, docs/settlement/PRODUCT.md/SYSTEM.md/EVALUATION.md capability sections, docs/testing guides cần sửa, packet README metadata. Reuse `data/settlement/worked-example-v1/build_packet.py` và b3-verbal-v2 generator đã có làm nguồn tham khảo; nếu cần tracked generator mới, tạo `scripts/build_travel_demo.py`, không đưa demo generator vào application.

**Recipe contract:** Demo mới ở `data/settlement/travel-demo-v1/`, không ghi đè worked-example/frozen datasets. Generator args `--work-ref`, `--output-dir`, `--settlement-as-of`; employee NV-DEMO-01/company/personas hiện có. employee-input/company-input/followup/expected tách riêng; manifest filename/doc role/work/actor/date/hash/duplicate variants. File tên nghiệp vụ, không chỉ K01/X02. Source IDs do API cấp sau upload: company packet template có doc references và hướng dẫn bind retained IDs, không fake `company:ref` thành source tự tin.

- [x] **3.1 Cập nhật điều hướng thay vì thêm guide**
README một bảng “hiểu nghiệp vụ / chạy demo / đánh giá / lịch sử” và entrypoint hiện hành duy nhất ở hướng dẫn chính. Commands legacy ở section lịch sử; B7 development20/replay5/LIVE mục đích khác nhau ghi rõ. Packet B3 v2 README phân biệt metadata lúc tạo với current capabilities. Completed plans là lịch sử triển khai, không second rulebook; cập nhật nhãn/links, không rewrite frozen policy theo rules hôm nay. System mô tả module map thực sau task2, không append tiếp một bài giải thích dài.

- [x] **3.2 Chuẩn bị demo theo đúng case thực hiện**
Xuất nguồn synthetic cho 3 khoản nhân viên 3M/1M/1M, receipts phù hợp, company flight3M, advance receipt2M cùng identity dùng ở B5, company coverage tới mốc sau chuyến đi và B7 rights riêng. JSON/proofs/form profile consistent employee/work/trip/time; không gộp followup reimbursement3M vào initial B7. Expected literal T8/E5/A2/RA0/P0/RP0/S3; sau receipt3 và gates S0. Không tự gán absence0 thiếu coverage.
Native/scan/PDF/text paths giữ các mục đích riêng. Fake demo dùng structured ledger/typed sources được Reader hiện có hỗ trợ; PDF/image demo dùng đường LIVE chỉ khi user cho phép, không gọi provider trong task này. Generator không nhét expected/net vào prompt inputs. Tái tạo giữ nghĩa/tính hash minh bạch; PDF metadata timestamp không được coi hash ổn định nếu chưa chứng minh. Người dùng nhập work-ref của hồ sơ liên kết, không sửa mã work trên server để khớp bộ cũ.
Không thêm dependency vào app vì generator; tái sử dụng tool/runtime PDF có sẵn khi cần, ghi requirement trên command. Manifest là index, không thêm nhiều README riêng cho từng file.

- [x] **3.3 Checkpoint: một người có thể test theo guide**
Trong guide B6/B7 hiện có, ghi exact file nào nhân viên upload, field nào khai, nguồn nào kế toán quản lý, thời điểm phải refresh/run và bước người duyệt. Template không là verified facts; HUMAN_SOURCE_REVIEW/preparation effort vẫn ghi nhận. Kiểm links/file roles/dates/owning refs/hash; không benchmark AI từ fake PDF failure. Giữ corpus đánh giá độc lập khỏi demo khi đo.

## Task 4 — Kiểm kê và tinh gọn có giới hạn, rồi nghiệm thu

**Files:** Existing README/guides/links; inventory `output/maintenance/consolidation-inventory.json` (ignored). Không thêm report/spec Markdown. Không sửa corpus/gold/DB.

- [x] **4.1 Inventory phân loại trước mọi đề xuất bỏ**
Ghi path/tracked-or-ignored/size/hash/owner/purpose/generator/references/lifecycle và KEEP/ARCHIVE/REGENERATE_CANDIDATE. Exclude .git/.venv/node_modules/.agents và private source content; metadata đủ cho bước này. Exact byte copies khác native/scan variants. Không đổi scope từ cognitive cleanup thành xóa mọi “file rác”.
Ưu tiên PDF output/input trùng byte và latest pointers có thể regenerate; xác minh references như WORKED_EXAMPLE trước khi đề xuất bỏ. Runtime artifacts giữ source ID/run association, frozen data giữ nguyên bytes. Bản có reference hoặc chưa chứng minh regeneration giữ KEEP. File không rõ owner/lifecycle giữ REVIEW_REQUIRED.

- [x] **4.2 Giảm context hoạt động, giữ provenance**
Update README/AGENTS routing nếu paths đổi thật; task chỉ load canonical + assigned plan + selected packet. Đánh dấu superseded guides/plans ở metadata hoặc links hiện có; không tự load archive. Không archive/delete cả thư mục đang có caller. Plan này không authorize xóa DB/uploaded evidence/frozen files; danh sách removal cần review riêng. Chọn một bộ demo mặc định không biến nó thành holdout hoặc baseline chất lượng.

- [x] **4.3 Final checks**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
So frozen input/policy/gold hashes trước-sau, kiểm link/command docs và persisted B3/B7/API regression. GUI/browser được phép: employee→accountant→approver từng checkpoint, nguồn mở được, action có reason, Stop/partial/incident đúng. Nếu chưa thao tác thật ghi USER_UI_UNEXECUTED; không gọi screenshots/tests là professional trial. Ghi evidence trong plan này và JSON inventory; không claim cải thiện effort/quality nếu chưa đo với người thực.

## Done và giới hạn

Done khi current workflow không bị report cũ phủ định; normal UI không phơi raw engine enum nhưng debug truy vết còn; linked child mở đúng và upload cạnh intake; các vai có next step rõ; Store façade có boundaries không phá transaction; tên nội bộ theo nghiệp vụ/wire values stable; một recipe demo đúng scope; docs navigation không dẫn người mới vào legacy; frozen/evidence không mất; tests + UI evidence được báo đúng mode.
Không coi giảm số file/dòng là mục tiêu tự thân. Shared models/types còn lớn không tự fail; không có deletion được chứng minh thì giữ. LIVE quality/holdout/trials và thay đổi core nghiệp vụ nằm ngoài lượt hợp nhất này.

## Prompt cho coding agent

```text
Thực hiện docs/superpowers/plans/2026-10-11-mvp-consolidation.md theo task1–4.
Đọc AGENTS.md và các sections canonical cần cho task, không nạp cả docs/archive.
Sửa trạng thái và navigation trước; chứng minh regression “đã nhận ứng nhưng UI
báo chưa phê duyệt” rồi triển khai. Review checkpoint UI trước refactor lớn.
Giữ API/schema/policy/financial gates; tách SQL lifecycle theo cùng connection/
transaction, không viết framework hoặc bỏ guard để giản lược. Giữ multi-upload
đã có và partial failure queue. Chuẩn hóa tên module, không rename persisted codes.
Hợp nhất README/docs và tạo một demo recipe đúng work/time/source identity;
không trộn gold/followup vào inputs. Inventory trước cleanup, không xóa DB,
originals/frozen data/run evidence. Không LIVE/Git/publish/subagent tự động.
Chạy checks theo task, báo actual mode/exit/count và UI chưa kiểm; không dùng
green unit tests để claim người dùng thao tác được hoặc AI đã đạt baseline.
```

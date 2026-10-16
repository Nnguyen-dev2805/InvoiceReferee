# Clean refactor design — agent-workability & readability

Status: **DRAFT for user review** — 2026-10-16. Chưa thực thi. Mọi thay đổi code chờ hết
cửa sổ cuộc thi (mặc định sau Demo Day 17/10) và lệnh authorize của user.

Authority: tài liệu này chỉ định **cấu trúc** (file/module/layout). Hành vi sản phẩm vẫn
thuộc [IMPLEMENTATION_CONTRACTS](../../final/IMPLEMENTATION_CONTRACTS.md) và
[ARCHITECTURE_AND_EVALUATION](../../final/ARCHITECTURE_AND_EVALUATION.md) — không đổi tại đây.
Quyết định cấu trúc được ghi thành ADR-0012…0014 (mục 7).

Plan thực thi: [2026-10-16-clean-refactor](../plans/2026-10-16-clean-refactor.md).
Nguồn bằng chứng: 5 subagent audit read-only + spot-check độc lập (16/10, `main@63b3dad6`,
worktree sạch). Chi tiết độ tin cậy ở mục 3.4.

## 1. Mục tiêu & phạm vi

Mục tiêu kép (do user chốt 16/10):

1. **Agent-workability** — coding agent đọc/định vị/sửa chính xác hơn với ít ngữ cảnh hơn:
   file không vượt ngân sách đọc, ranh giới module rõ, không dead code, không hai thế hệ
   code song song, docs làm bản đồ.
2. **Readability cho người** — hiểu nhanh hơn: hàm có tên các bước, một nguồn sự thật cho
   constants/helpers, cây thư mục tự giải thích.

Trong phạm vi: `src/`, `tests/`, `frontend/src/`, docs/repo-as-context.
Ngoài phạm vi: hành vi sản phẩm, contracts/DTO/schema/DB, stack (SQLite/FastAPI/React),
quy trình nghiệp vụ, bug hành vi (đi workflow bug riêng — mục 9).

KPI tổng: xem mục 6.3 (baseline 16/10 → đích).

## 2. Tiêu chí "clean" (research áp dụng)

Chưng cất từ: Clean Code (Martin) — hàm nhỏ, tên nói ý định, tests hạng nhất, smells;
Refactoring 2e (Fowler) — refactor không đổi hành vi quan sát được, "two hats", Extract
Function→Class/Module; A Philosophy of Software Design (Ousterhout) — deep module,
complexity = change amplification + cognitive load + unknown unknowns; Working Effectively
with Legacy Code (Feathers) — seam + characterization test trước khi phẫu thuật vùng khó;
thực hành agent-context 2025–2026 (AGENTbench/ETH: context do LLM viết có thể hại — ưu tiên
thông tin người viết, không suy diễn được).

Vận dụng thành 5 tiêu chí đo được cho repo này:

1. **Sửa hình dạng, không sửa hành vi** — suite hiện có là lưới an toàn; vùng thiếu test
   phải có characterization test trước.
2. **Đơn vị vừa ngữ cảnh** — file module đọc được trong một lượt; hàm dài phá thành các
   bước có tên. Ngân sách: module thường ≤600 dòng (phấn đấu), trần cứng 1.000 dòng có
   ngoại lệ ghi rõ; không hàm >300 dòng còn lại trong `src/`.
3. **Ranh giới deep** — interface nhỏ, tham số tường minh (`cx`, `session`, `row` như hiện
   có); không pass-through; không private coupling xuyên module.
4. **Một nguồn sự thật** — mỗi logic dùng chung (text, hashing, dates, refs, limits) một
   bản; biến thể có chủ đích phải đặt tên + docstring nêu khác biệt, không hợp nhất mù.
5. **Không nhiễu** — dead code = 0 (kèm quyết định ghi lại); mỗi vùng một thế hệ code;
   docs có bản đồ current-vs-history; clone mới đọc được entry point cho agent.

## 3. Baseline chẩn đoán

### 3.1 Quy mô (16/10/2026)

| Vùng | Số liệu |
|---|---|
| `src/invoice_referee/` | 72 file `.py`, **21.485 dòng**; `workflow/service.py` = 6.245 dòng (**29%**) |
| `tests/` | 107 file, **~20.415 dòng**, 756 `def test_` (781 collected theo status) |
| `frontend/src/` | ~4.800 dòng (+ tests 1.639 dòng / 11 file) |
| Docs tracked | contracts 930d; design 651d; status 659d; reviews 53 file (~92k từ ≈ 40% docs) |
| Chi phí ngữ cảnh 1 task điển hình | ~410 dòng/~4.900 từ (đọc tối thiểu theo AGENTS.md); ~1.070 dòng nếu đọc trọn status |

### 3.2 Sáu cụm vấn đề (bằng chứng ở Phụ lục A–D)

- **A. God files & hàm khổng lồ**: `service.py` 6.245d (93 method, 169 câu SQL, 76 local
  import); `admission.py` 1.114d (`admit_evidence` 489d); `linking.py` 977d
  (`link_advance_multifield` 517d); `pipeline.py` 781d (`read_root` 419d); `routes.py`
  761d; và trong service: `_advance_activity_link` 504d, `_record_actual` 453d,
  `_assess_and_commit` 367d, `read_employee_return_draft` 330d, `_case_view` 300d.
  Frontend: `intake.tsx` 941d, `advance.tsx` 659d, `questions.tsx` 630d, `App.tsx` 584d.
- **B. Trùng lặp**: chuẩn hóa text/diacritics **9 bản**; gom `EvidenceRefs` **8 bản**;
  canonical JSON+sha256 **8+ bản**; field accessor **7 bản**; `8_000_000/4_000_000` **2
  nơi** (`reconciliation/policy.py:17-18` vs `reconciliation/admission.py:59-60`);
  `_budget_for` 2 bản diff = IDENTICAL; `_parse_dt` 2 bản + 28 `fromisoformat` inline.
- **C. Dead code / planned-unwired**: ước tính ~350–400 dòng src + ~900–1.200 dòng test.
  Ba nhóm xử lý khác nhau (Phụ lục B): 0-caller (xóa thẳng); test-only (xóa kèm test);
  planned-unwired (`confirm_admissibility` plan:119, `propose_step` plan:158, `QuestionCard`
  plan:T6) — phải đối chiếu contracts trước (P0.4).
- **D. Hai thế hệ song song**: đọc evidence per-page vs file-level (chọn nhánh
  `service.py:5453-5479`); snapshot builder STUB (`snapshots.py:78-387`) vs typed
  (`evidence_assessment.py:137-184`); context import demo vs company (`runtime.py:63-68`);
  tracing `trace.py` vs `telemetry.py`; production→`evaluation.models` (lệch tầng;
  pattern đúng có sẵn ở `organization.py:9`).
- **E. Test suite**: không marker taxonomy (không chạy được subset); `conftest.py` 647d
  (5 trách nhiệm; còn ghi SQL trực tiếp `conftest.py:300-304` trái docstring);
  builder lặp (`_paper/_invoice` ≥15 file; `_report` 19 file; `Database()` 33/54 file;
  `CommandContext` dựng tay ~40 lượt/20 file; `FakeLlm`×3; `FakeClient`×3; reader giả ≥7);
  file test lớn nhất 1.116d; 7 module src không có test trực tiếp (Phụ lục D).
- **F. Repo-as-context**: `AGENTS.md` + `GLOSSARY.md` bị git-ignore (`.gitignore:6-7`) →
  clone mới mất entry point + từ điển, link tracked chết; status 659d lẫn nhật ký (330d
  trước "Current handoff", thứ tự ngày vỡ); lệch pha README:116 / README vs RUNBOOK
  hosting / plan T12 suite `holdout` không tồn tại / status ghi branch sai; "no subagent"
  trong 11+ file vs thực tế; 6 link chết tracked (+56 trong slides ignored).

### 3.3 Điểm đã kiểm chứng độc lập (spot-check 16/10)

- Dead code: `recover_incomplete` chỉ có caller test; `confirm_admissibility` chỉ test+plan.
- `8_000_000/4_000_000` đúng 2 nơi như Phụ lục C.
- `datetime.now` bỏ qua injected clock đúng 4 chỗ: `service.py:4474,4914,5045,5933`.
- `AGENTS.md`/`GLOSSARY.md` bị ignore đúng `.gitignore:6-7`.
- Import production→`evaluation.models` đúng `pipeline.py:21`, `snapshots.py:23`,
  `service.py:879/5783/5793`.

### 3.4 Độ tin cậy bằng chứng

Đã verify: LOC/khối lượng (wc/grep), cấu trúc hàm, danh sách dead code (grep toàn repo),
duplication (đọc/diff thân hàm), test inventory. UNVERIFIED: chưa chạy test/build trong
audit; line refs là snapshot `main@63b3dad6` (verify lại trước khi sửa); codegraph index
có thể chưa phủ commit mới nhất; một số nhận định "xâm lấn test" là đánh giá từ import,
chưa chạy thực tế.

## 4. Kiến trúc đích (TO-BE)

### 4.1 Ngân sách

| Đơn vị | Đích |
|---|---|
| File `src/*.py` | ≤600d phấn đấu; trần 1.000d (ngoại lệ ghi rõ trong status/plan) |
| File trong `workflow/` sau P3 | mỗi file ≤800d |
| Hàm | không hàm >300d trong `src/`; các hàm >150d mới phải chia bước có tên |
| File test | ≤500d; builder/stub dùng chung thay bản cục bộ |
| Docs hiện hành | mỗi file ≤~200d (contracts là spec — ngoại lệ có chủ đích) |

Không có migration DB trong toàn bộ chương trình: 100% thay đổi tổ chức code.

### 4.2 `workflow/` đích

- `workflow/service.py` — giữ nguyên vị trí import và **toàn bộ public method
  signatures** (contracts §9): `CaseWorkflow` là façade + transaction owner.
- Pure extraction (thuần, tham số tường minh, không import vòng):
  - `workflow/advance_link.py` — vùng H (`service.py:3156-3659`, gần-pure, nhận 2
    callback `_snapshot_ledger_entry`, `_tenant_company_name`).
  - `workflow/framework.py` — helpers N (`service.py:5877-5945`: `_require_root`,
    `_require_version`, `_bump`, `_reload`, `_audit`, `_query_one`).
  - `workflow/authority.py` — nhóm grant/money (`service.py:4904-5069`).
  - `workflow/case_view.py` — các sub-builder của `_case_view` (5 khối đọc thuần).
  - Assessment helpers (`_economic_keys_for`, `_transcription_for`, `_derive_state`,
    `_build_assessment_input` — `service.py:5437-5836`) về module assessment.
- PA-C (bước đệm rẻ, chốt trong ADR-0012): tách phần còn lại thành mixin modules trong
  `workflow/case/` (`commands.py`, `drafts.py`, `money.py`, `assessment.py`, `views.py`,
  `framework.py`); `service.py` chỉ còn assembly + `__init__` + `execute` + seams.
  Quy tắc: tên method/helper giữ nguyên; mixin không import lẫn nhau; base framework cuối
  MRO.
- PA-A (commands registry) / PA-B (collaborator classes): **hoãn** — ghi nhận trong
  ADR-0012; chỉ mở lại nếu sau P3 vẫn chưa đạt ngân sách, và với characterization đầy đủ.

### 4.3 `reconciliation/` + `evidence/` + `api/` đích

- `reconciliation/admission/` package: `fields.py` (helpers 67-208), `history.py`
  (277-364), `binding.py` (365-593), `admit.py` (`admit_evidence` 489d tách theo stage),
  `index.py` (claim index 1083+); `admission/__init__.py` re-export giữ nguyên điểm import.
- `reconciliation/linking/` : `link_advance_multifield` (517d) tách theo stage
  normalize → scan/score → tie-break → assemble; giữ façade `link_advance_multifield`.
- `evidence/pipeline.py`: tách trace-serialize (57-227) và STUB transcribe (228-360)
  khỏi pipeline thật; `read_root` giữ điểm vào qua re-export.
- `api/routes.py`: chia router theo nhóm route; phần chạy evaluation trong `/verify`
  chuyển thành helper ngoài handler (giữ nguyên hành vi HTTP).
- `evidence/extraction.py` (508d) và `workflow/context_records.py` (511d): tách nhẹ khi
  P4 chạm tới, không bắt buộc nếu ≤600d sau P1.

### 4.4 `tests/` đích

- `tests/builders/` (documents, reads, workflow factory), `tests/stubs/` (Llm/Client/
  readers), conftest mỏng theo tầng (root/integration), seed SQL đặt tên rõ
  (`seed_transcription_for_test()`).
- Marker taxonomy: `slow` (+ `--strict-markers`); subset nhanh `-m "not slow"` được
  tài liệu hoá; mặc định `pytest` vẫn chạy toàn bộ (không đổi ngữ nghĩa CI).
- File >500d tách theo cụm chủ đề (Phụ lục D).
- Giữ nguyên số lượng test hành vi; không đổi ngữ nghĩa assert khi tái cấu trúc.

### 4.5 `frontend/src/` đích

- `lib/money.ts`, `lib/datetime.ts` (chuẩn `Asia/Ho_Chi_Minh`), `lib/labels.ts`
  (hợp nhất `formatIssueTarget` đã diverge + labels).
- Tách `intake.tsx` → `features/intake/` (Upload/Review/draft mapping) +
  `hooks/useCasePolling.ts`; `questions.tsx` → `features/questions/` (formatting,
  settlementTables, QuestionCard); `advance.tsx` → hook `useAdvanceDraft`.
- `components/` primitives (Alert/Field/FileInput); `api.ts` → `api/client.ts` + dto;
  giữ nguyên `data-testid` được tests bám.

### 4.6 Docs & repo-as-context đích

- `AGENTS.md` + `GLOSSARY.md` được **track vào git**; AGENTS.md giữ mỏng, trỏ
  `docs/INDEX.md`.
- `docs/INDEX.md` — bản đồ repo (~60d): mỗi living doc 1 dòng (mục đích, thẩm quyền,
  "read when", độ dài) + quy tắc "review archive chỉ đọc theo trích dẫn".
- `IMPLEMENTATION_STATUS.md` ≤100d (hiện tại) + `docs/final/status-log/2026-10.md`.
- Archive các doc lịch sử vào `docs/archive/`; `reviews/README.md` index 53 review.
- Một bảng Commands duy nhất (deterministic/cần-provider/config riêng).

## 5. Lộ trình pha (chi tiết task trong plan)

| Pha | Nội dung | Rủi ro | Gate chính |
|---|---|---|---|
| **P0** | Doc-only: ADR-0012…0014; đối chiếu contracts cho planned-unwired; chốt baseline + open questions | Rất thấp | ADRs accepted; danh sách dead code P1 chốt |
| **P1** | Quick wins: dead code đợt 1; gom helper trùng; sửa lệch tầng; test markers; docs quick (INDEX, fix drift, track AGENTS/GLOSSARY) | Thấp | Full pytest + frontend tests xanh; LOC delta ghi lại |
| **P2** | Test suite làm điểm tựa: builders/stubs/factory; conftest; tách file >500d; parametrize; đo runtime; frontend builders + act | Thấp–TB | Pytest xanh; subset nhanh chạy được; thời gian đo ghi lại |
| **P3** | `service.py`: P3.0 characterization 5 hub → P3.1 pure extraction → P3.2 PA-C mixin → P3.3 đánh giá | **Cao** | Mọi file `workflow/` ≤800d; contracts §9 không đổi; suite xanh |
| **P4** | God files còn lại: admission, linking, pipeline, routes, extraction/context_records | TB | Điểm import công khai ổn định (re-export); suite xanh |
| **P5** | Frontend: libs → tách file → primitives → types | TB | Build exit0; vitest xanh; browser checkpoint UI chính |
| **P6** | Repo-as-context: status split, archive, reviews index, commands table, AGENTS.md trim | Thấp | Clean-clone check pass; không link chết tracked |

Thứ tự rationale: P1+P2 tạo nền an toàn + feedback nhanh **trước** khi phẫu thuật
service.py (P3); P4 cùng kỹ thuật; P5/P6 độc lập, làm sau vì ít chặn nhau.

## 6. Chiến lược kiểm chứng

### 6.1 Characterization tests trước P3 (viết test, không sửa src)

| Hub | Hành vi cần pin | Test liên quan hiện có |
|---|---|---|
| `_record_actual` (S:4149) | record money + instruction lifecycle + idempotency (reversal/partial/overpay) | test_money_execution, test_managed_money_history, test_coverage_confirmation |
| `_submit` + binding (S:2508-2882) | binding decision tree, declaration revision, job enqueue | test_advance_draft_api, test_settlement_link_submit, test_draft_activity_binding |
| `_answer_issue` (S:2883) | 4 nhánh nguồn + guard stale/wrong-owner | test_evidence_finance_workflow, test_coverage_confirmation |
| `_assess_and_commit` + `_commit_assessment` (S:5070+) | commit assessment, usage-registry dedup, Stop atomicity | test_submit_handoff/routine, test_evidence_finance_workflow |
| `execute` (S:1150) | fingerprint idempotency, command_log, transaction boundary | test_root_session, test_submit_job |

Trước P4: pin thêm `admit_evidence` (stage order + arithmetic gate),
`link_advance_multifield` (score/tie-break), `read_root` (stage sequence + failure
branches).

### 6.2 Gate mỗi bước (behavior-preserving)

- Trước & sau mỗi bước: `rtk proxy uv run pytest -q` (781 collected) — xanh; frontend:
  `npm --prefix frontend test -- --run` + `npm --prefix frontend run build` khi bước chạm
  frontend; stub mode, **không LIVE**.
- Mỗi bước nhỏ, một commit-checkpoint (chỉ khi được authorize); `git diff --check`.
- Public API (contracts §9) và DB schema bất biến; nếu test hiện có phải sửa để xanh →
  dừng, ghi nhận — gần như chắc chắn đã vi phạm "no behavior change".
- Sau khi di chuyển file lớn: làm tươi index codegraph theo
  [CODE_DISCOVERY](../../final/CODE_DISCOVERY.md) và spot-check discovery.

### 6.3 Metrics baseline → đích

| Metric | Baseline (16/10) | Đích |
|---|---|---|
| File src >1.000d | 2 (service 6.245; admission 1.114) | 0 (ngoại lệ ghi rõ) |
| File src >600d | 7 (Phụ lục A) | ≤3 có lý do ghi lại |
| Hàm >300d trong src | 8 (Phụ lục A) | 0 |
| Dead code src | ~350–400d + ~900–1.200d test | 0 kèm quyết định ghi lại |
| Mẫu dup ≥7 bản | 4 (text 9; refs 8; hashing 8+; accessor 7) | mỗi mẫu 1 nguồn / biến thể có tên |
| File test >500d | 5+ | ≤3 |
| Context cost 1 task | ~410–1.070d phải đọc | ≤~350–400d |
| Clone mới | thiếu AGENTS.md/GLOSSARY; 6 link chết | tracked + INDEX + 0 link chết tracked |

Cách đo: wc sort (như audit), đếm dead code bằng grep + codegraph, thời gian pytest,
link check, và đếm dòng đọc theo hành trình AGENTS.md. Ghi lại trước/sau mỗi pha.

## 7. Quyết định cần ghi thành ADR (P0)

- **ADR-0012 — Workflow service decomposition**: pure extraction + PA-C mixin; giữ
  `CaseWorkflow` vị trí import + public methods (contracts §9); PA-A/B hoãn; áp ngân sách
  4.1. Reviewed alternatives: PA-A registry, PA-B collaborators (lý do hoãn: rủi ro cao
  hơn + xâm lấn test, chưa cần cho mục tiêu kích thước).
- **ADR-0013 — Single-source shared helpers**: hợp nhất bản sao THỰC SỰ trùng (text,
  hashing, dates, refs collector, limits 8m/4m, `_budget_for`); biến thể có chủ đích
  (ref-match semantics linking vs admission) giữ nguyên, đặt tên/docstring nêu khác biệt.
- **ADR-0014 — Repo-as-context structure**: track `AGENTS.md`/`GLOSSARY.md`; thêm
  `docs/INDEX.md`; status ≤100d + status-log; archive tài liệu lịch sử; reviews index.

## 8. Rủi ro & giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Behavior drift khi tách hàm lớn | Cao | P3.0 characterization trước; giữ nguyên tên method; suite mỗi bước; dừng nếu test phải sửa |
| Test bám private (`workflow._*` 13 file; `wf._clock` 4 chỗ) | TB | PA-C không đổi tên; chỉ đổi tên khi buộc, có audit grep trước |
| MRO/mixin collision | TB | tên helper unique; base framework cuối MRO; compile + suite check |
| Import vòng khi tách (linking↔actual) | TB | pure extraction nhận callback tường minh; mixin không import lẫn nhau |
| Codegraph index stale sau move | Thấp | re-index + spot-check trước khi tiếp tục |
| Scope creep / bug-fix lẫn vào | TB | Non-goals mục 1; bug hành vi sang backlog riêng (mục 9) |
| Đụng runtime/live DB của user | Thấp | nhánh riêng; stub; tmp DB; không đụng `.runtime/`; không chạy LIVE |
| Thêm dependency ngoài kế hoạch | Thấp | mọi dep mới cần user chốt (kể cả pytest-xdist) |

## 9. Ngoài phạm vi nhưng đã ghi nhận (backlog bug — workflow riêng)

- Clock bypass 4 chỗ: `service.py:4474,4914,5045,5933` (`_audit` staticmethod dùng
  `datetime.now` thay `self._clock`).
- Nghi vấn thứ tự digest: `_evidence_basis` ORDER BY source_id (`S:563`) vs
  `_reusable_report` so sorted digest (`S:694-699`) — có thể reuse âm tính giả.
- Replay wiring: `runtime._wire_replay` bọc `ReplayReader` trong `FileOcrReader` nhưng
  `FileOcrReader.read_source` gọi `provider.ocr_file` trong khi `ReplayReader` chỉ có
  `ocr_page` — nghi vấn source-level, cần xác minh runtime.
- Mọi phát hiện mới trong quá trình refactor: ghi vào backlog, không tự sửa hành vi.

## 10. Điểm chờ user chốt

1. Ngân sách kích thước (mục 4.1) — xác nhận hoặc chỉnh.
2. Track `AGENTS.md` + `GLOSSARY.md` vào git — xác nhận (đề xuất: có).
3. Nhánh thực thi (đề xuất `refactor/clean-2026-10`) — chốt khi mở khoá.
4. Optional deps P2 (pytest-xdist/cov) — quyết khi có số đo runtime.
5. Thời điểm mở khoá thực thi code (mặc định sau Demo Day 17/10; P0 doc-only chạy được ngay).

---

## Phụ lục A — File & hàm lớn (snapshot `main@63b3dad6`)

File src >475d: `workflow/service.py` 6245 · `reconciliation/admission.py` 1114 ·
`reconciliation/linking.py` 977 · `evidence/pipeline.py` 781 · `api/routes.py` 761 ·
`workflow/context_records.py` 511 · `evidence/extraction.py` 508 · `evidence/trace.py` 496 ·
`evidence/telemetry.py` 483 · `evidence/matching.py` 475.

Hàm dài nhất: `link_advance_multifield` 517d (`linking.py:226-742`) ·
`_advance_activity_link` 504d (`service.py:3156-3659`) · `admit_evidence` 489d
(`admission.py:594-1082`) · `_record_actual` 453d (`service.py:4149-4601`) · `read_root`
419d (`pipeline.py:363-781`) · `_assess_and_commit` 367d (`service.py:5070-5436`) ·
`read_employee_return_draft` 330d (`service.py:1704-2033`) · `_case_view` 300d
(`service.py:5946-6245`).

Frontend >450d: `intake.tsx` 941 · `advance.tsx` 659 · `questions.tsx` 630 · `App.tsx` 584 ·
`dashboard.tsx` 525 · `document_viewer.tsx` 453.

## Phụ lục B — Dead code (đối chiếu P0.4 trước khi xóa)

- **0-caller (cả test)**: `APPROVER_LIMIT` (`policy.py:19`), `_has_grant_ignoring_amount`
  (`policy.py:110-121`), `_KNOWN_UNCAPPED` (`category.py:29-31`),
  `_invoice_is_employee_paid_basis` (`admission.py:534-545`), `cost_basis_digest`
  (`snapshots.py:388-398`), `null_operation` (`telemetry.py:323-328`), `write_manifest`
  (`packets.py:302-305`), `entry_from_packet` (`packets.py:372-396`), `QuestionCard`
  (`domain/issues.py:40-48` — trong plan T6, cần đối chiếu), `EligibilityDecision`/
  `previous_eligibility` (`domain/case.py:87-94,114` — schema luôn None),
  `ExpenseDisposition`/`expense_dispositions` (`domain/case.py:167-173,179` — luôn `()`).
- **Test-only (xóa kèm test)**: `JobStore.recover_incomplete` (`jobs.py:115-133`),
  `run_preview` + job cache helpers (`jobs.py:136-193`), `EvidenceReader` per-page +
  `OcrClient` + `relations_for` (`reader.py:37-189`), `assert_context_current`
  (`controls.py:58-65`), `validate_inventory` (`packets.py:220-269`), `KnownAmount`
  (`domain/common.py:122-126`).
- **Planned-unwired (P0.4 đối chiếu contracts/design)**: `confirm_admissibility` +
  `_FIELD_ROLES` (`admissibility.py`, plan:119), `propose_step` + `AllowedStep`/
  `Opportunity` (`planning.py`, plan:158), `write_report` (import tại `cli.py:102` không
  gọi).

## Phụ lục C — Trùng lặp (mẫu → vị trí)

| Mẫu | Số bản | Vị trí (file:line) |
|---|---:|---|
| Chuẩn hóa text/diacritics | 9 | `linking.py:186`, `advance_identity.py:33`, `employee_return.py:25`, `admission.py:100`, `matching.py:73`, `settlement_draft.py:264`, `service.py:3193/3694/4110` |
| Canonical JSON+sha256 | 8+ | `service.py:292-300`, `reconciliation/service.py:46-47,57-58`, `admission.py:277-284`, `context_records.py:80-81`, `money_history.py:25-27`=S:6109, `artifacts.py:43`, `telemetry.py:406-431` (+`snapshots.py:388-398` dead) |
| Gom EvidenceRefs | 8 | `admission.py:147`, `advance.py:92`, `matching.py:145`, `settlement_draft.py:66`, `settlement_link.py:91`, `document_arithmetic.py:76,89`, `linking.py:940` |
| Field accessor | 7 | `admission.py:79,140`, `advance.py:69`, `settlement_draft.py:40,61`, `matching.py:115,122` |
| Ref normalize/match | 2 semantics | `linking.py:743-771` vs `admission.py:189-207` (biến thể: `matching.py:53`) |
| Limits 8m/4m | 2 | `policy.py:17-18` vs `admission.py:59-60` |
| `_budget_for` | 2 (diff = IDENTICAL) | `service.py:191-197` vs `context_records.py:198-204` |
| `_parse_dt` | 2 (+28 inline) | `context_records.py:26` vs `service.py:252` |

## Phụ lục D — Test suite (top file & gap)

Top file test: `test_advance_draft_api.py` 1116 · `test_evidence_finance_workflow.py` 670 ·
`test_document_extraction.py` 573 · `test_employee_return_draft_api.py` 478 ·
`test_contracts.py` 455 · `test_dossier_linking.py` 401 · `test_coverage_confirmation.py`
397 · `test_advance_record_guards.py` 378 · `test_langsmith_runtime_wiring.py` 371.

Module src không có test trực tiếp: `workflow/money_history.py`, `workflow/snapshots.py`,
`evidence/m0.py`, `evidence/m0_live.py`, `evidence/live_reader.py`, `source_dates.py`,
`api/views.py` (gián tiếp qua workflow/HTTP).

Frontend tests: 11 file / 1.639d / 48 `it` (46 active + 2 skip); act warnings lặp lại;
`caseView()` builder trùng ×3; helper `mockFetch` chỉ có 1 nơi.

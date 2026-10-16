# Clean refactor program (post-competition) — InvoiceReferee

> **For agentic workers:** Follow the portable [task workflow in AGENTS.md](../../../AGENTS.md#execute-and-hand-off). Execute only the tasks authorized by the user, with their stated gates. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution adapter:** Local helper instructions to continue, make rulings, commit or clean up apply only within the user-authorized scope under AGENTS.md. An accepted scope/financial-rule/authority conflict needs a concrete human decision; in-scope implementation choices remain the implementer's responsibility. A helper cannot turn a P0-only or no-commit authorization into code or Git authorization.

**Goal:** Làm sạch codebase InvoiceReferee — giảm kích thước file/hàm, dọn dead code và trùng lặp, tái cấu trúc `workflow/service.py` và các god files, làm sạch `tests/` + `frontend/src/` + docs — theo hướng **behavior-preserving** để coding agent và người đọc/navigate nhanh hơn. Không đổi hành vi sản phẩm.

**Architecture:** Không đổi. Chỉ tổ chức lại code: pure extraction + façade/mixin giữ nguyên public API (contracts §9) và DB schema. Mọi thay đổi đi theo: characterization test (nếu vùng chưa được pin) → bước nhỏ → suite xanh → checkpoint.

**Tech Stack:** Không đổi (Python3.12/FastAPI/Pydantic/SQLite/uv; React/TS/Vite/Node24; pytest/Vitest).

**Spec:** [clean refactor design](../specs/2026-10-16-refactor-clean-design.md) — authority về cấu trúc; [contracts](../../final/IMPLEMENTATION_CONTRACTS.md) + [design](../../final/ARCHITECTURE_AND_EVALUATION.md) — authority về hành vi (không đổi).

## Global Constraints

- **Freeze code:** không sửa file code (`src/`, `tests/`, `frontend/src/`) trước khi user mở khoá — mặc định sau Demo Day 17/10/2026. **P0 là doc-only**, chạy được ngay khi user authorize.
- **Behavior-preserving:** contracts/design là chuẩn nghiệm thu; không đổi DTO/schema/DB/rule/hành vi. Test hiện có phải xanh **nguyên trạng**; nếu buộc phải sửa một assert để xanh → dừng, ghi nhận, báo user (gần như chắc chắn đã vi phạm "no behavior change").
- **Gates mỗi task:** `rtk proxy uv run pytest -q` (781 collected) xanh; task chạm frontend thêm `npm --prefix frontend test -- --run` + `npm --prefix frontend run build` (Node24, verify runtime trước build/test theo AGENTS.md). **Stub mode, không LIVE**; không đụng `.runtime/` hay DB/server của user; test dùng tmp.
- **One integrator** sở hữu shared files (`workflow/*`, `domain/*`, `api/*`); serialize edits; dispatch ghi owner + exact write set + reviewer; reviewer không tự triển khai phần mình review.
- **Commit chỉ khi được authorize:** exact paths, không squash/force-push, preserve unrelated changes; đề xuất nhánh `refactor/clean-2026-10` (user chốt khi mở khoá). `git diff --check` trước mỗi commit.
- **Không thêm dependency** trừ khi user chốt (kể cả pytest-xdist/pytest-cov ở P2.5).
- **Dead code chỉ được xóa khi:** P0.4 đã kết luận + xác nhận lần 2 (grep toàn repo + codegraph blast radius) + suite xanh. Planned-unwired không xóa khi chưa đối chiếu contracts/design.
- **Line refs là snapshot `main@63b3dad6`** (16/10) — verify lại trước khi sửa; file có thể đã drift.
- **Evidence chuẩn repo:** mỗi task ghi command, exit/result, version, provider mode, evidence location.
- **Checkpoint:** hoàn tất task → tick checkbox trong plan + cập nhật status checkpoint (evidence + remaining gaps) theo AGENTS.md. Interruption → giữ failing check + local changes + next action.
- Bug hành vi (clock, replay wiring, digest order — design §9) đi **workflow bug riêng (RED→GREEN)**, không trộn vào plan này.

## Review Focus

1. P3: `CaseWorkflow` public methods (contracts §9) bất biến? 13 file test bám `workflow._*` và 4 chỗ `wf._clock` vẫn xanh nguyên trạng?
2. Dead code: đủ 2 nguồn xác nhận trước mỗi lần xóa; planned-unwired đã có kết luận P0.4?
3. Hợp nhất helper: semantics không đổi (test bảo vệ); biến thể có chủ đích (ref-match, JSON option khác nhau) vẫn tách biệt, có tên/docstring nêu khác biệt.
4. Docs: 0 link chết tracked; AGENTS.md sau trim vẫn giữ authority/gates/handoff.
5. Frontend: `data-testid` giữ nguyên; timezone/format thống nhất một nơi — thay đổi hiển thị nào cũng phải được ghi nhận trong checkpoint.

## File Map

| Phase | Exact paths (nhóm chính) | Change type |
| --- | --- | --- |
| P0 | `docs/adr/0012-workflow-service-decomposition.md`, `0013-single-source-shared-helpers.md`, `0014-repo-as-context-structure.md` | Create (doc-only) |
| P1 | `domain/{text,hashing,dates}.py`, `reconciliation/refs.py` (mới); `reconciliation/{policy,admission,linking}.py`, `domain/{documents,case,common,issues}.py`, `evidence/{pipeline,reader,planning}.py`, `workflow/{jobs,controls,snapshots,service}.py`, `evaluation/{models,packets,reports}.py`; xóa theo P0.4: `reconciliation/admissibility.py` (nếu kết luận superseded); `cli.py`; `pyproject.toml`; `.gitignore`, `AGENTS.md`, `GLOSSARY.md` (track); `docs/INDEX.md`, `README.md`, `docs/final/RUNBOOK.md`, `docs/final/IMPLEMENTATION_STATUS.md` | Create/Modify/Delete |
| P2 | `tests/conftest.py`, `tests/builders/**`, `tests/stubs/**`, `tests/factories.py`, `tests/unit/**`, `tests/integration/**`, `frontend/tests/**`, `pyproject.toml` | Restructure |
| P3 | `src/invoice_referee/workflow/service.py`; new `workflow/{advance_link,framework,authority,case_view}.py`, `workflow/case/{framework,commands,drafts,money,assessment,views}.py`; `tests/integration/**` (characterization mới) | Create/Move/Modify |
| P4 | `reconciliation/admission/**` (package), `reconciliation/linking/**`, `evidence/pipeline.py`, `api/routes.py`, `evidence/extraction.py`, `workflow/context_records.py` | Split |
| P5 | `frontend/src/**` (`lib/**`, `features/intake/**`, `features/questions/**`, `hooks/**`, `components/**`, `api.ts` → `api/{client,dto}.ts`) | Split/Modify |
| P6 | `docs/final/IMPLEMENTATION_STATUS.md`, `docs/final/status-log/2026-10.md`, `docs/archive/**`, `docs/final/reviews/README.md`, `AGENTS.md`, `README.md`, `docs/final/RUNBOOK.md` | Restructure (doc-only) |

Không phase nào chạm: `data/**`, `docs/adr/0001–0011`, `docs/final/reviews/**` (trừ index mới), `docs/Challenge_Brief*`, contracts/design (không đổi), schema.sql.

## Sequence

P0 → P1 → P2 → P3 → P4 → P5 → P6. Lý do: P1+P2 tạo nền sạch + feedback nhanh **trước** khi phẫu thuật `service.py` (P3); P4 cùng kỹ thuật; P5/P6 độc lập, có thể đổi thứ tự nếu user muốn. P0 doc-only chạy ngay; P1 trở đi chờ mở khoá code.

### P0 — Chuẩn bị (doc-only)

**Files:** `docs/adr/0012-*.md`, `0013-*.md`, `0014-*.md`; cập nhật design/specs khi có quyết định mới.
**Produces:** 3 ADR accepted; kết luận planned-unwired; baseline metrics + open questions có câu trả lời.

- [ ] P0.1 Viết ADR-0012 (workflow decomposition: pure extraction + PA-C; giữ import path + public API; PA-A/B hoãn và lý do; ngân sách 4.1).
- [ ] P0.2 Viết ADR-0013 (single-source helpers; danh sách hợp nhất; nguyên tắc "biến thể có chủ đích giữ tách + docstring").
- [ ] P0.3 Viết ADR-0014 (repo-as-context: track AGENTS.md/GLOSSARY.md; INDEX.md; status ≤100d + status-log; archive; reviews index).
- [ ] P0.4 Đối chiếu contracts §5/§7/§10.5 + design §2–4 cho planned-unwired: `confirm_admissibility` + `_FIELD_ROLES` (`reconciliation/admissibility.py`; plan:119), `propose_step` + `AllowedStep`/`Opportunity` (`evidence/planning.py`; plan:158), `QuestionCard` (`domain/issues.py:40-48`; plan T6), `write_report` (`evaluation/reports.py:42-46`; import không gọi `cli.py:102`). Mỗi mục: superseded → đưa vào danh sách xóa P1 (kèm lý do + nguồn); còn nợ → giữ + ghi lý do + báo user. Ghi kết quả vào design Phụ lục B + status.
- [ ] P0.5 Ghi baseline metrics vào design §6.3 (đã có) + lấy trả lời user cho open questions §10 (ngân sách, track AGENTS/GLOSSARY, nhánh, deps, mốc mở khoá). Kết quả ghi vào checkpoint.
- **Gate:** 3 ADR accepted; kết luận P0.4 đầy đủ; open questions có câu trả lời; **chưa chạm code**.

### P1 — Quick wins an toàn (sau khi mở khoá)

**Files:** theo design Phụ lục B/C + `pyproject.toml` + docs quick wins.
**Consumes:** kết luận P0.4.
- [ ] P1.1 Dead code — nhóm 0-caller (Phụ lục B): mỗi mục xác nhận lần 2 (grep toàn repo + codegraph) rồi xóa; gom thành lô nhỏ, suite xanh sau mỗi lô.
- [ ] P1.2 Dead code — nhóm test-only: xóa code + test liên quan (`test_admissibility.py`, `test_preview_job.py`, phần `propose_step` trong `test_provider_contracts.py`, phần `validate_inventory` trong `test_packet_inventory.py`, phần `KnownAmount` trong `test_contracts.py`, phần `assert_context_current` trong `test_controls_races.py`) — chỉ phần liên quan, không đụng test khác; suite xanh từng nhóm.
- [ ] P1.3 Dead code — nhóm planned-unwired theo kết luận P0.4 (xóa hoặc giữ + ghi lý do; không tự quyết ngoài kết luận).
- [ ] P1.4 Helper consolidation: `domain/text.py` (9 bản chuẩn hóa — **so diff semantics từng bản trước**, chỉ hợp nhất bản trùng thật); `domain/hashing.py` (`canonical_digest`; chú ý 3 tổ hợp option JSON khác nhau → tham số hóa tường minh, không gộp mù); `domain/dates.py` (`_parse_dt` + 28 `fromisoformat` inline); `reconciliation/refs.py` (gom `EvidenceRefs` 8 bản + normalize; giữ 2 semantics ref-match có chủ đích + docstring). `_budget_for` về 1 nguồn; limits `8_000_000/4_000_000` một nguồn (`reconciliation/policy.py` import sang `admission.py`). Mỗi hợp nhất kèm test bảo vệ + suite xanh.
- [ ] P1.5 Layering: chuyển `Transcription`/`TranscriptionFact` sang `domain` (theo pattern `organization.py:9`); `evaluation.models` re-export để giữ tương thích; cập nhật `pipeline.py:21`, `snapshots.py:23`, `service.py:879/5783/5793`.
- [ ] P1.6 Test markers: đăng ký marker `slow` + `--strict-markers`; gắn `slow` cho `legacy_corpus` (subprocess), PDF generation, telemetry sleep; tài liệu hóa subset `-m "not slow"` (mặc định `pytest` vẫn chạy toàn bộ).
- [ ] P1.7 Docs quick wins: tạo `docs/INDEX.md`; fix drift (README:116 dead link; README vs RUNBOOK hosting; plan T12 suite `holdout`; status handoff branch); **track `AGENTS.md` + `GLOSSARY.md`** (bỏ 2 dòng `.gitignore`, commit khi authorized).
- **Gate:** full pytest + frontend tests xanh; LOC delta vs baseline ghi lại; status checkpoint cập nhật.

### P2 — Test suite foundations

**Files:** `tests/**`, `frontend/tests/**`, `pyproject.toml`.
- [ ] P2.1 Tạo `tests/builders/{documents.py,reads.py,workflow.py}` + `tests/stubs/{llm.py,clients.py,readers.py}` (gom từ các bản lặp: `_paper/_invoice` ≥15 file, `_report` 19 file, `FakeLlm`×3, `FakeClient`×3, reader giả ≥7); migrate theo file khi chạm — không big-bang.
- [ ] P2.2 Conftest refactor: tách fixture theo tầng (root/integration); `workflow_factory` thay 12–13 bản `_workflow` cục bộ; đổi tên seed SQL thành `seed_transcription_for_test()` (giữ API `AppFixture`).
- [ ] P2.3 Tách file test >500d theo cụm chủ đề: `test_advance_draft_api` (migration/API/races), `test_evidence_finance_workflow`, `test_document_extraction`, `test_employee_return_draft_api`, `test_contracts` — mỗi lần tách: suite xanh.
- [ ] P2.4 Parametrize nhóm cùng shape (5 `coverage_without_*`; các nhóm constants policy).
- [ ] P2.5 Đo runtime: full suite + `-m "not slow"` (≥2 lần, ghi median); trình user quyết định optional deps (pytest-xdist/cov).
- [ ] P2.6 Frontend tests: builder `caseView()` dùng chung; helper `mockFetch`; khảo sát và sửa act warnings (`app-restore`/restore tests) — không đổi hành vi các test khác.
- **Gate:** pytest xanh; subset nhanh chạy được + tài liệu hóa; runtime đo ghi lại; frontend tests xanh.

### P3 — `workflow/service.py` (phẫu thuật chính)

**Files:** `workflow/service.py` + new modules (design §4.2); characterization tests mới.
- [ ] P3.0 Characterization tests cho 5 hub (design §6.1): `execute`, `_submit`+binding, `_answer_issue`, `_record_actual`, `_assess_and_commit`+`_commit_assessment`. Chỉ **thêm test**, pin hành vi hiện tại; phát hiện hành vi bất ngờ → ghi backlog (design §9), không sửa.
- [ ] P3.1 Pure extraction từng bước (mỗi bước một commit-checkpoint): `workflow/advance_link.py` (S:3156-3659, 2 callback tường minh) → `workflow/framework.py` (S:5877-5945) → `workflow/authority.py` (S:4904-5069) → `workflow/case_view.py` (sub-builders S:5956-6209) → assessment helpers (S:5437-5836). CaseWorkflow giữ method delegating cùng tên.
- [ ] P3.2 PA-C mixin: `workflow/case/{framework,commands,drafts,money,assessment,views}.py`; `service.py` = assembly + `__init__` + `execute` + seams; quy tắc MRO (framework cuối; tên helper unique; mixin không import lẫn nhau); tên method/helper bất biến.
- [ ] P3.3 Đánh giá lại: mọi file `workflow/` ≤800d? Nếu chưa → đề xuất PA-A cho user (chỉ triển khai khi được chốt); ghi kết quả vào ADR-0012/status.
- **Gate:** mọi file `workflow/` ≤800d; contracts §9 API bất biến; full suite + targeted integration (`test_advance_draft_api`, `test_evidence_finance_workflow`, `test_money_execution`, `test_submit_job`) xanh; codegraph re-index + spot-check discovery.

### P4 — God files còn lại

- [ ] P4.1 `reconciliation/admission/` package: `fields.py` (67-208), `history.py` (277-364), `binding.py` (365-593), `admit.py` (tách `admit_evidence` 489d theo stage), `index.py` (1083+); `__init__.py` re-export giữ điểm import `from ...reconciliation.admission import admit_evidence`.
- [ ] P4.2 `reconciliation/linking/` staged split: normalize → scan/score → tie-break → assemble (pin score/tie-break bằng characterization trước — cùng P3.0 nếu liên quan).
- [ ] P4.3 `evidence/pipeline.py`: tách trace-serialize (57-227) và STUB transcribe (228-360); `read_root` giữ điểm vào qua re-export.
- [ ] P4.4 `api/routes.py`: chia router theo nhóm; phần evaluation trong `/verify` (347-390) ra helper ngoài handler; hành vi HTTP bất biến (integration API xanh).
- [ ] P4.5 Đánh giá `evidence/extraction.py` + `workflow/context_records.py`: chỉ tách nếu vượt ngân sách sau P1; ghi kết luận.
- **Gate (mỗi file):** điểm import công khai ổn định (re-export); suite xanh; re-index.

### P5 — Frontend

- [ ] P5.1 Libs: `lib/money.ts` (hợp nhất 4 biến thể format tiền, chốt 1 hậu tố), `lib/datetime.ts` (chuẩn `Asia/Ho_Chi_Minh`; thay các ép cục bộ coverage/dossier/debug_modal; xóa `formatDate` dead), `lib/labels.ts` (hợp nhất 2 bản `formatIssueTarget` đã diverge + KIND/MONEY/STATE labels + `roleMatchesOwner`; cập nhật dashboard/App).
- [ ] P5.2 Tách file: `intake.tsx` → `features/intake/{IntakeUpload,IntakeReview,draft.ts}` + `hooks/useCasePolling.ts`; `questions.tsx` → `features/questions/{formatting.ts,settlementTables.ts,QuestionCard.tsx,Questions.tsx}`; `advance.tsx` → `hooks/useAdvanceDraft.ts`; `App.tsx` → `hooks/useClickOutside.ts`.
- [ ] P5.3 Primitives `components/{Alert,Field,FileInput}.tsx`; `api.ts` → `api/client.ts` + `api/dto.ts`; siết types nơi khả thi (thay `as T` từng endpoint; `unknown[]` → type server khi đã có).
- [ ] P5.4 Verification: `npm test` xanh; build exit0; browser checkpoint UI chính (theo quy chuẩn task UI của repo).
- **Gate:** `data-testid` giữ nguyên; frontend tests + build xanh; browser check ghi evidence.

### P6 — Repo-as-context

- [ ] P6.1 Tách `IMPLEMENTATION_STATUS.md`: ≤100d phần hiện tại + `docs/final/status-log/2026-10.md` (330d entry-log trước "Current handoff"; sắp xếp theo ngày).
- [ ] P6.2 Archive: chuyển `RELEASE_EVIDENCE.md`, `BUILD_LOG.md`, `PROPOSAL_*`, `VIDEO_DEMO_SCRIPT.md`, `PDF_DATA_REVIEW_AND_UI_CHECKLIST.md`, `*_AGENT_PROMPT.md` → `docs/archive/`; tạo `docs/final/reviews/README.md` (index 53 file theo ngày/chủ đề).
- [ ] P6.3 Bảng Commands thống nhất (deterministic/cần-provider/config riêng; chính sách `rtk proxy`; playwright spec LIVE) + cập nhật README/RUNBOOK.
- [ ] P6.4 Trim `AGENTS.md` (bỏ phần discovery trùng `CODE_DISCOVERY`; giữ authority/gates/handoff/environment; thêm 1 dòng "hạn chế subagent theo từng task, không phải luật thường trực") — **user review trước khi commit**.
- [ ] P6.5 Clean-clone check: clone ra temp; đi theo hành trình đọc của AGENTS.md; kiểm 0 link chết trong tracked docs.
- **Gate:** clean-clone pass; không link chết tracked; context cost đo lại ≤~350–400d (design §6.3).

## Backlog ngoài chương trình

Bug hành vi đã ghi nhận (design §9): clock bypass `service.py:4474,4914,5045,5933`; nghi vấn digest order (`S:563` vs `S:694-699`); replay wiring mismatch (`runtime._wire_replay`/`FileOcrReader.read_source` vs `ReplayReader.ocr_page` — nghi vấn source-level). Đi qua workflow bug RED→GREEN riêng, từng lần một, có authorize.

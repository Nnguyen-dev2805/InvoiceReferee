# 08 — Tests: Hoangha codebase review

Ngày review: 2026-10-14
Source review: `.worktrees/hoangha` tại revision `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`
Phạm vi owner: `08-tests` trong `inventory.json` — **23 file / 5.035 dòng**.
Execution: **TESTS NOT_RUN · BUILD NOT_RUN · LIVE/PROVIDER NOT_RUN · GENERATOR NOT_RUN** theo yêu cầu.
Đếm tĩnh bằng AST: **149 test function definitions**; đây chỉ là số hàm `test_*` được định nghĩa trong source, **không phải số test pass** và không thay thế việc chạy pytest.

## 1. Kết luận review

Test suite Hoangha có giá trị tái dùng cao ở ba vùng: deterministic matcher, OCR/LLM adapter contract với fake provider, và orchestration/repository lifecycle cục bộ. Nó cũng có nhiều regression tốt cho confidence gate, document validity, duplicate handling, accountant override/requeue và UI evidence preview.

Nhưng suite hiện tại **không thể được dùng làm bằng chứng rằng pipeline §15 của `final` đã đúng**. Hai lý do chính là: (1) FastAPI integration fixture chủ động tắt worker và document pipeline; (2) các test document/LLM hiện hành dùng contract Hoangha cũ, chưa pin strict 17-type taxonomy, `SETTLEMENT_FORM`, provenance/field-state contract, global attempt budget, restart-resume budget hay `EVIDENCE_READY` boundary của §15/E0.

Quan trọng nhất đối với matching: deterministic core đã có test khá tốt, nhưng **không có test source trực tiếp cho LLM suggestion resolver** (`analyze_evidence_reconciliation` → `accepted_links` → promote `SUGGEST_LINK` ở `>=0.90`). Đây là coverage gap; **không phải đề xuất đổi matching semantics**. Semantics đã được user chọn “port full Hoangha” phải được giữ nguyên và viết regression test đúng các ngưỡng hiện hành trước implementation.

## 2. Phương pháp và giới hạn bằng chứng

- Dùng CodeGraph trước để định vị caller/callee và vùng test liên quan; graph trả về `worker_loop`, `create_app`, `_resolve_suggested_paper_links`, `match_paper_evidence`, `run_once` và các test callers liên quan. Theo handoff parent, index đang up-to-date nhưng `check_index_coverage`/generation id không exposed; vì vậy **graph coverage = UNKNOWN**.
- Mọi absence claim trong report này được kiểm bằng **bounded source search trên `tests/` hoặc đúng owner08 files**, không dựa vào graph negative.
- Đã đọc full 23 file owner08; 5 file còn lại sau checkpoint được đọc full ở lượt này. Không có file owner08 bị đánh dấu PARTIAL.
- Source tests được đọc và phân tích, nhưng **không chạy**. Mọi câu “test kiểm X” có nghĩa là source có fixture/assertion cho X; không có nghĩa là runtime hiện tại pass.
- Khi so với `final`, authority dùng §15 của `docs/final/ARCHITECTURE_AND_EVALUATION.md` và §§12.2–12.5 của `docs/final/IMPLEMENTATION_CONTRACTS.md`, không dùng README Hoangha làm proof.

## 3. Inventory đã đọc đầy đủ

<!-- reviewed-file: tests/integration/test_fastapi_app.py -->
<!-- reviewed-file: tests/integration/test_streamlit_app.py -->
<!-- reviewed-file: tests/unit/test_accounting_case_view.py -->
<!-- reviewed-file: tests/unit/test_accounting_review.py -->
<!-- reviewed-file: tests/unit/test_bbox_overlay.py -->
<!-- reviewed-file: tests/unit/test_document_validity.py -->
<!-- reviewed-file: tests/unit/test_evidence_repository.py -->
<!-- reviewed-file: tests/unit/test_inventory_policy.py -->
<!-- reviewed-file: tests/unit/test_kimi_reasoning.py -->
<!-- reviewed-file: tests/unit/test_local_case_store.py -->
<!-- reviewed-file: tests/unit/test_mistral_ocr.py -->
<!-- reviewed-file: tests/unit/test_network_resilience.py -->
<!-- reviewed-file: tests/unit/test_ocr_preview.py -->
<!-- reviewed-file: tests/unit/test_ocr_quality.py -->
<!-- reviewed-file: tests/unit/test_paper_evidence_matching.py -->
<!-- reviewed-file: tests/unit/test_process_case.py -->
<!-- reviewed-file: tests/unit/test_settlement_policy.py -->
<!-- reviewed-file: tests/unit/test_settlement_summary.py -->
<!-- reviewed-file: tests/unit/test_sqlite_settlement_repository.py -->
<!-- reviewed-file: tests/unit/test_submit_case.py -->
<!-- reviewed-file: tests/unit/test_uc3_testcase_catalog.py -->
<!-- reviewed-file: tests/unit/test_word_block_mapper.py -->
<!-- reviewed-file: tests/unit/test_word_confidence.py -->

| File | Dòng | Vai trò test | Input → output/assertion | Hàm chính / caller / callee | Hành vi lỗi được kiểm | Khả năng dùng lại sang `final` |
| --- | ---: | --- | --- | --- | --- | --- |
| `tests/integration/test_fastapi_app.py` | 274 | FastAPI intake/accounting integration | multipart payload + files → 202, case view, accounting HTML, action/delete | `_load_app()` → `app.fastapi_app` → routes/runtime/repository; `/internal/process-next` gọi processor thủ công | request-info transition, delete 404, no-evidence routes accountant | **Một phần.** Hữu ích cho HTTP/form/view assertions; fixture tắt worker và document pipeline nên không phải evidence cho §15 OCR/LLM/worker |
| `tests/integration/test_streamlit_app.py` | 190 | Legacy Streamlit integration | description-only submit, stored OCR artifact, stored processing result → rendered UI | `AppTest.from_file()` → `app/streamlit_app.py`, `LocalCaseStore`, `LocalEvidenceRepository` | UI exception count, delete confirmation | **Legacy/reference pattern**; không nên port nguyên Streamlit lifecycle vào `final` |
| `tests/unit/test_accounting_case_view.py` | 159 | FastAPI accounting presentation/decorating | case dict + fake OCR artifact → queue taxonomy, evidence preview, finding buckets | `_case_outcome_key`, `_decorate_accounting_case` → OCR preview helpers | processing error taxonomy, low-confidence block preview | Hữu ích cho provenance UI; DTO/status names phải map lại sang `EVIDENCE_READY`/final contracts |
| `tests/unit/test_accounting_review.py` | 132 | Legacy accounting text explanation | processing result + stored case → human-readable summary/reason | `_accounting_reasoning`, `_accounting_summary` | hides technical IDs; prioritizes inventory conflict; names missing support | Chỉ tái dùng principle “explain with user-facing evidence”; inventory semantics ngoài §15 |
| `tests/unit/test_bbox_overlay.py` | 43 | OCR visual overlay | image + OCR dimensions/boxes/confidence → scaled annotated pixels | `render_bbox_overlay` | không test malformed dimensions ở file này | Có thể tái dùng UI helper/test pattern nếu final giữ bbox preview |
| `tests/unit/test_document_validity.py` | 315 | Document profile validity | extracted fact/profile states → CLEAR/NEEDS_HUMAN/OUTSIDE_POLICY/eligibility | `validate_expense_document` và profile rules | unreadable critical field, invalid/mismatch tax, unknown type, unclear total, paper request warning | **Tái dùng chọn lọc.** Profile/criticality logic có giá trị, nhưng final phải chuyển sang strict E0 states/provenance và thêm `SETTLEMENT_FORM` |
| `tests/unit/test_evidence_repository.py` | 68 | Local filesystem evidence repository | stored files/OCR artifact → read/round-trip/delete | `LocalEvidenceRepository` | unsafe case id delete | Pattern lưu artifact hữu ích; repository cụ thể không port vì §15 giữ final workflow/DB |
| `tests/unit/test_inventory_policy.py` | 395 | Inventory-specific business policy | invoice/report facts + LLM conflict → findings/questions | inventory evaluator + fake analysis | missing support, mismatches, text-only claims ignored, semantic conflict handling | **Không port vào §15 evidence phase**; chỉ tham khảo test style cho source-vs-user-text separation |
| `tests/unit/test_kimi_reasoning.py` | 350 | LLM adapter schema/repair contract | fake completions → typed confidence/conflict/extraction objects | `KimiReasoningAdapter._analyze`, `analyze_confidence`, conflict/paper/expense extractors | transient retry, surrounding text JSON, one repair, incomplete coverage, second-invalid fail closed | Pattern rất hữu ích cho `XkiroClient` schema/repair tests; **không port Kimi provider** |
| `tests/unit/test_local_case_store.py` | 39 | Legacy local submission store | claim + upload → metadata/file/audit | `LocalCaseStore.save_submission` | chủ yếu happy path | Thấp; final đã có workflow/DB riêng |
| `tests/unit/test_mistral_ocr.py` | 82 | OCR adapter request contract | image/PDF → request payload, word confidence, retry | `MistralOcrAdapter.process` | transient socket retry | Hữu ích cho OCR adapter mechanics; final §15 phải thêm all-page OCR-only/no-native-bypass tests |
| `tests/unit/test_network_resilience.py` | 58 | retry primitive | callable raising WinError/validation error → retry/result/error | network retry helper | exhausted transient failure, non-network error is not retried | Có thể tái dùng helper-level contract nếu final adapter dùng cùng primitive |
| `tests/unit/test_ocr_preview.py` | 54 | OCR crop/preview | image/PDF page + block bbox → rendered preview | `render_ocr_block_preview` | không phải pipeline semantic test | Reuse UI evidence presentation only |
| `tests/unit/test_ocr_quality.py` | 78 | deterministic low-confidence candidate collection | OCR blocks/word scores → candidates | `collect_low_confidence_blocks` | formatting token filtering; no hardcoded bill-label dependency | Reuse tốt; final phải gắn critical-field missing-score semantics ở E5, không suy ra root pass từ candidate collector |
| `tests/unit/test_paper_evidence_matching.py` | 312 | deterministic paper↔evidence matcher | paper rows + extracted document facts → items/links/findings | `match_paper_evidence` | missing evidence/reason, reuse demotion, alternative proof, no double count | **Port test core gần nguyên vẹn** để khóa accepted §15 semantics; bổ sung exact threshold boundaries + LLM resolver tests |
| `tests/unit/test_process_case.py` | 904 | Legacy CaseProcessingService orchestration | fake OCR + fake reasoner + evidence inventory → decision/findings | `CaseProcessingService` caller chain qua OCR/confidence/conflict/inventory | fail-before-agent gates, unassessed fail closed, exact identifier guard, one conflict repair | Reuse pattern orchestration/confidence; inventory/legacy decision taxonomy không port vào §15 |
| `tests/unit/test_settlement_policy.py` | 291 | Hoangha financial/policy decisions | `SettlementDraft`/row evidence states → decision target/status | settlement policy evaluator | missing context/evidence, authority, personal expense, suspicious doc, unknown fields | **Không port vào §15 evidence-only**; final financial assessment remains separate authority |
| `tests/unit/test_settlement_summary.py` | 55 | decision text summary | settlement result variants → human-readable amount/reason | summary helper | không có external failure path | Reuse only wording/test pattern after final money contract is connected |
| `tests/unit/test_sqlite_settlement_repository.py` | 902 | Hoangha repository + processing lifecycle with fakes | submit/job/OCR/facts/review → persisted case/audit/artifacts | `SQLiteSettlementRepository`, `SubmitSettlementService`, `SettlementProcessingService.run_once`, `ReviewSettlementService` | provider failure→PROCESSING_ERROR, override, requeue, delete safety, quality stop, mismatch routes | Nhiều regression patterns tốt; **không port repository/lifecycle nguyên khối** vì §15 giữ final DB/job model |
| `tests/unit/test_submit_case.py` | 79 | legacy submit validation/dedup | description/files → receipt/errors/warnings | submit service/local store | empty submit, unsupported file, same-file duplicate across roles | Dedup/validation cases hữu ích; cần map sang final command/idempotency rules |
| `tests/unit/test_uc3_testcase_catalog.py` | 55 | static corpus shape check | `manifest.json` + case directories → schema/count/files/oracle presence | filesystem/json only | missing structural artifacts would fail assertion | Chỉ chứng minh **50-case v2 structure**; không chứng minh final 75-case §15 evidence eval hoặc gold quality |
| `tests/unit/test_word_block_mapper.py` | 135 | OCR word→block mapping | words + block markdown/table → mapped exact/partial/unmatched blocks | `restructure_mistral_ocr` | partial/unmatched mapping surfaced | Reuse tốt cho locator/provenance preprocessing, nhưng final validator cần source/page/block ownership checks riêng |
| `tests/unit/test_word_confidence.py` | 65 | confidence row flattening/levels | OCR pages → flat rows + LOW/REVIEW/GOOD labels | confidence helpers | old result compatibility | Reuse UI/diagnostic helper; final contract threshold authority nằm §15/E0 |

## 4. Coverage thật sự của suite theo nhóm contract

### 4.1 OCR và confidence

Source tests xác minh được:

- image request được base64 encode; PDF dùng `document_url`; request bật `include_blocks=True` và word confidence (`tests/unit/test_mistral_ocr.py:38-82`);
- network retry xử lý transient WinError 10013 và không retry validation error (`tests/unit/test_network_resilience.py:9-58`);
- low-confidence collector không dựa vào hardcoded bill keyword và bỏ formatting-only token (`tests/unit/test_ocr_quality.py:4-78`);
- word→block mapping giữ exact/normalized/table-reference và surface partial/unmatched (`tests/unit/test_word_block_mapper.py:13-135`);
- confidence presentation dùng LOW `<0.70`, REVIEW `0.70–0.84`, GOOD `>=0.85` (`tests/unit/test_word_confidence.py:55-65`).

Điều **chưa** được owner08 Hoangha suite chứng minh là final §15 rule **mọi trang PDF/JPG/JPEG/PNG đều qua OCR, kể cả PDF có text layer và không native-text fallback**. §15 pin behavior này tại `ARCHITECTURE_AND_EVALUATION.md:524-538`; current OCR adapter unit tests chỉ phân biệt request shape image/PDF, không dựng adversarial text-layer PDF để chứng minh native path không bypass OCR.

### 4.2 LLM adapter và fake fixtures

`test_kimi_reasoning.py` dùng fake completions để kiểm contract của adapter, không gọi LIVE. Nó kiểm retry transient, dedicated prompt, JSON extraction khi có text bao quanh, một repair cho JSON/schema lỗi, fail closed sau hai response không hợp lệ, complete candidate coverage cho confidence, conflict payload có đủ sources/business context, paper settlement row extraction và content-based document classification (`tests/unit/test_kimi_reasoning.py:158-350`).

Đây là **orchestration/schema evidence**, không phải model-quality evidence. Không test nào trong owner08 chứng minh Kimi/X-Kiro thực tế phân loại đúng tài liệu hoặc trích xuất đúng trên unseen invoices; và §15 final đã chốt dùng `XkiroClient`, không thêm Kimi (`ARCHITECTURE_AND_EVALUATION.md:538-540`). Khi port, nên tái dùng cách test fake response/repair/fail-closed, thay provider và DTO theo E0.

### 4.3 Confidence → extraction → conflict orchestration

`test_process_case.py` là vùng orchestration mạnh nhất của legacy path: missing bill/business context dừng trước OCR/agents; primary-only có thể pass quality mà không conflict call; critical low-confidence có thể hỏi human; noncritical/readable/peripheral có thể đi tiếp; unassessed candidate fail closed; exact identifier không được “semantic readable” che lỗi; hai nguồn OCR/confidence độc lập rồi mới conflict; một nguồn unclear dừng trước cross-source conflict; caller-level repair cho semantic-incomplete conflict (`tests/unit/test_process_case.py:242-904`).

Giá trị tái dùng ở đây là **thứ tự gate + fake spies + fail-closed assertions**. Các inventory decision/policy result trong cùng file là legacy semantics và không nên trở thành gold của §15, vì §15 dừng ở evidence report trước financial reconciliation (`ARCHITECTURE_AND_EVALUATION.md:530-534`).

### 4.4 Document validity/profile

`test_document_validity.py` có coverage tốt cho legacy profiles: unreadable required field không được coi là present; invalid tax format → human; company tax mismatch → outside policy; receipt/ticket có required-field khác invoice; unknown type không eligible; typo warning nonblocking; unclear total blocking; paper request phải clear trước matching; supported profiles có thể đạt CLEAR (`tests/unit/test_document_validity.py:45-315`).

Tuy vậy, final E0 contract mạnh hơn: strict 17 `DocumentType`, strict `DocumentEvidenceRole`, type↔role map code-owned, five-state `FieldState`, locator/source ownership, quote support, per-type schema và `SETTLEMENT_FORM` criticality (`IMPLEMENTATION_CONTRACTS.md:503-581`). Hoangha tests hiện chỉ là **partial precedent**, không phải proof cho contract này.

### 4.5 Deterministic matching

`test_paper_evidence_matching.py` thực sự exercise core matcher: exact invoice references, missing evidence, blank note, exception reason, alternative payment proof, payment proof không double-count, một evidence không auto-link hai lines, normalized vendor+amount auto-match (`tests/unit/test_paper_evidence_matching.py:36-312`). Ví dụ reuse demotion được assert trực tiếp: first link `AUTO_LINK`, second `SUGGEST_LINK` tại lines `219-250`.

Production matcher hiện pin score: exact invoice ref → `1.0`; nếu không thì amount `0.60` + semantic `<=0.30` + party `0.12/0.20` + non-original `0.10`; `<0.50` bỏ, `>=0.75` auto còn giữa là suggestion (`src/invoice_referee/application/paper_evidence_matching.py:149-199`). Final §15 **đã chốt port nguyên semantics này** (`ARCHITECTURE_AND_EVALUATION.md:552-555`; `IMPLEMENTATION_CONTRACTS.md:594-602`).

Khoảng trống: owner08 tests assert các outcome representative nhưng không có boundary test literal cho `0.50`, `0.75`, và không có direct test cho `0.90` LLM promotion. Vì vậy khi mang sang final, cần thêm regression **khóa đúng semantics đã chốt**, không chỉnh scoring trong test review này.

### 4.6 Repository, override, requeue, duplicate

`test_sqlite_settlement_repository.py` kiểm khá sâu local lifecycle với fake adapters:

- submit → `PENDING` → `run_once()` → `COMPLETED` + audit (`406-428`);
- external OCR failure → `PROCESSING_ERROR`, không giả thành request-info (`431-455`);
- same uploaded content ở case sau **không** tự trở thành duplicate-policy finding (`458-477`);
- accountant override ghi version/audit và thay decision (`480-500`);
- document pipeline fake OCR/fake extraction lưu OCR/facts/validity artifacts (`503-543`);
- warning/invalid/low-confidence gate dừng trước matching/extraction theo case (`546-839`);
- `REPROCESS_CASE` requeue cùng case rồi gọi `run_once()` lại (`842-868`);
- delete dọn DB/artifact/duplicate history và chặn unsafe case id (`871-902`).

`test_submit_case.py` còn kiểm duplicate cùng file trong một submission: file copy ở role khác bị bỏ và emit warning (`62-72`). Đây là coverage duplicate rõ ràng, nhưng vẫn là contract của Hoangha store/repository.

**Requeue không phải restart test.** Test `REPROCESS_CASE` chạy cùng process và cùng repository object; nó không kill/recreate app, không claim durable job sau process restart, không kiểm remaining budget. Vì vậy không được dùng test này làm proof cho §15 worker restart semantics.

### 4.7 FastAPI/Streamlit integration

FastAPI test fixture set:

```text
INVOICE_REFEREE_DISABLE_WORKER=1
UC03_DOCUMENT_PIPELINE_ENABLED=0
```

ngay tại `tests/integration/test_fastapi_app.py:8-14`. Case processing trong test được kích bằng `/internal/process-next` (`:80`, `:271`), nên integration suite này kiểm route/template/repository wiring, **không exercise background `worker_loop` và không exercise OCR/LLM document pipeline**.

Streamlit integration (`tests/integration/test_streamlit_app.py`) kiểm legacy app render/submit/OCR-debug/accounting-delete với `AppTest`. Nó hữu ích để thấy UI expectation và evidence preview nhưng không phải target runtime của `final`.

### 4.8 Corpus/evaluation

`test_uc3_testcase_catalog.py` chỉ kiểm manifest v2 có `case_count == 50`, 5 group × 10, expected decision enum, COVERED/PLANNED, và presence của request/evidence/oracle files (`tests/unit/test_uc3_testcase_catalog.py:19-55`).

Nó **không chứng minh** extraction/link answer quality, không chứng minh OCR/LLM behavior, và không phải final §15 75-case evidence evaluation. §15 còn nói UC-03 `expected.json` là financial corpus không độc lập và yêu cầu handwritten extraction/link gold trên subset (`ARCHITECTURE_AND_EVALUATION.md:564-566`). Plan evidence pipeline cũng ghi E8 phải bao phủ 75 formal UC-03 cases (`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md:356`).

## 5. Các contract user yêu cầu kiểm riêng

| Contract/scenario | Hoangha owner08 source coverage | Kết luận |
| --- | --- | --- |
| Background worker | FastAPI fixture **disable worker**; processor chỉ được gọi qua internal endpoint | **NOT COVERED** cho real `worker_loop` |
| Stop/control | Bounded source search không có test contract cho stop/cancel active background job | **NOT COVERED** trong owner08 |
| Accountant override | `test_accountant_override_is_versioned_and_audited` assert decision + previous decision + audit (`test_sqlite_settlement_repository.py:480-500`) | **COVERED ở Hoangha repository/service level** |
| Restart/resume durable job | Có `REPROCESS_CASE`, nhưng không restart process/recreate runtime (`:842-868`) | **NOT COVERED** cho §15 restart/resume |
| Auth/role enforcement | FastAPI integration gọi routes trực tiếp, không có 401/403/identity/permission assertions trong bounded owner08 search | **NOT COVERED** trong owner08; không suy rộng repo-wide ngoài phạm vi này |
| Duplicate | Same-file across roles (`test_submit_case.py:62-72`), later-case duplicate-policy behavior (`test_sqlite_settlement_repository.py:458-477`), deletion clears duplicate history (`:871-892`) | **COVERED cho Hoangha semantics** |
| Suggestion threshold `.50/.75` | Matcher production có thresholds; tests assert AUTO/SUGGEST outcomes nhưng không boundary literals | **PARTIAL** |
| LLM promote suggestion `>=.90` | Production `_resolve_suggested_paper_links` có candidate-only promote at `>=0.90`; bounded `tests/` search không có direct resolver/`accepted_links`/`LLM_RECONCILIATION` test | **NOT COVERED** |
| OCR-only all pages/no native bypass | OCR adapter request tests có image/PDF, nhưng không adversarial text-layer PDF/no-native proof | **NOT COVERED** cho §15 |
| Strict 17 types + code-owned roles | Legacy validity/extraction tests cover subset/types but không pin final 17-value enum/role compatibility | **NOT COVERED** cho E0 |
| `SETTLEMENT_FORM` schema/criticality | Hoangha uses legacy `PAPER_SETTLEMENT_REQUEST`; final-specific form matrix chưa có owner08 test | **NOT COVERED** |
| Global budget 8 files / 12 LLM / 10 OCR / one repair-root | Kimi unit checks one local repair; không có root budget accounting/restart remaining-budget test | **NOT COVERED** |
| `EVIDENCE_READY` + `assessment_ready=false` | Hoangha lifecycle kết thúc ở READY_FOR_APPROVAL/legacy outcomes | **NOT COVERED** |

## 6. Findings

### F08-1 — HIGH — VERIFIED TEST GAP: không có direct regression cho LLM suggestion promotion path

**Trigger.** Deterministic matcher tạo `SUGGEST_LINK`; `SettlementProcessingService._resolve_suggested_paper_links()` gọi `analyze_evidence_reconciliation`, lấy `accepted_links`, và promote candidate sẵn có thành `AUTO_LINK` khi confidence `>=0.90` (`src/invoice_referee/application/process_settlement.py:794-870`).

**Wrong behavior có thể lọt qua test.** Candidate sai có thể được promote; candidate mới ngoài deterministic set có thể bị chấp nhận nhầm; threshold `0.90` có thể drift; cùng document có thể bị reuse trái rule; resolver error path có thể làm mất/đổi deterministic uncertainty.

**Source evidence.** Bounded search toàn `tests/` không thấy `analyze_evidence_reconciliation`, `accepted_links`, `paper-link-resolution` hay `LLM_RECONCILIATION`. Search chỉ thấy `SUGGEST_LINK` trong deterministic matcher test. Đây là source-confirmed coverage gap, **không phải runtime bug claim**.

**Disposition cho final.** Port accepted semantics nguyên §15 rồi viết test cho: `<0.90` không promote; `==0.90` promote candidate có sẵn; unknown pair không được tạo; auto-linked document không reuse; resolver exception giữ deterministic suggestion; persisted reconciliation artifact đúng payload. Không thêm relation predicate/scoring mới nếu chưa có disposition riêng.

### F08-2 — HIGH — VERIFIED TEST GAP: FastAPI integration không exercise worker nền hoặc document pipeline

**Trigger.** App chạy theo cách production với worker lifespan và document pipeline enabled.

**Wrong behavior có thể lọt qua test.** Worker không claim job, loop chết, shutdown/cancel lỗi, concurrent worker xử lý cùng root, OCR/LLM path không wire, hoặc processing chỉ chạy khi gọi hidden internal endpoint.

**Source evidence.** `_load_app()` set `INVOICE_REFEREE_DISABLE_WORKER=1` và `UC03_DOCUMENT_PIPELINE_ENABLED=0` (`tests/integration/test_fastapi_app.py:8-14`). Integration test gọi `/internal/process-next` để xử lý (`:80`, `:271`). Production `create_app()` mới tạo `worker_loop()` khi env không disable (`app/fastapi_app.py:27-45`).

**Disposition cho final.** Không port test này như proof E7. Giữ nó cho route/UI smoke, và tạo integration riêng cho final worker/job lifecycle theo final contracts.

### F08-3 — HIGH — VERIFIED TEST GAP: Hoangha tests chưa khóa strict §15/E0 classification/extraction contract

**Trigger.** Final nhận mixed PDF/image, phân loại document unit, chọn schema và validate provenance.

**Wrong behavior có thể lọt qua test.** Model trả type/role ngoài enum; `UNKNOWN` vẫn bị schema-guess; role không tương thích type; overlapping units được chấp nhận; `FOUND` không có source ref/quote; `AMBIGUOUS` có single value; `SETTLEMENT_FORM` thiếu critical field vẫn pass.

**Source evidence.** Hoangha có `document_type`/field-state tests nhưng bounded owner08 search không có final `SETTLEMENT_FORM` DTO/schema contract, `EVIDENCE_READY`, `assessment_ready`, hay strict final role map. Authority final yêu cầu 17 types, 5 roles, five field states và source-aware field validation (`IMPLEMENTATION_CONTRACTS.md:503-581`). Plan E1/E4/E5 còn yêu cầu explicit failing tests cho enum/role/locator/schema/criticality trước code (`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md:150-152,216-243`).

**Disposition cho final.** Tái dùng legacy fixtures/profile examples làm seeds, nhưng viết final DTO/validation tests theo E0 trước khi nối matcher.

### F08-4 — HIGH — VERIFIED TEST GAP: không có proof cho §15 budget + restart/resume + one-active-job boundary

**Trigger.** Job bị restart giữa OCR/LLM calls, retry/repair xảy ra, hoặc hai worker cạnh tranh cùng root.

**Wrong behavior có thể lọt qua test.** Reset attempt counters sau restart, vượt 12 LLM/10 OCR, repair nhiều hơn một/root, chạy >8 source, hai worker cùng xử lý root, hoặc resume dùng basis khác.

**Source evidence.** Bounded `tests/` search không có root budget/restart/resume assertions. `REPROCESS_CASE` chỉ requeue và chạy lại cùng repository/process (`test_sqlite_settlement_repository.py:842-868`); FastAPI worker lại bị disable trong integration fixture. Final authority pin một active job/root, restart cùng basis với budget còn lại, ≤8 files / 12 LLM / 10 OCR / ≤1 repair-root (`ARCHITECTURE_AND_EVALUATION.md:541-543,559-561`).

**Disposition cho final.** Tạo test budget ledger + restart persistence + two-worker claim race ở final workflow; không coi Hoangha requeue test là substitute.

### F08-5 — MEDIUM — VERIFIED TEST GAP: Stop/control chưa được chứng minh trong owner08

**Trigger.** Human dừng một job đang xử lý.

**Wrong behavior có thể lọt qua test.** Stop chỉ đổi UI state nhưng provider call/job vẫn chạy; job resume sai; audit thiếu stop actor/reason; result sau stop vẫn commit.

**Source evidence.** Bounded source search owner08 không có stop/cancel control contract. Competition brief yêu cầu “tính năng can thiệp dừng và ghi đè hoạt động hiệu quả” trong human-control scoring (`docs/Challenge_Brief_OrganizationAI_VN.docx.md:202`). Hoangha có override test nhưng không có Stop test.

**Disposition cho final.** Đây là final workflow/control test obligation, không phải lý do sửa Hoangha source trong review này.

### F08-6 — MEDIUM — VERIFIED EVALUATION GAP: UC-03 test mới kiểm 50-case structure, chưa kiểm §15 evidence quality

**Trigger.** Dùng corpus test làm bằng chứng “evidence pipeline đã bao phủ UC-03”.

**Wrong conclusion.** 50 thư mục đầy đủ file/oracle có thể đều pass structural test trong khi OCR/classification/extraction/linking sai hoàn toàn.

**Source evidence.** `test_uc3_testcase_catalog.py:19-55` assert `case_count == 50`, 5 groups và artifact presence; không chạy reader/matcher. Final §15 còn yêu cầu handwritten extraction/link gold subset (`ARCHITECTURE_AND_EVALUATION.md:564-566`) và evidence-pipeline plan đặt 75 formal UC-03 cases ở E8 (`...hoangha-evidence-pipeline.md:356`).

**Disposition cho final.** Giữ structural catalog test nhưng tách nó khỏi evidence eval; thêm extraction/link gold tests và offline/LIVE evidence gates theo plan.

### F08-7 — MEDIUM — VERIFIED LIMIT: phần lớn document “end-to-end” tests dùng fake OCR/LLM

**Trigger.** Dùng green unit/integration suite để claim provider/model quality.

**Wrong conclusion.** Orchestration có thể đúng trong khi OCR trên scan thật, classification X-Kiro, extraction provenance hoặc suggestion resolver thực tế kém.

**Source evidence.** `test_process_case.py` và `test_sqlite_settlement_repository.py` inject fake OCR/reasoning classes; `test_kimi_reasoning.py` dùng fake completions. `test_fastapi_app.py` còn tắt document pipeline. LIVE/provider bị review này cấm chạy nên **model quality = NOT_EVALUATED**.

**Disposition cho final.** Dùng các test này làm deterministic harness; provider/model quality cần recorded replay/authorized LIVE eval riêng, có gold và ghi provider mode.

## 7. Model quyết định gì, code quyết định gì, human quyết định gì — nhìn từ test suite

| Chủ thể | Hoangha tests hiện mô tả | Ranh giới khi mang sang final |
| --- | --- | --- |
| Model/LLM | đánh giá readability/confidence, conflict, extraction, paper extraction; production còn có suggestion resolver | Chỉ proposal/observation theo strict schema; không được tự tạo role/scoring/policy/financial truth |
| Code | gate source/confidence, validate profile, tính matcher score/status, dedup/reuse, persist lifecycle/audit, route outcome | Giữ deterministic ownership; final code còn phải own type↔role, locator validation, budget, `EVIDENCE_READY` boundary |
| Human | accountant override/requeue/delete; human question trên uncertainty | Final cần thêm tested Stop/control/override audit theo accepted workflow |

## 8. DTO minh họa từ source tests

Các mẫu dưới đây là **minh họa**, không phải canonical JSON final.

**Input minh họa — deterministic matcher:**

```json
{
  "paper_line": {
    "description": "Chi phí ăn trưa Kiều Hoa Quán",
    "amount": "3314780",
    "requires_evidence": true
  },
  "document": {
    "document_id": "DOC-PAYMENT",
    "document_type": "PAYMENT_PROOF",
    "issuer_name": "Kiều Hoa Quán",
    "total_amount": "3314780"
  }
}
```

**Output minh họa — reuse demotion:**

```json
[
  {"document_id": "DOC-PAYMENT", "link_status": "AUTO_LINK"},
  {"document_id": "DOC-PAYMENT", "link_status": "SUGGEST_LINK"}
]
```

Source assertion: `tests/unit/test_paper_evidence_matching.py:219-250`.

**Input minh họa — accountant override:**

```json
{
  "action_type": "OVERRIDE_DECISION",
  "reason": "Cần xác minh thêm hợp đồng với khách hàng.",
  "override_decision": "REQUEST_INFO"
}
```

**Output minh họa:** automation decision trở thành `REQUEST_INFO`, primary finding `HUMAN_OVERRIDE`, human action lưu previous decision, audit event `OVERRIDE_DECISION` (`tests/unit/test_sqlite_settlement_repository.py:480-500`).

## 9. Nên mang gì sang `final`

Nên tái dùng **test ideas/fixtures**, không copy nguyên lifecycle Hoangha:

1. **Matcher regression set** từ `test_paper_evidence_matching.py` gần như nguyên logic, vì §15 đã chốt port full matcher core. Bổ sung boundary `.50/.75/.90` và direct suggestion-resolver tests.
2. **Confidence fail-closed matrix** từ `test_process_case.py`, đặc biệt unassessed candidate, exact identifier, code criticality không bị model hạ cấp.
3. **LLM fake-completion contract style** từ `test_kimi_reasoning.py`: one repair, schema error feedback, complete-candidate validation, fail closed; adapter target đổi sang X-Kiro.
4. **OCR request + block/confidence mapping fixtures** từ `test_mistral_ocr.py`, `test_word_block_mapper.py`, `test_ocr_quality.py`; bổ sung final all-page/no-native text-layer cases.
5. **Provider failure distinction** từ repository tests: external failure phải là technical processing error, không biến thành business `REQUEST_INFO`.
6. **Audit/override/duplicate regression concepts**; mapping sang final command/job/schema thay vì kéo `SQLiteSettlementRepository` Hoangha vào.

Adapter cần khi port:

- Hoangha `ExpenseDocumentFacts`/`PaperSettlementFacts` → final `DocumentAnalysis`/`FieldCandidate`/`DocumentLine` theo E0;
- legacy `PAPER_SETTLEMENT_REQUEST` → final `SETTLEMENT_FORM` strict type;
- Kimi fake completion seam → `XkiroClient` fake transport;
- Hoangha repository `run_once()` fixtures → final durable job/worker harness;
- legacy decision statuses → final evidence-only `EVIDENCE_READY`, `assessment_ready=false`, `EVIDENCE_ADMISSION_NOT_CONNECTED` trước financial assessment.

Không mang sang §15: inventory policy gold, Hoangha settlement financial policy decisions, Streamlit lifecycle, Kimi provider, hoặc repository/database lifecycle thứ hai.

## 10. Test plan tối thiểu trước khi coi Hoangha evidence logic đã được tích hợp đúng

Đây là test plan để **bảo toàn accepted semantics**, không phải policy change:

1. Contract tests strict 17 `DocumentType`, 5 `DocumentEvidenceRole`, compatibility map, five field states, locator bounds/source ownership và `SETTLEMENT_FORM` critical matrix.
2. OCR-only tests cho image, scanned PDF, text-layer PDF, mixed PDF; mọi page phải đi OCR và không native bypass.
3. Matching boundary tests: `<.50`, `=.50`, `<.75`, `=.75`, exact invoice ref `1.0`, reuse demotion; direct LLM promotion `<.90`/`=.90`, unknown pair rejected, resolver failure preserves suggestion.
4. Budget tests: >8 files, OCR attempt 10→11, LLM 12→13, second repair; counters persisted qua restart.
5. Worker tests: enqueue durable, one active job/root, two-worker claim race, process restart/resume cùng basis, Stop prevents late commit, audit records control.
6. Evidence boundary test: LIVE/RECORDED evidence completion → `EVIDENCE_READY`, `assessment_ready=false`, blocker `EVIDENCE_ADMISSION_NOT_CONNECTED`; không tự chạy finance/policy.
7. Evaluation tests: 75-case catalog coverage + handwritten extraction/link gold subset; structural presence test giữ riêng với accuracy/contract evaluation.

## 11. Verdict

**Hoangha test suite là nguồn regression rất đáng dùng, nhưng là evidence cho Hoangha contracts — chưa phải acceptance evidence cho final §15.** Phần nên port mạnh nhất là deterministic matcher tests, confidence/fail-closed cases, fake LLM schema/repair pattern và OCR block/confidence fixtures. Phần phải viết mới ở final là strict E0 taxonomy/schema/provenance, all-page OCR-only, LLM suggestion promotion, global budget, background worker/restart/Stop, và `EVIDENCE_READY` consumer boundary.

Findings source-confirmed: **F08-1…F08-7**. Trong đó F08-1/F08-2/F08-3/F08-4 là các gap ưu tiên cao trước integration. Không finding nào ở report này tự thay đổi matching/policy semantics đã chốt.

**Execution status của review:** 23/23 owner files đọc full; 149 AST test definitions; tests **NOT_RUN**; LIVE/provider **NOT_RUN**; graph coverage **UNKNOWN** vì coverage API không exposed.

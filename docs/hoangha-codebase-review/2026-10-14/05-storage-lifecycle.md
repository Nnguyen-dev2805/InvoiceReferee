# 05 — Storage & lifecycle

## Scope và kết luận

Đã đọc đầy đủ **9/9 file owner `05-storage-lifecycle`**, tổng **2.110 dòng**, theo `inventory.json` của worktree Hoangha tại `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Các finding bên dưới là **source-verified**. Test files chỉ được đọc như bằng chứng về assertion; **runtime/tests/build/generator/LIVE: NOT_RUN** theo ràng buộc của review, nên không claim hành vi runtime đã được xác nhận. CodeGraph đã được parent dùng ở mức Verify cho discovery, nhưng `check_index_coverage`/generation không exposed nên **graph coverage = UNKNOWN**; các file owner trong bảng được xác minh bằng full source read.

### Coverage ledger từng file

| File | Dòng | Vai trò | Input → Output | Hàm/chủ thể chính; caller → callee | Hành vi lỗi đáng chú ý | Khả năng mang sang `final` |
|---|---:|---|---|---|---|---|
| `src/invoice_referee/application/review_settlement.py` | 101 | Orchestrate human action cho UC-03 | `case_id/action/actor/reason/override` → mutation workflow/decision | `ReviewSettlementService.record_action()`; web review route → `record_human_action()` / `requeue_case()` | reason/action không hợp lệ bị từ chối; case không tồn tại được repository surface | **Có**, nhưng phải giữ authority/policy contract của `final` |
| `src/invoice_referee/application/settlement_summary.py` | 90 | Tạo business/cash-flow summary deterministic cho UI | case mapping → label/số tiền/reason hiển thị | `build_settlement_business_summary()`, `build_settlement_success_reason()`; web routes → helper Decimal/format | dữ liệu số không parse được có thể lỗi tại Decimal conversion; không tự sửa dữ liệu | **Có chọn lọc** cho presentation, không dùng như settlement ledger |
| `src/invoice_referee/application/submit_case.py` | 121 | Legacy `CASE-*` submission | `ClaimDraft + UploadPayload[]` → `SubmissionReceipt` | `SubmitCaseService.submit()`; Streamlit form → `CaseStore.save_submission()` → optional processor | validate extension/size; duplicate SHA trong request bị bỏ qua kèm warning; processor exception không có queue recovery tại layer này | **Thấp**; giữ ý tưởng validation, không kéo lifecycle legacy sang UC-03 |
| `src/invoice_referee/application/submit_settlement.py` | 167 | UC-03 submission validation/orchestration | `SettlementDraft + SettlementUpload[]` → `SettlementReceipt` | `SubmitSettlementService.submit()`; FastAPI route/runtime → `SQLiteSettlementRepository.create_case()` | gom validation issues rồi raise; duplicate name/SHA trong request, paper/digital link rules bị chặn | **Cao**, nhưng cần adapter vào DTO/repository contract của `final` |
| `src/invoice_referee/storage/__init__.py` | 19 | Package export boundary cho storage | module import → exported storage symbols | `__all__`; callers dùng `from invoice_referee.storage import ...` → concrete modules | import-time failure nếu dependency/module con lỗi | **Có**, chủ yếu là package boundary |
| `src/invoice_referee/storage/base.py` | 17 | Port tối thiểu của legacy submit | `ClaimDraft + uploads` → `SubmissionReceipt` | `CaseStore.save_submission()` protocol; `SubmitCaseService` → `LocalCaseStore` | không định nghĩa error/retry/query contract | **Thấp** cho `final`; interface quá hẹp cho UC-03 |
| `src/invoice_referee/storage/local_case_store.py` | 158 | Filesystem writer cho legacy `CASE-*` | draft/uploads → source files + `submission.json` + `audit.jsonl` + receipt | `LocalCaseStore.save_submission()`; `SubmitCaseService` → filesystem/temp-dir rename | collision/IO raise; exception trước publish dọn temp dir | **Chọn lọc**: safe filename + temp publish pattern hữu ích |
| `src/invoice_referee/storage/local_evidence_repository.py` | 158 | Filesystem query/artifact adapter của legacy | case/evidence ID, OCR/result JSON → `StoredCase`/path/artifact | `LocalEvidenceRepository`; `CaseProcessingService`/Streamlit views → filesystem | path traversal/missing file bị chặn; `list_cases()` bỏ qua metadata/JSON hỏng nên có thể làm mất case khỏi list mà không surface nguyên nhân | **Chọn lọc** cho path guard/artifact helpers, không dùng làm UC-03 source of truth |
| `src/invoice_referee/storage/sqlite_settlement_repository.py` | 1279 | Hybrid SQLite + filesystem repository cho UC-03 | draft/uploads/jobs/findings/decisions/actions/artifacts → receipt/job/case detail/files | `SQLiteSettlementRepository`; submit/process/review services + worker/routes → SQLite/filesystem/audit helpers | `FileNotFoundError`/`ValueError`/SQLite/IO được surface; có compensation nhưng còn crash window DB↔filesystem, không lease/cancel invariant cho job | **Cao**, nhưng cần harden lifecycle/recovery/atomicity trước khi merge vào `final` |

<!-- reviewed-file: src/invoice_referee/application/review_settlement.py -->
<!-- reviewed-file: src/invoice_referee/application/settlement_summary.py -->
<!-- reviewed-file: src/invoice_referee/application/submit_case.py -->
<!-- reviewed-file: src/invoice_referee/application/submit_settlement.py -->
<!-- reviewed-file: src/invoice_referee/storage/__init__.py -->
<!-- reviewed-file: src/invoice_referee/storage/base.py -->
<!-- reviewed-file: src/invoice_referee/storage/local_case_store.py -->
<!-- reviewed-file: src/invoice_referee/storage/local_evidence_repository.py -->
<!-- reviewed-file: src/invoice_referee/storage/sqlite_settlement_repository.py -->

Nhóm này có **hai hệ lưu trữ/lifecycle khác nhau đang cùng tồn tại**:

1. **Legacy Streamlit / `CASE-*`**: `SubmitCaseService` → `CaseStore` → `LocalCaseStore`, sau đó `LocalEvidenceRepository` đọc file, lưu OCR/processing artifact. Dữ liệu chính nằm trên filesystem.
2. **FastAPI UC-03 / `SET-*`**: `SubmitSettlementService` → `SQLiteSettlementRepository`, metadata/lifecycle nằm trong SQLite, source/canonical/OCR artifact nằm trên filesystem, xử lý qua `processing_jobs` background queue.

Không nên mô tả chúng như cùng một repository hay cùng một lifecycle. `CaseStore` chỉ là port của legacy submission; UC-03 phụ thuộc trực tiếp vào `SQLiteSettlementRepository`.

## 1. Legacy Streamlit storage

### Submission

`SubmitCaseService.submit()` kiểm tra giới hạn file/extension, deduplicate theo SHA-256 trong chính request, rồi gọi `CaseStore.save_submission()` (`submit_case.py:55-69`, `107-121`). File trùng giữa các role bị bỏ qua và chỉ tạo warning.

`CaseStore` chỉ định nghĩa đúng một operation `save_submission()` (`storage/base.py:10-17`). Đây không phải abstraction cho query, OCR, review hay UC-03.

`LocalCaseStore.save_submission()` tạo `CASE-*`, ghi toàn bộ source file, `submission.json`, `audit.jsonl` vào temp directory rồi mới `replace()` sang case directory cuối (`local_case_store.py:51-144`). Trong phạm vi một filesystem, đây là cơ chế publish nguyên case khá rõ ràng: exception trước rename sẽ xóa temp directory.

`submission.json` giữ claim + evidence metadata; audit ban đầu chỉ có `CASE_CREATED` và `EVIDENCE_ATTACHED` (`local_case_store.py:96-139`).

### Query và processing artifact

`LocalEvidenceRepository` là adapter riêng để đọc case đã lưu, không implement `CaseStore`. Nó dựng `StoredCase`/`StoredEvidence`, resolve path và chặn evidence path thoát khỏi case directory (`local_evidence_repository.py:33-87`).

Artifact được ghi trực tiếp theo case:

- OCR: `ocr/<evidence_id>.json` (`89-108`).
- Kết quả xử lý: `processing.json`, đồng thời append `CASE_PROCESSED` vào `audit.jsonl` (`110-137`).

`list_cases()` bỏ qua case có metadata lỗi/JSON lỗi thay vì surface lỗi (`39-49`). Vì vậy inventory/list UI có thể thiếu case hỏng mà không báo nguyên nhân.

`delete_case()` xóa thẳng toàn bộ directory bằng `shutil.rmtree()` sau khi validate `CASE-*` path (`139-158`). Không có soft-delete hoặc recovery lifecycle.

### Lifecycle legacy

Nếu `SubmitCaseService` được inject `processor`, processing chạy **đồng bộ ngay sau save** và receipt status được thay bằng decision của processor (`submit_case.py:64-69`). Nếu không có processor, receipt dừng ở `RECEIVED`.

Nói cách khác, legacy không có persistent job queue trong storage này; lifecycle processing do composition layer quyết định.

## 2. FastAPI UC-03 storage

### Data model

`SQLiteSettlementRepository` quản lý các bảng chính:

- `settlement_cases`
- `expense_items`
- `settlement_documents`
- `expense_item_documents`
- `settlement_findings`
- `settlement_decisions`
- `processing_jobs`
- `audit_events`
- `human_actions`

Source file/canonical JSON vẫn nằm ngoài DB dưới `artifacts_root` (`sqlite_settlement_repository.py:36-185`). Vì vậy đây là **hybrid SQLite + filesystem**, không phải SQLite-only.

### Submission → queued processing

`SubmitSettlementService` validate chặt hơn legacy: tên file trùng và SHA trùng trong cùng hồ sơ là validation error, evidence link phải khớp item đối với digital form, paper scan phải có đúng một settlement request form (`submit_settlement.py:47-167`).

Sau validation, service gọi thẳng concrete `SQLiteSettlementRepository.create_case()` (`55-60`).

`create_case()`:

1. tạo `SET-*` và temp artifact directory;
2. ghi immutable source files + `canonical/settlement_request.v1.json`;
3. insert case/items/documents;
4. insert một `PROCESS_SETTLEMENT/PENDING` job;
5. insert `CASE_CREATED` audit;
6. commit DB context;
7. rename temp directory thành case directory (`sqlite_settlement_repository.py:329-526`).

Receipt trả về `workflow_status=ACTIVE`, `processing_status=PENDING`.

### Worker lifecycle

`claim_next_job()` dùng `BEGIN IMMEDIATE`, lấy job `PENDING` cũ nhất, chuyển job sang `RUNNING` và case sang `PROCESSING` trong cùng DB transaction (`528-559`). Cơ chế này serialize việc claim giữa SQLite writers, tránh hai worker cùng claim một pending row trong đường chạy bình thường.

`complete_job()` replace findings hiện tại, **append** một decision version mới, cập nhật case sang `COMPLETED`, job sang `COMPLETED`, rồi ghi `CASE_PROCESSED` audit (`572-660`).

`fail_job()` chuyển job sang `FAILED`, case sang `PROCESSING_ERROR`, giữ error message và audit `PROCESSING_FAILED` (`662-689`).

## 3. Human review lifecycle

`ReviewSettlementService` hỗ trợ:

- `REQUEST_MORE_INFO` → `WAITING_EMPLOYEE`
- `ESCALATE_CASE` → `ESCALATED`
- `OVERRIDE_DECISION` → tạo decision mới và workflow tương ứng
- `STOP_PROCESSING` → `STOPPED`
- `REPROCESS_CASE` → gọi `requeue_case()`

Mọi action yêu cầu reason (`review_settlement.py:18-101`).

`record_human_action()` lưu `human_actions`, có thể append decision mới, cập nhật case state và ghi audit event (`sqlite_settlement_repository.py:691-797`). Decision history vì vậy có version theo row mới chứ không overwrite bảng decision.

`requeue_case()` append human action, **tạo thêm một PENDING job**, reset `automation_decision/uncertainty/primary_finding_code` và đưa case về `ACTIVE/PENDING` (`799-860`). Findings/decision rows cũ vẫn còn trong DB cho tới lần xử lý tiếp theo; `get_case()` ẩn latest decision khi `automation_decision` hiện tại là NULL, nhưng findings cũ vẫn được query.

## 4. Các lifecycle gap có bằng chứng trong source

### A. `STOP_PROCESSING` không hủy processing job

Đây là gap quan trọng nhất.

`STOP_PROCESSING` chỉ gọi `record_human_action(... workflow_status="STOPPED", new_decision=None)` (`review_settlement.py:88-100`). `record_human_action()` không cancel `processing_jobs` (`sqlite_settlement_repository.py:691-797`).

Trong khi đó `claim_next_job()` chỉ lọc `processing_jobs.status='PENDING'`, **không kiểm tra `settlement_cases.workflow_status`** (`528-559`). Vì vậy một case vừa bị STOP vẫn có thể được worker claim và xử lý tiếp nếu job còn pending; case đang RUNNING cũng không bị interrupt.

### B. Không có lease/recovery cho job `RUNNING`

`processing_jobs` có status/attempts/start/finish nhưng không có lease owner, heartbeat hoặc timeout recovery trong repository. Nếu worker chết sau khi job được chuyển sang `RUNNING`, source đang đọc không có đường tự động đưa row đó về `PENDING`.

### C. `REPROCESS_CASE` có thể tạo nhiều job

`requeue_case()` insert PENDING job mới mà không kiểm tra case đã có `PENDING/RUNNING` job hay chưa, và schema không có unique constraint bảo đảm một active job/case (`processing_jobs`, `requeue_case():799-860`). Đây là lifecycle invariant chưa được storage enforce.

### D. SQLite + filesystem không phải một atomic transaction

`create_case()` ghi temp files, commit SQLite transaction, rồi mới rename temp directory sang final directory (`329-516`). Exception thông thường sau DB commit được compensating delete case row, nhưng process crash giữa DB commit và final rename không thể được Python `except` dọn. Do đó atomicity ở đây là best-effort/compensating, không phải transaction xuyên DB + filesystem.

`delete_case()` cũng dùng staged rename filesystem → delete DB → xóa staged directory (`1127-1166`). Nó có rollback rename nếu DB delete ném exception, nhưng crash giữa các bước vẫn là một failure window.

### E. Migration bookkeeping không phải ordered migration engine

`_initialize()` chạy toàn bộ `SCHEMA_SQL`, kiểm tra một số column rồi `ALTER TABLE` nếu thiếu, sau đó `INSERT OR IGNORE` version 1–4 (`214-281`). Version rows không điều khiển từng migration theo thứ tự; chúng chủ yếu là bookkeeping sau heuristic schema repair. Không nên mô tả đây là migration framework đầy đủ.

## 5. Duplicate semantics khác nhau

Legacy `SubmitCaseService` silently deduplicate cùng SHA trong một submission và trả warning (`submit_case.py:107-121`).

UC-03 `SubmitSettlementService` coi duplicate filename hoặc duplicate SHA trong cùng submission là validation issue (`submit_settlement.py:75-86`). Repository còn có `find_duplicate_uploads()`/`find_case_duplicate_documents()` để phát hiện SHA đã xuất hiện ở case khác (`sqlite_settlement_repository.py:286-327`), nhưng submission service không gọi `find_duplicate_uploads()` trong path hiện tại.

Test hiện có còn khẳng định file giống ở case sau **không tự kích hoạt duplicate policy** (`tests/unit/test_sqlite_settlement_repository.py:458-477`). Vì vậy không được claim rằng UC-03 đang chặn cross-case duplicate chỉ vì repository có helper này.

## 6. Business summary không phải settlement ledger

`build_settlement_business_summary()` tính cash-flow từ `claimed_total` và `allocated_advance_amount`; reimbursement dùng toàn bộ claimed total (`settlement_summary.py:21-73`). Đây là deterministic UI/business summary, không phải bằng chứng có accepted/approved amount riêng hay payment execution ledger.

## 7. Boundary thực tế

| Concern | Legacy Streamlit | FastAPI UC-03 |
|---|---|---|
| ID | `CASE-*` | `SET-*` |
| Metadata source of truth | `submission.json` | SQLite |
| Source files | filesystem | filesystem |
| Canonical normalized request | không có contract tương đương trong storage này | `canonical/settlement_request.v1.json` |
| Processing | optional synchronous processor | persistent `processing_jobs` queue |
| Findings/decision | `processing.json` | normalized DB tables + decision history |
| Human action history | không có model tương đương ở storage này | `human_actions` + `audit_events` |
| Delete | direct `rmtree` | staged filesystem delete + DB cascade |
| Storage abstraction | `CaseStore` chỉ save | service phụ thuộc concrete repository |

## Kết luận review

Storage hiện tại đủ để demo hai luồng riêng, nhưng lifecycle UC-03 chưa nên được gọi là robust job orchestration. Trước production nên ưu tiên invariant cho active job/case, cancel/stop semantics, recovery cho RUNNING job và reconciliation DB↔filesystem. Đồng thời tài liệu phải luôn tách legacy `CASE-*` với UC-03 `SET-*`; gộp hai luồng sẽ tạo claim sai về storage, queue và review lifecycle.

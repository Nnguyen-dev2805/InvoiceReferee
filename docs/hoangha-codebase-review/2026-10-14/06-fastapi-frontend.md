# 06 — FastAPI frontend review: Hoangha → final

Ngày review: 14/10/2026
Reviewer: độc lập, read-only đối với source Hoangha
Nhóm inventory: `06-fastapi-frontend`

## 1. Phạm vi, bằng chứng và verdict

Tôi review đúng checkout:

- source: `/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.worktrees/hoangha`
- commit: `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`
- inventory: `docs/hoangha-codebase-review/2026-10-14/inventory.json` ở parent repo
- số file owned: **14/14 file đã đọc toàn bộ**, tổng **2.595 dòng**; line count và SHA-256 của cả 14 file đều khớp inventory tại thời điểm review
- không có file `PARTIAL`
- không chạy test, build, generator hay LIVE; các nhận định runtime bên dưới vì vậy chỉ được coi là **source-verified wiring**, trừ khi tôi ghi rõ là bằng chứng từ test source

Graph được dùng ở tier **Verify** trước source fallback. `codegraph status` trên đúng worktree báo **81 files / 1.204 nodes / 3.561 edges / 13 routes**, index `up to date`. MCP hiện không expose generation id và `check_index_coverage`, nên **graph coverage = UNKNOWN**. Để không biến graph coverage thành claim completeness, tôi đã đọc raw source toàn bộ 14 file owned và đọc caller/callee cần thiết ngoài scope. Không thay đổi index.

Đối với kết luận về đề thi, tôi đối chiếu trực tiếp `docs/Challenge_Brief_OrganizationAI_VN.docx.md`: đề A yêu cầu routine được tự xử lý, ba nhóm uncertainty, câu hỏi chuyển tiếp cụ thể và không khẳng định dữ liệu đã bị gắn nghi vấn (`:41-59`). Đường dẫn live phải truy cập công khai và Verify phải chạy nhanh (`:169-171`). Đây là lý do các mutation công khai và provenance actor ở web boundary là vấn đề thật khi ghép vào `final`, không chỉ là yêu cầu enterprise ngoài đề.

**Verdict:** FastAPI/Jinja surface của Hoangha là một prototype **đã wired thực sự** vào `SubmitSettlementService` → SQLite repository → `SettlementProcessingService` → `ReviewSettlementService`, có upload, queue, review, delete, polling và OCR preview. Có nhiều cơ chế đáng mang sang `final`, đặc biệt upload contract, source-ref decoration và OCR preview. **Không nên merge nguyên surface này vào final**. Có 8 finding source-verified cần disposition; 4 finding đầu là blocker cho việc port trực tiếp vì xung đột với actor/authority, lifecycle hoặc money/evidence contract đã chốt của final.

## 2. Trạng thái kiến trúc: wired, legacy hay tooling

### 2.1. Luồng FastAPI đang wired

`app/fastapi_app.py:27-59` tạo `AppSettings`, gọi `build_runtime()`, gắn runtime vào `app.state`, mount `/static`, include router, và trong lifespan chạy worker nền bằng `asyncio.to_thread(runtime.processor.run_once)` (`:31-45`). Đây không phải mock UI đứng riêng.

`app/web/runtime.py:28-72` là composition root thực: tạo `SQLiteSettlementRepository`, `SettlementPolicyConfig`, `SubmitSettlementService`, `SettlementProcessingService`, `ReviewSettlementService`; nếu document pipeline bật, nó tạo `MistralOcrAdapter` khi có Mistral key và `KimiReasoningAdapter` khi đủ Kimi config (`:37-57`). Vì thế web surface có thể đi vào OCR/reasoning thật khi môi trường có credential. **Tôi không gọi LIVE trong review này.**

`app/web/routes.py:560-871` định nghĩa **13 route**. Các route HTML đọc trực tiếp repository và render Jinja; các route mutation gọi service/repository thật. `POST /api/v1/settlements` tạo `SettlementDraft`/`SettlementUpload`, `POST /accounting/.../actions` gọi human-review service, `POST /internal/process-next` gọi processor, và document route trả file thật từ artifact store.

### 2.2. Phần compatibility/legacy

`_case_outcome_key()` (`app/web/routes.py:126-146`) có lớp compatibility rõ ràng: `AUTO_PROCESS` được trình bày thành `READY_FOR_APPROVAL`; một số `ESCALATE` cũ được remap sang `ACCOUNTANT_REVIEW` hoặc `RECOMMEND_REJECT` dựa trên `uncertainty_type` và `primary_finding_code`. `LEGACY_REJECTION_RULES`/`LEGACY_ESCALATION_RULES` ở `:114-123` xác nhận đây là presentation compatibility, không phải canonical domain mới.

`app/__init__.py:1` vẫn ghi `"Streamlit UI package."` trong khi package hiện chứa FastAPI; đây là stale docstring nhỏ. `app/web/__init__.py:1` mới mô tả đúng FastAPI package.

### 2.3. Tooling/presentation

Jinja templates + CSS + `settlement-form.js` là server-rendered frontend. Final design đã chốt ở `docs/final/ARCHITECTURE_AND_EVALUATION.md` rằng frontend đích là **React/TypeScript/Vite**, còn server view là authoritative. Do đó CSS/layout và interaction ở đây hữu ích như reference, nhưng không phải frontend stack cần merge nguyên vẹn.

## 3. Inventory 14/14 file — vai trò và cơ chế

<!-- reviewed-file: app/__init__.py -->
<!-- reviewed-file: app/fastapi_app.py -->
<!-- reviewed-file: app/static/css/app.css -->
<!-- reviewed-file: app/static/js/settlement-form.js -->
<!-- reviewed-file: app/templates/accounting/_finding_body.html -->
<!-- reviewed-file: app/templates/accounting/case_detail.html -->
<!-- reviewed-file: app/templates/accounting/queue.html -->
<!-- reviewed-file: app/templates/base.html -->
<!-- reviewed-file: app/templates/employee/case_status.html -->
<!-- reviewed-file: app/templates/employee/new_settlement.html -->
<!-- reviewed-file: app/web/__init__.py -->
<!-- reviewed-file: app/web/ocr_preview.py -->
<!-- reviewed-file: app/web/routes.py -->
<!-- reviewed-file: app/web/runtime.py -->

| File | Dòng | Vai trò | Input → output | Hàm chính / caller → callee | Hành vi lỗi | Khả năng dùng lại cho final |
|---|---:|---|---|---|---|---|
| `app/__init__.py` | 1 | Package marker, docstring còn nói Streamlit | import package → không có runtime output | Không có hàm | Không có | **Không cần port**; sửa mô tả khi hợp nhất package nếu file còn tồn tại |
| `app/fastapi_app.py` | 62 | Entrypoint + app lifecycle | env/settings → `FastAPI` app có runtime/router/static/worker | `create_app()` `:27-59`; lifespan → `runtime.processor.run_once()` `:33-45`; import-time `app=create_app()` `:62` | Startup có thể fail nếu settings/runtime fail; worker exception không được catch trong loop | **Dùng pattern có chọn lọc**: composition/lifespan hữu ích, nhưng final cần actor boundary và worker lifecycle theo contract final |
| `app/static/css/app.css` | 363 | Toàn bộ presentation cho sidebar/form/queue/detail/OCR evidence | HTML class → responsive visual layout | CSS được `base.html:7` load | Không có business error | **Reference visual**; final React nên chuyển design tokens/layout, không copy như business logic |
| `app/static/js/settlement-form.js` | 353 | Client form state, expense rows, file mapping, multipart submit | DOM + selected files → JSON `payload` + `FormData` → `POST /api/v1/settlements` | `addExpense()` `:48-116`; `renderFileMapping()` `:129-171`; `buildPayload()` `:184-242`; submit handler `:285-350` | Local issues hiển thị trong `#form-errors`; network fail báo lỗi chung `:344-345`; server 4xx dùng `issues/detail` | **Port interaction intent, không port identity/policy**; React nên dùng typed DTO/server view và actor từ server |
| `app/templates/accounting/_finding_body.html` | 68 | Partial hiển thị finding + question + source citation + OCR preview | decorated finding → HTML audit evidence | được include từ `case_detail.html:273,297` | Nếu preview/citation thiếu thì degrade sang label/original file | **Nên giữ concept** progressive evidence + exact source ref; chuyển thành React component |
| `app/templates/accounting/case_detail.html` | 390 | Màn review kế toán đầy đủ | decorated case → human review UI | action form `:83-120`; expense/matches `:213-258`; findings `:259-335`; source gallery `:336-376`; audit `:377-389` | `action_error` mở review panel; processing error có banner | **Reference mạnh về information architecture**, nhưng mutation phải đi qua final CaseWorkflow/actor/grant; không copy advance behavior |
| `app/templates/accounting/queue.html` | 97 | Queue theo time/outcome | timeline summary + decorated cases → table/filter UI | GET `/accounting/cases` cung cấp context | Empty-state khi không case | **Port layout/filter ideas**; dữ liệu phải đến từ canonical server view của final |
| `app/templates/base.html` | 37 | Shell + navigation | `active_page` → sidebar | được mọi template extend | Không có | **Visual reference**; nav hiện không có server-side role distinction |
| `app/templates/employee/case_status.html` | 36 | Trang trạng thái nộp hồ sơ | raw `case` → status/decision | GET employee status; meta refresh 3s khi `PENDING/PROCESSING` `:3-6` | 404 được route xử lý; nếu chưa decision hiển thị đang xử lý | **Có thể port polling semantics**, nhưng final React nên poll server view/API thay meta refresh |
| `app/templates/employee/new_settlement.html` | 141 | Form employee | browser fields/files → JS | script ở `:139-140`; advance declaration `:79-85`; evidence picker `:113-131` | validation chủ yếu ở JS + server DTO/service | **Không port nguyên form**; source/evidence UX hữu ích, nhưng actor và money/history phải theo final contract |
| `app/web/__init__.py` | 1 | Package marker đúng FastAPI | import → none | Không có | Không có | Giữ nếu package vẫn tồn tại |
| `app/web/ocr_preview.py` | 103 | Render trang ảnh/PDF và highlight OCR bbox | source path + page + OCR bbox/dimensions → PIL image | `_load_page()` `:14-34`; `render_ocr_block_preview()` `:37-103`; caller route `routes.py:852-858` | Reject page index/dimensions/bbox sai; PyMuPDF/PIL errors ngoài các validate cụ thể có thể nổi lên | **Khả năng tái dùng cao** như presentation adapter cho source locator |
| `app/web/routes.py` | 871 | HTML + JSON boundary và view-model decoration | HTTP → DTO/service/repository → JSON/HTML/file | `_decorate_accounting_case()` `:381-557`; `build_router()` `:560-871`; callers từ `create_app()` | 422 cho payload/action invalid; 404 case/doc/OCR; 400 delete case-id invalid | **Chỉ port seam/DTO ideas**. Không port raw repository access, anonymous mutation, legacy outcome mapping làm canonical |
| `app/web/runtime.py` | 72 | Composition root FastAPI surface | `AppSettings` + env credential → `WebRuntime` | `build_runtime()` `:28-72`; caller `create_app()` | Thiếu OCR/reasoning credential không fail startup; processor sẽ phát finding khi cần pipeline | **Dùng wiring tham khảo**, nhưng final adapter/model names phải theo canonical config; không để web runtime tự quyết authority |

## 4. Luồng thực tế theo điều kiện source

### 4.1. Startup và worker

```text
import app.fastapi_app
  → AppSettings.from_environment(PROJECT_ROOT)
  → build_runtime(settings)
      → SQLiteSettlementRepository
      → SubmitSettlementService
      → SettlementProcessingService
      → ReviewSettlementService
  → app.state.runtime = runtime
  → include build_router(...)
  → lifespan
      → worker_loop
          → asyncio.to_thread(processor.run_once)
```

Worker tự chạy trừ khi `INVOICE_REFEREE_DISABLE_WORKER=1` (`app/fastapi_app.py:38-40`). Mỗi vòng sleep 0,25s nếu vừa xử lý một job, 1,5s nếu queue rỗng (`:35-36`). Test integration source cố ý disable worker và document pipeline để điều khiển job bằng `/internal/process-next` (`tests/integration/test_fastapi_app.py:8-14`). Vì vậy test source đó không chứng minh background worker + provider thật chạy ổn.

### 4.2. Digital form: browser → DTO → persisted case

JS xây expense rows và mapping file theo filename. Với digital form, `buildPayload()` (`app/static/js/settlement-form.js:184-242`) tạo `expense_items` và đưa `evidence_names` của từng item vào JSON. Mỗi file được chọn một target item trong UI (`:129-160`).

**Minh họa DTO input** — giá trị minh họa, tên field là field thật:

```json
{
  "settlement_type": "EMPLOYEE_REIMBURSEMENT",
  "source_type": "DIGITAL_FORM",
  "employee": {
    "employee_id": "EMP-DEMO-001",
    "name": "Nguyễn Minh An",
    "department": "Phòng Kinh doanh",
    "position": "Nhân viên",
    "data_classification": "SYNTHETIC"
  },
  "business_context": {
    "purpose": "Tiếp khách dự án Demo"
  },
  "allocated_advance_amount": "0",
  "currency": "VND",
  "expense_items": [
    {
      "item_id": "ITEM-001",
      "category": "CLIENT_MEAL",
      "description": "Bữa trưa với khách hàng",
      "claimed_amount": "1200000",
      "currency": "VND",
      "evidence_names": ["bill.jpg"],
      "evidence_status": "ORIGINAL_EVIDENCE"
    }
  ]
}
```

Request thật là multipart: JSON trên nằm trong form field `payload`, file nằm ở `evidence_files`. Route parse JSON bằng `SettlementDraft.model_validate()` (`app/web/routes.py:737-743`), đọc file thành `SettlementUpload` (`:745-785`) và map `linked_item_id` bằng filename case-insensitive (`:757-785`). Service còn kiểm duplicate name/hash, extension, size và consistency giữa `evidence_names` với upload (`src/invoice_referee/application/submit_settlement.py:62-167`).

Repository tạo `SET-...`, canonical JSON, rows trong SQLite, documents và job `PENDING`; sau đó trả `SettlementReceipt` (`src/invoice_referee/storage/sqlite_settlement_repository.py:329-526`).

**Minh họa response 202** — ID/timestamp là minh họa:

```json
{
  "case_id": "SET-20261014-1A2B3C4D",
  "workflow_status": "ACTIVE",
  "processing_status": "PENDING",
  "submitted_at": "2026-10-14T07:00:00+07:00",
  "claimed_total": "1200000",
  "currency": "VND",
  "document_count": 1
}
```

JS redirect sang `/employee/settlements/{case_id}` (`settlement-form.js:333-349`). Trang này meta-refresh mỗi 3 giây đến khi processing không còn `PENDING/PROCESSING` (`employee/case_status.html:3-6`).

### 4.3. Paper scan: upload trước, items/matching sau

Khi `source_type=PAPER_SCAN`, JS cố ý gửi `expense_items=[]` (`settlement-form.js:192`) và bắt buộc có `settlement_form_file` (`:318-320`). Evidence file không được map thủ công; UI ghi “Sẽ tự đối chiếu sau khi OCR đơn giấy” (`:144-149`). Server cho evidence của paper scan chưa có `linked_item_id`; submit service chỉ yêu cầu đúng một request form (`submit_settlement.py:157-166`).

Sau đó processor đọc request form/evidence, OCR/extract paper facts và matching ở pipeline phía application. Đây là seam phù hợp với mục tiêu Hoangha evidence pipeline: **source upload không cần giả expense item trước khi OCR biết nội dung**.

### 4.4. Accounting queue → review → human action

`GET /accounting/cases` lấy tất cả case từ repository, sau đó presentation layer remap outcome và tính timeline (`routes.py:605-643`). `GET /accounting/cases/{case_id}` gọi `_decorate_accounting_case()` để:

- gắn URL/preview kind/validity vào từng document (`:390-409`);
- gắn documents/matches vào expense items (`:411-454`);
- resolve `FORM:EXPENSE_ITEM:*` và `DOC:*` source refs (`:456-497`);
- dựng OCR block preview metadata (`:425-430,484-491`);
- chia findings thành blocking/warn/pass/pending approval (`:499-539`);
- dựng decision evidence refs (`:540-556`).

Human action nhận ba form field `action_type`, `reason`, `override_decision` (`routes.py:675-688`). Service phía application quyết định semantics của `REPROCESS_CASE`, `REQUEST_MORE_INFO`, `ESCALATE_CASE`, `OVERRIDE_DECISION`, `STOP_PROCESSING` (`review_settlement.py:18-101`). Route chỉ redirect về detail sau khi ghi nhận.

**Minh họa human input:**

```text
action_type=REQUEST_MORE_INFO
reason=Vui lòng bổ sung tên khách hàng tham dự.
override_decision=
```

Kết quả source-verified: service tạo decision `REQUEST_INFO`, uncertainty `FACTUAL_UNKNOWN`, target `EMPLOYEE`, question chính là reason, workflow `WAITING_EMPLOYEE` (`review_settlement.py:38-47`). Đây phù hợp cơ chế đề A ở mức routing/question, nhưng identity người thao tác hiện chưa được server xác thực — xem Finding F1/F5.

### 4.5. Source ref → OCR preview

Nếu finding trỏ `DOC:{document_id}:page-X-block-Y`, `_ocr_block_index()` đọc persisted OCR artifact, tìm block, page dimensions, excerpt, confidence words và bbox (`routes.py:257-378`). `_decorate_accounting_case()` tạo URL `/ocr-preview?page_index=...&block_id=...` (`:484-491`). Route preview lấy đúng document trong case, dựng lại block index và gọi `render_ocr_block_preview()` (`:829-865`).

`ocr_preview.py` render PDF ở 2x hoặc image frame, scale bbox từ coordinate OCR sang image, clamp bbox và vẽ overlay đỏ (`:14-34,47-103`). Đây là một trong các phần reusable rõ nhất vì nó biến source locator thành artifact kiểm tra trực quan cho human reviewer.

## 5. Ai quyết định gì trong nhánh Hoangha

### Model quyết định / suy luận

- Chỉ khi document pipeline bật và đủ credential, Mistral adapter đọc OCR và Kimi reasoning adapter tham gia extraction/reasoning; wiring nằm ở `app/web/runtime.py:37-57`.
- Processor sử dụng kết quả OCR/reasoning để tạo facts/candidates; ví dụ low-confidence candidates dùng `self.word_confidence_threshold` (`process_settlement.py:313-326`).
- Với paper form, item/fact và evidence matching phát sinh sau OCR/extraction chứ browser không tự tạo items giả.

Model **không** phải nơi web route tự cấp quyền hay xóa case; các action đó là code/human boundary.

### Code quyết định

- Pydantic quyết định shape/validation DTO (`SettlementDraft`, `ExpenseItemDraft`).
- `SubmitSettlementService` quyết định file/relationship input có hợp lệ để persist không.
- policy/processing code quyết định findings và automation decision; presentation chỉ remap legacy outcome để hiển thị.
- repository quyết định lifecycle persistence, job claiming, audit storage và permanent delete.
- web code quyết định presentation, HTTP status, filename→item mapping, evidence/source-ref rendering.

### Con người quyết định / cung cấp

- Nhân viên nhập business context, khoản chi, trạng thái evidence, lý do ngoại lệ và chọn file→item trên digital form.
- Kế toán có UI để yêu cầu bổ sung, chuyển cấp, override, stop hoặc reprocess (`case_detail.html:83-120`).
- Tuy nhiên **current source không chứng minh người bấm là kế toán thật hoặc actor có grant**, vì route không có actor dependency và service fallback sang demo actor. Vì vậy human-control UI tồn tại nhưng server-side authority boundary chưa tồn tại trong nhóm này.

## 6. Findings đã xác minh từ source

Mỗi finding dưới đây có trigger cụ thể. Tôi không dùng test pass/fail tưởng tượng; test source chỉ được dùng để nói test đang kiểm điều gì.

### F1 — BLOCKER: accounting/data routes không có server-side actor/role boundary

**Trigger:** một client biết URL/case ID gọi `/accounting/cases`, `/api/v1/accounting/cases`, `/api/v1/cases/{case_id}`, document URL hoặc POST accounting action.

**Wrong behavior:** web boundary không kiểm actor/role/ownership trước khi đọc dữ liệu hoặc mutation. `get_case()` trả cả beneficiary/bank data, documents, findings, audit và human actions; `list_cases()` select cả `beneficiary_name`, `bank_account_number`, `bank_name`. Một caller web không được phân quyền có thể đọc hồ sơ và gọi action kế toán. Khi action được ghi, route không truyền `actor_id`, nên service gắn mặc định `ACCOUNTANT-DEMO-001`.

**Evidence:** `app/fastapi_app.py:27-59` không cài auth/session middleware; `app/web/routes.py:564-869` không có `Depends`/actor guard ở 13 routes; accounting action gọi `record_action(...)` không actor tại `:675-688`; `ReviewSettlementService.record_action()` có default `actor_id="ACCOUNTANT-DEMO-001"` tại `review_settlement.py:18-26`; repository `list_cases()` trả bank fields tại `sqlite_settlement_repository.py:862-896`, `get_case()` trả full nested detail tại `:898-1005`.

**Tác động khi ghép final:** final design §4 đã chốt demo persona không tự là authenticated identity và client role không tự cấp server authority. Port nguyên route sẽ làm audit/authority của final sai ngay tại boundary.

**Đề nghị nhỏ nhất:** giữ public demo entry nếu đề thi cần, nhưng mọi command/read phải đi qua `ActorContext`/server-side scope của final; employee chỉ thấy case thuộc scope của mình, accountant/authorized actor đi qua canonical grant checks. `actor_id` phải đến từ server context, không từ default/client field.

### F2 — BLOCKER: permanent delete là mutation trực tiếp từ public accounting surface

**Trigger:** POST `/accounting/cases/{case_id}/delete`.

**Wrong behavior:** route gọi thẳng `repository.delete_case()` và repository xóa row case cùng artifact directory vĩnh viễn. Browser `confirm(...)` chỉ là UX; caller HTTP có thể bỏ qua hoàn toàn. Đây là data-loss path nằm ngoài lifecycle/audit command của final.

**Evidence:** delete route `app/web/routes.py:714-728`; nút delete ở `accounting/queue.html:83-86` và `case_detail.html:15-18`; repository mô tả rõ “Permanently delete a demo case” và thực hiện rename staging → DB delete → `shutil.rmtree` tại `sqlite_settlement_repository.py:1127-1166`.

**Test source liên quan:** integration test chủ động POST delete và mong case thành 404 (`tests/integration/test_fastapi_app.py:123-133`). Test này chứng minh behavior là chủ ý của demo, không chứng minh authority/safety cho final.

**Đề nghị:** không mang endpoint này sang workflow nghiệp vụ final. Nếu vẫn cần reset dữ liệu demo, đặt nó ở demo/admin tooling tách biệt với user workflow và actor/audit contract.

### F3 — BLOCKER: `/internal/process-next` là public mutation có thể kích hoạt provider path

**Trigger:** POST `/internal/process-next` trong runtime mà `UC03_DOCUMENT_PIPELINE_ENABLED=1` và có credential.

**Wrong behavior:** bất kỳ caller nào tới route có thể yêu cầu processor claim job kế tiếp. `run_once()` có thể đi vào OCR/reasoning adapter đã được runtime wiring, gây state transition và external-provider work. Route gọi là “internal” nhưng tên URL không tạo isolation.

**Evidence:** route `app/web/routes.py:867-869`; runtime wiring provider `app/web/runtime.py:37-69`; worker đã có đường nền riêng `app/fastapi_app.py:33-40`; processor `run_once()` claim job tại `process_settlement.py:146-155` và document processing gọi OCR adapter tại `:279-317`.

**Giới hạn bằng chứng:** tôi **không gọi LIVE**, nên không claim provider thực đã bị gọi trong review. Đây là source-verified reachable call path dưới điều kiện config, chưa phải runtime exploit reproduction.

**Đề nghị:** bỏ route khỏi public router khi ghép final; Verify/test runner cần process deterministic thì dùng internal application/test adapter tách khỏi live HTTP surface. Background worker/durable job path mới là runtime seam.

### F4 — BLOCKER nếu port raw field: `allocated_advance_amount` thiếu responsible basis/history/limits

**Trigger:** employee chọn `ADVANCE_SETTLEMENT` và nhập `allocated_advance_amount`.

**Wrong behavior so với contract final:** template nói rõ “hệ thống dùng số tiền khai báo để tính quyết toán và không tra cứu khoản tạm ứng gốc” (`new_settlement.html:79-85`). JS đưa chính số này vào canonical payload (`settlement-form.js:231-234`), DTO chỉ kiểm `allocated_advance_amount >= 0`, và repository persist nó vào case. Field này không mang actor chịu trách nhiệm, scope, refs, thời điểm xác nhận, ledger/history coverage hay giới hạn áp dụng.

Q32/ADR007 hiện **cho phép** lời xác nhận chịu trách nhiệm của nhân viên + chứng từ dịch vụ làm căn cứ cho **employee-paid `E`** trong ngưỡng `E<=8tr`, `abs(S)<=4tr`, khi các điều kiện khác đủ và không có mâu thuẫn trọng yếu (`IMPLEMENTATION_CONTRACTS.md:49-52,86-89`). Vì vậy finding không phải “mọi xác nhận của nhân viên đều inadmissible”. Vấn đề cụ thể là Hoangha dùng raw field này như số **tạm ứng `A`** để tính ngay, trong khi contract `A/P/R` yêu cầu completed transfer/cash receipt/ledger hoặc confirmation tài chính đúng payer/payee/scope; raw declaration không chứng minh điều đó (`IMPLEMENTATION_CONTRACTS.md:52`).

**Evidence:** UI `new_settlement.html:79-85`; payload `settlement-form.js:231-234`; DTO `SettlementDraft.allocated_advance_amount` ở `domain/settlement.py:190-204`; repository write ở `sqlite_settlement_repository.py:384-431`.

**Đề nghị:** nếu giữ UX field này, map nó thành **declaration/observation** có provenance; không promote thẳng thành `A`. Việc dùng nó cho money basis phải đi qua confirmation/history/coverage đúng loại fact, actor/scope/refs và giới hạn đã chốt. Q32 chỉ áp dụng theo contract cho `E`; không dùng Q32 để hợp thức hóa raw advance field.

### F5 — IMPORTANT: employee identity được hard-code ở client và mọi submission web dùng cùng persona

**Trigger:** bất kỳ người nào dùng form browser hiện tại và submit.

**Wrong behavior:** payload luôn gửi `EMP-DEMO-001 / Nguyễn Minh An / Phòng Kinh doanh / Nhân viên / SYNTHETIC`, không lấy identity từ server session/context. Repository sau đó ghi `CASE_CREATED` với `actor_id=draft.employee.employee_id`, nên audit lineage phản ánh persona trong payload, không chứng minh actor thực.

**Evidence:** header cố định `new_settlement.html:10-13`; `buildPayload()` hard-code employee tại `settlement-form.js:217-223`; repository audit dùng draft employee id tại `sqlite_settlement_repository.py:497-505`.

**Đánh giá:** synthetic persona tự nó **không sai đề thi** — brief cho phép synthetic data nếu công bố rõ. Vấn đề là không được dùng persona client đó làm authority/audit identity khi port vào final.

### F6 — IMPORTANT cho live URL: upload được đọc toàn bộ vào memory trước khi service kiểm size

**Trigger:** client gửi multipart file rất lớn hoặc nhiều file rất lớn tới `/api/v1/settlements`.

**Wrong behavior:** route `await upload.read()` toàn bộ bytes để tạo `SettlementUpload` trước khi gọi `SubmitSettlementService`. Giới hạn 15 MB/file và 60 MB/tổng chỉ được check **sau đó** trong service. Một request quá giới hạn vẫn tiêu tốn memory để đọc trước khi bị reject; với endpoint live công khai, concurrent requests có thể khuếch đại.

**Evidence:** reads ở `app/web/routes.py:745-785`; giới hạn nằm ở `SubmitSettlementService.__init__` `submit_settlement.py:31-45` và `_validate()` `:62-96`.

**Đề nghị:** final upload adapter phải enforce limit trong lúc stream/copy từ `UploadFile` hoặc tại reverse-proxy/body limit trước khi materialize toàn bộ content. Giữ service validation như defense-in-depth.

### F7 — IMPORTANT: OCR review UI bỏ qua configured threshold

**Trigger:** deploy với `OCR_WORD_REVIEW_THRESHOLD` khác `0.85`, ví dụ `0.95`.

**Wrong behavior:** processor dùng ngưỡng cấu hình để chọn candidate cần review, nhưng web `_ocr_block_index()` lại hard-code `DEFAULT_WORD_REVIEW_THRESHOLD` (0.85) khi tạo `low_words`. Một word confidence 0.90 có thể bị pipeline coi là cần review ở threshold 0.95 nhưng UI không liệt kê nó trong vùng review.

**Evidence:** settings đọc env tại `config.py:14,38-50`; runtime truyền `settings.ocr_word_review_threshold` vào processor tại `app/web/runtime.py:63-70`; processor dùng `self.word_confidence_threshold` tại `process_settlement.py:313-326`; web so với `DEFAULT_WORD_REVIEW_THRESHOLD` tại `app/web/routes.py:343-351`; default là 0.85 tại `extraction/ocr_quality.py:8`.

**Đề nghị:** view decoration phải dùng cùng configured threshold hoặc, tốt hơn, render review candidates/flags đã persisted bởi processing artifact thay vì tái diễn giải threshold ở frontend adapter.

### F8 — SHOULD FIX trước khi API được coi là canonical: `decision` filter có hai semantics khác nhau

**Trigger:** API consumer gọi `/api/v1/accounting/cases?decision=ACCOUNTANT_REVIEW` hoặc `READY_FOR_APPROVAL` với case legacy.

**Wrong behavior:** HTML queue lấy tất cả case rồi dùng `_case_outcome_key()` để remap legacy `AUTO_PROCESS` → `READY_FOR_APPROVAL` và một số `ESCALATE` → `ACCOUNTANT_REVIEW`/`RECOMMEND_REJECT`. JSON API lại chuyển thẳng `decision` xuống repository, nơi SQL lọc **raw `automation_decision`**. Hai surface cùng dùng từ “decision” nhưng trả tập case khác nhau.

**Evidence:** presentation remap `app/web/routes.py:126-146`; HTML queue filter sau decoration `:611-629`; API route `:804-809`; repository SQL `WHERE automation_decision = ?` tại `sqlite_settlement_repository.py:891-896`.

**Đề nghị:** final chỉ expose một canonical server outcome/view model; nếu cần raw automation decision thì đặt field/filter tên riêng. Không mang lớp legacy mapping này vào React.

## 7. Giả thuyết/rủi ro chưa được test trong review này

Các mục sau **không phải finding đã reproduce**:

- Tôi chưa chạy multi-process/concurrency, nên không kết luận worker loop có vấn đề duplicate claim dưới nhiều Uvicorn workers. Repository có `BEGIN IMMEDIATE` khi claim job, nhưng load behavior chưa được test trong task này.
- Tôi chưa fuzz PDF/image malformed input; `ocr_preview.py` validate page/bbox nhưng resource behavior của PyMuPDF/PIL với file độc hại/chứa dữ liệu cực lớn chưa được đo.
- Tôi chưa chạy browser test nên không claim responsive/accessibility CSS thực tế dù CSS có media queries `app.css:313-363`.
- Tôi chưa gọi Mistral/Kimi; wiring source có nhưng chất lượng, latency, cost và failure behavior LIVE chưa được chứng minh ở đây.
- Tôi chưa đánh giá CSRF như một finding độc lập. Current app không có authenticated session boundary; nếu final thêm cookie session thì CSRF phải được xử lý trong boundary đó.

## 8. Test source chứng minh gì và chưa chứng minh gì

**Không test nào được chạy trong review này.** Đây là đọc test source để xác định intended behavior/coverage.

`tests/integration/test_fastapi_app.py`:

- `:17-38` chứng minh intent rằng employee/accounting pages và JS asset render được.
- `:41-133` bao trùm multipart submit → manual `/internal/process-next` → case API → accounting detail/queue → human action → permanent delete. Test cố ý set `INVOICE_REFEREE_DISABLE_WORKER=1` và `UC03_DOCUMENT_PIPELINE_ENABLED=0` tại `:8-14`.
- `:136-184` kiểm nhiều evidence file map sang nhiều item.
- `:187-229` kiểm paper submission nhận một form + unlinked evidence và chưa có item.
- `:232-274` kiểm `NO_EVIDENCE` được giữ và route sang `ACCOUNTANT_REVIEW` trong pipeline deterministic.

Điều integration test này **không chứng minh**: auth/role/ownership; actor provenance; background worker; Mistral/Kimi LIVE; upload memory limits; concurrent requests; external independent judge input beyond provided shapes; final React integration; CSRF; browser UX thực tế.

`tests/unit/test_accounting_case_view.py:43-79` kiểm legacy outcome taxonomy; `:82-159` kiểm OCR block→excerpt/low words/annotation/preview URL và finding grouping. Nó chưa kiểm configured threshold khác 0.85.

`tests/unit/test_ocr_preview.py:9-54` kiểm bbox trên image và PDF page render. Nó không kiểm invalid/malformed document matrix rộng hơn.

`tests/unit/test_sqlite_settlement_repository.py:895-902` kiểm unsafe case ID bị từ chối khi delete. Nó không phải authorization test.

## 9. Nên mang gì sang final và cần adapter gì

### Nên tái dùng gần như nguyên cơ chế

1. **OCR preview renderer** (`app/web/ocr_preview.py`). Đây là presentation adapter tốt: source locator → trang ảnh có bbox rõ ràng. Chỉ cần đổi input từ artifact shape Hoangha sang canonical locator của final và dùng canonical review threshold/candidate state.
2. **Source-ref decoration concept** từ `_decorate_accounting_case()` (`routes.py:381-557`): finding/decision phải dẫn được về document, page/block, excerpt và bản gốc. Final nên chuyển logic này thành typed server view builder thay vì để React tự resolve.
3. **Paper upload semantics**: request form + evidence có thể được persist trước khi biết expense lines; OCR/extraction/matching mới tạo relations sau. Điều này phù hợp evidence pipeline và tránh bắt user map thứ chưa biết.
4. **Human-review information architecture**: blocking findings hiển thị trước, WARN/PASS thu gọn, source preview và audit timeline. Đây là UX rất hợp đề A vì giúp human trả lời câu hỏi cụ thể thay vì “xem xét lại” chung chung.

### Chỉ nên tái dùng qua adapter

1. **Multipart upload adapter:** giữ khả năng upload nhiều file nhưng map thành canonical `Source`/upload command của final; stream + size guard ở boundary; không dùng filename làm relation canonical sau khi server đã có document IDs.
2. **Case/status API adapter:** trả **server view typed DTO**, không trả raw repository dict. Employee/accountant/authorized views phải lọc theo `ActorContext`.
3. **Review command adapter:** UI gửi intent như `REQUEST_MORE_INFO`/`ESCALATE`/`STOP`, nhưng final `CaseWorkflow` chịu trách nhiệm version, actor, grant, reason, basis và audit. Không gọi repository trực tiếp từ route.
4. **Worker adapter:** lifespan worker có thể dùng làm local pilot runner nếu final plan vẫn dùng in-process worker, nhưng command/job/state phải theo durable contract final; `/internal/process-next` không nằm trên public router.
5. **Outcome/view adapter:** legacy `_case_outcome_key()` chỉ dành cho migration/presentation. Final phải có canonical state/outcome một lần ở server.

### Không nên mang nguyên xi

- Jinja templates/vanilla JS như stack cuối vì final đã chốt React/TypeScript/Vite.
- hard-coded employee persona làm actor.
- default `ACCOUNTANT-DEMO-001` làm actor của mutation.
- permanent delete trong user workflow.
- employee-entered `allocated_advance_amount` làm money fact.
- raw repository dict làm public API.
- public `/internal/process-next`.

## 10. Mapping sang final mà không đổi policy đã chốt

Đề xuất integration boundary:

```text
React employee/accounting UI
        |
        v
FastAPI adapter
  - ActorContext / role / case scope
  - typed upload + command DTO
  - streaming limits
        |
        v
CaseWorkflow / EvidenceReader / Reconciler (final authority)
        |
        +--> Source + Observation + Relation + Assessment
        +--> Issue/Question đúng FACT/POLICY/AUTHORITY
        +--> Decision/Instruction theo grant/version/basis
        |
        v
SQLite + artifact store
        |
        v
Server View Builder
  - findings + exact source refs
  - OCR preview locator
  - human actions/audit
        |
        v
React presentation
```

Điểm quan trọng là **không chuyển policy vào frontend**. Hoangha đã có nhiều presentation logic tốt, nhưng final phải để backend quyết định facts/relations/money/policy/grant/state. React chỉ hiển thị server view và gửi intent, đúng contract final hiện tại.

Đối với đề A, phần đáng giá nhất của Hoangha không phải Jinja hay CSS mà là chuỗi có thể trace:

```text
source upload
→ OCR/extraction
→ relation/matching
→ finding có source_ref
→ câu hỏi/decision
→ human review nhìn được đúng evidence
```

Đây là phần nên đưa vào final evidence pipeline. Các mutation actor/authority, money history, Stop/version và final command semantics phải lấy từ canonical final contracts, không lấy từ demo web behavior của Hoangha.

## 11. Kết luận review

- **Files reviewed:** 14/14, 2.595 dòng, toàn bộ hash/line count khớp inventory.
- **Source-verified findings:** 8 — F1–F4 là blocker cho merge trực tiếp; F5–F7 là important integration/runtime risks; F8 là API semantic inconsistency nên đóng trước khi coi endpoint là canonical.
- **Reusable nhất:** OCR preview, source-ref→evidence view, paper-source upload semantics, accounting evidence presentation.
- **Không được coi là proof:** README/status prose, graph coverage unknown, test source chưa chạy, LIVE provider chưa gọi, browser/build chưa chạy.
- **Kết luận cho “đúng đề A”:** surface này có human escalation/review mechanics và evidence trace phù hợp hướng đề A, nhưng bản thân FastAPI frontend hiện chưa đủ để chứng minh control boundary của final vì actor/role/authority chưa được enforce ở server. Nó nên được dùng như **evidence/UI adapter source**, không như canonical workflow authority.

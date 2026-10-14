# 07 — Streamlit legacy, CaseProcessingService & inventory workflow

## Scope và bằng chứng

Đã đọc đầy đủ **16/16 file owner `07-streamlit-inventory`**, tổng **3.221 dòng**, theo `inventory.json` tại HEAD `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. SHA-256 của cả 16 file đều khớp inventory.

Các finding bên dưới là **source-verified**. Các test được trích dẫn chỉ được đọc để xem assertion và coverage intent; **runtime/tests/build/generator/LIVE: NOT_RUN** theo ràng buộc review. Vì vậy các câu “test xác nhận” trong báo cáo phải hiểu là **source test có assertion tương ứng**, không phải kết quả test đã chạy. CodeGraph đã được parent dùng ở mức Verify cho discovery, nhưng `check_index_coverage`/generation không exposed nên **graph coverage = UNKNOWN**; coverage 16 file owner được đóng bằng full source read + SHA match inventory.

### Coverage ledger từng file

| File | Dòng | Vai trò | Input → Output | Hàm/chủ thể chính; caller → callee | Hành vi lỗi đáng chú ý | Khả năng mang sang `final` |
|---|---:|---|---|---|---|---|
| `.streamlit/config.toml` | 13 | Cấu hình Streamlit legacy | Streamlit config → server/theme/upload settings | config sections; Streamlit runtime đọc trực tiếp | config parse/runtime setting failure do framework xử lý; `maxUploadSize=20` không phải business limit 15 MB | **Thấp**, chỉ UI/demo config |
| `app/components/__init__.py` | 1 | Package initializer | import package → package namespace | không có runtime function; Python import system → module con khi được import explicit | không có handling riêng | **Không đáng kể** |
| `app/components/bbox_overlay.py` | 118 | Diagnostic bbox visualization | image path + OCR page/block data → `PIL.Image` overlay | `render_bbox_overlay()`; OCR debug → PIL image/drawing helpers | file/shape dữ liệu không hợp lệ có thể surface từ PIL/indexing; màu confidence chỉ là heuristic UI | **Có chọn lọc** cho diagnostics, không phải decision policy |
| `app/components/sidebar.py` | 34 | Chọn workspace Streamlit | sidebar interaction → page label | `render_sidebar()`; `streamlit_app.py` → Streamlit sidebar widgets | không có domain error handling | **Thấp**, presentation-only |
| `app/components/submission_form.py` | 164 | Form legacy + chuyển upload thành DTO | widget values/files → action/payload với `ClaimDraft` + `UploadPayload[]` | `render_submission_form()`; employee view → `SubmitCaseService.submit()` | UI nhận nhiều extension hơn OCR processor hỗ trợ; service validation mới là acceptance gate | **Chọn lọc** cho UX; phải align accepted formats với pipeline `final` |
| `app/state/__init__.py` | 1 | Package initializer | import package → package namespace | không có runtime function | không có handling riêng | **Không đáng kể** |
| `app/state/submission_state.py` | 31 | Streamlit session-state helpers | receipt/form state → persisted session keys/version | `initialize_submission_state()`, `reset_submission_form()`, `remember_receipt()`, `pop_receipt()`; employee/form views → `st.session_state` | phụ thuộc session state; không có durable persistence/error recovery | **Thấp**, UI-specific |
| `app/streamlit_app.py` | 99 | Legacy composition root | settings/env → stores/adapters/services + rendered page | `build_submission_service()`, `build_ocr_adapter()`, `build_kimi_adapter()` + module routing; Streamlit runner → views/services | thiếu provider config có thể trả adapter `None`, downstream processing route technical failure; synchronous submit | **Không mang nguyên khối**; chỉ tham khảo wiring khi tách adapter |
| `app/styles.py` | 270 | CSS bundle cho Streamlit | static source → `APP_CSS` | `APP_CSS`; Streamlit app → markdown/style injection | không có domain behavior/error handling | **Thấp**, presentation-only |
| `app/views/__init__.py` | 1 | Package initializer | import package → package namespace | không có runtime function | không có handling riêng | **Không đáng kể** |
| `app/views/accounting_review.py` | 560 | Legacy accounting queue/read-only review + delete | `LocalEvidenceRepository` cases/results → queue/detail UI; delete click → permanent delete | `render_accounting_review()`; app → repository list/load/delete + render helpers | không có approve/reject/request-info/override/reprocess lifecycle; repository/delete lỗi có thể surface qua UI path | **Chọn lọc** cho presentation; human action workflow phải dùng UC-03/final contract |
| `app/views/employee_submission.py` | 65 | Employee submit page | `SubmitCaseService` + form/session input → receipt/status UI | `render_employee_submission()`; app → submission form/state helpers | chỉ hiểu `PASS/NEEDS_HUMAN/RECEIVED`; service exception thuộc submit path | **Thấp** vì taxonomy khác UC-03 |
| `app/views/ocr_debug.py` | 369 | Internal OCR diagnostics | stored case/evidence/OCR artifacts → preview/confidence/block/raw JSON UI | `render_ocr_debug()`; app → repository + bbox/render helpers | missing case/artifact được hiển thị như empty/unavailable path; không tạo business decision | **Có chọn lọc** như internal tooling |
| `src/invoice_referee/application/decision_guard.py` | 90 | Final routing guard của UC-03 settlement, không phải Streamlit | `SettlementFinding[]` → `SettlementDecision` | `build_settlement_decision()`; `process_settlement._finish()` → priority/rule mapping helpers | deterministic trên finding đã có; không gọi model; behavior phụ thuộc enum/rule IDs hợp lệ | **Cao** nếu mapping đúng policy `final`; không gắn sang legacy `PASS` |
| `src/invoice_referee/application/process_case.py` | 837 | Legacy synchronous evidence-quality + optional inventory workflow | `case_id` + filesystem repo + OCR/reasoning adapters → persisted processing result/`PASS|NEEDS_HUMAN` | `CaseProcessingService.process_case()`; `SubmitCaseService` → OCR, confidence/conflict agent, `evaluate_inventory_consistency()`, repository save | source/OCR/agent/coverage lỗi fail closed về `NEEDS_HUMAN`; accepted-format mismatch tạo technical review | **Chọn lọc**: quality/coverage guards hữu ích, lifecycle/status cần adapter sang `final` |
| `src/invoice_referee/policy/inventory.py` | 568 | Deterministic inventory consistency policy trên facts model extract | analysis + evidence roles/names → `ProcessingFinding[]` | `evaluate_inventory_consistency()`; `CaseProcessingService` → coverage/transaction/item helpers | coverage thiếu/thừa/trùng → `ERROR`; mismatch/unknown/applicability issues → blocking findings theo rule | **Cao** cho rule logic nếu policy đã được `final` chấp nhận; model output phải qua adapter/coverage guard |

<!-- reviewed-file: .streamlit/config.toml -->
<!-- reviewed-file: app/components/__init__.py -->
<!-- reviewed-file: app/components/bbox_overlay.py -->
<!-- reviewed-file: app/components/sidebar.py -->
<!-- reviewed-file: app/components/submission_form.py -->
<!-- reviewed-file: app/state/__init__.py -->
<!-- reviewed-file: app/state/submission_state.py -->
<!-- reviewed-file: app/streamlit_app.py -->
<!-- reviewed-file: app/styles.py -->
<!-- reviewed-file: app/views/__init__.py -->
<!-- reviewed-file: app/views/accounting_review.py -->
<!-- reviewed-file: app/views/employee_submission.py -->
<!-- reviewed-file: app/views/ocr_debug.py -->
<!-- reviewed-file: src/invoice_referee/application/decision_guard.py -->
<!-- reviewed-file: src/invoice_referee/application/process_case.py -->
<!-- reviewed-file: src/invoice_referee/policy/inventory.py -->

Kết luận quan trọng nhất: nhóm file này chứa **hai thế giới khác nhau**:

1. **Legacy Streamlit / `CASE-*`**: `app/streamlit_app.py` + `CaseProcessingService` + `LocalCaseStore`/`LocalEvidenceRepository` + inventory consistency policy.
2. **FastAPI UC-03 / `SET-*`**: `decision_guard.py` thuộc Track A settlement pipeline và được gọi từ `process_settlement.py`; nó **không phải** final decision guard của legacy Streamlit.

Vì vậy không được lấy behavior của `decision_guard.py` rồi mô tả thành behavior của Streamlit.

---

## 1. Streamlit thực sự đang chạy gì?

`app/streamlit_app.py` dựng composition như sau (`39-53`):

```text
LocalCaseStore
      │
      ├── SubmitCaseService
      │
LocalEvidenceRepository
      │
      └── CaseProcessingService
             ├── Mistral OCR adapter
             └── Kimi reasoning adapter
```

`SubmitCaseService` được inject `processor=CaseProcessingService`, nên sau khi lưu case, xử lý diễn ra **đồng bộ ngay trong lượt submit**, không qua background job queue.

Streamlit có ba workspace (`sidebar.py:7-33`):

- Nhân viên
- Kế toán
- OCR kiểm thử

OCR page còn tự ghi rõ là công cụ nội bộ và dự kiến gỡ khỏi bản chính thức.

### Storage/lifecycle của Streamlit

Streamlit dùng `LocalCaseStore` + `LocalEvidenceRepository`, tức filesystem legacy `CASE-*`. Kết quả processing nằm trong `processing.json`; OCR artifact nằm theo evidence. Đây không phải SQLite UC-03 repository và không có `processing_jobs`, `human_actions`, `settlement_decisions` như FastAPI.

---

## 2. Submission UI và role thực tế

`submission_form.py` tạo hai role:

- `PRIMARY_DOCUMENT`: “Hóa đơn, bill, vé, phiếu thu hoặc bằng chứng thanh toán”.
- `SUPPORTING_DOCUMENT`: “Kiểm kê, PO, report, biên bản hoặc tài liệu đối chiếu”.

Form tạo `ClaimDraft(subject, body)` và `UploadPayload` theo role, rồi gọi thẳng `service.submit()` trong spinner (`submission_form.py:145-164`).

Receipt ở employee page chỉ hiểu ba trạng thái (`employee_submission.py:34-44`):

- `PASS`
- `NEEDS_HUMAN`
- `RECEIVED`

Nếu processor được cấu hình như composition hiện tại, receipt sau submit thường phản ánh `PASS/NEEDS_HUMAN` của `CaseProcessingService`, không phải UC-03 `READY_FOR_APPROVAL`, `REQUEST_INFO`, `ESCALATE`, v.v.

### Mismatch format đáng chú ý

UI/service cho phép nhiều loại file hơn OCR workflow thực sự xử lý:

- primary UI cho `xml`, `json`;
- supporting còn cho `doc`, `docx`, `xls`, `xlsx`, `csv`, `txt`;
- `CaseProcessingService.OCR_SUFFIXES` chỉ có `jpeg/jpg/pdf/png/webp` (`process_case.py:27`).

Trong processing loop, file ngoài `OCR_SUFFIXES` tạo `processing_errors`; `_post_ocr_findings()` biến mọi `processing_errors` thành `OCR_PROCESSING_ERROR` status `ERROR`, rồi case đi `NEEDS_HUMAN` (`148-209`, `713-751`).

Tức là UI có thể **chấp nhận file mà pipeline legacy chắc chắn không OCR**, sau đó đẩy hồ sơ sang hàng “Cần xác minh”.

Ngoài ra Streamlit server đặt `maxUploadSize = 20` MB (`.streamlit/config.toml:9-10`), trong khi `SubmitCaseService` giới hạn mỗi file 15 MB. 20 MB là giới hạn transport/UI, không phải business acceptance limit.

---

## 3. Pipeline thật của `CaseProcessingService`

Đây là synchronous extraction-quality workflow, không phải full UC-03 settlement workflow.

### Gate 0 — Source gate trước OCR

`process_case()` tách `PRIMARY_DOCUMENT` và `SUPPORTING_DOCUMENT`, rồi chạy `_missing_source_findings()` **trước khi gọi OCR** (`114-135`).

Rule thực tế:

- không có primary → `MISSING_BILL_EVIDENCE` FAIL;
- không có `case.body` **và** không có supporting → `MISSING_BUSINESS_CONTEXT` FAIL (`688-710`).

Nếu có bất kỳ source finding nào, case dừng ngay ở `NEEDS_HUMAN`; OCR và agent không chạy. Test `test_missing_bill_stops_before_ocr_and_agents` và `test_missing_business_context_stops_before_ocr_and_agents` kiểm tra đúng thứ tự này (`tests/unit/test_process_case.py:242-273`).

Điểm cần hiểu đúng: **supporting document không bắt buộc cho mọi case**. Business context text có thể thay vai trò source context ở source gate.

### Gate 1 — OCR từng evidence độc lập

Mỗi evidence hợp lệ được OCR riêng, raw result được persist, sau đó:

1. restructure OCR thành hierarchy;
2. tìm low-confidence blocks;
3. gắn `source_file`;
4. tạo document payload cho các bước sau (`process_case.py:144-190`).

Sau vòng OCR, `_post_ocr_findings()` kiểm tra:

- ít nhất một primary OCR thành công;
- nếu body rỗng thì ít nhất một supporting OCR thành công;
- có processing error nào không (`192-209`, `713-751`).

Bất kỳ FAIL/ERROR ở đây đều dừng pipeline và route `NEEDS_HUMAN`.

### Gate 2 — Confidence quality theo từng evidence

Nếu không có low-confidence candidate: tạo `OCR_CONFIDENCE_REVIEW/PASS` (`211-219`).

Nếu có candidate, Kimi confidence agent được gọi **riêng cho từng document**, payload chỉ chứa evidence đó. Source test còn xác nhận confidence payload không chứa `documents` hay `business_context`, trong khi conflict agent sau đó mới nhận tất cả nguồn (`tests/unit/test_process_case.py:443-477`).

Nếu confidence agent không được cấu hình hoặc lỗi, `_technical_failure()` route toàn case sang `NEEDS_HUMAN` (`221-264`, `771-802`).

### Gate 3 — Deterministic quality guard trên output agent

Kimi không trực tiếp quyết định case PASS/FAIL. `_confidence_findings()` kiểm tra deterministic:

- candidate lạ → `OCR_CONFIDENCE_ASSESSMENT_INVALID/ERROR`;
- candidate thiếu hoặc assessment không unique → `LOW_CONFIDENCE_BLOCK_UNKNOWN/FAIL`;
- candidate thực sự ảnh hưởng field blocking và cần verification → `LOW_CONFIDENCE_ASK_HUMAN/FAIL`;
- nếu không có finding blocking → `OCR_CONFIDENCE_REVIEW/PASS` (`483-564`).

`_assessment_blocks_conflict()` chỉ block khi semantic reviewer map candidate vào field mà workflow dùng (`573-606`). Vì vậy low confidence tự thân **không đồng nghĩa** phải human review.

Behavior đáng chú ý:

- field không liên quan → không block;
- exact accounting fields như MST, invoice date/number, amount, transaction ref/status có cơ chế chặt hơn: nếu cần verification thì block; thậm chí khi reviewer không yêu cầu verification, text số chưa `READABLE` vẫn có thể block;
- field khác chỉ block khi `importance == CRITICAL` và cần verification.

Tests thể hiện rõ:

- non-critical low confidence vẫn PASS (`301-316`);
- critical + uncertain → NEEDS_HUMAN (`319-343`);
- critical nhưng readable → PASS (`376-395`);
- assessment thiếu → fail closed (`424-440`).

### Gate 4 — Không có supporting thì conflict check không áp dụng

Sau khi confidence gate sạch, nếu case **không có supporting**, service thêm `CROSS_SOURCE_CHECK_NOT_APPLICABLE/PASS` và kết thúc `PASS` (`296-321`).

Đây là một semantic boundary rất quan trọng:

> `PASS` của legacy Streamlit có thể chỉ có nghĩa “primary evidence qua source/OCR/quality gate và không có supporting để cross-check”.

Nó **không phải** `READY_FOR_APPROVAL` của UC-03, và cũng không chứng minh full settlement/policy approval.

Test `test_primary_document_only_passes_quality_without_conflict_agent` xác nhận conflict agent không chạy (`276-298`).

### Gate 5 — Cross-source Conflict Agent

Chỉ khi có supporting và các quality gate trước đều sạch, service mới gọi `reasoning_adapter.analyze_conflict()` (`323-371`).

Payload chứa:

- tất cả documents đã OCR/quality-pass;
- business context từ subject/body;
- nhưng business context được đánh dấu rõ `CONTEXT_ONLY_NOT_AN_INVENTORY_SOURCE` (`335-355`).

Nếu một evidence quality-blocking, pipeline dừng trước conflict. Test `test_one_unclear_evidence_stops_before_cross_source_conflict` xác nhận cả hai evidence được confidence-review nhưng conflict agent không được gọi (`480-501`).

Nếu conflict agent lỗi, case trở thành technical failure → `NEEDS_HUMAN`, không tự pass (`356-371`).

### Gate 6 — Coverage guard + một lần repair

Sau conflict agent, service không tin ngay JSON trả về. Nó gọi `evaluate_inventory_consistency()`.

Inventory policy yêu cầu `document_facts` phải cover **đúng tập evidence đầu vào** và không duplicate (`inventory.py:286-355`). Missing, unexpected hoặc duplicate evidence đều tạo `INVENTORY_EXTRACTION_COVERAGE_INVALID/ERROR`.

Nếu gặp coverage invalid, `CaseProcessingService` cho conflict agent **một lượt repair** với:

- danh sách required documents;
- missing IDs;
- unexpected IDs;
- previous invalid result (`process_case.py:384-433`).

Sau repair, policy được chạy lại. Test `test_inventory_policy_repairs_one_semantically_incomplete_response` xác nhận call thứ hai nhận `repair_request` và có thể phục hồi về PASS (`tests/unit/test_process_case.py:569-612`).

Nếu repair vẫn không đầy đủ, ERROR vẫn tồn tại và final legacy decision sẽ là `NEEDS_HUMAN` vì `_has_blocking_findings()` coi cả `FAIL` và `ERROR` là blocking (`process_case.py:28`, `434-462`, `761-765`).

---

## 4. Inventory policy: LLM extract/propose, code quyết định

`inventory.py` tự mô tả đúng vai trò: **deterministic inventory consistency checks over LLM-extracted facts**.

LLM có thể cung cấp:

- applicability;
- document facts;
- suggested item matches;
- potential semantic conflicts.

Nhưng code quyết định finding cuối.

### 4.1 Coverage trước semantics

Nếu coverage document không chính xác, function return ngay coverage ERROR, chưa xét inventory semantics (`298-355`). Điều này ngăn model bỏ quên một nguồn rồi vẫn được chấm PASS.

### 4.2 Applicability

Sau coverage:

- `UNKNOWN` → `INVENTORY_APPLICABILITY_UNKNOWN/FAIL`;
- `NOT_APPLICABLE` → `INVENTORY_NOT_APPLICABLE/PASS` (`357-377`).

### 4.3 Employee text chỉ là context, không phải evidence inventory

`_is_context_only_ref()` coi `EMPLOYEE_CLAIM*` và `TEXT_REPORT:*` là context-only (`37-40`).

Potential conflict có source ref từ employee text bị ignore (`379-403`). Tests còn xác nhận semantic conflict giữa attached evidence tạo human question, còn conflict dựa vào `EMPLOYEE_CLAIM` bị bỏ qua (`tests/unit/test_inventory_policy.py:345-390`).

`text_report` cũng không thay thế attached supporting evidence khi inventory applicable. Test `test_text_report_cannot_replace_an_attached_supporting_document` kỳ vọng `INVENTORY_SOURCE_REQUIRED/FAIL` (`120-137`).

### 4.4 Transaction-level rules

Với supporting evidence, policy kiểm tra deterministic:

- supplier tax code mismatch;
- supporting date cách primary quá 7 ngày;
- receipt status `RECEIVED_PARTIAL/PENDING/REJECTED`;
- receipt status `UNKNOWN` (`inventory.py:91-173`).

Các trường hợp này đều tạo FAIL.

### 4.5 Item-level rules

Policy yêu cầu primary và formal supporting đều có item để đối chiếu (`405-459`).

Item matching dùng hai nguồn:

1. LLM `suggested_item_matches`, nhưng phải semantic-match, ID tồn tại và supporting item chưa bị dùng;
2. fallback deterministic theo normalized `raw_name` nếu chỉ có đúng một candidate (`461-508`).

Sau đó code kiểm:

- quantity;
- unit / unit conversion;
- unit price;
- line amount;
- primary item unmatched;
- supporting item unmatched (`176-283`, `509-554`).

Nếu không có FAIL/ERROR, policy thêm `INVENTORY_CONSISTENCY/PASS` (`556-568`).

Tests kiểm happy path và quantity/amount mismatch (`tests/unit/test_inventory_policy.py:98-118`), và test end-to-end ở `CaseProcessingService` xác nhận happy case PASS, mismatch route NEEDS_HUMAN (`tests/unit/test_process_case.py:504-566`).

---

## 5. “Human intervention” trong legacy thực sự là gì?

Có hai tầng phải phân biệt.

### Tầng processing

`CaseProcessingService` có thể tạo câu hỏi kế toán rất cụ thể. `_accountant_question()` chuyển canonical field thành nhãn nghiệp vụ, nêu file và observed text nếu ngắn (`650-685`).

Các finding blocking được ghép thành reasoning và case route `ProcessingDecision.NEEDS_HUMAN`.

Inventory semantic conflict cũng có thể dùng `human_question` từ conflict agent, nhưng code chỉ chấp nhận conflict gắn với source evidence hợp lệ (`inventory.py:379-403`).

### Tầng UI kế toán

`accounting_review.py` chỉ:

- đọc case đã có `processing.json`;
- chia tab `PASS` và `NEEDS_HUMAN`;
- hiển thị summary/reasoning/findings/quality/inventory/evidence;
- bật/tắt bounding boxes;
- cho **xóa vĩnh viễn case** (`531-560`, `404-455`).

Không có UI/action để:

- xác nhận giá trị;
- sửa field;
- approve/reject;
- request more info;
- override decision;
- reprocess sau khi human trả lời.

Search trực tiếp trong view cho thấy control hành động nghiệp vụ duy nhất ngoài chọn/toggle là delete. Integration test `test_accounting_page_splits_processed_cases` cũng chỉ chứng minh queue hiển thị và delete flow (`tests/integration/test_streamlit_app.py:130-190`).

Vì vậy với legacy Streamlit:

> **Human intervention hiện là “route để kế toán xem và biết cần xác minh gì”, chưa phải closed-loop human review workflow.**

Không nên claim hệ thống đã có lifecycle human resolution/override từ Streamlit.

### Technical failure cũng vào cùng human queue

`OCR_NOT_CONFIGURED`, `KIMI_NOT_CONFIGURED`, confidence/conflict agent error và OCR processing error đều được lưu thành `NEEDS_HUMAN` qua `_technical_failure()` hoặc post-OCR findings.

Do accounting page chỉ chia theo `PASS` vs `NEEDS_HUMAN`, hàng “Cần xác minh” có thể trộn:

- uncertainty nghiệp vụ thật;
- OCR không đọc được;
- adapter chưa cấu hình;
- agent/runtime error.

Đây là khác biệt lớn so với FastAPI UC-03, nơi processing error có lifecycle `PROCESSING_ERROR` riêng trong SQLite repository.

---

## 6. Accounting presentation có transform riêng, không phải policy source

`accounting_review.py` cố tình chuyển technical output thành câu dễ hiểu:

- ưu tiên inventory findings nếu có;
- nếu coverage invalid, tự xác định evidence nào chưa được extract và nêu tên file + nhóm field thiếu;
- nếu human question từ agent chứa marker kỹ thuật như `candidate`, `block`, `confidence`, `ocr`, `ev-`, view thay bằng câu hỏi thân thiện từ source file + canonical fields (`84-176`).

Đây là **presentation logic**. Nó không thay đổi findings/decision đã persist.

`_render_inventory_review()` hiển thị cả document facts, suggested comparisons, text report, warnings (`321-402`) nhưng cũng không có quyền mutate policy result.

---

## 7. OCR debug và bbox là diagnostic, không phải decision gate

`ocr_debug.py` chỉ đọc OCR artifact đã persist và hiển thị:

- text;
- word confidence;
- hierarchical blocks;
- raw JSON;
- optional bbox overlay (`308-369`).

`bbox_overlay.py` dùng màu theo mapping status và block minimum confidence với ngưỡng cứng `0.70/0.85` (`16-30`). Đây là visualization heuristic.

Decision gate thật ở `CaseProcessingService` lại dựa trên:

- configurable `word_confidence_threshold` để collect candidate;
- semantic assessment;
- canonical blocking fields;
- deterministic guard.

Do đó màu bbox/UI không nên được mô tả là policy quyết định PASS/NEEDS_HUMAN.

---

## 8. `decision_guard.py` thuộc FastAPI UC-03, không thuộc Streamlit legacy

Dù file được owner 07, source cho thấy `build_settlement_decision()` được import/call bởi `process_settlement.py`, không bởi `process_case.py`.

FastAPI UC-03 final routing (`decision_guard.py:56-90`):

- lấy findings `status == "FAIL"` làm blocking;
- không có blocking → `READY_FOR_APPROVAL`;
- clear rejection rules (`SET_CATEGORY_001`, `SET_BUYER_IDENTITY_001`, `SET_DUPLICATE_001`) → `RECOMMEND_REJECT`;
- suspicious → `ACCOUNTANT_REVIEW`;
- factual unknown → `REQUEST_INFO`;
- beyond authority / manager / chief accountant / director target → `ESCALATE`;
- còn lại → `ACCOUNTANT_REVIEW`.

`process_settlement._finish()` gọi guard rồi lưu decision qua SQLite repository (`process_settlement.py:226-238`).

Legacy `CaseProcessingService` hoàn toàn không gọi guard này; nó tự quyết định binary `PASS/NEEDS_HUMAN` bằng `_has_blocking_findings()`.

### Bảng phân biệt

| Concern | Legacy Streamlit | FastAPI UC-03 |
|---|---|---|
| Case ID/storage | `CASE-*`, filesystem | `SET-*`, SQLite + filesystem |
| Main processor | `CaseProcessingService` | `SettlementProcessingService` |
| Execution | synchronous trong submit | persistent background job |
| Result routing | `PASS` / `NEEDS_HUMAN` | `READY_FOR_APPROVAL`, `REQUEST_INFO`, `ACCOUNTANT_REVIEW`, `ESCALATE`, `RECOMMEND_REJECT`, ... |
| Final guard | `_has_blocking_findings(FAIL/ERROR)` | `build_settlement_decision()` |
| Human UI/actions | xem queue + evidence + delete | review service có request-info/escalate/override/reprocess/stop |
| Inventory code trong scope này | có, dùng cho cross-source legacy | không đồng nghĩa toàn bộ UC-03 dùng cùng lifecycle |

---

## 9. Các claim cần tránh

### Không claim “Streamlit đã tự động quyết toán/approve hồ sơ”

`PASS` ở đây chỉ là output của extraction-quality + optional inventory consistency workflow. Primary-only case có thể PASS mà conflict agent không chạy.

### Không claim “Kimi quyết định đúng/sai inventory”

Kimi extract/propose facts, matches, conflicts. `evaluate_inventory_consistency()` mới tạo deterministic rule findings và `CaseProcessingService` mới route PASS/NEEDS_HUMAN.

### Không claim “business-context text là nguồn chứng minh inventory”

Payload ghi rõ context-only; policy bỏ conflict dựa vào `EMPLOYEE_CLAIM/TEXT_REPORT` và không cho text report thay attached supporting document.

### Không claim “human-in-the-loop đã khép kín”

Legacy UI chỉ surface câu hỏi và cho xem/xóa. Không có answer/override/reprocess lifecycle trong Streamlit.

### Không claim `decision_guard.py` là final guard của Streamlit

Nó là Track A settlement/UC-03 guard, caller thật nằm trong `process_settlement.py`.

---

## 10. Review findings ưu tiên

1. **Boundary/documentation — High:** tách rõ legacy Streamlit `CASE-*` khỏi FastAPI UC-03 `SET-*`; đặc biệt không gộp `PASS` với `READY_FOR_APPROVAL`.
2. **Human review closure — High:** `NEEDS_HUMAN` hiện chỉ là routing/display; nếu Streamlit còn được dùng như product flow thì thiếu action + persistence + resume/reprocess contract.
3. **Accepted-format vs OCR support — High:** UI nhận XML/JSON/DOC/XLS/CSV/TXT nhưng processor chỉ OCR image/PDF; source hiện tại tự tạo technical NEEDS_HUMAN cho những file này.
4. **Queue semantics — Medium:** legacy accounting queue trộn business uncertainty với technical/config failures vì tất cả cùng `NEEDS_HUMAN`.
5. **PASS semantics — Medium:** primary-only có thể PASS mà không cross-source check; tên/UX/tài liệu phải nói rõ scope của PASS.
6. **Diagnostics vs policy — Medium:** bbox/confidence UI là visualization; không dùng ngưỡng màu 0.70/0.85 để giải thích decision gate.
7. **Inventory architecture — Positive:** exact document coverage, one repair attempt, deterministic transaction/item checks và context-only protection là những guard thực có source + test backing; đây là phần mạnh hơn các claim chung trong README/docs cũ.

## Kết luận

Legacy Streamlit hiện là một **synchronous evidence-quality + optional cross-source inventory inspection demo** có deterministic guards khá rõ, nhưng human review chưa khép kín và status `PASS` có scope hẹp hơn một quyết định quyết toán. FastAPI UC-03 là lifecycle khác với storage, queue, decision taxonomy và human actions riêng. Mọi tài liệu kiến trúc/đánh giá nên giữ ranh giới này làm invariant.

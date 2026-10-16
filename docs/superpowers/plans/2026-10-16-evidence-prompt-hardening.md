# Evidence Prompt Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Installed skills are helpers; the portable workflow and authorized scope in AGENTS.md take precedence. This document authorizes no implementation, commit, deployment or data reset by itself.

**Goal:** Đưa hướng dẫn nghiệp vụ của Hoangha vào main và đóng đường prompt → schema → matching → admission, giữ căn cứ và quy tắc tiền hiện hành.

**Architecture:** Giữ pipeline và DTO public; dùng một module prompt, một helper schema-repair có quota/root và pure projection matching chung. Consumer dùng mapping đã kiểm nhưng giữ payer/authority/actual-money gates độc lập; version identity ngăn reuse report của prompt cũ.

**Tech Stack:** Python3.12, Pydantic2, httpx, pytest/pytest-asyncio, FastAPI/SQLite, Mistral OCR và LLM đang cấu hình; frontend React/Node24 chỉ dùng cho browser acceptance. Không thêm dependency.

**Spec:** [Thiết kế cụ thể](../specs/2026-10-16-evidence-prompt-hardening-design.md), [contracts §12](../../final/IMPLEMENTATION_CONTRACTS.md#12-pipeline-chứng-cứ--dto-và-interface-chốt-14102026), [AGENTS.md](../../../AGENTS.md). Đọc cả spec và plan; không lấy toàn bộ Hoangha làm yêu cầu sản phẩm.


## Execution checkpoint — 16/10/2026

P1–P6 đã implement và có regression/final review giới hạn. Tên test trong các bước
là nhãn hành vi dự kiến; assertions tương đương được gom vào test module sẵn có,
không tạo bốn module trùng fixture. Các command bên dưới trỏ module thực tế;
full suite và LIVE/UI gates có kết quả chi tiết trong
[acceptance report](../../final/reviews/2026-10-16-evidence-prompt-hardening-acceptance.md).

- [x] Production pipeline/prompt/schema/mapping/cache implementation, no new failing
  test ngoài baseline date fixtures; không dùng checkbox để claim fullsuitegreen.
- [x] Final frozen source tám LIVE roots, dữ liệu/context/gold không sửa.
- [x] Fresh browser TC01 upload→draft→submit→return→accountant→SETTLED; TC06blocked.
- [ ] TC03 đạt conditionalroutineBALANCED: bị chặn bởi source thiếu tripcontext,
  không được tự sửa profile/data trong task này.
- [x] Positive advance transfer/cash qua UI: privatefixtures mới CONFIRMED/ALLOCATED4m, source mẫu cũ vẫn giữ đúng unresolved/OBSERVED.
- [ ] Whole-plan release PASS: chưa đánh dấu khi còn gate dữ liệu/fixture chưa đạt.

Rulings: shared repair1/readpass giữ nguyên; optional ReadResult.reader_identity
là metadata additive để xử lý explicitreturnreread khôngSQLmigration; Mistral
pagewordscore mapping và whole-status consumer là sửa integration trong scope.
Không mang nghiệp vụ mới TC18/inventory hoặc sửa legacydatefixtures vào plan này.

## Global Constraints

- Planning snapshot main `08acde6`, Hoangha `1ee3348`; executor kiểm lại SHA/diff/status trước khi sửa, bảo toàn thay đổi đồng thời.
- PDF/ảnh qua OCR; taxonomy17/role map; UNKNOWN không đoán; missing không zero.
- Quote/page/source đúng nguồn; giữ nguyên chữ/dấu và date precision; model không quyết định policy, payer, authority hoặc ghi tiền.
- S=E−A−P+R; 8/4/20 triệu; B ngoài phạm vi; không khôi phục company-direct, lịch sử xác nhận dư hoặc ngân sách riêng.
- Confidence candidate <0.85; matching rule0.50/0.75, promotion>=0.90; không chỉnh threshold để pass dataset.
- Repair tối đa1/read pass/root, LLM12/OCR10 attempts, deadline90s, input120.000/output20.000 ký tự; không tăng cap ngầm.
- Không provider I/O trong SQLite transaction; Stop/stale không publish tiền; đọc/ghép không tạo money event.
- Không sửa PDF/context/gold để làm xanh test; gold chỉ ở harness chấm độc lập, không vào prompt/server context.
- Lượt hiện tại chỉ viết docs. Khi được giao thực thi: TDD cho behavior, chỉ chạy LIVE trong DB/artifacts riêng; không commit/push/deploy/reset khi chưa có ủy quyền tương ứng.
- Shell qua RTK; uv/Python3.12. Trước browser build, kiểm Node24 và npm's Node cùng scoped runtime theo AGENTS.md.

## Review Focus

1. Nhãn mờ và số tiền rõ cùng block: không hạ số tiền rõ, nhưng chữ số mờ thật vẫn chặn — P2.
2. JSON đúng object nhưng thiếu trường, enum sai, bool giả số, NaN confidence: không ASSESSED/AUTO_LINK — P1/P2/P4.
3. Nhiều tài liệu cùng hỏng schema: chỉ một repair trong read pass, hết deadline không gọi thêm — P1.
4. Model nhận cả hai ứng viên hoặc ghép vượt tổng: giữ ambiguity và không có financial effect — P4/P5.
5. Sources không đổi nhưng prompt/profile đổi, hoặc đổi trong lúc job chạy: không reuse/publish như kết quả hiện hành — P6.

## File Map và ownership

Một integrator sở hữu các boundary shared; có thể giao reviewer đọc độc lập, không
cho nhiều implementer sửa cùng pipeline/service/contracts. Trình tự P1→P2→P3→P4→P5→P6→P7.
Chỉ ghi hoàn thành checkbox khi gate task có command/result/SHA/mode/evidence.
Trước P1, giữ SHA baseline08acde6 và inventory/hash65PDF/context/lockfile vào
`.runtime/prompt-hardening/baseline-manifest.json`; chưa cần gọi provider.
P7 chạy baseline bằng source snapshot bất biến của SHA đó trong subprocess riêng,
nên không phụ thuộc working tree đã sửa và không checkout/reset nhánh người dùng.

Python paths dưới đây bắt đầu từ `src/invoice_referee/`:

| Owner/task | Create / Modify | Consumer và mục đích |
| --- | --- | --- |
| P1 integrator | Create `evidence/structured_output.py`; Modify `evidence/trace.py`, `evidence/extraction.py` | Shared repair slot và parser; không đổi transport API |
| P2 integrator | Create `evidence/prompts.py`; Modify `evidence/ocr_quality.py`, `evidence/document_validity.py`, `evidence/pipeline.py` | Readability context + strict assessment + field-local gate |
| P3 integrator | Modify `evidence/prompts.py`, `evidence/classification.py`, `evidence/extraction.py`, `evidence/document_profiles.py` | Prompt theo type, extraction state/quote/page |
| P4 integrator | Modify `evidence/prompts.py`, `evidence/matching.py`, `evidence/pipeline.py` | Resolver với facts, projection nhất quán |
| P5 integrator | Modify `reconciliation/admission.py`; read `workflow/evidence_assessment.py` | Dùng mapping hợp lệ, không nới payer/financial rules |
| P6 integrator | Modify `workflow/service.py`, `evidence/telemetry.py`, `evidence/trace.py`; read `workflow/evidence_jobs.py` | Identity/reuse/stale guards, trace versions |
| P7 integrator | Create `scripts/run_prompt_hardening_audit.py`; update docs status/contracts/runbook | Acceptance cô lập và handoff |

Tests/file exact được chỉ ở mỗi task. Không sửa legacy `workflow/jobs.py` chỉ vì
nó có tên cache; đường active report reuse nằm trong `workflow/service.py`.
Không đổi SQL schema; version metadata dùng JSON basis đã tồn tại.

### P1 — Repair đúng lỗi, dùng chung một quota

**Files:** Create `src/invoice_referee/evidence/structured_output.py`,
`tests/unit/test_structured_output.py`; Modify `src/invoice_referee/evidence/trace.py`,
`src/invoice_referee/evidence/extraction.py`, `tests/unit/test_document_extraction.py`.

**Interfaces:** `RunBudget` thêm `max_schema_repairs:int=1`, `schema_repairs:int=0`,
`claim_schema_repair() -> bool` (không tự charge LLM attempt). Helper generic:
`async complete_structured(llm:object, *, system:str, user:str, budget:RunBudget,
validate:Callable[[dict[str,object]],T], stage:str, prompt_version:str,
schema_version:str) -> T`. Shape validator ném `XkiroSchemaError`; lỗi
transport giữ nguyên. Extraction vẫn trả DocumentAnalysis qua API hiện tại.

- [x] Viết `test_repair_contains_previous_response_and_validation_error`: lần1 `fields` là chuỗi, lần2 đúng list; user repair khác primary và chứa diagnostic/path `fields`; quota=1, LLM calls=2.
- [x] Viết `test_two_documents_share_one_repair_slot`, `test_transport_not_repaired`, `test_exhausted_deadline_stops_repair`, `test_oversize_repair_keeps_source_and_fails_closed`: hai tài liệu mỗi primary đều hỏng cho tối đa3 calls tổng; schema_repairs=1; timeout/HTTP không thêm lượt.
- [x] Viết `test_provenance_or_arithmetic_disagreement_is_not_schema_repair`: quote bịa bị demote, số in sai giữ nguyên; không thêm call để model sửa tiền.
- [x] RED: `rtk proxy uv run pytest tests/unit/test_structured_output.py tests/unit/test_document_extraction.py -q`; ghi lỗi assert cụ thể, không dùng import error duy nhất làm bằng chứng behavior.
- [x] Implement helper + quota; repair giữ nguyên source request, thêm tối đa4.000 ký tự response và2.000 ký tự diagnostics; nếu tổng vượt cap không cắt OCR, không retry. Trace primary/repair cùng stage; không export raw/quote.
- [x] Chuyển extraction sang helper, bắt cả lỗi JSON và shape trước khi dựng DocumentAnalysis; giữ tương thích aliases hiện hành. GREEN cùng lệnh; gate là exact calls/quota và unresolved không throw ngoài ý muốn.

### P2 — Confidence có ngữ cảnh, schema đủ và chặn đúng field

**Files:** Create `src/invoice_referee/evidence/prompts.py`; Modify
`src/invoice_referee/evidence/ocr_quality.py`, `src/invoice_referee/evidence/document_validity.py`,
`src/invoice_referee/evidence/pipeline.py`, `tests/unit/test_ocr_quality.py`,
`tests/unit/test_document_validity.py`; Create `tests/unit/test_document_extraction.py`.

**Interfaces:** Giữ `collect_low_confidence_blocks`; mở rộng
`async review_ocr_quality(candidates, *, llm, budget, sources:tuple[OcrSourceResult,...]=()) -> ConfidenceReview`.
Pipeline truyền OCR sources; direct callers thiếu sources vẫn có candidate context,
được đánh dấu context giới hạn. `OCR_CONFIDENCE_SYSTEM_PROMPT` trong prompts.py;
private response validator trả ConfidenceReview sau kiểm schema, không default
candidate-only thành ASSESSED. Dùng helper P1.

- [x] Viết `test_candidate_only_assessment_is_repaired_or_technical`, `test_invalid_enum_and_string_bool_are_not_assessed`, `test_candidate_coverage_is_exact`: thiếu/duplicate/unexpected ID/thiếu bool không được pass, chỉ sử dụng repair slot còn lại.
- [x] Viết `test_confidence_payload_groups_context_by_source`: hai nguồn có tổng khác nhau, mỗi candidate gắn đúng OCR nguồn mình, có previous/next block; không chứa organization/gold/extracted facts.
- [x] Viết `test_blurred_label_does_not_demote_clear_amount_in_same_block`: offsets nhãn confidence0.4, token3.240.000 confidence0.99; total giữ FOUND. `test_blurred_digit_remains_unresolved`: token tiền0.4 + UNCERTAIN/ASK_HUMAN làm total UNREADABLE, không instruction.
- [x] Viết `test_unknown_or_technical_review_does_not_verify_critical_candidate`, `test_missing_offsets_keeps_conservative_fallback`, `test_no_candidates_does_not_call_llm`: lỗi review không thành PASS; candidate của source khác không chặn nhầm source hiện tại.
- [x] RED: `rtk proxy uv run pytest tests/unit/test_ocr_quality.py tests/unit/test_document_validity.py tests/unit/test_document_extraction.py -q`.
- [x] Implement prompt theo spec4.2, strict required keys và field/word overlap. Giữ enum DTO hiện tại; prompt không dùng DEFER_TO_POLICY; parser không đổi policy. Update fake responses cũ thành schema đầy đủ thay vì nới validator để giữ test xanh.
- [x] GREEN cùng lệnh. Gate: nhãn mờ/giá trị mờ cho kết quả khác nhau có căn cứ; không có skip được gọi là PASS.

### P3 — Classification và extraction theo loại chứng từ

**Files:** Modify `src/invoice_referee/evidence/prompts.py`,
`src/invoice_referee/evidence/classification.py`, `src/invoice_referee/evidence/extraction.py`,
`src/invoice_referee/evidence/document_profiles.py`, `tests/unit/test_document_classification.py`,
`tests/unit/test_document_extraction.py`, `tests/unit/test_document_extraction.py`.

**Interfaces:** `build_classification_prompt(document_types:tuple[str,...]) -> str`;
`build_extraction_prompt(document_type:str, allowed_fields:tuple[str,...]) -> str`.
Giữ public classify/extract signatures. Helpers response-shape riêng mỗi stage
dùng P1; value unsupported vẫn do provenance gate xử lý, không schema repair.
Không đổi FieldState, taxonomy hoặc payer acceptance.

- [x] Viết `test_type_guidance_does_not_depend_on_filename`, `test_unknown_type_is_not_guessed`: payload tên file gây hiểu nhầm không quyết định type; giữ page bounds/overlap guards có sẵn.
- [x] Viết `test_settlement_prompt_distinguishes_return_and_reimbursement`: nguồn hoàn700.000 giữ printed_return700000, không tự tính760000; nguồn công ty chi400.000 vào printed_reimbursement400000. Bỏ tổng cộng khỏi cost rows; giữ lý do `không có hóa đơn` nguyên nghĩa.
- [x] Viết `test_invoice_row_schema_preserves_quantity_unit_price_line_amount`: row `2 × 300.000 = 600.000` tạo ba field có quote riêng, không thành settlement invoice_refs. Không thêm phép kiểm inventory hoặc quantity arithmetic mới trong task này.
- [x] Viết `test_transfer_and_cash_follow_distinct_profiles`, `test_pending_transfer_not_completed`, `test_multiline_company_keeps_exact_quote`, `test_iso_date_does_not_invent_work_period`: tên2 dòng/value1 dòng, event_at05/10 giữ2026-10-05; không sinh trip_start/end.
- [x] Viết `test_field_quote_must_belong_to_claimed_page`: quote ở trang2 nhưng model ghi page1 không FOUND; các ví dụ JSON trong prompt parse được và nằm đúng allowed vocabulary, không chứa đáp án dataset.
- [x] RED: `rtk proxy uv run pytest tests/unit/test_document_classification.py tests/unit/test_document_extraction.py tests/unit/test_document_extraction.py -q`.
- [x] Implement base prompt + sections theo spec4.1, JSON example hợp lệ; serialize document_id/source_id/page_range/type/roles + OCR riêng unit. Kiểm page ownership và shape; giữ numeric/date/whitespace provenance; row vocabulary theo loại, không ép VAT lên ticket/receipt.
- [x] GREEN cùng lệnh; gate gồm assertions trên output/refs và request spy, không chỉ snapshot câu chữ prompt.

### P4 — Resolver dựa trên facts và projection matching đồng bộ

**Files:** Modify `src/invoice_referee/evidence/matching.py`,
`src/invoice_referee/evidence/prompts.py`, `src/invoice_referee/evidence/pipeline.py`,
`tests/unit/test_paper_evidence_matching.py`; Create `tests/unit/test_paper_evidence_matching.py`.

**Interfaces:** Mở rộng
`async resolve_evidence_suggestions(result, documents, *, paper:DocumentAnalysis, llm, budget) -> EvidenceMatchingResult`;
update mọi caller. Một helper pure
`project_evidence_matches(paper:DocumentAnalysis, documents:tuple[DocumentAnalysis,...], links:tuple[EvidenceLink,...]) -> EvidenceMatchingResult`
được cả rule matcher và resolver gọi. Model output `promotions` mỗi phần tử có
`item_id,document_id,confidence,rationale,basis`; `basis` là list objects
`{kind:AMOUNT|DOCUMENT_NUMBER|ISSUER|SERVICE,left_field,right_field}` trỏ đúng
field/row của cặp candidate, không chấp nhận quote hoặc ID nguồn model tự tạo.
Field selectors cố định: `left_field` là `row.amount`, `row.invoice_refs` hoặc
`row.description`; `right_field` là `document.total_amount`,
`document.document_number`, `document.issuer_name` hoặc `document.line_items[*].description`.
AMOUNT phải được code kiểm theo tolerance1VND hoặc explicit allocation hợp lệ;
DOCUMENT_NUMBER kiểm theo hàm ID hiện hành. ISSUER/SERVICE là nhận định ngữ nghĩa
có căn cứ từ field nguồn, vẫn phụ thuộc model, không được gọi là đã xác minh độc
lập bằng code. Mâu thuẫn định danh/số học có sẵn không được model ghi đè.

- [x] Viết `test_resolver_receives_pair_facts_not_only_scores`: request có mô tả/amount/ref dòng và issuer/number/total/line descriptions của đúng candidate; không OCR/raw/company ledger/gold.
- [x] Viết `test_promotion_requires_supported_amount_and_identity_basis`: 0.99 nhưng chỉ có amount => giữ suggestion; basis field không FOUND/không tồn tại => giữ suggestion. Hóa đơn khác service không được duyệt chỉ vì bằng tiền.
- [x] Viết `test_out_of_range_nonfinite_or_bool_confidence_is_rejected`, `test_competing_candidates_remain_unresolved`, `test_duplicate_serial_does_not_resolve_without_distinguishing_basis`: dùng các giá trị true,1.1,NaN; hai hóa đơn cùng số/tổng nhưng không tín hiệu phân biệt không AUTO_LINK.
- [x] Viết `test_llm_cannot_override_overallocation_or_consumed_document`: invoice500.000/claim600.000 hoặc hai dòng dùng chung invoice không có explicit allocations giữ blocker; tổng phân bổ không vượt nguồn.
- [x] Viết `test_projection_updates_row_allocation_findings_and_unmatched`: fixture row100.000 + invoice100.000 có gray matching hợp lệ; sau promote, link AUTO_LINK/LLM_RESOLVED, allocated100000, row ORIGINAL_EVIDENCE/original_total100000, nguồn ra khỏi unmatched, chỉ finding đã thực sự giải quyết được bỏ. Chạy projection lần2 bằng lần1.
- [x] RED: `rtk proxy uv run pytest tests/unit/test_paper_evidence_matching.py tests/unit/test_paper_evidence_matching.py -q`.
- [x] Implement facts payload + P1 validation, finite confidence, code-owned basis checks, allocation/cardinality/uniqueness; dùng projection chung để giữ rules ban đầu. Không tái dùng LLM để suy ra category hay tiền thiếu. Transport error trả kết quả rule còn unresolved.
- [x] GREEN cùng lệnh; gate là object report nhất quán, không chỉ kiểm link.method.

### P5 — Admission tiêu thụ đúng mapping, giữ payer độc lập

**Files:** Modify `src/invoice_referee/reconciliation/admission.py`,
`tests/unit/test_evidence_admission.py`; Create `tests/integration/test_document_arithmetic_gate.py`.
Read `src/invoice_referee/workflow/evidence_assessment.py`.

**Interfaces:** Giữ `admit_evidence` và AssessmentInput. Internal
`_match_expense_documents(report, paper)` trả tuple đúng annotation:
`tuple[list[_MatchedExpense], tuple[DocumentAnalysis,...]]`. Ưu tiên validated
mapping khi có links; không re-promote hoặc gọi model trong admission. Dùng
`project_evidence_matches` P4 để kiểm lại source/row/profile/allocation từ stored
report; không thêm một matcher thứ ba. Projection giữ refs của cả row và document
trên liên kết được nhận; thiếu ref hoặc sai source không tạo cost hợp lệ.

- [x] Viết `test_admission_uses_confirmed_mapping_not_another_suffix_match`: có hai hóa đơn dễ trùng suffix, report chọn một hợp lệ; admission dùng đúng document/amount/refs, không chọn tài liệu đầu tiên do dict order.
- [x] Viết `test_suggested_or_forged_link_cannot_establish_cost`, `test_resolved_link_does_not_establish_employee_payer`: LLM_RESOLVED hợp lệ có thể đóng lỗi ghép; company buyer thiếu printed invoice_ref vẫn không tự đóng payer; claimant/buyer mismatch tiếp tục FACT.
- [x] Viết `test_legacy_report_without_links_keeps_unique_reference_behavior`, `test_reused_invoice_does_not_double_count`, `test_multiple_sources_same_row_keep_source_bounded_allocation`: fallback giữ exact refs hợp lệ và explicit split trong cùng hồ sơ; không thêm invoice ngoài dòng thành chi phí thứ2.
- [x] Viết integration `test_confirmed_mapping_reaches_admission_without_money_side_effect`: request fake providers qua pipeline→stored report→admission; assertions document ID/refs cùng một mapping, unresolved không instruction; đọc không tạo money_events. Đủ payer/actual/policy mới được tính tiền.
- [x] RED: `rtk proxy uv run pytest tests/unit/test_evidence_admission.py tests/integration/test_document_arithmetic_gate.py tests/integration/test_document_arithmetic_gate.py -q`.
- [x] Implement seam nhỏ trong admission, không đổi `_invoice_binding` thành chỉ kiểm link hoặc confidence; giữ số học TC05/06/11 và actual money gates. Không bổ sung workflow mua hàng.
- [x] GREEN cùng lệnh; gate là matching, admission và financial outcome nhất quán với các căn cứ độc lập.

### P6 — Version identity, reuse và trace không bị lẫn bản cũ

**Files:** Modify `src/invoice_referee/evidence/prompts.py`,
`src/invoice_referee/evidence/telemetry.py`, `src/invoice_referee/evidence/trace.py`,
`src/invoice_referee/workflow/service.py`, `tests/integration/test_settlement_draft_ocr_reuse.py`,
`tests/integration/test_langsmith_runtime_wiring.py`; Create `tests/integration/test_settlement_draft_ocr_reuse.py`.

**Interfaces:** Prompt versions mới: classification-v2, extraction-v3,
ocr-confidence-review-v2, evidence-suggestion-resolution-v2; schema version đổi
khi response contract đổi. `evidence_reader_identity(*, reader:object,
classifier:object, activity_profile:str|None) -> str` trong prompts.py trả digest
canonical của prompt text/version + schema/profile/projection versions + models
cấu hình + OCR representation. Không hash credential/base URL chứa credential.

- [x] Viết `test_same_source_and_identity_reuses_report`, `test_prompt_or_profile_change_invalidates_reuse`, `test_report_without_identity_requires_fresh_read`: cùng identity không provider call khi submit; identity khác không reuse dù SHA file giống nhau.
- [x] Viết `test_running_job_cannot_publish_after_identity_change`, `test_stopped_job_still_cannot_publish`: stored basis đọc trước/version khác phải stale; không assessment/instruction từ kết quả cũ.
- [x] Viết `test_trace_primary_and_repair_have_current_versions`, `test_trace_does_not_export_repair_raw_or_ocr`: fake sink thấy stage/version/attempt/schema_repairs nhưng không OCR, quote, bank fields hay raw response.
- [x] RED: `rtk proxy uv run pytest tests/integration/test_settlement_draft_ocr_reuse.py tests/integration/test_settlement_draft_ocr_reuse.py tests/integration/test_langsmith_runtime_wiring.py tests/unit/test_trace.py -q`.
- [x] Lưu identity trong mọi nơi tạo/publish/reuse `input_basis_json`, kể cả direct draft và evidence job; dùng cùng builder P6. Report hiện hữu là historical read; không âm thầm re-assess hồ sơ đóng hay sửa money. Đổi thuật toán không bắt xóa DB.
- [x] GREEN cùng lệnh; gate là actual request counts và stale result không commit. Không mở rộng sang legacy preview engine chỉ để thống nhất tên cache.

### P7 — Chứng minh chất lượng bằng regression và paired LIVE

**Files:** Create `scripts/run_prompt_hardening_audit.py`,
`tests/integration/test_prompt_hardening_audit.py`,
`docs/final/reviews/2026-10-16-evidence-prompt-hardening-acceptance.md`;
Modify `docs/final/IMPLEMENTATION_CONTRACTS.md` §12 (refinement kỹ thuật),
`docs/final/IMPLEMENTATION_STATUS.md`, `docs/final/RUNBOOK.md`, plan checkboxes.

**Interfaces:** Harness CLI:
`uv run python scripts/run_prompt_hardening_audit.py --mode LIVE --baseline-ref 08acde6 --manifest data/demo/manifest.json --cases TC01 TC02 TC03 TC05 TC06 TC11 TC15 TC22 --as-of 2026-10-16T12:00:00+07:00 --output-dir .runtime/prompt-hardening/<run-id>`.
Chỉ đi production runtime/command/API; mỗi case có DB/upload riêng, đọc context
case tương ứng, không inject transcription/correction hoặc expected vào app.
Nếu script hiện có đáp ứng một phần, dùng lại hàm public phù hợp, không copy cả
harness legacy. Scoring nằm ngoài provider request, expected đọc độc lập từ README.

- [x] Viết offline `test_audit_uses_case_context_and_isolated_database`, `test_baseline_subprocess_imports_frozen_revision`, `test_expected_never_enters_runtime_or_prompt`, `test_missing_provider_is_not_live_pass`; RED rồi implement orchestration/report-only script, GREEN `rtk proxy uv run pytest tests/integration/test_prompt_hardening_audit.py -q`.
- [x] Từ SHA đã pin trước P1, xuất source snapshot vào thư mục ignored riêng bằng Git read-only; baseline và candidate chạy subprocess/cwd/import path khác nhau. Harness drive cùng public API/commands, không import module candidate vào baseline. Ghi thực tế source SHA, model/date/context digest; nếu không dựng được baseline thì UNAVAILABLE, không dựng số liệu trước/sau từ log lịch sử khác cấu hình.
- [x] Chạy focused suite toàn P1–P6 rồi `rtk proxy uv run pytest -q`; log mới kèm SHA/provider mode. So năm date-fixture failures lịch sử với baseline cùng môi trường; mọi failure mới chặn gate, lỗi cũ vẫn công khai. Không xfail hoặc chỉnh fixture ngoài scope để xóa số fail.
- [x] Chạy paired LIVE trước/sau tám case với model/context/clock/PDF hashes cố định, budget giữ nguyên. Provider/model alias không pin được phải ghi giới hạn so sánh. Không lặp chọn kết quả đẹp; lần chạy lặp vì lỗi phải lưu tất cả attempts.
- [ ] Assert TC01 COLLECT760000; TC02 PAY400000; TC03 BALANCED/không instruction0 khi đủ căn cứ; TC05 FACT số dòng500000 và còn mâu thuẫn nguồn; TC06 FACT60000; TC11 FACT100000; TC15 mismatch dịch vụ/ref; TC22 over-allocation2160000. Năm negative không affirmative instruction; UNKNOWN không bị biến thành0. Không sửa gold nếu app khác đáp án.
- [x] Audit từng case raw OCR→classification→fields/provenance→review→links/allocations→admission→issues/instruction; lưu private artifacts, request hashes/counts, latency và usage thực có. Phân biệt lỗi model/serialization/provenance/semantic matcher/finance, không chỉ pass/fail tổng.
- [x] Browser trên app/DB riêng: TC01 draft→submit→COLLECT760000→nhân viên nộp bằng chứng hoàn→kế toán xác nhận→đóng; receipt date sau instruction, trước demo clock, không sửa date nguồn. Kiểm thêm advance transfer/cash và TC06 không có nút execute tiền khi unresolved. Dùng source fixtures tạo đúng chronology nếu không có receipt phù hợp, ghi rõ synthetic.
- [x] Lưu screenshots/API/trace refs và provider counts; UI chỉ đọc mock report => không claim LIVE/UI acceptance. Nếu LangSmith không kết nối, local trace vẫn kiểm được nhưng LangSmith acceptance=NOT_RUN.
- [x] Viết acceptance report theo từng gate, coverage limitations, mọi failure/NOT_RUN; update contracts kỹ thuật, status và checkboxes đúng bằng chứng. Không claim25-case E2E hoặc hidden accuracy từ tám development cases.

## Definition of Done và tự review plan

- [x] P1–P6 có RED→GREEN, test mới bắt được phản ví dụ cũ và không chỉ mirror implementation.
- [x] Confidence schema/context/gate, extraction meanings, resolver facts/projection,
  admission identity, repair quota và report version đều có task sở hữu cụ thể.
- [ ] Offline + tám LIVE + browser gates có evidence hoặc nêu BLOCKED/NOT_RUN;
  chưa đủ bất kỳ gate bắt buộc nào thì chưa đánh dấu hoàn thành cả plan.
- [x] Không policy/authority/money mutation ngoài command hiện hành; không xóa DB;
  không thay dataset; không tăng budget để che timeout.

**Self-review lúc lập plan:** đối chiếu spec§3–5 với P1–P7; sửa thiếu sót về quota
repair/root, admission không dùng links và reuse không pin prompt. Tách rõ ghép
chứng từ với payer, thêm test claimed-page ownership và type-specific row schema.
Không có test/LIVE/UI nào được chạy trong planning turn. Coverage graph UNKNOWN;
source đọc trực tiếp; đây là plan giao implementer, không phải proof tính đúng.

**Handoff:** giao một integrator triển khai tuần tự. Reviewer có thể từ chối từng
gate; không tự làm thay implementer. Commit chỉ khi được ủy quyền riêng, stage
exact files của task; không tự dùng commit step trong skill làm quyền Git.

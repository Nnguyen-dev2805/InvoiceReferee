# Event Expense Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. AGENTS.md and user authorization govern execution; local skills do not grant commit/LIVE/deploy permission.

**Goal:** Từ một folder của một sự kiện, tạo bản nháp hoàn ứng đứng tên manager với một dòng/file, người chi trả từng dòng, chỉnh sửa có truy vết và tổng dự kiến đáng tin.

**Architecture:** Draft sự kiện là workspace soạn đơn riêng, không phải financial case nhiều người. Tái sử dụng session/storage/provider và tách evidence-only reader hiện có thành helper dùng chung với digital intake S6. Projection pure tính tiền; service lưu nguồn/revisions; React cho kiểm tra và gán người trả theo nhóm.

**Tech Stack:** Python3.12/uv, FastAPI/Pydantic/SQLite; React19/TypeScript/Vite/Node24; OCR/LLM adapters hiện hành; pytest/Vitest/browser harness sẵn có. Không thêm dependency mặc định.

**Spec:** [2026-10-17-event-expense-draft-design.md](../specs/2026-10-17-event-expense-draft-design.md). Đọc cả spec và plan trước khi làm.

**Status:** PLAN ONLY — chưa code, chưa chạy test sản phẩm, chưa browser/LIVE.
**Planning basis:** main `2730b353`, worktree sạch lúc khảo sát. Thực thi phải kiểm lại HEAD/diff và contracts; line numbers có thể đổi.

## Global Constraints

- Một folder tương ứng một sự kiện; nhiều folder tạo nhiều bản nháp độc lập.
- Mỗi file đại diện một chứng từ/một giao dịch, tương ứng một dòng report.
- Manager đứng tên đơn, từng dòng ghi người chi trả; không thêm persona thứ tư.
- V1 chỉ soạn/lưu/kiểm tra bản nháp trên web; không PDF/XLSX mới, không submit vào reconciler hay gửi kế toán.
- Không tạo financial case/usage/ledger/instruction; không biến tên người trả hoặc tiền ứng kê khai thành fact tài chính đã xác minh.
- Giữ S=E−A−P+R, quyền8/4/20 triệu, B ngoài phạm vi. `draft_delta` là phép tính kê khai riêng, không thay S.
- Tiền strict integer VND, không bool/float/âm; UNKNOWN không thành0; server sở hữu tổng.
- Mỗi file có sourceID/digest; filename/relative path không là identity hay storage path.
- PDF/PNG/JPEG; tối đa10 file,20MiB/file,50MiB/tổng draft. Giới hạn pilot, không measured guarantee.
- Một RunBudget hiện hành/pass; không tự tăng quota/timeout, không đổi model/provider/env.
- Dùng RTK; Python3.12 qua uv; Node24 đúng pin và npm chạy cùng Node trước build/test.
- Mọi test dùng DB/artifacts riêng; không DB người dùng/port8000/Railway; không provider call trong default suite.
- Không commit/push/merge/deploy khi chưa được yêu cầu riêng. Các checkpoint là diff kiểm tra được, không tự git commit.

## Review Focus

1. Cùng filename khác bytes hoặc folder trùng tên: source/draft IDs khác nhau, không gán nhầm người trả — T1/T3/T4.
2. Một file chưa đọc được hoặc budget cạn: vẫn đủ dòng, tổng đầy đủ/delta null và không hoàn thiện — T1/T2/T5.
3. Buyer/payee bị nhầm payer: giữ gợi ý có refs và yêu cầu manager gán; không thành verified — T1/T4.
4. Reload/retry/late read ghi đè sửa tay hoặc tốn call lại: version/idempotency/basis giữ sửa và nguồn — T3/T5.
5. Draft nhiều người vô tình tạo nghĩa vụ tiền hoặc tenant khác xem được: không side effects, session guard mọi nguồn — T3/T5.

## Discovery và ownership

Tier Verify theo phạm vi intake/evidence/draft; CodeGraph trả current source tại repo.
Generation/index coverage UNKNOWN (không expose status/coverage tools). Không có claim
exhaustive; xem spec§6 cho queries/symbols/callers và fallback. Đọc lại các đoạn
helper bị cắt trong graph trước khi thực sự tách code.

**Integrator khi execution:** agent chính nhận triển khai; tuần tự sở hữu mọi shared
boundary `workflow/{schema.sql,db.py}`, `api/app.py`,
`reconciliation/digital_intake.py`, `frontend/src/App.tsx`. Không dispatch nhiều
agent sửa các file này cùng lúc. Reviewer chỉ đọc; có thể làm UI độc lập sau T1/T3
khi DTO/API đã khóa. Các paths dưới đây là đề xuất triển khai, chưa có trong repo.

| Create/modify | Trách nhiệm |
|---|---|
| Create `src/invoice_referee/domain/event_drafts.py` | Strict DTO draft/row/patch/summary; không nhập finance Fact |
| Create `src/invoice_referee/reconciliation/event_draft.py` | Project validated evidence thành dòng và tổng kê khai, pure |
| Create `src/invoice_referee/evidence/evidence_batch.py` | Helper OCR/confidence/extract/validate dùng chung |
| Modify `src/invoice_referee/reconciliation/digital_intake.py` | Gọi helper, giữ digital_to_paper/matching/public interface |
| Create `src/invoice_referee/workflow/event_drafts.py` | Persistence, phiên bản, idempotency, source authorization/read coordinator |
| Modify `src/invoice_referee/workflow/schema.sql`, `db.py` | Bảng event draft/source/revision và additive schema version |
| Create `src/invoice_referee/api/event_drafts.py`; modify `api/app.py` | Router mới/service wiring, startup interrupt abandoned reads |
| Create `frontend/src/features/event-draft/{api.ts,types.ts,event-draft.tsx}`; modify `frontend/src/App.tsx` | Folder upload, review, gán nhóm, lưu/mở lại; entry riêng |
| Create tests listed in T1–T5 | Unit/API/component/browser; không dùng gold làm app input |
| Modify `docs/final/{IMPLEMENTATION_CONTRACTS.md,IMPLEMENTATION_STATUS.md,RUNBOOK.md}` at T5 | Draft boundary/API/runbook/evidence thực, không claim execution trước |
| Create `docs/final/reviews/2026-10-17-event-expense-draft-acceptance.md` at T5 | PASS/FAIL/NOT_RUN và giới hạn chất lượng |

## T1 — DTO và phép tính bản nháp độc lập

**Files:** create domain/event_drafts.py, reconciliation/event_draft.py,
`tests/unit/test_event_draft.py`.

**Interfaces:**
- `DraftValue`: `value:str|StrictInt|None`, `origin:OCR|MANAGER_DECLARATION|HUMAN_CORRECTION|UNSET`, `refs:tuple[EvidenceRef,...]`, optional `original:FieldCandidate`; metadata actor/time/reason của correction lưu ở revision. Validate amount riêng, không union-coerce string tiền.
- `EventDraftRow`: `id`, `source_id`, `source_digest`, `filename`, `relative_path`, `description/expense_date/document_number/amount/payer` (DraftValue), `payer_suggestion:FieldCandidate|None`, `read_status:NOT_READ|READ|ERROR|INTERRUPTED`, `issues:tuple[DraftIssue,...]`, `reviewed:bool`, `reviewed_basis_hash:str|None`, `excluded_duplicate_of:str|None`.
- `DraftIssue`: `code`, `field:str|None`, `message`, `blocking:bool`, `refs`. Issue trong draft, không BusinessIssue/FACT của hồ sơ.
- `EventExpenseDraft`: `id,version,event_name,manager_name,owner_actor,declared_advance:StrictInt,rows,read_status,review_status:DRAFT|REVIEWED,reviewed_basis_hash:str|None,summary`.
- `DraftSummary`: `partial_total:int,known_rows:int,total_rows:int,declared_total:int|None,draft_delta:int|None,direction:RETURN|REQUEST_MORE|BALANCED|UNKNOWN,ready_for_review:bool`.
- `project_event_rows(sources:tuple[SourceRef,...], report:ReadResult) -> tuple[EventDraftRow,...]`; mapping từng file, không chỉ iterate analyses thành rows.
- `summarize_event_draft(draft:EventExpenseDraft) -> DraftSummary` pure; mọi tổng server-recomputed.

- [ ] Viết RED `test_three_files_three_rows_and_return_800000`: amount1_080_000/2_160_000/960_000, advance5_000_000; total4_200_000, delta−800_000, RETURN. Row/sourceIDs đúng cả khi đổi thứ tự document trả về.
- [ ] RED `test_unknown_amount_is_not_zero`: một amountNone ⇒ declared_total/deltaNone, partial_total chỉ dòng biết; `test_missing_payer_blocks_review_not_known_amount_sum`.
- [ ] RED `test_manual_missing_amount_can_complete_draft_but_read_failure_cannot`, `test_amount_edit_cannot_clear_arithmetic_conflict`: phân biệt thiếu field từ nguồn đọc đủ với lỗi toàn nguồn/budget/coverage. Correction có origin và reason, không thành verified. Chỉ read/re-source mới gỡ lỗi nguồn, không nút chấp nhận chung.
- [ ] RED `test_file_total_not_sum_of_line_total_and_grand_total`, `test_buyer_is_not_automatic_payer`, `test_nonexpense_document_not_auto_counted`, `test_duplicate_digest_requires_explicit_exclusion`, `test_same_filename_distinct_source_rows`, `test_bool_float_negative_money_rejected`.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 pytest tests/unit/test_event_draft.py -q`; lưu RED do thiếu hành vi, không dùng lỗi môi trường làm bằng chứng.
- [ ] Implement DTO/projector tối thiểu; type-specific amount chọn field tổng nguồn hiện có; chưa rõ thì issue thay vì đoán. Giữ optional số chứng từ, bắt buộc ngày/nội dung/amount/payer trước REVIEWED; không yêu cầu category/hạn mức mới.
- [ ] Run lại cùng command ⇒ PASS. Checkpoint T1: DTO/API names khóa cho các task sau.

## T2 — Evidence-only batch không cần đơn đầu vào

**Files:** create evidence/evidence_batch.py,
`tests/integration/test_event_draft_reader.py`; modify reconciliation/digital_intake.py.

**Consumes:** SourceRef/ReadResult/RunBudget/DocumentAnalysis hiện có; T1 projector.
**Produces:**
`async read_evidence_sources(*,sources:tuple[SourceRef,...],reader:object,classifier:object,artifacts:object,source_bytes:dict[str,bytes],budget:RunBudget,provider_mode:str,root_id:str,activity_profile:str|None=None)->ReadResult`.
Trả documents/quality/coverage/problems/identity cho evidence; không tạo synthetic
paper hay `SETTLEMENT_FORM_MISSING` chỉ vì không nộp đơn.

- [ ] Viết RED spy3files ⇒ OCR3 lần, extraction3 lần khi không confidence candidates/repair; classifier riêng0. Không assert mọi input luôn đúng3LLM vì các bước phụ có điều kiện.
- [ ] Viết RED lỗi OCR1file ⇒3rows từ projector, coverage/error đúng nguồn, không missing-success; exhaustedbudget vẫn giữ file chưa đọc. Test ảnh buyerName khác payer không tự gán.
- [ ] Viết characterization cho S6 trước tách: cùng input/reader report giữ documents/refs/confidence/problems/matching/call-counts. Run `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_event_draft_reader.py tests/integration/test_s6_digital_api.py -q`.
- [ ] Tách đúng đoạn OCR→confidence→evidence extraction→validate/arithmetic của `read_digital_report` vào helper; cả S6 và newservice gọi nó. Không copy cả pipeline thành luồng thứ ba; giữ quota retry/schema/source guards/telemetry/provider identity.
- [ ] Run cùng command và `rtk proxy uv run --frozen --python 3.12 pytest tests/unit/test_role_aware_pipeline.py tests/integration/test_role_aware_workflow.py -q` ⇒ không regression. Checkpoint T2: reader không side effect tiền và không provider call thật.

## T3 — Lưu draft và API phiên bản, không tạo case tài chính

**Files:** create workflow/event_drafts.py, api/event_drafts.py,
`tests/integration/test_event_draft_api.py`; modify workflow/schema.sql,db.py,api/app.py.

**Consumes:** T1 DTO/projector/summary; T2 helper; Database/session/storage hiện có.
**Produces:** `EventDraftService(db,uploads_dir,evidence_wiring,max_source_bytes)`
(app inject DB/storage/reader factory hiện có, không tự tạo provider/config thứ hai),
methods `create(session,payload,command_id)`,
`list(session)`, `get(session,draft_id)`,
`attach(session,draft_id,uploads,expected_version,command_id)`,
`async read(session,draft_id,expected_version,command_id)`,
`patch(session,draft_id,patch,expected_version,command_id)`,
`review(session,draft_id,expected_version,command_id)`,
`interrupt_abandoned_reads()` và `get_source(session,draft_id,source_id)`.

API base `/api/event-drafts`: POSTcreate/GETlist; GET`/{id}`;
POST`/{id}/sources`; GET`/{id}/sources/{source_id}`;
POST`/{id}/read`; PATCH`/{id}`; POST`/{id}/review`.
Mutations nhận X-Command-Id và (trừ create) X-Expected-Version. Khi trùng command
đang chạy, read trả202 cùng draft/run; đã xong trả receipt đã lưu, không gọi lại.
Stale hoặc same-command-different-request409; cross-scope404; validation422.

Create fields `event_name,manager_name,declared_advance`. Patch fields header trên
và `row_updates[{row_id,description?,expense_date?,document_number?,amount?,payer?,correction_reason?}],reviewed_row_ids[],duplicate_exclusions[{row_id,duplicate_of}]`.
Không cho client gửi tổng/actor/refs/source paths/verified flags. `row_updates`
có thể chứa nhiều row để gán nhóm; validator chặn row/source không thuộc draft.
Sources multipart gồm `files` và manifest cùng độ dài với `client_file_id` duy
nhất, `relative_path` đã sanitize; response echo clientID→sourceID. Không đoán
mapping từ tên hoặc thứ tự DB trả về. ReadStatus toàn draft dùng
`NOT_READ|READING|COMPLETE|INCOMPLETE|INTERRUPTED`; trạng thái COMPLETE chỉ nói đã
đọc hết nguồn, không tự thành REVIEWED. Row sửa qua patch chỉ chấp nhận các trường
đã liệt kê, không xóa issue/source bằng payload tùy ý.

- [ ] RED create+attach+read+patch+review+get; manager đứng header, An/Bình đứng các rows, manager_name không ghi đè owner_actor. Persona employee hiện có dùng được; client manager role không cấp quyền mới.
- [ ] RED reopen qua service/app mới trên cùng testDB giữ sources/corrections/review; list hai folder tên giống nhau vẫn2draftIDs. Samefilename khácbytes ánh xạ bằng client_file_id→server source_id, không map bằngname.
- [ ] RED compare DB trước/sau full flow: không thêm/thay `cases,money_events,instructions,case_confirmations,usage_registry,case_conclusions`.
- [ ] RED cross-tenant/cross-owner GET/PATCH/source404; traversal filename không thoát storage; media sai415, tổng vượt50MiB hoặc>10file/20MiB413, không để nửa batch thành công giả. Reuse validators đang có thay vì tin MIME.
- [ ] RED duplicatecommand không thêm source/correction/provider; stalewrite409; late read không ghi đè patch mới; artifacts thất bại được giữ và read kết thúc stale rõ ràng. Restart pendingread→INTERRUPTED, manualretry mới chạy; re-read không mất correction.
- [ ] RED `test_review_tracks_content_not_stale_checkbox`: sửaamount/payer/batchpayer invalidates row+whole; đổiadvance/header invalidateswhole; read mới đổi nội dung invalidates relatedrow; GET/repeatcommand không invalidate. Patch vừa sửa vừa markreviewed cùng row422. File attach lần2 trả409; muốn thay nguồn tạo draft mới, không tự chuyển correction.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_event_draft_api.py -q` để lưu RED.
- [ ] Thêm3bảng riêng `event_expense_drafts`(current JSON/version/tenant/owner), `event_expense_sources`(source/digest/media/path metadata), `event_expense_draft_revisions`(immutable payload/actor/time/reason/command receipt/requesthash). Schema version lấy current+1 lúc implement, không hardcode13 nếu main đã đổi. Migration test từ DB cũ có dữ liệu, không xóa dữ liệu.
- [ ] Implement ngắn transaction lưu state, network ngoài transaction; read commit kiểm capturedversion/sourcebasis/readeridentity. Persist raw analysis/artifacts để nguyên; corrections phủ lên view và review lại khi liên quan đổi. Source content immutable sau attachbatch; file sửa cần tạo draft mới ở v1. Không gắn foreign keys sang canonical case root.
- [ ] Wire service/router trong create_app, session lấy từ server. Tiền ứng và tên manager là declaration, không authority. Startup chỉ interrupt event-draft read chưa kết thúc, không sửa workflow money jobs.
- [ ] GREEN command T3 + T1/T2; checkpoint có API durable/versioned/isolated, chưa claim browser.

## T4 — UI folder → report → chỉnh sửa/gán nhóm → bản nháp đã kiểm tra

**Files:** create frontend/src/features/event-draft/{api.ts,types.ts,event-draft.tsx},
`frontend/tests/event-draft.test.tsx`; modify frontend/src/App.tsx.

**Consumes:** T3 endpoints, T1 DTO names; API types mirror snake_case payloads.
**Produces:** `EventDraftWorkspace({onBack}:{onBack:()=>void})` và entry
**Tạo nháp từ folder** trong workspace người nộp, độc lập intake hiện có.

- [ ] RED chọn folder3files→3rows; không yêu cầu upload đơn chính, manager header và payer khác nhau đúng chỗ. Fallback chọn nhiều files chạy cùng path; `webkitdirectory` chỉ feature enhancement.
- [ ] RED select2rows+gánAn chỉ sửa2rows theo rowIDs; haifilename giống nhau không ảnh hưởng lẫn. Field chỉnh tay giữ nhãn **Đã chỉnh sửa**, OCR original/ref vẫn mở được.
- [ ] RED partial/error hiển thị N/M/tạm cộng; không **Đã trích xuất** toàn bộ hoặc hoàn thiện. Thiếupayer vẫn lưu nháp được; REVIEWED chỉ sau các dòng được kiểm tra, nhãn **Bản nháp đã kiểm tra**.
- [ ] Verify Node pin24 và npm's own node cùng scopedenv, ghi selector/version evidence trước npm. Run `rtk proxy npm --prefix frontend test -- tests/event-draft.test.tsx` để lưu RED.
- [ ] Implement màn hình theo design tokens hiện có: header sự kiện/manager/ứng kê khai, upload, bảng có chọn nhóm và nguồn gốc, footer tổng dự kiến. Nút **Lưu nháp**, **Hoàn thiện bản nháp**; không nút **Duyệt/Ghi nhận tiền/Gửi kế toán** trong feature này. Refresh hiển thị danh sách draft từ API, không chỉ localStorage.
- [ ] Source link dùng sourceID authenticated endpoint, tên file escape, không HTML từ OCR. Sửa số tiền dùng parser strict, gửi số nguyên; không `parseInt(x)||0` che dữ liệu trống.
- [ ] GREEN T4 + `rtk proxy npm --prefix frontend test -- tests/digital-intake.test.tsx tests/intake-draft.test.tsx tests/app-restore.test.tsx` + `rtk proxy npm --prefix frontend run build`. Checkpoint T4 component/build; browser còn NOT_RUN.

## T5 — E2E độc lập, hồi quy và báo cáo nghiệm thu

**Files:** create frontend/e2e/event-draft.spec.ts,
`scripts/seed_event_draft_browser.py`,
docs/final/reviews/2026-10-17-event-expense-draft-acceptance.md;
modify docs/final/{IMPLEMENTATION_CONTRACTS.md,IMPLEMENTATION_STATUS.md,RUNBOOK.md}.

**Consumes:** T1–T4; test-only synthetic sources/reader. Seed phải dùng testDB và
nguồn tổng quát cho feature mới, không sửa PDF/context/gold25case hiện có.

- [ ] RED browser trên DB mới/port riêng: folder3files→OCR fixture→assignAn/Bình→sửaamount→save→reload→review→reopen, file viewer mở đúng nguồn. Ví dụ tổng4.2m/ứng5m/hoàn800k đúng; trạng thái chỉ draft.
- [ ] Browser counterexample missingamount/failedsource hoặc budgetexhaustion giữ đủrows, chặnreview; duplicate digest và samefilename cases kiểm UI/API. Không network tới provider (fake transport/guard chặn ngoài).
- [ ] Browser reload lúc read đang chạy không tựPOSTread thêm; API late-result/stalewrite/restart regressions T3 và counters được ghi trong report.
- [ ] Dùng browser harness hiện có với seed riêng; ghi command,revision,mode,source inventory,DBpath,port,trace/screenshot và mọi FAIL. File seed không import vào production app.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 pytest tests/unit tests/integration -q`; frontend full `rtk proxy npm --prefix frontend test`, build và browser theo configured harness. Bổ sung scripts/version hiện có nếu HEAD đã đổi; không dùng sai Node để claim PASS.
- [ ] Reproduce bất kỳ failure trên baseline cùng snapshot/data/time nếu cần phân loại; không mặc định6lỗi cũ vẫn đúng. Không xfail/hạ guard/sửa expected để xanh. Nếu không chạy full/browser ghi NOT_RUN, không thay bằng componentPASS.
- [ ] Acceptance matrix: DTO/projection; evidence reuse/callcounts; persistence/migration/version; sourceownership; browserhappycase; adverseinput; S6regression; fullsuites; LIVEquality. Ghi PASS/FAIL/NOT_RUN từng gate, LIVEquality NOT_RUN nếu chưa được ủy quyền.
- [ ] Tài liệu giới hạn phải ghi: trùngbytes không phải chống mọi trùnggiao dịch; conflict số học do OCR có thể vẫn chặn ở V1; thayfile cần draftmới; chưa xuấtPDF/chưa giao việc đa tài khoản. Không che những giới hạn này bằng báo happycasePASS.
- [ ] Update contracts với draft-only boundary, status/checklists đúng evidence và runbook cách chọn folder/gánngười/lưu/mởlại. Checkpoint cuối: feature ready chỉ khi gate T1–T5 đạt; production/modelaccuracy/practitionerimpact chưa được chứng minh.

## Trình tự thực thi và bàn giao

T1→T2→T3→T4→T5. Khuyên một agent triển khai chính theo thứ tự vì read DTO, persistence
và source ownership liên quan chặt; một reviewer độc lập xem diff cuối. UI có thể
giao riêng sau khi T3khóa API; không cần5agent cùng sửa sharedfiles.

Planning turn chỉ tạo spec và plan này, builder-check và self-review tài liệu.
Chưa chạy pytest/npm/browser/provider hoặc đổi schema trên DB thật. Khi người dùng
chọn triển khai, kiểm lại HEAD và task gates; không hiểu chấp thuận plan là quyền
commit/deploy hay nâng quota/model.

## Planning review record

- Builder-check độc lập nhận spec và chỉ đọc: tìm3điểm cần chốt (sửa tay/gỡblocker,
  hiệu lực review sauedit, thayfile). Đã giải quyết trong spec§4 và T1/T3, không cần
  đổi happycase người dùng đã chốt; đây là các lựa chọn V1 được ghi rõ.
- Self-review: phạm vi đầu vào/đầu ra T1/T4; readerreuse T2; nguồn/version/tenant
  T3; mỗi ReviewFocus có regression; browser/regression/report T5. Chữ ký helper
  và DTO đồng nhất giữa các task. Không task nào submit/generate money.
- Mọi execution checkbox còn mở. Kết quả reviewer là reviewtài liệu, không
  approval code hoặc proof runtime. Người dùng có thể điều chỉnh giới hạn V1
  trước triển khai.

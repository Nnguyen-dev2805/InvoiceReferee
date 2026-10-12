# InvoiceReferee — System contract hiện hành

Ngày 09/10/2026. **Thiết kế được đồng ý; các chức năng mới chưa được nghiệm thu runtime.** Đây là bản hợp nhất contracts R7, không nâng PLANNED thành IMPLEMENTED. [Product](PRODUCT.md), [Rulebook](RULEBOOK.md), [Evaluation](EVALUATION.md) và [plan](../superpowers/plans/2026-10-09-settlement-mvp.md) là các nguồn hiện hành; nguyên bản và các quyết định trước đó nằm trong [archive](../archive/README.md).

## S1. Kiến trúc và trách nhiệm

Một backend Python/FastAPI/Pydantic, một SQLite qua `sqlite3` và thư mục originals/artifacts; React/TypeScript/Vite UI. HTTPX cho Mistral OCR và xkiro, `pypdfium2` cho PDF text/render, Pillow khi cần representation; workflow Python trong process. Không mặc định agent framework, ORM, vector DB, worker service hoặc queue phân tán.

```mermaid
flowchart TD
    UI["UI nghiệp vụ"] --> APP["Ứng dụng/workflow và controls"]
    APP --> READ["Đọc nguồn và đề xuất liên kết"]
    READ --> CHECK["Validation, quy tắc, tiền và quyền"]
    APP --> CHECK
    CHECK --> REPORT["Report có căn cứ hoặc câu hỏi"]
    REPORT --> APP
    APP --> STORE["SQLite và files: nguồn, runs, quyết định, tiền, history"]
    EVAL["Evaluator: input tách gold"] --> APP
```

UI và runner dùng cùng application path; UI không tính lại kết luận tài chính. Một bộ điều phối thực hiện nhiều tác vụ AI, không đồng nghĩa cần nhiều agents. AI không tự chọn financial tools, sửa policy hoặc lặp tới khi có số vừa ý.

Module map (sau consolidation): `store.py` là façade công khai giữ signature cho Service/API/tests và sở hữu connection/transaction (`_write`/`_read`). SQL lifecycle tách theo nghiệp vụ trong `settlement/persistence/` cùng một transaction: `sqlite_records.py` (helper record dùng chung), `queries.py` (read/selector/money-context), `decision_records.py` (B8), `money_records.py` (B9 + revalidation), `action_records.py` (handoff/closure/adjustment), `advance_records.py` (B3/B5), `linked_context_records.py` (B6→B7 child/context). Các hàm này nhận `conn:sqlite3.Connection` đã mở, không tự mở connection/commit và không gọi ngược façade. Module thuần tính toán: `advance_workflow.py`, `advance_reconciliation.py`, `settlement_workflow.py`, `settlement_reconciliation.py`, `linked_context.py`. Contract Pydantic tách theo vùng nghiệp vụ trong `settlement/contracts/` (xem S11); `models.py` là façade re-export + `model_rebuild`, `b3_intake.py` là entry re-export contract B3 (từ `contracts/b3_contracts.py`) và evaluator `b3_evaluation.py` (xem S11). `shared/` chứa `errors.py` (một `DomainError` class identity), `artifacts.py`, `clock.py` (thời gian ghi record — khác business time trong `*_workflow`). Tên module là nội bộ; wire values/persisted codes/DB schema/API path không đổi.

Reuse utilities/layout/guards thật đáp ứng. Lõi mới có tên và DB riêng trong quá trình chuyển đổi theo plan, không fallback sang reducer cũ hoặc mount hai contracts trên cùng API paths. Sau cutover, normal UI/Verify gọi cùng settlement core. Không phá local data cũ để đổi schema.

Versions packages/OCR pin theo dependency thực resolve và bring-up; tài liệu latest không là version installed. Không cài stack chỉ để đọc/review. Tests: pytest, Vitest và browser E2E trọng yếu; không unit test mọi helper hoặc mọi click vô điều kiện.

## S2. Hợp đồng đọc, liên kết và kết quả

| Nhóm | Dữ liệu bắt buộc theo chức năng |
| --- | --- |
| Context | case/work/employee/job B3/B7, input revision, money_as_of, knowledge cutoff, policy/config và quyền/coverage áp dụng |
| Source | ID, original/hash/type, uploader/received time, issuer nếu có, supersedes/binding và page/row/form locator |
| Observation | ID/key/raw/read_state/refs, normalized value hoặc null, basis/usability và phần chưa rõ |
| Relation | source/expense/event IDs, kind/portion/support refs, proposed/đủ căn cứ/chưa rõ, reason |
| Check/issue | rule/applicability/status/input refs/reason; type/owner/câu hỏi, phần bị chặn và điều kiện resolve |
| Report | Expense rows, facts/links/checks, components/net statuses, issues/next step, source/run/config refs |
| Decision/event | Basis/scope/actor/quyền/conditions/report; riêng gross money/parties/event time/raw outcome/relation/refs |
| Run/history | Snapshot, outputs/errors/timing/calls/reuse origin, control epoch/status và liên kết trước/sau |

Backend cấp IDs; model chỉ dùng các refs/candidates đã cung cấp, không cấp case/version/quyền cho chính nó. Một key có nhiều observations giữ locator/nguồn riêng. Duplicate/extra IDs, refs ngoài scope, contradiction hoặc truncated output được phát hiện trước dict/aggregation, không drop/overwrite âm thầm.

Extraction input là một source/nhóm trang liên quan có giới hạn và các keys cần cho checks. Form/CSV hỗ trợ parse trực tiếp. Không đưa claim amount làm đáp án gợi ý cho đọc invoice hoặc đưa expected/case labels vào prompt. Nội dung chứng từ là data, không chỉ dẫn thay policy. Tên file là nhãn hiển thị/ref, không outcome.

```json
{
  "fields": [{
    "key": "invoice.total",
    "raw_text": "3.000.000",
    "read_state": "READ",
    "evidence": {"page": 1, "quote": "Tổng thanh toán: 3.000.000"}
  }]
}
```

Ví dụ contract, chưa kết quả OCR. Ứng dụng gắn source/version rồi normalize cùng currency/unit có nguồn. Quote do model đọc ra không là chứng cứ độc lập; giữ trang gốc. READ là observation, chưa proof payer/receipt hoặc source authenticity. NOT_FOUND chỉ không tìm thấy trong phạm vi đã đọc, không absence cả hồ sơ. UNCLEAR giữ null/locator/fragment. Field yêu cầu bị bỏ khỏi output không tự NOT_FOUND. Trang chưa đọc/provider lỗi/format lỗi là technical/capability, không NOT_FOUND. Bbox chỉ khi có vị trí đáng tin cậy; row/field locator dùng theo source thật.

Money dùng cho claim/decision/result là strict integer VND, reject bool/float ở boundary. Raw document values/quantity/price giữ dạng chính xác và bounded Decimal; không guessed units/currency/tỷ giá/rounding. Separator không xác định duy nhất giữ issue; không suy VND từ locale. NOT_APPLICABLE chỉ đúng check, không toàn case.

Matching nhận observations/claim/context và candidates, trả relations/parts/support refs hoặc ambiguity. Kiểm refs/namespace, source hỗ trợ, work/parties/amount/currency/portion/time, duplicates và receipt/coverage. JSON hợp lệ không chứng minh semantic link đúng: material ambiguity giữ issue; đo link quality trên originals/gold riêng. Một invoice và payment là hai loại đối tượng; multiple sources của một payment không multiple payments, hai actual payments cùng invoice không được xóa như duplicate.

## S3. Report, câu hỏi và các nghĩa tiền

Check status PASS/FAIL có căn cứ/UNRESOLVED/NOT_APPLICABLE; technical execution là trục riêng. Issues có FACT/POLICY/AUTHORITY đồng thời; TECHNICAL/CAPABILITY/MONEY_INCIDENT/CONTROL không ép vào ba loại đầu. Check độc lập đủ nguồn vẫn lưu khi final net chưa đủ.

| Trường logic | Ý nghĩa |
| --- | --- |
| components | T/B/E/A/RA/P/RP value hoặc null, state và refs. B3 giữ forecast/request/history, không giả E/S hậu kiểm |
| calculated_net_vnd | Tính từ facts/eligibility đã rõ, có thể còn thiếu quyền/routing hợp lệ; Q14 calculated 3 nhưng authority chưa đủ |
| conditional_results | Kịch bản policy có điều kiện rõ từ facts đã xác minh; Q13 có nhánh chấp nhận toàn/phần. Không giả hotel amount mờ |
| proposed_net_vnd | Đủ facts/eligibility/căn cứ và đường quyền cho report-ready; chưa amount đã duyệt; authority chưa rõ giữ null |
| approved / actual / remaining | Từ decision/events riêng; không sao chép calculated/proposed thành approved/received |

Không lấy first-non-null làm payable. Material amount/payer/history unknown thì net phụ thuộc giữ null, subtotal riêng. Report job COMPLETE/INCOMPLETE khác accounting review/decision/receipt/closure. COMPLETE chỉ khi checks/material issues/routing trong scope đã đủ; technical failure ảnh hưởng kết quả không COMPLETE. Chờ financial decision thường quy sau report-ready không là missing-fact hoặc false escalation. B3 không incomplete chỉ vì approval đang xin chưa có.

Câu hỏi giữ issue_id/owner/refs, khoản/phần, đã biết, vướng mắc, loại nguồn/decision cần và phần bị chặn. Response giữ question_id/actor/scope/content/source hoặc decision/revision/time. Received chưa resolved; đúng owner/source/scope và re-check mới resolve. Response không đủ giữ reason/history; câu hỏi không còn áp dụng do revision có status riêng, không tính như đã được trả lời đúng. Có thể trả nhiều issue độc lập cùng lần, không hỏi lại phần đã đủ.

## S4. Đường đọc và điều phối AI

Form/bảng hỗ trợ parse trực tiếp; PDF text phù hợp dùng text+locator; ảnh/scan dùng Mistral OCR→xkiro extraction. PDF hỗn hợp routing theo trang/vùng; có text không proof mọi trang/field đủ hoặc lớp OCR ẩn đúng. Giữ bản gốc và case để phát hiện hidden-text mismatch; không claim heuristic phát hiện mọi lỗi layer.

Trang PDF render thành PNG gửi OCR với MIME của ảnh, giữ source PDF và số trang gốc. Budget trang tính mỗi trang gốc một lần; backend cấp observation ID theo nguồn/trang/vị trí field, không dùng model-local ID làm ID toàn hồ sơ. ID model trùng trong cùng response vẫn bị từ chối; các giá trị mâu thuẫn giữa nguồn/trang vẫn giữ để kiểm tra. OCR thất bại vẫn có call trace và giữ technical failure, không coi là không tìm thấy thông tin.

Render/rotate/crop là representation có transform/mapping về original. Crop giữ context tổng/subtotal/receipt và contradictions; không sinh lại chữ số thiếu rồi dùng làm evidence. Một tài liệu nhiều trang giữ context cần thiết; không gộp tất cả hồ sơ vào một prompt. Chỉ đọc fields/lines/parts cần theo check, nhưng không dùng total để bỏ chi tiết bắt buộc cho personal/split.

Đọc lại field/vùng chỉ khi có lý do và khả năng làm rõ; actual source che/thiếu giữ uncertainty, không gọi tới khi sinh số. Mọi corrective/transient/targeted attempts dùng chung budget. Provider failure/invalid output không thành employee violation.

Candidates theo scope với refs, parties/work/booking/currency/amounts/parts/time; không filter cứng same amount vì deposit/partial, không tự match từ amount/date/name. Ghi selection trace và phạm vi chưa xem. Empty top-k không absence; coverage cần thiết bị giới hạn giữ issue. Direct relations có nguồn đủ được kiểm bằng chương trình; AI chỉ hỗ trợ nhóm cần hiểu memo/nội dung. Trước calibration đủ cho nhóm semantic, proposal chưa auto thành fact vì model nói chắc. Ngưỡng từ signals/score thật theo loại quan hệ, không confidence tự báo.

Source mới: đọc phần mới và links/checks/decision validity ảnh hưởng. Claim payer/purpose đổi: không cần đọc lại original không đổi. History mới: cập nhật event/coverage/money; policy/quyền đổi: checks/basis liên quan. Reader/model/prompt/keys/representation đổi: không cache cũ để giả đo model mới. Reuse theo hash/config/keys/representation và origin, không filename; samebytes khác case không chuyển obligation/quyền.

Không cần generic dependency engine; mapping source→facts→links→checks/run đủ. Lỗi không đủ trace nguyên nhân giữ inconclusive, không quy hết OCR/LLM.

## S5. Provider và cấu hình pilot

Mistral OCR và xkiro do chủ dự án chọn. [Public catalog snapshot](../discovery/R7_XKIRO_CATALOG_EVIDENCE.json) là GET ngày 09/10/2026, không inference/account/quality proof. Candidates: `mistralai/mistral-small-2603` thử đầu, `mistralai/mistral-medium-3.5` challenger; reasoning_effort none theo metadata, chưa kiểm effective settings. Không default high hoặc thêm agent nếu không evidence cải thiện.

xkiro base `https://api.xkiro.com/v1` với full vendor/model. Docs công bố blocking 95 s và controls/capabilities có thể bị bỏ/điều chỉnh theo model; JSON mode không đảm bảo shape/truth, vision unsupported có thể bị bỏ ảnh mà không HTTP error. Validator và probe cần; HTTP 200 không proof đọc ảnh/enforced settings. Requested/returned model và request IDs ghi riêng; response model không xác thực upstream/weights khi gateway routing không lộ đủ. Benchmark gắn pipeline qua gateway/config yêu cầu, không independent upstream claim.

Mistral OCR pages/Markdown/locator/quality metadata phải kiểm đúng model/account; paragraph blocks phụ thuộc version. Không fake bbox/score khi vắng. OCR riêng+extraction giúp đo hai bước; annotations là variant OCR+LLM phía dịch vụ, không independent verification và chưa gọi thêm vô điều kiện. OCR alias latest chưa baseline pin. API keys server-only, không UI/public traces; không live→fake fallback.

| Config v0 đã đồng ý để thử, chưa benchmark | Giá trị |
| --- | --- |
| App |1 process;2 active runs; tối đa 5 accepted active/queued; một PDFium executor tuần tự vì không thread-safe |
| Calls |2 client calls toàn app, sources tuần tự mỗi run; không proof remote execution đã ngừng sau timeout |
| Run deadline |240 s từ accepted, gồm chờ slot |
| Call timeout |OCR 60 s/xkiro 80 s, capped bởi deadline còn lại |
| Attempts |Tối đa 2 mỗi extraction unit, lần đầu+1 retry/repair/targeted chia chung, không lách bằng tách unit cho cùng vùng |
| Total calls |32/run, gồm OCR/LLM/retries; SDK không retries ẩn |
| Output cap |3072 extraction/2048 matching; check finish_reason, không dùng truncated JSON |
| UI |Poll 1 s khi active, dừng/backoff khi terminal/tab không theo dõi |

Một attempt là một lần đường đọc, có thể OCR+LLM nên khác số calls; tất cả calls vật lý ghi budget. Matching không vòng tự mở rộng vô hạn. Hết budget/deadline giữ partial output và technical reason, không fake unreadable hoặc COMPLETE. Không-stream output nhỏ là cấu hình đầu; streaming là variant đo khi cần, không partial stream facts/action. Cancel/Stop local không bảo đảm upstream/bank hủy hoặc hoàn phí.

## S6. Versions, API và mutation guards

`case_version` tăng trên accepted mutations cho concurrency; `input_revision` cho form/scope/sources/responses/decisions ảnh hưởng snapshot; `control_epoch` tăng mỗi Stop/resume, `stop_active` riêng. Run giữ immutable snapshot/hash/IDs/money cutoff/knowledge cutoff/policy/config/epoch. Mutation version khác decision basis; correct fulfillment không tự invalidates tổng approval. Harmless notes không mất mọi decision. Material changes phải re-check phần liên quan.

Các paths dưới `/api`. POST/PATCH có actor_id/demo_role, expected_case_version khi case có và Idempotency-Key. GET không gọi provider/tạo actions. Backend allowed_actions+reasons và endpoints đều kiểm lại lúc ghi.

| Endpoint | Contract |
| --- | --- |
| POST /cases; GET /cases; GET /cases/{id} | Nhận Submission/job/scope/mốc; lưu unknown; trả versions/stage/sources/issues/actions, không cần approval đang xin |
| POST /b3-cases; POST /b7-cases | Managed create cho luồng thường ngày: chỉ actor + lời khai (`b3-intake-v1`) hoặc `{purpose,scope}` (B7 tự chi); định danh/scope/clock do backend cấp, `work_ref` = `case.id` cho hồ sơ mới; không nhận employee/work/job/clock/parent/quyền |
| PATCH /cases/{id}/submission | Revision mới, reason/version, giữ bản trước, invalidate/recheck phần ảnh hưởng |
| POST /cases/{id}/sources; GET /sources/{id}/content | Originals/provenance/supersedes/import, trạng thái/limits; source ID backend, không tùy ý client path; upload không verified facts |
| POST /cases/{id}/runs; GET /runs/{id}; GET /runs/{id}/report |202 run+status URL hoặc same command record; explicit allowed mode, snapshot/current; report đúng run/current khác history |
| GET /cases/{id}/questions; POST /questions/{id}/responses | Question/response riêng, source/actor/scope/revision và re-check trước resolved |
| POST /cases/{id}/reviews | report_id/refs/version/nội dung rà soát; không approval |
| POST /cases/{id}/decisions | basis/report/rights/content/amount/direction/conditions/reason, combined nội dung đủ quyền; không arbitrary final S |
| POST /cases/{id}/handoffs | Guard current rights/Stop/basis/remaining/pending, trả report/decision refs+audit; không payment entity  hoặc outbound send |
| POST /cases/{id}/money-events | Gross observations/parties/time/raw status/source/relation; giữ incidents, classification chưa đủ;201 record không actual receipt tự động |
| POST /cases/{id}/control |STOP/RESUME/scope/reason/version; ack sau persist, resume không tự retry provider/quyền chi |
| POST /cases/{id}/closures |SETTLEMENT_COMPLETE đủ gates hoặc REJECTED_REQUEST_ENDED đúng ý nghĩa, report/scope/as_of/basis |
| GET /cases/{id}/history |Linked source/revision/run/actor/decision/money/control/closure, raw history không overwrite |

Errors có code/message/refs/issues/current version:422 malformed type/ref,413 resource,415 format,409 stale/busy/action blocked,403 quyền nghiệp vụ theo demo-policy. Thiếu fact có thể accepted và report incomplete, không ép HTTP error. Slot full phản hồi bận rõ; tối đa một nonterminal run hiện hành mỗi case, revision supersedes cũ có history. Re-run new key được nhưng không new entitlement.

Transaction lookup command scoped case/actor/operation trước old version check: same key+same fingerprint trả record cũ và current state; same key+different payload 409. New key kiểm version/control/gates rồi ghi entity/command/audit/tăng version atomic. Record trả lại không tự proof còn valid. Command idempotency khác business same-event dedup; lưu observations mâu thuẫn, không upsert đè source namespace/ref.

## S7. Storage, trạng thái và Stop

Tám bảng SQLite với columns ID/query/constraints và typed payload JSON: cases, case_revisions, sources, runs, interactions(QUESTION/RESPONSE/REVIEW), decisions, money_events, audit_events. Data fields theo S2/S6; decision history/gross money/epoch/revisions giữ rõ, không table mỗi OCR field hoặc event-sourcing framework.

Foreign keys/unique command keys/current constraints phù hợp; writes ngắn, không giữ transaction lúc provider wait. Quyết định đọc gates và ghi current/action/control có boundary atomic phù hợp. Files và SQLite không shared transaction: staging/limits/hash→final file→DB metadata/revision; success chỉ khi cả hai dùng được. DB fail có thể orphan app-owned file nhưng không source accepted; cleanup chỉ staging/orphan thuộc app, không user original/history đang dùng. Reuse blob không same obligation/quyền.

Execution tách report completion và business stage:

```mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: Slot và guards hợp lệ
    RUNNING --> SUCCEEDED: Report được lưu
    RUNNING --> FAILED: Technical error
    RUNNING --> TIMED_OUT: Deadline/budget exhausted
    QUEUED --> TIMED_OUT: Deadline khi chờ
    QUEUED --> STOPPED: Stop persisted
    RUNNING --> STOPPED: Stop persisted
    QUEUED --> SUPERSEDED: Input thay thế
    RUNNING --> SUPERSEDED: Input thay thế
    QUEUED --> INTERRUPTED: Process ngừng
    RUNNING --> INTERRUPTED: Process ngừng
```

SUCCEEDED có report COMPLETE hoặc INCOMPLETE business issues; FAILED/TIMED_OUT giữ partial diagnostics không giả job complete. BUDGET_EXHAUSTED có reason riêng. Terminal không chạy lại; retry/resume tạo linked new run. Startup active/queued từ process cũ thành INTERRUPTED, không autoreplay/cost/action.

Stop ack sau commit epoch/flag/audit; callback kiểm revision/epoch/current_run/controls/policy tại publish/handoff/action/close. Late output chỉ historical, không current. Nguồn/tiền đã xảy ra vẫn record khi Stop; không để nguồn đó tự mở new action. Resume tăng epoch và cần recheck, không hồi phục old run/approval invalid.

## S8. Source envelope v0 và UI

Hỗ trợ v0 đề xuất JPEG/PNG, PDF không mã hóa đọc được; CSV UTF-8/BOM theo ledger contract; TXT/Markdown UTF-8 nguồn text/demo; native form JSON schema riêng, không arbitrary JSON policy. DOCX/XLSX/ZIP/HEIC/password PDF ngoài đường đọc, capability issue/cách bổ sung phù hợp khác business refusal.

Limits:20 MiB/file;20 active originals/80 MiB/run;20 PDF pages/file và 40 PDF/image pages/run(ảnh 1 page);24 MP/representation;1000 CSV data rows. Đây là config pilot để code/test, chưa là quality/capacity verified. Size/type/page/pixel/row được kiểm trước tốn resource, không tin extension/Content-Length. Overlimit không truncate first pages/rows rồi full coverage; ghi đúng part unprocessed/issue. File bị từ chối kỹ thuật không source đã đọc; có thể ghi metadata và capability issue. Không downsample/crop làm mất field rồi READ.

CSV columns: source_record_ref,event_kind,payer_ref,payee_ref,gross_amount_vnd,currency,event_at,reported_status; booking/work/employee refs và memo nếu nguồn có. Giữ raw/missing state, không force unknown status thành received. Header-only CSV không whole absence, coverage vẫn theo Rulebook.

UI mở được source từ observation→normalized fact/basis→link→rule→money impact; unknown nêu thiếu gì/owner; proposed/approved/actual/remaining riêng. Chạy từng slice từ intake/reload tới report/questions/decision/money/Stop/closure. Fake/replay hiện rõ, debug ở panel riêng. Run progress nêu stage/sources/pages đã xong/errors, không giả phần trăm/ETA.5 phiên/two writes/Stop/restart phải test; không tăng workers để claim 5 heavy calls.

## S9. Acceptance cho plan và evaluator

| ID | Hành vi cần actual evidence |
| --- | --- |
| SYS-01 | Tiếp nhận/import giữ nguồn, provenance và revision; mở lại được nguồn và tham chiếu đúng tài liệu |
| SYS-02 | Phát hiện ID trùng/thừa, output bị cắt, tiền kiểu bool/float và tham chiếu/locator sai trước khi tổng hợp |
| SYS-03 | B7 đủ nguồn trả đúng components, proposed amount, checks và refs; kết quả này chưa là tiền đã duyệt hoặc thực nhận |
| SYS-04 | Amount/payer/history/coverage chưa rõ giữ null và người cần làm rõ; subtotal đã biết không thay toàn bộ net |
| SYS-05 | Split payer, company direct, phần cá nhân và trùng lặp đúng parts/refs; net đúng tình cờ không đạt |
| SYS-06 | Vượt/chưa có B hoặc quyết định sai scope được xử lý đúng; không cắt tiền, tự nâng B hay miễn check theo role; combined decision được re-check mà không bắt duyệt lặp vô ích |
| SYS-07 | B3 hỗ trợ form/import, tách forecast và actual; không đòi approval đang xin như giấy tờ bị thiếu; dùng lại quyết định ngoài app còn hợp lệ |
| SYS-08 | Nhận phản hồi khác giải quyết issue; sai owner/source/scope không resolve; re-check đúng revision và phần ảnh hưởng |
| SYS-09 | Kế toán rà soát khác phê duyệt; phê duyệt không tạo receipt, thay raw fact hoặc tùy ý sửa S |
| SYS-10 | Chi một phần, sai người nhận, trả thừa và raw Paid giữ gross/history/issues/remaining; không đóng sai hoặc tự chi bù |
| SYS-11 | Sau Stop ack, chặn output hiện hành/handoff/action/closure từ kết quả đến muộn; resume không hồi phục run cũ hoặc quyền hết hiệu lực |
| SYS-12 | Thay đổi có ảnh hưởng được kiểm lại hiệu lực; fulfillment đúng giữ tổng đã duyệt; dữ liệu sau as_of không vào run cũ |
| SYS-13 | Retry cùng key và payload trả bản ghi cũ, không tạo trùng; cùng key khác payload bị chặn; copy/rerun không tạo tiền mới |
| SYS-14 | Đóng đúng scope/decision/sources/receipt, không Stop/pending/incident; từ chối giữ nghĩa vụ đang có; S = 0 không tạo money event 0 |
| SYS-15 | Vượt giới hạn không cắt dữ liệu rồi báo đạt; 5 phiên không trộn case hoặc ghi từ version cũ; run/calls/deadline có giới hạn |
| SYS-16 | UI và runner dùng cùng core; gold không vào input; báo đủ failures, assisted, mode và nguồn usage |
| SYS-17 | Routine job tự hoàn tất; A chưa tạo payment entity của B; action B có gates riêng; BTC chưa xác nhận ranh giới routine này |

Acceptance cần command/actual/log/mode/refs, không checkbox/spec hoặc worker self-report. [Evaluation](EVALUATION.md) giữ oracle và measurement gates; unit/integration/UI fake khác live quality và professional trial.

## S10. B3 v1 verbal intake (b3-intake-v1)

Nhánh khởi tạo B3 khi giao công tác bằng lời (Product P2a; plan
[2026-10-10-b3-verbal-intake](../superpowers/plans/2026-10-10-b3-verbal-intake.md)).
Form là lời khai (`B3Intake`, schema_version `b3-intake-v1`): IMPORT draft được
thiếu fields; bản confirmed phải đủ destination/purpose/dates/request dương/
deadline/ít nhất một row, `trip_start ≤ trip_end ≤ settlement_due`, tiền
StrictInt, không row âm, không row_id trùng. `Report.b3` là `B3Proposal`
(readiness/intake/forecast company–employee–total/work_permission/
advance_approval/accountant_ref/approver_ref/field_refs); components giữ a/ra
cho history actual (zero chỉ khi coverage đủ), b cho budget decision trước đó
(initial null), t/e/p/rp NOT_APPLICABLE; calculated/proposed/direction null.

Company context là backend fixture (`B3CompanyContext`, file env mới
`SETTLEMENT_B3_CONTEXT_PATH`; absent = None/unknown, malformed = startup
error, không fallback quyền). Clock cố định chỉ accepted khi activated+
synthetic; run ghi `simulation_clock` và map known-at nguồn tham gia snapshot
sang clock mô phỏng, audit nhận file vẫn giữ timestamp máy thật. Context
persist cùng RunInput (snapshot hash gồm submission/sources/revision/epoch +
policy + authority + b3_context + reader config); đổi config sau run không
sửa report/basis cũ.

Endpoint mới: `GET /api/demo-context` (people/routes, không cấp quyền do
client nhập); `POST /api/b3-cases` (actor_id + intake; persona/role/employee_ref
tra trong fixture; **hồ sơ mới lấy chính `case.id` làm scope** — không sinh
`WORK-...`; idempotent theo replay key trước khi phát id mới; clocks backend);
`POST /api/b7-cases` (B7 tự chi: `{purpose,scope}`, cùng định danh/scope/clock
do backend cấp, **không** tạo B3/ứng 0); `GET /api/runs/{run_id}/b3-context`
(snapshot grants/coverage/history, refs `company:<...>`). `CaseView`/`CaseSummary`
trả thêm `dossier_ref` (read-only: ID B3 gốc cho B3/linked/adjustment, ID riêng
cho B7 độc lập; suy từ persisted submission + origin_link, không từ `work_ref`).
PATCH submission giữ employee/work/clocks immutable cho B3 v1 và reject form
b3-intake-v1 trên hồ sơ legacy (không di trú ngầm). Generic
decision/money/handoff/closure vẫn bị chặn ở transaction guard bằng
`B3_REPORT_ONLY` (review chỉ nhận khi đã confirm); allowed_actions không quảng
cáo action chưa hỗ trợ.

Trình duyệt/quyết định ứng B3 (plan
[2026-10-11-b3-present-and-approve](../superpowers/plans/2026-10-11-b3-present-and-approve.md))
thêm hai endpoint chuyên biệt, **không** mở generic financial path:
`POST /api/cases/{id}/b3-presentations` (kế toán trình: `basis_report_id` +
đúng một `review_id` đã lưu hoặc `review` note/refs mới; lưu review +
presentation cùng transaction, stage `AWAITING_DECISION`; review mới lưu
`interactions` kind REVIEW, presentation lưu `audit_events` kind
`B3_PRESENTED`) và `POST /api/cases/{id}/b3-decisions` (`B3DecisionPayload`:
presentation_id/outcome APPROVE|RETURN|REFUSE/reason/work_allowed/budget_vnd/
advance_vnd; quyết định lưu `decisions` JSON kind `B3_ADVANCE`, audit
`B3_DECISION_RECORDED`). `CaseView.b3_workflow` (`B3WorkflowView`) là projection
derive từ records/basis (không suy từ free text): status NOT_PRESENTED/PENDING/
RETURNED/REFUSED/APPROVED/NEEDS_RECHECK, presentation/decision/basis_current/
blocked_reason. Presentation/decision bind một `basis_signature` (scope/form/
source hashes/policy/context/checks/issues — bỏ run id/timestamp/token) và
`context_signature`; đổi nguồn/revision/epoch/context làm basis stale
(`BASIS_STALE`/NEEDS_RECHECK). Quyền dùng `B3Grant` scoped (actor/employee/work/
hiệu lực, `max_budget_vnd`/`max_advance_vnd`; thiếu hạn mức không vô hạn) qua
`authorize_b3_decision`; route approver/accountant do backend cấp. APPROVE →
`AWAITING_MONEY`, RETURN → `CHECKING`, REFUSE → stage mới
`ADVANCE_REQUEST_REFUSED` (không thuộc `_CLOSED_STAGES`). `Service.start` gộp
quyết định B3 của chính hồ sơ (namespace `b3decision:<id>`) vào company history
khi re-run để không tạo issue duplicate giả; quyết định ngoài hồ sơ vẫn bị nêu.
B7 `_latest_decision_payload` chỉ đọc kind `SETTLEMENT`, nên `B3_ADVANCE` không
thành nghĩa vụ/money/handoff/closure B7. Error codes thêm: `BASIS_MISMATCH`
400, `B3_WORKFLOW_BLOCKED`/`B3_DECISION_EXISTS` 409 (cùng envelope hiện có).
Chưa có actual ứng (ghi tiền), liên kết nhập B3→B7, mở lại refusal hoặc đóng
lifecycle.

Reader B3 v1 dùng grammar `document.role/person.name/trip.*/advance.request.*/
forecast.*` (row_id document-local, backend namespace theo nguồn/trang;
`amount_words_value` là đề xuất diễn giải do LLM, Python so số). B3 v1 không
gọi generic payment matcher B7. Rule IDs: `trip_context`, `request_positive`,
`amount_words_consistency`, `estimate_arithmetic`, `request_forecast_consistency`,
`proposal_relation`, `source_form_consistency`, `history_coverage`,
`prior_advance_state`, `decision_route`. Nguồn tham chiếu form:
`form:<input_revision>:<field-path>`; không form-wins — form và nguồn khác
nhau là mâu thuẫn giữ cả hai refs.

**B5 ghi tiền ứng thực nhận** (plan
[2026-10-11-b5-advance-receipts](../superpowers/plans/2026-10-11-b5-advance-receipts.md))
thêm hai endpoint chuyên biệt, **không** mở generic financial path:
`POST /api/cases/{id}/b3-advance-proofs` (multipart; kế toán đúng route tải
chứng từ ứng; `Store.add_source(..., source_use="B3_ADVANCE_PROOF")` ghi audit
operation `B3_ADD_ADVANCE_PROOF` + `provenance.source_use` backend-owned, tăng
`case_version` nhưng **không** `input_revision` nên decision không stale) và
`POST /api/cases/{id}/b3-advance-events` (`B3AdvanceEventPayload`: decision_id/
namespace/ref/method/gross_vnd/payer_side/payee_ref/event_at/reported_status
RECEIVED|PENDING|FAILED|CANCELLED|UNCONFIRMED/evidence `B3MoneyFieldEvidence`
`HUMAN_SOURCE_REVIEW`/allocation_note/supersedes_event_id/`receipt_details`
(`B3BankReceiptDetails` proof_scope … hoặc `B3CashReceiptDetails`
voucher_number/acknowledgement …, kind phải khớp method); lưu `money_events`
JSON kind `ADVANCE_TO_EMPLOYEE`, audit `B3_ADVANCE_EVENT_RECORDED`).
`B3WorkflowView` thêm `funding:B3FundingSummary` và `advance_events`. Projection
`b3_funding.project_b3_funding` chỉ cộng RECEIVED xác nhận đúng employee,
payer COMPANY; giữ gross (không clip), OVERPAY/WRONG_RECIPIENT/
UNAUTHORIZED_OR_UNALLOCATED/CONFLICTING_OUTCOME thành incident; pending/unknown
làm `remaining_vnd` null (giữ subtotal đã biết); event sau `money_as_of` ghi
`after_money_cutoff`. Một giao dịch kinh tế (namespace+ref) không đếm hai lần;
final outcome supersede nonfinal cùng identity. Stage: FULFILLED →
`AWAITING_WORK_SETTLEMENT`, NEEDS_RESOLUTION → `RESOLVING_OBLIGATIONS`, còn lại
→ `AWAITING_MONEY`; **Stop không tự tiến stage** (fact vẫn lưu). B7
`_money_summary` lọc kind trước sum/pending nên advance không thành
reimbursement. Error codes dùng lại `BASIS_MISMATCH`/`BEYOND_AUTHORITY`/
`INVALID_PAYLOAD`.

**Gate evidence cho RECEIVED** (plan
[2026-10-12-advance-receipt-methods](../superpowers/plans/2026-10-12-advance-receipt-methods.md)):
một RECEIVED chỉ thành `CONFIRMED_RECEIPT` khi
`advance_reconciliation.validate_advance_receipt` thấy **mọi** field bắt buộc
(9 core + `receiver_name`) đọc từ **một** nguồn `B3_ADVANCE_PROOF` của đúng hồ sơ,
`origin=HUMAN_SOURCE_REVIEW`, `read_state=READ`, locator/raw nonblank, value khớp
payload, **và** nguồn chi thuộc `B3CompanyContext.effective_receipt_sources()`
đúng method (**bank** `proof_scope=RECEIVER_CONFIRMED`; **cash**
`acknowledgement=ACKNOWLEDGED` và `voucher_number=event_ref`). Guard trả
`evidence_issues`; thiếu căn cứ → `UNCONFIRMED` (giữ raw + issues, **không** cộng
fulfillment). `derive_classification` nhận `evidence_ok` tường minh, **không**
default True. `receipt_details`/`evidence_issues` lưu trong money JSON; view cũ
thiếu field vẫn parse (default None/[]).

**Nguồn chi demo mặc định**: công ty demo có đúng một tài khoản ngân hàng và một
quỹ tiền mặt, khai một lần ở `contracts/b3_contracts.py::DEMO_RECEIPT_SOURCES`
(namespace giữ nguyên `BANK:L01-COMPANY`/`CASH:L01-QUY-CHINH` để không phá liên
kết giao dịch; nhãn chung “Tài khoản ngân hàng công ty”/“Quỹ tiền mặt công ty”).
`B3CompanyContext.effective_receipt_sources()` trả config khai báo nếu có, **ngược
lại** hai nguồn mặc định — nên context demo hợp lệ không khai báo `receipt_sources`
vẫn có đủ hai nguồn, không cần file cấu hình riêng cho L01. Hàm này chỉ **suy ra
lúc đọc**, **không** ghi vào model → **không** đổi context signature/quyết định cũ.
UI (`GET /api/demo-context`) nhận `receipt_sources` read-only và tự gắn nguồn theo
phương thức; backend vẫn kiểm tra đúng phương thức (không dựa vào UI).

**Đọc biên nhận thành bản nháp** (plan
[2026-10-12-receipt-draft-reading](../superpowers/plans/2026-10-12-receipt-draft-reading.md)):
`POST /api/cases/{id}/b3-advance-receipt-reads` (ACCOUNTANT, `Idempotency-Key`)
nhận `source_id` + `method`, đọc **chỉ** grammar `receipt.*` (prompt
`settlement-receipt-extract.txt`) qua reader hiện có, rồi
`receipt_reading.build_receipt_draft` dựng `B3ReceiptReadView` (facts có
source/locator/quote; proposal; warnings) và lưu vào bảng `receipt_reads`
(append-only). Đây là **bước riêng**: **không** tạo money event, **không** đổi
stage/decision/`input_revision` (chỉ `case_version`). `GET .../b3-advance-receipt-reads`
liệt kê draft cũ→mới. Đọc lỗi → draft `FAILED` giữ file + `error`; kế toán nhập
tay. AI/reader chỉ trích xuất + đề xuất (`payee_ref`/`classification_hint`); tên
giống không tự chứng minh cùng người (`RECEIVER_NOT_MATCHED`); "lập lệnh/trích
nợ" không thành `RECEIVER_CONFIRMED`; cash chưa giao không thành đã nhận. Xác nhận
vẫn qua `record_b3_advance` (guard cũ).

**B6→B7 quyết toán liên kết** (plan
[2026-10-11-b6-linked-settlement](../superpowers/plans/2026-10-11-b6-linked-settlement.md))
tạo **hồ sơ B7 riêng** cùng employee/work (không đổi job B3) qua
`POST /api/cases/{b3_id}/settlements` (envelope version của **parent**; link/
employee/work do backend cấp trong `form.origin_link`, server-appended) và lưu
khai báo qua `PUT /api/cases/{b7_id}/settlement-submission` (schema
`b7-linked-intake-v1`; claim rows là **declarations**, không phải payment facts;
`Service.submit`/`revise` generic từ chối spoof schema/link). Company context:
`POST .../settlement-company-context` (ACCOUNTANT; `B7CompanyPacket` source-backed
coverage/events/expenses) và `POST .../settlement-context/refresh`; snapshot lưu
như system source audit `B7_CONTEXT_REFRESH` (source-use `LINKED_B7_CONTEXT`),
tăng `input_revision` khi đổi. `LinkedB7ContextSnapshot` build bằng Python từ
typed parent decision/events + packet (không LLM đọc lại số): history a/ra/p/rp
KNOWN chỉ khi coverage đủ group; `None` không thành 0. Run linked dùng **B7 rights
riêng** (`ServiceConfig.b7_context` grants; thiếu = AUTHORITY, không fallback
P-DEMO), nạp context observations/relations qua `process(..., linked_snapshot=)`.
`RelationKind` thêm `CLAIM_EXPENSE`; `Report.claim_comparisons` so khai↔chi phí
thực tế (MATCHED/CONFLICT/UNRESOLVED; mismatch không dùng forecast). Guards:
`LINKED_B7_REPORT_ONLY` chặn generic decision/money/handoff/closure (review vẫn
được); `linked_b7_dependency_fingerprint` cho publish/review stale; parent Stop →
child context `context_current=False`; `delete_case` parent có child →
`LINKED_CASE_EXISTS`.

**B8 duyệt quyết toán** (plan
[2026-10-11-b8-settlement-decision](../superpowers/plans/2026-10-11-b8-settlement-decision.md))
thêm hai endpoint chuyên biệt cho hồ sơ `b7-linked-intake-v1`, **không** mở generic
W05: `POST /api/cases/{id}/settlement-presentations` (kế toán trình: `B7PresentPayload`
basis_report_id + đúng một review_id/review; lưu audit `B7_PRESENT` + presentation;
stage `AWAITING_DECISION`) và `POST /api/cases/{id}/settlement-decisions`
(`B7DecisionPayload` presentation_id/outcome APPROVE|RETURN|REFUSE/reason; audit
`B7_DECIDE`; decisions JSON kind `B7_SETTLEMENT`). `CaseView.b7_workflow`
(`B7WorkflowView`) là projection derive từ records/basis. Target quyết toán
(`B7DecisionTarget` E/T/B/signed_net/direction/amount) do **Python** dựng
(`b7_workflow.settlement_target`) chỉ khi current COMPLETE report, không material
issue, claim không CONFLICT/UNRESOLVED, đủ required routine checks và component
KNOWN/int; `amount=abs(net)`, direction theo dấu (BALANCED=0). Quyền:
`authorize_b7_decision` dùng **một** B7 grant scoped (B7CompanyConfig riêng, không
kế thừa B3Grant/P-DEMO) cover cả E và abs(S) tại `effective_b7_time`; RETURN/REFUSE
chỉ cần grant scoped hiệu lực. Stage: APPROVE nonzero → `AWAITING_MONEY`; BALANCED
→ `READY_TO_CLOSE`; RETURN → `CHECKING`; REFUSE → `SETTLEMENT_REQUEST_REFUSED`
(không đóng). Presentation/decision bind business/parent/config/authority
signatures; đổi context/version/Stop → `BASIS_STALE`/`B7_WORKFLOW_BLOCKED`;
same-key replay trước version; `B7_ALREADY_DECIDED` cho presentation đã quyết.
Generic money/handoff/closure vẫn `LINKED_B7_REPORT_ONLY`; `B7_SETTLEMENT` không
vào B7 `_money_summary`. **Chưa** có B9 chi/thu, handoff/closure, override ngoại lệ
hoặc tạo B7 tự động.

**B9 chi/thu và đóng quyết toán** (plan
[2026-10-11-b9-settlement-fulfillment](../superpowers/plans/2026-10-11-b9-settlement-fulfillment.md),
IMPLEMENTED fake/replay; chưa nghiệm thu UI/LIVE) tiếp tục hai lớp tiền tách biệt:
whole-work S từ canonical history (có coverage/refs/as-of) và **decision
fulfillment** (`B7FulfillmentSummary` approved/recorded/fulfilled/remaining, do
`b7_fulfillment.project_b7_fulfillment` tính). Kế toán ghi sự kiện tiền thực tế
(`B7MoneyEventPayload`, kind `B7_SETTLEMENT_EVENT` trong `money_events`, employee/
work/classification do server suy từ `classify_b7_money`) cùng chứng từ
`B7_SETTLEMENT_PROOF` (audit-backed, bump case_version không input_revision). Số
thực nhận **không clip**: overpay giữ gross + incident `OVERPAY`; wrong
recipient/payer, purpose UNKNOWN, source unresolved giữ raw + incident; pending/
unknown → remaining null; một economic identity (namespace:ref) không đếm hai lần;
pending→final supersede đúng thứ tự; receipt→return là event mới. Bốn endpoint
chuyên biệt: `POST .../settlement-money-proofs` (multipart),
`.../settlement-money-events` (typed), `.../settlement-money-context/refresh`
(server clock, fold canonical B9 events vào packet events theo identity — không
auto mở rộng external coverage), `.../settlement-revalidations`
(`revalidate_b7_decision`: E/T/B không đổi và history delta = đúng qualifying
receipts → `VALID`, giữ decision gốc, không tạo approval mới). Handoff
(`B7HandoffView`, audit `B7_HANDOFF`) chỉ là tham chiếu phần remaining>0, đúng
direction, không BALANCED, không entity payment-request. Closure
(`B7ClosureView`, audit `B7_CLOSE`) chỉ khi mọi gate trong một transaction:
decision APPROVE hiện hành, revalidation `VALID`, fulfillment FULFILLED/BALANCED
không remaining/pending/unknown/incident, report hiện hành COMPLETE S=0, scope/
coverage hiện hành, không Stop parent/child, không câu hỏi mở; `S0`/refusal một
mình không đủ. Sau đóng, `POST .../settlement-adjustments` mở child B7 mới cùng
employee/work/B3 với `B7OriginLink.adjustment_of_case_id`; closure cũ bất biến,
một active settlement trong scope. `B7OriginLink` thêm `adjustment_of_case_id`
(nullable, server-owned). `B7WorkflowView` thêm `fulfillment/revalidation/
current_handoff/closure`. Generic money/handoff/closure **vẫn**
`LINKED_B7_REPORT_ONLY`; `B7_SETTLEMENT_EVENT` không vào B7 `_money_summary`.

## S11. Quy ước đặt tên và tổ chức code

Tên module/symbol theo nghiệp vụ, không theo mã nội bộ: dùng `B3/B5/B7/B8/B9`,
`E/A/RA/P/RP/T/B/S`, `EMPLOYEE/ACCOUNTANT/APPROVER`. Mã nội bộ chỉ xuất hiện ở
**persisted code** (operation string, `schema_version`, DB column, API path, JSON
field) và docstring — không dùng làm tên file/class/biến mới.

- **Contract**: tách theo vùng nghiệp vụ trong `settlement/contracts/`
  (`base`, `b3_contracts`, `advance`, `run`, `report`, `settlement`, `case`,
  `fingerprint`);
  `settlement/models.py` là façade re-export + `model_rebuild`, giữ nguyên
  `from invoice_referee.settlement.models import ...` cho caller cũ. Không đổi
  tên class/field/thứ tự field khi tách (thứ tự field là input của fingerprint).
- **Hậu tố**: `*View` (đọc/chiếu ra UI), `*Payload` (client gửi lên), `*Summary`
  (tổng hợp), `*Record` (bản ghi persisted), `*Result` (kết quả tính toán).
  Boolean đặt tiền tố `is_/can_/has_` (`is_b3_v1`, `has_request`).
- **Hàm dài nhiều bước**: tách theo *bước nghiệp vụ* thành hàm module-level
  (validate → group → resolve → check → route → build), truyền phụ thuộc tường
  minh; giữ nguyên thứ tự append và mọi chuỗi trong report.
- **Tránh lồng nhau**: package chỉ để nhóm theo nghiệp vụ; không thêm tầng
  `core/`/`utils/` trung gian khi không có consumer cụ thể.

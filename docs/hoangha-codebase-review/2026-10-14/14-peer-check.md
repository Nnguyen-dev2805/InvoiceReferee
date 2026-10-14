# 14 — Peer-check độc lập các report 03/04/05/06 với `final` hiện tại

Ngày kiểm: 14/10/2026. Vai trò: peer-check độc lập, không implementation.

## 1. Phạm vi và chuẩn bằng chứng

Peer-check này chỉ đối chiếu các claim có khả năng ảnh hưởng việc ghép Hoangha vào `final`:

- `03-llm-contracts.md` — semantic AI promotion và OCR boundary.
- `04-settlement-matching-policy.md` — exact matcher, pair-specific cleanup, trạng thái/output evidence pipeline.
- `05-storage-lifecycle.md` — STOP/job lifecycle proof.
- `06-fastapi-frontend.md` — actor/public mutation và money input boundary; F4 được sửa trực tiếp trong report 06 theo disposition dưới đây.
- `ARCHITECTURE_AND_EVALUATION.md` §14–15 hiện tại và `IMPLEMENTATION_CONTRACTS.md` §12, cùng các contract money/state có liên quan trực tiếp.

Source quan trọng được kiểm graph-first trên worktree Hoangha revision `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`; phần graph bị cắt được đọc raw đúng range. Không chạy test, build, generator, worker, HTTP route hay LIVE provider. Vì vậy mọi kết luận bên dưới phân biệt rõ **source-confirmed** với **runtime NOT_RUN**.

## 2. Kết luận disposition

| Claim | Peer verdict | Căn cứ accepted hiện tại | Source/runtime status | Hành động cho parent |
| --- | --- | --- | --- | --- |
| 03 F03-1: LLM có thể promote suggestion sai semantic chỉ bằng candidate + confidence | **KEEP AS ACCEPTED-RISK, CORRECT DISPOSITION** | §15/§12.4 đã chốt port core: model chỉ promote pair có sẵn ở `>=0.90`; contract hiện không thêm deterministic “amount + second signal” validator | Source-confirmed ở `process_settlement.py:857-872`; runtime **NOT_RUN** | Không chặn implementation đúng contract. Chỉ hỏi user nếu muốn harden và thay semantics accepted/gold |
| 03 bảng file nói reconciliation “phải thêm deterministic relation validator” | **CORRECT** | Mâu thuẫn với chính §15/§12.4 đã accepted | Editorial/report inconsistency; không phải runtime bug | Đọc câu này như proposal tùy chọn, không như requirement implementation |
| 03 OCR boundary ghi `PDF/JPG/JPEG` | **CORRECT INPUT LIST** | User đã chốt `PDF/JPG/JPEG/PNG`, mọi file/page đều OCR, kể cả PDF có text layer; native parse không được accepted | Không cần runtime proof | Khi port, gồm PNG; không native-text bypass/fallback |
| 04 exact normalized invoice ref → `AUTO_LINK/1.0` | **KEEP EXACTLY** | §15.2 và §12.4 chốt đúng semantics này, đồng thời thừa nhận risk mã trùng | Source-confirmed `paper_evidence_matching.py:153-168`; runtime **NOT_RUN** | Không đổi weight/threshold. Expose method/provenance và pin golden/metric |
| 04 F-06 promotion xóa FAIL theo document thay vì pair | **KEEP, MEDIUM integration correctness** | Không đổi scorer; typed final link đã keyed `(item_id, source_id, document_id)` và resolver chỉ promote existing pair | Source-confirmed `process_settlement.py:857-914`; runtime **NOT_RUN** | Adapter phải replace/unresolve đúng pair; không cần user policy decision |
| 04 nói LIVE/RECORDED_REPLAY kết thúc ở `WAITING` | **CORRECT — STALE** | §15.1 và §12.5 chốt `EVIDENCE_READY`, `conclusion=None`, no instruction, `assessment_ready=false` | Contract-confirmed; runtime final chưa có proof | Parent không mang claim `WAITING` sang implementation/review gate |
| 04 input adapter nói final `PDF/JPG/JPEG/PNG` | **KEEP** | Khớp user latest instruction và §15.1; §15.2 hiện thiếu chữ PNG là editorial inconsistency trong design | Không phải runtime issue | Chuẩn hóa docs sau; không cần hỏi user vì intent đã được user resolve |
| 05 A: STOP không cancel/guard job | **KEEP, HIGH as legacy lifecycle risk; NOT a runtime reproduction** | Final §6 yêu cầu atomic `control_epoch++`, prevent new commits, suspend pending, handed-off → execution unknown | Source-confirmed; STOP runtime **NOT_RUN**; scoped test search không thấy STOP test | Không port Hoangha lifecycle. Nếu tham khảo code, coi đây là do-not-port blocker |
| 05 B/C/D/E lifecycle gaps | **KEEP FACTS, DOWNGRADE integration relevance** | §15 đã chốt `final` giữ workflow/DB/audit; không port repository/lifecycle Hoangha | Source-level claims; runtime **NOT_RUN** | Dùng làm risk reference, không biến thành blockers của evidence-pipeline task |
| 06 F1 role/actor boundary | **KEEP as direct-port blocker** | Final authority phải do server/backend enforce; demo persona/client role không tự cấp quyền | Source-confirmed route/service wiring; runtime exploit **NOT_RUN** | Không merge route authority nguyên trạng; nếu chỉ dùng UI/reference thì không phải defect của final |
| 06 F2 permanent delete | **KEEP behavior, classify DO-NOT-PORT** | Không thuộc canonical final lifecycle; §15 giữ final DB/audit/workflow | Source-confirmed intentional demo behavior | Block direct merge của endpoint; không gọi đây là bug của accepted final nếu endpoint bị loại |
| 06 F3 `/internal/process-next` public mutation | **KEEP as reachable source risk, DO-NOT-PORT** | `run_job`/worker là internal; public route không phải authority seam | Source call path confirmed; provider call/exploit **NOT_RUN** | Loại khỏi public surface; không claim LIVE incident |
| 06 F4 raw `allocated_advance_amount` | **KEEP, REFRAME** | Q32 cho responsible employee confirmation đối với bounded employee-paid `E`; `A/P/R` vẫn cần completed transfer/cash receipt/ledger hoặc financial confirmation đúng scope | Source-confirmed raw field lacks actor/scope/refs/history/coverage/limit metadata | Report 06 đã sửa: issue là promotion raw `A`, không phải cấm mọi employee confirmation |

## 3. AI promotion: risk có thật, nhưng current contract đã disposition

### 3.1. Hoangha thực sự làm gì

`_resolve_suggested_paper_links()` chỉ tạo candidate từ các link đang `SUGGEST_LINK`. Candidate key là `(item_id, document_id)`. Khi model trả `accepted_links`, code chỉ kiểm ba điều:

1. pair đó có trong candidate set;
2. `confidence >= 0.90`;
3. document chưa nằm trong `auto_document_ids`.

Sau đó code đổi link thành `AUTO_LINK`, method `LLM_RECONCILIATION`, score thành model confidence (`process_settlement.py:857-872`). Không có code check lại `line_amount == document_total` hoặc “second signal” ở bước promotion.

Đây là **source-confirmed semantic risk** mà report 03 mô tả đúng. Tuy nhiên report 03 hiện có hai wording không còn cùng một disposition:

- `03:29` nói phải thêm deterministic validator trước khi relation được accepted;
- `03:249` lại thừa nhận §15 đã chốt port core promotion hiện tại và cần lead chọn nếu muốn harden.

Sau khi đối chiếu `final` hiện tại, câu thứ hai là authority đúng hơn. `ARCHITECTURE_AND_EVALUATION.md:552-555` và `IMPLEMENTATION_CONTRACTS.md:597-602` đã chốt matcher core và promotion `>=0.90`. Vì vậy **baseline implementation không còn một decision gate mở ở F03-1**.

Nếu parent muốn thêm predicate “amount equality + second deterministic signal”, đó là **thay accepted semantics** và phải hỏi user/update contract+gold trước khi implement. Nếu parent chỉ port đúng §15/§12.4 thì không cần hỏi lại.

### 3.2. Model quyết định gì, code quyết định gì

- Model chỉ chọn trong existing suggestions và trả confidence/rationale.
- Code quyết định candidate set, ngưỡng `0.90`, uniqueness theo document, và chuyển trạng thái sang `AUTO_LINK`.
- Exact reference `1.0` hoàn toàn do deterministic matcher quyết định; không phải model decision.
- Human/user chỉ cần tham gia nếu muốn **đổi** semantics accepted hoặc xử lý unresolved business case ở stage sau; peer-check không tự thay policy.

## 4. Exact invoice matcher `1.0`: giữ nguyên, chỉ expose risk

`match_paper_evidence()` normalize invoice refs và document number. Nếu exact match, source đặt trực tiếp:

```text
score = 1.0
method = INVOICE_NUMBER_EXACT
```

Source: `paper_evidence_matching.py:153-168`.

Report 04 xử lý điểm này đúng: đây không phải finding phải “fix score”. Final đã chốt exact ref → `AUTO_LINK/1.0` và biết risk issuer/content có thể khác (`ARCHITECTURE_AND_EVALUATION.md:552-555`; `IMPLEMENTATION_CONTRACTS.md:597-600`).

Disposition: **không sửa accepted weight/threshold**. Việc cần làm khi port là giữ `method`, refs/provenance và golden/metric để score `1.0` không bị diễn giải thành “semantic correctness tuyệt đối”.

## 5. F-06 pair-specific cleanup: bug source hợp lệ, không đụng core scorer

Promotion được keyed đúng pair ở `process_settlement.py:857-872`. Nhưng cleanup sau đó tạo `promoted_document_ids` và xóa mọi `SET_PAPER_MATCH_001 FAIL` có `DOC:{document_id}` thuộc tập đó (`:877-901`). Nó không kiểm `item_id` của finding bị xóa.

Trigger source hợp lệ:

- cùng `DOC-X` là suggestion cho `ITEM-001` và `ITEM-002`;
- model chỉ promote `(ITEM-001, DOC-X)`;
- cleanup theo document id có thể xóa FAIL dùng để giữ ambiguity của `ITEM-002`.

Đây là **finding source-confirmed, runtime NOT_RUN**. Severity `Medium` của report 04 là hợp lý: nó chủ yếu làm mất question/routing pair-specific; source đọc chưa chứng minh false financial approval tự động.

Fix trong adapter final phải giữ pair identity. Việc này tương thích §12.4 và không thay exact `1.0`, weight, threshold hay promotion cutoff, nên **không cần user policy decision**.

## 6. OCR/input/state: hai correction biên tập phải được parent áp dụng

### 6.1. Không native parse

Accepted direction là OCR **mọi trang của mọi accepted source**, kể cả PDF có text layer. Native text presence không tạo bypass/fallback. Report 03 đã đúng về boundary này; chỉ thiếu `PNG` trong một số wording.

Input effective cho peer-check này theo instruction mới nhất của user là:

```text
PDF / JPG / JPEG / PNG
      ↓
OCR mọi trang
      ↓
confidence → classify → extract → validate → match
```

`ARCHITECTURE_AND_EVALUATION.md:525-526` có `PDF/PNG/JPEG`; `:538` lại ghi `PDF/JPG/JPEG`. Đây là inconsistency biên tập trong design. User đã resolve trực tiếp là `PDF/JPG/JPEG/PNG all OCR`, nên **không còn decision cần hỏi**; chỉ cần chuẩn hóa tài liệu/implementation theo tập bốn loại này.

### 6.2. Evidence pipeline kết thúc ở `EVIDENCE_READY`

Report 04 dòng 452 còn nói LIVE/RECORDED_REPLAY expose `WAITING`. Claim này stale.

Authority hiện tại:

- Design §15.1: `EVIDENCE_READY`, `assessment_ready=false`, `assessment_blocker=EVIDENCE_ADMISSION_NOT_CONNECTED`, `conclusion=None`.
- Contracts §12.5: evidence report xong → `EVIDENCE_READY`; `WAITING` dành cho business issue/execution unknown; không tạo question card ở boundary này.

Disposition: parent phải dùng `EVIDENCE_READY`, không dùng `WAITING` từ report 04.

## 7. STOP proof: source đủ chứng minh gap, chưa đủ để claim runtime race đã xảy ra

### 7.1. Những gì source chứng minh được

`ReviewSettlementService.record_action()` xử lý `STOP_PROCESSING` bằng:

- `decision = None`;
- `workflow_status = "STOPPED"`;
- gọi `record_human_action(...)` (`review_settlement.py:88-100`).

Repository `record_human_action()` ghi human action/audit và update `settlement_cases.workflow_status`; source không cancel/suspend `processing_jobs` (`sqlite_settlement_repository.py:691-797`).

`claim_next_job()` chỉ chọn:

```sql
FROM processing_jobs
WHERE status = 'PENDING'
```

không join/check `workflow_status` (`:528-559`). Vì vậy source chứng minh pending job của case đã STOP vẫn **eligible to be claimed**.

`complete_job()` replace findings, append decision, set `processing_status='COMPLETED'`, complete job và audit (`:572-660`) mà không check `workflow_status`/control epoch trước commit. Vì vậy source cũng chứng minh đường late completion **không có guard STOP**.

### 7.2. Những gì chưa được chứng minh runtime

Review không chạy worker/concurrency test. Scoped source search trong `tests/` không tìm thấy `STOP_PROCESSING`, `STOPPED` hay equivalent STOP lifecycle test. Vì vậy report 05 không được nâng thành claim kiểu “đã reproduce race/late write”. Wording đúng là:

> Source cho thấy STOP không cancel pending job, không interrupt running job và không guard late completion; runtime concurrent execution chưa được chạy.

### 7.3. So với final contract

Final §6 chốt mạnh hơn Hoangha:

- `control_epoch` tăng khi STOP/RESUME;
- STOP atomic epoch++;
- chặn new commits;
- suspend pending;
- handed-off execution chuyển unknown cho tới khi kiểm lại (`IMPLEMENTATION_CONTRACTS.md:159-178`).

Do §15 đã chốt **không port repository/database/settlement lifecycle Hoangha**, finding A của report 05 là **HIGH do-not-port/reference risk**, không phải bug phải sửa trong evidence-pipeline task. B/C/D/E cũng là source-valid lifecycle gaps nhưng không nên biến thành blocker của task §15 nếu lifecycle cũ không được import.

## 8. F4 report 06: correction sau Q32 ACCEPTED

Report 06 trước peer-check mô tả `allocated_advance_amount` như self-declared money fact và có thể bị đọc thành “employee confirmation không bao giờ admissible”. Cách nói đó quá rộng sau §14/Q32.

Contract hiện tại phân biệt hai lớp:

- **Employee-paid `E` candidate:** có thể dùng responsible employee confirmation + service evidence trong `E<=8tr`, `abs(S)<=4tr`, các điều kiện khác đủ và không material conflict (`IMPLEMENTATION_CONTRACTS.md:49-50,86-89`).
- **`A/P/R/received`:** cần confirmed completed transfer/cash receipt/ledger có payer/payee/scope; requested/approved/pending không đủ (`:52`).

Source Hoangha `SettlementDraft.allocated_advance_amount` chỉ là `Decimal >= 0` (`domain/settlement.py:198`), browser gửi trực tiếp từ input, và search scoped cho thấy nó đi vào policy/summary/storage mà không mang `Confirmation(actor, scope, refs, observed_at)` hoặc ledger/history coverage.

Vì vậy F4 đúng sau khi reframe thành:

> **Raw `allocated_advance_amount` thiếu responsible basis/history/limits và không được promote thẳng thành `A`.**

Tôi đã sửa `06-fastapi-frontend.md` theo đúng boundary này. Không sửa Q32, không hạ quyền responsible employee confirmation cho bounded `E`.

## 9. Severity của các finding frontend/lifecycle khi ghép `final`

Một số report dùng từ `BLOCKER` theo nghĩa “block direct port/merge”. Parent cần giữ qualifier này để tránh hiểu thành “accepted final hiện có bug production”.

### Direct-port blockers hợp lý

- 06 F1: route/accounting action thiếu server actor/role/ownership boundary.
- 06 F2: permanent delete từ public accounting surface.
- 06 F3: public `/internal/process-next` có reachable processor/provider path.
- 06 F4: raw advance field nếu được dùng thẳng làm `A`.

Chúng block **copy/merge nguyên surface Hoangha**. Nếu final chỉ lấy view-model/UX seam và giữ canonical workflow/authority riêng, F2/F3 đặc biệt nên được ghi là `DO NOT PORT`, không dùng như bằng chứng final runtime đang hỏng.

Report 06 F3 đã giữ đúng giới hạn: call path source-confirmed, LIVE exploit/provider invocation **NOT_RUN**.

### Lifecycle findings 05

- A STOP gap: HIGH reference risk vì đụng control semantics.
- B RUNNING recovery, C multi-active-job, D DB/filesystem atomicity, E migration bookkeeping: source-valid nhưng là concern của lifecycle/repository cũ. Với §15 hiện tại, chúng là **reuse exclusion/risk reference**, không phải gate bắt task evidence phải sửa Hoangha storage.

## 10. Issues còn phải hỏi user trước implementation

Hiện chỉ còn **một loại thay đổi** cần hỏi user nếu parent muốn làm:

### Thay semantics LLM promotion ngoài §15/§12.4

Nếu muốn thêm deterministic predicate bắt buộc như:

- amount phải match trong tolerance;
- phải có second signal deterministic;
- hoặc thay cutoff/weight/promotion behavior;

thì đó là thay accepted matching semantics. Cần user/lead approve rồi cập nhật contract/gold trước implementation.

Nếu implementation **giữ nguyên** exact matcher `1.0`, weights `0.60/0.30/0.12|0.20/0.10`, thresholds `0.50/0.75`, và existing suggestion promotion `>=0.90`, thì **không cần hỏi lại**.

Các điểm sau không còn là user-decision:

- `PDF/JPG/JPEG/PNG` đều OCR, kể cả PDF text layer; không native parse bypass.
- evidence stage kết thúc `EVIDENCE_READY`, không `WAITING`.
- F-06 cleanup phải pair-specific trong adapter.
- Hoangha lifecycle/DB không được port vào §15.
- Q32 bounded responsible confirmation cho `E` giữ nguyên; raw `allocated_advance_amount` không tự thành `A`.

## 11. Handoff ngắn cho parent

1. Dùng report 03 như nguồn **risk description**, nhưng bỏ trạng thái “F03-1 bắt buộc disposition trước implementation” đối với baseline accepted; chỉ mở decision nếu muốn harden semantics.
2. Giữ report 04 exact matcher `1.0` nguyên trạng; sửa claim state `WAITING → EVIDENCE_READY`; giữ F-06 medium pair-specific bug.
3. Giữ report 05 STOP finding với nhãn **source-confirmed / runtime NOT_RUN / do-not-port lifecycle**; không claim reproduced race.
4. Dùng report 06 bản đã sửa F4; actor/delete/process-next vẫn là direct-port blockers, không phải bằng chứng final canonical workflow đã có các lỗi đó.
5. Khi tổng hợp input policy, dùng `PDF/JPG/JPEG/PNG`, tất cả qua OCR, không native parse.

## 12. Limits

- Không chạy tests/runtime/LIVE theo chỉ thị.
- Không review lại toàn bộ inventory/full-file groups; dùng report published + graph/source hẹp cho claim tranh chấp.
- CodeGraph exploration có source current-on-disk và call paths; coverage/generation MCP chính thức không exposed trong context được giao, nên không claim graph completeness.
- `ARCHITECTURE_AND_EVALUATION.md` §15.1/§15.2 hiện có inconsistency biên tập về PNG; latest user instruction đã resolve intended accepted set, nên report không mở lại policy decision này.

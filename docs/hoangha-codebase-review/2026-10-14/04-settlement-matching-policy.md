# Review độc lập — 04 Settlement / Matching / Policy

Ngày review: 14/10/2026
Nguồn Hoangha: `.worktrees/hoangha` @ `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`
Đích so sánh: nhánh `final` của InvoiceReferee
Nhóm inventory: `04-settlement-matching-policy`
Chế độ: **READ-ONLY source review**; không chạy test/build/generator, không gọi LIVE provider, không sửa source/status/plan.

## 1. Kết luận review

Nhóm code này có **hai phần rất đáng tái sử dụng** cho `final`:

1. ma trận profile/field importance và các helper validation có tính deterministic trong `policy/document_validity.py`;
2. core deterministic matcher trong `application/paper_evidence_matching.py`, gồm normalize invoice reference, amount/content/party scoring, ngưỡng suggestion/auto-link và cơ chế không tự dùng một document cho hai dòng.

Nhưng **không nên port nguyên `SettlementProcessingService`, `evaluate_settlement_policy` hoặc settlement lifecycle của Hoangha**. Hoangha hiện gắn OCR/extraction/matching trực tiếp với policy, quyết toán tiền, trạng thái approval và repository riêng. Trong giai đoạn evidence integration hiện tại, contract `final` đã chốt ranh giới khác: pipeline mới dừng ở evidence report, chưa tạo `Fact.KNOWN`, chưa vào Reconciler/policy/tiền, và LIVE/RECORDED_REPLAY phải ở trạng thái chưa sẵn sàng đánh giá tài chính (`assessment_ready=false`, state `EVIDENCE_READY`). Xem `docs/final/ARCHITECTURE_AND_EVALUATION.md:524-531,562-567` và `docs/final/IMPLEMENTATION_CONTRACTS.md:601-622`.

Về đề A của cuộc thi, matcher và cách tạo câu hỏi cụ thể khi thiếu/không chắc evidence đi đúng tinh thần “Escalation Referee”. Tuy nhiên source Hoangha còn vài đường có thể **chuyển tiếp không cần thiết** hoặc **phân loại lỗi kỹ thuật thành việc cho con người**, nên không thể dùng riêng code này để claim đáp ứng đề A. Đề A yêu cầu routine phải tự xử lý, không over-escalate và câu hỏi chuyển tiếp phải đúng người/đúng vấn đề (`docs/Challenge_Brief_OrganizationAI_VN.docx.md:47-59,69-83`).

Tổng cộng tôi xác minh từ source **6 finding hành vi cụ thể**. Ngoài ra có **4 ranh giới tích hợp/shortcut không nên gọi là bug** vì hoặc đã được thiết kế Hoangha cố ý, hoặc `final` đã chấp nhận trade-off đó.

## 2. Phạm vi và mức bằng chứng

Inventory giao đúng **6 file, 2.445 dòng**. Tôi đã đọc toàn bộ từng file từ dòng đầu đến dòng cuối; checksum của cả 6 file khớp inventory và checkout đúng commit được giao.

| File | Dòng | Trạng thái trong Hoangha | Trạng thái khi nhìn từ `final` | Vai trò | Input → output | Hàm chính / caller / callee | Hành vi lỗi | Khả năng dùng lại |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `src/invoice_referee/application/__init__.py` | 18 | Facade đang dùng | Tooling/facade | Re-export application services | module import → public symbols | caller: runtime/importers; callee: `process_case`, `process_settlement`, matcher, review/submit | lỗi import-time nếu module phụ thuộc lỗi | Thấp; chỉ giữ ý tưởng facade nếu cần |
| `src/invoice_referee/application/paper_evidence_matching.py` | 434 | **Wired** ở PAPER path | Core được chọn để port | Pure deterministic matching + row projection cũ | `PaperSettlementFacts` + document facts/metadata → `items, links, findings` | caller: `_finish_paper_case`; callee: normalize/category/semantic/party helpers | lỗi dữ liệu shape/key không bắt tại đây; outer worker có thể fail job | **Cao cho matching core**, trung bình/thấp cho row projection cũ |
| `src/invoice_referee/application/process_settlement.py` | 1.008 | **Wired** worker chính | Legacy lifecycle đối với `final`; chỉ tham khảo stage order | Claim job → source gate → OCR quality → extraction/validity → PAPER/FORM branch → policy/decision/persist | repository job/canonical/documents → artifacts/findings/decision/state | caller: FastAPI background worker; callees: OCR, reasoning, validity, matcher, policy, repository | external service exception → failed job; nhiều config/extraction lỗi lại thành business finding | Thấp khi port nguyên; cao như tài liệu hành vi/edge cases |
| `src/invoice_referee/policy/__init__.py` | 20 | Facade đang dùng | Tooling/facade | Re-export validity/inventory/settlement policy | module import → public symbols | caller: processor; callees: validity/inventory/settlement | lỗi import-time | Thấp |
| `src/invoice_referee/policy/document_validity.py` | 627 | **Wired** khi document pipeline bật | Profile matrix được `final` pin làm nguồn | Document profile, field importance, role map, validity | extracted facts → `DocumentValidityResult` | caller: `SettlementProcessingService`; callee: local deterministic helpers | không I/O; issue list thay vì raise cho dữ liệu nghiệp vụ | **Cao cho tables/helpers**, cần đổi semantics validity theo contract final |
| `src/invoice_referee/policy/settlement.py` | 338 | **Wired** source gate + final policy Hoangha | **Không port policy** | Demo settlement rules/caps/authority/deadline/evidence exception | `SettlementDraft` → `list[SettlementFinding]` | caller: processor; callee: pure helpers | không I/O; mọi vi phạm thành finding | Thấp; chỉ tham khảo pattern pure-function |

Graph được dùng trước source discovery theo quy định. Parent cung cấp trạng thái CodeGraph `81 files / 1204 nodes / 3561 edges`, up-to-date; trong phiên reviewer này `generation id` và `check_index_coverage` không được expose, nên **coverage = UNKNOWN**. Tôi dùng graph để tìm caller/callee/test rồi fallback sang đọc full source cho toàn bộ 6 file inventory. Không thay đổi index.

<!-- reviewed-file: src/invoice_referee/application/__init__.py -->
<!-- reviewed-file: src/invoice_referee/application/paper_evidence_matching.py -->
<!-- reviewed-file: src/invoice_referee/application/process_settlement.py -->
<!-- reviewed-file: src/invoice_referee/policy/__init__.py -->
<!-- reviewed-file: src/invoice_referee/policy/document_validity.py -->
<!-- reviewed-file: src/invoice_referee/policy/settlement.py -->

## 3. Trạng thái wired thực tế

Đây không phải một bộ helper rời rạc. Trong worktree Hoangha, `SettlementProcessingService` **được wire thật** vào FastAPI composition root. `app/web/runtime.py:28-71` tạo `SQLiteSettlementRepository`, `SettlementPolicyConfig`, optional `MistralOcrAdapter`, `KimiReasoningAdapter`, rồi inject tất cả vào processor; biến `UC03_DOCUMENT_PIPELINE_ENABLED` mặc định là `"1"` (`app/web/runtime.py:37-40`). `app/fastapi_app.py:31-45` tạo background loop và gọi `runtime.processor.run_once()` qua `asyncio.to_thread`.

Điều đó có nghĩa các finding bên dưới là finding của **đường runtime Hoangha có thể chạy**, không chỉ dead code. Tuy vậy, đối với kiến trúc `final`, toàn bộ repository/lifecycle này là legacy source để khai thác ý tưởng; canonical plan đã ghi rõ không transplant database, settlement lifecycle hay Kimi provider (`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md:5-7,16-18`).

## 4. Luồng xử lý theo điều kiện thật

### 4.1. Worker entry và source gate

`run_once()` claim job đầu tiên có status `PENDING`, chuyển job sang `RUNNING` và case sang `PROCESSING` qua repository (`process_settlement.py:146-153`; caller implementation ở `sqlite_settlement_repository.py:528-559`). Sau đó processor load canonical `SettlementDraft` và document metadata (`process_settlement.py:153-160`).

Trước OCR, code gọi `evaluate_settlement_policy()` một lần và chỉ giữ bốn rule source gate: `SET_CONTEXT_001`, `SET_INPUT_001`, `SET_ADV_001`, `SET_DOC_001` (`process_settlement.py:162-173`). Nếu một source-gate finding FAIL, case được finish ngay, không OCR.

Đây là khác biệt quan trọng với pipeline `final`: Hoangha cho **business policy chạy trước evidence read**; `final` E1–E8 đang thiết kế evidence pipeline độc lập và dừng trước Reconciler/policy.

### 4.2. Khi document pipeline bật

`_process_documents()` chạy theo hai pha lớn (`process_settlement.py:240-533`):

1. **OCR + quality cho tất cả document** (`279-415`). Mỗi file được OCR, lưu raw JSON, restructure blocks, thu low-confidence candidates. Nếu có candidate, reasoning model đánh giá confidence; nếu không có candidate, code hiện ghi PASS `SET_QUALITY_001` (`398-409`).
2. Nếu **bất kỳ finding nào FAIL**, function trả ngay `findings, [], None`, tức là không extraction bất kỳ file nào (`437-440`). Chỉ khi toàn bộ quality gate không FAIL mới extraction từng document (`442-533`).

Mỗi document sau extraction được validate. Request form dùng `validate_paper_settlement_document`; evidence dùng `validate_expense_document` (`453-484`). Facts và validity artifacts được persist trước khi facts đủ điều kiện được đưa sang matching (`486-512`).

Điểm này hữu ích về mặt fail-closed, nhưng barrier “một file fail → không extract tất cả file còn lại” là quá thô cho `final`: plan mới yêu cầu giữ OCR/analysis phần đọc được, đánh dấu unit còn lại unresolved/technical, không silently drop (`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md:21,32`). Vì vậy nên port **stage semantics**, không port barrier nguyên xi.

### 4.3. Nhánh PAPER_SCAN

Nếu `draft.source_type == PAPER_SCAN`, worker gọi `_finish_paper_case()` (`process_settlement.py:194-205`). Luồng thực tế:

1. chạy policy base (`547-554`);
2. yêu cầu phải có `paper_facts.lines` (`555-573`);
3. gọi `match_paper_evidence()` (`575-585`);
4. nếu có suggestion, có thể gọi LLM resolver (`586-592`, `794-915`);
5. kiểm warning/tổng dòng/tổng form (`593-652`);
6. với advance settlement, lấy `advance_amount` đọc từ form và tự tính chênh lệch (`657-729`);
7. persist paper items + links + beneficiary/bank data (`730-745`);
8. normalize các row thành `ExpenseItemDraft`, chạy settlement policy lại (`751-764`);
9. nếu không có FAIL, thêm `SET_APPROVAL_001/PENDING_APPROVAL` (`765-791`);
10. build deterministic decision và complete job (`792`, `_finish:226-238`).

Như vậy PAPER path của Hoangha **không dừng ở matching**. Nó đã đi sang policy, tính chênh lệch tiền và approval. Đây là phần phải cắt khi tích hợp sang `final`.

### 4.4. Nhánh DIGITAL_FORM

Nếu không phải `PAPER_SCAN`, worker chạy lại `evaluate_settlement_policy()`, append quality/validity findings, rồi nếu document pipeline bật thì chạy `_reconciliation_findings()` (`process_settlement.py:206-221`).

`_reconciliation_findings()` không dùng matcher theo invoice ref. Nó dựa vào `settlement_documents.linked_item_id`, lấy toàn bộ facts đã gắn item và cộng `total_amount` của tất cả chúng (`918-1002`). Chính điểm này tạo finding F-01 bên dưới.

### 4.5. State/error thật

Có hai đường lỗi khác nhau:

- exception bất ngờ hoặc `ExternalServiceUnavailableError` thoát ra `run_once()` → `repository.fail_job()` → job `FAILED`, case `PROCESSING_ERROR`, audit `PROCESSING_FAILED` (`process_settlement.py:222-223`; repository `662-689`);
- thiếu adapter/config hoặc nhiều lỗi extraction/quality được convert thành `SettlementFinding(status="FAIL")` → `_finish()` → job/case **COMPLETED** với một automation decision (`process_settlement.py:253-277,418-435`; repository `572-660`).

Sự phân đôi này là nguồn của F-04.

## 5. Matcher: cơ chế chính xác

Matcher là pure function ở `paper_evidence_matching.py:110-434`.

### 5.1. Normalize và feature

- Invoice/document reference được uppercase và bỏ toàn bộ ký tự ngoài `[A-Z0-9]` (`67-68`). Ví dụ minh họa: `"HD-001/26"` và `"HD00126"` trở thành cùng identifier.
- Vietnamese text được bỏ dấu, lowercase và collapse ký tự không phải chữ/số (`71-74`).
- Party similarity là tỷ lệ giao token giữa mô tả dòng và issuer, sau khi bỏ token generic như `cong`, `ty`, `tnhh`, `doanh`, `nghiep` (`22-38,77-93`).
- Semantic similarity dùng `difflib.SequenceMatcher` giữa mô tả paper row và chuỗi `issuer_name + line_item descriptions` (`96-107`). Đây là string similarity, không phải embedding semantic model.

### 5.2. Điểm và ngưỡng

Nếu normalized invoice number của document nằm trong `paper.lines[].invoice_refs`, code gán thẳng:

```text
score = 1.0
method = INVOICE_NUMBER_EXACT
```

(`paper_evidence_matching.py:153-171`).

Nếu không exact:

```text
score = 0.60 nếu amount lệch <= 1 VND
      + semantic_similarity * 0.30
      + 0.20 nếu party_similarity >= 0.80
        hoặc 0.12 nếu party_similarity >= 0.50
      + 0.10 nếu document không thuộc ORIGINAL_EXPENSE_DOCUMENT_TYPES
score tối đa 1.00
```

(`172-180`). Sau đó:

- `< 0.50`: bỏ candidate;
- `[0.50, 0.75)`: `SUGGEST_LINK`;
- `>= 0.75`: `AUTO_LINK` (`195-197`).

Nếu document đã auto-link vào một paper row trước đó, auto-link ở row sau bị hạ thành suggestion (`198-203`). Đây là safeguard tốt và test source có kiểm.

### 5.3. Ví dụ DTO minh họa — exact match

Đây là **minh họa suy ra trực tiếp từ source, không phải runtime capture**:

```json
{
  "paper_line": {
    "description": "Taxi sân bay",
    "invoice_refs": ["HD-001/26"],
    "amount": "450000"
  },
  "document": {
    "document_id": "DOC-01",
    "document_type": "E_INVOICE",
    "document_number": "HD00126",
    "issuer_name": "Công ty Taxi A",
    "total_amount": "700000"
  }
}
```

Mặc dù amount minh họa cố ý không khớp, normalized invoice reference vẫn cho:

```json
{
  "item_id": "ITEM-001",
  "document_id": "DOC-01",
  "link_status": "AUTO_LINK",
  "link_method": "INVOICE_NUMBER_EXACT",
  "score": 1.0
}
```

Đây **không phải bug mới cần sửa trong task tích hợp**: canonical design `final` đã chấp nhận chính trade-off này và ghi rủi ro “mã trùng auto-link dù issuer/nội dung khác” (`ARCHITECTURE_AND_EVALUATION.md:549-552`; plan `Review Focus` dòng 43). Phải giữ hành vi core để benchmark/port đúng, đồng thời expose method/facts để downstream không hiểu `1.0` là chứng minh semantic correctness.

### 5.4. Ví dụ suggestion

Nếu chỉ amount khớp và semantic/party bằng 0, score là `0.60`, nên candidate là `SUGGEST_LINK`. LLM chỉ được thấy candidate đã tồn tại; trong Hoangha `_resolve_suggested_paper_links()` chỉ promote khi model trả đúng `(item_id, document_id)`, confidence `>=0.90`, và document chưa auto-linked (`process_settlement.py:857-872`).

Đây là đúng hướng “model đề xuất trong vùng xám, code giữ candidate set và threshold”. `final` nên giữ invariant này nhưng đổi provider/DTO/method literal theo contract.

## 6. Validity: cái gì code cho phép đi vào matching

### 6.1. Profile matrix có giá trị tái sử dụng

`document_validity.py:32-81` định nghĩa importance cho các field trọng yếu theo type; `116-230` định nghĩa required fields và `any_of_fields` cho 14 loại tài liệu. `document_role_for_type()` tách original/support/unknown (`268-273`). Đây là phần `final` đã pin làm nguồn cho E0/E1.

Ví dụ:

- `E_INVOICE`: issuer/buyer identity, invoice number/template/serial/date/total/line items;
- `PAYMENT_PROOF`: payee, date, total, transaction reference, transaction status;
- `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, acceptance/delivery/goods receipt… có profile riêng.

### 6.2. Nhưng semantics blocking của Hoangha không được port nguyên

`_missing_issue()` đặt `blocking=document_type is None` (`document_validity.py:307-332`). Hệ quả: missing required field trên **expense document** mặc định không blocking, kể cả field importance là `CRITICAL`.

Điều này được test source xác nhận chứ không phải suy đoán:

- `test_electronic_invoice_missing_buyer_tax_code_is_retained_for_accountant_routing`: validity vẫn `CLEAR`, `eligible_for_matching=True`, rồi application layer mới convert critical E-INVOICE issue thành FAIL (`tests/unit/test_document_validity.py:57-64`);
- `test_payment_proof_requires_reference_payee_and_success_status`: thiếu payee/reference/status nhưng validity vẫn `CLEAR` (`139-153`).

Với E-INVOICE, `_validity_findings()` có một lớp vá ở `process_settlement.py:75-105`: critical missing identity bị biến thành FAIL, nên fact không được append cho matching. Nhưng logic này không tổng quát cho mọi document type.

Đối với `final`, đây là **integration contract mismatch**, không nên gọi đơn giản là bug Hoangha: code cũ cố ý cho phép “corroborate later”. Contract mới đã chốt `FOUND/NOT_PRESENT/UNREADABLE/AMBIGUOUS/NOT_APPLICABLE`, `FOUND` cần source quote/locator và critical uncertainty phải unresolved. Vì vậy nên port **profile tables**, viết lại validity semantics theo DTO mới.

## 7. Model quyết định gì, code quyết định gì, con người quyết định gì

### Model trong Hoangha

Model hiện có quyền đề xuất/đọc:

- confidence assessment cho OCR candidate;
- `ExpenseDocumentFacts` hoặc `PaperSettlementFacts` từ OCR text;
- document type nằm trong extracted facts hiện tại;
- accepted suggestion pairs trong evidence reconciliation.

`KimiReasoningAdapter` parse structured output và cho tối đa một repair attempt trước khi ném `KimiResponseError`; confidence stage còn kiểm đủ đúng một assessment cho mỗi candidate. Đây là safeguard tốt ở transport/model boundary.

Tuy nhiên Hoangha hiện gộp classification vào extraction output; `final` đã chốt **classification và extraction là hai stage riêng**, `UNKNOWN` không được chọn schema đoán (`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md:20,72-74`).

### Code quyết định

Code, không phải model, quyết định:

- ngưỡng OCR candidate;
- mapping type → role;
- required field profile;
- normalized exact invoice reference;
- matcher score/threshold;
- document reuse demotion;
- policy caps/category/deadline/authority trong Hoangha;
- priority finding → automation decision;
- state transition job/case.

Đây là điểm mạnh: core matching có thể audit được.

### Con người trong Hoangha

Tùy finding, câu hỏi được route tới employee/accountant/chief accountant/director. Paper path còn thêm `SET_APPROVAL_001/PENDING_APPROVAL` nếu không FAIL (`process_settlement.py:765-791`). Test `test_clear_paper_form_is_ready_for_accounting_approval` còn assert trực tiếp finding này (`tests/unit/test_sqlite_settlement_repository.py:605-649`).

Đối với `final` và đề A, không nên port bước approval mặc định này. Thiết kế `final` yêu cầu routine đủ căn cứ có thể tự kết luận trong quyền, không thêm một human approval chỉ để đóng hồ sơ (`ARCHITECTURE_AND_EVALUATION.md:138-150`). Human chỉ xuất hiện khi có FACT/POLICY/AUTHORITY hoặc thực hiện tiền ngoài app.

## 8. Findings đã xác minh từ source

### F-01 — DIGITAL_FORM có thể double-count invoice + payment proof và tạo escalation sai

**Mức:** High đối với Hoangha FORM path; tránh port sang `final`.

**Trigger**

Một digital expense item có hai document cùng `linked_item_id`: một original invoice 1.200.000 VND và một `PAYMENT_PROOF` 1.200.000 VND chứng minh thanh toán cho chính invoice đó.

**Hành vi source**

`_reconciliation_findings()` lấy **mọi** `item_documents`, lấy tất cả facts, rồi cộng toàn bộ `total_amount` (`process_settlement.py:931-971`). Không có role/original-support filter ở nhánh này. Nếu item claim 1.200.000, code tính `document_total=2.400.000` và tạo `SET_TOTAL_001 FAIL` (`972-989`).

Trong khi đó PAPER matcher đã có xử lý đúng hơn: khi có original + payment proof, amount reconciliation bỏ `PAYMENT_PROOF` khỏi tổng (`paper_evidence_matching.py:372-387`). Test `test_payment_proof_supports_invoice_without_double_counting_amount` bảo vệ đúng hành vi PAPER (`tests/unit/test_paper_evidence_matching.py:182-216`).

**Wrong behavior**

Routine hợp lệ có thể bị `REQUEST_INFO` chỉ vì payment proof hỗ trợ bị cộng như một expense amount thứ hai. Đây là over-escalation trực tiếp, ngược mục tiêu đề A.

**Bằng chứng test hiện có**

Không thấy test tương ứng cho DIGITAL_FORM + original invoice + payment proof trong các test được discover/read. `test_document_pipeline_extracts_and_reconciles_total` chỉ dùng một document (`test_sqlite_settlement_repository.py:503-543`).

**Khuyến nghị tích hợp**

Không port `_reconciliation_findings()`. Dùng role-aware `DocumentRowMatch`: supporting/payment evidence không đóng góp `original_total`; final plan đã chốt điều này (`2026-10-13-hoangha-evidence-pipeline.md:90`).

### F-02 — PAPER warning đã được đánh non-blocking lại bị biến thành FAIL ở bước sau

**Mức:** High cho over-escalation/question quality.

**Trigger**

Paper form có `extraction_warnings` dạng không trọng yếu, ví dụ “mô tả hàng hóa có lỗi chính tả”. `_warning_is_blocking()` cố ý nhận diện typo/tên hàng/tên dịch vụ là non-blocking (`document_validity.py:232-239,345-367`).

**Hành vi source**

`validate_paper_settlement_document()` tạo `PAPER_FORM_DATA_WARNING` với `blocking=False`; nếu không có issue blocking khác thì status vẫn `CLEAR` (`585-620`). `_validity_findings()` khi đó chỉ tạo `WARN`, không FAIL (`process_settlement.py:84-108`).

Nhưng sau matching, `_finish_paper_case()` loop **mọi** `paper_facts.extraction_warnings` và luôn append `SET_PAPER_CONSISTENCY_001 status="FAIL"` (`process_settlement.py:593-607`) mà không dùng lại kết quả `blocking` đã tính.

**Wrong behavior**

Cùng một warning có thể được tầng validity xác định “không cần chặn”, rồi tầng paper completion lại ép thành business escalation. Đây là inconsistency source-level, không cần suy đoán model.

**Test gap**

Worker test hiện có chỉ dùng warning rõ ràng blocking: `"Số tiền bằng chữ không khớp tổng cộng."` (`test_sqlite_settlement_repository.py:546-601`). Không có end-to-end test cho non-blocking paper warning. Test non-blocking typo hiện chỉ áp dụng expense document (`test_document_validity.py:176-195`).

**Khuyến nghị tích hợp**

Trong `final`, `DocumentProfileIssue.blocking`/typed status phải là nguồn duy nhất cho việc unresolved; không đọc lại raw warning string để đổi severity ở stage sau.

### F-03 — Validity `CLEAR/eligible_for_matching` không đồng nghĩa required critical fields đã đủ

**Mức:** Medium; **source-verified shortcut**, là integration blocker chứ không nên gọi là accidental bug.

**Trigger**

Expense evidence thiếu required field, kể cả field được đánh `CRITICAL`.

**Hành vi source**

`_missing_issue()` đặt `blocking=False` cho mọi expense document (`document_validity.py:307-332`). Status cuối chỉ nhìn `blocking_issues`; không có blocking issue thì `CLEAR`, `eligible_for_matching=True` (`520-546`).

E-INVOICE được application layer special-case lại thành FAIL cho critical missing identity (`process_settlement.py:75-105`), nhưng `PAYMENT_PROOF` không có safeguard tương đương. Test source chủ động assert payment proof thiếu payee/reference/status vẫn `CLEAR` (`test_document_validity.py:139-153`).

**Rủi ro**

Nếu port function nguyên xi sang evidence-only pipeline, downstream có thể hiểu sai `CLEAR` là “đủ dữ kiện typed/provenance”, trong khi contract `final` yêu cầu critical missing/ambiguous phải unresolved.

**Khuyến nghị**

Port `DOCUMENT_PROFILES` + `FIELD_IMPORTANCE_BY_TYPE`, không port `_missing_issue`/status semantics nguyên bản. `final` cần validity dựa trên `FieldState`, quote ownership và criticality matrix.

### F-04 — Thiếu provider/config bị ghi thành case COMPLETED + human finding thay vì technical failure

**Mức:** Medium-High cho đề A/evaluation.

**Trigger**

`UC03_DOCUMENT_PIPELINE_ENABLED=1` nhưng thiếu `MISTRAL_API_KEY` hoặc thiếu Kimi credential. Runtime vẫn tạo processor với adapter tương ứng bằng `None` (`app/web/runtime.py:37-68`).

**Hành vi source**

- OCR adapter `None` → `SET_QUALITY_001 FAIL`, target accountant (`process_settlement.py:253-263`).
- reasoning adapter `None` → `SET_EXTRACTION_001 FAIL`, target accountant (`264-277`).
- `run_once()` nhìn FAIL và gọi `_finish()`, nên repository ghi case/job `COMPLETED` cùng automation decision (`184-190,226-238`; repository `572-660`).

Trong khi actual `ExternalServiceUnavailableError` được re-raise (`416-417,513-514`) và outer handler gọi `fail_job()` → `PROCESSING_ERROR` (`222-223`; repository `662-689`).

**Wrong behavior**

Cùng bản chất “pipeline không thể chạy vì hạ tầng/provider”, một số case bị biến thành câu hỏi cho accountant và tính như business escalation. Điều này có thể làm sai denominator/miss-vs-unnecessary-escalation khi đánh giá đề A.

**Khuyến nghị**

`final` đã có `ProcessingProblem(kind=TECHNICAL/...)`; missing provider/config phải ở technical state, không tạo `BusinessIssue` FACT/POLICY/AUTHORITY.

### F-05 — Paper row persisted có thể tự mâu thuẫn với matching finding

**Mức:** Medium; data-contract inconsistency.

**Trigger A: không có auto-link, không có no-evidence reason.**

`match_paper_evidence()` tạo item `evidence_status` theo ternary ở `paper_evidence_matching.py:255-263`. Nếu không có original auto-link, không có alternative auto-link và cũng không có `reason`, nhánh cuối trả **`ORIGINAL_EVIDENCE`** mặc dù ngay sau đó matcher tạo `SET_PAPER_EVIDENCE_REQUIRED FAIL` (`303-357`).

**Trigger B: line amount không đọc được.**

`claimed_amount` được tạo bằng `line.amount or Decimal("0")` (`253`). Đồng thời matcher tạo `SET_PAPER_LINE_AMOUNT_001 FAIL` khi `line.amount is None` (`281-298`). Nghĩa là unknown amount vừa được biểu diễn thành 0 trong row DTO, vừa bị ghi finding là unknown.

**Persisted effect**

`_finish_paper_case()` gọi `replace_paper_items()` trước khi final decision (`process_settlement.py:730-745`). Repository ghi `claimed_amount` và `evidence_status` đúng các giá trị đó vào `expense_items` (`sqlite_settlement_repository.py:1038-1062`).

Decision thường vẫn bị chặn bởi matching finding, nên đây không phải bằng chứng false financial approval. Nhưng persisted case view có thể chứa **giá trị affirmative sai nghĩa** song song với FAIL.

**Khuyến nghị**

Đây chính là projection mà plan final đã sửa: missing amount giữ `None`; row chỉ `ORIGINAL_EVIDENCE` khi có auto-linked original; support-only là alternative; còn lại no evidence/unresolved (`2026-10-13-hoangha-evidence-pipeline.md:90`). Không port row projection cũ.

### F-06 — LLM promotion xóa match FAIL theo document, không theo cặp item-document

**Mức:** Medium; chủ yếu làm sai question/routing trong multi-row ambiguity.

**Trigger**

Cùng một document là `SUGGEST_LINK` cho nhiều paper rows. LLM chỉ accept/promote một cặp `(ITEM-001, DOC-X)`.

**Hành vi source**

Promotion đúng là keyed theo `(item_id, document_id)` ở `process_settlement.py:857-872`. Nhưng sau đó code tạo `promoted_document_ids`, rồi remove mọi `SET_PAPER_MATCH_001 FAIL` nếu `source_refs` chứa **document_id đã được promote**, không kiểm item_id (`877-901`).

Vì vậy FAIL của row khác có cùng suggested document cũng bị xóa. Row khác chưa được promote vẫn có thể bị policy layer bắt lại vì `evidence_names=[]`, nhưng câu hỏi chuyển từ “hãy xác nhận evidence thuộc khoản nào” sang generic missing-document/request path. Đây là mất thông tin pair-specific, ảnh hưởng chất lượng escalation.

**Test gap**

Không tìm thấy test gọi `analyze_evidence_reconciliation` trong `tests/`; `rtk rg -n analyze_evidence_reconciliation tests` trả no matches. Test multi-row hiện chỉ kiểm deterministic demotion trước LLM (`test_paper_evidence_matching.py:219-251`).

**Khuyến nghị**

Trong adapter final, resolver result và finding phải keyed theo `EvidenceLink(item_id, document_id, ...)`; chỉ replace finding của đúng pair được promote.

## 9. Những điều không nên gọi là bug

### 9.1. Exact invoice reference → 1.0 auto-link

Đây là **known trade-off đã được chấp nhận** trong canonical design, không phải finding sửa ngoài scope. Source lines `paper_evidence_matching.py:153-171`; final design `ARCHITECTURE_AND_EVALUATION.md:549-552`.

Điều cần làm là giữ method/provenance để downstream biết `score=1.0` có nghĩa “exact normalized identifier match”, không phải “mọi thuộc tính semantic đều đúng”.

### 9.2. Supporting/non-original được cộng +0.10

Đây là weight cố định của matcher (`paper_evidence_matching.py:178-180`) và final đã pin nguyên core score. Không tự đổi weight trong integration task. `final` xử lý rủi ro bằng role-aware projection: support không trở thành original evidence và không double-count amount.

### 9.3. Policy demo Hoangha khác policy final

`SettlementPolicyConfig` Hoangha dùng 30 ngày, authority 100 triệu, meal 5 triệu, taxi 2 triệu (`settlement.py:21-38`). Đây không phải “bug vì khác final”; nó là policy của một app/phiên bản khác. Nhưng **tuyệt đối không port** vì final đã chốt rulebook/authority khác và tài liệu integration cũng cấm import Hoangha policy/caps/authority (`2026-10-13-hoangha-evidence-pipeline.md:33,116`).

### 9.4. Paper advance/reimbursement arithmetic là legacy scope, không phải evidence core

Hoangha lấy `advance_amount` từ paper form, không kiểm lịch sử giải ngân, rồi dùng `abs(advance - claimed_total)` để đối chiếu số quyết toán in trên form (`process_settlement.py:657-729`; policy còn ghi rõ “MVP không đối chiếu khoản tạm ứng gốc” ở `settlement.py:93-119`).

Đây là shortcut sản phẩm cũ. Với `final`, nó **không hợp contract tiền** vì A/P/R phải dựa trên giao dịch/lịch sử/xác nhận có trách nhiệm; paper assertion không tự thành actual money (`ARCHITECTURE_AND_EVALUATION.md:103-119`). Vì vậy boundary đúng là dừng trước finance, không “sửa công thức” trong matcher task.

## 10. Các adapter/boundary cần có khi mang sang `final`

### A. Domain adapter: Hoangha facts → final typed candidates

Không dùng thẳng `ExpenseDocumentFacts`/`PaperSettlementFacts` làm known facts. Cần map extracted values vào `FieldCandidate` với state + source quote/locator. Missing phải là `NOT_PRESENT/UNREADABLE/AMBIGUOUS`, không `None` rồi ngầm hiểu zero.

### B. Classification split

Hoangha extraction trả luôn `document_type`; final phải có `DocumentClassification` riêng, validate page/block ownership, rồi mới chọn schema extraction. `UNKNOWN` dừng, không đoán schema.

### C. Role adapter

Giữ original/support distinction từ Hoangha, nhưng final cần `DocumentEvidenceRole` riêng. `PAYMENT_PROOF`/`CARD_SLIP` mặc định chỉ supporting; chỉ thêm `PAYMENT_EVIDENCE` khi payer+payee+amount+transaction identity/status có refs riêng. Không suy payer từ buyer/signature/payment wording.

### D. Matcher adapter

Port core scoring/normalize/demotion gần như nguyên trạng nhưng đổi output thành typed `EvidenceMatchingResult`/`EvidenceLink`/`DocumentRowMatch`.

Cần các deliberate differences đã chốt:

- missing amount giữ `None`;
- suggestion-only không được ghi `ORIGINAL_EVIDENCE`;
- support amount không vào `original_total`;
- không port `policy_exception_code`, `OUTSIDE_POLICY`, owner routing;
- one-document-many-row chỉ khi có explicit normalized `invoice_refs` + per-row amount, tổng allocation <= source amount;
- resolver method literal theo final là `LLM_RESOLVED`, trong khi Hoangha hiện dùng `LLM_RECONCILIATION` (`process_settlement.py:867-870`).

### E. Provider adapter

Không port `KimiReasoningAdapter`. Final đã chốt dùng `XkiroClient`. Có thể tái dùng invariant “structured output → validate → tối đa một repair” nhưng mọi call phải đi qua budget/trace contract final.

### F. State/error adapter

Evidence pipeline result phải phân biệt:

- business unresolved evidence;
- technical/provider/config failure;
- limit/unsupported.

Không convert missing model/OCR config thành accountant question. LIVE/RECORDED_REPLAY sau evidence processing chỉ expose report, `EVIDENCE_READY`, `conclusion=None`, no instruction cho tới plan admission kế tiếp.

### G. Input-type adapter

Hoangha `OCR_SUFFIXES` nhận cả `.webp` (`process_settlement.py:51`). Final accepted scope chỉ PDF/JPG/JPEG/PNG. Không mang `.webp` sang chỉ vì source cũ hỗ trợ.

## 11. Test source chứng minh được gì

Tôi **không chạy test** theo yêu cầu. Các nhận định dưới đây là từ việc đọc test source, không phải runtime pass claim.

### Đã có test source tương đối tốt cho

- exact invoice refs ghép nhiều evidence và kiểm tổng (`test_paper_evidence_matching.py:36-66`);
- thiếu evidence / no-evidence reason / case-level reason nhiều dòng (`69-164`);
- missing paper amount (`167-179`);
- invoice + payment proof không double-count ở **PAPER matcher** (`182-216`);
- một document không auto-link hai paper rows (`219-251`);
- amount + normalized vendor name có thể auto-link (`272-312`);
- document profile/role matrix và warning blocking/nonblocking (`test_document_validity.py:45-315`);
- quality chạy trước extraction và critical low-confidence stop extraction (`test_sqlite_settlement_repository.py:722-839`);
- external service failure đi vào processing error (`431-455`);
- clear paper case có `PENDING_APPROVAL` (`605-649`).

### Chưa thấy test source chứng minh

1. DIGITAL_FORM invoice + payment proof không double-count — F-01 hiện không được cover.
2. Non-blocking warning trên **paper request** vẫn non-blocking end-to-end — F-02 không được cover.
3. LLM suggestion promotion cho multi-row/multi-candidate, pair-specific finding replacement — F-06 không được cover.
4. Exact invoice reference nhưng issuer/content/amount xung đột — đây là risk được chấp nhận, cần golden test để pin hành vi chứ không phải test “sửa”.
5. Explicit allocation một invoice cho nhiều rows với tổng allocation bound — Hoangha core chưa có contract final này.
6. Final field-state + exact quote/page/block provenance validation.
7. Missing provider/config được phân loại technical thay vì human/business — Hoangha hiện đi đường F-04.
8. False-positive/false-negative rate thực tế của threshold `0.50/0.75/0.90`, SequenceMatcher và party overlap trên corpus độc lập.

## 12. Các giả thuyết chưa test — không nâng thành finding

Các điểm sau chỉ là **giả thuyết/rủi ro cần benchmark**, không phải bug đã xác minh:

- `SequenceMatcher` có thể cho similarity cao cho mô tả dài nhưng chung chung; chưa có benchmark false-link trên corpus mới.
- normalized invoice reference bỏ toàn bộ dấu phân cách có thể làm tăng collision; frequency thực tế chưa đo.
- threshold `>=0.90` do LLM tự báo confidence chưa chứng minh calibration hoặc precision; source chỉ enforce threshold.
- stable ordering của candidate khi score bằng nhau phụ thuộc thứ tự input facts; source deterministic với cùng input order, nhưng chưa thấy test permutation invariance.
- latency/cost của OCR + confidence + extraction + suggestion resolution không được xác minh trong review này vì LIVE/test đều bị cấm.

## 13. Đánh giá từng file

### `src/invoice_referee/application/__init__.py` — 18 dòng

Facade thuần, re-export processor/matcher/services (`1-18`). Không có nghiệp vụ. Có thể bỏ qua khi port; consumer final nên import từ evidence modules mới thay vì kéo theo settlement application package cũ.

### `src/invoice_referee/application/paper_evidence_matching.py` — 434 dòng

Đây là file giá trị nhất trong group. Core normalize/similarity/scoring rõ, pure sync, dễ test, explanation có thể audit. Phần cần tách là **candidate scoring** khỏi **Hoangha row projection/policy finding**. `final` nên giữ scorer nhưng chuyển output sang evidence-only DTO.

Ngoài F-05, file còn infer category bằng keyword (`41-64`). Với final, category chỉ nên là `category_candidate` mô tả; không được đi thẳng vào policy eligibility. Plan final đã chốt đúng ranh giới này.

### `src/invoice_referee/application/process_settlement.py` — 1.008 dòng

Đây là orchestration monolith của Hoangha: worker/state, source gate, OCR, confidence, extraction, validity, matcher, LLM reconciliation, settlement policy, finance arithmetic, persistence và approval. Nó giải thích behavior runtime rất tốt nhưng là seam xấu để port nguyên sang final.

Các phần đáng học:

- provider errors fail-closed;
- quality trước extraction;
- document_id returned by model phải khớp source (`460-478`);
- persist raw/facts/validity artifacts;
- LLM chỉ promote candidate được deterministic matcher tạo.

Các phần không port nguyên:

- preliminary/final settlement policy;
- global all-document barrier;
- PAPER finance arithmetic;
- `PENDING_APPROVAL` routine;
- repository mutation `replace_paper_items`;
- sync Kimi resolver/provider wiring;
- digital `_reconciliation_findings`.

### `src/invoice_referee/policy/__init__.py` — 20 dòng

Facade thuần. Không có finding nghiệp vụ. Khi final tách `evidence/document_validity.py`, không cần giữ dependency từ evidence sang settlement policy facade.

### `src/invoice_referee/policy/document_validity.py` — 627 dòng

Giá trị lớn nhất là profile matrix, role mapping và deterministic format checks. Nhưng file hiện trộn ba loại concern:

1. extraction/profile validity;
2. company-specific policy (`BUYER_TAX_CODE_MISMATCH`);
3. payment semantic heuristic (`transaction_status` string markers).

Final evidence stage chỉ nên giữ (1) và role compatibility. Company tax membership/policy phải ở adapter kế tiếp, không nhập vào evidence validity. `PAYMENT_EVIDENCE` role cũng cần predicate chặt hơn current `PAYMENT_PROOF` profile.

### `src/invoice_referee/policy/settlement.py` — 338 dòng

Pure deterministic function, code rõ nhưng policy **không phải policy final**. Nó rất hữu ích như ví dụ “LLM không quyết policy”, nhưng không phải source để copy constants/routing. Đặc biệt advance amount, 30-day deadline, category caps, authority 100m, always-review alternative evidence đều thuộc Hoangha demo policy.

## 14. Port recommendation theo ưu tiên

| Thành phần | Quyết định | Lý do |
| --- | --- | --- |
| Identifier/text normalization | **PORT** | Pure, deterministic, matcher contract đã pin |
| Matcher weights/thresholds | **PORT EXACTLY** | Canonical final đã chấp nhận; cần benchmark sau |
| Reuse demotion một document → row thứ hai | **PORT + EXTEND** | Giữ safeguard, thêm explicit allocation contract |
| Profile required fields / importance tables | **PORT DATA** | Canonical final đã pin source này |
| `_missing_issue`/`eligible_for_matching` semantics | **REWRITE** | F-03; final FieldState/provenance contract khác |
| Hoangha row projection | **REWRITE** | F-05; final projection rules đã khác có chủ đích |
| LLM suggestion resolver concept | **PORT CONCEPT, REWRITE ADAPTER** | Dùng Xkiro, async/budgeted, pair-specific result |
| `SettlementProcessingService` nguyên lớp | **DO NOT PORT** | Trộn evidence + policy + finance + DB/lifecycle |
| `_reconciliation_findings` FORM | **DO NOT PORT** | F-01 double-count support/original |
| `SettlementPolicyConfig/evaluate_settlement_policy` | **DO NOT PORT** | Policy final khác, task evidence cấm đổi policy |
| Paper advance/reimbursement computation | **DO NOT PORT** | Không có actual-money/history basis final |
| Routine `PENDING_APPROVAL` | **DO NOT PORT** | Không phù hợp automation boundary đã chốt |
| Kimi provider | **DO NOT PORT** | Final dùng Xkiro |
| Hoangha repository/worker lifecycle | **DO NOT PORT** | Final sở hữu workflow/DB/job/audit |

## 15. Verdict cho mục tiêu kết hợp với `final`

**Verdict: PORT CÓ CHỌN LỌC, KHÔNG MERGE MODULE NGUYÊN KHỐI.**

Core matcher và profile matrix có giá trị thực tế, có source/test rõ và đã được canonical plan `final` chọn làm input. Nhưng `process_settlement.py` chứng minh Hoangha đã đi xa hơn evidence pipeline: nó quyết policy, tính settlement difference, persist normalized finance rows và thêm approval. Mang nguyên lớp này sang `final` sẽ tạo **lifecycle thứ hai và policy thứ hai**, trái thiết kế đã chốt.

Đề xuất kỹ thuật phù hợp nhất với kế hoạch hiện tại:

1. copy/pin matcher core và golden tests trước;
2. port profile/importance tables như **data**, viết validity mới theo final FieldState/provenance;
3. viết typed adapter `DocumentAnalysis → EvidenceMatchingResult` và deliberate projection differences;
4. resolver Xkiro chỉ promote existing suggestion, keyed theo `(item_id, document_id)`;
5. trong giai đoạn evidence integration hiện tại, dừng ở `ReadResult`/evidence report; bước nối admissibility vào workflow tài chính final là giai đoạn tiếp theo;
6. thêm test regression cho F-01, F-02, F-05, F-06 và test technical-state cho F-04 trước khi gọi pipeline “tích hợp xong”.

Với đề A, hướng này giữ được phần mạnh nhất của Hoangha — evidence matching có giải thích và escalation cụ thể — trong khi tránh import các đường dễ over-escalate hoặc làm mờ ranh giới AI/evidence/policy/human decision.

## 16. Limits của review

- Đã đọc đủ **6/6 file owned, 2.445/2.445 dòng**; không có file PARTIAL.
- Caller/callee ngoài scope được đọc chỉ để kiểm chứng wiring/state/test; không claim các file đó thuộc group này.
- CodeGraph được dùng ở Verify-style discovery nhưng `check_index_coverage`/generation không exposed, nên coverage chính thức là **UNKNOWN**; full-source read là nguồn chốt cho 6 owned files.
- Không chạy test, build, generator hay LIVE provider theo chỉ thị. Vì vậy không có claim “tests pass”, latency, model accuracy, provider reliability hoặc benchmark quality trong báo cáo này.
- README/status prose không được dùng làm proof runtime. Canonical `final` design/contracts và source pinned commit là căn cứ cho kết luận integration.
- Các ví dụ input/output trong báo cáo đều được gắn nhãn minh họa/source-derived; không phải dữ liệu thu từ một execution mới.

## Ghi chú biên tập của lead

Lead sửa hai mô tả để khớp scope đã chốt: input final có cả PNG; evidence-only là ranh giới của giai đoạn tích hợp hiện tại, không phải giới hạn mục tiêu toàn bộ sản phẩm kết hợp. Không đổi finding, scorer hay policy.

Peer-check hiện hành: boundary evidence là **EVIDENCE_READY**, không WAITING; exact matcher và LLM promotion >=0.90 giữ accepted semantics. Lifecycle/storage findings là do-not-port/reference risks, không yêu cầu sửa source Hoangha trong task evidence. Xem [14](14-peer-check.md).

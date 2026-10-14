# 03 — LLM contracts: review độc lập nhánh Hoangha

Ngày review: 2026-10-14
Source review: `/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.worktrees/hoangha` @ `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`
Nhóm inventory: `03-llm-contracts`
Phạm vi hoàn tất: **3/3 file, 729/729 dòng**. Không có file PARTIAL.
Phương pháp: CodeGraph Verify để định vị caller/callee, sau đó đọc toàn bộ source của 3 file và đọc source caller/callee cần thiết. `check_index_coverage`/generation id không được exposed trong phiên parent nên **coverage graph = UNKNOWN**; các nhận định trọng yếu dưới đây được khóa lại bằng source.
Runtime validation: **NOT_RUN** theo phạm vi review; không chạy tests/build/generator/LIVE.

## 1. Kết luận cho mục tiêu ghép vào `final`

Nhánh Hoangha có một ý tưởng đúng hướng với đề A: **LLM chỉ làm công việc nhận biết/đối chiếu có phạm vi hẹp, còn code giữ quyền quyết định cuối**. Cụ thể, Kimi được dùng để đánh giá vùng OCR mờ, phân loại và trích xuất chứng từ, trích xuất đơn giấy, phân tích conflict ở luồng Streamlit cũ, và hỗ trợ giải quyết một số liên kết chứng từ mơ hồ. Các output đều đi qua Pydantic schema; confidence stage còn có validator kiểm đủ candidate và một lần repair khi output lỗi schema.

Tuy nhiên không nên mang nguyên khối `KimiReasoningAdapter` + prompt vào `final`. Thiết kế `final` đã chốt reader chỉ tạo observation/proposal, còn backend phải xác minh source/relationship/money/authority/state; model confidence không đủ làm căn cứ quan hệ. Hoangha có một điểm cần disposition trong **LLM evidence reconciliation**: code có thể nâng một `SUGGEST_LINK` thành `AUTO_LINK` chỉ vì model trả cặp candidate hợp lệ và `confidence >= 0.90`, trong khi điều kiện “số tiền khớp + ít nhất một dấu hiệu khác” chỉ nằm trong prompt. **Đây là rủi ro source-confirmed, không phải yêu cầu tự động thay semantics đã được lead chốt ở §15.** Đề xuất thêm deterministic predicate là phương án sau review và phải được lead quyết định trước implementation.

Về trạng thái tích hợp:

- **Wired vào FastAPI settlement path:** confidence quality, expense extraction, paper settlement extraction, evidence reconciliation. `app/web/runtime.py:37-70` tạo `KimiReasoningAdapter` khi document pipeline bật và đủ credential, rồi inject vào `SettlementProcessingService`.
- **Legacy Streamlit/inventory path:** cross-source inventory conflict prompt trong `conflict_reasoning.py`. `app/streamlit_app.py:39-81` tạo `CaseProcessingService`; caller thực tế là `process_case.py:335-433`. Luồng này tập trung bill/report/nhận hàng, trong khi `final` đã loại mua hàng/nhận hàng/tồn kho khỏi bản đầu (`ARCHITECTURE_AND_EVALUATION.md:35-39`). Vì vậy không nên port nguyên conflict contract này vào final core.
- **Tooling/shared adapter:** `_json_objects`, `_parse_analysis`, bounded schema repair và `KimiResponseError` là hạ tầng có thể tái dùng về mặt kỹ thuật, nhưng cần đặt sau interface reader của `final`, thêm budget/trace/read-set theo contracts thay vì để adapter tự trở thành boundary nghiệp vụ.

Đề A yêu cầu routine được tự xử lý, bất định được phân loại và câu hỏi chuyển tiếp phải cụ thể; đặc biệt không được khẳng định dữ liệu đã bị gắn nghi vấn (`Challenge_Brief_OrganizationAI_VN.docx.md:41-59`). Hướng confidence gate của Hoangha phù hợp với tinh thần này, nhưng chỉ khi semantic output của model được code kiểm chứng ở những quan hệ có thể làm đổi kết luận.

## 2. Bảng file đã đọc toàn bộ

| File | Dòng đã đọc | Vai trò | Input → Output | Hàm/constant chính; caller → callee | Hành vi lỗi | Khả năng dùng lại cho `final` |
| --- | ---: | --- | --- | --- | --- | --- |
| `src/invoice_referee/extraction/conflict_reasoning.py` | 130/130 | Prompt contract cho cross-source inventory/receipt conflict | Nhiều document đã qua quality gate + business context → JSON `ConflictAnalysis` | `CONFLICT_SYSTEM_PROMPT`; `CaseProcessingService.process_case` → `KimiReasoningAdapter.analyze_conflict` → `_analyze` | File chỉ là prompt; schema/transport error được adapter xử lý. Semantic coverage được caller/policy kiểm riêng | **Không port nguyên khối.** Có thể tham khảo pattern “model đề xuất comparison, code xác minh”, nhưng domain nhận hàng/kiểm kê là ngoài scope final V1 |
| `src/invoice_referee/extraction/evidence_reconciliation.py` | 27/27 | Prompt cho một call giải quyết candidate link mơ hồ | structured facts + `SUGGEST_LINK` candidates → `accepted_links`, `unresolved_item_ids`, summary | `EVIDENCE_RECONCILIATION_SYSTEM_PROMPT`; `SettlementProcessingService._resolve_suggested_paper_links` → `analyze_evidence_reconciliation` → `_analyze` | Schema lỗi có repair qua adapter; outage/exception ở caller bị giữ nguyên deterministic finding | **Ý tưởng có thể dùng**, giữ candidate membership/cutoff/uniqueness theo accepted contract; thêm deterministic amount/second-signal predicate là đề xuất hardening cần quyết định thay semantics |
| `src/invoice_referee/extraction/kimi_reasoning.py` | 572/572 | Prompt + adapter chung cho confidence, extraction, conflict, reconciliation | Python dict → OpenAI-compatible chat completion → Pydantic model | `_json_objects`, `_parse_analysis`, `KimiResponseError`, `KimiReasoningAdapter._complete/_analyze`, `analyze_confidence`, `analyze_conflict`, `analyze_evidence_reconciliation`, `extract_expense_document`, `extract_paper_settlement` | Service retry do `call_with_service_retry`; parse/validation fail thì một repair; fail lần hai → `KimiResponseError`. Confidence có semantic coverage validator; các stage còn lại chủ yếu schema-only | **Tái dùng có chọn lọc:** parser/repair pattern và prompt extraction là reference tốt. Cần adapter sang `EvidenceReader`/Observation contract, budget/trace, source locator validation và semantic predicates của final |

<!-- reviewed-file: src/invoice_referee/extraction/conflict_reasoning.py -->
<!-- reviewed-file: src/invoice_referee/extraction/evidence_reconciliation.py -->
<!-- reviewed-file: src/invoice_referee/extraction/kimi_reasoning.py -->

## 3. Cơ chế từng file

### 3.1 `conflict_reasoning.py` — prompt cross-source conflict, hiện là legacy inventory path

File này không chứa code thực thi; toàn bộ 130 dòng là một prompt contract. Prompt đặt ranh giới tương đối rõ:

- Chỉ nhận `documents` đã qua quality gate; `business_context` chỉ dùng để hiểu mục đích, không được biến thành nguồn kiểm kê (`conflict_reasoning.py:3-7`).
- Không kiểm confidence OCR, policy thuế, hạn mức/gian lận, và không được quyết định PASS/FAIL/duyệt (`:9-11`).
- Mỗi document phải được extract độc lập đúng một lần; không lấy giá trị của nguồn này điền cho nguồn khác (`:13-18`).
- Model được phép đề xuất mapping và comparison, nhưng status chỉ là proposal; prompt nói code sẽ xác minh lại số liệu (`:19-25`, `:45-47`).
- Prompt khóa nguồn: chỉ document có `evidence_id` là nguồn; text nhân viên không tạo receipt fact/conflict (`:27-32`).
- Prompt quy định output `document_facts`, `suggested_item_matches`, `comparisons`, `potential_conflicts`; source refs phải nằm trong nguồn đầu vào (`:34-60`).

Minh họa input, **không phải dữ liệu runtime đã quan sát**:

```json
{
  "case_id": "CASE-001",
  "business_context": {
    "description": "Nhân viên nói hàng đã nhận đủ.",
    "usage": "CONTEXT_ONLY_NOT_AN_INVENTORY_SOURCE"
  },
  "documents": [
    {"evidence_id": "EV-BILL", "role": "PRIMARY_DOCUMENT", "ocr_text": "..."},
    {"evidence_id": "EV-GR", "role": "SUPPORTING_DOCUMENT", "ocr_text": "..."}
  ]
}
```

Minh họa output:

```json
{
  "applicability": "APPLICABLE",
  "document_facts": [
    {"evidence_id": "EV-BILL", "document_type": "E_INVOICE", "items": []},
    {"evidence_id": "EV-GR", "document_type": "GOODS_RECEIPT", "items": []}
  ],
  "text_report": null,
  "suggested_item_matches": [],
  "comparisons": [],
  "potential_conflicts": []
}
```

Caller thật nằm ở legacy `CaseProcessingService.process_case`: caller dựng payload gồm toàn bộ nguồn đã quality-pass (`process_case.py:335-355`), gọi `analyze_conflict` (`:356-371`), rồi `evaluate_inventory_consistency` mới chuyển proposal thành finding (`:373-383`). Nếu model bỏ document, code phát hiện `INVENTORY_EXTRACTION_COVERAGE_INVALID`, dựng `repair_request`, gọi lại một lần và đánh giá lại (`:384-433`). Đây là boundary tốt: model không trực tiếp ghi decision.

Nhưng về mục tiêu ghép vào `final`, contract này mang domain **receipt/warehouse/inventory** (`conflict_reasoning.py:21-25`, `:27-29`). Final V1 đã chốt “không xây quy trình mua hàng/nhận hàng/tồn kho/thiết bị” (`ARCHITECTURE_AND_EVALUATION.md:35-39`). Vì vậy reuse hợp lý là pattern kỹ thuật, không phải domain prompt.

### 3.2 `evidence_reconciliation.py` — conditional grey-area resolver

Prompt chỉ 27 dòng nhưng nêu một contract quan trọng:

1. Input chỉ gồm structured facts + candidate links; không đọc OCR thô (`evidence_reconciliation.py:3-7`).
2. Chỉ được accept khi **số tiền có căn cứ trực tiếp** và có thêm ít nhất một dấu hiệu khác: số chứng từ, đơn vị hoặc nội dung dịch vụ (`:9-11`).
3. Không được ghép cùng document cho nhiều item (`:11-12`).
4. Output phân tách `accepted_links` và `unresolved_item_ids` (`:14-26`).

Minh họa input:

```json
{
  "workflow": "EVIDENCE_RECONCILIATION",
  "candidate_links": [
    {
      "item_id": "ITEM-001",
      "document_id": "DOC-002",
      "score": 0.68,
      "line_amount": "1000000",
      "document_total": "1000000",
      "document_number": "HD-123"
    }
  ],
  "documents": [
    {
      "document_id": "DOC-002",
      "issuer_name": "Nhà hàng A",
      "total_amount": "1000000",
      "line_items": ["Ăn trưa tiếp khách"]
    }
  ]
}
```

Minh họa output:

```json
{
  "accepted_links": [
    {
      "item_id": "ITEM-001",
      "document_id": "DOC-002",
      "confidence": 0.92,
      "rationale": "Số tiền và nội dung dịch vụ khớp."
    }
  ],
  "unresolved_item_ids": [],
  "summary": "Một liên kết có đủ hai tín hiệu."
}
```

Caller thật là `_resolve_suggested_paper_links` trong FastAPI settlement path. Nó chỉ gọi LLM khi matcher đã tạo `SUGGEST_LINK`; nếu không có candidate hoặc adapter không có method này thì giữ nguyên kết quả deterministic (`process_settlement.py:794-808`). Payload gửi model gồm `item_id`, `document_id`, matcher score/method, line amount, document total/type/number/explanation và structured facts (`:810-842`). Nếu LLM lỗi, code giữ nguyên finding mơ hồ ban đầu thay vì false-pass (`:843-849`). Đây là hành vi fail-safe đáng giữ.

Điểm yếu nằm ở bước promotion: caller chỉ kiểm `accepted` nằm trong candidate set, `confidence >= 0.90`, và document chưa được auto-link; sau đó đổi trạng thái thành `AUTO_LINK` (`process_settlement.py:857-872`). Không có code kiểm lại điều kiện amount equality hay “ít nhất một dấu hiệu khác” mà prompt yêu cầu.

### 3.3 `kimi_reasoning.py` — adapter và bốn contract chính

File này là lõi của nhóm. Có bốn prompt và một adapter chung.

#### A. Confidence quality

`CONFIDENCE_SYSTEM_PROMPT` (`kimi_reasoning.py:34-142`) giới hạn model vào từng evidence và các block có word confidence thấp. Model phải trả đúng một assessment/candidate, map `canonical_fields`, nêu `requires_verification`, không dùng business context/nguồn khác (`:34-62`). Prompt phân biệt `READABLE`, `SEMANTICALLY_READABLE`, `UNCERTAIN`, `UNREADABLE`, `UNKNOWN` (`:64-69`) và cấm dùng `DEFER_TO_POLICY` (`:71-75`).

Điểm mạnh là contract này **không chỉ nằm trong prompt**. `analyze_confidence` lấy toàn bộ `candidate_id` đầu vào, đếm output, và reject khi missing/unexpected/duplicate (`kimi_reasoning.py:484-520`). Nếu fail, `_analyze` đưa lỗi cụ thể vào repair prompt và thử lại một lần (`:440-482`).

Model quyết định: semantic category, canonical field mapping, quality state và nhu cầu xác minh.
Code quyết định: coverage exact-one-per-candidate; sau đó caller `_confidence_findings` mới quyết định block nào thực sự chặn workflow dựa trên blocking field và ký tự số (`process_case.py:484-606`).

#### B. Expense document extraction

`EXPENSE_EXTRACTION_SYSTEM_PROMPT` (`kimi_reasoning.py:145-228`) yêu cầu phân loại theo nội dung nhìn thấy, không dựa filename. Contract liệt kê các canonical document types (`:150-163`), chuẩn hóa amounts/source refs (`:165-167`), classification confidence/signals và field states (`:169-173`), đồng thời giới hạn warning vào ambiguity kế toán trọng yếu (`:175-182`).

FastAPI caller gửi đúng một document với `document_id`, filename, role và OCR text (`process_settlement.py:442-451`), rồi kiểm model trả cùng `document_id` (`:472-479`). Sau đó **code** gọi `validate_expense_document`, lưu facts + validity, và chỉ đưa facts vào matching khi `eligible_for_matching` (`:480-512`). Đây là seam rất phù hợp để chuyển thành `EvidenceReader`: model extract observation; code xác định admissibility.

#### C. Paper settlement extraction

`PAPER_SETTLEMENT_EXTRACTION_SYSTEM_PROMPT` (`kimi_reasoning.py:231-302`) giữ một số boundary tốt:

- Mỗi row trên giấy → một line; bỏ row tổng (`:236-238`).
- `requires_evidence` phản ánh **nội dung trên form**, không phải policy exemption; prompt nói rõ policy engine vẫn yêu cầu evidence/giải trình riêng (`:240-252`).
- `advance_amount` và `reimbursement_amount` chỉ lấy literal value; model không tự tính hay suy chiều dòng tiền, Python tính lại (`:254-260`).
- Bank beneficiary chỉ extract khi có trên form; cấm lấy bank account từ supplier invoice (`:262-266`).

Caller kiểm `document_id`, chạy `validate_paper_settlement_document`, rồi ở `_finish_paper_case` Python tự tính line total, advance difference và direction (`process_settlement.py:608-729`). Đây là đúng ranh giới “model đọc, code tính tiền”.

#### D. Shared JSON parser/repair

`_json_objects` quét response và thu các JSON object hoàn chỉnh, kể cả khi model thêm text (`kimi_reasoning.py:305-325`). `_parse_analysis` trả **object đầu tiên** validate được bằng Pydantic (`:328-344`). `_analyze` gọi model, validate; nếu fail thì gửi lại phần cuối tối đa 16.000 ký tự cùng lỗi schema và thử repair một lần (`:412-482`). Sau hai response không hợp lệ, `KimiResponseError` giữ stage + diagnostics (`:347-363`).

Điểm này hữu ích để chống output format lỗi, nhưng cần phân biệt rõ: **Pydantic-valid không đồng nghĩa nghiệp vụ-valid**. Confidence có custom `result_validator`; conflict có semantic coverage ở caller legacy; extraction có validity layer ở caller; reconciliation hiện thiếu predicate đủ mạnh.

## 4. Luồng theo điều kiện thật

### 4.1 FastAPI settlement path

```text
FastAPI runtime
  -> KimiReasoningAdapter được tạo nếu document pipeline bật và đủ KIMI credentials
  -> SettlementProcessingService.run_once
     -> source gate
     -> OCR từng file
     -> low-confidence candidates?
        -> có: analyze_confidence
        -> code quality gate FAIL? dừng trước extraction
     -> extract từng document
        -> paper form: extract_paper_settlement
        -> evidence: extract_expense_document
     -> code validity gate
     -> PAPER_SCAN?
        -> deterministic match_paper_evidence
        -> có SUGGEST_LINK? analyze_evidence_reconciliation
        -> code policy + math + approval finding
     -> DIGITAL_FORM?
        -> deterministic reconciliation/policy
```

Source chứng minh thứ tự confidence trước extraction và stop khi quality fail: `process_settlement.py:279-440`. Extraction/validity: `:442-533`. Paper matching và optional reconciliation: `:575-592`, `:794-915`.

Một điểm tốt là confidence failure không được dùng như dữ liệu tin cậy: nếu confidence adapter ném `KimiResponseError`, caller lưu `.error.json`, thay bằng `ConfidenceAnalysis()`; `_confidence_findings` thấy thiếu assessment và tạo FAIL (`process_settlement.py:335-397`; `process_case.py:516-532`). Do đó malformed Kimi output không tự biến thành pass.

### 4.2 Legacy Streamlit inventory path

```text
Streamlit
  -> LocalEvidenceRepository
  -> CaseProcessingService
     -> OCR + confidence
     -> nếu không có supporting document: kết thúc
     -> analyze_conflict(all quality-passed documents)
     -> deterministic evaluate_inventory_consistency
     -> thiếu document_facts: one semantic repair call
     -> PASS / NEEDS_HUMAN
```

Source: `app/streamlit_app.py:39-99`, `process_case.py:300-321`, `:323-433`.

Luồng này giải bài inventory/receipt khác với scope `final`. Khi ghép code, cần tránh đưa `ConflictAnalysis`/receipt-status vào core final chỉ vì nó đã wired ở nhánh Hoangha.

## 5. Ai quyết định cái gì

| Quyết định | Model | Code | Con người |
| --- | --- | --- | --- |
| Block OCR mờ có còn dùng được không | Đề xuất `quality_state`, field mapping, `requires_verification` | Kiểm đủ candidate; quyết định field nào blocking và biến thành finding | Xác nhận giá trị khi finding yêu cầu |
| Loại chứng từ và field đọc được | Phân loại + extract structured facts | Kiểm `document_id`, validity, required fields, admissibility/matching eligibility | Kiểm/nhập lại khi extraction/validity fail |
| Dòng trên đơn giấy | Extract line, note, amount, refs, advance/reimbursement literal | Tính lại tổng, chênh lệch và chiều tiền; policy check | Xác nhận khi total/amount/consistency mơ hồ |
| Bill/report inventory conflict | Đề xuất facts/mapping/comparison/potential conflict | Policy inventory xác minh và quyết định blocking | Trả lời câu hỏi conflict |
| Ghép evidence mơ hồ | Đề xuất accepted link + confidence | Hiện tại chỉ kiểm candidate membership, confidence threshold và duplicate document | Nhận câu hỏi nếu không được promote |
| Policy, quyền, PASS/FAIL cuối | Không được phép theo prompt | Rule/policy/workflow | Approval/override theo quyền |

Ranh giới đúng với final là: model output chỉ là observation/proposal; final contract ghi rõ admissibility phải kiểm source role, binding, quality/conflict và locator; “opaque LLM confidence” không đủ riêng lẻ để chứng minh activity link (`IMPLEMENTATION_CONTRACTS.md:47-62`). Vì vậy phần reconciliation phải được hạ xuống proposal cho `Reconciler`, không phải một shortcut từ confidence sang accepted relation.

## 6. Findings xác minh bằng source

### F03-1 — NEEDS DISPOSITION trước implementation: LLM confidence có thể biến link sai số tiền thành `AUTO_LINK`

**Trigger cụ thể.** Một paper line 1.000.000 VND và một document 900.000 VND có mô tả/issuer đủ giống để matcher đạt từ 0.50 đến dưới 0.75. Matcher cố ý tạo `SUGGEST_LINK` khi score trong vùng này (`paper_evidence_matching.py:149-197`). Ví dụ amount không khớp nhưng semantic similarity tối đa đóng 0.30, party similarity đóng 0.20 và supporting/non-original type có thể thêm 0.10 (`:155-180`), đủ đạt 0.50–0.60.

**Hành vi sai có thể xảy ra.** Prompt reconciliation nói chỉ accept khi amount có căn cứ trực tiếp và thêm một signal (`evidence_reconciliation.py:9-12`). Nhưng schema `EvidenceReconciliationLink` chỉ chứa `item_id`, `document_id`, `confidence`, `rationale`; không có field chứng minh signals (`domain/processing.py:70-82`). Caller nhận output rồi chỉ kiểm: pair có nằm trong candidates, confidence >= 0.90, và document chưa auto-link; nếu đạt thì chuyển thẳng thành `AUTO_LINK` (`process_settlement.py:857-872`). Code **không so lại `line_amount` với `document_total`** và không kiểm second signal.

Ban đầu matcher đã tạo `SET_PAPER_MATCH_001 FAIL` cho item có suggested link (`paper_evidence_matching.py:303-318`). Sau promotion, caller xóa matching FAIL liên quan và thêm PASS (`process_settlement.py:894-914`) nhưng không chạy lại amount-mismatch check của matcher; check amount ban đầu chỉ chạy trong nhánh đã có `auto_links` (`paper_evidence_matching.py:360-404`). Vì vậy một model output sai nhưng schema-valid có thể nâng evidence mismatch thành relation accepted.

**Rủi ro khi ghép final.** Giữ candidate promotion theo accepted §15/§12.4 nhưng không suy nó thành known financial relation. Các nguyên tắc source/relationship vẫn cần admission ở stage sau: relation/activity link không được dựa trên opaque model confidence (`IMPLEMENTATION_CONTRACTS.md:53-62`) và backend phải kiểm relation/money (`ARCHITECTURE_AND_EVALUATION.md:193-201`).

**Disposition đề xuất sau review, chưa phải semantics đã chốt.** Một phương án hardening là giữ LLM chỉ làm proposal và trước promotion kiểm predicate deterministic từ payload hiện có: amount equality/tolerance, candidate pair đúng input, second signal thuộc tập được chấp nhận và document uniqueness. Tuy nhiên §15 hiện đã chốt **port nguyên core matching Hoangha**, gồm cả promotion suggestion ở `confidence >= 0.90`; report này không tự thay quyết định đó. Lead cần chọn rõ một trong hai: (a) giữ semantics §15 và chấp nhận rủi ro có test/metric riêng; hoặc (b) approve predicate bổ sung rồi cập nhật contract/gold trước implementation.

**Mức xác minh:** source-confirmed. Không chạy testcase runtime.

### F03-2 — SHOULD FIX khi tái dùng parser: parser chấp nhận object schema-valid đầu tiên trong response nhiều object

**Trigger cụ thể.** Provider trả hai JSON object hoàn chỉnh trong cùng response, trong đó object đầu tiên qua Pydantic nhưng là bản nháp semantic kém hơn object thứ hai.

**Hành vi.** `_json_objects` thu mọi object (`kimi_reasoning.py:305-325`); `_parse_analysis` iterate theo thứ tự và `return` object đầu tiên validate (`:328-344`). Prompt nói “đúng một JSON object”, nhưng parser chủ động chấp nhận surrounding text/multiple objects. Confidence stage còn có coverage validator nên nhiều lỗi semantic có thể bị chặn; reconciliation/extraction không có generic semantic validator tương đương.

**Tác động.** Đây không tự tạo bug ở mọi stage; downstream validity vẫn bắt nhiều trường hợp. Nhưng với reconciliation, nó kết hợp trực tiếp với F03-1: một object đầu schema-valid nhưng semantic sai có thể được dùng để promote relation.

**Đề xuất hardening nếu người dùng chốt thay semantics.** Hoặc yêu cầu đúng một top-level schema-valid object, hoặc để parser trả ambiguity error nếu có nhiều object schema-valid. Quan trọng hơn, relation output vẫn phải qua deterministic validator nên parser permissive không thể tự đổi state nghiệp vụ.

**Mức xác minh:** source-confirmed về parser behavior; tác động cụ thể phụ thuộc response provider nên chưa runtime-test.

### F03-3 — SHOULD NOT PORT: conflict prompt kéo domain inventory/receipt vào final V1

**Trigger.** Tái sử dụng toàn bộ `conflict_reasoning.py`/`ConflictAnalysis` vì nó đã có multi-source mapping/comparison.

**Hành vi sai về scope.** Prompt coi goods receipt/inventory/delivery report là nguồn receipt chính thức và tạo `receipt_status` comparisons (`conflict_reasoning.py:21-29`, `:41-47`). Final V1 đã chốt không xây mua hàng/nhận hàng/tồn kho/thiết bị (`ARCHITECTURE_AND_EVALUATION.md:35-39`). Port nguyên domain sẽ mở lại một product scope đã đóng và làm evaluation khó diễn giải.

**Fix.** Chỉ tái dùng pattern: independent per-source extraction → proposed relation/comparison → deterministic reconciliation. Viết contract mới theo Source/Observation/Relation của final và accepted source table; không port receipt-status taxonomy vào core.

**Mức xác minh:** source + final design confirmed.

## 7. Những điểm tốt nên giữ

1. **Quality trước extraction.** FastAPI path OCR từng file, đánh confidence, và nếu bất kỳ quality finding FAIL thì return trước extraction/matching (`process_settlement.py:279-440`). Điều này hỗ trợ yêu cầu đề A “không khẳng định dữ liệu đã bị gắn nghi vấn”.
2. **One evidence per confidence call.** Prompt cấm dùng business context/nguồn khác để bù chữ mờ (`kimi_reasoning.py:34-62`), giảm nguy cơ hallucination cross-source.
3. **Exact coverage validator cho candidate.** `analyze_confidence` reject missing/unexpected/duplicate candidate (`:484-520`). Đây là pattern nên áp dụng cho reader output nào có tập expected id biết trước.
4. **Model không tự tính settlement direction.** Paper prompt bắt extract literal amount; Python tính lại chênh lệch và direction (`kimi_reasoning.py:254-260`; `process_settlement.py:683-729`).
5. **LLM outage ở reconciliation giữ unresolved.** Exception không xóa finding mơ hồ (`process_settlement.py:843-849`).
6. **Schema repair có giới hạn.** `_analyze` chỉ có initial + một repair cho một invocation; sau đó ném lỗi có diagnostics (`kimi_reasoning.py:440-482`). Pattern này hợp với final nếu được tính vào global attempt budget.

## 8. Tests liên quan: chứng minh gì và chưa chứng minh gì

Trạng thái thực thi toàn bộ test trong review này: **NOT_RUN**. Các dòng dưới đây chỉ mô tả điều test source định nghĩa/assert, không khẳng định test đang pass ở commit này.

`tests/unit/test_kimi_reasoning.py` kiểm khá tốt adapter contract:

- Transient socket error được retry trong fake client (`:158-166`).
- Confidence dùng dedicated prompt, `reasoning_effort=low`, `max_tokens=8192` (`:169-187`).
- Parser tìm JSON giữa surrounding text (`:190-200`).
- Truncated JSON và missing candidate coverage kích hoạt một repair; fail hai lần ném `KimiResponseError` (`:202-277`).
- Conflict schema thiếu `code/field` được đưa lỗi cụ thể vào repair (`:254-265`).
- Conflict prompt nhận cả hai nguồn và giữ business context ở vai trò context (`:280-310`).
- Paper/expense extractor parse đúng fixture cơ bản và kiểm prompt boundary (`:312-350`).

`tests/unit/test_process_case.py:569-612` định nghĩa scenario conflict output lần đầu thiếu một document, caller tạo semantic repair request và gọi lại. Đây là test bằng **fake reasoning adapter**, không gọi Kimi LIVE.

`tests/unit/test_sqlite_settlement_repository.py` có các fake OCR/reasoner kiểm integration ordering và fail-close: low-confidence tax code phải dừng trước extraction (`:752-785`), peripheral low-confidence text vẫn cho extraction tiếp (`:788-839`), paper warning dừng trước matching (`:560-603`), paper clear đi đến accounting approval (`:605-650`). Các test này exercise workflow bằng fake adapters, không chứng minh Mistral/Kimi model quality thực tế.

Khoảng trống được xác minh bằng scoped source search trong `tests/`: không có test định nghĩa trực tiếp hành vi `analyze_evidence_reconciliation`, `accepted_links`, `paper-link-resolution` hay `LLM_RECONCILIATION`. Search chỉ thấy `SUGGEST_LINK` ở matcher unit test và code production. Do đó **promotion path F03-1 chưa có test source trực tiếp trong inventory hiện tại**. Đây là absence claim từ bounded source search, không từ graph.

Chưa có bằng chứng từ các test source đã đọc ở phần này cho:

- model LIVE có tuân điều kiện “amount + second signal” của reconciliation hay không;
- false accept/false reject của classifier/extractor trên dataset độc lập;
- multiple schema-valid JSON object behavior;
- budget tổng across retries/recovery của final;
- source locator existence/citation support theo final contract.

## 9. Adapter nên có khi mang sang `final`

Không nên để `KimiReasoningAdapter` trở thành interface domain của final. Nên bọc các phần dùng được sau interface đã chốt:

```text
EvidenceReader.read(source, requested_fields, budget)
  -> OCR-only cho mọi trang PDF/JPG/JPEG/PNG; không native-text bypass/fallback
  -> classification batch theo strict DocumentType/DocumentEvidenceRole của §15/E0
  -> extraction theo schema từng document type đã pin ở E0
  -> Observation[] có source locator + read state + origin
  -> validate schema + locator + expected coverage

Reconciler.assess(snapshot, observations, relations)
  -> deterministic applicability/quality/math/admissibility
  -> optional bounded LLM proposal cho relation khó
  -> deterministic relation predicate
  -> SUPPORTED / DISPROVED / UNKNOWN / CONFLICT
```

Mapping cụ thể:

| Hoangha | Final target | Ghi chú |
| --- | --- | --- |
| Confidence prompt + exact candidate coverage | EvidenceReader quality substep | Giữ per-source isolation; output thành observation/read state |
| Expense extraction prompt | EvidenceReader extractor | Chỉ dùng sau **OCR-only**; classification phải map vào strict type↔role §15/E0, rồi chọn schema đúng loại; convert source refs thành literal locators/digest-bound refs |
| Paper settlement extraction | EvidenceReader form extractor | Chỉ dùng sau OCR-only; map form sang `SETTLEMENT_FORM`/declaration schema và critical-field matrix do E0 pin; giữ “literal extract, Python computes” |
| Evidence reconciliation prompt | Optional Reconciler proposal | Chỉ proposal; code predicate quyết định relation state |
| Conflict inventory prompt | Không vào final V1 core | Chỉ lấy pattern, không lấy receipt/inventory domain |
| `_analyze` repair | Provider adapter helper | Tính mọi call vào final LLM budget/read trace; timeout/schema error → technical outcome |

Final đã chốt `Mistral OCR, xkiro LLM` (`ARCHITECTURE_AND_EVALUATION.md:170-173`), trong khi Hoangha adapter mặc định `moonshotai/Kimi-K3` (`kimi_reasoning.py:369-386`). Vì vậy ngay cả prompt tốt cũng nên được coi là **contract/reference**, không phải lý do thay model/provider đã chốt.

## 10. Verdict

**Không merge nguyên module 03-llm-contracts vào final.** Mang sang ba ý chính: per-source confidence gate trước extraction, structured extraction với schema/repair có giới hạn, và optional LLM proposal cho đối chiếu khó. Pipeline target phải giữ quyết định §15: **mọi PDF/image đi OCR-only**, sau đó classification strict + schema/profile do E0 pin. Với relation promotion, không tự thêm deterministic predicate ngoài contract hiện hành; F03-1 phải được disposition trước implementation.

Finding cần disposition trước khi tái dùng reconciliation: **F03-1**. F03-2 là hardening hợp lý; F03-3 là ranh giới scope để tránh kéo legacy inventory vào final. Tests/LIVE đều **NOT_RUN** trong review này theo yêu cầu.

## Disposition của lead sau peer-check 14

Cơ chế F03-1 được source xác minh; nhưng §15/§12.4 hiện đã accepted existing-suggestion promotion >=0.90. Baseline giữ semantics này không cần hỏi lại hoặc bị block bởi proposal hardening trong report. Thêm amount/second-signal predicate sẽ đổi accepted behavior và cần chốt lại contract/gold trước implementation. Ranh giới input: PDF/JPG/JPEG/PNG đều OCR; không native parse. Bước evidence mới kết thúc EVIDENCE_READY, chưa phải financial assessment. Xem [peer-check](14-peer-check.md).

# Review độc lập — 02 OCR & Quality

Nguồn review: worktree Hoangha tại commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Phạm vi owner `02-ocr-quality` trong `inventory.json`: **6 file / 717 dòng**. Review chỉ đọc; không gọi Mistral/Kimi/LIVE, không chạy test/build.

CodeGraph được dùng để kiểm tra caller/callee và source của các symbol trọng yếu. Graph coverage vẫn **UNKNOWN** vì generation-id/`check_index_coverage` không được exposed; các claim quan trọng được đối chiếu source thật.

## Kết luận phạm vi

Đây là phần **tái sử dụng được nhiều nhất** của Hoangha cho evidence layer: adapter Mistral cô lập provider, retry network nằm riêng, mapper biến output OCR thành page→block→word, quality gate giữ bbox/context/source reference.

Rủi ro lớn nhất khi ghép vào final là **missing confidence hiện không tự trở thành uncertainty**. Word không có confidence bị bỏ khỏi các phép tính/candidate; nếu đúng trường tiền/MST/số hóa đơn bị thiếu score, downstream có thể không thấy lý do để review. Final contract đã chốt cần fail closed ở critical fields, nên phải thêm guard ở adapter/validator.

## Từng file

| File | Dòng | Vai trò | Input → Output | Hàm/lớp chính; caller/callee | Hành vi lỗi | Khả năng dùng lại |
| --- | ---: | --- | --- | --- | --- | --- |
| `src/invoice_referee/extraction/__init__.py` | 41 | Public export của extraction package | module symbols → import surface | re-export OCR adapter, confidence, quality, mapper/resilience | import fail theo module con | **Có**, sau khi chỉ export contract final cần |
| `src/invoice_referee/extraction/confidence.py` | 42 | Chuẩn hóa word confidence | Mistral page scores → flat rows + low/review/good | `confidence_level`, `extract_word_confidence_rows` | non-numeric/missing confidence bị skip | **Có adapter**; cần missing-score semantics |
| `src/invoice_referee/extraction/mistral_ocr.py` | 86 | Provider adapter | persisted PDF/image → `OcrExecution` | `MistralOcrAdapter.process` → `call_with_service_retry` → Mistral SDK | missing key, file không tồn tại, provider/retry errors | **Cao** |
| `src/invoice_referee/extraction/network_resilience.py` | 104 | Retry transient provider/network errors | callable → result hoặc wrapped unavailable error | `is_transient_service_error`, `call_with_service_retry` | non-transient rethrow ngay; transient hết retry → `ExternalServiceUnavailableError` | **Cao**, provider-neutral |
| `src/invoice_referee/extraction/ocr_quality.py` | 89 | Chọn block cần review | hierarchy + evidence ID + threshold → low-confidence candidates | `collect_low_confidence_blocks` | threshold invalid → `ValueError`; no qualifying low word → empty list | **Cao nhưng phải fail-closed missing confidence** |
| `src/invoice_referee/extraction/word_block_mapper.py` | 355 | Map word confidence vào OCR blocks | raw Mistral payload → hierarchical schema | `restructure_mistral_ocr`, `_restructure_page`, contiguous/table/partial mapping | payload không có page metadata → `ValueError`; unmatched giữ warnings/mapping state | **Cao** |

<!-- reviewed-file: src/invoice_referee/extraction/__init__.py -->
<!-- reviewed-file: src/invoice_referee/extraction/confidence.py -->
<!-- reviewed-file: src/invoice_referee/extraction/mistral_ocr.py -->
<!-- reviewed-file: src/invoice_referee/extraction/network_resilience.py -->
<!-- reviewed-file: src/invoice_referee/extraction/ocr_quality.py -->
<!-- reviewed-file: src/invoice_referee/extraction/word_block_mapper.py -->

## Luồng theo source thật

### 1. OCR provider

`MistralOcrAdapter.process(path, mime_type)`:

1. reject nếu path không phải file (`mistral_ocr.py:53-56`);
2. detect MIME, đọc toàn bộ bytes, encode data URL (`58-61`);
3. dùng `document_url` cho PDF, `image_url` cho ảnh (`63-66`);
4. gọi Mistral với `include_blocks=True`, `confidence_scores_granularity="word"`, timeout 120s (`68-76`);
5. normalize response thành `OcrExecution(provider, model, processed_at, response)` (`80-85`).

Đây là contract tốt cho final vì provider-specific SDK không rò vào domain.

**Ví dụ minh họa input:**

```text
evidence.pdf + mime=application/pdf
```

**Output minh họa:**

```json
{
  "provider": "mistral",
  "model": "mistral-ocr-latest",
  "processed_at": "...+07:00",
  "response": {"pages": [...]}
}
```

Ví dụ chỉ mô tả shape; review này không gọi provider.

### 2. Retry

`call_with_service_retry` retry lỗi transient theo socket code, HTTP 429/5xx hoặc một số exception class; non-transient được raise ngay (`network_resilience.py:74-104`). Default adapter dùng hai delay 0.75s/2.0s, tương ứng tối đa ba attempt (`mistral_ocr.py:36-51`).

Code quyết định **có retry hay không**; model không tham gia.

### 3. Word/block mapping

`restructure_mistral_ocr` nhận payload có `response.pages`, `pages`, hoặc một single-page payload hợp lệ; nếu không có page metadata thì raise `ValueError` (`word_block_mapper.py:144-154,333-355`).

Word được normalize thành text/start/end/confidence; confidence không phải số được đưa thành `None` (`34-48`). Mapping block tìm:

- exact contiguous match;
- normalized whitespace match;
- table-reference match;
- partial match dùng `SequenceMatcher`, threshold và offset giới hạn;
- nếu không map được, block vẫn có mapping state/warning thay vì bịa word confidence.

Confidence summary trả `average/minimum=None, word_count=0` khi không có score hợp lệ (`51-79`). Đây là thông tin hữu ích, nhưng downstream phải coi trường hợp này là unresolved khi block quan trọng.

### 4. Quality gate

`collect_low_confidence_blocks` duyệt mọi page/block; một block trở thành candidate nếu có ít nhất một word “meaningful”, confidence là số và thấp hơn threshold (`ocr_quality.py:23-50`). Candidate giữ `evidence_id`, page/block ID/type/content, bbox và low words; source trước/sau được giữ để reviewer/model có context (`52+`).

Default threshold tương ứng 0.85. Threshold runtime có thể đến từ `AppSettings`.

## Model / code / con người

| Chủ thể | Quyền quyết định trong owner 02 |
| --- | --- |
| Mistral OCR | Sinh OCR blocks/text và word confidence. Đây là provider observation, không phải quyết định nghiệp vụ. |
| Code | Encode request; retry; map words→blocks; phân mức confidence; chọn candidate review; giữ bbox/source context. |
| Model reasoning khác | Không nằm trong 6 file này; caller có thể gửi candidate cho confidence agent/Kimi. |
| Con người | Cuối cùng xử lý vùng không chắc chắn/REQUEST_INFO/exception ở workflow cao hơn; owner 02 không phê duyệt tiền. |

## Findings

### F01 — MUST FIX: missing confidence có thể biến thành “không có vấn đề”

**Source-verified.**

- `extract_word_confidence_rows` bỏ word nếu confidence không phải số (`confidence.py:24-30`).
- mapper giữ confidence `None` nhưng summary bỏ các value `None`; nếu không còn score thì `word_count=0`, min/avg `None` (`word_block_mapper.py:34-48,51-79`).
- `collect_low_confidence_blocks` chỉ nhận word khi confidence là số và < threshold; missing/non-numeric score không tạo candidate (`ocr_quality.py:37-50`).

**Trigger:** OCR text của trường trọng yếu (MST, số hóa đơn, tổng tiền, số tạm ứng...) có text nhưng provider không trả confidence.

**Wrong behavior:** block có thể không vào review dù quality evidence bị thiếu.

**Integration:** final cần một validator sau mapping: nếu critical extracted field chạm word/block không có confidence đủ tin cậy thì trạng thái phải unresolved/needs evidence review. Không mặc định quality PASS.

### F02 — SHOULD FIX: hai khái niệm threshold có thể lệch nhau

**Source-verified.**

`confidence.py` hard-code `LOW=0.70`, `REVIEW=0.85` và `confidence_level()` dùng hai mốc này (`7-16`). Trong khi `collect_low_confidence_blocks` nhận threshold runtime (`ocr_quality.py:23-31`), được config qua `OCR_WORD_REVIEW_THRESHOLD`.

**Trigger minh họa:** cấu hình runtime threshold 0.90.

- word 0.87 được `confidence_level` gắn `good`;
- collector 0.90 vẫn đưa word đó vào review.

Không phá extraction, nhưng UI/debug/evaluator có thể thấy label khác với gate thật. Nên truyền cùng policy threshold hoặc phân biệt rõ “display bucket” và “review threshold”.

### F03 — SHOULD GUARD: adapter không tự chứng minh coverage đầy đủ mọi page

**Source-verified + integration risk.**

Adapter gửi cả PDF cho provider và nhận response; source không có check “số page input = số page output” trước khi trả `OcrExecution` (`mistral_ocr.py:53-85`). Điều này **không chứng minh provider làm thiếu page**; đó là giả thuyết chưa chạy. Tuy nhiên final đã chốt OCR mọi page accepted, nên composition layer cần page-count/coverage validation riêng.

### F04 — WATCH: partial word-to-block matching là heuristic

**Source-verified mechanism; sai mapping cụ thể chưa được chứng minh.**

`_find_contiguous_match` cho phép partial match bằng `SequenceMatcher` nếu similarity qua threshold và start offset trong giới hạn (`word_block_mapper.py:82-121`). Heuristic này hữu ích khi markdown/spacing lệch, nhưng repeated text giống nhau có thể tạo candidate mapping không tối ưu. Cần evaluator/fixtures cho duplicate labels/table rows nếu final phụ thuộc bbox/confidence đúng block.

## Tests chứng minh gì

Các test đã có trong Hoangha mà CodeGraph liên kết:

- `tests/unit/test_mistral_ocr.py`: request shape/provider adapter, gồm `include_blocks=True`, word confidence; retry path.
- `tests/unit/test_ocr_quality.py`: threshold và candidate low-confidence.
- `tests/unit/test_word_block_mapper.py`: exact/normalized/table/partial/unmatched mapping.
- Caller legacy có các test fail-closed trong một số confidence scenarios.

Review này **không chạy** các test. Từ source/test scope đã đọc, chúng chưa chứng minh:

- mọi accepted PDF page đều xuất hiện sau OCR;
- missing confidence trên critical field luôn chặn automation;
- final X-Kiro/confidence-agent path có timeout/budget/bounded concurrency đúng contract;
- evidence quality kết nối đúng với financial workflow final;
- OCR quality trên 173 PDF UC-03 thực tế.

## Nên mang sang final

1. Mang `MistralOcrAdapter`, retry wrapper và hierarchical mapper theo adapter interface của final.
2. Mang candidate structure có bbox/context/source ID; đây là evidence hữu ích để audit và hỏi người dùng cụ thể.
3. Thêm `OCRCoverageValidator`/guard tương đương ở final cho page coverage + missing confidence critical fields.
4. Dùng một threshold policy source duy nhất cho gate; nếu vẫn giữ display buckets 0.70/0.85 thì ghi semantics rõ.
5. Không nối trực tiếp “OCR quality good” → “READY_FOR_APPROVAL”. Owner 02 chỉ xác nhận chất lượng evidence.

Giới hạn: không LIVE, không benchmark OCR, không render corpus, không chạy tests; graph coverage UNKNOWN. Vì vậy không có claim accuracy/recall hoặc “OCR đã hoạt động tốt trên bộ 75 case”.

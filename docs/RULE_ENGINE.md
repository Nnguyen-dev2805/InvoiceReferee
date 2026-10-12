# Rule Engine - Các luật hiện có

Tài liệu này là bản đồ rule lấy từ code hiện tại của InvoiceReferee. Mục tiêu là
trả lời được bốn câu hỏi cho mỗi rule: rule kiểm tra gì, cần dữ liệu nào, không
đạt sẽ đi đâu và được chạy ở luồng nào.

Phạm vi chính là UC03 - Hoàn ứng/quyết toán tạm ứng chạy qua FastAPI. Phần cuối
ghi lại các rule OCR/kiểm kê của luồng cũ để không nhầm chúng với policy UC03.

## 1. Quy ước trạng thái

`SettlementFinding.status` hiện được lưu trong code là `PASS`, `WARN`, `FAIL`,
`PENDING_APPROVAL` hoặc `ERROR`. Để dễ trao đổi nghiệp vụ, tài liệu dùng thêm
trạng thái chuẩn hoá dưới đây.


| Trạng thái tài liệu | Dạng lưu trong code                                     | Ý nghĩa / quyết định cuối                                                                     |
| ------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `PASS`              | `PASS`                                                  | Đã qua rule.                                                                                  |
| `WARN`              | `WARN`                                                  | Có lưu ý nhưng chưa chặn luồng.                                                               |
| `NEED_FACT`         | `FAIL` + `FACTUAL_UNKNOWN`                              | Thiếu/không rõ dữ kiện; Decision Guard trả `REQUEST_INFO`, thường hỏi nhân viên hoặc kế toán. |
| `NEED_ACCOUNTANT`   | `FAIL` + `OUTSIDE_POLICY` hoặc `SUSPICIOUS`             | Cần kế toán xác nhận ngoại lệ, chứng từ thay thế hoặc tình huống nghi vấn.                    |
| `ESCALATE`          | `FAIL` + `BEYOND_AUTHORITY`, hoặc target là cấp quản lý | Chuyển cấp trưởng bộ phận/kế toán trưởng/giám đốc.                                            |
| `RECOMMEND_REJECT`  | `FAIL` của rule bị từ chối rõ ràng                      | Đề xuất từ chối: chi cá nhân hoặc hóa đơn sai MST công ty.                                    |
| `PENDING_APPROVAL`  | `PENDING_APPROVAL`                                      | Kiểm tra tự động đã xong; vẫn chờ kế toán kiểm tra bản gốc/xác nhận/chữ ký.                   |
| `ERROR`             | `ERROR`                                                 | Lỗi kỹ thuật hoặc output agent không hợp lệ; không được tự pass.                              |


Lưu ý: `FAIL` là finding chặn luồng; `WARN` và `PENDING_APPROVAL` không tự làm
hồ sơ fail. Decision Guard chỉ chọn finding `FAIL` có ưu tiên cao nhất để tạo
quyết định tổng.

Từ policy version `1.3`, engine phân biệt rõ `UNKNOWN` với `OTHER`: `UNKNOWN` là
chưa có đủ fact để phân loại, nên phải `NEED_FACT`; `OTHER` là danh mục
đã xác định nhưng không thuộc nhóm chi tiết hơn. Tương tự,
`UNMATCHED_EVIDENCE` không được coi là chứng từ gốc chỉ vì người dùng đã
tải một file lên.

> Trạng thái triển khai: rule engine đã sẵn sàng chặn category/date/evidence
> chưa rõ. Nhánh `PAPER_SCAN` phải tiếp tục được refactor để tạo canonical item
> có các trạng thái này, rồi chạy lại Shared Policy Engine; chưa được tuyên bố
> lỗi bypass đơn giấy đã khép hoàn toàn.

## 2. Luồng áp dụng rule UC03

```text
Hồ sơ nhân viên
  -> Source Gate (form/context/tạm ứng/evidence)
  -> OCR từng file
  -> Confidence Gate + Extract/Document Validity từng file
  -> Chỉ chứng từ CLEAR mới được phép matching
  -> Digital form: chuẩn hoá item do nhân viên khai - đối chiếu evidence
     Paper scan: đọc đơn giấy - sinh canonical item - matching evidence
  -> Shared Policy chi phí/hạn mức/thời hạn/thẩm quyền
  -> Decision Guard -> REQUEST_INFO / ACCOUNTANT_REVIEW / ESCALATE /
                      RECOMMEND_REJECT / READY_FOR_APPROVAL
  -> PENDING_APPROVAL cho kế toán nếu không còn FAIL
```

`source_refs` của finding phải được lưu kèm (`DOC:<document_id>`, block OCR hoặc
`FORM:EXPENSE_ITEM:<item_id>`) để tab Kế toán hiển thị được dẫn chứng.

## 3. Gate hồ sơ đầu vào

Các rule này chạy trước khi OCR/LLM. Nếu fail, worker dừng sớm, chưa thực hiện
matching hay policy phía sau.


| ID code           | Luật                                                                                                                  | Trạng thái khi không đạt | Dữ liệu cần                                                              | Cơ chế    |
| ----------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------ | --------- |
| `SET_CONTEXT_001` | Hồ sơ form điện tử phải có mục đích công việc. Đơn giấy lấy purpose từ chính đơn sau OCR.                             | `NEED_FACT`              | `SettlementDraft.business_context.purpose`, `source_type`                | Hard code |
| `SET_INPUT_001`   | Hồ sơ `PAPER_SCAN` phải có giấy đề nghị hoàn ứng/quyết toán làm đơn chính.                                            | `NEED_FACT`              | `source_type`, document role `SETTLEMENT_REQUEST_FORM`                   | Hard code |
| `SET_ADV_001`     | Quyết toán tạm ứng form điện tử phải có `allocated_advance_amount > 0`; hoàn ứng nhân viên không được gắn số tạm ứng. | `NEED_FACT`              | `settlement_type`, `allocated_advance_amount`, `source_type`             | Hard code |
| `SET_DOC_001`     | Khoản khai báo là `ORIGINAL_EVIDENCE` phải có ít nhất một tên/file chứng từ hoặc mã ngoại lệ.                         | `NEED_FACT`              | `ExpenseItem.evidence_status`, `evidence_names`, `policy_exception_code` | Hard code |


## 4. Chất lượng OCR, phân loại và tính hợp lệ chứng từ

Mỗi file OCR được xử lý độc lập. Nếu file có finding `FAIL`, file đó không được
đưa vào bước matching. Ngưỡng word confidence hiện là `0.85`.


| ID code                            | Luật                                                                                                                                                           | Trạng thái khi không đạt | Dữ liệu cần                                                                        | Cơ chế                        |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------- | ----------------------------- |
| `SET_QUALITY_001`                  | OCR không cấu hình, file không thuộc `.jpg/.jpeg/.png/.webp/.pdf`, block confidence thấp ở field trọng yếu, hoặc Confidence Agent không thể kết luận block rõ. | `NEED_FACT`              | file, OCR words/blocks, confidence, `required_fields`, Confidence Agent assessment | OCR + LLM + hard guard        |
| `SET_EXTRACTION_001`               | Extraction Agent không cấu hình, OCR/LLM lỗi, document ID agent trả về không đúng file nguồn.                                                                  | `NEED_FACT`              | OCR response, extract response, document ID                                        | Tool/LLM guard                |
| `SET_DOCUMENT_CLASSIFICATION_001`  | Không phân loại được chứng từ vào loại UC03 hỗ trợ hoặc confidence phân loại thấp hơn `0.60` và có loại thay thế.                                              | `NEED_FACT`              | `document_type`, `classification_confidence`, `alternative_document_types`         | LLM extract + hard code       |
| `SET_DOCUMENT_REQUIRED_FIELDS_001` | Thiếu, mờ hoặc invalid một trường bắt buộc của profile chứng từ.                                                                                               | `NEED_FACT`              | `ExpenseDocumentFacts`, `field_states`, document profile                           | Hard code trên facts OCR/LLM  |
| `SET_DOCUMENT_CONSISTENCY_001`     | Extraction warning ảnh hưởng field trọng yếu, ví dụ MST/tổng tiền/ngày/số hóa đơn mâu thuẫn hoặc không chắc. Lỗi chính tả/tên món không trọng yếu chỉ `WARN`.  | `NEED_FACT` hoặc `WARN`  | `extraction_warnings`, required fields, document type                              | Hard code phân loại warning   |
| `SET_BUYER_IDENTITY_001`           | MST bên mua hợp lệ nhưng không nằm trong danh sách MST công ty đã cấu hình.                                                                                    | `RECOMMEND_REJECT`       | `buyer_tax_code`, `company_tax_codes`                                              | Hard code                     |
| `SET_PAPER_FORM_VALIDITY_001`      | Đơn giấy thiếu purpose/tổng tiền/dòng chi/số tạm ứng bắt buộc; hoặc dòng chi thiếu nội dung/số tiền hợp lệ.                                                    | `NEED_FACT`              | `PaperSettlementFacts`                                                             | OCR + LLM extract + hard code |
| `SET_PAPER_CONSISTENCY_001`        | Cảnh báo OCR/extraction mâu thuẫn trên chính đơn giấy.                                                                                                         | `NEED_FACT` hoặc `WARN`  | `PaperSettlementFacts.extraction_warnings`                                         | OCR + hard code               |
| `SET_DOCUMENT_VALIDITY_001`        | Chứng từ đã phân loại và đủ field bắt buộc. Đây chỉ là finding `PASS`, không có nhánh fail riêng.                                                              | `PASS`                   | Kết quả `validate_expense_document`                                                | Hard code                     |


### 4.1. Field bắt buộc theo loại chứng từ

`SET_DOCUMENT_REQUIRED_FIELDS_001` dùng profile dưới đây. Field có state
`ABSENT`, `UNREADABLE` hoặc `INVALID` được xem là không dùng được.


| Loại chứng từ                                         | Field bắt buộc                                                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `E_INVOICE`                                           | Tên/MST bên bán, tên/MST bên mua, số hóa đơn, mẫu số, ký hiệu, ngày, tổng tiền, danh sách hàng/dịch vụ |
| `PAPER_RECEIPT`, `HOTEL_RECEIPT`                      | Bên bán, ngày, tổng tiền                                                                               |
| `TRANSPORT_TICKET`                                    | Bên bán, số vé/chứng từ, ngày, tổng tiền                                                               |
| `COLLECTION_RECEIPT`                                  | Bên phát hành, bên mua, số chứng từ, ngày, tổng tiền                                                   |
| `CARD_SLIP`                                           | Đơn vị phát hành, ngày, tổng tiền, mã giao dịch                                                        |
| `PAYMENT_PROOF`                                       | Người nhận tiền, ngày, tổng tiền, mã giao dịch, trạng thái giao dịch                                   |
| `CONTRACT`                                            | Bên phát hành, bên mua, số, ngày, và có ít nhất tổng tiền hoặc dòng hàng                               |
| `QUOTATION`                                           | Bên phát hành, ngày, tổng tiền, dòng hàng                                                              |
| `PURCHASE_ORDER`                                      | Bên phát hành, bên mua, số, ngày, tổng tiền, dòng hàng                                                 |
| `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT` | Bên phát hành, bên mua, số (trừ acceptance record), ngày, dòng hàng, xác nhận/chữ ký                   |
| `SUPPLIER_CONFIRMATION`                               | Bên phát hành, xác nhận/chữ ký, và có ít nhất tổng tiền hoặc dòng hàng                                 |


Các kiểm tra chuyên biệt bổ sung:

- Hóa đơn điện tử: MST bán/mua phải đúng mẫu `10 số` hoặc `10 số-3 số`.
- Hóa đơn điện tử: bên mua ghi `khách lẻ` là `NEED_FACT`.
- Bằng chứng thanh toán: trạng thái phải thể hiện đã hoàn tất/thành công.
- Warning về lỗi chính tả, tên món/tên dịch vụ, thiếu dấu không chặn matching nếu field đó không bắt buộc.

## 5. Đối chiếu hoàn ứng từ form điện tử

Các rule chỉ chạy khi document pipeline đang bật, chứng từ của item đã qua
validity và item không chọn `NO_EVIDENCE`/mã ngoại lệ.


| ID code                | Luật                                                                                                                    | Trạng thái khi không đạt           | Dữ liệu cần                                                           | Cơ chế    |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | --------------------------------------------------------------------- | --------- |
| `SET_TOTAL_001`        | Tổng tiền các evidence ghép cho một item phải bằng `claimed_amount`, sai số tối đa 1 VND.                               | `NEED_FACT`                        | item amount, `linked_item_id`, extracted `total_amount` từng evidence | Hard code |
| `SET_ALT_EVIDENCE_001` | Nếu chọn bằng chứng thay thế mà không có file thì cần bổ sung. Nếu có file thay thế thì cần kế toán chấp nhận ngoại lệ. | `NEED_FACT` hoặc `NEED_ACCOUNTANT` | evidence status, file names, loại/lý do thay thế                      | Hard code |
| `SET_NO_EVIDENCE_001`  | Khoản được khai báo không có chứng từ phải có lý do và cần kế toán chấp nhận theo ngoại lệ.                             | `NEED_ACCOUNTANT`                  | evidence status, exception reason                                     | Hard code |


## 6. Đơn giấy và ghép evidence theo dòng chi

Các rule này chỉ chạy cho `PAPER_SCAN` sau khi đơn giấy và evidence đã qua gate
chất lượng/validity. Engine ưu tiên ghép theo số hóa đơn đúng tuyệt đối; nếu không
có thì tính điểm theo tổng tiền, nội dung và bên phát hành.


| ID code                        | Luật                                                                                                                    | Trạng thái khi không đạt | Dữ liệu cần                                                    | Cơ chế               |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ------------------------ | -------------------------------------------------------------- | -------------------- |
| `SET_PAPER_LINES_001`          | Không trích xuất được bảng dòng chi từ đơn giấy.                                                                        | `NEED_FACT`              | `PaperSettlementFacts.lines`                                   | OCR + LLM extract    |
| `SET_PAPER_LINE_AMOUNT_001`    | Một dòng chi không có số tiền.                                                                                          | `NEED_FACT`              | `PaperSettlementLine.amount`                                   | Hard code            |
| `SET_PAPER_MATCH_001`          | Evidence có score từ `0.50` đến dưới `0.75`: gần phù hợp nhưng không đủ chắc để tự ghép. Score từ `0.75` tự ghép.       | `NEED_FACT`              | invoice ref, amount, issuer, line description, extracted facts | Hard code similarity |
| `SET_PAPER_EVIDENCE_REQUIRED`  | Dòng ghi cần đính kèm nhưng không có evidence phù hợp hoặc lý do riêng cho dòng đó.                                     | `NEED_FACT`              | `requires_evidence`, evidence links, per-line reason           | Hard code            |
| `SET_PAPER_EVIDENCE_EXCEPTION` | Dòng không có chứng từ hoặc chỉ có giải trình ngoại lệ. Kế toán phải chấp nhận/từ chối.                                 | `NEED_ACCOUNTANT`        | reason, note trên đơn giấy, evidence status                    | Hard code            |
| `SET_PAPER_AMOUNT_001`         | Tổng evidence đã tự ghép không bằng số tiền dòng chi, sai số lớn hơn 1 VND.                                             | `NEED_FACT`              | line amount, total amount of linked evidence                   | Hard code            |
| `SET_PAPER_UNMATCHED_001`      | Có evidence không được ghép hay gợi ý ghép với dòng chi nào.                                                            | `NEED_FACT`              | danh sách evidence, auto/suggest links                         | Hard code            |
| `SET_PAPER_TOTAL_001`          | Thiếu tổng cộng trên đơn giấy hoặc tổng các dòng không bằng tổng cộng, sai số lớn hơn 1 VND.                            | `NEED_FACT`              | line amounts, paper total                                      | Hard code            |
| `SET_ADV_AMOUNT_001`           | Đơn quyết toán tạm ứng không có số tiền đã tạm ứng hợp lệ. MVP chỉ kiểm tra số trên đơn, chưa liên kết lịch sử tạm ứng. | `NEED_FACT`              | `advance_amount`, settlement type                              | Hard code            |
| `SET_SETTLEMENT_DIFF_001`      | Chênh lệch ghi trên đơn phải bằng `abs(tạm ứng - tổng chi)`, sai số tối đa 1 VND.                                       | `NEED_FACT`              | advance amount, paper total, reimbursement/refund amount       | Hard code            |
| `SET_APPROVAL_001`             | Không còn finding `FAIL`: hồ sơ chờ kế toán kiểm tra bản gốc và xác nhận/chữ ký. Không phải lỗi.                        | `PENDING_APPROVAL`       | kết quả các rule trước, đơn giấy nguồn                         | Hard code workflow   |


## 7. Policy chi phí và thẩm quyền


| ID code                    | Luật                                                                                    | Trạng thái khi không đạt      | Dữ liệu cần                                       | Cơ chế           |
| -------------------------- | --------------------------------------------------------------------------------------- | ----------------------------- | ------------------------------------------------- | ---------------- |
| `SET_CATEGORY_001`         | Không chấp nhận danh mục `PERSONAL`.                                                    | `RECOMMEND_REJECT`            | `ExpenseItem.category`                            | Hard code        |
| `SET_CATEGORY_UNKNOWN_001` | Chưa xác định được danh mục; không được coi là `OTHER` hay bỏ qua hạn mức.              | `NEED_FACT`                   | category, nguồn trích xuất                        | Hard code        |
| `SET_LIMIT_001`            | Hạn mức demo: tiếp khách `CLIENT_MEAL` tối đa 5.000.000 VND; taxi tối đa 2.000.000 VND. | `ESCALATE` đến kế toán trưởng | category, claimed amount, policy config           | Hard code/config |
| `SET_EXPENSE_DATE_001`     | Thiếu ngày chi nên chưa thể áp dụng thời hạn nộp hồ sơ.                                 | `NEED_FACT`                   | expense date, nguồn trích xuất                    | Hard code        |
| `SET_DEADLINE_001`         | Khoản chi nộp quá 30 ngày kể từ ngày chi.                                               | `NEED_ACCOUNTANT`             | expense date, ngày chạy, `submission_window_days` | Hard code/config |
| `SET_AUTH_001`             | Tổng hồ sơ VND vượt 100.000.000 VND.                                                    | `ESCALATE` đến giám đốc       | claimed total, currency, `authority_amount_vnd`   | Hard code/config |


Giá trị policy hiện tại nằm trong `SettlementPolicyConfig`: `30` ngày, `100.000.000 VND`,
`CLIENT_MEAL = 5.000.000 VND`, `TAXI = 2.000.000 VND`, và cấm `PERSONAL`.

## 8. Decision Guard - luật định tuyến cuối

Decision Guard chỉ xét finding `FAIL`. Nếu không có `FAIL`, quyết định là
`READY_FOR_APPROVAL`; `PENDING_APPROVAL` vẫn có thể xuất hiện để nhắc kế toán.


| Điều kiện finding                                                                    | Quyết định tự động   | Đích mặc định                 |
| ------------------------------------------------------------------------------------ | -------------------- | ----------------------------- |
| `SET_CATEGORY_001`, `SET_BUYER_IDENTITY_001`, `SET_DUPLICATE_001`                    | `RECOMMEND_REJECT`   | Kế toán                       |
| `uncertainty_type = SUSPICIOUS`                                                      | `ACCOUNTANT_REVIEW`  | Kế toán                       |
| `uncertainty_type = FACTUAL_UNKNOWN`                                                 | `REQUEST_INFO`       | Nhân viên/kế toán tùy finding |
| `uncertainty_type = BEYOND_AUTHORITY` hoặc target là quản lý/kế toán trưởng/giám đốc | `ESCALATE`           | Cấp có thẩm quyền             |
| `OUTSIDE_POLICY` còn lại                                                             | `ACCOUNTANT_REVIEW`  | Kế toán                       |
| Không có `FAIL`                                                                      | `READY_FOR_APPROVAL` | Kế toán                       |


## 9. Luồng OCR/kiểm kê cũ còn tồn tại trong chương trình

Các rule dưới đây thuộc `CaseProcessingService` và `policy/inventory.py`. Chúng
phù hợp cho UC01/luồng đối chiếu hóa đơn - phiếu kiểm kê cũ; không phải toàn bộ
đều được worker UC03 gọi ở thời điểm hiện tại.

`CROSS_SOURCE_CONFLICT` là tên workflow/payload khi gọi Conflict Agent, không
phải `rule_id` hay finding độc lập.

### 9.1. Gate nguồn và confidence


| ID code                             | Luật                                                                     | Trạng thái khi không đạt | Dữ liệu cần                                         |
| ----------------------------------- | ------------------------------------------------------------------------ | ------------------------ | --------------------------------------------------- |
| `MISSING_BILL_EVIDENCE`             | Không có bill/chứng từ chính.                                            | `NEED_FACT`              | primary evidence list                               |
| `MISSING_BUSINESS_CONTEXT`          | Không có text description và cũng không có file context/report.          | `NEED_FACT`              | case body, supporting evidence list                 |
| `OCR_NOT_CONFIGURED`                | Adapter OCR của luồng cũ chưa được cấu hình.                             | `ERROR`                  | OCR adapter configuration                           |
| `BILL_EVIDENCE_NOT_READABLE`        | Không OCR được bất cứ chứng từ chính nào.                                | `NEED_FACT`              | OCR success IDs                                     |
| `BUSINESS_CONTEXT_NOT_READABLE`     | Không có text và OCR được file context/report.                           | `NEED_FACT`              | case body, OCR success IDs                          |
| `OCR_PROCESSING_ERROR`              | Có file OCR lỗi kỹ thuật.                                                | `ERROR`                  | OCR errors                                          |
| `KIMI_NOT_CONFIGURED`               | Kimi chưa cấu hình tại bước confidence hoặc đối chiếu nhiều nguồn.       | `ERROR`                  | reasoning adapter configuration                     |
| `CONFIDENCE_AGENT_ERROR`            | Confidence Agent lỗi hoặc không trả được kết quả dùng được.              | `ERROR`                  | candidate blocks, agent response                    |
| `OCR_CONFIDENCE_ASSESSMENT_INVALID` | Confidence Agent trả `candidate_id` không tồn tại.                       | `ERROR`                  | candidate blocks, agent assessment                  |
| `LOW_CONFIDENCE_BLOCK_UNKNOWN`      | Candidate confidence thấp không được agent đánh giá đúng một lần.        | `NEED_FACT`              | candidate blocks, agent assessment                  |
| `LOW_CONFIDENCE_ASK_HUMAN`          | Block confidence thấp là `CRITICAL`, cần xác minh và map vào field chặn. | `NEED_FACT`              | word/block confidence, importance, canonical fields |
| `OCR_NON_BLOCKING_QUALITY_WARNING`  | Block chưa rõ nhưng không ảnh hưởng field cần đối chiếu hiện tại.        | `WARN`                   | confidence assessment                               |
| `OCR_CONFIDENCE_REVIEW`             | Không còn block confidence thấp cần người kiểm tra.                      | `PASS`                   | candidate blocks                                    |
| `CROSS_SOURCE_CHECK_NOT_APPLICABLE` | Không có supporting document nên không chạy đối chiếu nhiều nguồn.       | `PASS`                   | supporting evidence list                            |
| `CONFLICT_AGENT_ERROR`              | Conflict Agent lỗi khi đối chiếu bill và report/phiếu kiểm kê.           | `ERROR`                  | OCR context nhiều nguồn, agent response             |


### 9.2. Đối chiếu kiểm kê nhiều nguồn


| ID code                                                            | Luật                                                                            | Trạng thái khi không đạt | Dữ liệu cần                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------- | ------------------------ | -------------------------------------------------- |
| `INVENTORY_EXTRACTION_COVERAGE_INVALID`                            | Agent thiếu/trùng facts theo evidence ID hoặc trả fact cho nguồn không tồn tại. | `ERROR`                  | expected document roles, extracted inventory facts |
| `INVENTORY_APPLICABILITY_UNKNOWN`                                  | Chưa biết hồ sơ có phát sinh nhận/kiểm kê hàng hóa không.                       | `NEED_FACT`              | `analysis.applicability`                           |
| `INVENTORY_NOT_APPLICABLE`                                         | Không cần kiểm kê/nhận hàng.                                                    | `PASS`                   | `analysis.applicability`                           |
| `INVENTORY_SOURCE_REQUIRED`                                        | Thiếu chứng từ chính hoặc nguồn nhận hàng/kiểm kê để so sánh.                   | `NEED_FACT`              | primary/supporting documents                       |
| `INVENTORY_ITEMS_REQUIRED`                                         | Một trong hai nguồn thiếu danh sách item để đối chiếu.                          | `NEED_FACT`              | line items from both sources                       |
| `INVENTORY_SUPPLIER_MISMATCH`                                      | Nhà cung cấp/MST hai nguồn khác nhau.                                           | `NEED_FACT`              | supplier tax code                                  |
| `INVENTORY_DATE_MISMATCH`                                          | Ngày hai nguồn cách nhau quá 7 ngày.                                            | `NEED_FACT`              | document dates                                     |
| `INVENTORY_RECEIPT_STATUS_CONFLICT`                                | Trạng thái nhận hàng là một phần/chờ/từ chối.                                   | `NEED_FACT`              | receipt status                                     |
| `INVENTORY_RECEIPT_STATUS_UNKNOWN`                                 | Không đọc được trạng thái nhận hàng.                                            | `NEED_FACT`              | receipt status                                     |
| `INVENTORY_ITEM_MAPPING_INVALID`                                   | Conflict Agent map item không tồn tại, map trùng hoặc map không hợp lệ.         | `ERROR`                  | suggested item matches, source item IDs            |
| `INVENTORY_PRIMARY_ITEM_UNMATCHED`                                 | Item trên chứng từ chính không có dòng nhận hàng tương ứng.                     | `NEED_FACT`              | primary items, matches                             |
| `INVENTORY_SUPPORTING_ITEM_UNMATCHED`                              | Dòng nhận hàng không có item trên chứng từ chính.                               | `NEED_FACT`              | supporting items, matches                          |
| `INVENTORY_QUANTITY_UNKNOWN` / `INVENTORY_UNIT_UNKNOWN`            | Thiếu số lượng hoặc đơn vị.                                                     | `NEED_FACT`              | quantities, units                                  |
| `INVENTORY_UNIT_MISMATCH`                                          | Đơn vị hai nguồn khác nhau.                                                     | `NEED_FACT`              | normalized units                                   |
| `INVENTORY_QUANTITY_MISMATCH`                                      | Số lượng quy đổi hai nguồn khác nhau.                                           | `NEED_FACT`              | quantities, unit factors                           |
| `INVENTORY_UNIT_PRICE_UNKNOWN` / `INVENTORY_LINE_AMOUNT_UNKNOWN`   | Không đọc được đơn giá/thành tiền để so sánh.                                   | `NEED_FACT`              | prices, line amounts                               |
| `INVENTORY_UNIT_PRICE_MISMATCH` / `INVENTORY_LINE_AMOUNT_MISMATCH` | Đơn giá/thành tiền chênh quá 1 VND.                                             | `NEED_FACT`              | primary/supporting values                          |
| `INVENTORY_CONFLICT_REFERENCE_INVALID`                             | Conflict Agent dẫn nguồn không có trong hồ sơ.                                  | `ERROR`                  | conflict source refs                               |
| `INVENTORY_SEMANTIC_CONFLICT_<code>`                               | Conflict Agent phát hiện xung đột ngữ nghĩa có dẫn chứng hợp lệ.                | `NEED_FACT`              | conflict description, source refs                  |
| `INVENTORY_CONSISTENCY`                                            | Các nguồn và item nhất quán.                                                    | `PASS`                   | toàn bộ facts/matches                              |


## 10. Rule được nhắc trong UI/Decision Guard nhưng chưa có engine phát sinh

Hai rule sau có nhãn hoặc mapping, nhưng tại thời điểm viết tài liệu chưa thấy
worker tạo finding tương ứng. Chúng là khoảng trống cần triển khai, không được
trình bày như đã hoạt động.


| ID code             | Trạng thái     | Ghi chú                                                                                                                                 |
| ------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `SET_DUPLICATE_001` | Chưa phát sinh | Decision Guard biết rule này sẽ `RECOMMEND_REJECT`, nhưng chưa có query kiểm tra trùng số hóa đơn + MST bên bán + số tiền.              |
| `SET_SIGNATURE_001` | Chưa phát sinh | UI có nhãn "Xác nhận chữ ký"; luồng hiện tại dùng `SET_APPROVAL_001` để chờ kế toán xác nhận, chưa có OCR/chữ ký số validation độc lập. |


## 11. Vị trí triển khai chính


| Thành phần                                              | File                                                                                         |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Gate, OCR, extract, paper matching, reconciliation UC03 | `src/invoice_referee/application/process_settlement.py`                                      |
| Policy chi phí, hạn mức, thẩm quyền                     | `src/invoice_referee/policy/settlement.py`                                                   |
| Profile chứng từ và required-field validation           | `src/invoice_referee/policy/document_validity.py`                                            |
| Matching đơn giấy - evidence                            | `src/invoice_referee/application/paper_evidence_matching.py`                                 |
| Quyết định tổng và routing                              | `src/invoice_referee/application/decision_guard.py`                                          |
| OCR confidence và kiểm kê luồng cũ                      | `src/invoice_referee/application/process_case.py`, `src/invoice_referee/policy/inventory.py` |







| Nhóm                 | Case cần thêm                                                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Canonical paper item | Không xác định category; không đọc được ngày chi; category/date có confidence thấp                                                        |
| Hạn mức              | Taxi đúng 2 triệu, taxi 2 triệu + 1; tiếp khách đúng 5 triệu, vượt 1 đồng                                                                 |
| Thời hạn             | Nộp đúng ngày thứ 30; quá ngày thứ 31; ngày chi trong tương lai                                                                           |
| Chứng từ gốc         | Dòng không evidence, không lý do; evidence có nhưng chưa match; evidence match sai item                                                   |
| Chứng từ thay thế    | Vé điện tử hợp lệ; ảnh chuyển khoản đơn lẻ; biên bản nghiệm thu + thanh toán; loại thay thế được policy auto-allow                        |
| Matching             | Số hóa đơn khớp nhưng tiền lệch; một dòng cần hai hóa đơn; một hóa đơn bị phân bổ thiếu/thừa; evidence trùng hai hồ sơ                    |
| Hóa đơn điện tử      | Sai định dạng MST; người mua “khách lẻ”; thiếu MST người bán; số lượng × đơn giá lệch thành tiền; số tiền chữ lệch số; VAT/tổng tiền lệch |
| Tạm ứng              | Thiếu số tiền tạm ứng; số tạm ứng bằng 0; hoàn ứng nhưng lại khai tạm ứng; số hoàn trả/công ty trả thêm đúng và sai                       |
| OCR                  | Report mờ; evidence mờ ở tổng tiền/MST; OCR nhầm loại chứng từ; PDF nhiều trang                                                           |
| Workflow             | Thiếu form giấy chính; thiếu purpose trên form giấy; chưa có chữ ký chỉ là `PENDING_APPROVAL`, không phải `FAIL`                          |



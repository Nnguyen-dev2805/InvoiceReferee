# Quy Định Xử Lý Hồ Sơ Chi Phí - Sprint 1

> Trạng thái: đang được thực thi trên nhánh `hoang-ha`.
> Nguồn sự thật: code trong `src/invoice_referee/application/process_case.py`,
> `src/invoice_referee/policy/inventory.py` và các test tương ứng.

## 1. Mục đích

Tài liệu này là quy định nội bộ giả lập đang được InvoiceReferee thực thi
trong Sprint 1. Phạm vi của nó là tiếp nhận hồ sơ chi phí và kiểm tra độ rõ
của chứng từ, sau đó đối chiếu bill với tài liệu nhập kho hoặc kiểm kê khi có.

`PASS` chỉ có nghĩa hồ sơ đã qua các rule trong tài liệu này. Hệ thống không
thanh toán, ghi sổ, hoàn tiền, hoặc thay thế quyết định cuối của kế toán.

## 2. Tóm tắt 30 giây

1. Mọi hồ sơ xử lý tự động phải có ít nhất một bill hoặc chứng từ chính.
2. Mỗi file được OCR và kiểm tra độ rõ độc lập.
3. Thông tin quan trọng không đọc chắc chắn thì chuyển kế toán xác nhận.
4. Hồ sơ không có tài liệu hỗ trợ dừng sau bước kiểm tra chất lượng OCR.
5. Hồ sơ có tài liệu hỗ trợ chỉ được đối chiếu khi tất cả file đều đọc rõ.
6. Description của nhân viên chỉ là bối cảnh; không thay thế phiếu nhập kho,
   report hoặc bằng chứng nhận hàng.
7. Bất kỳ rule `FAIL` hoặc `ERROR` nào cũng đưa hồ sơ vào `NEEDS_HUMAN`.
8. `WARN` được lưu để kế toán biết nhưng không tự động chặn hồ sơ.

## 3. Vai trò và tài liệu được chấp nhận

- Nhân viên nộp nội dung đề nghị và một hoặc nhiều tệp đính kèm.
- Chứng từ chính (`PRIMARY_DOCUMENT`) là bill, hóa đơn, hoặc chứng từ chi phí.
- Chứng từ hỗ trợ (`SUPPORTING_DOCUMENT`) là phiếu nhập kho, phiếu kiểm kê,
  biên bản giao nhận, report, hoặc tài liệu liên quan.
- Kế toán xử lý mọi hồ sơ có kết quả `NEEDS_HUMAN`.

Nội dung đề nghị của nhân viên chỉ dùng để biết bối cảnh nghiệp vụ. Nó không
được xem là bằng chứng nhận hàng, không thể thay cho bill, và không thể tự tạo
ra dòng hàng hóa hay trạng thái nhận hàng.

## 4. Kết quả hiện hành

| Kết quả hệ thống | Ý nghĩa nghiệp vụ | Xử lý của kế toán |
| --- | --- | --- |
| `PASS` | Hồ sơ đã qua tất cả gate Sprint 1 đang áp dụng. | Có thể chuyển sang bước xử lý kế toán tiếp theo. |
| `NEEDS_HUMAN` | Thiếu nguồn, OCR không đọc được, dữ liệu cần xác nhận, kết quả agent lỗi, hoặc bill và tài liệu hỗ trợ mâu thuẫn. | Đọc câu hỏi/findings, yêu cầu bổ sung hoặc xác nhận, sau đó xử lý thủ công. |

Phạm vi của `PASS` phụ thuộc hồ sơ:

- Không có tài liệu hỗ trợ: chỉ xác nhận nguồn đầu vào và chất lượng OCR đạt.
  Hệ thống chưa kết luận khoản chi đúng chính sách công ty.
- Có tài liệu hỗ trợ: xác nhận thêm rằng policy đối chiếu kiểm kê hiện tại
  không tìm thấy chênh lệch cần kế toán xử lý.
- `PASS` không đồng nghĩa hóa đơn hợp lệ về thuế, không trùng, đúng danh mục
  chi phí hoặc nằm trong hạn mức phê duyệt; các rule đó chưa được triển khai.

Hai kết quả trên là tên kỹ thuật đang có trong code. Khi chuyển sang đáp án
Track A, `PASS` sẽ được ánh xạ thành `AUTO_PROCESS`; các lý do
`NEEDS_HUMAN` phải được tách thành `REQUEST_INFO` hoặc `ESCALATE` bởi
Decision Guard. Ánh xạ này chưa được code thực thi ở Sprint 1 hiện tại.

## 5. Rule tiếp nhận hồ sơ

1. Hồ sơ phải có ít nhất một trong hai: nội dung đề nghị hoặc tệp đính kèm.
2. Hồ sơ được phép tối đa 12 tệp; mỗi tệp tối đa 15 MB; tổng dung lượng tối đa
   50 MB.
3. Tệp trùng nội dung SHA-256 trong cùng một lần nộp chỉ được giữ một bản.
4. Hồ sơ phải có ít nhất một chứng từ chính. Thiếu chứng từ chính thì
   `NEEDS_HUMAN` với yêu cầu bổ sung bill/chứng từ chính.
5. Hồ sơ phải có business context: nội dung đề nghị không rỗng, hoặc ít nhất
   một tài liệu hỗ trợ đọc được. Nếu cả hai đều không có thì `NEEDS_HUMAN`.
6. Tệp được chấp nhận ở tầng nộp hồ sơ:
   - Chứng từ chính: `.jpeg`, `.jpg`, `.json`, `.pdf`, `.png`, `.webp`, `.xml`.
   - Chứng từ hỗ trợ: các định dạng trên và `.csv`, `.doc`, `.docx`, `.txt`,
     `.xls`, `.xlsx`.

Quy định OCR hiện tại chỉ xử lý `.jpeg`, `.jpg`, `.pdf`, `.png`, `.webp`.
Nếu tệp đính kèm không OCR được, hồ sơ không tự động qua gate và cần kế toán
kiểm tra.

## 6. Rule chất lượng chứng từ

1. Mọi evidence OCR được bằng Mistral OCR và lưu text, block, word confidence
   cùng bounding box.
2. Word có confidence dưới `0.85` được gom theo block và đưa đến Kimi
   Confidence Quality Agent. Ngưỡng này được cấu hình bằng
   `OCR_WORD_REVIEW_THRESHOLD`.
3. Agent phải đánh giá đúng một lần từng low-confidence block. Kết quả thiếu,
   lặp, hoặc có candidate không tồn tại làm hồ sơ `NEEDS_HUMAN`.
4. Một block cần xác nhận sẽ chặn xử lý khi không map được field, hoặc map vào
   một trong các field đối chiếu sau: `seller_name`, `seller_tax_code`,
   `buyer_tax_code`, `invoice_date`, `invoice_number`, `item_name`, `quantity`,
   `unit`, `unit_price`, `line_amount`, `total_amount`, `receipt_status`.
5. Thông tin mờ nhưng không cần cho đối chiếu hiện tại, ví dụ `tax_rate`, được
   lưu thành cảnh báo và không tự động chặn hồ sơ.
6. Nếu Mistral OCR, Kimi Confidence Agent, hoặc JSON schema của agent lỗi, hồ
   sơ là `NEEDS_HUMAN`. Hệ thống không đoán giá trị còn thiếu.
7. Gate hiện tại chỉ đánh giá nội dung đã được OCR nhưng có confidence thấp.
   Nó chưa kiểm tra một trường bắt buộc bị thiếu hoàn toàn trên chứng từ.
8. `buyer_tax_code` không rõ sẽ chặn hồ sơ, nhưng Sprint 1 chưa xác minh MST đó
   có đúng định dạng hoặc thuộc công ty hay không.

## 7. Rule đối chiếu bill và tài liệu hỗ trợ

Chỉ chạy khi có ít nhất một tài liệu hỗ trợ và tất cả evidence đã qua Quality
Gate. Nếu không có tài liệu hỗ trợ, hệ thống bỏ qua đối chiếu nhiều nguồn và
trả `PASS` sau Quality Gate. Kimi Cross-source Conflict Agent chỉ trích xuất
facts và đề xuất mapping; Python mới quyết định kết quả đối chiếu.

1. Agent phải trả đúng một `document_facts` cho mỗi evidence đầu vào. Hệ thống
   cho phép gọi sửa một lần nếu coverage không đúng.
2. Nếu nghiệp vụ không phải mua hoặc nhận hàng (`NOT_APPLICABLE`), đối chiếu
   được xem là đạt.
3. Nếu nghiệp vụ áp dụng đối chiếu, phải có cả chứng từ chính và chứng từ hỗ
   trợ, và cả hai phải có danh sách dòng hàng có thể đối chiếu.
4. Tên hàng có thể được agent map theo ngữ nghĩa. Một dòng tài liệu hỗ trợ chỉ
   được ghép tối đa một dòng chứng từ chính. Dòng không ghép được là
   `NEEDS_HUMAN`.
5. Nhà cung cấp trên tài liệu hỗ trợ phải khớp với chứng từ chính nếu cả hai
   đều có mã số thuế. Nếu không khớp, cần xác nhận hai nguồn có cùng giao dịch.
6. Khi đọc được ngày ở cả hai nguồn, ngày trên tài liệu hỗ trợ không được cách
   ngày chứng từ chính quá 7 ngày. Quá 7 ngày cần xác nhận hai nguồn có cùng
   lô hàng.
7. Trạng thái `RECEIVED_PARTIAL`, `PENDING`, `REJECTED`, hoặc `UNKNOWN` không
   đủ điều kiện xác nhận đã nhận đủ hàng và cần kế toán xử lý.
8. Mọi dòng hàng phải đối chiếu được số lượng và đơn vị. Hệ thống quy đổi
   `g`, `gram`, `kg`, `kilogram`, `tan`, `cai`, `chiec`, `don vi`, `unit` trước
   khi so sánh.
9. Đơn giá và thành tiền phải có ở cả hai nguồn và khớp trong sai số tối đa
   1 VND. Thiếu giá trị hoặc sai khác lớn hơn đều cần kế toán xử lý.
10. Xung đột ngữ nghĩa do Conflict Agent phát hiện chỉ được sử dụng khi dẫn
    chiếu đến evidence thật trong hồ sơ; xung đột dựa trên nội dung nhân viên
    viết bị bỏ qua.

## 8. Bảng quyết định hiện hành

| Tình huống | Kết quả | Hành động |
| --- | --- | --- |
| Không có bill/chứng từ chính | `NEEDS_HUMAN` | Yêu cầu bổ sung chứng từ chính. |
| Có bill nhưng không có description và không có tài liệu hỗ trợ | `NEEDS_HUMAN` | Yêu cầu bổ sung business context. |
| File rỗng, sai định dạng, quá dung lượng hoặc OCR lỗi | Từ chối khi submit hoặc `NEEDS_HUMAN` | Nhân viên cung cấp lại file phù hợp, đọc được. |
| OCR rõ, không có tài liệu hỗ trợ | `PASS` | Chuyển bước kế toán tiếp theo; chưa chạy kiểm kê. |
| OCR có field quan trọng không rõ | `NEEDS_HUMAN` | Kế toán xác nhận đúng field được nêu. |
| OCR chỉ mờ ở field không chặn | `WARN`, có thể `PASS` | Giữ cảnh báo để kế toán tham khảo. |
| Có bill và tài liệu hỗ trợ, một file chưa rõ | `NEEDS_HUMAN` | Dừng trước Conflict Agent và xác nhận file đó. |
| Hai nguồn rõ và thống nhất | `PASS` | Có thể chuyển bước kế toán tiếp theo. |
| Hai nguồn lệch nhà cung cấp, ngày, trạng thái, dòng hàng, số lượng, đơn vị, đơn giá hoặc thành tiền | `NEEDS_HUMAN` | Kế toán xác nhận chênh lệch cụ thể. |
| Conflict/Confidence Agent lỗi hoặc trả sai schema sau retry | `NEEDS_HUMAN` | Xử lý thủ công; không đoán kết quả. |

## 9. Mã rule để truy vết

### Nguồn và OCR

| Rule ID | Khi nào phát sinh |
| --- | --- |
| `MISSING_BILL_EVIDENCE` | Không có chứng từ chính. |
| `MISSING_BUSINESS_CONTEXT` | Không có description và cũng không có tài liệu hỗ trợ. |
| `BILL_EVIDENCE_NOT_READABLE` | Không OCR thành công bất kỳ chứng từ chính nào. |
| `BUSINESS_CONTEXT_NOT_READABLE` | Business context chỉ nằm trong tài liệu hỗ trợ nhưng tài liệu đó không OCR được. |
| `OCR_PROCESSING_ERROR` | Có ít nhất một file gặp lỗi hoặc định dạng chưa được pipeline OCR hỗ trợ. |
| `OCR_CONFIDENCE_ASSESSMENT_INVALID` | Confidence Agent trả candidate không tồn tại trong input. |
| `LOW_CONFIDENCE_BLOCK_UNKNOWN` | Candidate thiếu assessment hoặc bị đánh giá nhiều hơn một lần. |
| `LOW_CONFIDENCE_ASK_HUMAN` | Field quan trọng không thể sử dụng an toàn nếu chưa xác nhận. |
| `OCR_NON_BLOCKING_QUALITY_WARNING` | Field chưa rõ nhưng không chặn policy hiện tại. |
| `OCR_CONFIDENCE_REVIEW` | Không còn vấn đề chất lượng nào cần kế toán xác nhận. |
| `CROSS_SOURCE_CHECK_NOT_APPLICABLE` | Không có tài liệu hỗ trợ; hồ sơ kết thúc sau Quality Gate. |
| `OCR_NOT_CONFIGURED` / `KIMI_NOT_CONFIGURED` | Dịch vụ cần thiết chưa được cấu hình. |
| `CONFIDENCE_AGENT_ERROR` / `CONFLICT_AGENT_ERROR` | Agent không hoàn tất được kết quả hợp lệ. |

### Đối chiếu kiểm kê

| Rule ID | Khi nào phát sinh |
| --- | --- |
| `INVENTORY_EXTRACTION_COVERAGE_INVALID` | Conflict Agent bỏ sót, thêm thừa hoặc trả trùng evidence. |
| `INVENTORY_APPLICABILITY_UNKNOWN` | Chưa xác định được nghiệp vụ có cần đối chiếu nhận hàng hay không. |
| `INVENTORY_NOT_APPLICABLE` | Hồ sơ không thuộc nghiệp vụ nhận/kiểm kê hàng. |
| `INVENTORY_SOURCE_REQUIRED` | Nghiệp vụ áp dụng nhưng thiếu chứng từ chính hoặc file hỗ trợ chính thức. |
| `INVENTORY_SUPPLIER_MISMATCH` | MST nhà cung cấp giữa hai nguồn không khớp. |
| `INVENTORY_DATE_MISMATCH` | Ngày tài liệu hỗ trợ cách ngày chứng từ chính quá 7 ngày. |
| `INVENTORY_RECEIPT_STATUS_CONFLICT` | Hàng nhận một phần, đang chờ hoặc bị từ chối. |
| `INVENTORY_RECEIPT_STATUS_UNKNOWN` | Không xác định được trạng thái nhận hàng. |
| `INVENTORY_ITEMS_REQUIRED` | Một trong hai nguồn thiếu danh sách hàng để đối chiếu. |
| `INVENTORY_ITEM_MAPPING_INVALID` | Agent ánh xạ item không tồn tại hoặc dùng trùng dòng hỗ trợ. |
| `INVENTORY_PRIMARY_ITEM_UNMATCHED` | Dòng trên chứng từ chính không có dòng nhận hàng tương ứng. |
| `INVENTORY_SUPPORTING_ITEM_UNMATCHED` | Dòng trên nguồn nhận hàng không có dòng chứng từ chính tương ứng. |
| `INVENTORY_QUANTITY_UNKNOWN` / `INVENTORY_QUANTITY_MISMATCH` | Thiếu hoặc lệch số lượng sau quy đổi đơn vị. |
| `INVENTORY_UNIT_UNKNOWN` / `INVENTORY_UNIT_MISMATCH` | Thiếu hoặc không tương thích đơn vị tính. |
| `INVENTORY_UNIT_PRICE_UNKNOWN` / `INVENTORY_UNIT_PRICE_MISMATCH` | Thiếu hoặc lệch đơn giá giữa hai nguồn. |
| `INVENTORY_LINE_AMOUNT_UNKNOWN` / `INVENTORY_LINE_AMOUNT_MISMATCH` | Thiếu hoặc lệch thành tiền giữa hai nguồn. |
| `INVENTORY_CONFLICT_REFERENCE_INVALID` | Xung đột dẫn chiếu nguồn không tồn tại trong hồ sơ. |
| `INVENTORY_SEMANTIC_CONFLICT_*` | Hai file có mâu thuẫn ngữ nghĩa cần kế toán xác nhận. |
| `INVENTORY_CONSISTENCY` | Các dữ kiện kiểm kê có thể đối chiếu đều thống nhất. |

## 10. Ngoài phạm vi Sprint 1 hiện tại

Các rule sau được ghi trong `docs/POLICY.md` như kế hoạch, nhưng chưa được
enforce trong pipeline đang chạy và không được tuyên bố là rule thực thi:

- đối chiếu MST bên mua với hồ sơ công ty;
- vendor master, hóa đơn trùng lặp, lịch sử thanh toán;
- danh mục chi phí cấm, chi phí cá nhân, thời hạn nộp;
- hạn mức phê duyệt theo số tiền;
- phát hiện gian lận/bất thường;
- kiểm tra số học trong một hóa đơn và export readiness;
- tách `REQUEST_INFO` và `ESCALATE`, dừng/ghi đè quyết định.

## 11. Nhật ký và truy vết

Mỗi hồ sơ lưu `submission.json`, evidence, kết quả OCR, `processing.json` và
`audit.jsonl` trong thư mục `data/submissions/<case_id>`. Kết quả phải giữ
`rule_id`, `message` và `source_refs` để kế toán truy lại nguồn chứng từ.

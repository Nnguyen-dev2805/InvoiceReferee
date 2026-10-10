# UC-01 Implementation Plan - Đối chiếu mua hàng và nhận hàng

## 1. Trạng thái và mục tiêu

- Mức ưu tiên: sau UC-03.
- Vai trò trong cuộc thi: workflow mở rộng, không phải luồng Track A chính.
- Mục tiêu kỹ thuật: thay policy kiểm kê hiện tại bằng mô hình đối chiếu có mode, document role và dữ liệu từng dòng rõ ràng.
- Điều kiện hoàn thành: ba mode chạy được trên dữ liệu mới; mọi chênh lệch có nguồn; không yêu cầu sai loại tài liệu.

UC-01 không xử lý kiểm kê tồn kho định kỳ, ghi sổ kho, tạo bút toán hay quyết định thanh toán.

## 2. Khoảng cách so với code hiện tại

Code hiện tại có:

- `EvidenceRole.PRIMARY_DOCUMENT/SUPPORTING_DOCUMENT`.
- `InventoryDocumentFacts`, `InventoryAnalysis` và `inventory.py`.
- OCR từng file, Confidence Agent và Conflict Agent.
- Quyết định `PASS/NEEDS_HUMAN`.

Cần bổ sung:

- `case_type` và `reconciliation_mode` trong submission.
- Document role thực tế: PO, invoice, goods receipt, inspection report.
- Critical field theo document type.
- Mô hình ordered/invoiced/received/accepted/rejected.
- PolicyConfig, tolerance và unit conversion.
- Quyết định Track A và uncertainty class.
- Audit chi tiết cho extraction, matching và policy.

## 3. Hợp đồng đầu vào

### 3.1. Submission

```json
{
  "case_type": "PURCHASE_RECEIVING_RECONCILIATION",
  "reconciliation_mode": "THREE_WAY_MATCH",
  "source_type": "PAPER_SCAN",
  "employee": {
    "employee_id": "EMP-DEMO-001",
    "name": "Nguyễn Minh An",
    "department": "Phòng Kinh doanh"
  },
  "business_context": {
    "transaction_reference": "PO-2026-0015",
    "purpose": "Mua thiết bị cho dự án Demo",
    "notes": null
  },
  "documents": []
}
```

### 3.2. Document roles

```text
PURCHASE_ORDER
INVOICE
GOODS_RECEIPT
INSPECTION_REPORT
DELIVERY_NOTE
OTHER_SUPPORTING
```

`EvidenceRole` hiện tại vẫn có thể giữ để tương thích lưu file, nhưng phải bổ sung `document_role` sau bước phân loại. Không suy document role chỉ từ thư mục `primary/supporting`.

### 3.3. Ma trận tài liệu bắt buộc

| Mode | PO | Invoice | Nguồn nhận hàng |
| --- | --- | --- | --- |
| `PO_TO_RECEIPT` | Bắt buộc | Không áp dụng | Bắt buộc |
| `INVOICE_TO_RECEIPT` | Không áp dụng | Bắt buộc | Bắt buộc |
| `THREE_WAY_MATCH` | Bắt buộc | Bắt buộc | Bắt buộc |

Nguồn nhận hàng hợp lệ là một trong `GOODS_RECEIPT`, `INSPECTION_REPORT`, `DELIVERY_NOTE` theo `PolicyConfig`.

## 4. Domain model mục tiêu

Tạo `src/invoice_referee/domain/cases.py`:

```python
class CaseType(StrEnum):
    PURCHASE_RECEIVING_RECONCILIATION = "PURCHASE_RECEIVING_RECONCILIATION"
    ADVANCE_REQUEST = "ADVANCE_REQUEST"
    EXPENSE_SETTLEMENT = "EXPENSE_SETTLEMENT"

class ReconciliationMode(StrEnum):
    PO_TO_RECEIPT = "PO_TO_RECEIPT"
    INVOICE_TO_RECEIPT = "INVOICE_TO_RECEIPT"
    THREE_WAY_MATCH = "THREE_WAY_MATCH"
```

Tạo `src/invoice_referee/domain/reconciliation.py`:

```python
class PurchaseLineFact(BaseModel):
    line_id: str
    document_id: str
    item_code: str | None
    raw_name: str
    normalized_name: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    line_amount: Decimal | None
    condition: str | None
    source_refs: list[str]

class ReconciliationDocumentFacts(BaseModel):
    document_id: str
    document_role: str
    supplier_name: str | None
    supplier_tax_code: str | None
    document_number: str | None
    document_date: date | None
    transaction_references: list[str]
    receipt_status: str | None
    lines: list[PurchaseLineFact]
    total_amount: Decimal | None
    source_refs: list[str]

class ReconciledLine(BaseModel):
    match_id: str
    item_key: str
    po_line_id: str | None
    invoice_line_id: str | None
    receipt_line_ids: list[str]
    ordered_quantity: Decimal | None
    invoiced_quantity: Decimal | None
    received_quantity: Decimal | None
    accepted_quantity: Decimal | None
    rejected_quantity: Decimal | None
    quantity_variance: Decimal | None
    amount_variance: Decimal | None
    match_confidence: Decimal
    match_method: Literal["EXACT_CODE", "NORMALIZED_TEXT", "LLM_SUGGESTED", "HUMAN"]
    source_refs: list[str]
```

Pydantic validator phải cấm số lượng âm và yêu cầu `source_refs` cho mọi giá trị lấy từ chứng từ.

## 5. Critical fields theo tài liệu

| Document role | Critical fields |
| --- | --- |
| `PURCHASE_ORDER` | document number/reference, item name/code, quantity, unit |
| `INVOICE` | seller, invoice number, date, item, quantity khi là hàng hóa, line amount, total amount |
| `GOODS_RECEIPT` | receipt number/date, item, received quantity, unit, receipt status |
| `INSPECTION_REPORT` | item, inspected/accepted/rejected quantity, unit, condition |
| `DELIVERY_NOTE` | delivery reference/date, item, delivered quantity, unit |

MST không phải critical field bắt buộc trên phiếu nhận hàng nội bộ. Criticality được cấu hình theo document role và mode.

## 6. Workflow xử lý

```text
Submit
  -> validate mode/document matrix bằng code
  -> classify document role
  -> OCR từng file scan
  -> collect low-confidence blocks từng file
  -> Confidence Agent một lần cho các candidate của file đó
  -> dừng nếu critical field chưa rõ
  -> extract structured facts từng file
  -> kiểm tra coverage: mọi file cần đối chiếu có facts
  -> resolve transaction identity
  -> normalize units bằng conversion config
  -> propose line matching
  -> deterministic reconciliation
  -> Decision Guard
  -> accounting view + audit
```

### 6.1. Transaction identity

Hai nguồn chỉ được đối chiếu khi có đủ căn cứ cùng giao dịch. Dùng theo thứ tự:

1. PO/reference number trùng chính xác.
2. Supplier identity + khoảng ngày + item overlap.
3. Người dùng xác nhận thủ công.

LLM không được tự khẳng định hai nguồn cùng giao dịch khi reference mâu thuẫn.

### 6.2. Line matching

Thứ tự ghép:

1. `item_code` trùng chính xác.
2. Tên đã normalize và unit trùng.
3. LLM đề xuất semantic pair theo batch.
4. Cặp dưới ngưỡng hoặc một-nhiều mơ hồ được hỏi con người.

Không gọi LLM riêng cho từng dòng. Gửi một payload gồm toàn bộ dòng chưa ghép của các nguồn, giới hạn theo số dòng/token.

### 6.3. Unit conversion

```yaml
unit_conversions:
  - from: thùng
    to: chai
    factor: 24
    item_scope: "Nước suối 500ml"
```

Không sử dụng conversion chung cho mọi mặt hàng. Thiếu factor hoặc item scope thì `FACTUAL_UNKNOWN`.

## 7. Phân chia hardcode, LLM và tool

| Công việc | Thành phần |
| --- | --- |
| Kiểm tra đủ tài liệu theo mode | Python |
| OCR, bbox, word confidence | OCR adapter |
| Đánh giá candidate confidence thấp có ảnh hưởng nghiệp vụ | Confidence LLM, một call/file có candidate |
| Phân loại document role và trích xuất facts | Extraction LLM + Pydantic |
| Chuẩn hóa mã đơn vị đã biết | Python + config |
| Đề xuất ghép tên hàng gần nghĩa | LLM theo batch |
| Tính variance và tolerance | Python `Decimal` |
| Xác định action cuối | Decision Guard |
| Xác nhận cặp ghép mơ hồ hoặc ngoại lệ | Kế toán |

## 8. Policy rules

| Rule ID | Rule | Failure mapping |
| --- | --- | --- |
| `PRR_DOC_001` | Đủ tài liệu theo mode | Thiếu -> `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `PRR_QUALITY_001` | Critical field đọc rõ | Không rõ -> `REQUEST_INFO/FACTUAL_UNKNOWN` |
| `PRR_ID_001` | Các nguồn cùng giao dịch | Chưa đủ căn cứ -> `REQUEST_INFO` |
| `PRR_UNIT_001` | Unit trùng hoặc có conversion xác định | Thiếu conversion -> `REQUEST_INFO` |
| `PRR_QTY_001` | Quantity variance trong tolerance | Vượt rõ -> `ESCALATE/OUTSIDE_POLICY` |
| `PRR_PRICE_001` | Unit price variance trong tolerance nếu áp dụng | Vượt rõ -> `ESCALATE/OUTSIDE_POLICY` |
| `PRR_AMOUNT_001` | Line/total arithmetic nhất quán | Mâu thuẫn -> `REQUEST_INFO` |
| `PRR_DUP_001` | Document identity chưa từng xử lý | Exact duplicate -> `ESCALATE/OUTSIDE_POLICY` |
| `PRR_AUTH_001` | Tổng giá trị trong thẩm quyền | Vượt -> `ESCALATE/BEYOND_AUTHORITY` |

`PolicyConfig` phải xác định tolerance bằng số và đơn vị, ví dụ phần trăm hoặc lượng tuyệt đối; không ghi “chênh lệch nhỏ” bằng văn bản mơ hồ.

## 9. Decision Guard invariants

```text
Thiếu tài liệu bắt buộc -> không AUTO_PROCESS
Critical field UNKNOWN -> không AUTO_PROCESS
Transaction identity UNKNOWN -> không chạy line comparison kết luận
Unit conversion UNKNOWN -> không tính quantity variance
Exact duplicate -> không AUTO_PROCESS
Confirmed outside policy -> ESCALATE
Beyond authority -> ESCALATE
Chỉ AUTO_PROCESS khi mọi required check PASS/NOT_APPLICABLE
```

## 10. UI

### 10.1. Tab Nhân viên

- Chọn “Đối chiếu mua hàng và nhận hàng”.
- Chọn một trong ba mode bằng segmented control.
- Upload zone thay đổi theo mode và ghi đúng tên tài liệu yêu cầu.
- Nhập transaction reference và business purpose.
- Không cho submit khi thiếu nhóm file bắt buộc.

### 10.2. Tab Kế toán

- Header: mode, supplier, references, decision.
- Document matrix: loại tài liệu, trạng thái OCR, critical field.
- Bảng reconciliation từng dòng.
- Bộ lọc `MATCH`, `PARTIAL`, `MISMATCH`, `UNKNOWN`.
- Click số liệu mở đúng file/trang/bbox.
- Câu hỏi kế toán không chứa candidate ID hoặc confidence score kỹ thuật.
- Nút xác nhận kết quả, yêu cầu bổ sung, chuyển ngoại lệ, dừng và ghi đè có lý do.

## 11. Storage và audit

Nâng `submission.json` schema và tạo migration reader cho schema `1.0` hiện tại. Không sửa dữ liệu cũ tại chỗ.

Artifacts:

```text
submission.json
documents/{document_id}/source.*
ocr/{document_id}.json
facts/{document_id}.json
reconciliation.json
decision.json
audit.jsonl
```

Audit thêm `DOCUMENT_CLASSIFIED`, `LINE_MATCH_PROPOSED`, `LINE_MATCH_CONFIRMED`, `RECONCILIATION_COMPUTED`.

## 12. Module triển khai

| File/module | Thay đổi |
| --- | --- |
| `domain/cases.py` | Case type, mode, lifecycle, automation decision |
| `domain/documents.py` | Document role và source references |
| `domain/reconciliation.py` | Facts, matched line, result |
| `application/submit_case.py` | Validate document matrix theo mode |
| `application/process_reconciliation.py` | Orchestrator UC-01 |
| `extraction/document_facts.py` | Adapter extraction schema mới |
| `policy/reconciliation.py` | Rule tất định |
| `policy/decision_guard.py` | Mapping uncertainty/action chung |
| `storage/local_case_store.py` | Schema mới và audit events |
| `app/views/employee_submission.py` | Form UC-01 theo mode |
| `app/views/accounting_review.py` | Reconciliation table và source drill-down |

Không mở rộng tiếp `process_case.py` thành một hàm khổng lồ; dispatcher chọn handler theo `case_type`.

## 13. Thứ tự triển khai

### Phase 1 - Contract

- [ ] Thêm enums và Pydantic models.
- [ ] Thêm PolicyConfig demo có nhãn synthetic.
- [ ] Thêm migration reader cho submission cũ.
- [ ] Viết unit test model và document matrix.

### Phase 2 - Extraction

- [ ] Phân loại document role.
- [ ] Trích xuất facts từng file.
- [ ] Critical field theo role.
- [ ] Kiểm tra extraction coverage.

### Phase 3 - Reconciliation

- [ ] Exact matching.
- [ ] Unit conversion.
- [ ] LLM semantic matching theo batch.
- [ ] Tính variance bằng `Decimal`.
- [ ] Decision Guard.

### Phase 4 - UI và audit

- [ ] Form mode-aware.
- [ ] Accounting reconciliation table.
- [ ] Source drill-down.
- [ ] Human action và audit.

### Phase 5 - Verify

- [ ] Fixture PO-to-receipt pass.
- [ ] Fixture invoice-to-receipt pass.
- [ ] Fixture three-way quantity mismatch.
- [ ] Fixture unit conversion unknown.
- [ ] Fixture critical quantity unreadable.

## 14. Kiểm thử bắt buộc

- Unit: document matrix, unit conversion, tolerance, Decimal arithmetic, Decision Guard.
- Contract: LLM JSON đúng schema, thiếu field phải fail closed.
- Integration: mỗi file OCR đúng một lần; Confidence Agent chỉ chạy khi có candidate.
- Regression: text description không được thay evidence nhận hàng.
- UI: submit theo ba mode, mở source ref và override có audit.
- New-input: ít nhất hai bộ chứng từ chưa dùng khi phát triển.

## 15. Definition of Done

- Ba mode nhận đúng tài liệu và không phát sinh rule mâu thuẫn.
- Mọi quantity/amount trong bảng có source reference.
- Không ghép hoặc quy đổi mơ hồ rồi tự `AUTO_PROCESS`.
- Findings dùng ngôn ngữ kế toán dễ hiểu.
- Kết quả tái lập được từ canonical facts và PolicyConfig mà không gọi lại OCR.
- Test suite và `git diff --check` đạt.

# Đọc biên nhận tiền ứng thành bản nháp — Implementation Plan

**Goal:** Ở bước “Ghi nhận tiền ứng thực nhận”, sau khi kế toán tải chứng từ, hệ
thống đọc thành **bản nháp** (trường + căn cứ) để kế toán rà soát/sửa, rồi bấm
“Ghi nhận kết quả thực tế”. Đọc/upload thành công **không** tự tạo sự kiện tiền.

**Architecture:** Đọc là **bước riêng**, không chạy lại pipeline đề nghị B3. Tận
dụng `Reader` (đường native/OCR hiện có) với grammar `receipt.*` + prompt
`settlement-receipt-extract.txt`; `receipt_reading.build_receipt_draft` (Python
thuần) dựng `B3ReceiptReadView` (facts/proposal/warnings) và lưu bảng
`receipt_reads` (append-only). Xác nhận vẫn qua `record_b3_advance` + guard cũ.

**Status:** IMPLEMENTED (code + tests + docs); UI browser/LIVE chưa chạy.

## Thay đổi

- `contracts/receipt.py`: `RECEIPT_KEYS`, `B3ReceiptFact/Proposal/Warning/ReadView`.
- `prompts/settlement-receipt-extract.txt`: trích trường biên nhận, không kết luận.
- `reader.py`: chọn prompt receipt khi keys có `receipt.*`.
- `receipt_reading.py`: dựng proposal + warnings (payee ghép, scope bank/cash,
  amount vs remaining, trùng sự kiện). Tên giống ≠ cùng người.
- `service.read_b3_advance_receipt` + store `receipt_reads` (schema + save/list).
- API `POST/GET /api/cases/{id}/b3-advance-receipt-reads`; schema request.
- UI `AdvanceReceiptPanel`: tự đọc sau upload, prefill draft, hiện tên file/trạng
  thái/cảnh báo, nút Đọc lại, nhập tay khi lỗi; kết quả đọc muộn không ghi đè sửa
  của người dùng (editSeq/draftKey).

## Verification

- `pytest tests/settlement/test_b3_receipt_reading.py` (13) + `test_b3_funding*`.
- Full: backend **534 passed**, frontend **159 passed**, build OK, golden identical.
- Giới hạn: chưa chạy UI browser / LIVE; `USER_UI_UNEXECUTED`, `LIVE_UNEXECUTED`.

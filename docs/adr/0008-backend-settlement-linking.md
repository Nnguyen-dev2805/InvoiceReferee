# ADR0008 — Backend tự liên kết hồ sơ quyết toán (chốt 14/10/2026)

## Quyết định

Nhân viên nộp tài liệu, kiểm tra bản nháp rồi nộp — **backend** xác định hồ sơ
tạm ứng/công việc liên quan. Bỏ việc bắt nhân viên chọn "hoạt động" thường trực
trong luồng thông thường; UI chỉ hỏi khi liên kết chưa đủ chắc chắn.

## Căn cứ và ranh giới

- Bốn kết quả: `LINKED` (căn cứ mạnh chỉ đúng một hồ sơ), `NEEDS_CONFIRMATION`
  (chỉ căn cứ yếu — nhân viên xác nhận trong phạm vi), `NOT_FOUND` (tiếp nhận
  hồ sơ độc lập, không bịa ngân sách/grant), `CONFLICT` (căn cứ mạnh chỉ tới
  các hồ sơ khác nhau — giữ mâu thuẫn cho kế toán, không chọn theo thứ tự ưu
  tiên, không lấy phần tử đầu danh sách).
- Thứ tự căn cứ mạnh: A kế thừa liên kết server-owned → B số hồ sơ/tạm ứng in
  trên tài liệu (đúng công ty, đúng nhân viên/phạm vi, có namespace duy nhất)
  → C mã giao dịch/số phiếu đã có trong lịch sử (định danh có namespace).
  D (tên/nội dung/ngày/số tiền giống nhau) chỉ tạo ứng viên, không tự liên kết
  kể cả khi chỉ có một ứng viên. Hai khoản ứng cùng người/cùng số tiền vẫn
  phân biệt được; ngày/số tiền chỉ đối chiếu, không phải định danh.
- `exact equality` của purpose/name không phải cơ chế tự gắn.
- Quy tắc trên áp dụng cho **liên kết bản quyết toán với hồ sơ tạm ứng đã có**.
  Việc kế toán bổ sung một biên nhận ứng sau đó có quyết định riêng
  `MULTI_FIELD_MATCH` theo [ADR0011](0011-multifield-advance-link.md); không mở
  rộng liên kết quyết toán yếu thành tự động.
- Activity identity vẫn tồn tại ở backend (scope quyền/chính sách/lịch sử); root giữ
  invariant `(organization, employee, activity)`. Rebind vào hồ sơ đã tồn tại
  là conflict (tiếp tục hồ sơ đó), không ghi đè/xóa ngầm, không chuyển
  sources/ledger ngầm. Ngày chưa biết giữ chưa biết.
- LLM trích xuất (`advance_reference`, `transaction_reference` kèm quote refs);
  code kiểm và quyết định. Không LLM tự quyết liên kết/công nhận tiền.

## Ứng thực nhận đi kèm

- Giữ `event_at` chứng từ; `recorded_at` là giờ máy chủ. Người nhận phải là
  nhân viên hồ sơ; bên chi phải là nguồn quỹ công ty đã cấu hình (tên tổ chức
  trong context hoặc id `company:*`) — không hard-code một công ty cho mọi
  context, không tự thay người nhận bằng nhân viên hồ sơ.
- `external_key` phải có namespace; thiếu thì giữ chưa giải quyết, không bịa
  UUID. Cùng key tải lại là idempotent; cùng key khác payload trọng yếu
  (kind/amount/payer/payee/scope) là conflict; khác namespace là giao dịch khác.
- Upload/OCR thành công chưa phải confirmed money; `PENDING`/`FAILED`/`UNKNOWN`
  không thành ứng thực nhận; chứng từ do nhân viên tải lên chưa tự confirmed —
  kế toán xác nhận có trách nhiệm theo quyền/scope.

The accountant's upload-to-root binding, source retention, and separate work
acceptance and history-coverage facts are specified in
[ADR0010](0010-accountant-advance-and-coverage.md). Opening a root alone does not
prove that a later advance voucher belongs to it.

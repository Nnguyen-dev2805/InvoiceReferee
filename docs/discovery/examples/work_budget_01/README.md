# Packet giả lập 01 — Ngân sách tổng và quyết toán

Ngày tạo: 09/10/2026. **Toàn bộ tổ chức, người, nhà cung cấp, mã, quyết định và giao dịch ở đây là giả lập**, không lấy thông tin người thật. Markdown/CSV là nguồn mô tả sự kiện cho walkthrough, không ảnh hóa đơn/bank document đã được xác thực. Không có pipeline, OCR hoặc người dùng thật đã chạy trên packet này.

## Hai mốc độc lập

| Mốc | Chỉ dùng các nguồn này | Nội dung xem xét |
| --- | --- | --- |
| M1 — 08/10/2026 18:00 +07:00 | [Đề nghị/bảng kê](employee_claim.md), [quyền và quyết định trước chi](authority_and_pretrip.md), [chứng từ giả lập](expense_and_payment_sources.md), [nguồn tài chính](financial_events_m1.csv), [phạm vi M1](coverage_m1.md), policy snapshot theo manifest | Đối chiếu/quyết toán trước quyết định và chi thêm |
| M2 — 09/10/2026 10:00 +07:00 | Toàn bộ M1 + [nguồn mới M2](decision_and_receipt_m2.md) | Quyết định, actualreceipt và điều kiện đóng sau thực hiện |

[Đáp án walkthrough](expected_walkthrough.md) để riêng, **không phải đầu vào nguồn hoặc prompt**. File M2 không thuộc input M1. Những tên file/mốc ở đây là hướng dẫn thao tác bằng tay, chưa chứng minh application/harness đã chặn nguồn tương lai.

## Phiên bản thiết kế dùng trong ví dụ

Bundle `DESIGN-REPLAY-WORK-BUDGET-01` giữ snapshot policy ngân sách tổng, evidence R4.2, ba vai và intake contract; [manifest](policy_manifest.json) ghi đường dẫn nguồn và SHA256. Mỗi snapshot được giữ nguyên byte; relative links bên trong hiểu theo đường dẫn source trong manifest. Ngày trong nội dung là dòng thời gian **giả lập**, không tuyên bố policy thực đã hoạt động tại công ty vào các ngày đó.

Freeze này chỉ để tái dựng walkthrough. **Không là B1 runtime baseline, gold holdout hoặc policy live đã kích hoạt.** Nếu đổi policy cho ví dụ khác thì tạo bundle mới, không sửa snapshot/đáp án để làm kết quả đạt. Scope giao quyền trong packet chỉ thuộc trường hợp minh họa này, không tự trở thành cấu hình toàn MVP.

## Cách đi bằng tay

1. Đọc input M1 và policy snapshot, tự lập khoản/source/payer/history trước khi xem expected.
2. So với expected; nếu bất đồng ghi fact/rule cụ thể, không lấy output AI làm đúng mặc định.
3. Bổ sung riêng input M2, kiểm tra hiệu lực quyết định và actualreceipt; không xóa gross history.
4. Chỉ đưa vào R5 sau khi rà soát đáp án/coverage độc lập và công bố đây là dữ liệu tổng hợp. Một walkthrough không thay >=15 case hoặc professional-user trials.

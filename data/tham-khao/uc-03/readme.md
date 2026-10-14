# Bộ testcase UC-03 hoàn ứng và quyết toán tạm ứng

Toàn bộ tài liệu là dữ liệu giả lập, không có giá trị pháp lý hoặc kế toán.

## Dùng bộ này trên nhánh final

Đây là corpus **tham khảo Hoangha v1**, gồm 25 case/65 PDF. Các nhãn và
`expected.json` dưới đây giữ hợp đồng cũ, **không phải oracle nghiệp vụ của final**.
`COVERED/GAP_EXPECTED` không có nghĩa đã chạy PASS trong final.

**Mapping mục tiêu hiện tại khi mở rộng ngoài công tác:**
[v3 giữ PDF gốc](final-case-mapping-v3.json), cùng
[đặc tả policy và mẫu giấy chung](../../../docs/superpowers/specs/2026-10-14-general-expense-policy-and-form.md).
V3 là authoring metadata, chưa có 25 packet context/gold thực thi và không được
runtime/model nạp làm facts. Các giá trị tiền là kỳ vọng có điều kiện, không phải
facts đã đọc/xác minh trong một lượt chạy final.

[Bảng v2](CASE_MAPPING_FINAL.md) và
[JSON v2](final-case-mapping.json) là phương án **trước đây** khi final chỉ nhận
công tác; một số mục từng yêu cầu chuyển nội dung mua sắm/tiếp khách thành chuyến
công tác. Không dùng các bước chuyển ấy cho PDF gốc trong mục tiêu v3.

Một số giấy là tiếp khách/mua thiết bị, và form gốc không ghi chuyến công tác.
Giữ nguyên nguồn; hồ sơ thuộc profile công việc tương ứng. Các rule mới và
25 packet test chưa được tích hợp/chạy chỉ vì mapping v3 đã được viết.

`manifest.json.folder` đã được chỉnh theo folder không dấu có thật. Nhãn/rule legacy
được giữ, kể cả drift metadata TC19/TC20 đã ghi trong bảng chuyển đổi.

## Cách nộp theo giao diện Hoangha cũ

Phần này giữ hướng dẫn lịch sử. Với `final`, dùng luồng intake hiện tại và bảng
mapping ở trên; không coi tên menu/trạng thái dưới đây là hợp đồng UI final.

- Chọn `Quyết toán tạm ứng` và `Đơn giấy`.
- Tải `report_hoan_ung.pdf` làm đơn/báo cáo chính.
- Tải toàn bộ file PDF còn lại trong thư mục case làm evidence.
- `expected.json` là oracle nghiệp vụ, không tải vào hệ thống.
- File DOCX là nguồn có thể chỉnh sửa; PDF là bản dùng để OCR.
- Từ TC16, một report có nhiều dòng và nhiều evidence. Evidence có thể là hóa đơn,
  tài liệu thay thế hoặc không tồn tại nếu report đã khai báo lý do.
- `line_support_expectations` trong `expected.json` là mapping chuẩn giữa từng dòng
  report và các file chứng minh tương ứng.

## Danh sách case

| Case | Tình huống | Kết quả mong đợi | Trạng thái triển khai |
| --- | --- | --- | --- |
| TC01 | Hợp lệ nhân viên hoàn trả tiền thừa | AUTO_PROCESS | COVERED |
| TC02 | Hợp lệ công ty thanh toán thêm | AUTO_PROCESS | COVERED |
| TC03 | Hợp lệ không phát sinh chênh lệch | AUTO_PROCESS | COVERED |
| TC04 | Hợp lệ nhiều mặt hàng thiết bị | AUTO_PROCESS | COVERED |
| TC05 | Tổng các dòng trên báo cáo không khớp | REQUEST_INFO / SET_PAPER_TOTAL_001 | COVERED |
| TC06 | Chênh lệch quyết toán ghi sai | REQUEST_INFO / SET_SETTLEMENT_DIFF_001 | COVERED |
| TC07 | Số tiền bằng chữ trên báo cáo không khớp | REQUEST_INFO / SET_PAPER_CONSISTENCY_001 | COVERED |
| TC08 | Báo cáo và hóa đơn lệch số tiền | REQUEST_INFO / SET_PAPER_AMOUNT_001 | COVERED |
| TC09 | Mã số thuế người mua thuộc công ty khác | ESCALATE / SET_BUYER_TAX_001 | GAP_EXPECTED |
| TC10 | Hóa đơn thiếu mã số thuế người mua | REQUEST_INFO / SET_REQUIRED_FIELD_001 | GAP_EXPECTED |
| TC11 | Số học trên hóa đơn không nhất quán | REQUEST_INFO / SET_ARITH_001 | GAP_EXPECTED |
| TC12 | Hóa đơn trùng định danh với hồ sơ trước | ESCALATE / SET_DUP_001 | GAP_EXPECTED |
| TC13 | Khoản chi rượu bia cần chuyển policy | ESCALATE / SET_CATEGORY_001 | GAP_EXPECTED |
| TC14 | Tổng hồ sơ vượt thẩm quyền 100 triệu | ESCALATE / SET_AUTH_001 | COVERED |
| TC15 | Evidence cùng số tiền nhưng sai nội dung | REQUEST_INFO / SET_PAPER_MATCH_001 | COVERED |
| TC16 | Hợp lệ ba hóa đơn trong một báo cáo công tác | AUTO_PROCESS | GAP_EXPECTED |
| TC17 | Hợp lệ hóa đơn kèm vé điện tử thay thế | AUTO_PROCESS | GAP_EXPECTED |
| TC18 | Hợp lệ một dòng dùng hai tài liệu thay thế | AUTO_PROCESS | GAP_EXPECTED |
| TC19 | Thiếu chứng từ và không có lý do cho một dòng | REQUEST_INFO / SET_EVIDENCE_REASON_001 | GAP_EXPECTED |
| TC20 | Có lý do cho dòng không có chứng từ | ESCALATE / SET_NO_INVOICE_EXCEPTION_001 | GAP_EXPECTED |
| TC21 | Một hóa đơn được khai báo nhưng chưa đính kèm | REQUEST_INFO / SET_EVIDENCE_MISSING_001 | GAP_EXPECTED |
| TC22 | Một hóa đơn bị dùng vượt giá trị cho hai dòng | REQUEST_INFO / SET_EVIDENCE_REUSE_001 | GAP_EXPECTED |
| TC23 | Hợp lệ một hóa đơn phân bổ cho nhiều dòng | AUTO_PROCESS | GAP_EXPECTED |
| TC24 | Có hóa đơn đính kèm nhưng không xuất hiện trên report | REQUEST_INFO / SET_UNREFERENCED_EVIDENCE_001 | GAP_EXPECTED |
| TC25 | Tài liệu thay thế lệch số tiền với report | REQUEST_INFO / SET_ALTERNATIVE_AMOUNT_001 | GAP_EXPECTED |

`GAP_EXPECTED` là testcase chủ đích cho rule chưa triển khai đầy đủ. Case này
được giữ trong bộ regression để tránh nhầm khoảng trống sản phẩm thành happy path.

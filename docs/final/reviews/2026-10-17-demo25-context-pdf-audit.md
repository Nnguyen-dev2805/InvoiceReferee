# Demo25 — kiểm tra context/PDF ngày17/10/2026

Phạm vi: đọc text đủ65PDF/25case, đối chiếu manifestSHA256, README, context riêng và context chung. Không gọi OCR/LLM; không chạy25caseLIVE. Không sửa PDF để làm xanh. Kiểm tra nội dung/ngày/số liệu; không phải nghiệm thu hiển thị mọi trangPDF hay kết quả model.

## Cập nhật

- Context chung,50context riêng, TC01 tương thích và script sinh cùng mốc17/10/2026 23:59:59+07:00. Đồng bộ cả witness observed_at/quote; trước đó chỉ context chung được đổi horizon, witness còn16/10.
- Mọi ngày giao dịch thực trên65PDF là10/10; ứng trong context05/10; quyền/chính sách hiệu lực01/10–31/12. Không đổi ngày chứng từ sang17/10.
- Số ứng, số tiền, mục đích, actor, quyền8/4/20triệu, profile và lỗi cố ý giữ nguyên. Kiểm recursive diff xác nhận213giá trị đổi chỉ là mốc thời gian/witness quote.
- Test context có boundary: dùng được trưa/cuối17/10, không được coi bao phủ00:00ngày18/10. Không tắt guard thời gian.
- PDF hoàn760k mới theo yêu cầu người dùng được lưu ởoutput/pdf; là mô phỏng, nằm ngoài65PDF đầu vào/manifest25case.

## Kiểm tra theo case

PASS dưới đây chỉ là dữ liệu đầu vào/context phù hợp nhau và hash đúng; không nghĩa hồ sơ phải được duyệt.

| Case | PDF | Chi khai (đ) | Ứng context (đ) | Ngày PDF | Đối chiếu |
|---|---:|---:|---:|---|---|
| TC01 | 2 | 3,240,000 | 4,000,000 | 2026-10-10 | PASS |
| TC02 | 2 | 5,400,000 | 5,000,000 | 2026-10-10 | PASS |
| TC03 | 2 | 4,320,000 | 4,320,000 | 2026-10-10 | PASS |
| TC04 | 2 | 83,600,000 | 85,000,000 | 2026-10-10 | PASS |
| TC05 | 2 | 3,700,000 | 4,500,000 | 2026-10-10 | PASS |
| TC06 | 2 | 2,970,000 | 3,800,000 | 2026-10-10 | PASS |
| TC07 | 2 | 3,780,000 | 4,800,000 | 2026-10-10 | PASS |
| TC08 | 2 | 3,284,000 | 4,200,000 | 2026-10-10 | PASS |
| TC09 | 2 | 2,916,000 | 3,600,000 | 2026-10-10 | PASS |
| TC10 | 2 | 3,628,800 | 4,600,000 | 2026-10-10 | PASS |
| TC11 | 2 | 5,500,000 | 6,000,000 | 2026-10-10 | PASS |
| TC12 | 2 | 3,240,000 | 4,000,000 | 2026-10-10 | PASS |
| TC13 | 2 | 2,160,000 | 3,000,000 | 2026-10-10 | PASS |
| TC14 | 2 | 121,000,000 | 120,000,000 | 2026-10-10 | PASS |
| TC15 | 2 | 2,700,000 | 3,000,000 | 2026-10-10 | PASS |
| TC16 | 4 | 10,260,000 | 12,000,000 | 2026-10-10 | PASS |
| TC17 | 4 | 5,600,000 | 6,000,000 | 2026-10-10 | PASS |
| TC18 | 4 | 4,200,000 | 5,000,000 | 2026-10-10 | PASS |
| TC19 | 3 | 3,500,000 | 4,000,000 | 2026-10-10 | PASS |
| TC20 | 3 | 1,480,000 | 2,000,000 | 2026-10-10 | PASS |
| TC21 | 3 | 14,040,000 | 15,000,000 | 2026-10-10 | PASS |
| TC22 | 3 | 8,100,000 | 9,000,000 | 2026-10-10 | PASS |
| TC23 | 3 | 8,640,000 | 9,000,000 | 2026-10-10 | PASS |
| TC24 | 4 | 2,700,000 | 3,000,000 | 2026-10-10 | PASS |
| TC25 | 4 | 4,140,000 | 5,000,000 | 2026-10-10 | PASS |

## Những điều kiện còn giữ nguyên

- TC02/TC11 trùng mục đích “Mua thiết bị văn phòng phục vụ hoạt động công ty”; tiền ứng5triệu/6triệu khác nhau nhưng rule yếu theo nội dung có thể gợi ý cảhai. Không tự nối bằng số tiền và không đổi mô tả nếu chưa được yêu cầu.
- TC06 ghi770k thay vì830k: giữFACT lệch60k. TC07 bằng chữ4,04triệu khác số3,78triệu. TC08 report3,284triệu khác invoice3,024triệu. TC11 invoice5,5triệu khác tiền hàng+thuế5,4triệu. TC25 phiếu thu700k khác khai900k.
- TC09 MST người mua7777777777; TC10 thiếu MST; không sửa thành đúng tổ chức để ép pass.
- TC12 cần hồ sơ trước dùng invoiceTC01 để kiểm trùng; context không tự tạo lịch sử sử dụng.
- TC18 nghiệm thu Phúc An nhưng chuyển khoản ghi người nhận An Thịnh; thiếu thống nhất bên nhận cần xác minh, bộ chứng từ không tự độngPASS.
- TC03/các hồ sơTRAVEL vẫn có thể thiếu địa điểm/khoảng thời gian công tác trên giấy. Context không tự bù trip_start/end. TC19/20/21 giữ thiếu chứng từ; TC22 giữ phân bổ vượt; TC24 giữ tài liệu ngoài kê khai.
- Case vượt quyền vẫn cần xử lý đúng8/4/20triệu; không làm cả25case tự độngPASS.

## Bằng chứng

`.runtime/dataset-audit-20261017/pdf-texts.json` giữ text/hash65file; audit.json giữ đối chiếu25case. context-red.log → context-green.log (7PASS) gồm expiry boundary, isolated import/restart, generator repeatability, independent amounts and manifest hashes. Fullsuite kết quả ghi bổ sung sau khi chạy xong. Không resetDB/restartserver/push/deploy trong lượt này.

Full backend cuối: 1046PASS/6FAIL (1052total); đúng6tên lỗi baseline trước sửa thuế/context. Không thêm xfail hoặc nới guard. Test context cũ đã được cập nhật theo ngày fixture được người dùng yêu cầu, có đối chứng hết hạn ngày18/10.

- `tests.integration.test_employee_return_draft_api::test_employee_return_upload_is_durable_but_does_not_record_R`
- `tests.integration.test_employee_return_draft_api::test_accountant_confirmation_records_one_instruction_bound_return`
- `tests.integration.test_employee_return_draft_api::test_pending_second_return_cannot_confirm_after_collect_is_fulfilled`
- `tests.integration.test_employee_return_draft_api::test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction`
- `tests.integration.test_employee_return_draft_api::test_overpaid_return_is_recorded_but_raises_a_specific_blocker`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]`

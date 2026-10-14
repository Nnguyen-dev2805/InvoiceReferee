# Chuyển bộ UC03 Hoangha sang final — mapping đủ 25 case

**Ngày:** 14/10/2026. **Trạng thái:** MAPPING_COMPLETE; chưa tạo biến thể PDF/context/gold final, chưa chạy OCR/LLM/workflow. Đây là bản thiết kế chuyển case, không phải oracle mà runtime được phép đọc.

## 1. Điều đã kiểm và điều giữ nguyên

- Đã nạp 25 expected.json và đọc text của 65/65 PDF, mỗi file một trang; xem render mẫu TC01/TC16/TC20/TC23. Native text dùng riêng cho authoring audit; app vẫn OCR mọi source. Không claim visual QA toàn corpus hoặc model quality.
- Giữ nguyên 65 PDF, mọi DOCX và 25 expected.json cũ. Manifest chỉ sửa `folder` theo folder không dấu có thật; metadata legacy vẫn giữ để truy vết.
- [manifest.json](manifest.json) và [final-case-mapping.json](final-case-mapping.json) giúp tìm đúng nguồn và mapping. JSON mapping chỉ là authoring metadata, không được nạp vào model/app để suy fact hoặc output.
- `COVERED/GAP_EXPECTED` là nhãn Hoangha, không phải test PASS của final. Không chạy bộ chấm theo expected cũ rồi gọi đó là final evaluation.

## 2. Hai tầng kỳ vọng và một rào chắn chung

**Tầng đọc nguồn:** giữ loại/field literal/refs/cardinality/số học và những nguồn mâu thuẫn. Model không sửa số sai trên giấy; code so sánh sau. Kết quả extraction rõ khác với admissibility tài chính.

**Tầng nghiệp vụ:** chỉ tạo yêu cầu chi/thu sau khi đủ căn cứ T/E/A/P/R, hoạt động, ngân sách, quyền và usage. S = E − A − P + R. Routine không chờ kế toán phê duyệt lại eligibility; thực hiện tiền do con người và ghi actual riêng.

**Rào chắn raw corpus:** các form cũ không ghi rõ `trip_start/trip_end`; nhiều case còn khác phạm vi công tác. Profile SETTLEMENT_FORM hiện yêu cầu trip destination/start/end/purpose. Expected literal là NOT_PRESENT, không lấy ngày lập 10/10/2026 làm ngày công tác. Vì vậy không đóng gold matching end-to-end bằng cách bịa metadata để tất cả form CLEAR. Muốn kiểm lỗi đặc thù từng case, phải tạo source variant có profile hợp lệ hoặc kiểm matcher ở component level được công bố rõ.

**Rào chắn runtime hiện tại:** `_publish_evidence_report` và `_assess_and_commit` giữ LIVE/REPLAY ở EVIDENCE_READY, `assessment_ready=false`, chưa có finance admission. Các kết quả WAITING/READY_TO_EXECUTE/SETTLED bên dưới là mục tiêu sau plan finance, không phải dự đoán run hiện tại.

## 3. Common context phải bổ sung trước oracle nghiệp vụ

- Hồ sơ/employee/activity server-scoped, cùng một người và một hoạt động.
- Nguồn SETTLEMENT_FORM ghi trip destination/start/end/purpose; không suy trip từ ngày lập.
- Activity authorized, budget riêng có thời hạn/version, grant công nhận E<=8 triệu và phát instruction abs(S)<=4 triệu, cấp demo<=20 triệu đúng action/scope/time.
- Employee-paid basis: responsible employee confirmation+service evidence trong ngưỡng Q32; trên ngưỡng cần căn cứ tiền/xác nhận tài chính riêng.
- A là completed employee advance được kế toán xác minh/binding; printed advance không là actual.
- P/R zero cần coverage đủ, opening balances và fund scope; không lấy absence file làm zero.
- Không expense usage/reservation khác, trừ case duplicate12.
- Current LIVE/REPLAY boundary EVIDENCE_READY/conclusionNone/no instruction trước plan finance/admissibility.

Mọi context bổ sung là **đầu vào synthetic có trách nhiệm/provenance**, tách khỏi gold. Không tạo fake ngân hàng thật, không cho model đọc gold, không tự phát grant bằng cách sửa persona. Thời điểm test/as-of phải cố định; hoạt động/grant/budget/ledger có cùng scope và thời hạn. Người dùng không phải nhập mã backend; demo session cấp identity từ server.

### Cách đọc nhãn mục tiêu trong bảng

- `COLLECT` / `PAY`: tạo yêu cầu thu lại / chi thêm; không đồng nghĩa tiền đã thực hiện.
- `BALANCED`: đã cân bằng khi đủ căn cứ, không tạo yêu cầu số 0.
- `FACT`: cần xác định dữ kiện; `AUTHORITY`: cần người đủ quyền; `POLICY` chỉ khi rule hiệu lực thật sự yêu cầu quyết định ngoại lệ.
- `*_REQUIRED`, `FACT_THEN_*`: nhãn thiết kế để giữ dependency/chỗ chưa khóa oracle, không phải enum mới được đưa vào app.
- Cột mục tiêu chỉ có hiệu lực **sau chuyển source/context và triển khai admission**. Bản gốc vẫn là corpus tham khảo với các thiếu sót đã chỉ ra.

## 4. Bảng chuyển đổi 25 case

| Case | Logic giữ | Kỳ vọng Hoangha | Phạm vi nguồn gốc | Mục tiêu final sau chuyển nguồn/context |
| --- | --- | --- | --- | --- |
| [TC01](tc01-hop-le-nhan-vien-hoan-tra-tien-thua/expected.json) | Giữ kết quả thu lại tiền ứng thừa | `AUTO_PROCESS` | Tiếp khách địa phương | `COLLECT` — Nếu E=3.240.000/A=4.000.000/P=R=0 đã đủ căn cứ: READY_TO_EXECUTE, COLLECT 760.000; nhận tiền hoàn rồi mới SETTLED. |
| [TC02](tc02-hop-le-cong-ty-thanh-toan-them/expected.json) | Giữ kết quả công ty chi thêm | `AUTO_PROCESS` | Mua thiết bị | `PAY` — Nếu biến thể E=5.400.000/A=5.000.000/P=R=0 đủ căn cứ: READY_TO_EXECUTE, PAY 400.000. Bản máy in gốc không được coi là routine công tác. |
| [TC03](tc03-hop-le-khong-phat-sinh-chenh-lech/expected.json) | Giữ cân bằng không tạo yêu cầu số 0 | `AUTO_PROCESS` | Công tác | `BALANCED` — Nếu E=A=4.320.000 và P=R=0 verified: S=0, BALANCED/SETTLED, không instruction, không execution OPEN/UNKNOWN. |
| [TC04](tc04-hop-le-nhieu-mat-hang-thiet-bi/expected.json) | Giữ nhiều mặt hàng và số lớn | `AUTO_PROCESS` | Mua thiết bị | `AUTHORITY` — Sau khi scope/facts đủ: E=83.600.000 vượt 8 triệu, cũng vượt cấp demo 20 triệu; không routine, không instruction, cần cấp có quyền ngoài demo. |
| [TC05](tc05-tong-cac-dong-tren-bao-cao-khong-khop/expected.json) | Giữ lỗi tổng bảng kê | `REQUEST_INFO` | Tiếp khách địa phương | `FACT` — S chưa được khẳng định; WAITING/FACT về totals, không instruction. Không chọn 3.000.000/3.240.000/3.500.000 chỉ theo model confidence. |
| [TC06](tc06-chenh-lech-quyet-toan-ghi-sai/expected.json) | Giữ chênh lệch trên giấy ghi sai | `REQUEST_INFO` | Tiếp khách địa phương | `FACT` — FACT về printed settlement; 760.000 là phép tính tham chiếu khi E/A verified, chưa khẳng định balance trước giải quyết conflict. Printed_return không phải R đã nhận. |
| [TC07](tc07-so-tien-bang-chu-tren-bao-cao-khong-khop/expected.json) | Giữ số bằng chữ khác số bằng số | `REQUEST_INFO` | Tiếp khách địa phương | `FACT` — FACT blocking tổng/chữ theo contract §12.3 đã chốt amount_words critical; không instruction. Source hiện gán NON_CRITICAL là implementation drift cần sửa trước oracle runtime, không mở lại contract. |
| [TC08](tc08-bao-cao-va-hoa-don-lech-so-tien/expected.json) | Giữ bảng kê và invoice lệch tiền | `REQUEST_INFO` | Tiếp khách địa phương | `FACT` — FACT về cost value/binding, không invoice-match PASS rồi tự dùng E=3.500.000 hoặc E=3.240.000. |
| [TC09](tc09-ma-so-thue-nguoi-mua-thuoc-cong-ty-khac/expected.json) | Giữ buyer identity mâu thuẫn | `ESCALATE` | Tiếp khách địa phương | `FACT` — FACT về identity/binding trước. POLICY chỉ nếu rulebook đã có điều kiện buyer bắt buộc và facts rõ; không map ESCALATE cũ thành POLICY mặc định. |
| [TC10](tc10-hoa-don-thieu-ma-so-thue-nguoi-mua/expected.json) | Giữ trường bắt buộc/thiếu dữ liệu | `REQUEST_INFO` | Tiếp khách địa phương | `PROFILE_RULE_REQUIRED` — Chỉ khóa FACT nếu profile/admissibility thực sự yêu cầu MST này; nếu optional thì notice và đánh giá binding bằng nguồn khác. Hiện chưa freeze financial oracle. |
| [TC11](tc11-so-hoc-tren-hoa-don-khong-nhat-quan/expected.json) | Giữ số học nội bộ invoice sai | `REQUEST_INFO` | Mua thiết bị | `FACT` — FACT nội bộ invoice; không tự sửa total thành 5.400.000, không issue instruction theo 5.500.000. |
| [TC12](tc12-hoa-don-trung-dinh-danh-voi-ho-so-truoc/expected.json) | Giữ kiểm trùng economic obligation qua hai lần nộp | `ESCALATE` | Tiếp khách địa phương | `REUSE_NO_SECOND_INSTRUCTION` — Lần hai không phát hành obligation/instruction mới; giữ owner canonical và audit reuse/block. Không mặc định gian lận hoặc POLICY chỉ vì trùng byte. |
| [TC13](tc13-khoan-chi-ruou-bia-can-chuyen-policy/expected.json) | Giữ không hoàn trả chi cá nhân và vẫn thu lại ứng | `ESCALATE` | Chi cá nhân rõ | `EXCLUDED_COLLECT_ADVANCE` — Nếu toàn bộ khoản rõ là cá nhân: disposition EXCLUDED, E=0; A=3.000.000/P=R=0 verified thì COLLECT 3.000.000, không 840.000. Không buộc POLICY để phê duyệt khoản bị loại rõ. |
| [TC14](tc14-tong-ho-so-vuot-tham-quyen-100-trieu/expected.json) | Giữ vượt quyền lớn dù số phải chi nhỏ | `ESCALATE` | Mua thiết bị | `AUTHORITY` — E=121.000.000 verified vượt quyền công nhận 8 triệu và cấp demo 20 triệu dù S=1 triệu; không instruction, cấp ngoài demo. |
| [TC15](tc15-evidence-cung-so-tien-nhung-sai-noi-dung/expected.json) | Giữ cùng số tiền nhưng khác nghiệp vụ/reference | `REQUEST_INFO` | Sửa chữa thiết bị | `FACT` — FACT binding; equal amount hoặc LLM promote suggestion không đủ activity/expense admission. Không chọn document theo filename. |
| [TC16](tc16-hop-le-ba-hoa-don-trong-mot-bao-cao-cong-tac/expected.json) | Giữ ba khoản/matching đúng nhưng finance vượt ngưỡng | `AUTO_PROCESS` | Công tác | `AUTHORITY` — Với E=10.260.000/A=12.000.000: S=-1.740.000 là arithmetic khi verified, nhưng cần quyền công nhận E>8 triệu. Cấp demo <=20 triệu có thể quyết đúng grant; sau đó mới COLLECT. |
| [TC17](tc17-hop-le-hoa-don-kem-ve-dien-tu-thay-the/expected.json) | Giữ nhiều loại chứng từ có thể đủ thay invoice VAT | `AUTO_PROCESS` | Tiếp khách/cuộc họp | `ROLE_ADMISSION_REQUIRED` — Nếu cả 3 khoản có service evidence/payer đủ theo profile: E=5.600.000/A=6.000.000 => COLLECT 400.000. Không tự POLICY vì tài liệu không có chữ hóa đơn VAT. |
| [TC18](tc18-hop-le-mot-dong-dung-hai-tai-lieu-thay-the/expected.json) | Giữ một khoản có nhiều tài liệu bổ trợ không cộng trùng | `AUTO_PROCESS` | Sửa chữa thiết bị | `FACT_PAYEE_AND_ROLE` — Chưa tự AUTO theo old gold. Giữ bank payer và recipient literal; FACT payee/binding nếu chưa rõ. Sau happy-variant đủ service/payer: E=4.200.000/A=5.000.000 => COLLECT 800.000, không 5.700.000 hay chỉ 2.700.000. |
| [TC19](tc19-thieu-chung-tu-va-khong-co-ly-do-cho-mot-dong/expected.json) | Giữ thiếu chứng từ một dòng không ép unknown thành 0 | `REQUEST_INFO` | Công tác/khảo sát | `FACT` — FACT service/expense căn cứ dòng 800.000; không instruction cho tổng bị ảnh hưởng, không tự thu 1.300.000 từ E chỉ 2.700.000, không tự công nhận E=3.500.000. |
| [TC20](tc20-co-ly-do-cho-dong-khong-co-chung-tu/expected.json) | Giữ lý do thiếu chứng từ nhưng không biến lời giải thích thành tài chính | `ACCOUNTANT_REVIEW` | Công tác/khảo sát | `FACT_THEN_POLICY_IF_RULE` — FACT về service/value dòng 100.000 trước; POLICY chỉ khi đã đủ facts và có rule/exception path nhận thiếu chứng từ. Không tự E=1.380.000 hoặc E=1.480.000; lời lý do không tự tạo exemption. |
| [TC21](tc21-mot-hoa-don-duoc-khai-bao-nhung-chua-dinh-kem/expected.json) | Giữ khai số hóa đơn nhưng thiếu đúng file | `REQUEST_INFO` | Tổ chức hội nghị | `FACT_THEN_AUTHORITY` — FACT thiếu invoice00002103. Sau đủ source/finance E=14.040.000 verified cần AUTHORITY>8 triệu; câu hỏi thuộc dữ kiện có thể làm trước decision phụ thuộc. |
| [TC22](tc22-mot-hoa-don-bi-dung-vuot-gia-tri-cho-hai-dong/expected.json) | Giữ phân bổ vượt giá trị một invoice | `REQUEST_INFO` | Mua/lắp thiết bị | `FACT_THEN_AUTHORITY` — FACT allocation bound; không 2 lần source total. Nếu sửa nguồn và E cuối8.100.000 verified thì AUTHORITY>8 triệu; nếu total giảm theo nguồn khác, recompute không pin nhãn cũ. |
| [TC23](tc23-hop-le-mot-hoa-don-phan-bo-cho-nhieu-dong/expected.json) | Giữ allocation đúng nhưng quyền finance khác | `AUTO_PROCESS` | Vật tư văn phòng | `AUTHORITY` — Matching/allocation đúng nhưng E=8.640.000 vượt8 triệu; S=-360.000 verified không đủ làm routine. Cấp đúng grant<=20 triệu quyết sau. |
| [TC24](tc24-co-hoa-don-dinh-kem-nhung-khong-xuat-hien-tren-report/expected.json) | Giữ nguồn đính kèm dư không silently discard | `REQUEST_INFO` | Công tác | `FACT_UNTIL_RELEVANCE_CLEAR` — FACT relevance ban đầu; không cộng thêm1.080.000 và không xóa source. Nếu xác minh unrelated/personal: quarantine/exclude có reason, E=2.700.000/A3.000.000 => COLLECT300.000. Nếu liên quan, revise rồi assess lại. |
| [TC25](tc25-tai-lieu-thay-the-lech-so-tien-voi-report/expected.json) | Giữ chứng từ dịch vụ khác invoice VAT và amount mismatch | `REQUEST_INFO` | Công tác | `FACT` — FACT amount dòng3; không áp POLICY chỉ vì là phiếu thu. Không tự dùng printed_return860.000 hay repaired balance1.060.000 trước recheck nguồn/correction. |

## 5. Chi tiết từng case: giữ nguồn nào, sửa gì, hỏi ai

### TC01 — Hợp lệ nhân viên hoàn trả tiền thừa

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc01-hop-le-nhan-vien-hoan-tra-tien-thua/report_hoan_ung.pdf); [gold Hoangha](tc01-hop-le-nhan-vien-hoan-tra-tien-thua/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc tổng 3.240.000, ứng khai 4.000.000, số hoàn in 760.000; ref 00000101. Invoice chỉ nêu phương thức chuyển khoản, không chứng minh employee đã trả.
**Chuyển source:** Tạo biến thể bữa ăn phục vụ chuyến công tác; giữ 10 suất, đơn giá 300.000, VAT 240.000, tổng 3.240.000. Bổ sung trip trên giấy.
**Kỳ vọng nghiệp vụ có điều kiện:** Nếu E=3.240.000/A=4.000.000/P=R=0 đã đủ căn cứ: READY_TO_EXECUTE, COLLECT 760.000; nhận tiền hoàn rồi mới SETTLED.
**Issue owner:** không có khi routine đủ căn cứ. Kế toán thực hiện/ghi tiền theo instruction; khi thiếu payer/A, hệ thống tạo FACT đúng người theo field, không gán owner mặc định cho routine.
**Biến thể dự kiến:** `UC03-F01`; chưa tạo, không thay namespace/source gốc.

### TC02 — Hợp lệ công ty thanh toán thêm

**Mục đích trên PDF:** Mua thiết bị văn phòng phục vụ hoạt động công ty.
**Nguồn:** [đơn gốc](tc02-hop-le-cong-ty-thanh-toan-them/report_hoan_ung.pdf); [gold Hoangha](tc02-hop-le-cong-ty-thanh-toan-them/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc máy in văn phòng, tổng 5.400.000, ứng khai 5.000.000, phần chi thêm in 400.000; ref 00000201.
**Chuyển source:** Bản gốc dùng evidence-only. Tạo biến thể chi phí lưu trú công tác tổng 5.400.000, giữ số tiền/cấu trúc VAT, thay cả bảng kê và invoice; không chỉ đổi context.
**Kỳ vọng nghiệp vụ có điều kiện:** Nếu biến thể E=5.400.000/A=5.000.000/P=R=0 đủ căn cứ: READY_TO_EXECUTE, PAY 400.000. Bản máy in gốc không được coi là routine công tác.
**Issue owner:** không có khi routine đủ căn cứ. Execution accountant khác issue owner; thiếu phạm vi mới tạo FACT đúng trách nhiệm.
**Biến thể dự kiến:** `UC03-F02`; chưa tạo, không thay namespace/source gốc.

### TC03 — Hợp lệ không phát sinh chênh lệch

**Mục đích trên PDF:** Chi phí lưu trú trong chuyến công tác.
**Nguồn:** [đơn gốc](tc03-hop-le-khong-phat-sinh-chenh-lech/report_hoan_ung.pdf); [gold Hoangha](tc03-hop-le-khong-phat-sinh-chenh-lech/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc phòng nghỉ 4 đêm, trước thuế 4.000.000/VAT 320.000/tổng 4.320.000; ứng khai 4.320.000, số chênh in 0.
**Chuyển source:** Giữ chi phí lưu trú; bổ sung nơi đến/ngày đi-về, xác nhận nhân viên trả, A thực nhận và coverage P/R. Không suy trip từ ngày lập đơn.
**Kỳ vọng nghiệp vụ có điều kiện:** Nếu E=A=4.320.000 và P=R=0 verified: S=0, BALANCED/SETTLED, không instruction, không execution OPEN/UNKNOWN.
**Issue owner:** không có ở balanced đủ căn cứ. Nếu thiếu coverage, FACT thuộc kế toán; không lấy giấy ghi 0 thay coverage.
**Biến thể dự kiến:** `UC03-F03`; chưa tạo, không thay namespace/source gốc.

### TC04 — Hợp lệ nhiều mặt hàng thiết bị

**Mục đích trên PDF:** Mua thiết bị máy tính cho nhân viên.
**Nguồn:** [đơn gốc](tc04-hop-le-nhieu-mat-hang-thiet-bi/report_hoan_ung.pdf); [gold Hoangha](tc04-hop-le-nhieu-mat-hang-thiet-bi/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc tổng 83.600.000/ứng 85.000.000, chênh khai 1.400.000; nhiều item không tự thành nhiều lần chi.
**Chuyển source:** Bản thiết bị giữ evidence-only. Muốn test finance tạo biến thể chi công tác nhiều khoản giữ tổng; phải có confirmation tài chính/paid basis độc lập vì E>8 triệu.
**Kỳ vọng nghiệp vụ có điều kiện:** Sau khi scope/facts đủ: E=83.600.000 vượt 8 triệu, cũng vượt cấp demo 20 triệu; không routine, không instruction, cần cấp có quyền ngoài demo.
**Owner/câu hỏi hoặc hành động:** `HIGHER_AUTHORITY` — Ai có quyền công nhận chi phí 83.600.000 và tạo yêu cầu thu 1.400.000 cho hoạt động này? Không giả sẵn grant trên 20 triệu.
**Biến thể dự kiến:** `UC03-F04`; chưa tạo, không thay namespace/source gốc.

### TC05 — Tổng các dòng trên báo cáo không khớp

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc05-tong-cac-dong-tren-bao-cao-khong-khop/report_hoan_ung.pdf); [gold Hoangha](tc05-tong-cac-dong-tren-bao-cao-khong-khop/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ 2 dòng 2.000.000 + 1.000.000 = 3.000.000; printed_total 3.500.000; invoice gross 3.240.000. Model đọc literal, không sửa số nguồn.
**Chuyển source:** Tạo biến thể hai khoản công tác nhưng giữ đồng thời ba số và invoice_refs; cung cấp các căn cứ chung để lỗi totals được kiểm riêng.
**Kỳ vọng nghiệp vụ có điều kiện:** S chưa được khẳng định; WAITING/FACT về totals, không instruction. Không chọn 3.000.000/3.240.000/3.500.000 chỉ theo model confidence.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Bảng kê cộng 3.000.000, tổng ghi 3.500.000, hóa đơn ghi 3.240.000: hãy sửa bảng kê/nguồn tương ứng và xác định số nào đúng, gồm hay chưa gồm thuế.
**Biến thể dự kiến:** `UC03-F05`; chưa tạo, không thay namespace/source gốc.

### TC06 — Chênh lệch quyết toán ghi sai

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc06-chenh-lech-quyet-toan-ghi-sai/report_hoan_ung.pdf); [gold Hoangha](tc06-chenh-lech-quyet-toan-ghi-sai/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc 3.240.000/4.000.000/printed_return 700.000 và chữ 700.000; arithmetic reference là 760.000, không ghi đè printed_return.
**Chuyển source:** Chuyển dịch vụ sang chi phí chuyến công tác, giữ sai lệch 700.000 so với 760.000. Đảm bảo ledger chưa có return 700.000.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT về printed settlement; 760.000 là phép tính tham chiếu khi E/A verified, chưa khẳng định balance trước giải quyết conflict. Printed_return không phải R đã nhận.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Ứng 4.000.000 và chi 3.240.000 chênh 760.000, đơn ghi 700.000: đây là lỗi khai số phải hoàn hay đã có giao dịch hoàn một phần? Bổ sung/sửa đúng loại căn cứ.
**Biến thể dự kiến:** `UC03-F06`; chưa tạo, không thay namespace/source gốc.

### TC07 — Số tiền bằng chữ trên báo cáo không khớp

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc07-so-tien-bang-chu-tren-bao-cao-khong-khop/report_hoan_ung.pdf); [gold Hoangha](tc07-so-tien-bang-chu-tren-bao-cao-khong-khop/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ printed_total 3.240.000 và amount_words chỉ 3.500.000; không chuẩn hóa thành cùng giá trị.
**Chuyển source:** Tạo biến thể công tác giữ nguyên mâu thuẫn chữ-số; test admission semantic consistency riêng, không gọi đây là lỗi OCR.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT blocking tổng/chữ theo contract §12.3 đã chốt amount_words critical; không instruction. Source hiện gán NON_CRITICAL là implementation drift cần sửa trước oracle runtime, không mở lại contract.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Tổng bằng số 3.240.000 nhưng bằng chữ 3.500.000: hãy sửa đơn và xác nhận tổng đúng với chứng từ.
**Biến thể dự kiến:** `UC03-F07`; chưa tạo, không thay namespace/source gốc.

### TC08 — Báo cáo và hóa đơn lệch số tiền

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc08-bao-cao-va-hoa-don-lech-so-tien/report_hoan_ung.pdf); [gold Hoangha](tc08-bao-cao-va-hoa-don-lech-so-tien/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ claim 3.500.000, invoice 3.240.000, printed_return 500.000; ref exact vẫn có thể AUTO_LINK nhưng không chứng minh amounts khớp.
**Chuyển source:** Biến thể công tác; giữ exact reference và lệch 260.000 để kiểm tách matching khỏi admission.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT về cost value/binding, không invoice-match PASS rồi tự dùng E=3.500.000 hoặc E=3.240.000.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Khoản kê 3.500.000 và hóa đơn 3.240.000 lệch 260.000: có chi phí bổ sung nào có căn cứ hay bảng kê sai?
**Biến thể dự kiến:** `UC03-F08`; chưa tạo, không thay namespace/source gốc.

### TC09 — Mã số thuế người mua thuộc công ty khác

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc09-ma-so-thue-nguoi-mua-thuoc-cong-ty-khac/report_hoan_ung.pdf); [gold Hoangha](tc09-ma-so-thue-nguoi-mua-thuoc-cong-ty-khac/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ buyer name công ty An Thịnh nhưng MST 7777777777, context công ty 0319999996; không thay MST từ context vào OCR fact.
**Chuyển source:** Biến thể công tác giữ buyer mismatch; freeze predicate identity/activity trước gold business, không tự thêm quy định thuế.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT về identity/binding trước. POLICY chỉ nếu rulebook đã có điều kiện buyer bắt buộc và facts rõ; không map ESCALATE cũ thành POLICY mặc định.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — MST trên hóa đơn 7777777777 khác công ty 0319999996 dù tên giống: tài liệu thuộc đúng hoạt động không và cần nhà cung cấp sửa gì?
**Biến thể dự kiến:** `UC03-F09`; chưa tạo, không thay namespace/source gốc.

### TC10 — Hóa đơn thiếu mã số thuế người mua

**Mục đích trên PDF:** Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026.
**Nguồn:** [đơn gốc](tc10-hoa-don-thieu-ma-so-thue-nguoi-mua/report_hoan_ung.pdf); [gold Hoangha](tc10-hoa-don-thieu-ma-so-thue-nguoi-mua/expected.json).
**Kỳ vọng đọc/đối chiếu:** buyer_tax_code=NOT_PRESENT trên invoice; không lấy từ request/context để điền. Giữ các trường khác đọc được.
**Chuyển source:** Biến thể công tác; xác định field importance/requiredness của E_INVOICE trước golden business. Không biến thiếu informational field thành FACT bắt buộc.
**Kỳ vọng nghiệp vụ có điều kiện:** Chỉ khóa FACT nếu profile/admissibility thực sự yêu cầu MST này; nếu optional thì notice và đánh giá binding bằng nguồn khác. Hiện chưa freeze financial oracle.
**Owner/câu hỏi hoặc hành động:** `ACCOUNTANT` — Nếu MST cần cho binding: hóa đơn thiếu MST bên mua, hãy bổ sung bản sửa hoặc xác nhận identity bằng căn cứ được profile nhận.
**Biến thể dự kiến:** `UC03-F10`; chưa tạo, không thay namespace/source gốc.

### TC11 — Số học trên hóa đơn không nhất quán

**Mục đích trên PDF:** Mua thiết bị văn phòng phục vụ hoạt động công ty.
**Nguồn:** [đơn gốc](tc11-so-hoc-tren-hoa-don-khong-nhat-quan/report_hoan_ung.pdf); [gold Hoangha](tc11-so-hoc-tren-hoa-don-khong-nhat-quan/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ subtotal 5.000.000 + tax 400.000 nhưng total 5.500.000; printed/request 5.500.000 không làm invoice tự nhất quán.
**Chuyển source:** Gốc máy in evidence-only; biến thể dịch vụ công tác giữ subtotal/tax/printed_total sai.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT nội bộ invoice; không tự sửa total thành 5.400.000, không issue instruction theo 5.500.000.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Tiền hàng 5.000.000 + thuế 400.000 = 5.400.000, hóa đơn ghi 5.500.000: bổ sung invoice sửa đúng từ nhà cung cấp.
**Biến thể dự kiến:** `UC03-F11`; chưa tạo, không thay namespace/source gốc.

### TC12 — Hóa đơn trùng định danh với hồ sơ trước

**Mục đích trên PDF:** Chi phí tiếp khách lần nộp thứ hai.
**Nguồn:** [đơn gốc](tc12-hoa-don-trung-dinh-danh-voi-ho-so-truoc/report_hoan_ung.pdf); [gold Hoangha](tc12-hoa-don-trung-dinh-danh-voi-ho-so-truoc/expected.json).
**Kỳ vọng đọc/đối chiếu:** Invoice trùng số/issuer/date/amount TC01; phải đọc đúng cả hai submission. Byte hash chỉ là signal, không phải economic identity tự đủ.
**Chuyển source:** Dùng hai lần nộp của cùng UC03-F01, cùng người/hoạt động; dựng usage/reservation hoặc instruction trước trong runtime context, không chỉ tải file đơn lẻ.
**Kỳ vọng nghiệp vụ có điều kiện:** Lần hai không phát hành obligation/instruction mới; giữ owner canonical và audit reuse/block. Không mặc định gian lận hoặc POLICY chỉ vì trùng byte.
**Owner/câu hỏi hoặc hành động:** `ACCOUNTANT` — Chỉ hỏi nếu scope/usage chưa rõ: hóa đơn này đã dùng ở hồ sơ trước nào, cùng hoạt động và phần chi đã được xử lý chưa?
**Biến thể dự kiến:** `UC03-F12`; chưa tạo, không thay namespace/source gốc.

### TC13 — Khoản chi rượu bia cần chuyển policy

**Mục đích trên PDF:** Mua đồ uống phục vụ cá nhân sau giờ làm.
**Nguồn:** [đơn gốc](tc13-khoan-chi-ruou-bia-can-chuyen-policy/report_hoan_ung.pdf); [gold Hoangha](tc13-khoan-chi-ruou-bia-can-chuyen-policy/expected.json).
**Kỳ vọng đọc/đối chiếu:** Request ghi phục vụ cá nhân sau giờ làm; invoice rượu 2.160.000; giữ A khai 3.000.000 và chênh khai 840.000 nhưng không coi chúng là actual.
**Chuyển source:** Đặt nguồn chi cá nhân vào root công tác có activity/A/coverage hợp lệ; không đổi nguồn thành chi công việc. Không thêm blanket ban rượu ngoài rulebook.
**Kỳ vọng nghiệp vụ có điều kiện:** Nếu toàn bộ khoản rõ là cá nhân: disposition EXCLUDED, E=0; A=3.000.000/P=R=0 verified thì COLLECT 3.000.000, không 840.000. Không buộc POLICY để phê duyệt khoản bị loại rõ.
**Issue owner:** không có trên nhánh loại cá nhân rõ, đủ A/P/R. Kế toán chỉ là execution actor. Nếu có claim ngoại lệ mới, tạo issue theo rule riêng, không đưa thành câu hỏi bắt buộc cho case này.
**Biến thể dự kiến:** `UC03-F13`; chưa tạo, không thay namespace/source gốc.

### TC14 — Tổng hồ sơ vượt thẩm quyền 100 triệu

**Mục đích trên PDF:** Mua máy chủ phục vụ hệ thống nội bộ.
**Nguồn:** [đơn gốc](tc14-tong-ho-so-vuot-tham-quyen-100-trieu/report_hoan_ung.pdf); [gold Hoangha](tc14-tong-ho-so-vuot-tham-quyen-100-trieu/expected.json).
**Kỳ vọng đọc/đối chiếu:** Đọc máy chủ, invoice 121.000.000/ứng khai 120.000.000/chênh khai 1.000.000.
**Chuyển source:** Giữ gốc evidence-only; biến thể chi công tác lớn nếu cần test authority, bổ sung independent financial basis vì E>8 triệu. Không mang cap 100 triệu của Hoangha.
**Kỳ vọng nghiệp vụ có điều kiện:** E=121.000.000 verified vượt quyền công nhận 8 triệu và cấp demo 20 triệu dù S=1 triệu; không instruction, cấp ngoài demo.
**Owner/câu hỏi hoặc hành động:** `HIGHER_AUTHORITY` — Cần cấp có quyền công nhận chi phí 121.000.000; không chỉ kiểm yêu cầu chi thêm 1.000.000.
**Biến thể dự kiến:** `UC03-F14`; chưa tạo, không thay namespace/source gốc.

### TC15 — Evidence cùng số tiền nhưng sai nội dung

**Mục đích trên PDF:** Sửa chữa máy in văn phòng.
**Nguồn:** [đơn gốc](tc15-evidence-cung-so-tien-nhung-sai-noi-dung/report_hoan_ung.pdf); [gold Hoangha](tc15-evidence-cung-so-tien-nhung-sai-noi-dung/expected.json).
**Kỳ vọng đọc/đối chiếu:** Request sửa máy in/ref SC-2026-15, invoice vé máy bay/ref 00001501 đều 2.700.000; giữ hai descriptions/refs riêng.
**Chuyển source:** Gốc repair evidence-only; biến thể claim khách sạn nhưng attachment vé máy bay giữ amount 2.700.000 để test sai liên kết trong scope công tác.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT binding; equal amount hoặc LLM promote suggestion không đủ activity/expense admission. Không chọn document theo filename.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Khoản kê và chứng từ đều 2.700.000 nhưng nội dung/reference khác: hãy gắn đúng chứng từ cho từng khoản hoặc sửa khai báo.
**Biến thể dự kiến:** `UC03-F15`; chưa tạo, không thay namespace/source gốc.

### TC16 — Hợp lệ ba hóa đơn trong một báo cáo công tác

**Mục đích trên PDF:** Hoàn ứng chi phí chuyến công tác Đà Nẵng.
**Nguồn:** [đơn gốc](tc16-hop-le-ba-hoa-don-trong-mot-bao-cao-cong-tac/report_hoan_ung.pdf); [gold Hoangha](tc16-hop-le-ba-hoa-don-trong-mot-bao-cao-cong-tac/expected.json).
**Kỳ vọng đọc/đối chiếu:** Ba dòng 4.320.000 + 5.400.000 + 540.000 = 10.260.000, refs 00001601/2/3; một-một, không đếm tổng invoice lần hai.
**Chuyển source:** Giữ nội dung Đà Nẵng, thêm ngày công tác vào nguồn; finance actor xác nhận paid E, A=12.000.000/coverage; không dùng employee-only Q32 cho E>8 triệu.
**Kỳ vọng nghiệp vụ có điều kiện:** Với E=10.260.000/A=12.000.000: S=-1.740.000 là arithmetic khi verified, nhưng cần quyền công nhận E>8 triệu. Cấp demo <=20 triệu có thể quyết đúng grant; sau đó mới COLLECT.
**Owner/câu hỏi hoặc hành động:** `AUTHORIZED_APPROVER` — Có cấp đúng quyền công nhận chi phí 10.260.000 cho chuyến này không? Không hỏi lại chứng từ đã rõ chỉ vì vượt grant.
**Biến thể dự kiến:** `UC03-F16`; chưa tạo, không thay namespace/source gốc.

### TC17 — Hợp lệ hóa đơn kèm vé điện tử thay thế

**Mục đích trên PDF:** Hoàn ứng chi phí tiếp khách và tổ chức cuộc họp.
**Nguồn:** [đơn gốc](tc17-hop-le-hoa-don-kem-ve-dien-tu-thay-the/report_hoan_ung.pdf); [gold Hoangha](tc17-hop-le-hoa-don-kem-ve-dien-tu-thay-the/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ hai invoice 3.240.000/2.160.000 và vé bãi xe 200.000. Loại legacy E_TICKET không tự là TRANSPORT_TICKET; đọc nội dung và vai trò.
**Chuyển source:** Chuyển thành tiếp khách trong chuyến công tác, giữ số và parking voucher; thêm binding service/activity. Freeze loại/role dựa nguồn (không chỉ alias E_TICKET).
**Kỳ vọng nghiệp vụ có điều kiện:** Nếu cả 3 khoản có service evidence/payer đủ theo profile: E=5.600.000/A=6.000.000 => COLLECT 400.000. Không tự POLICY vì tài liệu không có chữ hóa đơn VAT.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Chỉ hỏi khoản thiếu service/use/payment identity; vé bãi xe không tự chứng minh passenger hay nhân viên đã trả.
**Biến thể dự kiến:** `UC03-F17`; chưa tạo, không thay namespace/source gốc.

### TC18 — Hợp lệ một dòng dùng hai tài liệu thay thế

**Mục đích trên PDF:** Hoàn ứng sửa chữa máy in văn phòng.
**Nguồn:** [đơn gốc](tc18-hop-le-mot-dong-dung-hai-tai-lieu-thay-the/report_hoan_ung.pdf); [gold Hoangha](tc18-hop-le-mot-dong-dung-hai-tai-lieu-thay-the/expected.json).
**Kỳ vọng đọc/đối chiếu:** Invoice 2.700.000; acceptance và bank cùng mô tả nhân công 1.500.000. Hai supporting docs không tạo 3.000.000 chi phí. Bank ghi recipient company An Thịnh, thiếu binding rõ tới trung tâm Phúc An.
**Chuyển source:** Gốc repair evidence-only; biến thể dịch vụ công tác giữ mẫu một dòng có hai nguồn hỗ trợ, làm rõ payee trong nguồn nếu muốn happy path. Biến thể giữ ambiguous payee là negative FACT riêng.
**Kỳ vọng nghiệp vụ có điều kiện:** Chưa tự AUTO theo old gold. Giữ bank payer và recipient literal; FACT payee/binding nếu chưa rõ. Sau happy-variant đủ service/payer: E=4.200.000/A=5.000.000 => COLLECT 800.000, không 5.700.000 hay chỉ 2.700.000.
**Owner/câu hỏi hoặc hành động:** `ACCOUNTANT` — Giao dịch 1.500.000 thực tế vào tài khoản nhà cung cấp dịch vụ nào? Vì sao source ghi người nhận công ty An Thịnh?
**Biến thể dự kiến:** `UC03-F18`; chưa tạo, không thay namespace/source gốc.

### TC19 — Thiếu chứng từ và không có lý do cho một dòng

**Mục đích trên PDF:** Hoàn ứng chuyến khảo sát khách hàng.
**Nguồn:** [đơn gốc](tc19-thieu-chung-tu-va-khong-co-ly-do-cho-mot-dong/report_hoan_ung.pdf); [gold Hoangha](tc19-thieu-chung-tu-va-khong-co-ly-do-cho-mot-dong/expected.json).
**Kỳ vọng đọc/đối chiếu:** Hai invoice 2.160.000/540.000; dòng ăn trưa 800.000 không file/lý do. Row NO_EVIDENCE không nghĩa cost=0 hay EXCLUDED.
**Chuyển source:** Giữ bản gốc, bổ sung activity dates/finance context cho các phần đã rõ để cô lập thiếu service evidence 800.000.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT service/expense căn cứ dòng 800.000; không instruction cho tổng bị ảnh hưởng, không tự thu 1.300.000 từ E chỉ 2.700.000, không tự công nhận E=3.500.000.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Khoản ăn trưa 800.000 chưa có chứng từ dịch vụ: hãy bổ sung tài liệu phù hợp hoặc nguồn xác minh được policy chấp nhận.
**Biến thể dự kiến:** `UC03-F19`; chưa tạo, không thay namespace/source gốc.

**Drift metadata cũ:** {"rule": {"manifest": "SET_EVIDENCE_REASON_001", "case_expected": "SET_PAPER_EVIDENCE_REQUIRED"}}. Giữ cả hai để đối chiếu; không dùng manifest legacy làm gold final.

### TC20 — Có lý do cho dòng không có chứng từ

**Mục đích trên PDF:** Hoàn ứng chuyến khảo sát hiện trường.
**Nguồn:** [đơn gốc](tc20-co-ly-do-cho-dong-khong-co-chung-tu/report_hoan_ung.pdf); [gold Hoangha](tc20-co-ly-do-cho-dong-khong-co-chung-tu/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ nhiên liệu 1.080.000 + vé phí đường bộ 300.000 + gửi xe thiếu nguồn 100.000 có lý do. Note là declaration, không receipt.
**Chuyển source:** Giữ gốc và bổ sung trip/ledger. Không tạo giấy/form giải trình mới; dùng câu hỏi typed đã giữ theo Q33.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT về service/value dòng 100.000 trước; POLICY chỉ khi đã đủ facts và có rule/exception path nhận thiếu chứng từ. Không tự E=1.380.000 hoặc E=1.480.000; lời lý do không tự tạo exemption.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Bãi xe không phát hành chứng từ cho khoản 100.000: có nguồn xác minh dịch vụ/số tiền nào được policy nhận? Sau đủ facts mới hỏi người có quyền ngoại lệ nếu cần.
**Biến thể dự kiến:** `UC03-F20`; chưa tạo, không thay namespace/source gốc.

**Drift metadata cũ:** {"decision": {"manifest": "ESCALATE", "case_expected": "ACCOUNTANT_REVIEW"}, "rule": {"manifest": "SET_NO_INVOICE_EXCEPTION_001", "case_expected": "SET_PAPER_EVIDENCE_EXCEPTION"}}. Giữ cả hai để đối chiếu; không dùng manifest legacy làm gold final.

### TC21 — Một hóa đơn được khai báo nhưng chưa đính kèm

**Mục đích trên PDF:** Hoàn ứng chi phí tổ chức hội nghị.
**Nguồn:** [đơn gốc](tc21-mot-hoa-don-duoc-khai-bao-nhung-chua-dinh-kem/report_hoan_ung.pdf); [gold Hoangha](tc21-mot-hoa-don-duoc-khai-bao-nhung-chua-dinh-kem/expected.json).
**Kỳ vọng đọc/đối chiếu:** Giữ refs 00002101/2/3; invoice nước uống 1.080.000 chưa nộp, total14.040.000/ứng15.000.000. Không điền từ gold vào nguồn.
**Chuyển source:** Gốc hội nghị giữ evidence-only; biến thể hội nghị gắn chuyến công tác cần scope rõ, hoặc profile riêng chưa bật.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT thiếu invoice00002103. Sau đủ source/finance E=14.040.000 verified cần AUTHORITY>8 triệu; câu hỏi thuộc dữ kiện có thể làm trước decision phụ thuộc.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Bảng kê ghi invoice00002103 nước uống 1.080.000 nhưng thiếu file: hãy nộp đúng source. Sau đó kiểm lại grant công nhận E.
**Biến thể dự kiến:** `UC03-F21`; chưa tạo, không thay namespace/source gốc.

### TC22 — Một hóa đơn bị dùng vượt giá trị cho hai dòng

**Mục đích trên PDF:** Hoàn ứng mua và lắp đặt thiết bị mạng.
**Nguồn:** [đơn gốc](tc22-mot-hoa-don-bi-dung-vuot-gia-tri-cho-hai-dong/report_hoan_ung.pdf); [gold Hoangha](tc22-mot-hoa-don-bi-dung-vuot-gia-tri-cho-hai-dong/expected.json).
**Kỳ vọng đọc/đối chiếu:** Invoice00002201=5.400.000 bị dùng cho L01 5.400.000 + L02 2.160.000 =7.560.000; vận chuyển540.000 riêng.
**Chuyển source:** Gốc giữ evidence-only; biến thể công tác giữ split+over-allocation 2.160.000 và total8.100.000, không đổi lỗi thành hai invoices khác.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT allocation bound; không 2 lần source total. Nếu sửa nguồn và E cuối8.100.000 verified thì AUTHORITY>8 triệu; nếu total giảm theo nguồn khác, recompute không pin nhãn cũ.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Hai dòng cùng invoice5.400.000 nhưng phân bổ7.560.000: dòng2 có chứng từ riêng hay bị khai trùng?
**Biến thể dự kiến:** `UC03-F22`; chưa tạo, không thay namespace/source gốc.

### TC23 — Hợp lệ một hóa đơn phân bổ cho nhiều dòng

**Mục đích trên PDF:** Hoàn ứng mua vật tư văn phòng.
**Nguồn:** [đơn gốc](tc23-hop-le-mot-hoa-don-phan-bo-cho-nhieu-dong/report_hoan_ung.pdf); [gold Hoangha](tc23-hop-le-mot-hoa-don-phan-bo-cho-nhieu-dong/expected.json).
**Kỳ vọng đọc/đối chiếu:** Invoice00002301=3.240.000 phân L01 2.160.000 + L02 1.080.000; invoice00002302=5.400.000; tổng8.640.000.
**Chuyển source:** Gốc office vật tư giữ evidence-only; biến thể công tác cùng activity/claimant, giữ tỷ lệ allocation và số tiền; cần independent financial confirmation vì E>8 triệu.
**Kỳ vọng nghiệp vụ có điều kiện:** Matching/allocation đúng nhưng E=8.640.000 vượt8 triệu; S=-360.000 verified không đủ làm routine. Cấp đúng grant<=20 triệu quyết sau.
**Owner/câu hỏi hoặc hành động:** `AUTHORIZED_APPROVER` — Cần cấp đúng quyền công nhận chi phí8.640.000, không hỏi chia invoice lại vì allocation đã đúng.
**Biến thể dự kiến:** `UC03-F23`; chưa tạo, không thay namespace/source gốc.

### TC24 — Có hóa đơn đính kèm nhưng không xuất hiện trên report

**Mục đích trên PDF:** Hoàn ứng chuyến công tác ngắn ngày.
**Nguồn:** [đơn gốc](tc24-co-hoa-don-dinh-kem-nhung-khong-xuat-hien-tren-report/report_hoan_ung.pdf); [gold Hoangha](tc24-co-hoa-don-dinh-kem-nhung-khong-xuat-hien-tren-report/expected.json).
**Kỳ vọng đọc/đối chiếu:** Hai row tổng2.700.000; thêm invoice00002409 ăn uống cá nhân1.080.000 không có row. Giữ unmatched_source và nội dung.
**Chuyển source:** Giữ gốc, bổ sung dates/ctx. Test hai phản hồi có căn cứ: đính nhầm/không liên quan vs bỏ sót khoản của hoạt động.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT relevance ban đầu; không cộng thêm1.080.000 và không xóa source. Nếu xác minh unrelated/personal: quarantine/exclude có reason, E=2.700.000/A3.000.000 => COLLECT300.000. Nếu liên quan, revise rồi assess lại.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Invoice00002409 trị giá1.080.000 không có trong bảng kê: đính nhầm, khoản cá nhân hay khoản công tác bỏ sót?
**Biến thể dự kiến:** `UC03-F24`; chưa tạo, không thay namespace/source gốc.

### TC25 — Tài liệu thay thế lệch số tiền với report

**Mục đích trên PDF:** Hoàn ứng chi phí công tác tỉnh.
**Nguồn:** [đơn gốc](tc25-tai-lieu-thay-the-lech-so-tien-voi-report/report_hoan_ung.pdf); [gold Hoangha](tc25-tai-lieu-thay-the-lech-so-tien-voi-report/expected.json).
**Kỳ vọng đọc/đối chiếu:** Rows1.080.000/2.160.000/900.000; collection receipt row3 ghi700.000, payer Nguyễn Minh An; giữ900 vs700 và identityPT-251026-016.
**Chuyển source:** Giữ gốc, thêm dates/ctx. Phân loại phiếu thu theo nội dung, không hard-code legacy RECEIPT; conflict200.000 là lỗi chính.
**Kỳ vọng nghiệp vụ có điều kiện:** FACT amount dòng3; không áp POLICY chỉ vì là phiếu thu. Không tự dùng printed_return860.000 hay repaired balance1.060.000 trước recheck nguồn/correction.
**Owner/câu hỏi hoặc hành động:** `EMPLOYEE` — Dòng di chuyển kê900.000 nhưng phiếu thu700.000: có thêm200.000 được chứng minh hay bạn cần sửa bảng kê?
**Biến thể dự kiến:** `UC03-F25`; chưa tạo, không thay namespace/source gốc.

## 6. Những thay đổi không được làm để ép case pass

- Không gắn context công tác cho giấy mua máy in/thiết bị/vật tư rồi gọi là nguyên case đã hợp phạm vi. Nếu chuyển story, sửa source của biến thể có phiên bản; giữ tình huống số học/quan hệ cần kiểm.
- Không đổi threshold matcher Hoangha đã chốt, exact-ref1.0 hoặc LLM promotion>=0.90 chỉ để nhận lại nhãn AUTO_PROCESS. Accepted semantic risk phải có metric/provenance, không biến link thành known money.
- Không suy đã trả từ buyer/signature/Chuyển khoản trên invoice. Printed return/reimbursement là khai báo số cần đối chiếu, không là R/P actual.
- Không coi vé bãi xe/toll `E_TICKET` legacy tự thành TRANSPORT_TICKET; không ép receipt thành alternative-policy chỉ vì không phải VAT invoice.
- Không coi thiếu khoản 800.000 đ / 100.000 đ / 1.080.000 đ là zero; không phê duyệt một phần rồi thu nhầm phần ứng bị ảnh hưởng bởi unresolved expense.
- Không mang cap100 triệu, deadline30 ngày, meal/taxi caps, blanket rượu bia rule từ Hoangha vào final. TC13 loại vì nguồn ghi rõ cá nhân, không chỉ vì có chữ rượu.
- Không nhận tất cả source hỗ trợ thành original_total; một service invoice+acceptance+payment proof không tạo nhiều lần chi.
- Không coi signature/approval mock trên PDF là server grant hay payment event.

## 7. Thứ tự chuyển dữ liệu và nối workflow đề xuất

1. **Khóa pilot UC03-F01/F02/F03:** source mới hợp profile công tác, giữ 3.240.000/4.000.000; 5.400.000/5.000.000; 4.320.000/4.320.000. F01 chuyển tiếp khách thành bữa ăn công việc trong chuyến; F02 chuyển máy in thành dịch vụ lưu trú; F03 giữ lưu trú. Thay story được công bố, không nói PDF gốc tự là công tác.
2. **Tạo input runtime tách oracle:** source PDF/ảnh + context/activity/B/grants/ledger/coverage + employee confirmation Q32. Mỗi field có ref/người/thời điểm; legacy gold chỉ evaluator đọc.
3. **Gold evidence viết tay trước** cho subset 10–15; lock quote/field state/role/cardinality/allocation. Không sinh nó từ output model. Có source hashes, schema/prompt version, reviewer/source disposition; block IDs từ capture hợp lệ, không bịa từ native text audit.
4. **Plan finance/admissibility riêng:** DocumentAnalysis/links -> scoped expense candidates -> admissibility Q32/Q34 -> AssessmentInput -> Reconciler -> canonical command/state/Instruction. Giữ guard EVIDENCE_READY cho đến gate này được triển khai; không tắt guard rồi gọi STUB builder.
5. **Pilot theo workflow thật:** F01thu760.000/F02chi400.000/F03balanced0; sau đó TC05/08/15/19/25 variantsFACT, TC16AUTHORITY, TC13personal-exclude, TC12dup-sequence.
6. **Các ca complex:**20 reason-not-fact;18 multi-support+payee;22/23 over/rightallocation;24 quarantine relevance;21missing+authority. Ngoài-scope nguồn gốc ở lane evidence/reference, không đếm routine finance.
7. **Chạy/chấm có mode:** STUB fake chỉ contract harness; RECORDED_REPLAY cần capture từLIVE có identity/version; LIVE mới đánhmodelquality. Model fail/timeout/LIMIT không đổi thành FACT business. Core4/Escalation5/holdout chọn riêng;25case development không tự làindependentholdout.

## 8. Deliverable cần có ở bước code/data tiếp theo

- [ ] Bộ nguồn/context pilot F01–F03 tạo bằng generator portable, kèm source↔variant provenance.
- [ ] `expected-evidence` hand-reviewed, không nạp runtime; `expected-business` riêng có preconditions, issue groups/owner/questions, direction/amount/state và post-action state.
- [ ] Mapping/admission consumer được plan và implement; gate không còn fallback transcription giả ởLIVE.
- [ ] Sequence F01: E3.240.000/A4.000.000/P0/R0 -> COLLECT760.000; sau receivedR760.000, S0/SETTLED, không instructionmới.
- [ ] Sequence F02: E5.400.000/A5.000.000/P0/R0 -> PAY400.000; sau receivedP400.000, S0/SETTLED.
- [ ] Sequence F03: E=A4.320.000/P0/R0 -> BALANCED/SETTLED và0instruction.
- [ ] TC12 priorusage/context được dựng bằng workflow hợp lệ; lầnnộplại không tạo obligation thứhai.
- [ ] Profile/Q32/taxbuyer/alternativeadmissibility được pin operativecontract; không tự thêmfinancialrules mới trong gold.
- [ ] Recorded/LIVE/tests/UI evidence thật, goldscoring không thành feedback practitioners.

**Lượt này hoàn thành mapping và sửa manifest; các checkbox triển khai ở trên chưa thực hiện.**

## 9. Bằng chứng của lượt mapping

- Structural check bằng `rtk proxy uv run --no-sync python`: 25 IDs đầy đủ TC01–TC25, 65 refs đúng SHA-256, 25 expected.json cũ và mọi PDF/DOCX không đổi; manifest chỉ đổi folder; 0 link Markdown lỗi; exit 0.
- Manifest trước sửa có 25/25 folder path không tồn tại; sau sửa 25/25 path trỏ đúng folder và expected.
- Metadata drift TC19/TC20 được giữ và nêu rõ, chưa dùng làm oracle final.
- `rtk proxy git diff --check`: exit 0. Kiểm cấu trúc/hash/đọc nguồn không chứng minh pipeline pass.
- Native text audit/4 bản render mẫu nằm trong ignored `.runtime/uc03-mapping-review`; không phải đầu vào/representation của runtime.
- Không chạy product tests, browser hay provider LIVE; không tạo biến thể PDF/context/gold thực thi, không sửa code/policy/grant/matcher, không commit/push trong nhiệm vụ mapping.

## 10. Sửa theo review độc lập — tách issue, projection và execution

[Review độc lập](../../../docs/final/reviews/2026-10-14-uc03-mapping-review.md) ban đầu NEEDS_REVISION. Các correction thuộc data contract, không đổi policy/source:

- JSON v2 giữ `scenario_goal` như mô tả ý đồ case, không còn `outcome/owner` đơn lẻ làm oracle. Tách `issue_sequence` (kind/owner/field/condition/depends_on/required_answer), `projection_if_known`, `allowed_effect_after_gates`, trạng thái và execution actor.
- Routine TC01/02/03 và nhánh clear personal TC13 có `issue_sequence=[]` khi common gates đủ. Kế toán thực hiện instruction không là người phải trả lời câu hỏi eligibility của routine.
- TC20: EMPLOYEE FACT dịch vụ/số tiền -> AUTHORIZED_APPROVER POLICY **chỉ nếu** rule hiệu lực đòi ngoại lệ. Không cho actor xác nhận fact tự waive rule.
- TC04/14/16/23: ACCOUNTANT FACT paid-basis **nếu chưa có căn cứ phù hợp** -> AUTHORITY khi E đã known >8 triệu. Nếu fact precondition đã đủ thì không tạo câu hỏi giả. TC04/14 vượt demo20 triệu phải cấp ngoài demo.
- TC21/22: FACT source/allocation -> FACT paid-basis nếu cần -> AUTHORITY khi E cuối known >8 triệu. Nếu correction làm E xuống ngưỡng, authority template không active; không giữ nhãn cũ bằng mọi giá.
- TC12 chỉ hỏi kế toán nếu usage/scope chưa rõ; canonical reuse/no-second-instruction không bắt buộc có câu hỏi.
- TC07 contract đã pin `amount_words` critical. Gán NON_CRITICAL trong implementation hiện tại là drift; mapping có `implementation_dependency` và giữ FACT blocking inconsistency theo contract.
- Các dependency là template: precondition đã verified làm dependency satisfied, không cưỡng ép thêm issue/resolution giả. Đây chưa phải `BusinessIssue` hoặc runtime schema mới.

Các bảng mục tiêu là điều kiện tương lai; `allowed_effect_after_gates` NONE với amount null không có nghĩa đã balanced. NONE/0 chỉ cho balanced đủ căn cứ và không tạo instruction số0. Các possible_effect sau resolution không được phát hành trước facts/policy/grants đủ.

## 11. Pilot đã tạo — 14/10/2026

Ba biến thể F01/F02/F03 hiện có tại [uc03-pilot](../../test-kit/uc03-pilot/README.md), kèm6PDF/context/confirmation/gold/provenance vàscript sinh lại. Đã self-check source/shape/geometry; **chưa nối admission, chưa E2E/LIVE/UI**, nên vẫn giữ ready_for_financial_oracle=false cho mapping corpus gốc. Xem [plan nối finance](../../../docs/superpowers/plans/2026-10-14-evidence-finance-admission.md).

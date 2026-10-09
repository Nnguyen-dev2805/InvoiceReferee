# R5.6 — Chưa có ngân sách và số tiền không đọc được

Ngày: 09/10/2026 · **ĐÃ DỰNG NGUỒN VÀ ĐÁP ÁN NHÁP; CHƯA CHẠY OCR/PIPELINE HOẶC THẨM ĐỊNH GOLD ĐỘC LẬP**.

Toàn bộ tổ chức, người, chứng từ, quyền và sự kiện tiền là giả lập. [Suite manifest](suite_manifest.json) tách đầu vào ban đầu, nguồn bổ sung, đáp án và policy snapshots. Hai case cùng họ dữ liệu development trước đó; không dùng làm holdout độc lập hoặc suy độ chính xác thực tế.

| Case | Vấn đề ban đầu | Cách giải quyết được chọn | Kết quả sau nguồn/decision đủ |
| --- | --- | --- | --- |
| [Q15](Q15/README.md) | Nhân viên tự chi5triệu, công ty trảvé3triệu; công việc được phép nhưng chưa có ngân sách hoặc quyết định chấp nhận chi phí | Người đủ quyền chấp nhận chi phí sau phát sinh, đồng thời phê duyệt hoàn trả | E5, A/P/RA/RP0 có căn cứ, S=+5triệu; chưa thực nhận/đóng |
| [Q08](Q08/README.md) | Tổng tiền hotel bị che trong PNG; không có giá/amount thanh toán rõ ở nguồn khác | Bản rõ của cùng invoice/receipt, giữ ảnh cũ và liên kết nguồn mới | Hotel3, T8/E5/A2, S=+3triệu; báo cáo sau hỗ trợ, chưa duyệt tiền/đóng |

## Q15 — Quyền ra quyết định khác quyết định đã có

Nguồn AUTH-POST-02 giao người duyệt quyền xem xét chi phí công việc cụ thể tới8triệu; **đây không phải B8 đã được phê duyệt**. Quyết định trước công việc chỉ cho phép công tác, không ngân sách, ứng hoặc chấp nhận chi phí trước.

Nguồn payment/coverage đủ để xác định khoản chi, payer, companydirect3 và absence ứng/hoàn trước. Hệ thống vẫn chuẩn bị bảng đối chiếu, không tạo fakeadvance0 hoặc từ chối chỉ vì thiếu B. Nhưng chưa được lấy số nhân viên khai hoặc giới hạn quyền8 làm ngân sách để auto-pass.

Nguồn bổ sung được chọn chấp nhận chi phí thực tế8 sau phát sinh, employee5 và chi5 theo cùng quyết định trong quyền. B trước chuyến đi vẫn chưa tồn tại; ghi đúng modePOST_INCURRED_COST_ACCEPTANCE, không backdate thành phê duyệt trước. S=5 và approval5 chưa là employee nhận5; không tạo P5/close.

## Q08 — Một ảnh đọc được nhiều trường vẫn thiếu amount critical

Nguồn đầu: [hotel receipt PNG](Q08/input/hotel_receipt.png). Nguồn bổ sung riêng: [bản rõ](Q08/followup/hotel_receipt_clear.png). Hai ảnh mới được dựng xác định bằng Pillow với text/shape, không chỉnh sửa ảnh người dùng hoặc hóa đơn thật. Watermark chỉ rõ giả lập. Case kiểm tra tổng tiền bị che, không mô phỏng mọi loại blur/scan/camera noise.

Ảnh ban đầu chỉ có vùng opaque che tổng tiền, không số ẩn dưới vùng đó hoặc metadata text. Không dòng giá/thuế/số tiền bằng chữ để suy lại tổng. Các nguồn text ban đầu cũng bỏ hotelamount và bankreceiptamount; employee kê phần đó chưa đọc rõ. Forecast employee5 và B8 là số kế hoạch, không nguồn chứng minh actualhotel3.

Đã xem trực quan cả hai ảnh: các trường khác và payer/paid được giữ rõ; total ban đầu không nhìn thấy, bản bổ sung có3.000.000VND. [Expected](Q08/expected/before.json) có vùng ảnh thực tế `[80,750,1160,900]` trên canvas1240×1500, ở ngoài input; không bịa vị trí của ảnh chưa có.

Companydirect3 + meal1 + ground1 là subtotal expense5 chưa gồmhotel; employee-paid subtotal2 chưa gồmhotel, đúng bằng A2. **Subtotal2−A2=0 không phải S toàn hồ sơ bằng0**. Hotelamount/T/E/S cuối vẫn chưa xác định; không cấp quyền chi/thu/đóng từ subtotal.

Muốn giải quyết phải có nguồn amount rõ phù hợp; một số người gõ hoặc financialapproval không làm ảnh gốc đọc được. Nếu đã có alternative source đủ thì dùng nó, không bắt đọc lại ảnh che. Ở case này chủ động không có alternative đủ tronginitialpacket, vì vậy câu hỏi bổ sung là cần thiết.

## Mốc và dữ liệu được đưa vào từng run

Mốc tiền08/10 18:00 giữ nguyên. Bản rõ và quyết định sau phát sinh nhận09/10 09:00 nói về chi phí trước mốc; không actualpayment mới09/10 được đưa vào Pở08/10. Trước nguồn bổ sung chưa finalS, sau nguồn đúng vẫn ghi assisted, không biến run ban đầu thành first-passroutine.

CaseID/README/expected/construction/fixturechecks không vào prompt. Chỉ originaltext/CSV/PNG theo manifest. Không đưa PNG rõ vào runQ08 ban đầu; nguồn đã có trong folder nhưng không có trong initialmanifest. Chưa có harness/application đã thực thi giới hạn input này.

## Trạng thái corpus và bước tiếp

[Kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_AND_IMAGE_FIXTURE_SANITY_ONLY: phase/hash/refs, nguồn Q15 không có B, vùng ảnh initial chỉ còn opaque và không metadata số ẩn, arithmetic sau nguồn bổ sung. Kiểm tra trực quan ảnh đã thực hiện, nhưng không kết quả OCR/pipeline hoặc adjudication độc lập.

Đã dựng đủ15packetconditions B7 theo catalogue, cùng một templatefamily, với expected singleauthor. Đây là dữ liệu development đã tạo, không15case đã chạy/chấm hoặc bằng chứng đáp ứng cuộc thi. Chưa5B3, lifecyclecontrol traces đầy đủ, independentgold/holdout, professionaltrial hoặc B1freeze.

Image case thêm một nguồn raster đã kiểm tra trực quan; chưa gọi OCR/provider hoặc xác minh khả năng tự đọc của sản phẩm. Bộ narrative sạch vẫn đơn giản hơn đầu vào thực tế; cần sourceformat/quality strata và measurement mode phù hợp trước khi kết luận chất lượng.

Tiếp theo dựng5case đề nghị ứng A01..A05 rồi rà soát gold/nguồn/role/mốc trên toàn corpus. Không thêm bank/ERP/auth hoặc nhiều cấp quyền để hoàn thiện case; giữ business policy đã chốt và các bất biến nguồn/tiền/action.

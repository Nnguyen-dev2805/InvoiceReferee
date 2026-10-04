# InvoiceReferee V2 — Hợp đồng baseline, bản nháp

Ngày: 04/10/2026. Trạng thái: **DRAFT — đề xuất để thảo luận**, chưa phải spec
đã duyệt và chưa có implementation. Source main tham khảo ban đầu (B0):
`main@196e266541526123844a60820737f400e09b3a36`.

## 1. Những lựa chọn đã được người phát triển nêu

- Viết lại trên nhánh `rebuild`.
- Bối cảnh là hồ sơ chi phí của công ty.
- Phát triển lại ý tưởng/policy main để tạo MVP baseline mới B1; cải tiến sau
  đó là B2 và được so với B1 trên dữ liệu/phạm vi đã chốt.
- Scope MVP: một app, một người thao tác; không giải bài toán production
  nhiều user, tenancy, enterprise auth, scale hoặc distributed recovery.
- So sánh bằng hành vi có bằng chứng, không chỉ bằng số lượng tính năng.

## 2. Quy tắc kế thừa và phạm vi hiệu lực

| Hợp đồng | Kế thừa gì? | Phạm vi |
| --- | --- | --- |
| Source identity | Giữ evidence ID, source ref và đúng coverage | Mỗi phép kiểm tra phải có nguồn cần thiết; object có mặt chưa chứng minh mọi field đầy đủ |
| Quality | Đánh giá riêng từng evidence trước khi dùng dữ kiện quan trọng | Thiếu score/coverage hoặc OCR rỗng không tự trở thành chất lượng đạt |
| Numeric data | Số chuẩn, Decimal và quy đổi đơn vị có căn cứ | Currency, rounding và signed adjustments còn cần định nghĩa |
| Inventory consistency | Đối chiếu bill với report nhận hàng, dòng hàng, lượng và các giá trị liên quan | Chỉ áp dụng cho profile mua hàng/nhận hàng; không ép mọi hồ sơ chi phí có report kho |
| Context boundary | Lời khai không thay dữ kiện kiểm kê của chứng từ | Business purpose có thể là khai báo của nhân viên; lưu loại nguồn riêng |
| Model boundary | Model trích xuất/gợi ý; code kiểm tra và tổng hợp | Không lấy kết luận tự do của model làm phê duyệt |
| Bounded repair | Giới hạn sửa JSON và sửa coverage | Hai loại repair riêng, có trace và budget |

Các giá trị 0.85, 7 ngày và tolerance 1 được ghi nhận như tham số baseline.
Chưa công nhận chúng là quy định công ty hoặc gán áp dụng cho mọi profile.

## 3. Hành vi cần thay đổi có chủ đích

- F01: không coi OCR rỗng hoặc không đủ quality coverage là đạt.
- F02: không ghi đè/mất dòng khi model trả item ID trùng.
- F03: thống nhất block/evidence refs, kiểm tra nguồn thực sự tồn tại.
- F04: đơn giá chỉ được so khi quy về đơn vị tương thích có căn cứ.
- Một profile không áp dụng không đủ để kết luận toàn hồ sơ hợp lệ.
- Consistency và arithmetic là hai kiểm tra riêng; hai nguồn khớp vẫn có thể
  cùng sai số học.

Các finding và probe gốc nằm trong
[đánh giá main](reviews/main-baseline-196e266/MAIN_BASELINE_REVIEW.md).
Main và evidence B0 được giữ làm tham chiếu lịch sử. B1 là implementation
MVP mới sau khi đạt nghiệm thu; không dùng bug main làm expected đúng của
B1. Khi thử cải tiến B2, giữ kết quả B1 và đo trên cùng inputs/phạm vi.

## 4. Phạm vi sản phẩm mới cần chốt tiếp

Đề xuất: nhân viên nộp hồ sơ chi phí; hệ thống kiểm tra các điều kiện công bố,
giải quyết hồ sơ thường quy trong quyền được giao, hỏi bổ sung dữ kiện hoặc
chuyển người có quyền quyết định ngoại lệ; nhận phản hồi và kiểm tra lại.

Trước khi triển khai quyết định nghiệp vụ, cần xác định rõ:

1. Loại chi phí nào được hỗ trợ và điều kiện nhận chứng từ của từng loại.
2. Ai trả tiền, ai đề nghị, ai có quyền xử lý hoặc phê duyệt.
3. Policy mô phỏng nào được dùng; phạm vi, hạn mức và ngoại lệ của nó.
4. Công việc cụ thể mà hệ thống được phép tự hoàn tất. Quality/consistency
   đạt không tự có nghĩa đã được duyệt hoàn ứng hoặc đã chi tiền.
5. Câu trả lời nào đóng được issue nào; lưu quyết định và dữ liệu trước/sau.

Chưa tự đặt hạn mức tiền hoặc quy định thuế. Những lựa chọn này chưa phải
điều kiện đã thống nhất với một công ty hoặc người dùng chuyên môn.

## 5. Tám tình huống đầu tiên để chốt hợp đồng hành vi

Các case là giả lập để thiết kế kiểm thử; chưa phải dataset chính thức.

| ID | Input/điều kiện | Main hoặc bằng chứng | V2 cần đạt theo đề xuất |
| --- | --- | --- | --- |
| C01 | Bill/report rõ và nhất quán trong profile nhận hàng | B00 và happy fixture | Gate consistency đạt; vẫn đánh giá các gate nghiệp vụ còn áp dụng |
| C02 | Bill và report khác số lượng | Unhappy fixture trong main | Issue có hai giá trị, nguồn và yêu cầu làm rõ; không tự sửa nguồn |
| C03 | OCR rỗng hoặc word quan trọng thiếu coverage | Q01–Q03 | Chất lượng chưa đủ căn cứ; không dùng dữ kiện đó cho quyết định chắc chắn |
| C04 | Hai dòng hàng cùng item ID | I04 | Nhận diện extraction invalid; không mất dòng hoặc tự hoàn tất |
| C05 | 1 kg giá 1000/kg và 1000 g giá 1/g; cùng amount | I02 | Không báo chênh đơn giá chỉ do khác đơn vị khi phép quy đổi đã xác định |
| C06 | Conflict dẫn tới block thực sự tồn tại trong source registry | I01 cho thấy mismatch về format | Chấp nhận reference hợp lệ; từ chối reference không tồn tại |
| C07 | Hai nguồn cùng quantity 2, price 100, amount 1 | G01 probe: consistency đạt | Consistency có thể đạt nhưng arithmetic check phát hiện vấn đề theo profile đã chốt |
| C08 | Các gate kỹ thuật đạt nhưng policy/quyền tự xử lý chưa được cấu hình | Gap scope của baseline | Chưa tự kết luận được duyệt hoàn ứng; biểu diễn điều kiện workflow còn thiếu |

C03 không đồng nhất tài liệu unreadable với lỗi mạng provider; C04 không
đồng nhất lỗi extraction với vi phạm chính sách của nhân viên. Chi tiết
taxonomy/status sẽ được thiết kế sau khi chốt trách nhiệm nghiệp vụ.

## 6. Công việc ngay sau khi chốt bản nháp

1. Viết policy mô phỏng cho một phạm vi chi phí hẹp và bổ sung case factual,
   outside-policy, beyond-authority. Không cần thiết kế framework policy chung.
2. Thiết kế hợp đồng dữ liệu và một luồng nộp -> kiểm tra -> hỏi/duyệt -> phản
   hồi -> kiểm tra lại, giữ provenance và lịch sử.
3. Lập kế hoạch implementation rồi mới tạo code; bắt đầu bằng pure policy
   và fake provider để kiểm chứng hành vi.

Bản nháp này là điểm bắt đầu để thảo luận nội dung, không phải thông báo rằng
policy hoặc các luồng trên đã tồn tại trong nhánh rebuild.

## 7. Đối chiếu yêu cầu cuộc thi

Xem [requirement mapping](COMPETITION_REQUIREMENTS.md) đã đọc lại từ đề bài gốc.
Các case baseline ở trên cần bổ sung ba nhóm bất định, routine action thật,
Core/Escalation Verify, Stop/Override, audit, feedback adaptation và evaluation
độc lập. Research không thay thử nghiệm với 3 nhân sự nghiệp vụ thực tế.
Tên enum và cách chia module là lựa chọn thiết kế, không phải tên bắt buộc
trong đề. Bản nháp vẫn chưa được chuyển thành spec implementation đã duyệt.

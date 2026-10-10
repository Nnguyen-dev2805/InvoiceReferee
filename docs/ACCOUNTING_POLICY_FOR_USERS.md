# Chính Sách Tiếp Nhận Và Kiểm Tra Hồ Sơ Chi Phí

## 1. Mục đích

Chính sách này hướng dẫn nhân viên nộp hồ sơ chi phí và kế toán kiểm tra hồ sơ
trên InvoiceReferee. Mục tiêu là giảm việc hỏi lại các thông tin cơ bản, phát
hiện sớm chứng từ chưa rõ hoặc không khớp, và để kế toán tập trung vào các hồ
sơ thực sự cần quyết định.

Hệ thống chỉ hỗ trợ tiếp nhận và kiểm tra chứng từ. Hệ thống không tự thanh
toán, không tự ghi sổ và không thay thế quyền quyết định của kế toán hoặc người
phê duyệt.

## 2. Ai làm gì

| Vai trò | Trách nhiệm |
| --- | --- |
| Nhân viên | Nộp bill/hóa đơn, mô tả mục đích chi và tài liệu liên quan một cách trung thực, rõ ràng. |
| Kế toán | Kiểm tra các hồ sơ cần xác nhận, yêu cầu bổ sung khi cần và đưa ra quyết định nghiệp vụ cuối cùng. |
| InvoiceReferee | Đọc chứng từ, phát hiện vùng thông tin chưa rõ và đối chiếu bill với tài liệu nhận hàng/kiểm kê khi hồ sơ có các tài liệu đó. |

## 3. Nhân viên cần nộp gì

Mỗi hồ sơ chi phí cần có:

1. Ít nhất một chứng từ chính: bill, hóa đơn, biên lai, hoặc chứng từ chi phí.
2. Nội dung đề nghị giải thích ngắn gọn khoản chi dùng cho công việc gì. Nếu
   có thể, nêu người chi, mục đích và dự án/khách hàng liên quan.
3. Tài liệu hỗ trợ khi có: phiếu nhập kho, phiếu kiểm kê, biên bản giao nhận,
   report hoặc tài liệu xác nhận hàng hóa/dịch vụ đã nhận.

Nội dung mô tả giúp kế toán hiểu bối cảnh, nhưng không thay thế bill/hóa đơn.
Một hồ sơ chỉ có mô tả mà không có chứng từ chính sẽ được yêu cầu bổ sung.

## 4. Cách chuẩn bị hồ sơ tốt

- Chụp toàn bộ hóa đơn, không che tổng tiền, ngày lập, tên người bán hoặc danh
  sách hàng hóa.
- Bảo đảm ảnh sáng, thẳng, không bị mờ hoặc lóa.
- Khi có nhiều trang, nộp đủ tất cả các trang liên quan.
- Với khoản mua hàng, đính kèm phiếu nhập kho, phiếu kiểm kê hoặc biên bản giao
  nhận nếu có.
- Không nộp cùng một tệp nhiều lần. Hệ thống sẽ chỉ giữ một bản nếu nội dung
  tệp giống hệt nhau.

Mỗi hồ sơ tối đa 12 tệp; mỗi tệp tối đa 15 MB; tổng dung lượng tối đa 50 MB.

## 5. Các kiểm tra hệ thống đang thực hiện

### Kiểm tra khả năng đọc chứng từ

Hệ thống kiểm tra liệu các thông tin quan trọng trên chứng từ có đọc được để
phục vụ đối chiếu hay không, gồm tên và mã số thuế người bán, ngày chứng từ,
số hóa đơn, tên hàng, số lượng, đơn vị, đơn giá, thành tiền, tổng tiền và trạng
thái nhận hàng.

Nếu thông tin quan trọng bị mờ hoặc không chắc chắn, kế toán sẽ nhận được câu
hỏi cụ thể để yêu cầu xác nhận. Các thông tin không ảnh hưởng đến đối chiếu
hiện tại, ví dụ thuế suất, có thể được ghi nhận là cảnh báo mà không chặn hồ sơ.

### Đối chiếu bill với tài liệu hỗ trợ

Khi hồ sơ có tài liệu hỗ trợ, hệ thống đối chiếu độc lập từng nguồn. Với nghiệp
vụ mua hoặc nhận hàng, các điểm chính cần thống nhất là:

- nhà cung cấp, khi cả hai nguồn đều có mã số thuế;
- ngày chứng từ và ngày tài liệu hỗ trợ, với chênh lệch không quá 7 ngày;
- trạng thái đã nhận hàng;
- tên hàng, số lượng và đơn vị;
- đơn giá và thành tiền, nếu cả hai nguồn đều có giá trị này.

Nếu không phải nghiệp vụ mua/nhận hàng, bước đối chiếu kiểm kê không áp dụng.
Nếu không có tài liệu hỗ trợ, hệ thống hiện chỉ kiểm tra chất lượng đọc chứng
từ rồi chuyển hồ sơ sang bước tiếp theo.

## 6. Kết quả và cách xử lý

| Kết quả hiện trên hệ thống | Ý nghĩa | Việc cần làm |
| --- | --- | --- |
| `PASS` | Hồ sơ đã qua các kiểm tra Sprint 1 đang áp dụng. | Kế toán có thể tiếp tục xử lý theo quy trình nội bộ. |
| `NEEDS_HUMAN` | Thiếu chứng từ, thông tin chưa đọc chắc chắn, có lỗi đọc tệp hoặc dữ liệu giữa bill và tài liệu hỗ trợ không khớp. | Kế toán xem lý do, yêu cầu nhân viên xác nhận/bổ sung hoặc xử lý thủ công. |

Ví dụ câu hỏi tốt: “Vui lòng xác nhận tổng thanh toán trên hóa đơn là
2.442.860 đồng hay một giá trị khác.” Ví dụ cần tránh: “Vui lòng kiểm tra lại.”

## 7. Những gì hệ thống chưa tự quyết trong Sprint 1

Kế toán vẫn chịu trách nhiệm kiểm tra và quyết định các nội dung sau, vì chúng
chưa được hệ thống thực thi tự động:

- hóa đơn có đúng tên hoặc mã số thuế công ty hay không;
- hóa đơn có trùng với hồ sơ đã xử lý hay không;
- chi phí có thuộc danh mục được phép hay là chi phí cá nhân;
- chứng từ có nộp đúng hạn hay không;
- khoản chi có vượt hạn mức phê duyệt hay không;
- dấu hiệu gian lận hoặc bất thường;
- tính toán số học trong cùng một hóa đơn.

Khi có nghi ngờ ở các nội dung trên, kế toán không dựa duy nhất vào kết quả
`PASS` mà cần thực hiện kiểm tra theo quy trình nội bộ.

## 8. Minh bạch và bảo mật

Mỗi hồ sơ giữ lại chứng từ gốc, kết quả đọc chứng từ, kết quả kiểm tra và nhật
ký thời điểm xử lý để kế toán truy vết. Nhân viên chỉ nộp dữ liệu cần thiết cho
nghiệp vụ; dữ liệu thật cần được xử lý và chia sẻ theo quy định bảo mật của tổ
chức.

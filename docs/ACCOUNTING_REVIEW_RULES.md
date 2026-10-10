# Bộ Quy Tắc Kiểm Tra Hồ Sơ Chi Phí - Sprint 1

## 1. Phạm vi áp dụng

Bộ quy tắc này áp dụng cho hồ sơ chi phí nhân viên gồm bill/hóa đơn, nội dung
đề nghị và tài liệu hỗ trợ như phiếu nhập kho, phiếu kiểm kê hoặc biên bản giao
nhận. Đây là policy giả lập cho cuộc thi và chỉ mô tả các rule đã được pipeline
hiện tại thực thi.

Mục tiêu của policy là quyết định một hồ sơ có đủ rõ để đi tiếp (`PASS`) hay
cần kế toán xác nhận (`NEEDS_HUMAN`). `PASS` không có nghĩa là hệ thống đã
thanh toán, ghi sổ hoặc phê duyệt khoản chi.

## 2. Nguyên tắc quyết định

1. Không tự đoán phần thông tin mờ, thiếu hoặc mâu thuẫn.
2. Nội dung nhân viên khai chỉ là bối cảnh; không thay thế chứng từ hoặc bằng
   chứng nhận hàng.
3. Kết quả của AI chỉ hỗ trợ đọc chứng từ và gợi ý đối chiếu. Rule Python là
   thành phần chốt kết quả cuối của Sprint 1.
4. Một rule không đạt, dữ liệu chưa rõ, hoặc lỗi kỹ thuật trong bước kiểm tra
   đều đưa hồ sơ sang `NEEDS_HUMAN`.

## 3. Rule kiểm tra

| Mã rule | Điều hệ thống kiểm tra | Điều kiện `PASS` | Khi nào cần `NEEDS_HUMAN` |
| --- | --- | --- | --- |
| `AC-01` | Có chứng từ chính | Có ít nhất một bill, hóa đơn hoặc chứng từ chi phí. | Không có chứng từ chính. |
| `AC-02` | Có bối cảnh nghiệp vụ | Có nội dung đề nghị, hoặc có tài liệu hỗ trợ đọc được. | Không có mô tả và cũng không có tài liệu hỗ trợ đọc được. |
| `AC-03` | Tệp hợp lệ để tiếp nhận | Tối đa 12 tệp, mỗi tệp không quá 15 MB, tổng không quá 50 MB; tệp không rỗng và đúng định dạng được hỗ trợ. | Vượt giới hạn, tệp rỗng hoặc sai định dạng. |
| `AC-04` | Đọc được chứng từ | Ít nhất một chứng từ chính được OCR thành công; mọi evidence cần xử lý đều đọc được. | Bill không đọc được, OCR lỗi hoặc có evidence xử lý thất bại. |
| `AC-05` | Độ rõ của thông tin quan trọng | Vùng chữ có confidence thấp đã được đánh giá và không ảnh hưởng đến dữ liệu cần đối chiếu. | Không đọc chắc tên/mã số thuế người bán, ngày, số hóa đơn, tên hàng, số lượng, đơn vị, đơn giá, thành tiền, tổng tiền hoặc trạng thái nhận hàng. |
| `AC-06` | Đủ dữ liệu để đối chiếu hàng hóa | Nếu có đối chiếu kho, cả chứng từ chính và tài liệu hỗ trợ đều có danh sách hàng hóa có thể đối chiếu. | Một trong hai nguồn thiếu danh sách hàng hóa hoặc không có tài liệu hỗ trợ cần thiết. |
| `AC-07` | Nguồn đối chiếu đầy đủ | Mỗi tệp đầu vào có đúng một bộ fact được trích xuất. | Agent bỏ sót tệp, trả thừa tệp, hoặc trả trùng fact của một tệp. |
| `AC-08` | Nhà cung cấp | Mã số thuế nhà cung cấp khớp giữa bill và tài liệu hỗ trợ, khi cả hai nguồn đều có mã số thuế. | Hai mã số thuế khác nhau. |
| `AC-09` | Ngày của giao dịch liên quan | Khi cả hai nguồn đọc được ngày, chênh lệch không quá 7 ngày. | Chênh lệch quá 7 ngày. |
| `AC-10` | Trạng thái nhận hàng | Tài liệu hỗ trợ xác nhận đã nhận đủ, hoặc không áp dụng đối với giao dịch đó. | Trạng thái là nhận một phần, chờ nhận, từ chối nhận hoặc chưa rõ. |
| `AC-11` | Ghép dòng hàng | Mọi dòng trên bill có một dòng tương ứng ở tài liệu hỗ trợ và ngược lại. | Có dòng hàng không ghép được hoặc agent trả mapping không hợp lệ. |
| `AC-12` | Số lượng và đơn vị | Số lượng bằng nhau sau khi quy đổi đơn vị được hỗ trợ. | Thiếu số lượng/đơn vị, đơn vị khác loại hoặc số lượng không khớp. |
| `AC-13` | Đơn giá và thành tiền | Khi cả hai nguồn đều có số liệu, chênh lệch không quá 1 VND. | Số không đọc được để đối chiếu hoặc chênh lệch lớn hơn 1 VND. |
| `AC-14` | Xung đột ngữ nghĩa | Không có xung đột được dẫn chiếu bởi chứng từ thật. | Có xung đột về hàng hóa hoặc trạng thái giao dịch được agent dẫn chiếu đến evidence trong hồ sơ. |

## 4. Các quy tắc diễn giải quan trọng

### Chứng từ mờ

Tên món hàng bị sai vài ký tự nhưng vẫn nhận diện chắc ý nghĩa có thể tiếp tục.
Ngược lại, nếu một chữ số làm thay đổi tổng tiền, số lượng hoặc đơn giá thì phải
chuyển sang `NEEDS_HUMAN` để xác nhận.

### Tài liệu hỗ trợ

Nếu hồ sơ không có tài liệu hỗ trợ, hệ thống hiện bỏ qua bước đối chiếu nhiều
nguồn. Hồ sơ có thể `PASS` nếu các rule về chứng từ và chất lượng đọc đều đạt.

Nếu đã có tài liệu hỗ trợ, hệ thống bắt buộc phải đối chiếu; không được lấy mô
tả của nhân viên để thay thế phiếu nhập kho hoặc biên bản giao nhận.

### Đơn vị tính

Hệ thống có thể quy đổi các đơn vị sau trước khi so sánh: `g`, `gram`, `kg`,
`kilogram`, `tan`, `cai`, `chiec`, `don vi`, `unit`. Các đơn vị khác cần kế
toán xác nhận nếu không thể so sánh trực tiếp.

## 5. Các chính sách chưa được áp dụng tự động

Những nội dung sau không được dùng để kết luận `PASS` hay `NEEDS_HUMAN` trong
code Sprint 1 hiện tại. Kế toán vẫn phải tự kiểm tra:

- hóa đơn có đúng tên hoặc mã số thuế công ty;
- hóa đơn trùng lặp và lịch sử thanh toán;
- chi phí cá nhân, danh mục chi phí cấm và chứng từ nộp quá hạn;
- hạn mức phê duyệt theo giá trị tiền;
- dấu hiệu gian lận hoặc bất thường;
- phép tính số học bên trong một hóa đơn.

Khi triển khai đầy đủ Track A, các nhóm trên sẽ được tách thành
`REQUEST_INFO` khi thiếu dữ kiện, hoặc `ESCALATE` khi đã có bằng chứng rõ về
vi phạm policy, vượt thẩm quyền hoặc có nghi vấn.

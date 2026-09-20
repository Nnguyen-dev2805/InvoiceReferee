# InvoiceReferee — Đặc tả sản phẩm

## 1. Tổng quan sản phẩm

**InvoiceReferee** là tác tử kế toán hỗ trợ kiểm tra hóa đơn điện tử, hóa đơn/chứng từ do nhân viên chụp và bằng chứng thanh toán liên quan.

Sản phẩm trả lời câu hỏi:

> Với những bằng chứng hiện có, chứng từ hoặc đề nghị chi này có đủ căn cứ, đúng chính sách và nằm trong thẩm quyền để tiếp tục xử lý không?

Hệ thống tự xử lý trường hợp thường quy và yêu cầu con người tham gia khi:

- thông tin bị thiếu hoặc mâu thuẫn;
- nội dung nằm ngoài chính sách công ty;
- số tiền hoặc loại chi vượt thẩm quyền của tác tử;
- có dấu hiệu bất thường/nghi vấn.

## 2. Người dùng mục tiêu

- **Kế toán thanh toán:** kiểm tra hóa đơn, chứng từ và đề nghị chi trước khi nhập liệu hoặc kiểm tra thanh toán.
- **Nhân viên/người yêu cầu:** bổ sung mục đích kinh doanh, khách hàng/dự án, lý do chi và bằng chứng liên quan.
- **Bộ phận mua hàng/kho/chủ dự án:** xác nhận đơn đặt hàng, hàng hóa/dịch vụ đã nhận hoặc bối cảnh dự án.
- **Quản lý tài chính:** phê duyệt trường hợp vượt thẩm quyền, ngoài chính sách hoặc có nghi vấn.

## 3. Phạm vi Sprint 1

Sprint 1 xử lý ba nhóm chứng từ:

1. **Hóa đơn điện tử** từ XML/PDF/văn bản/ảnh/JSON đã trích xuất.
2. **Hóa đơn/chứng từ do nhân viên chụp** như nhà hàng, taxi/Grab, khách sạn, văn phòng phẩm, in ấn và sửa chữa.
3. **Bằng chứng bổ sung** như đơn đặt hàng, biên bản nhận hàng, phiếu thu, ảnh chuyển khoản, lịch sử thanh toán và đề nghị chi của nhân viên.

Quy trình mua hàng dựa trên PO vẫn là một luồng con của hệ thống, không phải phạm vi duy nhất.

## 4. Mô hình đầu vào

### 4.1. Hóa đơn điện tử

Các trường bắt buộc tối thiểu:

- tên công ty bên mua;
- mã số thuế bên mua;
- tên công ty bên bán;
- mã số thuế bên bán;
- ngày lập hóa đơn;
- tên hàng hóa/dịch vụ;
- số lượng nếu là hàng hóa;
- tổng tiền;
- mẫu số;
- ký hiệu;
- số hóa đơn.

Các trường không bắt buộc:

- mã cơ quan thuế;
- địa chỉ bên mua/bán;
- người liên hệ/đại diện bên mua/bán;
- số lượng nếu là dịch vụ;
- số tiền bằng chữ;
- đơn giá, thuế, chiết khấu và phí dịch vụ.

### 4.2. Hóa đơn/chứng từ của nhân viên

Các trường có thể trích xuất:

- cửa hàng/nhà cung cấp;
- ngày giờ giao dịch;
- hàng hóa/dịch vụ;
- số lượng, đơn giá và thành tiền từng dòng;
- tổng số tiền;
- chiết khấu;
- thuế/phí dịch vụ;
- phương thức thanh toán.

Bối cảnh cần lấy thêm:

- người chi/nhân viên;
- mục đích kinh doanh;
- khách hàng/dự án;
- mã chuyến đi/sự kiện/đơn hàng;
- bằng chứng nhận hàng/dịch vụ nếu cần.

### 4.3. Bằng chứng bổ sung

- đơn đặt hàng (PO);
- biên bản nhận hàng hoặc nghiệm thu dịch vụ;
- bản ghi thanh toán;
- khai báo của nhân viên;
- dữ liệu gốc về nhà cung cấp/khách hàng;
- lịch sử chứng từ đã xử lý;
- chính sách công ty.

## 5. Các phép kiểm tra cốt lõi

1. **Nhận diện loại chứng từ:** hóa đơn điện tử, chứng từ nhân viên, bằng chứng thanh toán, chứng từ bổ sung hoặc không xác định.
2. **Độ đầy đủ của trường bắt buộc:** trường bắt buộc theo loại chứng từ và loại chi phí.
3. **Chất lượng trích xuất:** ảnh mờ, cảnh báo OCR, trường không đọc chắc chắn.
4. **Danh tính công ty:** mã số thuế/tên bên mua có phải công ty mình hay không.
5. **Danh tính bên bán/nhà cung cấp:** mã số thuế bên bán, cửa hàng và bản ghi nhà cung cấp.
6. **Ngày và thời hạn nộp:** có ngày giao dịch/lập hóa đơn và có quá hạn hay không.
7. **Số học trên dòng:** số lượng × đơn giá, chiết khấu, thuế/phí dịch vụ, thành tiền dòng và tổng tiền.
8. **Tính nhất quán của số tiền:** số tiền bằng chữ khớp số tiền bằng số nếu có.
9. **Trùng lặp:** số hóa đơn + mã số thuế bên bán + số tiền, hoặc dấu vân tay của chứng từ/bằng chứng thanh toán.
10. **Bối cảnh kinh doanh:** nhân viên, mục đích, khách hàng/dự án và loại chi phí.
11. **Danh mục chính sách:** chi phí cá nhân, rượu bia/mặt hàng bị cấm hoặc loại chi không được hỗ trợ.
12. **Tính nhất quán của bằng chứng:** chứng từ so với khai báo nhân viên, bằng chứng thanh toán, PO, số lượng nhận hàng hoặc nghiệm thu dịch vụ.
13. **Trạng thái thanh toán:** chưa thanh toán/đã thanh toán/thanh toán một phần/không xác định.
14. **Ngưỡng thẩm quyền:** số tiền hoặc loại chi có vượt ngưỡng của tác tử hay không.
15. **Bất thường/nghi vấn:** nhà cung cấp, số tiền, thời điểm hoặc mẫu hành vi bất thường.

Mã tất định chịu trách nhiệm so sánh tiền, số lượng, trùng lặp, ngày, ngưỡng và ánh xạ quy tắc. LLM chỉ suy luận trên dữ kiện đã có cấu trúc, tạo giải thích/câu hỏi và đề xuất hành động để Bộ bảo vệ quyết định kiểm tra.

## 6. Mô hình quyết định

Hệ thống có ba hành động hiển thị cho người dùng.

### `AUTO_PROCESS`

Dùng khi:

- chứng từ đọc được và đủ trường bắt buộc;
- số liệu nội bộ nhất quán;
- bên mua, công ty và bối cảnh hợp lệ;
- không còn trùng lặp chưa giải quyết;
- đúng chính sách;
- không có bất thường chưa xử lý;
- nằm trong ngưỡng thẩm quyền.

### `REQUEST_INFO`

Dùng khi chưa đủ dữ kiện để kết luận:

- thiếu trường bắt buộc;
- ảnh/OCR không chắc chắn;
- chứng từ không có ngày;
- chưa rõ mục đích kinh doanh, nhân viên, dự án/khách hàng;
- chứng từ và khai báo của nhân viên khác nhau;
- chỉ có ảnh chuyển khoản nhưng chưa rõ hàng hóa/dịch vụ hoặc mục đích;
- PO, biên bản nhận hàng hoặc nghiệm thu dịch vụ mâu thuẫn;
- trạng thái thanh toán không rõ.

`REQUEST_INFO` phải có câu hỏi cụ thể và đối tượng cần trả lời nếu có thể xác định.

### `ESCALATE`

Dùng khi dữ kiện đã rõ nhưng tác tử không được tự quyết:

- `OUTSIDE_POLICY`: mã số thuế bên mua là công ty khác, chi phí cá nhân, danh mục bị cấm, chứng từ quá hạn hoặc thiếu mục đích kinh doanh theo chính sách;
- `BEYOND_AUTHORITY`: số tiền hoặc loại chi vượt ngưỡng của tác tử;
- `SUSPICIOUS`: dấu hiệu gian lận/bất thường cần con người kiểm tra.

## 7. Thứ tự ưu tiên quyết định

```text
1. Đầu vào kỹ thuật không hợp lệ
      → INPUT_ERROR

2. Chưa xác định được loại chứng từ/hồ sơ
      → REQUEST_INFO

3. Dữ kiện bắt buộc bị thiếu, không đọc được hoặc mâu thuẫn
      → REQUEST_INFO

4. Dữ kiện đã rõ nhưng nằm ngoài chính sách
      → ESCALATE / OUTSIDE_POLICY

5. Dữ kiện đã rõ nhưng có cờ nghi vấn
      → ESCALATE / SUSPICIOUS

6. Dữ kiện đã rõ nhưng vượt thẩm quyền
      → ESCALATE / BEYOND_AUTHORITY

7. Đủ dữ kiện + đạt các phép kiểm tra + đúng chính sách + trong thẩm quyền
      → AUTO_PROCESS
```

Không được biến việc thiếu dữ kiện thành `AUTO_PROCESS`. Không được hỏi bằng chứng không liên quan đến loại chứng từ đã xác định.

## 8. Yêu cầu đầu ra

Mỗi kết quả kiểm tra cần có:

- các trường chứng từ đã chuẩn hóa;
- cảnh báo/độ tin cậy của quá trình trích xuất nếu có;
- kết quả kiểm tra theo quy tắc;
- bối cảnh chính sách;
- đánh giá của tác tử;
- quyết định cuối cùng;
- lý do;
- câu hỏi/đối tượng cần trả lời nếu có;
- nhật ký kiểm toán;
- các trường kế toán/xuất dữ liệu được đề xuất.

Giao diện phải cho phép dán/tải lên JSON mới để đánh giá đầu vào chưa từng thấy qua đúng luồng `review()` dùng trong sản phẩm.

## 9. Kiểm soát của con người

Con người luôn giữ quyền cuối cùng:

- **Dừng:** đổi trạng thái luồng công việc thành `STOPPED`, không tạo quyết định nghiệp vụ mới.
- **Ghi đè:** đổi quyết định có hiệu lực thành một trong `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`, kèm người thực hiện/thời gian/lý do.

Nhật ký kiểm toán phải chỉ được ghi nối tiếp ở tầng ứng dụng; thao tác ghi đè không xóa quyết định ban đầu của tác tử.

## 10. Tiêu chí thành công

Sprint 1 đạt yêu cầu khi:

- xử lý được ít nhất 15 trường hợp kiểm thử đã mô tả;
- có cả hóa đơn điện tử và chứng từ của nhân viên;
- trường hợp thường quy được tự động xử lý;
- trường hợp không rõ ràng không bị suy đoán;
- trường hợp ngoài chính sách, vượt thẩm quyền và nghi vấn được chuyển đúng;
- câu hỏi bổ sung cụ thể;
- kiểm tra trùng lặp, thanh toán, chính sách và thẩm quyền bằng mã tất định;
- đầu vào mới được xử lý bằng cùng một logic;
- nhật ký kiểm toán và Dừng/Ghi đè hoạt động;
- bộ Verify chạy được bằng một thao tác.

## 11. Ngoài phạm vi

Sprint 1 không nhằm xây dựng:

- bộ máy tuân thủ thuế GTGT/TNDN đầy đủ;
- kê khai thuế;
- bút toán kế toán tự động hoàn chỉnh;
- thanh toán tự động;
- hệ thống thay thế ERP;
- hệ thống OCR cấp độ sản xuất;
- bộ máy phát hiện gian lận đầy đủ.

Bộ chuyển đổi OCR/PDF/XML, nếu có, chỉ là tầng trích xuất và phải đưa dữ liệu về lược đồ chuẩn. Giá trị cốt lõi là ranh giới quyết định dựa trên bằng chứng, chính sách và khả năng kiểm toán.

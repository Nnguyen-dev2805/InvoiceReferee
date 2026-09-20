# InvoiceReferee — Chính sách v0

## 1. Mục đích

Chính sách v0 định nghĩa ranh giới quyết định cho bản thử nghiệm tác tử kế toán. Đây là **chính sách giả lập**, dùng để đánh giá và trình diễn, không phải chính sách thật của một doanh nghiệp cụ thể.

Mục tiêu:

- chứng từ thường quy và hợp lệ → `AUTO_PROCESS`;
- dữ kiện thiếu hoặc chưa chắc chắn → `REQUEST_INFO`;
- ngoài quy định, vượt thẩm quyền hoặc có nghi vấn → `ESCALATE`.

## 2. Phạm vi

Chính sách v0 áp dụng cho:

- hóa đơn điện tử của công ty;
- hóa đơn/chứng từ do nhân viên chụp;
- bằng chứng thanh toán và bằng chứng bổ sung liên quan đến việc kiểm tra chi phí;
- PO, biên bản nhận hàng hoặc nghiệm thu dịch vụ như bằng chứng bổ sung khi có.

Chính sách v0 chưa phải bộ máy xử lý thuế/GTGT/TNDN hoàn chỉnh.

## 3. Thứ tự ưu tiên quyết định

```text
1. Đầu vào kỹ thuật lỗi hoặc sai định dạng
      → INPUT_ERROR

2. Không xác định được loại chứng từ/hồ sơ
      → REQUEST_INFO

3. Dữ kiện bắt buộc bị thiếu, không đọc được, có cảnh báo OCR nghiêm trọng
   hoặc mâu thuẫn
      → REQUEST_INFO

4. Dữ kiện đã rõ nhưng vi phạm/nằm ngoài chính sách
      → ESCALATE / OUTSIDE_POLICY

5. Dữ kiện đã rõ nhưng có cờ bất thường/nghi vấn
      → ESCALATE / SUSPICIOUS

6. Dữ kiện đã rõ nhưng vượt thẩm quyền
      → ESCALATE / BEYOND_AUTHORITY

7. Đủ dữ kiện + đạt các phép kiểm tra + đúng chính sách + trong thẩm quyền
      → AUTO_PROCESS
```

Nguyên tắc: chưa biết dữ kiện thì hỏi; dữ kiện đã rõ nhưng tác tử không có quyền thì chuyển; chỉ tự động xử lý khi đầy đủ bằng chứng.

## 4. Quy tắc chính sách

### P01 — Trường bắt buộc theo loại chứng từ

Hóa đơn điện tử phải có:

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

Hóa đơn/chứng từ của nhân viên phải có tối thiểu tổng tiền và ngày giao dịch, hoặc lời giải thích hợp lệ về ngày. Nếu chứng từ quá mờ, bị che hoặc thiếu trường cần thiết:

```text
REQUEST_INFO
```

### P02 — Không coi dữ liệu trích xuất không chắc chắn là đạt

Nếu OCR/bộ phân tích không đọc chắc chắn trường quan trọng như tổng tiền, ngày, số hóa đơn hoặc mã số thuế bên bán/bên mua:

```text
REQUEST_INFO
```

Ví dụ câu hỏi:

> Số tiền trên chứng từ chưa đọc chắc chắn là 45 triệu hay 48 triệu đồng. Giá trị chính xác là bao nhiêu?

### P03 — Bên mua phải là công ty mình khi chứng từ yêu cầu bên mua

Với hóa đơn điện tử dùng để ghi nhận chi phí công ty, mã số thuế/tên bên mua phải khớp hồ sơ công ty.

Nếu thiếu mã số thuế bên mua:

```text
REQUEST_INFO
```

Nếu mã số thuế bên mua rõ ràng thuộc công ty khác:

```text
ESCALATE / OUTSIDE_POLICY
```

### P04 — Danh tính bên bán/nhà cung cấp phải truy vết được

Mã số thuế bên bán, cửa hàng hoặc nhà cung cấp phải đủ để truy vết. Nếu không đọc được:

```text
REQUEST_INFO
```

Nếu nhà cung cấp nằm trong danh sách bị chặn hoặc bị cấm:

```text
ESCALATE / OUTSIDE_POLICY
```

### P05 — Tính nhất quán số học

Nếu có các dòng hàng:

```text
quantity * unit_price - discount + tax/service_charge == line/grand total
```

Nếu có số tiền bằng chữ thì phải khớp với số tiền bằng số. Nếu số liệu tự mâu thuẫn:

```text
REQUEST_INFO
```

### P06 — Phát hiện trùng lặp

Định danh trùng lặp ưu tiên:

```text
seller_tax_code + invoice_serial_no + invoice_number
```

Hoặc với hóa đơn/chứng từ/bằng chứng thanh toán:

```text
merchant + date/time + amount + payment_ref/image_hash
```

Nếu trùng rõ ràng với chứng từ đã xử lý:

```text
ESCALATE / OUTSIDE_POLICY
```

Nếu chỉ có tín hiệu yếu, chưa đủ kết luận:

```text
REQUEST_INFO
```

### P07 — Trạng thái thanh toán

Nếu chứng từ/lịch sử thanh toán cho thấy đã `PAID` hoặc `PARTIALLY_PAID` nhưng người dùng gửi lại như đề nghị chi mới:

```text
REQUEST_INFO
```

Nếu trạng thái thanh toán không rõ và cần thiết cho quyết định:

```text
REQUEST_INFO
```

### P08 — Chứng từ nhân viên phải có bối cảnh kinh doanh

Hóa đơn/chứng từ của nhân viên cần có:

- người chi/nhân viên;
- mục đích kinh doanh;
- loại chi phí;
- khách hàng/dự án/chuyến đi/sự kiện khi liên quan.

Nếu thiếu bối cảnh:

```text
REQUEST_INFO
```

Ví dụ:

> Chứng từ 1,2 triệu đồng chưa có mục đích kinh doanh hoặc dự án. Khoản chi này phục vụ mục đích kinh doanh nào?

### P09 — Tính nhất quán giữa chứng từ, đề nghị chi và thanh toán

Hóa đơn, khai báo của nhân viên, bằng chứng thanh toán, PO, biên bản nhận hàng hoặc nghiệm thu dịch vụ không được mâu thuẫn.

Ví dụ:

- PO ghi 10 máy tính nhưng phiếu nhận hàng ghi 8 máy;
- nhân viên đề nghị 1,5 triệu đồng nhưng hóa đơn ghi 1,2 triệu đồng;
- ảnh chuyển khoản có số tiền nhưng không có hàng hóa/dịch vụ hoặc mục đích.

Nếu mâu thuẫn chưa có bằng chứng giải thích:

```text
REQUEST_INFO
```

### P10 — Bằng chứng nhận hàng/dịch vụ

Việc mua hàng hóa/dịch vụ cần bằng chứng đã nhận hàng/dịch vụ nếu chính sách yêu cầu. PO, biên bản nhận hàng hoặc nghiệm thu dịch vụ là bằng chứng bổ sung, không bắt buộc với mọi hóa đơn.

Nếu loại chi phí yêu cầu bằng chứng nhưng chưa có:

```text
REQUEST_INFO
```

### P11 — Chi phí bị cấm hoặc mang tính cá nhân

Nếu dữ kiện đã rõ và khoản chi thuộc danh mục không được phép:

- chi tiêu cá nhân;
- rượu bia/danh mục bị cấm theo chính sách;
- tiếp khách không có mục đích kinh doanh sau khi đã xác định đầy đủ dữ kiện;
- chứng từ được nộp quá hạn theo chính sách;

thì:

```text
ESCALATE / OUTSIDE_POLICY
```

### P12 — Thời hạn nộp

Quy tắc giả lập:

```text
submission_date - document_date <= 30 days
```

Nếu quá hạn và ngày tháng đã rõ:

```text
ESCALATE / OUTSIDE_POLICY
```

Nếu thiếu ngày giao dịch/lập hóa đơn:

```text
REQUEST_INFO
```

### P13 — Ngưỡng thẩm quyền

Quy tắc thẩm quyền giả lập:

```text
amount <= 50,000,000 VND
    → Tác tử có thể AUTO_PROCESS nếu mọi quy tắc khác đều đạt

amount > 50,000,000 VND
    → Cần Quản lý tài chính phê duyệt
```

Kết quả:

```text
ESCALATE / BEYOND_AUTHORITY
```

### P14 — Bất thường/nghi vấn

Nếu có dấu hiệu bất thường:

- số tiền cao bất thường so với lịch sử;
- nhà cung cấp mới hoặc lạ trong loại chi phí rủi ro;
- nhiều hóa đơn giống nhau;
- giao dịch ngoài giờ hoặc ngày nghỉ;
- nhân viên nộp nhiều chứng từ sát nhau;
- ảnh có dấu hiệu chỉnh sửa;
- hàng hóa/dịch vụ không tương xứng với mục đích kinh doanh;

thì:

```text
ESCALATE / SUSPICIOUS
```

Nếu tín hiệu chưa đủ mạnh và cần bổ sung dữ kiện:

```text
REQUEST_INFO
```

### P15 — Mức độ sẵn sàng để xuất dữ liệu kế toán

Chỉ được trả về `AUTO_PROCESS` khi có đủ trường tối thiểu cho hệ thống phía sau nhập/xuất dữ liệu:

- ngày chứng từ;
- nhà cung cấp/cửa hàng;
- bối cảnh bên mua/công ty nếu cần;
- loại chi phí;
- tổng tiền;
- trường thuế/phí nếu có, hoặc được đánh dấu là không có;
- mục đích/bối cảnh kinh doanh với chứng từ của nhân viên;
- định danh duy nhất của chứng từ/thanh toán.

Nếu thiếu trường bắt buộc để xuất dữ liệu:

```text
REQUEST_INFO
```

## 5. Điều kiện `AUTO_PROCESS`

Một hồ sơ chỉ được `AUTO_PROCESS` khi tất cả điều kiện sau đều đúng:

1. Đã xác định loại chứng từ/hồ sơ.
2. Đầy đủ các trường quan trọng bắt buộc.
3. Không có cảnh báo trích xuất nghiêm trọng.
4. Danh tính bên mua/công ty hợp lệ nếu áp dụng.
5. Số học và số tiền nhất quán.
6. Không còn trùng lặp chưa giải quyết.
7. Trạng thái thanh toán không mâu thuẫn.
8. Đầy đủ bối cảnh kinh doanh.
9. Đủ bằng chứng nhận hàng/dịch vụ nếu cần.
10. Không thuộc danh mục bị cấm, cá nhân hoặc quá hạn.
11. Không còn cờ nghi vấn chưa giải quyết.
12. Số tiền nằm trong ngưỡng thẩm quyền.

## 6. Đối tượng chuyển tiếp

| Tình huống | Đối tượng |
| --- | --- |
| Vượt ngưỡng 50 triệu đồng | Quản lý tài chính |
| Ngoài chính sách/danh mục bị cấm | Chủ chính sách kế toán/tài chính |
| Bất thường/nghi vấn | Quản lý tài chính/kiểm soát nội bộ |
| Mã số thuế bên mua thuộc công ty khác | Kế toán/người phụ trách thuế |
| Chi phí nhân viên thiếu bối cảnh | Nhân viên/người yêu cầu |
| Thiếu PO/bằng chứng nhận hàng hoặc dịch vụ | Bộ phận mua hàng/kho/chủ dự án |

Thiếu dữ kiện không mặc định chuyển cho Quản lý tài chính; trước hết phải hỏi nguồn có thể cung cấp dữ kiện.

## 7. Chất lượng câu hỏi

Mỗi `REQUEST_INFO` hoặc `ESCALATE` phải có câu hỏi:

- nêu dữ kiện/quy tắc đang gặp vấn đề;
- đưa ra số liệu/bằng chứng liên quan;
- có thể trả lời trực tiếp;
- không chung chung kiểu “kiểm tra lại giúp tôi”.

## 8. Ranh giới của LLM

Mã tất định bắt buộc xử lý:

- tiền và số lượng;
- định danh trùng lặp;
- trạng thái thanh toán;
- ngày/thời hạn nộp;
- ngưỡng thẩm quyền;
- ánh xạ chính sách.

Tác tử LLM chỉ:

- suy luận trên dữ kiện/phép kiểm tra có cấu trúc;
- đề xuất loại không chắc chắn/hành động;
- chọn vấn đề chưa giải quyết quan trọng nhất;
- tạo giải thích và câu hỏi;
- xác định đối tượng từ bối cảnh chính sách.

Bộ bảo vệ quyết định phải từ chối đề xuất trái quy tắc, ví dụ `FACTUAL_UNKNOWN → AUTO_PROCESS` hoặc số tiền trên 50 triệu đồng → `AUTO_PROCESS`.

## 9. Dừng/ghi đè bởi con người

`STOP` là trạng thái luồng công việc, không phải quyết định nghiệp vụ. `OVERRIDE` chỉ được đổi quyết định có hiệu lực thành một trong:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

Nhật ký kiểm toán phải lưu quyết định ban đầu, quyết định/trạng thái mới, người thực hiện, thời gian và lý do.

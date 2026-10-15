# Proposal gửi người dùng trải nghiệm — InvoiceReferee

**Track:** VNG · **Đề bài:** A — Bộ điều phối chuyển tiếp  
**Ngày chuẩn bị:** 15/10/2026  
**Nhóm thực hiện:** [Điền tên nhóm và người phụ trách]  
**Liên hệ:** [Điền email hoặc số liên hệ]

> Bản đề xuất phục vụ việc lấy phản hồi từ ba người đang trực tiếp tham gia xử lý
> hồ sơ chi phí/quyết toán. Các đường dẫn trong ngoặc vuông cần được nhóm điền và
> kiểm tra trước khi chuyển cho chị Kelly. Đây là kế hoạch thử nghiệm; chưa có
> phản hồi hay số liệu tác động từ người dùng thực tế.

## 1. Bài toán và mục tiêu

Một hồ sơ quyết toán có thể gồm giấy đề nghị, hóa đơn, chứng từ ứng tiền và bằng
chứng hoàn trả. Nhân viên, kế toán và người có quyền quyết định phải đối chiếu
nhiều nguồn, phân biệt **số tiền kê khai** với **tiền đã thực nhận**, kiểm tra
chênh lệch và xác định khi nào cần hỏi lại. Những bước này dễ lặp lại hoặc bị
bỏ sót nếu các bên chỉ nhìn một tài liệu riêng lẻ.

**InvoiceReferee** nhận hồ sơ PDF/ảnh, đọc và trích xuất thông tin, kiểm tra
quan hệ giữa các chứng từ và quy tắc nghiệp vụ đã cấu hình. Với trường hợp đủ
căn cứ trong phạm vi được giao, hệ thống đưa ra kết quả đối soát và yêu cầu
chi/thu phù hợp. Khi có số liệu mâu thuẫn, tài liệu thiếu hoặc vấn đề vượt
quyền, hệ thống dừng kết luận tiền và gửi câu hỏi cụ thể tới người xử lý.
Con người vẫn kiểm tra và xác nhận **giao dịch tiền thực tế**; ứng dụng không
tự chuyển tiền qua ngân hàng.

Mục tiêu của đợt trải nghiệm này là tìm hiểu liệu người làm công việc thật có
thể hiểu căn cứ, biết bước tiếp theo và giảm được công sức đối chiếu **toàn
quy trình** hay không. Nhóm cũng muốn nhận diện thao tác mới gây mất thời gian,
điểm dễ tin nhầm kết quả và những bước không khớp với cách tổ chức vận hành.

## 2. Ai nên tham gia và cách thử

Đề nghị ba người **đã trực tiếp nộp hoặc xử lý hồ sơ chi phí/quyết toán** tham
gia. Có thể là nhân viên phát sinh chi phí, kế toán hoặc người từng phê duyệt
ngoại lệ. Nhóm ghi nhận vai trò và kinh nghiệm thực tế của từng người; không
giả định cả ba đều có cùng vai trò.

Mỗi người dùng cùng bộ hồ sơ **giả lập** để thực hiện hoặc quan sát hai nhiệm
vụ dưới đây. Nếu điều kiện cho phép, họ xử lý một nhiệm vụ theo cách thường
làm, rồi bằng ứng dụng; ghi cả thời gian thao tác lẫn thời gian kiểm lại nguồn,
đợi người khác và sửa sai. Thứ tự cách làm được đổi giữa người tham gia để
giảm ảnh hưởng của việc đã quen bộ hồ sơ. Người hướng dẫn không đọc sẵn đáp án.

| Nhiệm vụ | Tài liệu và thao tác | Điều cần quan sát |
| --- | --- | --- |
| **Hồ sơ thường quy** | Giấy quyết toán, hóa đơn và chứng từ công ty đã ứng **4.000.000 đ** cho nhân viên; chi phí đủ điều kiện **3.240.000 đ**. Sau kết luận cần thu **760.000 đ**, nhân viên nộp bằng chứng hoàn tiền và kế toán xác nhận thực nhận. | Người dùng hiểu vì sao còn phải thu; có phân biệt yêu cầu thu, bằng chứng vừa tải và tiền công ty đã nhận; có biết ai làm bước tiếp theo? |
| **Hồ sơ mâu thuẫn** | Hai dòng chi **2.000.000 + 1.000.000 đ** nhưng giấy ghi tổng **3.500.000 đ**. Người dùng xem câu hỏi và căn cứ hệ thống nêu, rồi quyết định cần bổ sung/sửa gì. | Hệ thống có dừng phát hành tiền; người dùng có hiểu lệch **500.000 đ**, tìm được chứng từ liên quan và trả lời được mà không phải đoán? |

Nhiệm vụ thứ hai là để đánh giá **cách hệ thống hỏi khi chưa chắc chắn**, không
phải yêu cầu người dùng chấp nhận một trong các số tiền đang mâu thuẫn. Nhóm
có thể thay dữ liệu giả lập bằng một hồ sơ đã được phép sử dụng và ẩn danh,
nhưng sẽ giữ cùng mục tiêu quan sát.

## 3. Câu hỏi muốn gửi cho ba người dùng

1. Hiện nay anh/chị xử lý một hồ sơ tương tự từ lúc nhận đến lúc xong như thế
   nào? Bước nào mất công nhất, ai thường phải hỏi ai?
2. Sau khi nhìn kết quả của InvoiceReferee, anh/chị có biết hệ thống dựa vào
   tài liệu và con số nào không? Chỗ nào anh/chị vẫn phải mở giấy gốc để chắc chắn?
3. Khi giấy ghi tổng **3.500.000 đ** nhưng hai dòng chỉ cộng thành
   **3.000.000 đ**, câu hỏi của hệ thống có giúp anh/chị biết cần làm gì tiếp
   không? Còn thiếu thông tin gì trong câu hỏi?
4. Anh/chị có phân biệt được **số tiền nhân viên khai đã hoàn**, **yêu cầu thu**
   và **tiền kế toán xác nhận đã nhận** trên giao diện không?
5. Có thao tác nào ứng dụng khiến anh/chị phải nhập lại, kiểm lại hoặc liên hệ
   thêm với người khác so với cách làm hiện tại không?
6. Có lúc nào kết quả trình bày quá chắc chắn khiến anh/chị dễ tin dù chứng từ
   chưa đủ hoặc còn mâu thuẫn không? Anh/chị muốn thấy cảnh báo/căn cứ thế nào?
7. Nếu dùng cho công việc thật, phần nào anh/chị sẵn sàng dùng ngay, phần nào
   chưa thể dùng? Vì sao?
8. Nếu chỉ được thay đổi **một điều** ở sản phẩm, anh/chị muốn thay đổi gì?

Người tham gia có thể trả lời theo vai trò của mình; câu nào không thuộc công
việc của họ sẽ được ghi **không áp dụng**, không suy đoán thay câu trả lời.
Đề nghị họ nêu ví dụ cụ thể và cho phép ghi lại nhận xét **nguyên văn**.

## 4. Nhóm sẽ ghi nhận và xử lý phản hồi như thế nào

| Nội dung | Cách ghi nhận |
| --- | --- |
| Người tham gia | Vai trò, loại công việc đang làm, kinh nghiệm liên quan; danh tính/liên hệ lưu riêng theo mức đồng thuận. |
| Công sức trước/sau | Thời gian thao tác, đọc/tra lại chứng từ, chờ hệ thống hoặc người khác, số lần hỏi và sửa. Không chỉ đo thời gian OCR. |
| Kết quả nhiệm vụ | Bước hoàn thành được, sai sót, chỗ phải nhờ hướng dẫn và lý do dừng. |
| Phản hồi | Lời nhận xét nguyên văn, điều hữu ích, **ít nhất một bất cập hoặc tác động tiêu cực**. |
| Cải tiến | Chọn một vấn đề có bằng chứng, thay đổi sản phẩm, lưu ảnh/luồng trước–sau và commit liên quan; thử lại nếu kịp. |

Nhóm sẽ chỉ báo cáo số liệu **đã đo** và trích dẫn **đã được người tham gia xác
nhận**. Với ba người, kết quả được mô tả theo từng tình huống; không suy ra tỷ
lệ hiệu quả chung cho mọi doanh nghiệp. Dữ liệu của sản phẩm hiện dùng trong
demo là **giả lập**; các xác nhận người dùng thật chỉ được ghi sau buổi thử và
không được tạo thay người tham gia.

## 5. Phạm vi và giới hạn để người dùng biết trước

- Bản demo tập trung vào quyết toán khoản chi do nhân viên thanh toán bằng VND.
  Hồ sơ mẫu, công ty, khoản ứng và chính sách là dữ liệu giả lập có chủ đích.
- OCR/AI có thể đọc hoặc phân loại sai; người dùng cần xem được nguồn để sửa
  hoặc yêu cầu xác minh khi gặp mâu thuẫn.
- Ứng dụng theo dõi giao dịch đã ghi vào **hồ sơ**, không xác nhận đã kiểm tra
  toàn bộ lịch sử ngân hàng của một tổ chức.
- Lệnh yêu cầu chi/thu trong ứng dụng không chứng minh tiền đã chuyển. Tiền
  thực nhận do người có trách nhiệm kiểm tra và xác nhận.
- Nhóm chưa công bố thời gian tiết kiệm hay mức độ hài lòng trước khi có kết
  quả thử nghiệm thật.

## 6. Đường dẫn và tài liệu gửi kèm

| Thành phần | Đường dẫn / việc nhóm cần điền |
| --- | --- |
| Bản dùng thử đúng phiên bản gửi người dùng | **[Điền URL truy cập công khai; thử bằng cửa sổ ẩn danh]** |
| Hướng dẫn thao tác ngắn và hai bộ hồ sơ giả lập | **[Điền link Drive/tệp hướng dẫn]** |
| Video demo tối đa 3 phút của phiên bản hiện tại | **[Điền link video]** |
| Năm slide theo mẫu cuộc thi | **[Điền link slide]** |
| GitHub | https://github.com/Nnguyen-dev2805/InvoiceReferee — **[kiểm tra phiên bản nộp đã được cập nhật trên repo công khai]** |
| Người liên hệ hỗ trợ buổi thử | **[Điền tên và kênh liên hệ]** |

**Đề nghị phản hồi:** Nêu rõ vai trò của mỗi người, trả lời các câu hỏi ở Mục 3
bằng lời của họ, chỉ ra cả điểm thuận lợi và bất cập. Nhóm sẽ dùng phản hồi để
điều chỉnh sản phẩm và cập nhật phần người dùng trên slide sau khi nhận kết quả.

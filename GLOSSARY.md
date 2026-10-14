# InvoiceReferee — Quyết toán chi phí nhân viên

Ngôn ngữ dùng cho hồ sơ quyết toán sau công việc và nghĩa vụ tiền liên quan.
Các thuật ngữ này phân biệt yêu cầu, kết luận kiểm tra và tiền thực tế.

## Language

**Hồ sơ quyết toán**:
Tập hợp khai báo, chứng từ và dữ kiện liên quan dùng để xác định chi phí đủ điều kiện và nghĩa vụ tiền còn phải xử lý.
_Avoid_: Dùng một hóa đơn hoặc một giấy đề nghị để chỉ toàn bộ hồ sơ.

**Quyết toán chi phí**:
Việc đối chiếu chi phí được chấp nhận với lịch sử tiền liên quan để xác định công ty trả thêm, nhân viên hoàn lại hoặc cân bằng.
_Avoid_: Dùng “hoàn ứng” cho mọi kết quả chi/thu.

**Chi phí nhân viên đã thanh toán**:
Khoản chi phục vụ công việc mà nhân viên thực tế trả cho bên cung cấp, bằng tiền ứng hoặc tiền riêng.
_Avoid_: Đồng nhất với chi cá nhân không phục vụ công việc.

**Chi phí nhân viên khai đã thanh toán**:
Khoản tiền nhân viên xác nhận mình đã trả cho bên cung cấp theo nội dung đề nghị quyết toán.
_Avoid_: Đồng nhất lời khai với giao dịch ngân hàng đã được xác minh hoặc chi phí đã được công nhận theo policy.

**Giải trình**:
Nội dung người nộp hồ sơ làm rõ lý do thiếu chứng từ hoặc thông tin khác nhau của một khoản chi.
_Avoid_: Đồng nhất với phê duyệt ngoại lệ hoặc xác nhận tiền đã thực nhận.

**Tiền ứng thực nhận**:
Khoản tiền ứng mà nhân viên đã thực tế nhận từ công ty.
_Avoid_: Đồng nhất với số xin ứng hoặc số ứng đã được duyệt.

**Chi phí công ty trả trực tiếp**:
Khoản chi công việc do công ty thanh toán trực tiếp cho bên cung cấp.
_Avoid_: Cộng vào khoản tiền phải hoàn trả cho nhân viên.

**Chi phí nhân viên được chấp nhận**:
Phần chi phí nhân viên đã thanh toán được công nhận theo policy hoặc quyết định ngoại lệ có hiệu lực.
_Avoid_: Đồng nhất với mọi khoản nhân viên khai đã chi hoặc số tiền công ty còn phải trả.

**Tổng chi công việc**:
Tổng chi thực tế phục vụ hoạt động trong phạm vi đối chiếu, gồm phần nhân viên và công ty trả trực tiếp.
_Avoid_: Cắt về ngân sách hoặc coi tổng chi bằng phần chi phí được hoàn trả cho nhân viên.

**Yêu cầu chi**:
Chỉ dẫn chờ thực hiện việc công ty trả một khoản tiền đã được xác định đủ điều kiện cho người nhận.
_Avoid_: Gọi là đã chi hoặc đã nhận tiền.

**Yêu cầu thu**:
Chỉ dẫn chờ thực hiện việc thu một khoản tiền đã được xác định từ người có nghĩa vụ hoàn lại.
_Avoid_: Gọi là đã thu hoặc tự coi tiền đã về công ty.

**Quyền tự xử lý**:
Phạm vi tổ chức giao cho hệ thống để tự hoàn tất kết luận và yêu cầu chi/thu thường quy.
_Avoid_: Coi vai trò hoặc chức danh tự động là quyền không giới hạn.

**Ngân sách hoạt động**:
Mức kinh phí được tổ chức chấp nhận cho một hoạt động công việc cụ thể, theo quyết định hoặc quy định có hiệu lực.
_Avoid_: Đồng nhất với dự toán do nhân viên đề nghị hoặc tiền ứng thực nhận.

**Xác nhận nghiệp vụ**:
Thông tin được người có trách nhiệm xác nhận về một dữ kiện cụ thể, kèm căn cứ và phạm vi xác nhận.
_Avoid_: Đồng nhất với phê duyệt ngoại lệ hoặc lời đồng ý chung cho toàn hồ sơ.

**Cân bằng nghĩa vụ tiền**:
Tình trạng dữ kiện và lịch sử tiền đã được xác minh cho thấy không còn khoản công ty phải trả hoặc nhân viên phải hoàn trong phạm vi hồ sơ.
_Avoid_: Suy cân bằng từ việc chưa tìm thấy chứng từ hoặc coi một yêu cầu chi/thu vừa tạo là đã thực hiện.

**Chi phí công việc đã phát sinh**:
Giá trị chi phí của hoạt động đã được xác lập và có căn cứ, bao gồm phần chưa thanh toán nếu nghĩa vụ đã được xác minh.
_Avoid_: Đồng nhất với tiền đã chi, dự toán tương lai hoặc tổng ghi trên hóa đơn chưa được xác minh.

**Chi phí nhân viên trực tiếp thanh toán**:
Phạm vi bản đầu: khoản chi công việc mà nhân viên thực tế đã trả cho bên cung cấp, bằng tiền ứng hoặc tiền riêng; công ty trả trực tiếp nhà cung cấp nằm ngoài phạm vi.
_Avoid_: Đồng nhất với khoản công ty trả trực tiếp hoặc khoản chưa ai trả.

**Phần ngoài phạm vi**:
Khoản chi mà nguồn cho thấy công ty trả trực tiếp hoặc người trả thuộc bên khác, được giữ làm dữ kiện để đối chiếu và báo, không đưa vào phép tính hoàn trả nhân viên.
_Avoid_: Bỏ nguồn để kết luận tiền, hoặc ép thành khoản nhân viên đã trả.

**Lời xác nhận chi tiền**:
Lời nhân viên tự xác nhận có trách nhiệm rằng mình đã trả một khoản chi, dùng làm một phần căn cứ cho khoản nhân viên đã trả khi có chứng từ dịch vụ và không mâu thuẫn trọng yếu.
_Avoid_: Đồng nhất với giao dịch ngân hàng đã được xác minh hoặc chứng từ thanh toán độc lập.

**Căn cứ hóa đơn (policy demo)**:
Quy ước nghiệp vụ cho demo (chốt 14/10/2026): hóa đơn gốc hợp lệ, gắn đúng nhân viên và hồ sơ, được chấp nhận làm căn cứ khoản chi nhân viên đã thanh toán, không cần giấy xác nhận thanh toán riêng.
_Avoid_: Gọi là xác minh ngân hàng hoặc tạo giao dịch ngân hàng/confirmation giả; coi bên mua là công ty trên hóa đơn là người trả.

**Loại tài liệu**:
Nhãn phân loại nội dung một tài liệu (hóa đơn, biên nhận, vé, chứng từ thanh toán, giấy quyết toán, …), do model đề xuất và code kiểm.
_Avoid_: Đồng nhất với vai trò chứng cứ của tài liệu đó trong hồ sơ.

**Vai trò chứng cứ**:
Vai trò của một tài liệu trong hồ sơ (khai báo quyết toán, chứng từ chi phí gốc, căn cứ thanh toán, tài liệu hỗ trợ, chưa xác định); một tài liệu có thể mang nhiều vai trò nếu mỗi vai trò có căn cứ riêng.
_Avoid_: Đồng nhất với loại tài liệu, hoặc coi tài liệu hỗ trợ là chứng từ gốc.

**Trạng thái trường**:
Kết quả trích xuất một trường: có thấy (`FOUND`), không có trong nguồn (`NOT_PRESENT`), không đọc được (`UNREADABLE`), mơ hồ (`AMBIGUOUS`), hoặc không áp dụng (`NOT_APPLICABLE`).
_Avoid_: Coi "không thấy" là số 0, hoặc suy đoán khi không đọc được.

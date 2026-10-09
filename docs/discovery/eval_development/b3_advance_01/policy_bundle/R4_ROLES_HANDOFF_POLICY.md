# R4 — Ba vai, quyền quyết định và bàn giao hồ sơ

Ngày: 09/10/2026 · Trạng thái: **CHỦ DỰ ÁN ĐÃ ĐỒNG Ý MÔ HÌNH BA VAI; BÀN GIAO CỤ THỂ DƯỚI ĐÂY ĐỂ REVIEW, CHƯA CODE/RUNTIME**.

Căn cứ [policy ngân sách tổng](R4_WORK_BUDGET_POLICY.md), [evidence R4.2](R4_EVIDENCE_RULES_DRAFT.md), [B8/B9](B8_B9_MVP_PROPOSAL.md). Thay đề xuất hai cấp duyệt tiền tại [bản lịch sử](R4_AUTHORITY_POLICY_DRAFT.md); không kế thừa10/30triệu. Lead tự review, không subagent. Đây là workflow MVP giả lập, không tuyên bố đã xác minh cơ cấu/quyền của công ty thật.

## 1. Ba vai nghiệp vụ đã thống nhất

| Vai | Được thực hiện | Ranh giới |
| --- | --- | --- |
| Nhân viên | Nộp đề nghị, mục đích và nguồn; trả lời/bổ sung đúng phần; cung cấp căn cứ chi/hoàn tiền phía mình | Không khai thay company-side facts/absence hoặc tự tạo ngân sách/approval |
| Kế toán | Rà soát report và căn cứ; xử lý/cập nhật fact đúng scope; chuẩn bị trình duyệt; thực hiện/ghi chi thu theo quyết định và cung cấp nguồn tài chính phù hợp | Không phê duyệt ngân sách/ứng/quyết toán hay ngoại lệ chỉ vì role kế toán; không thay sourcequality bằng đánh dấu đã kiểm tra |
| Người duyệt có quyền — gọi là sếp trong demo | Cho phép công việc, duyệt ngân sách/ứng, quyết định chấp nhận/ngoại lệ và phê duyệt quyết toán trong phạm vi được giao | Chức danh/role picker không tự tạo quyền; approval không sửa số mờ, không chứng minh tiền đã trả hoặc xóa nghĩa vụ |

Hệ thống là bên chuẩn bị đối chiếu, không thêm một role người dùng. Một operator có thể mô phỏng ba vai; sự kiện vẫn ghi đúng người/vai/phạm vi. Không xây auth/tenancy hay bắt có ba tài khoản thật.

## 2. Một người duyệt, các nội dung quyết định riêng

| Nội dung | Cần xác định | Thời điểm |
| --- | --- | --- |
| Cho phép công việc | Người/công việc, mục đích, địa điểm/thời gian/phạm vi và điều kiện | Trước công việc hoặc dùng căn cứ phù hợp đã có |
| Ngân sách và ứng | Tổng B, phần dự kiến company-direct/employee, số ứng duyệt và quyền/phạm vi | Trước chi; có thể cùng quyết định với cho phép công việc khi đủ quyền/thông tin |
| Chấp nhận chi phí, ngoại lệ và quyết toán | Các khoản/phần, nguồn/rule, E/S khi đủ, số/chiều và nghĩa vụ cần xử lý | Sau phát sinh chi hoặc hủy cần xử lý ứng |

Không một boolean Approved cho tất cả. Duyệt công tác không tự duyệtB; duyệtB không tự cấp ứng; duyệt ứng không tự là employee nhận; quyết toán không tự là đã thực hiện tiền. Một thao tác có thể chứa nhiều nội dung nếu nguồn/quyền/phạm vi rõ, không yêu cầu nhiều lần bấm theo số loại quyết định.

Đề nghị ban đầu đang xin phép/duyệt ngân sách là input hợp lệ để hệ thống và kế toán chuẩn bị, không yêu cầu nhân viên nộp lại chính approval đang xin. Chưa duyệt B không tự là đủ điều kiện chi; đưa đúng nội dung xin quyết định tới người duyệt. Căn cứ bên ngoài còn hiệu lực được dùng lại, không bắt duyệt lại chỉ vì nhập ngoài app.

## 3. Bàn giao trước công việc

1. Nhân viên nộp công việc, dự toán tổng và phân chia dự kiến, số xin ứng, nguồn sẵn có.
2. Hệ thống kiểm tra thông tin/dự toán/history cần thiết, chuẩn bị report và câu hỏi; phần thiếu fact được hỏi đúng owner.
3. Kế toán rà soát report, giải quyết vướng mắc về nguồn/tiền, trình các nội dung cần quyết định. Không tự ghép/tính lại toàn bộ như một yêu cầu bắt buộc của workflow.
4. Người duyệt cho phép/từ chối/trả lại, duyệtB/ứng trong quyền. Nội dung đã được phép và có căn cứ không bị xin lại vô ích; thay đổi ảnh hưởng cần re-check.
5. Kế toán thực hiện chi ngoài app theo quyết định có hiệu lực, cung cấp source; hệ thống đối chiếu actualreceipt. Không auto transfer/auto retry.

Từ chối không chi mới; khoản ứng bên ngoài đã thực nhận hoặc nghĩa vụ đang có vẫn phải giữ để xử lý theo workflow, không đóng sạch vì một đề nghị bị từ chối. Lệnh pending/mâu thuẫn actualreceipt phải đối chiếu trước khi cho thực hiện lại.

## 4. Bàn giao sau công việc

1. Nhân viên nộp bảng kê/chứng từ/phạm vi đang giải quyết; kế toán cung cấp nguồn công ty/history phù hợp đã có.
2. Hệ thống đọc/đề xuất ghép, kiểm tra số học/rule/budget/payer/duplicate/history, tính E/S khi toàn fact/policy ảnh hưởng đủ rõ; report có refs và issue owners.
3. Kế toán rà soát bảng đối chiếu, mở nguồn cần xác minh và sửa/bổ sung có căn cứ. **Đã rà soát** là trạng thái kiểm tra, không phê duyệt tiền hoặc miễn gate.
4. Người duyệt quyết định: phê duyệt kết quả đầy đủ; trả lại vì lỗi; không chấp nhận theo căn cứ; hoặc quyết định ngoại lệ trong quyền. Fact bắt buộc còn mờ/thiếu thì chưa được phê duyệt kết quả đủ để chi cuối.
5. Kế toán thực hiện chi/thu ngoài app theo quyết định hiện áp dụng; hệ thống đối chiếu thực nhận và đóng khi đủ toàn nghĩa vụ/scope/mốc nguồn theo B9.

VượtB có fact rõ có thể trình người duyệt quyết định ngoại lệ, không bắt người nộp tìm thêm chứng từ không giải quyết được policy. Missing fact khác exception, beyond-authority khác không thích khoản chi. Nếu quyết định muốn đổi E/S thì ghi khoản/phần/lý do, re-check source/rule/phép tính/quyền trước khi làm căn cứ thực hiện; không sửa field S đơn độc. Duyệt toàn nghĩa vụ nhưng chỉ thực hiện một phần giữ phần còn lại, không tự giảm nghĩa vụ.

## 5. Ví dụ một hồ sơ trình duyệt

Giả lập đủ căn cứ: B=8triệu, company-direct3triệu, employee5triệu hợp lệ, A=2triệu, RA=P=RP=0, không nghĩa vụ khác/pending. Hệ thống tính T=8, E=5, S=+3. Kế toán rà soát report/nguồn và trình. Người duyệt phê duyệt chi3triệu trong quyền. Kế toán chuyển ngoài app; nguồn phù hợp xác định nhân viên nhận3 thì hệ thống ghi receipt, giữ lịch sử, kiểm tra điều kiện đóng. Invoice company-direct không thành đề nghị hoàn cho employee; approval của sếp không thành P=3 trước receipt.

Nếu người duyệt chỉ cho trả2triệu, không tự biến S=3 thành2. Phải phân biệt muốn đổi phần chi phí chấp nhận có căn cứ với duyệt3 nhưng thực hiện2 trước, theo B8/B9 đã chốt; trường hợp sau vẫn còn1triệu chưa thực hiện.

## 6. Quyền của một người duyệt vẫn phải có căn cứ

MVP giả định người duyệt được giao cả quyền công việc và tài chính trong một phạm vi được công bố. Không suy rằng mọi trưởng bộ phận trong doanh nghiệp có quyền này. Cần biết nội dung được giao, công việc/phạm vi, hạn chế tiền/ngoại lệ nếu có và hiệu lực nguồn quyền. Thiếu hạn chế tiền không tự thành vô hạn; muốn giới hạn bằng số cần một tham số riêng được chủ dự án chốt, không hai cấp10/30 như cũ.

Vượt phạm vi người duyệt: hệ thống giữ report, ghi nội dung/số/nguồn cần quyền, yêu cầu căn cứ quyết định/giao quyền phù hợp. Có thể tiếp nhận căn cứ ngoài app khi đủ; không tạo thêm role UI để giả đã giải quyết. Hệ thống không tự gửi thông báo ra email/chat ngoài app.

## 7. Tự phản biện và bước tiếp

Workflow có hai checkpoint con người thường xuyên: kế toán rà soát và người duyệt quyết định. Đừng giới thiệu là hệ thống tự hoàn tất toàn bộ9bước. Muốn giảm việc, report phải giảm tìm/ghép/cộng nguồn; không buộc kế toán và sếp kiểm lại toàn bộ theo cách cũ. R5 đo effort/timing của cả hai checkpoint cùng input prep và question-answer, không chỉ thời gian AI. Rủi ro job check/report vs routine hoàn toàn tự động theo brief vẫn mở tại R3.

Tiếp theo khóa nguồn công ty/nhân viên, phạm vi coverage, phiên bản policy và nguồn giao quyền đủ cho case/gold. [R4.4 nguồn tiếp nhận](R4_SOURCE_INTAKE_CONTRACT.md) cụ thể hóa phần nguồn để review. Không có con số quyền đã được chốt ở bước này; không thêm tỷ lệ ứng, trần nhóm hoặc hạng vé ngầm. Thiết kế nguồn/evaluation trước kiến trúc/code theo roadmap, không coi mô hình role là implementation/runtime evidence.

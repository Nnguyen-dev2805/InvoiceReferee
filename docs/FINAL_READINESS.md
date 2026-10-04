# InvoiceReferee — Khoảng cách đến chung kết

Ngày lập: 04/10/2026. Source đã đọc tại HEAD `196e266` cùng working tree.

> Sau khi lập bản này, người phát triển đã yêu cầu dọn implementation và tạo
> nhánh `rebuild`. Những mô tả source dưới đây là hiện trạng bản Sprint 1 tại
> `196e266`, không phải năng lực đang có trên working tree rebuild.

Đây là bản phân tích hiện trạng và thứ tự công việc đề xuất, chưa phải thiết kế
đã được duyệt hoặc kế hoạch triển khai. Chưa thay đổi production code, chạy test
hay gọi provider trong quá trình lập bản này.

## Mục tiêu và căn cứ

Người phát triển xác nhận đã vượt qua Sprint 1. Điều này không được dùng làm
bằng chứng rằng mọi yêu cầu Sprint 1 đã hoàn tất. Mục tiêu tiếp theo là đóng các
khoảng cách Sprint 1 và tạo bằng chứng Sprint 2 để tham dự chung kết 17/10.

Căn cứ cuộc thi: [đề bài trong repo](Challenge_Brief_OrganizationAI_VN.docx.md),
đặc biệt mục 2.A, mục 3 và mục 4–5. Theo tài liệu này, khóa bài nộp ngày 15/10,
Demo Day ngày 17/10. Người phát triển cho biết đã nhận phản hồi khá chung
chung và sẽ cung cấp sau; nội dung chưa được đọc trong bản phân tích này.
Khi nhận phản hồi hoặc cập nhật của BTC, phải đối chiếu lại phạm vi và mốc thời gian.

Thang điểm vòng chung kết được ghi tại mục 4: demo 45 điểm, phản biện 35 điểm,
kiểm thử xác thực đề bài 20 điểm. Thang 40/20/20/20 là cách phân bổ của vòng
sơ loại. Đề A đánh giá 5 trường hợp mới: phát hiện và phân loại chuyển tiếp
(8 điểm), tránh chuyển tiếp sai hồ sơ thường quy (6 điểm), câu hỏi cụ thể
(6 điểm).

## Bảng hiện trạng

`IMPLEMENTED` dưới đây chỉ khẳng định source đã được đọc. Không có kết quả
runtime mới trong bản phân tích này. `INCONCLUSIVE` có nghĩa chưa có bằng
chứng đủ để kết luận, không có nghĩa người phát triển chưa thực hiện.

| Yêu cầu / năng lực | Hiện trạng | Bằng chứng và khoảng cách |
| --- | --- | --- |
| Tiếp nhận và xử lý hồ sơ mới | IMPLEMENTED một phần | `SubmitCaseService.submit` nối validation, dedupe, persistence và `CaseProcessingService.process_case`. Chưa xác minh input mới với provider thật. |
| Đọc chứng từ và xem lại nguồn | IMPLEMENTED | Mistral adapter, OCR hierarchy, evidence preview và dữ liệu OCR theo evidence ID. Hỗ trợ xử lý ảnh/PDF; định dạng được nhận ở đầu vào rộng hơn. |
| Quy định nghiệp vụ làm căn cứ cho giám khảo | Chưa thấy tài liệu policy đủ cho mục tiêu đề A trong bộ docs đã đọc | Có policy đối chiếu kiểm kê trong Python. Cần chốt một quy trình, điều kiện thường quy, điều kiện ngoài quy định và giới hạn thẩm quyền; chưa tự chọn hạn mức. |
| Tự động xử lý hồ sơ thường quy | IMPLEMENTED một phần | Runtime có `PASS`, nhưng primary-only có thể kết thúc ngay sau OCR quality. Cần định nghĩa chính xác việc hệ thống tự hoàn tất và điều kiện được phép hoàn tất. |
| Ba nhóm bất định của đề A | Chưa được biểu diễn trong output quyết định đã đọc | `ProcessingDecision` chỉ có `PASS` và `NEEDS_HUMAN`; trạng thái này đang gộp thiếu dữ kiện, lỗi kỹ thuật và xung đột. Cần phân loại thực tế chưa biết / ngoài quy định / vượt thẩm quyền. Tên enum cụ thể là lựa chọn thiết kế, không phải tên bắt buộc trong đề. |
| Câu hỏi chuyển tiếp cụ thể | IMPLEMENTED một phần | Có câu hỏi từ low-confidence và inventory findings. Cần đánh giá người dùng có thể trả lời ngay hay vẫn phải tự tìm lại vấn đề trong hồ sơ. |
| Không khẳng định trên dữ liệu đáng ngờ | IMPLEMENTED một phần | Có nhánh dừng khi provider lỗi, output invalid, thiếu coverage hoặc uncertainty cần cho đối chiếu. Chưa có bằng chứng bao phủ toàn bộ tình huống nghiệp vụ; OCR confidence không chứng minh tính hợp lệ của hồ sơ. |
| Kế toán trả lời và hồ sơ tiếp tục xử lý | Chưa có trong luồng giao diện đã đọc | Accounting hiển thị kết quả và cho xóa hồ sơ. Chưa thấy hành động trả lời câu hỏi, xác nhận dữ kiện hoặc quyết định có thẩm quyền rồi chạy lại có truy vết. |
| Audit, can thiệp dừng / ghi đè | IMPLEMENTED audit cơ bản; các control chưa có trong luồng đã đọc | Có `CASE_CREATED`, `EVIDENCE_ATTACHED`, `CASE_PROCESSED`. `processing.json` bị ghi đè khi xử lý lại; xóa case xóa luôn history. Cần lưu quyết định gốc, căn cứ, actor, lý do và hành động can thiệp. |
| Verify chung: 4 case tuần tự, expected/actual, pass/fail, timestamp | IMPLEMENTED runner cơ bản; thiếu hợp đồng nghiệm thu này | `app/views/verify_runner.py` gọi service thật, dùng `ThreadPoolExecutor`, hiển thị actual status và elapsed time. Chưa có đối chiếu expected/actual hoặc kết luận test pass/fail trong runner đã đọc. |
| Verify đề A: 3 thường quy + 2 chuyển tiếp | INCONCLUSIVE về bộ dữ liệu; runner chưa phân suite này | Cần suite riêng với expected action, nhóm chuyển tiếp và câu hỏi kỳ vọng được kiểm chứng trên production path. |
| Ít nhất 15 tình huống | INCONCLUSIVE | Chưa kiểm kê và gán nhãn bộ dữ liệu hiện tại trong bản phân tích này. Không dùng số lượng thư mục hoặc unit test thay cho số tình huống nghiệp vụ hợp lệ. |
| Đánh giá trên tập độc lập | INCONCLUSIVE | Cần tách dữ liệu phát triển/điều chỉnh khỏi tập đánh giá cuối; báo cáo bỏ sót chuyển tiếp và chuyển tiếp thừa với tử số/mẫu số rõ ràng. |
| Tự điều chỉnh ngưỡng từ phản hồi | Chưa có trong source cấu hình và xử lý đã đọc | Hiện có `OCR_WORD_REVIEW_THRESHOLD` cố định theo cấu hình. Cần định nghĩa ngưỡng chuyển tiếp nào được điều chỉnh, feedback nào đủ tin cậy, giới hạn và cách kiểm chứng; không đồng nhất OCR threshold với mọi quyết định chuyển tiếp. |
| Ít nhất 3 người dùng thực tế và một cải tiến từ phản hồi | INCONCLUSIVE | Cần người trực tiếp làm nghiệp vụ, phản hồi của chính họ, bằng chứng trước/sau và ít nhất một bất cập phát sinh. Không thể tạo bằng chứng này chỉ bằng code. |
| Live URL và runbook tái lập | INCONCLUSIVE | Không suy ra đã hoặc chưa deploy từ source. Cần xác minh deployment thực tế và clean-clone runbook; dữ liệu demo không được lẫn dữ liệu nhạy cảm. |
| 5 slide, video tối đa 3 phút, build log 1 trang | INCONCLUSIVE về bộ bài nộp | Có `docs/BUILD_LOG.md`, nhưng cần cập nhật theo công việc và bằng chứng mới; chưa kiểm tra slide/video hiện có. |

## Thứ tự công việc đề xuất

1. **Chốt quy trình và hợp đồng quyết định.** Viết quy định nghiệp vụ hẹp và
   kiểm chứng được; xác định input, kết quả tự động, ba nhóm chuyển tiếp,
   quyền trả lời/phê duyệt và cách phân biệt lỗi kỹ thuật. Đây là phụ thuộc
   trước khi thiết kế policy, nhãn testcase và feedback.
2. **Hoàn thiện một vòng xử lý có con người.** Nối các gate đang có với kiểm tra
   nghiệp vụ đã chốt; tạo câu hỏi cụ thể; tiếp nhận câu trả lời; tiếp tục xử lý;
   bảo toàn audit và quyết định ban đầu khi can thiệp.
3. **Hoàn thiện Verify và đánh giá độc lập.** Dùng cùng đường production;
   expected/actual rõ ràng; 4 core case và 5 case đề A; bộ ít nhất 15 tình huống;
   tập độc lập và số liệu lỗi chuyển tiếp. Một hồ sơ chuyển tiếp đúng có thể là
   một testcase đạt — không dùng `PASS` nghiệp vụ làm kết luận test đúng.
4. **Làm bằng chứng Sprint 2 song song.** Mời 3 người dùng ngay; ghi baseline,
   kiểm thử trải nghiệm, phản hồi, bất cập và cải tiến. Thiết kế việc điều chỉnh
   ngưỡng từ feedback sau khi biết feedback và quyết định nào cần điều chỉnh;
   tách dữ liệu điều chỉnh khỏi đánh giá cuối.
5. **Đóng gói và diễn tập.** Xác minh live URL, clean-clone runbook, provider,
   dữ liệu an toàn, 5 slide đúng cấu trúc, video và build log. Diễn tập 5 input
   mới, giải thích căn cứ từng quyết định và thao tác can thiệp.

Phần 4 phải khởi động cùng phần 1. Không đợi hoàn tất mọi tính năng mới tìm
người dùng. Mốc đề xuất: hoàn thiện luồng chính 04–09/10, kiểm thử độc lập và
cải tiến từ phản hồi 10–12/10, ổn định và đóng gói 13–15/10, diễn tập
16–17/10. Đây là phân bổ ban đầu, chưa cam kết khả thi khi chưa biết nhân lực,
khả năng tiếp cận người dùng và phản hồi BTC.

## Những quyết định còn cần làm rõ

- Phản hồi Sprint 1 hoặc bài toán thách thức riêng từ giám khảo.
- Quy trình nghiệp vụ và quy định thực tế được người dùng chuyên môn chấp nhận.
- Nhân lực/thời gian phát triển; người dùng có thể tham gia; hiện trạng deployment.
- Bộ dữ liệu, nhãn và quyền sử dụng; bằng chứng Sprint 2 đã có ngoài repo.

## Lệch tài liệu đã xác định

`docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md` và build log vẫn
ghi Verify chưa tồn tại. Source hiện có trang Verify nối từ composition root.
Trang này chưa tương đương Verify đủ yêu cầu cuộc thi. OCR debug vẫn tồn tại
nhưng sidebar hiện chỉ cho chọn Nhân viên, Kế toán và Verify. Cần cập nhật tài
liệu theo từng thay đổi đã được kiểm chứng.

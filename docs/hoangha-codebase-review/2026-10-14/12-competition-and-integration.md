# Căn cứ đề thi và tiêu chuẩn kết hợp Hoangha với final

Ngày đọc: 14/10/2026. Nguồn yêu cầu: [đề thi](../../Challenge_Brief_OrganizationAI_VN.docx.md), mục 1, 2A, 3 và 4. Đây là bảng tiêu chuẩn để đọc báo cáo code; phần đối chiếu thực thi được tổng hợp sau khi hoàn thành các báo cáo module. Không phải chứng nhận đủ điều kiện thi hay dự đoán kết quả cuộc thi.

## 1. Điều phải chứng minh

| Yêu cầu | Bằng chứng kỹ thuật cần có | Bằng chứng ngoài code cần có |
| --- | --- | --- |
| Routine tự xử lý | Hồ sơ đủ căn cứ chạy đến hành động nghiệp vụ xác định, không bắt người đánh giá lại mọi hồ sơ | Demo người ngoài chạy được, giới hạn hành động công bố rõ |
| FACT / POLICY / AUTHORITY | Mỗi lý do chuyển người giữ đúng nhóm, đúng người có trách nhiệm và câu hỏi trả lời được | Rulebook rõ và các ca giám khảo mới xử lý hợp lý |
| Không khẳng định đầu vào nghi vấn | OCR/extraction/link trọng yếu chưa rõ không bị chuyển thành số 0 hoặc kết luận hợp lệ | Case lỗi và ngoại lệ tái lập được |
| Tối thiểu 15 case | Corpus có input thực dùng, kỳ vọng riêng, chạy cùng application service | Công bố giả lập/thực tế |
| Verify Core4 và Escalation5 | Một thao tác chạy, kết quả actual/expected và timestamp; Escalation5 gồm 3 routine + 2 chuyển người | Trang Verify dùng được trong khoảng thời gian chấm |
| Dữ liệu mới | Luồng không phụ thuộc ID, filename hoặc gold; nhận hồ sơ chưa từng có | Giám khảo cung cấp input mới |
| Audit / Stop / override | Truy được hành động, thời điểm, dữ liệu, lý do; dừng thật và ngăn kết quả trễ ghi đè | Slide 2 mô tả đúng vị trí con người trong runtime |
| Điều chỉnh ngưỡng có đánh giá | Feedback đúng trách nhiệm, thay đổi có phiên bản, kiểm tra trước/sau trên holdout | Không gọi dữ liệu tự sinh là feedback của nhân sự thực tế |
| Đánh giá độc lập | Định nghĩa mẫu số và oracle; báo tỷ lệ bỏ sót chuyển người và chuyển người thừa | Tập độc lập với development, công bố sai số và bất cập |
| Người dùng thực tế | Cơ chế lưu bằng chứng phản hồi và thay đổi sản phẩm | Ít nhất 3 nhân sự thực tế, phản hồi nguyên văn và 1 cải tiến truy vết được |
| Khả năng vận hành | Clean-clone runbook, cấu hình portable, LIVE thật được phân biệt với fake/replay | Public URL, lịch sử công khai, 5 slide, video <=3 phút và build log |

Việc không chuyển tiền ngân hàng trong app tương thích với việc tự tạo yêu cầu chi/thu: cần định nghĩa điểm hoàn thành routine tại ranh giới nghiệp vụ đã công bố. Nếu mọi routine vẫn bắt kế toán đánh giá lại đủ điều kiện thì chưa chứng minh tính tự chủ theo mục 2A.

## 2. Nguồn code và nguồn tài liệu có giá trị khác nhau

- [README Hoangha](../../../.worktrees/hoangha/README.md) ghi lệnh `verify.harness` là hợp đồng giai đoạn tiếp theo, chưa triển khai. Đây là lời công bố của repo, không phải kết quả chạy.
- [ARCHITECTURE Hoangha](../../../.worktrees/hoangha/docs/ARCHITECTURE.md) mục 3 ghi cấu trúc **đề xuất**, gồm nhiều module mang tính thiết kế. Không lấy cây thư mục này để mô tả cây code hiện tại.
- [PROJECT_OVERVIEW Hoangha](../../../.worktrees/hoangha/docs/PROJECT_OVERVIEW.md) tập trung Streamlit/inventory; FastAPI UC03 đã có composition root riêng. Phải phân biệt hai đường chạy trước khi kết luận một rule đã/chưa được thực thi.
- [usecase Hoangha](../../../.worktrees/hoangha/docs/new/usecase.md) có UC01, UC02 và lifecycle mục tiêu. Một mục xuất hiện trong đặc tả không đủ chứng minh đã có endpoint, service và persistence.
- Thiết kế `final` hiện tại ở [§1–4 và §14–15](../../final/ARCHITECTURE_AND_EVALUATION.md) là nguồn quyết định phạm vi tích hợp. Header hiện ghi §14 ACCEPTED: employee-paid, xác nhận có ngưỡng, giữ nguồn ngoài phạm vi, hoãn form giải trình. Phải kiểm tra operative contracts trước implementation; không dùng bản hỏi đáp cũ để mở lại quyết định đã chốt.

## 3. Ranh giới đề xuất cho việc kết hợp

| Phần | Hướng kết hợp | Điều kiện trước đưa vào sản phẩm |
| --- | --- | --- |
| OCR và cấu trúc page/block/word | Dùng cơ chế Hoangha dưới source/artifact ownership của final | Mọi PDF/ảnh qua OCR; giữ toàn bộ trang; lỗi và giới hạn explicit |
| Confidence | Dùng cách chọn candidate và kiểm tra coverage; đối chiếu critical fields với profile | Không coi thiếu confidence là đã rõ; model review không tự viết lại fact |
| LLM extraction | Dùng ý tưởng schema và prompt theo loại, qua provider hiện tại final | Field có provenance xác minh được; phân biệt missing/unreadable/ambiguous |
| Matching | Giữ logic lõi đã chọn, công bố giới hạn và kiểm regression | Không cộng trùng tài liệu hỗ trợ; thiếu tiền không thành 0; allocation có căn cứ |
| Policy và quyền | Một hợp đồng nghiệp vụ thống nhất của final | Không giữ hai bộ ngưỡng, hai người quyết định và hai định nghĩa đủ điều kiện |
| Storage / jobs / lifecycle | Một owner cho case/version/job/audit/Stop | Không tạo repository và worker thứ hai cùng quyết định một hồ sơ |
| Frontend | Tham khảo cách xem chứng từ và finding của Hoangha, dùng server view của final | Label đúng nghiệp vụ; server enforce quyền và trạng thái |
| Data / tests | Mang input thích hợp, tách gold và mapping nhãn | Chỉ số từ E2E thật; các UC ngoài scope không thành routine của final |

Đây là lựa chọn tích hợp để đạt một hệ thống thống nhất. Báo cáo chi tiết từng file xác định phần nào có thể tái sử dụng, phần nào cần adapter và phần nào phải sửa trước khi mang sang.

## 4. Giới hạn của lượt đọc này

Không chạy test suite, browser, provider LIVE hoặc public deployment. Không xác minh người dùng thực tế, consent, lịch sử public hay chất lượng OCR của 173 PDF. Những mục này phải có bằng chứng riêng; số file được đọc và số test được định nghĩa không thay thế kết quả vận hành.

# Nhật ký phát triển InvoiceReferee

**MLAI Hackathon 2026 · Track VNG · 15/10/2026**

> Nhóm dùng Codex và coding agent để rút ngắn vòng đọc mã nguồn, triển khai và kiểm thử. Con người chốt phạm vi, quy tắc nghiệp vụ và nghiệm thu kết quả.

**AI hỗ trợ viết và rà code → nhóm soát phần mã thay đổi, chạy kiểm thử và tái lập lỗi → con người chốt thay đổi.**

## AI được dùng trong quá trình lập trình

Codex được dùng để đọc và lần theo luồng xử lý trong mã nguồn, phân tích log, đề xuất và sửa code. Coding agent/subagent nhận các phần việc cụ thể như triển khai thay đổi, viết kiểm thử hồi quy hoặc phản biện một lát cắt kiến trúc. Nhóm chia việc để tăng tốc, nhưng tự quyết định quy tắc tiền, phạm vi sản phẩm và cách xử lý rủi ro.

Đầu ra agent được coi là đề xuất cần kiểm chứng: nhóm soát phần mã thay đổi, đối chiếu với hợp đồng nghiệp vụ và chứng từ gốc, chạy kiểm thử liên quan, rồi mới chấp nhận. Agent báo “đã xong” không thay thế kết quả kiểm thử hoặc việc xem code.

## Lợi ích, chi phí và thời gian phát sinh

AI giúp nhóm rút ngắn việc tìm điểm cần sửa, tạo bản triển khai đầu và chuyển lỗi đã tái lập thành kiểm thử hồi quy. Ví dụ TC05 dưới đây biến một sai lệch quan sát được thành quy tắc kiểm tra và hồi quy có thể chạy lại.

Phần việc phát sinh là chuẩn bị đúng ngữ cảnh cho từng agent, phối hợp thay đổi trên cùng codebase, đọc diff, xác minh trên dữ liệu nguồn và chạy lại kiểm thử sau mỗi sửa đổi. Nhóm chưa ghi tổng giờ công phát triển hoặc chi phí API của coding agent, nên không tuyên bố số giờ hay mức tiết kiệm chưa đo.

### TC05: từ tái lập lỗi đến kiểm thử hồi quy

**Lỗi tái lập:** Hệ thống từng cộng hai dòng 2.000.000 + 1.000.000 đ thành 3.000.000 đ và phát hành yêu cầu thu **1.000.000 đ**, dù giấy quyết toán in tổng 3.500.000 đ.

**Thay đổi kỹ thuật:** Coding agent bổ sung kiểm tra tổng các dòng với tổng in trên giấy và kiểm thử hồi quy cho chênh lệch này. Khi chạy lại cùng hồ sơ, trạng thái chuyển sang **“Chờ làm rõ”**, chưa kết luận số tiền và không phát hành yêu cầu thu. Đây là ví dụ phản chứng cho thấy phần mã AI hỗ trợ viết vẫn cần được kiểm tra bằng tình huống cụ thể.

## Tính năng lớn nhất đã cắt

Nhóm không xây **quy trình xin tạm ứng trước chuyến đi và ngân sách dự toán B riêng**. InvoiceReferee bắt đầu ở khâu quyết toán sau khi phát sinh chi phí; khoản ứng được ghi nhận theo tiền thực tế công ty đã giao và được xác nhận từ chứng từ. Theo quyết định demo, khoản ứng cũng là số tiền công ty giao cho công việc; lưu thêm một ngân sách B tách biệt sẽ tạo hai con số cần đối chiếu cho cùng quyết định, nhưng không tăng căn cứ về số tiền thực nhận.

Quyết định này giữ trọng tâm vào câu hỏi cốt lõi sau chuyến đi: chi phí nào có căn cứ, nhân viên thực trả bao nhiêu, đã nhận ứng và hoàn lại bao nhiêu. Đánh đổi là InvoiceReferee không tiếp nhận hay phê duyệt yêu cầu ứng trước, không quản lý hạn mức dự toán riêng và không so sánh ngân sách kế hoạch với chi phí thực tế. Các bước đó thuộc quy trình công ty bên ngoài sản phẩm.

**Bài học:** AI làm vòng lặp phát triển nhanh hơn; độ tin cậy phải đến từ kiểm chứng chứng từ gốc, quy tắc bằng mã nguồn và giữ nguyên các lần chạy thất bại để sửa.

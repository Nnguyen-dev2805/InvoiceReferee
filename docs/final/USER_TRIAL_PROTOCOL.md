# Giao thức thử nghiệm người dùng — InvoiceReferee

Trạng thái: **chuẩn bị từ T2** (plan T2 bước protocol; thực hiện thật tại T10/T12).
Chủ trì thử nghiệm: **người dùng (chủ dự án)** — chỉ người dùng mời người thật.
Agent không gửi lời mời, không tự tạo người tham gia, không tự điền phiếu thay người tham gia.
Mọi kết quả dùng để claim "Sprint 2/impact" chỉ có giá trị khi đến từ tài liệu này với
người thật, đồng thuận thật và phản hồi bằng văn bản thật.

## 1. Mục tiêu và phạm vi

- Tối thiểu **3 practitioner thật**: người có công việc phát sinh chi phí công tác và
  từng tham gia quyết toán chi phí.
- Đo **toàn bộ công sức con người**, không chỉ thao tác: thời gian tay, thời gian soạn
  nháp, thời gian chờ, thời gian onboarding, số lần làm lại, số gián đoạn, tác dụng phụ.
- So sánh **ghép cặp manual ↔ app** trên cùng dữ liệu vào, thứ tự đảo chiều giữa các
  người tham gia (counterbalanced) để giảm hiệu ứng học.
- Phản hồi phải là văn bản thật, có căn cứ; phản hồi không xác minh được giữ `pending`,
  không tính là verified support cho adaptation (T11).
- Không dùng kết quả thử nghiệm để chỉnh tập holdout (T12).

## 2. Sổ người tham gia (điền trước buổi)

| # | Tên/viết tắt | Vai trò công việc | Kinh nghiệm quyết toán | Đã ký đồng thuận (ngày) | Kênh liên hệ |
| - | ------------ | ----------------- | ---------------------- | ----------------------- | ------------ |
| 1 |              |                   |                        |                         |              |
| 2 |              |                   |                        |                         |              |
| 3 |              |                   |                        |                         |              |
| 4 |              |                   |                        |                         |              |

## 3. Phiếu đồng thuận (mẫu trống)

> Tôi, ______________________, đồng ý tham gia buổi thử nghiệm InvoiceReferee.
> Tôi hiểu: (a) đây là bản demo với dữ liệu tổng hợp, không phải hệ thống thật của
> doanh nghiệp; (b) buổi làm được ghi chú về thời gian/thao tác và phản hồi;
> (c) thông tin cá nhân được lưu riêng tư, chỉ công bố bản đã che thông tin khi tôi
> đồng ý; (d) tôi có thể dừng bất kỳ lúc nào.
>
> Ngày: ____________  Chữ ký/xác nhận: ______________________

## 4. Bộ bài ghép cặp (manual ↔ app)

Cùng một bộ hồ sơ cho cả hai chế độ; không gợi ý đáp án; thứ tự manual/app đảo giữa
người 1–2 và người 3–4.

| Bài | Nội dung | Điều đáng quan sát |
| --- | -------- | ------------------ |
| A   | Hồ sơ công tác routine, chứng từ rõ, có ứng và khoản nhân viên đã trả | Có tự kết luận đúng và ra việc cần làm không |
| B   | Hồ sơ thiếu payer/nguồn chưa rõ | Có dừng đúng chỗ và hỏi đúng người thay vì đoán không |
| C   | Hồ sơ vi phạm policy hoặc vượt quyền action | Có chuyển đúng người và giữ đúng số thật không |

## 5. Phiếu đo trong buổi (mỗi người × mỗi chế độ)

| Chỉ số | Manual | App |
| ------ | ------ | --- |
| Thời gian tay (phút) |        |     |
| Thời gian soạn nháp (phút) |   |     |
| Thời gian chờ hệ thống (phút) | |     |
| Thời gian onboarding/hướng dẫn (phút) | | |
| Số lần phải làm lại (rework) | | |
| Số gián đoạn/câu hỏi |        |     |
| Tác dụng phụ/quan sát khác | |     |

## 6. Phiếu phản hồi văn bản (người tham gia tự viết)

> 1. Phần nào giúp bạn rõ ràng nhất? Vì sao?
> 2. Phần nào bạn phải hỏi/tự suy đoán ngoài app?
> 3. Có thời điểm nào app có thể khiến bạn tin một điều chưa chắc chắn?
> 4. Nếu phải dùng cho hồ sơ thật của bạn, bạn cần gì thêm?
> 5. Điều gì khiến bạn mất thời gian vô ích?
>
> Người tham gia: ____________________  Ngày: ____________

## 7. Quy tắc dữ liệu và xác minh

- Ghi chú buổi, câu trích dẫn, thông tin liên hệ lưu dưới `private/` (đã được ignore).
- Không công bố PII; chỉ công bố bản che thông tin khi có đồng ý bằng văn bản.
- Phản hồi phải gắn phiên bản app + bài + thời điểm; người xác minh độc lập ghi nguồn
  (không để client/API tự đánh dấu đã xác minh).
- Nếu người tham gia rút lại phản hồi: chuyển sang `pending`, ghi rõ lý do.

## 8. Checklist

- [ ] ≥3 practitioner đã ký đồng thuận.
- [ ] Bộ bài A/B/C chuẩn bị trên bản demo đã khóa phiên bản.
- [ ] Thứ tự manual/app đã gán trước buổi (không đổi sau khi bắt đầu).
- [ ] Thiết bị/kênh ổn định; URL và tài khoản demo sẵn sàng.
- [ ] Phiếu đo và phiếu phản hồi in sẵn cho từng người.
- [ ] Sau buổi: ghi kết quả tay vào bảng tổng hợp + lưu private/; đánh dấu phản hồi
      `verified`/`pending` kèm nguồn xác minh.

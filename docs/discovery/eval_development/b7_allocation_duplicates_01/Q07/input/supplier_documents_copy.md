# Nguồn giả lập — Chứng từ chi phí và thanh toán

Các khối dưới là **original synthetic facts bằng văn bản**, không hóa đơn/statement ngân hàng thật. Amount ghi rõ để walkthrough semantics; không dùng kết quả này chứng minh OCR ảnh mờ/scan/PDF. Không có expected labels hoặc số hoàn trả cuối.

## air-invoice

Issuer giả lập `VENDOR-AIR-01`, invoice `INV-AIR-001`; booking `BOOK-DEMO-01`, hành khách `NV-DEMO-01`, hành trình phục vụ công tác Hà Nội05–06/10/2026. Tổng dịch vụ3.000.000VND. Nguồn thanh toán xem riêng khối sau; tên người bay không tự chứng minh payer.

## air-receipt

Biên nhận synthetic `PAY-AIR-001` do vendor giả lập phát hành: đã nhận3.000.000VND từ `ORG-DEMO-01` ngày04/10/2026, thanh toán toàn bộ nghĩa vụ `INV-AIR-001` / `BOOK-DEMO-01`. Không phải booking request hoặc phiếu xin chi.

## hotel-invoice

Issuer `VENDOR-HOTEL-01`, invoice `INV-HOTEL-001`, khách lưu trú `NV-DEMO-01`, dịch vụ lưu trú05–06/10/2026. Tổng gồm thuế/phí dịch vụ3.000.000VND, không khoản cá nhân/ngoài scope trong nội dung synthetic. Không cung cấp giá từng đêm; policy tổng công việc không yêu cầu breakdown để áp trần từng đêm.

## hotel-payment

Payment source synthetic `PAY-HOTEL-001`, ngày06/10/2026: payer tài khoản cá nhân của `NV-DEMO-01`, actualpayee `VENDOR-HOTEL-01`, amount3.000.000VND. Biên nhận phía vendor xác định đã nhận khoản đó để thanh toán toàn bộ `INV-HOTEL-001`; không chỉ lệnh/debit/pending. Không tự là source companyhistoryabsence.

## meal-receipt

Issuer `VENDOR-MEAL-01`, receipt `RCPT-MEAL-001`, ngày06/10/2026 lúc12:30. Dịch vụ ăn uống tổng1.000.000VND; vendor xác nhận đã nhận đủ bằng tiền mặt. Không ghi payer. Nguồn payer cần [cash attestation nhân viên](employee_claim.md#cash-attestation), cùng company scope để áp bộ căn cứ R4.2. Phương thức Cash là đã trả trong biên nhận synthetic này, không phương thức dự kiến trên order.

## ground-receipt

Issuer `VENDOR-GROUND-01`, receipt `RCPT-GROUND-001`, dịch vụ di chuyển công tác05–06/10/2026, tổng1.000.000VND. Chứng từ synthetic xác nhận nhận đủ tiền mặt từ `NV-DEMO-01` ngày06/10, đúng khoản này. Không thêm trần theo ngày hoặc giả đây là bank verification.

## advance-receipt

Nguồn receipt synthetic phía nhận `RCV-ADV-001`, liên kết transfer `TX-ADV-001`: ngày04/10/2026 tài khoản `NV-DEMO-01` đã được ghi nhận nhận2.000.000VND từ `ORG-DEMO-01` cho ứng `CT-DEMO-01` theo `DEC-PRE-DEMO-01`. Source mô tả tiền đã tới đúng beneficiary, không chỉ Submitted/Paid/debit. Sự kiện cũng xuất hiện ở [ledger công ty](financial_events_m1.csv); hai nguồn mô tả cùng event, không cộng hai lần.

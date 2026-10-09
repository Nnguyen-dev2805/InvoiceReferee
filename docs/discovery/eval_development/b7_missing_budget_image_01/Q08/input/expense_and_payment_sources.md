# Nguồn giả lập — Chứng từ chi phí và thanh toán

Các khối dưới là **original synthetic facts bằng văn bản**, không hóa đơn/statement ngân hàng thật. Amount ghi rõ để walkthrough semantics; không dùng kết quả này chứng minh OCR ảnh mờ/scan/PDF. Không có expected labels hoặc số hoàn trả cuối.

## air-invoice

Issuer giả lập `VENDOR-AIR-01`, invoice `INV-AIR-001`; booking `BOOK-DEMO-01`, hành khách `NV-DEMO-01`, hành trình phục vụ công tác Hà Nội05–06/10/2026. Tổng dịch vụ3.000.000VND. Nguồn thanh toán xem riêng khối sau; tên người bay không tự chứng minh payer.

## air-receipt

Biên nhận synthetic `PAY-AIR-001` do vendor giả lập phát hành: đã nhận3.000.000VND từ `ORG-DEMO-01` ngày04/10/2026, thanh toán toàn bộ nghĩa vụ `INV-AIR-001` / `BOOK-DEMO-01`. Không phải booking request hoặc phiếu xin chi.

## hotel-invoice

Nguồn invoice/receiptINV-HOTEL-001 của VENDOR-HOTEL-01, dịchvụluutrúNV-DEMO-01 ngày05–06/10 nằmtrong [ảnh được cungcấp](hotel_receipt.png). Packet text này không transcript total, unitprice, lineamount hoặc amountpaid củahotel. Không lấy ngân sách/dựtoán để thayactualamount.

## hotel-payment

Nguồn payer/actualpaymentcash củahotel cũng là [chứng từvendor trong ảnh](hotel_receipt.png): danh tính payer/receipt đọc từsource đó. Không có source ngân hàng hoặc biên nhận ghi số tiền rõ riêng cho hotel tronginitialpacket hoặc attestationamount củahotel. Body giữ đúngsource, không số đoán rồiconfirmed.

## meal-receipt

Issuer `VENDOR-MEAL-01`, receipt `RCPT-MEAL-001`, ngày06/10/2026 lúc12:30. Dịch vụ ăn uống tổng1.000.000VND; vendor xác nhận đã nhận đủ bằng tiền mặt. Không ghi payer. Nguồn payer cần [cash attestation nhân viên](employee_claim.md#cash-attestation), cùng company scope để áp bộ căn cứ R4.2. Phương thức Cash là đã trả trong biên nhận synthetic này, không phương thức dự kiến trên order.

## ground-receipt

Issuer `VENDOR-GROUND-01`, receipt `RCPT-GROUND-001`, dịch vụ di chuyển công tác05–06/10/2026, tổng1.000.000VND. Chứng từ synthetic xác nhận nhận đủ tiền mặt từ `NV-DEMO-01` ngày06/10, đúng khoản này. Không thêm trần theo ngày hoặc giả đây là bank verification.

## advance-receipt

Nguồn receipt synthetic phía nhận `RCV-ADV-001`, liên kết transfer `TX-ADV-001`: ngày04/10/2026 tài khoản `NV-DEMO-01` đã được ghi nhận nhận2.000.000VND từ `ORG-DEMO-01` cho ứng `CT-DEMO-01` theo `DEC-PRE-DEMO-01`. Source mô tả tiền đã tới đúng beneficiary, không chỉ Submitted/Paid/debit. Sự kiện cũng xuất hiện ở [ledger công ty](financial_events_m1.csv); hai nguồn mô tả cùng event, không cộng hai lần.

# Original synthetic facts — Expense/payment sources

Các khối là văn bản nguồn giả lập, không ảnh/PDF/ngân hàng thật, không expected labels hoặc final money. Không dùng để tuyên bố OCR/live quality.

## air-invoice

Issuer VENDOR-AIR-03, invoice INV-AIR-03, booking BOOK-DEMO-03, passenger NV-DEMO-03, hành trình công tác Hà Nội05–06/10. Dịch vụ tổng3.000.000 VND.

## air-receipt

Vendor synthetic receipt PAY-AIR-03, ngày04/10: VENDOR-AIR-03 đã nhận3.000.000 VND từ ORG-DEMO-01 thanh toán toàn bộ INV-AIR-03/BOOK-DEMO-03. Không booking hoặc request chưa trả.

## hotel-invoice

Issuer VENDOR-HOTEL-03, invoice INV-HOTEL-03, lưu trú NV-DEMO-03 ngày05–06/10, tổng gồm thuế/phí dịch vụ 2.000.000 VND. Nguồn không có khoản cá nhân/ngoài công việc trong nội dung synthetic. Không giá từng đêm vì không áp trần đêm.

## hotel-payment

Receipt PAY-HOTEL-03, ngày06/10: VENDOR-HOTEL-03 đã nhận 2.000.000 VND từ tài khoản cá nhân của NV-DEMO-03, thanh toán toàn bộ INV-HOTEL-03. Payer/payee/outcome/ref rõ, không chỉ lệnh hoặc debit.

## meal-receipt

Receipt RCPT-MEAL-03, issuer VENDOR-MEAL-03, lúc12:30 ngày06/10: dịch vụ ăn tổng 800.000 VND, đã nhận đủ cash. Không ghi payer. Xem [attestation đúng phần](employee_claim.md#cash-attestation) và source company coverage, không tự coi cash là bankverified.

## ground-receipt

Receipt RCPT-GROUND-03, issuer VENDOR-GROUND-03, dịch vụ di chuyển công việc05–06/10 tổng 500.000 VND; vendor đã nhận đủ cash từ NV-DEMO-03 ngày06/10, đúng khoản này.

## advance-receipt

Nguồn receipt phía nhận RCV-ADV-03, event TX-ADV-03, ngày04/10/2026: tài khoản NV-DEMO-03 đã thực nhận 4.000.000 VND từ ORG-DEMO-01 cho ứng CT-DEMO-03 theo DEC-PRE-03. Đây là receiver-side synthetic receipt, không chỉ Submitted/debit. Ledger công ty và receipt này là hai source cùng event, không hai lần nhận.

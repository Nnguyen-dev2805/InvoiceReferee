# Original synthetic facts — Expense/payment sources

Các khối là văn bản nguồn giả lập, không ảnh/PDF/ngân hàng thật, không expected labels hoặc final money. Không dùng để tuyên bố OCR/live quality.

## air-invoice

Issuer VENDOR-AIR-02, invoice INV-AIR-02, booking BOOK-DEMO-02, passenger NV-DEMO-02, hành trình công tác Hà Nội05–06/10. Dịch vụ tổng3.000.000 VND.

## air-receipt

Vendor synthetic receipt PAY-AIR-02, ngày04/10: VENDOR-AIR-02 đã nhận3.000.000 VND từ ORG-DEMO-01 thanh toán toàn bộ INV-AIR-02/BOOK-DEMO-02. Không booking hoặc request chưa trả.

## hotel-invoice

Issuer VENDOR-HOTEL-02, invoice INV-HOTEL-02, lưu trú NV-DEMO-02 ngày05–06/10, tổng gồm thuế/phí dịch vụ 3.000.000 VND. Nguồn không có khoản cá nhân/ngoài công việc trong nội dung synthetic. Không giá từng đêm vì không áp trần đêm.

## hotel-payment

Receipt PAY-HOTEL-02, ngày06/10: VENDOR-HOTEL-02 đã nhận 3.000.000 VND từ tài khoản cá nhân của NV-DEMO-02, thanh toán toàn bộ INV-HOTEL-02. Payer/payee/outcome/ref rõ, không chỉ lệnh hoặc debit.

## meal-receipt

Receipt RCPT-MEAL-02, issuer VENDOR-MEAL-02, lúc12:30 ngày06/10: dịch vụ ăn tổng 1.000.000 VND, đã nhận đủ cash. Không ghi payer. Xem [attestation đúng phần](employee_claim.md#cash-attestation) và source company coverage, không tự coi cash là bankverified.

## ground-receipt

Receipt RCPT-GROUND-02, issuer VENDOR-GROUND-02, dịch vụ di chuyển công việc05–06/10 tổng 1.000.000 VND; vendor đã nhận đủ cash từ NV-DEMO-02 ngày06/10, đúng khoản này.

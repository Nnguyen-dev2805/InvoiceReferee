# Original synthetic facts — Invoice và từng phần payment

Văn bản nguồn giả lập, không scan/bank document thật, không finaloutcome hoặc goldlabel.

## hotel-invoice

IssuerVENDOR-HOTEL-05, invoiceINV-HOTEL-05 ngày06/10, bookingBOOK-HOTEL-05, lưu trúNV-DEMO-0505–06/10, tổng gồm thuế/phí5.000.000VND. Nguồn invoice ghi đặtcọc2.000.000 đãnhận, phầncònlại3.000.000. Tổng5 là giátrị dịchvụ, không cộngdeposit/balance thành expenses mới. Không linecá nhân/ngoàicôngviệc trong source.

## company-deposit-receipt

ReceiptVENDOR-DEP-05, VENDOR-HOTEL-05 xácnhận nhận2.000.000VND từORG-DEMO-01 ngày04/10 cho bookingBOOK-HOTEL-05, đặtcọc dịchvụluutrú. Booking xácđịnh đúnginvoice trên; đây là company→vendor, không advance→employee.

## employee-balance-receipt

ReceiptVENDOR-BAL-05, ngày06/10: VENDOR-HOTEL-05 xácnhận nhận3.000.000VND từtàikhoản cá nhân củaNV-DEMO-05 thanh toán balance đúngINV-HOTEL-05/BOOK-HOTEL-05. Amount/payer/payee/phần/receipt rõ, không chỉcheckboxPERSONAL hoặc phép trừ.

## advance-receipt

SourcephíanhậnRCV-ADV-05, eventTX-ADV-05: NV-DEMO-05 đã thựcnhận1.000.000VND vào tàikhoản ngày04/10 từORG-DEMO-01 cho ứngCT-DEMO-05 theoDEC-PRE-05. Ledger cũngmô tả event này, không2lầnnhận. Chưa córeceipt hoànchi phí.

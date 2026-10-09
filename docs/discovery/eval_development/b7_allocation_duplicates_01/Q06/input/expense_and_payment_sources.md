# Original synthetic facts — Invoice có các lines

Nguồn text giả lập, không ảnh/PDF/statement thật hoặc expected. Không trần từngloại chi phí.

## hotel-invoice

IssuerVENDOR-HOTEL-06, invoiceINV-HOTEL-06 ngày06/10, customerNV-DEMO-06. Tổng7.000.000VND. Nội dung dịchvụ/hànghóa rõ ở lines sau; sourcevendor không tự xácđịnh mụcđíchcôngviệc của từngline.

## invoice-line-l1

L1: dịchvụluutrú05–06/10, gồm thuế/phí6.000.000VND.

## invoice-line-l2

L2: đồdùng mangvề1.000.000VND. Purpose xem statementnhânviên riêng, không classifier đoánlinecấm từ tên.

## employee-payment-receipt

ReceiptPAY-HOTEL-06: vendorVENDOR-HOTEL-06 đãthựcnhận7.000.000VND ngày06/10 từtàikhoản cá nhânNV-DEMO-06, đúng toàninvoiceINV-HOTEL-06. Không invoice/receipt6triệu hoặc payment6 khieligiblecost bịloại1; không chỉlệnhdebit.

## advance-receipt

Receiver sourceRCV-ADV-06, eventTX-ADV-06: NV-DEMO-06 thựcnhận2.000.000VND từORG-DEMO-01 ngày04/10 cho ứngCT-DEMO-06 theoDEC-PRE-06. Sourcecompanyledger cùngevent, không cộngthêm lần2.

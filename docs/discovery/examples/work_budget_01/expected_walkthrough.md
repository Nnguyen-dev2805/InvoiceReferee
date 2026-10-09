# Đáp án walkthrough bằng tay — Tách khỏi input

**DRAFT EXPECTED, CHƯA PHẢI GOLD ĐỘC LẬP ĐÃ ĐƯỢC THẨM ĐỊNH.** Lead dựng nguồn và phép tính để kiểm tra tính nhất quán thiết kế. Không đưa file này vào input/prompt; chưa chạy pipeline/OCR/Verify hoặc thử người thật. Kết quả conditional theo nguồn/policy bundle được công bố, không đúng cho mọi công ty.

## M1

| Nội dung | Căn cứ | Kết quả bằng tay |
| --- | --- | --- |
| Công việc/ngân sách/quyền | employee_claim + authority/pretrip | Phạm vi đúng, B=8.000.000, quyền cho nội dung packet đủ |
| Vé | airinvoice + vendorreceipt + FIN-ROW-001 | Expense3.000.000, companydirect3.000.000; không E |
| Hotel | hotelinvoice + hotelpayment + scope/purpose | Employee-paid3.000.000, đủ điều kiện theo ngân sách tổng; không áp trần đêm |
| Ăn | anonymous paid cashreceipt + scopedattestation + companycoverage | Employee-paid1.000.000 được chấp nhận theo attestationpolicy; không bankverifiedpayer |
| Di chuyển | named paid cashreceipt + purpose/coverage | Employee-paid1.000.000, không trần ngày |
| Advance | FIN-ROW-002 + advance-receipt | A=2.000.000 gross, không4.000.000 do hai source |
| Returns/reimbursements/pending | coverageM1 + employeeScope | RA=P=RP=0 có căn cứ, không mặc định từ ledger chỉ2rows |

T=3.000.000+3.000.000+1.000.000+1.000.000=8.000.000=B.

E=3.000.000+1.000.000+1.000.000=5.000.000.

S=5.000.000-(2.000.000-0)-(0-0)=+3.000.000VND.

Job kiểm tra có thể hoàn tất report mà không hỏi bổ sung fact/policy cho input M1 được công bố. Kế toán rà soát và người duyệt quyết định là checkpoint nghiệp vụ tiếp theo, **chưa có approval quyết toán, chưa có request tự động giai đoạnB, chưa PAID/close**. Source prep trong syntheticpacket không chứng minh automatic rawmatching/human effort hoặc BTC acceptance.

## M2

Giữ B/T/E/A và gross history M1. Finaldecision trong quyền chấp nhận E=5.000.000 và chi thêm3.000.000; receipt đúng nguồn/phạm vi mới cho P=3.000.000, RA=RP=0.

S=5.000.000-(2.000.000-0)-(3.000.000-0)=0.

Decision3 đã thực hiện đủ, không pending/sai lệch/ngoại lệ/nguồn thiếu trong toàn scope M2: đủ điều kiện đóng **as-of M2**. Không tạo lệnh0 hoặc chi thêm3 lần nữa, không xóa advance/reimbursement facts. Nguồn mới sau M2 có ảnh hưởng vẫn phải xử lý theo linkedversion, không bảo đảm vĩnh viễn.

## Biến thể cần lập expected độc lập ở R5

- Bỏ hoặc cắt scope M1: không được mặc địnhP=0 hoặc kết luận finalS=3.
- Chỉ có approval ứng2, không receipt: A chưa xác định, không dùng2 thay actualreceipt.
- Bỏ cashattestation: payer meal chưa đủ theo profile anonymousreceipt, không tự E=5.
- Đưa receiptM2 vào inputM1: sai mốc input; không dùng nguồn tương lai để đổi expectedM1 thành0.
- Source hotelpayment mâu thuẫn với companypaid: giải quyết đúng portion/obligation, không tin checkbox hoặc tự kết luận fraud.
- Đổi work/employee so với authoritysource: source quyền cũ không bao phủ, không chỉ đổirolepicker cho qua.

Các dòng trên mới là hướng test, chưa tạo6case đầy đủ hoặc gán gold đã VERIFIED.

# R5.3 — Bốn case thiếu/mâu thuẫn nguồn và đường bổ sung

Ngày: 09/10/2026 · **ĐÃ DỰNG INPUT/FOLLOWUP/EXPECTED NHÁP; CHƯA CHẠY PIPELINE HOẶC THẨM ĐỊNH GOLD ĐỘC LẬP**.

Toàn bộ dữ liệu synthetic, Markdown/CSV cho semantic development. Bốn scenarios rẽ từ Q01 để thử đúng một nhóm vấn đề mỗi lần; không nguồn ngân hàng thật, không testOCR/ảnhmờ hoặc professionaltrial. Dùng cùng policy snapshot bất biến tại [suite manifest](suite_manifest.json), không nới rule để case dễ đạt.

| Case | Điều còn thiếu/mâu thuẫn | Phần vẫn giữ được | Câu trả lời/nguồn chọn để kiểm tra lại |
| --- | --- | --- | --- |
| [Q11](Q11/README.md) | Approvalứng2triệu và lệnhSUBMITTED nhưng không biết actualreceipt | Giá trị/employee-paid expenses, companydirect, approval và amount lệnh; A/S cuối unknown | Receipt phía nhận gắn TX-ADV-001 chứng minh thực nhận2triệu trước mốc; finance đối chiếu đã thực hiện đủ/không còn lệnh chờ |
| [Q10](Q10/README.md) | Nguồn company chỉ tới06/10, mốc cần08/10 | Các invoices/payments trước06 và actualadvance2; tổng lũy kế/coverage cuối chưa đủ | Nguồn/phạm vi07–08 cho toàn nhóm ảnh hưởng, actualmoney/expense/history đúng owner/observability |
| [Q09](Q09/README.md) | Mealreceiptcash đãpaid nhưng khôngpayer/statement đủ | Mealvalue1triệu, hotel/groundemployee-paid4triệu; E/S cuối unknown | Scopedattestation đủ cho đúng receipt/part/vendor/time/purpose theoR4.2; không bắt bankstatement cho khoản cash |
| [Q12](Q12/README.md) | Employee khaiPERSONAL vé3triệu, sourcevendor nhận đủcompany3triệu cùngbooking | Invoicevalue, companypayment và employee-paidphầnkhác; E/S cuối unknown | Correction cóscope chứng minh khai nhầm và không personalpayment cho booking/phần đó; không chỉ bấmApproved |

## Trước và sau câu trả lời

Trước source bổ sung, cả bốn chưa được chốt S hoặc approve/chi/thu/close cuối. Có thể lưu các checks/sums độc lập đã rõ; **không dùng subtotal như quyền chi một phần**. Q10 không biến knownadvance2 thành tổngA=2 khi nguồn chưa phủ phần còn lại. Q09 không suy employee trảmeal bằng tổng trừcompany; Q12 không cộng số hai lần trả thành hai chi phí hoặc gọi gian lận từ checkbox.

Sau **nguồn được chọn cụ thể** trong `followup/`, các fact/policy/authority còn lại theo mỗi scenario đều đủ: E=5triệu, A=2triệu, RA=P=RP=0 cócăn cứ, S=+3triệu. Đây là report sau bổ sung, **assisted**, không first-passroutine, chưa có financialsettlementapproval/actualreimbursement hoặc quyền đóng. Không mọi câu trả lời đều ra3triệu; nếu facts thật khác phải tính lại, thiếusource/pending chưa xử lý vẫn dừng.

## Mốc tiền và mốc biết thông tin

Mốc xét tiền giữ08/10/2026 18:00. Reply nhận09/10 09:00 xác nhận các sự kiện xảy ra trước mốc đó hoặc bổ sung phạm vi tới mốc; không đưa actualpayment phát sinh09/10 vào Pở08/10. Q11 receipt được cung cấp muộn xác nhận credit04/10, không tiền tới09/10. Khác với Q04 ở suitecore: Q04 actualreceipt thật trong câu chuyện xảy ra09/10 nên đổi mốc tiền sang09/10.

Manifest của từng case liệt kê initialinput và followup riêng, expected nằm ngoài cả hai. Chưa có harness/application đã thực hiện giới hạn input này; cần triển khai/kiểm tra theoR7/R9. Không đưa README/caseID/expected/fixturechecks vào prompt hoặc dùng chúng để branch sản phẩm.

## Kiểm tra case có thật sự chưa đủ nguồn

- Q11 bỏ receiverreceipt ở mọi source và statement employee không xác nhận actualadvance; đổi rawstatus/source của dònglệnh và không để companycoverage khẳng định actualreceipt/no-pending cho chính lệnh đó.
- Q10 cắt scopecompany toàn bộ, đồng thời tránh employee statement tự xác nhận totalfunds hoặc companyabsence cho07–08. Expense/refund phía employee vẫn cóscope riêng; receiptadvance2 chỉ là phần đã biết, không đủ absence những events khác.
- Q09 xóa cả attestation và khai báo payer đủ phạmvi trong bảng kê; employee-scope không lén xác nhận payerreceiptmeal. Sourceanonymousreceipt không có tênpayer; không tạo questionritual nếu nguồn đã đủ statement ngay từ đầu.
- Q12 giữ nguyên cả companyvendorreceipt và lời khai ban đầu; chỉ followup có correction. Nếu cả hai có proof thực trả thì không chọn companysource vì chức danh; cần giữ doublepayment/rights exception đúng B7.

Đây là kiểm tra fixture và lập luận nguồn nội bộ, chưa adjudication độc lập. Before/afterexpected làDRAFT_SINGLE_AUTHOR_NOT_INDEPENDENTLY_ADJUDICATED; sourcewrapper narrative còn đơn giản hơn hóa đơn thật, không suy qualitylive từ dữ liệu này.

## Giới hạn corpus và bước tiếp

[Kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_FIXTURE_SANITY_ONLY: phases/refs/hashes, source critical không còn đủ ở initial, unknown khác0, selectedfollowup arithmetic và action/close boundaries. Đây không là output hệ thống, evaluation accuracy hoặc independentadjudication.

[Core4](../b7_core_01/README.md) và suite này cho8caseconditions development đầu tiên trong catalogue, cùng1templatefamily; followup không được đếm thành4caseđộc lập nữa. Scenarios là thế giới nguồn thay thế, **không gộp events cùngrefs giữa cácscenarios**, không đem một nhánh làmholdout cho nhánh khác. Chưa20fullcase, >=15caseđượcchấm/Verify hoặc metricđộchínhxác.

Tiếp theo dựng policygap/budgetexceed và beyondauthority bằng nguồn quyền đúng cho từngnhánh để khôngtrộn reason; rồi đối chiếu duplicate/splitpayer/personalpart và kiểm soátlifecycle. Giữ các caseknown/unknown, câu hỏiowner/source và đápán ngoàiinput trước kiến trúc/code. Không mặc định mọi hạn chế đều là missingbill, không autoaccept câu trả lời hoặc xóa rawhistory.

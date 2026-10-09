# R4.2 — Phép kiểm tra áp dụng và bộ căn cứ được chấp nhận

Ngày: 09/10/2026 · Trạng thái: **CHỦ DỰ ÁN ĐÃ ĐỒNG Ý THIẾT KẾ BỘ CĂN CỨ MVP, GỒM CASH RECEIPT + ATTESTATION CÓ ĐIỀU KIỆN; CHƯA KÍCH HOẠT POLICY RUNTIME/CODE**.

Căn cứ [R3](R3_MVP_SCOPE_DRAFT.md), [R4.1](R4_DATA_SOURCE_DRAFT.md), [khung 9 bước](R2_CASE_WALKTHROUGH.md). Phần này chốt logic đủ căn cứ theo từng check; chưa đặt hạn mức tiền/ngày, thẩm quyền số tiền hoặc ngưỡng confidence nhà cung cấp. R4 tiếp theo chốt các tham số/cách tính/authority, R5/R7 kiểm chứng quality và implementation. Không đánh giá pháp lý hóa đơn/thuế hoặc xác thực ngân hàng từ ảnh.

Bản hiện tại đã bổ sung sau [review R4.2](../reviews/2026-10-09-r4-evidence/REVIEW.md). [Snapshot](../reviews/2026-10-09-r4-evidence/TARGET_R4_EVIDENCE_RULES_DRAFT.md) và verdict gốc giữ nguyên; bản bổ sung được lead kiểm tra và chủ dự án đồng ý ngày 09/10/2026. Chưa review độc lập lại hoặc kích hoạt runtime. Theo yêu cầu mới, từ R4.3 lead tự review, không dùng subagent review.

## 1. Tách hai profile trước và sau chi

| Profile | Checks cần áp dụng | Không dùng sai giai đoạn |
| --- | --- | --- |
| Đề nghị ứng trước công việc | Nhận diện người/công việc/phạm vi; dự toán và số xin; căn cứ công việc; rule/authority cần thiết; lịch sử ứng/chi chờ/đã xử lý liên quan | Chưa bắt hóa đơn hậu kiểm hoặc chứng minh khoản đang xin đã nhận. Approval có thể là điều đang xin ở bước sau, không ép có sẵn trước intake |
| Quyết toán/hoàn trả sau công việc hoặc hủy | Khoản/phần/công việc, evidence giá trị/nội dung, payer/coverage theo phần, consistency, policy, trùng nghĩa vụ, gross tiền ứng/chi/thu và phạm vi nguồn để tính cuối | Không bắt có khoản ứng/loanID khi tự chi; A=0 cần nguồn absence đủ. Hủy không tự có E=0 hoặc thu toàn bộ ứng |

Check không áp dụng có lý do theo profile/rule, không waive các check khác. Inventory/PO/nhận hàng ngoài scope R3 hiện tại, không đòi các chứng từ đó cho meals/hotel/travel. Một hồ sơ có các check độc lập nhưng finalS còn phụ thuộc tất cả thành phần ảnh hưởng.

## 2. Điều kiện chung trước khi dùng một fact

Fact dùng cho check cần đồng thời: source thật trong hồ sơ đã lưu, locator có thể mở, value/currency/unit/ý nghĩa rõ, source-role/provenance phù hợp check, quan hệ đúng người/khoản/phần/mốc, và không còn mâu thuẫn có thể đổi kết quả check. Số được normalize nguyên VND khi không mơ hồ; raw vẫn giữ. Không lấy confidence cao, financialapproval hoặc Paid label làm thay thế các điều kiện này.

Provider xử lý xong khác fact đọc đủ; amount rõ khác actualpaid. Nếu số tiền bắt buộc mờ thì cần source rõ/confirmation về cách đọc có căn cứ chấp nhận; không dùng lời đoán hoặc quyền approve để mở gate. Có alternative source phù hợp thì ghi source/cách xác định, không bắt chụp lại khi đã có căn cứ đủ. Missing/ambiguous/conflicting/technicalfailure giữ đúng nguyên nhân/owner.

Readingconfirmation chỉ giải quyết sự bất định của provider/OCR khi người xác nhận thực sự đọc được retained source, có locator/value và scope. Source bản thân không đọc được thì phải bổ sung source khác rõ/factual evidence phù hợp; không nhập số rồi đánh dấu confirmed, không dùng financialapproval hoặc payerattestation làm printed invoice amount rõ hơn. Giá trị suy ra từ nguồn khác/derivation nếu rule cho phép được ghi đúng loại/source, không giả là đã đọc được trường trên bản gốc.

## 3. Evidence về khoản chi và mục đích

| Nhóm khoản | Bộ dữ kiện/căn cứ đề xuất |
| --- | --- |
| Chung | Khoản/phần người nộp muốn xử lý; nội dung, giá trị/currency, thời điểm và source đủ rõ cho check cần dùng; mục đích công việc/boundary. Tổng bill không tự là số nhân viên được hoàn |
| Vé/di chuyển | Source thể hiện chuyến/dịch vụ, value và ref phù hợp như booking/ticket/trip/receipt khi có; quan hệ người/công việc/những ngày cần xét. Không bắt mọi taxi có ref kiểu airline; ref không đủ thì dùng quan hệ khác đủ theo rule hoặc hỏi |
| Khách sạn | Source phòng/dịch vụ/giá trị và thời gian lưu trú cần để áp policy; phần company/NV trả theo source. Deposit/remaining là money evidence, không cộng vào invoice total thành expense mới |
| Ăn phục vụ công việc/tiếp khách | Receipt/nội dung chi và mục đích/bối cảnh từ nguồn; detail/attendees chỉ bắt buộc khi rule áp dụng cần chúng. Không suy toàn bộ bàn ăn là công việc hoặc tự loại item không có rule |

MVP không mặc định taxID/invoiceVAT, unitprice/quantity hoặc toàn bộ metadata bắt buộc cho mọi bill. Nếu rule áp dụng cần chi tiết để loại phần không hợp lệ, total rõ không waive detail mờ/thiếu. Lời khai mục đích có thể là source được demo-policy chấp nhận, nhưng mâu thuẫn về công việc phải làm rõ; không biến xác nhận mục đích thành proofpayer.

## 4. Evidence payer/receipt theo phương thức

| Bộ evidence | Đủ cho check nào, với điều kiện | Không đủ khi |
| --- | --- | --- |
| Paymentrecord có outcome receipt xác định theo semantics của source được chấp nhận | Amount/currency, payer/payee và liên kết đúng khoản/phần; outcome xác định đã tới đúng người nhận theo format/rule. Tài liệu expense và event có thể cùng source nếu đủ các fact | Chỉ thấy lệnh/debit/Submitted/Paid generic; source/party/meaning chưa rõ; event còn chờ/returned/mâu thuẫn |
| Cash receipt/chứng từ giao nhận có payer và bên nhận/role đủ liên kết | Amount/part/time/ref rõ, source xác nhận đã giao/nhận đúng phần với origin phù hợp; không phải chỉ phiếu đề nghị/phiếu chi chưa thực hiện | Nguồn chỉ đặt chỗ/order hoặc không đủ nhận diện payer/actualreceipt; chữ company trên invoice không là payer |
| Receipt cash đã trả nhưng không ghi payer + attestation của A | **Thiết kế demo-policy đã được chủ dự án đồng ý, chưa kích hoạt runtime:** receipt giá trị/cashpaid rõ, statement có scope A thực trả amount/part/vendor/time và ref; quan hệ/công việc rõ; nguồn công ty trong scope đủ để kiểm tra companydirect/duplicate và không có mâu thuẫn; policy cho phép dùng loại xác nhận này | Chỉ chọn PERSONAL; thiếu cashpaid/statementbound/ref; source critical mờ; history thiếu hoặc có companypayment/nguồn khác chưa giải quyết. Attestation không tự override contradiction |

Hai bộ đầu cho kết luận theo evidence được source contract chấp nhận, không là forensic authenticity guarantee. Bộ cashattestation **được chấp nhận trong thiết kế demo-policy đã chốt, khi đủ toàn bộ điều kiện**, report ghi mode/source “payer theo receipt + xác nhận người nộp”, không gọi được kiểm chứng độc lập bằng bank. Việc áp dụng runtime cần policy có phiên bản và kích hoạt rõ; receipt cash không có payer và không đủ bộ attestation vẫn chưa xác định payer.

Bộ cashattestation ở dòng này chỉ dành check phần expense A thanh toán vendor theo scope; không dùng lại để chứng minh A/P được công ty trả hoặc RA/RP công ty thực nhận bằng lời nhân viên đơn độc. Các cashhandover named/recordreceipts và source phía nhận dùng profile tương ứng. Receipt phải thể hiện cashpayment đã hoàn thành đủ rõ, không chỉ chọn phương thức dự kiến Cash trên order/đề nghị.

Statement đủ scope đã có ở intake thì không hỏi lại cùng lời xác nhận để làm ritual. Nếu phải hỏi/bổ sung sau Run, ghi human touch/mode assisted theo R3. Nếu company có source paid và A có source paid, xử lý linkage/portion/doublepayment; không mặc định sourcefinance thắng vì chức danh hoặc sourceNV làfraud.

## 5. Actualmoney, lịch sử và số0

| Thành phần | Source/căn cứ đủ để dùng |
| --- | --- |
| Ứng A thực nhận, hoàn chi phí P A thực nhận | Bộ receipt phù hợp phương thức, đúng người/phạm vi/mốc và loại/amount; cấp ứng/approval/paymentattempt không thay receipt |
| Hoàn ứng RA, trả lại hoàn chi phí RP công ty thực nhận | Bộ receipt phía company và quan hệ đúng A/P; một event/phần không là đồng thời toàn RA và toàn RP. Vendorrefund khácloại |
| Companydirect | Source payercompany/payeevendor và phần nghĩa vụ đủ liên kết; employee liên quan không phải actualpayee. Partialcoverage ghi đúng phần |
| Không có sự kiện / một nhóm bằng0 | Coverage được xác định đủ theo rule: người/công việc, **loại event/phương thức cần xét**, từ–đến/asof và source/update phạm vi; hoặc confirmation absence của đúngowner theo rule có căn cứ, không chỉ actorrole/string “không có” |

Tập nguồn tới15 mà mốc cần21 không đủ khẳng định nhóm0 tới21; asof/filter có ý nghĩa thời điểm đúng, không chỉ ngày tải file. Tổngnet0 sau A nhận2/hoàn2 giữ gross2/2, không thành neveradvanced. B9 source Paid nhưng receipt unknown thì P chưa xác định, không P=0 mặc định. Giao dịch0 không được tạo để làm placeholder absence.

Owner xác nhận absence phải có khả năng quan sát đầy đủ **loại sự kiện, phương thức, phía tiền, đối tượng và khoảng/mốc thời gian đang xét**, cùng source/căn cứ. Nhân viên không xác nhận thay company-side payment/history chỉ vì chọn COMPANY/PERSONAL; nguồn/owner phía công ty có scope phù hợp mới dùng cho absencecompanydirect. Người chỉ thấy một account hoặc register không tự chứng minh absence ở các phương thức/account chưa được phủ; phần đó giữ unknown. Việc một người kiêm nhiều vai chỉ hợp lệ theo phạm vi quan sát/căn cứ rõ, không từ rolepicker.

## 6. Confirmation, contradiction và vòng tiếp tục

Readingconfirmation xác định nội dung source; factualconfirmation xác định một fact bên ngoài; financialdecision phê duyệt nội dung trong quyền. Mỗi confirmation cần target/value/part/ref/actorrole/scope/time và nguồn/căn cứ theo policy, không một confirmedboolean. Operatordemo đóng vai người biết fact phải được ghi rõ mode giả lập; không giới thiệu như nhân viên/company thật đã xác nhận.

Mâu thuẫn giữa sources về fact ảnh hưởng check không giải bằng lấy mới nhất hoặc authority của uploader. Xác định chúng mô tả cùng nghĩa vụ/phần không; nếu có correction/decision supersede có căn cứ, giữ quan hệ/version và source cũ, re-check. Chưa rõ thì hỏi chủ nguồn hoặc đúng người quyết định, không asktoapprove số đang mờ. Ngoài automation/ngoài policy/vượtauthority có reason riêng, không ngụy technicalerror thành missingreceipt.

Check nào đủ thì lưu kết quả check đó; trường không cần không block. Nếu còn unresolvedmaterial trong cùngsettlement thì chưa finalS/chi/thu/close; refusal một khoản có rule rõ không tự refusal toàncase hoặc xóaadvance. Violation vs policygap/exception cụ thể sẽ chốt ở phần rulebook tiếp theo, không tự đặtcap tại đây.

## 7. Quyết định cần chốt và giới hạn tiếp theo

Chủ dự án đã đồng ý evidence theo **câu hỏi/check và phương thức**, gồm **receipt cash + attestation đầy đủ có điều kiện** cho phần nhân viên thanh toán nhà cung cấp. Sourcefacts/receipt/history coverage đủ thì kiểm tra tự động, thiếu đúng phần thì hỏi đúngowner. Không gọi attestation là proof độc lập hoặc cho PERSONAL đơn lẻ qua. R4.3 tiếp tục monetary rules/limits/authority; sự đồng ý thiết kế không là kích hoạt runtime hay xác nhận quy định của một công ty thật.

Các profiles này là proposed company/demo rules, không quy định thuế/law. [Cornell documentation](https://finance.cornell.edu/travel/expense-reporting/documentation) tham khảo việc tách businesspurpose/paymentproof và nhiều dạng nguồn; [UW Payment Tracking](https://finance.uw.edu/travel/WDpaymentoptions) minh họa Paid/Reconciled không đủ chứng minh tiền vào người nhận. Không nhập ngưỡng/giấy tờ bắt buộc của các tổ chức đó thành chính sách VN.

Phép thử thiết kế chưa chạy: clearamount+Paid vs bluramount+Paid; sameexpense cash namedreceipt vsanonymousonly vsboundedattestation; namedcompanyinvoice butApayment; Aattest+companypaidcontradiction; requestedadvance2 vsreceived1; importedhistorytruncated/coveragecompletezero; RA/RPoverlap; confirmationreading vsmoney; preadvance profile noinvoice vsafterexpensemissingrequiredsource. R4 tiếp theo chốt monetaryrules/limits/authority và activeversion, R5gold/qualityevaluation, R7/providerformat/runtimegates; không tạo confidence_score giả để profile tựpass.

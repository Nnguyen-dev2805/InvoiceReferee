# Bước 8–9 — Quyết định tài chính, chi/thu thực tế và đóng hồ sơ

Ngày: 09/10/2026 · Trạng thái: **ĐÃ ĐƯỢC CHỦ DỰ ÁN DUYỆT Ở MỨC WALKTHROUGH; POLICY/NGUỒN/QUYỀN CHI TIẾT CÒN Ở R4, CHƯA CODE**.

Chủ dự án đồng ý Bước 8 và 9 sau bản bổ sung/review và hỏi các chặng còn lại. Việc duyệt chốt hướng nghiệp vụ giả lập, không chứng minh dữ liệu/quyền doanh nghiệp thật, runtime hoặc mức đạt cuộc thi.

Căn cứ: [walkthrough](R2_CASE_WALKTHROUGH.md) và [phạm vi B7 MVP đã được đồng ý](B7_MVP_PROPOSAL.md). Một nhân viên/một công việc/VND trong nguồn đủ phạm vi. Không thực hiện ngân hàng hoặc xây ERP/auth doanh nghiệp. Role demo không xác thực người/thẩm quyền thật. B7 tự chuẩn bị kết quả; B8 con người quyết định; B9 con người chi/thu bên ngoài và hệ thống đối chiếu nguồn.

Case giả lập thường quy: tổng chi phí 8 triệu, company direct 3, phần nhân viên thanh toán hợp lệ 5, ứng thực nhận ròng 2, chưa hoàn chi phí trước đó và không có pending/ngoại lệ ảnh hưởng → B7 đề xuất công ty trả A thêm 3. Quyền, policy, chất lượng và phạm vi nguồn trong case là giả định để thảo luận, chưa VERIFIED.

Bản này đã bổ sung các ràng buộc sau [review B8/B9](../reviews/2026-10-09-step-8-9-design/REVIEW.md). [Snapshot được review](../reviews/2026-10-09-step-8-9-design/TARGET_B8_B9_MVP_PROPOSAL.md) và verdict gốc giữ nguyên; bản sau bổ sung được lead kiểm tra, chưa có review độc lập lại hoặc runtime evidence.

## 1. Giao diện nghiệp vụ giữa B7 → B8 → B9

B8 nhận bảng khoản/phần, nguồn và rule refs; chi phí chấp nhận/phần loại/còn vướng; số tiền từng nghĩa/lịch sử/coverage/mốc; chiều và số đề xuất khi đủ căn cứ; các ngoại lệ cùng phạm vi. Vấn đề nguồn/số bắt buộc hoặc nghĩa vụ tiền còn unresolved trong cùng settlement phải được xử lý trước quyết định đủ để thực hiện cuối. Không đưa component +3 sang chi khi recovery 1 trong cùng phạm vi chưa xử lý, không tự cấn trừ thành +2.

B8 ra quyết định gắn với người/công việc/phạm vi, report/hồ sơ/quy định và mốc nguồn đã xét; hướng chi/thu hoặc xác nhận cân bằng; số/phạm vi được quyết định, người/vai có quyền, thời điểm, lý do/điều kiện khi có. B9 nhận quyết định hiện áp dụng, phần đã thực hiện/lệnh chờ có nguồn và điều kiện còn thiếu. “Được duyệt” không là “đã chi/thu”; một lần nhập lại report/decision không tạo quyền thực hiện lần nữa.

## 2. Bước 8 — Rà soát và quyết định quyết toán

### 2.1. Người duyệt làm gì?

Người có quyền tài chính đọc bảng đối chiếu, nội dung và vấn đề đã chuẩn bị, mở nguồn khi cần và quyết định trong quyền. Hệ thống không yêu cầu họ tìm/ghép và tính lại từ đầu; họ có thể xem tất cả nguồn. Quyết định không thay proof chất lượng/số học/người trả hoặc xóa hard gate. Một người có thể kiêm vai duyệt và thực hiện theo policy, nhưng hai ý nghĩa/sự kiện vẫn riêng.

| Kết quả B8 | Xử lý đề xuất |
| --- | --- |
| Đồng ý kết quả đủ căn cứ S=+3 triệu | Ghi quyết định công ty trả A 3 triệu, gắn phạm vi/version/quyền; chờ B9 thực hiện và đối chiếu. |
| Đồng ý kết quả đủ căn cứ S=−0,7 triệu theo policy giả lập | Ghi quyết toán đề xuất A hoàn công ty 0,7 và điều kiện/phạm vi; B9 ghi công ty thực nhận. Không tự trích tài khoản/khấu trừ lương. |
| Kết quả S=0, không còn nghĩa vụ/vướng mắc thuộc phạm vi | Ghi xác nhận cân bằng/điều kiện kết thúc. B9 kiểm tra đóng, không tạo lệnh chuyển 0. Nếu case đã xử lý và không có thay đổi, dùng history đúng quan hệ, không bắt quyết định/chi mới chỉ vì nộp lại. |
| Phát hiện lỗi hoặc muốn đổi nội dung/số/chiều | Ghi khoản/ref/lý do, trở lại B7 kiểm tra nguồn/quy tắc/phần ảnh hưởng; kết quả mới cần quyết định đúng phạm vi. Không sửa raw facts hoặc nhập một số final tùy ý cho khớp ý định. |
| Trả lại để bổ sung hoặc yêu cầu sửa | Hỏi/ghi yêu cầu cụ thể và owner; sửa đề nghị tạo revision, bổ sung source giữ loại/nguồn; B7 re-check trước quyết định tiếp. |
| Từ chối | Lưu quyết định và lý do; không phát sinh thực hiện mới theo đề nghị bị từ chối. Giữ tiền đã nhận/đã chi và nghĩa vụ chưa xử lý, không tự hủy công tác hoặc coi chi phí/ứng bằng0. Từ chối một đề nghị không tự chứng minh phải hoàn toàn bộ ứng hay hồ sơ đã đóng. |
| Tạm dừng hoặc chưa trả lời | Giữ chờ/dừng theo phạm vi; không suy đồng ý hoặc tự chi vì tới hạn. |

### 2.2. Giới hạn MVP và hiệu lực

MVP không cung cấp duyệt từng phần của một kết quả quyết toán còn nghĩa vụ chưa xử lý. B7 tính còn phải trả 3 nhưng người duyệt nói “duyệt2”: chưa tự biến thành final2 và đóng phần1. Phải làm rõ họ đang yêu cầu đổi chi phí/quy định/phạm vi hay đề nghị chi từng phần; kiểm tra/ghi đúng kết quả hoặc chuyển cách xử lý ngoài luồng được hỗ trợ. Duyệt mức ứng thấp hơn số xin ở B4 khác với làm biến mất nghĩa vụ quyết toán đã xác định ở đây.

“Duyệt toàn bộ3, chi2 trước” giữ quyết định tổng3 và chỉ dẫn thực hiện riêng, không biến decision amount thành2. MVP ghi nguồn/nội dung chỉ dẫn để người thực hiện xử lý, không tự lên lịch hay tạo lệnh theo đợt. Nếu thực tế nhận2, ghi2 và phần1 chưa hoàn thành; chưa đóng. Chỉ dẫn/điều kiện thực hiện có hiệu lực phải được xét trước phần hành động tương ứng, không dùng fullapproval để bỏ chỉ dẫn rõ của người có quyền.

Nếu có điều kiện hợp lệ rõ, ghi quyết định và điều kiện/phạm vi; chưa đủ điều kiện thì chưa đưa cho thực hiện chi/thu. Cách chứng minh điều kiện và nguồn/vai theo policy; không buộc duyệt lại mọi điều kiện khi cách xác định đáp ứng đã rõ. Điều kiện mơ hồ hoặc dựa vào số/nguồn bắt buộc chưa xác minh không thành quyền chi có thể dùng.

Phân biệt điều kiện fact với một quyết định quyền lực còn thiếu. “Có biên nhận phù hợp” có thể kiểm tra từ source theo rule; “nếu trưởng bộ phận chấp thuận” phải có quyết định của đúng người/phạm vi và căn cứ, không để AI tự đánh giá là đã đồng ý. Chưa có quyết định cần thiết thì B8 chưa đủ cho handoff chi/thu. Có quyết định thật đáp ứng theo policy thì kiểm tra/ghi quan hệ, không mặc định yêu cầu người duyệt đầu bấm lại.

Trước chấp nhận quyết định để đi tiếp, kiểm tra thẩm quyền và dữ liệu/report hiện áp dụng cùng các thay đổi ảnh hưởng đã biết. Sai người có route rõ thì điều phối, vượt quyền thì chuyển đúng cấp. Ngoại lệ chỉ theo policy/quyền rõ, giữ kết quả gốc và không waive hard gates. Hai quyết định mâu thuẫn cần làm rõ hiệu lực/thay thế; không lấy latest, ưu tiên trong app hoặc cộng các quyền chi.

Quyết định bên ngoài đủ nguồn/phạm vi/quyền/hiệu lực có thể dùng lại; import không là request/approval mới. Source mới ảnh hưởng entitlement, số, chiều, scope hoặc nghĩa vụ thì giữ lịch sử và yêu cầu kiểm tra/đánh giá hiệu lực. Ghi chú vô hại không mặc định làm mất quyết định.

Chi/thu thực tế hoàn thành đúng một phần của quyết định không mặc định buộc duyệt lại phần còn lại: ví dụ duyệt tổng3, đã thực nhận1, không có pending/issue/đổi entitlement thì có thể tiếp tục phần2 trong quyết định đó khi điều kiện đủ. Đây là xử lý tiền đã xảy ra, không là tính năng phê duyệt từng phần; nguồn mới vượt/chệch quyết định phải được xét riêng.

## 3. Bước 9 — Thực hiện, đối chiếu và điều kiện đóng

### 3.1. Trước và sau hành động bên ngoài

Ngay trước khi tạo/giao gói thực hiện trong app, kiểm tra quyết định hiện áp dụng, người/phần/số/chiều, nghĩa vụ cùng phạm vi, nguồn tiền đến mốc cần thiết, phần đã hoàn thành/lệnh chờ và Stop/thu hồi đã biết. Thiếu/cũ/mâu thuẫn/ngoại lệ ảnh hưởng thì chặn phần liên quan; không dùng số đã tính trước để tạo thực hiện mới cho cùng phần. App chỉ kiểm soát hành động trong workflow, không bảo đảm dừng lệnh ngân hàng bên ngoài.

Gói đang bàn giao giữ report/decision version và mốc nguồn. Source mới ảnh hưởng sau handoff thì đánh dấu gói cần kiểm tra lại/dừng sử dụng trong app; người thực hiện phải kiểm tra trạng thái/gói hiện áp dụng trước hành động ngoài app. Nếu vẫn dùng bản giấy cũ hoặc tiền đã đi, ghi sự kiện thật và xử lý sai lệch; không tuyên bố app ngăn được hành động đó. Fulfillment đúng phạm vi chỉ giảm phần chưa thực hiện, không mặc định thay entitlement như guard ở B8.

Chi thêm: người tài chính thực hiện chi, đối chiếu A thực nhận. Hoàn lại: A thực hiện trả, người phụ trách tài chính đối chiếu công ty thực nhận. Không tự cấn trừ/khấu trừ/chuyển tiền. Phương thức và source phù hợp theo rulebook; tiền mặt có chứng từ quỹ/giao nhận phù hợp, chuyển khoản có nguồn/trạng thái/đúng người nhận, không bắt cùng một loại sao kê cho mọi case.

Sự kiện ghi số thực tế, bên trả/bên thực nhận, thời điểm, quan hệ khoản/quyết định/công việc, loại tiền và nguồn. Raw source/claim/fact/xác nhận giữ riêng. Debited/Submitted/Paid label không tự là thực nhận; nguồn chưa đủ coverage không chứng minh không có chi/thu khác. Giao dịch nhầm người hoặc chưa rõ loại/phân bổ không được tự nhận là đã hoàn thành đúng nghĩa vụ.

| Kết quả thực tế có căn cứ | Trạng thái và hành động |
| --- | --- |
| A thực nhận đủ3 đúng quyết định chi thêm | Ghi hoàn chi phí đã nhận3 cùng nguồn; B7 trong scope đầy đủ E5/ứng ròng2/hoàn chi phí ròng3 cho S0; kiểm tra điều kiện đóng. |
| Công ty thực nhận0,7 đúng nghĩa vụ hoàn ứng | Ghi hoàn ứng thực nhận0,7, giữ ứng gross4/return0,7; với E3,3 và không history/issue khác, S0; kiểm tra đóng. |
| Chỉ nhận1 của quyết định chi3, phần2 xác định chưa thực hiện | Giữ1 thực nhận và phần còn lại; chỉ tiếp tục đúng phần còn lại khi quyền/điều kiện/lịch sử đủ và không pending/issue. Không dùng lại toàn bộ3; chưa đóng. |
| Lệnh/sự kiện còn chờ hoặc kết quả chưa rõ | Giữ pending/unknown, không cộng vào thực nhận hoặc tạo thêm thực hiện cho cùng phần. Tại mốc đối chiếu/hành động kiểm tra đã công bố mà source vẫn thiếu outcome, tạo câu hỏi cụ thể cho chủ nguồn về đúng lệnh/phần/trạng thái; không im lặng giữ chờ vô hạn hoặc tự coi failed/0. |
| Thất bại/hủy có căn cứ đủ về tiền liên quan | Giữ attempt/kết quả, kiểm tra lại phần còn được thực hiện trước lần tiếp theo. Một lỗi UI hoặc thiếu nguồn không tự chứng minh chưa chi/chưa nhận. Không auto-retry ngân hàng. |
| Đúng A nhận4 cho cùng nghĩa vụ quyết định chi3, quan hệ/nguồn đã rõ | Ghi đầy đủ event4; phần nghĩa vụ cũ3 đã được thực hiện, phần vượt1 là ngoại lệ riêng chưa giải quyết. Không clip event thành3, không cho chi3 lần nữa, chưa đóng hoặc tự xác định A phải hoàn1 khi policy/căn cứ chưa có. |
| Sai người, loại/phân bổ hoặc nguồn mâu thuẫn | Giữ money event/source và sự cố; chưa xác nhận fulfillment đối với người/phần đúng khi quan hệ chưa rõ. Chuyển người phụ trách; không tự cho chi bù hoặc suy fraud/cấn trừ. Chuyển3 cho B không là A đã nhận3; A=0 cũng chỉ khi nguồn đủ xác định. |
| Refund/reversal/thu hồi hoặc sự kiện đến muộn | Giữ lịch sử và quan hệ, kiểm tra phần ảnh hưởng theo B5/B7. Stop/thu hồi không xóa money fact, không chứng minh đã hủy lệnh hoặc đã hoàn tiền. Ghi/xác minh tiền thật theo quyền không cho phép chi mới. |
| S=0 và không cần hành động tiền | Chỉ kiểm tra nguồn/decision/history/điều kiện đóng; không tạo giao dịch0. |

Một sự kiện nhập qua nhiều sources không cộng nhiều lần; same amount/date chưa đủ gộp, IDs cần phạm vi nguồn/quan hệ. Refund/reversal đúng loại, không vừa trừ net vừa cộng return; không đưa vendor refund khác quyền hưởng thành P/RA tùy ý. Phần ngoài luồng tự tính có kết quả xử lý theo đúng người/policy và căn cứ phải giữ riêng; chưa resolved không là footnote để đóng.

Quyết định đã thực hiện đủ không tự được mở lại quyền thực hiện do refund/reversal. Giữ nguồn và kiểm tra B7/quyền hiệu lực; phần phát sinh cần quyết định/cách xử lý hợp lệ ở B8 theo policy. Attempt thất bại trước fulfillment khác với received rồi refund; chỉ cái trước có thể tiếp tục phần chưa hoàn thành của quyết định còn áp dụng khi đã đủ nguồn/điều kiện, không tự auto-retry.

### 3.2. Khi nào được đóng?

Chỉ đóng theo **mốc/phiên bản nguồn và phạm vi được công bố**, khi đồng thời:

1. Quyết định/nguồn xử lý đang áp dụng đúng quyền/phạm vi; mọi thay đổi ảnh hưởng đã được kiểm tra.
2. Các khoản phải chi/thu trong scope đã đối chiếu thực nhận đủ, hoặc có kết quả cân bằng không cần chuyển tiền. Lịch sử chi/thu/ứng/returns khớp, không thiếu scope để giả số0.
3. Không còn pending, sai lệch, nguồn bắt buộc chưa rõ hoặc nghĩa vụ/ngoại lệ tiền chưa giải quyết trong cùng phạm vi, kể cả ngoài công thức tự tính.
4. Kết quả và căn cứ xử lý được lưu, các sự kiện tiền không bị xóa/ghi đè. Từ chối/Stop hoặc sốS0 đơn độc không thay các điều kiện trên.

Nguồn/sự kiện mới sau đóng có ảnh hưởng thì giữ lần đóng trước, tạo bản bổ sung/điều chỉnh liên kết và kiểm tra lại phần ảnh hưởng; không âm thầm sửa case đã chi hoặc tạo tiền mới từ bản copy. Exact resubmission không mở nghĩa vụ/chi mới chỉ vì pipeline chạy lại. R4 chốt quy tắc nguồn/mốc/trạng thái cụ thể, không giả đóng là bảo đảm biết mọi giao dịch ngoài hệ thống về sau.

## 4. Điều cần chủ dự án review và phép thử

Đề xuất chốt MVP: B8 phê duyệt kết quả đầy đủ hoặc trả lại/từ chối/tạm dừng; số/chiều khác cần re-check. B9 ghi/đối chiếu thực tế, giữ incomplete và chỉ đóng theo evidence. Không thêm installmentapproval, bank execution hoặc quyền xử lý mọi recovery giữa ba bên.

Phép thử thiết kế chưa chạy: +3 approve/receive3/close; −0,7 approve/companyreceived/close; zero no money; approve2 khi đề xuất3; refusal vẫn còn advance; wait noresponse; điều kiện chưa đạt; money/entitlement thay đổi trước action; paid1 vs pending2; wrongbeneficiary/overpaid; Stop giữa handoff/receipt; importedapproval reused; exactcopy sauclosed vsbillnew; exceptionresolved/source không đủ. Gold/policy và runtime/Verify sẽ chốt sau.

Hai bước là thiết kế đang thảo luận, không xác nhận đúng luật tài chính thực tế hoặc BTC đã chấp nhận routine boundary của Challenge A. Giữ đo toàn công sức con người và chất lượng chuyển tiếp, không thay denominator để tuyên bố đạt.

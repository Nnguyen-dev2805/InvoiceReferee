# R3 — Phạm vi phát hành và đơn vị tự động hóa của MVP

Ngày: 09/10/2026 · Trạng thái: **CHỦ DỰ ÁN ĐÃ ĐỒNG Ý KHUNG PHẠM VI; CONTRACT CHI TIẾT CHỐT R4/R5/R7, CHƯA CODE**.

Chủ dự án đồng ý đề xuất lấy quyết toán sau chi làm công việc đánh giá chính, giữ kiểm tra ứng trong MVP và đánh giá riêng theo phạm vi đã trình bày. R3 chốt hướng/phạm vi sản phẩm để tiếp R4; không chốt những schema/ngưỡng/định dạng chưa được mô tả hoặc chứng minh BTC đã chấp nhận boundary.

Căn cứ: [brief gốc](../Challenge_Brief_OrganizationAI_VN.docx.md), [roadmap](../DISCOVERY_ROADMAP.md), [khung 9 bước đã duyệt](R2_CASE_WALKTHROUGH.md), [B8/B9](B8_B9_MVP_PROPOSAL.md). Không dựa current code hoặc spec cũ để đặt nhu cầu/gold. Nguồn/quyền/ngưỡng demo chưa thành policy doanh nghiệp thật.

Bản này đã bổ sung sau [review độc lập R3](../reviews/2026-10-09-r3-scope/REVIEW.md). [Snapshot được review](../reviews/2026-10-09-r3-scope/TARGET_R3_MVP_SCOPE_DRAFT.md) và verdict gốc giữ nguyên; bản bổ sung được lead kiểm tra và chủ dự án đồng ý ở mức phạm vi, chưa được review độc lập lại hoặc runtime verified.

## 1. Phát biểu phạm vi

MVP giúp người phụ trách xử lý hồ sơ công tác của một nhân viên: kiểm tra đề nghị ứng trước công việc và đối chiếu/quyết toán sau công việc từ chứng từ cùng nguồn tài chính trong phạm vi được cung cấp. Hệ thống hoàn tất phần kiểm tra và báo cáo khi đủ căn cứ; khi thiếu hoặc vượt phạm vi/quyền, tạo câu hỏi/vấn đề có người nhận, nhận bổ sung và kiểm tra lại phần ảnh hưởng.

Người dùng nghiệp vụ chính là người kiểm tra tài chính/kế toán; nhân viên nộp/bổ sung, người có quyền cho phép công tác/quyết định tiền, người thực hiện chi/thu. MVP vận hành do một operator, có thể mô phỏng các vai; không phải multi-user enterprise auth. Mỗi hồ sơ một nhân viên/một công việc, hệ thống có thể có nhiều hồ sơ/lịch sử liên quan để kiểm tra trùng trong dataset được quản lý, không coi toàn công ty đã được kết nối.

## 2. Hai công việc được giao tự động, không chỉ đọc OCR

| Công việc | Bắt đầu | Hoàn thành phần routine | Khi chưa đủ |
| --- | --- | --- | --- |
| Kiểm tra đề nghị tạm ứng (B3) | Đề nghị, căn cứ công tác áp dụng, policy và nguồn lịch sử cần thiết đã được tiếp nhận | Lưu báo cáo từng check/nguồn/rule, số xin và nghĩa tiền, quyền/người xử lý tiếp; kết luận đủ điều kiện kiểm tra hoặc không đủ điều kiện rõ theo rule. Không cần operator tính/ghép lại để tạo báo cáo | Lưu vấn đề, câu hỏi đúng phần/người/ref hoặc lỗi xử lý; chưa kết luận đủ điều kiện dựa trên fact nghi vấn |
| Đối chiếu/quyết toán sau chi (B7) | Hồ sơ B6 và nguồn tài chính áp dụng đủ context; từng check có thể chạy độc lập khi đủ | Lưu bảng khoản/phần, nguồn/rule, phần chấp nhận/loại, nghĩa tiền/lịch sử/coverage; tính số/chiều đề xuất khi toàn scope ảnh hưởng đủ rõ. Không cần người xác nhận lại mọi dòng đã đủ nguồn | Giữ phần đã kiểm tra; chưa final số toàn hồ sơ khi materialunknown/ngoại lệ unresolved; lưu câu hỏi/vấn đề/người nhận để tiếp tục |

Không bắt mọi hồ sơ được phép kết luận ngay mới coi là có xử lý: công việc có thể dừng đúng với câu hỏi có chủ sở hữu. Nhưng không báo case escalated là routine tự hoàn tất, không coi mọi lời trả lời của người dùng là gold đúng hoặc gọi failure là thiếu chứng từ.

Điểm bắt đầu job là gửi một yêu cầu kiểm tra với input/source theo interface được công bố, **kể cả nguồn thiếu/mâu thuẫn**. “Đủ nguồn” là điều kiện của case routine/kết luận cuối, không filter để loại case khó trước khi đếm. Thiếu chính context cần thiết thì hệ thống lưu vấn đề đúng, không đoán hoặc gộp bừa. Question→answer→re-check thuộc cùng lifecycle có liên kết/version; không coi sau khi người bổ sung xong là case đã routine-auto ngay từ đầu.

Routine đo trên job kiểm tra mới: từ input được nộp tới report/kết luận được lưu không cần người chọn đúng transaction, sửa số, map payer/khoản, xác nhận fact hoặc trả lời câu hỏi giữa chừng. Source upload/import là input, nhưng mọi công sức chuẩn bị/tìm chọn nguồn theo case trước lúc gửi cũng phải đo trong vòng đời nghiệp vụ, không gọi free pre-processing. Case được người ghép trước có thể kiểm tra tiếp, nhưng phải ghi mode/effort assisted, không dùng nó chứng minh hệ thống tự ghép routine raw sources.

Đề xuất **B7 quyết toán sau chi là công việc trình diễn/đánh giá chính của Challenge A**; B3 kiểm tra ứng vẫn thuộc MVP và có tập/cổng riêng. R5 chốt coverage/strata/mẫu số, báo cả hai thay vì gộp để che lỗi; Verify3routine/2escalation có scope công bố rõ. Task kiểm tra hoàn tất không đồng nghĩa toàn 9 bước được tự chủ hoặc BTC đã chấp nhận ranh giới.

## 3. Các bước workflow trong bản MVP

Tiếp nhận form/tài liệu/import bảng có sẵn vào cùng lõi; có thể dùng căn cứ công tác/phê duyệt bên ngoài khi đủ theo policy. Theo dõi quyết định và sự kiện tiền theo khung 9 bước. Operator ghi/nhập/import source tài chính cùng phạm vi/mốc; employee declaration và financial evidence vẫn khác nghĩa. Không ép nhân viên tự tính net hoặc khai thay tất cả chi phí công ty biết.

B2/B4/B8 là quyết định của người có quyền theo nội dung đã chốt. B5/B9 do con người thực hiện tiền ngoài app; hệ thống ghi/đối chiếu source. B7 đủ kiểm tra tạo báo cáo chờ quyết định tài chính B8. Sau quyết định hợp lệ, MVP chuẩn bị thông tin/gói thực hiện phù hợp; đây chưa là bank instruction đã gửi hoặc money receipt.

Giai đoạn ưu tiên đo chất lượng là **A: hoàn thành kiểm tra/báo cáo**. Hướng **B: tự tạo đề nghị chi/thu theo quyền** vẫn nằm trong roadmap để cải tiến sau khi có baseline A và các gates hành động; không lấy độ đúng A làm bằng chứng an toàn B. Wrapper ghi quyết định/chi/thu theo 9 bước không tự có nghĩa mọi hành động tạo request của B đã được tự động hóa.

Trong A, “gói thực hiện” là report + quyết định hiện áp dụng + refs/lịch sử để người thực hiện sử dụng; không là entity/lệnh chi/thu mới được hệ thống tự tạo. B bổ sung tự tạo đối tượng đề nghị chi/thu sau quyết định hợp lệ và các actiongates, có ID/status/version/quyền và chống tạo trùng; vẫn không thay người quyết định tiền hoặc bank execution. B chưa tự nằm trong lời hứa phát hành A chỉ vì một nút manual hoặc wrapper có tên tạo đề nghị.

| Bước / luồng | Tự động trong A | Con người / ngoài app | B bổ sung |
| --- | --- | --- | --- |
| 1 — Đề nghị trước công việc | Nhận/lưu nguồn, chuẩn bị dữ kiện và kiểm tra ban đầu | Nhân viên nộp/khai mục đích, source hoặc phần chưa biết | Không thay quyết định người |
| 2 — Cho phép công tác | Trình context/nguồn, kiểm tra dùng căn cứ có sẵn, ghi decision | Người có quyền cho phép, trả lại/từ chối; source ngoài được dùng theo policy | Không tự cho phép công tác |
| 3 — Kiểm tra ứng | Tự check/rule/math/history và lưu report/câu hỏi cụ thể | Chủ nguồn giải quyết phần thật sự thiếu hoặc người có quyền xử lý ngoại lệ | Không tự biến report thành financialapproval |
| 4 — Quyết định ứng | Lưu/check quyền/hiệu lực/phiên bản và điều kiện quyết định | Người có quyền quyết định ứng | Đề nghị chi sau quyết định/gates nếu triển khai B |
| 5 — Chi ứng thực tế | Đọc/đối chiếu source và lưu actualevents/currentstate | Con người chi bên ngoài, cung cấp nguồn; unresolved hỏi đúng owner | Không bank execution |
| 6 — Hồ sơ sau chi | Nhận/đọc/đề xuất khoản và source, giữ relations/versions | Nhân viên xác định khoản/phạm vi/mục đích; nguồn finance có sẵn hoặc cung cấp khi thiếu | Không thay nhân viên định phạm vi đề nghị |
| 7 — Kiểm tra quyết toán | Tự ghép/check/số/rule và lưu report/net khi đủ, hoặc vấn đề/câu hỏi | Chỉ giải quyết missing fact/ngoại lệ/quyền thật sự cần | Không tự bỏ unresolved để tạo request |
| 8 — Quyết định tài chính | Lưu/check reportdecision đang áp dụng, điều kiện và quyền | Người có quyền quyết định, trả lại/từ chối/tạm dừng | Tạo đề nghị chi/thu sau approval/gates nếu triển khai B |
| 9 — Chi/thu và đóng | Đối chiếu receipts/history, kiểm tra và lưu closure theo quyền/nguồn/policy đã chốt | Người chi/thu bên ngoài; xác minh source, xử lý issue; confirmation khi policy yêu cầu | Không auto-transfer/recovery; requestaction chưa là receipt |

## 4. Phạm vi case ưu tiên

| Nội dung | Đề xuất MVP |
| --- | --- |
| Nghiệp vụ | Tạm ứng công tác và hồ sơ quyết toán/hoàn trả chi phí công tác; có ứng hoặc tự chi không ứng, hủy/thay đổi có tiền cần xử lý |
| Nhóm chi | Vé/di chuyển, khách sạn, ăn phục vụ công việc/tiếp khách trong hồ sơ công tác; không tự mở sang mua hàng–PO–nhận hàng/tồn kho |
| Tiền và khoản | VND, nhiều khoản/chứng từ trong một hồ sơ; một khoản có nhiều source, payer theo phần rõ; company direct khác employee-paid; ít nhất lịch sử trong phạm vi cần kiểm tra |
| Nguồn tiếp nhận | Form/bảng kê, ảnh hoặc PDF chứng từ, tài liệu phê duyệt/bằng chứng phù hợp; financial source nhập/import theo phạm vi. Không hứa đọc mọi mẫu/định dạng hoặc source giả mạo được xác thực |
| Lịch sử | Actual advance/returns/reimbursements theo đúng source/scope; nộp lại/bổ sung/revision có quan hệ; pending/actualpartial receipt/sai lệch được giữ, không suy0 hoặc mở quyền chi lại |
| Refund hỗ trợ | Thuộc đúng phần employee-borne đã được xét và A thực nhận theo nguồn/policy rõ; giữ gross facts, không double count hoặc net theo tên giấy |
| Kiểm soát | Phiên bản nguồn/policy/quyết định, căn cứ/ref, Stop trong workflow, thay đổi/override đúng quyền không waive hard gates; exact replay không tạo action trùng, closure theo mốc/nguồn và tất cả nghĩa vụ cùng scope |

Source schemas, loại proof tối thiểu cho từng khoản, thời hạn/hạn mức/rounding/quyền và format import được chốt ở R4/R7, không tự đặt con số ở R3. Mỗi phạm vi định dạng cần có case chứng minh trước khi gọi là hỗ trợ; chưa được phép đọc thì báo giới hạn nguồn/technical xử lý đúng, không approve từ dữ kiện suy đoán.

## 5. Không tự xử lý toàn bộ các ngoại lệ

Refund về bên khác/quyền hưởng chưa rõ; company-paid personal recovery; double payment/vượt nghĩa vụ; giao dịch gộp/phân bổ nhiều người/công việc chưa có quy tắc; ngoại tệ/chi ngoài nhóm áp dụng: lưu source/issue/người nhận và giới hạn, không ép vào một công thức. Ngoại lệ tiền còn unresolved trong cùng settlement chặn final chi/thu/đóng dù component đã tính được. Xử lý ngoài luồng có căn cứ giữ riêng; chỉ quay lại automatic path khi nguồn/cách biểu diễn/rule đủ, không “bấm resolved” để thay E/A/P.

Không xây ngân hàng, ERP integration, payroll deduction, accounting engine mọi nghĩa vụ, multi-tenancy/SSO/scaling/microservices. Đây là giới hạn capability, không suy mọi case ngoài auto-scope là business policy cấm. Nếu policy chưa định → chủ policy; fact chưa rõ → chủ source; vượt quyền → người có quyền; processor không hỗ trợ nhưng fact/rule rõ → nêu giới hạn tự động riêng. Sai routing có người đúng đã biết thì tự điều phối, không câu hỏi vô ích.

## 6. Đầu ra kiểm tra và điều kiện hoàn thành

| Kết quả | Điều kiện/hành động |
| --- | --- |
| Báo cáo hoàn tất trong phạm vi | Những checks bắt buộc áp dụng có nguồn/quality/rule và đạt; kết luận hoặc số/chiều rõ khi cần, lưu/ref/phiên bản, đưa tới bước quyết định phù hợp. Không cần người làm lại công việc kiểm tra |
| Không đủ điều kiện rõ | Phần bị loại cùng rule/source/lý do. Không tự hỏi “duyệt cho qua” khi không có ngoại lệ hợp lệ, không xóa nghĩa vụ tiền đã xảy ra |
| Cần làm rõ fact | Khoản/phần/các source/giá trị chưa rõ, owner và câu hỏi cụ thể; nguồn bổ sung/confirmation đúng scope được lưu rồi re-check |
| Ngoài quy định / vượt quyền | Nguyên nhân riêng, phần cần quyết định và đúng người; không gộp với missing fact hoặc dùng approve để xóa quality gate |
| Ngoài khả năng tự động / lỗi xử lý | Capability limit khác technical failure, khác policy ban; giữ trạng thái và dữ kiện, không giả success, không tự loại khỏi báo cáo đánh giá |

Lời khai, dữ kiện do AI đề xuất và xác nhận con người không tự cùng authority; rulebook định fact/source nào đủ cho check nào. Confidence hoặc feedback không nới businesslimits/quyền/bằng chứng bắt buộc. Không tài chính final trên số bắt buộc còn nghi vấn. Một khoản chưa đủ không ngăn check độc lập nhưng không authorize chi phần đã biết khi còn issue ảnh hưởng kết quả.

## 7. Tác động và yêu cầu cuộc thi cần chứng minh

Tuyên bố giá trị dự kiến: giảm tìm/ghép nguồn, cộng tiền và kiểm tra lại lịch sử; người duyệt xem bảng đối chiếu/căn cứ để quyết định. Phải đo cả nhập/import, chờ/bổ sung, số lần chạm hồ sơ và chất lượng cuối; không giả định upload + OCR tự làm nhanh hơn.

R3 đề xuất tên/boundary metric: thời gian thao tác chủ động; thời gian chuẩn bị/tìm/nhập/import/ghép nguồn; số lần human touch; số vòng question-answer/sửa/re-check; thời gian chờ riêng; outcome/quality/error và technical failure; first-pass routine completion của job công bố và kết quả toàn lifecycle. Đếm checkpoint tài chính cố định riêng nhưng không giấu khỏi total human effort. R5 chốt cách đo/định nghĩa denominator/threshold và phép chấm độc lập, không tự đặt tỷ lệ đạt tại R3.

So before/after dùng cùng phạm vi nguồn/case và cùng điều kiện thao tác; paired internaltest có cùng operator nhưng xử lý thứ tự/case tương đương để giảm hiệu ứng nhớ/học. Không loại nguồn prep ở MVP mà tính nó ở baseline, không chỉ chọn case thuận lợi hoặc bỏ technicalfail khỏi tổng báo cáo. Kết quả/log/checkpoints và timing của người khi có phải đủ để tái dựng phép đo; chưa hứa software tự đo được mọi thời gian chuẩn bị ở ngoài app. Thử người dùng thực và cải tiến từ feedback vẫn bắt buộc cho Sprint2, khác selftest.

Theo [brief](../Challenge_Brief_OrganizationAI_VN.docx.md), bản thi cần >=15 case, Core4/Escalation5 (3 routine/2 cần chuyển tiếp), input mới, independent miss/unnecessary escalation, câu hỏi có người trả lời, ngưỡng chuyển tiếp thích nghi và ít nhất3 người làm nghiệp vụ thực cùng cải tiến từ feedback. LiveURL/no-account, runbook/audit/Stop/Override, repo/history, video/5slides/buildlog là yêu cầu giao nộp; phase R5–R9 thiết kế/triển khai/chứng minh, không defer khỏi mục tiêu Sprint2. Research/agent không thay trial thật.

Rủi ro mở: brief yêu cầu routine tự động hoàn toàn, trong khi khung giữ humanfinancialcheckpoints. Đề xuất đơn vị đo là hai công việc kiểm tra ở Mục2, sau một yêu cầu chạy routine không cần con người bổ sung/ghép/tính để lưu kết quả. Báo riêng checkpoint cố định, câu hỏi cần giải quyết bất định và toàn humaneffort; không đổi denominator để tuyên bố phù hợp. Chưa có xác nhận BTC rằng report-ready-for-human-approval được tính là routine hoàn tất theo ChallengeA. R3 chốt phạm vi sản phẩm không tự đóng rủi ro này.

## 8. Quyết định cần chủ dự án chốt

Đề nghị đầu tiên R3: **bản MVP hỗ trợ cả hai luồng đã thống nhất; baseline đầu chứng minh hệ thống tự hoàn thành hai công việc kiểm tra/báo cáo, phần quyết định/tiền là workflow con người có căn cứ; tự tạo đề nghị chi/thu theo quyền là cải tiến B sau gates**. Phạm vi nhóm chi/sources/ngoại lệ ở Mục4/5 là đề xuất phát hành, chưa tự được duyệt chỉ vì có trong R2.

Sau quyết định này, R4 chốt rulebook/source/authority cụ thể và R5 oracle/gates. R3 chỉ đóng khi các lựa chọn phạm vi, đầu ra/hành động và giới hạn được chủ dự án chốt; không coi bản thảo này là spec giao coding agent hoặc B1 đã đóng băng.

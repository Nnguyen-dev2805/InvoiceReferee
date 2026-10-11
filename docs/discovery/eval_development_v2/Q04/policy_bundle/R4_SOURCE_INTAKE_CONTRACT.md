# R4.4 — Bộ nguồn tiếp nhận và đối chiếu cho MVP

Ngày: 09/10/2026 · Trạng thái: **CHỦ DỰ ÁN ĐÃ ĐỒNG Ý BỘ NGUỒN/PHẠM VI ĐƯỢC TRÌNH BÀY; CHƯA KÍCH HOẠT/CODE, CHƯA LÀ GOLD ĐÁNH GIÁ**.

Chủ dự án trả lời “Đồng ý tiếp tục đi” sau trình bày R4.4. Ghi nhận chốt cách nhận nguồn nhân viên/company/quyết định và nhập/import sự kiện tiền có căn cứ/coverage, không nhập đáp án. Schema/API/format pipeline, căn cứ quyền và bản freeze đánh giá vẫn chưa được suy là hoàn tất. [Packet giả lập đầu tiên](examples/work_budget_01/README.md) dùng để đi bằng tay theo bản thiết kế, không phải thử người thật hoặc Verify.

Căn cứ [lõi dữ kiện R4.1](R4_DATA_SOURCE_DRAFT.md), [evidence đã chốt R4.2](R4_EVIDENCE_RULES_DRAFT.md), [policy ngân sách tổng](R4_WORK_BUDGET_POLICY.md), [ba vai/bàn giao](R4_ROLES_HANDOFF_POLICY.md). Phần này cụ thể hóa nguồn và coverage cho MVP, không mở thêm hạn mức nhóm chi, ngân hàng/ERP/auth doanh nghiệp. Lead tự review, không subagent. Phân biệt phần được chốt trước với định dạng/quyền/phiên bản còn cần chốt ở cuối.

## SI-01 — Hai gói đầu vào theo giai đoạn

| Giai đoạn | Người nộp/nguồn nhân viên | Nguồn công ty/quyết định | Kết quả có thể chuẩn bị |
| --- | --- | --- | --- |
| Trước công việc | Người/công việc, mục đích/phạm vi, thời gian, dự toán tổng/phần dự kiến employee–company, số xin ứng; form hoặc hồ sơ ngoài app | Quyền người duyệt; căn cứ công việc/ngân sách nếu đã có; history ứng/approval/request/pending liên quan đủ phạm vi | Report kiểm tra đề nghị và nội dung cần quyết định; không đòi invoice sau công việc hoặc proof đã nhận khoản đang xin |
| Sau công việc/hủy cần xử lý | Bảng kê/phạm vi chi đang đề nghị, chứng từ chi phí, payer evidence phù hợp phương thức; purpose/attestation khi cần | Căn cứ B/công việc hoặc quyết định chấp nhận sau phát sinh khi đã có; company-direct, actualadvance/returns/reimbursements, pending và lịch sử hồ sơ liên quan | Bảng đối chiếu chi phí và tiền; E/S cuối chỉ khi fact/policy/quyền ảnh hưởng đủ |

Thiếu gói hoặc trường không ngăn lưu hồ sơ/chạy các check độc lập; hệ thống ghi đúng vấn đề. Chính quyết định đang xin chưa có không là lỗi upload: chuẩn bị report để người có quyền quyết định. Nhân viên không phải khai thay company-side history hoặc tự tính S.

## SI-02 — Nguồn nào đủ cho việc gì?

| Câu hỏi cần trả lời | Nguồn chủ yếu / ai cung cấp | Điều kiện đủ trong demo-policy | Điều không được suy |
| --- | --- | --- | --- |
| Khoản là gì, giá trị bao nhiêu, thuộc công việc nào? | Invoice/receipt/vé từ nhân viên hoặc công ty; purpose/context nhân viên theo policy | Value và facts cần dùng rõ, source/locator thật, quan hệ công việc đủ và không còn contradiction ảnh hưởng | Form khai tổng không tự là invoice amount; tổng rõ không làm các fact critical khác rõ |
| Nhân viên đã trả phần nào cho vendor? | Payment source cá nhân/receipt phù hợp; hoặc bộ cash receipt + bounded attestation đã chốt | Amount/parties/part/ref và actualpayment đủ theo R4.2; company-side source liên quan đủ, không unresolved contradiction | PERSONAL, tên trên bill, invoice companyname hoặc chỉ receipt không payer chưa là proof |
| Công ty đã trả vendor phần nào? | Nguồn tài chính công ty do kế toán đưa vào, source phát hành và receipt phù hợp | Companypayer/vendorpayee, amount/phần và expense/booking liên kết rõ, receipt semantics đủ | Companyname trên invoice, paymentrequest/approval hoặc row Paid generic không tự actualreceipt |
| Nhân viên đã nhận ứng/hoàn chi phí? | Source phù hợp của sự kiện tiền do kế toán/nhân viên cung cấp | Đúng actualpayee, amount, work/obligation/purpose và outcome thực nhận theo R4.2 | Đã duyệt, đã gửi lệnh, debit hoặc kế toán upload file không tự chứng minh đã tới người nhận |
| Công ty đã nhận tiền hoàn ứng/trả lại tiền hoàn chi phí? | Source phía nhận của công ty qua kế toán, quan hệ với khoản gốc | Actualreceipt phía company và phân loại/quan hệ RA/RP đủ; giữ gross history | Nhân viên nói đã chuyển không tự companyreceived; vendorrefund không tự RA/RP |
| Ngân sách/phạm vi và quyền quyết định? | Quyết định trong app hoặc căn cứ ngoài app, quyền được giao | Nội dung/người/quyền/phạm vi/hiệu lực/version rõ; tái dùng khi còn phù hợp | Approved chung không quyết tất cả nội dung; sếp/rolepicker không tự có quyền |
| Có khoản khác đã xử lý/pending hoặc nhóm bằng0? | Tập nguồn/hồ sơ liên quan cùng coverage, hoặc confirmation absence đúng owner/observability | Đủ đúng công việc/người/nhóm/phương thức/phía tiền/mốc cần xét, không contradiction | Không thấy trong một file hoặc không có đề nghị ứng không chứng minh0/chưa từng nhận |

Một tài liệu có thể đáp ứng nhiều hàng nếu đủ nội dung, không bắt mỗi hàng có một file. Có alternative source rõ/phù hợp thì dùng có ref; không bắt nộp thêm đúng một mẫu giấy chỉ để đủ danh sách. Không xác thực forensic/tax/legal bằng ảnh hoặc giả coi tất cả export là nguồn ngân hàng thật.

## SI-03 — Tập nguồn tài chính công ty: nhập/import, không nhập đáp án

Đề xuất MVP nhận bảng nguồn tài chính theo lô (CSV hoặc bảng nhập tương đương) cùng tài liệu/căn cứ liên quan. Không tích hợp live bank/ERP. Có thể dùng nguồn kế toán đang quản lý nếu đủ nghĩa/provenance theo R4.2; không yêu cầu mọi trường hợp luôn có bankstatement. Nguồn gốc và độ đủ phải được công bố, không dùng cột do operator gõ để giả independent bank verification.

Các thông tin nghiệp vụ tối thiểu khi cần dùng một dòng:

- Ref của bản ghi trong namespace nguồn; loại/purpose sự kiện theo nguồn, giữ raw và phần chưa rõ.
- Số gross VND, payer/payee thực tế, thời điểm sự kiện và rawstatus/outcome; không gom amount approval với receipt.
- Booking/invoice/work/employee refs và memo **nếu nguồn có**; không bắt operator tìm/map đúng invoice trước để phần ghép tự động có vẻ thành công.
- Source/locator và căn cứ kết luận actualreceipt hoặc pending/returned/unknown. Row Paid không đổi thành received chỉ do upload thành công.

Các nhóm cần nhận diện: company→vendor; ứng company→employee; hoàn chi phí company→employee; hoàn ứng employee→company; trả lại hoàn chi phí employee→company; vendorrefund và paymentattempt/pending khi liên quan. Loại chưa rõ giữ source và câu hỏi, không tự ép mọi khoản vào A/P/RA/RP. Một dòng có employee liên quan không tự có payee là employee.

Chưa chốt tên cột/schema/API/storage bằng tài liệu này; R7 cụ thể hóa sau business contract. ID nội bộ do app sinh chỉ để quản lý/ref, không giả transactionref gốc. Nguồn có mã công việc thật thì giữ; một dòng dùng cho nhiều sources giữ quan hệ để không cộng lại, không xóa source cũ.

**Không đưa vào gói nguồn các đáp án** như số được hoàn cuối, nhãn PASS/NEEDS_HUMAN hoặc reason kỳ vọng. Quyết định thực đã xảy ra/giá trị được duyệt là source legitimate khác đáp án của run hiện tại; giữ ngày/phạm vi/hiệu lực. Cùng amount/date không đủ tự ghép/gộp. Mapping do người giải quyết sau hỏi được ghi assisted, không gọi first-pass autonomous.

## SI-04 — Phạm vi nguồn được cung cấp

Kế toán cung cấp/giải thích phạm vi nguồn công ty theo công việc đang xét; nhân viên cung cấp nguồn phía mình. Phạm vi gồm: origin/issuer, ai đưa vào, owner có thể xác nhận; người/công việc và loại/phương thức/phía sự kiện được phủ; từ–đến/as-of phù hợp và filters/missingranges/căn cứ đủ nguồn. Có thể một bộ nguồn phủ nhiều hồ sơ; không nhập lại bản đã có cho từng case.

Coverage là thông tin có căn cứ, không checkbox “đầy đủ” vô điều kiện. Kế toán chỉ thấy một bankaccount không tự xác nhận toàn bộ cash/card/account khác; nhân viên không xác nhận thay companydirect. Owner có khả năng quan sát đúng scope mới xác nhận absence theo R4.2. Dữ liệu nhập tay/CSV do kế toán chuẩn bị được ghi đúng mode/source; role không tự xác thực issuer hoặc biến lời nhớ thành statement tài chính.

Ví dụ mốc quyết toán ngày08/10, nguồn chỉ tới06/10: phần07–08 còn thiếu nếu cần để xác định payment/history. Không mặc địnhP=0. Nếu nguồn đủ mọi nhóm ảnh hưởng và xác định không ứng/không hoàn trước, A/P có thể bằng0 mà không tạo hai giao dịch0 giả. A nhận2 và trả lại2 giữ gross2/2, không gọi chưa từng ứng.

Ngân sách tổng cần nguồn các chi phí thuộc đúng công việc, gồm companydirect; không đòi lịch sử bữa ăn của công việc khác hoặc toàn công ty như bảng trần ngày cũ. Chứng từ/hồ sơ liên quan vẫn dùng để kiểm tra trùng nghĩa vụ khi có căn cứ. Nếu scope liên quan ngoài bộ nguồn chưa rõ thì report nêu giới hạn và giữ kết luận ảnh hưởng pending.

## SI-05 — Ví dụ một bộ nguồn minh họa

Ví dụ giả lập bằng mô tả, không nguồn ngân hàng thật, không fixture/gold hoặc runtime đã xác minh:

| Nhân viên cung cấp | Kế toán/nguồn công ty cung cấp |
| --- | --- |
| Bảng kê phần employee5triệu; hotel3, ăn1, di chuyển1 và originals/purpose; payer evidence phù hợp cho từng phần | Quyết định công việc vàB=8triệu đúng quyền; company→airline3triệu liên kết vé; ứng employee thực nhận2triệu; nguồn phạm vi đủ cho chi công ty/lịch sử/pending tới mốc xét, RA/P/RP=0 có căn cứ |

Hệ thống đối chiếu T=8, E=5, S=+3 chỉ khi mọi điều kiện đủ. Không cần trần khách sạn từng đêm/ăn từng ngày; vẫn cần source cho amount, actualpayer và công việc. Căn cứ vé công ty trả3 không cộng vào E và không trừ lần nữa. Payer cá nhân không bắt buộc bankstatement nếu bộ cash evidence đã chốt đáp ứng; sự kiện ứng/hoàn chi phí không dùng lại lời attestation payer expense để chứng minh actualreceipt.

Nếu nhân viên khai vé PERSONAL, cùng booking/phần có nguồn companypaid: hệ thống chỉ rõ hai nguồn/khai báo và hỏi căn cứ phần nhân viên thanh toán. Không tự hoàn thêm3 hoặc gọi gian lận. Nếu cả hai thực trả cùng nghĩa vụ thì giữ sự cố/doublepayment cần xử lý theo B7, không ép vào công thức routine.

## SI-06 — Thiếu dữ kiện thì hỏi ai, xử lý thế nào?

| Vướng mắc | Người phù hợp / xử lý |
| --- | --- |
| Amount/source expense mờ, mục đích chưa rõ hoặc employee payment thiếu | Nhân viên hoặc chủ nguồn phù hợp; readingconfirmation chỉ khi original thực đọc được, không nhập số đoán |
| Companydirect/ứng/hoàn chi phí/return/pending hoặc coverage company còn thiếu | Kế toán/chủ nguồn company có observability đúng scope |
| Không có B, vượtB, thay công việc hoặc chấp nhận sau phát sinh | Người duyệt trong quyền; nguồn fact bắt buộc vẫn phải đủ |
| Người duyệt chưa có quyền cho nội dung/phạm vi | Cần nguồn quyền/quyết định phù hợp; không tạo role cấp cao thứ hai như một lối tắt |
| Provider/format xử lý lỗi hoặc ngoài khả năng tự động | Trạng thái kỹ thuật/capability riêng; có thể bổ sung nguồn/phương thức đọc trong scope nhưng không giả employee sai hồ sơ |

Report giữ fact/check độc lập đã đủ. Unresolvedmaterial trong cùng quyết toán chặn finalS/chi/thu/đóng; không xử lý phần rõ như quyền chi từng phần đã được cấp. Source mới lưu version/re-check ảnh hưởng; không sửa ngầm tiền đã thực nhận hoặc quyết định cũ.

## SI-07 — Tự review: nguồn tốt vẫn có chi phí chuẩn bị

Một ledger do kế toán nhập/ghép hết trước Run có thể giúp kiểm tra tiền đúng nhưng chưa chứng minh AI giảm việc. R5 phải đo tìm/export/nhập/ghép nguồn trước Run, hỏi/bổ sung trong Run và review/approval sau Run, không chỉ latency. Phân biệt importedrawsource với handmatchedassisted và source giả lập với nguồn người thật có permission.

Không bắt một phương thức chính danh độc lập cho mọi fact: cashattestation được policy chấp nhận có giới hạn/mode; financesource/counterpartyreceipt đánh giá đúng profile. Nhưng không dùng sự đơn giản của MVP làm lý do miễn amount/receipt/linkage/coverage hard gates. Nhập/import là lựa chọn kết nối MVP, không đảm bảo dữ liệu công ty luôn đầy đủ/thật.

## Việc tiếp theo trước R5

Đề nghị chốt mô hình nhập/import nguồn có căn cứ và phạm vi, không nối ERP/bank và không bắt người nhập đáp án. Sau đó khóa policy/version + nguồn giao quyền của người duyệt + một vài packets giả lập đại diện; R5 lập expected độc lập từ originals/nguồn. Các schema/providerquality ngưỡng và storage/API cụ thể thuộc R7; không tự tạo confidence_score để nguồn thiếu đi qua.

Chưa có số giới hạn quyền, hiệu lực policy demo hoặc danh sách format đã chạy được từ tài liệu này; không gọi toàn R4 hoặc >=15case đã hoàn tất. Agent/selfreview và ví dụ không thay Sprint2 thử ít nhất3 người làm nghiệp vụ thật. Chưa dùng code cũ để quyết định nhu cầu/gold.

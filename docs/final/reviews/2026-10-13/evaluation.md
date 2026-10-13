# Review độc lập — Evaluation, adaptive escalation và đo lường tác động

**Ngày:** 13/10/2026. **Vai trò:** reviewer độc lập, chuyên trách evaluation/causal measurement. **Đối tượng:** thiết kế InvoiceReferee trên nhánh final, từ đề gốc và quyết định Q1–Q30. **Không đánh giá:** code/runtime, phần triển khai ERP, chi tiết SQL/race, hiệu năng thực đo, hoặc kết luận reviewer trước.

## 0. Verdict và phạm vi bằng chứng

**Verdict: CHỈ ĐỦ ĐỂ LẬP IMPLEMENTATION PLAN SAU KHI CHỈNH MỘT SỐ HỢP ĐỒNG ĐÁNH GIÁ CÓ RANH GIỚI.** Không thấy căn cứ buộc phải hủy phạm vi sản phẩm, đổi stack hay nới quyền tự quyết về tiền. Nhưng chưa nên chuyển nguyên văn mục 7–9 thành acceptance/claim của builder: cơ chế chứng minh lợi ích của threshold thích nghi chưa xác định được hiệu ứng phản thực tế; định nghĩa chỉ số an toàn còn bỏ lọt một loại kết luận sai; thiếu protocol tối thiểu để đo chất lượng câu hỏi và tác động người thật. Các thiếu sót này có thể sửa trong hợp đồng evaluation, không đòi một hệ thống ML học phức tạp.

**Đây là verdict cho mức độ đủ thông tin để viết plan; KHÔNG phải PASS của hệ thống, của Sprint 1/2, hay xác nhận phù hợp với bộ dữ liệu giám khảo.** Chính thiết kế xác nhận chưa có app, gold, benchmark, deploy, phản hồi chuyên môn hay kết quả M0: docs/final/ARCHITECTURE_AND_EVALUATION.md:3-8,355-359,393-407. Đề thi đòi phần mềm vận hành, live URL và Verify; giấy tờ không thay thế: docs/Challenge_Brief_OrganizationAI_VN.docx.md:25,37-39,169-171,197-206.

### Nguồn được xem trực tiếp

- docs/Challenge_Brief_OrganizationAI_VN.docx.md, toàn bộ 297 dòng; SHA-256 **33fbaba876e4b9392ba67f5503878a171db0032d68a8c19758d9d3a16c57a487**.
- docs/final/ARCHITECTURE_AND_EVALUATION.md, toàn bộ 430 dòng; SHA-256 **6407032ad9f148f0e1bca37b23db084e829fdc7597427380b7ee1209eeacf5ee**.
- GLOSSARY.md, toàn bộ 58 dòng; SHA-256 **e77b518df1dd615f294c781ba7f028c8a147f3b25f5924dd53972f52b2d100b3**.

Đã kiểm SHA-256 và branch final trực tiếp tại workspace. Đề gốc là **mandate cuộc thi**; tài liệu kiến trúc là **quyết định thiết kế đã chốt hoặc đề xuất của lead**, không phải kết quả đo; các đề xuất bên dưới là **suy luận và khuyến nghị reviewer**, không được gán thành yêu cầu BTC. Kết luận reviewer cũ tại docs/final/ARCHITECTURE_AND_EVALUATION.md:409-414 không được dùng làm chứng cứ. Phạm vi là non-code Markdown. Parent đã báo graph không có index cho các đường dẫn tài liệu; thế hệ index/coverage không xác minh được. Tôi không khẳng định đã kiểm codegraph, symbols, caller/callee hay runtime.

### Điều thiết kế đã làm đúng, không nên phá chỉ để “có finding”

Giữ rõ ba loại FACT/POLICY/AUTHORITY và TECHNICAL riêng, không biến lỗi provider thành business escalation: docs/final/ARCHITECTURE_AND_EVALUATION.md:235-245. Không cho học từ nút đồng ý, im lặng hay nhãn chưa xác minh; giữ guard tiền/nguồn/quyền bất biến: cùng tài liệu:247-267. Có phát biểu cần đối chứng độc lập, holdout không dùng để tinh chỉnh, gold trước output, literal oracle ngoài Reconciler, false-pass/false-fail của LLM judge, lỗi kỹ thuật nằm trong denominator: cùng tài liệu:269-286,316-343. Đây là những lựa chọn hợp lý. Vấn đề bên dưới chủ yếu là **cách chứng minh chúng đúng**, không phải tác giả hoàn toàn bỏ qua các nguyên tắc đó.

**Ưu tiên:** P1 = phải làm rõ hợp đồng trước khi chuyển thành acceptance/claim; P2 = builder có thể cụ thể hóa trong plan nhưng cần test chứng minh; P3 = cải tiến tùy chọn. “P1” không có nghĩa hiện đã có lỗi runtime; hiện chưa có runtime để kết luận.

## 1. Findings

### EV-01 — [P1] Adaptive threshold chưa có đại lượng nhân quả được xác định

**Nguồn.** Đề A Sprint 2 đòi *tự động điều chỉnh ngưỡng chuyển tiếp dựa trên phản hồi người dùng*: docs/Challenge_Brief_OrganizationAI_VN.docx.md:61-67. Thiết kế chốt học ngưỡng giữa “thử thêm một recovery hợp lệ” và “hỏi người ngay”, không đổi money/rights/quality guard, yêu cầu chứng minh routing thay đổi: docs/final/ARCHITECTURE_AND_EVALUATION.md:186-196,247-262,380-388.

**Cơ chế thiếu.** Gọi thêm một lượt OCR/LLM, thay đổi số request, hay đổi giá trị threshold không tự chứng minh **ngưỡng chuyển tiếp tốt hơn**. Phải định nghĩa unit can thiệp là **cơ hội quyết định recovery-vs-human tại một issue với snapshot chứng cứ ban đầu cố định**. Hai hành động có thể so được là R = thử đúng một bước recovery cho phép, H = lập câu hỏi đúng người ngay. Kết quả cần đo là khả năng **tự hoàn thành đúng và an toàn**, số lần cần con người, chi phí và độ trễ. Không được suy “tự chủ tốt hơn” từ số calls.

**Counterexample.** Hồ sơ công tác đủ ngân sách/quyền và lịch sử, nhưng hóa đơn scan không đọc được số. Có **ảnh phụ rõ nét** trong cùng hồ sơ. Với R, hệ thống đọc ảnh phụ, có nguồn và đối chiếu được 450.000đ, không cần hỏi; với H, nhân viên phải trả lời FACT. Một threshold học được chỉ có ích nếu tăng lựa chọn R cho loại cơ hội như vậy và vẫn hỏi ngay khi không có nguồn bổ sung. Nếu chỉ tăng OCR từ 1 lên 2 nhưng cả hai đều hỏi người, chưa có lợi ích về escalation. Nếu OCR trả 450.000đ thiếu support mà vẫn chốt, đó là **vi phạm guard**, không phải thành công adaptation.

**Tác động.** Có nguy cơ demo “ngưỡng đã cập nhật” nhưng không đạt ý nghĩa nghiệp vụ của yêu cầu Sprint 2. Rủi ro cạnh tranh cao vì phần A được kiểm trực tiếp trên case mới: đề gốc:69-83.

**Sửa nhỏ nhất.** Định nghĩa trước khi coding: feature vector X quan sát **trước** quyết định, action R/H, định nghĩa “recovery có ích” (giảm human intervention nhờ nguồn thực sự hỗ trợ mà không sai guard), outcome thất bại và phí. Log **giá trị score, threshold, lựa chọn, nguồn bổ sung, outcome, lý do** theo version. So candidate với fixed baseline ở cùng snapshot trước khi nói improved.

**Acceptance.** Một tập cơ hội có ít nhất một case “R đúng làm đổi FACT→routine” và một case “R vô ích, H thích hợp”; replay cả baseline/candidate; xuất bảng transition H→R, R→H, kết quả cuối, nguồn chứng minh, calls, latency. Không ghi “adaptive escalation proved” nếu chỉ số calls/giá trị threshold đổi.

**Phản biện biện pháp sửa.** Không cần huấn luyện classifier hoặc bandit để làm việc này; rubric và trace ở mức issue là đủ. Không thể khẳng định BTC chắc chắn coi ngưỡng recovery là đúng ý “ngưỡng chuyển tiếp”; đây là **cách giải thích có thể bảo vệ** dựa trên tác động thực sự đến quyết định hỏi người, không phải xác nhận từ BTC.

### EV-02 — [P1] Feedback của nhánh đã chọn không cho biết outcome của nhánh bị bỏ qua

**Nguồn.** Thiết kế đề xuất feature text presence/representation/alternative source/budget, feedback có xác minh và cập nhật theo đợt: docs/final/ARCHITECTURE_AND_EVALUATION.md:247-262. Yêu cầu cuộc thi đo tỷ lệ bỏ sót chuyển tiếp và chuyển thừa trên independent test: docs/Challenge_Brief_OrganizationAI_VN.docx.md:63-66.

**Cơ chế lỗi đo lường.** Nếu threshold cũ luôn hỏi người khi OCR yếu, ta thấy nhãn “human xác nhận số tiền” nhưng **không biết recovery đã có thể đọc đúng hay không**. Nếu threshold cũ luôn thử recovery trên tài liệu có text, ta chỉ quan sát recovery của những case dễ; lấy tỷ lệ thành công này để ước lượng cho toàn bộ các case là **selection bias**. Phản hồi “hỏi thừa” chỉ là nhãn về trải nghiệm/hành vi nhìn thấy, không tự là ground truth về kết quả recovery giả định.

**Counterexample số.** 20 issue: 10 scan rõ được thử R và thành công 9; 10 scan tối không có text bị đưa H ngay. Tỷ lệ 9/10 trên nhóm đã thử không chứng minh R thành công 90% trên 20 issue. Nếu tăng threshold để thử cả nhóm scan tối, rất có thể 10 lần tốn phí mà không giải quyết thêm. Chiều ngược lại cũng có thể xảy ra nếu 10 scan tối có ảnh phụ rõ nhưng chính sách cũ không thử.

**Tác động.** Ngưỡng có thể học theo policy cũ thay vì học lợi ích recovery, làm tăng escalation sai hoặc tăng chi phí mà không giảm workload.

**Sửa nhỏ nhất.** Dùng **paired offline evaluation** trên các packet đã được xác minh: cùng trạng thái trước decision, chạy một nhánh H và một nhánh R trong môi trường test, đối chiếu cùng independent gold; không cần A/B trực tiếp trên hồ sơ tiền thật. Khi R dùng provider có ngẫu nhiên, ghi model/prompt/seed nếu hỗ trợ và trạng thái replay/LIVE; nếu không khống chế được thì báo phân tán trên các lần lặp, không giả kết quả hoàn toàn xác định. Chỉ dùng production feedback làm nhãn trực tiếp của hành vi thực quan sát; **không điền nhãn giả** cho action chưa thử. Tách lợi ích offline trên synthetic và lợi ích thực tế đã quan sát.

**Acceptance.** Bảng mỗi candidate gồm số eligible opportunities, số cơ hội có outcome quan sát mỗi nhánh, paired gain có nguồn, số chưa định danh vì thiếu phản thực tế, và trade-off calls/time. Hai nhánh cùng policy, model, budget, initial facts. Khi chỉ có logs một nhánh, hệ thống phải nói **“chưa định danh được lợi ích đối với nhánh kia”**.

**Phản biện.** Paired runs tốn calls hơn và chỉ chứng minh ở dữ liệu replay. Nhưng chi phí thấp hơn thử nghiệm trực tiếp có nguy cơ với tiền; có thể dùng synthetic packet đã có gold. Không nên đòi causal attribution chắc chắn ở pilot người thật n=3.

### EV-03 — [P1] “Verified feedback” chưa có protocol xác minh và phân biệt assisted/unassisted

**Nguồn.** Thiết kế phân biệt correction/exception/đánh giá agent, không dùng acceptance im lặng làm nhãn: docs/final/ARCHITECTURE_AND_EVALUATION.md:253-267. Input draft đã được nhân viên sửa trước nộp và sau escalation mới có người trả lời: cùng tài liệu:125-138. Đề đòi phản hồi người dùng và thay đổi sản phẩm thực tế: docs/Challenge_Brief_OrganizationAI_VN.docx.md:65-67,201,257-260.

**Cơ chế.** Nhãn “đúng/sai” của người xử lý dễ lẫn ít nhất bốn việc: model trích xuất đúng raw; con người **bổ sung một fact vốn không hiện trong raw**; manager **cho phép ngoại lệ**; hoặc kế toán xác nhận lịch sử. Cả ba trường hợp sau tạo kết quả cuối đúng nhờ **can thiệp**, không chứng minh initial autonomous routing đúng. Routine không bị hỏi thường **không nhận feedback** nên không thể suy recall/safety từ feedback của escalated cases.

**Counterexample.** Model đọc hóa đơn 480.000đ trong ảnh mờ; nhân viên sửa thành 450.000đ. Sau đó manager cho vượt B; kết quả S cuối đúng. Nếu gán nhãn “recovery success” hoặc “model correctness” từ quyết toán cuối đã được duyệt, hệ thống sẽ học tăng tự động hóa trên chính phân khúc nhiều lỗi.

**Sửa nhỏ nhất.** Tạo schema label: feedback_origin (synthetic/internal/professional); issue/source/initial_revision/decision_version; người gắn nhãn/căn cứ; observed_action; raw-evidence-sufficient?; recovered_from_existing_source?; human_supplied_new_fact?; exception_granted?; final_correct?; question_needed?; label_verification_status và verifier. **Đóng băng initial unassisted verdict**, lưu assisted final outcome riêng. Với routine, chọn mẫu audit bởi người có trách nhiệm để phát hiện silent false-pass, ghi tỷ lệ được audit; không diễn giải mẫu này là ngẫu nhiên nếu chọn vì nghi vấn.

**Acceptance.** Test ít nhất ba feedback: sửa OCR, cung cấp chứng từ mới, cấp ngoại lệ. Chỉ case có đủ chứng cứ cho “recovery đọc được từ nguồn vốn có” mới thành nhãn calibration tương ứng. Không đổi threshold từ nhãn chưa verified, accepted-click, manager grant, hay correction không truy được nguồn. Report audit coverage của routine và escalated riêng.

**Phản biện.** Không cần hai người xác minh mọi nhãn; với pilot có thể một owner được chỉ định xác minh + một reviewer độc lập cho các case nguy hiểm/ngoại lệ. Thêm nhiều trường cho mọi thao tác người dùng sẽ gây mệt mỏi: phần audit label có thể làm offline trên trace, không bắt nhân viên điền form nghiên cứu.

### EV-04 — [P1] Gate activation/validation còn quá định tính để chứng minh cập nhật an toàn

**Nguồn.** Thiết kế nêu batch update, validation riêng, không tăng dangerous misses/false escalations, lưu rollback; N tối thiểu và công thức để builder chọn: docs/final/ARCHITECTURE_AND_EVALUATION.md:257-262,335-343. Holdout 20 được giữ cuối và không chỉnh theo đó: cùng tài liệu:273-275,316-320. Ngưỡng 8/4/20 triệu và rulebook là fixed decisions: cùng tài liệu:44-61.

**Cơ chế.** “Không tăng” trên mẫu ít case có thể là **không quan sát được lỗi**, không là bằng chứng không có lỗi. Dùng cùng dữ liệu vừa chọn threshold vừa phê duyệt threshold là optimistic. Kích hoạt tự động sau 2 feedback chẳng hạn có thể lật hàng loạt routing; ngược lại, thiết kế rất thận trọng nhưng không bao giờ kích hoạt thì chỉ chứng minh khả năng cập nhật theo lý thuyết, chưa thỏa được diễn đạt Sprint 2.

**Counterexample.** Threshold cũ và mới đều đạt 5/5 validation, candidate tiết kiệm một lượt OCR. Nhưng 5 case toàn PDF text rõ, trong khi vùng thay đổi threshold chủ yếu scan thiếu text; validation **không chứa điểm ngưỡng thực sự đổi action**. Báo “validated adaptation” là false pass. Một ví dụ khác: candidate tối ưu từ 15 development và sau khi 0/10 human-miss trên holdout, tác giả tăng threshold lần nữa theo kết quả holdout; tập này không còn independent.

**Sửa nhỏ nhất.** Viết một **activation contract tiền đăng ký**, versioned:

1. Tập đủ eligibility: chỉ issue FACT/quality nơi có recovery action hợp lệ và cơ hội có observable features; không tối ưu nhãn POLICY/AUTHORITY.
2. Có threshold fixed baseline, candidate được chọn **chỉ** trên verified-feedback development; mỗi candidate ghi support theo document family, feature bucket, nhóm recovered/irrecoverable.
3. Validation riêng, **không dùng chọn candidate**, phải chứa case ở cả hai phía/ngay gần ngưỡng và **ít nhất một decision thực sự đổi**. Ưu tiên paired result ở EV-02.
4. Gates theo thứ tự: zero critical false-pass trên validation; evidence/rights invariants; so sánh number of correct unassisted completions và unnecessary human questions; sau đó calls/latency/usage. Không lấy tiết kiệm phí bù cho lỗi tiền/quyền.
5. Chốt N_min, bucket đủ support và margin cải thiện trước khi nhìn validation; N_min phải dựa trên rủi ro/khả năng thu thập, công bố rõ đó là **ngưỡng kỹ thuật pilot**, không bảo đảm thống kê. Nếu thiếu support → giữ fixed, log lý do, **không claim đã chứng minh adaptation Sprint 2**.
6. Candidate/version/feedback IDs/selection data/validation IDs/activation time/rollback trigger được lưu; sau activate theo dõi đúng outcome với denominator mọi eligible opportunity, rollback khi guard vi phạm.

**Acceptance.** Một test tích cực có eligible feedback + validation độc lập khiến ngưỡng đổi routing đúng; ba test âm: thiếu N; không có decision flip; có dangerous error → phải không activate. Test holdout accessed-to-tune → invalidates independent claim và yêu cầu tập mới.

**Phản biện.** Ép con số N_min=30 hay 100 mà không có power analysis/bối cảnh là tùy tiện. Không khuyến nghị xây causal bandit hay retraining LLM. Bài toán đang là chọn **một tham số rất hẹp**; chỉ cần threshold rule, discrete buckets, paired experiments và gate cứng. Trade-off thật: có thể **không đủ feedback kịp để bật adaptation**; đó là kết quả trung thực cần đưa vào quyết định ưu tiên Sprint 2, không “lách” bằng dữ liệu giả.

### EV-05 — [P1] Định nghĩa “missed escalation” có thể cho qua khẳng định nguy hiểm không phát hành instruction

**Nguồn.** Metric hiện tại: “Miss = human-required được tự phát hành action / tổng human-required”: docs/final/ARCHITECTURE_AND_EVALUATION.md:322-333. Hệ thống có nhánh S=0 **kết luận cân bằng, không tạo yêu cầu số 0** và chỉ số 0 đã được chứng minh mới vào phép tính: cùng tài liệu:96-106,129-144. Đề cấm khẳng định khi input nghi vấn: docs/Challenge_Brief_OrganizationAI_VN.docx.md:51-57,197-203.

**Cơ chế.** Nếu gold yêu cầu FACT nhưng app công bố **“đã cân bằng, S=0”** dù lịch sử ứng chưa phủ mà không tạo payment instruction, numerator miss theo công thức trên bằng 0. Kết luận sai vẫn có thể chặn người xử lý và gây thiệt hại; đây là dangerous false-pass. Cùng lỗi xảy ra khi app ghi routine eligible nhưng pending event chưa xác minh. Metric hiện tại đúng cho **unsafe monetary instructions**, chưa đủ cho **unsafe affirmative conclusions**.

**Counterexample số.** Hóa đơn E=2.000.000đ, hồ sơ có giao dịch ứng A=2.000.000đ nhưng thiếu lịch sử P/R hoặc proof nhận tiền. App tự chốt “S=0; cân bằng” dù gold yêu cầu kế toán xác nhận coverage. Không có instruction; theo metric miss nguyên văn = 0. Hoặc ứng trước kỳ có tồn đầu kỳ chưa đưa vào scope: cùng kiểu false-known.

**Sửa nhỏ nhất.** Giữ metric đang có nhưng đổi tên **unsafe_action_miss**. Thêm **unsafe_conclusion_miss** = số human-required đã phát hành kết luận khẳng định cuối cùng khi căn cứ trọng yếu chưa đủ / tổng human-required; **any_dangerous_miss** = union hai loại, đếm mỗi dossier một lần và vẫn ghi cả issue-level errors. Phân biệt “safe reject/ask”, “correct auto-complete”, “wrong affirmative”, “technical failure”, “unresolved without actionable question” và “assisted resolution”. Đừng lấy failure kỹ thuật làm true positive escalation hoặc loại khỏi denominator tổng.

**Acceptance.** Injection fixture có thiếu coverage + S tưởng bằng 0 phải fail nếu app chốt cân bằng; pass khi FACT xuất đúng người, không có final affirmative. Test routine không technical fail để không tăng tỷ lệ “chuyển thừa” giả; technical fail luôn trừ completion tổng, tách chỉ số availability/timeout.

**Phản biện.** Nhiều metric có thể gây rối; báo cùng một confusion ledger ở mức dossier và chiếu ra 4–6 con số chính, không cần hàng chục score khó đọc. Các trạng thái không nhất thiết loại trừ nhau (technical fail sau một câu hỏi đúng), nên ghi outcome timeline và quy tắc counting cụ thể.

### EV-06 — [P1] Ground truth cần tách “thực tế mô phỏng” khỏi “có thể khẳng định từ raw input”

**Nguồn.** Thiết kế đã đòi raw source, fact/locator/quality, relations, history coverage, oracle độc lập và nguồn hỗ trợ claim: docs/final/ARCHITECTURE_AND_EVALUATION.md:100-112,181-184,281-286,316-328. Đề cho phép synthetic nhưng phải phân biệt rõ, đồng thời đánh giá dữ liệu mới: docs/Challenge_Brief_OrganizationAI_VN.docx.md:35-39.

**Cơ chế.** Một case synthetic có thể có “sự thật” do tác giả seed (số tiền là 450.000đ) nhưng ảnh thực tế mờ 450/480. Model đoán trúng 450 không đồng nghĩa được quyền kết luận. Nếu gold chỉ có true amount và expected S, grading sẽ **thưởng cho may mắn** và phạt chuyển FACT đúng. Tương tự, hóa đơn ghi người mua không chứng minh payer/received; equality của OCR fields không chứng minh quan hệ giữa giao dịch, nhân viên và hoạt động.

**Counterexample.** Raw có hóa đơn 1.200.000đ tên nhân viên, sao kê công ty cũng có chuyển khoản 1.200.000đ cùng ngày nhưng **không có reference nối giao dịch với hóa đơn đó**. True synthetic ledger biết đây là giao dịch khác. App nối theo amount/date sẽ cho sai E/C/S. Ngay cả khi số tính trùng hợp bằng gold ở một case, relation vẫn sai và có nguy cơ duplicate ở case kế tiếp.

**Sửa nhỏ nhất.** Một gold packet có **ba lớp độc lập**: (a) latent business truth do scenario designer seed; (b) raw-evidence-observable facts và supported/unsupported relations theo locator, bao gồm missing/conflict/quality và coverage; (c) **allowed behavior** theo policy/grants tại từng revision, gồm required issue set, owner, no-action/decision/remaining. Gold đóng băng trước khi chạy engine; reviewer kiểm một số critical cases bằng phép tính hoặc bảng ledger riêng không dùng Reconciler. Ghi provenance cho các số T/E/A/P/R/S và loại “unknown because evidence insufficient”.

**Acceptance.** Mutate raw để làm mờ số trong khi giữ latent amount → allowed behavior đổi sang FACT dù true amount không đổi. Xóa transaction link/coverage → FACT, không tự nối bằng equality. Đổi payer thành company-direct → không hoàn lại C cho nhân viên. Khôi phục source/relation proof đúng → có thể routine nếu các gate khác đủ. Scorer kiểm trực tiếp nguồn support, không chỉ existence của ref.

**Phản biện.** Gold ba lớp tốn công hơn một CSV label, nhưng chỉ áp dụng đầy đủ cho 15/20 packet và vài metamorphic variants. Không cần một ontology hay annotation platform phức tạp. Trường hợp nguồn cố tình mờ có thể dùng human adjudication 2 người cho tranh chấp; solo builder cần công bố ai đóng vai gold author và hạn chế tính độc lập, không giả có tổ chức xác minh bên ngoài.

### EV-07 — [P1] Chất lượng câu hỏi chưa được biến thành phép đo theo đúng tình huống giám khảo

**Nguồn.** BTC cho 6/20 điểm đề A cho câu hỏi cụ thể, **có thể quyết định ngay trong một câu trả lời mà không cần tra cứu lại hồ sơ gốc**: docs/Challenge_Brief_OrganizationAI_VN.docx.md:75-83. Thiết kế nói câu hỏi gồm facts/refs/owner/ảnh hưởng, LLM judge bổ trợ sau hiệu chuẩn: docs/final/ARCHITECTURE_AND_EVALUATION.md:129-138,235-245,281-286,322-329.

**Cơ chế.** Dùng kiểm tra keyword hoặc model judge “câu hỏi cụ thể” dễ false pass khi thiếu chứng cứ hiển thị, sai người có quyền, hoặc hỏi chung trong khi có hai vấn đề riêng. Việc question text khớp expected strings không chứng minh người có trách nhiệm **trả lời được trong một lượt**.

**Counterexample.** “Hóa đơn này 450.000 hay 480.000đ? Vui lòng xác nhận” nghe cụ thể nhưng UI không hiển thị crop/nguồn, không cho biết hóa đơn nào trong sáu hóa đơn; người dùng phải mở toàn bộ hồ sơ. “Bạn có phê duyệt không?” với khoản vượt B nhưng không nêu số vượt, rule, giới hạn grant, nguồn là sai rubric. Một issue đồng thời FACT và AUTHORITY còn có thể bị gửi manager duyệt trên số tiền chưa xác định.

**Sửa nhỏ nhất.** Bảng rubric có ít nhất: (1) đúng FACT/POLICY/AUTHORITY và đúng owner/scope; (2) nêu đối tượng, giá trị/điểm mâu thuẫn, rule và ảnh hưởng; (3) source excerpt/crop/locator **hiển thị trong câu hỏi** và support nội dung; (4) yêu cầu một quyết định/dữ kiện có thể trả lời trong một lượt; (5) nếu phụ thuộc, không hỏi approval số chưa rõ; (6) không tạo câu hỏi thừa trên routine. Test với người đóng vai actor **chỉ thấy question card**, đo có trả lời được mà không mở dossier (đúng rubric BTC); cho phép liên hệ/chứng từ mới khi đó là thông tin thật sự chưa có, nhưng câu hỏi phải nói chính xác cần xác minh cái gì.

**Acceptance.** Trong Escalation5 có hai issue khác nhóm (ít nhất FACT và một POLICY/AUTHORITY khi đủ facts) cùng context card; judge thủ công/rubric literal xác nhận owner, source, one-reply, answer path. Case thiếu crop/nhầm owner/ghi “xem xét lại” phải fail dù model judge cho điểm cao. LLM judge được dùng làm kiểm phụ sau khi hiệu chuẩn trên các false-pass/false-fail cố ý.

**Phản biện.** Không nên ép exact string hoặc “chỉ một câu văn”; có thể một card hiển thị nhiều dữ kiện và một câu hỏi chính. Chỉ 2 human trong Escalation5 không chứng minh đủ cả 3 nhóm; cần thêm development/holdout rubric cases, không yêu cầu làm demo5 thành 6.

### EV-08 — [P1] Holdout 20 balanced là kiểm tra lỗi có ích, không đủ cho kết luận độ tin cậy rộng

**Nguồn.** Quyết định 20 case độc lập 10 routine/10 human, 0/10 misses và 0/10 unnecessary escalation mục tiêu; thiết kế cũng thừa nhận giới hạn: docs/final/ARCHITECTURE_AND_EVALUATION.md:273-275,316-320,335-343. Đề đòi tỷ lệ theo independent set và sẽ tự ra **5 case mới**, khoảng 2 cần human: docs/Challenge_Brief_OrganizationAI_VN.docx.md:63-81.

**Cơ chế.** Hai tỷ lệ 0/10 dễ gợi “100% an toàn” khi hỗ trợ rất yếu. Nếu giả sử mỗi case là phép thử độc lập cùng phân phối, 0 lỗi/10 vẫn có **upper bound một phía 95% khoảng 25,9%** cho xác suất lỗi thật (vì (1-p)^10 = 0,05). Với 0/20 cũng khoảng **13,9%**. Trên dữ liệu synthetic chọn chủ đích, giả định độc lập/cùng phân phối còn yếu hơn. Balanced 10/10 cố ý thay đổi prevalence so với hồ sơ thật; không được dùng tỷ lệ balanced để suy workload hay tần suất escalation production.

**Counterexample.** Holdout 10 human có 8 FACT missing proof, 1 POLICY, 1 AUTHORITY; đạt 10/10 không kiểm tốt AUTHORITY grant hết hạn/sai scope/đồng thời POLICY. Hoặc 10 routine cùng một issuer/layout, pass cả 10 nhưng lỗi ở ảnh chụp dọc, document khác issuer.

**Sửa nhỏ nhất.** Pre-register **strata/matrix** cho 20 packet trước khi freeze: loại routine/human, loại issue FACT/POLICY/AUTHORITY và co-occurrence, travel activity, source format/quality, provider/non-doc technical state ở tập riêng, money direction, boundary E/S/B/grant, missing history, relation và duplicate. Chốt grouping theo **activity, economic obligation, source family/layout/issuer** để ngăn cùng hóa đơn thay số nằm giữa development và holdout. Cấu trúc 10/10 giữ nguyên; báo **count/denominator/confidence bound nếu có điều kiện**, không tuyên bố đã đo rủi ro toàn doanh nghiệp. Chạy judge-new-input như challenge bất biến của sau freeze.

**Acceptance.** Manifest có family/group_id, split, digest và expected trước run; contamination test với một invoice clone giữa splits phải fail inventory. Báo cả confusion count lẫn critical-miss subtypes, cùng số lượng mỗi stratum. Nếu xem kết quả holdout và sửa prompt/threshold/model, đánh dấu nó đã dùng để phát triển và tạo holdout mới.

**Phản biện.** Không nên ép 20 case che phủ mọi tổ hợp; số tổ hợp tăng rất nhanh. Chọn pairwise/high-risk boundaries có lý do, và dùng technical/metamorphic suite riêng. Không thể dùng CI trên 10 case có chủ đích để có kết luận xác suất production đáng tin; con số minh họa chỉ chỉ ra vì sao claim tổng quát không hợp lệ.

### EV-09 — [P1] Inventory “15” hiện là kế hoạch, chưa là development set đủ điều kiện

**Nguồn.** Đề A cần **ít nhất 15 trường hợp kiểm thử** gồm ambiguity/out-of-policy/over-authority: docs/Challenge_Brief_OrganizationAI_VN.docx.md:45-59. Tài liệu thiết kế liệt kê D01–D15 nhưng nói rõ chưa tạo packet; tiếp khách địa phương là profile sau gate; hồ sơ thực nhận trước vẫn phải có >=15: docs/final/ARCHITECTURE_AND_EVALUATION.md:19-22,269-280,293-320.

**Quan sát cụ thể.** D05/D07/D08 ở docs/final/ARCHITECTURE_AND_EVALUATION.md:300,302-303 thuộc tiếp khách địa phương (profile sau gate). Trong D01–D15, **chỉ còn nhiều nhất 12 ID** để có thể cấu thành bộ công tác trước gate, trước cả khi kiểm D09 (procurement/refund ngoài scope) và D13 (scenario nhiều dossier) có được định nghĩa làm raw dossier/case hợp lệ như yêu cầu không. D11/D15 ghi “variant” nhưng **variant/ảnh clone không tự là hồ sơ độc lập** theo chính docs:306,310,312-314. 15 dòng inventory không bằng 15 packet raw độc lập của profile được nhận.

**Cơ chế/tác động.** Builder có thể lấy việc “bảng có 15 dòng” làm acceptance và bỏ qua việc profile travel đầu tiên thiếu ca đủ rộng; khi đó chưa có bằng chứng tối thiểu trên workflow đang claim hỗ trợ. Đây là **lỗ hổng kế hoạch**, không phải tác giả đã tuyên bố test pass; tài liệu có cảnh báo nhưng thiếu checklist lấp chỗ trống.

**Sửa nhỏ nhất.** Trước khi chạy dev eval, bổ sung **>=15 raw, distinct travel dossiers**, mỗi packet có source thật dưới dạng file mẫu/synthetic có disclosure, context/grants/history, gold, expected trace/owner. Ưu tiên thêm ba family rủi ro khác biệt như (a) E=8m/S=4m boundary và vượt 1đ; (b) false-zero history với opening balance; (c) claim bị mâu thuẫn bởi payer/duplicate cross dossier. D05/07/08 giữ lại thành test riêng của profile local meeting **sau gate**, không tính làm bằng chứng travel nếu chưa chuyển scenario và gold thật.

**Acceptance.** Script inventory đếm distinct root obligations, family và raw packet IDs trong travel; loại clone/variant ra khỏi số unique; có ít nhất FACT/POLICY/AUTHORITY, routine CHI/THU/CÂN BẰNG và các critical guards. Kiểm raw PDFs/images có thể được nạp bởi cùng pipeline. Không nói “15 tests passed” nếu chỉ có 15 bảng mô tả.

**Phản biện.** BTC yêu cầu 15 cases tổng thể, không nói riêng 15 travel; yêu cầu “>=15 profile đầu” là **contract nội bộ đã chốt** ở docs:312-314. Nếu muốn bỏ yêu cầu nội bộ để ưu tiên thời hạn, đó là **đổi quyết định** phải hỏi user, không phải reviewer tự thay yêu cầu BTC.

### EV-10 — [P1] Metric về route/owner cần đơn vị và quy tắc cho hồ sơ nhiều issue, technical failure, human assistance

**Nguồn.** Một hồ sơ có thể cùng lúc FACT/POLICY/AUTHORITY; issue phụ thuộc phải xử lý theo thứ tự, issue độc lập có thể hỏi song song: docs/final/ARCHITECTURE_AND_EVALUATION.md:59-61,129-138. Metric hiện nêu miss, chuyển thừa, group/owner/question, auto completion, technical failures: cùng tài liệu:322-333. Đề bắt 3 nhóm và xử lý hết routine: docs/Challenge_Brief_OrganizationAI_VN.docx.md:47-59.

**Cơ chế.** Chấm nhãn duy nhất cho một dossier có cả thiếu payer (FACT) và E vượt 8m (AUTHORITY) sẽ đánh sai một thứ tự xử lý hợp lý. “Chuyển thừa” ở routine dễ bị nhầm với câu hỏi nhân viên phải điền/sửa **trước khi xác nhận nộp**, hoặc recovery thử thất bại có thật; ngược lại, technical failure sau provider có thể được giữ trong completion denominator nhưng vẫn không xuất hiện đủ rõ ở **escalation coverage**. “3/3 routine hoàn toàn tự động” cần định nghĩa điểm bắt đầu và kết thúc.

**Counterexample.** E có thể là 7m hoặc 9m do scan mờ, A=4m; chưa thể xác định E<=8m hay không, nên trước tiên FACT. Sau khi người xác minh E=9m, AUTHORITY mới xác định. Một scorer chỉ đòi AUTHORITY ngay initial turn sẽ phạt hành vi đúng. Nếu case bị timeout và app không ra action/human question, metric unsafe_action=0/1 có thể trông tốt nhưng nhiệm vụ hoàn toàn thất bại.

**Sửa nhỏ nhất.** Định nghĩa ba đơn vị cố định: **dossier** (được cấp/sai kết luận, auto completion), **issue-stage** (required category/owner/question ở revision cụ thể) và **recovery opportunity** (EV-01). Gold issue là **set có dependency và allowed transition**; không ép chính xác một thứ tự giữa các issue độc lập. Báo outcome tại initial submission (unassisted) và sau human answers (assisted); completion denominator tính tất cả submitted packets kể cả technical fail. Tách draft-correction trước nộp khỏi business escalation, nhưng đo effort draft riêng.

**Acceptance.** Một case FACT→AUTHORITY, một case POLICY+FACT độc lập, một case TECHNICAL sau OCR timeout, một routine bị lỗi trích xuất rồi phải hỏi người và một routine đúng không cần human. Report đúng số issue, route qua stage, dossier unsafe, assisted/unassisted, technical failure; không biến TECHNICAL thành một trong 3 nhãn business.

**Phản biện.** Không cần cả state-machine evaluator thứ hai; ledger expected transitions có thể là danh sách trạng thái/sự kiện cho vài complex cases, literal oracle cho phần còn lại. Chỉ áp metric nào có denominator thật sự quan sát được; N=0 → NA.

### EV-11 — [P1] Chưa có protocol người thật/before-after đủ để phân biệt giảm việc với dồn việc sang chỗ khác

**Nguồn.** Brief nói rõ tăng tốc độ không đủ, phải xét thời gian làm quen, cường độ làm việc, nhận thức và tương tác phối hợp: docs/Challenge_Brief_OrganizationAI_VN.docx.md:17-21. Đề A yêu cầu >=3 người trực tiếp xử lý, cải tiến phát sinh từ feedback: cùng đề:63-67,197-202,257-260. Slide 3 đo impact và Slide 5 nêu limits: cùng đề:179-187. Tài liệu thiết kế liệt kê trials, before/after, origin và chưa có feedback: docs/final/ARCHITECTURE_AND_EVALUATION.md:264-267,279,342-343,380-396.

**Cơ chế.** Không định nghĩa **đơn vị công việc, start/end và điều kiện so sánh** sẽ dẫn đến “AI xử lý 15 giây, kế toán xử lý 8 phút” khi 15 giây chỉ tính request inference, còn 8 phút gồm tìm chứng từ, đợi nhân viên, đối chiếu ngân hàng, gọi manager, sửa sai và học công cụ. Với 3 người và hồ sơ khác độ khó, before/after không chứng minh tác động nhân quả tổng quát; nhưng vẫn đủ ghi nhận feedback thực tế có phương pháp.

**Counterexample timeline.** Thủ công: 6 phút đọc + 3 phút đối chiếu + 2 phút liên hệ = 11 phút thời gian chủ động, 1 ngày chờ email. Dùng app: OCR 20 giây, nhân viên sửa bản nháp 4 phút, kế toán audit 6 phút, trả lời câu hỏi 4 phút và chờ 1 ngày. Nếu chỉ báo 20 giây, claim “nhanh gấp 33 lần” là gây hiểu lầm. Hoặc app tăng throughput 20 hồ sơ/ngày nhưng tạo 35 lần interrupt thay vì 10: gánh nặng mới cần nói ra.

**Sửa nhỏ nhất.** Một trial protocol có sự đồng ý rõ ràng, >=3 **nhân sự đúng vai trò nghề nghiệp**. Với từng người, dùng vài **cặp hồ sơ tương đồng** trong sandbox, cân bằng thứ tự A/B (manual/app) khi khả thi; nếu không cân bằng, ghi rõ limitation và không gọi causal proof. Cùng endpoint đo từ “nhận packet đầy đủ” đến “kết luận đủ căn cứ và tạo instruction/đặt vấn đề cụ thể”, tách **thực hiện chuyển tiền** ngoài app và thời gian chờ bên ngoài. Thu: elapsed time, hands-on time của mỗi actor, số câu hỏi, số lần tra hồ sơ, rework, lỗi được phát hiện/bỏ sót, thời gian làm quen, perceived workload (ví dụ câu hỏi thang ngắn), hành vi blindly accept/sửa AI, gián đoạn giao tiếp. Ghi raw anonymized timing/survey/quote với consent và một thay đổi có trước/sau.

**Acceptance.** >=3 người thật có chức danh, thông tin đồng thuận/chế độ ẩn danh, dữ liệu trial và trích dẫn họ xác nhận; bảng từng người/từng hồ sơ manual vs app (không gộp tổng che outcome xấu), origin data; ít nhất một bất cập cụ thể và một thay đổi có trace/commit hoặc ảnh/đối chiếu trước sau. Phân biệt **mô tả quan sát được** với **quan hệ nhân quả chưa kiểm soát**. Không dựng fictional professional users.

**Phản biện.** Đối chứng ngẫu nhiên quy mô lớn là không thực tế và không phải mandate. Trial ba người tự nguyện có carryover/learning effect; mục đích ở đây là trung thực, tái lập và tạo product improvement, chưa phải kết luận thay đổi hiệu suất toàn tổ chức.

### EV-12 — [P2] Verify cùng pipeline là cần, nhưng chưa định nghĩa thế nào là bằng chứng “LIVE” và độc lập

**Nguồn.** Brief yêu cầu Core4 một thao tác, Escalation5 3 routine+2 human và giám khảo tự nhập case mới: docs/Challenge_Brief_OrganizationAI_VN.docx.md:57-59,69-81,169-171,197-227. Thiết kế nói EvaluationRunner chung CaseWorkflow/Reconciler, context độc lập, raw expected scorer riêng, LIVE/replay rõ mode: docs/final/ARCHITECTURE_AND_EVALUATION.md:168-174,281-291,361-372.

**Cơ chế.** Dùng đúng Python functions nhưng cung cấp sẵn observations đã được người viết packet chép vào DB có thể bypass khó khăn thật của OCR/source/relation. Một “PASS” từ code expected oracle có thể chỉ chứng minh rule test chứ không chứng minh **new raw uploads**. Ngược lại, chạy 4/5 case thật nhiều OCR liên tiếp có thể vượt thời lượng giám khảo mà bản unit-test verify nhìn vẫn xanh.

**Counterexample.** Core4 dùng JSON facts thay vì receipt scan; mọi case pass 0,1 giây. Giám khảo upload JPEG xoay/mờ: extraction trả string không hợp schema rồi lỗi, UI không đưa câu hỏi. Core4 xanh mà tiêu chí dữ liệu mới/90 giây không qua.

**Sửa nhỏ nhất.** Mỗi public Verify packet cần manifest input **raw docs + context + initial state**, live app path upload→draft/submit→read→assess→persist→view; lưu original file digest, engine version, start/end timestamp, predicted/expected, reason, source links, mode “LIVE provider” hay “REPLAY recorded” hoặc “RULE-ONLY”. Replay có thể giúp tái lập ngoại tuyến nhưng không được quảng cáo là LIVE OCR/LLM result. Trong 4 và 5 case, chọn đủ loại nguồn để lộ lỗi pipeline; cô lập session/DB trừ scenario cross-dossier được chủ ý chia sẻ context. Không hardcode tên filename/ID làm branch.

**Acceptance.** Clean-start một nút chạy Core4 và Esc5 trong ngân sách giao diện được công bố; ghi p50/p95 khi có N, timeout và partial failure; thay 1 file nguồn cùng format phải đi qua ứng dụng và trả hành vi hợp lý không đọc expected; đối chiếu Verify run với UI/action DB. Có negative tests: mất API, malformed output, missing proof, non-document, stale data → không pass giả. Trình bày trung thực nếu thời gian 90 giây vượt hạn.

**Phản biện.** Không cần bắt 9 case luôn gọi model live trong mọi lần local developer test; replay/offline rule tests hợp lệ **nếu mode và conclusion scope được công khai**. Hội đồng chấm mới là nơi cần live/new-input evidence, không nên tăng API bill chỉ để screenshot xanh.

### EV-13 — [P2] M0/model comparison và usage/latency cần fair comparison, khả năng thất bại cũng là KPI

**Nguồn.** M0 kế hoạch baseline thật, dữ liệu text/scanned/ambiguous/non-document, compare ứng viên trên cùng dev, pin model/version: docs/final/ARCHITECTURE_AND_EVALUATION.md:191-196,345-359. Brief yêu cầu live, no signup, xử lý 2 đầu vào mới; vòng nhanh có 8 phút và riêng 90 giây đề A: docs/Challenge_Brief_OrganizationAI_VN.docx.md:37-39,69-73,197-223.

**Cơ chế.** So model A theo 10 file rõ với model B theo 8 file sống sót sau timeout là survivorship bias. Lấy median latency chỉ trên success bỏ qua critical failed calls gây ra retry, chi phí và timeouts. So prompt/temperature/budget không giống nhau khó quy lỗi đúng cho provider/model. LangSmith “green” không chứng minh nghiệp vụ; thiết kế đã nhận giới hạn này, nhưng cần phép đo làm acceptance.

**Counterexample.** OCR A đọc đúng 8/10, timeout 2; B đúng 7/10, timeout 0. Chỉ báo accuracy trên successful responses A=100%, B=70% sẽ che A còn 20% input không thể xử lý. Nếu A gọi 3 lần thay vì 1, so latency của 1 call thay vì end-to-end khiến lựa chọn sai.

**Sửa nhỏ nhất.** Pre-register cùng packet IDs, cùng policy/parser/recovery-budget, cùng case-level deadline và rubric; pinned concrete models/config. **Report n attempted, completed, schema-valid, evidence-supported, wrong-known, correct routes, technical-failed, retries, tokens/pages/usage available, total latency**. Cũng đo end-to-end từ upload đến action hoặc actionable question trên Core4/Esc5/new input. Missing usage = unknown chứ không phải 0; public-host cold start và reset session là điều kiện demo.

**Acceptance.** M0 có một run manifest hiển thị attempted/success/error counts của từng provider, model/config IDs, dataset version, p50/p95 kèm N, cost theo nguồn usage thực và pricing version nếu có, critical errors kèm raw ref. Một thử nghiệm provider unavailable vẫn xuất technical failure có cơ chế dừng/an toàn. Nếu chưa chạy, trình bày “unknown”, không ghi ước lượng là measured.

**Phản biện.** N nhỏ, so hai model chỉ mang tính lựa chọn kỹ thuật theo dataset demo; không suy supremacy ngoài miền. Không cần mua nhiều API hoặc chạy nhiều lần khi thiết kế chưa có app; M0 phải là *bước trước* claim/training lớn.

### EV-14 — [P2] Regression boundaries tiền/quyền cần chứng minh bằng mutation, không chỉ case kết quả đúng

**Nguồn.** Quyết định E<=8m, |S|<=4m, manager<=20m theo đúng scope; B tách riêng và tiền S=E−A−P+R; grant phải đúng actor/action/profile/time: docs/final/ARCHITECTURE_AND_EVALUATION.md:44-66,79-112. Release gate “không critical false-pass”: cùng tài liệu:335-340. Đề kiểm tra khả năng xử lý case mới chứ không chỉ case đã viết: docs/Challenge_Brief_OrganizationAI_VN.docx.md:37,71-83,197-199.

**Cơ chế.** Test một ví dụ D04 “E12, S1” phát hiện lỗi chỉ nhìn S mà quên E, nhưng không chứng minh implementation xử lý boundary bằng/trên, grant sai scope/time hoặc B độc lập. Số arithmetic đúng trong một dossier cũng không chứng minh payer/source/history đầy đủ.

**Counterexample.** E=8.000.000, S=4.000.000 được auto xử lý khi đủ B/quyền; đổi E thành **8.000.001** (S vẫn 4m do A đổi đồng thời) phải AUTHORITY. Đổi E giữ nguyên nhưng S thành **4.000.001** phải AUTHORITY. Có B=7.999.999 và T=8m phải POLICY dù E/S trong ngưỡng. Có manager grant 20m nhưng chỉ travel, đem dùng cho local meeting thì AUTHORITY. Với hồ sơ thiếu A/P/R coverage, S=0 không là routine.

**Sửa nhỏ nhất.** Matrix **metamorphic assertions** trên cùng packet: thay từng chiều E, S, B, grant scope/expiry, payer/recipient, source support và history coverage; so expected transitions và stable invariants. Không cộng clone vào số distinct 15/20. Giữ một tệp expected literal rule table độc lập với production Reconciler.

**Acceptance.** Cặp trên/bằng/dưới E và |S|, B<T, grant đúng/sai scope/expiry, false-zero, payment proof đảo payer, duplicate cross dossiers. Khi thay một biến trọng yếu, status/question/action thay đúng; các source/câu hỏi/audit refs còn liên kết đúng revision. Fail nếu output kết luận khẳng định dù marker trọng yếu bị loại.

**Phản biện.** Không sinh Cartesian product hàng nghìn case; chọn các mutation có nguy cơ làm sai thẩm quyền/tiền, pairwise và bất biến trực tiếp, tránh overengineering eval.

## 2. Đề xuất phương pháp nhỏ nhất có thể thực thi và kiểm chứng

Không đề xuất thêm LangGraph, training classifier, active-learning platform, bandit, causal inference library hay ngân hàng sandbox. Các quyết định ứng dụng Python workflow/FastAPI/Pydantic/SQLite/React, Mistral/xkiro, LangSmith + local audit được giữ nguyên: docs/final/ARCHITECTURE_AND_EVALUATION.md:163-196,345-353. Để biến mục 7–9 thành hợp đồng có thể code/review, chỉ cần **bốn artifact loại nhỏ**:

**A. Dataset packet + immutable manifest.** Mỗi scenario có raw file digests, scope và actor/grant, evidence/context/history, family/split, policy version, seeded truth tách observable evidence, gold expected issue/action/amounts/state. Test scorer chỉ đọc expected sau app. Frozen holdout có digest và không chạy dùng để chọn ngưỡng/model/prompt. Dùng một schema cho development, paired validation, holdout, Core4 và Esc5; khác nhau ở intended purpose/visibility.

**B. Issue-level routing ledger.** Khi app quyết định, lưu initial revision, eligible action(s), observable X trước lựa chọn, threshold/version/score, selected branch, extra source/actual recovery outcome, source quality/supported relations, guard outcome, final decision hay human question. Lấy từ local audit và trace đã đề xuất; không tạo pipeline scoring độc lập chứa business logic. Với human feedback bổ sung label_origin, verification và assisted status.

**C. Một paired threshold evaluator.** Trên eligible verified packet, chạy H và R từ snapshot giống nhau trong evaluation sandbox; tính per-item outcome. So với fixed baseline trước, chọn **một** candidate threshold (có thể threshold theo 1–2 feature buckets cố định), validation riêng. Feature phải có trước decision, không dùng “đã được human sửa” hay recovered value làm feature vì leakage. Quan sát tối thiểu:

| Đại lượng | Đơn vị và cách đo | Không được suy diễn |
| --- | --- | --- |
| Eligible | recovery opportunity có bước hợp lệ và budget trước khi chọn | Không dùng toàn bộ hồ sơ làm mẫu số lợi ích recovery |
| Correct auto after R | cơ hội R tạo source-supported final routine đúng; no critical guard failure | Human cung cấp fact mới không là auto |
| H-question necessary | cùng cơ hội nếu H chọn; question/owner cần theo gold tại thời điểm đó | “Hỏi người” không mặc định sai khi nguồn mờ thật |
| Changed routing | các cơ hội H↔R tạo khác biệt ở hỏi người hoặc kết luận cuối | Chỉ thay số calls không đủ |
| Dangerous wrong outcome | unsafe affirmation/action; report numerator cả 0 | Tối ưu cost không bù lỗi |
| Resource | extra calls/pages/tokens/cost/latency end-to-end, incl. failures | Không chỉ so latency successful attempts |
| Feedback support | verified opportunities theo family/bucket, independent validation count | Không suy counterfactual từ feedback của nhánh được chọn |

**D. Một report generator với ba bảng.** (1) correctness/safety/route + source/owner/question quality; (2) paired fixed-vs-candidate adaptation trên validation, support/gates/rollback; (3) professional trial manual/app và adverse effects. Verify là UI chạy cùng pipeline và dùng scorer này, không làm thêm judge “tự chấm chính mình”.

### Flow có thể kiểm

1. **Freeze contracts:** chuẩn hóa outcome units, gold 3 lớp, rubric question, source support và split rules; viết expected của các scenario nhỏ trước engine. Q1–Q30 không đổi.
2. **Làm tối thiểu 15 raw travel dossiers** cùng bất biến money/rights và error strata. Bổ sung technical suite, mutation riêng; khóa 20 holdout từ những family/obligations không giao nhau.
3. **M0 trên development:** một baseline model thực gọi được; ghi n-attempted, all errors, complete decisions, evidence, latency/usage. Candidate model nếu thật khả dụng thì chạy cùng protocol và chỉ chọn trên dev.
4. **Fixed baseline first:** xử lý cùng dev/validation packet qua upload→decision/question, giữ audit/dossier timeline. Escalation question được chấm rubric theo actor.
5. **Collect verified labels:** từ internal/professional user thật trên nguồn synthetic hoặc consented real, tách correction vs new proof vs exception vs agent mistake; có source/actor/time và audit routine sampled.
6. **Candidate threshold:** chọn chỉ trên development feedback, paired R/H, kiểm validation đã đóng băng, guard-then-benefit-then-resource; activate/rollback version nếu gate có thật. Nếu không, giữ fixed và báo thiếu bằng chứng adaptation.
7. **Final holdout một lần cho báo cáo cuối**, công bố raw counts/denominators, error strata và mọi lỗi. Sau khi sửa từ holdout, nó trở thành dev; cần tập độc lập mới.
8. **Public Verify + 2 new inputs + trial:** trải nghiệm không signup, mode rõ, đo thời gian trực tiếp; sau đó >=3 chuyên viên thật để xác định impact và một cải tiến bắt nguồn từ phản hồi. Đưa giới hạn và adverse effect lên slide/report.

Đây là thứ tự phụ thuộc logic, **không phải khẳng định khả thi trong thời gian còn lại**. Đề gốc ghi khóa bài ngày 15/10 và demo 17/10: docs/Challenge_Brief_OrganizationAI_VN.docx.md:231-245. Review ngày 13/10 không làm thay đổi lịch hay xác nhận gia hạn.

## 3. Bảng gate và bằng chứng cần yêu cầu builder giao

| Gate | Điều kiện tối thiểu kiểm được | Bằng chứng nộp kèm | Có thể claim |
| --- | --- | --- | --- |
| Eval contract | oracle độc lập; units/denoms; issue dependencies; question rubric; split manifest | Spec + ≥1 false-pass/false-fail của mỗi metric quan trọng | Đã định nghĩa phép đo, chưa đo hiệu suất |
| Dataset | >=15 raw travel distinct; 20 holdout frozen 10/10; technical suite độc lập; family split | Packet digest, provenance, independent gold, manifest | Bộ test được tạo; không thay runtime PASS |
| Correctness/safety | zero observed critical false-pass trong suite định nghĩa; số thực, nguồn, quyền, Stop/duplicates; correct Core4/Esc5 | case-by-case expected/actual, audit snapshots, raw refs, replay mode | Pass **trên suite/version được chạy**, không zero risk |
| Question quality | card trả lời được trong một lượt không tra lại dossier gốc; đúng owner/source/rule | rubric, blinded actor evaluation, false-pass probes | Chất lượng câu hỏi trên case được xem |
| Threshold update | verified feedback, paired R/H, fixed comparator, independent validation có flip, guard pass, rollback | label IDs, candidate/baseline tables, threshold/version, activation log | Tự điều chỉnh có bằng chứng **nếu kích hoạt thật**; nếu không thì chỉ mechanism |
| Holdout | chạy một lần sau lock; report unsafe/false-escalation/technical, confusion count và strata | frozen digest + raw results + N + CI caveat | Empirical 0/10 hay x/10 trong pilot; không suy khái quát |
| Model/M0 | attempted/completed/failed; model/config; source support; calls/usage/latency | event logs, provider errors, protocol, mode | So sánh có giới hạn trên input đã chạy |
| Public/Verify | clean clone/runbook, live URL no signup, Core4/Esc5, 2 unknown inputs, Stop/Override | URL, timestamped run, audit click-through, screen recording | Vận hành tại thời điểm kiểm nếu có kết quả thật |
| Professional trial | >=3 practitioners consented, before/after endpoint rõ, raw quotes, burden, one product change | anonymized timing/task sheets, signed/attributable quotes theo luật/đề, before-after/commit | Phản hồi/tác động quan sát ở pilot, không causal generalization |

## 4. Ranh giới quyết định: sửa contract, builder detail, hay hỏi user?

**Nên sửa ngay trong evaluation/acceptance contract (không mở lại Q1–Q30):** EV-01 đến EV-08, EV-10 và EV-11 ở phần định nghĩa observable, counterfactual, gold, units/denominators, question rubric, split, trial endpoints và activation gate. EV-09 cần checklist raw packets trong plan; không coi inventory = dataset. Đây là làm chính xác lựa chọn đã chốt và mandate đề gốc.

**Builder có quyền tự chọn trong ranh giới, nhưng phải công bố trước khi đo:** tên field/tables, câu lệnh scorer, schema trace, exact N_min/margin có lập luận, cách chọn 1–2 feature buckets, paired replay harness, p50/p95 protocol, exact M0 models/config/ceilings, layout card, hosting/TTL. Không được đổi quality guard vì thấy số validation xấu; không được dùng holdout để tune rồi vẫn gọi độc lập. Mỗi lựa chọn phải có fixture/test và ghi version.

**Nếu cần thay đổi quyết định đã chốt, phải hỏi user với trade-off rõ:** (a) bỏ hẳn adaptive-threshold demo hoặc chỉ cho thấy cơ chế chưa kích hoạt trong khi vẫn muốn claim Sprint 2; (b) mở rộng threshold sang money/evidence/rights để kiếm apparent recall — reviewer **không khuyến nghị**, vì làm hỏng an toàn và Q17/Q20; (c) bỏ yêu cầu 15 travel độc lập trước profile gate hoặc lấy local meeting để đủ số; (d) dùng người/thời gian trial giả thay cho 3 professionals thật — **không chấp nhận**, vi phạm yêu cầu và trung thực. Phương án an toàn khi không đủ feedback là **giữ fixed + công bố thiếu bằng chứng Sprint 2**, dù mất phần điểm tương ứng; user quyết định ưu tiên nguồn lực giữa vận hành core và chứng minh adaptation.

## 5. Điều chưa biết và giới hạn review

1. Chưa có code/runtime nên không có quan sát thực về OCR, relation inference, control races, providers hay caller path. Không chạy OCR/LLM/model calls/tests và không suy “PASS” từ architecture text.
2. Chưa có raw packet, signed gold, feedback hay người thật; không thể xác định thật tỷ lệ miss/false-escalation, sample representativeness, verified labeling cost, adaptive effect, expected latency, xkiro/Mistral khả dụng, hay cost/calls. Các counterexamples là **phép thử đề xuất**, không phải lỗi đã tái hiện.
3. Không có sự xác nhận độc lập từ BTC rằng “threshold recovery-vs-human” thỏa yêu cầu Sprint 2 trong mọi cách chấm. Nên chứng minh **end-to-end changed routing đúng** theo EV-01 thay vì dựa vào diễn giải chữ “threshold”.
4. Các case có source synthetic không chứng minh tình hình tác nghiệp của một công ty thực. Test với ít nhất ba professionals là bằng chứng về usability và tác động có giới hạn, cần phương pháp và lời xác nhận thật; không là dữ liệu để suy causal enterprise uplift.
5. Không có dữ liệu để thiết kế một power analysis đáng tin hoặc cam kết N_min cụ thể. Ranh giới release gate nên công bố conservative support criteria và giữ fallback fixed; đừng coi con số tự chọn là statistical guarantee.

**Kết luận độc lập:** Thiết kế đã có ranh giới an toàn nghiệp vụ hợp lý cho phạm vi quyết toán VND một claimant/một hoạt động. Điểm yếu đáng sửa trước khi lập plan là **hợp đồng chứng minh**: thu được observable labels nào, quyết định R/H tạo hiệu ứng gì, counterfactual nào có thể so, loss an toàn nào metric đang bỏ lọt, và thử nghiệm người thật thực sự đo tổng công việc nào. Có thể làm đúng bằng các packet, oracle và ledger nhỏ cùng pipeline đã chọn. Không cần đổi kiến trúc chính, nhưng nếu chưa bổ sung EV-01/02/04/05/06/07/10/11 thì một implementation plan vẫn có thể tạo demo chạy được mà không chứng minh được phần quan trọng nhất của đề A: **khi nào được tự xử lý, khi nào phải hỏi người, việc hỏi có đúng và có thật sự giảm gánh nặng cho người dùng không**.

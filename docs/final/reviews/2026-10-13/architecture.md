# Review độc lập — Kiến trúc AI agent và tính đúng đắn quyết toán

**Ngày:** 13/10/2026 · **Phạm vi:** đề A / InvoiceReferee, thiết kế trước implementation · **Kết luận:** **CHỈ ĐỦ LẬP IMPLEMENTATION PLAN SAU KHI CHỐT MỘT SỐ CONTRACT CÓ GIỚI HẠN**.

## 0. Ranh giới, bằng chứng, phương pháp và cách đọc

Đây là review mới, không kế thừa đánh giá cuối tài liệu thiết kế. Tôi đọc trực tiếp:

- [Đề gốc](../../../Challenge_Brief_OrganizationAI_VN.docx.md), 298 dòng; SHA-256: 33fbaba876e4b9392ba67f5503878a171db0032d68a8c19758d9d3a16c57a487.
- [Thiết kế](../../ARCHITECTURE_AND_EVALUATION.md), 430 dòng; SHA-256: 6407032ad9f148f0e1bca37b23db084e829fdc7597427380b7ee1209eeacf5ee.
- [Thuật ngữ](../../../../GLOSSARY.md), 58 dòng; SHA-256: e77b518df1dd615f294c781ba7f028c8a147f3b25f5924dd53972f52b2d100b3.
- ADR 0002 (ranh giới tự chủ), 0003 (profile) và 0005 (Python workflow): các quyết định accepted; không tự đặt lại bài toán.

Đường dẫn ở phần findings dùng dạng **tệp:dòng** để kiểm tra trực tiếp trên snapshot trên. Parent đã thử CodeGraph cho các tệp này và nhận “This project has nothing indexed”; list/index_status/coverage không được expose, generation/coverage chưa xác định. Vì phạm vi ở đây là **Markdown thiết kế, không phải code**, tôi đọc trực tiếp tệp theo số dòng; không phát biểu bất kỳ symbol, call-chain hoặc tình trạng chạy code nào. Không đọc nhánh rebuild, memory hay báo cáo review cũ để làm chứng cứ.

**Đề gốc bắt buộc**: tự hoàn tất routine, phân ba nhóm thiếu fact/ngoài policy/vượt quyền, hỏi cụ thể, không khẳng định đầu vào nghi vấn, không chuyển mọi việc cho người, bộ dữ liệu >=15 và Escalation5 3 routine/2 escalations (đề gốc:47–59,71–83). Giám khảo cần live URL/Verify, input mới, audit và Stop/Override thực thi (đề gốc:169–172,197–206,218–223). Đề mở về công nghệ và quy trình (đề gốc:31–35). Vì vậy nhiều ràng buộc tài chính dưới đây là **invariants tự chọn của sản phẩm**, không được gán nhầm là BTC quy định công thức E−A−P+R.

**Giả định đã duyệt, giữ nguyên**: quyết toán sau công việc, một claimant/một hoạt động/VND; nhiều ứng và actual events; nhân viên và công ty có thể cùng chi; công tác trước, tiếp khách sau gate; routine tự kết luận và tạo **yêu cầu** chi/thu, người thực hiện tiền; E<=8 triệu và |S|<=4 triệu cho quyền tự xử lý, cấp quản lý demo 20 triệu trong đúng phạm vi; workflow Python/FastAPI/Pydantic/SQLite/React/Vite; Mistral/xkiro, LangSmith và audit local; tối đa một recovery bổ sung cho mỗi issue trong budget chung. Nguồn: thiết kế:10–32,39–76,79–112,163–196,235–267; ADR 0002:8–15, ADR 0003:8–12, ADR 0005:8–14.

**Chưa có** code/runtime, model/OCR calls, benchmark M0, bộ raw/gold, deployment, feedback xác minh, hoặc thử nghiệm nghiệp vụ thực tế; chính tài liệu xác nhận điều này (thiết kế:355–359,369–372,393–396). Tôi không chạy API, test, cài thư viện, chỉnh Git hay thiết kế gốc. Các số trong ví dụ là **counterexamples tự xây**, không phải lỗi quan sát được từ app. Verdict đánh giá độ kín của hợp đồng để giao builder, không khẳng định ứng dụng hiện có bug hoặc pass.

**Độ nghiêm trọng:** **B0** = thiếu contract có thể dẫn tới tự phát hành sai tiền/quyền hoặc false known; cần khóa trước plan. **B1** = mơ hồ thiết kế có thể gây phân nhánh không tương thích / mất audit; cần đưa thành acceptance trước hoặc ngay ở đầu plan. **B2** = chi tiết thực thi cần chỉ định cụ thể trong plan, không tự biến thành product decision. **Loại:** **C** = chỉnh rõ hợp đồng trong phạm vi đã chốt; **I** = lựa chọn cho builder dưới contract; **D** = muốn đổi quyết định Q1–Q30, phải hỏi người dùng. Severity là mức **rủi ro thiết kế**, không là kết quả test.

## 1. Findings có phản ví dụ và nghiệm thu

### A01 [B0 · C] Ngân sách theo hoạt động thiếu hợp đồng tổng hợp xuyên hồ sơ và chống đồng thời

**Nguồn:** thiết kế:19–27 (một hoạt động nhưng nhiều tài liệu/actual), 44–50 (T trong B), 83–94 (T khác E), 204–212 (reservation/economic identity), 288–290 (cross-dossier). Những dòng này yêu cầu đúng nguyên tắc nhưng **không chỉ rõ** mức khóa ngân sách là hồ sơ hay activity, cách tính chi phí đã dùng ở các hồ sơ khác, và lúc nào reserve T.

**Counterexample:** activity X có B=6 triệu, cùng một nhân viên. Hồ sơ D1 có hóa đơn riêng, T=4, E=4, A=P=R=0; hồ sơ D2 có hóa đơn *khác*, T=4, E=4, A=P=R=0. Riêng từng hồ sơ: T<=B, E<=8, S=4<=4, đủ evidence nên đều tự tạo yêu cầu chi 4. Nhưng **T toàn hoạt động = 8 > B=6**. Đối chiếu trùng hóa đơn không cứu được vì đây là hai nghĩa vụ kinh tế khác nhau. Nếu hai worker commit đồng thời và đều nhìn budget còn 6, cùng một lỗi xảy ra dù mỗi worker có case version đúng.

**Tác động:** routine bị auto-pass trong khi vượt B đáng ra đi POLICY theo rulebook; có thể trả tiền sai và thua trực tiếp thử case ngoại lệ của đề A (đề gốc:49–57,75–81).

**Sửa nhỏ nhất:** định nghĩa một **activity settlement scope** có định danh ổn định, tổng T đã xác minh/đã sử dụng, đã giữ chỗ và những nghĩa vụ của hoạt động; commit quyết định phải kiểm điều kiện **T tổng đã chấp nhận/đang reserve + khoản mới <= B** với truy vấn và khóa giao dịch nhất quán trên SQLite. Làm rõ T trong pending issue có được reserve hay chỉ chặn; không chuyển T unresolved thành 0. Các hồ sơ thuộc cùng activity phải tham chiếu một ngân sách/căn cứ hiệu lực, không sao chép B rồi tiêu độc lập. Điều này không thay hạn mức 8/4/20 hay thêm allocation nhiều claimant.

**Acceptance:** D1 thành công; D2 với khoản khác phải POLICY; hai lệnh song song không thể cùng tạo action hợp lệ vượt B; khi D1 bị hủy trước chi thì giải phóng reservation theo state thực tế; một company-direct C cũng chiếm T budget nhưng không tự biến thành tiền trả nhân viên. Có test chỉ thay thứ tự commit để bảo đảm cùng kết quả. **Phản biện:** khóa per-activity làm giảm throughput, nhưng pilot ~5 người/SQLite và transaction ngắn có chi phí hợp lý; không cần distributed locks hoặc service mới.

### A02 [B0 · C] MoneyEvent thực xảy ra chưa có hợp đồng phân loại, phân bổ và đảo bút toán độc lập

**Nguồn:** thiết kế:81–104 định nghĩa A/P/R/S; 109–112 coverage; 139–144 nhận ghi tiền; 214–226 nhận actual sai và không gọi đó là fulfillment. Glossary:20–26,36–42,56–58 tách tiền thực và instruction. Đây là nền tảng tốt; thiếu cách biểu diễn **actual khác scope / chưa xác định / chuyển nhầm / reversal** mà vẫn không làm sai P/R/S.

**Counterexample 1:** E=5, A=2, P=R=0 ⇒ S=+3 triệu, đã tạo yêu cầu chi 3 cho nhân viên N. Kế toán chuyển 3 cho **người M** do nhập sai số tài khoản. Transfer xảy ra thật; không thể nhập P=3 của N rồi kết luận S=0. Nhưng cũng không được làm giao dịch thật biến mất khỏi audit. Nếu sau đó app tự cấp một instruction 3 mới mà chưa xác minh trạng thái ngân hàng, có rủi ro thực hiện hai lần.

**Counterexample 2 (reversal):** E=3, A=2, P=1, R=0 ⇒ S=0. Ngân hàng sau đó **hoàn trả giao dịch P=1 do chuyển khoản thất bại**. Khoản P có hiệu lực phải trở lại 0 ⇒ S=+1 và kết luận cân bằng trước đó phải được mở lại. Ghi reversal như R=1 là sai về **nguồn và bản chất**: R chỉ là tiền nhân viên thực hoàn và công ty thực nhận, không phải ngân hàng đảo lần chi P. Ghi reversal như một khoản P âm không gắn với giao dịch gốc cũng khó chống ghi lặp.

**Sửa nhỏ nhất:** bắt buộc lớp **actual event ledger** bất biến có id, loại A/P/R/C/khác, hướng tiền, payer/payee, hoạt động, giao dịch tham chiếu, timestamp nghiệp vụ và timestamp ghi nhận, chứng từ, trạng thái chứng thực, liên kết với instruction nếu có. Có **event điều chỉnh/reversal** tham chiếu event gốc, không xóa hay sửa dấu một cách tùy ý. Tách **actual observed** khỏi **valid fulfillment** và khỏi **allocated to dossier/activity**; unresolved actual phải tạo issue/freeze phần phụ thuộc. Công thức S chỉ dùng **net posted events hợp lệ đúng scope**, trong khi toàn bộ actual, kể cả sai, vẫn nằm trong audit. Nếu sai chuyển tiền được thu hồi hay chuyển hướng, phải có sự kiện bù có căn cứ; không tự biến chúng thành R.

**Acceptance:** ghi transfer đến M giữ P(N)=0 và hiện issue đúng người; ghi bank reversal P1 làm thay đổi S từ 0 thành +1, trạng thái case đã cân bằng được invalidate; ghi hai lần cùng bank transaction id không nhân đôi giá trị; ghi tiền thật sai điều kiện không bị API từ chối hoặc âm thầm tính thành fulfillment. **Phản biện:** ledger đầy đủ kiểu kế toán kép quá nặng; ở pilot chỉ cần bảng append-only money_event, optional reversal_of/settles_instruction, trạng thái kiểm chứng và bảng allocation. Không cần xây ngân hàng hay tổng sổ doanh nghiệp.

### A03 [B0 · C] Instruction, partial execution và remaining dễ bị hòa vào phép tính S

**Nguồn:** thiết kế:26–27 nói nhiều lần actual; 89–94 xác định S; 131–143 phân biệt hoàn thành đối soát với tiền xong; 204–207 command id; 214–221 fulfillment/remaining và ngăn instruction trùng. Tuy nhiên thiếu một state transition contract quyết định số còn lại của **instruction đang mở** so với **nghĩa vụ tính lại**, đặc biệt với chứng từ đến muộn.

**Counterexample:** E=4, A=P=R=0; instruction I chi 4. Kế toán chi 2, chứng từ ghi nhận P=2 và I.remaining=2; tính lại S=2. Nếu engine dựa S>0 để tự tạo I2 chi 2 mà vẫn giữ I.remaining=2, app xuất hai yêu cầu cùng 2 triệu. Ngược lại, nếu app chỉ giảm remaining theo sự kiện mới mà không recalculation khi P bị đảo, sẽ giữ I.remaining=0 dù S lại dương. Nếu một chuyển khoản 2 được nhận lại qua hai payload API với **hai command id khác nhau**, command-id idempotency không đủ; cần identity của giao dịch thực.

**Sửa nhỏ nhất:** định nghĩa state cho instruction như ISSUED → PARTIALLY_EXECUTED → FULFILLED / SUSPENDED / SUPERSEDED / CANCELLED (đặt tên builder tự chọn); mỗi actual allocation chỉ fulfill một phần **chưa fulfill** của instruction, với unique transaction identity và amount giới hạn. Mọi lần re-assess phải đối chiếu **S hiện tại ↔ phần obligation chưa được cover bởi instructions còn hiệu lực**, không suy “S mới = cần tạo instruction mới”. Khi basis thay đổi, treo/supersede instruction liên quan, không delete; xử lý unknown bank status bằng trạng thái pending và câu hỏi kế toán trước khi phát hành lại.

**Acceptance:** I=4, ghi P2 → chỉ còn đúng **một** chỉ dẫn hợp lệ cho 2; đồng thời hai clerk ghi cùng transfer P2 → chỉ một actual allocation; nhận P3 sau P2 ngoài authorized remainder 2 → ghi đủ actual5, cảnh báo overexecution1, không đánh dấu I hợp lệ chi5 hoặc auto phát hành thu1 trước kiểm tra; đảo P2 → S và trạng thái instruction được recheck, vẫn truy được I gốc. **Phản biện:** không cần event-sourcing framework; transaction SQLite + unique constraints + vài transition được kiểm là đủ.

### A04 [B0 · C] “Economic identity” là tiêu chí đúng nhưng thiếu phép chứng minh chống trùng có thể vận hành

**Nguồn:** thiết kế:46–51 (không tính trùng), 100–107 (relation khác fact), 181–184 (refs), 209–212 (cùng nghĩa vụ qua nhiều PDF/profile), 281–284 và 307–309 (gold/test). Tài liệu biết hash hoặc amount/date không đủ nhưng chưa có **oracle identity/usage schema** và giới hạn auto khi không xác định được cùng nghĩa vụ.

**Counterexample 1:** hóa đơn khách sạn số H17 giá 3 triệu được scan thành ảnh và PDF khác nhau, lần lượt nằm ở hai hồ sơ của cùng hoạt động. Hash khác nhau, tên file khác; hai dossier đều tự hoàn E=3 ⇒ công ty chi 6 cho **một** khoản 3.

**Counterexample 2 đảo chiều:** một hóa đơn giá 8 có **employee-paid 5** và **company-direct 3** với hai chứng từ chi khác nhau. Nếu dedup khóa cả invoice vào một người trả đầu tiên, app xóa nhầm C hoặc E. Nếu nhân viên/nhà cung cấp xuất hai hóa đơn khác nhau cùng số tiền/ngày, rule chỉ dựa amount/date lại báo trùng sai. Do đó **document identity, expense identity, payment event identity và reimbursement usage** phải tách.

**Sửa nhỏ nhất:** gắn observation cho issuer, document number nếu có, thời gian, line items, total, payer và transaction ref; tạo quan hệ expense/part-payment/claim-use với evidence từng cạnh. Rule deterministic bắt duplicate khi có định danh mạnh được xác minh hoặc sử dụng cùng một expense slice; khi identity không đủ mạnh, route FACT có cặp tài liệu cần so sánh, không tự suy rằng “không trùng”. Commit reserve/claim expense slice dưới unique key/transaction; chuyển profile không làm mất usage. Không đặt fuzzy AI score thành kết luận pháp lý; cũng không khóa toàn invoice khiến hai payer hợp lệ bị đánh trượt.

**Acceptance:** cặp H17 ảnh/PDF khác byte từ hai dossiers chỉ phát hành một obligation; hóa đơn 8 chia payer5/3 cho E5/C3 đúng T8 và không trả C cho nhân viên; hai hóa đơn thật khác cùng amount/date không bị hợp nhất; bản scan không đủ số/issuer giữ FACT. Tất cả chạy shared scenario DB, không reset giữa hai dossier. **Phản biện:** không thể bảo đảm nhận diện 100% qua mọi ảnh thiếu định danh; công khai vùng không đủ chứng cứ và chuyển đúng một câu hỏi fact cụ thể vẫn đáp ứng đề A tốt hơn giả tự động tuyệt đối.

### A05 [B0 · C] “Source ref thật sự hỗ trợ mệnh đề” chưa biến thành rule kiểm chứng chứng cứ có thể chạy

**Nguồn:** thiết kế:100–107,125–138,170–189,281–286,327–328. Đã **đúng** khi tách Source, Observation, Relation, Declaration/Confirmation và bác model confidence làm căn cứ. Vấn đề là Reconciler chưa nhận một **contract về cấp chứng cứ cho từng critical field/quan hệ**, source locator chỉ xác nhận “đọc ở đâu” chứ chưa xác minh “suy được điều gì”.

**Counterexample:** hóa đơn khách sạn ghi “khách lưu trú: N; tổng 1,2 triệu; đã thanh toán”. Ảnh có thật và text OCR đúng, nhưng nó **không chỉ ra ai trả**. Nếu model suy N trả vì tên N trên receipt rồi gắn chính locator của receipt vào E=1,2, check “ref tồn tại” vẫn pass nhưng có thể công ty đã trả trực tiếp. Tương tự tên trên quyết định công tác không chứng minh giao dịch A đã tới tài khoản N; một giấy **đề nghị** 2 triệu không chứng minh **đã nhận** 2 triệu.

**Sửa nhỏ nhất:** thêm bảng **claim → evidence admissibility** cho ít nhất: identity người, activity, expense identity, số/currency, payer, đã trả/đã nhận, thời điểm, ngân sách B, A/P/R/C, grant, relation transaction↔obligation, history coverage. Với mỗi fact lưu literal span/page + normalized value, source type/role, căn cứ/actor khi xác nhận, trạng thái VERIFIED / DECLARED / DISPUTED / UNKNOWN và thời điểm hiệu lực. Reconciler kiểm rule riêng: ví dụ invoice hỗ trợ item/số, **không đơn độc hỗ trợ payer**; bank debit hỗ trợ trích tiền nhưng không luôn đủ để chứng minh người nhận đã nhận; confirmation chỉ đủ khi thuộc loại cho phép và người có quyền. Hành vi “nhân viên sửa OCR” là declaration/correction, không biến nguồn nguyên thủy thành bằng chứng. LLM chỉ đề xuất observation/relation, code chịu trách nhiệm gate.

**Acceptance:** receipt khách N nhưng bank công ty trả ⇒ E0/C1,2 nếu đúng căn cứ; receipt “paid” không có payer ⇒ FACT payer; giấy đề nghị ứng2 mà ledger chưa có actual ⇒ A chưa xác minh; model sinh số tiền đúng nhưng citation sai trường/trang ⇒ bị giữ UNKNOWN; nhân viên sửa 1,2 thành 1,7 không có chứng từ phù hợp ⇒ không được tự auto-pass. **Phản biện:** định nghĩa full ontology kế toán không cần thiết; một bảng field requirements theo profile + bộ validator cho các critical predicates là đủ để xây MVP.

### A06 [B1 · C] Xác nhận nghiệp vụ và “coverage đầy đủ” còn một lỗ hổng về người chịu trách nhiệm và phạm vi negative evidence

**Nguồn:** thiết kế:102–112 yêu cầu xác nhận tiền/payer/received và lịch sử 0 có trách nhiệm; 116–123 phân người; 137–138 yêu cầu recheck; glossary:52–58. Đây là điểm mạnh rõ rệt so với ngầm coi missing=0. Nhưng acceptance chưa tách **người tuyên bố coverage, nguồn họ đã kiểm, scope tài khoản/kỳ, mức quyền xác nhận** và câu trả lời “không có” đã được kiểm chứng.

**Counterexample:** kế toán xem các chuyển khoản tháng 10 của tài khoản quỹ A và trả “không có tạm ứng”. Nhân viên đã nhận A=2 triệu bằng tiền mặt ngày 29/09 từ quỹ B. Nếu confirmation này vô tình được coi là A=0 bao phủ cả kỳ công tác 29/09–02/10, với E=3 triệu, app tạo CHI3 thay vì CHI1. Một nút “tôi xác nhận” từ employee hoặc người có quyền phê duyệt **ngoại lệ** cũng không có thẩm quyền tạo chứng cứ số dư của hai quỹ.

**Sửa nhỏ nhất:** mẫu Confirmation có fact_type, actor_role/grant, provenance nguồn kế toán/quỹ/tài khoản (hoặc nguồn simulated xác định), range thời gian đến **as-of watermark**, scope người/hoạt động/loại dòng tiền, assertion positive/negative, và bằng chứng/ghi chú xác minh. Yêu cầu actor xác nhận tính **đầy đủ** của tập nguồn cần kiểm, kể cả opening balances; không chỉ đánh dấu “đã tra”. Nếu không thể biết tất cả nguồn, trả FACT hỏi đúng kế toán, không gửi cả hồ sơ cho quản lý. Persona demo là quyền synthetic, không tuyên bố xác minh pháp lý.

**Acceptance:** coverage chỉ tháng 10/quỹ A không chấp nhận A=0 trên kỳ gồm 29/09/quỹ B; coverage đầy đủ 29/09–ngày đối soát mọi quỹ liên quan mới cho A=0; employee “không nhận ứng” không tự thay confirmation kế toán; phản hồi quản lý “duyệt khoản chi” không giải quyết coverage. **Phản biện:** không cần tích hợp trực tiếp mọi tài khoản ngân hàng; pilot có thể dùng bảng ledger synthetic có closed-world boundary được ghi rõ và người demo chịu trách nhiệm xác nhận.

### A07 [B1 · C] Mốc hiệu lực policy/grant/B và thời điểm sự kiện chưa có quy tắc “as-of” cho từng loại quyết định

**Nguồn:** thiết kế:41–42,48–66 (version/scope/expiry, quyết định sau khi chi không được giả thành trước), 75–77 (exception), 96–112 (time/coverage), 200–207 và 231–233 (basis/version lịch sử). Snapshot lịch sử được nhấn mạnh, nhưng thiếu rule **version nào xét eligibility thời điểm nào, grant nào xét lúc tạo action**.

**Counterexample:** nhân viên chi T=7 triệu ngày 29/09; ngân sách hoạt động đã được phê duyệt khi đó B=6. Ngày 05/10 được cấp B=8 **chỉ cho chi phí phát sinh từ 05/10**. App đối soát ngày 13/10 đọc B “mới nhất” bằng 8 và tự cho T7 trong B; thực ra khoản phát sinh 29/09 đã vượt B6 và cần POLICY. Tương tự người quản lý có grant hiệu lực từ ngày 10/10 không thể bị ghi hồi tố là người đã cho phép ứng tiền ngày 29/09; tuy nhiên grant hiện tại có thể cho phép **ra quyết định ngoại lệ mới** nếu quy định cho phép.

**Sửa nhỏ nhất:** định nghĩa hai mốc khác nhau: **event/expense effective time** cho policy áp dụng với khoản chi và B đã có hiệu lực, **decision/commit time** cho quyền actor tạo quyết định mới; override/ngoại lệ có decision time thật và effect scope cụ thể, không rewrite quá khứ. Bất kỳ policy revision nào phải nêu hiệu lực từ ngày, có/không retroactive rõ trong record; thiếu thì POLICY/FACT theo tính chất, không lấy latest. Mỗi decision giữ exact IDs+versions+as-of timestamps của B, policy và grant.

**Acceptance:** trên ví dụ 29/09, B6/B8, app vẫn POLICY trừ khi có quyết định có hiệu lực bao phủ khoản trước 05/10; quyết định ngoại lệ ký 13/10 hiển thị **quyết định sau chi** với grant 13/10, không gắn grant đó lên event 29/09; đổi rulebook sau khi action phát hành vẫn tra được căn cứ ban đầu. **Phản biện:** không cần temporal DB phức tạp; policy_version, effective_from/to, quyết định revision và snapshot ID là đủ.

### A08 [B1 · C] T là tiền thực đã chi, nhưng hóa đơn có số dư nhà cung cấp chưa trả có thể làm sai kết luận “đủ B/đã đóng”

**Nguồn:** thiết kế:28–37 (loại trừ refund nhà cung cấp, không lặng lẽ bỏ tình huống ngoài scope), 46–50 (T trong B), 81–98 (T tổng chi thực tế, khác E+C), 142–144 (điều kiện đóng nghĩa vụ); glossary:32–34. Hợp đồng chỉ định nghĩa T “thực tế” nhưng chưa nói cách xử lý **face amount / số đã thanh toán / số chưa trả nhà cung cấp** trong một hóa đơn. Đây là giới hạn suy luận, không có yêu cầu bản đầu phải quản lý accounts payable.

**Counterexample:** hóa đơn nhà cung cấp 10 triệu, nhân viên đã chứng minh trả 5, công ty trả trực tiếp 3, trên hóa đơn còn ghi “còn phải trả 2”. B của hoạt động là 8. Nếu tính T=E+C=8, app có thể tuyên bố “toàn bộ chi hoạt động trong B” rồi hoàn tất, mặc dù còn 2 triệu chưa thanh toán và trách nhiệm khoản ấy chưa được xác định. Nếu tùy tiện coi T=10 là “đã chi” thì lại sai định nghĩa T thực trả. Nguồn ở đây chứa một nghĩa vụ liên quan chưa được xác minh/ngoài phạm vi hỗ trợ; không thể coi phần 2 là số 0.

**Sửa nhỏ nhất:** mỗi expense giữ **face amount, paid portions theo payer, known unpaid amount/unknown và quan hệ thanh toán**. T chỉ là tổng chi công việc thực trả đã xác minh theo rulebook; **separate completeness flag** cho invoice/expense (fully paid, partly paid, unresolved) để không dùng điều kiện T<=B như bằng chứng invoice/hoạt động đã hoàn tất. Nếu số dư có khả năng ảnh hưởng phạm vi quyết toán hay B, chặn money conclusion liên quan và hỏi FACT “2 triệu còn lại ai đã/đang phải trả?”. Nếu thực sự là payable cho nhà cung cấp, gắn “outside current money workflow”, nêu rõ giới hạn và không phát hành instruction cho nhà cung cấp. Muốn **xử lý khoản payable ấy** là mở scope, phải hỏi người dùng; ở đây không đề xuất mở.

**Acceptance:** invoice10, E5/C3/unpaid2 không được biến thành T10 “đã chi”, cũng không được âm thầm coi đây là invoice fully settled; nếu nguồn sửa thành “đã trả đủ” có chứng từ 2 phù hợp thì cập nhật T/payer, kiểm B lại. Tại giao diện, phân biệt tổng giá trị hóa đơn và T thực chi. **Phản biện:** nếu payable2 rõ ràng độc lập và không thay đổi quyền lợi nhân viên, giữ case employee-paid ở trạng thái đã đối soát *có giới hạn* thay vì bắt sửa tất cả mới cho phép xem kết quả; chỉ chặn action khi có phụ thuộc money/budget trọng yếu. Điều này phù hợp việc tránh chuyển thừa routine.

### A09 [B1 · I/C] Gán một document.role cho toàn PDF sẽ sai với PDF gộp nhiều loại chứng từ

**Nguồn:** thiết kế:100–107 mô tả “một loại document.role thuộc từng tài liệu”, 125–130 nhận nhiều PDF/PNG, 170–184 evidence units. Quy tắc hiện tại giải quyết lỗi tưởng “đề nghị khác bảng kê là conflict”; tuy nhiên không đủ để đọc **PDF gồm nhiều chứng từ**.

**Counterexample:** người dùng upload một PDF 3 trang: trang 1 đơn **đề nghị tạm ứng 2 triệu**, trang 2 phiếu ngân hàng **đã trích** 2 triệu, trang 3 xác nhận **nhân viên đã nhận** 2 triệu. Nếu chọn role=REQUEST cho cả PDF, trang 2–3 mất trọng lượng làm chứng cứ actual; nếu chọn role=PAYMENT, trang 1 có thể bị nâng nhầm thành tiền đã chuyển. Một PDF scan ghép quyết định công tác + 3 hóa đơn cũng thuộc nhiều role.

**Sửa nhỏ nhất:** giữ document container nhưng tạo **document_segment/evidence_unit** ít nhất ở cấp trang hoặc khoảng trang; role và observation được gán cho từng evidence unit khi tài liệu gộp. Có thể giữ role chính ở cấp file cho UX, nhưng **validation đọc role ở cấp đoạn**. Không yêu cầu AI tách đối tượng tự do bằng workflow phức tạp: phân trang và cho người chỉnh boundary khi nghi vấn là đủ.

**Acceptance:** PDF gộp 3 trang nhận đúng loại mỗi trang, không coi số “đề nghị” là A actual; tách thành 3 file độc lập cho kết quả tài chính giống hệt; scan có trang không rõ được gắn UNKNOWN cục bộ, không làm sai các nguồn khác. **Phản biện:** việc chia segment tăng số objects/refs nhưng giảm nhiều false conflict; builder có thể implement ngay trong EvidenceReader, không cần module mới.

### A10 [B1 · C] Invalidation, Stop, Resume, Override và event đến muộn cần một state-transition table chung

**Nguồn:** thiết kế:133–143 (issue hết hiệu lực khi basis đổi, recheck trước action), 198–233 (version/transaction/Stop/Override/audit), 231–233 (snapshot cũ). Tài liệu mô tả các guard đúng hướng nhưng chưa có **transition được phép**, nhất là khi command và event có thứ tự arrival khác thời điểm nghiệp vụ.

**Counterexample 1 — race:** worker W đọc case version 4 và gọi OCR. Người dùng Stop case version 5. OCR W trả về kết quả cũ và cố tạo instruction; nếu so chỉ input revision mà không so control epoch, W sẽ commit sau Stop. Hệ thống đã viết “worker muộn không tạo quyết định” (thiết kế:218–220), nhưng thiếu cam kết epoch nằm trong commit predicate và audit atomically.

**Counterexample 2 — giao nhận không chắc chắn:** instruction I chi 3 đã được kế toán mở trên app; Stop được bấm; kế toán vẫn có thể đã xác nhận chuyển tiền trên ngân hàng mà chưa ghi app. Nếu Stop tự hủy I và giải phóng reservation, Resume có thể phát hành I' chi 3; nếu ngân hàng thực tế đã chi I, kết quả là hai lệnh cho một nghĩa vụ. Nếu app không ghi nhận “handed-off / execution unknown”, Stop cũng không phân biệt cái đã xảy ra với cái có thể ngăn.

**Counterexample 3 — replay câu trả lời:** Q hỏi kế toán “đã nhận ứng 2 hay 0?” ở case version 6. Trong lúc chờ, nguồn ngân hàng mới xác minh A=2 ở version 7. Reply cũ “A=0” gửi từ một tab đang mở không được phép override evidence mới để phát hành CHI nhiều hơn.

**Sửa nhỏ nhất:** bổ sung state table cho dossier, assessment/basis, issue, instruction và actual; mỗi command có **expected basis/control epoch, actor permission, idempotency key**, và precondition chặt. Transaction cập nhật read-set versions/Stop/usage/financial instructions/audit; successful provider call không phải commit. Status ít nhưng rõ: DRAFT, ASSESSING, WAITING, READY/ISSUED, STOPPED, SUPERSEDED, COMPLETED; điều quan trọng là transition + predicate, không phải tên enum. Stop sau commit **suspend pending**, không tự reverse ngân hàng; Resume rehydrate từ DB và kiểm mới; Override là quyết định bù đúng quyền có bản ghi lý do/căn cứ, không mutate audit hoặc xóa actual. Câu trả lời cũ được lưu lịch sử nhưng không tự áp dụng nếu basis khác.

**Acceptance:** chạy lịch W-read → Stop → W-commit, luôn chặn W; replay response version cũ bị đánh stale và không đổi A; Stop sau I handed-off đặt execution UNKNOWN rồi cần accounting check trước phát hành I'; case crash sau commit/trước HTTP response, retry cùng command id trả cùng instruction/audit; thay policy/grant/actual buộc re-assess trên dependent basis. **Phản biện:** không cần message queue hoặc orchestration engine; SQLite transaction, process-stage enum, version + explicit transition table/test là đủ cho Python workflow.

### A11 [B1 · C] Kiểm |S| hiện tại có nguy cơ “rửa quyền” qua payment đã xảy ra hoặc nhiều installment

**Nguồn:** thiết kế:52–61 (E<=8, |S|<=4, manager20), 89–94 (S trừ P và cộng R), 139–144 (actual sau action), 214–226 (actual sai phải được ghi, có issue), ADR 0002:8–15. Đây là **khả năng bypass control**, không phải yêu cầu thay đổi các ngưỡng Q30.

**Counterexample:** E=8, A=P=R=0 ⇒ S=8: cần AUTHORITY cho yêu cầu chi8. Một khoản P=5 được kế toán chuyển trước khi có instruction/grant hợp lệ. Hệ thống buộc ghi nhận tiền thật, nay S=3 và **nếu chỉ kiểm |S|<=4**, agent có thể tự tạo yêu cầu chi 3, hoàn thiện một tổng chi8 trong khi 5 đầu tiên chưa có căn cứ được quyền chi. Một biến thể: hai instruction 4 triệu mỗi lần được tạo trên cùng nghĩa vụ 8 sau những thay đổi basis/partial events; nhìn từng command thì <=4 nhưng tổng active authorization không đúng ranh giới.

**Sửa nhỏ nhất:** vẫn áp dụng E<=8 và |S|<=4 đúng như duyệt, song **nguồn P/R dùng để giảm/đổi S phải có trạng thái actual hợp lệ, scope đúng, grant/ủy quyền cho hành động đã thực hiện hoặc quyết định rà soát sai phạm**. Một payment sai quyền vẫn hiện trong sổ actual (A02), nhưng không được tự giải quyết lỗ hổng authority của obligation ban đầu. Giữ cumulative coverage theo obligation và **trace parent authorization** cho các phần fulfill; số đang chờ thực hiện là toàn bộ uncovered authorized obligation, không thể tạo vô hạn I<=4 bằng cách chia nhỏ. Nếu P5 được một chủ thể **có quyền** thực hiện hợp lệ, agent có thể kết luận phần còn lại3 theo gate hiện tại; không bắt mọi routine lên manager.

**Acceptance:** E8/S8 ⇒ AUTHORITY; chèn P5 thiếu cấp quyền ⇒ còn AUTHORITY hoặc issue về payment unauthorized, không auto chi3; chèn P5 có grant và allocation hợp lệ ⇒ S3 có thể qua gate nếu mọi điều kiện khác đủ; hai I4 đồng thời trên cùng nghĩa vụ8 không cùng hợp lệ chỉ do mỗi cái <=4. **Phản biện:** đòi “duyệt toàn bộ E8” lần nữa bất kể grant hợp lệ sẽ trái mục tiêu autonomy; điều cần bảo vệ là **proof of authorization per financial action**, không thiết lập một hạn mức mới hay luật xét duyệt toàn hồ sơ khác Q30.

### A12 [B1 · C] Ngoại lệ POLICY, grant công nhận E và grant tạo chi/thu phải đóng trên ba đối tượng tách biệt

**Nguồn:** thiết kế:44–66 phân E, |S|, B và manager; 75–77 yêu cầu ngoại lệ cụ thể; 122–123 phân quyền fact/exception; 235–245 phân POLICY và AUTHORITY. Tài liệu nhận ra một hồ sơ có nhiều issue song song, nhưng chưa cho bảng **quyền per action** và rule “một quyết định giải quyết chính xác dependency nào”, khiến builder có thể gộp approvals quá rộng.

**Counterexample 1:** E=6, A=P=R=0, B=7, T=6, mọi evidence đủ. Manager ký “chấp nhận chi phí công tác 6” (công nhận E) nhưng **không có quyết định cho phép phát hành yêu cầu chi 6**. Nếu app coi chữ ký ấy giải quyết mọi AUTHORITY, S6 vượt quyền tự tạo request4 mà vẫn auto chi6. Giấy chấp nhận E và grant phát hành chi là hai actions khác nhau.

**Counterexample 2:** T=9 > B=8, E=5, A=2, S3; người có quyền cho phép riêng **khoản khách sạn 1 vượt budget**. Một khoản 0,5 khác đang thiếu payer và relation. Nếu app nhờ exception mà đánh toàn hồ sơ “đã giải quyết”, câu hỏi FACT bị bỏ, dù POLICY đã được quyết định hợp lệ.

**Sửa nhỏ nhất:** bảng nhỏ mapping permission: authorize activity B; recognize eligible E/expense; approve over-B/explicit exception; issue payment/collection by direction & amount; confirm financial facts; record actual money. Exception/decision chứa actor, grant_id+version, specific activity/expense IDs, action, amount ceiling, effect dates, policy/rule ID, reason, source refs và dependent issue_ids được resolve. Chỉ resolve những issue nằm trong phạm vi decision; chạy lại tất cả gates khác. Grant 20 triệu phải được kiểm **theo action và thời hạn**, không một chữ “MANAGER” bao phủ mọi quyền. Không chuyển quản lý thành người xét lại routine khi server có grant auto hợp lệ.

**Acceptance:** manager chấp nhận E6 nhưng chưa approve request S6 ⇒ còn AUTHORITY đúng hành động; approve cả E6 và yêu cầu chi6 đúng scope ⇒ có thể tạo instruction tương ứng sau khi recheck; grant chỉ travel không approve tiếp khách; exception over-B không làm biến mất missing payer; người trả lời fact không tự cấp quyền policy. **Phản biện:** authorization matrix khoảng 5–6 hành động cần vài record và unit tests, không cần IAM doanh nghiệp hay service cấp grant bên ngoài.

### A13 [B2 · I] “Pure Reconciler” và “CaseWorkflow” chưa xác định snapshot input/output đủ chặt để kiểm test tài chính độc lập

**Nguồn:** thiết kế:163–179 liệt kê 4 module và interface, 181–189 mô hình dữ liệu, 200–207 commit, 281–286 oracle. Decomposition ít lớp là lựa chọn hợp lý cho pilot 5 người; nhưng contract hiện tại chỉ có Reconciler.assess(snapshot, observations, relations). Không rõ **declarations/confirmations, actual ledger, policy/grant effective versions, budget aggregate, usage/reservations** có nằm trong snapshot immutable hay đọc DB sau đó.

**Counterexample:** worker lấy observations/relations lúc t0; kế toán thêm P2 lúc t1; Reconciler tạo S3 dựa ledger t0; workflow commit lúc t2 chỉ so version của case mà **ledger dùng chung của activity** không tăng case version đó. Kết quả đã outdated dù Reconciler “pure” đúng với input nó được đưa. Nếu Reconciler tự query DB, lại không còn pure và không thể oracle-test cùng một snapshot.

**Sửa nhỏ nhất (builder detail, không yêu cầu thêm top-level service):** đặt một **AssessmentInput immutable** gồm scope, source/evidence statuses, declarations/confirmations, relations, ledger allocations, policy/grant/B version + as-of, duplicate usage/reservations và read-set version tokens; output **AssessmentResult** tách amount/issue/route/required authorizations/decision basis/allowed next effect. Reconciler chỉ tính; CaseWorkflow nắm transaction, FSM, command id, retry, persisting immutable decisions/events/audit; EvidenceReader cung cấp typed observations/locators và extraction failure; EvaluationRunner gọi cùng public workflow. API REST chỉ gọi CaseWorkflow command, React chỉ render server state. Phân tách helpers và tệp theo responsibility thực tế: data models, evidence/admissibility, finance, policy/grant, persistence/transaction, workflow, API; **không bắt 7 microservices hoặc mỗi tên thành một class**.

**Acceptance:** hai lần assess cùng canonical input ra cùng exact T/E/C/A/P/R/S/issues; case có P2 đến muộn làm commit stale fail rồi re-assess; Reconciler không gọi LLM/SQL hoặc thay audit; sửa OCR locator thiếu không thể sửa money trước control gates; test với stub EvidenceReader, no provider call và same command path. **Phản biện:** dựng generic repository interface, event bus, DI framework hoặc hàng chục abstraction khi chỉ có SQLite là overengineering; ba hợp đồng DTO + transaction ownership rõ hơn cả “module architecture” dài.

### A14 [B2 · I] Demo không cần đăng nhập phải cô lập persona và quyền ở server, nếu không tự tạo grant là quá dễ

**Nguồn:** thiết kế:122–123 nói role client/scan signature không cấp quyền; 363–370 nói demo personas, server provision, session isolation; đề gốc:169,197,218–223 không yêu cầu đăng ký tài khoản và giám khảo sẽ thử Stop/Override. Chủ trương đúng, còn implementation contract phân biệt user/session/demo actor chưa được diễn đạt.

**Counterexample:** giám khảo mở tab A dưới persona “nhân viên”, sửa HTTP body thành role=MANAGER và gửi approve exception cho hồ sơ của tab B. Nếu server dùng role theo request mà không ràng buộc case/session/grant server-side, mọi authorization tests đơn giản có thể pass nhờ dữ liệu do client tự đặt. Nếu reset Verify xóa một database shared, hồ sơ của giám khảo khác bị mất, audit cũng biến mất.

**Sửa nhỏ nhất:** server cấp **demo actor ID + session namespace + grant synthetic** từ context cấu hình, mọi control/answer/record_execution kiểm actor ID/grant cụ thể ở DB (không từ field role do UI gửi), state và artifact/test DB partition per session hoặc scenario, TTL/reset có scope. Cho phép tự chuyển persona qua **UI demo được công bố**, nhưng việc chuyển phải tạo sự kiện actor switch và chỉ trong session sandbox; không claim đó là xác thực doanh nghiệp thực.

**Acceptance:** user gửi body sửa role nhưng không có grant trong server ⇒ reject; hai browser/session không đọc/sửa hồ sơ của nhau; Verify chạy nhiều lần không dọn hồ sơ session khác; actor switch hiển thị trong audit; giám khảo vẫn demo không cần signup. **Phản biện:** đây chỉ là mô phỏng quyền, không nên kéo OAuth/SSO, chữ ký số hay xác thực pháp lý ngoài scope.

### A15 [B2 · I] Giới hạn recovery một lần chưa đảm bảo chi phí/call path đầu vào được khống chế và lỗi kỹ thuật có trạng thái phục hồi nhất quán

**Nguồn:** thiết kế:186–196 giới hạn initial read + một recovery per issue, timeout riêng; 242 (TECHNICAL), 345–359 M0/cost/tracing, 363–372 public upload/calls. Chưa có threshold và model baseline thật: đây là **việc builder phải đo/định nghĩa**, không phải lý do tự đổi Q17 hoặc đòi một platform agent khác.

**Counterexample:** hồ sơ chứa 120 trang scan, 30 fields, 20 issues. Nếu backend chia “initial pass” không ràng buộc số trang/chunks/provider attempts, “tối đa một recovery per issue” vẫn có thể trở thành hàng chục request đắt hoặc hết thời gian trong lúc Verify. Lúc provider timeout sau khi đã đọc 5 trang, app có thể vô tình xem những field còn lại là BLANK thay vì NOT_READ rồi auto-pass nếu schema không giữ read status.

**Sửa nhỏ nhất:** sau M0 đặt ceiling per-case/per-request ở server: file/page/size, OCR/model calls, tokens/usage nếu quan sát được, deadline/retry policy, max issues thử recovery và total budget chung; lưu **read coverage** theo file/page/field với trạng thái NOT_ATTEMPTED, READ, UNREADABLE, PROVIDER_ERROR để không diễn giải missing từ lỗi API. Cho phép dùng lại observations nguyên vẹn có version/locator; khi vỡ limit giữ evidence đã đọc, kết quả chưa thể quyết định là TECHNICAL/UNKNOWN có thể resume, không giả là FACT nghiệp vụ hay “đủ điều kiện”. M0 nên kiểm một case dài bất thường và response schema lỗi; không cần cài queue ngoài.

**Acceptance:** case over page/call limit phản hồi giới hạn rõ và không tạo action; timeout partial read giữ NOT_READ/ERROR không biến thành A/P/R=0; retry bounded không duplicate expensive calls hoặc command effect; no LangSmith vẫn có local audit. **Phản biện:** hard ceiling quá thấp có thể làm tăng chuyển tiếp không cần thiết; hiệu chỉnh theo M0/development, ưu tiên cap server thay vì tự đoán ấn định trong spec. Không biến quota technical error thành success escalation trong metric đề A.

## 2. Những chỗ thiết kế đã đúng, cần giữ khi sửa

Không phải mọi điều trên đều là thiếu sót triết lý hệ thống. Nhiều nguyên tắc quan trọng đã **được viết minh bạch**, và findings trên chủ yếu đòi biến chúng thành contracts quan sát được:

1. **Đúng ranh giới sản phẩm:** routine đủ căn cứ được tự hoàn thành phần quyết toán; người giữ chuyển tiền và ngoại lệ. Không biến mỗi hồ sơ thành ticket xin duyệt (thiết kế:12–17,131–144; đề gốc:47–57). Việc buộc human re-approve tất cả vì sợ lỗi sẽ phá thẳng bài thi.
2. **Đúng toán tiền cơ sở:** tách E phần nhân viên trả đủ điều kiện, C công ty trả trực tiếp, T tổng thực chi hoạt động, A tiền ứng đã nhận, P công ty hoàn thực tế, R nhân viên hoàn thực tế; S=E−A−P+R (thiết kế:79–98). Không trừ C thêm lần nữa, không gộp requested advance vào A, không dùng S=0 từ dữ liệu thiếu (thiết kế:91–112; glossary:20–42,56–58). Các findings A01–A03 không yêu cầu thay công thức, chỉ yêu cầu rõ **events nào được tham gia**.
3. **Đúng phân nhóm dừng:** FACT/POLICY/AUTHORITY là những lỗi nghiệp vụ phân biệt được; lỗi provider/config/schema là TECHNICAL (thiết kế:235–245). Q chuyển tiếp có known facts, câu hỏi hành động, người chịu trách nhiệm và nguồn liên quan (thiết kế:133–138), phù hợp đề gốc:49–59,79–83. Không nên gom mọi unknown thành “xin quản lý xem xét”.
4. **Đúng loại quyền:** E<=8, |S|<=4, B riêng; cấp quản lý20 có action/scope/thời hạn; có thể nhiều issue đồng thời và điều kiện khác vẫn phải pass sau approval (thiết kế:44–77). A11–A12 làm rõ khả năng lách ngưỡng, **không đề nghị tăng hoặc giảm số**.
5. **Đúng chiến lược kỹ thuật cho quy mô nhỏ:** Python workflow tường minh, SQLite transaction, bốn logical modules, LLM chỉ đề xuất, LangSmith không phải ledger (thiết kế:163–196,198–233,345–353). Chưa có bằng chứng nào buộc phải thêm LangGraph, Kafka, microservices, IAM doanh nghiệp hoặc mô hình OCR thứ ba.
6. **Đúng sự khiêm tốn về chứng cứ:** tài liệu nêu rõ chưa có app/model trials, synthetic khác user thật, gold độc lập với scorer, không claim đạt Sprint2 chỉ vì có thiết kế (thiết kế:264–267,281–286,335–343,393–396). Đây là thái độ đúng nhưng chưa thay được bằng chứng thực thi.

## 3. Các contract cần khóa trước khi tách tickets cho builder

Tôi đề xuất **một phụ lục ngắn dạng bảng + các invariant tests** trong spec; không cần viết lại toàn bộ Q1–Q30. Thứ tự sau phản ánh rủi ro quyết định sai tiền hơn là sở thích kiến trúc:

| Thứ tự | Contract cần ghi rõ và chốt acceptance | Findings | Loại/quyền quyết |
| --- | --- | --- | --- |
| 1 | Scope chung per activity, tổng T/B trên mọi dossier, reservations và atomic commit | A01 | **C**, lead làm rõ; không đổi Q |
| 2 | Actual money event taxonomy, ownership/allocation, negative evidence, reversal và net S; instruction fulfillment/remaining | A02–A03, A06 | **C**, lead làm rõ; không đổi công thức Q |
| 3 | Admissibility per critical fact/relation; identity expense vs document vs payment; unknown/duplicate policy | A04–A05 | **C**, lead làm rõ; không đòi AI giải mọi ambiguous |
| 4 | Basis/permission per action, temporal effective/as-of, stage laundering guard, exceptional decision scope | A07, A11–A12 | **C**, lead làm rõ; giữ 8/4/20 |
| 5 | State transitions, late event, Stop/Override/replay/crash, audit immutable | A10 | **C**, lead làm rõ, builder chọn enum/schema |
| 6 | Invoice partially paid/outside scope và định nghĩa kết luận giới hạn; segment role trong mixed PDF | A08–A09 | **C/I**, không mở vendor payable |
| 7 | AssessmentInput/Result, command ownership, session/demo isolation, bounded provider usage | A13–A15 | **I** trong acceptance hiện có |

**Lưu ý về sửa contract và đổi quyết định:** Những sửa được đề xuất ở trên không cần “xin duyệt Q31” vì chỉ làm chặt invariants **đã hứa**: tiền phải đúng scope, không chi trùng, nguồn đủ, quyền đúng, giữ actual thật, Stop/recheck đúng. Builder có thể quyết định tên bảng, phương pháp canonicalization, SQL lock mode, retry ceilings và layout package miễn test không phá invariant. **Chỉ khi muốn** (i) tự quản lý/tự chi payable/refund nhà cung cấp, (ii) tự xác thực tư cách pháp lý người ký, (iii) phân chia cùng invoice cho nhiều claimant/hoạt động, hoặc (iv) thay quyền 8/4/20 hay partial approval khi hồ sơ còn phụ thuộc unresolved thì mới thật sự phải **hỏi người dùng để đổi quyết định D**; tôi không khuyến nghị các mở rộng đó trong pilot.

## 4. Bộ counterexample tối thiểu để người dùng kiểm contract, độc lập với accuracy của AI

Đây là **đề xuất test scenarios**, chưa phải fixtures đã tạo hoặc chạy. Các số là triệu đồng, chỉ rút từ những rules Q đã chốt. Không dùng mã case hardcoded làm đáp án hệ thống; gold và engine phải độc lập như thiết kế:281–290.

| Test | Initial state → event/đối chứng | Kỳ vọng bắt buộc |
| --- | --- | --- |
| F01 | activity B6; hồ sơ 1 có T4/E4/S4 và hồ sơ 2 khác có T4/E4/S4 | Chỉ một hồ sơ có thể được auto action trước; hồ sơ làm T tổng8>B6 → POLICY, cả khi commit song song |
| F02 | E5/A2, request CHI3 cho N; chuyển thực tế 3 cho M | Actual có trong audit; P(N)=0; không đánh FULFILLED; accounting issue và hold instruction nếu execution còn chưa rõ |
| F03 | E3/A2/P1/R0 → S0; ngân hàng reversal đúng transfer P1 | Net P0 ⇒ S1; hủy hiệu lực “cân bằng” cũ; reversal không tạo R giả |
| F04 | I CHI4; trả 2 rồi cùng transfer2 bị nộp lại bằng command mới | P2, I.remaining2, không I' cho cùng phần2; không đếm P4 |
| F05 | I CHI4; trả2 rồi trả thêm3 thực tế, tổng P5 | P5 thật được lưu; chỉ 4 tối đa có thể gắn fulfillment của I; 1 overpayment cần issue, không tự sinh THU1 dựa dữ kiện không đủ |
| F06 | Một hóa đơn 8, employee thực trả5, company-direct3 | E5, C3, T8; company C không được hoàn cho claimant; cùng invoice không bị dedup sai phần |
| F07 | Hóa đơn 3 qua PNG và PDF hai dossiers; invoice number + merchant xác minh trùng | Một economic expense/slice, tối đa một reimbursement usage; lần sau FACT/duplicate theo evidence |
| F08 | Guest N có tên trên invoice “paid1,2”, payer không ghi | Không được tự suy E1,2; FACT “ai thực trả?”; nếu bank công ty đủ chứng cứ thì C1,2 |
| F09 | 29/09 T7 với B6; B8 chỉ có hiệu lực từ 05/10 | Không tự dùng B8 để auto approve; POLICY trừ quyết định bao phủ hồi tố |
| F10 | E8/S8 cần AUTHORITY; ghi P5 thiếu grant trước khi re-assess | Không chuyển thành routine CHI3 chỉ vì S giảm; hỏi/kiểm chứng payment authorization |
| F11 | E6/S6, manager duyệt “công nhận E6” nhưng chưa cho quyền issue chi6 | AUTHORITY cho instruction còn, không tự phát hành CHI6 |
| F12 | Worker OCR đang chạy; Stop commit rồi worker trả; tab cũ trả lời A0 | Không action sau Stop; reply stale không ghi thành authoritative fact; audit giữ timeline |
| F13 | Một PDF ba trang đơn xin ứng, ủy nhiệm chi, xác nhận nhận tiền | Đọc đúng các document segments; requested advance không bằng actual received |
| F14 | Invoice10 đã trả E5/C3, còn nợ nhà cung cấp2 | T actual không tự =10, invoice completeness không tự “đã trả đủ”; không tạo vendor action; money outcome có giới hạn/issue nếu nghĩa vụ đó material |
| F15 | Hai public demo sessions, một session sửa role client thành manager | Server không chấp nhận grant từ role payload; case/audit/Verify/reset cô lập theo session |
| F16 | OCR timeout sau 3 trang trên 10, chưa có ledger coverage | 7 trang NOT_READ/ERROR, không tự cho A/P/R=0 hoặc đủ nguồn; state TECHNICAL/UNKNOWN, cho resume có kiểm soát |

**Kiểm thử hữu ích nhất của riêng reviewer tài chính** là kiểm property và timeline thay vì chỉ đối chiếu output cuối:

- **Conservation:** mỗi MoneyEvent verified net tính đúng **một** lần vào A/P/R/C của đúng activity/claimant và có provenance; S luôn được recompute từ event allocations hợp lệ; instruction đơn thuần không thay P/R.
- **No duplicate coverage:** tổng các amount fulfilled của một instruction không vượt authorized amount; một economic expense slice không được hoàn hai lần; event thực hiện sai vẫn tồn tại nhưng không tăng valid fulfillment.
- **No optimistic unknown:** tài liệu/read/bank history/grant/relation unknown không đồng nhất bằng 0/false; thiếu nguồn quan trọng giữ FACT/TECHNICAL hoặc ngoài scope rõ.
- **Authorization invariants:** mỗi eligible expense recognition và payment instruction mang đúng grant/action/as-of; exception giải đúng issue được phép; chia nhỏ execution không tạo quyền mới.
- **Serializability:** mọi thứ tự commit/retry của hai worker trên cùng activity cho một kết quả tài chính nhất quán; stale/Stop epoch không thể tạo instruction hợp lệ.
- **Auditability:** với bất kỳ decision và MoneyEvent có thể truy lại nguồn, normalized observation, relation, người/thời điểm, scope/grant/policy đúng **version lúc quyết định**, dù live context đã thay.

Đây là các checks ở **layer deterministic** cần xây từ fixture synthetic; chúng không chứng minh OCR/LLM nhận biết được mọi chứng từ lạ. Bài toán AI phải thêm test quan sát thực theo đề gốc và M0; riêng đánh giá chia train/holdout, calibration/adaptation sâu do reviewer khác phụ trách, tôi không kết luận từ thiết kế.

## 5. Đánh giá rủi ro triển khai và thi, không suy từ tài liệu thành vận hành

**Rủi ro trực tiếp tới đề A:** lỗi A01/A04/A05/A11/A12 có thể tạo false-pass routine vượt quyền, sai người, trùng expense hoặc sai nguồn. Đề gốc yêu cầu tuyệt đối không khẳng định dữ liệu nghi vấn, đồng thời không chuyển tất cả routine cho người (đề gốc:47–59,71–83). Vì vậy nghiệm thu phải có cả **routine sạch tự ra instruction ngay** và adversarial cases giữ FACT/POLICY/AUTHORITY đúng; cấm “chữa” bằng cách buộc kế toán xác nhận lại mọi trường hợp.

**Rủi ro chấm vận hành:** A02/A03/A10 có thể làm UI báo “đã thanh toán” từ instruction hoặc không thể rollback/suspend một hành động đúng như audit. BTC sẽ trực tiếp mở một action, xem log rồi bấm Stop/Override (đề gốc:19,201–203,222–223). Demo “có nút Stop” nhưng worker cũ vẫn commit không đủ chứng minh. Bản thiết kế hiện chưa có bất cứ bằng chứng chạy nào (thiết kế:393–396); không có nền tảng để tự chấm pass phần này.

**Rủi ro thời gian:** chỉ từ brief đã có hạn nộp 15/10, demo 17/10 và điều kiện nộp không có app thì mất quyền chấm (đề gốc:25–27,169–175,206,240–244). So với mốc 13/10, triển khai toàn bộ data contracts + actual workflow + Verify + public demo + 3 professional trials là khối lượng lớn; review không tự giả đã được BTC gia hạn hoặc miễn user evidence. Đây là nhận định **khả thi/risk**, không khẳng định người dùng phải bỏ milestone nào.

**Giữ pilot 5 người đơn giản:** SQLite WAL/transaction ngắn + unique constraints, một workflow Python có state rõ, bảng event/expense/usage/basis, field-level provenance cho critical fields và mock server-side personas là đủ nền tảng. Provider boundary chỉ tập trung OCR/LLM extraction & bounded recovery. Có thể demo synthetic first với nguồn đơn giản có định danh rõ, giữ FACT khi mơ hồ; không cần cố giải computer vision matching ở mọi ảnh hay xây ERP. Mỗi bổ sung nên được biện hộ bằng **một failure mode ở bảng F01–F16**, không bằng một xu hướng framework.

## 6. Verdict và điều kiện bàn giao

**Verdict độc lập: CHỈ ĐỦ LẬP IMPLEMENTATION PLAN SAU KHI CHỈNH BOUNDED CONTRACTS.**

- **Chưa nên giao thẳng plan theo đúng văn bản hiện tại như một hợp đồng đầy đủ**, vì A01–A05 còn lỗ hổng có thể dẫn tới sai tiền/quyền/số hoàn, và A06–A12 còn những chỗ hai builder giỏi có thể hiện thực hai kết quả khác nhau mà đều tưởng tuân spec. Tôi không dùng verdict “READY” ghi ở thiết kế:409–414 làm bằng chứng.
- **Không cần xin đổi quyết định sản phẩm Q1–Q30** để sửa các vấn đề này: giữ nguyên scope, công thức tổng quát, mức quyền, tech stack, một recovery/issue, routine autonomy và human cash execution. Lead nên cập nhật **contract fields + temporal/state tables + acceptance timeline F01–F12** rồi mới khóa task tickets; các chi tiết package/SQLite queries/M0 limit thuộc builder.
- **Tuyệt đối không kết luận runtime đạt yêu cầu:** chưa có artifact chạy/gold/LIVE/professional feedback. Khi có implementation, phải chạy độc lập các counterexamples và kiểm raw effects, không chấp nhận chỉ screenshot, LangSmith xanh, test màu xanh hoặc tác giả tuyên bố “đã xử lý”.

**Nguyên tắc chặn plan:** nếu nhóm chưa thống nhất được một MoneyEvent có được tính vào S hay chỉ là observed actual, cách xác định một expense đã được dùng qua nhiều dossier, activity budget aggregation và việc hủy hiệu lực instruction khi actual/Stop đến muộn, thì không thể review đúng tính chất tài chính của code được viết ra. Đây là khoảng trống cụ thể để hoàn thiện, không phải lời kêu gọi xây kiến trúc đồ sộ hơn.

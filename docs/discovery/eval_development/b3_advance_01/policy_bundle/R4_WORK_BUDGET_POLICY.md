# R4.3 — Policy MVP theo ngân sách tổng công việc

Ngày: 09/10/2026 · Trạng thái: **CHỦ DỰ ÁN ĐÃ ĐỒNG Ý POLICY NGÂN SÁCH TỔNG VÀ MÔ HÌNH BA VAI; CHƯA KÍCH HOẠT RUNTIME/CODE**.

Chủ dự án đã đồng ý bảng policy ngân sách tổng và sau đó đồng ý [mô hình ba vai](R4_ROLES_HANDOFF_POLICY.md): Nhân viên — Kế toán — Người duyệt có quyền. Kế toán kiểm tra/trình/thực hiện, người duyệt quyết định công việc và tài chính trong quyền; không dùng đề xuất hai cấp10/30triệu. Nguồn/phạm vi giao quyền vẫn cần khóa rõ, không suy quyền vô hạn.

Đây là bản policy hiện hành để tiếp tục thảo luận R4.3, thay đề xuất trần tiền riêng từng nhóm tại [bản cũ](R4_DEMO_POLICY_PARAMETERS_DRAFT.md). [Evidence R4.2](R4_EVIDENCE_RULES_DRAFT.md), [R3](R3_MVP_SCOPE_DRAFT.md), [khung 9 bước](R2_CASE_WALKTHROUGH.md) vẫn là căn cứ. Không đặt lại số trần cũ, không gọi số minh họa là định mức pháp luật/doanh nghiệp thật. Lead tự review, không có subagent review cho bản ngân sách tổng này.

## PB-01 — Phạm vi và đơn vị kiểm tra

MVP hỗ trợ đề nghị ứng và quyết toán/hoàn trả chi phí công tác trong nước, VND, một nhân viên/một công việc cho mỗi hồ sơ. Một công việc có nhiều lần nộp/bổ sung thì dùng cùng ngân sách và lịch sử, không tạo thêm hạn mức vì có thêm hồ sơ. Công việc khác có ngân sách riêng; một khoản/phần không được tính vào hai công việc. Nguồn thuộc nhiều người/công việc mà chưa phân bổ rõ thì chuyển làm rõ, không xây engine phân bổ tổng quát.

Giữ phân loại vé/di chuyển, khách sạn, ăn và tiếp khách để hiểu nguồn/mục đích; **không có trần tiền riêng từng loại, từng ngày, từng đêm hoặc từng sự kiện**. Không mặc định giữ điều kiện hạng phổ thông từ bản cũ; điều kiện cụ thể về loại dịch vụ chỉ áp khi quyết định/phạm vi được duyệt quy định rõ. Không cần breakdown từng đêm chỉ để chạy một hạn mức đã bỏ; thông tin nào ảnh hưởng purpose/scope/amount/payer vẫn cần đủ.

## PB-02 — Ngân sách có quyền và phạm vi

Ngân sách B là số tiền **người có quyền tài chính cho phép dùng cho toàn công việc**, gồm cả phần công ty thanh toán trực tiếp và phần nhân viên thanh toán. B không bằng số xin ứng, dự toán khai báo, số đã ứng hoặc checkbox Approved. Không đặt một mức B mặc định cho mọi chuyến đi.

Quyết định ngân sách cần đúng công việc/người/phạm vi, tổng tiền, các điều kiện cụ thể nếu có, người/vai có quyền, thời điểm và phiên bản/căn cứ. Người cho phép công tác không tự có quyền duyệt ngân sách. Phần dự kiến công ty trả/nhân viên trả được giữ riêng để xét nhu cầu ứng; phân chia dự kiến không chứng minh actual payer và không là trần riêng nếu quyết định không quy định vậy.

Có thể duyệt ngân sách và số ứng trong cùng quyết định tài chính ở B4 hoặc dùng quyết định bên ngoài đủ căn cứ; không bắt một vòng duyệt ngân sách riêng nếu đã có quyết định đáp ứng. Duyệt ứng2 triệu không tự là duyệt tổng ngân sách8 triệu. Quyết định sửa ngân sách giữ bản cũ và quan hệ phiên bản, không overwrite hoặc hợp thức hóa quá khứ bằng cách đổi field B.

## PB-03 — Khoản chi đủ điều kiện

Mỗi khoản/phần cần giá trị và nguồn phù hợp đủ rõ, liên quan công việc/phạm vi được phép, payer theo phần và history cần thiết. Nguồn thiếu, mờ hoặc mâu thuẫn có thể đổi kết quả thì hỏi đúng người; không lấy trong ngân sách làm căn cứ miễn chứng từ. Áp bộ cash receipt + attestation có điều kiện đã chốt ở R4.2, không chỉ tin PERSONAL.

Phần xác định rõ là chi cá nhân không thuộc công việc thì không đưa vào chi phí công việc/hoàn trả, giữ giá trị và lý do loại. Mục đích chưa rõ khác xác định chắc chắn là cá nhân: hỏi trước, không gắn nhãn từ chối theo suy đoán. Nếu muốn công ty chi cho phần ngoài phạm vi, cần quyết định riêng có quyền; không để AI tự mở rộng policy.

## PB-04 — Kiểm tra ngân sách tổng

T là tổng chi phí công việc đã đối chiếu thuộc cùng phạm vi ngân sách, gồm phần công ty trả trực tiếp và phần nhân viên trả. T khác tổng mọi giá trị trên mọi file; không cộng hóa đơn tổng + deposit + receipt thành ba chi phí. Giữ tổng thực chi, phần công việc và phần không được chấp nhận riêng.

| Điều kiện | Kết quả check ngân sách |
| --- | --- |
| B/T và phạm vi nguồn đủ rõ; T≤B | Trong ngân sách, gồm trường hợp bằng B; chưa thay các check eligibility/payer/history/quyền |
| T>B có căn cứ rõ | Nêu B, T, phần vượt và nguồn; chuyển người có quyền quyết định ngoại lệ, không tự cắt xuống B |
| Chưa có B hợp lệ hoặc T còn thiếu/mâu thuẫn ảnh hưởng | Giữ kết quả đã kiểm tra, hỏi đúng fact hoặc quyết định cần có; không mặc định trong mức hoặc từ chối |

Không cộng tiền ứng A hoặc hoàn chi phí P vào T: đó là tiền cấp/hoàn cho nhân viên, không chi phí công việc mới. Điều chỉnh chi phí/hoàn tiền nhà cung cấp cần nguồn và quyền/phần đúng; ngoại lệ người nhận khác giữ theo giới hạn B7, không tự net để làm trong ngân sách.

Nguồn đủ cho T cần đúng toàn công việc và mốc đang xét, gồm chi công ty liên quan; không đòi sổ chi phí cả công ty hoặc mọi bữa ăn ở công việc khác. Không tìm thấy giao dịch không tự là không có. Thay đổi/nguồn đến muộn kiểm tra lại phần ảnh hưởng và hiệu lực quyết định, giữ lịch sử theo B8/B9.

Người có quyền ngoại lệ có thể chấp nhận toàn bộ, xác định phần chấp nhận/loại hoặc yêu cầu sửa, với số/phần/lý do/phạm vi rõ. Nếu chỉ chấp nhận một phần thì giữ T thực tế và chênh lệch, re-check E/S và quyền; không áp công thức `min(T,B)` mặc định. Muốn đổi B phải là quyết định phiên bản mới, không âm thầm đổi trần.

## PB-05 — Tạm ứng theo nhu cầu được xem xét

Số xin ứng >0 và được so với dự toán phần nhân viên dự kiến thanh toán trong ngân sách/phạm vi đã duyệt. Không lấy cả B gồm vé công ty trả làm nhu cầu tiền ứng của nhân viên. **Bỏ trần xin ứng cố định5 triệu của bản đề xuất cũ**; quyền duyệt ứng vẫn phải rõ theo PB-08. Vượt dự toán phần nhân viên hoặc thay phạm vi cần người có quyền xem xét, không tự giảm số xin.

Chưa đòi chứng từ sau công việc hoặc proof đã nhận khoản đang xin. Số xin, số được duyệt và thực nhận riêng. Approval có thể duyệt số thấp hơn với nội dung/phạm vi rõ; phần chưa được duyệt không tự tạo đề nghị mới.

Sửa/bổ sung cùng đề nghị chưa chi không tự là ứng bổ sung. Đề nghị cũ hủy/chưa chi và không còn quyền/request/lệnh áp dụng có thể xét lại; từ chối còn hiệu lực không bị vượt qua bằng submit mới. Approval còn hiệu lực hoặc lệnh pending cần được kiểm tra trước để không tạo nghĩa vụ chi trùng. Chưa biết actualreceipt không thành0.

Đã thực nhận ứng rồi xin thêm: đưa actualreceipt, pending và nhu cầu còn lại tới người có quyền; giữ ngoài routine của MVP, không gọi tự động là chi trùng/cấm ứng thêm. Không đưa lại một trần theo ngày/nhóm để xử lý supplementary advance.

## PB-06 — Hồ sơ tự chi, chưa có ngân sách được duyệt

Vẫn tiếp nhận và kiểm tra chứng từ, purpose, nguồn tiền và lịch sử. Không bắt tạo khoản ứng giả hoặc coi A=0 chỉ từ việc không thấy đơn ứng. Không tự lấy số nhân viên khai làm B hoặc từ chối chỉ vì thiếu ngân sách trước.

Chuyển người có quyền quyết định việc chấp nhận chi phí cho công việc này: tổng/phần đang xét, căn cứ, phạm vi và số được chấp nhận rõ. Ghi đây là quyết định sau phát sinh chi, không giả đã được duyệt trước. Khi đủ quyết định và fact mới re-check để ra kết quả cuối. Quyết định có thể cùng lúc xử lý việc chấp nhận và phê duyệt tài chính nếu đúng quyền, đủ evidence và scope; không bắt hai vòng bấm cùng một nội dung.

Đây là đường có human decision ngoài routine ngân sách đã duyệt, phải được đo riêng; không lọc khỏi corpus hoặc gọi sau người trả lời là first-pass automatic. Nếu có căn cứ ngân sách hợp lệ ở ngoài hệ thống thì dùng lại, không yêu cầu tạo mới.

## PB-07 — Tính số quyết toán

`S = E - (A - RA) - (P - RP)`

- E: phần nhân viên thanh toán được chấp nhận, gồm cả chi bằng tiền ứng; không cộng phần công ty trả nhà cung cấp.
- A/RA: ứng nhân viên thực nhận / hoàn ứng công ty thực nhận.
- P/RP: tiền hoàn chi phí nhân viên thực nhận / trả lại tiền hoàn chi phí công ty thực nhận.

Các thành phần cùng phạm vi lũy kế/mốc nguồn. Giữ gross history, không double count và không missing-as-zero. S dương đề xuất trả thêm; âm đề xuất nhân viên hoàn lại;0 nhóm này cân bằng, chưa đủ để đóng toàn hồ sơ. Không trừ company-direct lần nữa vì đã loại khỏi E. Nếu nghĩa vụ/fact/policy ảnh hưởng chưa rõ thì chưa chốt S cuối; các check độc lập đủ căn cứ vẫn được lưu.

Số kết luận nguyên VND, tính bằng chương trình; AI đọc/phân loại/đề xuất ghép có nguồn, không tự tạo B, miễn rule hoặc quyết số được hoàn. Các giá trị cần quy tắc làm tròn mà chưa được định rõ không được làm tròn ngầm để pass.

## PB-08 — Thẩm quyền và hành động

| Nội dung quyết định | Cơ sở kiểm tra quyền |
| --- | --- |
| Cho phép công tác | Phạm vi công việc được giao cho người quyết định |
| Duyệt ngân sách | Tổng B và phạm vi/điều kiện; không chỉ số ứng |
| Duyệt ứng | Số/phạm vi ứng được duyệt, ngân sách liên quan và trạng thái quyền/lệnh trước |
| Quyết toán thường quy | E trước đối trừ và số phải chi/thu theo quyết định, không chỉ net0 |
| Ngoại lệ vượt ngân sách / chấp nhận ngoài đường thường quy | Quyền quyết định ngoại lệ rõ, khác quyền duyệt thường quy |

Ba vai đã chốt: Nhân viên; Kế toán rà soát/trình và thực hiện chi/thu; Người duyệt có quyền cho phép công việc, duyệt ngân sách/ứng, quyết toán/ngoại lệ. Kế toán không có quyền phê duyệt tài chính mặc định. Role demo không là xác thực danh tính/thẩm quyền công ty thật. Một người duyệt có thể quyết nhiều nội dung trong cùng thao tác nếu đủ quyền, nhưng nội dung/phạm vi/phiên bản vẫn riêng.

**Phạm vi giao quyền cho người duyệt phải rõ trước khi freeze gold R5.** Không dùng các mức5/10/30triệu từ draft cũ hoặc coi thiếu giới hạn là vô hạn. Quyền có thể giới hạn nội dung/phạm vi hoặc tiền theo căn cứ được công bố; nếu chọn giới hạn tiền thì cần chốt một tham số, không tái tạo hai cấp duyệt. Không cần trần riêng từng nhóm chi phí hoặc role khác để có case beyond-authority.

Khoản bị loại chắc chắn theo rule làm E giảm khác người duyệt muốn tự giảm số để lọt giới hạn quyền được giao. Kiểm tra quyền trước quyết định đang xét, không dùng số người duyệt tự giảm sau đó để hợp thức hóa. Fact correction/loại theo rule cần nguồn/lý do/re-check; phần ngoại lệ chưa giải quyết thì chưa có E/S cuối.

Con người phê duyệt tiền và thực hiện ngoài app. Hệ thống hoàn tất job kiểm tra/báo cáo khi đủ căn cứ; report hoàn tất không là quyền chi, request không là PAID. A ưu tiên report, tự tạo đề nghị chi/thu của giai đoạn B chỉ sau gates đã chốt R3. Không tự chuyển tiền/khấu trừ lương. Đóng chỉ khi nguồn, quyết định, thực nhận và toàn nghĩa vụ trong scope đã xử lý theo B9; Stop/từ chối/S=0 đơn độc không đủ.

## PB-09 — Câu hỏi và bằng chứng đầu ra

Report hiển thị B/phiên bản, khoản/phần và source, T, phần company-direct/employee/unknown, phần chấp nhận/loại/cần làm rõ, actual advances/returns/reimbursements, E và S khi đủ, vấn đề/quyền/người xử lý tiếp. Không bắt người duyệt tự tìm/ghép lại từ đầu.

Hỏi fact có khoản/ref/nguồn/owner; hỏi vượt ngân sách có B/T/phần vượt/lý do đang biết/quyết định cần có; hỏi quyền chuyển đúng người có quyền, không hỏi lại khi routing đã biết. Thiếu source, ngoài policy, beyond authority và lỗi kỹ thuật giữ khác nguyên nhân. Không gọi mọi case hỏi thêm là người duyệt tài chính bắt buộc, hoặc ngược lại dùng checkpoint tài chính để giấu escalation.

## Ví dụ review — không phải kết quả chạy hệ thống

| Dữ kiện đầy đủ trong cùng scope | Kết quả |
| --- | --- |
| B=8 triệu; company-direct3; employee5 đều đủ điều kiện; A=2; RA=P=RP=0 có căn cứ | T=8 trong ngân sách; E=5; S=+3; chờ quyết định tài chính trong quyền |
| Cùng scope nhưng tổng chi phí công việc T=9, B=8 | Vượt1, chuyển ngoại lệ; chưa tự chốt phần chấp nhận/S cuối |
| Tổng khoản đã chi7; phần cá nhân xác định1; công việc6; B=8; employee trả tất cả; A=2; RA=P=RP=0 | Báo thực chi7, loại cá nhân1, T=E=6, S=+4 khi toàn check/quyền đủ; không coi trongB là hoàn cả7 |
| E=5; A=2; P=3; RA=RP=0 có căn cứ | S=0; không đề nghị chi lại cùng nghĩa vụ |
| Nhân viên tự chi5, không ứng/không hoàn trước có căn cứ; chưa có B hoặc quyết định chấp nhận phù hợp | Đối chiếu được fact nhưng chuyển chấp nhận chi phí sau phát sinh; chưa kết luận đủ điều kiện cuối |

## Trạng thái chốt và việc còn lại

Chủ dự án đã đồng ý bảng policy ngân sách tổng được trình bày, giữ các nguyên tắc PB-01..09 ở mức nghiệp vụ. Ngưỡng delegation, hiệu lực/phiên bản áp dụng, hợp đồng nguồn còn cần chốt trước R5/R7; không gọi toàn R4 hoàn tất. Không có thêm mặc định deadline, tỷ lệ ứng, score gian lận, hạng vé hoặc hạn mức bữa/đêm. Số8triệu trong ví dụ không thành ngân sách mặc định cho mọi công việc.

Không sửa nhãn/nguồn walkthrough cũ để ép đạt. Khi freeze policy mới, R5 viết expected độc lập, gồm budget equality/exceed, personalpart, splitpayer, thiếuB, selfpaid, duplicate/pending, sourcequality và quyền. Đo cả công sức nhập/tìm nguồn, hỏi/bổ sung, review và kết quả cuối. Đúng theo ngân sách demo không chứng minh giá trị với doanh nghiệp thật hoặc tự đóng rủi ro brief Challenge A đã ghi ở R3.

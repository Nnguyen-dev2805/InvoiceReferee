# InvoiceReferee — kịch bản thuyết trình 15 phút, đúng 5 slide

Bản nháp ngày16/10/2026 để tập nói và xác định việc cần hoàn thành. Không phải xác nhận các agent đã triển khai xong hoặc đã có kết quả người dùng. Không sửa slide/code trong lượt viết kịch bản.

## Cách sử dụng

- Xưng “em/nhóm em”; thay tên nhóm khi chốt. Phần trong ngoặc vuông là chỉ dẫn sân khấu, không đọc.
- Bản này dành15phút trình bày theo thời lượng người dùng cung cấp; phần hỏi đáp ngoài lịch này. Không thêm slide mở đầu/kết thúc ngoài5slide.
- Thời gian là ngân sách tập nói, chưa được đo bằng một buổi rehearsal. Nếu nói nhanh, dành thời gian chỉ vào nguồn và tương tác; không cố kéo dài bằng đọc mọi chữ.
- Ví dụTC01 thu760000 vàTC25 tranh chấp200000 dựa trên các lượt kiểm tra có lưu trước đây, không là accuracy của bản cuối. Ảnh demo phải ghi mode/phiên bản và được kiểm lại sau tích hợp.
- Slide3 hiện dùng lời nói đúng trạng thái chưa đo. Có đoạn thay thế sau thử nghiệm, chỉ dùng khi đã có số liệu. Không tuyên bố có3practitioners, tiết kiệmX%,20/20 hoặc production-ready.
- Không chạy OCR/LLM mới giữa bài rồi đứng đợi. Nếu trình diễn trực tiếp, mở sẵn hồ sơ đã xử lý và nói rõ là hồ sơ có sẵn; Replay phải ghi Replay, không giả thành LIVE. Dùng ảnh/clip dự phòng của cùng phiên bản khi cần.

## Ngân sách thời gian

| Mốc | Slide | Thời lượng |
|---|---|---:|
|00:00–02:00|1. Vấn đề|2:00|
|02:00–05:00|2. Đầu vào → xử lý → đầu ra và con người|3:00|
|05:00–08:30|3. Tác động và phương pháp đo|3:30|
|08:30–12:00|4. Kiến trúc và ranh giới tin cậy|3:30|
|12:00–14:30|5. Giới hạn, rủi ro và bước tiếp theo|2:30|
|14:30–15:00|Dự phòng; vẫn giữ Slide5|0:30|

## Slide 1 — Muốn quyết toán đúng, phải nối được dữ kiện giữa nhiều chứng từ

**Hình:** một giấy quyết toán, một hóa đơn và bản ghi ứng; nhấn3.240.000/4.000.000/760.000. Thêm một điểm cảnh báo cho thấy dữ liệu khớp số chưa đủ kết luận. Không số liệu thị trường hoặc thời gian thủ công tự ước tính.

**Lời nói:**

“Em xin bắt đầu bằng một hồ sơ rất nhỏ. Một nhân viên nhận tạm ứng bốn triệu đồng, sau đó nộp giấy quyết toán và hóa đơn cho khoản chi ba triệu hai trăm bốn mươi nghìn đồng.

Nếu khoản chi hợp lệ và tiền ứng đã được xác nhận, nhân viên cần hoàn lại bảy trăm sáu mươi nghìn đồng. Phép trừ rất đơn giản. Phần khó là xác định chúng ta có đủ căn cứ để thực hiện phép trừ đó hay chưa.

Kế toán cần biết khoản chi phục vụ công việc nào, hóa đơn có thực sự chứng minh dòng chi đang kê không, khoản ứng có đúng nhân viên và công việc không, và trước đó đã có khoản hoàn trả nào được ghi nhận chưa.

Những thông tin này thường nằm trên các tài liệu khác nhau. Giấy quyết toán thể hiện lời kê khai. Hóa đơn chứng minh hàng hóa hoặc dịch vụ và giá trị của nó. Chứng từ ứng thể hiện một giao dịch tiền. Mỗi nguồn giải quyết một phần của hồ sơ.

Vì vậy, khó khăn không chỉ là nhập lại số tiền từ PDF. Người xử lý còn phải nối các nguồn, kiểm tra sự nhất quán và xác định phần nào có thể quyết định ngay, phần nào cần hỏi lại.

Khi đưa AI vào đây, có hai rủi ro đối xứng. Nếu hệ thống hỏi con người mọi trường hợp, khối lượng kiểm tra vẫn còn nguyên. Nếu hệ thống luôn cố đưa ra kết luận, một dữ kiện đọc sai hoặc liên kết nhầm có thể trở thành yêu cầu chi hoặc thu sai.

InvoiceReferee được nhóm em xây dựng cho Đề A: tự đối soát những hồ sơ đủ căn cứ trong phạm vi được giao, đồng thời chuyển đúng vấn đề đến người có thể giải quyết khi cần.

Đối tượng nhóm em tập trung là quyết toán chi phí công việc. Trong phạm vi demo, nhóm chưa xây quy trình xin tạm ứng trước công việc và không kết nối tự động chuyển tiền ngân hàng.”

**Chuyển:** “Để thấy ranh giới giữa tự xử lý và cần người, em đi qua hai hồ sơ cụ thể.”

## Slide 2 — Đủ căn cứ thì tự xử lý; có vướng mắc thì giao đúng vấn đề

**Hình:** luồng3khối Nhận→Đối soát→Kết quả; nhánh AUTO và FACT/POLICY/AUTHORITY; điểm xác nhận giao dịch tách khỏi phát hành yêu cầu. TC01 vàTC25 là hai ví dụ xuyên suốt.

**Lời nói:**

“Đầu vào của hệ thống gồm giấy quyết toán, hóa đơn hoặc các chứng từ hỗ trợ, cùng dữ liệu công ty như khoản ứng đã ghi nhận và quyền xử lý.

Hệ thống đọc tài liệu, trích xuất thông tin và tạo bản nháp có tham chiếu nguồn để nhân viên kiểm lại trước khi nộp. Xác nhận bản nháp là xác nhận lời kê khai của nhân viên, chưa phải phê duyệt tài chính.

Sau đó, hệ thống đối chiếu từng khoản chi với chứng từ, kiểm tra số học, dữ kiện thanh toán, chính sách và thẩm quyền. Các vấn đề được giao theo nội dung cần giải quyết, không buộc tất cả hồ sơ đi qua cùng một chuỗi duyệt thủ công.

Ở hồ sơ thứ nhất, chi phí đủ điều kiện là ba triệu hai trăm bốn mươi nghìn đồng và khoản ứng đã xác nhận là bốn triệu. Khi mọi điều kiện còn lại hợp lệ, kết quả là yêu cầu thu bảy trăm sáu mươi nghìn đồng.

Em nhấn mạnh chữ yêu cầu. Hệ thống chưa khẳng định công ty đã nhận tiền. Nhân viên còn phải thực hiện hoàn trả, nộp bằng chứng, và kế toán xác nhận giao dịch thực nhận trước khi hồ sơ có thể đóng.

[Chỉ vào kết quảTC01; dành khoảng15giây cho khán giả đọc.]

Hồ sơ thứ hai có một khoản di chuyển. Giấy quyết toán kê chín trăm nghìn đồng nhưng phiếu thu cùng tham chiếu ghi bảy trăm nghìn đồng. Hệ thống cần giữ cả hai giá trị, nêu sai lệch hai trăm nghìn và chưa phát hành yêu cầu tiền.

Câu hỏi cần giúp nhân viên hiểu ngay đang tranh chấp khoản nào, hai nguồn ghi gì, và cần cung cấp chứng từ đúng hoặc điều chỉnh kê khai như thế nào. Việc tự chọn một con số rồi tính tiếp sẽ bỏ qua chính mâu thuẫn cần được giải quyết.

[Chỉ vào900.000/700.000/200.000 và hai đoạn nguồn; dành khoảng20giây.]

Ba loại chuyển tiếp có trách nhiệm khác nhau. FACT là dữ kiện thiếu hoặc mâu thuẫn, giao người có thể xác minh. POLICY là trường hợp cần quyết định ngoại lệ theo chính sách. AUTHORITY là hành động vượt quyền hiện có, cần người có grant phù hợp.

Ví dụ, chi phí đủ căn cứ mười hai triệu đồng vượt mức tự công nhận tám triệu của hệ thống thì cần người phê duyệt. Kế toán vẫn xử lý phần tiền và chứng từ thuộc trách nhiệm của mình, nhưng không tự có quyền duyệt chi phí chỉ vì đang xem hồ sơ.

Mục tiêu của câu hỏi là giải quyết đúng vấn đề đang chặn. Một câu trả lời không được tự động xóa các vấn đề độc lập khác.”

**Chuyển:** “Hai ví dụ này cho thấy cách sản phẩm hoạt động. Phần tiếp theo phân biệt điều đó với bằng chứng sản phẩm thực sự làm công việc tốt hơn.”

## Slide 3 — Đo công sức đối soát cùng chất lượng quyết định

**Hình:** bên trái kết quả kỹ thuật đã nghiệm thu theo số đếm; bên phải phương pháp/thử nghiệm người dùng. Không điền số chưa đo. Chú thíchN,mode,version,phạm vi ngay trênslide.

**Lời nói hiện dùng được khi chưa có thử nghiệm:**

“Với một công cụ xử lý hồ sơ tài chính, thời gian nhanh hơn chỉ có ý nghĩa nếu kết luận vẫn đúng. Một thao tác tạo kết quả sai trong vài giây sẽ không giúp người dùng khi họ phải kiểm lại toàn bộ hồ sơ.

Vì vậy, nhóm em tách việc đánh giá thành hai phần.

Phần thứ nhất là chất lượng kỹ thuật. Hệ thống có bỏ sót hồ sơ cần chuyển tiếp không, có hỏi thừa hồ sơ thường quy không, có giao đúng loại vấn đề và đúng người không, và có phát hành đúng số tiền theo đúng chiều hay không.

Nhóm kiểm kết quả với đáp án được xác định trước khi chạy. Đơn vị chính là hồ sơ; một lần retry hoặc nhiều file trong cùng hồ sơ không được tính thành nhiều trường hợp độc lập. Trường hợp lỗi kỹ thuật và chưa hoàn thành được giữ trong báo cáo.

Các ví dụ nhóm đã kiểm như hồ sơ thu bảy trăm sáu mươi nghìn đồng và hồ sơ tranh chấp hai trăm nghìn đồng cung cấp bằng chứng cho những hành vi cụ thể. Chúng chưa đủ để kết luận tỷ lệ chính xác trên toàn bộ hồ sơ doanh nghiệp, đặc biệt vì các case này đã được dùng trong quá trình sửa hệ thống.

Phần thứ hai là tác động lên công việc con người. Điểm kết thúc nhóm đề xuất giữ giống nhau ở cả hai cách làm: từ lúc nhận đủ hồ sơ đến khi xác định đúng kết luận đối soát và hành động tiếp theo. Nhóm chưa so thời gian chuyển tiền thực tế với thời gian app chỉ tạo yêu cầu.

Người làm thủ công cần được cung cấp cùng thông tin mà app có: khoản ứng, danh tính, phạm vi công việc và quy định. Nếu hai bên có dữ liệu khác nhau thì so sánh tốc độ sẽ không công bằng.

Nhóm sẽ ghi riêng thời gian chủ động đọc, kiểm và sửa; thời gian chờ hệ thống; kết quả đúng hoặc sai; và các lần cần hỗ trợ. Thời gian làm quen cũng phải được ghi nhận.

Để giảm việc lần thứ hai nhanh hơn do đã biết đáp án, bộ thử gồm các cặp hồ sơ tương đương về độ khó và đổi thứ tự làm thủ công với dùng app.

Tại thời điểm chuẩn bị bản trình bày này, nhóm chưa có thử nghiệm với ba người làm nghiệp vụ độc lập. Nhóm chưa công bố phần trăm tiết kiệm thời gian hay mức hài lòng. Nếu chỉ thực hiện với thành viên phát triển, nhóm sẽ ghi đúng là thử nghiệm nội bộ với một người.

Một quan sát quan trọng cần tìm là liệu app có chuyển công đọc chứng từ thành công kiểm tra lại AI hay không. Nếu có, đó là chi phí mới cần báo cáo, không thể bỏ qua chỉ vì phần OCR chạy nhanh.

Kết quả cuối cùng nhóm muốn đưa ra là công sức để hoàn thành đúng nhiệm vụ, cùng những trường hợp hệ thống vẫn làm người dùng mất công.”

**Đoạn thay thế sau thử nghiệm — chỉ đọc khi đã có dữ liệu:**

“Trong thử nghiệm [nêuNngười thật và vai trò], mỗi người thực hiện [nêu nhiệm vụ/phân bổ] bằng thủ công và bằng app. Với các cặp cùng hoàn thành đúng, thời gian chủ động là [số đo thủ công] so với [số đo app], trên [mẫu số cặp hợp lệ]. Toàn bộ thử nghiệm có [đúng/sai/timeout] ở từng điều kiện; nhóm không bỏ những lượt này khỏi báo cáo.

Vướng mắc quan sát được là [sự kiện cụ thể]. Nhóm thay đổi [đúng phần sản phẩm], từ phiên bản[trước] sang[sau], và kiểm lại [kết quả]. Nếu đây là tự thử nghiệmN=1, kết quả chỉ mô tả buổi nội bộ này, chưa chứng minh hiệu quả với kế toán độc lập.”

Không cộng đoạn thay thế vào toàn bộ lời hiện trạng; thay các đoạn tương ứng để giữ thời lượng. Không biến phương pháp dự kiến thành số đo đã thực hiện.

**Chuyển:** “Để hiểu vì sao một kết quả AI không được tự biến thành tác động tài chính, em xin trình bày kiến trúc và các ranh giới của hệ thống.”

## Slide 4 — AI đọc dữ kiện; code kiểm soát quyền và tác động

**Hình:** React→FastAPI/workflow→OCR/LLM→validation/admission→policy/authority→instruction→human-confirmed ledger. Audit/Stop nằm ngoài luồng model. Tô rõ bên ngoài/không tin cậy, vùng thực thi và thành phần giả lập. Kiểm lại topology/model/version thực tế trước xuất bản.

**Lời nói:**

“Kiến trúc của InvoiceReferee gồm giao diện web, backend điều phối, bộ đọc chứng từ, phần kiểm nghiệp vụ và dữ liệu lưu hồ sơ, quyết định, giao dịch cùng lịch sử thao tác.

Trong runtime được chọn cho các lượt kiểm tra gần đây, OCR dùng Mistral và phần hiểu tài liệu dùng Kimi-K3. Model cung cấp dữ kiện có cấu trúc và tham chiếu nguồn. Backend kiểm tra dữ kiện trước khi đưa vào đối soát.

Ranh giới đầu tiên nằm giữa tài liệu và quyền thực thi. Một PDF có thể chứa câu ‘đã được sếp duyệt’. Hệ thống có thể đọc câu đó như nội dung tài liệu, nhưng câu đó không tạo grant. Quyền đến từ dữ liệu tổ chức và được kiểm ở server.

Ranh giới thứ hai nằm giữa dữ kiện model đề xuất và dữ kiện được sử dụng. Ví dụ, giá trị tổng tiền phải có nguồn tương ứng. Liên kết hai tài liệu không được tự chứng minh ai đã trả tiền, hoặc chứng minh toàn bộ số tiền được phép phân bổ.

Ranh giới thứ ba nằm giữa quyết định và thực hiện. Các phép tính tiền, điều kiện chính sách, kiểm quyền và thay đổi trạng thái nằm trong mã nghiệp vụ. Yêu cầu chi hoặc thu được tạo ra không tự biến thành một giao dịch ngân hàng đã hoàn thành.

Để trả lời yêu cầu Enterprise, nhóm em nhìn kiến trúc theo bốn câu hỏi.

Một là danh tính: ai đang yêu cầu hành động. Hai là quyền tối thiểu: người đó được làm hành động gì, trong phạm vi nào và với hạn mức bao nhiêu. Ba là ranh giới thực thi: dữ liệu AI đưa ra phải qua điều kiện nào trước khi có tác động. Bốn là cô lập: dữ liệu và tác vụ thử nghiệm có thể ảnh hưởng đến hồ sơ khác hay không.

Phần có thể minh họa ở cấp ứng dụng là việc kiểm tenant và hồ sơ, giới hạn action theo grant, kiểm phiên bản, chống ghi nhận trùng và cơ chế Stop ngăn kết quả cũ tạo tác động mới. Mỗi khẳng định cần đi kèm kiểm thử trên phiên bản được trình diễn.

[Chỉ qua bốn ranh giới trên sơ đồ, dành khoảng20giây; không đọc danh sách công nghệ.]

Nhóm cũng phân định rõ phần giả lập. Công ty, hồ sơ và các khoản tiền trong bộ demo là dữ liệu tổng hợp. Nút đổi vai giúp giám khảo thử các vai trò nhưng chưa phải xác thực kế toán doanh nghiệp. Ứng dụng chưa kết nối chuyển tiền ngân hàng.

Mô hình một ứng dụng với cơ sở dữ liệu và worker đơn giản phù hợp phạm vi pilot nhỏ. Khi chuyển sang production, việc thay danh tính demo bằng danh tính thật, kiểm quyền tại từng thao tác, quản lý dữ liệu gửi provider và cô lập tác vụ đọc file là những bước phải hoàn thiện. Chạy trong Docker chưa đủ để khẳng định đã có sandbox an toàn cho mọi tác vụ.”

**Chuyển:** “Các ranh giới này giúp giới hạn tác động sai. Chúng không có nghĩa sản phẩm đã giải quyết hết mọi loại hồ sơ hoặc sẵn sàng vận hành doanh nghiệp.”

## Slide 5 — Giới hạn quyết định phạm vi có thể tin dùng

**Hình:**3hàng Tình huống→Hệ quả→Bảo vệ/bước tiếp theo. Giữ lời kết ở chính trang này, không thêm slide thứ6.

**Lời nói:**

“Nhóm em tập trung vào ba giới hạn có ảnh hưởng trực tiếp đến mức có thể tin dùng sản phẩm.

Thứ nhất, chứng từ đọc rõ vẫn có thể chưa đủ nghiệp vụ. Chẳng hạn, một biên bản nghiệm thu và một chuyển khoản cùng có số tiền một triệu rưỡi, nhưng bên cung cấp dịch vụ và bên nhận tiền không khớp. Hệ thống cần làm rõ quan hệ đó, thay vì chấp nhận chỉ vì hai số giống nhau.

Ở nhóm bằng chứng thay thế, dữ kiện dịch vụ và thanh toán cần được kiểm trước; việc chấp nhận ngoại lệ phải có người đúng quyền. Một khoản có hai tài liệu hỗ trợ vẫn chỉ được tính là một khoản chi.

Thứ hai, bản demo có giới hạn về vận hành doanh nghiệp. Quyền nghiệp vụ có thể được kiểm bằng code, nhưng nút chọn vai chưa xác minh danh tính thật. Cô lập tenant ở ứng dụng chưa chứng minh đầy đủ cô lập parser hoặc worker ở hạ tầng. Nhóm sẽ không sử dụng bản demo này như hệ thống ghi nhận giao dịch doanh nghiệp thật khi các khoảng thiếu đó chưa được xử lý.

Thứ ba, bằng chứng đánh giá còn giới hạn. Một tập đã dùng để sửa prompt hoặc rule cho biết lỗi cũ có quay lại không; nó chưa chứng minh năng lực trên dữ liệu chưa từng thấy. Thử nghiệm nội bộ với một thành viên cũng chưa đại diện cho kế toán hoặc tổ chức thực tế.

Vì vậy, bước tiếp theo được ưu tiên là khóa phiên bản và bộ đo, kiểm dữ liệu mới với đáp án xác định trước, đo cả bỏ sót lẫn hỏi thừa, rồi xác thực tác động với người trực tiếp làm nghiệp vụ. Nhóm giữ lại các lượt thất bại để phân tích và không thay đáp án theo kết quả app.

Trong quá trình phát triển, AI hỗ trợ nhóm đọc code, triển khai và tạo kiểm thử. Phạm vi sản phẩm, ranh giới quyền và quyết định chấp nhận thay đổi vẫn phải do nhóm hiểu và chịu trách nhiệm.

Điều InvoiceReferee hướng tới là giao cho hệ thống phần việc có đủ căn cứ và quyền, đồng thời giúp người xử lý hiểu rõ phần việc còn cần họ quyết định. Nhóm muốn chứng minh điều đó bằng hành vi có thể chạy lại, cùng các giới hạn được công bố rõ ràng.

Em xin cảm ơn hội đồng.”

## Checklist trước khi dùng ngày thi

- Thay phầnSlide3 bằng số đo thật nếu đã thực hiện; nếu chưa, giữ công khai khoảng thiếu và hiểu rằng chưa đáp ứng đầy đủ tiêu chí impact.
- Bỏ hoặc sửa mọi câu mô tả guard/flow chưa đạt gate trên bản tích hợp cuối. Kiểm lại đúng quyền người phê duyệt và khả năng response có hiệu lực saureload.
- Hai ví dụTC01/TC25 phải có ảnh/case đúng phiên bản; không dùng ảnh cũ làm proof cho code mới, không ghi Replay thànhLIVE.
- Không cộng testcase/retry thành số người hoặc số hồ sơ độc lập; không dùng14/20 dự đoán làm điểm đã đo.
- Tập một lượt có bấm giờ. Nếu quá14:30, cắt đoạn phương pháp chi tiết ởSlide3 và danh sách thành phần ởSlide4; giữ ví dụ, kết quả, thật/giả lập và giới hạn.
- Nếu demo lỗi, dùng đúng ảnh dự phòng và nói rõ đang xem kết quả lưu; không thao tác vào DB để sửa kết quả trên sân khấu.

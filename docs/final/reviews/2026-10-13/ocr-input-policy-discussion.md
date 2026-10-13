# Quy tắc đầu vào và OCR — bản thảo thảo luận

**Trạng thái:** BẢN THẢO — Q1/Q2 đã được người dùng đồng ý; thiết kế tích hợp Hoangha → final còn các câu hỏi mở; chưa phải policy/contract đã triển khai.

**Phạm vi:** Ghi lại pipeline hiện tại ở `hoangha`, khác biệt liên quan ở `final`, và các quyết định còn mở về định dạng đầu vào/OCR.

## Pipeline hiện tại ở worktree `hoangha`

Đã kiểm tra `hoang-ha-fresh` tại commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`.

### Đường quyết toán FastAPI

1. `SubmitSettlementService` chấp nhận `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`, cùng `.json`, `.txt`, `.xml`.
2. Khi `UC03_DOCUMENT_PIPELINE_ENABLED=1` (mặc định trong runtime), `SettlementProcessingService` chỉ đưa `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp` vào OCR. PDF được gửi cho Mistral dưới dạng `document_url`; ảnh dưới dạng `image_url`. Adapter yêu cầu OCR blocks và word confidence, rồi lưu kết quả thô vào artifact.
3. Các block có confidence thấp mới kích hoạt Kimi Confidence Agent. Sau quality gate, Kimi tiếp tục trích xuất dữ kiện có cấu trúc cho giấy quyết toán và từng chứng từ chi.
4. Validator quy tắc kiểm tra trường bắt buộc/tính hợp lệ; matcher nối chứng từ với dòng chi; policy quyết định findings và tuyến xử lý.
5. Nếu pipeline bị tắt, worker bỏ qua OCR/trích xuất tài liệu. Nếu bật nhưng OCR hoặc Kimi không cấu hình được, hồ sơ nhận lỗi kỹ thuật/thiếu căn cứ thay vì được tính như đã đọc xong.
6. Nếu matcher chỉ tạo `SUGGEST_LINK`, Kimi có thể nhận metadata ứng viên để phân xử; code chỉ cho phép promote ứng viên hiện có khi confidence >= 0.90 và tài liệu chưa được auto-link. Matcher thường trước đó đã có thể auto-link khi số hóa đơn trùng chính xác.

**Chi tiết Q6 cần quyết định:** `collect_low_confidence_blocks()` chỉ tạo candidate khi có word confidence dạng số và nhỏ hơn ngưỡng 0.85. Nếu OCR không trả word scores, candidate list rỗng; processor hiện ghi quality `PASS` mà không gọi Kimi Confidence. Khi có candidate, Kimi phải đánh giá đúng một lần cho từng candidate; thiếu/sai assessment tạo finding chặn. Vì thế “theo Hoangha” có thể mang theo nhánh pass khi confidence bị thiếu.

**Ngoại lệ hiện có:** `.json`, `.txt`, `.xml` được nhận khi upload nhưng không thuộc `OCR_SUFFIXES`; chúng sẽ không được OCR tự động. DOCX không nằm trong allowlist của đường quyết toán nên bị từ chối.

### Đường submission cũ

`SubmitCaseService` cũ nhận thêm `.doc`, `.docx`, `.xls`, `.xlsx`, `.csv`, nhưng `CaseProcessingService` chỉ OCR PDF/JPEG/PNG/WEBP. File ngoài tập đó bị ghi nhận là định dạng chưa hỗ trợ; không có bước chuyển DOCX/Office sang PDF hoặc ảnh.

### So với đường LIVE hiện tại của `final`

Trong `final`, `MistralPageReader` thử lấy text layer của PDF bằng `native_text()` trước. Chỉ khi trang không có text đọc được mới render trang và gọi Mistral OCR. Sau đó `transcribe_text()` dùng parser quy tắc với tập cue/regex giới hạn; đường Submit LIVE hiện chưa gọi Kimi. Vì vậy, PDF có text ở `final` hiện có thể không đi qua OCR.

## Đã xác nhận

- Chỉ nhận PDF, JPG/JPEG và PNG; chưa nhận WEBP, DOCX/Office hoặc định dạng khác.
- Mọi trang trong mọi file được chấp nhận đều đi qua OCR, kể cả PDF có text layer.
- Không dùng native text extraction để bỏ qua OCR.

Các quyết định trên được ghi nhận từ câu trả lời đồng ý Q1/Q2; chưa sửa code.

## Quyết định còn mở

Phạm vi vòng chốt: thiết kế tới bước facts và liên kết chứng từ/dòng chi, dừng trước phép tính tài chính và policy.

1. **Q3 — Workflow owner:** giữ `final` làm chủ root/activity, source, command, audit và financial lifecycle; chỉ port OCR/Kimi/validity/matching của Hoangha qua contracts của `final`? Đề xuất: có, không mang aggregate/database/decision pipeline thứ hai của Hoangha sang.
2. **Q4 — Nơi chạy OCR:** chuyển Submit của `final` sang job nền bền vững để request trả trạng thái đang xử lý, rồi worker OCR/extract; hay giữ xử lý đồng bộ trong Submit? Đề xuất: job nền một-worker/root, có retry/recovery và lưu phase, vì OCR/model có thể chậm/lỗi.
3. **Q5 — Gán loại tài liệu:** nhân viên chọn vai trò lúc tải lên, hay hệ thống phân loại sau OCR? Đề xuất: upload không cần người dùng phân loại; Kimi đề xuất loại, code kiểm schema/căn cứ, loại chưa rõ chuyển FACT cho kế toán.
4. **Q6 — Hợp đồng extraction:** Kimi xuất candidate facts theo loại chứng từ, mỗi fact có source ID, trang, literal quote và state; code xác minh cấu trúc/locator trước khi tạo `Fact`/`Observation` trong final? Đề xuất: có; không nạp DTO Hoangha trực tiếp thành fact đã biết.
5. **Q7 — Confidence gate:** Kimi Confidence chỉ rà block OCR confidence thấp như Hoangha, hay field tài chính thiếu confidence cũng phải unresolved? Đề xuất: confidence thiếu/không hỗ trợ ở trường trọng yếu không được coi là đạt; Kimi chỉ phân loại/đề xuất, không được tự biến giá trị thành KNOWN.
6. **Q8 — Ghép chứng từ:** giữ rule exact invoice-number auto-link của Hoangha, hay yêu cầu kiểm tra thêm số tiền/bên phát hành/nội dung trước auto-link? Đề xuất: không giữ exact-number-only; liên kết chưa đủ căn cứ là Relation UNKNOWN/SUGGESTED, Kimi không tự nâng thành xác nhận.
7. **Q9 — OCR/extraction lỗi:** giữ case unresolved, lưu lỗi và giao người xử lý; không fallback native text hay số 0? Đề xuất: có, nhất quán với Q2.

Q3–Q9 là đề xuất cho cuộc phỏng vấn, chưa phải quyết định của người dùng.

## Cập nhật sau khi người dùng trả lời

Mục cập nhật này là trạng thái mới nhất và thay thế danh sách “Quyết định còn mở” phía trên.

Q1/Q2 vẫn được xác nhận: chỉ PDF/JPG/JPEG/PNG, mọi trang qua OCR, không native-text fallback. Người dùng cũng đồng ý có worker nền đơn giản cho khoảng 5 người dùng, tự phân loại vai trò tài liệu, và giữ hồ sơ unresolved khi OCR/extraction lỗi.

### Cập nhật trả lời

Người dùng đã đồng ý Q3/Q4: không thêm Kimi; wire `XkiroClient`/provider được cấu hình cho `final` vào bước structured extraction, và giữ `final` làm workflow owner. Đây là quyết định thiết kế; X-Kiro hiện chưa được gọi trong Submit LIVE.

Worker nền đơn giản cho khoảng 5 người dùng, phân loại document role tự động và xử lý lỗi theo hướng unresolved cũng đã được người dùng đồng ý.

Trạng thái mới nhất: Q1/Q2, dùng X-Kiro thay vì thêm Kimi, giữ `final` làm workflow owner, worker nền đơn giản, auto-classification và fail-unresolved đã được đồng ý. Còn mở: taxonomy document role, confidence gate, contract extraction/provenance và điều kiện matcher.

Người dùng đã đồng ý Q9 về bội số: nhiều chứng từ có thể hỗ trợ một dòng; một chứng từ chỉ dùng cho nhiều dòng khi có phân bổ dòng/giá trị rõ ràng, tổng phân bổ không vượt giá trị chứng từ. Nếu thiếu phân bổ thì để unresolved.

### Các câu hỏi còn mở

Chưa chốt taxonomy loại tài liệu, hợp đồng facts/source locators, confidence gate và điều kiện matcher; cần hỏi người dùng trước khi thiết kế chi tiết hoặc sửa code.

## Cập nhật sau câu trả lời Q6

Q6 đã được chốt theo cách của Hoangha: Kimi Confidence chỉ chạy khi có candidate low-confidence. Bổ sung guard: nếu thiếu confidence ở trường tài chính trọng yếu thì không coi là PASS; giữ unresolved.

**Frontier tiếp theo:** chốt matching contract; extraction proposal/provenance đã được người dùng đồng ý.

## Trạng thái grilling mới nhất

Người dùng đã đồng ý tách `document_type` khỏi `evidence_role`; model phân loại, giá trị mơ hồ giữ `UNKNOWN`. Q1–Q7, workflow owner, worker đơn giản và fail-unresolved đã được chốt như các cập nhật phía trên. Câu hỏi kế tiếp là tiêu chí và bội số ghép; matcher phụ thuộc vào các facts/locator đã chốt.

## Mốc tham chiếu trong code

- `hoangha`: `src/invoice_referee/application/submit_settlement.py`, `src/invoice_referee/application/process_settlement.py`, `src/invoice_referee/extraction/mistral_ocr.py`, `src/invoice_referee/extraction/kimi_reasoning.py`, `app/web/runtime.py`.
- `final`: `src/invoice_referee/evidence/live_reader.py`, `src/invoice_referee/evidence/pipeline.py`, `src/invoice_referee/runtime.py`.

## Quyết định matching mới nhất

Người dùng chọn **dùng đầy đủ logic matching hiện tại của Hoangha**. Quyết định này thay thế đề xuất thận trọng hơn ở Q8 trước đó; đây là lựa chọn thiết kế, chưa có nghĩa thuật toán đã được chứng minh an toàn cho mọi dữ liệu.

Phạm vi được chọn gồm:

- Chuẩn hóa mã hóa đơn; mã trùng chính xác tự động liên kết với điểm 1.0, không đòi thêm điều kiện trùng số tiền, bên phát hành hay nội dung trước nhánh auto-link.
- Nếu mã không trùng, dùng điểm tổng hợp: số tiền (0.60), tương đồng ngữ nghĩa (tối đa 0.30), tương đồng bên phát hành (0.12 hoặc 0.20), và loại tài liệu (+0.10); dưới 0.50 thì bỏ, từ 0.50 đến dưới 0.75 là gợi ý, từ 0.75 là tự liên kết.
- Kimi chỉ xử lý các liên kết gợi ý; có thể nâng một cặp ứng viên lên auto-link khi confidence từ 0.90, và code giới hạn lựa chọn trong các cặp ứng viên có sẵn.
- Sau liên kết, kiểm tra tổng số tiền chứng từ với dòng chi; nếu một chứng từ đã auto-link cho dòng trước thì tái sử dụng cho dòng tiếp theo bị hạ thành gợi ý.

Rủi ro đã biết và được giữ lại trong lựa chọn này: mã hóa đơn trùng có thể auto-link dù bên bán/nội dung mâu thuẫn; kiểm tra tổng tiền phía sau có thể bắt sai lệch số học nhưng không bắt được mọi trường hợp sai nhà cung cấp hoặc sai loại chi nếu số tiền vẫn khớp. Nhánh điểm tổng hợp và Kimi cũng có thể auto-link một gợi ý dù bằng chứng chưa đủ mạnh theo tiêu chuẩn độc lập cao hơn. Các rủi ro này phải được đưa vào bộ test/evaluation khi triển khai.

Người dùng cũng đã đồng ý cardinality: nhiều chứng từ có thể hỗ trợ một dòng chi; một chứng từ chỉ được phân bổ cho nhiều dòng khi có phân bổ giá trị rõ ràng, tổng phân bổ không vượt số tiền trên chứng từ; nếu thiếu phân bổ thì unresolved. Logic Hoangha hiện tại không tự tạo phân bổ này, nên việc port cần giữ giới hạn đã chốt thay vì suy diễn phân bổ.

**Frontier tiếp theo:** chốt taxonomy hữu hạn cho `document_type` và `evidence_role` trước khi chốt schema trích xuất cụ thể cho từng loại. Chưa sửa code.

Người dùng đã đồng ý taxonomy gọn cho phiên bản đầu:

- `document_type`: giấy quyết toán; hóa đơn; biên nhận; vé/boarding pass; chứng từ thanh toán; tài liệu khác; chưa xác định.
- `evidence_role`: khai báo quyết toán; chứng từ chi phí; căn cứ thanh toán; tài liệu hỗ trợ; chưa xác định.

Việc phân loại chưa chắc chắn giữ `UNKNOWN`; không ép vào loại đã biết. Danh mục này giới hạn phạm vi ban đầu, không kéo toàn bộ enum rộng của Hoangha sang.

**Frontier tiếp theo:** quyết định gọi model phân loại và trích xuất trong một lượt hay hai bước có điều kiện. Chưa chốt schema trường theo từng document type và chưa sửa code.

Người dùng đã đồng ý hai bước tuần tự: model phân loại `document_type`/`evidence_role` trước, kèm căn cứ OCR; chỉ khi phân loại đủ rõ mới gọi bước trích xuất theo schema của loại tài liệu. Phân loại chưa rõ thì giữ `UNKNOWN` và không chọn schema bằng suy đoán.

**Frontier tiếp theo:** chốt trạng thái cho từng trường được trích xuất để phân biệt dữ liệu vắng mặt, không đọc được và mâu thuẫn/đa nghĩa. Chưa sửa code.

Người dùng đã đồng ý các trạng thái trường: `FOUND`, `NOT_PRESENT`, `UNREADABLE`, `AMBIGUOUS`, `NOT_APPLICABLE`. `NOT_PRESENT` không phải số 0; `UNREADABLE` không được suy đoán; bất đồng giữa tài liệu được giữ thành căn cứ riêng.

**Frontier tiếp theo:** chốt độ tường minh của payload extraction — đặc biệt trường không tìm thấy và dòng lặp — trước khi thiết kế schema cụ thể theo từng loại.

Người dùng đã đồng ý mỗi tài liệu trả một payload theo schema loại tài liệu; mọi trường áp dụng đều có status tường minh; trường thiếu không được lược bỏ. Mục lặp là danh sách có căn cứ từng mục; code cấp khóa nội bộ sau validate thay vì tin model tạo ID bền vững.

**Frontier tiếp theo:** chốt cardinality của `evidence_role` trên một tài liệu, đồng thời yêu cầu căn cứ độc lập cho từng vai trò được gán.

Người dùng đã đồng ý một tài liệu có thể mang nhiều `evidence_role` chỉ khi mỗi vai trò có căn cứ OCR riêng. Gán nhiều vai trò không nhân đôi khoản chi/giá trị; vai trò mơ hồ giữ `UNKNOWN`.

**Frontier tiếp theo:** định nghĩa schema theo loại tài liệu; bắt đầu với hóa đơn và giới hạn suy luận từ người mua/chữ ký/phương thức thanh toán.

Người dùng đã đồng ý schema hóa đơn gồm bên bán, định danh/ngày hóa đơn, bên mua, dòng hàng/dịch vụ, tổng và loại tiền, cùng lời ghi thanh toán nguyên văn. Bên mua chỉ phục vụ đối chiếu danh tính; thông tin “TM/CK”, chữ ký hay tên người mua không tự chứng minh người trả hoặc việc đã thanh toán.

**Frontier tiếp theo:** chốt schema facts cho giấy quyết toán của nhân viên và không đưa trở lại trường phân bổ công ty trả/nhân viên trả đã bị loại khỏi phạm vi.

Người dùng đã đồng ý schema giấy quyết toán: tên khai trên giấy (không thay danh tính tài khoản), nơi đến/thời gian/mục đích, số ứng khai trên giấy, các dòng chi và tổng/đề nghị hoàn lại hay thanh toán thêm in trên giấy. Chỉ trích xuất các tổng đã in; không tính chênh lệch ở bước này; không có cột công ty/nhân viên trả.

## Đính chính Q10 — phạm vi taxonomy theo bộ case Hoangha

Người dùng rút lại đồng ý taxonomy gọn Q10 trước đó: muốn mở rộng taxonomy để dùng các case Hoangha. Kiểm tra `data/testcase_uc3_v2/README.md` cho thấy bộ UC-03 v2 có 5 nhóm x 10 case; `tools/generate_uc3_testcases_v2.py` hiện sinh các loại tài liệu `E_INVOICE`, `PAPER_RECEIPT`, `PAYMENT_PROOF`, `TRANSPORT_TICKET`, `OTHER`, `UNKNOWN`. Domain enum của Hoangha rộng hơn và còn có `CARD_SLIP`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`, `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION`.

Chưa chốt dùng sáu loại thực tế của bộ UC-03 v2 hay toàn bộ enum/các bộ case cũ hơn của Hoangha. Cần hỏi phạm vi case mục tiêu trước khi đóng taxonomy; không coi Q10 gọn là còn hiệu lực.

Người dùng chọn phương án 1: giữ đủ 16 giá trị `ExpenseDocumentType` hiện có của Hoangha để hướng tới dùng tất cả bộ case Hoangha. Cần lập inventory case → loại tài liệu; enum được giữ không đồng nghĩa mỗi loại đã có extraction/validation coverage.

**Frontier tiếp theo:** chốt code-owned compatibility giữa `document_type` và `evidence_role`; model chỉ đề xuất và không được tạo một tổ hợp vai trò không được phép.

Người dùng đồng ý code-owned compatibility cho cặp loại/vai trò. Tổ hợp không cho phép/không rõ không bị model hoặc code âm thầm remap; giữ chưa xác định để xử lý. Một tài liệu vẫn có thể nhiều vai trò nếu mỗi vai trò có căn cứ riêng.

**Frontier tiếp theo:** định nghĩa schema nhóm biên nhận: trường chung và trường chuyên biệt cho biên nhận dịch vụ, lưu trú và thu tiền.

Người dùng đồng ý schema nhóm receipt: trường chung về bên phát hành/thu, số/ngày, mô tả, số tiền/tiền tệ và evidence locators; cộng trường riêng cho `PAPER_RECEIPT`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`. Phiếu thu và receipt dịch vụ không bị gộp ý nghĩa.

**Frontier tiếp theo:** schema `TRANSPORT_TICKET`; không suy luận đã đi chỉ từ việc vé được phát hành.

Người dùng đồng ý schema `TRANSPORT_TICKET`: nhà vận chuyển, vé/mã đặt, hành khách, tuyến/ngày giờ, ngày phát hành, giá/phí/tổng và trạng thái chỉ khi nguồn ghi; vé phát hành không chứng minh chuyến đi hoàn tất.

**Frontier tiếp theo:** schema cho chứng từ giao dịch thanh toán và mức kết luận được phép từ trạng thái thể hiện trên chứng từ.

Người dùng đồng ý schema `PAYMENT_PROOF`: đơn vị thanh toán/ngân hàng, mã tham chiếu, thời điểm, bên trả/nhận, tiền tệ/số tiền/phí, nội dung và trạng thái theo nguồn; giao dịch hoàn tất chưa tự liên kết với khoản chi. Không lưu đầy đủ số tài khoản.

Người dùng yêu cầu gom nhiều câu hỏi độc lập trong mỗi lượt để rút ngắn vòng grilling; các câu hỏi tiếp theo sẽ được nhóm theo cụm quyết định thay vì hỏi từng mục một.

Người dùng đồng ý Q21–Q25: schema `CARD_SLIP` có giới hạn dữ liệu thẻ; schema riêng gọn cho bảy loại tài liệu mua sắm/giao nhận; phân loại mơ hồ giữ nhãn chính `UNKNOWN` và lưu ứng viên/căn cứ; code xác thực quote/vị trí thuộc đúng OCR nguồn sau chuẩn hóa hạn chế; tối đa một lượt repair cho JSON/schema, lỗi còn lại chuyển unresolved.

**Frontier tiếp theo:** chốt payload và quyền tham gia matching của `OTHER` so với `UNKNOWN`, rồi xác định cách mang các loại hỗ trợ vào evidence graph mà không biến chúng thành chứng từ chi gốc.

### Bằng chứng implementation liên quan trong Hoangha

Code hiện đặt `E_INVOICE`, `PAPER_RECEIPT`, `TRANSPORT_TICKET`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT` vào `ORIGINAL_EXPENSE_DOCUMENT_TYPES`; `CARD_SLIP`, `PAYMENT_PROOF`, `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION` vào nhóm supporting. `OTHER` và `UNKNOWN` không nằm trong hai nhóm. Matcher vẫn duyệt mọi `ExpenseDocumentFacts`; loại không phải original được cộng 0.10 ở nhánh fuzzy, còn tiêu chí `has_original_evidence` kiểm riêng nhóm original. Do đó một supporting doc có thể có link nhưng link đó không đáp ứng điều kiện có original evidence. Đây là hành vi implementation hiện tại, cần UI/domain contract biểu đạt rõ.

Người dùng đồng ý Q26–Q28:

- `OTHER` là loại nhận diện được nhưng không có schema chuyên biệt; trích xuất schema chung tối thiểu. `UNKNOWN` là chưa phân loại; giữ OCR/các ứng viên và không chọn schema extraction bằng suy đoán.
- Giữ matching Hoangha cho tài liệu hỗ trợ: có thể liên kết bổ trợ với dòng, nhưng không thay thế chứng từ gốc. Thiếu chứng từ gốc vẫn phải được biểu đạt là thiếu, dù có support link.
- Ánh xạ mặc định Hoangha được chấp nhận: original = `E_INVOICE`, `PAPER_RECEIPT`, `TRANSPORT_TICKET`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`; supporting = `CARD_SLIP`, `PAYMENT_PROOF`, `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION`; `OTHER` supporting; `UNKNOWN` chưa xác định. Vai trò phụ chỉ được gán khi có căn cứ riêng.

## Mốc chốt vòng thiết kế trước tính toán/policy

Người dùng kết thúc vòng hỏi và đã chốt các quyết định OCR, worker tích hợp vào workflow `final`, phân loại document type/evidence role, extraction có trạng thái và provenance, schemas theo nhóm tài liệu, matcher theo Hoangha, và vai trò gốc/hỗ trợ. Đây là quyết định thiết kế cho bước tích hợp; chưa sửa code, chưa kiểm chứng port trên runtime, và chưa chốt phép tính tài chính hoặc policy.

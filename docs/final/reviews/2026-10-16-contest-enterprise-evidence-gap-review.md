# Đối chiếu đề thi, bằng chứng và yêu cầu Enterprise

Ngày 16/10/2026. Đánh giá độc lập trong phạm vi yêu cầu cuộc thi; không phải chứng nhận an toàn, điểm chấm chính thức hoặc nghiệm thu toàn bộ ứng dụng.

## Kết luận

InvoiceReferee phù hợp Đề A và có nền tảng nghiệp vụ đáng trình diễn. Khoảng thiếu lớn nhất là **chuỗi bằng chứng có thể kiểm tra lại**: bộ chấm đáng tin → dữ liệu độc lập → kết quả trên phiên bản xác định → tác động lên người thật. Tin nhắn BTC bổ sung một trọng tâm quan trọng: chứng minh đội hiểu ranh giới tin cậy và đánh đổi từ demo sang production.

Không nên đồng nhất ba phát biểu: có nhiều test; đã chạy một số hồ sơ LIVE; đã chứng minh chất lượng trên dữ liệu độc lập. Hiện chỉ có bằng chứng cho hai phát biểu đầu, với giới hạn phiên bản và phạm vi.

## Nguồn và giới hạn kiểm tra

- Đọc lại `docs/Challenge_Brief_OrganizationAI_VN.docx.md`, đặc biệt §2A, §3, §4, §6; đối chiếu plan T9–T12, checkpoint, protocol/proposal, build log, các acceptance report và code liên quan.
- Local main HEAD khi bắt đầu: `8a9bbdc7b25d687d9978ce513cb1e7c18ee300b8`, có thay đổi chưa commit. Trong lượt review, agent khác tiếp tục sửa dataset TC05–TC10 và code intake/runtime. Đây là đánh giá theo bằng chứng có định danh, **không phải qualification một snapshot cuối đã khóa**.
- CodeGraph: đúng project, báo up-to-date, có cảnh báo engine cũ. Không có công cụ generation/coverage tương ứng Codebase Memory; coverage **UNKNOWN**. Dùng graph trước, đọc nguồn hiện hành ở phạm vi thiếu/snippet bị cắt; không tự reindex. Không tuyên bố audit đầy đủ mọi đường quyền hay mọi file.
- Python 3.12.13 qua `rtk proxy uv run --frozen --python 3.12`.
- Không gọi OCR/LLM LIVE, không thao tác UI, DB người dùng, port8000 hoặc Railway. Không commit/push/deploy. Chỉ thêm báo cáo này và bằng chứng riêng dưới `.runtime/contest-gap-review-20261016-v2/`.
- Không đọc Drive/email riêng hoặc xác nhận phiên bản đang deploy. User xác nhận trong lượt này: **chưa nhận và chưa có phản hồi chi tiết của ba người dùng**. Tin nhắn BTC nói feedback nhìn chung tốt nhưng không cung cấp ba hồ sơ người dùng, lời trích dẫn hoặc số đo.
- Một số artifact cũ được acceptance report dẫn, như `.runtime/prompt-hardening/qualification-v3/full-final.xml`, không hiện diện tại checkout này. Ghi nhận là kết quả được báo cáo trước đây, không giả vờ vừa tái lập hoặc đọc raw log.

## 1. Đề thi thực sự yêu cầu gì?

**Đề A:** tự xử lý hồ sơ thường quy; ít nhất15 case; phân biệt FACT/POLICY/AUTHORITY; hỏi cụ thể; không khẳng định với dữ kiện nghi vấn; Verify Escalation5 gồm3 thường quy +2 cần người. Sprint2 bổ sung điều chỉnh ngưỡng từ feedback, tỷ lệ bỏ sót/chuyển tiếp thừa trên tập độc lập, ít nhất3 người trực tiếp làm nghiệp vụ và một thay đổi từ phản hồi của họ.

**Chung kết:** §4 ghi **45 điểm trình diễn +35 điểm phản biện +20 điểm xác thực đề A**. Không dùng thang sơ loại 40/20/20/20 để giả lập điểm chung kết. Phần xác thực A có8 điểm phát hiện đúng,6 điểm không chuyển tiếp thừa,6 điểm chất lượng câu hỏi.

**Sản phẩm nộp:** URL công khai với hướng dẫn bắt đầu; Core4 tuần tự, pass/fail và timestamp; repo công khai có lịch sử; video tối đa3 phút; đúng5 slide; build log1 trang; runbook và bảng input/expected/cách chạy. Slide3 phải có phương pháp và kết quả tác động; Slide4 phân định thật/giả lập; Slide5 nêu giới hạn và lỗi thực tế. Phương pháp dự kiến không thay kết quả đã đo.

**Tin nhắn mới của BTC:** yêu cầu giải thích identity, least privilege, deterministic execution boundaries, sandbox isolation và demo→production. Đây là hướng chuẩn bị phản biện bổ sung; tin nhắn không công bố trọng số mới hoặc miễn yêu cầu người dùng thực tế của đề gốc.

## 2. Đối chiếu hiện trạng

| Yêu cầu | Bằng chứng và kết luận |
|---|---|
| Quy trình và policy rõ | Có hợp đồng nghiệp vụ, S=E−A−P+R, quyền8/4/20 triệu, B ngoài phạm vi. Phù hợp A. |
| Đọc chứng từ đến quyết định | Có pipeline, provenance, admission, issue và yêu cầu tiền; một số lượt LIVE có artifact. Chưa có bảng đánh giá độc lập toàn bộ25 case trên một phiên bản cuối. |
| Ngăn phát hành khi mâu thuẫn | TC25 lưu kết quả chặn900k/700k lệch200k; core TC18 có regression deterministic. Không suy rộng thành mọi mâu thuẫn đều được phát hiện. |
| Xử lý thường quy tự động | Có kết quả routine trước đây; chưa có tỷ lệ chuyển tiếp thừa đáng tin trên tập mới. Xác nhận giao dịch thực tế của kế toán không tự động được tính là escalation ngoại lệ. |
| Verify Core4/Esc5 | **FAIL đường API hiện tại:** trỏ corpus đã bỏ; không chạy case vẫn release=true. UI gọi development/STUB. |
| Bộ chấm đúng | **FAIL một số phản ví dụ** dưới đây. Có test nhưng chưa bao phủ lỗi thật của bộ chấm. |
| Holdout độc lập | Chưa có báo cáo final holdout kiểm được trong phạm vi rà soát.25 case đã dùng đọc/debug/tune là development. |
| Học ngưỡng từ feedback | T11 còn unchecked; tìm các symbol chọn/kiểm/activate ngưỡng trong src/tests chỉ thấy taxonomy split. Chưa chứng minh hoạt động. |
| Ba người dùng và impact | **Chưa có**, được owner xác nhận. Protocol trống; proposal và Slide3 vẫn ghi chưa đo. |
| Human control/audit | Có code và kiểm thử Stop, phiên bản, idempotency, quyền và nhật ký. Chưa diễn tập lại đầy đủ trên bản deploy cuối trong lượt này. |
| Submission | Có slide/build log/video script. Không tìm thấy video thành phẩm dưới docs; không kết luận video không có ở nơi khác. RUNBOOK còn thông tin hosting và dữ liệu cũ. |
| Enterprise identity | Session/actor server-side có thật, nhưng persona switching là mô phỏng danh tính, không phải xác thực nhân sự doanh nghiệp. |
| Sandbox production | Có phân chia logic và cơ chế scope; chưa chứng minh worker/parser sandbox riêng, IAM production hoặc network isolation. |

## 3. Lỗi cụ thể của công cụ chứng minh — đã tái hiện hiện tại

### 3.1 Không chạy hồ sơ nào vẫn báo đạt

`api/routes.py:375` dùng `data/kiem-thu`, hiện không có. `select_suite` trả rỗng; `IndependentScorer.release_gate:197` chỉ xét union==0. Gọi trực tiếp handler thật với workflow sentinel không cho đọc/ghi bất kỳ dữ liệu nào:

```json
{"suite":"core","mode":"STUB","total":0,"union_dangerous_miss":0,"release":true,"rows":[]}
```

Escalation và development cũng vậy. UI `frontend/src/features/verify.tsx:39` gọi development/STUB; dòng100 hiển thị “ĐẠT CHUẨN PHÁT HÀNH”. Không có số liệu nào được đo trong kết quả này.

### 3.2 Bộ chấm chưa phân biệt an toàn, đúng và đủ lượt chạy

| Phản ví dụ đưa vào scorer | Kết quả thực tế của scorer |
|---|---|
| Gold UNSUPPORTED, actual PAY1 triệu | correct_auto_completion=1, dangerous=0, release=true |
| Gold FACT/employee, actual POLICY/approver | correct_auto_completion=0 nhưng release=true |
| Actual lỗi kỹ thuật | technical_failure=1 nhưng release=true |
| Routine cân bằng đúng, không có lệnh tiền | correct_auto_completion=0 dù actual_route=AUTO |

Đây là phản ví dụ **cho scorer**, không phải khẳng định pipeline đã thực sự tạo bốn kết quả sai này. Trường hợp chuyển sai FACT→POLICY có thể an toàn về tiền nhưng sai Đề A. Không được dùng “không có hành động nguy hiểm” thay cho “đúng và hoàn thành”.

`ActualIssue` không mang câu hỏi; mapper `actual_from_view` chỉ lấy kind/owner và bool(refs). Nó chưa chấm được câu hỏi có trả lời được hay refs thực sự chứng minh nội dung. Instruction owner bị mapper gánNone cũng làm yếu kiểm người thụ hưởng.

**Sửa nhỏ nhất cần có:** một manifest hiện hành, số case bắt buộc, missing/empty→ERROR hoặc NOT_RUN; kết quả per-case gồm expected/actual/correctness/completeness/question/source/time/mode. Core4 đúng4, Esc5 đúng5 và đúng3AUTO/2HUMAN. Thêm phản ví dụ cho chính bộ chấm. Tách workflow/DB/upload/provider-mode của Verify khỏi app; runner hiện được truyền shared workflow và có thao tác import context/thay transcriber.

### 3.3 Test xanh không khép được hai lỗi trên

Fresh offline tests trong lượt này:

- Scoring/suites/visibility/Verify: **28 passed**.
- Controls/financial-verification/TC18: **26 passed**.
- Activity-profile/session/config-storage: **25 passed**.

Tổng79 kiểm tra chọn lọc pass, trong khi các probe vẫn cho kết quả sai. Điều này chứng minh thiếu hợp đồng kiểm thử cụ thể, không chứng minh tất cả test vô giá trị. Không chạy full pytest/build/browser trong lượt này.

## 4. Dataset: đổi số khác với tạo phép đo độc lập

Trong lúc review, agent khác đã thay mục đích/số tiền TC05–TC10; README hiện đã có giá trị mới. Không dùng số tiền của báo cáo LIVE cũ để chấm lại PDF mới. Việc đa dạng hóa này giúp demo và giảm trùng ứng viên, nhưng không biến những case đã được dùng sửa hệ thống thành holdout.

Một test chỉ “độc lập” khi policy/cấu hình và tiêu chí đúng được chốt trước khi đọc kết quả, dữ liệu không được dùng để chọn prompt/rule/model, và nhóm mẫu không rò rỉ qua template/case sửa số. Dataset định hướng tìm lỗi không đại diện tần suất công việc ngoài đời; tỷ lệ lỗi trên25 case không được công bố như tỷ lệ lỗi production.

TC03 là ví dụ cần giữ: README có kết quả cân bằng có điều kiện, nhưng giấy công tác thiếu nơi đến/thời gian. Với policy TRAVEL yêu cầu những dữ kiện đó, WAITING có thể là xử lý đúng. Phải chốt oracle theo dữ kiện quan sát được, không coi tên “hợp lệ” là bảo đảm đủ căn cứ.

Đề xuất một tập đánh giá nhỏ mới, người thứ hai chốt expected trước khi chạy: đủ routine để đo chuyển tiếp thừa; FACT/POLICY/AUTHORITY; nhiều cách diễn đạt; một trường hợp ngoài phạm vi; chứng từ xung đột; giả chỉ dẫn trong tài liệu; sai danh tính; Stop/retry.20 hồ sơ là quy mô thực dụng, không phải đủ chứng minh độ tin cậy production. Nếu mẫu nhỏ, công bố số đếm và mẫu số, không chỉ phần trăm.

Đơn vị chính là hồ sơ, không số file, số lần retry hoặc số lời gọi LLM. Báo riêng:

- Cần người nhưng bị tự cho qua / tổng hồ sơ cần người.
- Routine bị hỏi ngoại lệ thừa / tổng routine đủ căn cứ.
- Đúng FACT/POLICY/AUTHORITY và đúng người; câu hỏi đủ căn cứ để trả lời.
- Đúng tiền/hướng/người/không tính trùng; từ chối hợp lý; lỗi kỹ thuật.
- Initial autonomous outcome tách assisted final; một câu trả lời có giải quyết issue không.
- Thời gian đọc/ra quyết định và thao tác/chờ thực tế; số call/token/cost chỉ khi dữ liệu đầy đủ.

## 5. Enterprise: câu trả lời phải dựa trên ranh giới thực

| Trục BTC hỏi | Có thể chứng minh từ code | Giới hạn phải công bố |
|---|---|---|
| Identity | API lấy actor từ session server; truy vấn root theo tenant và quyền xem của employee. | `/demo/persona` cho đổi vai; `start_session` mặc định tenant:demo. Đây là danh tính demo, không xác thực người đang giữ vai kế toán. |
| Least privilege | `_actor_has_grant` kiểm action/scope/profile/amount/effective-time; không chỉ nhãn role. | Biết kiểm grant không khắc phục gốc danh tính demo. Phân quyền nghiệp vụ không tương đương process/credential isolation. |
| Deterministic boundaries | Schema/provenance/admission, số học, grant, idempotency và Stop nằm ở code. Upload bằng chứng khác confirmed money. | Code quyết định nhất quán theo input không bảo đảm model trích xuất input đúng. Prompt chống injection không phải ranh giới bảo mật độc lập. |
| Sandbox isolation | Có tenant/root predicates, nguồn/DB riêng trong một số harness và giới hạn đọc. | Dockerfile một app, không khai báo USER riêng; chưa có bằng chứng sandbox parser/worker theo job, egress allowlist hoặc tách credential. Không được claim có Docker là đã sandbox agent. |

Nguồn: `workflow/service.py:882,924,5931,6773,6780`; `api/routes.py:90,170`; `workflow/controls.py`; `Dockerfile`.

**Ví dụ mạnh để thuyết trình:** tài liệu ghi “đã được sếp duyệt” hoặc model trả confidence cao không được tạo grant. Số khớp chưa xác minh người trả; nhân viên tải biên nhận hoàn chưa được tăngR; worker trả muộn sauStop không được tạo lệnh. Hiện có test cho một số ranh giới này. Muốn trình diễn payload injection cụ thể phải chạy probe và giữ kết quả; review này chưa chạy attack trên OCR/model mới.

**Đánh đổi đáng bảo vệ:** MVP không cho model truy cập một bộ tool tùy ý để ghi sổ/chuyển tiền. Model cung cấp dữ kiện có cấu trúc; mã nghiệp vụ quyết định bước được phép. Không cần bổ sung agent framework hoặc ngân hàng thật để minh họa tư duy Enterprise.

**Khoảng cách production nhỏ nhất:** thay demo-persona bằng identity thật và tenant/role từ server; duy trì kiểm quyền ở từng hành động; tách benchmark khỏi trạng thái người dùng; xử lý file không tin cậy trong worker ít quyền với thư mục theo job và giới hạn tài nguyên, kiểm soát network/secrets; xác lập lưu/xóa tài liệu và dữ liệu gửi OCR/LLM/telemetry; kiểm khả năng khôi phục và truy nguyên nhật ký. Không cần đồng loạt chuyển microservices/Kubernetes cho pilot5 người.

Nhật ký SQLite hiện là audit ứng dụng, chưa có bằng chứng chống sửa bởi quản trị viên có quyền DB. Nếu được hỏi, phân biệt có lịch sử thao tác với tamper-evident audit.

Đối chiếu nguyên tắc với nguồn chính thức: [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) và [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html). OWASP phân biệt xác thực với phân quyền, yêu cầu quyền tối thiểu/kiểm từng request và kiểm quyền thực thi ngoài model. Đây là tài liệu hỗ trợ lập luận, không phải tiêu chí chấm mới do BTC ban hành.

## 6. Phần người dùng còn thiếu không thể bù bằng benchmark

Owner xác nhận chưa có3 phản hồi. “BTC đánh giá nhìn chung tốt” có thể ghi như thông tin liên lạc tổng quát, không chuyển thành3 quotes, ba chức danh hay tác động định lượng. Dữ liệu tổng hợp được đề cho phép; người dùng và lời xác nhận phải thật.

Cách hợp lệ nếu còn thời gian: người trực tiếp làm nghiệp vụ thử hồ sơ synthetic; so manual/app trên nhiệm vụ tương đương, đảo thứ tự, ghi thời gian đọc/sửa/chờ/onboarding; lấy phản hồi bằng lời của họ. Có thể dùng3 người cho pilot nhỏ; không suy ra doanh nghiệp đại diện. Nếu chỉ xem video rồi góp ý, chỉ claim phản hồi định tính, không claim tiết kiệm thời gian tác nghiệp.

Điều cần tìm không chỉ là “có thích không”: có hiểu chênh lệch và căn cứ để trả lời một lần không; có bị hỏi thừa không; có nhầm yêu cầu tiền là đã thu tiền không; có tăng công sức kiểm lại AI không. Mỗi thay đổi từ feedback cần phiên bản trước/sau, nguyên văn nguồn và kết quả kiểm lại. Agent review/owner debug không được đổi tên thành feedback từ ba practitioner.

Nếu không thu được, Slide3 phải ghi rõ chưa đo; vẫn có thể trình bày kết quả kỹ thuật có thật, nhưng **không thể tuyên bố đã đáp ứng phần impact/user Sprint2**. Tương tự, ngưỡng cố định vẫn là chưa đạt yêu cầu adaptive threshold; không tự gọi đổi model là học từ feedback.

## 7. Thứ tự ưu tiên trước thuyết trình

1. **Đóng lỗi công cụ đo:** Verify không xanh rỗng; bộ chấm bắt phản ví dụ; benchmark không thay trạng thái/runtime của app. Đây là ưu tiên trên cả chạy thêm25 case.
2. **Khóa một bản có thể trình diễn:** source/config/prompt/model/context/PDF hashes; Core4, Esc5 đúng3+2; một input mới; trả lời→kiểm lại; audit; Stop; một vòng tiền đến đóng. Ghi rõ LIVE/replay/STUB và thời gian thực. Không cần lặp toàn bộ provider để kiểm các ranh giới code đã có recording phù hợp.
3. **Làm một gói chứng minh Enterprise:** mỗi trục BTC một ví dụ code và một probe; ghi đã làm/chưa làm. Ưu tiên chống phát sinh tác động sai hơn liệt kê tên công nghệ.
4. **Đánh giá độc lập nhỏ có oracle khóa:** giữ mọi kết quả, gồm fail/timeout, và đo chuyển tiếp thừa lẫn bỏ sót. Tập đã sửa theo kết quả chuyển thành development.
5. **Feedback thật và impact nếu thu được:** nếu không, công bố khoảng thiếu thay vì diễn giả lập thành kết quả thật.
6. **Đồng bộ5 slide/video/runbook:** Slide2 nêu quyền thật của AI/người; Slide3 có số đo và phạm vi; Slide4 vẽ ranh giới identity/model/decision/ledger và chỉ rõ demo; Slide5 dùng lỗi đã quan sát + rủi ro production cụ thể.

Không có căn cứ để đưa điểm dự đoán hoặc xác suất vô địch. Lợi thế thực của project là có thể giải thích và kiểm tra vì sao một kết quả AI không tự biến thành quyền thực hiện tài chính. Lợi thế này chỉ thuyết phục khi đội trình diễn được cả giới hạn bảo vệ lẫn những giới hạn chưa triển khai.

## Bằng chứng mới

Trong `.runtime/contest-gap-review-20261016-v2/`:

- `probes.json`: Python/HEAD, hash5 file đánh giá, kết quả handler rỗng3 suite và4 phản ví dụ scorer; sentinel bảo đảm không chạm workflow/DB.
- `evaluation-tests.xml`:28pass.
- `targeted-product-tests.xml`:26pass.
- `scoped-boundary-tests.xml`:25pass.

Ba lệnh pytest dùng các nhóm test được liệt kê ở §3.3, có `--junitxml` tương ứng. Không full-suite, không browser/public acceptance, không kiểm proof spoof/OS sandbox bằng pentest. Các artifact cũ và code đang thay đổi phải được gắn lại đúng phiên bản trước khi dùng làm hồ sơ nghiệm thu cuối.

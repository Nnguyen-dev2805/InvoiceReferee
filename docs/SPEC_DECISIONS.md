# InvoiceReferee V2 — Các quyết định cần chốt trước spec

Ngày: 04/10/2026. Trạng thái: **MVP SCOPE CONFIRMED; chi tiết spec TO_CONFIRM**.
Người phát triển nhận xét định hướng đề xuất phù hợp, đồng thời làm rõ đây là
MVP giải quyết bài toán cốt lõi, không phải production nhiều người dùng. Các
giá trị rulebook và implementation details vẫn cần được chốt trong spec.
Không cài dependency, scaffold, deploy hay gọi provider trong lượt này.

Căn cứ: [roadmap](ROADMAP_V2.md), [requirement mapping](COMPETITION_REQUIREMENTS.md),
[baseline review](reviews/main-baseline-196e266/MAIN_BASELINE_REVIEW.md).

## 1. Những gì đã chốt, không hỏi lại

- Viết lại ý tưởng/policy main trên rebuild để tạo MVP baseline mới B1.
- Main `196e266` là tham chiếu ban đầu B0; cải tiến tiếp theo B2 được so với B1.
- Một người thao tác và một app là đủ; không làm multi-tenant, enterprise
  auth/RBAC, scale-out, distributed jobs hoặc automatic crash recovery.
- Hồ sơ chi phí công ty; bao phủ yêu cầu đề A và Sprint 2.
- Routine: xác nhận eligibility, accepted amount và tạo payment request.
- Không thực hiện chuyển tiền ngân hàng trong phạm vi này.
- Roadmap -> spec -> plan -> implementation.
- Người phát triển không muốn dùng ước lượng số giờ/nhân lực để cắt scope.
- Hiện chưa có người quen làm nghiệp vụ để tham gia user trial.

## 2. Nghiệp vụ và phạm vi — cần người phát triển chốt

### D01 — Dùng rulebook nào?

Cần chốt: chấp nhận một công ty và policy mô phỏng làm căn cứ prototype?
Đề xuất: công ty mô phỏng, quy định có phiên bản và công bố synthetic; dùng
research làm nguồn tham khảo, không gọi đây là policy của một công ty thật.
Lý do: có ground truth đủ rõ để code/test và giám khảo tạo input mới. Người
dùng chuyên môn vẫn cần thử và phản hồi riêng để đóng Sprint 2.

### D02 — Những nhóm chi phí nào nằm trong workflow?

Cần chốt: các nhóm và loại chi cụ thể, điều gì thuộc luồng khác.
Đề xuất: công tác/đi lại, tiếp khách, mua vật dụng/vật tư cho công việc;
inventory profile chỉ áp dụng khi có nghiệp vụ nhận hàng.
Lý do: thể hiện các case company expenses và tận dụng consistency của main.
Đánh đổi: nhiều profile có checklist khác nhau; không dùng một required-field
list hoặc một bộ chứng từ chung cho tất cả.

### D03 — Quyền tự động, hạn mức và ngoại lệ

Cần chốt: giới hạn từng loại chi, giới hạn authority của hệ thống/role và
trường hợp nào được phép xin ngoại lệ.
Đề xuất: tách eligibility limits khỏi authority limits; profile trong quyền
có thể tự hoàn tất, vượt quyền chuyển approver. Rulebook định nghĩa rõ known
refusal và policy exception; người thiếu authority không thể approve bằng
một xác nhận dữ kiện. Chưa chọn số tiền trong tài liệu này.
Lý do: ba nhóm bất định không bị gộp và không dùng feedback để tự đổi quyền.

### D04 — Accepted amount, currency và phần chi cá nhân

Cần chốt: khi số đề nghị khác số chấp nhận, có cho phép chấp nhận một phần
không; xử lý discount/tax/tip/refund và currency như thế nào.
Đề xuất: bắt đầu với VND; số tiền dùng integer đồng/Decimal theo field,
không dùng float. Có breakdown giải thích accepted amount từng khoản; chỉ
tạo payment request khi các điều kiện chặn cần thiết cho request đã giải quyết.
Không tạo nhiều khoản trả một phần trong lúc case còn thay đổi nếu chưa chốt
lifecycle/idempotency tương ứng.
Lý do: tính tiền minh bạch và tránh duplicate/stale request. Các phép làm tròn
và phân bổ phải được viết trong rulebook, không suy từ lời giải thích model.

### D05 — Chứng từ và định dạng đầu vào

Cần chốt: mỗi loại chi cần evidence gì, khi nào chấp nhận chứng từ thay thế;
PDF/ảnh và các nguồn XML/CSV/Excel có cần trong release không.
Đề xuất: PDF/ảnh theo baseline; đưa structured formats cần cho profile vào
spec bằng parser riêng, không gửi mọi định dạng qua OCR. Evidence requirements
theo loại chi; nguồn thay thế chỉ được dùng khi policy cho phép.
Lý do: sửa mismatch intake/OCR của main và không yêu cầu bằng chứng không
phù hợp cho routine case. Với XML/cấu trúc khác, parse đúng không tự chứng
minh authenticity hoặc tax compliance.

### D06 — Ai làm gì và quy trình phê duyệt nào?

Cần chốt: roles nào được xác nhận field, giải thích, duyệt ngoại lệ, thay policy
và override; có cần pre-approval với loại chi nào.
Đề xuất: employee cung cấp dữ kiện; accounting review evidence; manager hoặc
approver quyết định trong quyền; policy owner định nghĩa/đổi rule. Một người
có thể thao tác các vai trò mô phỏng. Spec định nghĩa đúng thẩm quyền nghiệp
vụ của từng action; không triển khai hệ thống phân quyền doanh nghiệp.
Lý do: human response không trở thành một lệnh approve chung; source evidence
và authority không bị thay thế cho nhau.

## 3. Technical — đề xuất kiến trúc để người phát triển lựa chọn

### D07 — Stack và ranh giới frontend/backend

Cần chốt: giữ Streamlit hay chuyển sang frontend/API riêng.
Đề xuất: **React + TypeScript + Vite, Python + FastAPI**; pure policy vẫn là
Python, UI gọi API và không chứa decision logic. Modular monolith cho backend.
Lý do: workflow nhiều role, evidence/issue panels, history và controls trong
lúc job chạy có contract/UI rõ. Verify có thể gọi cùng application layer.
Đánh đổi: hai toolchains và contract frontend/API phải được giữ đồng bộ.
Stack mới không tự làm model hoặc decision đúng hơn.

Streamlit vẫn có thể làm prototype đầy đủ nếu xử lý execution/session/thread
boundaries phù hợp. React là lựa chọn trải nghiệm/vận hành đề xuất, không phải
yêu cầu cuộc thi hoặc bằng chứng baseline thất bại chỉ do framework.

### D08 — Lưu trữ tối thiểu cho MVP

Đề xuất phù hợp scope mới: **SQLite cho structured state + filesystem cho
artifacts**, một app. Lưu case, decision/run, human response, payment request
và căn cứ đủ cho audit/benchmark. Không thêm DB server, storage distributed
hoặc migration framework phục vụ production.
Lý do: cần dữ liệu và lịch sử để giải thích/đánh giá kết quả. Một lần bấm lại
không nên tạo request trùng; đó là tính đúng của bài toán, không phải scale.
Host demo cần giữ dữ liệu cần dùng trong buổi thử; không thiết kế HA/SLA hay
multi-instance để giải quyết nhu cầu chưa có.

### D09 — Provider và vai trò của Kimi

Cần chốt: tiếp tục Mistral/Kimi làm provider baseline; endpoint/model/version
và phần nào được gọi live.
Đề xuất: giữ hai provider làm phương án đầu để so sánh, adapters có contract
và cấu hình. Facts được trích xuất theo document với provenance; quality và
semantic proposals là nhiệm vụ riêng. Code kiểm tra contracts/coverage/rules.
Lý do: giữ phép so công bằng và giảm cơ hội trộn nguồn. Đánh đổi: per-document
calls có thể tăng overhead; benchmark trước khi gộp hoặc thay provider.
Không giả định confidence call nhìn ảnh hoặc model cụ thể hỗ trợ multimodal
khi adapter/configuration chưa được kiểm chứng.

### D10 — Execution đủ cho MVP và nút Stop

Scope đã chốt không yêu cầu job engine production. Đề xuất: xử lý một case
đang hoạt động theo luồng đơn giản, có progress và Stop flag; ghi input/output/
result cần cho audit. UI nhận thao tác Stop trong lúc chờ provider và không
áp dụng kết quả muộn sau stop. Core Verify chạy tuần tự.
Lý do: các control cuộc thi cần có hiệu lực; không cần broker, worker fleet,
leases, automatic resume sau crash hoặc scheduling framework. Nếu app dừng,
buổi thử có thể chạy lại với trạng thái/lịch sử rõ và tránh request trùng.
Chi tiết execution được agent thiết kế tối thiểu cho một app, không hỏi lại
người phát triển về nhu cầu nhiều user/instance.

### D11 — Stop/Override semantics

Cần chốt: stop ngăn bước nào; override thay quyết định nào; action nào không
được miễn bằng override.
Đề xuất: stop ngăn bước/hành động kế tiếp và áp dụng kết quả muộn; override có
actor, authority, reason, scope, original decision và run mới. Evidence chưa
usable và các hard gates không bị tự bỏ bằng một lý do tự do.
Lý do: control có tác dụng và audit giải thích được. Không nói remote model
đã bị hủy chỉ vì hệ thống không áp dụng output của nó; delete không thay stop.

### D12 — Demo MVP dễ dùng và chạy được

Scope mới: một app demo, không cần signup, dùng synthetic data và vai trò mô
phỏng được ghi rõ. Không triển khai enterprise identity, tenant isolation,
onboarding nhiều user hoặc environment nội bộ riêng phục vụ production.
Các input boundary/secret cơ bản vẫn được xử lý khi cần để chạy app an toàn.
Thử ba nhân sự nghiệp vụ có thể là các buổi thử tuần tự trên cùng MVP; người
và phản hồi phải thật, không biến role mô phỏng thành user evidence thật.
Lý do: đáp ứng accessibility và proof cuộc thi, tập trung vào correctness và
experience của một case. Hosting/configuration tối thiểu để app hoạt động
và giữ evidence cần dùng; không có cam kết vận hành doanh nghiệp.

## 4. Evaluation, adaptation và bằng chứng

### D13 — Test corpus và chuẩn nghiệm thu

Cần chốt: quy mô evaluation độc lập, tiêu chí release và expected được gán ra sao.
Đề xuất: Core 4, Escalation 5, corpus nghiệp vụ ít nhất 15; thêm probes từ B0
và đóng băng outputs B1 để so từng cải tiến B2. Evaluation holdout riêng với
label theo rulebook. Không dùng rule đang được kiểm tra
tự gán nhãn rồi tự chấm. Không có wrong automation trên acceptance cases cố
định là một gate; independent eval báo đầy đủ tử số/mẫu số và giới hạn mẫu.
Lý do: có phép so công bằng và biết thay đổi nào tăng chất lượng; không tự hứa
accuracy cao hoặc latency/cost chưa đo. Size/thresholds cụ thể chốt ở protocol.

### D14 — Feedback adaptation

Cần chốt: tham số chuyển tiếp nào được điều chỉnh và feedback nào đủ authority/
ground truth để dùng.
Đề xuất: bounded adaptation trên tham số được cho phép, có feedback provenance,
parameter version, before/after và rollback khi đánh giá không đạt; hard policy
limits/authority không tự đổi. Calibration data và eval data riêng.
Lý do: đáp ứng S01 mà không biến một lần approve ngoại lệ thành policy chung.
Ngưỡng 0.85 của main không tự trở thành lựa chọn adaptation đã được duyệt.

### D15 — Budget và bằng chứng live

Cần chốt: trần chi phí provider/hosting và ai cung cấp cấu hình/credit được dùng.
Đề xuất: log call/token/latency/repair; concurrency và per-run budget hữu hạn;
fake để phát triển, live để chứng minh integration/quality khi thực hiện;
cache chỉ reusable evidence theo hash/version trong phạm vi MVP, không cache expected
answer theo case name. Không chọn số tiền budget thay người phát triển.
Lý do: Verify và live input có chi phí thật; tránh coi fake suite hoặc cache
hit như một lời khẳng định đã gọi provider live.

### D16 — Cách đóng yêu cầu 3 nhân sự thực tế

Cần chốt: phương án tiếp cận và bằng chứng thử nghiệm; không hỏi lại giả định
rằng người phát triển đã có accountant contacts.
Đề xuất: tìm hỗ trợ kết nối qua BTC/cố vấn hoặc cộng đồng chuyên môn; chuẩn bị
protocol ngắn và prototype có synthetic case để người thử tham gia dễ hơn.
Research/agent simulation phục vụ preparation, chưa đóng S03. Chưa liên hệ
hoặc gửi thông điệp cho người khác trong quá trình lập tài liệu.
Lý do: cần feedback của chính người trực tiếp làm nghiệp vụ, một cải tiến và
một bất cập phát sinh có bằng chứng; code generation không tạo được evidence này.

### D17 — Trải nghiệm và phần trình bày quyết định

Cần chốt: evidence, issue và câu hỏi hiển thị cùng nhau thế nào; accepted amount
và payment request có cần export phục vụ demo/runbook không.
Đề xuất: tiếng Việt, các chế độ nhân viên/reviewer/approver cho một người
thao tác có nhiệm vụ rõ; mỗi issue
hiện vấn đề, giá trị, source và action cần làm; timeline theo run; export
payment request/report có identity, không tự gắn trạng thái “đã chi tiền”.
Lý do: giám khảo/người dùng giải quyết được câu hỏi mà không đọc raw JSON hoặc
toàn bộ hồ sơ; UI đẹp phải đi cùng sự rõ ràng của nghiệp vụ.

### D18 — Tạo MVP baseline rồi cải tiến có đối chứng

Người phát triển đã làm rõ: tham khảo ý tưởng main để code lại/cải thiện;
MVP viết lại đủ đúng và hiệu quả trở thành baseline mới, sau đó phát triển
các cải tiến để so sánh với baseline đó.

Đề xuất: ghi rõ B0 main lịch sử, B1 MVP nền và B2 từng cải tiến. B1 có workflow
cốt lõi, các guard cần thiết và benchmark; giữ input/policy/model version
để so B2 công bằng. Các bug đã chứng minh của main không được giữ làm đáp án
đúng của B1. Mỗi cải tiến có giả thuyết và kết quả đo, không chỉ thêm feature.
Lý do: có baseline hữu ích để học, thử nghiệm và chứng minh cải tiến chất lượng.

Git history/phản hồi BTC là phần hỗ trợ, không phải nghĩa chính của D18:
giữ history theo yêu cầu cuộc thi, không squash/force-push; stage/commit/push/
publish theo yêu cầu trực tiếp của người phát triển. Lưu scope/version khi
phản hồi BTC thay acceptance criteria; không tự khẳng định quyền Git mới.

## 5. Bundle đề xuất và thứ tự chốt

Bundle để review: policy công ty mô phỏng; ba nhóm chi D02; VND; rules theo
profile; React/TypeScript/Vite + FastAPI/Python; SQLite + local artifacts;
execution đơn giản và lịch sử đủ cho case/audit; Mistral/Kimi
theo adapter; source-aware facts và decision bằng code; issue/owner/human loop;
hai Verify suites và independent eval; adaptation có giới hạn.

Người phát triển đã nhận xét định hướng đề xuất phù hợp với điều kiện MVP;
chi tiết business rules/contracts vẫn cần chốt trong spec. Không diễn giải
điều đó thành đã duyệt mọi implementation detail hoặc đã có runtime.

Ưu tiên người phát triển chọn trước: D01–D06 (nghiệp vụ và quyền), D07–D08
(stack/storage tối thiểu), D11–D12 (control/demo boundaries), D15–D16 (nguồn lực
bên ngoài và bằng chứng). Các D09/D10/D13/D14/D17/D18 có thể dùng đề xuất làm
draft trong spec rồi review chi tiết.

Coding agent có thể tự xử lý file layout, naming, version pinning sau checks,
test structure và implementation details trong contract đã duyệt. Không giao
agent tự đặt company limits, authority, ground-truth labels hoặc người dùng
thật. Không cần người phát triển quyết định từng helper, SDK method hay CSS token.

## 6. Nguồn kỹ thuật đã đối chiếu 04/10/2026

- [React: build an app from scratch](https://react.dev/learn/build-a-react-app-from-scratch):
  Vite/TypeScript là một đường SPA; routing/data-fetching và nhu cầu framework
  vẫn cần được thiết kế. Không dùng nguồn này để nói React bắt buộc.
- [Streamlit: multithreading](https://docs.streamlit.io/develop/concepts/design/multithreading):
  thread/session context có ranh giới cần xử lý; không suy ra Streamlit không
  thể làm background workflow.
- [FastAPI: background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/):
  tác vụ có thể chạy sau response; khi cần nhiều process/server có trade-off
  với hệ thống job khác. Đây không phải cam kết persistence/recovery.
- [SQLite: appropriate uses](https://www.sqlite.org/whentouse.html):
  local storage/ít write concurrency phù hợp; một writer một thời điểm, nên
  topology và workload cần quyết định lựa chọn.
- [PostgreSQL: concurrency/MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html):
  cơ chế concurrency là căn cứ xem xét client-server DB khi topology yêu cầu.

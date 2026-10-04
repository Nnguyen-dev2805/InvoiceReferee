# InvoiceReferee — Yêu cầu cuộc thi và căn cứ triển khai lại

Ngày đối chiếu: 04/10/2026. Phạm vi: đề A, The Escalation Referee, bảng
OrganizationAI của MLAI Hackathon 2026; không gộp yêu cầu riêng đề B/C.

Nguồn gốc: [Challenge Brief](Challenge_Brief_OrganizationAI_VN.docx.md).
SHA-256: `33fbaba876e4b9392ba67f5503878a171db0032d68a8c19758d9d3a16c57a487`.
Đã xác nhận file gốc không thay đổi so với `main@196e266`.

Đây là requirement mapping và hướng thiết kế để thảo luận, không phải spec
implementation đã duyệt. Các ID A/S/C dưới đây do chúng ta đặt để theo dõi,
không phải AC ID của BTC. Phản hồi riêng của giám khảo đã được người phát
triển nhận nhưng nội dung chưa được cung cấp; khi có cần đối chiếu bổ sung.

## 1. Điều cuộc thi muốn sản phẩm chứng minh

Theo mục 1–2, hệ thống cần tự thực hiện công việc thường quy, biết dừng đúng
lúc, giải thích bằng dữ liệu và giữ quyền can thiệp của con người. Sản phẩm
phải chạy thực tế; kế hoạch hoặc kiến trúc đẹp không thay bằng chứng runtime.

Đề A tập trung vào cân bằng: xử lý hoàn toàn các case thường quy trong phạm
vi công bố, nhưng chuyển đúng case không đủ dữ kiện/ngoài policy/vượt quyền
với câu hỏi trả lời được. Không tối ưu để mọi case PASS hoặc mọi case đều
chuyển người. Case IDs và expected labels chỉ ở test, không ở production.

## 2. Yêu cầu Sprint 1 của đề A

| ID | Yêu cầu gốc và nơi đọc | Áp dụng cho InvoiceReferee | Bằng chứng nghiệm thu cần có |
| --- | --- | --- | --- |
| A01 | Quy trình cụ thể + tài liệu quy định; §2.A, dòng 47 | Phạm vi hồ sơ chi phí, điều kiện, quyền và kết quả tự xử lý được công bố | Rulebook có ví dụ trong/ngoài phạm vi; reviewer tra được căn cứ quyết định |
| A02 | Tự động xử lý case thường quy; §2.A, dòng 47,55 | Định nghĩa việc hệ thống được phép tự hoàn tất; chưa thể dùng OCR PASS thay approval | Case thường quy đi từ input tới hành động nghiệp vụ đã định nghĩa mà không cần bấm duyệt từng case |
| A03 | Ít nhất 15 trường hợp; §2.A, dòng 49 | Bộ case có cả rõ ràng, thiếu dữ kiện, ngoài policy, vượt quyền | Input/evidence, expected behavior, cách chạy, nguồn ground truth theo rulebook |
| A04 | Ba nhóm bất định; §2.A, dòng 51 | Factual unknown / outside policy / beyond authority, với căn cứ tương ứng | Kết quả và trace phân loại đúng; không chỉ có một bucket NEEDS_HUMAN |
| A05 | Câu hỏi chuyển tiếp cụ thể; §2.A, dòng 53 | Nêu vấn đề, dữ kiện đã có, thông tin hoặc quyết định còn cần | Người xử lý hiểu phải trả lời gì; rubric final ưu tiên trả lời mà không phải tra cứu lại toàn hồ sơ |
| A06 | Không khẳng định trên input bị gắn cờ nghi vấn; §2.A, dòng 57 | Không tự hoàn tất khi evidence quan trọng chưa dùng được hoặc issue chặn còn mở | Cases OCR/coverage/conflict cho ra hành vi an toàn; không chỉ test schema |
| A07 | Verify đề A: 5 case, 3 thường quy + 2 chuyển tiếp, một thao tác; §2.A, dòng 59 | Suite Escalation có kết quả, nhóm bất định và câu hỏi rõ | Chạy production path; kết quả thực sự khớp expected; không ép tỷ lệ bằng code theo case ID |

Ba nhóm là nguyên nhân nghiệp vụ, không phải ba mức confidence cao/vừa/thấp.
Một case có thể có nhiều issue; lỗi provider và cấu hình cần thể hiện riêng,
không giả vờ là một quyết định ngoài chính sách.

## 3. Yêu cầu Sprint 2 của đề A

| ID | Yêu cầu gốc và nơi đọc | Áp dụng cho bản viết lại | Bằng chứng nghiệm thu cần có |
| --- | --- | --- | --- |
| S01 | Tự động điều chỉnh ngưỡng chuyển tiếp từ phản hồi; §2.A, dòng 63 | Chốt tham số nào được điều chỉnh, feedback nào hợp lệ và phạm vi an toàn | Feedback được ghi nhận; hệ thống tự cập nhật tham số được phép; có before/after và version |
| S02 | Độ chính xác trên tập độc lập: bỏ sót chuyển tiếp, chuyển tiếp thừa; §2.A, dòng 65 | Tách dữ liệu điều chỉnh khỏi evaluation cuối | Tử số/mẫu số, nhãn theo rulebook, manifest, outputs và trace; không dùng PASS rate như accuracy |
| S03 | Ít nhất 3 nhân sự trực tiếp làm quy trình và một cải tiến từ phản hồi; §2.A, dòng 67; §4, dòng 201; §6, dòng 258 | Thử với nhân sự có vai trò thực tế, phản hồi của chính họ và sửa sản phẩm | Danh tính/chức danh được cung cấp theo yêu cầu BTC; nhận xét nguyên gốc; thay đổi có commit hoặc đối chiếu trước/sau |

Đổi `OCR_WORD_REVIEW_THRESHOLD` bằng tay chưa phải S01. Ngưỡng OCR cũng không
tự đồng nghĩa ngưỡng chuyển tiếp. Đây là lựa chọn thiết kế cần chốt. Feedback
không được tự đổi hạn mức company policy, quyền người duyệt hoặc bỏ hard gate
khi evidence bị nghi vấn. Cần đánh giá tác động trước/sau trên tập độc lập.

Người phát triển hiện chưa có người dùng chuyên môn để thử. Research công
khai hỗ trợ thiết kế nghiệp vụ và case; không thay S03 hoặc trở thành phản
hồi của 3 người đã sử dụng prototype. Có thể tìm hỗ trợ kết nối qua BTC/cố
vấn, nhưng chưa có hoạt động liên hệ hoặc bằng chứng thử nghiệm trong repo.

## 4. Các yêu cầu chung tiếp tục áp dụng

| ID | Yêu cầu gốc | Điều cần triển khai/chứng minh |
| --- | --- | --- |
| C01 | Live URL công khai, không cần tạo tài khoản/cài đặt, có hướng dẫn thao tác đầu tiên; §3.a, dòng 169 | Demo dễ tiếp cận với dữ liệu tổng hợp; thử runtime trên deployment thật |
| C02 | Verify chung: 4 case chạy tuần tự, một nút/lệnh, pass/fail + timestamp; có ít nhất một case đúng là từ chối/chuyển tiếp; §3.b, dòng 171 | Suite Core riêng với expected/actual; business NEEDS_HUMAN có thể là testcase PASS |
| C03 | Giám khảo nhập input mới, gồm case bất thường; §1–2, dòng 37; §4, dòng 199,220 | Cùng production path tiếp nhận input mới; không lookup đáp án theo filename/test label |
| C04 | Runbook từ clean clone tới chạy được; §3.b, dòng 171 | Các lệnh và cấu hình đủ tái lập; xác minh độc lập môi trường đang dùng |
| C05 | Người dùng truy lại đã làm gì, lúc nào, trên dữ liệu nào và vì sao; §1, dòng 19; §4, dòng 202 | Input/decision/policy identity và lịch sử đủ để giải thích một hành động bất kỳ |
| C06 | Can thiệp dừng và ghi đè hoạt động; §4, dòng 202; phiên sơ loại thử dừng/hoàn tác ở dòng 222 | Stop phải ảnh hưởng hành động thực tế; Override giữ được quyết định gốc, căn cứ và người can thiệp. Delete case không thay thế các control này |
| C07 | Public repo đủ history, không squash/force-push; §3.c, dòng 173 | Giữ lịch sử Sprint 1 và tiến trình rebuild; không tự thực hiện Git mutation chưa được người phát triển yêu cầu |
| C08 | 5 slide đúng cấu trúc, video tối đa 3 phút, build log 1 trang; §3.d–f, dòng 175–189 | Đúng gói bài nộp và chỉ báo cáo năng lực/bằng chứng thực có; chọn video dưới 3 phút để khớp rubric mục 4 |
| C09 | Đo tác động và nêu bất cập thực tế; §1, dòng 21; §4, dòng 201 | Tách thời gian làm việc/chờ, chi phí học dùng, burden kiểm tra lại, nguy cơ ỷ lại; không tự đặt số tiết kiệm |
| C10 | Công bố synthetic vs real; dữ liệu thật có phép và ẩn danh; §2, dòng 37; §6, dòng 258–260 | Slide 4 và dataset provenance ghi rõ; không dùng lời kể Reddit hoặc case tổng hợp như hồ sơ phỏng vấn |

Các điều kiện chung không phải tất cả là một bảng feature cần một framework
riêng; cần hành vi có thể biểu diễn và kiểm thử. Mục 4/C06 ghi rõ Stop và
Override; phần mô tả ban đầu/sơ loại còn nhắc hoàn tác. Nên định nghĩa tác
động và khả năng đảo/ghi đè trong đúng phạm vi hành động mà sản phẩm thực hiện.

## 5. Chấm chung kết và mốc bài nộp

Mục 4, dòng 225: chung kết 20 phút, **45 điểm demo + 35 điểm phản biện + 20
điểm kiểm thử đề bài**. Không áp nguyên bảng 40/20/20/20 của sơ loại làm bảng
điểm final. Đề không mô tả chi tiết phân bổ con của 45/35; không tự suy ra.

20 điểm đề A, §2.A dòng 75–81:

- 8 điểm: phát hiện đúng hai trường hợp cần chuyển tiếp và phân loại đúng.
- 6 điểm: ba case thường quy không bị chuyển tiếp sai.
- 6 điểm: câu hỏi cụ thể, đủ căn cứ để người xử lý quyết định.

Giám khảo cung cấp **5 case mới** dựa trên rulebook, khoảng 2 cần chuyển tiếp.
Suite 5 case chuẩn bị trước không chứng minh xử lý được năm case mới này.

Theo lịch trong file gốc, §5 dòng 241–242: **khóa bài nộp 15/10; Demo Day
17/10**. Đây là mốc từ bản đề trong repo, chưa đối chiếu thông báo riêng mới
hơn. Không để mọi hoạt động phát triển dồn tới 17/10.

Gói 5 slide (§3.e):

| Slide | Nội dung |
| --- | --- |
| 1 | Vấn đề và quy trình hiện trạng |
| 2 | Input -> xử lý -> output và vị trí con người quyết định |
| 3 | Tác động trước/sau và phương pháp đo |
| 4 | Kiến trúc/triển khai; real vs simulated |
| 5 | Giới hạn, rủi ro, failure cases và cách xử lý |

## 6. Đối chiếu với baseline main và rebuild

Baseline: `main@196e266`; căn cứ [source review](reviews/main-baseline-196e266/MAIN_BASELINE_REVIEW.md)
và [architecture assessment](reviews/main-baseline-196e266/ARCHITECTURE_ASSESSMENT.md).
Rebuild hiện mới có tài liệu, chưa có implementation.

Theo làm rõ mới của người phát triển: main là tham chiếu B0; MVP viết lại
đủ đúng/hiệu quả sẽ thành baseline B1 để so các cải tiến B2. Scope là một app
MVP, không có yêu cầu production nhiều user, tenancy hoặc scale-out. Các yêu
cầu cuộc thi về chất lượng, human controls và bằng chứng vẫn được giữ.

| Yêu cầu | Main có gì dùng lại? | Khoảng cách cần giải quyết |
| --- | --- | --- |
| A01–A02 | OCR/quality/inventory checks và decision bằng code | Rulebook hoàn ứng, quyền và hành động nghiệp vụ tự hoàn tất; quality PASS chưa đủ |
| A03 | Các fixture/test và tài liệu research có 15 case candidates | Dataset nghiệp vụ chính thức có evidence và expected độc lập; chưa khẳng định số case main đủ yêu cầu |
| A04–A06 | Findings, câu hỏi và các nhánh dừng | Ba nhóm, lỗi kỹ thuật riêng, quality coverage, refs và field contract; sửa F01–F04/A01 đã tái hiện |
| A07/C02 | Verify gọi production service, store riêng | Hai suite, expected/actual, testcase pass/fail, timestamp và Core tuần tự; giữ các run thay vì xóa hết |
| C03 | Main nhận claim và file mới | Evidence correctness trên input mới; tránh skip inventory biến thành toàn case PASS |
| C05–C06 | Case/evidence/processing files và audit cơ bản | Runs/input/policy identity, Stop/Override; chưa có human answer/resume |
| S01 | OCR threshold cấu hình | Feedback loop và auto adaptation chưa có |
| S02 | Selected fake suite đã kiểm chứng | Independent eval về chuyển tiếp chưa có |
| S03/C09 | Research để khám phá vấn đề | User trial/feedback/impact thực tế chưa được cung cấp |
| C01/C04/C08 | Cấu trúc UI/README/docs cũ làm tham khảo | Deployment/runbook và gói bài nộp V2 cần tạo và xác minh; trạng thái baseline deployment không suy ra từ source |

## 7. Yêu cầu bắt buộc và lựa chọn thiết kế khác nhau

**Đề bài yêu cầu hành vi:** tự xử lý thường quy; ba nhóm bất định; câu hỏi;
Verify; input mới; audit/can thiệp; adaptation; independent eval và người dùng.

**Đề không bắt buộc:** tên enum AUTO_PROCESS/REQUEST_INFO/ESCALATE, Mistral/Kimi,
RAG, database, nhiều agent, microservice, một `review()` API hoặc nhập JSON
thay vì file/form. Các tên action hay phương án kỹ thuật là lựa chọn của ta.

**Đề xuất của chúng ta:** extract có provenance, profile-specific checks,
decision coverage, issue có owner/closure, human response -> reevaluate và
run history. Đây là cách phục vụ các yêu cầu, không phải câu chữ spec gốc.
Đặc biệt reply/resume và immutable runs là lựa chọn triển khai; không nói đề
bắt buộc một UI reply hay một framework append-only cụ thể.

## 8. Flow mục tiêu để thảo luận

```text
Policy và phạm vi quyền đã công bố + hồ sơ mới
  -> dữ kiện có nguồn và quality/coverage
  -> các check áp dụng: consistency + eligibility + authority
  -> thường quy: thực hiện hành động tự động được giao và lưu căn cứ
  -> thiếu dữ kiện: hỏi người có dữ kiện với câu hỏi cụ thể
  -> ngoài policy: chuyển người quyết định ngoại lệ
  -> vượt quyền: chuyển đúng cấp phê duyệt
  -> human action -> đánh giá lại phần bị ảnh hưởng, giữ lịch sử
  -> Stop/Override có hiệu lực ở các điểm hành động đã định nghĩa
```

Hành động tự động phải là một kết quả nghiệp vụ thực trong phạm vi prototype
đã công bố; chỉ đổi màu badge PASS không đủ chứng minh A02. Đề không yêu cầu
mặc định tích hợp ngân hàng, nên có thể chốt ranh giới khác nếu giải thích rõ
công việc được tự hoàn tất, điều còn do con người/hệ thống khác thực hiện.

## 9. Thứ tự triển khai đề xuất từ yêu cầu

1. Chốt quy trình chi phí hẹp, rulebook mô phỏng, authority và hành động
   routine được phép tự hoàn tất; giữ inventory main làm profile khi áp dụng.
2. Viết case expectations cho routine/factual/policy/authority trước khi code;
   8 baseline cases hiện có cần mở rộng để có đủ các nhóm nghiệp vụ.
3. Thiết kế contract và một vertical slice: submit -> decision -> human action
   -> reevaluate; đóng quality/source gaps, lưu identity và runs ngay từ đầu.
4. Dựng Core/ Escalation Verify cùng production path; input mới, Stop/Override
   và giải thích được từ audit.
5. Bổ sung feedback adaptation có giới hạn và independent evaluation.
6. Song song giải quyết tiếp cận người thử thực tế; sau phản hồi có một thay
   đổi và báo cáo tác động/bất cập thật. Không đợi code xong mới tìm người thử.
7. Xác minh live deployment/clean-clone runbook, hoàn thiện 5 slide, video,
   build log và diễn tập input mới/phản biện trước mốc khóa bài.

Đây là định hướng, chưa phải implementation plan hoặc cam kết rằng mọi gap
đã đóng. Các source code/diagram baseline mô tả main; yêu cầu cuộc thi mô tả
đích cần chứng minh; giữ hai loại tài liệu phân biệt trong mọi báo cáo.

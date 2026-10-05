# B1 — Evaluation và nghiệm thu baseline MVP

Version 0.1, 04/10/2026. **DRAFT — protocol để review, chưa có kết quả B1**.
Nguồn: [Product](B1_PRODUCT_SPEC.md), [Rulebook](B1_RULEBOOK.md),
[System](B1_SYSTEM_SPEC.md), [cuộc thi](../COMPETITION_REQUIREMENTS.md).

## 1. Ba mức bằng chứng

- POLICY_REPLAY: cùng declared/factual inputs chuẩn hóa, kiểm tra evaluators
  và decision; không chứng minh OCR/provider/UI.
- PIPELINE_FAKE_OR_REPLAY: application flow với fake adapters hoặc OCR/model
  artifacts có identity, kiểm tra quality/source/human/actions; công bố mode.
- LIVE_END_TO_END: document mới qua adapters thật, lưu provider/prompt/model
  và trace; không suy ra live quality từ fake suite.

UI và Verify dùng cùng application/decision logic; expected labels chỉ trong
evaluation runner. Case ID, tên happy/unhappy hoặc expected action không được
đưa vào production branching hoặc prompt như đáp án cần đạt.

Rulebook proposal 2/5 triệu có thể được nạp thành fixture active **chỉ cho
test mô phỏng**, ghi rõ `policy_origin=proposed_test_fixture`. Điều này không
coi hạn mức đã được người phát triển duyệt cho demo live.

## 2. Manifest và dataset

Mỗi case: opaque case ID, description, profile, Claim input, evidence paths/
hashes/roles, evaluation reference date nếu cần, policy version, expected
execution/action/issue classes/owner/checks/amount/request count và lý do.
Gold answers từ rulebook/extraction ground truth riêng, không do production
rule tự chạy rồi ghi thành expected.

Datasets được gắn nhãn synthetic hoặc real có quyền dùng. Image/PDF và OCR/
fact ground truth liên quan được giữ cùng source identity; không coi 15 dòng
scenario research là đã có 15 execution fixtures hoàn chỉnh.

Ba tập khác nhau:

1. Development/acceptance corpus: >=15 cases và các regression probes.
2. Feedback/calibration set đề xuất: 12 cases (4 routine, 4 factual, 2 outside
   policy, 2 authority), dùng khi làm adaptation B2.
3. Held-out evaluation đề xuất: 20 cases (6 routine, 6 factual, 4 outside policy,
   4 authority). IDs/documents/labels không dùng để tune prompt/rule/
   threshold; khóa manifest trước thử nghiệm. Không suy ra independence chỉ
   bằng việc đổi tên cùng một document.

Đề không chỉ định size holdout; 12/20 là proposal của project, không phải số
BTC yêu cầu hoặc số case đã tạo. Mọi báo cáo ghi numerator/denominator và
giới hạn mẫu, chưa đặt target accuracy chưa có dữ liệu. Nếu dùng lỗi holdout
để sửa hệ thống, ghi tập đó đã trở thành development evidence và tạo/khóa
holdout mới; không gọi phép chấm lại trên cùng tập đã tune là independent.
Tách capability chung và capability mới khi so các version.

## 3. 15 case nghiệp vụ đầu tiên theo proposal rulebook

Toàn bộ là **synthetic proposed cases**. Các input không nêu vấn đề đặc biệt
có source/quality/context đầy đủ và điều kiện còn lại hợp lệ.

| ID | Tình huống | Expected cốt lõi |
| --- | --- | --- |
| TC01 | TRAVEL 1.200.000đ, PERSONAL, đủ purpose/bill | CREATE_PAYMENT_REQUEST; ROUTINE_AUTO; amount 1.200.000; một request |
| TC02 | CLIENT_MEAL 1.800.000đ, đầy đủ purpose | Routine amount 1.800.000; không đòi report kho |
| TC03 | WORK_PURCHASE 900.000đ; bill/receipt khớp, nhận đủ | Routine amount 900.000; inventory checks thật sự chạy |
| TC04 | Claim có nội dung nhưng không primary bill | REQUEST_INFO; FACTUAL_UNKNOWN; EMPLOYEE; zero request |
| TC05 | Original image có total rõ nhưng OCR/quality chưa đủ căn cứ; cần reviewer xem ảnh | REQUEST_INFO; FACTUAL_UNKNOWN; REVIEWER; zero request trước confirmation |
| TC06 | Bill 1.280.000đ, requested 1.480.000đ, chưa có căn cứ phần chênh | FACTUAL_UNKNOWN/AMT-01; hỏi EMPLOYEE về 200.000đ; không tự chọn min/max |
| TC07 | TRAVEL có bill rõ nhưng thiếu khai báo chuyến đi | REQUEST_INFO tới EMPLOYEE, nêu thông tin thiếu; không hỏi lại field đã rõ |
| TC08 | OTHER: chi phí không thuộc catalog B1 | ESCALATE; OUTSIDE_POLICY; APPROVER phân loại/deny, chưa tạo request |
| TC09 | Khai báo xác định PERSONAL_PURPOSE, không chi cho công việc | REJECT ELIG-01; zero request; không dùng tên hàng làm căn cứ duy nhất |
| TC10 | Case hợp lệ đúng 2.000.000đ | Routine auto; inclusive boundary, một request |
| TC11 | Case hợp lệ 2.000.001đ | ESCALATE; BEYOND_AUTHORITY; APPROVER; zero request trước approval |
| TC12 | Case hợp lệ đúng 5.000.000đ | APPROVER; amount approval riêng trước khi tạo request |
| TC13 | Case hợp lệ về dữ kiện, amount 5.000.001đ | BEYOND_AUTHORITY; APPROVER; amount approval riêng chưa đóng |
| TC14 | Bill quantity 10, receipt 8; chưa giải quyết conflict | FACTUAL_UNKNOWN/INV-02; refs hai nguồn, zero request |
| TC15 | Model trả ID thừa/trùng hoặc source không tồn tại sau bounded repair | Technical FAILED/NONE, zero request; không gán lỗi model thành policy violation |

TC05 có ground truth trên ảnh gốc và reviewer confirmation sequence riêng;
missing/upload source là fixture khác do EMPLOYEE bổ sung. Không chấp nhận
expected owner “ai cũng được” khi tạo fixture chính thức.

## 4. Hai suite Verify

- **Core 4:** TC01, TC03, TC04, TC11; chạy tuần tự, một button/command, ít
  nhất một case đúng là human. Expected refusal/human vẫn có thể test PASS.
- **Escalation 5:** TC01, TC02, TC03, TC06, TC11: 3 routine + 2 human, có nhóm,
  source, câu hỏi và owner. Không ép tỷ lệ trên inputs khác ngoài suite này.

Mỗi result: run ID/timestamp, policy/input versions, mode, expected/actual,
test PASS/FAIL/INCONCLUSIVE, elapsed time, request count và trace location.
Actual business status không được dùng như test verdict.
Technical failure ngoài expected làm testcase FAIL; intentionally expected
technical case như TC15 có thể test PASS. Trace giữ nguyên các runs cũ.

## 5. Regression từ B0 và contract probes

Giữ input/output B0 để tham khảo, dùng desired behavior B1 từ spec:

- Empty OCR, missing scores và unassigned required words: không quality auto-pass.
- Duplicate item IDs: không overwrite/mất dòng rồi consistency PASS.
- Block refs: resolve được khi có thật, reject khi không có registry entry.
- 1 kg × 1000/kg và 1000 g × 1/g: không báo chênh do khác unit basis.
- Inventory N/A: không miễn eligibility/authority của whole case.
- 2 × 100 = 1: consistency có thể khớp, arithmetic áp dụng vẫn chặn.
- UNREADABLE total + requires_verification=false: invalid/contradictory analysis,
  không approve bằng boolean thuận lợi.
- Signed return/credit/FX input: không tự áp dụng normal-purchase math hoặc đổi
  currency/dấu để thành case eligible.

Corpus có thêm human-loop/control cases: correction đúng, correction chưa đủ
nguồn, approval sai mode/scope, changed amount invalidates approval, exception
chưa có approval, bấm chạy lại, Stop khi provider chờ, late output, Override
và decision gốc, technical provider failure và metadata missing/config draft.

## 6. Metrics và reporting

| Metric | Định nghĩa |
| --- | --- |
| Wrong routine automation | Case không đủ điều kiện/authority nhưng có routine payment request / tổng routine requests |
| Missed escalation | Case cần human mà hệ thống tự hoàn tất / tổng case cần human |
| Unnecessary escalation | Case routine bị chuyển human / tổng routine cases |
| Class/owner correctness | Human cases có đúng issue class và owner / tổng human cases đủ nhãn |
| Amount correctness | Requests có amount/breakdown đúng / tổng requests tạo |
| Source correctness | Ref/value resolve đúng ground truth / tổng required facts được kiểm tra |
| Closure correctness | Human action chỉ đóng đúng issues và tạo action khi đủ điều kiện / tổng human sequences |
| Technical failure | Số lỗi execution, stage/reason, trên tổng attempts; giữ riêng khỏi business classification |
| Runtime/cost | Duration theo stage/run, call/repair/token và provider mode/cache identity nếu có |

Không loại technical failures để làm metric đẹp: báo coverage/denominator và
end-to-end success của toàn suite, đồng thời business metrics trên tập có nhãn
phù hợp. Không dùng model tự-rated confidence như tỷ lệ chính xác đo được.

Release acceptance: expected cases/regressions đều đạt, zero unintended
request trên fixed safety suite, đúng boundary amount/owner, Stop/Override
và human closure đúng. Đây không chứng minh zero error trên mọi dữ liệu mới.

## 7. B1 và B2

B1 được ghi nhận baseline khi core workflow có wiring/execution evidence,
policy/spec versions chốt và benchmark inputs/outputs/trace được khóa.
Các cải tiến B2 so cùng common input/ground truth; capability mới được báo
riêng, không dùng việc B0/main không có capability đó làm bug regression.

Feedback adaptation cần provenance, tham số được cho phép, version/before-
after và evaluation trên holdout. Không tự chỉnh policy limits/authority hoặc
tune trên case final vừa dùng để chấm; freeze policy/threshold trong một run.

Thử với 3 nhân sự nghiệp vụ là user evidence riêng. Agent hoặc người phát
triển tự đóng vai chỉ tạo simulation/technical evidence. Ghi feedback gốc,
thay đổi từ feedback và bất cập; không lấy benchmark simulation thay trial.

## 8. Chốt và triển khai

Rulebook values, templates, fixture sources và held-out protocol cần review
trước khi plan activation và live tests. File này định nghĩa phép chứng minh;
chưa có fixture B1 đầy đủ, kết quả metric mới hoặc user trial nào được tạo
trong lượt viết spec.

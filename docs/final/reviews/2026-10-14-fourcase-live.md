# Bốn case LIVE — F02/F03 công tác và Hoangha TC08/TC23

Ngày14/10/2026. **Hai case công tác đạt kết quả tiền mong đợi. Hai case Hoangha
chuyển người/chặn instruction đúng ở bước đầu, nhưng còn lỗi dữ kiện tài chính
TC08 và định danh khoản chi TC23. Không kết luận4case hoàn toàn PASS.**

## Phạm vi và danh tính test

- Đóng băng package từ working tree `final` lúc bắt đầu; HEAD `0b205420bfd3b4ce41e8739a1a701798a805bca1`. Snapshot bao gồm thay đổi backend agent đang làm và nằm dưới `.runtime/fourcase-live-20261014-155735/snapshot/src`.
- Source bytes/hash và snapshot hashes được ghi vào identity.json, kiểm lại cuối run không đổi. Không sửa PDF, input org corpus hoặc application source.
- LIVE Mistral OCR + configured X-Kiro `qwen/qwen3.7-flash:free`, không native-PDF text bypass, không dùng gold/expected.json/mapping trong ứng dụng/model.
- Context tài chính SIMULATED; clock harness công khai10/10/2026 18:00+07. Actual advance là fixture riêng, không suy từ paper.
- F02/F03 dùng nguyên `input/organization.json`; employee-confirmation.json không được gửi, invoice demo basis phải tự bind đúng nhân viên.
- TC08/TC23 dùng context độc lập theo cùng rulebook: company/person/activity đúng; advance4m/9m, coverage đủ; TC08 B8m, TC23 B12m. System recognize8m/issue4m; grant approver TC23≤20m, không cấp system8.64m để ép AUTO.
-4case trong4database riêng. Chạy hai lượt song song một lần để hạn chế concurrency provider. Không reset/write user DB, không thực hiện tiền, không commit/push/subagent.
- Đã render và nhìn đủ9PDF trước run. Mong đợi từ nguồn/số học/policy được viết trước run trong independent-expectations.json.
- CodeGraph up-to-date với cảnh báo engine cũ; tool coverage Codebase Memory không expose, coverage UNKNOWN. Source liên quan đã đọc; không audit toàn repo.
- Browser/UI, vòng phản hồi/approval/actual-payment sau trạng thái ban đầu, full25-case suite: NOT_RUN trong lượt này. Không kết luận luồng UI agent chưa bàn giao đã đúng.

## Kết quả đầu tiên

| Case | T/E | A | S | Route/effect thực tế | Gate ban đầu | Giây |
|---|---:|---:|---:|---|---|---:|
| F02 — công tác chi thêm |5.400.000|5.000.000|+400.000|READY_TO_EXECUTE; PAY400000, no issues|PASS|68.117|
| F03 — công tác cân bằng |4.320.000|4.320.000|0|SETTLED; no instruction, no issues|PASS|56.739|
| TC08 — giấy/hóa đơn lệch |3.500.000 được đánh KNOWN, xem finding|4.000.000|−500.000 được đánh KNOWN|WAITING; FACT employee về allocation; no instruction|PASS riêng chặn/chuyển người|76.376|
| TC23 — split một hóa đơn |8.640.000|9.000.000|−360.000|WAITING; AUTHORITY approver/RECOGNIZE_COST; no instruction|PASS riêng số tiền/quyền|105.718|

F02 chỉ tạo yêu cầu chi, chưa chứng minh công ty đã chi400k. F03 không có nghĩa vụ
tiền mới theo history fixture, nên được SETTLED trực tiếp mà không tạo request0.

## Đầu vào và logic từng case

### F02

`data/test-kit/uc03-pilot/f02-cong-tac-cong-ty-chi-them/input/`:
giấy công tác06–10Oct, invoiceIR26101002 lodging5.4m, claim Nguyễn An. Company
ledger fixture advance5m. Pipeline giữ TRAVEL, đọc đủ destination/start/end,
buyer-person đúng Nguyễn An, total5.4m và tax400k. S=400k, trong quyền.

### F03

`data/test-kit/uc03-pilot/f03-cong-tac-can-bang/input/`:
giấy công tác06–10Oct, invoiceIR26101003 lodging4.32m, advance fixture4.32m.
Pipeline đọc đúng trip/name/amount; S0, không có issue/execution còn mở.

**Giới hạn context:** các organization.json pilot hiện không có category_policies
versioned; category_policy count trong AssessmentInput là0. Hai lượt này chứng minh
trip/source/payment arithmetic/B/grants/history ở fixture đã dùng, không chứng minh
gate category/deadline30days của policy mở rộng. Cần bổ sung fixture/gate riêng nếu
muốn gọi toàn bộ rulebook mới được test; không tự sửa corpus trong lượt điều tra.

### TC08

`data/tham-khao/uc-03/tc08-bao-cao-va-hoa-don-lech-so-tien/`:
paper row/total3.5m, invoice00000801 total3.24m, lệch260k. Paper printed return500k
khớp chính số3.5m nhưng chưa giải quyết invoice. Hệ thống có gọi suggestion LLM
bổ sung một lần; admission vẫn phát hiện allocation3.5m>source3.24m.

Câu hỏi thực tế owner employee, basis "Tổng phân bổ3500000 vượt tổng chứng từ3240000".
Không có issue thiếu B/payer/coverage che lỗi và không instruction.

**Finding P1 — tiền tranh chấp vẫn thành tiền đủ điều kiện đã xác minh:**

- Expense.incurred=KNOWN3.5m, eligibility=ELIGIBLE, ExpensePayment.amount3.5m.
- Projection T=E=KNOWN3.5m, S=KNOWN−500k, dù source invoice chỉ3.24m và issue đang OPEN.
- `admit_evidence` thêm allocation issue (615–641 tại snapshot) nhưng vẫn tạo
  employee-paid portion bằng row amount (749–764) và KNOWN incurred (800–817).
- Reconciler suppress effect vì issue, nhưng projection/consumer UI vẫn có thể
  gọi3.5m là chi phí đủ điều kiện đã xác minh. Chặn chi/thu đúng chưa đóng lỗi false-known.

Fix theo contract: giữ declared/proposed amount riêng; portion/eligibility/incurred
đang tranh chấp không được nâng KNOWN/ELIGIBLE. Không cắt âm thầm xuống3.24m hoặc
chọn3.5m. FACT giữ source refs/values/difference; sau correction có căn cứ mới
đánh giá lại. Test UNKNOWN E/S và no effect, cùng positive partial-allocation cases.

### TC23

`data/tham-khao/uc-03/tc23-hop-le-mot-hoa-don-phan-bo-cho-nhieu-dong/`:

- Invoice00002301 backs rows2.16m+1.08m=3.24m.
- Invoice00002302 backs separate row5.4m.
- Total E8.64m, advance fixture9m, S−360k. B12m đủ, nhưng E vượt system recognize8m.
-3expense rows giữ đúng amounts, không nhân total3.24m cho mỗi row; no FACT;
  AUTHORITY RECOGNIZE_COST tới approver, no COLLECT360k trước quyết định.

**Finding P1 — identity của invoice thứ hai bị gán thành invoice thứ nhất:**

Admission gán cả3expenses `economic_key=invoice:CÔNG TY TNHH VĂN PHÒNG PHẨM HÒA BÌNH:00002301`.
Hai row đầu chung key là hợp lý, nhưng row mực in5.4m thuộc invoice00002302 phải có
key riêng. `_economic_key(report, refs, index)` (873–884) bỏ qua refs/document của
expense và trả invoice đầu tiên của report cho mọi row.

Fix: derive canonical issuer/number identity từ document thực sự bound vào
expense; retain allocation identity và source refs. Test2rows/1invoice chungkey,
invoice thứ hai kháckey, source order independence và economic-usage boundary.
Lượt này chưa chạy second root/TC12; không khẳng định đã tái hiện cross-root double
payment, nhưng identity collision trong chính input TC23 đã được xác nhận.

## Assertions và giới hạn verdict

Private `test_observed_results.py` chấm saved artifacts mới, không gọi provider lần
hai, không thay cho full product regression:

-4business-gate assertions PASS: expected money/effect/state hoặc exact owner/route/no instruction.
-2post-run deeper integrity checks FAIL: TC08 E không UNKNOWN, TC23 invoice key collision.
-Command exit1, **4passed/2failed**. Không gọi4gate ban đầu là4case fully PASS.
- Source/snapshot hashes kiểm cuối run đều nguyên.

Mong đợi routing/amounts viết trước run; hai integrity checks là findings phát hiện
sau khi đọc evidence, không giả thành một frozen suite đã có từ trước.

## Bằng chứng và lệnh

Thư mục `.runtime/fourcase-live-20261014-155735/`:

- `identity.json`, `independent-expectations.json`, `score.json`, frozen snapshot và run_case.py.
- Mỗicase: ảnh render, context.json, report.json, view.json, result.json,
  admission-input.json, audit.json, stages.jsonl, raw OCR artifacts và DB riêng.
- Result chứa provider/model/origin/clock/seconds/module path; không chứa credential.
- Lệnh cho mỗicase:
  `rtk proxy env PYTHONPATH=<evidence>/snapshot/src uv run --no-sync python <evidence>/run_case.py F02` (F03/TC08/TC23 tương tự): cả4exit0, job ran; exit0 không là toàn bộ safety PASS.
- Assertions:
  `rtk proxy uv run --no-sync pytest <evidence>/test_observed_results.py -q -p no:cacheprovider` → exit1,4passed/2failed.

Không sửa code/DB người dùng. Next: integrator xử lý false-known projection và
source-bound economic identity cùng regression; giữ F02/F03 và TC23 authority
gate. Rerun trên revision đã bàn giao, sau đó mới kiểm browser/vòng phản hồi.

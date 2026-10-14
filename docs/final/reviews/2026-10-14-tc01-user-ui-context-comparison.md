# TC01 trên web người dùng — khác biệt với lượt test độc lập

Ngày14/10/2026. Đã kiểm API backend thật tại127.0.0.1:8000 và đọc SQLite bằng
connection `mode=ro`; không sửa hồ sơ/context/money hoặc chạy provider lại.
GET demo session tạo phiên quan sát mới; không chuyển persona hay gửi mutation command.

## Danh tính quan sát

- Checkout clean, HEAD `96e7b888424b9d02169ba69dc2da69f2f55aa1d0`.
- Process PID32305, started14Oct16:32:53 local, command `scripts/dev.py --host127.0.0.1 --port8000`.
- Health LIVE/live_ready=true. Runtime DB `.runtime/invoice-referee.sqlite`.
- Default context file `data/demo/company-context.json` SHA256:
  `296954958c4db388eb2b49bf1ea33b1cf0ce4e23884c20ad74779b0bd7335fdb`;
  đúng digest backend báo đã import, không đoán từ file hiện có.
- Target `case:11a8bf493b51386c3afb`, v3/WAITING.
- Source invoice digest `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019`,
  paper digest `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c`:
  đúng2PDF TC01 của lượt test trước.
- CodeGraph up-to-date/earlier-engine warning; coverage tool không expose, UNKNOWN.
  Đã đọc load_context, invoice_binding và submit/intake consumers liên quan.

## Căn cứ từ API/DB

| Mục | Lượt test độc lập ra COLLECT760k | Web người dùng |
|---|---|---|
| Activity | activity:tc01, tiếp khách dự án, có context | activity:proposed:a27e6f11931b4080a572a66f7f0dd601 |
| Profile | WORK_EXPENSE | WORK_EXPENSE |
| Person context | NGUYỄN MINH AN | Tài khoản demo Nguyễn Văn A |
| Scoped company_name | Công ty An Thịnh | Snapshot default company_name=null |
| B |8m riêngactivity:tc01 | Không record B cho activityproposed |
| Advance | fixture confirmed4m | money_events của root=[]; context ledger=[] |
| Coverage | đủ, đến10Oct18:00 | null |
| Clock |10Oct18:00+07 harness |14Oct16:34:57+07 server |

Snapshot default chỉ chứa các activity:travel-a..travel-g,5budgets cho những
activity đó. Nó không chứa activityproposed của case. `load_context` chỉ trả
snapshot chứa đúng activity; ở case này kết quả None. Admission nhận organization
fallback chỉ có organization_id, không person/company/budget/ledger/coverage của
activity. Đây là nguyên nhân trực tiếp3FACT, không phải3PDF bị thiếu.

Nguyễn Văn A vs Nguyễn Minh An là một khác biệt danh tính khác phải giải quyết
trong thiết lập test/binding hợp lệ. Gate hiện chưa báo mismatch cụ thể vì scoped
context đã bị thiếu ngay từ đầu. Không tự alias hai người hoặc sửa tên account để
né xác minh trong vận hành thật.

Case declaration đã persist: confirmed declared_name NGUYỄN MINH AN, declared
advance4m, incurred_total3.24m, purpose tiếp khách. Activity vẫn PROPOSED sau submit.
Intake preselects catalog by exact purpose/name; không có mục phù hợp thì giữ NEW
activity của draft. Submit cho phép giữ hoạt động mới PROPOSED và chưa cấp B/quyền
hoạt động. Vì vậy account/corpus/context hiện chưa là một bộ test web TC01 nhất quán.

## Kết quả user case

OCR invoice và paper đều CLEAR; invoice total3.24m, paper name đúng NGUYỄN MINH AN,
paper advance4m. Invoice không có buyer_person_name và buyer_company=An Thịnh.

- TKNOWN3.24m; E/A/P/R/SUNKNOWN; no instruction.
- FACT expense:payer owneremployee.
- FACT budget:B ownerorg-data.
- FACT ledger:coverage owneraccountant.

Giữ tiền chưa biết và chặn instruction là đúng với dữ liệu còn thiếu. Tuy nhiên
generic payer question không diễn đạt đúng vấn đề gốc: thiếu binding người/công ty/
activity/context. Nó không tự chứng minh người dùng phải nộp thêm supplier-payment
receipt sau khi đã chốt invoice demo basis.

## Probe xác nhận nguyên nhân (không mutation)

Lấy **chính ReadResult của user case**, đưa vào admission/Reconciler pure với
context TC01 độc lập của lượt trước, đúng activity/person/company/B/history và
clock công khai10Oct18:00. Không gọi OCR/LLM mới, không update user DB, không
commit effect của probe.

Result: issues=[], E3.24m, A4m, allowed_effect=COLLECT760000. Cùng facts gốc có thể
cho760k khi được bound tới đúng context. Probe không chứng minh tiền công ty thật
hay server14Oct đã có coverage; không chuyển kết quả này vào hồ sơ người dùng.

## Kết luận và bước tiếp theo

Test trước chứng minh source→finance với fixture đầy đủ, **không** chứng minh
default web setup tự có TC01. Hai lượt khác nhau về context/activity/account/clock,
không về bytes PDF. Không sửa logic để bỏ3FACT hoặc mặc định A4m từ giấy.

Cần một demo/test setup TC01 portable có company/person/activity/profile/B/grants
phù hợp, cùng lựa chọn có ứngrecord/khôngứngrecord; importer và activity binding
phải đưa đúng dữ liệu vào admission. Global company/person identity cần được
giải quyết rõ, không mất chỉ vì thiếu một activity snapshot. Với nhánh thiếu ứng,
kế toán upload/confirm qua luồng hiện có; lịch sử/coverage cần đúng thời điểm test.
Sau đó nghiệm thu lại từ **lệnh khởi động chuẩn + browser** trong môi trường test
riêng. Không dùng old coverage10Oct để giả nó còn bao phủ14Oct.

## Bằng chứng

`.runtime/tc01-user-ui-20261014-164127/` gồm api-case.json, session-public.json
(không lưu session cookie), db-readonly.json và same-user-report-matched-context.json.
Observed state được lưu, không coi đây là authoring gold hoặc toàn bộ branch audit.
Không application fix/reset/git/provider run trong lượt giải thích này.

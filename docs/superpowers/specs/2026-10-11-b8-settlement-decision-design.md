# B8 — Trình và duyệt quyết toán

Ngày 11/10/2026. **PLANNED**. Đây là thiết kế mở B8 cho hồ sơ
`b7-linked-intake-v1`, tiếp nối [B6–B7](2026-10-11-b6-linked-settlement-design.md).
[Product](../../settlement/PRODUCT.md), [Rulebook R7–R10](../../settlement/RULEBOOK.md)
và [System S3/S6/S7](../../settlement/SYSTEM.md) là contracts áp dụng.

## 1. Phạm vi và lựa chọn

Kế toán rà soát report hiện hành, trình người duyệt được cấu hình. Người duyệt
phê duyệt toàn bộ kết quả có căn cứ, trả lại để làm rõ hoặc từ chối đề nghị.
Không chuyển tiền, không ghi receipt, không đóng hồ sơ trong B8.

Chọn lifecycle typed riêng cho linked B7, dùng tám bảng SQLite hiện có và
audit tương tự B3 presentation. Không mở generic decision/money/closure bằng
cách xóa `LINKED_B7_REPORT_ONLY`. Generic W05 vẫn bị chặn trên linked B7;
dedicated endpoints có guards của B8/B9. Legacy B7 giữ đường hiện tại và không
được dùng làm bằng chứng rằng lifecycle mới đã đạt acceptance.

Hai phương án không chọn: thêm nút vào generic decision hiện có bỏ qua
presentation/quality gates; hoặc dựng workflow engine/table/service mới.
Phương án đầu thiếu bảo vệ nghiệp vụ, phương án sau không cần cho MVP năm người.

## 2. Điều kiện B6–B7 trước khi mở hành động

Implementation report-only hiện có không tự là nghiệm thu. B8 task đầu phải
kiểm tra và sửa trong phạm vi liên kết: coverage đúng employee/work, khoảng
thời gian/method/group/opening, refs mở được; B5 actual + company ledger
được hợp nhất theo economic event và không cộng hai lần; pending/unknown
không bị bỏ qua thành zero; forecast không actual; source date/known time
không vượt snapshot mà vẫn đóng góp vào kết quả.

`build_linked_context` hiện tính history từ packet theo groups và complete flag;
`linked_context_observations` hiện dựng một số source IDs/links từ context.
Đây là các điểm cần chứng minh bằng tests source-backed, không mặc định PASS
từ tên hàm/checkbox. Đầu ra phải giữ issue khi thiếu căn cứ, không patch gold
hoặc đặt report COMPLETE trong fixture để bypass pipeline.

## 3. Các hành động

| Hành động | Vai và điều kiện | Kết quả |
| --- | --- | --- |
| Lưu rà soát | Kế toán đúng route; current report/scope/refs | REVIEW, không phê duyệt |
| Trình quyết toán | Kế toán đúng route; intake đã confirm; report COMPLETE; không material issue/Stop/stale | Presentation gắn report + review + basis signature + route |
| Phê duyệt | Người duyệt đúng route; một B7 grant đủ scope/time/E/net; presentation current | Decision APPROVE, chưa thực nhận |
| Trả lại | Người duyệt đúng route và grant còn hiệu lực trong scope; lý do cụ thể | RETURN, tiếp tục sửa/bổ sung rồi recheck/re-present |
| Từ chối | Như RETURN; lý do cụ thể | REFUSE, không tạo chi/thu mới và giữ nghĩa vụ đã có |

Nếu chưa đủ facts/quyền để trình, hệ thống hiển thị issue đúng owner. Người
duyệt không dùng RETURN/REFUSE để biến số tiền chưa rõ thành 0. Nhận định
“không chấp nhận khoản chi” phải được chuyển thành xử lý eligibility/exception
có căn cứ và report mới, không sửa riêng net ở màn quyết định.

Route kế toán/người duyệt dùng company route B3 của cùng employee, nhưng
**quyền B7 dùng B7CompanyConfig riêng**. Route không cấp hạn mức. Demo role
selector không phải đăng nhập/xác thực công ty. Không thêm role mới.

## 4. Nội dung phê duyệt

Python lấy E/T/B/A/RA/P/RP, signed S và refs từ current report. Client chỉ gửi
presentation ID, outcome, reason. Server chốt direction/amount/E/scope/basis;
extra fields amount/E/direction/rights bị 422, không nhận rồi bỏ qua.

| S của report | Direction | Amount phê duyệt | Trạng thái sau APPROVE |
| --- | --- | --- | --- |
| > 0 | PAY_EMPLOYEE | abs(S) | Đã duyệt — chờ công ty chi thêm |
| < 0 | COLLECT_FROM_EMPLOYEE | abs(S) | Đã duyệt — chờ nhân viên hoàn lại |
| = 0 | BALANCED | 0 | Đã duyệt cân bằng — chờ kiểm tra đóng |

Amount 0 chỉ thuộc decision BALANCED; không tạo money event 0.
E là phần nhân viên đủ điều kiện được người duyệt chấp nhận; S là nghĩa vụ
sau bù trừ. E5/A2 ⇒ duyệt E5 và chi thêm3, không chỉ kiểm quyền3.
“Duyệt2 thay vì report3” không được hỗ trợ. “Duyệt toàn3, chi2 trước” thuộc B9.

Một grant phải cover E và abs(S), đúng employee/work và hiệu lực tại thời
điểm quyết định server. Không cộng hai grants; không dùng max_advance của B3;
không fallback generic P-DEMO; thiếu limit không unlimited. RETURN/REFUSE
không tạo tiền nên chỉ cần đúng route + scoped effective B7 grant, không
giả lập monetary acceptance. Grant signature/ref và effective decision time
được lưu; thời điểm facts/as-of không thay thế thời điểm ra quyết định.

Policy exception chưa được xử lý có nguồn vẫn chặn APPROVE. Slice này không
tạo màn override ngoại lệ hay tự tăng B để hợp thức hóa vượt ngân sách. Người
có quyền cung cấp quyết định/nguồn ngoại lệ theo rulebook; chỉ khi pipeline
đã xử lý được nguồn đó và report không còn blocker mới dùng APPROVE. Nếu
đường resolution đó chưa có, UI nói chưa hỗ trợ, giữ hồ sơ chờ xử lý; không
claim toàn bộ exception lifecycle đã hoàn thành.

## 5. Lưu trữ, versions và currentness

Presentation lưu trong audit; decision payload `kind=B7_SETTLEMENT` lưu
trong decisions. CaseView có `b7_workflow`; không nhét decision này vào
`_latest_decision_payload` rồi để generic MoneySummary tính lại.

Presentation giữ basis report/review/employee/work/input revision/control
epoch, semantic business signature, parent dependency, policy/config/route
signature. Decision giữ các basis đó + outcome, actor, time, quyền áp dụng,
E/S/direction/amount từ server và signature của financial history tại duyệt.

Same key+same payload replay trước stale version checks; different payload
409. New key trên cùng presentation đã quyết định không tạo approval mới;
trả 409 B7_ALREADY_DECIDED và record cũ có thể xem lại. RETURN muốn nộp lại
cần presentation mới sau recheck. REFUSE không được vượt qua bằng resubmit
hoặc key mới; mở xem xét lại qua accountant re-presentation có reason và
supersedes_decision_id, chỉ khi chưa có executable approval/receipt cần xử lý.
Đã APPROVE không supersede tùy ý trong UI; thay đổi material chuyển NEEDS_RECHECK.

Trong cùng transaction: kiểm version, child và parent Stop, current report,
review/presentation, source/context/policy/config signatures, quyền và ghi
entity/audit/stage. Provider waits nằm ngoài transaction.

Semantic business basis loại run ID/usage/ghi chú thuần túy, nhưng bao gồm
expense/eligibility/payer/relations, budget, scope, policy, source hashes và
history baseline. B9 receipt đúng fulfillment được xét riêng; không dùng
case_version thay cho basis để làm mất hiệu lực approval chỉ vì ghi tiền.
Một rerun cùng facts không tự cần approve lại và không tạo nghĩa vụ mới.

Stop/resume không hồi phục action tự động. Recheck xác lập currentness;
nếu chỉ Stop/harmless changes và business basis còn đúng, có thể tiếp dùng
decision hợp lệ, không bắt nghi thức duyệt lại. Quyền cho hành động mới vẫn
kiểm current config. Quyền hết hạn sau khi đã duyệt không làm receipt cũ
biến mất hoặc tự phủ nhận action hợp lệ tại thời điểm thực hiện.

## 6. UI và trạng thái

Kế toán: tóm tắt E/ứng thực nhận/đã chi hoặc đã thu trước/net đề xuất, bảng
đối chiếu có nguồn, issue trọng yếu, rà soát và nút **Trình duyệt quyết toán**.
Có thể dùng review current đã lưu hoặc gộp lưu review + trình trong một command.
Không bắt mở lại mọi tài liệu hay checkbox “đã mở” để giả chứng minh review.

Người duyệt: **Chờ duyệt quyết toán**, người/công việc, các con số đúng nghĩa,
ý kiến kế toán và căn cứ. Ba nút **Phê duyệt quyết toán / Yêu cầu làm rõ /
Từ chối đề nghị**. Số tiền readonly, reason bắt buộc; không hiện debug ID/epoch
ở vùng thao tác chính. Disabled action hiển thị lý do backend.

Nhân viên: xem đang chờ ai, lý do trả lại/từ chối, khoản cần sửa; không thấy
form quyết định. Report-ready, đã trình, đã duyệt và đã chi/thu là các nhãn riêng.
Sau APPROVE vẫn **Chưa ghi nhận tiền thực tế**; BALANCED ghi **Không cần chi/thu
theo kết quả này**, không ghi “đã thanh toán0”.

## 7. Acceptance và giới hạn chứng minh

- T8/E5/A2/RA0/P0/RP0 ⇒ S+3; presentation+decision persistent, chưa receipt.
- E1.3/A2 ⇒ S−0.7; E2/A2 ⇒ BALANCED, không money event.
- Report incomplete/unknown/conflict/provider failure không APPROVE.
- Grant E4/net10 không cover E5 dù net3; missing/expired/wrong-work grants bị chặn.
- Source mới, parent money/Stop, route/policy/grant đổi giữa read và commit bị chặn.
- Return/refuse không xóa A/P/E, không tự đóng hoặc tự thu tất cả ứng.
- Reload/đổi vai/retry/two writers giữ một presentation quyết định; tiền chưa nhận.
- Generic endpoints và trực tiếp Store không bypass dedicated guards.

Tests fake/replay chứng minh logic/wiring; HUMAN_SOURCE_REVIEW không chứng minh
OCR/LLM quality. UI chỉ VERIFIED khi có thao tác thật; không có browser quyền
thì ghi USER_UI_UNEXECUTED, không chuyển công cụ để bypass denial. Không LIVE,
Git, publish hoặc bank API trong plan này.

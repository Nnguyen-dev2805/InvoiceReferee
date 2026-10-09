# W05 — Decision, tiền thực tế, Stop và đóng hồ sơ

Ngày 09/10/2026. Lát cắt actions của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W05).
Trạng thái: **VERIFIED** ở chế độ fake reader (PIPELINE_FAKE_OR_REPLAY).

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED)

- Decision (R8/R9): `POST /api/cases/{id}/decisions` — yêu cầu vai APPROVER
  **và** grant bao phủ work_ref + số tiền (config authority); thiếu một trong
  hai → `BEYOND_AUTHORITY` 403, không ghi. Decision lưu basis đầy đủ:
  `basis_report_id` (run có thật), `basis_case_version`,
  `basis_input_revision`; direction `PAY_EMPLOYEE`/`COLLECT_FROM_EMPLOYEE`/
  `REFUSE`; amount=None khi từ chối. **Số duyệt không đè calculated/proposed
  của report** (report giữ nguyên). Combined decision: `exception_of` +
  `conditions` gộp ngoại lệ và quyết toán trong một bản ghi. REFUSE giữ hồ sơ
  mở (`closed()` false, stage không thành SETTLEMENT_CLOSED).
- Review (SYS-14): `POST /api/cases/{id}/reviews` — chỉ ACCOUNTANT; review
  **không tạo approval** (`money_summary.approved_vnd` vẫn None); review mang
  `amount_vnd` → `REVIEW_NOT_APPROVAL` 400 (không thể lén duyệt qua review).
- Money events (R9, C02/C03/C07): `POST /api/cases/{id}/money-events` — gross
  giữ nguyên, **không clip theo mức duyệt**: duyệt 3 nhận 4 → received 4,
  remaining 0, incident `OVERPAY` excess 1.000.000; payee sai (NV-99) → giữ
  raw, không tính vào received, incident `WRONG_RECIPIENT`. PENDING không tính
  vào received. Dedup theo `event_ref` (namespace case) →
  `DUPLICATE_EVENT_REF` 409 khác HTTP key; idempotency theo (op, actor, case,
  key) như các mutation khác. Event sau `money_as_of` → `after_cutoff=True`,
  cờ hiển thị, **report cũ nguyên vẹn** (C07). Money event được ghi cả khi
  Stop (S7: tiền đã xảy ra vẫn record, chỉ không mở action mới).
- Money summary trên CaseView: `approved_vnd`/`received_vnd`/`remaining_vnd`
  tách biệt (None = chưa có/chưa biết, không phải 0 giấu), `pending_events`,
  `incidents` (OVERPAY excess, WRONG_RECIPIENT event/payee). Remaining =
  approved − received, floor 0 chỉ khi phần vượt được giữ thành incident.
- Control (C04): `POST /api/cases/{id}/control` STOP/RESUME — Stop ack được
  persists (stop_active + audit), chặn run/decision/handoff/closure mới nhưng
  **không** chặn add_source/record_money. Run đang chạy bị STOPPED tại
  checkpoint/publish; output đến muộn không thành current. RESUME tăng
  `control_epoch` (epoch mới); run cũ không tự hồi phục, run mới chạy bình
  thường. Restart process: Store init đánh dấu run QUEUED/RUNNING còn treo →
  `INTERRUPTED`; publish guard (`run.status != RUNNING` → RUN_TERMINAL)
  không cho worker cũ ghi đè (S7).
- Handoff (stage A): `POST /api/cases/{id}/handoffs` — chỉ định decision_id;
  gates: case mở, không Stop, decision tồn tại, **basis tươi** (run hiện tại
  SUCCEEDED với input_revision == input_revision của case). Input đổi sau
  decision (C05) → `BASIS_STALE` 409; **re-check xong thì handoff được mà
  không cần duyệt lại** decision cũ. Không tạo payment entity (stage B).
- Closure (R10, C01/C02): `POST /api/cases/{id}/closures` với kind
  `SETTLEMENT_COMPLETE` hoặc `REJECTED_REQUEST_ENDED` — hai trạng thái kết
  thúc **khác nhau**. Gates trong transaction: remaining > 0 (message nêu
  rõ remaining), sự kiện PENDING, money incident, Stop active, câu hỏi
  OPEN/ANSWERED chưa xử lý → `CLOSURE_BLOCKED` 409. Đã có decision duyệt số
  tiền thì không được kết thúc kiểu "request bị từ chối". Sau đóng: decide/
  review/money/add_source/handoff/closure mới → `CASE_CLOSED` 409; cùng
  semantic payload đóng lại → replay; rerun sau đóng (C01) không mở nghĩa vụ
  mới (report chạy lại cho kết quả như cũ, không đếm vào entitlement).
- Idempotency mọi mutation W05 theo (operation, actor, scope, key) + fingerprint
  payload; cùng key khác payload → `IDEMPOTENCY_CONFLICT`; replay trả bản ghi
  cũ (200); stale `expected_case_version` → `STALE_VERSION` 409. Replay tra
  **trước** các gate version để retry an toàn.
- UI Actions.tsx: money summary (approved/received/remaining/pending),
  incidents hiển thị rõ không tự sửa; form decision (cảnh báo BEYOND_AUTHORITY
  khi vai chưa đúng), review, money event (event_ref/gross/payee/status,
  after cutoff), Stop/Resume với epoch, handoff decision gần nhất (lấy từ
  history), closure theo kind + căn cứ; mọi mutation xong loadCase lại
  (case_version tăng).

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED | `pytest tests/settlement/test_{decisions,money,controls,closure}.py -q` trước implement | 17 failed + 6 errors (Service thiếu decide/record_money/control/close_case/review/handoff) |
| Decisions | `rtk proxy .venv/bin/python -m pytest tests/settlement/test_decisions.py -q` | **8 passed** (authority/typed basis/không đè report/idempotency+stale/combined exception/C05 BASIS_STALE→re-check→handoff không duyệt lại/REFUSE giữ mở/review không approval) |
| Money | `... -m pytest tests/settlement/test_money.py -q` | **6 passed** (C02 3/2/pending→remaining 1; C03 overpay giữ gross + incident, wrong recipient giữ raw; DUPLICATE_EVENT_REF; replay/conflict; C07 after_cutoff không đổi report cũ; ghi tiền khi Stop) |
| Controls | `... -m pytest tests/settlement/test_controls.py -q` | **4 passed** (barrier mid-call: stop ack → run STOPPED, handoff_allowed false; stop chặn run/decision mới nhưng add_source OK; resume epoch+1, run cũ không hồi phục; restart → INTERRUPTED không bị publish đè) |
| Closure | `... -m pytest tests/settlement/test_closure.py -q` | **5 passed** (S=0 đóng có căn cứ; chặn bởi remaining/pending/Stop; REJECTED_REQUEST_ENDED ≠ SETTLEMENT_CLOSED; C01 rerun sau đóng + replay/CASE_CLOSED/add_source chặn; câu hỏi mở chặn đóng) |
| API HTTP | `... -m pytest tests/settlement/test_actions_api.py -q` | **4 passed** (decide 403/201/200/409; review 400 REVIEW_NOT_APPROVAL; money dedup 409; stop→handoff 409→resume→handoff 201→closure 409→thanh toán đủ→201→CASE_CLOSED) |
| Toàn bộ backend | `rtk proxy .venv/bin/python -m pytest tests/ -q` | **523 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | **43 passed** (5 test Actions mới) / ok / pass |
| UI thực tế | 2 servers thật port 8010/5174 (DB/artifacts scratchpad riêng) + Playwright | **11/11 bước pass**: report B7 → quyết định 3.000.000 (APPROVER P-DEMO) → AWAITING_MONEY + summary → 2 trang cùng case: trang B ghi với version cũ bị `STALE_VERSION`, trang A ghi EV-1 2.000.000 (received 2tr, remaining 1tr) → closure bị `CLOSURE_BLOCKED` (remaining) → Stop → closure bị chặn lý do Stop → trang B reload ghi EV-2 1.000.000 ngay khi Stop (remaining 0) → resume (epoch+1) → đóng SETTLEMENT_COMPLETE → reload giữ stage đóng, actions chỉ đọc. Screenshot: `data/settlement/evidence/w05-01..05-*.png` |

## Giới hạn và phần chưa xác minh

- E2E browser dùng **fake reader** (PIPELINE_FAKE_OR_REPLAY): chứng minh
  workflow/gates/UI, không chứng minh chất lượng OCR/LLM live. Live provider
  chưa được gọi trong task này (giữ cấu hình fail-loudly như W03).
- "Stop midcall" được chứng minh ở tầng integration bằng BarrierReader
  (threading.Event, không sleep); trên browser, Stop được chứng minh **giữa
  các action** (khi run đã terminal) vì fake reader kết thúc trong millisecond.
- "2 writes cùng case" trên UI = hai page hai phiên kế toán, write thứ hai với
  version cũ bị STALE_VERSION; scenario 5 phiên đồng thời rộng hơn chưa chạy
  (pilot một writer mỗi thời điểm là mô hình dự kiến).
- Payment entity của stage B và chuyển tiền ngân hàng **chưa triển khai**
  theo đúng phạm vi: handoff chỉ là reference cho con người.
- E2E chạy trên DB/artifacts scratchpad riêng (không đụng DB pilot
  `data/settlement/settlement.sqlite`); DB pilot chưa được migrate dữ liệu W05
  (Store `_migrate` thêm cột khi mở).

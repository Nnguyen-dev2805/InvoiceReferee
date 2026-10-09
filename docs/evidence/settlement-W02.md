# W02 — B7 report thuần và kiểm chứng tiền trên UI

Ngày 09/10/2026. Lát cắt report của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W02).
Trạng thái: **VERIFIED** cho các hành vi dưới đây ở chế độ
PIPELINE_FAKE_OR_REPLAY (reader giả lập structured ledger, không gọi provider
thật); không kết luận gì về chất lượng OCR/LLM live.

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED)

- Rule engine deterministic (`settlement/rules.py`): tiêu thụ
  Observation/Relation có refs, validate trước tổng hợp (fact ID trùng,
  relation tham chiếu unknown, tiền bool/non-integer bị chặn ở boundary —
  SYS-02), tính `S = E − (A − RA) − (P − RP)` với unknown giữ `None` (không
  bao giờ 0), company direct không trừ lần hai, duplicate same-event tính
  một lần, portion vượt gross fail-closed (giữ incident, không cắt số),
  personal bị loại khỏi T/E nhưng giữ raw trong rows.
- Budget: T ≤ B PASS; T > B → check FAIL + issue AUTHORITY owner APPROVER +
  conditional result (kịch bản, không phải số đã duyệt); B thiếu →
  UNRESOLVED, không lấy claim làm B.
- Authority: proposed_net chỉ có khi có grant đủ hạn mức đúng scope;
  calculated giữ nguyên khi authority chưa đủ (Q14 semantics).
- B3 path riêng: không hậu tính E/S cho job B3; các check request/forecast/
  budget/history độc lập.
- Report persisted với run status/job completion; GET report không re-read
  provider (hai lần GET trả cùng `generated_at`); mode FAKE_OR_REPLAY ghi
  rõ trên run + report + UI.
- Run lifecycle: POST /cases/{id}/runs 202 (idempotent theo key + snapshot
  fingerprint; cùng key khác snapshot → 409), stale version 409, một run
  nonterminal mỗi case, capacity 5 accepted, 2 active (semaphore), deadline
  240s + 32 calls/run trong RunBudget; checkpoint kiểm Stop/revision/epoch
  trước từng stage; publish guard trong transaction (late output không thành
  current — nền cho W05).
- UI: nút "Chạy kiểm tra", poll 1s khi active, ReportPanel hiển thị
  components/proposed(calculated riêng)/expense rows với refs mở được nguồn
  gốc/checks/issues có owner/next step; nhãn "chưa duyệt, chưa chi" tách bạch.

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED | `pytest tests/settlement/test_rules.py -q` trước khi tạo module | ImportError (contract chưa tồn tại) |
| Rules + builders | `rtk proxy .venv/bin/python -m pytest tests/settlement/test_rules.py -q` | **21 passed** (positive/negative/zero/unknown, company direct, duplicate, portion, budget, authority, B3) |
| API + service | `... -m pytest tests/settlement/test_report_api.py -q` | **8 passed** (Q01/Q03/Q04/unknown qua cùng service, persisted report, idempotency, stale) |
| Toàn bộ backend | `... -m pytest tests/ -q` | **461 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | **38 passed** (gồm 4 test ReportPanel) / build ok / pass |
| UI thực tế | 2 servers thật + Playwright (Chrome) | **7/7 bước pass**: upload 2 nguồn ledger qua UI → chạy B7 → Q01 COMPLETE + 3.000.000 VND trên UI → mở nguồn gốc từ ref của report → reload vẫn hiện report persisted → case unknown: INCOMPLETE, proposed "—", issue FACT đúng owner |

Screenshots: `data/settlement/evidence/w02-*.png` (runtime, Git-ignored).

## Lỗi đã phát hiện và sửa trong lúc làm

- DB runtime W01 thiếu cột `runs.detail` (schema đổi sau khi DB đã tạo) gây
  500 trên server thật dù TestClient xanh — thêm migration cộng thêm trong
  Store init. Bài học: TestClient với DB tươi không phủ được migration;
  đã có `_migrate` cho các lát sau.

## Acceptance mapping

- **SYS-02** VERIFIED (duplicate/unknown refs/money boundary trước aggregation).
- **SYS-03** VERIFIED (Q01 đủ nguồn → components/proposed/refs; chưa duyệt/chưa nhận).
- **SYS-04** VERIFIED (unknown giữ null + issue owner; subtotal không thay net).
- **SYS-05** VERIFIED (split payer, company direct, duplicate, portion).
- **SYS-06** VERIFIED phần vượt B (exception + conditional, không cắt); sai
  scope authority (Q15) thuộc W04.
- **SYS-13/15** VERIFIED cho runs (idempotency key, stale, capacity guard).

## Giới hạn còn lại

- Reader W02 là structured ledger giả lập (mode FAKE_OR_REPLAY); Mistral/xkiro
  + budget thật là W03. Không có kết luận chất lượng live.
- Chưa có questions/response records (W04), decision/money events/Stop
  UI/closure (W05), evaluator/baseline (W06).
- Evaluator hook hiện là chính Service facade + report persisted (W06 sẽ
  dựng SuiteReport/compare trên đó).
- 5 phiên/2 writes song song trên cùng case chưa test (W05).

# B3 verbal intake (b3-intake-v1) — Test evidence

Plan: [docs/superpowers/plans/2026-10-10-b3-verbal-intake.md](../../docs/superpowers/plans/2026-10-10-b3-verbal-intake.md)
Ngày: 2026-10-10 · Branch: `rebuild` (chưa commit theo chỉ dẫn) · Mode chính:
**PIPELINE_FAKE_OR_REPLAY / FAKE_OR_REPLAY** — không có live OCR/LLM trong đợt này.

## 1. Commands đã chạy và kết quả

| Command | Kết quả |
| --- | --- |
| `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q` | **658 passed** (trong đó B3: 27 intake + 27 proposal + 27 API + 7 pipeline/reader mới; sau chỉnh sửa cuối: 240 settlement passed) |
| `rtk proxy .venv/bin/python -m pip check` | No broken requirements found |
| `rtk proxy npm --prefix frontend run test -- --run` | **58 passed** (B3Intake 5, App 4, Report +3) |
| `rtk proxy npm --prefix frontend run build` | built OK (dist 191.63 kB js) |
| `rtk proxy npm --prefix frontend run typecheck` | clean |
| Playwright E2E (Chrome headless, backend 8010 + frontend 5174, fake mode) | U01/U02/U04/U05 OK — ảnh dưới |

Lưu ý môi trường: `.env` của repo đang đặt `SETTLEMENT_PROVIDER_MODE=live`; mọi lệnh
pytest ở trên chạy với `SETTLEMENT_PROVIDER_MODE=fake` ghi đè (biến export thắng
`.env`). Toàn bộ test không phụ thuộc DB/`.env` thật (fixture b3_client dựng
Service riêng).

E2E servers (đã dừng sau khi chụp):

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_DB_PATH=data/settlement/b3-e2e/b3.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b3-e2e/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app --factory \
  --host 127.0.0.1 --port 8010
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

## 2. UI screenshots (actual)

| Ảnh | Nội dung | Actual vs expected |
| --- | --- | --- |
| `u01-01-intake-panel.png` | Panel B3: persona Nguyễn An (readonly), fixture "mô phỏng" + clock, không có input người duyệt/mã work/mốc | Đạt P2a (không nhập tự do) |
| `u01-02-form-filled.png` | Form WEB đầy đủ 2M + 4 dòng dự toán; preview công ty 3M · nhân viên 5M · tổng 8M | Đạt |
| `u01-03-report-ready.png` | Report: `READY_FOR_ACCOUNTANT_REVIEW`, số xin 2.000.000 VND, forecast 3M/5M/8M, A=RA=0, B null, work/B/advance "Đang chờ quyết định", tuyến ACC-DEMO-01/APR-DEMO-01, company context `company:grant-01`/`company:coverage-01`, cảnh báo B3 v1 chưa có action duyệt/chi | Khớp business-oracle (T01) |
| `u02-01-draft-preview.png` | IMPORT draft + 2 nguồn ledger (giả lập): report `DRAFT_CONFIRMATION_REQUIRED`, forecast 8M từ rows có refs nguồn | Đạt T02 (draft) — **FAKE, không phải PDF thật** |
| `u02-02-confirm-panel.png` | "Điền form từ bản nháp report" → form confirm đầy đủ + lý do | Đạt |
| `u02-03-report-after-confirm.png` | Sau confirm + rerun: `READY_FOR_ACCOUNTANT_REVIEW`, 2M/8M, giữ refs nguồn gốc | Đạt T02 |
| `u04-01-revise-panel.png` | Panel sửa B3 (form đầy đủ, không rút còn purpose/scope) sửa request 3M + lý do | Đạt U04 |
| `u04-02-after-revise.png` | Report sau revision: 3.000.000 VND; report cũ không còn là current basis | Đạt U04 |
| `u05-01-no-coverage-needs-info.png` | Backend restart với context bỏ coverage → case MỚI: `NEEDS_INFORMATION`, A/RA "—" (không phải 0), issue owner Kế toán, work vẫn pending (không đòi upload) | Đạt T08/U05 |
| (curl) U06 | `POST /decisions` và `POST /money-events` cho case B3 v1 → **409 B3_REPORT_ONLY** (xem log bàn giao) | Đạt U06; B7 regressiondo bộ test decisions/money/closure xanh |

U05 immutable: run cũ `R-e51e78689c10` (tạo với context đầy đủ) vẫn trả
`coverage: 1` ở `GET /api/runs/{id}/b3-context` sau khi config đổi.

## 3. Actual-vs-expected theo acceptance matrix (T01–T15)

Tất cả T01–T15 được tự động hóa trong `tests/settlement/test_b3_proposal.py`
(28 test, xanh) — mỗi dòng assert số/refs/state/owner, không chỉ completion.
Tóm tắt actual:

| ID | Expected | Actual |
| --- | --- | --- |
| T01 | 2M; 3/5/8M; A/RA=0 qua coverage; B null; READY; pending decisions | PASS |
| T02 | Draft → confirm cùng kết quả; refs nguồn giữ | PASS (API + UI) |
| T03 | Words 3M ≠ số 2M → FAIL, EMPLOYEE, không clip | PASS |
| T04 | Printed 4M ≠ rows 5M → FAIL giữ cả hai | PASS |
| T05 | Xin 6M > forecast 5M → NEEDS_AUTHORIZED_REVIEW + issue hạn mức riêng | PASS |
| T06 | Form 3M ≠ nguồn 2M → conflict giữ cả hai refs, không form-wins | PASS |
| T07 | Row UNCLEAR → null, issue EMPLOYEE kèm locator, không partial-sum | PASS |
| T08 | Coverage drop → A/RA unknown, ACCOUNTANT, không đòi upload | PASS |
| T09 | As-of ngoài cửa sổ / employee khác → unknown | PASS |
| T10 | Pending/approved/refused giữ riêng, route APPROVER | PASS |
| T11 | Forecast 8M > budget grant 7M → route insufficient | PASS |
| T12 | File nhân viên không cấp quyền; grant hết hạn → không ready | PASS |
| T13 | Bản trùng không cộng 2 lần; khác nội dung → conflict không cộng | PASS |
| T14 | Technical failure → INCOMPLETE, giữ phần rõ | PASS |
| T15 | Giấy chỉ tên/department → không đòi employee_ref/giấy lệnh; tên khác persona → hỏi EMPLOYEE | PASS |

## 4. Chưa verify / giới hạn

- **U02/U03 với PDF/PNG thật của packet: USER_LIVE_UNEXECUTED.** Fake reader
  không đọc được PDF/ảnh; E2E import ở trên dùng ledger text giả lập (đánh dấu
  FAKE). Cần chủ dự án bật `SETTLEMENT_PROVIDER_MODE=live` (chi phí API) và chạy
  theo phụ lục U02/U03 trong
  [SETTLEMENT_MANUAL_TEST_GUIDE.md](../../docs/testing/SETTLEMENT_MANUAL_TEST_GUIDE.md).
- Live quality (OCR Mistral + xkiro), trial ≥3 người nghiệp vụ thật, và so
  critical facts/links/checks với oracle: chưa làm — **không phải baseline đo được**.
- Packet oracle là single-author assertion, không phải independent gold; kết
  quả khớp oracle ở fake mode chỉ chứng minh application path đúng nghiệp vụ.
- UI import với file thật từng bị fake reader từ chối (SOURCE_UNREADABLE) —
  hành vi đúng (technical failure), không phải PASS nghiệp vụ.
- Bẫy kỹ thuật đã ghi: sau `page.screenshot({fullPage:true})` phải
  `window.scrollTo(0,0)` trước khi click (Playwright/Chromium miss hit-target);
  ledger fake cho phép giá trị chứa dấu cách (`" ".join(parts[3:])`).

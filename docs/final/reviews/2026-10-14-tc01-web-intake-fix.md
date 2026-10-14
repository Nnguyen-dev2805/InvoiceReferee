# TC01 web intake fix — implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `0b205420`. No commit or
push (no Git authorization); no database reset; no checkout; no subagent. A
concurrent agent's uncommitted frontend edits were preserved.

Fixes the P1-1..P1-5 + P2 findings of
[2026-10-14-tc01-independent-live-web.md](2026-10-14-tc01-independent-live-web.md).

## Write set, consumers, completion

| Finding | Files | Consumers | Gate |
| --- | --- | --- | --- |
| P1-1 draft bypasses OCR | new `reconciliation/settlement_draft.py`, `workflow/service.py::read_settlement_draft`, `evidence/pipeline.py` (profile passthrough already) | draft endpoint, UI | draft from the §12 report; no pypdf+regex |
| P1-1 reuse on submit | `workflow/service.py::_reusable_report`/`_store_evidence_report`, schema v4 `input_basis_json` | submit job | submit reuses a still-valid read (no re-OCR) |
| P1-2 fabricated fallback | `frontend/src/features/intake.tsx` | UI | no demo facts; failure → error + retry; null stays unknown |
| P1-3 always new activity | `workflow/service.py::_submit` rebind; `frontend` activity select | admission scope | draft binds to a chosen catalog activity; non-catalog rejected |
| P1-4 edits/notes dropped | `domain/commands.py::Declaration`, `api/views.py`, `workflow/service.py::_declaration_draft_json`, schema v5 `draft_json` | reconciliation | confirmed draft + original persisted; ledger untouched |
| P1-5 no async refresh | `frontend/src/features/intake.tsx` polling | UI | UI follows server version/state |
| P2 money labels | `frontend/src/features/intake.tsx` | UI | "Ứng nhân viên kê khai"; no false "Cân bằng" |

## RED → GREEN (backend)

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Behaviour | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| draft maps real report values; unknown stays null; unmatched row not CLEAR | `tests/unit/test_settlement_draft_mapper.py` | `settlement_draft` missing | 4 passed |
| draft uses OCR; submit reuses (no re-OCR); provider failure raises | `tests/integration/test_settlement_draft_ocr_reuse.py` | — | 3 passed |
| confirmed edits/notes persist; ledger untouched; survives reload | `tests/integration/test_declaration_edits_persist.py` | `draft_json` column missing | 3 passed |
| draft binds to a catalog activity; non-catalog rejected | `tests/integration/test_draft_activity_binding.py` | submit raised UnsupportedCommandError | 2 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **528 passed**.
Frontend (Node 24.19.0): `npm test` → **27 passed / 2 skipped**; `npm run build` → exit 0.
New frontend tests: `tests/intake-draft.test.tsx` (4) — real draft, failure+retry,
unknown money, confirmed-draft payload.

## LIVE + browser evidence

- **LIVE TC01 original PDFs** (`.runtime/tc01-web-fix/run_live.py`, real Mistral OCR +
  X-Kiro, SIMULATED context, clock `2026-10-10T18:00+07`): the draft read through the
  OCR pipeline = declared_name `NGUYỄN MINH AN`, purpose "Chi phí tiếp khách phục vụ
  dự án Nâng cấp văn phòng 2026", total `3.240.000`, advance `4.000.000`, invoice
  `00000101`, **no invented trip**. Submit reused the read (no second OCR) →
  **READY_TO_EXECUTE, COLLECT 760000**, T=E=3240000, A=4000000, S=-760000, basis
  `EMPLOYEE_PAID_INVOICE`. Artifacts: `live-draft.json`, `live-result.json`.
- **Browser** (`.runtime/tc01-web-fix/server.py` + `browser.mjs`, real socket + built
  frontend): upload both original PDFs → **Đọc chứng từ** → review → select activity
  → **Xác nhận và nộp hồ sơ**. Network: `POST /settlement/draft` 200,
  `POST /submit` 200. Draft screen (`web-draft.png`): "Kiểm tra bản nháp hồ sơ",
  "Đã trích xuất", Hoạt động = "Tiếp khách dự án · 2026-10-10", purpose read, row
  "Chi phí tiếp khách…" 00000101 3.240.000 ✓ Khớp tệp: hoa_don_dien_tu.pdf, labels
  "Tổng chi phí kê khai" / "Ứng nhân viên kê khai". After submit (`web-after-submit.png`):
  "Sẵn sàng phê duyệt" (v3), T=3.240.000, E=3.240.000, A=4.000.000, S=-760.000, basis
  "Hóa đơn thanh toán cá nhân" — the UI refreshed to the server's final state (no stale
  "Đang xử lý"). DB: activity `activity:tc01`, instruction COLLECT 760000, one declaration.

## Data correctness notes

- The draft root is created against a PROPOSED placeholder (no fabricated activity),
  then rebound to the chosen AUTHORIZED catalog activity at submit. The three former
  FACT issues (budget/coverage/payer) were the intake-scope failure; with the correct
  activity scope they resolve to COLLECT 760000.
- A row's invoice link is shown as **verified** only from an `AUTO_LINK`; a
  `SUGGEST_LINK` is shown as "Có thể liên quan (chưa xác nhận)", never a ✓ match.
- The declaration is a correction, not a fact: an advance edit keeps the company
  ledger at 4,000,000 and records the correction + original for the reconciliation.
- Creating a COLLECT instruction is not money received; the case is READY_TO_EXECUTE,
  not SETTLED, until the return is recorded.

## NOT_RUN / remaining

- **Verify Core4/Escalation5**: NOT_RUN — the evaluation dataset `data/kiem-thu` is
  absent, so `/api/verify` returns 0 packets.
- **Fault-injection browser probe** (HTTP500 on the draft) was reproduced by the
  investigation report; this task's frontend unit test covers the error+retry path,
  but a re-run of the injected-500 browser probe is NOT_RUN here.
- **M0 LIVE / RECORDED_REPLAY captures / Docker / public hosting / practitioner
  pilot**: NOT_RUN (unchanged).
- The two frontend tests skipped in `intake-submit.test.tsx` are the concurrent
  agent's (personal paid-claim section), not this task.

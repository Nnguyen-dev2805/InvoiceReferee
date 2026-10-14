# Employee-paid invoice basis + advance recording — implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `2e53fd05`. No commit or
push (no Git authorization); no database reset; no subagent. A concurrent UI-UX
refactor (frontend Tailwind/dual-pane) by another agent was preserved; the new
advance UI is an additive component.

Every finding was re-verified on the current checkout (graph/source + regression
tests) before changing code, not taken from a prior checkpoint.

## Write set, consumers, completion

| Area | Files | Consumers | Completion |
| --- | --- | --- | --- |
| C invoice basis | `domain/finance.py` (`EMPLOYEE_PAID_INVOICE`), `reconciliation/admission.py`, `evidence/document_profiles.py` | Reconciler, policy, dossier UI, `payment_basis` view | a valid bound invoice is the employee-paid basis with no separate payer confirmation |
| E binding + advance gap | `reconciliation/admission.py` (declared-advance gap), `workflow/service.py` (scope guard, `CaseView.activity/employee`) | policy issues, instruction gate, UI scope | wrong person/dossier/amount blocked; declared advance with no record → accountant |
| D advance form | `domain/finance.py` (`RecordMoneyInput`/`MoneyEvent` instrument fields), `workflow/money.py`, `workflow/service.py` (`read_advance_draft`), `reconciliation/advance.py`, `api/{views,routes}.py` | `/actuals`, `/advance/draft` | status≠COMPLETED never received; retry no double count |
| A/B data | `scripts/sinh_uc03_pilot.py`, `data/test-kit/uc03-pilot/**` | tests, evaluation loader | F01 invoice buyer person; 2 advance docs; F02/F03 unchanged math |
| E/F UI + tests | `frontend/src/{api.ts,types.ts,roles.ts,App.tsx,features/advance.tsx,features/dossier.tsx}`, `frontend/tests/advance.test.tsx`, `tests/**` | — | UI records advance; both flows reach COLLECT |
| Docs | `docs/adr/0007-*.md`, contracts §3/§4, design §3, `GLOSSARY.md`, this report, `IMPLEMENTATION_STATUS.md` | — | old docs no longer demand a responsible employee confirmation as the routine basis |

## Decisions implemented (user chốt 14/10/2026)

1. Only employee-pays-vendor is supported; company-direct stays out of scope.
2. In the demo policy a **valid invoice, bound to the right employee and dossier, is
   the employee-paid basis** (`EMPLOYEE_PAID_INVOICE`), with no separate payment
   confirmation and no long printed declaration.
3. The basis is a **demo business assumption**, never presented as bank verification;
   no fake bank transaction/confirmation is created.
4. The **advance actually received still needs its own company record**; an approved
   advance does not become received. The accountant records `ADVANCE_RECEIVED` from a
   read document.
5. Demo signatures are text "Ký bởi: …" + date; no certificate/signature-crypto check.
6. Budget/authority/scope/history/arithmetic/Stop/Resume/dedup rules unchanged.

## RED → GREEN (backend)

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Behaviour | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| clear bound invoice = employee-paid basis, no confirmation | `tests/unit/test_invoice_paid_basis.py` | `eligibility == UNKNOWN`; no payment portion | 8 passed |
| buyer-person/claimant mismatch blocked; unclear invoice blocked | same | no binding FACT | (in above) |
| source status ≠ COMPLETED never confirms | `tests/unit/test_advance_instrument.py` | `CONFIRMED` for PENDING/FAILED/UNKNOWN | 6 passed |
| declared advance with no record drops coverage | `tests/unit/test_declared_advance_gap.py` | coverage kept → wrong A=0 | 3 passed |
| advance draft prefill (transfer + receipt-like cash) | `tests/unit/test_advance_draft.py` | mapper absent | 6 passed |
| two flows converge; pending blocked; retry no double count | `tests/integration/test_f01_two_flows.py` | — | 5 passed |
| advance draft endpoint reads doc, records no money | `tests/integration/test_advance_draft_api.py` | — | 2 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **476 passed**.
Frontend (pinned Node 24.19.0, npm's own Node verified): `npm test` → **16 passed**;
`npm run build` → **exit 0**.

## LIVE / HTTP / UI evidence

- **LIVE F01** (`.runtime/f01-invoice-basis-verification/run.py`, real Mistral OCR +
  X-Kiro, SIMULATED context, controlled clock `2026-10-10T18:00+07`):
  - flow-2 (advance already recorded), no claim → **READY_TO_EXECUTE, COLLECT 760000,
    T=E=3240000, A=4000000, S=-760000, basis `EMPLOYEE_PAID_INVOICE`**.
  - flow-1 (no record) → blocked (A/S UNKNOWN, `ledger:advance` FACT); accountant reads
    the transfer receipt → A=4000000 → **COLLECT 760000**.
  - flow-1 cash branch (voucher read as receipt-like) → same **COLLECT 760000**.
  - Loop closure: record `EMPLOYEE_RETURN 760000` → **R=760000, S=0, SETTLED**, no zero
    instruction (all three scenarios).
- **LIVE F02/F03** (`.runtime/f01-invoice-basis-verification/f02_f03.py`): F02
  T=E=5400000, A=5000000, **S=400000, PAY 400000**; F03 T=E=A=4320000, **S=0, SETTLED,
  no instruction**. Arithmetic unchanged under the new basis.
- **HTTP** (`.runtime/f01-invoice-basis-verification/http_check.py`, real uvicorn socket,
  isolated DB): both flows through the real routes reach COLLECT 760000; the draft
  endpoint returns the prefilled fields; no money recorded by the read.
- **UI** (Playwright, real built frontend, pinned-clock server):
  - `/tmp/ui_f01_advance-employee.png` — "Sẵn sàng duyệt & Thực thi", S = −760.000 đ,
    T=E=3.240.000, A=4.000.000, unpaid 0, basis "Hóa đơn gắn đúng nhân viên (căn cứ
    theo policy demo)".
  - `/tmp/ui_f01_no_advance-employee.png` — "Chờ người xử lý ngoại lệ", A = "Chưa xác
    minh"; `/tmp/ui_f01_no_advance-accountant.png` — accountant records the advance
    ("Đã ghi nhận tiền ứng thực nhận", A=4.000.000) then "Sẵn sàng duyệt".

Provider: **OCR/LLM LIVE** (Mistral `mistral-ocr-latest`, X-Kiro configured model);
**financial context SIMULATED**. No user DB was reset or written; all runs used
isolated `.runtime/` DBs.

## PDF/data

- `scripts/sinh_uc03_pilot.py` regenerates the corpus. F01 invoice adds
  "Họ tên người mua: Nguyễn An"; the settlement form drops the attachment line and the
  payment-declaration sentence; two signature blocks sit on one borderless centered
  row. F01 adds two **alternative** advance-basis documents (transfer receipt, cash
  voucher) for the SAME 4.000.000 đ; exactly one is used per branch (never summed).
  F02/F03 reference updates only (buyer person, basis label). Gold/provenance/README
  updated; the Hoangha TC01 reference set is untouched. PDFs rendered and visually
  checked (Vietnamese font, table, money alignment, signature area).

## NOT_RUN / remaining

- **M0 LIVE / RECORDED_REPLAY captures / Docker / public hosting / practitioner pilot**:
  NOT_RUN (unchanged).
- The concurrent **UI-UX refactor** (dual-pane, document viewer, debug modal) is
  another agent's uncommitted work; the advance UI is additive and does not modify
  their components beyond one import + one render line in `App.tsx` and the accountant
  panel list.
- The D form's OCR prefill runs the full evidence pipeline for one uploaded file; the
  UI currently sends one file per read. Multi-file advance packets are not exercised.

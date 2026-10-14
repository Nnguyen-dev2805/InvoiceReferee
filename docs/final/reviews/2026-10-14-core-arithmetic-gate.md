# Core arithmetic gate + numeric provenance — implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `96e7b888`. No commit or
push (no Git authorization); no database reset; no checkout; no subagent. The
concurrent agent's frontend work was already committed at `96e7b888`; the working
tree was clean at start.

Fixes the three failures of
[2026-10-14-tc06-tc11-live-negative.md](2026-10-14-tc06-tc11-live-negative.md):
TC06 issues money despite a printed-refund contradiction, TC11 accepts an invoice
total that does not equal subtotal+tax, and `_value_supported` mis-reads a money
value against a quote that also carries a percentage.

## Write set, consumers, completion

| Fix | Files | Consumers | Gate |
| --- | --- | --- | --- |
| TC06 paper arithmetic | new `reconciliation/document_arithmetic.py`; `reconciliation/admission.py` | `Reconciler.assess` → `_commit_assessment` | `expense:arithmetic:return` FACT; `allowed_effect=None`; no instruction |
| TC11 invoice arithmetic | same module + `admission.py` | same | `expense:arithmetic:total` FACT; `allowed_effect=None`; no instruction |
| Unknown material component | `document_arithmetic.py` | same | `invoice-components-unread` FACT (tax UNREADABLE ≠ 0) |
| Numeric provenance | `evidence/extraction.py::_value_supported`/`_numeric_tokens` | `extract_document` (both draft and submit) | percentage/identifier digit-runs are not money tokens |
| Draft surfacing | `reconciliation/settlement_draft.py`; `frontend/src/api.ts` | draft endpoint / UI | the SAME finding shows on the review screen |

No change to `workflow/service.py` or the schema: the gate is a pure mapper
consumed by the existing admission → Reconciler → commit boundary, so the draft
and the submit use one result. `settlement_draft.py`, `extraction.py` and
`admission.py` were the only shared files touched; the concurrent agent's
frontend files were not modified beyond a non-breaking optional type.

## RED → GREEN (backend)

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Behaviour | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| money/percentage/identifier provenance | `tests/unit/test_numeric_provenance.py` | 3 assertions failed (`_value_supported` picked `8`) | 6 passed |
| per-type document arithmetic | `tests/unit/test_document_arithmetic.py` | module missing | 9 passed |
| gate blocks at Reconciler + commit; TC01 unblocked | `tests/integration/test_document_arithmetic_gate.py` | — | 4 passed |
| TC01 no-advance branch → accountant, then COLLECT | `tests/integration/test_tc01_no_advance_record.py` | — | 4 passed |
| draft surfaces the contradiction | `tests/unit/test_settlement_draft_mapper.py` | — | 6 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **all
passed** (537 tests). Frontend (Node 24.19.0): `npm test` → **27 passed / 2
skipped**; `npm run build` → exit 0.

## LIVE reruns (original PDFs, current source)

Harness `.runtime/core-arith-20261014/` (git-ignored): real Mistral OCR + X-Kiro
`qwen/qwen3.7-flash:free`, SIMULATED independent context, clock
`2026-10-10T18:00:00+07:00`. Full `CaseWorkflow → evidence worker → admission →
Reconciler → commit`. Source hashes unchanged from the negative report
(TC06 report `8ff6df5d…`, invoice `3625468b…`; TC11 report `6ad1a550…`, invoice
`1ae75778…`).

| Case | State | Instructions | Decisive FACT |
| --- | --- | --- | --- |
| **TC06** | WAITING | **none** | `expense:arithmetic:return` — "ứng 4000000 − chi 3240000 = 760000 nhưng số hoàn lại in trên giấy là 700000 (lệch 60000)", owner employee, refs on the paper's own quotes |
| **TC11** | WAITING | **none** | `expense:arithmetic:total` — "Tiền hàng 5000000 cộng thuế/phí ra 5400000 nhưng tổng hóa đơn in 5500000 (lệch 100000)", owner employee. Tax now reads **FOUND** (provenance fix), so the check is a real 5.4m vs 5.5m, not a missing-field artifact |
| **TC01** | READY_TO_EXECUTE | **COLLECT 760000** | no arithmetic FACT; T=E=3240000, A=4000000, S=−760000, basis EMPLOYEE_PAID_INVOICE |

The negative cases block **because of the exact contradiction**, not because of
missing B/coverage or a provider error: their money projection is otherwise KNOWN
(A=4m / A=6m, S=−760k / −500k). Source numbers are preserved (the FACT prints the
computed figure as a *comparison*, never rewrites the printed total).

### Numeric provenance probe (no provider call)

| value | quote | result |
| --- | --- | --- |
| 400000 | `Thuế GTGT (8%): 400.000` | True (was False) |
| 400000 | `400.000` | True |
| 240000 | `Thuế GTGT (8%): 240.000` | True (was False) |
| 8 | `Thuế GTGT (8%): 400.000` | False (the `8%` rate is not money) |

## TC01 no-advance branch

`tests/integration/test_tc01_no_advance_record.py` (in-process, no provider):
with the paper still declaring 4m but no `ADVANCE_RECEIVED` record, A/S stay
**UNKNOWN**, no instruction, and a `ledger:advance` FACT is raised to the
**accountant**. A PENDING record does not establish A. After the accountant
records the actual 4m through the existing granted `RecordActual` path, the
re-assessment reaches **COLLECT 760000** with A=4m (no double count); a repeat is
idempotent by external key.

## Browser evidence (Playwright + built frontend + real socket)

Dedicated pinned-clock LIVE server (`.runtime/core-arith-20261014/server.py`).

- **TC06** (`/api/cases/{id}/settlement/draft` 200, `/submit` 200): the review
  screen surfaces the contradiction; after submit the case is WAITING with no
  "Thu hồi" instruction.
- **TC01** (fresh server): draft reads NGUYỄN MINH AN / 3.240.000; submit 200;
  conclusion OUTSTANDING, instruction **COLLECT 760000 ISSUED** (NOT_STARTED).

## Constraints honoured

- No policy relaxed and no PDF/gold edited; the gate only blocks on a document's
  own arithmetic, never to force a case to a target figure.
- Integer VND / `parse_vnd` only; no float and no tolerance — the 60k/100k gaps
  are exact.
- Validators are per document type: a receipt/ticket with no VAT fields is not
  forced to reconcile; a genuinely FOUND tax=0 with a matching total is clear.
- Approval/EXCEPT_POLICY does not waive the arithmetic FACT (it is an admission
  FACT on `expense:arithmetic:*`, not the `expense:missing_required_evidence`
  exception path).
- A material component read as UNREADABLE (tax) is a FACT, never a silent zero.

## NOT_RUN / remaining

- The full 25-case Hoangha rerun, Docker, public hosting and the practitioner
  pilot remain NOT_RUN (out of this task's scope).
- Verify Core4/Escalation5 remains NOT_RUN (`data/kiem-thu` absent).

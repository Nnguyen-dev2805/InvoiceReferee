# F01 investigation — five-group fix: implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `0be840c4`. No commit or
push (no Git authorization); no database reset; no subagent. Concurrent frontend
(Tailwind) edits by another agent were preserved.

Every finding was re-verified on the current checkout before changing code
(graph/source + regression tests), not taken from the investigation report.

## Write set, consumers, completion

| Group | Files changed | Consumers | Completion |
| --- | --- | --- | --- |
| A unknown payment | `domain/finance.py`, `reconciliation/finance.py`, `reconciliation/admission.py`, `workflow/snapshots.py`, `tests/factories.py` | `reconciliation/service.py`, dossier UI | unpaid KNOWN only when every expense's payment status is established |
| B claimant/activity binding | `reconciliation/admission.py`, `workflow/service.py` | reconciler issue merge | name mismatch → FACT; submit activity-scope mismatch rejected |
| C coverage + clock | `workflow/service.py`, `workflow/evidence_assessment.py`, `reconciliation/admission.py`, `reconciliation/service.py` | policy engine | assessment time = workflow clock; coverage must be valid |
| D context import | `workflow/service.py`, `workflow/context_records.py`, `domain/organization.py`, `runtime.py` | catalog + typed admission | one snapshot source; activity-scoped load |
| E UI claim refs | `domain/evidence.py`, `workflow/service.py`, `frontend/src/{types.ts,features/intake.tsx}`, `frontend/tests/intake-submit.test.tsx` | submit command | server source id + real quote; no first-source default |

## Root cause per finding

- **A.** `project_finance` set `gross_paid=0` when no payment was admitted, then
  returned `unpaid = KNOWN(T - 0)`. Missing evidence of payment was read as a
  proven debt. `Eligibility` and payment status were conflated.
- **B.** `admit_evidence` read `declared_name` but never compared it to the
  responsible claimant; `_submit` ignored `declaration.activity_id`.
- **C.** `build_evidence_assessment_input` used `as_of or datetime.now(UTC)` and
  `_build_assessment_input` never passed the workflow clock; `admit_evidence`
  accepted any non-None coverage as a zero basis.
- **D.** `import_demo_context` wrote only the legacy relational tables; the typed
  admission read `context_snapshots`, so the web entry's context never reached
  the assessment. `load_context` also returned the newest tenant snapshot for any
  activity.
- **E.** `intake.tsx` took `current.sources[0]`, built `file:<last storage-key
  segment>`, and sent the fabricated quote "nhân viên xác nhận"; the backend
  resolves by filename+digest / server source id, so the real UI claim was
  rejected (`UnsupportedCommandError`, `ui-claim-result.json`).

## Regression RED → GREEN

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Group | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| A | `tests/unit/test_unknown_payment.py` | factory rejected `payment_state` (field absent) | 5 passed |
| B | `tests/unit/test_claimant_binding.py`, `tests/integration/test_employee_paid_claims.py::test_submit_for_another_activity_is_rejected` | no binding issue produced; submit did not raise | 4 + 5 passed |
| C | `tests/unit/test_coverage_freshness.py`, `tests/integration/test_evidence_finance_workflow.py` (clock, stale-coverage) | `coverage_is_valid` import error | 9 + 5 passed |
| D | `tests/integration/test_context_import_unification.py` | no snapshot created by demo import | 4 passed |
| E | `tests/integration/test_employee_paid_claims.py::test_claim_can_reference_a_server_source_id`, `frontend/tests/intake-submit.test.tsx` | (backend resolver already accepted server id; frontend sent a rejected ref) | backend + frontend 14 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **444 passed, exit 0**.
Frontend (pinned Node 24.19.0, npm's own Node verified): `npm test` → **14 passed**;
`npm run build` → **exit 0**.

## LIVE / HTTP / UI evidence

- **LIVE F01** (`.runtime/f01-fix-verification/run.py`): real Mistral OCR + X-Kiro,
  SIMULATED pilot context, controlled clock `2026-10-10T18:00+07`. Result
  (`.runtime/f01-fix-verification/result.json`): `READY_TO_EXECUTE`, zero issues,
  `COLLECT 760000`, T=E=3240000, A=4000000, S=-760000, unpaid KNOWN 0, basis
  `EMPLOYEE_DECLARATION_Q32`. This is provider/workflow integration evidence, not
  bank verification and not full E2E (no actual-money execution recorded).
- **Negative variants** (`.runtime/f01-fix-verification/variants.py` →
  `variants.json`): stale coverage @14/10 → no effect + `ledger:coverage` FACT +
  unpaid UNKNOWN; claimant mismatch → `expense:claimant_binding` FACT; unknown
  payer (no claim) → unpaid UNKNOWN.
- **HTTP** (`.runtime/f01-fix-verification/http-result.txt`): dev server LIVE,
  upload two PDFs → claim by server source id → worker read → `WAITING`, unpaid
  **UNKNOWN** (was KNOWN 3.24m), demo activity without coverage blocks correctly.
- **UI** (browser, screenshot `/tmp/ui_f01.png`): claim form with document
  selector + quote; audit shows `RECORD_EMPLOYEE_PAID_CLAIMS (Q32)` accepted
  (previously rejected); money panel shows "Chưa thanh toán: Chưa xác minh".

## NOT_RUN / remaining

- **M0 LIVE / RECORDED_REPLAY captures / Docker / public hosting / practitioner
  pilot**: NOT_RUN (unchanged from prior status).
- **Matcher unmatched-paper finding** (investigation §"Additional matching
  inconsistency"): `SET_PAPER_UNMATCHED_001` still references the settlement form
  itself. Out of this write set; recorded here, not suppressed. Admission does not
  consume `match_findings` as a material gate; a targeted matcher/admission check
  is still needed.
- **Duplicate `ledger:coverage` issue** from admission + policy was deduped in
  `reconciliation/service.py`.
- The web server keeps the real clock; a historical-fixture harness must inject
  the controlled clock (never a client value). Today's date (14/10) is after the
  pilot coverage (10/10), so the interactive UI correctly blocks the effect.

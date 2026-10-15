# Remove Activity Budget Gate Implementation Plan

**Goal:** Remove activity budget B from the current settlement decision while keeping cost admissibility, policy, coverage, activity scope, and action authority gates intact.

**Architecture:** Keep legacy budget fields and imported records readable, but stop using them to create FACT/POLICY issues, suppress effects, or change the eligible-cost basis. Reconciliation continues to derive money from verified expenses and ledger history, then checks policy and the existing 8/4/20 action grants.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, React/TypeScript, Markdown/JSON fixtures.

**Spec:** User-approved decision in attachment `97a6fa9f-21dd-4ed2-b164-6178f78c0b0c/Pasted text.txt`; current implementation contracts and design.

## Global Constraints

- Preserve `S = E - A - P + R`; never replace unknown values with zero.
- Keep self-recognition at 8m, system issue/collection at 4m, and approver per-action authority at 20m, with exact action/scope/time checks.
- Preserve coverage, policy, payer, identity, source quality, Stop/Resume, idempotency, audit, and tracing gates.
- Keep activity identity and legacy budget data for compatibility; no database migration or destructive DB operation.
- No gold in runtime/model input; preserve unrelated dirty work; no subagents, commit, push, reset, or LIVE provider call.

## Review Focus

1. Missing B must not create FACT or AUTHORITY; `T > B` must not create POLICY.
2. Varying B alone must leave the result and cost basis unchanged.
3. Missing coverage, unverified advances, policy limits, and action grants must still block independently.
4. A legacy open `budget:B` issue must be closed by normal reassessment without losing other history.
5. Old evaluation rows that exercise financial outcomes remain in the denominator; only B-specific preconditions/data are retired with a recorded reason.

## File Map

- `src/invoice_referee/reconciliation/policy.py`: remove B FACT/POLICY gates only.
- `src/invoice_referee/reconciliation/service.py`: exclude B from cost-basis identity.
- `src/invoice_referee/workflow/service.py`: remove draft-only synthetic budget issue; preserve activity identity.
- `tests/unit/test_policy.py`, `tests/integration/test_answer_loop.py`, `tests/integration/test_root_session.py`, `tests/integration/test_organization_context_records.py`: pin A–H through pure policy, real workflow/API, legacy issue refresh/read, and draft view.
- `data/demo/tc01-*.json`, `data/test-kit/uc03-pilot/**`, `scripts/sinh_uc03_pilot.py`, `tests/unit/test_uc03_pilot_data.py`: remove B from current TC01/pilot context and update preconditions without changing financial oracle values.
- `scripts/du_lieu_kiem_thu/{ho_so.py,dap_an.py}`, `tests/unit/test_pdf_generation.py`: move B-only D06 to future scope with unchanged source/oracle; current authoring denominator 14 and 15-root gate remains NOT_MET.
- `frontend/e2e/budget-retirement.spec.ts`, `frontend/playwright.budget-retirement.config.ts`: isolated STUB browser/API readback for a new DRAFT with no budget question.
- `docs/final/IMPLEMENTATION_CONTRACTS.md`, `docs/final/ARCHITECTURE_AND_EVALUATION.md`, `GLOSSARY.md`, new `docs/adr/0009-activity-budget-out-of-scope.md`, current implementation plan/status: promote the decision and state evaluation scope/evidence.

## Tasks

### Task 1: Reconcile without B

- [x] Rewrite budget-boundary/missing-budget tests as RED cases for no-B, E4/A4 balanced, E3.24/A4 collect 760k, E5/A4 pay 1m, and B low/high invariance.
- [x] Confirm missing-coverage, >8m recognition, >4m issue, category/policy, and wrong-scope-grant tests remain independent.
- [x] Remove the budget-specific FACT/POLICY branch and budget from `_cost_basis`.
- [x] Run unit tests; literal finance outputs and unchanged independent gates pass.

### Task 2: Remove workflow-created B questions and refresh old issues

- [x] Add failing integration/API tests for a draft with no B, reassessment of a legacy open B issue, and preservation of independent issue/history rows.
- [x] Remove the DRAFT-only synthetic B issue; ordinary reevaluation closes stale B issues.
- [x] Exercise real workflow/API plus browser DRAFT/readback and question component; no UI-only filtering.

### Task 3: Data, accepted contract, and evaluation scope

- [x] Remove B from TC01 transfer/cash contexts and UC03-F01–F03 current contexts; retain storage DTO/schema and prove old B fields remain readable.
- [x] Remove B from the UC03-F01–F03 preconditions; T/E/A/P/R/S/route/instruction expectations are unchanged and the 3-case denominator remains.
- [x] Update contracts, design, glossary, ADR, plan, prompts/checklist and status; 8/4/20 remains distinct from legacy B.

### Task 4: Verify and hand off

- [x] Targeted workflow/API, full Python suite, frontend tests/build, and isolated STUB Playwright DRAFT check pass.
- [x] No shared DB/server, original source PDF, or provider call; D06's original oracle is unchanged.
- [x] PASS/NOT_RUN limits recorded in `docs/final/IMPLEMENTATION_STATUS.md`; Git remains uncommitted.

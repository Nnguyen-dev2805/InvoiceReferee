# Money Flow and Settlement UI Simplification Plan

> **For agentic workers:** Implement inline. The user explicitly prohibited subagents, commits, pushes and resets. Keep all existing worktree changes. Use RED → GREEN for each behavior change.

**Goal:** Make each actual money movement a single, source-backed, instruction-bound workflow and show only the accountant/employee action needed at the current step.

**Architecture:** Keep `RecordActual`, the existing OCR reader, source store and admission/coverage rules. Add a durable employee-return draft that uses the existing evidence pipeline, then require the accountant's source-bound confirmation to create `EMPLOYEE_RETURN`. Bind new PAY/COLLECT events to the current instruction ID and derive fulfillment from that ID. Compose the cashflow UI from the money history, only currently valid actions and a conditional coverage confirmation.

**Tech Stack:** Python, FastAPI, SQLite, Pydantic, React/TypeScript, pytest, Vitest and Playwright.

**Spec:** User attachment `f0c96d4d-ccb1-49f6-b998-54285b8d4020`.

## Global Constraints

- Preserve `S = E − A − P + R`; unknown is never zero and no zero-value instruction is created.
- A money upload/read is not an actual movement. Only the accountable confirmation writes a confirmed P/R event.
- `P` means company supplementary payment received; `R` means employee return received by company.
- Each new P/R event names an active instruction. Never mint a transaction identity; use the source's namespaced transaction reference.
- A partial movement leaves the instruction remainder active. A surplus or wrong recipient remains a specific blocker.
- Keep all existing role/scope/version/idempotency/audit/Stop/Resume rules and coverage freshness behavior.
- Do not reintroduce B, company-direct vendor payment, a payer-policy change, or financial facts inferred from declarations.
- Use isolated test DBs/uploads; no user DB reset or business-data mutation. No commit, push or subagent.
- Reuse `case_sources`, `read_root`, `RecordActual`, tenant identity and existing coverage rather than adding a second OCR pipeline.

## Review Focus

- A person uploads a return proof and the UI must show it as awaiting accountant confirmation while R is unchanged.
- A return draft whose collect instruction was fulfilled, superseded, suspended or changed cannot be confirmed against that stale request.
- Two roots or two instructions with the same amount cannot share a movement event; same-root same-key retry stays idempotent.
- Partial/overpayment, wrong payer/payee, pending/failed source and duplicate transfer must remain visible without becoming an incorrect fulfillment.
- A post-coverage movement makes only that root's coverage stale; reconfirmation must reuse prior entries for review but still require an explicit accountant action.

## File Map

- `src/invoice_referee/domain/{finance.py,case.py,commands.py}` and `api/views.py`: optional instruction/draft identities and read-only return-draft view.
- `src/invoice_referee/workflow/{schema.sql,db.py,service.py}`, `api/routes.py`: durable employee-return draft, source-bound accountant confirmation, instruction-scoped fulfillment, idempotency and audit.
- `src/invoice_referee/workflow/money.py`: pure fulfillment by instruction, with legacy-event handling pinned by tests.
- `frontend/src/{App.tsx,roles.ts,api.ts,types.ts,features/{advance.tsx,coverage.tsx,execution.tsx,dossier.tsx}}` plus one focused employee-return/history component: progressive role-aware flow and unambiguous labels.
- `tests/integration/{test_money_execution.py,test_pilot_money_execution.py,test_advance_draft_api.py,test_coverage_confirmation.py}` and focused unit tests: movement ownership, partial/overpay, failed/wrong/duplicate/stale/restart/tenant cases.
- `frontend/tests/{advance.test.tsx,coverage.test.tsx,execution.test.tsx,role-workspaces.test.tsx}` and Playwright money-flow scenario: UI action gating and browser→API→DB→UI proof.
- `docs/final/{IMPLEMENTATION_CONTRACTS.md,IMPLEMENTATION_STATUS.md}`, `docs/adr/0010-accountant-advance-and-coverage.md`, and this plan: operative boundary and evidence.

## Tasks

### Task 1 — Bind P/R movements to instructions

- [x] RED: test instruction ID on the money input/event, partial fulfillment only for the matching active instruction, rejection of stale/wrong-direction/foreign-root instruction IDs, legacy records, and same-key idempotency.
- [x] GREEN: persist optional `instruction_id` in `MoneyEvent` JSON; require it for new `REIMBURSEMENT_RECEIVED`/`EMPLOYEE_RETURN` commands; validate actor, root, direction, active status and source refs at the `RecordActual` boundary; calculate fulfillment from the named instruction. Keep `S` based on all confirmed money movements.
- [x] Verify existing integration/reversal/overpayment tests and update only intended callers.

### Task 2 — Employee return upload and accountant review

- [x] RED: API tests for employee-only upload against an active COLLECT instruction; saved source/read survives a workflow restart; upload does not change R or coverage; accountant confirms one source-bound return; partial/overpay/wrong payee/pending/failed/duplicate/stale-role cases.
- [x] GREEN: add a durable movement-draft record and typed read view; reuse `case_sources`, `read_root`, OCR extraction and `RecordActual`; employee may upload but cannot create money; accountant revalidates the draft and current instruction when confirming.
- [x] Verify retry/reload, dedup and coverage invalidation boundaries in SQLite. Tenant/root foreign-source guards remain enforced by shared upload/record guards.

### Task 3 — Progressive accountant and employee UI

- [x] RED: frontend tests for active PAY/COLLECT gating, no generic random-ID form, employee upload request shape, accountant confirmation and conditional coverage form.
- [x] GREEN: add employee return upload/read flow, accountant review/confirm, PAY form bound to active instruction and proof, explicit P/R labels, no-active-PAY state, hidden current-coverage form with prefilled stale/missing record.
- [x] Preserve Vietnamese labels, document preview selection and accessible labels.

### Task 4 — Full verification and handoff

- [x] Run targeted RED/GREEN tests, full Python suite, frontend tests/build under pinned runtimes.
- [ ] LIVE TC01 Playwright on isolated DB/uploads: create/confirm one 4m advance; confirm full pre-return history to establish COLLECT 760k; employee uploads return proof and R stays unchanged; accountant confirms one R; coverage becomes stale, is re-confirmed explicitly, S reaches zero and the case closes only with no blockers. NOT RUN: the currently available LIVE browser server is backed by the user's persistent DB; no feature-specific isolated LIVE runner is in place.
- [ ] Also verify PAY, BALANCED/S=0, partial and surplus return, failed transfer, wrong payee, duplicate, stale instruction, reload/restart and role boundaries. Distinguish LIVE extraction from deterministic coverage.
- [ ] Update contract/ADR/status with commands, provider mode, clock, source hashes, DB/audit/UI paths and remaining limits. Do not commit.

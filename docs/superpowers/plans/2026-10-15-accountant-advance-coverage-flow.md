# Accountant Advance and Coverage Flow Implementation Plan

> **For agentic workers:** Implement inline with `superpowers:executing-plans`. Each task must show a regression fail before production changes.

**Goal:** Let an accountant durably bind a received-advance voucher and a responsible coverage confirmation to the existing dossier, including a new activity that has no preconfigured activity fixture.

**Architecture:** Keep the dossier root as the server-owned employee/activity scope. Persist advance source bytes through the existing case source store; only a unique, source-supported activity reference or an explicit accountant link confirmation can establish the advance-to-activity relation. Store activity acceptance and history coverage as separate typed records; feed both through admission without changing PROPOSED to AUTHORIZED or granting financial authority.

**Tech Stack:** Python, FastAPI, Pydantic, SQLite migrations, React/TypeScript, pytest, Vitest, Playwright.

**Spec:** User request pasted in attachment `6f2fe1ce-31c0-4bba-b95f-493db980852a` (15/10/2026).

## Global Constraints

- Preserve UNKNOWN as distinct from zero; retain `S = E − A − P + R`.
- Keep activity B out of all settlement gates; retain existing 8m/4m/20m action limits and grants.
- An advance voucher proves neither full history coverage nor payment to the vendor.
- Company/employee/policy/grant identity is tenant-wide context; money, coverage, acceptance, and activity references must be restricted to the dossier's employee and activity.
- Matching on amount/date/name similarity alone is weak; conflicting strong evidence stays unresolved.
- Pending/failed/unknown vouchers never create confirmed A or accepted-work evidence.
- Tenant isolation, actor/session checks, idempotency, case versions, audit, Stop/Resume, and tracing remain intact.
- Use isolated test databases. Do not read or mutate the user's live database, call external providers except the separately authorized LIVE verification, commit, push, reset, or spawn agents.

## Review Focus

- A reference pointing to another activity/employee/company must not be overridden by the currently open dossier.
- A duplicate event identity in another root must be a conflict, even if amount and parties match.
- A same-root duplicate remains idempotent; a changed payload with the same identity remains a conflict.
- A backdated event written after coverage confirmation invalidates that root's coverage before any financial effect.
- An upload alone, a typed free-text answer, or an activity acceptance must not establish coverage or authority.

## File Map

- `src/invoice_referee/domain/finance.py`, `domain/case.py`, `domain/commands.py`, `api/views.py`: typed advance-link, activity-acceptance and coverage contracts.
- `src/invoice_referee/workflow/schema.sql`, `workflow/db.py`: additive per-root records and migration.
- `workflow/service.py`, `workflow/context_records.py`, `workflow/evidence_assessment.py`, `reconciliation/admission.py`, `reconciliation/policy.py`: persistence, scope-safe context composition and admission.
- `api/routes.py`, `api/views.py`, `frontend/src/features/advance.tsx`, coverage UI, API/types: real accountant actions and Vietnamese labels.
- Integration/unit/UI tests: root workflow and API behavior, persistence/restart, tenant/scope isolation, live UI.
- `docs/final/IMPLEMENTATION_CONTRACTS.md`, `ARCHITECTURE_AND_EVALUATION.md`, `GLOSSARY.md`, `docs/adr/`: accepted domain meaning and handoff.

## Tasks

### Task 1: Preserve tenant identity while scoping activity records

**Interfaces:** `load_context(cx, tenant, activity, as_of)` returns organization identity/policy/people/grants from the newest tenant snapshot, overlays the selected activity when present or the server-owned proposed activity row otherwise, and filters ledger/coverage/activity references to that exact activity. No other activity's ledger or coverage may enter admission.

- [x] Add integration regressions for a new proposed activity retaining company/employee identity and policy/grants while excluding another activity's ledger, coverage, and references.
- [x] Run the tests and observe expected failure.
- [x] Implement the scoped context composition without changing activity status or granting authorization.
- [x] Run the targeted tests and observe pass.

### Task 2: Persist and bind advance evidence; record accepted work separately

**Interfaces:** Advance upload uses existing `case_sources` and uploads storage. `AdvanceDraft` carries extracted activity reference(s), any strong conflict, and persistent refs. Accountant confirmation includes an explicit activity-link basis and reason when not uniquely linked by an exact reference. A verified completed event may create an `ActivityAcceptance` scoped by root, employee, activity, event key, actor, time, reason, and durable refs. It is a fact, not a grant or status promotion.

- [x] Add workflow/API integration regressions for source survival after restart, exact reference auto-link, ambiguous explicit accountant confirmation, wrong company/employee/activity conflict, pending/failed rejection, duplicate idempotency and cross-root event conflict.
- [x] Run tests and observe expected failures.
- [x] Implement persistent source handling, evidence-bound linkage, and acceptance persistence/consumption.
- [x] Run targeted tests and observe pass; confirm `activity:proposed:*` remains PROPOSED and no grant/action set changes.

### Task 3: Add structured, actor-scoped history coverage with freshness checks

**Interfaces:** `CoverageConfirmation` captures employee/activity, period start, actual `as_of`, funds, included flow kinds, opening balance, unresolved/unallocated movements, witness refs, reason, actor, recorded time, and root ledger version. Admission creates `CoverageRecord` only from this persisted confirmation and accepts it only while the covered root history version still matches. Only accountant persona may confirm; event writes (including backdated) invalidate only that root's confirmation.

- [x] Add regressions for upload-not-coverage, accountant confirmation consumed by admission, wrong-owner rejection, restart, backdated/supplemental events invalidating stale coverage, and other-root/tenant isolation.
- [x] Run tests and observe expected failures.
- [x] Implement typed coverage persistence, version checking, invalidation and audit.
- [x] Run targeted tests and observe pass; ensure free text alone and event absence still do not imply zero.

### Task 4: Deliver the Vietnamese accountant workflow and verify TC01

- [x] Add UI/API tests for advance source preview/link confirmation and the structured “Xác nhận đã đối chiếu lịch sử tiền” form; verify technical field names/enums do not appear.
- [x] Run frontend tests and observe expected failures.
- [x] Implement the accountant screens and API wiring; update case view after source attachment/version changes.
- [x] Run focused frontend tests and build.
- [x] Run Python full suite and isolated Playwright against separate SQLite/upload paths.
- [x] Run TC01 with the two original settlement PDFs and one chosen 4m advance voucher on a fresh isolated LIVE profile; record provider mode, hashes, clock, revision and separate extraction/link/admission/outcome gates. Employee-return evidence is covered by `test_f01_completed_return_closes_the_loop` in the Python suite; it was not part of the LIVE browser run.
- [x] Update contract, design, glossary, ADR and status with evidence and NOT_RUN/FAIL gates; do not rewrite gold.

## Domain Boundary

### Follow-up — routine button confirmation (15/10/2026)

- [x] RED: routine API record without text, hidden routine text input, and repeat
  record's unsupported TRANSACTION_IDENTITY acceptance basis reproduced.
- [x] GREEN: derive statement at the authenticated source-bound command boundary;
  require explanations only for missing-source-field/manual-link exceptions.
- [x] Keep pending/conflict/ownership/version/idempotency checks; sync acceptance
  DTO and UI basis; update affected browser helper consumers.
- [x] Verify full Python727, frontend38/2skipped, build, and copied-TC01 browser
  first receipt + reload/retry. Restart port8000 preserving business fingerprints.
  Saved LIVE OCR was reused; fresh-provider E2E scenarios were not rerun.

Organization-wide data: organization ID/name, employee names/aliases, policy versions, and grants. These records may be used as matching/reference data across the tenant, but grants still require their exact action/scope/profile/time checks.

Activity/dossier data: activity identity/purpose/status, references, money events, acceptance evidence, coverage, settlement sources and coverage witnesses. These must be exact-root or exact-activity scoped. A tenant-wide record can never substitute for an activity-specific ledger or coverage record.

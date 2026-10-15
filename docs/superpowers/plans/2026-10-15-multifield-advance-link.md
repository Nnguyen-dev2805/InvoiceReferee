# Multi-field Advance Link Implementation Plan

> **For agentic workers:** Execute inline; the user prohibited subagents, commits, pushes and resets. Each behavior change needs a RED test before production code.

**Goal:** Automatically link TC01's completed advance voucher to its settlement root only when tenant-safe identity, specific purpose, declared advance, chronology and uniqueness checks all support the same root.

**Architecture:** Keep explicit reference linking as the strongest path, then add a pure, explainable multi-field decision for unregistered-but-unambiguous references. The workflow gathers evidence and all tenant competitors, persists source-backed signals, and the accountant still confirms actual money. The UI displays the selected voucher and the basis without asking for a second link checkbox when the server has already linked it.

**Tech Stack:** Python, Pydantic, SQLite additive migration, FastAPI, React/TypeScript, pytest, Vitest and Playwright.

**Spec:** User request attachment `d996ecb0-e2d8-49c1-a94e-93755577660e`.

## Global Constraints

- Preserve policy, authority, arithmetic, tenant isolation, Stop/Resume, audit, idempotency and coverage behavior.
- A link never records money, creates coverage, authorizes work or creates a financial instruction.
- Never seed `TU-TC01` into an activity reference catalog for the TC01 LIVE proof.
- No activity-specific edit or rewrite of the original PDFs; use the original source bytes.
- Keep conflicting identity, organization, reference and cross-root transaction evidence blocking.
- Similarity may propose only a candidate; one available candidate is not by itself proof.
- The accountant still confirms the completed transfer and records the money event.
- Use isolated databases/uploads for integration, browser and LIVE verification; preserve the user's active DB/server.
- No commit, push, reset or subagent.

## Review Focus

1. Generic purposes such as “tiếp khách” must never auto-link; TC01's project-specific phrase must.
2. Same employee/company/amount with a different project or competing same-project root must not auto-link.
3. `TU-TC01` only on the voucher is unresolved by reference, but must not veto a valid multi-field result; a reference mapped elsewhere remains CONFLICT.
4. Settlement date, invoice date, work period and transfer date must retain distinct meanings; missing/contradictory dates block auto-link.
5. Duplicate/replayed/concurrent transaction keys, pending vouchers and wrong tenant/root must never create a second confirmed advance or acceptance.

## File Map

- `src/invoice_referee/reconciliation/linking.py`: pure decision and typed match signals.
- `src/invoice_referee/reconciliation/advance.py`: extract source-backed transfer purpose and declared-advance fields into the draft.
- `src/invoice_referee/workflow/service.py`: tenant-wide candidate collection, conflict/duplicate checks, revalidation at record time, acceptance persistence.
- `src/invoice_referee/domain/finance.py`, `src/invoice_referee/workflow/{schema.sql,db.py}`: typed audit signals and additive migration.
- `frontend/src/{App.tsx,api.ts,types.ts,features/{advance.tsx,document_viewer.tsx}}`: explain auto-link, preserve manual review for uncertainty and select the voucher used by the draft.
- `tests/unit/test_dossier_linking.py`, `tests/unit/test_advance_draft.py`, `tests/integration/test_advance_draft_api.py`, `tests/integration/test_advance_record_guards.py`, `frontend/tests/{advance.test.tsx,document-viewer.test.tsx}`, `frontend/e2e/accountant-advance-coverage.spec.ts`: regression gates.
- `docs/final/{IMPLEMENTATION_CONTRACTS.md,ARCHITECTURE_AND_EVALUATION.md,IMPLEMENTATION_STATUS.md}`, `docs/adr/{0008-backend-settlement-linking.md,0010-accountant-advance-and-coverage.md,0011-multifield-advance-link.md}`, `GLOSSARY.md`: operative decision and evidence.

## Tasks

### Task 1: Pure multi-field decision

- [x] RED: Add tests for TC01 specific purpose, generic-only purpose, different project, wrong employee/company, missing/conflicting fields, amount vs declared advance (not expense total), chronology and reference-to-other-activity conflict.
- [x] GREEN: Add `MULTI_FIELD_MATCH` and structured signals. Exact references remain stronger. Multi-field may link only when required identity/company/purpose/amount/time checks pass, all tenant candidates are considered, no competitor is close enough to be ambiguous, and no strong conflict exists.

### Task 2: Workflow persistence and transaction safety

- [x] RED: Add API/workflow tests for unregistered voucher-only `TU-TC01` matching via the two source PDFs, persisted matched/missing/conflicting signals, reload/restart, duplicate key in another root, same-root idempotency, concurrent claims and tenant isolation.
- [x] GREEN: Assemble candidate evidence from server-owned employee/company/activity data and source reports; check existing transaction ownership; re-evaluate the link against current tenant state at confirmation; store the basis, signals and refs in the durable acceptance. Keep money absent until the accountant confirms.

### Task 3: Accountant UI and source preview

- [x] RED: Assert auto-linked explanation and evidence appear with no link checkbox/reason; uncertain links keep the manual flow; conflicts cannot be overridden; the document viewer selects the draft's source ID.
- [x] GREEN: Implement the Vietnamese success/candidate/conflict states and controlled viewer selection without exposing other dossier identities or technical enums.

### Task 4: Contract and end-to-end proof

- [x] Update ADR0008/ADR0010 and add ADR0011; update contract, design, glossary and status. Record the requested source-path correction: original directory is `tc01-hop-le-nhan-vien-hoan-tra-tien-thua`.
- [x] Run targeted tests RED→GREEN, full Python suite, frontend tests/build and isolated Playwright.
- [x] Run LIVE TC01 with `report_hoan_ung.pdf`, `hoa_don_dien_tu.pdf` and `03-bien-nhan-chuyen-khoan.pdf` using the provider's actual evidence, no reference seeding or gold input, isolated DB/uploads. Confirm auto-link in API/UI, then explicitly confirm the advance and inspect DB/audit for exactly one 4,000,000 VND event and one `MULTI_FIELD_MATCH` acceptance. Coverage remains absent until separately entered.
- [x] Record provider mode, real system clock, hashes, commands/results and remaining limits. No commit.

### Follow-up — Vietnamese source dates and saved-draft recheck (15/10/2026)

- [x] RED: reproduce prose-date false missing, day/month swap false support,
  invalid/ambiguous dates and swapped trip endpoints; saved-draft GET and UI absent.
- [x] GREEN: shared calendar parser, field-aware date provenance, extraction prompt
  v2, unchanged multiline-name support and source quotes; recheck stored drafts
  with no provider calls or financial writes.
- [x] Verify: 726 Python tests; 37 frontend passed / 2 skipped; Node24 build;
  Playwright on copied TC01 DB including reload; actual port8000 read-only GET.
  Browser proof reuses stored LIVE OCR, not a fresh provider extraction.
- [x] Restart backend with its existing command, preserve business-table hashes,
  and record evidence in `docs/final/reviews/2026-10-15-source-date-fix.md`.

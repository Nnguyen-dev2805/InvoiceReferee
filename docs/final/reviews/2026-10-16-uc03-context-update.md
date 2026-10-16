# TC01–TC25 context update

## Follow-up — one app with all advances

User requested one shared app that skips accountant advance upload for all25.
The default company-context.json now contains25 confirmed simulated advances and
25 separate activity histories. Optional OrganizationContext.coverages supports
this catalog; load_context selects only the requested activity's history and
ledger, with no changes to one-case legacy coverage or financial thresholds.
This supersedes the earlier common-catalog-without-money description below.

RED two shared-context checks; GREEN21 focused context/history tests including
all25 after restart. Full Python782 passed /5 same pre-existing date-fixture
failures, evidence pytest-all25.xml/log under the same private evidence directory.
Regeneration is byte-identical;65 PDF hashes unchanged. Fresh LIVE/UI NOT_RUN.
README now supplies one startup command with the shared context, fixed clock and
a separate DB. No user server restart or persistent-DB change performed.

User scope: update context from data/demo/README.md, review shared context, remove
unrelated demo cases. No provider call, user DB write/reset, server restart,
commit or push. Initial untracked clean-refactor plan/spec belong to other work.

## Delivered

- Default company context now uses typed OrganizationContext, only25 activities,
  Nguyễn Minh An/An Thịnh, canonical MST0319999996, both business profiles,
  current category policies and8/4/20 authority. No old travel-a…g, STUB
  transcription, legacy budget or preloaded money in the shared catalog.
-25 per-case context.json fixtures: exactly one independently declared simulated
  completed advance, correct employee/activity/transaction, explicit zero-state
  basis for P/R, scoped witnesses, as_of16/10/2026 12:00+07:00.
-25 context-ui.json fixtures: same identities/policies/work, no advance/coverage;
  the accountant must record the actual advance through the source-bound workflow.
- Default catalog is not the financial fixture for all25 cases simultaneously.
  Run cases with isolated DBs; manifest identifies the per-case context. TC12
  requires a real predecessor execution in its test scenario. No duplicate flag,
  fabricated usage, expected E/S or route is injected.
- Existing TC01 root/transfer/cash context paths updated compatibly; receipt
  manifest hashes refreshed. Transfer and cash are alternatives, not two advances.
- Original65 PDF hashes preserved; no gold/expected file edited. No other corpus
  removed. The seven retired activities remain only in a regression test fixture
  at tests/fixtures/legacy-company-context.json; affected old tests and the legacy
  Playwright suite now explicitly use it instead of the public default.
- scripts/sinh_context_uc03.py regenerates the pack deterministically. It reads
  README amount declarations and checks them against source PDF declarations for
  authoring; it never reads gold. This is not the application's OCR path.
- Minimal compatibility edits: file import dispatches typed contexts through the
  existing typed importer; optional company_tax_id is retained by the scoped
  loader. This does NOT implement a new invoice-vs-company-MST validation gate.

## Verification

RED: four new integration tests failed on old common schema/missing manifest.
GREEN:27 relevant tests pass, including all25 contexts through real composition,
scope/restart, reference imports, generator determinism and TC01 PDF regeneration.

Full Python:786 collected, **781 passed /5 failed**. Same pre-existing clock
failures in tests/integration/test_employee_return_draft_api.py:

- test_employee_return_upload_is_durable_but_does_not_record_R
- test_accountant_confirmation_records_one_instruction_bound_return
- test_pending_second_return_cannot_confirm_after_collect_is_fulfilled
- test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction
- test_overpaid_return_is_recorded_but_raises_a_specific_blocker

They retain hard-coded15/10 return dates while new instructions use the real
16/10 clock; this was diagnosed before this task. No financial chronology guard
was weakened. Scope does not include that unrelated fixture repair.

Commands: `rtk proxy uv run python scripts/sinh_context_uc03.py`; targeted pytest
over test_uc03_demo_contexts, test_tc01_demo_context,
test_activity_reference_import, test_uc03_pilot_data; full pytest with explicit
addopts and JUnit output. Python3.12.13/uv. git diff --check exits0.

Private evidence: .runtime/uc03-context-update-20261016/context-check.json,
pytest-final.xml and pytest-final.log. Context check confirms25 cases/50 scoped
contexts, byte-identical regeneration, all65 source hashes unchanged and no
legacy activities/transcription/budget keys under data/demo.

## Limits

Fresh LIVE and browser UI: NOT_RUN. No frontend build/test run for the one
Playwright-fixture-path adjustment. Context readiness is not25-case E2E acceptance:
MST predicate, missing trip facts, service ambiguity, duplicate predecessor and
the known Verify/scorer issues require their own checks. No policy gates were
removed to force AUTO. No new advance/return PDFs were authored for the other
cases. Replacing files does not delete old catalog/cases from an existing DB;
the README uses an isolated database. Receipt confirmation does not require a
new general-history checkbox.

Discovery: current CodeGraph snippets (Verify tier), graph status up-to-date with
older-engine warning; coverage/generation tools unavailable, coverage UNKNOWN.
Scoped config-path fallback mapped callers before modifying fixture paths.

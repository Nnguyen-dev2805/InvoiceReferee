# TC01–TC25 demo contexts

User-authorized execution: update demo context from data/demo/README.md and remove
unrelated demo cases. This task does not change financial rules, PDF sources,
the scorer, the user's persistent DB, or running services.

## Owned files and consumers

- `data/demo/company-context.json`: only the25 declared activities; current
  identity, policy and grants; no seeded document transcription or actual money.
- `data/demo/cases/*/context.json` and `context-ui.json`: per-case isolated
  simulated contexts, with/without independently supplied confirmed advance.
- `data/demo/manifest.json`, short README usage: source hashes, explicit clock,
  scenario prerequisites outside runtime/model input. No expected E/S/route in context.
- `scripts/sinh_context_uc03.py`: deterministic generation of the above; does not
  read gold or mutate PDF/application data. Existing TC01 transfer/cash paths stay
  compatible; inactive seven-travel-case fixture moves to tests only.
- `OrganizationContext.company_tax_id`, scoped loader: store authoritative company
  identity for later validation; does not claim a new tax-validation policy gate.
- context-file import accepts typed data through the existing typed importer;
  old format remains covered by a regression-only fixture.
- related tests/Playwright fixture config: old assertions use the archived test
  fixture; new tests exercise the real demo context and import/restart/scoping.

## Checks

- [ ] RED: exact25 cases, amounts keyed independently from README, no old activity,
  budget/transcription/expected fields, 8/4/20 grants, correct profiles and clock.
- [ ] Generate contexts; two financial starting states per case; no P/R invented.
- [ ] Typed import/restart preserves identity, per-case A, zero-state basis and
  authority limits; unrelated activity does not inherit money.
- [ ] TC12 duplicate requires an actual predecessor in its scenario; do not
  manufacture usage history or a duplicate flag in input.
- [ ] Check deterministic regeneration, source PDF hashes and exact write scope.
- [ ] Run relevant and full Python checks; report pre-existing clock failures
  separately. Fresh LIVE/UI NOT_RUN unless explicitly exercised.

Discovery: CodeGraph current on-disk snippets, Verify tier; project is this repo,
index reports up-to-date with older-engine warning. Generation/coverage tools
unavailable: coverage UNKNOWN. Scoped config-literal searches map consumers.

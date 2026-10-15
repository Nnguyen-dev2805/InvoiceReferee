# TC01 context references and LIVE verification — 15/10/2026

## Verdict

- **Reference import and backend linking: PASS.** Typed and legacy contexts now validate, persist, and expose `activity.references` through the real composition root/catalog. A LIVE TC01 upload linked to `activity:tc01` with basis `DOCUMENT_REFERENCE` in both separate database branches.
- **Expected financial outcome: FAIL in both LIVE branches.** `A=4.000.000`, but `T` and `E` remained `UNKNOWN`; `S` remained `UNKNOWN`; the case stayed `WAITING` with open FACT issues `expense:T` and `expense:payer`. No `COLLECT 760.000` instruction was issued.
- **Re-upload idempotency: PASS as a subcheck in both methods.** After a UI correction sourced from the PDF and a valid demo accountant confirmation, the API view retained `A=4.000.000`; each isolated database still has zero `money_events` rows and zero instructions. The imported context still contains exactly one advance key for that method.
- **Re-upload extraction accuracy: FAIL.** Transfer re-read returned `payer_name=null`; cash re-read returned `payee_name=null`. Those fields were entered from the source PDF in the UI to finish the isolated idempotency check. The corrections do not count as successful OCR extraction.

The overall TC01 LIVE acceptance is therefore **FAIL / incomplete**, despite the import/link fix passing. No formula, policy, authority, coverage, or gold change was made to force the expected result.

## Change made

`references_json` already existed in `context_activities`, `schema.sql`, and migration v6; the isolated LIVE databases report `user_version=6`. No schema or migration change was needed.

- `context_records._project_relational` now validates and upserts the typed activity reference list, including replacing removed references with an empty list for a newer payload.
- The legacy `_DemoActivity` schema now accepts the same optional references through the shared validator. The legacy relational importer persists them and its typed snapshot retains them.
- Missing/null references remain empty. Non-list values, blank entries, non-string entries, and duplicates within one activity fail import rather than being dropped silently.
- Existing `(tenant, activity_id)` uniqueness, snapshot digest/version behavior, audit calls, and tenant-scoped catalog reads remain in place. Settlement matching and financial logic were not changed.

CodeGraph was used before source inspection for both importer paths, the catalog-to-linker call path, and schema version. It returned current on-disk definitions in this session. The CodeGraph generation identifier and coverage-check API were not exposed, so no exhaustive absence claim relies on graph coverage; the changed import paths, schema, and consumers were checked directly and exercised by integration tests.

Changed source/test paths owned by this task:

- `src/invoice_referee/workflow/context_records.py`
- `src/invoice_referee/workflow/service.py` (the pre-existing `company_name` line in this shared dirty file was preserved)
- `tests/integration/test_activity_reference_import.py`
- `frontend/e2e/live-tc01-reference.spec.ts`
- `frontend/playwright.tc01-live.config.ts`

## Backend proof

The new integration tests use `runtime.build_workflow` and both actual importers, not hand-built `ActivityCandidate` instances. They cover typed/legacy references, restart, same-payload import, activity uniqueness, replacing removed references, absent-reference compatibility, invalid declarations, unique reference-only linking, duplicate-reference conflict, tenant isolation, contradictory strong bases, weak-only confirmation, and transaction identity.

- Targeted regression command: `rtk proxy uv run pytest -q tests/integration/test_activity_reference_import.py tests/integration/test_context_import_unification.py tests/integration/test_settlement_link_submit.py tests/unit/test_settlement_link.py` — **29 passed**, exit 0.
- Full Python suite: `rtk proxy uv run pytest -q` — reached **100%**, exit 0.
- Frontend tests: `npm test` — **30 passed, 2 skipped**; existing React `act(...)` warnings in `app-restore.test.tsx`.
- Frontend production build: `npm run build` — exit 0 with Node **24.19.0** / npm **11.12.1**.
- `npx playwright test --config playwright.tc01-live.config.ts --list` — three TC01 tests discovered.
- `rtk proxy git diff --check` — exit 0.

## LIVE setup

Both branches used the real built frontend, `scripts/dev.py --mode live`, configured Mistral OCR and X-Kiro, a headless Playwright browser, one worker, and separate SQLite/upload directories. The application health response reported `mode=LIVE`, `live_ready=true`, LangSmith enabled, and zero export errors. No response was mocked and no state was injected through an API mutation.

The demo assessment clock was `2026-10-14T23:00:00+07:00`; trace timestamps remained real. The transfer branch used port 52016 and `data/demo/tc01-company-context.json`; cash used port 53351 and `data/demo/tc01-chung-tu-ung/context-tien-mat.json`. Each database contains only its own 4-million-VND advance; they were never combined. The original `report_hoan_ung.pdf` and `hoa_don_dien_tu.pdf` were used unchanged. No gold file was loaded.

Commands used (from `frontend/`; all Playwright runs used the config's headless,
one-worker, zero-retry settings):

```sh
rtk proxy uv run --no-sync python scripts/dev.py --mode live --host 127.0.0.1 --port 52016 --context data/demo/tc01-company-context.json --demo-as-of 2026-10-14T23:00:00+07:00 --db .runtime/tc01-reference-live/20261015-005259-ICT/transfer/app.sqlite --uploads .runtime/tc01-reference-live/20261015-005259-ICT/transfer/uploads
rtk proxy env PATH='/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin' LIVE_PORT=52016 TC01_EVIDENCE_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/transfer' PLAYWRIGHT_OUTPUT_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/transfer/playwright' npx playwright test --config playwright.tc01-live.config.ts --grep 'TC01 transfer'
rtk proxy env PATH='/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin' LIVE_PORT=52016 TC01_EVIDENCE_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/transfer' PLAYWRIGHT_OUTPUT_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/transfer/playwright-B-corrected' npx playwright test --config playwright.tc01-live.config.ts --grep 'TC01 transfer B'
rtk proxy uv run --no-sync python scripts/dev.py --mode live --host 127.0.0.1 --port 53351 --context data/demo/tc01-chung-tu-ung/context-tien-mat.json --demo-as-of 2026-10-14T23:00:00+07:00 --db .runtime/tc01-reference-live/20261015-005259-ICT/cash/app.sqlite --uploads .runtime/tc01-reference-live/20261015-005259-ICT/cash/uploads
rtk proxy env PATH='/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin' LIVE_PORT=53351 TC01_EVIDENCE_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/cash' PLAYWRIGHT_OUTPUT_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/cash/playwright' npx playwright test --config playwright.tc01-live.config.ts --grep 'TC01 cash A+B'
rtk proxy env PATH='/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin' LIVE_PORT=53351 TC01_EVIDENCE_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/cash' PLAYWRIGHT_OUTPUT_DIR='/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/tc01-reference-live/20261015-005259-ICT/cash/playwright-B-final' npx playwright test --config playwright.tc01-live.config.ts --grep 'TC01 cash B'
```

The transfer A run stopped waiting for the expected dossier figures after the
backend job had completed; the persisted API/SQLite view was then captured. The
transfer A output directory was later moved to
`transfer/playwright-transfer-submit-interrupted/` to preserve it before the next
run. The remaining commands ran the accountant UI actions independently on the
same branch databases.

### Transfer branch — database `.runtime/tc01-reference-live/20261015-005259-ICT/transfer/app.sqlite`

The employee flow uploaded the settlement report, e-invoice, and transfer receipt. The actual UI settlement-draft response (recovered from the Playwright trace) was `LINKED`, `activity:tc01`, basis `DOCUMENT_REFERENCE`; its source reference is page 1, quote `TU-TC01`. The response also contained a matching `TRANSACTION_IDENTITY` candidate for `FT-TC01-0001`, so the live receipt contains both identities. The separate backend integration test proves that `TU-TC01` alone links without a transaction code.

OCR classified the three sources as `PAYMENT_PROOF`, `SETTLEMENT_FORM`, and `E_INVOICE`. It found `TU-TC01`, `FT-TC01-0001`, the 4-million advance amount, payee, date, invoice number, and invoice total 3.24 million. It marked the payment proof payer `UNREADABLE` / `NEEDS_HUMAN`; the invoice/payment evidence confidence was unresolved. The submitted case then remained `WAITING`, with `T=E=S=UNKNOWN` and open FACTs `expense:T` and `expense:payer`.

The accountant re-read the transfer receipt. The draft returned amount 4 million, payee Nguyễn Minh An, transaction key `FT-TC01-0001`, date `2026-10-05`, `COMPLETED`, and `already_recorded=true`, but payer was null. The source PDF's text layer states the company name, so the UI field was corrected from that source before confirming the simulated duplicate. The API view before/after retained `A=4.000.000`, `P=R=0`, and no instructions. The database has zero `money_events`, zero instruction rows, and still one context ledger key `transfer:FT-TC01-0001`.

The first post-confirmation Playwright assertion failed because its snapshot helper omitted `P` and `R`; that helper has been corrected. I did not repeat the transfer provider read after confirming the API snapshot and SQLite state directly.

### Cash branch — database `.runtime/tc01-reference-live/20261015-005259-ICT/cash/app.sqlite`

The employee UI uploaded the same two original PDFs and the cash voucher. Its live response was `LINKED`, `activity:tc01`, basis `DOCUMENT_REFERENCE`, with the page-1 quote `TU-TC01`; it also found the recorded cash slip `PC-TC01-0001`. The extracted declaration total was 4 million and invoice total was 3.24 million. After submit, the case likewise stayed `WAITING` with `T=E=S=UNKNOWN`, open FACTs `expense:payer` and `expense:T`, and no instruction.

The accountant re-read the cash voucher. It returned amount 4 million, company payer, `PC-TC01-0001`, `COMPLETED`, `already_recorded=true`, and date `05/10/2026` (the document's Vietnamese date format). The payee was null and listed as missing. The UI entry was corrected from the source PDF before confirming the simulated duplicate. API before/after retained `A=4.000.000`, `P=R=0`, and no instructions; SQLite has zero `money_events`, zero instruction rows, and exactly one context ledger key `cash:PC-TC01-0001`.

### Expected vs actual

| Measure | Expected | Transfer actual | Cash actual |
| --- | ---: | ---: | ---: |
| `T` | 3.240.000 | UNKNOWN | UNKNOWN |
| `E` | 3.240.000 | UNKNOWN | UNKNOWN |
| `A` | 4.000.000 | 4.000.000 | 4.000.000 |
| `P`, `R` | 0, 0 | 0, 0 | 0, 0 |
| `S` | −760.000 | UNKNOWN | UNKNOWN |
| Instruction | `COLLECT 760.000` | none | none |
| Case status | not closed/collected | `WAITING` | `WAITING` |
| New money events on re-upload | 0 | 0 | 0 |

The balance was not inferred from a reported total: both actual views remain blocked on open issues. No coverage date was moved forward.

### Read-only admission diagnosis

Rebuilding `AssessmentInput` from each persisted LIVE `ReadResult` and the stored
context (no DB mutation, no provider call) narrows the blocker:

- The single paper row and invoice produce an `Expense` with incurred **3.240.000
  KNOWN**, eligibility `ELIGIBLE`, and payment basis `EMPLOYEE_PAID_INVOICE`; the
  context coverage is present and admission emits no issue for that row.
- `expense_set_complete` is still **false** because at least one document in the
  report is not `profile_status=CLEAR`; the included `PAYMENT_PROOF` is
  `NEEDS_HUMAN` in both LIVE reports. The reconciler therefore does not publish a
  complete `T/E/S` result.
- Separately, `match_paper_evidence` reports `SET_PAPER_EVIDENCE_REQUIRED` and
  `SET_PAPER_UNMATCHED_001`: the paper row references `00000101` while the invoice
  extraction returns `IR26E00000101` (cash `IR26E/00000101`), so that matcher only
  produces `SUGGEST_LINK` by amount/content. The admission mapper itself
  suffix-matches the same invoice and produces the known expense above. This
  mismatch between the evidence-matching finding and admitted invoice basis is
  recorded for the next regression; this task did not alter invoice identity
  rules or convert that number into an advance reference.

These observations explain why the expected result is not currently accepted;
they do not authorize suppressing the unresolved profile/matching gates.

## Traces and artifacts

The isolated branch folders contain Playwright videos/traces/screenshots, the redacted browser diagnostics, captured LIVE extraction/link summaries, database/API summaries, full OCR `ReadResult` artifacts, read-only admission-input rebuilds, input hashes, and LangSmith run references:

- Transfer: `.runtime/tc01-reference-live/20261015-005259-ICT/transfer/`
- Cash: `.runtime/tc01-reference-live/20261015-005259-ICT/cash/`
- Run manifest / final working-tree digest: `.runtime/tc01-reference-live/20261015-005259-ICT/run-manifest.json`

Playwright recorded no console errors. The only failed network requests were source-preview GETs aborted during UI navigation; the LIVE draft and actuals requests returned HTTP 200. They do not indicate a provider error.

LangSmith project `invoice-referee` was queried after the run. Health reported zero export errors. Root trace links:

- Transfer [settlement draft](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/41399e20-8c6c-56c1-829b-f9df7c405c8a?poll=true) · [accountant re-read](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/1b784601-c94c-5d1b-b0b6-0b1a7d61a2b3?poll=true) · [idempotent actuals command](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/db059f78-0d7a-5360-b745-6734f1bf738d?poll=true)
- Cash [settlement draft](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/c0e155d1-3171-515b-b913-6a4d792948f3?poll=true) · [accountant re-read](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/f47aea5f-c8a4-5a82-b3f5-57207acb125a?poll=true) · [idempotent actuals command](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/r/da8113cf-6c04-55d8-9b9c-d2f8154fa9ea?poll=true)

## Limits and next gate

The live receipt included a transaction code as well as `TU-TC01`; only the imported-context integration test isolated reference-only matching. The reference import/link itself is no longer the blocker. The evidence report has an unresolved payment-proof profile and a paper/invoice exact-reference mismatch; those gates leave the final view `WAITING` even though the pure admission mapper can construct one known eligible expense. The re-upload party extraction also needs work before either branch can receive an overall PASS.

The existing contract/design limits the OCR/matching pipeline to evidence proposals and keeps financial rules unchanged. The next implementation task should investigate the open `expense:T` / `expense:payer` blockers and the missing payer/payee extraction separately, with new regression evidence. This run did not change those behaviors.

No commit, push, reset, user database change, or gold edit was made. The two local LIVE servers and SQLite databases were isolated under `.runtime/` and the test servers were stopped after capture.

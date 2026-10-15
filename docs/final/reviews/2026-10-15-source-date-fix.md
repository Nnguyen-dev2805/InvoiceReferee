# TC01 — source-date normalization and saved-draft recheck

User authorized implementation on `final`, base `38d8da3a`, with concurrent dirty
changes preserved. This task owns the date helper, date provenance/linker changes,
saved advance-draft GET/UI and their tests/docs; it does not claim ownership of the
existing broader evidence/finance changes in the same files.

## Reproduction and change

Stored TC01 paper date was `10 tháng 10 năm 2026`; voucher date was `05/10/2026`.
The old linker could not parse the prose date and marked time MISSING. The previous
date provenance check also accepted a day/month swap because it compared digit
sets. New tests failed for those defects before implementation (9 date/extraction
failures), plus 2 missing GET tests and 1 missing UI recheck test.

`source_dates.py` parses complete calendar values without guessing years and
checks source day/month order. Extraction normalizes date-only values to ISO,
retains quotes/timestamp precision, and requests ISO in prompt v2 without adding
model calls. Explicit source ranges bind their start/end fields. Invalid or
multi-date ambiguous quotes do not establish a known date. The existing multiline
company-name source checks still pass.

GET `/api/cases/{root}/advance/draft?draft_id=…` re-evaluates the stored read
against current candidates and transaction ownership. It requires the accountant,
checks source digest/root/scope and returns the existing draft ID with current
link signals; no provider/financial command is invoked. The UI's recheck button
selects the voucher and hides the manual fields when LINKED. Unmapped-code details
stay available without appearing as the main successful-link basis.

## Verification

| Check | Result |
|---|---|
| `rtk proxy uv run --no-sync pytest -v -p no:cacheprovider --junitxml=.runtime/date-fix-pytest.xml` | 726 passed, exit0 |
| Scoped Node24 `npm --prefix frontend test` | 37 passed / 2 skipped, exit0; pre-existing act warnings |
| Scoped Node24 `npm --prefix frontend run build` | Passed, exit0 |
| `rtk proxy git diff --check` | Passed |
| Playwright on copied user TC01 DB | LINKED/MULTI_FIELD_MATCH; checkbox/reason absent; refresh after reload passed |
| Actual port8000 GET after restart | Same automatic link; no OCR/LLM call |
| User business tables before/after restart and GET | All nine hashes unchanged |

Python3.12.13, Node24.19.0, npm11.12.1 were verified. Node selector:
`PATH=/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin`.

Browser server used a copy of the real DB, the real built frontend and workflow;
its provider adapters deliberately reject any OCR/model call. It reuses saved LIVE
OCR rather than claiming a fresh LIVE extraction. Browser/API assertions include
zero new money, activity acceptance, coverage and instruction. Screenshots, trace,
browser script, copied DB and actual-port readback are in
`.runtime/tc01-date-fix-20261015/`; test logs/XML are `.runtime/date-fix-*`.

## Runtime handoff and limits

The existing port8000 backend command was restarted as
`uv run --no-sync python scripts/dev.py --host 127.0.0.1 --port 8000`.
It remains LIVE. Refresh the web page, open **Sổ cái & Dòng tiền**, then click
**Kiểm tra lại bản nháp đã lưu**. No reupload is needed for the captured TC01.
Accountant confirmation of actual money and coverage remain separate actions.

No bank transfer or receipt was executed. Fresh OCR/LLM extraction with prompt v2
is NOT_RUN; deterministic extraction tests verify ISO normalization/source binding
and one primary call. No new dependency, schema migration, DB reset, commit, push
or subagent. The temporary browser server is stopped; the user's backend remains.
CodeGraph current source was used; index-status/coverage tools were unavailable,
so index coverage is UNKNOWN and omitted material ranges were read directly.

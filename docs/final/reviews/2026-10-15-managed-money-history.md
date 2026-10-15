# Managed money history — implementation evidence

Scope approved inline by user on 15/10/2026: one explicit initial accountant
assertion replaces the separate coverage form; accepted in-workflow money does
not require another assertion. No subagents, commits, push or user DB reset.
Baseline `final` / `7e7883c`; changes remain uncommitted.

## Behavior

- UI shows recorded money, one unchecked full-prior-history statement and an
  explicit button. Removed date/fund/opening balance/source/page/quote/reason
  inputs. Actor/scope/clock/version are derived on the server. Upload alone does
  not establish money, history or a zero. Unknown/unallocated/conflicting money
  prevents the initial confirmation.
- `MANAGED_HISTORY` uses existing coverage JSON/table; no migration. Its zero
  opening asserts no omitted carry-in, not a fabricated bank account balance.
  Witnesses may be empty: absence rests on the accountable assertion, not a fake
  PDF quote. Positive money events keep their own source references.
- Source-bound, confirmed/completed A and instruction-bound P/R atomically
  advance the checkpoint with `TRACK_MONEY_HISTORY` audit. Initial actor/time/
  statement remain intact. No renewal after an already stale checkpoint.
- Backdated (before tracked Vietnam calendar day), out-of-band, reversed,
  unresolved/unallocated money or changed imported ledger requires review again.
  Receipt precision is a calendar day; hours are not invented. Midnight alone
  does not invalidate managed history. Legacy structured coverage remains legacy.
- A regression exposed nondeterministic latest-checkpoint selection when server
  clock values tied: select insertion rowid, not random coverage UUID. Regression
  observed RED then GREEN. The history UI also displayed midnight source dates
  as the prior UTC day; a RED→GREEN test now fixes the Vietnam calendar display.

## Verification

- Initial API RED: 3 failed (route absent), then GREEN: explicit assertion,
  accountant-only, current version, persistence across restart/day, no fake fund
  or quote, no money mutation from confirmation.
- UI RED: long form still present and no new button; GREEN: unchecked action,
  request binding, unresolved-money blocking, no second prompt for current state.
- `tests/integration/test_managed_money_history.py`: 9 tests cover typed 3.24m /
  4m loop, full/partial return, unchanged R on upload, one checkpoint, retry,
  restart, PAY400k, balanced/no zero instruction, historical/out-of-band additions,
  changed imported history, unallocated money and reconfirmation at a tied clock.
- `rtk proxy uv run --no-sync pytest -v --junitxml=.runtime/managed-history-pytest.xml`
  → **763 passed**, exit 0. Full log `.runtime/managed-history-pytest.log`.
- Frontend `npm test -- --run` → **43 passed / 2 skipped**, 11 files; existing React
  act warnings in restore tests. `npm run build` → exit 0. Verified scoped Node
  24.19.0 and npm's own Node24 / npm11.12.1. Logs `.runtime/managed-history-*`.
- `git diff --check` → exit 0.

## Browser → API → DB proof

Isolated port65108 and SQLite backup of a prior TC01 test DB. Originals use the
stored real LIVE OCR; the new 760k return uses a valid synthetic PDF and a
deterministic OCR/LLM adapter. No new external provider request. This is browser
integration evidence, **not fresh LIVE OCR quality evidence**.

Playwright completed:
1. One initial statement → COLLECT760000, R=0.
2. Employee uploads/reads return → MATCHED, awaiting accountant, R remains0.
3. Accountant confirms receipt → R760000, S0, SETTLED; no history prompt.
4. Reload retains closed state; latest built UI shows correct Vietnam day and
   visible “Đã quyết toán”.

SQLite readback: one ADVANCE_RECEIVED4000000, one EMPLOYEE_RETURN760000, both
CONFIRMED; one coverage record; one FULFILLED COLLECT760000; one initial assertion
and one managed-update audit event. Evidence folder:
`.runtime/managed-history-20261015/` (`browser-result.json`, `trace.zip`,
`initial.png`, `employee-pending.png`, `settled.png`, `settled-dossier.png`).

## User web and limits

Port8000 restarted with its same `scripts/dev.py --host 127.0.0.1 --port 8000`
command. Health reports LIVE, ready and tracing enabled; OpenAPI includes the new
endpoint. Ten user business-table fingerprints before/after restart match
(`user-db-unchanged.json`); no financial command was sent to that DB.

No bank integration/cryptographic proof is added. Initial completeness is still
the accountant's explicit responsibility; external movements must be declared.
The old LIVE accountant test's selectors were updated, but that full fresh
provider suite was NOT_RUN. Review was a bounded self-review; no independent
subagent review was requested. No new dependencies or public data PDFs changed.

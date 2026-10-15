# Managed money history — initial confirmation, then tracked execution

**Superseded for the ordinary UI by the follow-up below:** user explicitly
removed the remaining initial-history checkbox/action. Do not reintroduce it.

User approved inline implementation on 15/10/2026. No subagents, commits, reset or
business writes to the user's DB. Baseline: final `7e7883c` (clean).

## Accepted behavior

Replace the standalone coverage form with one explicit accountant confirmation:
all prior money movements of this employee/work are recorded, with no unrecorded
opening balance or other movements. This is an accountable assertion, not bank
verification and not an inference from an uploaded receipt. Show recorded totals
before the action. Missing/unallocated/conflicting entries block confirmation.

After this checkpoint the system tracks only verified, source-bound advances and
instruction-bound P/R through the existing workflow. Those movements do not ask
for another history confirmation. Historical additions, reversals, unknown events,
context-ledger changes or a missed ledger version require explicit review again.
Use source calendar days for chronology because PDF dates may have no clock time.
Legacy structured coverage retains its existing behavior; no silent conversion.

## Write set and consumers

- Domain command/API DTO + route: a boolean accountable history confirmation;
  root/employee/actor/time/ledger version are server-derived.
- CoverageRecord: optional managed-history metadata in existing JSON storage.
- Admission validator + workflow history helper + service: persist checkpoint,
  validate scoped local/context history, maintain after approved workflow events.
- React coverage/API/types: remove date/fund/opening/quote form, retain history
  and return review, show one unchecked declaration and explicit button.
- Integration/frontend tests; contract/ADR/runbook/status and this plan.

No schema migration, dependency, provider or financial formula change.

## Gates

- [x] RED→GREEN: initial confirmation requires accountant, expected version and
  explicit true; no implicit money/zero from upload or unchecked action.
- [x] Confirmed return preserves managed history and closes TC01;
  partial/PAY/retry/restart work; out-of-band/backdated/unallocated/context change
  invalidates without automatic recovery. Legacy tests remain valid.
- [x] RED→GREEN: UI removes long form, shows totals and explicit confirmation;
  current history hides action, unresolved transactions block it.
- [x] Python suite, frontend suite/build, diff check, isolated browser→API→DB
  checkpoint/return/close. Mark actual provider mode; fresh LIVE not implied.
- [x] Update operative contract/ADR/status with evidence and remaining limits.

Completion evidence: `docs/final/reviews/2026-10-15-managed-money-history.md`.
Python763 / frontend43 (+2 skipped); isolated browser completed TC01 S0/SETTLED.
Fresh provider LIVE not run; stored original OCR plus deterministic return adapter.
Bounded self-review; no subagents. No commit/push or user business-data changes.

## Discovery limits

CodeGraph source and scoped fallbacks used. Generation/index_status and
check_index_coverage are not exposed; coverage UNKNOWN, required ranges read.
Existing 8000 health is LIVE; health does not prove it loaded the latest files.

## Rulings

- Reuse coverage JSON/table with a distinct managed source; preserve legacy API.
- A checkpoint covers the work's full recorded history and explicitly asserts no
  omitted carry-in; it is not a fabricated account balance or PDF quote.
- Context money fingerprint invalidates financial imports without tying the
  checkpoint to unrelated policy changes. Existing policy/grant checks still run.

## Follow-up — receipt confirmation only (user correction)

- [x] RED→GREEN: completed, source-bound advance confirmation directly enables
  dossier reconciliation; no extra history command, no opening-bank balance.
- [x] Remove history checkbox/button/client call and update callers/E2E expectations.
- [x] Full/partial imported-advance returns work without initial confirmation;
  employee upload alone keeps R unchanged; source/instruction/idempotency guards.
- [x] Python765, frontend43 (+2 skipped), build/diff; isolated browser zero-money
  TC01 → A4m/COLLECT760k → employee proof → accountant receipt → S0/SETTLED.
- [x] Contract/ADR/runbook/status updated. Web8000 restarted, ten business-table
  fingerprints unchanged. No user money writes or fresh LIVE provider calls.

Write set: coverage UI/advance caller/API helper/tests, source enum/admission,
money_history/service receipt boundary, relevant docs and E2E callers. Legacy
history APIs retained for compatibility; no migration. Source scope is dossier
records, not complete external-bank history. Evidence:
`docs/final/reviews/2026-10-15-no-extra-history-confirmation.md`.

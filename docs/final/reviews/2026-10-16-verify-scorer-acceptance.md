# Verify/scorer — corrected acceptance, 17/10/2026

Supersedes the previous “100%/Replay4/4+5/5” report: those runs used synthetic
native PDF text + handwritten extraction and are NOT accepted provider replay.
Original report/probes are preserved in main .runtime/verify-scorer-independent-review-20261017.

## Scope
Worktree codex/verify-scorer, base2a889d5f; authorized fix R1–R5 then integrate
with main dadf563d. No provider quota, real recording capture, shared app DB,
Railway/deploy/push. Existing5case business expectations unchanged; independent
oracle enriched with issue fields/value/source requirements, not app output.

## Fixes
- Synthetic recordings marked SYNTHETIC_FIXTURE. Public replay validates real
  capture metadata/current reader identity/source inventory or NEEDS_RECORDING.
  Null/missing OCR confidence stays unknown; geometry/word data preserved.
- Exact canonical request hash: system/user/source/page/config versions. No
  role-only/single-response fallback. Shared aliases remap registered source IDs;
  response contents still go through current schema/quote/admission validation.
- Structured full issue set, owner/rule/values/dependencies and raw OCR reference
  digest/page/quote checks. All refs must be valid, expected source coverage kept.
  Question linguistic quality remains NOT_REVIEWED; no semantic entailment claim.
- Missing beneficiary/open blocker/invalid state cannot be routine success.
  Balanced requires E/A/P/R/S known, S0, SETTLED, no unresolved execution.
  Persisted case employee is the recipient scope; no input-employee fallback.
- Exact unique suite root membership, locked whole input/context/gold/recording
  file hashes and no symlinks. Missing/corrupt manifest executes zero cases.
  Uses existing bind_sources containment/digest resolver; explicit locked upload roles.
- Isolated per-run/per-case DB, bounded150s/case, per-process single-run lock,
  immutable run reports and atomic last pointer. Report source tree digest rather
  than bare dirty HEAD; actual returned model/effort unknown remain null.
- UI distinguishes NEEDS_RECORDING/errors from executed failure, displays actual
  questions/refs/timestamps and development-set limits. LIVE requires explicit click.

## Current gates
PASS: adversarial RED→GREEN + legitimate structured question/source and balanced
positives; two-source exact replay/request mismatch; synthetic rejection;
manifest/gold tamper and missing middle member; API isolation of nonempty app DB
with network connect blocked; retry creates distinct retained reports; frontend
component/build. Final commands/results and combined main gates in merge ledger
`.runtime/verify-fix-merge-20261017/` at main checkout.

NOT_RUN/NEEDS_RECORDING: real provider capture, Core4/Escalation5 real recorded
replay acceptance, LIVE model quality/latency, independent human question review.
Do not label the development/synthetic suite independent holdout or production ready.

Full backend baseline has six pre-existing failing tests (five employee-return
date fixtures, one ignored legacy corpus packet missing). No xfail/guard weakening.
A merge does not claim full-regression green or real-model acceptance.

## Usage
`uv run --frozen --python3.12 python -m invoice_referee.cli evaluate --suite core --mode replay`
(and escalation) must currently exit1 with NEEDS_RECORDING, completed0, releasefalse.
These are correct blocked states, not benchmark success. No fabricated recordings
should be installed to turn the badge green.

## Independent review fixes before integration
Review Planck found F1 oracle identifiers/card context, F2 all-zero projection,
F3 fabricated authority IDs. Fixed with RED→GREEN: contract IDs
expense:arithmetic:return / RECOGNIZE_COST, numeric card context checks question
plus displayed basis; explicit independent E/A/P/R/S expectations; preserved
actual authority IDs resolved against visible grant action/scope/profile/actor/
amount/time. Added positive actual arithmetic-card and grant tests alongside
wrong-field/value/grant counterexamples. No reviewer re-approval is claimed.

## Combined main integration checkpoint

Implementation commit a0afeb7b; merge06e03767. Tracked shared hunks auto-merged;
S6 modifications remain. Full combined pytest1005 tests:999PASS/6FAIL, exact same
six names as pre-merge main baseline (combined-baseline-comparison.json).
Frontend69PASS/2SKIP/buildPASS. Verify browser Core4/Escalation5/reload PASS with
NEEDS_RECORDING,0completed,0passed,releasefalse; all attempts stored privately.
Independent review fixes tested, no claim reviewer approved the later snapshot.
No LIVE/provider calls, push, deploy, user DB/port8000 mutation.

S6 browser after merge: first attempt timed out at the script's10s actual-response
wait although the DB committed P1m; preserved under failed-s6/. Retry used a fresh
isolated DB with tracing disabled/outbound network blocked:18/18PASS, SETTLED,
P3.7m/S0/PAYFULFILLED/CLOSED_CONFIRMED. Running both Verify suites after this
settlement left the entire app DB SQL dump unchanged (post-settlement-isolation.json).
This is deterministic browser evidence, not LIVE provider or latency validation.

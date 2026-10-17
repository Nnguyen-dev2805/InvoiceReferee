# Escalation answerability — offline implementation acceptance, 17/10/2026

**Verdict: targeted API/UI/browser gates PASS. Full regression remains FAIL on six
inherited tests; LIVE/real-recording/practitioner/rubric20-point acceptance NOT_RUN.**

## Snapshot and ownership

Managed worktree `/Users/tnhatnguyendev2805/.codex/worktrees/escalation-answerability/InvoiceReferee`,
branch `codex/escalation-answerability`, base96e6c4b0. Changes are uncommitted;
main was not edited, merged, restarted or deployed. User requested implementation
quality; no new provider quota or publication authorization was inferred.
Source hashes: `.runtime/escalation-answerability/tested-source-hashes.json`.

RTK0.44.2, uv --frozen/Python3.12.13, Node24.19.0/npm11.12.1. CodeGraph first
looked up main's _decide/_build_assessment_input/cards, then exact source fallback
for the worktree. Worktree graph generation/coverage tools unavailable: UNKNOWN.
No automatic indexing. One integrator; one independent read-only review.

## Implemented behavior

- Server GET card carries current case_version/basis, source quotes, owner,
  typed response kind and per-action amount/limit/authorization explanation.
  No provider call or mutation. Quote identifiers/dates remain verbatim.
- FACT answers cannot act as POLICY/AUTHORITY approvals. Named owner, current
  basis/version, Stop and source membership checked. A response that does not
  resolve the specific fact is refused rather than reported as successful.
  Q32 invoice/employee/amount/refs guards remain.
- Authority decisions persist per action/material basis. E9/A8 approves9m and
  can issue PAY1m; E9/A1 checks RECOGNIZE9 and ISSUE8 separately and atomically.
  Client amount1/wrong scope/action/empty issues/cross root/stale/invalid grant
  cannot authorize either. E25 with grant20 stays blocked.
- Decisions survive reload/reassessment/restart for unchanged inputs, retain
  reason/actor/grant/source audit and never write A/P/R or fabricate closure.
  Revoked/revised grants, changed cost/source/epoch invalidate prior authority.
- Natural grant expiry does not erase approval for an already-issued unchanged
  obligation. Partial/full instruction-bound receipts do not ask for recognition
  again. New/changed obligations still require current authority.
- Reactivated/retained obligations rebind to current authorization IDs with an
  explicit audit event; historical decision refs remain in audit. Stop/Resume
  uses actual root epoch in STUB snapshots, not a hardcoded0.
- CorrectDeclaration is explicit employee-authored revision with reason and
  before/after fields. Original stored report and PDF are unchanged. Code-owned
  correction choices support return/reimburse discrepancies and a unique linked
  expense amount; matching is recomputed from the new claim, not stale allocation.
  Modified original source basis invalidates old revisions. Ambiguous/invoice
  validity changes require genuine source documents, not free-text waiver.
- Missing-original reason can be a responsible row/source-bound declaration;
  it does not waive service/payment/party mismatch. S6 ExceptionReview keeps its
  UI/API and scoped exception persistence, now using server preview basis.
  Foreign client evidence refs are rejected; persisted exception refs come from
  the current server card. RED→GREEN plus8 positive/negative S6/API tests pass.
- Existing OCR region viewer retained. Clean uv exposed undeclared PyMuPDF
  dependency; reused locked PDFium renderer and corrected bundled font path.
  No new runtime dependency or uv.lock change.

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Authority positive/negative/lifecycle | PASS23 tests | test_escalation_decision_roundtrip.py; review-red/green logs |
| TC06 correction/API/read-only/reload/idempotency/source invalidation | PASS | test_escalation_fact_policy_roundtrip.py, test_escalation_card_api.py |
| Unique expense amount correction rematches safely | PASS RED→GREEN | test_escalation_amount_revision.py; allocation-revision-valid-red/green |
| Three routines through typed admission | PASS | test_escalation_routine_regressions.py |
| Reason supplement preserves independent mismatch | PASS | test_escalation_reason.py |
| Full backend | 1033PASS /6FAIL (1039total) | accepted-final-v2.log/xml |
| Full frontend | 73PASS /2SKIP | frontend-accepted.log |
| Production build | PASS | build-accepted.log |
| Browser final core rehearsal | 7/7PASS | browser-output/summary.json + PNG + after.json |
| S6/TC18 self-expense execution compatibility | 18/18PASS, SETTLED/P3.7m/S0 | .runtime/s6-browser/flow-a2-self-clean/ |
| git diff --check | PASS | executed command exit0 |
| LIVE/real recording accepted benchmark | NOT_RUN | no quota used; public Verify remains NEEDS_RECORDING |
| Three actual practitioners / independent rubric score | NOT_RUN | no fabricated users, feedback or20/20 |

Browser scenarios on private ports65201–65208:9m approval→PAY1m; compound9/8;
25m vs20m blocked; TC06 explicit correction→COLLECT830k; TC01 collect760k;
TC02 pay400k; balance settled without zero instruction. Requests originate from
UI, then API and reload assertions inspect stored state. Authority scenarios are
STUB literals; typed paper/routine fixtures are synthetic RECORDED_REPLAY input,
NOT genuine provider captures. Socket hooks deny outbound connections. This
proves deterministic orchestration/response semantics, not OCR/model accuracy.

Earlier compound browser attempt failed on a selector matching a hidden second
card; scoped visible-card retry passed. Both are retained under pre-review-browser.
A seed attempt failed on nested SQLite transaction/session setup; preserved in
browser-seed-failed-01 and logs. No app input/gold was modified to make green.
Final7/7 and18/18 were freshly seeded after review fixes. Last UI-only delta
labels declaration provenance as non-PDF text; component/build verify it and do
not claim a new original file exists. Financial/card API logic is unchanged by it.

Final source-ref guard was added after browser rehearsal; normal S6 and forged-ref
API regression tests were rerun (8PASS), followed by full backend. Browser7/7
and S6 18/18 apply to the preceding snapshot; no final browser rerun is claimed
for this last guard. One Stop test initially reused the preceding command ID;
a fresh command ID now tests the deliberately stale case version. Both failed
attempt logs remain. All8 owned private servers were stopped after cwd/command
ownership checks; user port8000 was untouched.

## Independent review

Godel `.runtime/escalation-answerability/INDEPENDENT_REVIEW.md` requested changes
R1 expiry/receipt, R2 instruction authority rebind, R3 STUB epoch. All reproduced
before fixes (review-red.log), then verified with workflow regression tests,
full suite and final browser runs. No second reviewer approval is claimed.

## Baseline failures (not waived)

The exact six names match main's previously executed full baseline at96e6c4b0.
Five return-fixture tests fail date plausibility; one requires an absent ignored
legacy case06 organization.json. No date guard relaxed and no xfail added.

- `tests.integration.test_employee_return_draft_api::test_employee_return_upload_is_durable_but_does_not_record_R`
- `tests.integration.test_employee_return_draft_api::test_accountant_confirmation_records_one_instruction_bound_return`
- `tests.integration.test_employee_return_draft_api::test_pending_second_return_cannot_confirm_after_collect_is_fulfilled`
- `tests.integration.test_employee_return_draft_api::test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction`
- `tests.integration.test_employee_return_draft_api::test_overpaid_return_is_recorded_but_raises_a_specific_blocker`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]`

## Scope limits and handoff

No automatic original-invoice rewrite or universal source-replacement wizard.
Cards with unsupported/ambiguous source changes explicitly retain blockers and
request corrected original documentation. Narrow employee declaration revisions
are a different provenance layer, never OCR repair or independent proof of money.
Full-suite GREEN and contest20/20 remain unclaimed. Real records/practitioner
acceptance remain separate gates. No new financial thresholds, B, global grants,
scorer/dataset/Verify edits, provider calls, commit/push/merge/deploy or port8000.

Shared hunks: service.py answer/decide/override/snapshot/commit/instruction refs;
API routes/views; domain DTOs and additive schema12; questions.tsx/S6 preview API;
admission consumes scoped reason declarations; policy consumes local decisions.
New modules own authority checks, card construction and declaration revision.
Main currently has unrelated untracked dataset/scripts; leave them untouched.
To integrate later, include untracked new modules/tests/seed/browser assets, never
copy whole shared files over newer main. Re-run combined gates if main advances.

## Additional negative API test — accountant edits employee declaration

Requested additional scenario: accountant submits a valid employee correction
option/basis/version for TC06. Expected rejection: only the named employee may
revise their declaration. Result: PASS, HTTP400/UNSUPPORTED_COMMAND with named
employee explanation. Exact snapshots of cases, declarations/corrections, original
report, issues, instructions and money_events remain unchanged. Zero provider calls.
Evidence: accountant-correction-negative-final.log/xml. Initial test assumed422;
actual documented domain rejection is400; preserved initial status-assumption log.
No application code change. This one added test ran after the full1039-test snapshot;
the full suite was not repeated for this test-only addition.

## Pre-merge refresh — authorized local merge, 17/10/2026

User explicitly requested merge. Branch fresh full suite:1034PASS/6FAIL
(1040total), premerge-final.xml. Current main07ed4a77 full baseline has exactly
the same six failure names (premerge-comparison.json in main runtime evidence).
The additional accountant-correction test is now included in this full run.
No baseline failures waived. Local merge authorized; no push/deploy authorization.

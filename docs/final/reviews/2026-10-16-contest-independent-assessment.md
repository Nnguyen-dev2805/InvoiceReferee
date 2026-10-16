# InvoiceReferee — independent assessment against OrganizationAI Challenge A

Reviewed 16/10/2026. This is an evidence-based review, not a compliance certificate,
an official score, or an implementation task. No application code, existing user
database, deployment, policy or accepted business scope was changed.

## Verdict

**Good fit for Challenge A; not yet supported as a championship-ready submission.**
The strongest differentiator is the controlled transition from source evidence to
financial instructions and then to confirmed money. The largest gaps are the
trustworthiness of Verify/scoring, independent evaluation, real-practitioner
evidence and a reproducible judge-facing demonstration. Adding frameworks,
document types or more UI polish is lower priority than closing these gaps.

The final round is **45 points live demonstration + 35 points defence/interview +
20 points Challenge A validation**. Do not mechanically use the preliminary
40/20/20/20 rubric as the final-round numerical score. General deliverables and
Sprint 2 evidence remain relevant to the judging and interview.

## Scope, snapshot and discovery

- Local branch `main`, HEAD `37e61428`, with pre-existing uncommitted UI changes.
  Prior conversation's `final` is historical branch context; review used the
  actual checkout. Remote main resolved to the same HEAD; remote final resolved
  to `f2b17444`. No checkout, fetch, commit, reset or push performed.
- Authority: `docs/Challenge_Brief_OrganizationAI_VN.docx.md`, current contracts,
  selected architecture/plan sections, implementation checkpoint, sources and
  concrete evidence artifacts. Superseded budget B/history UI decisions were not
  used as current requirements.
- CodeGraph used first for source discovery. Project is this repository; status
  reported up to date, 246 files, with older-engine-index warning. Generation and
  `check_index_coverage` tools are unavailable; coverage is **UNKNOWN**. Material
  source was read through current-on-disk CodeGraph snippets/node ranges. Scoped
  raw fallbacks checked docs, config, test fixtures and absence of adaptation
  references. This is bounded Verify-tier review, not an exhaustive code audit.
- Public Railway home and health checked read-only. No public Verify execution,
  dossier creation, upload, financial confirmation or role change performed.
  Loading the app may create its normal demo session. No fresh OCR/LLM calls were
  made in this review. Saved LIVE evidence is explicitly historical.
- Not checked: full public E2E, private/Drive user feedback, final submitted video,
  full Git history integrity, all source files, all 75 Hoangha inputs or new LIVE
  provider performance. No claim these outside artifacts do not exist.

## Requirements and current evidence

| Requirement | Evidence and assessment |
| --- | --- |
| One routine workflow with documented policy | Employee work-expense settlement; current contracts define the 8m recognition / 4m instruction / 20m approver limits, categories and source rules. Good fit for A. |
| At least 15 cases | Hoangha manifest lists 25 v1 + 50 v2 cases; pilot has three money outcomes. Inventory exceeds 15, but this is not a completed common-policy evaluation or independent test. |
| FACT / POLICY / AUTHORITY | Implemented DTOs, admission/policy branches and selected integration tests. Need judge-facing proof of all three, co-occurrence and answer/resume. |
| Three ordinary + two escalated cases, one action | Suite selection exists; production-facing dataset path is retired, UI only selects development/STUB. Not verified as meeting the contract. |
| Core4 with pass/fail and timestamp | Default CLI fails due missing dataset. API returns zero rows with release=true. Current UI lacks per-case pass/fail, timestamp and answerable question in its table. Must fix. |
| New inputs | Public LIVE health and real upload architecture exist; this review did not execute new provider inputs. Historical one-case success is insufficient proof of generalisation. |
| Stop / override / audit | Stop/Resume and persisted audit exist with tests. Override endpoint exists, but selected test accepts three broad states and does not establish the claimed financial effect or preservation in detail. Need concrete interactive proof, not API existence. |
| Independent error rates | Current independent holdout report was not found in reviewed artifacts; pilot explicitly says development. Historical baseline is development and includes failures. |
| Feedback-based automatic thresholds | T11 is unchecked; no adaptation implementation found in bounded src/tests/frontend search, and no verified-feedback activation evidence supplied. Not demonstrated. |
| At least three practitioners + quotes + traced change + adverse effect | Current protocol is blank, proposal says no results, Slide 3 says not measured. Feedback outside repo remains unverified. |
| Public URL / repo | Railway home HTTP200, no JS page errors observed; health LIVE. GitHub public. Home has eight shared existing dossiers, no first-task instruction or explicit visible synthetic-data notice in captured body. |
| Five slides / video <=3m / one-page build log | Five-slide HTML deck and build log exist. Video script exists; final video availability/duration not checked. Proposal still has link placeholders. Runbook has stale public-hosting/history instructions. |

## Confirmed findings

### 1. Verify can report release with zero executed cases

`api/routes.py:361` uses `data/kiem-thu`, which is absent. `select_suite` returns an
empty list. `IndependentScorer.release_gate` uses only `union == 0`, so a direct
isolated call to the real handler returns, for core/escalation/development:

```json
{"total": 0, "union_dangerous_miss": 0, "release": true, "rows": []}
```

`frontend/src/features/verify.tsx:100` renders this as
`ĐẠT CHUẨN PHÁT HÀNH`. The UI at line39 explicitly calls development/STUB, not
Core4 or Escalation5. The documented default CLI instead correctly exits2:
`không có packet cho suite core ... data/kiem-thu`.

Why tests can pass: `tests/conftest.py:594` generates the retired corpus privately
under `.runtime/legacy-corpus`; `test_verify.py` passes that alternate directory.
This is a different entry path from the public API and default runbook command.

Smallest remedy: one current manifest/source path for app and CLI; exact required
membership/count checks; missing/empty suites are NOT_RUN/error; separate safety,
correctness and execution completeness; test the actual entry points. Keep
STUB/replay/LIVE visibly distinct. Isolate benchmark DB/context/reader wiring:
the current API passes the shared web workflow, while EvaluationRunner imports
context and changes its transcriber. Reconnecting cases must not pollute the demo.

### 2. Scorer has concrete false-pass and false-negative semantics

Three independent synthetic probes against the production scorer:

| Probe | Actual score |
| --- | --- |
| Gold UNSUPPORTED, actual PAY1m | correct_auto_completion1, dangerous0, release=true |
| Gold FACT, actual POLICY/approver | correct_auto_completion0, dangerous0, release=true |
| Valid BALANCED/SETTLED, no instruction | actual_route AUTO, correct_auto_completion0, release=true |

The UNSUPPORTED false pass occurs because scorer.py:146 puts UNSUPPORTED in the
routine branch, and an empty expected_amounts map skips money matching. The
balanced path has no correct-completion branch when no instruction exists.
Wrong category and unsafe money are different errors, but the UI's release label
currently conflates them. `ActualResult` also lacks question text and maps
instruction owner to None in runner.py:34, limiting question-quality and payee
assessment. `refs_ok` only checks presence of refs, not whether they support the
claim. These are measurement limits, not proof the app itself produced each
counterexample.

Smallest remedy: explicit required outcome per route/conclusion, exact money and
recipient, unsupported handling, full issue sets with owners, explicit source
support, answerability review and a correctness pass distinct from financial
safety. Add adversarial tests for the scorer before using its output as evidence.

### 3. Current full-suite failure is date-dependent fixture drift

Fresh pytest: **776 passed, 5 failed**, all in employee-return-draft API tests.
The fixture receipt and model extraction hard-code 15/10/2026. AppFixture uses
the real clock, so new instructions are dated16/10. Return matcher line164 rejects
event_date < instruction_date. The same five original test functions pass with
only the fixture workflow clock set to 15/10/2026 03:00UTC.

This isolates the test failure to inconsistent scenario time; it does not show a
real transfer after its instruction is rejected. Fix the fixture clock or produce
internally consistent dated scenarios. Preserve chronology validation. The same
pitfall applies to replaying yesterday's return PDF in a newly created demo case.

### 4. Do not confuse mechanical/source agreement with service validity

Matching uses exact invoice references (score1) or amount/text/party heuristics;
the so-called semantic similarity is SequenceMatcher string similarity, not a
verified semantic-entailment model. Admission also resolves document references.
A settlement row saying room rental and an invoice saying dining can agree on
invoice number and amount without establishing that the documented service is
the claimed service. The TC05 fix report explicitly leaves this as a separate
question; this review did not claim a fresh end-to-end exploit.

Test a pair with identical source IDs, issuer, amounts and arithmetic but a
materially different service, plus a benign paraphrase pair. Required behavior:
ask for the missing service relation on a real conflict; accept compatible
paraphrases. Do not auto-reject on different words, and do not let an aggregate
confidence score erase an explicit contradiction.

### 5. Judge-facing proof and documents are behind the running product

Railway returned HTTP200 and LIVE health; README includes that URL. RUNBOOK still
says public hosting has not run and refers to retired history confirmation.
Proposal link placeholders remain. Public home has eight generic same-named
dossiers and no visible first-task guidance. This makes the judge spend time
finding the intended workflow rather than testing it. Do not delete the existing
dossiers; add clear curated entry points and an isolated test run.

## Engineering strengths worth retaining

1. Evidence extraction, admissibility, policy/authority and execution are separate.
   Correct source text does not itself grant authority to create a money command.
2. Unknown values stay unknown; money claims and confirmed events are different.
   Employee upload cannot itself increase confirmed company receipts.
3. One simple application with SQLite and a small worker suits the stated pilot
   size. A framework migration would not resolve the observed gaps.
4. Version/epoch/idempotency guards and source references address real financial
   failure modes beyond a visually polished OCR demo.
5. TC05 is a concrete build-log story: observed false collection, source-backed
   arithmetic regression, fresh LIVE blocking result. It shows learning and limits.

Accepted simplifications must be stated precisely: B is out of scope, not equal
to actual advance; EMPLOYEE_PAID_INVOICE is a demo organisation policy assumption,
not independent bank verification; DOSSIER_RECORDS covers admitted case records,
not all external bank activity. Do not reopen these decisions merely to widen scope.

## Priorities and completion evidence

| Order | Action | Required proof |
| --- | --- | --- |
| P0 | Repair scorer and real Verify entry points | Empty suite fails; Core4 exactly4; Escalation5 exactly5/3auto2human; independent expected/actual, correctness, question, source, mode, timestamp; isolated DB; reload/re-run works. |
| P0 | Repair scenario clock reproducibility | Full suite green on controlled clock; separate date-boundary tests; demo PDFs dated consistently with actual instructions. |
| P1, parallel | Obtain/import actual BTC/practitioner feedback | Three named real roles, their own quotes, a traced product change and a concrete adverse effect; consent as appropriate. No agent-created feedback. |
| P1 | Freeze a small independent test with a second author | Lock policy/model/prompt/source hashes; include routine, FACT, POLICY, AUTHORITY, unsupported and material service mismatch. No tuning on holdout; disclose sample size and failures. |
| P1 | Rehearse the final live evaluation | On deployed version: 3routine +2human, a new input, answer/resume, audit source/reason, Stop, actual scoped override, return proof/confirmation/closure. Record actual durations. |
| P2 | Fill submission evidence and Slides3/5 | Real measured before/after with correction/review time, direct feedback/change, observed failure and remaining limit; correct URLs/video/runbook/version. |
| P2 | Implement bounded feedback adaptation if support exists | Adapt a read/matching/escalation threshold using verified separate calibration/validation data; do not tune financial limits/rights. Show actual routing change, validation and rollback. Without support, disclose fixed thresholds. |

For measuring A: missed required escalations / all human-required cases;
unnecessary escalations / all routine cases; separately wrong classification,
wrong person, wrong money, technical failures and answerability. Initial
autonomous result and assisted final result must be reported separately.

For user impact: compare matched tasks with a common endpoint; report active
review/correction time and waiting separately; include onboarding; counterbalance
manual/app order. Three practitioners demonstrate a small pilot, not broad
population performance. Routine money confirmation is execution responsibility;
it should not be counted as an exception escalation. If every routine case still
requires a human to redo eligibility or arithmetic, autonomy has not been shown.

## Fresh evidence from this review

Private reproducibility files: `.runtime/contest-review-20261016/`.

- `pytest.xml`: 781 tests, 776 pass /5fail, 16.13s; Python3.12.13 from uv/.venv.
- Frontend Vitest: 46 pass /2skip, Node24.19.0/npm11.12.1; existing act warnings.
  No frontend production build run and no local server restart.
- `probes.py`, `probes.json`: zero-case API and scorer counterexamples.
- `clock-probe.py`, `clock-probe.json`: all five original failing functions pass
  with controlled fixture time; app code untouched.
- `public-readonly.json`, `public-home.txt`, `public-home.png`: public entry check,
  HTTP200 and no observed page JS errors. Health LIVE/ready/tracing enabled is
  configuration/runtime liveness, not proof of successful provider export.
- Default Core4 CLI exits2. Explicit legacy dataset development/STUB run completed
  with total15, dangerous union2 (D05,D13), POLICY→FACT on D06 and release=false.
  Legacy corpus/gold reflect retired assumptions; this is diagnostic evidence,
  not an independent estimate of current product quality or instruction to weaken
  current guards. Align current fixtures/oracles intentionally before acceptance.
- Historical source-backed LIVE evidence reviewed separately: TC05 fixed run
 72.6s; TC01 no-extra-history browser E2E reused stored LIVE originals and fake
 return adapters. Do not claim these jointly constitute a fresh full LIVE E2E.

No official competition score or win probability is asserted. The documents give
requirements, not information about competing submissions or judges' final marks.

## User clarification during review: feedback has not arrived

The owner confirmed that BTC's three-user feedback has not yet been received and
asked whether it can be simulated. Simulation is useful for rehearsal, usability
hypotheses and checking the study questions. Label it explicitly AI role-play;
it is not practitioner evidence, cannot fill the three real participants, and
cannot supply genuine quotes or measured human impact. The competition explicitly
allows synthetic source data but disqualifies fabricated users/feedback.

Two legitimate next paths: wait for the actual BTC feedback and preserve its
provenance, or recruit real people who actually submit/process settlements and
have them use synthetic dossiers. Video-only comments can support qualitative
feedback but cannot establish measured task-time reduction. Record pending
evidence honestly if neither path completes. Do not publish agent-written quotes
under fictitious practitioner identities or classify internal owner/agent fixes
as improvements caused by the unavailable three-user feedback.

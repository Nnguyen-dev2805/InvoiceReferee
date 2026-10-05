# Evidence — T11 (Verify corpus + runner qua production service)

Mode: PIPELINE_FAKE_OR_REPLAY (replay artifacts, no network). Does NOT prove live
provider quality or deployment (T15). Expected labels live only in the manifest /
runner — never in the application path.

## Commands and results

- RED: `pytest tests/integration/test_verify.py` → runner absent / `FileNotFoundError`
  (fixture path bug) — expected RED before the runner + corpus existed.
- GREEN: `PROVIDER_MODE=fake rtk proxy .venv/bin/python -m pytest tests/integration/test_verify.py -q`
  → 4 passed.
- Full backend: `PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q` → 373 passed.
- Frontend: `npm --prefix frontend run test -- --run` → 5 passed; `npm run build` clean.
- CLI replay:
  - `--suite core` → 4/4 PASS
  - `--suite escalation` → 5/5 PASS
  - `--suite all` → 15/15 PASS (0 fail, 0 inconclusive)

## Corpus (synthetic; gold from the rulebook, not from the running rule)

- development: 15 cases TC01–TC15 (`tests/fixtures/development/manifest.json`).
- calibration: 12 cases, distribution 4 routine / 4 factual / 2 outside / 2 authority.
- holdout: 20 cases, distribution 6/6/4/4.
- Each case has a Claim, a synthetic upload, replay artifacts (document + registry,
  and receipt for WORK_PURCHASE), and a gold expectation. File hashes differ per
  case; the manifest hash excludes itself and is verified on load.

## What was built

- `src/invoice_referee/verify/{__init__,manifest,replay,runner,metrics,jobs,__main__}.py`.
- `ReplayProviders` (a `FakeProviders`) supplies per-case artifacts keyed by ROLE,
  remapped to the ids `Repository` actually assigns — replay never looks up an
  outcome by case id/filename.
- Runner drives the real `CaseService.submit`/`start_run`/`wait` (same path the UI
  uses) and compares actual vs expected; a business REQUEST_INFO/ESCALATE is a
  testcase PASS when it matches expected. Live mode → INCONCLUSIVE (not wired).
- `CaseService.reserve`/`release_reservation`: a Verify suite holds the slot for
  its whole run; interactive run/action/policy update is refused (RUN_BUSY).
- API: `POST /api/verify-runs` (202 + job id), `GET /api/verify-runs/{id}`
  (progress/report); frontend `VerifyPanel` runs core/escalation/all and shows
  expected/actual/verdict. API and runner use the SAME `CaseService` (spy test).

## Gold corrections during build (recorded)

Three generator gold labels contradicted the rulebook and were fixed (the code was
correct): TC09 ELIG-01 REJECT is a known refusal (no open issue); TC14 bill/receipt
conflict owner is REVIEWER (source reconciliation), not EMPLOYEE; TC15 technical
failure has `execution_status=FAILED` per Evaluation §4. Calibration/holdout
"factual" variants expect AMT-01/EMPLOYEE.

## Limits

- Replay/fake only: does not prove live OCR/Kimi quality or the Mistral per-word
  score adequacy (T15, needs spend authorization).
- The "visible numbers" requirement is met by the OCR markdown/gold artifacts;
  synthetic byte files stand in for the raw documents (no PDF renderer installed).

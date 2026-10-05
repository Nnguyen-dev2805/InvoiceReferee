# Evidence — T08 (One-process executor, atomic action, Stop/Override)

Mode: integration / synthetic-fake (real SQLite + `FakeProviders` + a threading
barrier). This proves the executor slot, Stop ordering, closure and action
routing through the REAL service/repository path. It does NOT prove live
OCR/Kimi quality, remote provider cancellation, deployment, or real-user
acceptance. The bundle is injected at the persistence boundary via `seed_case`.

## Commands and results

- RED (before implementation):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_execution_controls.py -q`
  → `ImportError while loading conftest ... ModuleNotFoundError: No module named
  'invoice_referee.application.service'` (feature missing, not a typo).
- GREEN (T08 focus + repository):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_execution_controls.py tests/integration/test_human_closure.py tests/integration/test_repository.py -q`
  → 66 passed (after review round 2).
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 342 passed.
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.
- Flakiness: the covering suite was re-run 3× → 65 passed each time.

## Review round 1 (1 Critical + 1 Important + 3 minors), all addressed

- CRITICAL: DENY / OVERRIDE-DENY leaked the single run slot (permanent RUN_BUSY);
  `_apply_and_start` now returns whether a worker was submitted and the caller
  releases the slot on the synchronous path. Regression tests added.
- IMPORTANT: `schema_meta` version guard (round 2) classifies the DB by its ACTUAL
  schema BEFORE creating anything — a legacy DB (old global `issues(id)` PK, no
  `schema_meta`) is refused at startup instead of being silently stamped.
- Minors: `stage_evidence` unlink now wraps the whole write (COMMIT failures too);
  `_futures` drops done futures; `_confirmation_matches` spelling rule pinned.

## Persisted evidence (SYS-05/06/07)

- Stop: `STOP_REQUESTED` reply + `runs.stop_requested=1` + a `STOP_REQUESTED`
  event, and ZERO `CREATED` payment request after a late provider result.
- Override: the original run/decision are preserved (original run `SUCCEEDED`
  with `REQUEST_INFO`) while the fresh evaluation creates the request.
- Busy: `act`/`start_run` during RUNNING raise `RUN_BUSY`; `stop` is still
  accepted; a data-revising action bumps `case_version` + revokes the request in
  one transaction.

## Carried-from-earlier fixes (T04/T07 reviews)

- `create_run` active set now includes `STOP_REQUESTED`.
- STOP routed via `Repository.request_stop`, never `apply_human_action`.
- CONFIRM_FIELD path reconciled + wired through `process()`/`evaluate`.
- T07 deep checks (ref resolution, full coverage, non-ambiguous units) run at the
  service boundary.
- ADD_EVIDENCE atomic linkage; `issues` table made per-run.

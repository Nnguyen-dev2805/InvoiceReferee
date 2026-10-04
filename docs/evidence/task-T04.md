# Evidence — T04 (SQLite history, evidence artifacts, atomic request lifecycle)

Mode: integration / fake-boundary (synthetic PDF bytes + injected bundle).
Does NOT prove OCR/PDF quality, live providers, deployment, or real-user
acceptance. The bundle in `seed_case` is injected straight into the persistence
boundary; no provider is called.

## Commands and results

- RED (implementation absent):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_repository.py -q`
  → `ModuleNotFoundError: No module named 'invoice_referee.storage'`
  (1 collection error; expected — brief step 1 keeps the test RED until the
  repository/schema exist).
- GREEN (T04 test file):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_repository.py -q`
  → 29 passed.
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 176 passed
  (147 unit from T01–T03 + 29 T04 integration).
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.

## Race orderings (both directions, no sleeps)

`test_stop_before_final_creates_no_request` and
`test_final_then_stop_is_already_completed` pin the two deterministic orders.
`test_concurrent_stop_and_finalize_never_leave_running` runs two real threads
released from a `threading.Barrier` against the same `BEGIN IMMEDIATE` lock and
asserts the persisted invariant: a STOPPED run has zero request, a SUCCEEDED run
has exactly one, and the run is never left RUNNING.

## Scope note

- `seed_case` remaps both the snapshot's logical IDs (`e-1`/`e-2`) and the
  builder bundle's logical IDs (`e-primary`/`e-receipt`) to the real evidence IDs
  `Repository` assigns — verified by
  `test_seed_case_remaps_bundle_to_real_evidence_ids`. `tests/builders.py` was
  NOT modified.
- `request_stop`/`assert_run_current`/`finalize_run` share the same write lock;
  `finalize_run` returns the stored run on a repeat call and ignores the incoming
  result.

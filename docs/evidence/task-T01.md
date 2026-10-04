# T01 evidence — Domain contracts, demo policy và test builders

- **Task:** T01 (contract ledger lock; master plan §3)
- **Branch:** `rebuild` (no commits — work left in the working tree per Global
  Constraints and AGENTS.md)
- **Mode:** PIPELINE_FAKE_OR_REPLAY not applicable — T01 is a pure-contract task
  (no providers, no pipeline). Evidence is a focused unit suite on real records.
- **Timestamp:** 2026-10-04T14:04:55Z

## Runtime

- Python **3.14.5** (`python3`), inside `.venv` created for this task.
- `pip 26.1.1`.
- Installed via `python3 -m venv .venv` then
  `.venv/bin/python -m pip install -e '.[test]'`.
- No dependency required a Python narrower than 3.14; `pip check` clean.

## Commands and outcomes

| Command | Outcome |
| --- | --- |
| `.venv/bin/python -m pip install -e '.[test]'` | OK — built `invoice-referee-0.1.0`, resolved pydantic 2.13.5, fastapi 0.142.2, pytest 9.1.1, httpx 0.28.1 |
| `.venv/bin/python -m pytest tests/unit/test_contracts.py -q` (RED) | 1 error: `ModuleNotFoundError: No module named 'invoice_referee.config'` — failed for the right reason (modules not yet written) |
| `.venv/bin/python -m pytest tests/unit/test_contracts.py -q` (GREEN) | **24 passed** |
| `.venv/bin/python -m pip freeze --exclude-editable > requirements.lock` | OK — 23 pinned packages (no editable self, no secrets) |
| `.venv/bin/python -m pip check` | **No broken requirements found.** |

Lock file SHA256: `4be8429605278b96546161c43e4a63c91c63376a86d0a0dbe294e551beff713a`.

## What the suite proves

- `requested_amount_vnd` is `StrictInt`, positive, `>0`, `<=999_999_999_999_999`;
  `True`, `1.5`, `-1`, `0`, `'1200000'` all rejected; `None` is a valid *missing*
  value (missing ≠ invalid format); the 15-digit upper bound holds.
- Records forbid extras, are frozen (immutable), and reject invalid enum values.
- `PolicyConfig` requires `currency` and `version`.
- `config/demo-policy.json` encodes the PROPOSED demo values
  (2,000,000 / 5,000,000 / 7 days / `'1'` / `'0'` / `'0.85'`) and loads
  **inactive** (`active=false`, `origin='proposed'`, `activation_id=None`).
- The test fixture `demo_policy()` is **active** with `origin='proposed_test_fixture'`
  — distinct from the config file. Runtime does not implicitly activate fixtures.
- `activate_demo_policy` returns a new config with `active=true`, a UUID
  `activation_id`, and `origin='developer_activated_demo'`; a blank reason raises
  `DomainError('INVALID_INPUT', ...)`.
- `StoppedRun` is a `DomainError` with code `STOPPED`.
- `SourceRegistry` rejects duplicate block IDs and duplicate word IDs.
- `snapshot_hash` equals a manual SHA256 of canonical (sorted-key, compact,
  UTF-8) JSON excluding `input_hash`; it is stable across identical snapshots and
  unchanged when only `input_hash` differs; it changes when amount, policy, or
  active action IDs change.
- Builders are gold-independent: TRAVEL/CLIENT_MEAL/WORK_PURCHASE required
  evidence IDs are correct; `document_facts` refs resolve in `text_registry`;
  WORK_PURCHASE at amount=900000 yields 900000/kg ≡ 900/g (both line totals
  900000); mapping pairs the two item IDs; `human_action` carries id/time/version.

## Limitations / notes

- This is a contract suite only. It does not exercise evaluators, storage,
  providers, pipeline, API, or UI (all downstream tasks).
- `AGENTS.md` was intentionally not edited (gitignored; controller-maintained),
  per the binding decision for T01.
- `.gitignore` change is additive; the user's existing edits are preserved.

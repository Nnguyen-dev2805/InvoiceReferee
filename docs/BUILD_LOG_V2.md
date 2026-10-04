# InvoiceReferee — Build Log (V2 / rebuild)

Concise log of what the rebuild actually did. Entries are added per task with
evidence pointers; nothing planned is recorded as done.

## T01 — Domain contracts, demo policy và test builders

- Created the Python package (`src/invoice_referee`, setuptools src layout),
  `pyproject.toml` with `>=3.12,<3.15`, and installed `.[test]` into a new
  `.venv` (Python 3.14.5). Pinned exact versions in `requirements.lock`;
  `pip check` clean.
- Implemented the locked contract ledger (master plan §3.1): strict, immutable
  Pydantic v2 records (`extra='forbid', frozen=True`), all enums as
  `Literal` aliases, `DomainError`/`StoppedRun`, and the `Record` base.
- Implemented `load_policy`, `activate_demo_policy`, `snapshot_hash`
  (`src/invoice_referee/config.py`). `config/demo-policy.json` holds the PROPOSED
  demo values and starts **inactive**; activation is explicit and versioned.
- Implemented gold-independent builders (`tests/builders.py`) and the T01
  contract suite (`tests/unit/test_contracts.py`). RED observed (import error),
  then GREEN: 24 passed.
- Added `.env.example`, `README.md`, additive `.gitignore` entries.
- Evidence: `docs/evidence/task-T01.md`.
- Not done: evaluators, storage, providers, pipeline, API, UI (downstream tasks).

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

## T02 — Numeric parsing, source resolution và derived quality

- Created `src/invoice_referee/policy/{__init__,numeric,quality}.py` (stdlib
  `decimal`/`re` only — no new dependency).
- `parse_candidates(raw, kind, locale)`: explicit `fullmatch` grammars
  (CANONICAL / VI / US); `locale=None` returns the sorted, Decimal-deduped union
  so ambiguous input (`'1.234'` → `1.234` **and** `1234`) keeps every candidate.
  Rejects exponent/NaN/Infinity/junk/sign, money >15 int digits, quantity/price
  >12 int + 6 frac digits, and nonpositive quantity; strips known currency tokens.
- `normalize_quantity(value, unit)`: g/kg/tấn → grams via explicit factors under
  `localcontext(DECIMAL_CONTEXT)` (prec 50, no ambient inheritance); opaque units
  are left unconverted.
- `derive_fact(fact, registry, numeric, threshold, confirmation)`: derived
  usability from real coverage — USABLE only with resolvable refs and all word
  scores ≥ threshold (inclusive), or a valid REVIEWER `CONFIRM_FIELD`. Model
  READABLE never waives missing/low scores; UNREADABLE/UNKNOWN with
  `requires_verification=False` and bad/foreign refs raise
  `DomainError('INVALID_ANALYSIS')`.
- Tests: `tests/unit/test_numeric_quality.py`. RED observed (module missing),
  then GREEN: 47 passed; full suite 88 passed; `pip check` clean.
- Review round 1 (evidence integrity): `derive_fact` now requires the claimed
  `raw_value` to match the resolved locus text and `normalization_trace` to be
  non-empty (mismatch/empty → UNCERTAIN, rescuable by a reviewer confirmation);
  `_find_block` also matches `block.evidence_id`; `parse_candidates` fails closed
  with `DomainError('INVALID_INPUT')` on unknown `kind`/`locale`. Suite 47 → 59,
  full 88 → 100 passed.
- Evidence: `docs/evidence/task-T02.md`.
- Not done: policy/decision evaluators, storage, providers, pipeline, API, UI.

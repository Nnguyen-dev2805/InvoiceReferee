# T02 evidence — Numeric parsing, source resolution và derived quality

- **Task:** T02 (master plan §3.2 T02 row; §1–§2 Global Constraints)
- **Branch:** `rebuild` — committed at `eb11ab0` (`feat(T02): numeric parsing, source resolution và derived quality`).
- **Mode:** pure-evaluator unit suite. No providers, no pipeline, no storage —
  `PIPELINE_FAKE_OR_REPLAY` / `LIVE_END_TO_END` are not applicable to T02.
- **Timestamp:** 2026-10-04T14:29:25Z

## Runtime

- Python **3.14.5** in the repo-root `.venv` (created at T01).
- No dependency added: T02 uses stdlib `decimal` + `re` only.
- `py_compile` clean on `policy/{__init__,numeric,quality}.py`.

## Commands and outcomes

| Command | Outcome |
| --- | --- |
| `.venv/bin/python -m pytest tests/unit/test_numeric_quality.py -q` (RED) | `ModuleNotFoundError: No module named 'invoice_referee.policy'` — failed for the right reason (module not yet written) |
| `.venv/bin/python -m pytest tests/unit/test_numeric_quality.py -q` (GREEN) | **47 passed** |
| `.venv/bin/python -m pytest tests/ -q` | **88 passed** (41 T01 + 47 T02), no regression |
| `.venv/bin/python -m pip check` | **No broken requirements found.** |
| (review round 1) `.venv/bin/python -m pytest tests/unit/test_numeric_quality.py -q` | **59 passed** after the evidence-integrity fix |
| (review round 1) `.venv/bin/python -m pytest tests/ -q` | **100 passed** (41 T01 + 59 T02) |

### Review round 1 (evidence-integrity)

- `derive_fact` now requires `fact.raw_value` to match the resolved locus text
  (canonical numeric form) and `normalization_trace` to be non-empty; mismatch or
  empty trace → UNCERTAIN (fail-closed), still rescuable by a reviewer
  `CONFIRM_FIELD`. `INVALID_ANALYSIS` stays reserved for bad/foreign refs, unknown
  locator/word IDs, out-of-range scores, and the unreadable-without-verification
  contradiction.
- `_find_block` now also matches `block.evidence_id` so a foreign block cannot resolve.
- `parse_candidates` raises `DomainError('INVALID_INPUT')` for unknown `kind`/`locale`.
- `derive_fact` docstring documents the required `numeric=True` for numeric fields.

## What the suite proves

**Numeric parsing (`parse_candidates`)**

- Explicit `fullmatch` grammars: CANONICAL (dot-decimal), VI (grouped-dot +
  decimal-comma), US (grouped-comma + decimal-dot); `locale=None` returns the
  union. `'1.234'`/None → `(1.234, 1234)`, sorted and Decimal-deduped; a
  comma-decimal or dot-grouped form is never silently collapsed to one value.
- `'1.234,56'`/VI → `1234.56`; `'1,234.56'`/US → `1234.56`; `'1.234'`/CANONICAL
  → `1.234`; `'1.200.000'`/VI → `1200000`.
- Exponent (`1e3`, `1E3`), `NaN`/`Infinity`/`-Infinity`, junk (`1.2.3`), sign
  (`-5`/`+5`), and space-separated groups → `()` (never a guessed value).
- Bounds: money ≤15 integer digits (15-digit accepted, 16 rejected); quantity /
  price ≤12 integer + 6 fractional digits; nonpositive quantity rejected while
  zero money is allowed.
- Known currency tokens (`₫`, `đ`, `VND`, `USD`, `$`, `đồng`) stripped; arbitrary
  punctuation is not.

**Unit normalization (`normalize_quantity`)**

- `g`→g, `kg`→g (×1000), `tấn`→g (×1,000,000); input is strip/lowercased.
- Runs under `localcontext(DECIMAL_CONTEXT)` (prec 50): with ambient `prec=2`,
  `123456.789 kg` → `(123456789, 'g')`, i.e. the ambient context is not inherited.
- Opaque units stay unconverted (`thùng`→`thùng`, `hộp`→`hộp`) so equal opaque
  units compare directly and different ones are treated as unknown upstream.

**Derived quality (`derive_fact`)**

- USABLE only when the fact's refs resolve in the actual registry AND all
  relevant words have scores ≥ threshold; threshold is inclusive (`0.85` passes,
  `0.849` fails). Returns a NEW `FieldFact`; the input record is not mutated.
- Model `READABLE` alone never waives missing/low score coverage → UNCERTAIN.
- UNREADABLE/UNKNOWN observation with `requires_verification=False` →
  `DomainError('INVALID_ANALYSIS')` (contract contradiction), never PASS; with
  `requires_verification=True` → UNCERTAIN unless a valid confirmation rescues it.
- Bad block ID, ref from a different evidence, unknown locator, unknown word ID,
  unassigned word used as coverage, and a score outside 0..1 (reported even when
  another word is missing) → `INVALID_ANALYSIS`.
- Empty raw value → MISSING; claimed value with no refs → UNUSABLE; locator with
  no words → UNCERTAIN; empty registry never yields PASS.
- A REVIEWER `CONFIRM_FIELD` on the exact field/value with owned, resolvable refs
  makes a low-score or empty-source fact USABLE without touching raw OCR; wrong
  value, EMPLOYEE mode, `PROPOSE_CORRECTION`, or no refs → not usable.
- Non-numeric fact with a valid source is USABLE regardless of a low word score.

## Limitations / notes

- Pure evaluator suite; it does not exercise providers, storage, pipeline, API,
  or UI (downstream tasks T03+).
- Parser bounds are technical bounds, not company allowances; policy limits live
  in T03. Signed/credit documents are out of scope (SCOPE-02) and rejected here.
- No file outside the T02 packet was modified; `tests/builders.py` was **not**
  touched (its `b-2` block is not needed by these fixtures).

# Compact analysis output implementation — 05/10/2026

User approved the compact model-facing contract after the restaurant live run
produced 32,180 output tokens, invalid refs and a failed repair. This change
implements that boundary; it does not change financial policy or domain records.

## Changes

- `extraction/compact.py`: strict wire raw/src/reading/verify, owned source IDs,
  native word/token scopes, deterministic normalization, missing/uncertain
  handling and recognized-table coverage. No generated OCR scores or numeric
  corrections to make arithmetic pass.
- `providers.py`/prompts: compact schema/prompt version, model source catalog,
  repair with the same schema and previous output, output budget and truncated
  response rejection. Legacy domain/replay fixtures remain domain-shaped;
  live analysis clients must use the new wire version.
- Pipeline retains original and enriched registries so generated source scopes
  resolve during reevaluation/replay. No extra registry write for unchanged fakes.
- Worker-safe HTTP deadline via request-scoped async transport, finite repair
  count and configurable output budget; no new dependency or provider/model switch.
- Verify's API test now waits on an elapsed deadline with a yielding poll instead
  of assuming 200 tight polls are enough. Business expectations unchanged.

## Verification scope

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_compact_extraction.py tests/unit/test_provider_contracts.py -q
rtk proxy .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
```

Initial compact tests were RED against the full-output adapter; core tests GREEN
after implementation. Regression coverage includes owned refs, missing/low
scores, ambiguity, unknown refs/quality bypass, missing required fields,
no-drop/no-merge rows, token truncation, preserved repair budget and worker
deadline. Exact final counts/review are recorded after completion below.

Offline projection of the previous restaurant response decodes 19 items with
owned headers/refs and retains incorrect OCR beer price 28,000. Evaluation is
REQUEST_INFO; AMT-02 UNKNOWN and LIM-01/AUTH-01 FAIL. This is POLICY_REPLAY from
an illustrative projection, **not** a new live response or latency result.
ITEMIZED_WITH_ADJUSTMENTS arithmetic limitations in the current policy remain
outside this patch; the adapter does not invent absent adjustment terms.

Existing user edits in providers/analyze prompt/provider tests were backed up
before editing under `data/output/compact-implementation/20261005T131740Z`.
No stage/commit/push or live API calls were made in this implementation turn.
The prior 91,046→7,601 character sizing was an offline format projection,
not a measured token or live-speed improvement of this implementation.

## Independent review — 4 findings fixed (05/10/2026)

A task review reproduced 3 Critical + 1 Important defects on this patch; all
four are fixed here and each has a regression test (26 compact tests, all pass):

- **CR-01 (digit concatenation).** `_text_key` stripped whitespace/`|`, so source
  `'1 2'`/`'1|2'` matched model raw `'12'` and produced a USABLE `12`. Replaced
  with token-based grounding (`_text_key`/`_grounded`) that never merges digits
  across a separator; the value must be grounded in the cited locator's own words.
  Currency affixes (`'đ'` inside `'120.000đ'`) are still allowed explicitly.
- **CR-02 (dropped unreadable row).** `_table_rows` only counted rows whose
  quantity/price/amount cells ALL parsed, so a `'?'`-quantity row vanished from
  coverage and the doc passed with one item. Now a header-scoped data line whose
  three numeric cells are all PRESENT is an item row regardless of parseability
  (separator/header/footer lines with empty numeric cells excluded), so omitting
  it fails closed (`Missing source item rows`).
- **CR-03 (unqualified locale hint).** `_number_locale` ignored reading/verification
  and word score, letting an UNREADABLE/low-score hint resolve `'1.234'` to `1234`.
  Hints now require a non-UNREADABLE reading, an exact in-scope span, and every
  resolved word meeting the B1 threshold.
- **IM-01 (DNS extends deadline).** `asyncio.run` joined the default executor on
  exit, so a slow resolver kept the caller waiting past `LLM_TIMEOUT` (probe: 20ms
  deadline, 446ms return). `_DeadlineClient.post` now drives a loop it owns with a
  non-waiting `ThreadPoolExecutor`, so the worker returns on the deadline (23ms).

Verification: `pytest tests/` 411 passed; frontend `npm run test` 13 passed;
`pip check` clean. All four reproductions confirmed closed end-to-end (policy no
longer reaches `CREATE_PAYMENT_REQUEST` for CR-01/CR-03; CR-02 fails closed).

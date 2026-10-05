# Evidence — T06 (Production pipeline and vertical slice)

Mode: **integration / fake-boundary**. Uses `FakeProviders` and test builders.
NO live network call, no spend, no live API key.
Proves end-to-end wiring of the processing pipeline from snapshot inputs to
`PipelineResult` and deterministic `Decision`. Does NOT prove live OCR/Kimi
quality, network latency, database persistence, or human intervention loops.

## Commands and results

- RED (implementation absent):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_pipeline.py -q`
  → `ModuleNotFoundError: No module named 'invoice_referee.application.pipeline'`
  (collection error; expected — keeps the suite RED until pipeline exists).
- GREEN (T06 focused suite):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_pipeline.py -q`
  → 21 passed in 0.10s.
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 247 passed in 0.37s
  (195 unit from T01–T03/T05 + 31 repository integration from T04 + 21 pipeline integration from T06).
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.

## Verified behaviors pinned by tests

- Preflight short-circuiting:
  - Inactive policy (`policy.active=False`) → `CONFIG_NOT_ACTIVE` without calling providers.
  - Payer not employee (`COMPANY`, `ADVANCE`, `VENDOR`) or purpose `PERSONAL` → `REJECT` before calling providers.
  - Missing primary invoice or ambiguous multiple primary invoices → `REQUEST_INFO` asking for clarification.
- Vertical slice routine approval:
  - Routine travel snapshot with valid OCR facts produces `Decision(action='CREATE_PAYMENT_REQUEST', completion_basis='ROUTINE_AUTO')` in `PipelineResult`. Payment request creation belongs to T08 `finalize_run`, not the pipeline.
  - Amount over auto-approval threshold (> 2M VND) escalates to `APPROVER`.
- Dynamic active-threshold re-derivation:
  - Pipeline overrides T05 fixed 0.85 threshold by re-deriving quality via `derive_fact` using `snapshot.policy.word_review_threshold`.
- Cross-source proposal gating:
  - Cross-source inventory analysis only executes when `snapshot.claim.profile == 'WORK_PURCHASE'`.
  - Unique item names map deterministically without LLM pairs.
  - Uncertain numeric values on inventory lines escalate to `REVIEWER`.
- Stop checkpoint handling:
  - Stop requested before provider call halts execution without calling the provider.
  - Stop requested after provider call raises `StoppedRun`; execution halts immediately and late provider results are completely discarded without being applied.
- Anti-waiver and error handling:
  - `TOTAL_ONLY` with uncovered OCR item regions is rejected (`_reject_waived_checks`).
  - Transport failures and invalid schemas produce technical `NONE` decisions without corrupting state.
- Isolation:
  - Pipeline does not import storage or SQLite and does not write payment requests directly.

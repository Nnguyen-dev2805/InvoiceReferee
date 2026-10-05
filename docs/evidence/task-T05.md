# Evidence — T05 (Mistral OCR, per-document Kimi, cross-source proposals)

Mode: **fake-boundary / contract**. No live provider call, no API key, no spend.
Proves request shape, contract validation, and the shared repair budget against
injected fake transports. Does NOT prove live OCR quality, latency, or the real
`word_confidence_scores` payload — see `docs/evidence/provider-contract.md`.

## Commands and results

- RED (implementation absent):
  `rtk proxy .venv/bin/python -m pytest tests/unit/test_provider_contracts.py -q`
  → `ModuleNotFoundError: No module named 'invoice_referee.extraction'`
  (collection error; expected — brief step 1 keeps the test RED).
- GREEN (T05 focused, after fix round 1):
  `rtk proxy .venv/bin/python -m pytest tests/unit/test_provider_contracts.py -q`
  → 48 passed.
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 226 passed
  (178 from T01–T04 + 48 T05).
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.

## Verified provider facts (2026-10-05)

Full detail in `docs/evidence/provider-contract.md`.

- Mistral OCR `POST /v1/ocr`, model `mistral-ocr-latest`, with
  `confidence_scores_granularity='word'` returns per-page
  `confidence_scores.word_confidence_scores = [{text, confidence (0–1),
  start_index}]`. **A native per-word numeric score exists**, so
  `registry_from_ocr` carries it; missing scores stay `None` (→ UNCERTAIN), never
  fabricated.
- Kimi/Moonshot `POST /v1/chat/completions`, model `kimi-k2.6`, OpenAI-compatible,
  `response_format={"type":"json_object"}`.
- Thin `httpx` transport chosen over the `mistralai` SDK (which pulls httpx2 +
  jsonpath-python + dateutil for one JSON endpoint); finite 60 s timeout, retries
  disabled.

## Contract behaviour pinned by tests

- Ownership: `doc.evidence_id != request.evidence.id` → `INVALID_ANALYSIS`; a
  registry whose evidence differs from the request is also rejected.
- Uniqueness: duplicate item IDs rejected. Refs: foreign evidence / unknown block
  / unknown locator rejected.
- Coverage: `TOTAL_ONLY` rejected when the registry has OCR item regions
  (fail-closed anti-waiver); itemized template with zero items is rejected; a
  valid itemized document passes even when its `covered_item_regions` labels do
  not match the opaque OCR region ids.
- Quality: an UNREADABLE/UNKNOWN observation with `requires_verification=false`
  is a contradiction → rejected. An honest UNREADABLE+verification → UNCERTAIN.
- Missing/low word score → derived UNCERTAIN; a model `USABLE` claim is
  overridden by real coverage; empty raw → MISSING.
- Applicability decided by code: `TOTAL_ONLY` cannot waive breakdown when regions
  are uncovered or facts carry quantity/unit-price.
- Shared repair budget = 1: malformed-JSON then schema-invalid then correct stops
  after the 2nd response with `INVALID_ANALYSIS` (the 3rd is never requested);
  one repair recovers on the 2nd. Cross-source gets ONE extra invocation (max 3
  calls), then technical. Transport failure → `PROVIDER_FAILED`; missing key →
  `CONFIG_NOT_ACTIVE`; missing token counts → `None`.
- Payload boundary: `analysis_payload` contains only `evidence_id`, `role`,
  `source_registry`, `required_fields`, `threshold_version`, `schema_version` —
  no case ID, employee ID, or employee prose. `cross_source_payload` carries
  facts + refs only.
- Repair accounting: `LiveProviders.repair_calls` + `.repair_reasons` record each
  repair invocation; `FakeProviders` exposes the same fields (zero/empty).
- Item regions: `registry_from_ocr` populates `uncovered_item_regions` from OCR
  table blocks/tables, so the TOTAL_ONLY anti-waiver guard is live in production
  (direction-only; a valid itemized document passes regardless of label ids).
- Broken OCR structure (non-int page index, duplicate page index, bad `pages`)
  → `DomainError('PROVIDER_FAILED')`.

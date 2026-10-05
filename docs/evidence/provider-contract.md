# Evidence — provider contracts (T05)

Verified date: **2026-10-05**. Method: official docs (WebFetch) + the published
Python SDK source (`mistralai/client-python`). No live call was made and no API
key was used — see "What this does NOT prove".

## Mistral OCR — `POST https://api.mistral.ai/v1/ocr`

- Docs: <https://docs.mistral.ai/capabilities/document_ai/basic_ocr/> and
  <https://docs.mistral.ai/api/endpoint/ocr>.
- SDK model docs: <https://github.com/mistralai/client-python> →
  `docs/models/ocrrequest.md`, `ocrresponse.md`, `ocrpageobject.md`,
  `ocrconfidencescore.md`, `ocrpageconfidencescores.md`, `ocrusageinfo.md`.
- Model id: **`mistral-ocr-latest`** (alias; a sample response reported
  `mistral-ocr-2503-completion`). Pinned as `MISTRAL_OCR_MODEL`.

### Request (verified fields)

| Field | Type | Value used |
| --- | --- | --- |
| `model` | string | `mistral-ocr-latest` |
| `document` | `DocumentURLChunk`/`ImageURLChunk`/`FileChunk` | `{type: 'document_url', document_url: 'data:<mime>;base64,<bytes>'}` |
| `include_blocks` | bool | `true` |
| `confidence_scores_granularity` | `'word'`/`'page'`/`'block'` | **`'word'`** |

### Response (verified fields)

- Top level: `pages: list[OCRPageObject]`, `model: str`, `usage_info: OCRUsageInfo`
  (`pages_processed: int`, `doc_size_bytes: int|None`).
- `OCRPageObject`: `index: int` (0-based), `markdown: str`,
  `images`, `tables?`, `dimensions`, `blocks?`, and
  `confidence_scores?: OCRPageConfidenceScores`.
- `OCRPageConfidenceScores.word_confidence_scores?: list[OCRConfidenceScore]`
  — **populated only for `'word'` granularity** — plus
  `average_page_confidence_score`, `minimum_page_confidence_score`.
- `OCRConfidenceScore`: `text: str`, `confidence: float` (0–1),
  `start_index: int` (index into the page markdown).

### Does OCR expose a per-word/per-span score for numeric facts?

**Yes.** With `confidence_scores_granularity='word'`, each page returns
`confidence_scores.word_confidence_scores` = a list of `{text, confidence (0–1),
start_index}`. A numeric span (e.g. `1200000`) is its own entry, so a per-word
score for a required numeric fact **is** available. This meets the B1
source/quality gate at the provider level: `registry_from_ocr` maps each word to
a citable line locator (`{block_id}-l{n}` via `start_index`) and carries the
native score. There is **no** separate "numeric-span" score — the score is
per-word/token; the numeric word's own score is what the gate uses. Scores are
`exp(logprob)`-derived model confidence, a review parameter (threshold 0.85),
**not** a probability that the invoice is correct.

### Does OCR expose item regions (for the TOTAL_ONLY anti-waiver guard)?

**Yes, at region granularity.** With `include_blocks=True`, each page returns
`blocks: list[Block]` in reading order; block variants include `OCRTableBlock`
(`type: "table"`, optional `table_id`, bounding box) and `OCRTextBlock`
(`type: "text"`, `content`, bounding box). Pages may also carry an extracted
`tables: list[OCRTableObject]` (`id`, `content`, `format_`, optional
`word_confidence_scores`). `registry_from_ocr` treats each table block/table as
an **item region** id (`table_id`, or `<block_id>-t{i}`) and lists it in
`SourceRegistry.uncovered_item_regions`. The validator uses these for the
anti-waiver guard: a document that claims `TOTAL_ONLY` while OCR detected item
regions is rejected in production, not only in tests. The check is by direction
only — OCR region ids are opaque/internal, so a valid itemized document whose
`covered_item_regions` uses its own labels still passes (no exact-id matching).
If an OCR deployment returns no table blocks (plain text only),
`uncovered_item_regions` is empty and the guard simply has nothing to assert — it
is not fabricated.

## Kimi / Moonshot — `POST https://api.moonshot.ai/v1/chat/completions`

- Docs: <https://platform.kimi.ai/docs/api/chat> (redirect target of
  `platform.moonshot.ai/docs/api/chat`).
- OpenAI-compatible: `Authorization: Bearer <key>`, body
  `{model, messages, response_format, temperature}`; response
  `choices[0].message.content`, `usage{prompt_tokens, completion_tokens,
  total_tokens}`.
- Model id: **`kimi-k2.6`** (also listed: `kimi-k3`, `kimi-k2.7-code`). Pinned as
  `KIMI_MODEL`.
- JSON mode: `response_format: {"type": "json_object"}` (also supports
  `json_schema`). Used for both tasks.

## Transport decision

A **thin `httpx` transport** is used for both APIs (one client, `httpx` is
already a project dependency) instead of the official `mistralai` SDK. Reason:
the SDK (3.0.0) pulls `httpx2`, `jsonpath-python`, `python-dateutil` and
`opentelemetry-semantic-conventions` for a single JSON endpoint; the OCR API is
a plain JSON POST. Per AGENTS.md "prefer stdlib/native/existing dependencies
before adding new ones". Timeouts are finite (60 s/call) and
`httpx.HTTPTransport(retries=0)` disables retries so the repair budget is not
multiplied. `mistralai` remains installable on Python ≥3.10 if a later task
wants the SDK.

## Configuration (`pyproject.toml`, `.env.example`)

- `httpx>=0.27,<1` promoted from the test extra to a runtime dependency (was
  already locked at `httpx==0.28.1`; `requirements.lock` content is unchanged —
  no new transitive package).
- `.env.example` pins `MISTRAL_OCR_MODEL=mistral-ocr-latest`,
  `MISTRAL_BASE_URL=https://api.mistral.ai/v1`, `KIMI_MODEL=kimi-k2.6`,
  `KIMI_BASE_URL=https://api.moonshot.ai/v1`; keys stay empty. These four values
  are **actually read** by `LiveProviders` (via `os.environ`, hardcoded verified
  defaults as fallback); an explicit constructor argument wins over the
  environment. The composition root (T06) may also pass them.
- Live mode with a missing key raises `DomainError('CONFIG_NOT_ACTIVE')`; a
  transport failure raises `DomainError('PROVIDER_FAILED')`. Neither falls back
  to fake.

## What this does NOT prove (limitations)

- **No live call was made.** API shape is verified from official docs/SDK source,
  but live latency, real score distributions, rate limits, and the exact
  `word_confidence_scores` payload on real Vietnamese receipts are **unproven**.
- Fake transports only prove the request shape and the contract/repair logic.
  They do not prove live OCR quality.
- **Live routine-auto capability: INCONCLUSIVE** until a synthetic live sample is
  run under explicit user authorization (T15). The doc-level signal exists, but
  its real-world adequacy for the 0.85 gate is not measured here.

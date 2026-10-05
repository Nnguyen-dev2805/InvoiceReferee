# InvoiceReferee — Architecture (current state)

> Current-state document for the B1 rebuild. It describes the wiring that exists
> in source and tests, and marks the rest **PLANNED**. Contracts live in
> `docs/specs/`; product behavior in `docs/PRODUCT.md`.

## Layers (IMPLEMENTED)

```
application/pipeline.py   preflight + process (orchestration)
        |
        v
extraction/providers.py   OCR / AnalyzeDocument / ProposeCrossSource boundary
extraction/validation.py  contract + applicability + coverage gate
        |
        v
policy/{numeric,quality,expenses,inventory,decision}.py   pure evaluators
        |
        v
domain/models.py          frozen Pydantic records (shared contract ledger)
storage/{repository,artifacts}.py   SQLite + backend-owned artifacts (T04)
```

The pipeline calls providers, then hands a `CaseSnapshot` + `EvidenceBundle` to the
pure `evaluate`. It never inserts a payment request; `Repository.finalize_run` is
the only writer (T08).

## Pipeline stages

`preflight(snapshot) -> Decision | None` short-circuits cases that need **no
provider call**:

1. config not active / version missing -> technical `NONE` (`CONFIG_NOT_ACTIVE`);
2. payer COMPANY/ADVANCE/VENDOR or purpose PERSONAL -> `REJECT`;
3. no primary bill -> `REQUEST_INFO` (SRC-01, EMPLOYEE);
4. more than one primary bill -> `REQUEST_INFO` (clarify/split, never pick the first).

Otherwise it returns `None` and `process` runs the per-document path:

```
for each evidence (PRIMARY_BILL, GOODS_RECEIPT, CONTEXT):
    checkpoint("ocr:<id>:before") -> providers.ocr -> checkpoint("...:after")
    registry_from_ocr(...)                       # citable source registry
    checkpoint("analyze:<id>:before") -> providers.analyze -> checkpoint("...:after")
    checkpoint("apply:<id>")                     # stop check before applying facts
    re-derive facts with the ACTIVE policy threshold
    write artifacts (raw OCR / registry / parsed document)
optional cross_source (WORK_PURCHASE, only when both docs are usable)
checkpoint("before:evaluate") -> evaluate(snapshot, bundle) -> checkpoint("before:return")
```

`process(snapshot, providers, checkpoint, artifact_writer) -> PipelineResult`
captures every `StageIdentity`, `provider_calls`, `repair_calls`, and
`stage_durations_ms`.

## Key design rulings (recorded at T06)

- **Re-derive at the active threshold.** T05's `validate_document` derives
  usability at a fixed 0.85. The pipeline re-derives every fact with
  `snapshot.policy.word_review_threshold`, so a calibrated B2 threshold actually
  applies. `threshold_version` is carried in the hashed analyze request as
  identity, not parsed as a value.
- **Applicability is code-decided.** `is_applicable` (T05) is wired into the
  production path: a document that claims `TOTAL_ONLY` while facts carry a
  quantity/unit-price basis (or OCR found item regions) cannot waive breakdown —
  it is a technical `INVALID_ANALYSIS`.
- **Providers are called only for the per-document path.** Missing/ambiguous
  required sources and declaration-grounded refusals are decided by code, so no
  OCR/Kimi call is made just to discover a required file is absent.
- **Error classification.** Transport/contract errors -> technical `NONE` with a
  `technical_code` (`PROVIDER_FAILED`, `INVALID_ANALYSIS`, `CONFIG_NOT_ACTIVE`).
  Empty OCR / missing scores are **factual** blockers (-> `UNCERTAIN` -> issues),
  not technical errors, and never an approval.
- **Context evidence.** A provided CONTEXT file is analyzed for facts/conflicts
  relevant to payer/purpose with its own required-field hints; a submitted source
  containing a company-paid contradiction becomes a `MODE-02` factual issue that
  blocks a routine request.
- **Stop.** The checkpoint runs before/after every SDK call, before applying facts,
  before `evaluate`, and before returning. `StoppedRun` propagates to the executor
  (T08) so the run becomes STOPPED, not FAILED. Raw late output may be stored as a
  diagnostic; effective facts / business action are not applied.
- **No caching in B1.** A reevaluation re-calls providers.
- **Purity / no leakage.** No testcase IDs or filenames in production code; prompts
  receive only registry + role + hints (never employee prose or expected labels).

## Provider boundary (IMPLEMENTED, live path unproven E2E)

- `Providers` (ABC): `ocr(evidence)`, `analyze(request)`, `cross_source(bundle)`,
  `identities`. `FakeProviders` is deterministic with a `.calls` trace;
  `LiveProviders` implements Mistral OCR + Kimi/Moonshot over a thin `httpx`
  transport (finite timeout, no retries, repair budget = one shared + one
  cross-source coverage repair).
- **Provider mode is explicit.** The composition root must supply real or fake mode;
  there is no silent live->fake fallback. Fake mode is the default for the test
  suite; no network call is made there.

## Storage (IMPLEMENTED, T04)

- SQLite with one connection per transaction, `BEGIN IMMEDIATE`, foreign keys on.
- One current payment request per case (partial unique index on `status='CREATED'`);
  superseded/revoked rows are kept for history.
- `finalize_run` is one transaction and the only writer of the final action; it
  fails closed on a stale/superseded run or a `CREATE` without a valid amount/basis.
- Artifacts are backend-owned: `put_artifact` sanitizes the name and writes
  atomically under `root/case_id/run_id/`.

## PLANNED (not wired yet)

- `application/human.py` (T07) and `application/{service,executor}.py` (T08).
- `api/app.py` composition root and routes (T09); React UI (T10).
- `verify/` evaluation boundary (T11); `adaptation/` threshold tuning (T13).
- Docker/deployment (T15). No broker, queue, microservice, or shared cache.

Do not treat a PLANNED module as operational because it is named in a spec or plan.

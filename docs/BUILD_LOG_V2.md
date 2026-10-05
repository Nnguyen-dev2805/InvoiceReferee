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

## T03 — Policy, inventory/arithmetic, authority và decision reducer

- Created `src/invoice_referee/policy/{expenses,inventory,decision}.py` (pure
  evaluators; no provider/SQLite/UI imports).
- Full rule matrix (Rulebook §3): SRC-01/02/03, CTX-01, MODE-01/02, SCOPE-01/02,
  ELIG-01, AMT-01/02, LIM-01, AUTH-01, INV-01/02 (inventory only WORK_PURCHASE).
  Inclusive thresholds: ≤2,000,000 ROUTINE_AUTO; >2m–≤5m BEYOND_AUTHORITY;
  >5m BOTH LIM-01 + AUTH-01 (separate authorizations). Accepted amount never
  raised/clipped/dropped; undetermined → no request.
- Arithmetic templates TOTAL_ONLY / SIMPLE_ITEMIZED (ROUND_HALF_UP per line,
  tolerance 1đ) / ITEMIZED_WITH_ADJUSTMENTS (UNKNOWN unless all terms present);
  consistency and arithmetic are separate checks; duplicate item IDs rejected
  before aggregation; unit-price exact on normalized basis. Reducer priority per
  Rulebook §6; N/A ≠ whole-case eligible; missing matrix check → technical.
- Tests: `tests/unit/test_expense_decisions.py`, `test_inventory_arithmetic.py`.
  RED observed, then GREEN; full suite 142 → 147 passed after review round 1.
- Review round 1 (Critical/Important): consume `MappingProposal.conflicts`
  (INV-02 non-PASS); aggregate matrix rules per rule_id (worst-status-wins) for
  multi-document bundles; SRC-01 split from non-BILL primary; SCOPE-02 UNKNOWN on
  unusable currency; registry-less documents flagged not dropped.
- Evidence: `docs/evidence/task-T03.md`.
- Not done: storage, providers, pipeline, API, UI (downstream tasks).

## T04 — SQLite history, evidence artifacts và atomic request lifecycle

- Created `src/invoice_referee/storage/{schema.sql,repository,artifacts}.py`
  (stdlib `sqlite3`, no ORM). Connection per transaction (`isolation_level=None`
  + explicit `BEGIN IMMEDIATE`), FKs on, JSON payload columns; partial unique
  index `one_current_payment_request ... WHERE status=CREATED`.
- `Repository`: create/get/list case, snapshot, create_run, get_run,
  request_stop, assert_run_current, finalize_run, get_payment_request,
  apply_human_action, history, mark_interrupted_runs, record_stage,
  record_policy_change, get_active_policy. Atomic artifact write (mkstemp +
  fsync + os.replace), sanitized basenames, backend-assigned paths.
- `finalize_run` atomic: stop flag, current-run, case_version and input_hash
  checked under one write lock; idempotent (repeat returns stored run); CREATE
  needs positive VND amount; identical request returns existing; changed
  input/decision revokes/supersedes in the same transaction as the version bump.
  Stop-before-finalize → STOPPED/zero request; finalize-before-stop →
  ALREADY_COMPLETED. `policy_versions` persists activation across restart.
- Intake validation (meaningful input, strict positive int, ext/mime, 12/15 MiB/
  50 MiB limits, byte dedup); missing amount/purpose/bill = factual, not format.
- Tests: `tests/integration/{support,test_repository}.py` (real SQLite +
  threading.Barrier race). RED observed, then GREEN; full suite 176 → 178 passed.
- Review round 1 (Critical/Important): `finalize_run` current-run guard (a
  superseded run can no longer create/supersede a request); `create_run`
  active-run guard (RUN_BUSY); dead const removed; stable STALE_VERSION code;
  run_id identity comment; concurrency test asserts threads joined.
- Evidence: `docs/evidence/task-T04.md`.
- Not done: providers, pipeline, API, UI (downstream tasks).

## T05 — Mistral OCR, per-document Kimi và cross-source proposals

- Created `src/invoice_referee/extraction/{providers,validation}.py` + prompts
  `{analyze-v1,cross-source-v1,repair-v1}.txt`. `Providers`/`LiveProviders`/
  `FakeProviders` (same signatures, `.calls`, subclassable), `registry_from_ocr`,
  `validate_document`. Thin `httpx` transport (no extra SDK); finite 60s timeout,
  retries disabled.
- One SHARED repair budget per invocation (malformed→schema-invalid→stop after
  2nd with INVALID_ANALYSIS; no 3rd call); cross-source gets one extra. Repair
  count/reason recorded. No fabricated scores: missing word score → None →
  UNCERTAIN. No prose/label/case-ID leakage; one evidence per analyze.
- Verified official Mistral OCR exposes native per-word confidence
  (`confidence_scores_granularity="word"`), so the B1 quality gate is
  provider-feasible — but real adequacy on Vietnamese receipts is unmeasured.
  Live smoke deferred to T15 under explicit spend authorization.
- Tests: `tests/unit/test_provider_contracts.py` (fake transports only). RED
  observed, then GREEN; full suite 178 → 226 passed.
- Review rounds 1–2: threshold_version into the analyze request hash; repair
  count/reason recorded; `uncovered_item_regions` populated from OCR tables so
  the TOTAL_ONLY anti-waiver guard is live; malformed OCR page → PROVIDER_FAILED;
  coverage reconciliation relaxed to direction-only (valid itemized output is no
  longer rejected on opaque label mismatch).
- Evidence: `docs/evidence/provider-contract.md`, `docs/evidence/task-T05.md`.
- Not done: pipeline, API, UI (downstream); live provider quality (T15).

## T06 — Production pipeline và vertical slice

- Created `src/invoice_referee/application/{__init__,pipeline}.py`. `process()`
  runs preflight → OCR → registry → AnalyzeDocument → validate_document →
  re-derive at the ACTIVE policy threshold → cross-source (WORK_PURCHASE) →
  `evaluate`, returning a `PipelineResult` (decision, bundle, artifacts,
  identities, durations, call counts). `preflight()` short-circuits no-provider
  cases (config inactive, grounded refusal, missing/multi primary) and returns
  None when providers must run.
- No payment request is inserted in the pipeline (T08/finalize_run writes).
  Checkpoints before/after each SDK call and before apply/evaluate/return;
  `StoppedRun` propagates (STOPPED, not FAILED) and late output is diagnostic
  only. Technical vs business errors are separated; identities (incl. repairs)
  and call counts captured. `is_applicable` is wired so applicability is
  code-decided.
- Tests: `tests/integration/test_pipeline.py` (FakeProviders). RED observed,
  then GREEN; full suite 226 → 247 passed. Vertical slice: TRAVEL 1.2m → CREATE;
  missing primary → REQUEST_INFO; 2.000.001 → ESCALATE approver; company-paid/
  PERSONAL → REJECT (no provider calls); inactive/timeout/invalid schema →
  technical NONE; WORK_PURCHASE inventory + unique-name code join.
- Review round 1: code-side unique normalized-name 1:1 mapping; MODE-02 check
  replaced not duplicated; identities captured by index (repairs retained);
  header fields require USABLE; cross-source gated on item usability.
- Created `docs/PRODUCT.md`, `docs/ARCHITECTURE.md` (actual pipeline/wiring).
- Evidence: fake-pipeline only; live OCR/Kimi quality unproven (T15).
- Not done: human actions, executor/Stop, API, UI (downstream tasks).

## T07 — Human action validation, closure và input revision

- Created `src/invoice_referee/application/human.py`
  (`validate_human_action(action, snapshot, decision) -> HumanAction` +
  `authorization_matches`). Discriminated payload validation with extra keys
  rejected; role/scope per kind (EMPLOYEE/REVIEWER/APPROVER/POLICY_OWNER, 5m
  boundary); no approve-all; confirmation effective only for the named
  field/source/case-version; OVERRIDE re-checks the wrapped operation's keyset.
  Authorization bound to case_version + policy_version + profile + purpose +
  amount. Pure (no SQLite/providers/UI).
- Modified `src/invoice_referee/storage/repository.py`: `apply_human_action` in
  ONE transaction (append action/event, version bump when data changes, revoke
  affected request, keep old run); `snapshot()` active-ID closure excludes
  `PROPOSE_CORRECTION` from both `confirmations` (hashed) and `active_action_ids`.
- Tests: `tests/unit/test_human_actions.py` (validator + repo scope). RED
  observed, then GREEN; full suite 287 → 306 passed.
- Review round 1: OVERRIDE keyset for all ops; deep ref/coverage/unit checks
  documented as T08-owned (not claimed); canonical-string-only numeric
  confirmations; declaration value type-check → INVALID_ACTION; proposal no
  longer changes the recomputed hash; added coverage tests.
- Scope: T07 is validator/repository; end-to-end service closure is T08.
- Evidence: fake/synthetic; live quality unproven (T15).
- Not done: executor/Stop, API, UI (downstream tasks).

## T08 — One-process executor, atomic action và Stop/Override

- Created `src/invoice_referee/application/{service,executor}.py`: `CaseService`
  (submit, start_run, get_run, act, add_evidence, stop, wait, set_policy, close)
  over one `ThreadPoolExecutor(max_workers=1)` with a one-permit semaphore. `wait`
  never flips status on timeout. Persisted Stop flag + STOP_REQUESTED event
  written before ack; no late business action; `StoppedRun` → STOPPED; repeat Stop
  idempotent; completed run → ALREADY_COMPLETED. `set_policy` idle-only; SYSTEM
  actor may change only `word_review_threshold`/`threshold_version`.
- Wired the carry-forwards: `create_run` active set includes `STOP_REQUESTED`;
  STOP routed via `Repository.request_stop`; CONFIRM_FIELD path reconciled with
  `quality._confirmation_matches` and confirmations threaded through `process()`;
  T08-owned deep ref/coverage/unit checks (`_deep_confirm_field`/
  `_deep_confirm_mapping`); `stage_evidence` all-or-nothing ADD_EVIDENCE.
- Modified `policy/{decision,expenses,inventory,quality}.py` and
  `application/pipeline.py` to thread `confirmations` (no-op when absent);
  `storage/repository.py` + `schema.sql` (`issues` PK → `(run_id,id)`,
  `schema_meta` version guard).
- Tests: `tests/integration/{conftest,test_execution_controls,test_human_closure}.py`
  (barrier-driven ordering, persisted invariants, no hung workers). RED observed,
  then GREEN; full suite 306 → 342 passed.
- Review rounds 1–2: DENY/OVERRIDE-DENY no longer leaks the executor slot
  (service would otherwise brick with RUN_BUSY); schema guard classifies a DB by
  actual DDL (fresh/current/legacy) and refuses a legacy DB instead of silently
  stamping it; stage_evidence unlink wraps the whole write; `_futures` pruned.
- Evidence: fake/synthetic; live quality/remote cancellation unproven (T15).
- Not done: API, UI (downstream tasks).

## T09 — FastAPI composition và contract responses

- Created `src/invoice_referee/api/{__init__,app}.py`: `create_app(service)`
  (tests inject a service) and `create_runtime_app()` (composition root builds
  repo/providers/policy/service ONCE). Routes: POST/GET `/cases`; POST
  `/cases/{id}/runs`; GET `/runs/{id}`; POST `/cases/{id}/actions`; POST
  `/runs/{id}/stop`; GET `/cases/{id}/history`, `/payment-request`,
  `/evidence/{id}` (owned only); GET `/policy`, POST `/policy/activate`;
  GET `/health`. No decision logic in routes. No Verify routes (T11).
- `PROVIDER_MODE` explicit fake/live, no silent fallback (invalid/missing →
  RuntimeError). Multipart intake (`claim_json` + files + roles) with strict
  Claim + storage limits, never `stored_path`; ADD_EVIDENCE → `add_evidence`.
  Error envelope `{code,message}` with the ledger DomainError→HTTP mapping;
  execution-started failures live in the RunRecord, not HTTP. Policy activation
  (POLICY_OWNER + reason) persists config+event; runtime starts INACTIVE.
- Tests: `tests/integration/test_api.py` (real TestClient + T08 `runtime`
  fixture). RED observed, then GREEN; full suite 342 → 369 passed.
- Review round 1: malformed/non-JSON action body → 422 envelope (was 500);
  removed the `CaseService.repo` leak (narrow read-only service methods);
  `_http_error` preserves status; `ActionBody.payload` default_factory;
  fake-mode doc note; sanitized echoed `original_name`.
- Evidence: fake-provider wiring only; live quality/deployment unproven (T15).
- Not done: UI, Verify, deployment (downstream tasks).

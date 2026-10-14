# LangSmith — nối tracing vào workflow thật

14/10/2026. Implementer report. Branch `final`, base HEAD `77760d10`. No commit or
push (no Git authorization); no database reset; no checkout; no subagent. The
working tree was clean at start; a concurrent agent's frontend edits are preserved
(none touched by this task beyond a non-breaking type/field addition).

Closes the gap in the prior read-only review: **the web workflow now emits real
root/child operation traces to LangSmith**, verified by reading them back from the
cloud.

## Write set, consumers, completion

| Concern | Files | Consumers |
| --- | --- | --- |
| Operation/step recorder | new `evidence/telemetry.py` | workflow, evidence job, pipeline |
| Span model + sink | `evidence/trace.py` (`TraceSpan` topology/timings/error/metadata; `_send` real start/end + `parent_run_id`; allowlist redaction) | recorder, M0/CLI |
| Pipeline steps | `evidence/pipeline.py` (`read_root`: OCR per file, confidence, classify, extract, validate, match) | evidence job, draft read |
| Operation roots + assessment steps | `workflow/service.py` (`execute` per-command root; admission/reconcile/commit; draft reads; `trace_refs` in view) | API, UI debug |
| Evidence-job root | `workflow/evidence_jobs.py` | durable worker |
| Composition root | `runtime.py::_wire_trace` | dev server, Verify, CLI |
| Debug view | `domain/case.py` (`CaseView.trace_refs`), `api/routes.py` (health `langsmith_enabled`/`langsmith_export_errors`), `api/views` (existing raw JSON) | UI debug modal |
| Frontend debug | `frontend/src/types.ts`, `features/debug_modal.tsx` (technical area only) | UI |

## Design (contracts §9)

- **Composition root only.** `runtime.build_workflow` builds the recorder from
  `Settings` and hands it to the real workflow. Tracing off/unkeyed ⇒ a local
  no-op sink; the recorder always exists. No separate observation pipeline.
- **Operation roots, not a long-lived case span.** One root per real operation:
  `command:<kind>` (draft, submit, answer, decide, record_actual, control,
  override), `settlement-draft-read`, `advance-draft-read`, `evidence-job`.
  Operations are linked by metadata (root_id/job_id/command_id, read-set
  versions, basis, provider_mode, code revision), never one open span.
- **Per-step child spans** with their OWN ids and the root as `parent_run_id`:
  `ocr:<file>`, `confidence-review`, `classify`, `extract:<type>`,
  `validate:<type>`, `match`, `admission`, `reconcile`, `commit`, `handler`.
- **Real timings.** Start/end are wall-clock instants at entry/exit; a span with
  no end stays open (never `start==end==now` faking latency 0).
- **Honest skip.** A step that did not run is recorded with an explicit
  `skipped` reason (e.g. `no_low_confidence_candidates`, `no_settlement_form`),
  never as a successful provider call.
- **No network in a txn.** Spans buffer locally; the recorder flushes when the
  operation exits, which the callers place around (outside) the SQLite
  transaction.
- **Never blocks.** A sink failure is captured in `export_errors` (diagnosed, not
  silently swallowed) and never raises or changes the business result.
- **Redaction.** Inputs/extra are filtered by key; real secrets
  (`api_key`, `token`, `authorization`, …) and private content (`raw`, `content`,
  `pdf`, `image`) are dropped, while numeric metrics whose name merely contains a
  sensitive word (`token_count`, `total_tokens`) are KEPT.

## RED → GREEN (backend)

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Behaviour | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| root/child ids, no reuse, parallel isolation, real timing, skip, redaction, sink failure | `tests/unit/test_telemetry.py` | module missing | 10 passed |
| adapter keeps real start/end, no fake close, numeric metrics kept | `tests/unit/test_langsmith_trace.py` | old test encoded fabricated close | 12 passed |
| runtime composes the recorder; real submit/evidence-job/draft/record_actual emit spans; sink failure safe; cache reuse no OCR | `tests/integration/test_langsmith_runtime_wiring.py` | — | 5 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **588
passed / 0 failed**. Frontend (Node 24.19.0): `npm test` → **27 passed / 2
skipped**; `npm run build` → exit 0.

## LIVE acceptance (real provider + real LangSmith export)

Evidence `.runtime/langsmith-live-20261014/` (git-ignored). Provider LIVE (Mistral
OCR + X-Kiro `qwen/qwen3.7-flash:free`), context SIMULATED, clock
`2026-10-10T18:00:00+07:00`.

**TC01 end-to-end** (`run_tc01_live.py`, original PDFs): create → attach → draft
read → submit → evidence job. Result **READY_TO_EXECUTE, COLLECT 760000**,
T=E=3.240.000, A=4.000.000, S=−760.000; `trace_refs=[command:submit:…]`;
`langsmith_enabled=true`, `export_errors=[]`.

Traces read back from the cloud (`read_trace.py` → `remote-trace-read.json`), all
roots found, no errors:

| Operation root | Children in LangSmith |
| --- | --- |
| `command:create_draft` | `handler` |
| `command:attach_sources` | `handler` |
| `settlement-draft-read` | `ocr:report_hoan_ung.pdf`, `ocr:hoa_don_dien_tu.pdf`, `confidence-review`, `classify`, `extract:SETTLEMENT_FORM`, `validate:SETTLEMENT_FORM`, `extract:E_INVOICE`, `validate:E_INVOICE`, `match` |
| `command:submit` | `admission`, `reconcile`, `commit`, `handler` |

**TC08 (FACT) + accountant** (`run_fact_and_accountant.py`): WAITING with
`expense:allocation` dispute FACT and no instruction; the accountant's
`command:record_actual` is a SEPARATE operation root (`admission`/`reconcile`/
`commit`/`handler`); the evidence job root carries the full pipeline + assessment.

**Export-failure non-interference** (`check_export_failure.py`, unreachable
endpoint): the business result is identical (WAITING, no instruction, same FACTs,
T/S UNKNOWN, conclusion present) while **19 export errors are diagnosed** — a
broken LangSmith never loses a conclusion or rolls back money.

**Redaction** (`check_redaction.py`): 66 recent runs scanned for the configured
keys, bearer tokens, `%PDF` and private markers → **0 violations**.

## Browser evidence (TC01, real socket + built frontend)

Pinned-clock LIVE server (`server.py`) + Playwright (`browser.mjs`):
`POST /settlement/draft` 200, `POST /submit` 200; the dossier shows T=E=3.240.000,
A=4.000.000, S=−760.000, "Sẵn sàng phê duyệt"; the DB has one `COLLECT 760000`
ISSUED instruction; the UI debug area shows the technical trace refs. The run's
traces landed in LangSmith (2× `settlement-draft-read`, 2× `command:submit`, all
pipeline/assessment steps). Health:
`{"langsmith_ready":true,"langsmith_enabled":true,"langsmith_export_errors":0}` —
config-ready and export-healthy are distinct.

## Constraints honoured

- No change to money, policy, authority or any settled result. The recorder only
  observes; it never increases input revision, issues an instruction or records
  money.
- No network I/O inside a SQLite mutation transaction (buffered, flushed on
  operation exit).
- No extra OCR/LLM call to trace; cache reuse adds no OCR call (tested).
- The `run_settlement_draft` reuse path is not recorded as a provider call.
- Stop/stale-version/retry/idempotency/authority are untouched (full suite green).
- No gold/expected enters the application or the trace.

## NOT_RUN / remaining

- The 25-case suite, Docker, public hosting and the practitioner pilot remain
  NOT_RUN (out of scope).
- Verify Core4/Escalation5 remains NOT_RUN (`data/kiem-thu` absent).
- RECORDED_REPLAY tracing is wired by the same composition root but NOT_RUN with
  a captured recording.

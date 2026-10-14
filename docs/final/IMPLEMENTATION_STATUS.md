# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ 91d444fa (working tree has unrelated concurrent edits; no commit made by this task). |
| Phase | T1..T10 + R0–R8 done; evidence pipeline + admission + invoice basis + advance recording + general-expense T1–T5 + TC08/TC23 fixes committed. LangSmith root/step wiring is followed by this **input/output tracing completion** (2026-10-14, uncommitted): stage summaries, actual provider `llm` spans, recursive redaction, atomic create payloads and bounded flush are read back from cloud. |
| Authorized scope now | LangSmith input/output tracing; complete. Isolated LIVE evidence `.runtime/langsmith-io-tracing-20261014-153951/`, report `report.md`. **Uncommitted — no Git authorization given.** |
| Setup review | ACCEPTED; clean-clone proof passed. |
| Execution method | Inline execution, single integrator; per-behaviour TDD (RED observed → GREEN) + full-suite after. No subagent review (user-directed). |
| Workflow integrator | Inline executor — single writer for workflow/api/domain/frontend shared files |
| Next application task | User reviews the tracing report and direct LangSmith traces. No commit/push is authorized by this task. |
| Last completed application task | LangSmith input/output tracing completed with offline RED→GREEN, full Python suite, LIVE browser TC01/TC06 and final cloud read-back. |
| Product unit/integration/LIVE evidence | `rtk proxy uv run pytest -q` → **646 passed / 0 failed**. Frontend build passed with Node **24.19.0** / npm **11.12.1**. Playwright LIVE (built frontend + LIVE backend, simulated context, controlled clock `2026-10-10T18:00+07`) → **TC01 READY_TO_EXECUTE / COLLECT 760000; TC06 WAITING / FACT `expense:arithmetic:return`, no instruction**. Read back from LangSmith `invoice-referee`: **21 runs per case, 0 `outputs=null`**, observed start/end times, no errors, correct per-document LLM attempt indices, arithmetic finding visible in `validate`/`reconcile`, parent links intact; privacy scan **0 violations**. `health`: `langsmith_ready/enabled=true`, `export_errors=0`. **RECORDED_REPLAY / Docker / hosting / practitioner pilot NOT_RUN.** |
| CodeGraph | 220 files / 3,897 nodes / 11,998 edges; index up to date, older-engine warning. `check_index_coverage` unavailable; coverage remains unknown. |
| Git handoff | `final` @ 91d444fa, **ahead 1** of `origin/final`; tracing changes are uncommitted. Other concurrent working-tree changes were preserved. No commit/push/reset. |

### Evidence pipeline E0–E8 (2026-10-14)

Implemented the Hoangha evidence pipeline on `final` (plan
`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md`). E0 promoted the
accepted decisions into design §15 / contracts §12 / ADR0006-0007 / glossary. E1–E6
added `domain/documents.py`, `evidence/{artifacts,ocr_quality,classification,
document_profiles,extraction,document_validity,matching}.py` with strict DTOs,
all-page OCR, the confidence gate, classification, provenance-checked extraction,
profile validation and the ported Hoangha matcher. E7 wired `read_root` through
`runtime.build_workflow` for LIVE/RECORDED_REPLAY into a durable, basis-checked
evidence worker (`workflow/evidence_jobs.py`, lifespan-owned) that publishes a typed
`ReadResult` and sets `EVIDENCE_READY` (`conclusion=None`, no instruction,
`assessment_ready=false`); `_assess_and_commit` early-returns so LIVE/REPLAY never
reaches the Reconciler, and STUB keeps its assessment path. E8 imported the 75-case
UC-03 corpus into `data/test-kit/hoangha-uc03`. A fresh opus whole-branch review found
4 Critical + 12 Important findings; all were fixed in one TDD pass (see the ledger
`.superpowers/sdd/2026-10-13-hoangha-evidence-pipeline/progress.md`).

Remaining gaps (NOT_RUN / deferred, not claims): M0 LIVE measurement; RECORDED_REPLAY
captured recordings; the full per-stage counter/read-cache persistence on restart
(the input-basis check is implemented); Q34 out-of-scope payer detection (documented
known hole); the finance/admissibility adapter. Plan checkboxes E1–E8 ticked except
those three (lines for restart-counter test anchors, recordings, M0 LIVE).

### Remediation pass (2026-10-13, reviewed commit 13a6eb09)

Six Important findings from an independent review were each reproduced against
HEAD, fixed with a test that failed first, and committed:

1. **Authority scope + amount** (e8745125) — `_grant_covers`/`_actor_has_grant`
   ignored the grant scope, and a decision never checked its amount against
   `max_amount`; a grant scoped to another activity authorized a payment and a
   25m decision passed a 20m ceiling. Now scope and per-action amount are
   enforced at both the pure policy and the workflow decision boundary.
2. **Money verification** (de87d7ed) — `record_actual` hard-coded
   `CONFIRMED`/`ALLOCATED`, so a bare amount claim settled the case. Now
   verification/allocation are derived from a responsible completion claim,
   refs or a linked reversal; only CONFIRMED events project/fulfill.
3. **Stop/Resume** (1acd8a08) — a handed-off instruction (execution
   OPEN/UNKNOWN) was reset to NOT_STARTED because Resume re-issued the same
   deterministic id via `INSERT OR REPLACE`. Now suspended instructions are
   found and reactivated without resetting an unresolved execution, and ids are
   unique per issuance so history is never clobbered.
4. **Answer loop** (c01037d2) — an answer marked the issue ANSWERED then the
   re-assessment deleted and recomputed it, discarding the value. Now the answer
   persists as a scoped confirmation (`case_confirmations`) that the snapshot
   consumes.
5. **Scorer/runner/suites** (6439c572) — the scorer ignored direction, the
   runner defaulted `refs_ok=True`, a BALANCED-on-human-required was not unsafe,
   and the CLI ignored `--suite`. All four fixed; `core`=Core4,
   `escalation`=Escalation5.
6. **LIVE read** (2b641e63) — a LIVE submit never read the uploaded sources.
   `evidence/pipeline.py` + `live_reader.py` now read sources outside the
   transaction; a wired reader makes the STUB fallback inapplicable; a failed
   read stays unresolved (not zero).

The three Minor findings were already resolved in HEAD: rejected-attach dir
pruning (`_prune_empty_upload_dirs`), the catalog filters `status='AUTHORIZED'`,
and `_case_view` filters people by tenant.

**Schema note (13/10/2026).** `context_grants` and `context_people` use composite
primary keys `(tenant, grant_id)` / `(tenant, id)` for tenant isolation; the
remediation added `case_confirmations` (owner answers) and
`instructions.authority_refs_json`. `Database.migrate()` only runs
`CREATE TABLE IF NOT EXISTS`, so it does **not** alter an existing table. No
runtime DB exists in this repo, so nothing needs migrating today; any DB file
created before these changes must be deleted and recreated (a real versioned
migration is a T10 clean-clone/runbook item, not done here).

## Evidence on demand

### Planning handoff — 14/10/2026

User-authorized documentation task: Hoangha OCR/classification/extraction/matching integration into `final`, ending before financial calculation/policy. [Implementation plan](../superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md) and [review/disposition](reviews/2026-10-13/hoangha-evidence-plan-synthesis.md) are saved. Initial independent review was NOT READY; the response/closure closed residual R1–R4 at specification level. E0–E8 are **NOT_IMPLEMENTED**; no product tests, browser, LIVE call, commit or push ran in the planning task. Existing implementation evidence above is historical and does not prove the new pipeline. Next action: user reviews this plan, then an integrator completes E0's canonical evidence contract gate before dependent code tasks.

- For this setup's observed checks, read [setup evidence](reviews/2026-10-13-agent-setup/SETUP_EVIDENCE.md).
- For the setup review/closure, read [independent response](reviews/2026-10-13-agent-setup/RESPONSE.md); the original findings remain linked there.
- For the reviewed plan's disputed clauses, read [plan disposition](reviews/2026-10-13-plan/SYNTHESIS.md).
- For implementing a task, start from [AGENTS.md](../../AGENTS.md) and that task in [the plan](../superpowers/plans/2026-10-13-invoice-referee-final.md). Review archives are not a bulk context pack.

## Update this checkpoint at handoff

Replace current values with observed state. Record:

1. Current task/owner/write set, completed gate and pending dependencies.
2. Changed files and exact verification commands/results, mode and artifact paths.
3. Uncommitted work, active failure or external gap, and one concrete next action.

Mark completed only when the task's gate passed; distinguish BLOCKED, FAILED and
NOT_RUN. A task skipped by request stays explicitly unverified. A design/contract
change updates its existing source and invalidates affected checks until rerun.

## UC03 mapping task — 14/10/2026

User-authorized next step: map all 25 Hoangha v1 cases under
`data/tham-khao/uc-03` to the accepted final contract, and repair manifest paths.
Write set: corpus `manifest.json` (folder fields only), `readme.md`, new
[CASE_MAPPING_FINAL](../../data/tham-khao/uc-03/CASE_MAPPING_FINAL.md), new
`final-case-mapping.json`, this scoped checkpoint and the independent review ledger.
No application source/finance/policy change, data regeneration, product tests,
browser/provider LIVE, commit or push belongs to this task.

Mapping v2 covers 25 IDs and 65 immutable PDF refs. All legacy PDF/DOCX/gold
artifacts are preserved; 25 broken `manifest.folder` values now resolve. Context,
source variants and executable financial oracle are **NOT_IMPLEMENTED**. All
`ready_for_financial_oracle` flags remain false. The mapping is authoring-only and
must never enter runtime/model input as facts. Its conditional issue sequences
separate FACT/POLICY/AUTHORITY owners from projection/effects/execution actors.

Initial independent review was NEEDS_REVISION; owner/issue sequencing and TC07
criticality drift were corrected in the mapping only. Closure verdict and evidence:
[review ledger](reviews/2026-10-14-uc03-mapping-review.md). Mapping verification
checks 25 IDs, 65 hashes, unchanged legacy artifacts, folder-only manifest diff,
issue dependencies/owners, arithmetic, no zero instruction and local links; exit 0.
`rtk proxy git diff --check` exit 0. These are document/data checks, not product
acceptance results.

Next task: create the planned UC03-F01/F02/F03 travel-source/context/gold variants
and write the evidence-to-finance/admissibility plan; retain the current
EVIDENCE_READY guard until that consumer's contract and gate are implemented.
Source originals TC01/TC02 are reception/equipment, not automatic travel routines.

## UC03 pilot + admission plan — 14/10/2026

User authorized creation of F01–F03 data and the finance/admissibility plan;
explicitly requested **no subagent review**. Native self-review only. Created
[pilot3](../../data/test-kit/uc03-pilot/README.md), 6 PDFs, runtime context/submission/
employee-confirmation inputs, separately authored hidden evidence/business gold,
provenance, `scripts/sinh_uc03_pilot.py`, 3 artifact-tool tests and
[A0–A8 admission plan](../superpowers/plans/2026-10-14-evidence-finance-admission.md).
Mapping points to the created variants; original156 reference/gold/DOCX artifacts
stay byte-identical. No application finance/admission/matcher implementation changed.

Evidence: [self-review ledger](reviews/2026-10-14-uc03-pilot-evidence.md). PDF text,
one-page bounds and final render/layout checked; input DTOs parse; invoice/gold math
and hashes agree. Generator tests observed RED then **3passed**. Full final pytest:
**353passed /11failed**; failures still depend on deleted `data/kiem-thu`, named in
ledger. No claim suite GREEN. Provider LIVE/captures/UI/finance pilot E2E NOT_RUN.
Data/gold initial clock10/10/2026 18:00+07; interactive current-date execution needs
fresh responsible coverage. No bank verification or actual payment is inferred from
the synthetic employee declaration, printed balance or passing artifact tests.

Plan self-reviewed, **A0–A8 NOT_IMPLEMENTED**. Next: user reviews the concrete plan,
then one native integrator implements it with the stated gates. Keep EVIDENCE_READY
guard until its typed admission consumer gate passes. No commit/push in this task;
unrelated working-tree activity was preserved.

## Architecture / workflow / decision diagrams — 14/10/2026

User-authorized documentation task. Three read-only subagents used CodeGraph for
separate architecture, workflow and decision-logic slices. Parent CodeGraph status
reported 215 files / 3,685 nodes / 11,267 edges and “up to date”, with an older
engine-version warning. `check_index_coverage` was unavailable, so coverage is
unknown; no indexing or product tests ran.

All source evidence is pinned to clean commit
`bd9e8769b9c0a970f8ec4e8e2ac1910c512b2877` and checked against a clean detached
checkout. The primary working tree had uncommitted changes, including a 757-line
diff in `workflow/service.py`; those changes are deliberately outside these
diagrams and remain untouched.

- [Workflow HTML](../../.archify/workflow-invoicereferee-20261014-203402/invoicereferee-workflow.html)
  — Archify `finalize` passed validate, deliver, provenance check and browser-check;
  visual-check passed at 1440×900 and 2048×1320. Captures were inspected; several
  return paths remain long but readable.
- [Decision-logic HTML](../../.archify/workflow-decision-logic-invoicereferee-20261014-203402/invoicereferee-decision-logic.html)
  — the same four `finalize` gates and visual-check passed; desktop capture inspected.
- [Architecture candidate](../../.archify/architecture-invoicereferee-20261014-203402/candidate.json)
  — no accepted HTML. After a measured reflow, the showcase desktop-readability
  gate still required a viewBox width ≤930px; the candidate measured 1,357px and
  projected 4.1px context text. Per the Archify repair bound, it remains an
  unaccepted candidate for a fresh compact composition.

This documentation task changes no application behavior. No product tests, provider
calls, commits or pushes were run.

## LangSmith input/output tracing completion — 14/10/2026

User-authorized implementation and verification; **no subagents**, no commit/push/reset. Scope: understand actual caller/export behavior, add bounded stage outputs and provider-level LLM spans, and verify new traces from an isolated LIVE browser run.

Initial cloud read-back confirmed the cited runs were ended and had no error: `extract:SETTLEMENT_FORM` (`fcf47f12-4b8f-5fb4-9a1c-ce868e651755`) and `settlement-draft-read` (`03a889f6-58a6-5acb-9f39-6a3c3ff0d699`) had `outputs=null`; sibling `extract:E_INVOICE` (`a9bc03e7-eb73-53b5-a9b6-222166e7903c`) only had `profile_status`. The root and many stage callers omitted summaries or recorded only counts/status. The sink also split run creation and output/error/end-time into a conditional `update_run`, creating an unverified loss window for SDK batching. The historical samples do not prove whether that window caused the inconsistent extraction output; the implementation now sends all completed fields in one create request and flushes after operation close.

The change adds a recursive, bounded payload filter and stage allowlists; explicit `COLLECTED` / `EMPTY` / `NOT_COLLECTED` / `REDACTED` states; OCR, confidence, classification, extraction, validation (including the shared arithmetic rule), matching, admission, reconcile, commit, draft-root and command-root summaries; actual X-Kiro `run_type=llm` spans per HTTP attempt; per-document attempt indexes; provider-reported model/usage; and bounded SDK flush. Full prompts, full parsed model responses, exact quotes, raw OCR/PDF/image, credentials and private name/account values are not sent to LangSmith. Business DTOs and financial decisions are unchanged.

Changed files owned by this task: `evidence/{trace.py,telemetry.py,xkiro.py,pipeline.py,classification.py,extraction.py,ocr_quality.py,matching.py}`, `workflow/{service.py,evidence_jobs.py}`, `tests/unit/{test_langsmith_trace.py,test_telemetry.py,test_xkiro_tracing.py}`, `tests/integration/test_langsmith_runtime_wiring.py`, and this checkpoint. Other dirty files in the shared checkout were preserved.

Verification:

- Per-behavior RED→GREEN tests caught absent create payload outputs, missing output-state distinction, shallow redaction, missing stage data, absent X-Kiro spans, cross-document attempt numbering, and missing validation arithmetic. Focused trace/provider/pipeline/runtime tests pass.
- `rtk proxy uv run pytest -q` — **646 passed**, exit 0.
- `rtk proxy git diff --check` — exit 0.
- `rtk proxy env PATH=<bundled Node 24.19.0> npm run build` — exit 0 with npm 11.12.1. `ruff check` is NOT_RUN because Ruff is not installed.
- Isolated LIVE Playwright run [`langsmith-io-tracing-20261014-153951`](../../.runtime/langsmith-io-tracing-20261014-153951/) — **2 passed**. Backend health reported LIVE, `live_ready=true`, LangSmith enabled and zero export errors. Context origin `SIMULATED`; controlled clock `2026-10-10T18:00:00+07:00`, matching the coverage snapshot; gold files were not loaded.
- LangSmith SDK read-back [`cloud-readback.json`](../../.runtime/langsmith-io-tracing-20261014-153951/cloud-readback.json) — **PASS**, 21 runs per case, zero null outputs, errors absent, observed start/end times, correct parent links and LLM attempt numbering, privacy scan zero violations. TC06 arithmetic basis and numeric variance are present in `validate`, draft-root and reconcile outputs.

LIVE business outcome remained unchanged: TC01 reached `READY_TO_EXECUTE` with a `COLLECT 760000` instruction (`execution_state=NOT_STARTED`); TC06 reached `WAITING` with open FACT `expense:arithmetic:return`, difference 60000, and no instruction. TC06's `S` projection is recorded as known `-760000`, while the arithmetic issue blocks the effect.

- TC01 [draft trace](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/trace/71fc7ecc-edb2-537c-beda-9bf21f1daf8c/run/71fc7ecc-edb2-537c-beda-9bf21f1daf8c?start_time=2026-10-14T15%3A40%3A06.814270%2B00%3A00) · [submit/reconcile trace](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/trace/b7c1eb9c-52e6-5e45-b9d4-78d5ae4eb702/run/b7c1eb9c-52e6-5e45-b9d4-78d5ae4eb702?start_time=2026-10-14T15%3A41%3A13.817716%2B00%3A00)
- TC06 [draft trace](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/trace/e4807c8c-9051-5f34-8c97-8e5b394f4d41/run/e4807c8c-9051-5f34-8c97-8e5b394f4d41?start_time=2026-10-14T15%3A41%3A17.583194%2B00%3A00) · [submit/reconcile trace](https://smith.langchain.com/o/6290bb7f-942c-4bbf-a501-58c5a46a1220/projects/p/97168b16-9ee9-4485-9ff0-35642aea1c4b/trace/ccf79730-b0dc-58ca-b257-b151780a0569/run/ccf79730-b0dc-58ca-b257-b151780a0569?start_time=2026-10-14T15%3A42%3A20.944738%2B00%3A00)

The LIVE submit reused the persisted draft report, so admission/reconcile/commit are children of `command:submit`; no `evidence-job` operation was created on that path. Full prompt/response content remains intentionally unavailable in LangSmith; the model span includes schema/prompt hashes, lengths, parsed-output shape/hash and any provider usage, while validated facts are visible in stage spans. `REPLAY`, M0, Stop/Resume/actual-money browser flows, Docker/hosting and practitioner pilot are NOT_RUN here.

Final Git state: HEAD `91d444fae408b42b753ea4c53ca5cfabf6a7b95f`, branch `final` ahead 1. Changes remain uncommitted; no Git integration was authorized.

## TC02/TC03 harness and invoice-scoped Q32 answer — 14/10/2026

User-directed correction following the independent audit. Scope stayed with the
TC02/TC03 test harness/context and the employee-paid answer loop; no policy grants,
company-direct payer choices, or finance thresholds were changed.

- The LIVE harness startup JSON no longer re-declares `activity:tc02` or
  `activity:tc03`, so it cannot shadow the richer typed snapshots. The acceptance
  runner now starts `scripts/dev.py` directly; it no longer injects a runtime
  monkeypatch or ineffective timeout override.
- Regression reproduces seed → production startup import → `load_context`; both
  activities retain company name, exact advance, coverage and catalog entries.
- A LIVE missing-payer question is now keyed to the exact invoice. The answer is
  an integer VND amount plus a responsible reason; the server derives payer from
  the case employee, scope from the case activity, and source refs from that
  invoice. It rejects generic payer answers, another actor/scope, amounts outside
  invoice/Q32 bounds, and answers that do not produce the matching Q32 basis.
  Multiple rows sharing one invoice do not reuse one claim across rows.
- The question UI presents one numeric employee-paid amount field; it adds no
  company/partner payer choices. The browser harness now uses the rendered radio
  selector and opens the accountant case row before checking instructions.

Verification:

- `rtk proxy uv run pytest -q` — exit 0.
- `npm test` — 30 passed, 2 skipped; existing React `act(...)` warnings appeared
  in `app-restore.test.tsx`.
- `npm run build` — exit 0 (Node 24.19.0, npm 11.12.1).
- `rtk proxy git diff --check` — exit 0. `playwright --list` discovers both cases.
- New integration regressions cover invoice binding, two-invoice isolation,
  employee/activity scope, invalid amounts and refusal of the generic LIVE payer
  answer. Frontend regression covers numeric amount + reason input.

LIVE evidence remains **not accepted as a complete browser pass**. Run
`tc02-tc03-live-20261014-155534` confirmed the corrected loaded context but stopped
at stale draft-format/activity selectors before either case submitted. Run
`tc02-tc03-live-20261014-160324` used the production server with correct typed
context: TC02's OCR request returned `httpx.ReadTimeout` at the 60-second client
limit and stayed DRAFT; TC03 submitted and the isolated SQLite DB records SETTLED
with zero instructions. The browser stopped on the old accountant-dashboard
locator, so reload and UI instruction assertions were NOT_RUN. The selectors have
since been corrected, but no further provider call/browser rerun was made. The
existing run DBs are isolated under `.runtime/playwright-live/`; the shared app DB
was not changed.

Current Git state: `final` at `cea29405`, ahead 2 of `origin/final`. This correction
and other concurrent working-tree changes are unstaged/uncommitted; no push.

# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ 96e7b888 (general-expense workflow + advance + intake review UI). |
| Phase | T1..T10 + R0–R8 done; evidence pipeline + admission + invoice basis + advance recording + general-expense T1–T5 done; TC01 web intake fix committed (`96ba5987`, `96e7b888`). **Core arithmetic gate implemented** (2026-10-14, uncommitted): per-type document arithmetic (TC06 paper `advance−cost=refund`; TC11 invoice `subtotal+tax=total`) is checked in code and blocks the Reconciler/commit as a FACT; a material UNREADABLE component is a FACT (never 0); numeric provenance no longer mistakes a percentage for money. |
| Authorized scope now | Core validation fix, prompt `docs/final/CORE_ARITHMETIC_AGENT_PROMPT.md`, evidence `2026-10-14-tc06-tc11-live-negative.md`. **Uncommitted — no Git authorization given.** |
| Setup review | ACCEPTED; clean-clone proof passed. |
| Execution method | Inline execution, single integrator; per-behaviour TDD (RED observed → GREEN) + full-suite after. No subagent review (user-directed). |
| Workflow integrator | Inline executor — single writer for workflow/api/domain/frontend shared files |
| Next application task | Whole-branch review of the core-arithmetic range, then user-authorized commit. T11 still BLOCKED on practitioners. |
| Last completed application task | Core arithmetic gate + numeric provenance (TC06/TC11) + LIVE + browser evidence. |
| Product unit/integration/LIVE evidence | `uv run pytest` → **537 passed / 0 failed**. Frontend vitest **27 passed / 2 skipped**, build exit 0 (Node 24.19.0). **LIVE TC06/TC11 original PDFs through the current source** (real Mistral/X-Kiro `qwen/qwen3.7-flash:free`, SIMULATED independent context, clock 2026-10-10T18:00+07): TC06 → WAITING, **no instruction**, FACT `expense:arithmetic:return` (760000 vs 700000, lệch 60000); TC11 → WAITING, **no instruction**, FACT `expense:arithmetic:total` (5.4m vs 5.5m, lệch 100k), tax now FOUND. **LIVE TC01 regression** → READY_TO_EXECUTE, **COLLECT 760000**, T=E=3240000, A=4000000, S=-760000. **Browser (Playwright, real socket + built frontend)**: TC06 draft surfaces the contradiction, submit ends WAITING with no instruction; TC01 draft reads the values, submit 200, COLLECT 760000 ISSUED. **Verify Core4/Escalation5 NOT_RUN** (`data/kiem-thu` absent). **M0 LIVE / RECORDED_REPLAY / Docker / hosting / practitioner pilot NOT_RUN.** |
| CodeGraph | Re-check with `rtk proxy codegraph status` before relying on it; the index lags writes. |
| Git handoff | Commits on `final` (unpushed): … 0b205420, 96ba5987, 96e7b888. The core-arithmetic fix is **uncommitted working-tree changes** (no Git authorization). |

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

# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## TC05 row-total validation correction — 15/10/2026

Closed the previously recorded TC05 negative review with one shared source-backed
`SETTLEMENT_FORM` rule: the sum of represented itemized expenses must equal the
paper's printed total. Summary/subtotal rows are excluded; missing or unreadable
cost rows/totals remain unresolved, and an absent printed-total assertion creates
no invented relation. The same finding is shown on the employee draft and blocks
financial admission, leaving T/E/S unknown and emitting no instruction. Invoice
linking/allocation semantics, S formula, policy/authority and other money rules
were not broadened.

Fresh isolated LIVE run on the original TC05 PDFs: Mistral OCR `mistral-ocr-latest`
and configured LLM `qwen/qwen3.7-flash:free`; context explicitly SIMULATED
(advance4m plus scoped grants/coverage), gold not loaded. OCR/extraction returned
paper rows2m+1m, printed total3.5m, advance4m/refund500k, invoice3.24m. Draft
shows the 500k mismatch with page/quote refs; final is WAITING with one employee
FACT, T/E/S UNKNOWN, A4m, P/R0 and no instruction. Read-only Playwright opened
the isolated pre-submit draft DB and final DB on private ports65111/65112; both
surfaces show the source-backed question. No provider call was made by either
view server. Exact outputs/screenshots are under
`.runtime/tc05-live-review-20261015/fix-run-final/`.

Verification: `rtk proxy uv run pytest -q` → exit0 (781 collected); frontend
`npm --prefix frontend test -- --run` under Node24.19.0/npm11.12.1 → 45 passed,
2 skipped; same runtime `npm --prefix frontend run build` → exit0;
`git diff --check` → exit0. Targeted regressions
cover TC05, unresolved rows/totals, summary rows, TC01, TC06, TC11, VAT boundary,
and shared-invoice allocation. Invoice-description/service validity remains a
separate question: matching the invoice number does not resolve it. Existing
unrelated deletions of `frontend/link-*.png` were preserved. The fresh LIVE calls
used only the isolated runtime; no write was made to the user's DB/server. No
commit, push or reset.
[Implementation and evidence](reviews/2026-10-15-tc05-live-arithmetic-fix.md).

## TC05 LIVE negative review — 15/10/2026

Read-only application review of original Hoangha TC05 (paper rows2m+1m but
printed total3.5m; invoice3.24m). Both PDFs rendered/visually inspected, then
production LIVE OCR/LLM through create/attach/draft/submit on isolated SQLite,
with explicitly simulated advance4m/activity/grants/coverage to isolate the
arithmetic gate. Gold not loaded. OCR and structured extraction preserve all
numbers, but draft warnings are empty and final issues=[] / READY_TO_EXECUTE /
COLLECT1000000. This is **business FAIL**, not acceptance PASS. Read-only
Playwright observes the same UI/API result. Two artifact-based regressions RED.

Missing rule: paper row sum versus printed total; existing advance−printed_total
and invoice subtotal+tax checks pass their respective relations. No app fix or
user DB write/reset, no commit/push/subagent. Private view server stopped.
[Source analysis and evidence](reviews/2026-10-15-tc05-live-negative.md).

## Receipt confirmation only — no initial-history UI — 15/10/2026

Supersedes the ordinary UI checkpoint below by explicit user correction. Removed
the initial-history checkbox/button and frontend call. Confirming a clear,
completed source-bound advance now records A once and starts `DOSSIER_RECORDS`
reconciliation atomically. This represents recorded dossier money, not an
accountant declaration that all external bank history is complete. No fabricated
opening balance/fund/absence quote. Unknown/unallocated/conflicting money blocks.
Employee upload alone never changes R; accountant confirms the proof to record
R, fulfill COLLECT and close when S0/no blockers. Imported advances also support
P/R without the separate initial-history action; legacy APIs remain compatible.

Verification: Python **765 passed**; frontend **43 passed / 2 skipped**, Node24
build/diff check pass. Isolated TC01 browser starts with zero money: one advance
confirmation immediately yields COLLECT760000; no initial history request;
employee proof keeps R0; accountant receipt gives R760000/S0/SETTLED, reload
persists. Stored LIVE originals + deterministic return adapters; fresh LIVE
NOT_RUN. Backend8000 restarted LIVE; ten business-table fingerprints unchanged.
No user financial command/reset, commit/push or subagent.
[Evidence](reviews/2026-10-15-no-extra-history-confirmation.md).

Earlier initial-history UI/statement below is historical, not the current flow.

## One initial money-history confirmation, then managed execution — 15/10/2026

User-approved replacement of the long coverage UI: one unchecked accountant
statement that all prior money of this employee/work is recorded, no omitted
carry-in. A new source `MANAGED_HISTORY` lives in existing coverage JSON; server
owns actor/scope/time/ledger version/context-money fingerprint. No fake fund,
bank balance or PDF absence quote. Verified source-bound A / instruction-bound
P/R update the valid checkpoint atomically, with audit, without another prompt.
Historical/out-of-band/reversed/unresolved/unallocated money or changed context
ledger invalidates it; a stale checkpoint is not automatically repaired.
Legacy coverage keeps its old semantics, without silent migration.

Verification: full Python **763 passed**, frontend **43 passed / 2 skipped**,
Node24 build and diff check pass. Initial API/UI, tied-clock latest-checkpoint and
Vietnam date-display regressions observed RED→GREEN. Isolated Playwright on a
copied TC01 DB went from one history assertion through employee proof upload
(R unchanged), accountant receipt760k to S0 / SETTLED, reload preserved. Original
OCR was stored LIVE; new return used deterministic adapters, fresh LIVE NOT_RUN.
Backend8000 restarted with the same command, LIVE health and new route checked;
ten business-table fingerprints unchanged. No user financial command, reset,
commit/push or subagent. [Evidence](reviews/2026-10-15-managed-money-history.md).

The instruction-bound checkpoint below predates this update: managed history no
longer asks for reconfirmation after each properly confirmed workflow movement.

## Instruction-bound money movement and return review — 15/10/2026

New P/R events are bound to the active same-root PAY/COLLECT instruction and
source refs. Employee return upload/read is durable and leaves R/coverage
unchanged; an accountant confirmation revalidates the stored read and writes R
idempotently. Partial returns keep the COLLECT remainder; overpayment and
party/status mismatches remain blocking. The employee workspace now exposes the
proof upload only when a COLLECT is active. The accountant sees a return draft
awaiting review, a supplementary-payment form only for an active PAY, clear P/R
labels, and the coverage form only when missing, stale or blocked (with prior
values prefilled for review).

Verification: `rtk proxy uv run pytest -q` → exit 0 after updating the v8→v10
migration assertion; after adding workflow-restart persistence coverage,
`rtk proxy uv run pytest tests/integration/test_employee_return_draft_api.py -q`
→ exit 0 (9 tests). Frontend `npm test -- --run` → 41 passed / 2 skipped;
Node 24.19.0 / npm 11.12.1 `npm run build` → exit 0. API/unit tests use
isolated temporary databases and stub OCR. Playwright LIVE TC01 was NOT_RUN:
the available port 8000 reports LIVE but is the user's persistent server/DB,
and there is not yet a feature-specific isolated LIVE runner. No request was
sent to that server; no user DB was modified. Changes remain uncommitted.

## Accountant receipt confirmation by button — 15/10/2026

Routine source-clear, complete, auto-linked advance drafts now require only the
accountant's **Xác nhận ghi nhận** action. The backend revalidates the saved read
and derives its responsible statement; actor/time/source/draft are recorded.
Missing-field corrections retain an explanation; manual links use their existing
reason instead of a duplicate declaration. Conflicts remain blocked and pending
sources remain observed. Coverage is unchanged. Added TRANSACTION_IDENTITY to the
acceptance DTO/frontend union after a browser retry exposed the missing literal.

Proof: **727 Python passed**, **38 frontend passed / 2 skipped**, Node24 build and
diff check pass. Playwright on copied real TC01 reads the saved OCR, has no routine
declaration/link textboxes, records one confirmed 4m event and one acceptance,
then reloads/retries without duplication. No provider/coverage/instruction is
created. Backend8000 restarted and LIVE health checked; nine user business-table
fingerprints are unchanged. Original database was not used for monetary commands.
[Evidence](reviews/2026-10-15-advance-button-confirmation.md). No commit/push/reset.

## Vietnamese source dates and stored TC01 draft — 15/10/2026

Shared calendar normalization now accepts Vietnamese prose dates alongside numeric
dates, rejects impossible days and day/month swaps, and binds trip-range endpoints
to their field roles. Extraction prompt v2 requests ISO dates in its existing call;
source quotes and multiline-company-name handling are preserved. Missing dates
and present-but-invalid formats now have different linker explanations.

The accountant can use **Kiểm tra lại bản nháp đã lưu** to re-evaluate a stored
read, including after restart. GET checks ownership/source digests and current
link candidates; it does not call a provider, bump the case, record money or create
coverage. Unmapped codes on a successful match are in optional reference details.

Verification: **726 Python passed**, **37 frontend passed / 2 skipped** (existing
React act warnings), Node24 production build and diff check passed. Playwright on
a copied TC01 DB proves LINKED/MULTI_FIELD_MATCH, hidden manual link fields and
reload. This reuses actual stored LIVE OCR; fresh provider extraction NOT_RUN.
Backend port8000 restarted with its existing command; a read-only authenticated
GET on the user's case also returns LINKED/MULTI_FIELD_MATCH. All nine business
table fingerprints before/after restart/readback match. No monetary confirmation,
coverage, reset, commit or push. [Evidence](reviews/2026-10-15-source-date-fix.md).

## TC01 multi-field advance link — 15/10/2026

An unregistered reference on an accountant-uploaded voucher no longer blocks a
separate, conservative `MULTI_FIELD_MATCH` decision. The backend requires a
unique employee match, configured company payer, specific matching project
purpose, exact declared-advance amount, source-backed chronology, a transaction
identity not owned by another root, and one compatible tenant root. Missing or
ambiguous facts require accountant confirmation; wrong identity/company,
reference-to-other-activity and cross-root event ownership are conflicts. Each
decision signal keeps its source references. The exact-reference path remains
stronger.

The accountant UI displays the auto-link basis and selects the voucher that was
read. It hides the second link checkbox/reason only for a server-linked result;
the accountant still checks and confirms the money event. This adds no coverage,
grant, authority or instruction.

**Verification:**

- `rtk proxy uv run pytest -q` — PASS, exit 0; focused linker/extraction/advance
  API and guard tests also pass. Added concurrent-upload coverage proves a
  transaction cannot be auto-linked to two roots; tenant isolation, mapped-code
  conflicts, duplicate recording and pending vouchers remain covered.
- Frontend Vitest — PASS, 36 passed / 2 skipped. Build — PASS with Node
  24.19.0 / npm 11.12.1. `git diff --check` — PASS.
- Isolated LIVE Playwright — PASS, one test using the original three PDFs and a
  new proposed root. It linked by `MULTI_FIELD_MATCH` with `TU-TC01` unmapped,
  displayed no link checkbox/reason, and recorded one 4,000,000 VND confirmed
  advance after accountant action. DB/audit retained one acceptance with 13
  refs and eight decision signals; coverage/instruction counts are zero. The
  case remains `WAITING`; full settlement is not claimed. Details and hashes:
  [LIVE evidence](reviews/2026-10-15-multifield-advance-link-live.md).

The clean LIVE context contained only company and employee identities (no
activity references, ledger, grants or coverage). Runtime DB/uploads and browser
evidence are under `.runtime/tc01-multifield-live-20261015-1145/`. The user's
default database/server was not read, restarted or modified. No commit, push,
reset or subagent was used.

## Accountant advance and money-history coverage — 15/10/2026

The accountant can now attach and durably read a transfer/cash voucher on an
existing dossier, verify or complete missing required fields from that saved
source, establish an explicit activity link when no unique reference link exists,
and record the received amount as an actual money event. Activity acceptance is
persisted as its own fact and leaves the new activity `PROPOSED`; it does not add
authority. Money-history coverage is a separate accountant confirmation with
fund/window/opening balance/flow set/witness/reason/server time and the covered
root's ledger version. An upload or absent event history alone never means zero.

**Verification:** full Python suite passed (`rtk proxy uv run pytest -q`); frontend
Vitest passed 34 tests with 2 skipped (existing React `act(...)` warnings); frontend
production build passed with the pinned Node 24 runtime. Final isolated LIVE
Playwright passed in 1.4m using the two original TC01 settlement PDFs and one 4m
advance voucher. The tested UI exposed the paper-declared 760k return, and the
accountant recorded why no company receipt was established in the checked money
history. The final DB contains one confirmed advance, one activity acceptance with
11 refs spanning the voucher and settlement report, one versioned coverage
confirmation and one `COLLECT 760.000` instruction. Reload retained it.

Final admission is `READY_TO_EXECUTE` with `T=E=3.240.000`, `A=4.000.000`,
`P=R=0` by the accountant's scoped history confirmation, and `S=-760.000`.
`execution_state=NOT_STARTED`: no money was collected and the case remains open.
Coverage is a responsible human assertion, not independent bank verification.
The employee-return scenario was verified in deterministic
`test_f01_completed_return_closes_the_loop`; it was not part of the LIVE browser
run. Intermediate isolated failures and the superseded run are preserved in the
[evidence report](reviews/2026-10-15-accountant-advance-coverage-live.md).

The first run exposed missing-payer correction; the accepted correction only
allows an accountant to fill missing required fields from the saved source, and
does not allow overriding populated conflicting OCR. Further regressions fixed
the missing overview-tab transition, the UTC/local date-only check and settlement
source refs on explicit acceptance.

**Evidence and limits:** [isolated LIVE report](reviews/2026-10-15-accountant-advance-coverage-live.md),
[accountant runbook](ACCOUNTANT_ADVANCE_COVERAGE_RUNBOOK.md), and final local evidence
under `.runtime/accountant-flow-live-20261015-confirmed/`. The running user's DB
was not read or changed. No commit, push, reset, or subagent was used.

### Multiline payer provenance and Vietnamese name display — 15/10/2026

The transfer receipt's sender name is split across OCR lines. Text provenance
validation now collapses whitespace only when comparing normalized text values
to a source quote, while preserving the quote exactly in `EvidenceRef`. Wrong or
truncated names remain unresolved. The accountant payer field stays blank unless
the source supports a value; organization context is not used as a substitute.
The payer/payee inputs use larger text so stacked Vietnamese marks remain legible.

**Proof:** positive and negative multiline-name extraction regressions passed;
full Python suite passed. Frontend Vitest passed 34 tests / 2 skipped and build
passed. Isolated LIVE Playwright against the same synthetic source bytes found the
full payer `CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH` with no manual correction,
retained the line-break quote, and showed the payee `NGUYỄN MINH AN` unchanged.
See [LIVE evidence](reviews/2026-10-15-multiline-payer-name-live.md). Provider
mode was LIVE on an isolated DB; the user's DB was not read or changed. Collection
remains `ISSUED` / `NOT_STARTED`, not executed. The currently running server was
left alone; its Python process must be restarted before it can use the backend
validator change.

## Activity budget B removed from current settlement gates — 15/10/2026

User-approved decision in attachment `97a6fa9f-21dd-4ed2-b164-6178f78c0b0c`;
canonical contract/design/ADR0009 updated. Missing B no longer creates FACT in
Reconciler or DRAFT views; `T>B` no longer creates POLICY; B no longer changes
`cost_basis`. The existing B DTO/import/storage remains compatible with old
contexts. No migration or user DB change.

**Regression proof:** TDD RED observed for B-missing/over-B outcomes, legacy
cost-basis sensitivity, DRAFT API issue, generated TC01/pilot contexts and the
D06 denominator. Current tests cover no-B collect 760k, pay 1m, balanced S=0,
low/high/missing-B invariance, retained missing-coverage FACT, retained >8m
RECOGNIZE_COST AUTHORITY and action/scope grants, plus a real answer/reassessment
that closes a seeded legacy `budget:B` issue while keeping coverage, sources,
money-event history and prior audit.

- `rtk proxy uv run pytest -q` → exit 0, all tests reached 100%.
- Targeted unit/integration/generator suite → exit 0.
- Frontend Vitest → 30 passed, 2 skipped; existing React `act(...)` warnings.
- Frontend build → exit 0 with Node 24.19.0 / npm 11.12.1.
- Playwright UI DRAFT/API readback → 1 passed on isolated STUB DB
  `.runtime/budget-retirement-ui-20261015-2/`; no B issue or replacement AUTHORITY.
  OCR draft read itself returned the expected STUB limitation (no LIVE reader),
  so extraction/settlement UI remains NOT_RUN. No provider call was made.
- UC03-F01/F02/F03 remain in their 3-case denominator with financial oracle
  values unchanged; B was removed from their contexts/preconditions. B-only D06
  keeps its original source/oracle in `FUTURE_SCOPE_CASES`; current authored set
  is 14, so the planned 15-development-root gate is **NOT_MET** pending an
  in-scope replacement. No gold outcome was silently rewritten.

No shared web DB, LIVE server, original Hoangha PDF, or external provider was
changed/called. No subagents, commit, push, or reset. Existing unrelated dirty
worktree changes were preserved.

## PDF identity cleanup — 15/10/2026

User-authorized generator/data cleanup: eight pilot PDFs regenerated for Nguyễn
Minh An / Công ty An Thịnh; one obsolete Nguyễn An expansion PDF deleted. Added
two TC01 reception advance forms and paired transfer/cash contexts via the shared
generator's `--tc01-output`. Monetary oracle unchanged; evidence names, provenance,
source manifests and refs updated. [Evidence](reviews/2026-10-15-pdf-identity-cleanup.md):
five generator tests and 32 related tests GREEN, full Python suite exit 0, all ten
PDFs one-page/render-reviewed, hash/name inventory checked. Fresh LIVE/browser for
new PDF bytes NOT_RUN. DB/server/original Hoangha sources untouched; no commit/push.

## TC01 portable demo context — 14/10/2026

User selected a SIMULATED confirmed advance of 4m. Legacy demo now names
NGUYỄN MINH AN / Công ty An Thịnh; a separate typed TC01 fixture provides scoped
B/grants/category policy/ledger/coverage. Runtime accepts the typed JSON through
the existing validated importer; legacy import preserves company name. Dev CLI
adds an explicit timezone-aware `--demo-as-of` for repeatable fictional-history
assessment, while default real-time behavior and trace timestamps stay unchanged.

[Runbook](../../data/demo/README.md) starts a separate database on port 8012.
[Evidence](reviews/2026-10-14-tc01-portable-demo-context.md): 3 meaningful REDs,
21 targeted tests GREEN, full Python suite exit 0, diff check exit 0. Actual stored
LIVE TC01 OCR + new context in isolated admission yields COLLECT 760k with no
issues. Original sources still require confirmation of the one weak link
candidate; no fabricated strong reference/automatic name match was added.
Fresh LIVE/browser NOT_RUN. User's default DB/server and unrelated frontend work
are untouched. Base `38d8da3a`; this task has no commit/push authorization.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ `38d8da3a8b50d7b117a313a2498916302071e55b` (working tree includes prior concurrent edits; no commit made by this task). |
| Phase | Prior T1..T10 + R0–R8/evidence work remains historical. Latest user-authorized scope: accountant advance and full-history coverage workflow; implementation and gates recorded above. |
| Authorized scope now | Accountant advance/coverage workflow, isolated TC01 verification and handoff docs complete. No commit/push/reset. |
| Setup review | ACCEPTED; clean-clone proof passed. |
| Execution method | Inline execution, single integrator; per-behaviour TDD (RED observed → GREEN) + full-suite after. No subagent review (user-directed). |
| Workflow integrator | Inline executor — single writer for workflow/api/domain/frontend shared files |
| Next application task | Continue from the latest product request; if investigating TC01 further, preserve the distinction between human coverage confirmation and independent bank evidence. |
| Last completed application task | Accountant advance receipt, activity acceptance, structured coverage, Vietnamese UI, live runbook and isolated LIVE TC01 verification. |
| Product unit/integration/UI evidence | Full Python suite exit 0. Frontend tests 34 passed/2 skipped and production build passed (Node 24.19.0/npm 11.12.1). Final isolated LIVE Playwright passed with a new proposed activity, durable 4m advance, explicit activity link, settlement and voucher refs, coverage warning for paper-declared return and COLLECT 760k; earlier failed/superseded attempts remain documented. Employee-return closes the 760k collection in deterministic integration coverage. |
| CodeGraph | 220 files / 3,897 nodes / 11,998 edges; index up to date, older-engine warning. `check_index_coverage` unavailable; coverage remains unknown. |
| Git handoff | `final` @ `38d8da3a8b50d7b117a313a2498916302071e55b`; this and prior concurrent changes remain uncommitted. No commit/push/reset. |

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

## TC01 activity-reference import and LIVE verification — 15/10/2026

User-authorized fix and verification; no subagents, commit, push, reset, or edits
to the user's shared database. The typed and legacy import paths now validate,
persist, and expose `activity.references` through the existing v6
`context_activities.references_json` column. New versions replace removed
references; missing references remain empty. The backend linker was not changed.

**Backend gate PASS:** composition-root integration tests prove typed/legacy import,
catalog read, restart, same-payload idempotency, reference replacement/removal,
invalid declaration rejection, unique `DOCUMENT_REFERENCE`, duplicate-reference
conflict, tenant isolation, contradictory strong basis, weak-only confirmation,
and transaction identity. `rtk proxy uv run pytest -q` exited 0 at 100%.
Frontend tests/build and `git diff --check` also pass.

**LIVE gate FAIL:** transfer and cash ran on separate local databases with the
fixed demo clock `2026-10-14T23:00:00+07:00`, real OCR/LLM providers, and the built
frontend. Each settlement upload linked to `activity:tc01` by
`DOCUMENT_REFERENCE` from the page-1 `TU-TC01` quote. The full expected financial
result was not produced: both cases remain `WAITING`, `A=4.000.000`,
`P=R=0`, `T/E/S=UNKNOWN`, with open FACTs `expense:T` and `expense:payer`; no
collection instruction was created. No future coverage was introduced and no
money/policy/grant formula was changed.

Re-upload idempotency subcheck PASS in each branch after the accountant UI was
corrected with party names read from the same source PDF. The API view kept
`A=4.000.000`; isolated SQLite showed zero `money_events` and zero instructions,
while the imported snapshot still contained exactly one method-specific advance
key. Extraction accuracy remains FAIL: transfer `payer_name=null`; cash
`payee_name=null`. These values were recorded as manual corrections, not as OCR
success. The independent trace, OCR, UI, API and database artifacts are under
`.runtime/tc01-reference-live/20261015-005259-ICT/`; the review record contains
expected-versus-actual values, provider state and LangSmith links. The next gate
is to investigate the unresolved cost basis and missing OCR party field before
claiming TC01 financial acceptance.

Read-only reassembly of the stored LIVE reports confirmed the admission mapper
can construct one expense with `incurred=3.240.000 KNOWN`, `ELIGIBLE`, and
`EMPLOYEE_PAID_INVOICE`, but `expense_set_complete=false`: the included payment
proof has `profile_status=NEEDS_HUMAN`. The separate paper/invoice matcher also
reports `SET_PAPER_EVIDENCE_REQUIRED` / `SET_PAPER_UNMATCHED_001` because the paper
references `00000101` and invoice extraction includes series `IR26E`. No rule was
weakened to turn this incomplete evidence set into an instruction.

Current Git work remains uncommitted; unrelated shared working-tree changes were
preserved.

### Transfer receipt receiver field across classification variants — 15/10/2026

The latest default-DB draft classified the uploaded transfer voucher as
`COLLECTION_RECEIPT`. That profile reused the generic receipt field vocabulary,
which omitted `payee_name`; the OCR report still contained the printed receiver.
`COLLECTION_RECEIPT` now has a dedicated profile that retains the generic receipt
fields and also asks extraction for `payee_name`. `PAPER_RECEIPT` stays unchanged.

Regression covers the same two-party transfer layout under both
`COLLECTION_RECEIPT` and `PAYMENT_PROOF`, checking the prompt vocabulary, both
source-bound names, and their quotes. RED was observed for
`COLLECTION_RECEIPT`; `rtk proxy uv run pytest -q` then passed and
`rtk proxy git diff --check` exited 0. No provider/browser rerun was made. The
default server process predates this change and remains running; its startup
imports context into the default DB, so it was not restarted. Restart the server
and reread the saved PDF before expecting the receiver to appear in that draft.

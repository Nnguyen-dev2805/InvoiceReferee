# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ (R8 head). T1..T10 committed; the post-T10 remediation pass (7 commits); then the R0–R8 data/pipeline remediation. |
| Phase | T1..T10 implemented; post-T10 remediation done; **R0–R8 data/pipeline remediation done** (2026-10-13): 15 real cases with source-borne facts, published corpus, reader-per-mode runtime, durable jobs, raw 6-case pipeline, role workspaces, independent suites, M0 LIVE + LIVE baseline. |
| Authorized scope now | Execute the PDF-data/pipeline plan (user-authorized 13/10/2026). Committed on `final`. |
| Setup review | ACCEPTED; clean-clone proof passed. |
| Execution method | Inline execution (executing-plans), single integrator; per-task TDD + full-suite after each. A whole-branch fresh review has not been run. |
| Workflow integrator | Inline executor — single writer for workflow/api/domain owned files |
| Next application task | T11 — needs real feedback (BLOCKED on practitioners). Public hosting + real pilot still BLOCKED. |
| Last completed application task | R0–R8 (data/pipeline remediation). |
| Product unit/integration/UI/LIVE evidence | `uv run pytest` → **244 passed**; vitest 6; playwright 9; build exit 0. M0 LIVE over the 4 technical probes succeeded (real provider calls). LIVE baseline (development) union=**1** (D05, a case without a real conflict source), correct_auto_completion=9. STUB core/escalation union=0. See [RELEASE_EVIDENCE](RELEASE_EVIDENCE.md). Docker build NOT_RUN. Public hosting + practitioner pilot BLOCKED. |
| CodeGraph | Re-check with `rtk proxy codegraph status` before relying on it; the index lags writes. |
| Git handoff | R0–R8 commits (on `final`): R1 81c45067, R2 2918f83f, R3 d99bef60, R4 c0b058b5+4a7e42dd, R5 53a9c011, R6 cc16347e, R7 c7ba4314, R8 (this). Unpushed (no push authorization). |

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

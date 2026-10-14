# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ 68c5e2eb (after R0–R8 + the doc/data cleanup commit). |
| Phase | T1..T10 + R0–R8 done. **Scope change 14/10/2026**: employee-paid narrowing + evidence pipeline promoted into canonical docs (plan E0 done, docs only). Code/contracts/gold **not yet migrated** to the new scope. |
| Authorized scope now | Docs-only turn authorized 14/10/2026: update canonical docs for the accepted scope (Q32–Q34) and the Hoangha evidence pipeline (E0). No code change authorized this turn. |

### Docs turn 14/10/2026 — scope + evidence pipeline (E0)

Docs-only; no code/tests run. Files: new `docs/adr/0007-money-confirmation-basis.md`;
`docs/adr/0006-employee-paid-scope.md` (Q33/Q34 → ACCEPTED);
`docs/final/ARCHITECTURE_AND_EVALUATION.md` (§14 ACCEPTED, new §15, §1/§3 scope);
`docs/final/IMPLEMENTATION_CONTRACTS.md` (§3 Q32, §4 Q32/Q34, §9 async reader, new §12,
`EVIDENCE_READY` in §2/§10.3); `GLOSSARY.md` (6 new terms);
`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md` (E0 ticked, plus
builder-check resolutions). A fresh builder-check subagent read the docs; its 7
questions were resolved: (Q1) `SETTLEMENT_FORM` = uploaded paper, missing ⇒
`SETTLEMENT_FORM_MISSING` finding, no matching; (Q2) evidence gold hand-authored on a
subset (~10–15); (Q3) new `EVIDENCE_READY` state; (Q4) out-of-scope payer deferred as a
documented known hole; plus corpus path fix (v1 = `data/tham-khao/uc-03/`) and an
offline no-live-call guard note. Verification: `git diff --check` pass; headings/enums/
thresholds present. **No commit** (not authorized).
| Setup review | ACCEPTED; clean-clone proof passed. |
| Execution method | Inline execution (executing-plans), single integrator; per-task TDD + full-suite after each. A whole-branch fresh review has not been run. |
| Workflow integrator | Inline executor — single writer for workflow/api/domain owned files |
| Next application task | Hoangha-evidence plan E1–E8 (start E1: strict document/evidence DTOs). Finance/admissibility mapping (Q32/Q34) is a later plan. T11 still BLOCKED on practitioners. |
| Last completed application task | R0–R8 (data/pipeline remediation). |
| Product unit/integration/UI/LIVE evidence | Last recorded run: `uv run pytest` → **244 passed**; vitest 6; playwright 9; build exit 0. LIVE baseline (development) union=**1**; STUB core/escalation union=0. See [RELEASE_EVIDENCE](RELEASE_EVIDENCE.md). **Not re-run this turn** (docs-only); Docker build NOT_RUN. Public hosting + practitioner pilot BLOCKED. |
| CodeGraph | Re-check with `rtk proxy codegraph status` before relying on it; the index lags writes. |
| Git handoff | R0–R8 commits + 68c5e2eb (doc/data cleanup) on `final`. This turn's doc edits are uncommitted (no commit authorization). |

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

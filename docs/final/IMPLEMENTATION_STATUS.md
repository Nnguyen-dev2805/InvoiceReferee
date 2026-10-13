# Implementation checkpoint

This file records observed progress, not product policy or runtime configuration.
The plan owns task acceptance; package/config files own executable commands.

## Current handoff

| Field | Current value |
| --- | --- |
| Base branch | `final` @ 1c395de (T2 commit); `t2-canonical-intake` == 1c395de (same commit, worktree `.worktrees/t2` clean) |
| Phase | T1+T2 committed on `final`; a domain-contract conformance pass is **uncommitted** in the working tree (datetime UTC, EvidenceRef, Instruction, MarkExecution, page_range, bare Fact, factories, CLI entry) — awaiting the user's review and any commit authorization |
| Authorized scope now | Domain-contract conformance fixes (user-authorized 13/10/2026). No Git authorization: these changes stay uncommitted on `final` |
| Setup review | ACCEPTED at documentation/setup level; actual clean-clone and agent-execution proof remain open |
| Execution method | Inline execution (executing-plans) with one integrator; the whole-branch final review has not been run |
| Workflow integrator | Inline executor — single writer for workflow/api/domain owned files |
| Next application task | T6, not started (needs authorization) |
| Last completed application task | T5 — gate passed (M0 genuinely run against real Mistral OCR; LangSmith tracing verified). T4 = ae819ac |
| Product unit/integration/UI/LIVE evidence | T5: `uv run pytest` → **116 passed**; `frontend npm run build` exit 0. **M0 LIVE ran for real** (`.runtime/evidence/m0/m0-manifest.json`): text 69 chars/24ms native, clear_scan 70 chars/1240ms OCR, unclear_scan 70 chars/937ms OCR, non_document 12 chars/680ms OCR — all ok against `mistral-ocr-latest`. **LangSmith tracing verified**: 4 `m0-live:*` runs landed in project `invoice-referee` with basis/model/agent_id/agent_environment. UI source-preview checkpoint: NOT_RUN (Playwright browsers not installed) |
| CodeGraph | **Fresh** at `1c395de`: `codegraph status` → 34 files, 505 nodes, 1135 edges (python 24, tsx 4, typescript 6). The earlier "stale/0 files" note was itself outdated; re-check with `rtk proxy codegraph status` before relying on it |
| Git handoff | T1 = 57d2e19, T2 = 1c395de, domain-conformance = 3245d00, boundary fixes = ec37242 — all on `final` (unpushed beyond 1c395de; no push authorization) |

**Schema note (13/10/2026).** `context_grants` and `context_people` changed primary
keys to `(tenant, grant_id)` / `(tenant, id)` for tenant isolation. `Database.migrate()`
only runs `CREATE TABLE IF NOT EXISTS`, so it does **not** alter an existing table.
No runtime DB exists in this repo, so nothing needs migrating today; any DB file created
before this change must be deleted and recreated (a real versioned migration is a T10
clean-clone/runbook item, not done here).

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

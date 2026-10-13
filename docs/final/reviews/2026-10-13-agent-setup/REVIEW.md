# Independent review — coding-agent setup

**Date:** 2026-10-13  
**Branch observed:** `final`  
**Verdict: NEEDS_CHANGES before calling this a portable, execution-ready coding-agent setup.** The local onboarding/checkpoint is usable for the presently authorized setup/review work. This verdict does **not** approve T1 implementation, select its execution method, or reopen Q1–Q31.

## Boundary, evidence and review standard

Independent, read-only review of `AGENTS.md`, `docs/final/IMPLEMENTATION_STATUS.md`, `.gitignore`, `.python-version`, `.node-version`, and `docs/final/reviews/2026-10-13-agent-setup/SETUP_EVIDENCE.md`. Read `.agents/skills/writing-for-agents/SKILL.md`; used its tests for pointer triggers, progressive disclosure, step/completion criteria, co-location, single-source-of-truth, portability, pruning and sprawl. Read the plan header/Global Constraints/File Map/T1/T2/handoff, contracts §2/§9 and necessary operative refinements, and design §1–4/§12 only as pointer consumers. Inspected the local `subagent-driven-development` and `executing-plans` skills to verify dependencies and instructions that a coding agent would encounter. No product implementation or full architecture review was performed.

Snapshot integrity: `AGENTS.md` has 71 lines and SHA-256 `aad495c97cde1af4985815643a0baa046ad78f13a48010b26cfc5a94dbe5928e`; `IMPLEMENTATION_STATUS.md` SHA-256 `8c8ab8d677beba8a756d6cf3a43e14de11fa1dcbd3191759d77dd6664fadea95`, matching the assigned versions. Read-only `git status --short --branch` showed `final...origin/final`, modified `.gitignore` and untracked instructions, pins and docs. `git ls-files` reported only `.gitignore` and the competition brief as tracked. The inspected Markdown set (`AGENTS.md`, status, setup evidence, plan, contracts) had **21 local links, 0 broken in this workspace**; this checks present files, not a Git clone.

Graph: a scoped `codegraph explore` returned **“This project has nothing indexed”**. The graph generation and index coverage are unknown, and graph MCP discovery/coverage tools were unavailable in the handed-off context. Review tier is **Verify for non-code instruction/config artifacts**, using explicitly authorized scoped file and Git reads. No code-graph completeness or negative code claims are made.

Severity: **P1 = requires resolution before the relevant coding handoff; P2 = implementation variance to reduce before its first trigger; P3 = optional hardening/future trigger.** Findings describe observed text/config and conditional failure scenarios; they are not claims that a fresh clone or coding agent was actually run.

## Findings

### F01 — P1: Required execution skills are intentionally absent from portable Git content

**Where:** `.gitignore:2–3` ignores `.agents/` and `.claude/`; `docs/superpowers/plans/2026-10-13-invoice-referee-final.md:3` says **REQUIRED SUB-SKILL** `superpowers:subagent-driven-development` or `superpowers:executing-plans`; its `Execution handoff` links `../../../.agents/skills/writing-plans/SKILL.md` (`:325–330`). `AGENTS.md:7,37` says to use installed relevant skills, calls local facilities optional, and asks to report an unavailable explicitly requested skill. The two executor skills exist locally only under the ignored `.agents/skills/`. Both refer to `superpowers:using-git-worktrees` in their setup, but that skill was not in the enumerated local `.agents/skills/` files; it may exist through another installation.

**Counterexample:** After an authorized Git publication, a new worker clones the repository without `.agents/` or `.claude/`, reads the tracked plan and encounters a mandatory skill reference it cannot resolve. It can follow the T1 test/contract steps conceptually, but cannot satisfy the plan's explicit skill prerequisite without additional installation or an agreed fallback. The locally valid `writing-plans` link becomes absent in that clone. The current link check cannot detect this because it runs in the creator's workspace.

**Minimal correction:** Choose one authoritative, explicit execution contract: either (a) make the in-repo T1–T13 task steps and gates executable without these machine-local skills and classify the skills as optional orchestration helpers, while still reporting an explicitly user-requested missing skill; or (b) declare the specific skill dependency and supported installation/availability check as a portable prerequisite. Do not copy the entire local skill library into the repository just to repair one link. The plan header and handoff must express the same rule, with no dangling mandatory pointer in the supported clone flow.

**Checkable acceptance:** From a clean checkout with `.agents/` and `.claude/` absent, an agent reads the entry point and either (a) demonstrably selects an authorized native T1 path with all documented gates and no missing mandatory skill, or (b) reliably reports a named, documented prerequisite before touching application files. All mandatory links for the chosen flow resolve. Do not claim this acceptance from current-workspace link checks.

### F02 — P1: Execution skill instructions contradict scoped authorization and human-controlled policy changes

**Where:** `AGENTS.md:5,13,26–30` makes the current user request the scope authority, reserves changes to accepted scope/financial rules/authority for the user, and restricts Git action. Plan Global Constraints `:22,26` and handoff `:325–330` preserve this. However, `.agents/skills/subagent-driven-development/SKILL.md:17–30` and `.agents/skills/executing-plans/SKILL.md:27–43` say **“Execute all tasks from the plan without stopping”** and **“Rulings, not stalls”**, with only four prescribed stopping conditions; the latter skill also says to commit as the plan specifies. Those broad skill directions are in the very execution paths the plan mandates.

**Counterexamples:** (1) The human authorizes **only T1** after this review. An executor following “all tasks without stopping” begins T2–T13, even though status still records no implementation method/integrator and the new instruction authorized one task. (2) During T3, a source proposes a new expense/grant ceiling contrary to the accepted 8/4/20-million demo limits; “rule and continue” would make an unapproved financial-policy choice instead of preserving a counterexample and asking the human. (3) A task is authorized without Git commits, but the executor follows the skill's generic commit step. These are **instruction conflicts and foreseeable failure modes, not observed actions**. The current user and `AGENTS.md` have priority; that fact reduces the risk but does not remove the ambiguous competing workflow text.

**Minimal correction:** Put a task-bounded adapter/override directly at the plan's skill-invocation point, or revise the locally selected execution workflow before use: *continuous execution applies only to the set of tasks the human actually authorized; a genuine conflict with accepted scope, money rules or authority is escalated with a concrete counterexample; commits require existing user authorization*. Routine implementation choices can still be decided by the implementer. Keep the financial rules in the contracts, not duplicated in the adapter.

**Checkable acceptance:** In a dry run using the chosen execution method, an instruction authorizing T1 alone ends at T1's gate; an unresolved change to `E <= 8m`/`|S| <= 4m`/grant 20m produces a targeted human decision request; a no-commit instruction results in no Git mutation. Neither generic “continuous execution” nor “ruling” silently expands scope.

### F03 — P2: RTK is made a hard operational prerequisite despite the portable-tool claim

**Where:** `AGENTS.md:34,37`; `SETUP_EVIDENCE.md:15–18,26–37`. `AGENTS.md` requires every shell command to be prefixed with `rtk`; if RTK is unavailable it directs the agent to report a prerequisite or seek an explicit override. The same file describes local tool settings as optional machine facilities. RTK 0.44.2 is available **on this machine**; its availability is unverified on external clones.

**Counterexample:** A newly cloned machine has Python 3.12, Node 24 and the repo but no `rtk` binary. The agent can read the tasks and has working standard shell commands, yet the onboarding contract directs it to stop for an unrelated local CLI. This turns a convenience wrapper into a blocker for all setup commands.

**Minimal correction:** Either explicitly declare RTK as a supported-environment prerequisite (with bootstrap and version check), or make it a preference when installed and prescribe normal shell command fallback with the same command/result logging. The latter aligns more naturally with the existing “local facilities optional” statement. Maintain the separate requirement to use the pinned interpreters.

**Checkable acceptance:** A fresh environment without RTK can conduct a read-only onboarding/preflight and report exactly which shell implementation ran, without silently claiming RTK coverage or changing global configuration. If RTK is intentionally mandatory, the prerequisite is named and verifiable before T1 is dispatched.

### F04 — P2: Two always-loaded graph workflows consume almost half the entry point, while index availability is conditional

**Where:** `AGENTS.md:39–71` (33/71 lines including marker boundaries) defines Codebase Memory and CodeGraph discovery separately. Both prescribe graph-before-text searching and later source fallback, but with different tools, availability/coverage semantics and ordering. `.gitignore:4` excludes `.codegraph/`; this workspace has such a directory, but the graph query returned no indexed code. The user-provided graph boundary explicitly permits scoped non-code reads for this review.

**Counterexample:** A fresh task to edit only `AGENTS.md` loads two long code-discovery procedures it never needs. A later code task with both tools available may spend calls on both indexed representations, or mistake a clean coverage response from one for confirmation of the other. Neither outcome is currently demonstrated. The required fallback is already documented, so this is **attention cost and ambiguity**, not an existing broken code lookup.

**Minimal correction:** Consolidate the **trigger/decision tree** near the code-discovery entry point: use available Codebase Memory graph for code symbols with explicit coverage; use CodeGraph when its separate index exists and contributes evidence; fall back to scoped source where absent/stale/insufficient. Keep detailed tier, pagination and coverage mechanics in a tracked reference reached **only for code discovery**, or compact them under one heading. Preserve unknown coverage disclosure and the rule that index creation is the user's decision. Do not move mandatory trigger conditions behind a vague pointer.

**Checkable acceptance:** With no graph/index available, a code task reaches scoped source without claiming index completeness; with a suitable graph, it collects the required coverage check once per relevant evidence set. A non-code setup task need only retain a short discovery pointer rather than parse 33 graph-specific lines.

### F05 — P2, first trigger T2: Version pins select targets, but the executable command path is not yet reproducible from portable evidence

**Where:** `.python-version:1` = `3.12`; `.node-version:1` = `24`; `AGENTS.md:35–36`; `SETUP_EVIDENCE.md:27–37`; plan T1/T2 commands at `:73–110`. The default shell observed in this review resolves `python3` **3.14.5** and `node` **v26.0.0**. The parent recorded successfully running uv Python **3.12.13** and scoped Codex Node **v24.19.0**/npm **11.12.1**. `.runtime/agent-toolchain.json` contains machine-specific executable paths and is correctly ignored. T1 creates project manifests/locks; those do not exist yet.

**Counterexample:** At T2, the executor runs the plan's `rtk proxy npm --prefix frontend run build` in its default shell. Without selecting a Node 24 binary in that **same command environment**, a green build might be produced under Node 26 despite the declared pin. Conversely, copying `.runtime/` absolute paths into portable scripts breaks on another machine.

**Minimal correction:** At the first Node-running task, make the preflight executable and local to the task: resolve pinned Node 24 with an available manager/harness, verify `node` **and the npm-launched process** see major 24 under the same scoped environment, then run build/test. Once manifests exist, specify scripts/locks there; retain local paths only as optional hints. `AGENTS.md:35–36` already states most of this correctly, so this is a **T2 execution-proof hardening item**, not a request to install packages during setup review.

**Checkable acceptance:** A T2 evidence record shows the exact selector/command, active Node 24 and npm versions, lockfile/build command, exit code, and any UI/browser verification result. The setup review makes no assertion that such application commands were run.

### F06 — P3, conditional future fixture: Broad database ignore patterns can hide intentionally versioned synthetic data

**Where:** `.gitignore:12–15` ignores all `*.sqlite*` and `*.db*`, including files under `tests/fixtures/`. A live probe with `git check-ignore -v --no-index tests/fixtures/sample.db` selected `.gitignore:14`. The plan currently specifies JSON manifests and synthetic PDF/JSON data, and **no required SQLite fixture was found in T1/T2's file map**.

**Counterexample:** If a later verification task intentionally adds `tests/fixtures/reference.db` as an independently reviewed synthetic fixture, it will remain ignored by default while `.pdf`/`.json` counterparts remain visible. A reviewer could wrongly assume the fixture was packaged.

**Minimal correction:** Retain the broad ignore for real/local DB state, and add an explicit, narrow exception **only if** a committed synthetic SQLite fixture becomes part of an accepted task. Alternatively, prefer a generator plus checked-in JSON input, as the existing plan does. Avoid speculative fixture creation now.

**Checkable acceptance:** Any future required DB fixture is in `git ls-files` or is rebuilt from tracked inputs; local app/runtime/private DBs remain ignored. No action required until a DB fixture becomes part of an authorized task.

## Scenario assessment and positive controls

| Scenario | Result and evidence boundary |
| --- | --- |
| Fresh **local** worker receives only `AGENTS.md` | **Pass for orientation.** Steps `:5–7` point to checkpoint, design, plan and operative contracts with a task gate. `:11–13` identifies accepted scope and authority; `:27–29` demands RED/GREEN and result evidence. All checked present-workspace links resolve. Actual agent-following behavior was not executed. |
| External clean clone **without `.agents/.claude`** | **Not ready/untested.** F01/F03; the current tracked tree has only two files and does not yet include `AGENTS.md`, pins, plan or status. `SETUP_EVIDENCE.md:52–53` correctly discloses this. Do not describe the current valid links as clone proof. |
| Interrupted T1; resumed in a changed worktree | **Well specified on paper.** `AGENTS.md:5,29` requires branch/worktree comparison and interrupted proof; status `:27–37` requires owner/write set, failing command/result and next action. Plan checkbox alone is explicitly insufficient. No interrupted T1 execution exists to validate recovery. |
| New authorization supersedes setup-only status | **Pass, with an operational check.** `AGENTS.md:5` explicitly places the current user request above the snapshot; status `:3–4,10–19` is observed progress, not authority. A worker must reconcile both before editing and update the checkpoint after an authorized task. F02 addresses conflicting executor-skill expansion. |
| Old review disagrees with final design, or new financial-policy ambiguity emerges | **Pass in the main entry point; executor-skill conflict remains.** `AGENTS.md:11–13` makes contracts and §10/§11 refinements operative; historical reviews are dispute-only. The accepted Q31 incurred-cost rule also appears in design §12 and contracts. No Q1–Q31 re-decision is required. F02 covers the local skills' “rule and continue” behavior. |
| Multiagent writes shared workflow/schema/commands files | **Pass as an instruction contract.** `AGENTS.md:26` and plan Global Constraints `:26` require one designated integrator, exact write sets, serial shared-file integration and independent review. Current status `:13–14` correctly says no method/integrator is assigned. No concurrent implementation was performed. |
| T2 build from shell Node 26 versus pin Node 24 | **Known setup hazard, guarded in prose.** Pins, local scoped runtime evidence and requirement to verify the running interpreter exist. F05 asks for verification in the same actual build environment before calling it green. |
| Completion claimed from checkboxes or read-only probes | **Pass as a prohibition.** `AGENTS.md:27–29`, status `:17,27–37`, and plan handoff `:325–330` require actual gates, command exits, modes and artifacts. `SETUP_EVIDENCE.md:44–55` explicitly distinguishes setup from app/unit/UI/LIVE/clean-clone proof. |

## Disposition and handoff

**Blocking before portable coding-agent execution:** resolve **F01** (execution method/skill dependency) and **F02** (strict task/policy authority despite generic executor skills), then perform a **separate publishing/clean-clone gate** after Git action is authorized: stage/commit exact intended setup/design/plan files, verify a clean checkout includes the entry point and required references, and run a bounded onboarding probe. Uncommitted delivery is **an acknowledged pending gate, not a misrepresentation by the setup author**. The current request did not authorize a commit or clean-clone publication.

**Conditional:** resolve **F03** if external workers without RTK are supported; address **F05** before T2's Node build. **F04** is an instruction-quality/sprawl improvement; **F06** only applies if future DB fixtures become normative. The design itself, its settled money policy and Q1–Q31 are out of this review's change scope.

Read-only checks run under RTK: `git status --short --branch`, `git ls-files`, `git diff -- .gitignore`, `git check-ignore -v --no-index` on representative local, secret, data and fixture paths; `shasum -a 256` on setup files; `rg`/scoped reads on instruction/plan/contract/skill files; a Python path-existence check of 21 local Markdown links; `codegraph explore`; `rtk --version`, default `node --version` and `python3 --version`. No app/provider tests, installation, runtime reset, Git mutation or UI/LIVE claims. Independent reviewer edited **only this report**; the parent owns any subsequent setup changes and their verification.

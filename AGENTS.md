# InvoiceReferee — agent entry point

## Start a task

1. Read [IMPLEMENTATION_STATUS](docs/final/IMPLEMENTATION_STATUS.md); compare its checkpoint with the current branch, worktree and files. The user's current request sets the authorized scope.
2. For product work, read [design §1–4](docs/final/ARCHITECTURE_AND_EVALUATION.md), then the header, Global Constraints, File Map and assigned task in [the plan](docs/superpowers/plans/2026-10-13-invoice-referee-final.md). Complete the current task's gate before advancing.
3. For implementation, read [contracts §2/§9](docs/final/IMPLEMENTATION_CONTRACTS.md) for shared DTOs/interfaces and the relevant branches below. Defining shared DTOs also requires their §10/§11 refinements. Before editing, state the task, owned files, consumers and proof of completion. The repo's workflow is self-contained; installed skills are optional helpers. If the user explicitly requests an unavailable skill, report that specific gap.

## Authority and context

- [Competition brief](docs/Challenge_Brief_OrganizationAI_VN.docx.md): contest requirements. Design: accepted scope/Q1–Q31. Contracts: operative behavior; §10/§11 refine earlier shorthand. Plan: task sequence and acceptance. Status: observed progress only.
- Build the fresh `final` design (or an authorized branch based on it). Earlier branches and review archives are historical evidence; consult a review only for the specific clause under dispute.
- Resolve apparent ambiguity by reading the operative contract. For an actual conflict or a proposed change to accepted scope, financial rules or authority, preserve the counterexample and ask the user; ordinary in-scope implementation choices belong to the implementer.

| Work branch | Read before changing behavior |
| --- | --- |
| Evidence/OCR/payer/history | Contracts §3/§8/§10.2; source admissibility and read failures |
| Money/policy/eligibility | Contracts §4/§5/§10.1–3; actual, fulfillment, usage and material basis |
| Commands/jobs/Stop/restart | Contracts §6/§9/§10.3–4; versions, durable jobs and execution state |
| Evaluation/adaptation | Contracts §7/§10.5/§11; gold visibility, units, paired evidence and gates |
| UI | Design §4/§10 and current task's browser checkpoint; server view is authoritative |
| A changed domain term or accepted technical decision | [GLOSSARY](GLOSSARY.md) or the relevant [ADR](docs/adr/); update its existing source |

## Execute and hand off

- One integrator owns the shared workflow/schema/command boundary identified in the plan. Dispatches identify the actual integrator, exact write set, dependencies and reviewer; serialize shared-file edits. A reviewer does not implement the change being reviewed.
- Use meaningful RED → implementation → GREEN for the task's behavior. Run its required integration/raw/browser checks; report UI NOT_RUN when only a component was checked. Completion requires the task's specified gate, not a plausible diff.
- Record command, exit/result, tested version, provider mode and evidence location. Runtime results outrank prose; independent gold stays outside the application/model input.
- At a completed task, update its plan checkboxes and the status checkpoint with evidence and remaining gaps. At interruption, preserve the failing check, local changes and next action. After resume, verify the checkpoint against the checkout before editing.
- Keep changes within the request. Commit/publish/reset only within the user's authorization; stage exact intended files, preserve unrelated changes and public history. A missing optional service or tool is a specific capability gap, not grounds to invent an approval flow.

## Environment

- RTK (Rust Token Killer) is a supported-environment prerequisite required by the user. Verify `rtk --version` and `rtk gain`; prefix shell commands with `rtk`, using `rtk proxy <command>` for raw output. If absent, report the named prerequisite with the [official bootstrap instructions](https://github.com/rtk-ai/rtk/blob/develop/docs/guide/getting-started/installation.md); ordinary-shell fallback requires the user's explicit override. Optional local skill/settings files are a separate capability.
- Resolve Python from `.python-version` with uv; resolve Node from `.node-version` using an available manager or harness runtime. Verify the interpreter used by the command, rather than assuming the shell default. Package scripts/lockfiles become the command source when implemented.
- If the shell runtime differs from a pin, `.runtime/agent-toolchain.json` (when present) is a machine-local path hint; verify its executable before use. If absent, resolve the runtime on the current machine. Keep machine paths outside portable project configuration.
- Before the first npm build/test, verify both `node --version` and npm's own Node via `npm --loglevel=verbose --version` under the same scoped environment used for that build/test. Capture the selector and versions in evidence.
- Local credentials/state/evidence belong under ignored `.env`, `.runtime/` or `private/`. Synthetic inputs/gold, source and lockfiles belong in the repo. Local skill/tool settings are optional machine facilities; portable workflow rules are in this file and the plan.

<!-- codebase-memory-mcp:start -->
## Code discovery

Before locating or understanding code, read [CODE_DISCOVERY](docs/final/CODE_DISCOVERY.md): select the suitable graph, verify its evidence/coverage and pass limits to delegates. Scoped string/config/docs searches use raw tools directly. An absent/stale/incomplete index leads to disclosed source fallback, not an index-completeness claim or automatic indexing.
<!-- codebase-memory-mcp:end -->

<!-- CODEGRAPH_START -->
CodeGraph uses the same discovery procedure above; its index freshness and coverage remain separate from Codebase Memory.
<!-- CODEGRAPH_END -->

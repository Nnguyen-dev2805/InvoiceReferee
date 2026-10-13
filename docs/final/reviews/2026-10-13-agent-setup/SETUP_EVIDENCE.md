# Agent setup evidence — 13/10/2026

Scope: coding-agent instructions/configuration for the fresh `final` build.
This is a setup check, not product implementation, runtime quality or clean-clone proof.

## Change set

| File | Purpose |
| --- | --- |
| [AGENTS.md](../../../../AGENTS.md) | Portable entry point, authority/pointers, current-task gates, ownership and discovery |
| [IMPLEMENTATION_STATUS](../../IMPLEMENTATION_STATUS.md) | Resume/handoff checkpoint; no duplicate task checklist or product policy |
| [CODE_DISCOVERY](../../CODE_DISCOVERY.md) | Conditional graph/coverage procedure; one reference loaded for code discovery |
| [.python-version](../../../../.python-version) / [.node-version](../../../../.node-version) | Project interpreter selectors matching the accepted contract |
| [.gitignore](../../../../.gitignore) | Make agent guidance trackable; separate local secrets/state from committed synthetic inputs |

Local `.agents/`, `.claude/`, `.codegraph/` remain machine facilities. No global
Codex settings, model defaults, external tools or whole skill library were changed.
The current setup does not select the product implementation method or authorize
all future task execution. The user's next instruction controls that scope.

## Observed checks

All commands were prefixed with RTK; completed checks below returned exit 0.

| Check | Actual result |
| --- | --- |
| `rtk proxy git branch --show-current` | `final` |
| `rtk --version` / `rtk proxy uv --version` | RTK 0.44.2 / uv 0.12.9 |
| `rtk proxy uv run --no-project --python 3.12 --no-python-downloads python ...` | Assertion for Python 3.12 passed; 3.12.13. uv warned that no application project manifest exists, as expected at this phase. |
| Scoped PATH to the discovered Codex Node runtime, then `rtk proxy ... node ...` | Assertion for Node major24 passed; v24.19.0 |
| Same scoped PATH then `npm --version` | 11.12.1 |
| Same scoped PATH then `npm --loglevel=verbose --version` | npm reported `using node@v24.19.0`; verified npm itself uses Node24 |
| `git check-ignore` assertions | 10 intended repo paths visible; 12 local/generated paths ignored |

The default shell still resolves Python3.14/Node26; pins do not rewrite the shell.
Python is resolved through uv. For this machine, a local hint at
`.runtime/agent-toolchain.json` records the verified Node bin directory; use it
only as a hint and recheck the command's interpreter. Another machine resolves
its own runtime through an installed manager/harness, not these machine paths.
An initial local probe assumed npm lived beside the bundled Node binary and failed.
The corrected hint resolves npm separately from the scoped PATH; Python, Node and
npm executable probes then all passed. Node selection also applies to npm's
interpreter through that scoped PATH, without changing global npm installation.

Visibility probes: AGENTS, version files, status, `.env.example`, lockfiles and
synthetic input PDF/gold JSON. Ignore probes: `.env*`, runtime/private/SQLite,
venv/node_modules/build outputs, and local skill/tool settings. These probes do
not create or commit sample secrets, databases or synthetic dossiers.

## Corrections after independent review

The [original review](REVIEW.md) found six issues; its report remains unchanged.
The parent applied F01/F02: the plan header/handoff now points to the repo's
self-contained process; optional local helper skills cannot widen authorized
tasks, change accepted financial rules or perform unapproved Git operations.
Shared DTO work explicitly reaches operative §10/§11 refinements.

F03: RTK remains a named supported-environment prerequisite because the user
requires its command prefix. The entry point links the official bootstrap and
requires version/gain verification; automatic bare-shell fallback was declined.
F04: AGENTS reduced from71 to48 lines; graph details are in one conditional
tracked reference. F05: npm's own Node24 is verified, and T2 now requires that
proof in the same build environment. F06 is deferred until an accepted task
requires a committed DB fixture; current packets use tracked PDF/JSON/generators.

Fresh local checks after corrections: 10 visible/13 ignored representative paths,
version selectors, scoped Python/Node/npm, and a temporary documentation snapshot
without `.agents/` or `.claude/`. Its 17 inspected mandatory/context links resolve;
the plan has no mandatory local-skill dependency and states T1-only/no-commit scope.
This snapshot is a file-copy probe, not a Git clone or empirical agent execution.

## Evidence limits and review

CodeGraph returned “This project has nothing indexed”; no generation or coverage
tool is exposed. This work uses non-code file/config fallback, not code discovery.
There is no product source/test/manifest implemented in this change set.
No unit/UI/LIVE evaluation, provider request, dependency installation, DB reset,
Git commit/push or public deployment was performed.

Setup files and accepted design/plan are still uncommitted. `AGENTS.md` is now
trackable; guidance has not yet been proven to ship in a fresh remote clone.
An independent reviewer is assigned to the setup surface only; its findings are
historical evidence, not an alternative source of project policy.

## Final independent closure

[Hubble's response](RESPONSE.md) accepts the corrected instruction/setup contract:
F01–F04 closed; F05 verified for preflight with actual T2 still required; F06 deferred
until a DB fixture is an accepted dependency. Reviewer independently checked npm's
Node24 and RTK, and performed a paper T1-only/no-Git/absent-skills onboarding probe.
No empirical coding-agent execution or product tests occurred. Status now records
that setup review is complete, while implementation/method/integrator remain open.

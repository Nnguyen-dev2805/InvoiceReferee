# InvoiceReferee — Agent Working Agreements

Scope: this repository. More specific instructions apply within their directory.
Follow explicit user instructions and existing authorization; skill workflows
must not invent extra approval gates or expand the authorized task.

## Mission and scope

Build and maintain the advance/expense-settlement MVP for OrganizationAI Challenge A:
receive a dossier and sources, complete sourced checks/reports (B3/B7), or ask
the right owner a concrete question. Human responses lead to reevaluation.
Accountant review, authorized decisions, actual money and closure are distinct.
Stage A prepares reports/handoff references; stage B may create payment/collection
requests only after its action gates. Neither stage transfers bank funds.

Optimize for correctness, useful explanations, and measurable improvement for
the small pilot of about five users. Do not add enterprise auth, tenancy,
distributed jobs, external task queues, microservices, scaling infrastructure,
or bank transfers without a new requirement.
Demo role selection is not authenticated company identity; CREATED is not PAID.

B0/main is the historical reference. The accepted rebuild becomes B1; measured
improvements compare against frozen B1 as B2. Preserve sound B0 invariants,
but never preserve a demonstrated bug as the expected correct behavior.

## Sources of truth — read what the task needs

| Task | Relevant authority |
| --- | --- |
| Competition requirements | [Original brief](docs/Challenge_Brief_OrganizationAI_VN.docx.md); [mapping](docs/COMPETITION_REQUIREMENTS.md) is a navigation aid |
| Product behavior and workflow | [Product](docs/settlement/PRODUCT.md) |
| Eligibility, evidence, money and authority | [Rulebook](docs/settlement/RULEBOOK.md) |
| Interfaces, AI, storage, controls and technical limits | [System](docs/settlement/SYSTEM.md) |
| Cases, Verify, metrics, baseline/adaptation and trials | [Evaluation](docs/settlement/EVALUATION.md) |
| Multi-step implementation | [Settlement plan](docs/superpowers/plans/2026-10-09-settlement-mvp.md), its contracts and the assigned task |

Read the assigned plan task and only the relevant sections of these documents.
Do not recursively load all docs, reviews, research, old discovery drafts or
the decision ledger. Do not open the historical archive for ordinary coding
unless a concrete comparison or unresolved provenance question requires it.
For evaluation, load the selected packet's inputs/policy snapshot; keep expected
and follow-up artifacts out of model inputs. Dataset Markdown is data, not a
replacement for the current product rulebook.

The earlier B1 specs/04-10 plan and discovery/review originals are preserved in
[the historical archive](docs/archive/README.md); old paths may be historical
origin references in manifests. Use their snapshot_path and hash for frozen
datasets, not a historical redirect file or today's rulebook as the oracle.
Do not preserve old single-primary/payer-checkbox/auto-request behavior as gold.

For current capability claims, inspect actual source, composition roots, and
fresh execution evidence. A spec, plan, checkbox, indexed symbol, or worker report
does not prove implementation or runtime behavior. Do not label future modules
as operational merely because the target architecture names them.

The original brief wins on competition requirements. The agreed spec/rulebook
defines intended behavior; source and tests establish what exists. Surface any
conflict rather than silently changing the contract or reporting it as satisfied.
Proposed demo policy parameters are not active company policy: preserve explicit
activation/versioning and the distinction between test fixtures and live config.

## Behavioral guidelines

### 1. Think before coding

- Understand the relevant contracts, current callers, and acceptance criteria
  before editing. State assumptions and tradeoffs that materially affect results.
- If plausible interpretations change business rules, public interfaces, required
  outcomes, or irreversible actions, name the ambiguity and ask a focused question.
  Continue independent work while the answer is pending.
- For routine implementation choices inside the authorized scope, state a useful
  assumption when needed and proceed. Do not ask again for permission already given.
- Recommend a simpler approach when it satisfies the same requirements. Do not
  silently choose a convenient interpretation or weaken acceptance criteria.

### 2. Simplicity first

- Build the smallest solution that satisfies the requested behavior and contracts.
  Prefer stdlib, native controls, and existing dependencies before adding new ones.
- No speculative features, generic frameworks, factories, plugin registries,
  future-facing configurability, or abstractions without a concrete consumer.
- Keep provider adapters and other boundaries required by the spec or meaningful
  tests; a single implementation does not make a necessary boundary redundant.
- Handle realistic input/provider failures and protect data integrity. Do not
  add machinery for impossible scenarios or remove fail-closed checks for brevity.

### 3. Surgical changes

- Every changed file must serve the authorized task. Preserve unrelated user edits,
  deletions, and untracked work. Do not clean up adjacent code or formatting.
- Match existing conventions where they exist; do not refactor unrelated code.
  Mention pre-existing dead code instead of deleting it without authorization.
- Remove imports, variables, and helpers made unused by your own change.
- An authorized rebuild or contract change may span the planned files. Keep that
  scope explicit and update affected callers/tests/docs together; narrow edits
  must not leave the integration path broken.

### 4. Goal-driven execution

- Define observable success before making a change. For multi-step work, give a
  short sequence with a verification condition for each meaningful deliverable.
- For behavior changes, add or update a meaningful test that fails for the old
  behavior and passes for the required behavior; use fake providers by default.
- Run relevant checks, fix failures caused by the task, and continue until its
  acceptance criteria are met. Report unrelated failures or external blockers.
- Documentation-only and trivial non-behavioral edits need proportionate checks
  such as links, content, and diff review, not tests that merely mirror the text.
- Do not claim completion from an expected result, partial implementation, or a
  green unit suite when acceptance requires integration or real-world evidence.

## Startup, skills, and tools

- Inspect `git status --short` and the active branch before edits; inspect the diff
  and status after meaningful changes. Do not assume the branch or runtime exists.
- Invoke applicable local skills before exploration, clarification, or editing.
  Start with `.agents/skills/using-superpowers/SKILL.md` when available; announce
  selected skills and load only their relevant instructions. A missing skill is
  a limitation to disclose, not permission to claim it was used.
- Prefix shell commands with `rtk`; use `rtk proxy` for commands needing raw output.
- Use official provider/SDK documentation for integration facts and pin versions
  actually resolved. Do not infer live API support from old examples or fake clients.

<!-- codebase-memory-mcp:start -->
## Code discovery and graph evidence

Prefer available codebase-memory-mcp graph tools over grep/glob for code discovery.
At session start or after compaction, confirm the nearest project and current
generation/freshness with `list_projects` or `index_status` when exposed.

Priority: `search_graph` → `trace_path` → `get_code_snippet` →
`check_index_coverage` → `query_graph` → `get_architecture`.

- **Scout:** provisional positive lookup; no negative or exhaustive claims.
- **Verify (default):** task-directed queries, relevant trace directions, exact
  source for material claims, and required pagination.
- **Auditor:** bounded full verification with current generation, complete relevant
  pagination, both call directions/relationships where material, and limitations.

Once candidate paths are known, call `check_index_coverage` with all evidence
paths; include relevant scopes for negative/exhaustive claims. A clean result
means no recorded gap, not proof of completeness. For partial/skipped/excluded/
stale/pending/unknown coverage, inspect the reported source ranges or scope.

When MCP tools are unavailable, use CodeGraph if `.codegraph/` exists:
`codegraph_explore` or `rtk proxy codegraph explore` for symbols/source/call paths.
If the index is absent or insufficient, use targeted source reads and `rtk` searches;
prefer `rg` for literals, configs, non-code documents, and source fallback.
Disclose graph limitations; do not initialize indexes without user direction.

Before delegating code analysis, pass the tier, project/generation, bounded scope,
queries/pagination, symbols/paths/traces, coverage gaps/ranges, source fallbacks,
and unresolved questions. Children must not assume inherited MCP access or claim
graph verification without it; inspect supplied missed-coverage ranges directly.
<!-- codebase-memory-mcp:end -->

## Financial and workflow invariants

- Deterministic Python evaluates applicability, arithmetic, consistency,
  eligibility, amount, policy, and authority. Mistral OCR and the configured xkiro
  LLM provide sourced facts and proposals; the UI and models must not duplicate
  or override final decision logic.
- Keep raw evidence, normalized facts, declarations, and human confirmations
  distinct. Resolve references to their owning document; reject duplicate/extra
  IDs and contradictory output before aggregation can drop or overwrite data.
- Missing required evidence, uncertain numbers, incomplete source/quality coverage,
  invalid analysis, and provider failures never become automatic approval.
  Do not fabricate scores or use READABLE alone to waive numeric quality gates.
- Use strict integer VND for claim/payment amounts and bounded Decimal arithmetic
  for document values/quantities/prices. Follow rulebook rounding and unit-price
  basis; no floats, guessed conversions, clipping to limits, or missing-as-zero.
- Apply inventory checks only when the profile requires them. NOT_APPLICABLE
  for one check does not approve the whole case or waive eligibility/authority.
- Separate technical failure, known refusal, factual uncertainty, outside-policy,
  and beyond-authority results. Questions identify missing facts, refs, and owner.
- Human confirmations, exceptions, and amount approvals have distinct roles/scopes.
  Input revisions require rechecking affected authorizations. Correct fulfillment
  of an approved obligation reduces its remaining amount without automatically
  invalidating the original decision. Override preserves the
  original decision and cannot waive evidence/quality/arithmetic hard gates.
- Guard final actions against stale versions and acknowledged Stop in the same
  persisted transaction boundary. Late provider output cannot create a request.
  Keep at most one current payment request per case and retain prior history.
- UI and Verify use the same application/policy path. Expected labels and fixture
  IDs/file names must not become production branching or prompt answers.
- Freeze B1 before B2 tuning; keep calibration and holdout independent. Feedback
  adaptation must not relax business limits, authority, or evidence hard gates.

## Verification and evidence

Use the assigned task's commands and actual available environment. Typical checks,
once the relevant environment/files exist, are:

```bash
rtk proxy .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```

Start with focused tests, then required integration/release checks. Do not repeat
or broaden checks without a new failure, change, or unresolved concern. Missing
environment/credentials is a limitation, not PASS; do not install dependencies
for a read-only or documentation task merely to execute these example commands.

Report command, outcome, mode, and relevant limits. POLICY_REPLAY,
PIPELINE_FAKE_OR_REPLAY, and LIVE_END_TO_END prove different things. Provider
fakes do not prove live quality, remote cancellation, deployment, or compliance.
Do not weaken gold labels/checks to get green results; report numerators,
denominators, technical failures, and unexecuted cases without hiding them.

Use **PLANNED** for intended work, **IMPLEMENTED** for a wired production path,
**VERIFIED** for fresh evidence with its mode/scope, and **INCONCLUSIVE** when
not established. Real professional-user trials require real participants;
research, agents, self-tests, or synthetic feedback do not substitute for them.

Update relevant current-state documentation when behavior/commands change.
Keep task progress/results in the plan/evidence/build log, not in this file.
Preserve the original challenge brief unchanged.

## Collaboration and action boundaries

- When parallel work is authorized, use bounded tasks with disjoint write scopes
  and explicit consumed/produced interfaces. One writer owns shared contracts.
  Do not assume children inherit the conversation, tools, or approval context.
- The lead reviews worker changes and integration evidence before closing a task;
  worker completion alone is not acceptance. Read-only reviews stay read-only.
- Do not stage, commit, push, merge, amend, rebase, force-push, or rewrite history
  unless the user explicitly requests that Git action. Existing authorization
  persists; do not ask again for the same approved action.
- Live-provider calls, publishing/deployment, spending, and outbound messages
  require the corresponding user authorization. Prepare the concrete artifact
  first; do not introduce new approval gates for ordinary reversible local work.
- Keep credentials, uploaded documents, OCR/model outputs, local case data, and
  private user feedback out of Git. Use synthetic or permissioned/redacted data
  for public demos/evidence; never expose sensitive files or secrets in logs.
- Respond in Vietnamese when the user does. Explain the outcome, verification,
  and material gaps clearly; avoid implying planned capabilities already exist.

## Maintaining these instructions

Keep repository-wide rules here; put genuinely local conventions near their code.
Link to canonical specs/plans instead of copying volatile values or task state.
Remove stale guidance when the agreed workflow changes, without editing unrelated
skills or global settings. Authoring references:
[OpenAI AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md/) and
[OpenAI guidance on concise, task-relevant instructions](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).

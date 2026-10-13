# Code discovery reference

Load for code symbols, call paths or architectural source claims. Config/docs and
string-literal searches may use scoped raw tools directly. This file is the repo's
single discovery procedure for Codebase Memory and CodeGraph.

## Select evidence

1. At session start/resume, confirm the nearest graph project/generation with
   `list_projects` or `index_status` when exposed. Choose Scout (provisional positive
   lookup), Verify (default task verification), or Auditor (bounded full verification).
2. Prefer Codebase Memory MCP when available: `search_graph` for symbols,
   `trace_path` for relevant callers/callees, `get_code_snippet` for material source;
   use `query_graph`/`get_architecture` for complex structure/summary.
3. If `.codegraph/` exists and CodeGraph is the suitable available index, use
   `codegraph_explore` (or `rtk proxy codegraph explore ...`) before raw code
   search/read. Treat fresh returned source as read. Use a second index only to
   resolve a remaining question; a coverage result belongs to its own index.
4. Absent tools/index or insufficient results: report the actual availability and
   use scoped source fallback. Index creation is the user's decision. A tool that
   reports unindexed code is not proof no code exists.

## Coverage and claim strength

After paths are known, call `check_index_coverage` once for all evidence paths
when exposed; include relevant scopes for negative/exhaustive claims. Clean means
no recorded gap, not proof of completeness. For partial/skipped/excluded/stale/
pending/unknown coverage, read missed ranges or the bounded scope before reliance.
When coverage tools are absent, record unknown coverage and verify needed source.

Verify uses task-directed graph evidence, relevant trace directions, exact material
snippets and relevant pagination. Auditor additionally requires current generation,
complete relevant pagination, both call directions/broader relationships where
material, and every limitation disclosed. Scout supports only provisional positive
lookup; it cannot establish absence or an exhaustive repository result.

CodeGraph freshness warnings require current reads of affected ranges; an unknown
or recovering index is not promoted to fresh. Graph structure does not prove
runtime correctness; tests/runtime evidence remain separate.

## Delegate

Pass tier, project/generation/freshness, bounded scope, queries/pagination, qualified
symbols/paths, relevant call chains, coverage gaps with ranges/reasons, source
fallback already performed and unresolved questions. A child without graph tools
uses supplied evidence plus exact source and states its access limits.

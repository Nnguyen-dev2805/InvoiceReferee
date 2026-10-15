# Accountant advance confirmation by button — 15/10/2026

Scope: user-approved simplification on `final` base `38d8da3a` plus existing dirty
worktree. Complete, source-clear, automatically linked advance drafts are recorded
by the accountant's explicit button action without repeated free text. Backend
revalidates actor, source, parties, values, status and current link, then derives
the statement and persists recorded_by/record_reason/draft/refs. Missing-field
corrections require explanation; manual links reuse their existing reason.
Generic non-draft money recording is not changed. Pending/conflicting/unclear
sources cannot gain confirmed received money from this shortcut.

## Evidence

- RED: routine API record with empty reason was rejected; UI still exposed the
  declaration and demanded text. Tests failed before implementation.
- Browser first receipt succeeded but retry exposed an existing mismatch:
  linker returns TRANSACTION_IDENTITY while ActivityAcceptance rejected it. Added
  a failing API retry assertion, synchronized the DTO/frontend literal, then
  verified one physical event and one acceptance after retry/reload.
- `rtk proxy uv run --no-sync pytest -v -p no:cacheprovider
  --junitxml=.runtime/advance-click-pytest.xml`: **727 passed**, exit0.
- Scoped Node24 `npm --prefix frontend test`: **38 passed, 2 skipped**, exit0;
  existing React act warnings remain.
- Scoped Node24 `npm --prefix frontend run build`: pass, exit0.
- `rtk proxy git diff --check`: pass.
- Python3.12.13 / Node24.19.0 / npm11.12.1. Node selector:
  `/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`
  prepended to `/opt/homebrew/bin:/usr/bin:/bin`.

Playwright used the actual built frontend/workflow on a copy of the real TC01 DB,
reusing saved LIVE OCR. Provider adapters deliberately reject calls. It refreshed
the stored draft, asserted no routine declaration/correction/manual-link inputs,
clicked the button once, verified confirmed 4m plus one acceptance, then reloaded
and repeated without duplication. Coverage and instructions remain absent.
Read-only DB checks confirm authenticated accountant actor and server-generated
record_reason. Evidence, screenshot, trace, copied DB and script:
`.runtime/advance-click-20261015/`. Test logs/XML: `.runtime/advance-click-*`.

The user's backend8000 was restarted with the same existing dev command; LIVE
health was checked. All nine business-table hashes before/after restart match.
No monetary command was sent to the user's original DB. No reset, schema migration,
dependency, commit, push or subagent. Fresh-provider LIVE scenarios were NOT_RUN;
their affected field-label callers were updated, without claiming rerun results.
CodeGraph current snippets plus exact omitted ranges were read; coverage tooling
was unavailable, so graph coverage remains UNKNOWN.

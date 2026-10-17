# Groq selective integration — 17/10/2026

Base mainca888b2e. Local implementation; no whole-branch merge/cherry-pick from
worktreegroq-bench5e1a53ce. Source worktree left unchanged. Kimi stays default;
xKiro remains selectable. No .env/credential edits, provider calls, userDB writes,
server restart, commit/push/deploy in this task.

## Changes

- Optional Groq adapter/config/runtime/readiness/safe Verify config with model
  openai/gpt-oss-20b. .env.example documents explicit opt-in. Shared workflow.
- Every real HTTPattempt, including429, chargesRunBudget and emits its own trace.
  Before retry checks remaining attempts/deadline; wait larger than remaining
  deadline (or60s) refuses. Each request timeout bounded by remaining deadline
  using asyncio.timeout plus HTTPtimeout. No fallback to another provider.
- Provider finishlength/content_filter/tool_calls or refusal fails as incomplete
  transport outcome even when content is validJSON. Invalid envelope/content and
  HTTPerrors are not schema-repaired. One shared schema repair remains supported.
- JSON cleanup unwraps outer fences/leadingthink only, preserves literal source
  tags inside JSONvalues. ErrorHTTP does not echo provider body into logs.
- Flat row normalization keeps objectvalue/state/quote/page; missing source quote/
  page or scalarfield never manufactures a FOUND citation. Invalid wrapped field
  is not silently dropped. Existing schema/source validator and shared repair gate
  apply to allproviders. Code generates rowids; model cannot grant money authority.
- Explicit line-normalization version participates in both legacy/role-aware reader
  identity to invalidate incompatible cached reads. No force re-read of user cases.
- Selectively copied provider plumbing only. Old inadmissibility keywords, inferred
  VAT/discount code, PyMuPDF/dependency changes and hard-case scripts NOT imported.
  Hash checks confirm admission/VAT, lockfile and demo context unchanged frombase.

## Verification

Red before implementation:9failures on missing-source normalization, budget/deadline,
finish/refusal, perHTTPtrace, literalJSON tag preservation. Separate malformedrow
RED→GREEN reproduced and fixed. Focus covers adapter/provider/readiness/extraction/
sharedrepair/roleawarepipeline/telemetry/cache identity. Timeout simulated using
HTTPMockTransport; all artifacts under.runtime/groq-integration-20261017.

Focused 111PASS. Full 1073PASS/6FAIL (1079total); exact six inherited names match base final audit.
- `tests.integration.test_employee_return_draft_api::test_employee_return_upload_is_durable_but_does_not_record_R`
- `tests.integration.test_employee_return_draft_api::test_accountant_confirmation_records_one_instruction_bound_return`
- `tests.integration.test_employee_return_draft_api::test_pending_second_return_cannot_confirm_after_collect_is_fulfilled`
- `tests.integration.test_employee_return_draft_api::test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction`
- `tests.integration.test_employee_return_draft_api::test_overpaid_return_is_recorded_but_raises_a_specific_blocker`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]`

No xfail/financial/time guard relaxed. gitdiffcheckPASS. Fullsuite notGREEN.
Browser/UI NOT_RUN (no frontend edits); LIVE/modelaccuracy/25case acceptance
NOT_RUN. Existing benchmark logs are historical only, not certification of this
snapshot. No claim that Groq is faster or equally accurate based on mock tests.
Graph used main composition/sharedstructured symbols; new Groq/source changes
verified by bounded direct source reads; index generation/coverageUNKNOWN.


## User-authorized default change and commit — 17/10/2026

Supersedes the optional/Kimi-default checkpoint above: user explicitly requested
Groq default in source and local.env. Provider/model/effort are groq / openai/gpt-oss-20b /
low. `.env.example` documented; ignored `.env` updated privately, key blank for user
entry. Local read confirmed missing settings onlyGROQ_API_KEY; no secrets printed.
Kimi/xKiro configuration retained. No restart (running process retains old config),
no LIVE call, push or deploy. Tests for default readiness/composition now explicitly
expect Groq and verify selected evidence classifier; Kimi tests select Kimi explicitly.
Initial default-change failures retained in default-full.xml/log before fixture
expectations were updated. No runtime fallback/financial guard disabled.

Final Groq-default snapshot: 1073PASS/6baselineFAIL (1079total), default-full-final.xml. Default/wiring focused tests60PASS+15PASS. No new failures relative to base.

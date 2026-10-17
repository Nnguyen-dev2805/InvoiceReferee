# Multi-rate VAT hardening — 17/10/2026

Scope: selectively port VAT support from fix-hard-cases5e1a53ce onto main9c01477e.
No wholesale merge/cherry-pick: inadmissibility keywords, dependency changes and
live scripts are excluded. Existing user context-date edit and output PDF preserved.

## Behavior

- Printed total VAT is preferred in legacy and role-aware extraction prompts.
  Without total VAT, independent printed component amounts may repeat tax fields.
- Do not infer VAT from rates or try discount allocations to fit printed total.
- Keep any unreadable/ambiguous monetary component blocking, in either field order.
- Repeated tax source locations (source/digest/page + bbox, record key, or quote)
  block instead of being summed. Equal values with independent source refs count
  separately. Mixed total/breakdown labels block for clarification, not double sum.
- Signed printed discount is treated as a deduction. No changes to money formula,
  authority, eligibility/policy or original source documents.
- Source refs on findings include all monetary components, including alternatives.
- Prompt content participates in reader identity hash, so modified prompts change
  cache identity without relying on the human-readable version label alone.

## Evidence

`.runtime/vat-hardening-20261017/`: red.log (4 failing regressions before code),
region-red.log (same bbox/different quote counterexample), green.log,
focused-final.log (83PASS), full-final.log/xml, context-baseline.log, result.json.
Unit and workflow tests cover distinct/equal VAT amounts, repeat source, mixed
summary/components, unread field order, unallocated discount, negative discount,
FACT/no instruction/no money event and immutable original report, plus routine
COLLECT760000. Extraction/pipeline focused regressions also run. No provider calls.

Full backend: 1044PASS/7FAIL (1051total).

Six known baseline failures remain (five employee-return date fixtures and missing
legacy case06 organization.json); no guard relaxed/xfail added. Additional demo
context regression expected fixed16/10 but user changed live demo context to17/10
before VAT work. Reproduced independently with pre-VAT HEAD code in isolated source
snapshot; context edit retained. Full suite is not GREEN.

Failures:
- `tests.integration.test_employee_return_draft_api::test_employee_return_upload_is_durable_but_does_not_record_R`
- `tests.integration.test_employee_return_draft_api::test_accountant_confirmation_records_one_instruction_bound_return`
- `tests.integration.test_employee_return_draft_api::test_pending_second_return_cannot_confirm_after_collect_is_fulfilled`
- `tests.integration.test_employee_return_draft_api::test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction`
- `tests.integration.test_employee_return_draft_api::test_overpaid_return_is_recorded_but_raises_a_specific_blocker`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]`
- `tests.integration.test_uc03_demo_contexts::test_shared_app_has_all25_advances_with_independent_history_after_restart`

## Limits

No LIVE/OCR/LLM quality claim, UI/browser NOT_RUN (no UI change), no user-DB edits,
server restart, commit, push or deployment. Existing read results are not forcibly
reprocessed. Ambiguous source totals remain blocked. Location checks depend on
available source refs, not proof of complete OCR coverage. Unsupported alternative
cost exclusion workflow stays out of main; requires separate policy/design task.

Discovery: CodeGraph queried main gate/callers; coverage/generation API unavailable,
worktree stale/unknown. Exact source fallback used for changed files. Consumers:
pipeline, settlement draft/digital intake, admission and workflow commit tests.

## Follow-up authorized context synchronization and commit

User requested commit and25-case audit for17/10. Updated generator/50contexts/witnesses/manifest and independent test horizon with next-day rejection; extra date assertion failure resolved by authorized fixture update, not disabling expiry.
Full backend cuối: 1046PASS/6FAIL (1052total); đúng6tên lỗi baseline trước sửa thuế/context. Không thêm xfail hoặc nới guard. Test context cũ đã được cập nhật theo ngày fixture được người dùng yêu cầu, có đối chứng hết hạn ngày18/10.
No inadmissibility policy/dependency from worktree merged; no LIVE/UI/restart/deploy.

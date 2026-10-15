# TC01 payer question in the user's default web runtime

Read-only diagnosis on final `38d8da3a` (clean at inspection). Backend port 8000/PID 29097 started at 23:00:16 +07:00 with `scripts/dev.py --host 127.0.0.1 --port 8000`, no custom context argument. No application change, provider call, session creation, DB write, reset or restart performed.

## Exact case and evidence

- Case `case:f9cec6607ff0ceeab9eb`, WAITING, version 3, employee `employee:employee-a`, profile WORK_EXPENSE.
- Activity remains `activity:proposed:e363da2a5c7547419d599ea4a9384fd2`; declaration has `confirmed_activity_id=null`.
- Attached source digests match original TC01 exactly: report `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c`; invoice `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019`.
- Both documents CLEAR. Paper claimant NGUYỄN MINH AN, declared advance 4m, total 3.24m, row invoice reference 00000101. Invoice buyer company CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH, no buyer person, total 3.24m.
- Open issues: budget:B (org-data), expense:00000101:employee_paid (employee), ledger:coverage (accountant). The screenshot shows only the employee's issue, not the whole case's blockers.
- No recorded money event for this root.

## Runtime cause

Default `data/demo/company-context.json` is still company "Công ty Demo" and account name "Nguyễn Văn A", with seven travel activities. Its imported snapshot has company_name=null, empty ledger and no coverage. It does not contain this proposed WORK_EXPENSE activity. `load_context` therefore returns None, and `build_evidence_assessment_input` falls back to organization_id only.

`_invoice_binding` cannot find the employee identity in this fallback, so it returns false before checking composite company + claimant + row binding. The invoice-scoped fallback question asks the employee to confirm paid amount. The question format/key has changed from the old generic payer issue; it does not prove the old answer-loop defect persists.

Two separate gaps exist: the default demo data does not represent TC01, and global organization/person identity is coupled to finding an activity-scoped snapshot. For an unlinked dossier, the latter also masks the actual account/claimant mismatch and produces a payer question instead of identifying the missing/mismatched organizational identity.

## Pure counterfactual

Reused the stored LIVE ReadResult. Runtime fallback gives invoice_bound=false and E/A/S UNKNOWN. An explicitly hypothetical organization with only matching company/person identity (no budget, grants, ledger or coverage) gives invoice_bound=true and E=3.24m KNOWN, while A/S remain UNKNOWN. This isolates invoice-binding context as the payer-question trigger; it does not establish actual advance or permit COLLECT 760k.

Probe: `.runtime/tc01-current-question-20261014/identity-probe.json`.

## Next work

Provide a portable, validated TC01 organizational fixture with the correct company/account identity, and keep history/B/rights independent. Read global tenant identity even for a proposed activity; load activity budget/history only after a justified link or appropriate responsible recording. Missing organization data must go to the responsible organization-data owner, not be converted into a generic employee payment declaration. Verify standalone TC01 without advance stays blocked on A/history, and the fully evidenced/bound variant reaches the previously agreed financial result. Do not auto-link by purpose/amount, copy paper advance into ledger, fill a future coverage without a responsible witness, or suppress issues to force a pass.

This inspection used CodeGraph current snippets (222 files, 3927 nodes, 12175 edges; earlier-engine warning), scoped SQLite read-only inspection and a pure admission/projection probe. Index-coverage tool unavailable; coverage UNKNOWN. A new LIVE/browser run was NOT_RUN.

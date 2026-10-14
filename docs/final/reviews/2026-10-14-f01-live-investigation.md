# F01 — investigation of the three FACT questions

User-authorized investigation and LIVE reproduction, 14/10/2026. No application,
policy, input corpus or original runtime DB changed. No subagents, commit or push.

## Scope and tested revision

- Branch `final`, HEAD `0be840c48188b27718df499100a144dd85ecec36`.
- Python 3.12.13 via `rtk proxy uv run --no-sync`.
- CodeGraph Verify: project InvoiceReferee, 156 files, index reports up to date,
  earlier-engine warning. Codebase Memory generation/coverage tools unavailable;
  coverage UNKNOWN. Exact source excerpts for relevant elided functions were read.
- Original case: `case:5aa9e240c82bba079c21`, matches the user's audit timestamps
  and both PDF SHA256 hashes. Original SQLite opened read-only.
- Evidence folder: `.runtime/f01-live-investigation/` (ignored private data).

## Original runtime, not inferred from the screenshot

The original run is LIVE/LIVE_READ. Both documents have profile CLEAR. OCR raw
artifacts preserve the employee's payment declaration and Nguyễn An. Extraction
preserves name, destination, trip dates, purpose, declared advance 4m, printed
return 760k, total 3.24m. The exact invoice reference IR26101001 yields AUTO_LINK
score 1. Therefore these three FACT cards are not caused by failing to OCR the
source amount, name or invoice link.

The case belongs to `tenant:demo`, `employee:employee-a`, a proposed activity
`activity:proposed:5e2c96c3ba154870a685416f02eba24c` named `a`. Imported people map
that employee to Nguyễn Văn A. `context_snapshots`, `case_confirmations` and
`case_declarations` are empty. The imported context is the default demo context,
not the pilot's `tenant:uc03-pilot` / `activity:uc03-f01` context.

The original conclusion records T=3.24m, E/C/A/P/R/S UNKNOWN, but unpaid KNOWN
3.24m. The three open issues are budget:B, expense:payer and ledger:coverage.

## LIVE reproduction

Executed:

```text
rtk proxy uv run --no-sync python .runtime/f01-live-investigation/run.py
```

Diagnostic DB `diagnostic-v3.sqlite`; original DB untouched. Used unchanged F01
PDFs, typed pilot organization context imported with `import_company_context`,
and EmployeePaidClaim via the existing Submit command. No gold read; no fabricated
OCR/facts. File refs use the command's current filename+digest convention.

Mistral `mistral-ocr-latest`: two real calls, 2.40s/3.72s. Configured LLM
`qwen/qwen3.7-flash:free`: three real calls, one classification batch and two
extractions, 8.63s/19.71s/23.34s. No confidence-review/suggestion-resolution call
occurred in this reproduction. Token usage not captured by current client.

Exit 0: READY_TO_EXECUTE, zero issues, COLLECT760000, T=E3240000, C0, A4000000,
P=R0, S=-760000, unpaid0; declaration basis retained. This is provider/workflow
integration evidence with SIMULATED organization/claim and no actual-money execution,
HTTP/browser check or full-suite run. It is not bank verification or complete E2E.

The harness requested historical clock10/10/2026 18:00+07 for fixture compatibility.
However `_build_assessment_input` does not pass workflow clock into
`build_evidence_assessment_input`, so assessment uses actual datetime.now(UTC).
Consequently the observed happy-path result is additionally a counterexample for
stale coverage acceptance, not proof that historical/current timing gates work.
Separate pure admission/reconciliation probes pass an explicit as_of to distinguish
that issue. No source or witness date was extended.

Two harness setup attempts failed before any provider calls: Python dict validation
of strict tuple fields required model_validate_json; a resolved source ID was
rejected because the current claim command accepts filename+digest. Attempts kept
as diagnostic.sqlite/diagnostic-v2.sqlite; final successful run is v3.

## Confirmed findings

### 1. Default web startup and typed finance context use incompatible import paths

`runtime.py:53` calls import_demo_context, which writes relational demo tables but
does not create a context_snapshots row. `evidence_assessment.py:97` loads only the
typed snapshot; absent snapshot becomes empty OrganizationContext at line99.
Thus catalog budget/grants and typed assessment can disagree even when a user
selects an existing demo activity. In the actual case the proposed activity also
genuinely has no approved budget. Two PDFs cannot establish organizational budget
or completed company ledger history.

### 2. Employee declaration exists in OCR but does not enter structured declaration handling

SETTLEMENT_FORM allowed_fields (`document_profiles.py:77`) has no payment-declaration
field. The original typed report has neither a paid statement field nor a
confirmation. `admission.py:210` builds paid claims exclusively from stored
confirmations. A responsible UI confirmation may legitimately still be required,
but the UI currently asks a generic missing-payer question instead of presenting
the already-read declaration for confirmation and identity binding.

### 3. UI paid-claim source refs are rejected by the real upload convention

`frontend/src/features/intake.tsx:80` chooses the first source, and line81 uses the
last segment of storage_key as filename. API upload keys end in opaque source IDs.
`service.py:1135` resolves claims by the actual case_sources.filename+digest.

Reconstructed the exact frontend payload against a SQLite backup of the original
case. Existing command rejects it with UnsupportedCommandError: source:c2be... does
not match the uploaded file 02-hoa-don-dich-vu.pdf. Result in ui-claim-result.json.
This is independent of OCR quality. The placeholder quote “nhân viên xác nhận” is
also not an exact source quote; repair should use real evidence refs or a typed
declaration record reference, not invent a source quotation.

### 4. Unknown payment becomes known unpaid amount

`reconciliation/finance.py:81` initializes gross_paid0; absent admitted payment stays
an empty list, even when payer/eligibility are UNKNOWN. Line107 then returns
unpaid=KNOWN(T-gross_paid). Reproduced with real LIVE report, correct context and no
claim: E UNKNOWN while unpaid KNOWN3240000. Missing evidence of payment cannot
establish a supplier debt. This is a backend projection error, not just wording.

### 5. Name conflict is not a blocking material binding check

Actual OCR/facts name Nguyễn An, account context name Nguyễn Văn A, but original
issues do not mention the mismatch. Pure probe with correct other inputs and
account name changed to Nguyễn Văn A still yields COLLECT760000/no issues.
Admission reads declared_name in the report but never checks it against the
responsible claimant context. A mismatch requires confirmation/correction/alias
evidence; it must not be ignored or interpreted as fraud automatically.

### 6. Coverage presence is treated as sufficient; freshness and workflow clock not enforced

`admission.py:213` accepts coverage presence for known A. `finance.py:94` similarly
accepts any non-None coverage for A/P/R. An explicit probe as_of14Oct with coverage
through10Oct still gives COLLECT760000/no issues, contrary to contract§3 and planA3.
The workflow also omits its clock parameter at service.py:1799. Correcting one
without the other is insufficient.

### Additional matching inconsistency (observed; not the three-question trigger)

Both original and new reports return SET_PAPER_UNMATCHED_001 UNRESOLVED referencing
the settlement form itself even though its invoice row has AUTO_LINK1.0/PASS.
Pipeline passes tuple(documents), including the paper, to match_paper_evidence.
Admission does not consume match_findings/row matches as material gates. The
current F01 result is not blocked by this finding. It needs a targeted matcher/
admission check rather than simply suppressing all unresolved findings.

## Diagnostic probes on the actual LIVE report

Results saved as probes.json; no further network calls:

| Change | Observed | Expected implication |
|---|---|---|
| Correct context, no paid claim | FACT payer; unpaid KNOWN3.24m | Payer unresolved valid; unpaid should stay unresolved |
| Correct context+claim, explicit historical as_of | COLLECT760k/no issues | Happy-path money math works |
| Same inputs, as_of14Oct/coverage10Oct | COLLECT760k/no issues | Must block until adequate historical coverage |
| Same inputs, account Nguyễn Văn A/paper Nguyễn An | COLLECT760k/no issues | Must resolve claimant binding mismatch |
| Reconstruct real UI paid-claim payload on DB backup | UnsupportedCommandError | Frontend/backend ref contract incompatible |

## Recommended repair order

1. Fix false-known unpaid, claimant/activity binding and coverage/time validation.
   Add regression cases using this captured report; no policy relaxation.
2. Make dev/API startup import the same typed organization context that admission
   reads; reconcile catalog/read context per tenant/activity and support pilot setup.
3. Read the PDF payment declaration as a proposal, prefill its invoice/amount/source
   and request server-bound responsible confirmation. Repair UI ref construction.
4. Resolve false unmatched-paper finding and enforce actual material matching gates.
5. Re-run F01 LIVE through real HTTP/UI, including missing context, wrong claimant,
   stale history and recorded completion. A green unit suite/happy-path number
   does not establish these controls.

No repair performed in this investigation. No database reset is recommended as
a solution to these source/wiring errors.

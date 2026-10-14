# Independent review — UC03 25-case mapping into `final`

Date: 2026-10-14  
Scope: read-only review of the 25-case UC03 mapping and corrected manifest. No runtime, test, LIVE/provider call, data regeneration, source/finance implementation, commit, or publish was performed.  
Write set used by this review: this file only.

## Verdict

**NEEDS_REVISION** before the mapping is used to generate `expected-business` or a finance/admissibility data plan.

The substantive case reasoning is mostly sound and materially better than copying the Hoangha legacy labels. The blocking issue is the mapping schema: `finance_target.outcome` and one scalar `finance_target.owner` mix terminal money outcome, current issue type, future dependent issue, question owner, and execution actor. That loses contract semantics for routine cases and chained FACT → POLICY/AUTHORITY cases. TC07 also treats `amount_words` criticality as still open even though the accepted contract already pins it as critical; the current implementation is the drifting artifact, not the contract.

After those two corrections are made, the mapping is suitable to become the authoring input for the next data/finance plan. The raw corpus should remain reference evidence and the planned `UC03-Fxx` variants should remain separately versioned sources with provenance.

## Evidence and review boundary

- Review object: `data/tham-khao/uc-03/CASE_MAPPING_FINAL.md`, `final-case-mapping.json`, corrected `manifest.json`, all 25 legacy `expected.json`, accepted design §§1–4/14–15, contracts §§3–5/12, and selected cached source-text inspections for the material counterexamples.
- The mapping records `final_head_at_start=51444fec845239b0394d2fa52d48b02de729f384`. During this independent review the branch had advanced to `68f37cd7f4c678ba68cb4848a027416252c79021` because another actor was active. No concurrent source changes were modified by this reviewer.
- `final-case-mapping.json` contains exactly **25 cases / 65 inputs / 65 unique paths**. All 65 files exist and their current SHA-256 matches the mapping entry.
- Against `.runtime/uc03-mapping-review/pre-edit-hashes.json`, **156/156** tracked raw case artifacts other than `manifest.json` and `readme.md` are unchanged. This covers the 65 PDFs plus legacy DOCX/`expected.json` artifacts. The planned `UC03-F01..F25` sources have not been created.
- `manifest.json` diff changes only the 25 `folder` values from old accented names to the actual lowercase hyphenated folders. Legacy decision/rule/status metadata is preserved. This is the correct manifest repair.
- TC19 and TC20 legacy metadata drift is real and is correctly recorded rather than silently normalized: TC19 manifest rule differs from case gold; TC20 manifest decision/rule differs from case gold.
- Current source still enforces the evidence-only boundary: `src/invoice_referee/workflow/service.py:523-534` publishes `EVIDENCE_READY`, and `_assess_and_commit` returns when the evidence reader is wired at `src/invoice_referee/workflow/service.py:1708-1729`. Therefore every READY/WAITING/AUTHORITY/COLLECT/PAY target in this mapping is future finance/admissibility design, not a claim about a current LIVE/REPLAY run. This matches design §15 and contracts §12.5 (`docs/final/ARCHITECTURE_AND_EVALUATION.md:531`, `docs/final/IMPLEMENTATION_CONTRACTS.md:620`).
- CodeGraph returned current on-disk source for the material code checks. `check_index_coverage`/Codebase Memory coverage tooling was not exposed in this review, so graph coverage remains **UNKNOWN**. No exhaustive negative code claim relies on the graph.
- Cached PDF native text was used only for authoring audit. No runtime OCR/provider call or full-corpus visual QA was performed.

## Blocking findings

### P1 — `finance_target.outcome` + scalar `owner` loses the final issue contract

Evidence: `final-case-mapping.json` stores one `outcome` and one `owner` per case, for example TC01 `COLLECT/EMPLOYEE` (`:53-55`), TC13 `EXCLUDED_COLLECT_ADVANCE/ACCOUNTANT` (`:521-523`), TC20 `FACT_THEN_POLICY_IF_RULE/EMPLOYEE` (`:848-850`), TC21 `FACT_THEN_AUTHORITY/EMPLOYEE` (`:892-894`) and TC22 the same pattern (`:936-938`).

This is not expressive enough for the accepted contract:

- Routine cases have **no business issue/question owner** once their facts and authority are complete. The accountant may later execute a valid instruction, but execution actor is not issue owner. Design §4 separates employee, accountant, and authorized decision-maker responsibilities and says a question must name the correct person (`docs/final/ARCHITECTURE_AND_EVALUATION.md:127-145`).
- FACT must come first when POLICY/AUTHORITY depends on an unresolved fact (`docs/final/ARCHITECTURE_AND_EVALUATION.md:142`). One scalar owner cannot represent TC20/21/22 correctly after the first issue is resolved.
- TC13's clear-personal happy path does not require a policy question at all. Once A/P/R coverage is verified, the system excludes the personal expense and computes the collection obligation. `ACCOUNTANT` can be the actor who verified money or later records execution, but should not be frozen as a standing issue owner.
- TC12 should only ask an accountant if prior usage/scope is actually unresolved. If the usage registry already establishes canonical ownership, duplicate prevention is a system/business-state result, not a mandatory accountant question.

**Required revision:** keep the current prose, but change the authoring JSON shape before downstream gold generation. A minimum safe shape is:

```text
preconditions
issue_sequence[]:
  kind: FACT | POLICY | AUTHORITY
  owner
  field_or_rule
  depends_on[]
projection_if_known:
  E, A, P, R, S
allowed_effect_after_gates:
  direction: PAY | COLLECT | NONE
  amount
expected_state_before_resolution
post_execution_state
```

For routine TC01/02/03, `issue_sequence` should be empty once common preconditions are satisfied. For TC20, encode employee FACT first and an approver POLICY issue only if the operative rule actually requires an exception. For TC21/22, encode employee FACT first, then AUTHORITY only after the amount is known. Do not use the execution accountant as a question owner.

### P1 — TC07 leaves an accepted contract decision falsely open

TC07 says: “Nếu code coi `amount_words` non-critical thì phải review contract trước khi freeze oracle” (`CASE_MAPPING_FINAL.md:135` onward). The contract already made this decision: the `SETTLEMENT_FORM` criticality matrix must include `amount_words` (`docs/final/IMPLEMENTATION_CONTRACTS.md:577-579`).

Current source is the drifting implementation: `src/invoice_referee/evidence/document_profiles.py:55-75` marks `amount_words` as `NON_CRITICAL`, while the contract says it is critical.

**Required revision:** TC07 should be anchored to the accepted contract, not to current code behavior. Record the expected final evidence/business condition as a blocking inconsistency/FACT under the contract and add an explicit `implementation_dependency` or `implementation_drift` note saying the current profile must be brought back into contract before this case can serve as a runtime oracle. Do not reopen the contract merely to match the present source.

### P1 — Above-8m cases need the FACT paid-basis gate explicitly before AUTHORITY

Q32 allows employee confirmation + service evidence only inside both automatic thresholds. Contracts §3 says an employee-paid candidate above the threshold needs payment proof or valid financial confirmation (`docs/final/IMPLEMENTATION_CONTRACTS.md:50`), and §5 explicitly says “Missing payer and E maybe above8 → FACT first, AUTHORITY if after verification E>8” (`docs/final/IMPLEMENTATION_CONTRACTS.md:155`).

The mapping prose understands this, but the JSON's single `outcome=AUTHORITY` can erase the ordering for TC04/14/16/23, especially TC16 (`final-case-mapping.json:648-650`) and TC23 (`:980-982`). The same sequencing problem exists in TC21/22 after their missing/allocation facts are repaired.

**Required revision:** encode the paid-basis precondition or FACT issue separately from the authority issue. `AUTHORITY` is a valid final target only after the variant/context supplies an admissible employee-paid basis and E is known. This is data-contract work; it does not require changing finance source in this review.

## Case-level disposition

| Case | Review | Required disposition before data/gold generation |
| --- | --- | --- |
| TC01 | OK with schema revision | Core arithmetic is correct: E3.240m/A4m/P0/R0 ⇒ S=-760k ⇒ COLLECT. Once facts are complete there is no issue owner; accountant execution is a separate step. |
| TC02 | OK with schema revision | E5.4m/A5m ⇒ S=+400k ⇒ PAY. Original printer source remains evidence-only; the lodging/travel variant must change the source, not only context. |
| TC03 | OK with schema revision | E=A4.32m ⇒ S=0, BALANCED/SETTLED with no zero-value instruction. Missing history coverage belongs to accountant FACT if present; routine happy path has no question owner. |
| TC04 | CONDITIONAL | 83.6m is outside automatic recognition and beyond demo 20m. Require admissible paid basis first; then higher authority. Do not let the small S=-1.4m bypass E authority. |
| TC05 | OK | Preserve all three values 3.0m / 3.24m / 3.5m as conflicting facts. No model-confidence choice and no instruction. |
| TC06 | OK | Printed return 700k is not actual R. Arithmetic 760k is a derived reference only after E/A are verified. |
| TC07 | REVISION REQUIRED | Contract already makes `amount_words` critical; current implementation is drift. Freeze against the contract and record the implementation dependency. |
| TC08 | OK | Exact reference can link documents but does not resolve 3.5m vs 3.24m amount conflict. FACT first. |
| TC09 | OK | Buyer identity contradiction is a binding FACT. Do not import the Hoangha tax rule as a final POLICY by default. |
| TC10 | HOLD / correctly not frozen | Current final contract does not establish buyer tax code as a required E_INVOICE field; current source requires issuer/number/date/total only (`src/invoice_referee/evidence/document_profiles.py:98-105`). Keep this case out of financial oracle until an operative profile/admissibility rule is accepted. |
| TC11 | OK | 5.0m + 0.4m ≠ printed invoice total 5.5m. Preserve literal source; do not auto-repair to 5.4m. |
| TC12 | OK with schema revision | Correctly model economic reuse/usage, not fraud and not byte duplication alone. Prior usage must be runtime context. Ask accountant only if usage/scope is actually unresolved. |
| TC13 | REVISION REQUIRED only for owner/schema | Source explicitly says personal after-hours purchase. Correct final arithmetic is E=0, A=3m, P=R=0 ⇒ COLLECT 3m, not 840k. No POLICY approval is required for the clear exclusion path. |
| TC14 | CONDITIONAL | E=121m/A120m gives arithmetic S=+1m, but recognition E is far above both automatic and demo authority. Paid basis must be verified before authority resolution. |
| TC15 | OK | Equal amount is insufficient; content/reference mismatch remains FACT binding. |
| TC16 | REVISION REQUIRED for issue ordering | 4.32+5.4+0.54=10.26m; A12m ⇒ S=-1.74m. Because E>8m, employee Q32 confirmation alone is insufficient. Verify paid basis first, then route AUTHORITY. |
| TC17 | OK / conditional | 3.24+2.16+0.2=5.6m; A6m ⇒ S=-400k only after service role, payer and activity binding are admissible. Do not make “not VAT invoice” an automatic POLICY issue. |
| TC18 | OK | The 1.5m acceptance + bank proof support one service obligation, not two expenses. Bank text names employee as payer but company as recipient, so payee/binding is genuinely unresolved. Happy variant must repair source/payee evidence, not infer it from context. |
| TC19 | OK | Missing 800k service evidence blocks the affected total. Do not treat missing as zero or collect 1.3m from the two known invoices only. Legacy manifest-vs-gold rule drift is correctly preserved. |
| TC20 | REVISION REQUIRED for issue chain/owner | The “parking lot issued no receipt” note is a declaration/reason, not proof of service/value and not an exemption. Employee FACT first; POLICY/exception owner only after facts are sufficient and an operative rule requires it. Legacy drift is correctly preserved. |
| TC21 | REVISION REQUIRED for issue chain | Missing declared invoice is employee FACT first. If the repaired E is 14.04m, AUTHORITY follows because E>8m. One scalar `owner=EMPLOYEE` is insufficient for both stages. |
| TC22 | REVISION REQUIRED for issue chain | Over-allocation 7.56m against a 5.4m invoice is FACT first. Recompute E after repair; only then apply the >8m authority gate if E remains above 8m. |
| TC23 | REVISION REQUIRED for issue ordering | Allocation 2.16+1.08=3.24m is sound; total E=8.64m/A9m ⇒ S=-360k. E>8m still requires admissible paid basis and AUTHORITY despite small S. |
| TC24 | OK | Unreferenced source must not be silently discarded. Even though its content says personal, its relation to the submitted root is initially unresolved; confirm relevance, then quarantine/exclude with reason. If confirmed unrelated/personal, E2.7m/A3m ⇒ COLLECT 300k. |
| TC25 | OK | Claim 900k vs receipt 700k is a true FACT conflict. Do not freeze either printed COLLECT 860k (claim total 4.14m) or repaired COLLECT 1.06m (if 700k were accepted) before correction/recheck. |

## Numerical checks that matter

These arithmetic results are safe only under the stated factual/admissibility preconditions; they do not turn unresolved source values into known financial facts.

| Case | Check |
| --- | --- |
| TC01 | 3.240m − 4.000m = **−0.760m** ⇒ COLLECT 760k |
| TC02 | 5.400m − 5.000m = **+0.400m** ⇒ PAY 400k |
| TC03 | 4.320m − 4.320m = **0** ⇒ BALANCED |
| TC04 | 83.600m − 85.000m = **−1.400m**, but E authority blocks instruction |
| TC13 | 0 − 3.000m = **−3.000m** after clear personal exclusion |
| TC14 | 121.000m − 120.000m = **+1.000m**, but E authority blocks instruction |
| TC16 | 10.260m − 12.000m = **−1.740m**, subject to paid basis + authority |
| TC17 | 5.600m − 6.000m = **−0.400m**, conditional on admissibility |
| TC18 | 4.200m − 5.000m = **−0.800m** on the repaired happy variant, not on the ambiguous current bank payee |
| TC23 | 8.640m − 9.000m = **−0.360m**, subject to paid basis + authority |
| TC24 | 2.700m − 3.000m = **−0.300m** only after the extra invoice is responsibly confirmed unrelated/personal |
| TC25 | Claim total 4.140m would imply −860k; substituting the 700k receipt would imply 3.940m − 5.000m = **−1.060m**. The conflict must remain unresolved until corrected. |

## What is already correct and should be preserved

1. **Do not copy Hoangha decision labels into final.** The mapping correctly converts business meaning, not labels. TC13, TC16, TC18, TC20, TC23 and TC25 are the strongest examples.
2. **Keep mapping/gold out of runtime input.** `authoring_only=true`, `runtime_must_not_read_this_file=true`, and all 25 `ready_for_financial_oracle=false` are correct safeguards.
3. **Keep raw sources immutable.** Current hash checks support this. Create new `UC03-Fxx` sources with new digest/provenance rather than editing the 65 reference PDFs in place.
4. **Preserve final scope.** Office equipment/server/material-purchase originals should remain evidence/reference cases unless a source variant genuinely rewrites them into the accepted employee-paid domestic-travel scope. Merely adding travel context is insufficient (`ARCHITECTURE_AND_EVALUATION.md:15-31`, `:54`).
5. **Preserve Q32 limits.** Employee responsible confirmation is sufficient only inside E<=8m and abs(S)<=4m when other conditions are clean (`IMPLEMENTATION_CONTRACTS.md:50`, design `:487` onward).
6. **Preserve oracle isolation.** Legacy `expected.json`, mapping JSON, and future expected-business files belong to evaluator/authoring paths only. Context/activity/budget/grants/ledger/coverage supplied to runtime must be independently authored inputs with provenance.
7. **Preserve the current evidence/finance boundary.** Do not remove the `EVIDENCE_READY` guard merely to make the 25 cases produce money decisions. The next plan must connect evidence/admissibility into `AssessmentInput` explicitly.

## Minimum closure for `READY_FOR_DATA_PLAN`

The parent/integrator can close this review without touching source/finance code by revising only the mapping artifacts so that:

1. `finance_target` separates issue sequence/owners from projection, allowed effect and post-execution state.
2. TC07 states the accepted `amount_words` criticality and records current implementation drift as a dependency.
3. TC04/14/16/23 and TC21/22 explicitly encode FACT paid-basis/value resolution before dependent AUTHORITY where applicable.
4. TC10 remains intentionally non-oracle until a real profile/admissibility requirement is accepted; no buyer-tax rule is invented in data.
5. Routine cases do not carry a fake question owner; execution actor is represented separately if needed.
6. The 25 IDs, 65 immutable source paths/hashes, TC19/20 legacy drift, authoring-only flags and planned source-variant provenance remain unchanged.

Once those edits are made, my expected verdict is **READY_FOR_DATA_PLAN**; finance source implementation and data regeneration can remain a separate authorized step.

## Closure addendum — 14/10/2026

Closure check scope was intentionally limited to the three P1 findings above. I did not re-open broader case review, run product/runtime tests, call LIVE/provider services, or inspect unrelated source changes.

**Updated verdict: `READY_FOR_DATA_PLAN`.** The v2 mapping closes all three blocking P1 findings.

1. **Issue/outcome/owner separation — CLOSED.** `final-case-mapping.json` no longer uses one scalar outcome/owner as the oracle. It now separates descriptive `scenario_goal`, conditional `issue_sequence`, `projection_if_known`, `allowed_effect_after_gates`, execution actor and post-execution state. TC01/02/03 and clear-personal TC13 have `issue_sequence=[]`; TC12 only creates the usage FACT when prior usage/scope is unverified; TC20 uses EMPLOYEE FACT then AUTHORIZED_APPROVER POLICY only when an effective exception rule actually requires it. Dependency semantics explicitly allow an already-verified precondition to satisfy a dependency without creating a phantom issue.

2. **TC07 `amount_words` contract — CLOSED.** TC07 now treats the words-vs-digits conflict as a blocking FACT under the accepted contract and records the current `NON_CRITICAL` implementation as `implementation_dependency`/code drift. It no longer reopens the contract to match current source behavior.

3. **Paid-basis FACT before dependent AUTHORITY — CLOSED.** TC04/14/16/23 encode ACCOUNTANT paid-basis FACT when the admissible basis is missing, followed by AUTHORITY only after E is known above the threshold. TC21/22 correctly add their source/allocation FACT first, then paid-basis FACT if needed, then AUTHORITY. Owners are correct for the threshold path: `HIGHER_AUTHORITY` for TC04/14 beyond demo 20m; `AUTHORIZED_APPROVER` for TC16/21/22/23 where the final amount remains within the demo grant ceiling.

The special semantics requested for gold generation are also correct:

- unresolved FACT/POLICY/AUTHORITY cases use `allowed_effect_after_gates.direction="NONE"` with `amount_vnd=null`; this means **no current financial effect**, not BALANCED;
- TC03 is the only reviewed balanced case with `direction="NONE"`, `amount_vnd=0`, `instruction_count=0`, and its balanced condition explicitly requires the gates to be complete;
- projected E/A/P/R/S values are conditional authoring projections, not known values from the original PDFs;
- any execution actor recorded on an unresolved case is the future actor after the gates resolve; the current effect remains NONE/null;
- all 25 cases still have `ready_for_financial_oracle=false`, so scenario goals and possible post-resolution effects are not current executable gold.

No further correction is required for these three P1 findings before the parent proceeds to the data/finance planning step. The initial findings above remain as historical review evidence; this addendum records their closure rather than rewriting them.

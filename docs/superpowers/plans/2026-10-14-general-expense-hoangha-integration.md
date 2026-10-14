# General Employee-Expense Settlement Implementation Plan

> **For agentic workers:** Use the repository's AGENTS.md, executing-plans or
> equivalent native implementation one task at a time. RED → implement → GREEN;
> record commands and outcomes. Another agent currently owns shared invoice/advance
> files. Start shared-file changes only after its handoff. No subagent review was
> requested for this plan. Do not commit/push/reset without user authorization.

**Goal:** Accept original Hoangha TC01–TC25 in the appropriate final business
scope, retain final's finance/history/authority/control rules, and make the
employee-paid workflow testable on raw PDF/array input without inventing trips.

**Architecture:** Extend one CaseWorkflow and its typed evidence→admission→policy→
Reconciler path. Use a server-owned business activity profile and per-expense category.
Adapt Hoangha's document taxonomy, matching and common paper structure, not its
separate DB/lifecycle/100m grants or paper-as-actual-advance shortcut.

**Tech Stack:** Existing Python3.12/uv, Pydantic/FastAPI/SQLite/Mistral/X-Kiro,
React/TypeScript. Keep current provider interfaces and frontend stack; no new
framework/broker.

**Spec:** [general-expense-policy-and-form](../specs/2026-10-14-general-expense-policy-and-form.md),
[v3 mapping](../../../data/tham-khao/uc-03/final-case-mapping-v3.json),
final contracts§3–6/§10/§12, design§1–4/§14–15, ADR0006/0007.

## Global Constraints

- User-approved Hoangha rules: work/client meal ≤5,000,000 VND per canonical expense;
  taxi/ride ≤2,000,000 VND per canonical expense; submission within30 calendar days
  of established expense date; personal expense not recognized as business expense.
- Final authority remains system-recognize E≤8,000,000, system-issue abs(S)≤4,000,000,
  demo approver ≤20,000,000 VND per granted action/scope. B is independent.
  Do not copy Hoangha's100m authority or force regular accountant approval.
- Employee-paid only, one claimant/activity/VND. No corporate supplier payment,
  foreign currency, multi-claimant allocation or asset/inventory lifecycle.
- Original65 Hoangha PDFs/DOCXs and old expected.json remain byte-identical. Old
  labels are comparison metadata; author independent final input/context/gold.
- All accepted PDFs/images pass OCR; model fields are proposals with source refs.
  No native-PDF text bypass at runtime. Gold and mapping do not enter app/model.
- Actual A/P/R and zero history require scoped completed money/witness/coverage.
  Printed advance, printed return, approval and a signed-looking PDF are not actual
  events. Never fabricate dates/coverage/grants to make a case AUTO.
- Employee-paid demo invoice basis is the user's accepted policy, labeled as such.
  For original company-buyer-only invoice, a clear paper claimant plus source link
  plus organization identity can bind it when nothing contradicts; a mismatching
  natural person or explicit other payer stays FACT/out-of-scope. Source role still
  determines whether a ticket/receipt is original expense or supporting evidence.
- TC20: employee reason in row → FACT on unestablished service/value/payment →
  exact missing-evidence POLICY/EXCEPT_POLICY after facts. No extra explanation UI.
- `OTHER`/unclassified category is not an automatic unlimited PASS. Invoice amount
  caps apply to one economic expense, not arbitrary subdivisions of its paper row.
- Case/provider/control read-set must remain current at commit. Stop, duplicate,
  reversal, pending/unknown execution and overpay protections remain intact.
- The current shared-file implementer finishes its gate before this integrator
  edits service/schema/domain/frontend/contract/UC03 pilot files. Re-read current
  checkout after handoff. Preserve concurrent files including frontend UI work.

## Review Focus

1. TC01 original form has no trip dates and invoice names the company rather than
   buyer-person: route only with composite claimant/company/activity binding (Task2/4).
2. TC20 reason is not proof: no partial issue until FACT then exact POLICY decision
   and independent paid/money basis (Task5).
3. TC23 split one invoice over two rows: accept allocations totaling source3.24m,
   but never bypass category cap or system-recognize8m on total E8.64m (Task4/6).
4. TC18 acceptance+bank file: do not double-count service; respect literal payer/
   payee, no automatic employee-paid conclusion from bank ambiguity (Task4/6).
5. TC14 E121m, S+1m: small net does not waive recognition authority and demo20m;
   TC13 personal E0 still settles actual A (Task4/6).

## File map and interface decisions

One integrator owns shared code. Keep domain category/policy interface small:

- `domain/finance.py`: extend Expense with source-backed category/status without
  reusing payment_state; preserve existing constructors/explicit STUB fixtures.
- `domain/policy.py` and `workflow/context_records.py`: add versioned category
  policy data under scoped organization context and preserve digest/provenance.
  No process-wide unversioned mutable singleton. Implement same-row/source reader
  for category config used by both UI view and decision.
- `workflow/service.py` + additive schema: server-owned activity profile/catalog,
  proposed activity remains unauthorised until granted. No client-supplied grant.
- `evidence/document_profiles.py`, `document_validity.py`, extraction prompt/type
  vocabulary: common paper fields with TRAVEL-only refinements. Hoangha original
  invoice/receipt/ticket/supporting role taxonomy stays type-specific.
- `reconciliation/admission.py`: build economic expense/allocations and category
  with literal refs; conflicting source/claimed values remain unresolved.
- `reconciliation/policy.py`: append category/date and missing-evidence decisions
  to existing FACT/POLICY/AUTHORITY outcome; Reconciler remains financial owner.
- `domain/issues.py`/commands and current issue/decision persistence only as needed:
  typed reason/exception scoped to rule, expense, basis and actor/grant. Server
  owns identity and effective time. Do not invent a second approval workflow.
- `evaluation/packets.py`/runner/scorer and source corpus helpers: make v3 packets
  executable and independent gold; `frontend/src/features/intake.tsx`, questions,
  dossier and API views show activity profile/category/evidence and current issue.

Final method names/signatures should be selected against the post-handoff checkout.
Keep one consumer `build_evidence_assessment_input(...)->AssessmentInput`; do not
copy `process_settlement.py` or create a parallel policy route. A new category
evaluation helper may be pure but must return existing BusinessIssue/decision types.

## T0 — Establish fresh write ownership and baseline

**Files:** read-only AGENTS, status, contracts, current diff, CodeGraph coverage;
task notes under ignored `.runtime/general-expense/`.

- [ ] Verify current HEAD/branch/status; identify the other integrator's completed
  files, checks, contract changes and pending work. Wait for its shared-file handoff,
  preserving all work; no reset or checkout toggle.
- [ ] Snapshot current focused tests and mode labels without claiming prior results
  as current. Record compatibility expectations for F01–F03 and old STUB paths.

## T1 — Activity profile and general paper source contract

**Files:** workflow/service.py/context_records.py, domain/case/commands and API
activity DTO, evidence/document_profiles.py/document_validity.py/extraction.py,
additive schema as needed. Focused tests: `tests/unit/test_general_paper_profile.py`,
`tests/integration/test_activity_profile_scope.py`.

- [ ] RED: TC01 paper purpose/name/row/amount accepted as WORK_EXPENSE without
  `trip_*`; real travel packet continues to require trip context (source or
  responsible context) and missing trip does not become invented data.
- [ ] RED: new proposed activity has no budget/grant; catalog profile and verified
  organization profile survive restart; cross-tenant or client-forged profile fails.
- [ ] Implement common settlement form validation and conditional travel refinement.
  Recognize advance-settlement and no-advance employee reimbursement separately;
  missing paper advance is UNKNOWN until verified zero from history.
- [ ] GREEN focused tests and current travel F01–F03 profile/receipt tests.

## T2 — Multi-type source admission and claimant/company binding

**Files:** domain/organization.py/company context, evidence/document_profiles.py,
reconciliation/admission.py + matching seam; `tests/unit/test_general_source_binding.py`,
`tests/integration/test_tc01_original_sources.py`.

- [ ] RED TC01: original paper Nguyễn Minh An plus company-buyer invoice00000101,
  with scoped person/company/activity record and no contradiction, can be admitted
  under the accepted demo employee-paid basis; do not require paper rewrite or
  fabricated paid-confirmation.
- [ ] RED buyer-person mismatch, company-buyer identity conflict, explicit other
  payer, wrong activity and stale refs stay blocking FACT/out-of-scope. TC10 absent
  mandatory E_INVOICE buyer tax field stays unresolved, not filled from context.
- [ ] Preserve Hoangha type-specific original expense types (invoice, receipt,
  ticket, lodging) versus supporting payment/acceptance evidence; supported
  non-VAT tickets do not inherit VAT-invoice required fields. An explicit
  company payment in TC18 is not overwritten by demo employee-only convention.
- [ ] GREEN raw-source mocked/recorded tests; no bank-confirmation label from invoice.

## T3 — Category, deadline, budget and authority policy

**Files:** domain/finance/policy, context_records, reconciliation/admission/policy;
`tests/unit/test_expense_category_policy.py`,
`tests/integration/test_general_financial_authority.py`.

- [ ] RED 5m/5m+1 meal,2m/2m+1 taxi,30/31-day dated expense, unknown date FACT,
  explicit category with no separate cap, unknown/OTHER requiring responsible
  determination when category materially changes the decision.
- [ ] RED distinct expenses totaling E9m despite each meal<5m need recognition
  AUTHORITY; office E7.5m/A0 PAY7.5m needs issuance AUTHORITY; TC14 E121m/S1m
  beyond demo20m; independent B below T gives POLICY even when category passes.
- [ ] Port only the accepted Hoangha category caps/window and personal exclusion.
  Bind category/date rule to policy version and expense/source evidence, not
  informal keyword substring or one global hardcoded date. Unknown source date
  cannot be substituted by report submit date.
- [ ] GREEN focused policy tests plus existing finance, authority, personal and
  unknown-money checks. Stage results describe which rule blocked, not only WAITING.

## T4 — Source allocation and unusual evidence

**Files:** evidence/matching.py, reconciliation/admission.py and supporting DTOs;
`tests/integration/test_general_evidence_allocation.py`.

- [ ] RED TC17 meeting ticket+invoices stays three costs only when role/source
  valid; TC18 receipt+acceptance+bank proof for one labor row does not count extra
  cost; TC22 invoice5.4m cannot be allocated7.56m; TC23 invoice3.24m may back
  two allocations2.16m+1.08m and separate invoice5.4m exactly once.
- [ ] RED TC15 equal amount wrong service is not auto-linked; TC24 extra invoice
  creates relevance FACT, can be quarantined only by a scoped responsible answer;
  TC25 receipt700k versus paper900k stays FACT200k.
- [ ] Keep original documents and material findings; use exact invoice ref1.0 and
  accepted matcher weights/.50/.75/.90 unchanged. Do not fabricate repaired totals
  or count a payment proof as another invoice.
- [ ] GREEN focused matching/admission tests; persist gross source + individual
  allocation refs for reviewer.

## T5 — FACT → POLICY for missing evidence, scoped decisions

**Files:** reconciliation/admission/policy, issue/decision persistence, API answer/
decision DTO/views; `tests/integration/test_tc20_fact_policy_exception.py`.

- [ ] RED TC19 missing800k without reason: FACT, no partial instruction. TC20
  stated reason for100k: unresolved service/value/employee-paid basis first FACT,
  not accepted E or immediate POLICY. Wrong owner answer cannot mark known.
- [ ] RED after facts known: exact `expense:missing_required_evidence` POLICY to
  granted actor; approved exception has rule/expense/basis/max_effect/time/scope/
  reason; denial excludes known100k. Old approval expires when basis/source changes.
- [ ] RED with verified A2m/P/R0, accepted TC20 employee-paid100k: E1.48m,
  COLLECT520k; denied known100k: E1.38m, COLLECT620k. No initial effect and no
  duplicate instruction when an issue is answered/decision changes.
- [ ] Implement using existing Answer/Decide commands and audit; no new screen,
  standalone explanation PDF or waiver of FACT. GREEN focused tests.

## T6 — Build 25 independent final test packets from original sources

**Files:** `data/test-kit/hoangha-general/` with human-readable TCxx folder names,
`data/tham-khao/uc-03/final-case-mapping-v3.json` authoring input only,
new script under `scripts/` for packet context/gold separation,
`tests/integration/test_hoangha_general_packets.py` and Verify adapter.

- [ ] Literal inventory: all25 case ids/65 PDF SHA256 values match v3 and are
  unchanged. Do not copy old `expected.json` into runtime or use it as final gold.
- [ ] For each original TCxx create *independent* synthetic organization/person/
  activity/category-policy/budget/grant/ledger/coverage context with provenance.
  Budget never appears by inference from a printed amount; large TC04/14 historic
  approvals need genuinely scoped external demo authority in fixture or remain
  blocked. Multi-case TC12 runs sequential economic usage in a shared tenant.
- [ ] Choose and disclose per-packet controlled as_of inside valid source/policy/
  grant intervals. Preserve future/late originals; never change source dates or
  extend coverage witnesses silently. Interactive UI uses actual server time and
  may need refreshed responsible context.
- [ ] Author independent gold for source fields, roles, links, FACT/POLICY/AUTHORITY
  owner and conditional post-answer effects. Freeze only after current implementation
  handles raw sources. Distinguish source-readable, finance-admissible, and
  executed/settled states. Expected Hoangha AUTO labels may legitimately diverge
  under final8/4/20, e.g. TC23 AUTHORITY and TC13 exclude personal cost.
- [ ] RED packet loader refuses gold/model leakage, wrong digest, wrong scope;
  GREEN all25 structural/evaluation adapter tests. Keep F01–F03 corpus and
  generator stable; prototype common PDF is visual authoring only.

## T7 — Employee/accountant UI and final execution gate

**Files:** frontend intake/dossier/questions/current API views, evaluation runner/
scorer/Verify, status/runbook; browser tests in existing frontend test tree.

- [ ] RED: employee can choose a work-cost activity without entering backend IDs;
  upload paper+evidence; see specific questions with source/known values; no
  trip fields for nontravel. Accountant receives only actually needed money/
  factual tasks. Policy owner sees exact expense/rule/effect, not generic approval.
- [ ] Implement minimal UI changes against current agent's settled frontend; no
  redesign of concurrent work. Payment basis view truthfully distinguishes demo
  invoice policy from actual bank/ledger event. No zero/false-known money UI.
- [ ] Targeted tests first, then backend full suite, pinned Node/npm frontend
  scripts/build and browser flow. Exercise TC01 local reception, TC02 office
  purchase, TC03 travel, TC20 FACT→POLICY, TC23 AUTHORITY, TC12 duplicate and
  F01–F03 regressions. Full25 LIVE when providers available and budget bounded;
  record actual model/source/prompt/revisions and failures. Do not call a fake
  or native-text run LIVE.
- [ ] Verify Core4/Escalation5 and one-action harness on the updated independent
  gold. Report separate source-quality, decision and action outcomes; missing
  provider/recording/browser/live evidence is NOT_RUN, not PASS.
- [ ] Update operative contract/glossary/ADR only for actual accepted changes,
  status with exact evidence and remaining gaps. No commit/push/reset without user
  authorization.

## Self-review and handoff

Native self-review against user decisions: old TC source byte preservation, new
category caps/window, independent B, final8/4/20, original buyer company binding,
personal A retention, alternative evidence, missing-source FACT→POLICY, multi-row
invoice allocation, scoped actual history, Stop/usage and old-gold visibility are
assigned to T1–T7. This plan is documentation; application implementation and
LIVE raw-case assessment are NOT_RUN here. One integrator implements T1–T7 after
the current shared-file agent completes its gate; re-read live source/HEAD then.

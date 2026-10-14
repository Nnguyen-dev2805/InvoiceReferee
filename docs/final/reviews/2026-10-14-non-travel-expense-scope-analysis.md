# Beyond travel — Hoangha source analysis and proposed final scope

User requested read-only engineering analysis while another agent implements the
invoice-demo basis and advance-recording work. This report is a proposal, not an
accepted policy revision or implementation plan. No shared application, contract,
glossary, data or working-tree file is modified by this analysis.

## Evidence and limits

Hoangha worktree `.worktrees/hoangha`, branch `hoang-ha-fresh`, HEAD
`1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8` unchanged. Source discovery uses
CodeGraph Verify, current verbatim snippets and bounded reads for trimmed ranges.
Generation/coverage APIs unavailable: coverage UNKNOWN; no reindex. Final is
actively edited by another implementer; source statements below describe the
observed checkout, not a frozen post-implementation certification.

Read primary bounded scope: Hoangha domain/settlement.py, policy/settlement.py,
application/paper_evidence_matching.py, application/process_settlement.py,
policy/document_validity.py, application/settlement_summary.py and decision_guard;
final domain/case/finance, evidence/document_profiles, workflow/service and
reconciliation/admission/policy; accepted design scope and competition brief.
Hoangha CURRENT_COMPANY_RULES.md describes the older Streamlit inventory path,
so it is not used as authority for current UC03 FastAPI settlement behavior.

Corpus metadata inspected: 25 v1 expected.json files and 50 v2, five v2 groups.
These are authored examples/expectations, not 75 observed successful executions.
The actual TC01 LIVE run is documented in 2026-10-14-hoangha-tc01-live-investigation.md.
No new provider, product test or browser run in this analysis.

## What Hoangha actually models

Two settlement types:

- ADVANCE_SETTLEMENT: reconcile expenditure against declared allocated advance;
  propose employee return/company top-up/no difference.
- EMPLOYEE_REIMBURSEMENT: employee-funded expense reimbursement; declared advance
  must be zero, reimbursement proposal equals claimed total.

BusinessContext uses purpose, optional project/client and optional activity dates;
it does not require every cost to be a trip. Digital input and paper input converge
on ExpenseItemDraft with category, description, date, amount and evidence binding.

Expense categories: CLIENT_MEAL, TRAVEL, HOTEL, TAXI, OFFICE_SUPPLIES, OPERATIONS,
PERSONAL, OTHER and UNKNOWN. An enum value is representational support, not a
complete specialized process. Existing paper _infer_category uses transparent
keywords: taxi/Grab, food/reception/cafe, hotel/lodging, ticket/travel and stationery.
Unrecognized text becomes OTHER; OPERATIONS and PERSONAL have no direct keyword
branch in that function. Digital forms can supply category explicitly.

One settlement workflow handles these categories. Runtime document validation is
selected by document type, not category: invoices, receipts, hotel receipts, tickets
and supporting documents have different required fields. Contractor acceptance,
delivery notes, supplier confirmations/payment evidence exist as supporting types;
this does not establish a complete purchase/inventory/vendor-payment workflow.

## Implemented UC03 policy, not a proposed generalized rulebook

SettlementPolicyConfig defaults:
- CLIENT_MEAL cap5m per expense item.
- TAXI cap2m per expense item.
- PERSONAL prohibited.
- Submission window30days per expense date.
- Authority100m per case.
- Configurable company name/tax codes for applicable document checks.

evaluate_settlement_policy also handles missing sources, category/date unknown,
alternative evidence/no evidence and source-type/advance-type consistency.
Categories without category_limits entries have no dedicated category cap. OTHER
does not equal UNKNOWN and can avoid the unknown-category gate. Paper keywords
therefore are not sufficient for conservative category eligibility decisions.
Example: corpus TC13 explicitly marks an expected policy behavior GAP_EXPECTED;
copying its expected label is not proof the runtime enforces it.

Clean input routes READY_FOR_APPROVAL to accountant; this differs from final's
automatic routine instruction issuance. Hoangha accepts paper advance and explicitly
does not reconcile historical disbursement. Do not transfer these shortcuts or the
100m ceiling as final policy without a separate accepted decision.

## Three dimensions must remain separate

| Dimension | Examples | Determines |
|---|---|---|
| Settlement financial history | Received advance / verified no advance | A and the resulting settlement math |
| Business activity | Trip, client reception, office purchase, maintenance | Purpose/scope and relevant context |
| Expense category | Meal, taxi, lodging, supplies, repair | Category eligibility/rules/evidence needs |

A trip can contain several categories. A taxi can belong to either a trip or a
local client meeting. "Reimbursement" is not a category alongside "hotel".
An arbitrary project code should not be required of employees; server-owned case/
activity identity remains the linkage, with a human-readable activity purpose.

## What can be reused in final

Final's financial identity is one claimant/one activity, VND; CaseScope.profile is
already a string and grants have allowed_profiles. Its S=E-A-P+R, actual ledger,
instruction fulfillment, duplicate economic usage, Stop/Resume, OCR pipeline and
FACT/POLICY/AUTHORITY ownership apply beyond travel.

This reuse does not establish support automatically. Observed gaps:
- workflow/service DEFAULT_ACTIVITY_PROFILE="TRAVEL" used when creating cases;
  demo snapshot construction also writes TRAVEL.
- SETTLEMENT_FORM required_fields include trip_destination/start/end for every form.
- Expense DTO lacks a business category; policy has no per-category contract like
  Hoangha's ExpenseItemDraft/SettlementPolicyConfig.
- Purpose/context/grants/dataset expectations currently follow accepted travel-first
  scope. A new profile needs corresponding authorization, budgets/evidence/gold.

Changing labels or removing trip fields globally would weaken existing trip checks.
Field requirements must be profile-appropriate; a general expense report should
not be rejected for lacking an imaginary trip, and a real trip still needs its
agreed context. Document-type profiles and activity policy profiles are distinct.

## Proposed first expansion

Product scope: employee-paid business-expense settlement, with or without a
received advance. Keep one employee, one activity, VND, existing allowed money
directions and current instruction/control logic.

First supported business families, to discuss/approve before implementation:

1. Domestic travel (existing).
2. Local work/client reception and meetings — TC01 becomes relevant unchanged.
3. Office purchases: stationery and small equipment paid by employees — TC02/TC04
   can inform cases; this is expense reimbursement, not asset registration or a
   procurement workflow.
4. Small operations/maintenance services: printing, repair, delivery and work-related
   fees; received-service/acceptance requirements must be explicit where material.

Use a generic business-expense profile plus the travel-specific refinements if
that keeps actual differences small; do not add a separate workflow engine or a
class per category. Lead option, not a user-approved enum/name decision.

Introduce a small expense-category policy table. Each supported category must state
whether admitted, relevant cap/aggregation unit if any, required business context,
evidence basis and responsible owner for missing facts/exception/authority. Absence
of a cap must be an explicit business rule, not an accidental dict miss. UNKNOWN
must be unresolved when category changes the decision; OTHER is not a blanket PASS.

Keep existing system/grant thresholds unless user changes them. Hoangha's5m/2m/30day
rules are options for discussion, not automatic imports. The recently accepted
demo-invoice paid basis must be documented per supported profile; acceptance of a
payment basis does not prove missing service/receipt/identity/activity facts.

Do not expand to foreign currency, employee-to-employee payments, corporate supplier
payment, multi-claimant allocations, payroll/tax filing, inventory or depreciation
just because corresponding words/documents occur in the reference corpus.

## Input shape and controls

Generic settlement form: claimant, activity/purpose, document date, expense rows
(description/category if declared, invoice reference, amount), totals, declared
advance/difference. Trip location/dates belong to the travel profile, not universal
required fields. Optional client/project supplements purpose; it is not an
authorization token. Data matching retains literal refs and economic identity.

Verified-no-advance requires a valid organizational/financial basis, not the absence
of an advance file. Actual ledger/coverage remains scoped and current in both
advance-settlement and employee-reimbursement paths.

Acceptance matrix: routine sufficient input→AUTO; unknown claimant/category/receipt
or source conflict→FACT; known cost violates explicit category/budget rule→POLICY;
known eligible cost/effect beyond grant→AUTHORITY. Resolve only affected facts and
keep independent money history. No routine mandatory accountant approval imported
from Hoangha's READY_FOR_APPROVAL branch.

## Competition fit and implementation ordering

Competition A asks for one clearly defined routine process, at least15 varied cases,
FACT/POLICY/AUTHORITY, actual routine autonomy, concrete answerable questions, no
affirmative result on flagged input and one-action5-case Verify. Breadth alone is
not evidence of quality. A single employee-expense settlement process can include
several cost categories while retaining a coherent evaluation unit.

Recommended next sequence:
1. Approve supported families and a category/evidence policy matrix.
2. Write a separate expansion spec while the active implementer owns shared files.
3. After its current invoice/advance gate, extend profile selection, extraction/
   validity, category admission, policy/context and actual UI fields as one slice.
4. Adapt TC01 first without inventing trip fields, then office purchases and operations.
   Preserve Hoangha source PDFs; supply independent final context/gold.
5. Verify routine/FACT/POLICY/AUTHORITY for each supported family, then broaden the
   existing15-case development suite/Core4/Escalation5. Do not label the whole
   Hoangha corpus supported without actual runtime evidence.

This is a scope proposal only. No implementation, policy thresholds or generic
profile names were finalized by this read-only task.

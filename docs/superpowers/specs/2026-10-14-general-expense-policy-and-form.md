# General employee-expense settlement — Hoangha + final

Status: concrete policy/form specification. User approved importing Hoangha's
category rules and submission window while retaining final's8/4/20 authority
on14/10/2026. Application integration is NOT_IMPLEMENTED by this task; another
agent owns the current shared-file invoice/advance implementation. No subagents.
User additionally approved FACT → POLICY through the existing answer/decision flow
for rows with missing evidence and a stated reason. No separate explanation screen.

## Intent and fixed scope

One process: settle business expenses paid by one employee for one activity in VND.
It covers travel, local client/work meetings, office purchases including small
equipment, and small operations/maintenance services. It supports received advance
settlement and verified-no-advance employee reimbursement. It does not add corporate
supplier payments, inventory/asset/depreciation/payroll/vendor-debt workflows,
foreign currency or multi-claimant cost allocation.

The user-selected demo invoice basis and accountant advance-recording flow remain
operative: no extra supplier-payment confirmation document or long payment statement
on the paper. Uploaded actual-advance sources still need the accountant's server-
bound confirmation; invoice acceptance must never manufacture an actual A/P/R event.

## Missing evidence and binding of original documents

Read the reason already printed in a paper row as a declaration, not independent
proof of service, amount or payment. If those facts are not established, ask the
specific FACT owner about that row. Once facts are established, absence of required
expense evidence invokes the operative POLICY rule
`expense:missing_required_evidence`. Only an actor with a scoped EXCEPT_POLICY
grant for the exact rule/expense/effect may approve an exception. A refusal gives
a known excluded disposition; both outcomes are audited and reassessed. Neither
outcome may override a material source conflict or create a completed A/P/R event.

TC20's100k parking row starts as FACT while service/value remain unresolved. With
independent, responsible employee-paid basis for the100k row plus verified A2m and
P=R0: after a valid exception and admitted E1.48m, S=-520k;
after a final exclusion with admitted E1.38m, S=-620k. These are *conditional*
branches, not an instruction based on a missing row. Existing answer/decision UI
handles the case; no new explanation PDF or dedicated screen is required.

Hoangha's original invoice may name the company buyer without naming its employee.
For the user-selected demo employee-paid policy, allow composite binding: the
paper claimant matches the server employee, the paper row links the invoice,
the company buyer matches the scoped organization, and there is no contradictory
natural-person/payer evidence. A buyer-person name, if present, must match the
employee. Do not change original PDFs to force a name or manufacture a confirmation.
Supporting payment/acceptance documents remain distinct evidence and never count
as extra costs. Explicit company/other-payer evidence blocks the affected
employee-paid basis until an accountable correction establishes the true payer.

## Imported rules and retained authority

Source Hoangha: `.worktrees/hoangha/src/invoice_referee/policy/settlement.py` at
1ee33487 (SettlementPolicyConfig and evaluate_settlement_policy).
Source final: IMPLEMENTATION_CONTRACTS§5 and current context/grants.

| Rule | Value/unit | If facts are known and rule fails |
|---|---|---|
| Work/client meal | <=5,000,000 VND per expense item | POLICY exception decision |
| Taxi/ride service | <=2,000,000 VND per expense item | POLICY exception decision |
| Submission window | <=30 calendar days from established expense date | POLICY exception decision |
| Personal expense | Not recognized as business expense | Retain source/history, apply final disposition/settlement rules |
| System cost recognition | E<=8,000,000 VND for the activity settlement | AUTHORITY if higher, after facts/basis known |
| System instruction issuance | abs(S)<=4,000,000 VND | AUTHORITY if higher, after facts/basis known |
| Demo approver | <=20,000,000 VND per granted action and effect scope | Need an actor/grant with sufficient authority; no automatic elevation |

These are different checks, not interchangeable thresholds.8m is not a universal
budget;4m is not a limit on total invoice cost;20m is not automatic approval of
every claim below20m. B remains an independent authorized record. No instruction
until material evidence, history, policy and grants are satisfied. Hoangha's100m
authority is not imported. No silent escalation-threshold adaptation in this change.

Per-item category limit means a canonical expense, not each freely split paper row.
Source allocation/economic identity must prevent splitting one meal/taxi cost into
several rows solely to bypass the limit. Limit amount uses claimed/admitted gross
VND including applicable tax, as in Hoangha's item claimed_amount check. No newly
invented per-day or per-person caps.

## Category table

| Category | Examples | Category-specific amount rule |
|---|---|---|
| Work/client meal | Work meal, restaurant/client reception | 5m/item |
| Taxi/ride service | Taxi, Grab, similar work transport | 2m/item |
| Travel tickets/transport | Flight/train/bus ticket | No separate category cap in imported rules |
| Lodging | Hotel/accommodation | No separate category cap in imported rules |
| Office purchases | Stationery, printing supplies, small equipment | No separate category cap in imported rules |
| Small operations/services | Printing, maintenance/repair, work fees | No separate category cap in imported rules |
| Personal | Established personal purpose | Exclude from business recognition; retain actual-money obligations |
| Other/unknown | Category not established or outside supported families | A missing category is FACT when material; established unsupported scope needs explicit handling, never implicit unlimited PASS |

"No separate category cap" is explicit: B,8/4 system rights,20m approver grants,
30days, accepted evidence/identity and ordinary financial gates still apply.
Hoangha's fallback OTHER and default EmployeeProfile are not imported as proofs.
LLM category is a proposal linked to source/context; code selects the operative rule.

## Routing examples

All examples assume valid identity, independent adequate B, admitted payment basis,
complete current financial history and valid scoped grants, unless stated otherwise.

- TC01 reception: E3.24m/A4m/P0/R0 => S=-0.76m. Under5m category/8m recognition/4m
  instruction: AUTO/COLLECT760k, no routine approval question.
- Taxi2.2m/A3m => S=-0.8m. Small S does not waive2m taxi policy: POLICY.
- Two distinct meals4.5m+4.5m, A8m => E9m/S1m. Each meal meets5m, but E exceeds8m:
  recognition AUTHORITY; no system instruction until it is resolved.
- Admitted office cost7.5m, verified A=P=R0 => S7.5m. Recognition within8m, issue
  beyond4m: issuance AUTHORITY.
- Late claim with established date31days earlier => POLICY, even if amounts small.
- Missing expense date => FACT, not an assumed deadline failure.
- An action25m => outside demo approver20m grant; no implied100m fallback.

## General paper form, adapted from Hoangha

Use the structural layout from scripts/generate_uc3_testcases.py::create_report_pdf:
company/national heading, document date, centered title/purpose, claimant, five-column
table, total/words, declared advance/difference and three horizontal signatures.
Use final's portable NotoSans asset; do not copy Windows font/dependency paths.

Canonical title: GIẤY ĐỀ NGHỊ QUYẾT TOÁN CHI PHÍ. Optional mode subtitle distinguishes
received-advance settlement from employee-funded reimbursement. Printed names are
source declarations, not server identity or authorization.

Common fields:
- Company and document number/date.
- Recipient accounting/approver function, claimant name; department/position optional
  when available from account/context, never required to enter backend employee IDs.
- Business purpose/activity. Client/project optional; server owns linkage identifiers.
- Table STT / NỘI DUNG / HÓA ĐƠN, CHỨNG TỪ / SỐ TIỀN / GHI CHÚ.
- Total with Vietnamese amount words.
- For advance settlement, declared advance and proposed return/top-up/no difference.
  For no-advance reimbursement, amount requested to reimburse. Do not interpret a
  missing advance field as independently verified A0.
- Signature row: employee applicant / accountant / approver. Text "Ký bởi"/date is
  sufficient for demo signature display, not a grant or a bank event.

No mandatory attachment-summary sentence or supplier-payment declaration paragraph.
References in rows + uploaded file binding are used. Travel location/start/end
remain required only for travel scope; non-travel papers are not forced to invent
trip fields. Expense date comes from actual source/validated context and must not
be replaced blindly with report submission date.

Prototype: data/test-kit/uc03-expansion/mau-giay-quyet-toan-chi-phi-chung.pdf.
It is an authoring visual, not a complete executable packet or a runtime pass.

Original-source mapping for all25 Hoangha v1 cases:
data/tham-khao/uc-03/final-case-mapping-v3.json. All65 source PDF hashes/bytes stay
unchanged. The previous travel-first mapping remains historical context, not the
current target for these original PDFs. Neither mapping is executable gold.

## Integration responsibilities after the active agent's gate

Retain one CaseWorkflow/DB/ledger/reader/Reconciler. Make case profile selection
server/context-owned; remove unconditional TRAVEL assignments. Introduce generic
settlement-field requirements with travel-specific refinements rather than globally
deleting trip validation. Add typed per-expense category and versioned category
policy into admission/current context and evaluate it in existing policy engine.

Keep the existing financial/history/source/Stop/duplicate invariants and routine
autonomy. Do not port Hoangha's always-READY_FOR_APPROVAL end state or paper-as-actual
advance assumption. If facts are missing, ask concrete FACT; if known rule fails,
POLICY; if sufficient basis exceeds granted action range, AUTHORITY.

No shared code/schema/contract edit until the active integrator hands off its
current invoice/advance gate. Then refine the operative contract and implement
against the actual checkout; this spec is not a substitute for current source.

## Completion evidence required for later implementation

- Original TC01 accepted as client/work reception without invented trip dates;
  independent final context/gold and correct person/company linkage.
- Office purchase and operations examples supported through same workflow.
- Both advance-present and advance-missing/accountant-follow-up flows.
- Boundaries5m/5m+1,2m/2m+1,30/31days,8/4/20, B/grant/profile/scope and unknown dates.
- Split-row threshold bypass, unknown-category fallback, multi-source/duplicate and
  stale-history/Stop checks.
- PDF authoring separated from app/model/gold; existing travel regressions retained.
- At least15 varied development cases and existing one-action Verify suites updated
  from real results. LIVE and browser evidence explicitly separate from fake tests.

This task produces the specification and form prototype only, with no product
implementation/tests/LIVE/UI claims. Remaining implementation gate belongs to a
subsequent coordinated task.

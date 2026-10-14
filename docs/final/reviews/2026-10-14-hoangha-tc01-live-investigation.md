# Hoangha TC01 — LIVE run and decision-basis analysis

User requested the unchanged original TC01 PDFs through Hoangha's pipeline before
deciding whether to remove attachment/payment-declaration prose from final's form.
No PDF/application code changed. No subagents, commit/push, original DB mutation,
accounting approval or actual-money action.

## Execution identity

- Source worktree `.worktrees/hoangha`, branch `hoang-ha-fresh` at
  `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`, unchanged before/after.
- Used official `app.web.runtime.build_runtime`, SubmitSettlementService,
  SettlementProcessingService.run_once and SQLiteSettlementRepository. A private
  subclass records adapter inputs/outputs/timing and delegates unchanged behavior.
- Python3.12 via final's `uv run --no-sync`, with sys.path explicitly selecting
  Hoangha source/app. The script asserts imported invoice_referee package location.
- Real Mistral and Kimi credentials loaded from Hoangha's ignored .env, no key output.
- Separate runtime directory/database; no native PDF extraction substituted for OCR.
- Source code discovery used CodeGraph Verify for Hoangha; coverage/generation tool
  unavailable (UNKNOWN); relevant trimmed ranges read directly. No re-index.

Command:

```text
rtk proxy uv run --no-sync python .runtime/hoangha-tc01-live-investigation/run.py
```

Exit0. Case `SET-20261014-B1103715`. Evidence is under
`.runtime/hoangha-tc01-live-investigation/`: trace.json, manifest.json, provider
requests/responses, parsed facts, before-paper-matching.json, final-findings.json,
result.json, business-summary.json and the isolated DB/artifacts.

The input draft is PAPER_SCAN / ADVANCE_SETTLEMENT, with empty expense_items,
purpose empty and allocated_advance_amount0. Those values are filled from OCR/LLM
facts, not seeded gold. Employee profile is the application's default synthetic
Nguyễn Minh An / Phòng Kinh doanh, not a person parsed from PDF. No gold was read.

Original PDFs are byte-identical to the reviewed TC01 copies:

- report: SHA2566af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c
- invoice: SHA256d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019

## Actual trace

| Stage | Observed result | Time |
|---|---|---:|
| Intake/repository | Two uploads with roles REQUEST_FORM / EXPENSE_EVIDENCE; queued job | — |
| Mistral OCR report | One page; raw OCR persisted | 4.49s |
| Mistral OCR invoice | One page; raw OCR persisted | 4.19s |
| Kimi confidence quality | One low-confidence invoice signature-name block; NON_CRITICAL/READABLE/CONTINUE | 6.69s |
| Kimi paper extraction | One cost row, total3240000, advance4000000, printed difference760000 | 4.81s |
| Kimi expense extraction | E_INVOICE, identity/totals/tax read; payer/transaction fields null | 7.52s |
| Rule validity | Both documents CLEAR and eligible_for_matching | — |
| Rule matching | AUTO_LINK/INVOICE_NUMBER_EXACT/score1.0 for 00000101 | — |
| Arithmetic/policy | 14 PASS, one PENDING_APPROVAL, zero FAIL | — |
| Decision/storage | READY_FOR_APPROVAL, target ACCOUNTANT, processing COMPLETED | — |

Elapsed intake-to-result approximately28.04s. Two OCR calls and three Kimi calls;
no schema-repair call and no ambiguous-link resolution call in this run. Kimi model
`moonshotai/Kimi-K3`, OCR `mistral-ocr-latest`. No token-cost claim: wrapper records
the adapter's bounded text response, not the provider billing envelope.

Confidence candidate concerned “MINH” in seller signature text. The quality agent
treated it as readable because the seller name appeared clearly elsewhere. This
is readability classification, not cryptographic signature verification. Its
parsed result has requires_verification=false and no accounting fact decision.

## What exactly was checked

Paper parsed facts:

```text
purpose = Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026
total_amount = 3240000
advance_amount = 4000000
reimbursement_amount = 760000
line invoice_refs = [00000101]
line amount = 3240000
line note = Đính kèm hóa đơn điện tử
```

Invoice facts include subtotal3000000, tax240000, total3240000, document
number00000101, seller/buyer identity and payment_method=Chuyển khoản. Crucially:

```text
payer_name = null
payee_name = null
transaction_reference = null
transaction_status = null
confirmation_present = null
```

The rule code validates the paper's required purpose/total/lines/advance fields,
and the invoice's required identity/date/total/line fields. It matches the exact
invoice number, checks paper line total against paper total, computes
abs(4000000-3240000)=760000, compares the printed difference and derives direction
from advance versus cost.

Hoangha policy version DEMO-EXPENSE-2026/1.3 includes client-meal cap5m, taxi cap2m,
authority100m and submission window30days. These are Hoangha's demo rules, not
final's8m/4m20m budget/authority contract. In this run company_legal_name=None and
company_tax_codes empty: seller/buyer fields present does not prove a configured
company-identity comparison passed.

## Why no paid-confirmation sentence or history question is required here

The pipeline does not establish an independently verified employee-paid E or an
actual received A/P/R ledger. It calculates a proposed settlement from invoice
cost and the advance declared on the paper. The rule's own persisted message is:

> Đơn khai số tiền đã tạm ứng 4,000,000 VND; MVP không đối chiếu với lịch sử giải ngân.

Source: process_settlement.py:657–734 (SET_ADV_AMOUNT_001 and difference check);
policy/settlement.py:93–100 explicitly accepts the paper-read advance path without
the original advance record. replace_paper_items at process_settlement.py:729
stores allocated_advance_amount directly from paper_facts.advance_amount.

The final guard decision (decision_guard.py:56–79) is READY_FOR_APPROVAL when no
finding FAILs. It targets ACCOUNTANT and does not issue a bank payment/collection
instruction. The paper path appends SET_APPROVAL_001/PENDING_APPROVAL:
accountant checks originals and performs confirmation/signature before subsequent
approval. The three printed “Đã ký” blocks do not skip that software step.

Therefore the observed success proves OCR/extraction/matching/arithmetic/routing
work for these two PDFs under this policy. It does not prove actual money received,
employee payer, history completeness, valid electronic signatures or completed
settlement. Those predicates were not required by this processing contract.

## Concrete boundary issue visible in this run

The report says department Hành chính nhân sự. Result/audit summary says Phòng Kinh
doanh because that is the default EmployeeProfile. PaperSettlementFacts/extraction
does not populate employee identity/department. The default name happens to match
the source name. This is not evidence of identity verification. Do not transplant
this default-context behavior into final as an identity-binding solution.

## Implication for the requested simpler form

“Tài liệu kèm theo: 01 hóa đơn dịch vụ” need not be a required standalone line when
the row's invoice reference and uploaded-source relation are available. Hoangha's
original report still has a row note “Đính kèm hóa đơn điện tử”; the successful run
does not separately prove that deleting every attachment note preserves behavior.

The employee-paid sentence can be omitted from the printed form while retaining
responsible confirmation elsewhere in the workflow. Hoangha's run demonstrates
that a proposal-to-accountant workflow works without that sentence; it does not
demonstrate that final may automatically assert E/A/P/R from the same two PDFs.

Keep these choices distinct: simpler PDF wording; responsibility/location of paid
confirmation; actual historical money evidence; automated instruction versus human
approval routing. A change to final's accepted basis/routing contract requires an
explicit design decision. No change was made in this investigation.

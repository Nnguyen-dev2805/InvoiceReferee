# TC05 — LIVE negative-case review

Verdict: **FAIL — unsafe affirmative collection on contradictory source totals.**
Read-only application review; no fix, user DB write/reset, subagent or commit.
Current final HEAD7e7883c plus shared uncommitted changes. Relevant code hashes
and source PDF hashes saved under `.runtime/tc05-live-review-20261015/`.

## Source inspection

Case is the original Hoangha `tc05-tong-cac-dong-tren-bao-cao-khong-khop`, the
same corpus family as TC01. Rendered both one-page PDFs at1500px and visually
inspected the complete pages; text extraction used only for review, not runtime.

Paper:
- Claimant Nguyễn Minh An, An Thịnh; reception for office-upgrade project2026.
- Reception2000000 + meeting-room1000000 = **3000000**.
- Printed total **3500000**, words also3.5m: difference **500000**.
- Declared advance4000000, printed employee return500000; these agree only with
  the printed3.5m total, not the sum of rows.
- Both rows reference invoice00000501.

Invoice00000501:
- Dining/reception10 ×300000 =3000000; VAT8%=240000; gross3240000.
- Internal invoice arithmetic is consistent.
- No meeting-room service is shown. Shared invoice reference is not intrinsically
  invalid (partial allocation can be legitimate), but the extra room description
  and gross/net allocation require clarification; do not invent a second service.

No unique financial collection is established by these contradictory documents.
500k uses the printed total,760k uses invoice gross,1m uses row sum. None should
be issued automatically before the contradiction is resolved.

## LIVE execution

Single current production composition (`runtime.build_workflow`, LIVE), private
SQLite/uploads, same HTTP create/attach/draft/submit endpoints as the web.
No fake reader or native-PDF text path. Provider settings at run: Mistral
`mistral-ocr-latest`, configured LLM `qwen/qwen3.7-flash:free`, Python3.12.13.
73.51seconds total; OCR/classification/extraction/validation/matching71.51seconds
including API/session preparation; no fresh provider call on submit.

Context origin is explicitly **SIMULATED**: TC01 company fixture adapted to a
distinct activity:tc05, witnessed actual advance4m, valid activity/rights and
scoped coverage at controlled server clock2026-10-15 16:00+07. This isolates the
source-validation failure from missing-history/authority issues. The two PDFs
alone do NOT independently establish actual advance4m. Gold/expected.json was
not loaded into application/model inputs. Web8000 was not used or modified.

Observed:
- OCR markdown preserves all numbers correctly.
- LLM structured paper: lines2m/1m, printed_total3.5m, declared_advance4m,
  printed_return500k. Invoice: subtotal3m, tax240k, total_amount3.24m.
- Both documents `profile_status=CLEAR`.
- Both rows `AUTO_LINK` / `INVOICE_NUMBER_EXACT`, allocations2m and1m.
- Employee draft: incurred_total3500000, **warnings=[]**.
- Final: **READY_TO_EXECUTE**, **issues=[]**, T=E=3000000, A=4000000,
  P=R=0, S=-1000000. One **ISSUED COLLECT1000000**, executionNOT_STARTED.
  No physical money moved in this test.
- Read-only Playwright UI/API observation reproduces this unsafe state on private
  port65110. This characterization is evidence of failure, not acceptance PASS.

## Cause verified in current source

`document_arithmetic.py::_check_settlement_form` checks advance−printed_total
against printed_return/reimbursement. TC05 passes that relation:4m−3.5m=500k.
It does not check sum(paper line amounts) against printed_total.

`admission.py::_match_expense_documents` admits the row amounts, linked by invoice
reference. The allocations3m do not exceed invoice3.24m, so existing over-allocation
checks do not fire. The final total becomes3m. No blocker connects that total to
the contradictory paper3.5m. `settlement_draft.py` displays printed_total and only
surfaces the same incomplete arithmetic findings, so it gives no warning either.

Probe of the **actual LIVE report** returns zero arithmetic findings. Two local
regressions are **RED /2failed**: detect the paper row-total contradiction and
forbid the observed affirmative collection. They are under `.runtime`, outside
the default product suite; no application implementation was changed.

## Required correction

1. Source-backed paper row-sum ↔ printed-total validation, with unreadable/missing
   rows staying unresolved rather than zero. One shared rule used by draft and
   financial admission; factual source refs, exact500k difference, employee owner.
2. Block issuance while that contradiction is open; never silently choose3m,
   3.24m or3.5m as authoritative or label its refund final.
3. Review gross/net/partial allocation and service coverage separately. Do not
   fix this by forbidding all shared-invoice allocations or forcing every row
   to equal the full invoice; preserve valid TC23 cases.

## Evidence files

`.runtime/tc05-live-review-20261015/`: report.png / invoice.png, sources.json,
context.json, run.sqlite, draft.json, report.json, view.json, result.json,
audit.json, jobs.json, ocr-paper.md / ocr-invoice.md, raw artifacts/, live.log,
arithmetic-probe.json, test_tc05_regression.py / regression-red.log,
ui-unsafe-result.png / ui-observation.json / ui-trace.zip, code-hashes.json.

The first UI harness attempt used an invalid relative API URL; that harness URL
was corrected and the read-only observation rerun. No provider/business logic was
altered to obtain the result. Private view server stopped after verification.
Graph generation/coverage tools unavailable: relevant full snippets/ranges read,
coverageUNKNOWN, not an exhaustive repository audit.

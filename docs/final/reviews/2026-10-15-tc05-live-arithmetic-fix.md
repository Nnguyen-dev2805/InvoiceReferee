# TC05 — LIVE row-total arithmetic correction

Verdict: **the TC05 arithmetic contradiction now blocks a financial conclusion
and any instruction.** This resolves the narrow false-collection failure from
the prior negative review. It does not prove that every expense row is complete,
or that the invoice describes a valid service for each linked row.

## Rule and code path

The previous validator checked only advance − printed total against the stated
refund/reimbursement, so TC05's 4m − 3.5m = 500k passed while its expense rows
totaled only 3m. Admission accepted the two rows against invoice number
00000501 and produced a 1m collection from the row sum.

`check_document_arithmetic` now checks itemized settlement rows against the
printed total using integer VND and the shared `parse_vnd` path. Total/subtotal
summary rows are not counted as expenses. An explicitly represented row with
missing, ambiguous or unreadable description/amount, or a present but unreadable
printed total, produces an unresolved finding; it is not treated as zero and a
readable subset is not summed as if complete. `printed_total=NOT_PRESENT`/
`NOT_APPLICABLE` asserts no aggregate relation. No VAT, fee, discount or missing
expense is inferred to force equality.

The same finding flows into the employee draft and financial admission. TC05's
contradictory expenses remain disputed, T/E/S are UNKNOWN, there is no payment
basis and no instruction is issued. The S formula, advance/refund rules,
authority, policy and Stop/Resume behavior were left intact. Exact invoice-number
matching still establishes a link only; it does not establish the meeting-room
service. That service-description question remains separate for resolution after
this arithmetic blocker.

## Regression and suite evidence

Added regression coverage for TC05 mismatch, unreadable/ambiguous represented
rows, unreadable/absent printed total, summary rows, no VAT inference, shared VND
parsing and no partial-row summation. Integration proves one employee FACT,
source refs, UNKNOWN financial basis, WAITING state and no instruction. Other
regressions preserve TC01, TC06, TC11, a valid multirow paper and two rows sharing
one invoice within its total (TC23 allocation behavior). Extraction preserves
explicit empty/unstructured settlement rows so the validator can keep them
unresolved. The one modified `test_invoice_paid_basis.py` input was a synthetic
9m row/3.24m total that became contradictory under the new rule; that fixture's
printed total was corrected to 9m to keep that test focused on its intended
invoice-paid basis question. No TC05 source, gold or expected outcome was edited.

Verification on 15/10/2026:

- `rtk proxy uv run pytest -q` → exit 0; 781 tests collected.
- Node selector: `/Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`; Node24.19.0, npm11.12.1. `npm --prefix frontend test -- --run` → 45 passed, 2 skipped.
- `npm --prefix frontend run build` → exit 0; Vite build completed.
- `rtk proxy git diff --check` → exit 0.
- Two read-only Playwright views used isolated private databases on ports65111/65112. The pre-submit draft shows “Có mâu thuẫn số liệu”, both row values, the 3.5m paper total marked unverified, “Chênh lệch kê khai dự kiến: Chưa xác định”, and source filename/page/quotes. The final view shows one employee FACT with the same source refs, T/E/S unknown, A4m, P/R0, and no instruction. Neither view server has a working OCR/LLM provider; browser navigation did not submit or mutate data.

## Fresh LIVE run

Ran the actual application LIVE composition through create/attach/read/draft/
submit/assessment on the original TC05 PDFs, with a fresh separate SQLite DB,
uploads and artifact root. OCR and LLM were genuinely called: Mistral
`mistral-ocr-latest`, configured LLM `qwen/qwen3.7-flash:free`; Python3.12.13.
Elapsed time72.6s. The TC01-derived activity/grants/coverage fixture and known
advance4m were explicitly **SIMULATED** context; this is not evidence that the
two PDFs independently prove the advance or company authorization. Gold was not
loaded into application/model inputs. The user's web server/database and port
8000 were not contacted.

The LIVE extraction returned rows2m +1m, printed total3.5m, advance4m,
paper return500k, and invoice gross3.24m. The draft showed one
`settlement-line-total` finding: row sum3m versus printed3.5m, a 500k difference,
with page1 quotes for both descriptions/amounts and the printed total. Final
state was WAITING; exactly one employee-owned FACT remained open; T/E/S were
UNKNOWN, A4m, P/R0, `instructions=[]`, and no technical problems were reported.
This is fresh LIVE behavior, separate from unit replay and the prior negative
review.

## Evidence and limits

Private run files, DBs, the saved pre-submit DB and screenshots are under
`.runtime/tc05-live-review-20261015/fix-run-final/` (`draft.sqlite`, `run.sqlite`,
`result.json`, `report.json`, `view.json`, `audit.json`, `draft-detail.png`,
`final-detail.png`). The paper source SHA-256 is
`b86695951b340957cba2a39aafc474c77e50d209d9ad2430ff4fe94141378d67`.

The rule detects discrepancies among rows the reader represents. If a model
omits an entire real row without emitting any row marker, arithmetic alone cannot
prove that the list is complete. Invoice description/service admissibility also
remains separate from invoice-number matching. Existing unrelated deletions of
`frontend/link-*.png` were preserved. No user DB write, commit, push, reset or
provider call against the user's running web was made.

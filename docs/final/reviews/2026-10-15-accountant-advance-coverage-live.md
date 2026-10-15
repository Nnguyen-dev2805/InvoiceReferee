# TC01 accountant advance and coverage — isolated LIVE evidence

**Accepted run:** `.runtime/accountant-flow-live-20261015-confirmed/` — one fresh
isolated database, new proposed activity, two original settlement PDFs and one
4m advance voucher. Browser test PASS in 1.4m. The user's running database was
not read or changed. No commit, push, reset, or subagent was used.

## Scope and tested source

- Branch `final`; base `HEAD=38d8da3a8b50d7b117a313a2498916302071e55b`. The checkout
  remained dirty with this implementation and earlier shared changes; this
  evidence describes that working tree, not the base commit alone.
- Runner: `frontend/e2e/accountant-advance-coverage.spec.ts`; config:
  `frontend/playwright.accountant-flow.config.ts`.
- Provider mode `LIVE`; OCR/model calls completed. Playwright recorded no
  console errors. It saw three aborted PDF-preview GETs during navigation; all
  API mutations in the accepted run returned 200.
- Context digest:
  `707c9b27be320c266129084354f638020cf31ab304addf61b85934ba67022d1d`.
- Case `case:c21f9b8a3fe248b067e5`; activity
  `activity:proposed:590ca62135f8401d8219623cc208d011`; final version 7. The
  proposed activity stayed `PROPOSED`.
- Live clock, UTC: advance event `2026-10-04T17:00:00Z` (5 Oct, UTC+7),
  accountant acceptance `2026-10-15T02:30:34.784Z`, coverage
  `2026-10-15T02:30:36.565Z`. No frozen test clock was used.
- Input SHA-256:

| Input | SHA-256 |
| --- | --- |
| `report_hoan_ung.pdf` | `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c` |
| `hoa_don_dien_tu.pdf` | `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019` |
| `03-bien-nhan-chuyen-khoan.pdf` | `f8dd97896dd8acaf6f34c75186756672ff41ec9beb5490b56fe71bcf3601c709` |

## Accepted run gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Fresh case and settlement intake | PASS | Before advance, no money-history rows; `A`, `P`, `R`, `S` were UNKNOWN. No `activity:tc01` fixture was used. |
| Extraction | PASS with human completion | Settlement extraction gave `E=3.240.000`, declared advance `4.000.000`, invoice `00000101` matched. Voucher extraction gave 4m, `FT-TC01-0001`, 5 Oct, COMPLETED, `TU-TC01`; payer was missing and was entered from the saved original voucher. Missing values are not counted as OCR success. |
| Activity link and acceptance | PASS by accountant confirmation | `TU-TC01` did not identify the new activity in the tenant catalog. Accountant confirmed the link with a reason. The stored acceptance has 11 source refs spanning both the settlement paper and advance voucher, plus actor, time and proposed-activity scope. No conflict or authority grant was overridden. |
| Durable source and money write | PASS | Isolated DB has three attached source files, one persisted advance draft and one confirmed/allocated `ADVANCE_RECEIVED` of 4m. DB audit contains `READ_ADVANCE_DRAFT`, `RECORD_ACTUAL`, and `ACTIVITY_ACCEPTANCE_FROM_ADVANCE`. Reload retained the records. |
| Paper-declared employee return | PASS with explicit distinction | The settlement paper declares a 760k employee return. Coverage UI surfaced that claim as paper text, not a received-money event. The accountant's recorded reason says the company had no corresponding receipt transaction in the checked history; `R=0` is the accountant's scoped assertion, not OCR or bank verification. |
| Coverage and admission | PASS, accountable human assertion | Accountant recorded period, bank fund, opening balance, required flow kinds, witness source/page/quote, reason, server time and ledger version `1`. `coverage_current=true`; no open issue remained. |
| Financial result and reload | PASS, conditional on that assertion | `T=E=3.240.000`, `A=4.000.000`, `P=R=0` KNOWN, `S=-760.000`; state `READY_TO_EXECUTE`; one `COLLECT 760.000` instruction `ISSUED`. Reload preserved it. `execution_state=NOT_STARTED`: no money was collected and the case was not closed. |
| Actual employee return | PASS in deterministic integration test | `test_f01_completed_return_closes_the_loop` starts with `COLLECT 760.000`, records a confirmed `EMPLOYEE_RETURN 760.000`, reconfirms coverage, then asserts `R=760.000`, `S=0`, `SETTLED`. This regression is in the full Python suite; this actual-return branch was not run in the LIVE browser. |

Coverage is an accountable confirmation that the accountant checked the stated
history. The accepted run did not upload a bank statement or independently query
a bank. The 760k paper claim remains distinguishable from money actually received;
do not represent the issued collection as an executed or independently verified
bank transaction.

## Other isolated LIVE attempts retained

These attempts used separate local databases. They are not counted as accepted
business-result evidence:

| Directory | Outcome |
| --- | --- |
| `.runtime/accountant-flow-live-20261015/` | OCR omitted payer; the first correction guard stopped before money recording. This exposed the missing-field correction defect. |
| `.runtime/accountant-flow-live-20261015-retry/` | Browser completed and produced `COLLECT`, but its coverage reason said no return while the settlement paper declared 760k. Kept as a test artifact, rejected as a valid business attestation. |
| `.runtime/accountant-flow-live-20261015-final/` | Browser stayed on the dossier overview tab; stopped before voucher upload. This exposed a missing Playwright tab selection. |
| `.runtime/accountant-flow-live-20261015-verified/` | Browser completed after the UI warning was added. A subsequent date-only extraction exposed a UTC/local-day comparison bug; this run predates that fix and is superseded. |
| `.runtime/accountant-flow-live-20261015-accepted/` | API rejected a date-only OCR value because comparison used UTC day. Fixed by comparing the source and submitted date in the Vietnam business timezone. |

The final run also verifies acceptance provenance for the settlement document and
handles the date-only OCR value. The deterministic suite verifies those two
regressions directly.

## Artifacts

- Passing Playwright evidence, trace, video and screenshot:
  `.runtime/accountant-flow-live-20261015-confirmed/evidence/` and
  `.runtime/accountant-flow-live-20261015-confirmed/playwright/`
- Passing isolated DB and uploaded sources:
  `.runtime/accountant-flow-live-20261015-confirmed/app.sqlite` and
  `.runtime/accountant-flow-live-20261015-confirmed/uploads/`
- Passing provider artifacts:
  `.runtime/accountant-flow-live-20261015-confirmed/artifacts/`

All `.runtime` evidence is local and ignored by Git. No provider credentials
were changed.

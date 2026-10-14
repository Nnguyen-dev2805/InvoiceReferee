# TC08/TC23 core fixes + F02/F03 reruns — implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `a98b7f2f`. No commit or
push (no Git authorization); no database reset; no checkout; no subagent. A
concurrent agent is editing `frontend/src/features/{approval,dossier,questions}.tsx`
and added `docs/final/reviews/2026-10-14-langsmith-wiring.md`; those are preserved
and untouched.

Fixes the two data failures of
[`.runtime/fourcase-live-20261014-155735`](../../../.runtime/fourcase-live-20261014-155735)
(branch/route checks passed; financial-data + economic-identity checks failed).

## Write set, consumers, completion

| Fix | Files | Consumers | Gate |
| --- | --- | --- | --- |
| TC08 disputed amount | `reconciliation/admission.py`, `reconciliation/policy.py`, `domain/case.py` (`disputed_expense_ids`) | Reconciler → `_commit_assessment` | disputed cost `incurred` UNKNOWN + `eligibility` UNKNOWN + no payment; `expense:allocation` FACT (both numbers + 260k); no generic `expense:payer` |
| TC23 economic identity | `reconciliation/admission.py::_economic_key` | `Expense.economic_key` | identity from the bound document, not the first invoice |
| Identity reaches dedup | `reconciliation/service.py` (`economic_keys`), `domain/case.py` (`AssessmentResult.economic_keys`), `workflow/service.py` (`_obligation_owned_elsewhere`, `_issue_instruction`, `_economic_keys_for`) | usage registry / anti-duplicate | LIVE path records/checks the identity admission produced |
| F02/F03 non-negative return | `reconciliation/document_arithmetic.py` | arithmetic gate | refund/reimburse compared to `max(...,0)` |

No schema change (the new `economic_keys` rides inside the existing
`case_conclusions.payload_json`; `disputed_expense_ids` inside `AssessmentInput`).
Shared files (`admission.py`, `service.py`, `domain/case.py`) were the only ones
touched; the concurrent agent's frontend files were not modified.

## RED → GREEN (backend)

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Behaviour | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| disputed amount not verified money | `tests/unit/test_disputed_amount_admission.py` | E=KNOWN 3.5m, eligibility ELIGIBLE, payment present | 5 passed |
| per-cost economic identity | `tests/unit/test_economic_identity.py` | all three rows keyed to 00002301 | 3 passed |
| LIVE dedup/usage on the bound identity | `tests/integration/test_economic_usage_dedup.py` | `usage_registry` empty on the LIVE path | 2 passed |
| TC23 AUTHORITY + 3 keys | `tests/integration/test_tc23_authority_and_correction.py` | — | 2 passed |
| correction/revision + no waiver | `tests/integration/test_dispute_correction.py` | — | 3 passed |
| F02/F03 non-negative return | `tests/unit/test_document_arithmetic.py` | F02 false `settlement-return` FACT (live-observed) | 13 passed |

Backend suite: `rtk proxy uv run --no-sync pytest -p no:cacheprovider` → **571
passed / 0 failed**. Frontend (Node 24.19.0): `npm test` → **27 passed / 2
skipped**; `npm run build` → exit 0.

## LIVE reruns (original PDFs, current source)

Harness `.runtime/fourcase-fix-20261014/` (git-ignored; copy of the observed
harness, pointing at the current source). Real Mistral OCR + X-Kiro
`qwen/qwen3.7-flash:free`, SIMULATED independent context, clock
`2026-10-10T18:00:00+07:00`. Full `CaseWorkflow → evidence worker → admission →
Reconciler → commit`. Source hashes unchanged from `identity.json` (TC08 report
`2e6cee3a…`, invoice `3211a01c…`; TC23 report `0c7274b3…`, invoices `294e59c2…`,
`0c94bce5…`).

| Case | State | Instructions | Result |
| --- | --- | --- | --- |
| **F02** | READY_TO_EXECUTE | **PAY 400000** | T=E=5.4m, A=5m, S=400k; no issues |
| **F03** | SETTLED | **none** | T=E=A=4.32m, S=0; no issues |
| **TC08** | WAITING | **none** | T/E/S **UNKNOWN**, A=4m KNOWN; FACT `expense:allocation` (3.5m vs 3.24m, lệch 260k, owner employee, 15 refs) + `expense:T`; **no** `expense:payer` |
| **TC23** | WAITING | **none** | T=E=8.64m, A=9m, S=−360k KNOWN; **AUTHORITY** `RECOGNIZE_COST` → approver |

TC23 admission identities: `expense:1` = `expense:2` =
`invoice:…HÒA BÌNH:00002301`; `expense:3` = `invoice:…MỰC IN VIỆT:00002302` —
three rows, sum 8.64m, no double count.

### Numeric-provenance / arithmetic cross-check

The disputed 260k and the F02 zero-refund both pass without a false positive:
F02's paper (advance 5m < cost 5.4m) has a verified-zero refund and a 400k
reimbursement, and its arithmetic gate is clean.

## PASS/FAIL per dimension (independent)

- **Xử lý / branch routing**: F02 PAY 400k, F03 SETTLED no instruction, TC08
  WAITING no instruction, TC23 AUTHORITY no instruction — **PASS**.
- **Dữ kiện tài chính (financial facts)**: TC08 T/E/S UNKNOWN with A=4m KNOWN and
  no issued money — **PASS** (was FAIL_FALSE_KNOWN). F02/F03 figures exact —
  PASS.
- **Economic identity**: TC23 three rows, first two share 00002301, third has
  00002302 — **PASS** (was FAIL_ECONOMIC_KEY).
- A job that exits 0, or a correct final state, is not by itself a full PASS;
  each dimension above is reported separately.

## Constraints honoured

- No policy relaxed and no PDF/gold edited; no native-text bypass and no sample
  data added — the existing OCR pipeline is unchanged.
- The disputed cost keeps BOTH source numbers (3.5m declared, 3.24m evidenced)
  and the 260k difference; nothing is silently cut to 3.24m or taken as 3.5m.
- The verified advance history (A=4m) is retained; only the disputed cost's
  amount is UNKNOWN, not every figure.
- A generic approval/EXCEPT_POLICY decision does not waive the dispute FACT
  (proven in `test_dispute_correction.py`); a new valid basis at the next
  revision is consumed.
- The identity is not derived from file/row order; no valid row is lost and no
  invoice is counted twice.
- AUTHORITY (TC23) does not turn established figures UNKNOWN.

## NOT_RUN / remaining

- The full 25-case Hoangha rerun, Docker, public hosting and the practitioner
  pilot remain NOT_RUN (out of scope).
- Verify Core4/Escalation5 remains NOT_RUN (`data/kiem-thu` absent).
- The browser check was run for **TC08 only** (see below); F02/F03/TC23 browser
  were NOT_RUN.

## Browser evidence (TC08)

Dedicated pinned-clock LIVE server + built frontend + real socket
(`.runtime/fourcase-fix-20261014/server.py`, `browser.mjs`):
`POST /settlement/draft` 200, `POST /submit` 200. The dossier (`TC08-after.png`)
shows T / E / C / unpaid / S as "—" (chưa xác minh), A = 4.000.000 đ, state
"Chờ xử lý ngoại lệ", the dispute + T issues, and **no** collect instruction.
Conclusion BLOCKED, `allowed_effect=None`, 0 instructions.

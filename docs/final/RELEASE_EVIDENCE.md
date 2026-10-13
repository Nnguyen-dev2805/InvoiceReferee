# Release evidence — data/pipeline remediation (R0–R8)

This records the observed evidence for the PDF-data and pipeline remediation plan
([2026-10-13-du-lieu-pdf-va-pipeline-kiem-thu](../superpowers/plans/2026-10-13-du-lieu-pdf-va-pipeline-kiem-thu.md)).
Results and machine artifacts live under ignored `.runtime/evidence/`; only this
filtered summary is published. It is not a claim that the whole competition is
met — the practitioner pilot, public hosting, adaptive threshold (T11) and the
final contest handoff remain outside this plan.

## What changed

| Task | Deliverable | Commit |
| --- | --- | --- |
| R0 | Snapshot locked (HEAD, baseline, existing counterexamples) | (no code) |
| R1 | `scripts/sinh_du_lieu_kiem_thu.py` + `scripts/du_lieu_kiem_thu/*`: 15 cases with real staged PDFs, literal 3-layer gold, source resolver | 81c45067 |
| R2 | Publish `data/kiem-thu`, retire `data/evaluation` + old generator, move UC-03 to `data/tham-khao/uc-03` | 2918f83f |
| R3 | Named money/instruction seams, profile-scoped grants, versioned migration | d99bef60 |
| R4 | `runtime.build_workflow` reader-per-mode; durable recoverable submit job | c0b058b5, 4a7e42dd |
| R5 | Typed context importer; the first 6 cases run through the raw pipeline | 53a9c011 |
| R6 | Role workspaces (UX01) | cc16347e |
| R7 | Scorer direction/beneficiary/count; real Core4/Escalation5 | c7ba4314 |
| R8 | M0 LIVE + LIVE baseline; extractor fix; this evidence | (this commit) |

## Tests (fresh, this session)

- Backend: `uv run --frozen --python 3.12 pytest` → **244 passed**.
- Frontend: Node 24.19.0 `npm test` → 6 passed; `npm run build` exit 0;
  `playwright test` → 9 passed.

## M0 LIVE (real provider calls)

`invoice-referee m0 --input data/kiem-thu/ky-thuat --mode live` — all four probes
read successfully; native text without OCR, both scans and the non-document via
OCR (`mistral-ocr-latest`):

| kind | ok | used_ocr | chars | ms |
| --- | --- | --- | --- | --- |
| text | true | false | 48 | 30 |
| clear_scan | true | true | 48 | 1702 |
| unclear_scan | true | true | 48 | 1464 |
| non_document | true | true | 38 | 1242 |

## LIVE baseline (real provider calls)

`invoice-referee evaluate --dataset data/kiem-thu --suite development --mode live`
— 15 roots scored against independent gold:

| metric | value |
| --- | --- |
| total | 15 |
| union_dangerous_miss | **1** |
| action_miss | 1 |
| affirmative_miss | 1 |
| correct_auto_completion | 9 |
| unnecessary_question | 3 |
| release | false |

The single union miss is D05 (`dev-relation-conflict`): the generated case does
not actually present two conflicting sources (the review's E2 finding), so the
app's auto-completion is unsafe. D11/D12/D14 raise an unnecessary question
rather than a dangerous miss. Before the R8 extractor fix the same run was
union=3 / correct=0; the fix (merge facts across a root's sources; recognise the
payer/receipt wording) is what moved it to union=1 / correct=9.

## Known limits

- D05 needs a real second conflicting source before it can be a genuine
  relation-conflict case; the app is not wrong to auto-complete the current one.
- The extractor is a bounded literal reader (no model); LIVE monetary accuracy
  depends on it and on real OCR quality.
- T11 adaptive threshold, public hosting and the real-practitioner pilot are out
  of scope and remain unproven.
- Docker build NOT_RUN (docker not installed here).

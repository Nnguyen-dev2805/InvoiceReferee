# TC02 — main versus Railway, 17/10/2026

## Verdict

TC02 source arithmetic is consistent. The Railway failure is an unresolved
`printed_total` on the settlement paper, later shown by the frontend as an
arithmetic contradiction. This is not evidence that 5,000,000+400,000 differs
from5,400,000. The separate TC02/TC11 selector is weak-purpose ambiguity.

The failing Railway state was obtained from two actual saved reports and its
LangSmith traces, then deterministically rebuilt offline through main's draft
mapper. A fresh main LIVE read with temporarily selected Kimi did NOT reproduce
the unresolved field. A later single Groq extraction against reconstructed exact
Railway input also returned FOUND. No claim that the underlying intermittent
extraction problem has been fixed.

## Source / scope

- Main HEAD2730b353d306382c8c32f0cb2bf3299f3e808ccb, with existing dirty changes.
- GitHub Railway deployment7134567183 identifies the same SHA and success status;
  production health LIVE, Python3.12.15. Local Python3.12.13.
- Another agent changed document_validity/ocr_quality/prompts/service while this
  diagnosis ran. Fingerprints recorded before/after; extraction.py and arithmetic
  code pertinent to the rejected field remained unchanged. This was NOT a clean,
  frozen whole-diff acceptance run. No edits to application code by this agent.
- New private diagnostic DBs/artifacts under .runtime/tc02-main-diagnosis-20261017/.
  No submit, financial instruction, bank action, port8000 restart or deploy.
- Production inspection used normal demo read access and existing trace credentials;
  no production case/source/financial edit or re-read was requested.
- Graph tierVerify, bounded symbols/call paths; no exposed project-generation or
  coverage tool. Source snippets plus scoped fallbacks; coverage UNKNOWN, not audit.

## Original PDFs

Invoice03e5473e19ce2c368cc1b696afd21f7e687c8170b094f9b19bbae4c6f4ce1d6d:
subtotal5,000,000 + VAT400,000 =5,400,000.
Paper5361b509da576e842896bf9df302af98336a76dd4406019af1da50cf3d3fcfe2:
one cost row5,400,000; printed aggregate5,400,000; advance5,000,000;
requested extra400,000. Text and rendered page inspected; PDF/context/gold unchanged.
With valid admitted costs and money history, the intended TC02 result is PAY400,000;
that financial action was not exercised by this read-only diagnostic.

## Actual Railway failures

Case case:5d1c6c1cf786a728f424, trace970cd006-4011-503e-bf3d-7366ee718cc0,
started12:21:49 Asia/Saigon; case case:fe5e1a4bd2282c159750,
trace0cae4570-46e6-57c8-8a7d-efd97196c0e2, started12:40:38 Asia/Saigon.
Both use the exact original two PDF digests above. Each trace has2OCR stages,
1confidence review and2extractions; all LLM spans SUCCEEDED, model returned
openai/gpt-oss-20b. These historical failures are not the later local quota429.

Both saved reports contain:
- cost row amount FOUND5400000 and invoice ref00000201;
- declared_advance FOUND5000000, printed_reimbursement FOUND400000;
- printed_total UNREADABLE, value null, no surviving refs;
- paper profile_findings[], validation profile_status CLEAR/blocking_count0;
- arithmetic finding settlement-line-items-unresolved, mentioning ONLY
  aggregate total UNREADABLE, not a numeric inequality.

The same finding, wording and row refs rebuild through the current main mapper.
This reproduces the screenshot downstream using actual production evidence,
without another production model call or changing a source value.

## Where the loss occurs, and what is still unknown

`extraction.py:_validate_field` can turn a field into UNREADABLE when its raw
state says so, alternatives lose source support, page is invalid, exact quote
is absent from its page, or normalized value is unsupported by that quote.
`document_validity.validate_document` would emit CRITICAL_FIELD_UNVERIFIED or
QUOTE_NOT_IN_SOURCE if its later checks performed that downgrade. The production
validation trace has zero such findings and already-unreadable printed_total.
This localizes the failure to model field output / extraction source validation,
not the subsequent arithmetic rule or its numeric-confidence downgrade.

Important limit: production traces store parsed_json_summary/count/hash, not
raw returned field objects or the reason a field was rejected. Therefore the
historical raw state versus exact quote/value/page failure cannot be distinguished
from these retained artifacts. Do NOT assert a particular malformed quote or
blurry money token as a proven historical cause.

Offline reconstruction of the paper LLM user input, using cached real OCR and
the production source/document IDs, matches the exact user_sha256 for BOTH
failing production traces. The extraction system prompt hash also matches:
7603da73d763a74d5d4a87018ecc37b2b4655696062a730bcfbb2142d92cd45b.
The input contains the proper total row. This rules out a different PDF, missing
paper input or a different paper extraction prompt in the compared reads.

## Runs performed

1. Main LIVE/default Groq:2real OCRs, then rate-limit wait exceeded the pass deadline.
   Script raised; full error log retained in live.log, artifacts/DB in live-groq/.
   This new attempt does not reproduce the historical server error.
2. User-approved temporary Kimi, same main working tree, own DB, same2PDFs/common
   catalog: HTTP200,30.8s, printed_total FOUND5.4m, no arithmetic finding,
   processing_status ready.3LLM HTTP200 (confidence+2extract). Evidence captures
   fields before/after validation, actual OCR and provider requests/responses.
3. One bounded Groq paper-only extraction from cached real OCR: FOUND5.4m,
   supported quote `Tổng cộng |  | 5.400.000`.
4. One bounded Groq paper-only request with reconstructed production source IDs
   and exact production prompt/user input hashes: same FOUND result. No extra OCR,
   no schema repair, no application/model fallback and no production mutation.

The latter probes establish that this request can succeed with Groq too; they
are not grounds to claim Kimi or a redeploy definitively fixes the historical bug.

Diagnostic setup note: an early cached probe attempted to read attached sources
from the private test DB and found none (the draft endpoint accepts transient
uploads); it failed before any provider call. Subsequent probes correctly used
the captured typed OCR. The fresh main read tests the draft extraction API, not
full persisted upload→submit→settlement execution. No claim that PAY was issued.

## Why TC11 is also suggested

common context gives TC02 andTC11 identical purpose and date, same employee.
Neither uploaded paper establishes TU-TC02 as a strong advance reference. The
weak matching branch only compares normalized activity purpose/name and returns
all matching candidates. It never automatically chooses one.
`linking.py:_weak_candidates` writes candidate.amount from weak_amount, which
here is the paper's declared advance5m, not each candidate's actual ledger.
TC11's own scoped ledger has advance6m. Showing5m beside TC11 is misleading
comparison metadata, not proof its ledger changed. SelectingTC02 resolves only
this association question, not printed_total=UNREADABLE.

## Recommended bounded fixes (not implemented here)

1. Preserve raw rejected field and structured reason MODEL_UNREADABLE /
   QUOTE_NOT_IN_SOURCE / VALUE_NOT_SUPPORTED / PAGE_OUT_OF_RANGE in private
   diagnostics and source-bound issues. Keep the safety guard; do not guess0 or
   substitute invoice/row total for a claimed paper aggregate.
2. Use existing bounded recovery for the affected printed_total from its actual
   total row on cached OCR; require exact page/quote/value support before reuse.
   No whole-root reread loop, lowered confidence or edited gold/PDF.
3. Split UI labels: unresolved read/provenance ≠ verified numerical contradiction.
   This screenshot should ask to verify/read the aggregate, not assert bad math
   or demand a corrected paper when the source is already consistent.
4. Label candidate declared versus ledger advance separately; preserve explicit
   user selection when multiple activities genuinely remain plausible.
5. Before acceptance, regression the actual failed reports and raw-candidate
   counterexamples, plus genuine wrong totals. A fresh successful model call is
   insufficient evidence that the original issue is repaired.

## Evidence index

railway/case_* .json and *-trace.json: original case views and LangSmith runs.
railway/*-rebuilt-draft.json and comparison.json: deterministic failure rebuild.
input-hash-comparison.json: exact serialized-input reconstruction.
live-kimi/: fresh read, validation-stages, llm-http and summary.
live-groq/,live.log: quota-blocked fresh run; never discarded.
groq-paper-raw/parsed.json,railway-exact-probe-*.json: bounded cached probes.
source-before.json/source-after.json: changing working-tree fingerprints.
base-HEAD-reference/: Git HEAD references; service's original dirty content is
NOT reconstructed by HEAD (recorded initial hash differs). Not mislabeled as
an original working-tree source snapshot.
main-working-diff-after.patch: other-agent diff at the end, preserved/read only.

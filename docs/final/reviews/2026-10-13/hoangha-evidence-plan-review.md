# Independent Plan Review: Hoangha Evidence Pipeline

**Plan reviewed:** [`docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md`](../../../superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md)
**Review type:** Read-only plan review; no plan, code, contract, or data was changed.
**Verdict: NOT READY**

## What this plan proposes

The plan replaces final's current LIVE transcription path with all-page Mistral OCR, conditional confidence review, document classification and typed extraction through final's configured X-Kiro client, source validation, and Hoangha evidence matching. It keeps final's workflow and database, and says financial equations and policy remain outside scope.

The sequence and most accepted decisions are represented. The plan is not ready to execute because it currently exceeds final's per-job model-call budget, does not make the no-financial-effects boundary enforceable at the actual workflow seam, and leaves parts of the accepted Hoangha algorithm and OCR-confidence behavior underspecified. There are also unresolved portability and interface-contract issues.

## Ranked findings

### Must fix before implementation

1. **Per-document model calls exceed the existing job budget** (`plan:L153-L160`, `plan:L173-L180`, `plan:L193-L200`, `contracts:L179-L181`)
   - **Evidence:** Classification and extraction are separate stages; the interfaces accept one `OcrSourceResult` at a time, and the tasks describe those stages per document. Final currently allows up to 8 files per case and 12 LLM attempts per job. Eight files × classification plus extraction already requires 16 attempts, before confidence review, schema repair, suggestion resolution, or retries.
   - **Problem:** A valid maximum-size submission cannot complete within the accepted `RunBudget`; failures would depend on document count and where the budget is consumed. The plan says “bounded” but does not specify batching or change the applicable ceiling.
   - **Correction:** Specify the call schedule and hard upper bound against the existing 12-attempt budget. For example, batch classification and extraction by compatible type while preserving the required classify-before-extract dependency, or propose a separately versioned technical-ceiling change with evidence and authorization. Add a worst-case 8-file integration test that includes low-confidence candidates, one repair, and suggestions, and asserts the bound and visible unresolved behavior when exhausted.

2. **The financial side-effect boundary is not closed at final's real consumer seam** (`plan:L7`, `plan:L58-L59`, `plan:L224-L234`; `contracts:L33-L40`, `contracts:L49-L60`, `contracts:L163-L164`)
   - **Evidence:** Final's current assessment input is built from `Transcription` and can create finance facts. The plan says evidence proposals may pass into `build_assessment_input`, then says to let existing admissibility/reconciliation determine what can be used. The current contract permits facts only after source-role, positive-predicate, binding, quality/conflict, and locator checks; an exact OCR quote by itself is not enough.
   - **Problem:** “Existing admissibility” can be read as permission to map extracted candidates or matcher links into finance facts during this integration. That would cross the stated boundary even if no equation or policy function changed. The repeated assertion that there are no side effects does not define the allowed mapping.
   - **Correction:** State explicitly that this plan stores and exposes `ReadResult` evidence analysis only; it does not add or alter mapping from these candidates/links into `AssessmentInput.expense_facts`, confirmations, ledger/coverage, `Fact.KNOWN`, or finance events. If any existing path consumes it, name the exact field mapping and prove it remains proposal-only. Add an integration assertion over the actual `CaseWorkflow` submit/preview path that the evidence pipeline cannot change `FinancialEffect`, money events, zero-flow claims, or financial conclusions.

3. **“Full Hoangha matcher” is not specified precisely enough to reproduce, and the allocation rule is a new interpretation** (`plan:L23-L25`, `plan:L57`, `plan:L195-L202`; Hoangha `paper_evidence_matching.py:L67-L107`, `:153-L203`, `:372-L403`)
   - **Evidence:** The plan gives score weights and thresholds but omits the exact normalization and similarity functions: accent-folded text normalization, `SequenceMatcher(..., autojunk=False)`, party-token filtering/overlap, and the thresholded explanation signals. The accepted user decision was to use the full current Hoangha logic. The plan also adds a new allocation encoding: each settlement row must repeat the normalized source-document number and its amount. Hoangha itself auto-links one source to the first qualifying row, then demotes reuse on later rows; it does not implement this explicit-allocation protocol.
   - **Problem:** An implementer could produce a materially different matcher while satisfying the listed weights. The new allocation protocol is a plausible way to implement the accepted “explicit, amount-bounded allocation” rule, but the exact source-number requirement was not directly approved. The plan currently presents this interpretation as settled contract.
   - **Correction:** Pin the port to a named Hoangha revision/source and specify or import the exact normalization, similarity, ordering, original/supporting classification, unmatched-link behavior, and post-match amount checks. Keep the accepted allocation extension separate from “Hoangha behavior”; label its exact row-reference representation as a lead decision or derive it from an existing approved case format. Add golden tests from Hoangha plus adversarial exact-ID, reused-source, multiple-invoice, and payment-proof cases.

4. **Provider-stage signatures conflict with final's asynchronous interface contract** (`plan:L53-L59`, `plan:L132`, `plan:L153-L159`, `plan:L193`; `contracts:L249-L257`)
   - **Evidence:** The plan declares `ocr_file`, classification, extraction, validation, matching, and `read_root` with ordinary synchronous signatures, although several stages call remote providers. Final's contract requires `EvidenceReader.read(...)` and `CaseWorkflow.run_job(...)` to be async; the current worker/job lifecycle and provider boundary are built around that contract.
   - **Problem:** The plan does not say whether remote calls block the event loop, run in a thread, or are async. That choice affects Stop responsiveness, worker concurrency, timeout/cancellation, and whether the stated simple worker remains bounded.
   - **Correction:** Make provider-calling interfaces explicitly async and define the composition boundary, or name the exact existing executor adapter that safely contains synchronous clients. Keep pure validation/matching synchronous where appropriate; separate the model suggestion call from the pure matcher so return types and budget consumption are unambiguous. Add a blocked-provider/Stop test proving the event loop and per-root job controls remain responsive.

5. **The corpus import scope and source are not portable or fully defined** (`plan:L236-L255`; decision note `ocr-input-policy-discussion.md:L137-L143`, `:171-L180`)
   - **Evidence:** The accepted Q10 choice was described as using all Hoangha case sets and keeping all 16 types, then inventorying cases. E8 narrows the import to two `data/testcase_uc3*` roots. The current Hoangha worktree also contains other case roots; the plan does not define which are formal/in-scope or why they are excluded. The importer has no source-root argument, source revision/digest, or checked-in source packet; the named roots currently live in the separate `.worktrees/hoangha` checkout, which is machine-local. Gold files also need a named, deterministic destination separate from runtime inputs.
   - **Problem:** Another developer or CI runner may not have the Hoangha worktree at that path, and “every formal case” has no reproducible denominator. The imported manifest could silently represent only the two UC-03 directories while appearing to cover all approved Hoangha cases.
   - **Correction:** Define the formal corpus inventory and exclusions from the source README/manifest, pin the source repository revision and input digests, and make the importer consume a portable checked-in/vendor-independent source bundle or an explicit source-root argument with a clear missing-source failure. Specify separate `inputs/` and gold/oracle paths and test that runtime manifests cannot reach gold. If the approved scope is only UC-03, state that as a deliberate scope clarification rather than calling it all Hoangha case coverage.

### Should fix before implementation

6. **Confidence handling has no executable definition of “critical” or review outcomes** (`plan:L18`, `plan:L33`, `plan:L132-L141`, `plan:L173-L180`; Hoangha `process_settlement.py:L314-L365`, `ocr_quality.py:L11-L50`)
   - **Evidence:** The plan tests for missing confidence on a critical quote, but does not define which fields are critical for each of the 16 types and `SETTLEMENT_FORM`, how OCR word offsets map to an extracted quote/block, or what `ConfidenceReview` outcomes permit continuation versus require unresolved. Hoangha's candidate collector ignores words without numeric scores; its pipeline calls the confidence model only when candidates exist and then interprets per-block assessments using blocking-field rules. The accepted decision tightened this behavior for missing critical confidence.
   - **Problem:** The implementer cannot write deterministic tests for the central guard from the current text. A field could be marked unresolved simply because an unrelated word lacks a score, or incorrectly accepted because its quote cannot be mapped back to scored words; an LLM review could also have no defined effect.
   - **Correction:** Add a per-profile critical-field matrix, a precise locator/word-offset mapping rule, and the allowed confidence-review state transitions. Test missing/non-numeric confidence on critical and noncritical fields, low-score critical/noncritical words, malformed/omitted candidate assessments, and “review says readable” without allowing the model to rewrite OCR or provide the field value.

7. **The cache key omits the tenant required by the current contract** (`plan:L222-L229`; `contracts:L157-L158`)
   - **Evidence:** The plan lists source digest, OCR/extraction models, prompt/schema, confidence threshold, and matcher version. The current contract keys cached reads by tenant plus source digest and reader/config dimensions.
   - **Problem:** The cache contract can be implemented without tenant isolation. Identical file bytes submitted in different tenant scopes could then share a read result/artifact reference contrary to the contract.
   - **Correction:** Include tenant in the cache identity and test equal source digests across two tenant scopes do not share cached results or artifact ownership. Keep policy/decision results uncached as the contract requires.

8. **The role contract drops the distinct payment-evidence role** (`plan:L45`, `plan:L54-L56`, `plan:L90-L95`, `plan:L153-L160`; decision note `ocr-input-policy-discussion.md:L108-L115`, `:159-L163`, `:171-L180`)
   - **Evidence:** The accepted role taxonomy includes declaration, expense/original evidence, payment basis, supporting document, and unknown. The plan says “four document roles plus UNKNOWN,” but E4 only maps types to declaration/original/supporting/unknown, and maps `PAYMENT_PROOF` to supporting by default without defining how the separately accepted payment-evidence role is represented. Q14 allows multiple roles only when each role has its own OCR evidence; Q28 makes payment proof supporting by default.
   - **Problem:** The DTO and compatibility map cannot unambiguously represent a payment proof that is both supporting and a payment basis when the source contains separate evidence for those roles. This also risks confusing “supports the expense” with “supports who paid.”
   - **Correction:** Enumerate all role values exactly and define `PAYMENT_PROOF`'s default supporting role plus the conditions/evidence locator required to add `PAYMENT_EVIDENCE`. Add compatibility and non-duplication tests for a payment proof, a card slip, and a document assigned multiple roles.

9. **Raw artifact retention and limits are not contracted** (`plan:L46-L48`, `plan:L75`, `plan:L112-L119`, `plan:L222-L229`)
   - **Evidence:** E2 requires retaining complete raw provider JSON under the local artifact root; E7 adds references to durable job/cache state. The plan does not define retention/deletion, maximum OCR artifact bytes, or behavior when artifact persistence fails. Final already has limits for upload size, total input, pages, and processing time (`contracts:L175-L181`).
   - **Problem:** “Persist raw OCR safely” does not tell the implementer how to bound storage growth or whether an OCR result may be treated as complete when its audit artifact could not be committed. OCR output can also contain sensitive document contents.
   - **Correction:** Reuse the final artifact root/size limits, define an artifact retention/deletion rule consistent with source retention, and state that failed required artifact persistence leaves the read technical/unresolved. Test oversized provider responses and atomic-write failure. Do not add a second artifact store.

### Editorial defect

10. **E7 repeats Step 2 and shifts the step sequence** (`plan:L224-L232`)
    - **Problem:** The side-effect test appears twice as Step 2, with slightly different wording; later steps continue at Step 3. This makes progress checklists and task handoff ambiguous.
    - **Correction:** Merge the assertions into one side-effect-test step and renumber the remaining steps.

## Explicitly unapproved or still-open assumptions

These are not reasons to reopen accepted decisions. The plan should label them as lead calls or keep them outside its implementation boundary until defined:

1. **Allocation encoding:** requiring the same normalized source document number and a stated amount on every settlement row is an implementation interpretation. The user approved explicit amount-bounded allocation, not this exact representation.
2. **Corpus denominator:** “all formal Hoangha cases” is not tied to an authoritative inventory or explicit exclusion list. The plan's two UC-03 roots may be narrower than the user's accepted “all Hoangha case sets.”
3. **Critical-field and confidence semantics:** the accepted guard exists, but the plan does not define the field matrix, quote-to-word mapping, or review-state transition table.
4. **Artifact retention:** raw OCR persistence was included in the plan, but a retention period/deletion rule was not directly approved or specified in current contracts.
5. **Role compatibility:** the plan's current default map does not fully express the accepted payment-basis role and the conditions for assigning it alongside a supporting role.

## Accepted scope correctly represented

- PDF, PNG, and JPEG only; OCR must cover every page, including searchable PDFs; no native-text bypass (`plan:L15`, `:112-L121`).
- Final remains the workflow/database owner; one simple persisted worker and configured X-Kiro client; no Kimi or second case store (`plan:L16-L17`, `:222-L234`).
- Separate classification and extraction; `UNKNOWN` must not select a guessed schema; `OTHER` uses generic extraction (`plan:L19-L20`, `:153-L162`, `:175-L184`).
- Per-field statuses, source-bound quote/page/block provenance, and one repair attempt (`plan:L21-L22`, `:173-L184`).
- Hoangha score thresholds, exact invoice-number risk, suggestion-only LLM promotion at `>=0.90`, and supporting-vs-original distinction are explicitly called out (`plan:L23-L25`, `:195-L204`).
- The plan states that financial equations, policy, authority, and payment effects are out of scope (`plan:L26-L28`, `:201-L204`). This boundary still needs the enforceable E7 correction above.

## Evidence and limits

Reviewed the plan, accepted decision note, final implementation contracts, and relevant current source paths in both indexed projects. CodeGraph reported current indexes for `final` and `.worktrees/hoangha`; the CodeGraph coverage-check tool was unavailable, so index coverage is unknown. Material source claims above were checked against returned current source snippets, including final's `ReadResult`/transcription and job/cache contracts, Hoangha's matcher and confidence code, and the Hoangha document taxonomy. This is a plan review, not runtime or test evidence; no provider calls or test suites were run.

**Final verdict: NOT READY.** Resolve findings 1–5 before implementation dispatch; resolve findings 6–9 in the plan/contracts before the owning tasks begin. Finding 10 is a checklist cleanup.

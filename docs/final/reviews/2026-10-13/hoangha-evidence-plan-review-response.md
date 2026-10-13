# Independent re-review: Hoangha evidence pipeline

**Verdict: READY WITH REQUIRED REVISIONS.**

**Reviewed:** `docs/superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md`, 342-line working-tree version, SHA-256 `1cf0047a01197e2638814e4cfd5f21fa92db838d9b4c3403985fd52f44f7d2e2`.

**Baseline:** [original review](hoangha-evidence-plan-review.md), [accepted decisions](ocr-input-policy-discussion.md), current final contracts §§2–3/6/8–10, design §§1–4/14, implementation checkpoint and canonical plan constraints. Final source HEAD: `aee7fb38186e4c84c3c5f4c30648fbf76d556176`; Hoangha HEAD: `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`.

This is an independent documentation/source re-review. Only this response was written. No plan, contract, code, dataset, or test was edited; no tests, live providers, indexing, commits, or publishing were run. CLOSED means the plan now specifies a satisfactory correction, not that implementation has passed its gate. The parent added verification anchors and schema vocabulary during review; those additions and the central consumer guard are included in this snapshot.

## Closure of every original finding

| Original finding | Status | Current disposition |
| --- | --- | --- |
| **1. Job model-call budget** | **CLOSED** | Global constraints L20/L24 and E8 Step 6 give `1 classification + 1 conditional confidence + 8 extraction + 1 repair + 1 suggestion = 12` attempts. Retries consume the same budget; more than eight document units and oversized batches produce visible LIMIT results. The eight-unit schedule is a bounded case, not a guarantee that every eight-file submission completes. R4 below addresses the separate request-size enforcement dependency. |
| **2. Financial consumer boundary** | **CLOSED** | Architecture L7, consumer guard L82, and E7 now stop LIVE/REPLAY at stored/exposed evidence. The guard is inside `_assess_and_commit`, covers Answer/Decide/Resume/recording paths, blocks seeded transcription fallback, and exposes `EVIDENCE_ADMISSION_NOT_CONNECTED`. Historical conclusions remain history; changed-basis conclusions are not displayed as current, and stale pending instructions are suspended. The added command-path test closes the earlier submit-only gap. STUB remains an explicit separate path. |
| **3. Full matcher and allocation interpretation** | **OPEN** | The source revision, normalizers, similarities, thresholds, ordering, exact-ID risk, and separately labeled allocation extension are now pinned. The row reference/amount representation is an implementation interpretation of the approved allocation rule; no new approval is required here. However, E6 Step 3's accepted evidence projection conflicts with Steps 7/10's promise to reproduce all Hoangha row statuses, amount checks and golden results. Resolve R2. |
| **4. Async provider interfaces** | **CLOSED** | Interfaces L67–79 make OCR, classification, extraction, confidence review, suggestion resolution and root orchestration async. Validation/matching are pure sync; suggestion resolution is a separate budgeted call. E7 and its test anchors require a provider barrier/Stop race, provider I/O outside transactions, and existing per-root job controls. |
| **5. Corpus scope and portability** | **CLOSED** | E8 identifies exactly 25 v1 plus 50 v2 manifest cases at the pinned revision, a required migration-only `--source-root`, input/gold hashes and checked-in portable results. Generic OCR examples are separate; derived and experimental roots are explicitly excluded. I independently read the two manifests/READMEs and counted 25 and 50 entries. This closes inventory/portability specification, not source-by-source quality verification. |
| **6. Criticality and confidence transitions** | **OPEN** | The pinned profiles, literal schema vocabulary, field-to-word mapping, no-score guard, exact candidate cardinality and diagnostic-only noncritical handling are substantial corrections. E5 Step 5 still omits Hoangha's optional-flag fallback and contradicts its own code-owned criticality rule. Resolve R1. |
| **7. Tenant missing from cache identity** | **CLOSED** | E7 L277 explicitly includes tenant and configuration dimensions, tests equal digests in different tenants, and keeps root matching out of the per-source cache. R3 is a distinct remaining source/artifact ownership issue within one tenant. |
| **8. Payment-evidence role omitted** | **CLOSED** | All five role values, separate document/page role types, `role_refs`, supporting defaults, and conditions for additional `PAYMENT_EVIDENCE` are explicit. E4 requires separate source evidence for multiple roles. Buyer/signature/payment-method text does not establish payer or completed payment; role assignment still authorizes no financial fact. |
| **9. Raw artifact retention and bounds** | **CLOSED** | L26 and E2 specify a private tenant/root/source/version path, source-matched lifetime, atomic writes, lead-chosen 20/40 MiB caps, and technical unresolved behavior for oversized output or persistence failure. The new wording correctly distinguishes upload ceilings from measured OCR limits. R3 below must keep those lifetime/ownership promises compatible with cache reuse. |
| **10. Duplicate E7 Step 2** | **CLOSED** | Numbered Steps 1–8 no longer repeat Step 2; additional guard checkboxes have distinct purposes. |

## Required residual corrections

### R1 — Make the confidence transition independent of accidental model omissions

**Locations:** plan L69, E3 Step 5 (L191), E5 Step 5 (L232); Hoangha `application/process_case.py:566–606` and `policy/document_validity.py:32–80`.

The plan makes `requires_verification` optional, but blocks an exact-accounting field only when it is explicitly true or uncertain digit text is not READABLE. Hoangha first computes an effective flag: use the explicit boolean when present; otherwise use `review_action == ASK_HUMAN`.

**Counterexample:** a low-confidence `total_amount` quote is assessed as READABLE with `review_action=ASK_HUMAN`, while `requires_verification` is omitted. The written E5 rule allows continuation; the pinned Hoangha helper blocks it. This is an unapproved relaxation of the selected confidence behavior, not a schema-mapping nit.

For other profile-critical fields, E5 also requires model `importance=CRITICAL` plus ASK_HUMAN while saying that code criticality cannot be downgraded. An E_INVOICE `template_number` is code-critical; returning `importance=NON_CRITICAL` and ASK_HUMAN must not make it usable solely through that model label. Likewise, an explicitly true verification flag must not disappear merely because the action says CONTINUE.

**Correction:** define the effective verification flag exactly, then specify how code-owned criticality wins when the model importance/action disagrees. Keep missing critical word scores and applicable DEFER_TO_POLICY unresolved. Bind the block assessment through the verified field quote/word overlap; the model must not evade an already mapped critical field by omitting its canonical label. Add named tests for omitted flag + READABLE + ASK_HUMAN, explicit true + CONTINUE, and code-critical/model-noncritical disagreement. Do not change the .85 trigger, rewrite OCR, introduce another confidence call, or apply policy.

### R2 — Separate the pinned matching algorithm from its evidence-only result adaptation

**Locations:** plan E6 Steps 3/7/10 (L251/L255/L258); Hoangha `application/paper_evidence_matching.py:243–281,305–403`.

The selected normalization/scoring/linking behavior can be ported exactly. Hoangha's complete row/result projection cannot be copied unchanged while satisfying the accepted original/supporting distinction and stop-before-policy boundary:

- With no auto-link and no reason, Hoangha labels a row `ORIGINAL_EVIDENCE` at L255–262 despite lacking an original link; the final report must show missing evidence.
- Hoangha's amount check excludes only PAYMENT_PROOF, then falls back to all auto-links (L372–387). An invoice for 100 plus a linked CONTRACT for 100 can therefore produce a 200 total. E6 Step 3 correctly excludes all support-only documents from the original sum.
- A reason creates `policy_exception_code=PAPER_EVIDENCE_EXCEPTION` and an OUTSIDE_POLICY finding in Hoangha (L277–278/L325–337). Final must retain the literal reason as evidence metadata, without importing that policy exception or owner routing. Missing line amount must also remain absent rather than adopting Hoangha's zero fallback at L253.

**Correction:** state that the pinned core algorithm is unchanged, while the final evidence projection applies the already accepted field-state, support/original and no-policy rules. Make this precedence explicit in Steps 7/10 and the gold gate. Require ORIGINAL_EVIDENCE only with an auto-linked original, ALTERNATIVE_EVIDENCE for support-only auto-links, and NO_EVIDENCE otherwise; keep missing-original findings independent of support links. Golden tests should preserve core scores/links and separately assert these deliberate projection differences, allocation portions and metadata-only reasons. Do not add issuer/amount prerequisites to exact-ID auto-link or reopen the approved matcher risk.

### R3 — Specify ownership when a same-tenant cache hit belongs to another source/root

**Locations:** plan L26/L59–64/L84 and E7 L277–284; final `workflow/jobs.py:82–113,160–178`.

The cache is tenant/digest/config keyed, while OCR results and every quote carry a source ID, and raw artifacts are root scoped with the source's deletion lifetime. Current `cached_read` returns serialized results unchanged.

**Counterexample:** two roots in the same tenant upload identical bytes as source A and source B. Reusing A's serialized result for B can retain A's source/role/page refs and A's artifact ownership. Validation against B rejects it, or the API exposes references outside B's source set. Removing A's source can also invalidate B's reused artifact. Tenant isolation alone does not solve this.

**Correction:** contract the cache payload as reusable source-content data and rebind all source-owned refs to the requesting SourceRef on a hit, with a root-owned artifact copy/reference that survives deletion of the other source. Alternatively, restrict reuse with an ownership-qualified cache identity. Keep root-specific links out of that cache. Add one same-tenant/two-root/equal-digest test asserting B-only provenance and independent artifact lifetime. No new artifact service or financial identity is needed.

### R4 — Give the model request caps a concrete contract and task owner

**Locations:** plan L25, E0/E2/E4/E8; final `evidence/trace.py:59–70` and `evidence/xkiro.py:30–62`.

L25 requires effective model input/output limits recorded in the M0 RunManifest. The current manifest has model/prompt/schema/trace/usage fields but no limit fields. The configured X-Kiro adapter has a local 20,000-character response cap and no request-size check. The tasks currently change M0 for all-page OCR, without specifying where the new cap record and preflight check are defined.

**Counterexample:** the root classification/confidence batch contains eight large OCR results. The attempt count fits 12, but no recorded cap exists to decide whether the first request is permitted. An implementer must invent a limit, treat it as unlimited, or stop every batch as unknown.

**Correction:** assign the manifest/configuration contract and request preflight to an explicit owning task, including `evidence/trace.py` and provider-contract tests. Name the cap units, model/config version and evidence origin; distinguish an application payload bound from a provider context-window claim. Specify unknown-cap behavior and verify size before sending, with LIMIT and preserved OCR when oversized. Retain the existing response bound unless a separately evidenced technical change is made. Use offline injected limits in tests; no invented provider window, new vendor/env variable, or live call is needed for this review.

## Accepted decisions preserved

PDF/JPG/JPEG/PNG all-page OCR, current X-Kiro provider, final-owned simple worker, conditional confidence review, separate classification/extraction, all sixteen Hoangha types plus SETTLEMENT_FORM, sourced field states/alternatives, one job-level repair slot, the exact-ID risk, suggestion threshold .90, explicit amount-bounded allocation, and original/support roles remain accepted. Mixed-PDF document IDs and role refs are appropriate evidence refinements; they do not establish economic identity or authorize a financial effect. The official 75-case inventory, separate generic OCR smoke and separately labeled synthetic type fixtures are appropriate coverage units; imported Hoangha decision gold must not become final financial policy.

Batching, the row-reference encoding, eight-unit LIMIT handling and source-matched artifact lifetime are documented technical interpretations. This review does not request another business interview or resolution of Q32–Q34. E0 must promote the evidence contract before dependent code tasks; it must not settle those deferred finance/policy questions.

## Evidence and limits

Verify tier: independently ran `rtk proxy codegraph status` in both checkouts. Final reported 121 files/up-to-date with the earlier-engine warning; Hoangha reported 81 files/up-to-date. No graph generation identifier or `check_index_coverage` tool was exposed, so coverage remains unknown. Used CodeGraph first for relevant symbols/call paths, then exact scoped source reads for material gaps: workflow assessment/callers/view/transcription behavior, cache serialization, RunManifest/X-Kiro, Hoangha matcher projection and confidence helpers. No exhaustive graph-completeness claim is made.

Manifest counting was read-only and exited 0: v1=25, v2=50, v2 declared count=50. This is inventory evidence only. Required implementation, raw pipeline, browser and LIVE gates remain NOT_RUN by this reviewer. The response does not establish operational readiness, extraction quality or financial correctness.

**Dispatch condition:** revise R1–R4 in the plan/canonical evidence contract before the affected implementation tasks begin. Keep E0 as the first gate. No implementation or finance/policy expansion is authorized by this verdict.

---

## Closure addendum — bounded R1–R4 check, 2026-10-14

**Updated verdict: READY for implementation-plan dispatch with respect to R1–R4. None of these four residual corrections remains a dispatch blocker.**

**Current plan snapshot:** 349 lines, SHA-256 `43d99ee241513b46c438bad785f3c879e31b50491323a607700dec100ed23783`.

The earlier **READY WITH REQUIRED REVISIONS** verdict, its reviewed SHA-256, findings and dispatch condition above are preserved as the historical conditional snapshot. This addendum updates only the disposition of R1–R4 against the revised plan; it is not a broad fresh audit or a claim that implementation/tests are complete.

| Residual | Closure | Evidence in the current plan |
| --- | --- | --- |
| **R1 — Confidence transitions** | **CLOSED** | E3 L196 explicitly uses the provided boolean, otherwise `review_action == ASK_HUMAN`. E5 L237 binds the actual field through verified quote/word overlap, applies that effective flag, preserves unresolved critical tokens, and prevents model importance or omitted canonical labels from lowering code criticality. L238 names the four omission/disagreement regressions: `test_readable_ask_human_with_omitted_flag_blocks`, `test_explicit_verification_true_continue_blocks`, `test_code_critical_model_noncritical_blocks`, and `test_omitted_model_field_label_cannot_evade_word_overlap`, with unresolved-field and no-extra-confidence-call assertions. |
| **R2 — Matching core versus projection** | **CLOSED** | Interface L77 and projection precedence L87 distinguish the pinned candidate/link core from the deliberately adapted evidence-only result. E6 L261/L264 require unchanged core scores/links plus separate projection assertions: actual original/support/no-link statuses, original-only sums and allocation portions, invoice100+contract100 yielding original_total100, missing amount remaining `None`, and literal reasons creating no policy exception or owner routing. The previous promise to reproduce incidental Hoangha row shortcuts is replaced by explicit precedence. |
| **R3 — Cache and artifact ownership** | **CLOSED** | L26 and E7 L283 qualify reuse by tenant/root/source ID/digest/configuration. A different owned source with equal bytes gets its own OCR/artifact; cache hits retain the same source ownership. L27 keeps artifacts root scoped and source-lived. L291 names the equal-digest/two-root test: B-only provenance/artifacts, two OCR calls, B surviving removal/reset of A's artifacts, and subsequent same-source/config reuse within B. This selects the ownership-qualified alternative requested in R3, without shared-content lifetime coupling. |
| **R4 — Request caps and ownership** | **CLOSED** | L25 defines versioned application caps of **120,000 serialized input-message characters** and **20,000 response characters**, explicitly excluding a provider context-window claim. Oversized batches become LIMIT without truncation or unbudgeted splitting; provider context-limit errors remain technical. E3 owns `xkiro.py` and `trace.py` at L184–187, including manifest fields `max_llm_input_chars`, `max_llm_output_chars`, `limit_version`, and `limit_origin`. L194 assigns pre-network preflight to `complete_json` and names fake-HTTP/injected-cap tests for oversized requests, manifest cap records and unknown-cap failure. |

**Remaining correction within R1–R4:** none. The plan may proceed through its existing E0 canonical-contract gate and authorized implementation sequence; this closure does not authorize finance/policy integration, live calls or Git actions.

**Verification scope:** read-only comparison of the four prior residuals with their revised plan clauses, task ownership and test assertions. No code exploration, broader findings, product tests or live provider calls were performed. Only this addendum was appended; the prior response text remains unchanged. CLOSED here is specification closure, with implementation/runtime gates still to be executed by their owners.

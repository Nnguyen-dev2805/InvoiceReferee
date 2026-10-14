# Hoangha Evidence Pipeline Integration Implementation Plan

> **For agentic workers:** Follow the task workflow in [AGENTS.md](../../../AGENTS.md#execute-and-hand-off). This is a follow-on plan to the completed R0–R8 work; it supersedes the T5 LIVE text-only reader where they conflict. Use one workflow integrator for shared domain/job/workflow files. Steps use checkbox syntax.

**Goal:** Replace final's cue-based LIVE transcription with an auditable, all-page OCR → confidence gate → document classification → typed extraction/validation → Hoangha evidence matching pipeline, while keeping final as the only workflow and financial decision owner.

**Architecture:** Extend final's `ReadResult` and durable job/read-cache path; do not transplant Hoangha's second repository, database, or settlement lifecycle. Mistral supplies OCR pages/blocks/word confidence and the configured X-Kiro client supplies bounded classification, extraction, confidence review, and suggested-link resolution. This plan ends with a persisted/API-visible evidence report: LIVE/RECORDED_REPLAY results are not passed into `AssessmentInput` or Reconciler yet. Existing finance/policy behavior remains unchanged; a later plan owns the evidence-to-finance mapping.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite/local artifacts, `uv`; Mistral OCR and the configured X-Kiro-compatible HTTP client; React/TypeScript/Vite only for typed API compatibility (no UI redesign); pytest, existing STUB/RECORDED_REPLAY harness, independent case gold.

**Spec:** [accepted OCR/evidence decisions](../../final/reviews/2026-10-13/ocr-input-policy-discussion.md), [design document §14](../../final/ARCHITECTURE_AND_EVALUATION.md), [implementation contracts §§2–3, 5, 8–10](../../final/IMPLEMENTATION_CONTRACTS.md). E0 promotes these decisions into a canonical design/contract section before code tasks depend on them. Financial/policy decisions outside this evidence boundary remain governed by the existing contract.

## Global Constraints

- Accept only PDF, PNG, and JPEG. Every page of every accepted file must go through OCR, including searchable and hybrid PDFs; native PDF text must not bypass OCR.
- Keep `final` as workflow/database/audit owner. Reuse its existing single-process persisted-job model and current concurrency ceilings (2 global workers/jobs, 1 active job/root); no broker, microservices, second case store, or new agent framework.
- Current-code correction: `CaseWorkflow.execute` awaits `_read_sources_for_submit` before command/version validation; `create_app` has no evidence-worker lifespan loop. E7 must enqueue durably after validating the command, return `PROCESSING`/job ID immediately, and drain those jobs in one background asyncio worker started/stopped by FastAPI lifespan. One worker is within existing ceilings; do not claim this is already wired.
- Use the LLM/provider already configured for final (`XkiroClient`); do not add Kimi or a second model vendor.
- OCR confidence threshold follows Hoangha: a meaningful word score below `0.85` creates a confidence candidate. Copy Hoangha's `DocumentProfile.required_fields` and `FIELD_IMPORTANCE_BY_TYPE` as the per-type criticality matrix; add the `SETTLEMENT_FORM` required fields from the accepted paper-form schema. Missing confidence for a quote touching a critical field is unresolved, never a quality pass.
- Classification and extraction are separate sequential model stages. Uncertain classification remains `UNKNOWN` and does not select an extraction schema.
- A source PDF may contain several document units. Classification assigns source-owned page/block ranges; code creates `document_id` from source digest plus the validated range, and extracts/matches each unit separately. More than 8 units or an over-limit batch preserves all OCR and reports the remaining units as `LIMIT`; it never merges their amounts or silently drops units.
- Keep all 16 Hoangha `ExpenseDocumentType` values and add the final workflow's `SETTLEMENT_FORM` type: `E_INVOICE`, `PAPER_RECEIPT`, `CARD_SLIP`, `PAYMENT_PROOF`, `TRANSPORT_TICKET`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`, `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION`, `OTHER`, `UNKNOWN`, and `SETTLEMENT_FORM`. Define `DocumentEvidenceRole` as `SETTLEMENT_DECLARATION`, `ORIGINAL_EXPENSE_EVIDENCE`, `PAYMENT_EVIDENCE`, `SUPPORTING_DOCUMENT`, or `UNKNOWN`; keep it separate from final's existing page-level `EvidenceRole`. Code owns compatibility; `OTHER` gets only generic extraction; `UNKNOWN` gets no guessed extraction. `PAYMENT_PROOF` and `CARD_SLIP` default to supporting; assign the additional `PAYMENT_EVIDENCE` role only when the source independently shows payer, payee, amount, transaction identity/status, with its own locator. Invoice buyer/signature/`TM/CK` alone cannot add that role.
- Per-field states are exactly `FOUND`, `NOT_PRESENT`, `UNREADABLE`, `AMBIGUOUS`, and `NOT_APPLICABLE`. Missing is never numeric zero. Every `FOUND` value carries an exact OCR quote and source/page/block locator.
- Allow one schema-repair call; after that, preserve the technical error and unresolved result. No unbounded retries or confidence/model consensus loops.
- Keep the existing hard budget: at most 8 files, 12 LLM attempts, 10 OCR attempts, and current page/file/total/deadline ceilings per job. Lead call for the call schedule: one batched classification call per root, at most one batched confidence review, one extraction call per classified document, at most one repair call per root/job, and one batched suggestion-resolution call. Count every provider retry against the same 12-attempt budget; when exhausted, leave remaining documents unresolved in stable source order.
- Bound X-Kiro requests with versioned local pilot limits: `MAX_LLM_INPUT_CHARS=120_000` for serialized messages and existing `MAX_OUTPUT_CHARS=20_000` for the response; these are lead-chosen character/size limits, not a claim about the model context window. Reject an oversized batch with `LIMIT`, retaining OCR and unresolved units; never silently truncate or split into unbudgeted calls. M0 measures whether these caps and the selected model are usable; a provider context-limit error remains technical. Record effective limits/model/prompt versions in the manifest.
- Cache reuse is ownership-qualified: `(tenant, root_id, source_id, source_digest, reader_config)`. The `reader_config` includes this ownership key plus model/prompt/profile/schema/representation/requested-fields versions; its hash can use the existing read-cache schema without new shared-content storage. Equal bytes under another source/root trigger a new OCR/artifact, not reuse of another root's refs; unchanged source/basis still reuses the cache within its owner.
- Raw OCR is private derived data stored under `uploads_dir.parent / "artifacts"`, scoped by tenant/root/source digest and version. It has the same lifetime/deletion behavior as its uploaded source; add no independent TTL or new environment variable. Lead-chosen derived-artifact ceilings are 20 MiB/source and 40 MiB/root, using the same numerical caps as existing uploads (these were upload limits, not previously measured OCR limits). Oversized output or failed atomic persistence is a technical unresolved result, never silently truncated or treated as complete.
- Port matcher source and tests from Hoangha commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`, `src/invoice_referee/application/paper_evidence_matching.py` and `tests/unit/test_paper_evidence_matching.py`. Preserve normalized exact invoice reference → `AUTO_LINK`/1.0; otherwise amount 0.60 (within 1 VND), semantic similarity up to 0.30, issuer similarity 0.12/0.20, supporting/non-original type +0.10, capped at 1.00; `<0.50` omitted, `[0.50,0.75)` suggestion, `>=0.75` auto-link. The configured final LLM may promote only an existing suggestion at confidence `>=0.90`.
- Multiple documents may support one expense row. One document may support multiple rows only through an explicit, amount-bounded allocation; supporting documents never count as original expense evidence or duplicate an expense amount.
- **Settlement-form anchor:** `SETTLEMENT_FORM` is an **uploaded paper** settlement form, not final's in-app declaration. When a root has no `SETTLEMENT_FORM`, the pipeline still OCRs/classifies/extracts but **skips matching** and records a `SETTLEMENT_FORM_MISSING` finding (evidence-only; not blocking, not a business issue). This is a lead call resolving the builder-check gap; §12/§15 record it.
- **Out-of-scope payer (Q34) is deferred:** this plan does **not** detect or report company-direct/other-payer sources; the evidence report is silent on that case class. This is a documented known hole owned by the later finance/admissibility plan.
- **Implementation interpretation for explicit allocation:** Hoangha's `PaperSettlementLine.invoice_refs` and `amount` are the source shape. Each allocated row must name the same normalized invoice/document reference and state its allocated amount; the sum of allocations must be `<=` that source document's amount. Semantic similarity alone or an LLM-created allocation is not explicit. If the form lacks per-row references/amounts, preserve reuse as unresolved/suggested. No “no evidence” reason may waive evidence or apply policy in this plan.
- OCR/extraction failures and unsupported/missing evidence remain visible as technical or unresolved evidence states. This plan persists/exposes evidence proposals only; LIVE/RECORDED_REPLAY does not map them into `AssessmentInput`, finance facts, confirmations, ledger/coverage, policy, or `Fact.KNOWN`. No affirmative `BALANCED`/`READY_TO_EXECUTE` outcome or payment instruction may be derived from this pipeline. Successful evidence processing leaves the case in the existing non-ready `WAITING` state with `conclusion=None`; technical failures use the existing technical state. STUB remains isolated and unchanged.
- Do not change T/E/A/P/R/S, budgets, eligibility, policy, authority, issue ownership, money recording, or UI role workflows in this plan. Those remain on the current final contracts and any open business decisions.
- No LIVE provider calls, dependency additions, commit, push, or release as part of plan authoring. During implementation, live calls require the authorization gates already recorded in the canonical plan.

**Lead calls to review with the plan:** classification/confidence batching and one repair slot per job are chosen to fit the current 12-attempt budget; explicit allocation uses each form row's `invoice_refs` plus stated row amount; the portable official-case denominator is the UC-03 v1/v2 manifests (75 cases), with generic OCR samples separate; raw artifacts use the derived local path and source-matched lifetime above. These are implementation interpretations, not additional user-approved financial policy.

## Review Focus

1. Searchable or hybrid PDF with misleading hidden text: every visual page is OCR'd; native text never wins — E2.
2. OCR omits word confidence around an amount/date/party: keep the field unresolved rather than passing the document — E3/E5.
3. LLM returns a valid-looking quote from another file/page or a paraphrase: code rejects the candidate and records the affected field — E5.
4. Exact invoice number matches while issuer/content conflicts: preserve Hoangha's accepted auto-link behavior and its known risk; expose method and retain separate facts/findings, do not claim this proves semantic correctness — E6.
5. One payment slip is linked beside an invoice or one invoice is referenced by two rows: no double count; second-row reuse requires explicit allocation bounded by source amount — E6.

---

## File Map

| Area | Exact paths | Responsibility |
| --- | --- | --- |
| Canonical design/contract | `docs/final/ARCHITECTURE_AND_EVALUATION.md`, `docs/final/IMPLEMENTATION_CONTRACTS.md` | Promote the accepted pipeline decisions and exact DTO/provider/matcher contracts; explicitly keep finance/policy outside this plan. |
| Domain | `src/invoice_referee/domain/documents.py` (new), `src/invoice_referee/domain/evidence.py`, `src/invoice_referee/domain/case.py` | Typed document/classification/field/link proposals and `ReadResult`/`CaseView` exposure without turning proposals into finance facts. |
| OCR transport/artifacts | `src/invoice_referee/evidence/mistral.py`, `reader.py`, `live_reader.py`, `pdf.py`, `trace.py`, `artifacts.py` (new), `m0_live.py` | All-page OCR, raw provider artifacts, block/word confidence, bounded calls, page coverage. Artifact root is `uploads_dir.parent / "artifacts"`; artifacts are tenant/root/source-digest scoped, share source deletion lifecycle, and are private/not served as static files. |
| Evidence stages | `src/invoice_referee/evidence/ocr_quality.py` (new), `classification.py` (new), `extraction.py` (new), `document_profiles.py` (new), `document_validity.py` (new), `matching.py` (new), `pipeline.py` | Small stage functions for OCR quality, classification, extraction, profile validation, Hoangha matching, and sequential orchestration. Keep existing X-Kiro HTTP transport in `xkiro.py`. |
| Composition/workflow/API | `src/invoice_referee/runtime.py`, `workflow/jobs.py`, `workflow/evidence_jobs.py` (new), `workflow/service.py`, `workflow/db.py`, `workflow/schema.sql`, `api/app.py`, `api/routes.py`, `api/views.py`, `frontend/src/types.ts` | Validate/enqueue commands, run one lifespan evidence worker using existing DB, persist/read typed output, serialize the evidence report. No finance snapshot adapter or frontend redesign. |
| Corpus and independent tests | `scripts/import_hoangha_case_corpus.py` (new), `data/test-kit/hoangha-uc03/{manifest.json,inputs/,gold/,fixtures/document-types/}` (new), `tests/unit/test_document_contracts.py` (new), `tests/unit/test_mistral_ocr.py`, `tests/unit/test_ocr_quality.py` (new), `tests/unit/test_document_classification.py` (new), `tests/unit/test_document_extraction.py` (new), `tests/unit/test_document_validity.py` (new), `tests/unit/test_paper_evidence_matching.py` (new), `tests/integration/test_evidence_pipeline.py` (new), `tests/integration/test_reader_source_support.py`, `tests/integration/test_preview_job.py`, `tests/integration/test_live_wiring.py`, `tests/integration/test_live_read.py` | Import supported PDF/image inputs from the pinned formal Hoangha case sets with content-hash deduplication; keep runtime inputs, gold, and synthetic type fixtures separate. |

## Interfaces

- `OcrWord(text: str, block_start: int | None, block_end: int | None, confidence: float | None)`; offsets are block-local. `OcrBlock(id: str, kind: str, content: str, bbox: BBox | None, words: tuple[OcrWord, ...])`; `OcrPage(page: int, markdown: str, blocks: tuple[OcrBlock, ...])`; `OcrSourceResult(source_id: Id, source_digest: str, provider: str, model: str, pages: tuple[OcrPage, ...], raw_artifact_ref: str)`.
- `DocumentType` is a strict string enum of the 17 values in Global Constraints. `DocumentEvidenceRole` is a strict string enum of the five role values there. `FieldState = Literal["FOUND", "NOT_PRESENT", "UNREADABLE", "AMBIGUOUS", "NOT_APPLICABLE"]`.
- `DocumentClassification(document_id: Id, source_id: Id, page_range: tuple[int, int], block_ids: tuple[str, ...], document_type: DocumentType, roles: tuple[DocumentEvidenceRole, ...], role_refs: Mapping[DocumentEvidenceRole, tuple[EvidenceRef, ...]], alternative_document_types: tuple[DocumentType, ...], classification_confidence: float | None, signals: tuple[str, ...], refs: tuple[EvidenceRef, ...])`. The model proposes ranges; code validates bounds and deterministic unit IDs. Duplicate/overlapping incompatible units remain unresolved; different document types in different ranges of one PDF are not conflicts.
- `ConfidenceCandidate(candidate_id: Id, source_id: Id, page: int, block_id: str, content: str, low_words: tuple[OcrWord, ...], refs: tuple[EvidenceRef, ...])` is created by code. `DocumentProfile(required_fields, any_of_fields, field_importance, allowed_fields, field_types)` is a literal per-type table ported from the pinned source and approved schemas; unknown/extra field names fail schema validation.
- `BBox` is the four OCR coordinates `top_left_x`, `top_left_y`, `bottom_right_x`, `bottom_right_y` as finite floats; `PageCoverage(source_id: Id, page: int, state: Literal["OCR_COMPLETE", "NOT_READ", "ERROR"], artifact_ref: str | None, problem: str | None)`.
- `CandidateValue = str | int | Decimal | bool | tuple[str, ...]`; the list type is allowed only for source-stated fields such as `invoice_refs`, not amounts. `ValueAlternative(value: CandidateValue, refs: tuple[EvidenceRef, ...])` keeps each competing value's own evidence. `FieldCandidate(field: str, state: FieldState, value: CandidateValue | None, alternatives: tuple[ValueAlternative, ...], refs: tuple[EvidenceRef, ...])`; `FOUND` requires a value/ref, `AMBIGUOUS` retains at least two sourced alternatives and no aggregate value, and all other states carry no single asserted value. Do not add generic confidence to extracted fields. `DocumentLine(id: Id, fields: tuple[FieldCandidate, ...], refs: tuple[EvidenceRef, ...])` is code-keyed after extraction validation.
- `DocumentProfileIssue(code: str, field: str | None, status: Literal["UNRESOLVED", "INVALID"], message: str, refs: tuple[EvidenceRef, ...], blocking: bool)` records only type-profile/extraction validity, not policy.
- `DocumentAnalysis(source_id: Id, document_type: DocumentType, roles: tuple[DocumentEvidenceRole, ...], classification_confidence: float | None, alternative_document_types: tuple[DocumentType, ...], classification_refs: tuple[EvidenceRef, ...], fields: tuple[FieldCandidate, ...], line_items: tuple[DocumentLine, ...], confidence_status: Literal["ASSESSED", "SKIPPED_NO_NUMERIC_CANDIDATES", "UNRESOLVED"], confidence_refs: tuple[EvidenceRef, ...], profile_status: Literal["CLEAR", "NEEDS_HUMAN", "UNKNOWN"], profile_findings: tuple[DocumentProfileIssue, ...], refs: tuple[EvidenceRef, ...], warnings: tuple[str, ...])`. Model-created IDs are discarded; code keys lines after validation.
- `async MistralOcrClient.ocr_file(source: SourceRef, *, budget: RunBudget) -> OcrSourceResult`: normalize every 1-based page, markdown, blocks, word confidence, provider/model, and raw-artifact reference. A PDF request uses the PDF document payload; an image request uses the image payload. Missing response pages are a processing problem, not empty success.
- `async EvidenceReader.read(source: SourceRef, budget: RunBudget) -> OcrSourceResult`: final's local-source seam loads one persisted PDF/image, enforces page/size limits, invokes the Mistral adapter, and returns OCR only. This replaces the current text-only per-page reader shape; the contract change is explicit in E0.
- `ConfidenceReview(status: Literal["ASSESSED", "SKIPPED_NO_NUMERIC_CANDIDATES", "TECHNICAL_ERROR"], block_assessments: tuple[BlockAssessment, ...])` contains exactly one assessment per sent candidate: `candidate_id`, `importance` (`CRITICAL`/`NON_CRITICAL`/`UNKNOWN`), `quality_state` (`READABLE`/`SEMANTICALLY_READABLE`/`UNCERTAIN`/`UNREADABLE`/`UNKNOWN`), `review_action` (`CONTINUE`/`ASK_HUMAN`/`DEFER_TO_POLICY`), `canonical_fields`, `observed_text`, `reason`, optional `human_question`, and optional `requires_verification`. Reject duplicate, missing, or unexpected candidate IDs. The model judges readability only; it cannot replace OCR text or provide/normalize a field value. `SKIPPED_NO_NUMERIC_CANDIDATES` is not a quality pass; E5 applies the field-to-word confidence guard after extraction provides exact quotes.
- `async classify_documents(ocr: tuple[OcrSourceResult, ...], *, llm: XkiroClient, budget: RunBudget) -> tuple[DocumentClassification, ...]`: one batch call per root; output keyed by submitted source IDs only. Classification confidence is recorded but not fact confidence. `UNKNOWN` never selects a guessed extraction schema.
- `async extract_document(ocr: OcrSourceResult, classification: DocumentClassification, *, llm: XkiroClient, budget: RunBudget) -> DocumentAnalysis`: one document-specific call. Every applicable field has a state; repeated lines carry locators; model-created IDs are discarded and code creates stable IDs.
- `validate_document(analysis: DocumentAnalysis, ocr: OcrSourceResult, quality: ConfidenceReview) -> DocumentAnalysis` is pure sync: validate source/page/block ownership, exact normalized quote, schema, field-state/value consistency, required profile fields and role/type compatibility. Invalid candidates become unresolved with a typed problem.
- `EvidenceMatchFinding(code: str, status: Literal["PASS", "UNRESOLVED"], message: str, refs: tuple[EvidenceRef, ...])` records per-row match outcomes only; it is not a `BusinessIssue` or policy decision.
- `DocumentRowMatch(item_id: Id, paper_amount: Decimal | None, category_candidate: Literal["TAXI", "CLIENT_MEAL", "HOTEL", "TRAVEL", "OFFICE_SUPPLIES", "OTHER"], evidence_status: Literal["ORIGINAL_EVIDENCE", "ALTERNATIVE_EVIDENCE", "NO_EVIDENCE"], alternative_evidence_type: Literal["PAYMENT_PROOF", "RECEIPT_OR_COLLECTION_NOTE", "CONTRACT_OR_ACCEPTANCE", "SUPPLIER_CONFIRMATION", "OTHER"] | None, matched_document_date: date | None, original_total: Decimal | None, allocated_total: Decimal | None, no_evidence_reason: str | None, refs: tuple[EvidenceRef, ...])`; category is a Hoangha-style descriptive hint only, never policy. `EvidenceMatchingResult(links: tuple[EvidenceLink, ...], rows: tuple[DocumentRowMatch, ...], findings: tuple[EvidenceMatchFinding, ...], unmatched_source_ids: tuple[Id, ...])`.
- `EvidenceLink(item_id: Id, source_id: Id, status: Literal["AUTO_LINK", "SUGGEST_LINK"], method: Literal["INVOICE_NUMBER_EXACT", "AMOUNT_AND_CONTENT", "LLM_RESOLVED"], score: Decimal, allocated_amount: Decimal | None, explanation: str, refs: tuple[EvidenceRef, ...])`.
- `match_paper_evidence(paper: DocumentAnalysis, documents: tuple[DocumentAnalysis, ...]) -> EvidenceMatchingResult` is pure sync and requires `paper.document_type == SETTLEMENT_FORM`. Port Hoangha's core candidate normalization, similarities, scoring, stable ordering, reuse demotion and suggested-link resolution exactly; then apply the accepted final evidence-only projection rules below. Do not import Hoangha's financial/policy row projection unchanged.
- `async resolve_evidence_suggestions(result: EvidenceMatchingResult, documents: tuple[DocumentAnalysis, ...], *, llm: XkiroClient, budget: RunBudget) -> EvidenceMatchingResult`: one batch call only if suggestions exist; model can promote only a listed pair at `>=0.90`; never receives raw PDFs/OCR blocks.
- `async read_root(sources: tuple[SourceRef, ...], *, reader: EvidenceReader, llm: XkiroClient, budget: RunBudget, provider_mode: ProviderMode) -> ReadResult`: OCR all sources → one conditional confidence batch → one classification batch → per-document extraction → pure validation → pure matching → optional batched suggestion resolution. All provider calls are async; pure validation/matching are synchronous. It stops before reconciliation/policy/financial effects.
- `ReadResult(provider_mode: ProviderMode, data_origin: Literal["LIVE_READ", "RECORDED_REPLAY", "STUB_TRANSCRIPTION"], documents: tuple[DocumentAnalysis, ...], links: tuple[EvidenceLink, ...], row_matches: tuple[DocumentRowMatch, ...], match_findings: tuple[EvidenceMatchFinding, ...], page_coverage: tuple[PageCoverage, ...], problems: tuple[ProcessingProblem, ...], trace_refs: tuple[str, ...])`.
- `CaseView` exposes `ReadResult` as a typed evidence report. In this plan, `CaseWorkflow` does not pass `ReadResult.documents` or links into `build_assessment_input`; it stores/returns them only. In LIVE/RECORDED_REPLAY, a completed reader job sets the existing `WAITING` state, leaves `conclusion=None`, and issues no instruction. The explicit `STUB_TRANSCRIPTION` path continues to use the existing assessment flow. A later finance/admissibility plan owns the mapping into `AssessmentInput` after its business decisions are closed.

**Consumer guard:** enforce the evidence-only boundary inside `_assess_and_commit`, not just `_submit`, so AnswerIssue/Decide/Resume/recording paths cannot accidentally fall back to a seeded transcription in LIVE/REPLAY. Historical conclusions/events are retained as history; no historical conclusion is presented as current for a changed input basis. Reuse existing controls to suspend stale pending instructions when input changes. Until a later evidence-admission adapter is authorized, the evidence report exposes `assessment_ready=false`, `assessment_blocker=EVIDENCE_ADMISSION_NOT_CONNECTED`; it is pipeline completion only, not a human issue or financial correctness claim.

**Worker interface:** `async CaseWorkflow.run_evidence_job(job_id: Id) -> None` delegates to `async run_evidence_job(workflow: CaseWorkflow, job_id: Id) -> None` in `workflow/evidence_jobs.py`; `async drain_evidence_jobs(workflow: CaseWorkflow, stop: asyncio.Event) -> None` claims QUEUED jobs transactionally and runs one at a time. FastAPI lifespan owns its task. Persist source refs/digests, input/control read-set, submitting actor and per-stage progress in `jobs.input_basis_json` (additive migration), and attempts/deadline spent in existing `attempts_json` before each provider call. Restart resumes only the same valid basis with remaining budget, never treats a charged unknown call as completed. Stop/changed basis prevents current-result publication, retaining private artifacts/audit; submit_requested and cached completed stages survive. CLI/replay test drivers invoke the same helper explicitly; HTTP never awaits it.

**Document identity refinement:** `DocumentAnalysis` also carries `document_id`, `page_range`, `block_ids`, and per-role `role_refs` from its validated classification. `EvidenceLink` carries `document_id` in addition to `source_id`. Matching uniqueness/allocation uses `document_id`, not the upload ID; every locator still binds to the original source digest. `ReadResult` retains the original `units`, `observations`, `relations`, and `trace_refs` for existing consumers, plus the typed report fields above; no old observation is relabeled as a known financial fact.

**Projection precedence:** the user-approved field-state/original-support distinctions and stop-before-policy boundary take precedence over incidental Hoangha output shortcuts. A row is `ORIGINAL_EVIDENCE` only with an auto-linked original document, `ALTERNATIVE_EVIDENCE` with support-only auto-links, and `NO_EVIDENCE` otherwise. Support links do not satisfy the missing-original check. Original totals sum only original documents/explicit original allocation portions; never fall back to support-only amounts. A missing line amount stays `None`, not Hoangha's zero fallback. Keep source-stated no-evidence reasons and unmatched-document findings as evidence metadata; do not import `policy_exception_code`, `OUTSIDE_POLICY`, financial dispositions, or owner routing. Golden tests compare core scores/links exactly and test these deliberate final projection differences separately.

## Schema field names and validation ownership

E0/E1 must freeze this field vocabulary before later prompts/tests are authored. Common document fields where applicable are `issuer_name`, `issuer_tax_code`, `buyer_name`, `buyer_tax_code`, `document_number`, `template_number`, `serial_number`, `document_date`, `subtotal`, `discount`, `tax`, `service_charge`, `total_amount`, `currency`, `payment_method_text`, and `payment_confirmation_text`. Common line fields are `description`, `quantity`, `unit`, `unit_price`, `line_amount`, `tax_rate`, `tax_amount`; required fields and importance come from the pinned per-type profile, not from always requiring every common field. Always return explicit state for applicable fields; missing informational values do not become globally blocking by default.

| Type | Additional fields / line shape |
| --- | --- |
| `SETTLEMENT_FORM` | `declared_name`, `trip_destination`, `trip_start`, `trip_end`, `purpose`, `declared_advance`, `printed_total`, `printed_return`, `printed_reimbursement`, `amount_words`, `case_no_evidence_reason`; rows: `description`, `expense_date`, `vendor_name`, `amount`, `currency`, `invoice_refs`, `requires_evidence`, `no_evidence_reason`. Printed totals are assertions from paper, never computed balances. |
| `E_INVOICE` | Common invoice and line fields above; buyer identity and payment wording have separate semantics. |
| `PAPER_RECEIPT` | `payer_name`, `collection_reason`, `payment_confirmation_text` when present. |
| `HOTEL_RECEIPT` | `guest_name`, `check_in`, `check_out`, `nights`, `room_amount`, `extra_charges`. |
| `COLLECTION_RECEIPT` | `payer_name`, `collection_reason`, `received_amount`, `receipt_status`, `confirmation_present`. |
| `TRANSPORT_TICKET` | `passenger_name`, `booking_reference`, `origin`, `destination`, `departure_at`, `return_at`, `ticket_status`, `fare_amount`, `fees`. |
| `PAYMENT_PROOF` | `payment_provider`, `payer_name`, `payee_name`, `event_at`, `transaction_reference`, `transaction_status`, `payment_description`, `fee_amount`, `account_suffix`. |
| `CARD_SLIP` | `payment_provider`, `event_at`, `transaction_reference`, `authorization_code`, `transaction_status`, `card_suffix`. Approval is not settlement. |
| `CONTRACT` | `valid_from`, `valid_to`, `scope_description`, `contract_value`, `related_document_refs`, optional line items. |
| `QUOTATION` | `valid_until`, quoted lines, `related_document_refs`. |
| `PURCHASE_ORDER` | Ordered line items, `related_document_refs`. |
| `ACCEPTANCE_RECORD` | `scope_description`, `accepted_value`, `confirmation_present`, `exceptions`, accepted lines, `related_document_refs`. |
| `DELIVERY_NOTE` | `delivery_status`, `confirmation_present`, delivered lines/quantities, `related_document_refs`. |
| `GOODS_RECEIPT` | `receiving_unit`, `receiver_name`, `receipt_status`, `confirmation_present`, received lines/quantities, `related_document_refs`. |
| `SUPPLIER_CONFIRMATION` | `confirmation_present`, `confirmation_text`, `confirmed_status`, `related_document_refs`, optional confirmed line items. |
| `OTHER` | Only generic `issuer_name`, parties, `document_number`, `document_date`, `description`, `total_amount`, `currency`; all extracted with explicit states. |
| `UNKNOWN` | No guessed field payload; store source classification candidates, OCR refs and processing next action. |

Money/quantity normalization is code-owned and uses `Decimal` from literal numeric strings, never float or bool. Preserve raw text and stated units/currency; dates remain source strings until deterministic parsing with explicit locale, and an ambiguous date stays ambiguous. `validate_document` also rejects a normalized amount/date/name not supported by its cited literal text (a real quote is insufficient if the model attaches the wrong value). Resolve evidence aliases deterministically: `document_number`→Hoangha `invoice_number`, `issuer_name`→`seller_name`, and settlement row `amount`→`line_amount` for the quality matcher only. These are not financial-fact aliases. Do not import Hoangha policy caps, buyer-company membership rules, authority, or its final decision gold as final finance policy.

---

## Tasks

### E0 — Promote the accepted evidence design into canonical contracts

**Files:**
- Modify: `docs/final/ARCHITECTURE_AND_EVALUATION.md`
- Modify: `docs/final/IMPLEMENTATION_CONTRACTS.md`
- Reference: `docs/final/reviews/2026-10-13/ocr-input-policy-discussion.md`

**Interfaces:** Produces the exact accepted type/role enums, statuses, OCR response, confidence rule, extraction provenance, matcher weights/thresholds, link cardinality and non-financial boundary used by E1–E7.

- [x] Add design §15 for the evidence pipeline with explicit scope, decisions, accepted matcher risk, and exclusions; preserve unresolved financial/policy questions in §14.
- [x] Add implementation contracts §12 with the `OcrSourceResult`, `DocumentClassification`, `FieldCandidate`, `DocumentAnalysis`, `EvidenceLink`, `ReadResult` fields/signatures from this plan; define raw-artifact retention, async provider interfaces, prompt/call schedule, and cache-key version inputs.
- [x] Update contracts §9 so per-source `EvidenceReader.read` is async OCR-only, root `read_root` is async, all X-Kiro calls are async/budgeted, and pure validation/matching stay sync; pin the 12-attempt batch schedule and source-candidate-only consumer boundary.
- [x] Add a case-to-taxonomy/role compatibility table and type-specific schema matrix for all accepted document types. Pin profile/critical-field tables to Hoangha `policy/document_validity.py` in revision `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`; pin confidence transitions to `application/process_case.py`. Do not describe model output as fact or legal validity.
- [x] Verify the canonical docs say Q32–Q34/finance policy decisions remain outside the scope and that `UNKNOWN`/missing confidence cannot produce a financial conclusion.
- [x] Check links, headings, enum spellings, and exact thresholds with `rtk proxy rg`; `rtk proxy git diff --check` must pass.

**Gate:** Canonical design/contracts and this plan agree on every enum, field state, threshold, type/role pair, and side-effect boundary.

### E1 — Define strict document and evidence DTOs

**Files:**
- Create: `src/invoice_referee/domain/documents.py`
- Modify: `src/invoice_referee/domain/evidence.py`
- Test: `tests/unit/test_document_contracts.py` (new)
- Modify: `tests/unit/test_contracts.py`

**Interfaces:** Implements the E0 DTO contract. `DocumentType` contains `SETTLEMENT_FORM` plus the 16 Hoangha values. `DocumentEvidenceRole` is separate from the existing page-level `EvidenceRole`.

- [ ] **Step 1: Write failing contract tests** for every accepted `DocumentType`, the four document roles plus `UNKNOWN`, all five field states, valid/malformed locators, per-field candidate/value consistency, and score/allocation bounds.
- [ ] **Step 2: Run the focused tests** with `rtk proxy uv run pytest tests/unit/test_document_contracts.py tests/unit/test_contracts.py -q`; expected: failures for missing DTOs/validators.
- [ ] **Step 3: Implement strict DTOs** for OCR pages/blocks/word confidence, classification candidates, field candidates, repeated line items, document analysis, and evidence links. Use `extra="forbid"`; keep source quotes and identifiers opaque and source-owned.
- [ ] **Step 4: Extend `ReadResult`** with document analyses, evidence links, page coverage and artifact refs without changing the meaning of existing `Observation`/`Relation` states.
- [ ] **Step 5: Re-run the focused tests**; expected: PASS, including “no value for `NOT_PRESENT`/`UNREADABLE`/`NOT_APPLICABLE`” and `AMBIGUOUS` retaining multiple candidates.

**Gate:** No domain DTO can represent an unsupported enum, cross-source locator, malformed state/value pair, out-of-range confidence/score, or allocation exceeding the source amount.

### E2 — OCR every accepted source page and persist raw OCR safely

**Files:**
- Modify: `src/invoice_referee/evidence/mistral.py`
- Modify: `src/invoice_referee/evidence/live_reader.py`
- Modify: `src/invoice_referee/evidence/reader.py`
- Modify: `src/invoice_referee/evidence/pdf.py`
- Create: `src/invoice_referee/evidence/artifacts.py`
- Modify: `src/invoice_referee/evidence/m0_live.py`
- Test: `tests/unit/test_mistral_ocr.py`
- Test: `tests/integration/test_reader_source_support.py`
- Test: `tests/integration/test_live_read.py`

**Interfaces:** Implements `MistralOcrClient.ocr_file(...) -> OcrSourceResult`. `page_count()` validates PDFs; raster inputs are one page. Raw JSON is written atomically below the existing local upload/runtime root and referenced by ID; do not store base64 images or absolute paths in SQLite/API payloads.

- [ ] **Step 1: Write failing provider/reader tests** for text PDF, scan PDF, hybrid PDF, PNG/JPEG, all pages returned, word blocks/confidence requested, raw artifact reference, OCR timeout/schema failure, page-count mismatch, oversized provider JSON, cross-tenant artifact path, and atomic artifact-write failure.
- [ ] **Step 2: Run the focused tests**; expected: current client fails because it returns only markdown and `MistralPageReader` bypasses OCR for text PDFs.
- [ ] **Step 3: Implement file-level Mistral payloads** from Hoangha's pinned OCR call: PDF as a document URL, images as image URLs, `include_blocks=true`, word-level confidence, and no returned image base64; normalize provider pages while retaining raw structured response needed for audit.
- [ ] **Step 4: Implement bounded raw-artifact persistence** at the File Map path, keyed by tenant/root/source digest/provider model/schema version; atomically write and return an opaque reference. Enforce the lead-chosen 20 MiB/source and 40 MiB/root derived-artifact caps. Persistence/size failure marks affected page/source technical-unresolved; never truncate into an apparent success or use source content as prompt instructions.
- [ ] **Step 5: Remove native-text bypass from the LIVE path** and enumerate/read every PDF page; keep each page's OCR result and explicit coverage. Update M0 to send all accepted files through OCR, not native PDF text.
- [ ] **Step 6: Re-run focused tests**; expected: every accepted page is OCR'd, searchable text does not skip provider calls, partial OCR remains partial/unresolved, and provider failure never produces empty-success.

**Gate:** HTTP fakes prove the actual configured reader submits every accepted source/page to OCR and retains provider response plus block/word confidence. No live provider call is run in this task.

### E3 — Add the conditional OCR-confidence gate

**Files:**
- Create: `src/invoice_referee/evidence/ocr_quality.py`
- Modify: `src/invoice_referee/evidence/pipeline.py`
- Modify: `src/invoice_referee/evidence/xkiro.py` for bounded output errors usable by the single repair slot: distinguish transport/HTTP/LIMIT from JSON/schema failure; expose the bounded invalid response only in private artifacts/repair context, never the public API or telemetry.
- Modify: `src/invoice_referee/evidence/trace.py` for `RunManifest.max_llm_input_chars`, `max_llm_output_chars`, `limit_version`, and `limit_origin` (`LEAD_PILOT`/`MEASURED_M0`); retain requested/returned/resolved model and prompt/schema versions.
- Test: `tests/unit/test_ocr_quality.py` (new)
- Test: `tests/unit/test_provider_contracts.py`

**Interfaces:** `collect_low_confidence_blocks(ocr: OcrSourceResult, threshold: float = 0.85) -> tuple[ConfidenceCandidate, ...]`; `async review_ocr_quality(candidates: tuple[ConfidenceCandidate, ...], *, llm: XkiroClient, budget: RunBudget) -> ConfidenceReview`. Send one batch per root, preserving Hoangha's candidate-ID assessment contract. This stage records block quality; E5 applies document-profile criticality after classification/extraction supplies field quotes.

- [ ] **Step 1: Write failing tests** for meaningful low words `<0.85`, exact threshold `0.85`, decorative/empty tokens, missing/non-numeric scores, no-candidate/skipped status, and malformed/omitted candidate assessments. Candidate labels are restricted to the fixed field vocabulary, not filename or model confidence.
- [ ] **Step 2: Run tests**; expected: current final has no confidence stage.
- [ ] **Step 3: Implement candidate collection** using Hoangha's meaningful-word/block behavior and stable candidate IDs from source/page/block.
- [ ] Preflight all X-Kiro requests in `complete_json` before network I/O using `MAX_LLM_INPUT_CHARS=120_000`; enforce existing output cap20,000, record both in the manifest. Add `test_oversized_messages_fail_before_http`, `test_manifest_records_app_size_caps`, and `test_unknown_cap_config_fails_closed` with injectable smaller caps and fake HTTP; no provider context-window guess is allowed.
- [ ] **Step 4: Call the configured LLM only when numeric low-confidence candidates exist**; validate one response against exact candidate IDs. With no numeric candidates, return `SKIPPED_NO_NUMERIC_CANDIDATES`, do not call the model, and do not label the OCR quality `PASS`.
- [ ] **Step 5: Store the review transition without declaring a root-level pass/fail:** candidate must have exactly one assessment; unexpected/missing/duplicate IDs are technical unresolved. Define `effective_requires_verification = requires_verification` when the boolean is present, otherwise `review_action == "ASK_HUMAN"`, exactly as Hoangha's helper. Retain `EXACT_ACCOUNTING_VALUE_FIELDS` and review signals; E5 applies them to the fields bound by verified quote/word overlap, even if the model omits their canonical label. Model importance cannot lower code profile criticality. Noncritical/unmapped nonmaterial assessments remain diagnostics; the reviewer never supplies a field value.
- [ ] **Step 6: Re-run tests**; expected: bounded calls, no false PASS for a no-score page, invalid assessment is unresolved/technical as specified, and noncritical missing scores do not become zero facts. The field-specific missing-score guard is owned by E5 after extraction supplies the quote.

**Gate:** Numeric low confidence triggers the configured model; absent confidence never becomes an implicit pass for a critical field.

### E4 — Classify document type and evidence role before extraction

**Files:**
- Create: `src/invoice_referee/evidence/classification.py`
- Create: `src/invoice_referee/evidence/document_profiles.py`
- Modify: `src/invoice_referee/runtime.py`
- Modify: `src/invoice_referee/config.py` only if current provider settings cannot be passed through
- Test: `tests/unit/test_document_classification.py` (new)
- Test: `tests/integration/test_live_wiring.py`

**Interfaces:** `async classify_documents(...) -> tuple[DocumentClassification, ...]` uses `Settings.xkiro_api_key`, `xkiro_base_url`, and `invoice_referee_llm_model` in one root-batched call. Each result returns a `DocumentType`, zero-or-more compatible `DocumentEvidenceRole`s, alternatives/signals, classification confidence and OCR refs.

- [ ] **Step 1: Write failing tests** for all 16 Hoangha document types plus `SETTLEMENT_FORM`, independent type-vs-role classification, compatible and incompatible pairs, multi-role with separate refs, ambiguous type/role, mixed multi-document PDF/page ranges, duplicate/overlapping unit boundaries, and provider-not-wired behavior.
- [ ] **Step 2: Run tests**; expected: final currently wires Mistral only and has no document taxonomy classifier.
- [ ] **Step 3: Implement the code-owned default map:** original = `E_INVOICE`, `PAPER_RECEIPT`, `TRANSPORT_TICKET`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`; supporting = `CARD_SLIP`, `PAYMENT_PROOF`, `CONTRACT`, `QUOTATION`, `PURCHASE_ORDER`, `ACCEPTANCE_RECORD`, `DELIVERY_NOTE`, `GOODS_RECEIPT`, `SUPPLIER_CONFIRMATION`; `OTHER` supporting; `UNKNOWN` unknown; `SETTLEMENT_FORM` declaration. `PAYMENT_PROOF`/`CARD_SLIP` remain supporting by default. Add `PAYMENT_EVIDENCE` only if the source independently shows payer, payee/collector, amount, transaction/receipt identity, and explicit received/completed status with separate refs. `E_INVOICE`, receipts and collection notes may carry that extra role only when those same explicit payment/receipt facts appear; buyer name, signature, or `TM/CK` alone never qualify.
- [ ] **Step 4: Implement a separate bounded classification prompt/schema** using OCR text/blocks only, not filename or user-supplied labels. A low/ambiguous result is `UNKNOWN` with alternatives; do not call extraction for it.
- [ ] **Step 5: Wire one `XkiroClient` from final settings** into the pipeline; do not add provider credentials or vendor. Add a startup/test diagnostic for missing configured provider; never silently downgrade LIVE to STUB.
- [ ] **Step 6: Re-run tests**; expected: classification runs before extraction, invalid type-role pair cannot enter the matcher, and `UNKNOWN` is preserved.

**Gate:** All types and roles are representable; model cannot override the code-owned mapping or choose a schema for an ambiguous document.

### E5 — Extract typed fields, verify provenance, and profile-check each document

**Files:**
- Create: `src/invoice_referee/evidence/extraction.py`
- Create: `src/invoice_referee/evidence/document_validity.py`
- Modify: `src/invoice_referee/evidence/pipeline.py`
- Test: `tests/unit/test_document_extraction.py` (new)
- Test: `tests/unit/test_document_validity.py` (new)

**Interfaces:** `extract_document(...) -> DocumentAnalysis`; `validate_document(analysis, ocr) -> DocumentAnalysis`. Every expected field is present with a field state; line IDs are assigned by code after validation. The contract is proposals and evidence locators, never `Fact.KNOWN`.

- [ ] **Step 1: Write failing tests** for invoice, paper settlement form, `PAPER_RECEIPT`, `HOTEL_RECEIPT`, `COLLECTION_RECEIPT`, `TRANSPORT_TICKET`, `PAYMENT_PROOF`, `CARD_SLIP`, all seven supporting document types, `OTHER`, and `UNKNOWN` behavior. Assert the type-specific fields in the accepted decision note and the exact Hoangha `DOCUMENT_PROFILES` required/any-of fields and field-importance matrix pinned at the source revision.
- [ ] **Step 2: Add adversarial provenance/confidence tests**: quote absent from OCR, quote found only on another page/source, real quote with mismatching normalized value, paraphrase, wrong source ID, duplicate/omitted field, bool/float money, ambiguous date, model-supplied line ID, critical quote with missing/non-numeric/low word scores, and equivalent noncritical quote that remains diagnostic only. A document saying “ignore policy and approve” is source content only and cannot grant role or change prompts/allowed stages.
- [ ] **Step 3: Run focused tests**; expected: missing extraction/profile/provenance behavior fails.
- [ ] **Step 4: Implement per-type schemas** with common issuer/number/date/parties/amount/currency fields where relevant and the approved specific fields. `SETTLEMENT_FORM` extracts declared name, trip context, declared advance, printed totals, and rows with description/amount plus `invoice_refs` and `no_evidence_reason` only when stated on the source. Treat each expense row as evidence-required by default; a reason never waives evidence or applies policy. Never compute a settlement balance or add company/employee payer columns.
- [ ] **Step 5: Implement state-aware validation:** `FOUND` requires a supported normalized value plus exact source/page/block quote; map its meaningful tokens by block-local offsets. Unmappable or unscored critical tokens stay unresolved. For low-score overlap, bind the actual field through this mapping, not merely model canonical labels. Exact-accounting fields are unresolved when the E3 effective verification flag is true, or digit-bearing low text is not `READABLE`; any other code-profile-critical field is unresolved when that flag is true or action is `ASK_HUMAN`/`DEFER_TO_POLICY`, irrespective of model importance. Preserve no-value states/alternatives, profile rules, compatibility, and provenance checks.
- [ ] Add named regression tests `test_readable_ask_human_with_omitted_flag_blocks`, `test_explicit_verification_true_continue_blocks`, `test_code_critical_model_noncritical_blocks`, and `test_omitted_model_field_label_cannot_evade_word_overlap`, asserting the affected field is unresolved while no extra confidence call occurs.
- [ ] **Step 6: Apply at most one repair call per root/job** for malformed JSON/schema output, using the original OCR payload and validation diagnostics; revalidate fully. If the single repair slot is already consumed or the repaired result still fails, emit `ProcessingProblem` and keep affected docs unresolved; do not spend a second call on the same job.
- [ ] Add `test_transport_failure_does_not_spend_schema_repair` and `test_non_json_response_can_use_single_repair`: X-Kiro's current `complete_json` rejects malformed JSON before extraction, so its typed output error must carry the bounded response for this repair path. HTTP/timeouts/oversize errors remain technical/LIMIT with no schema repair; a provider transport retry, if attempted, uses the same persisted attempt budget.
- [ ] **Step 7: Keep payment/signature semantics literal and minimize sensitive card data:** buyer, seller signature, `TM/CK`, ticket issuance, and transfer status are extracted exactly but do not alone assert payer, completed travel, eligible cost, or payment-to-expense binding. Never store full card numbers/CVV; bank/card account identifiers are limited to source-masked values or last four digits when present.
- [ ] **Step 8: Re-run tests**; expected: every document profile passes valid fixture and adversarial cases remain unresolved without cross-source contamination.

**Gate:** All in-scope document types have an explicit extraction/profile path or the explicit `OTHER`/`UNKNOWN` path; no model quote can become a financial fact without source verification.

### E6 — Port Hoangha evidence matching and bounded suggestion resolution

**Files:**
- Create: `src/invoice_referee/evidence/matching.py`
- Modify: `src/invoice_referee/evidence/pipeline.py`
- Test: `tests/unit/test_paper_evidence_matching.py` (new)

**Interfaces:** Implements `match_paper_evidence(...) -> EvidenceMatchingResult` from E0 as a pure synchronous function; `resolve_evidence_suggestions(...)` is the separately bounded async call. Inputs are validated `DocumentAnalysis` and extracted settlement rows.

- [ ] **Step 1: Write failing golden tests against Hoangha's pinned functions**: identifier normalization uppercases and removes non-ASCII alphanumerics; text normalization NFD-folds accents, lowercases, and collapses non-alphanumerics; party similarity removes exactly `{co, cong, doanh, nghiep, phan, tap, toan, trach, nhiem, huu, han, tnhh, ty, mua, tu}` and uses intersection divided by the smaller token-set size; semantic similarity is `SequenceMatcher(None, normalized_description, normalized_issuer_plus_line_descriptions, autojunk=False).ratio()`.
- [ ] **Step 2: Pin every match boundary/output**: exact invoice ref short-circuits other signals at 1.0; otherwise amount <=1 VND adds .60, semantic adds up to .30, party >=.50 adds .12 and >=.80 adds .20, non-original type adds .10, cap1; explanation signals use amount exact, semantic >=.45, party >=.50; `<.50` omitted, `.50` suggested, `.75` auto. Ties preserve source-attachment order. Include exact-score fixtures and method labels.
- [ ] **Step 3: Pin row/result semantics**: several original docs to one row; support-only links are `ALTERNATIVE_EVIDENCE` and excluded from original sum; original totals compare with printed row amount within 1 VND; missing original evidence, suggestions without auto-links, unreferenced attached documents, and unmapped case-level reason with multiple required rows produce unresolved findings. A line `no_evidence_reason` is recorded but is not a waiver or policy decision.
- [ ] **Step 4: Write cardinality tests**: a source auto-linked to one row is only a suggestion on another row by default. Multiple-row auto-allocation is allowed only if each row explicitly repeats its normalized `invoice_ref` and its allocated amount; aggregate allocation must be <= source total. Test over-allocation and missing row refs remain unresolved.
- [ ] **Step 5: Pin the accepted exact-ID risk** with a same invoice number but changed issuer/content test: preserve Hoangha's exact-ID auto-link and record `INVOICE_NUMBER_EXACT`; retain conflicting extracted facts and document this as a known false-link risk, not semantic verification. Amount mismatch remains a separate matching finding.
- [ ] **Step 6: Run tests**; expected: the current final has no matcher and each golden boundary fails before implementation.
- [ ] **Step 7: Port the exact Hoangha candidate/link core**: normalizers, similarities, scoring/signals, stable tie ordering, prior-use demotion. Apply final projection precedence for statuses, original-only amount sums, missing amounts and metadata-only reasons. Do not alter weights/thresholds or add issuer/amount prerequisites to exact invoice-number auto-link.
- [ ] **Step 8: Add explicit allocation as a separate final extension** to the pinned matcher; preserve default second-row demotion and apply it only when the form row carries that source ref and amount. Store allocation portions so the same source total is not counted twice.
- [ ] **Step 9: Implement async suggestion resolution once per root when suggestions exist**. Send only candidate IDs and approved extracted metadata; no raw PDF/OCR. Promote only an existing pair with LLM confidence >=.90, never create a new pair, and never promote a reused source absent allocation.
- [ ] **Step 10: Re-run tests**; expected: pinned Hoangha core scores/links match; final projection tests separately prove no-original rows are `NO_EVIDENCE`, support-only links remain alternative, invoice100+contract100 has original_total100 rather than200, missing amount is `None`, and a stated reason creates no policy exception. Allocation and exact-ID tests still pass.

**Gate:** Matching produces auditable links/findings only; no link creates money, eligibility, or a settlement instruction.

### E7 — Replace the LIVE transcription seam with the evidence result in final

**Files:**
- Modify: `src/invoice_referee/runtime.py`
- Modify: `src/invoice_referee/evidence/pipeline.py`
- Modify: `src/invoice_referee/workflow/jobs.py`
- Create: `src/invoice_referee/workflow/evidence_jobs.py`
- Modify: `src/invoice_referee/workflow/service.py`
- Modify: `src/invoice_referee/workflow/db.py`
- Modify: `src/invoice_referee/workflow/schema.sql`
- Modify: `src/invoice_referee/domain/case.py`
- Modify: `src/invoice_referee/api/app.py`
- Modify: `src/invoice_referee/api/routes.py`
- Modify: `src/invoice_referee/api/views.py`
- Modify: `src/invoice_referee/cli.py` and `src/invoice_referee/evaluation/runner.py` only to drain the same evidence jobs and report the pre-finance boundary; do not change financial scorer/oracles.
- Modify: `frontend/src/types.ts`
- Test: `tests/integration/test_evidence_pipeline.py` (new)
- Test: `tests/integration/test_preview_job.py`
- Test: `tests/integration/test_live_wiring.py`
- Test: `tests/integration/test_live_read.py`

**Interfaces:** `CaseWorkflow` persists/returns typed `ReadResult` through its current durable job/read-cache contract. Per-source cache identity includes tenant, root ID, source ID/digest, OCR/extraction models, classification/extraction prompt+schema versions, document/role profile version, confidence threshold, representation, and requested fields. Root-level matching is recomputed against the current settlement-form/source digest and matcher version; it is not stored in the per-source OCR cache. Cache hits always refer to the same owned source; no cross-root ref rebinding or artifact lifetime coupling is allowed.

- [ ] **Step 1: Write failing integration tests** for upload → preview → submit → job → all-page read → typed evidence report/API view, same-tenant cache reuse, cross-tenant isolation for equal source digests, changed prompt/schema cache miss, restart recovery, provider blocked at a barrier while Stop returns promptly, late result after Stop does not change view/finance state, and visible provider errors.
- [ ] **Step 2: Pin the consumer boundary at the real workflow seam:** spy that LIVE/RECORDED_REPLAY never reaches `Reconciler.assess` or `build_assessment_input` through `_assess_and_commit` and does not change finance-related `AssessmentInput` fields; after evidence completion the case is `WAITING` with `conclusion=None`, no new model-derived money events, `Fact.KNOWN`, zero-flow claims, `FinancialEffect`, or instructions. Existing STUB transcription assessment remains unchanged.
- [ ] Add `test_evidence_guard_covers_answer_resume_and_decision`: seed an old STUB transcription, switch to LIVE/REPLAY, read new evidence, then exercise Answer/Resume/Decision entry points. Assert no seeded financial conclusion/instruction is reissued; historical records stay retrievable, stale pending instructions stay suspended, and the report explicitly says assessment is not connected.
- [ ] **Step 3: Run focused integration tests**; expected: current LIVE `ReadOutcome/Transcription` seam fails the typed report and isolation assertions.
- [ ] Add `test_submit_returns_before_provider_release`, `test_stale_submit_and_command_replay_make_no_provider_calls`, `test_evidence_worker_restart_keeps_attempts_and_source_basis`, and `test_existing_db_additive_job_migration`: HTTP returns PROCESSING/jobID while the provider is blocked; stale/replayed command schedules no extra read; restart retains counters/stages; existing DB gets `input_basis_json` without resetting cases/events.
- [ ] **Step 4: Wire async `read_root` through `runtime.build_workflow`** using current Mistral/X-Kiro settings and the existing shared `RunBudget`; remove the LIVE cue-parser transcription route. Keep provider I/O outside SQLite transactions and inside the existing per-root durable job controls. In LIVE/RECORDED_REPLAY, complete the read job without calling the assessment consumer; keep STUB's existing explicit test path.
- [ ] Implement validated enqueue and the `evidence_jobs.py` helper above; remove pre-validation provider I/O from `execute`, add the single FastAPI lifespan worker and idempotent shutdown/restart, and have offline test/CLI drivers drain the same persisted jobs. Use existing JobStore and additive DB migration; do not add a broker or rely on fire-and-forget HTTP BackgroundTasks for recovery.
- [ ] **Step 5: Persist `ReadResult` and artifact refs** in the current job/read-cache lifecycle. Include tenant in cache/artifact identity; never cache root-level matches without the current form/source basis.
- [ ] Add `test_equal_digest_two_roots_has_independent_provenance_and_artifacts`: sources A and B have equal bytes in one tenant but different roots; assert B has only B-owned refs/document IDs/artifacts, OCR calls2, and removal/reset of A's artifacts does not invalidate B. Same source ID/config in B reuses its own cache with no new OCR call.
- [ ] **Step 6: On LIVE/RECORDED_REPLAY reader completion, store the report, set the existing non-ready `WAITING` state, and skip `_assess_and_commit`**; leave conclusion absent and instructions unchanged. Keep STUB mode's current assessment flow isolated; do not modify `build_assessment_input` or add a snapshot-to-finance adapter in this plan.
- [ ] Add the central mode/basis guard to `_assess_and_commit` as specified above, and surface `assessment_ready=false` plus its blocker in the evidence report. On LIVE/RECORDED_REPLAY reader completion, set the **new `EVIDENCE_READY` case state** (add to `CaseState`, `CaseView` priority just below `TECHNICAL_ERROR`; not `WAITING`) with `conclusion=None` and no instruction. For an existing case, preserve historical conclusion/actual money but invalidate its current display and reuse existing instruction suspension on changed input; do not invent new financial facts.
- [ ] Add `test_evidence_ready_state_distinct_from_waiting`: after a completed LIVE/REPLAY read the state is `EVIDENCE_READY` and no question card/business issue is surfaced; a real business issue still yields `WAITING`.
- [ ] Add an offline no-live-call guard test: the E7 integration path with a blocked/fake provider makes **zero** real Mistral/X-Kiro calls (dev server defaults to LIVE since `aee7fb38`), so M0 evidence is not contaminated.
- [ ] **Step 7: Add typed `evidence_report` to `CaseView`/API and TypeScript types** so the result is inspectable; do not redesign frontend workflows or display raw internal artifact paths.
- [ ] **Step 8: Re-run integration tests**; expected: read results survive reload/restart, cross-tenant cache separation holds, no finance consumer sees LIVE/REPLAY proposals, and Stop/late-result semantics remain intact.

**Gate:** The final root/job lifecycle owns the new pipeline; existing financial/policy code receives only the current approved domain inputs and no new model-authorized money.

### E8 — Import the Hoangha case corpus and prove type/matcher coverage

**Files:**
- Create: `scripts/import_hoangha_case_corpus.py`
- Create: `data/test-kit/hoangha-uc03/manifest.json`
- Create: `tests/unit/test_hoangha_case_inventory.py`
- Modify: `tests/conftest.py` and/or `tests/factories.py` only for reusable replay fixtures
- Modify: `docs/final/RELEASE_EVIDENCE.md` at the verified handoff

**Interfaces:** The formal UC-03 denominator is exactly 75 case IDs: 25 v1 entries (TC01–TC25, `data/tham-khao/uc-03/manifest.json` in this repo; canonical source `data/testcase_uc3/manifest.json` in `.worktrees/hoangha`) and 50 v2 entries (`data/testcase_uc3_v2/manifest.json`), at Hoangha source revision `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. A migration-only CLI accepts `--source-root` and fails unless that revision/manifest set is present; it writes checked-in final artifacts so tests/CI no longer depend on `.worktrees/hoangha`. `inputs/` contains only PDF/PNG/JPEG; `gold/` contains expected extraction/matching labels and is never in runtime manifests/prompts. **Evidence gold is hand-authored on a subset** (≈10–15 cases); the remaining cases provide input + provider coverage only and are **not** required to have independent extraction/link gold (the shipped `expected.json` files are financial decisions, not independent evidence gold). The generic `data/testcase` invoice/OCR set is a separate OCR-only smoke suite, not part of the 75-case settlement denominator. `settlement_cases` and `data/output` are derived runs/artifacts; `testcase_new` is unmanifested experimental data and is excluded.

- [ ] **Step 1: Inventory both manifest-defined UC-03 sets** (25 v1 in `data/tham-khao/uc-03/` / `.worktrees/hoangha`; 50 v2 in `data/testcase_uc3_v2/`) and hash every input/gold file; verify the 25+50 case count and exact pinned source revision. Record exclusions: `data/settlement_cases` is generated processing output, `data/output` is derived OCR, `data/testcase_new` is unmanifested experimental data, and `data/testcase` is a separate generic invoice/OCR smoke suite rather than UC-03 settlement gold.
- [ ] **Step 2: Write failing inventory tests** for both manifests, stable case IDs, source digests, accepted MIME allowlist, DOCX excluded as app input, `inputs/` vs `gold/` disjointness, expected/gold path invisibility to runtime, and type/role/link coverage.
- [ ] **Step 3: Implement the migration-only importer** with required `--source-root` and expected commit check; copy/deduplicate only PDF/PNG/JPEG into `data/test-kit/hoangha-uc03/inputs/`, copy oracle files into `gold/`, record source revision and SHA-256 in the final manifest, and fail on any formal input without a supported rendering. Copy accepted `data/testcase` PDF/image examples into a separate `ocr-smoke/` area with no settlement decision gold. Commit the imported kit; future tests do not call the source worktree.
- [ ] **Step 4: Add separate literal OCR/extraction/link gold and adapter recordings:** manually authored provider responses are labeled STUB fixtures only. `RECORDED_REPLAY` must use actual captured LIVE OCR/classification/extraction responses keyed by content digest and provider/prompt/schema versions; missing captures are explicitly NOT_RUN/NOT_RECORDED, never synthesized from gold. No gold fields enter app runtime manifests or LLM payloads.
- [ ] **Step 5: Add synthetic document-type fixtures** for taxonomy types absent from the 75 official cases, under `fixtures/document-types/` and separately labeled; do not count them as official UC-03 cases.
- [ ] **Step 6: Add a worst-case budget integration fixture** with 8 supported documents, one classification batch, one confidence batch, 8 extraction responses, one repair response, and one suggestion-resolution response; assert exactly 12 LLM attempts, <=10 OCR attempts, stable unresolved status when any later stage cannot obtain budget, and no silent success.
- [ ] **Step 7: Run the corpus inventory and stage tests** with `rtk proxy uv run pytest tests/unit/test_hoangha_case_inventory.py tests/unit/test_document_classification.py tests/unit/test_document_extraction.py tests/unit/test_document_validity.py tests/unit/test_paper_evidence_matching.py tests/integration/test_evidence_pipeline.py -q`; expected: exactly 75 official cases are portable and every taxonomy type has either an official-case fixture or a separate synthetic profile fixture.
- [ ] **Step 8: Run repository gates** with `rtk proxy uv run pytest`, `rtk proxy npm --prefix frontend run test`, and `rtk proxy npm --prefix frontend run build`; record raw result, code version, mode, and evidence path. Do not claim visual/browser verification because this plan does not redesign UI.
- [ ] **Step 9: Run M0 LIVE only under its existing authorization gate** with all-page OCR probes; record actual provider/model/response shape, calls, latency, errors, and unresolved coverage. Do not claim quality from a mocked provider run.

**Gate:** Every formal Hoangha case is represented by supported inputs (all 75), evidence gold is hand-authored on a subset (≈10–15 cases) and clearly scoped, all taxonomy values have a case or a documented gap, full offline tests pass, and LIVE evidence is reported separately from STUB/REPLAY.

## Task verification commands and test anchors

Each code task uses its command below for both RED and GREEN, before and after its minimal implementation. Environment/import setup failures alone are not a meaningful RED; each listed test must fail on the behavior it pins. Fakes and test helper builders belong to that task's test file (shared only when a later consumer exists). No provider credentials are used in these offline tests.

| Task | Focused command | Required named test and core assertions |
| --- | --- | --- |
| E1 | `rtk proxy uv run pytest tests/unit/test_document_contracts.py tests/unit/test_contracts.py -q` | `test_missing_is_not_zero`: `assert field.state == "NOT_PRESENT"; assert field.value is None`; `test_ambiguous_keeps_each_source`: `assert len(field.alternatives) == 2; assert field.value is None`. |
| E2 | `rtk proxy uv run pytest tests/unit/test_mistral_ocr.py tests/integration/test_reader_source_support.py tests/integration/test_live_read.py -q` | `test_searchable_pdf_uses_ocr_on_every_page`: `assert provider.calls == 1; assert covered_pages == (1, 2, 3); assert native_text_calls == 0`; `test_failed_artifact_write_is_technical`: `assert result.problems; assert not result.complete`. |
| E3 | `rtk proxy uv run pytest tests/unit/test_ocr_quality.py tests/unit/test_provider_contracts.py -q` | `test_word_threshold_boundary`: `assert candidate_scores == (0.849,)`; `test_no_scores_is_skipped_not_pass`: `assert review.status == "SKIPPED_NO_NUMERIC_CANDIDATES"; assert llm.calls == 0`. |
| E4 | `rtk proxy uv run pytest tests/unit/test_document_classification.py tests/integration/test_live_wiring.py -q` | `test_classification_batch_precedes_extraction`: `assert calls[0].stage == "CLASSIFY"; assert extraction_calls_for_unknown == 0`; `test_mixed_pdf_has_two_document_units`: `assert len(units) == 2; assert len({u.document_id for u in units}) == 2`. |
| E5 | `rtk proxy uv run pytest tests/unit/test_document_extraction.py tests/unit/test_document_validity.py -q` | `test_quote_from_other_source_rejected`: `assert field.state != "FOUND"`; `test_missing_critical_word_confidence_blocks`: `assert analysis.profile_status == "NEEDS_HUMAN"`; `test_second_schema_failure_is_unresolved`: `assert repair_calls == 1`. |
| E6 | `rtk proxy uv run pytest tests/unit/test_paper_evidence_matching.py -q` | `test_exact_number_preserves_hoangha_method`: `assert link.score == Decimal("1"); assert link.method == "INVOICE_NUMBER_EXACT"`; `test_overallocation_keeps_reuse_unresolved`: `assert not both_rows_auto_linked; assert findings`; `test_unknown_candidate_not_promoted`: `assert unchanged_links == links`. |
| E7 | `rtk proxy uv run pytest tests/integration/test_evidence_pipeline.py tests/integration/test_preview_job.py tests/integration/test_live_wiring.py tests/integration/test_live_read.py -q` | `test_live_evidence_never_assesses_finance`: `assert reconciler.calls == 0; assert view.conclusion is None; assert view.instructions == ()`; `test_stop_during_provider_wait`: `assert stop_returned_before_provider_release; assert late_result_not_current`. |
| E8 | `rtk proxy uv run pytest tests/unit/test_hoangha_case_inventory.py tests/integration/test_evidence_pipeline.py -q` | `test_official_uc03_inventory`: `assert formal_case_count == 75`; `test_all_stages_fit_call_budget`: `assert llm_attempts == 12; assert ocr_attempts <= 10`; `test_replay_does_not_read_gold`: `assert gold_read_spy.calls == 0`. |

The snippets above are the assertions of the named tests, not new production properties: e.g. `covered_pages`, `complete`, and call spies are values computed by the local test harness from the DTOs. For E0, verify canonical headings/links/enums/thresholds with `rtk proxy rg` and `rtk proxy git diff --check`, with no product test run. Before E8 npm commands, resolve the pinned Node 24 and verify `node --version` plus `npm --loglevel=verbose --version` in the same scoped environment per AGENTS.md. Each implementation gate also updates its checkpoint and exact evidence location; commits are separate, only if execution/Git authority is given, and stage only the task's exact files.

## Self-Review

- **Spec coverage:** Q1/Q2 all-file all-page OCR → E2; X-Kiro/final workflow ownership and existing simple job limits → E4/E7; 12-attempt schedule → E3/E8; confidence/missing-score/profile matrix → E3/E5; all document types/roles and extraction states → E1/E4/E5; per-field provenance/one job-level repair → E5; exact Hoangha matcher/cardinality/LLM suggestions → E6; all 75 formal UC-03 cases plus separate OCR smoke/synthetic type fixtures → E8; no finance/policy consumer change → E0/E7.
- **Step scan:** Every code task starts with a failing test, names the command and behavior, defines the interface/files, and ends at a testable gate. No commit is planned without Git authorization.
- **Type consistency:** async `EvidenceReader.read -> OcrSourceResult`; async root pipeline `OcrSourceResult -> DocumentClassification -> DocumentAnalysis -> EvidenceMatchingResult -> ReadResult`; only `STUB_TRANSCRIPTION` continues through current assessment. LIVE/REPLAY `ReadResult` is stored/exposed and does not cross into `AssessmentInput`/Reconciler in this plan.
- **Review Focus tests:** E2 covers hidden/native-text PDF/artifact failures; E3/E5 missing confidence and field-to-word mapping; E5 wrong quote/source and card-data minimization; E6 exact-ID risk, full scoring/row outputs, and allocation; E7 workflow consumer boundary/cross-tenant cache/Stop; E8 12-call and corpus coverage gates.
- **Proportion/scope:** One plan is justified because the sequential evidence stages share DTOs, job cache keys, and one integration gate. It stops before finance/policy; the corpus importer is included to prove all 75 formal Hoangha UC-03 cases, with other repository data roots explicitly separated.

## Execution Handoff

This is a design/implementation plan only. Implementation requires the user to review this plan and choose an execution method under the repository's `AGENTS.md`; no code or live provider call has been performed by writing this plan.

Review trail: [initial findings](../../final/reviews/2026-10-13/hoangha-evidence-plan-review.md), [independent closure of R1–R4](../../final/reviews/2026-10-13/hoangha-evidence-plan-review-response.md), [lead disposition](../../final/reviews/2026-10-13/hoangha-evidence-plan-synthesis.md). Closure is specification-level, not implementation PASS. The later explicit lifespan-worker/command-enqueue clarification was source-checked by the lead; it is not claimed as a new whole-plan audit by the reviewer.

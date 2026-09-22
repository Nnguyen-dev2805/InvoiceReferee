# InvoiceReferee — Current Architecture

## Scope

This document describes the modules and call paths present in the current
checkout. It is not a target-state architecture.

The application is a synchronous Streamlit process backed by the local
filesystem. It uses Mistral for OCR and an OpenAI-compatible Kimi endpoint for
structured reasoning.

## Runtime composition

`app/streamlit_app.py` is the composition root. It:

1. loads `.env` and `AppSettings`;
2. creates one `LocalCaseStore` and `LocalEvidenceRepository` over
   `data/submissions` by default;
3. creates `MistralOcrAdapter` only when `MISTRAL_API_KEY` exists;
4. creates `KimiReasoningAdapter` only when all Kimi settings exist;
5. injects the adapters into `CaseProcessingService`;
6. injects processing into `SubmitCaseService`;
7. routes the selected sidebar page to the employee, accounting, or OCR-debug
   view.

Streamlit resource caching keeps service and provider instances for the running
application process.

## End-to-end call path

```text
app.components.submission_form.render_submission_form
        ↓ ClaimDraft + UploadPayload[]
SubmitCaseService.submit
        ├── technical validation
        ├── SHA-256 deduplication
        └── LocalCaseStore.save_submission
                ↓ persisted case
CaseProcessingService.process_case
        ├── LocalEvidenceRepository.get_case
        ├── source gate
        ├── MistralOcrAdapter.process per supported evidence
        ├── restructure_mistral_ocr
        ├── collect_low_confidence_blocks
        ├── KimiReasoningAdapter.analyze_confidence per candidate-bearing evidence
        ├── optional KimiReasoningAdapter.analyze_conflict across evidence
        ├── evaluate_inventory_consistency
        └── LocalEvidenceRepository.save_processing_result
                ↓
employee receipt + accounting queues + OCR debug
```

There is no separate `review()` service or Verify entrypoint in the current
checkout.

## Repository structure

```text
app/
├── streamlit_app.py              composition root
├── components/
│   ├── sidebar.py                page selection
│   ├── submission_form.py        employee input
│   └── bbox_overlay.py           OCR debug rendering
├── state/submission_state.py     Streamlit form/receipt state
└── views/
    ├── employee_submission.py    submit experience
    ├── accounting_review.py      PASS/NEEDS_HUMAN queues
    └── ocr_debug.py              OCR diagnostics

src/invoice_referee/
├── config.py                     environment-backed local settings
├── domain/
│   ├── submission.py             claim, upload, evidence, receipt contracts
│   ├── processing.py             OCR/conflict/result contracts
│   └── errors.py                 submission validation error
├── application/
│   ├── submit_case.py            validation, dedupe, persistence, trigger
│   └── process_case.py           processing orchestration and current status
├── extraction/
│   ├── mistral_ocr.py            provider adapter
│   ├── kimi_reasoning.py         structured Kimi adapter and retry
│   ├── conflict_reasoning.py     cross-source prompt contract
│   ├── confidence.py             confidence normalization
│   ├── ocr_quality.py            candidate collection
│   └── word_block_mapper.py      page/block/word hierarchy
├── policy/inventory.py           deterministic inventory checks
└── storage/
    ├── base.py                   submission-store protocol
    ├── local_case_store.py       atomic case creation
    └── local_evidence_repository.py  query/result/delete operations
```

## Domain contracts

### Submission side

- `ClaimDraft`: recipient, subject, and body.
- `UploadPayload`: original name, bytes, MIME type, and evidence role.
- `EvidenceRecord`: persisted metadata including SHA-256 and relative path.
- `SubmissionReceipt`: case identifier, status, counts, size, and warnings.

### Processing side

- `RuleFinding`: rule ID, `PASS/WARN/FAIL/ERROR`, message, and source refs.
- `BlockAssessment`: structured Kimi assessment of one low-confidence candidate.
- `ConfidenceAnalysis`: document types and block assessments.
- `InventoryAnalysis` / `ConflictAnalysis`: per-document facts, mappings,
  comparisons, conflicts, and extraction warnings.
- `CaseProcessingResult`: current `PASS/NEEDS_HUMAN` result plus supporting
  evidence and diagnostics.

Some fields remain for backward compatibility with older persisted
`processing.json` files. They are not proof of an active production path.

## Provider boundaries

### Mistral OCR

`MistralOcrAdapter` sends one image as a base64 data URL or one PDF as a
document URL. It requests word confidence and returns provider/model/timestamp
metadata with the raw SDK response.

The adapter does not create a business decision.

### Kimi confidence analysis

Each call contains one evidence's OCR text and low-confidence candidate blocks.
It does not receive other documents or employee business context. The response
must validate as `ConfidenceAnalysis`.

### Kimi cross-source analysis

One call receives all OCR-readable documents after their quality gates pass.
The prompt instructs the model to extract each document independently, preserve
evidence IDs, keep employee text context-only, and avoid making the final
decision. The response must validate as `ConflictAnalysis`.

Both Kimi paths perform one bounded schema-repair attempt. Exhausted repair
raises an error and processing fails closed.

## Deterministic policy boundary

`evaluate_inventory_consistency` receives structured model output plus the
actual evidence-role and filename maps. It validates and evaluates:

- exact evidence coverage and duplicate evidence IDs;
- missing facts required for an applicable inventory comparison;
- allowed source references;
- supplier and date differences;
- item mappings and unsupported extra lines;
- decimal quantity, unit conversion, unit price, and line amount;
- receipt status;
- semantic conflicts tied to attached evidence.

The policy returns `RuleFinding[]`. `CaseProcessingService` maps any `FAIL` or
`ERROR` to `NEEDS_HUMAN`; otherwise it returns `PASS`.

## Storage model

`LocalCaseStore` writes into a temporary case directory and atomically renames
it into place after all evidence, metadata, and initial audit events are ready.
Stored filenames include generated evidence IDs and sanitized original names.

`LocalEvidenceRepository` resolves and validates case-relative paths, stores OCR
results and the latest processing result, appends a basic processing event, and
can permanently delete a complete case directory.

The store is process-local filesystem state. It has no transaction isolation,
user ownership, retention policy, or remote persistence contract.

## Failure behavior

The processor returns `NEEDS_HUMAN` for:

- missing primary bill or business context;
- missing OCR/Kimi configuration when that provider is needed;
- unsupported or failed OCR evidence;
- incomplete or invalid confidence assessment;
- blocking low-confidence fields;
- invalid/incomplete cross-source analysis;
- deterministic inventory conflicts.

Technical failures and business uncertainty are not yet represented separately.

## Known architectural limits

- The accepted upload formats are broader than the processing formats.
- Primary-only `PASS` is based on OCR quality, not complete accounting policy.
- There is no canonical normalized accounting document between OCR and policy.
- The final status model has two values rather than Challenge A's three actions.
- Audit events cannot fully reconstruct the processing input and reasoning.
- Reprocessing overwrites the current result.
- Permanent deletion removes audit history.
- All Streamlit users share one unauthenticated local case store.
- There is no Verify entrypoint or public-deployment proof.

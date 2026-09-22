# InvoiceReferee — Current Product

## Purpose

InvoiceReferee currently supports one employee expense-intake workflow. An
employee submits a description and evidence; the system reads supported
documents, checks OCR quality, optionally compares a primary bill with
supporting evidence, and routes the case to one of two current queues.

This document describes runtime behavior at the current commit. The original
competition requirements remain in
`docs/Challenge_Brief_OrganizationAI_VN.docx.md`.

## Users and views

### Employee

The employee view accepts:

- recipient, subject, and free-text business context;
- zero or more primary documents;
- zero or more supporting documents.

The submission service rejects only a completely empty submission. It can store
a description without evidence or evidence without a description, but the
processing source gate may immediately return `NEEDS_HUMAN`.

### Accounting

The accounting view lists every processed case in the shared local store and
splits them into:

- `PASS`;
- `NEEDS_HUMAN`.

It shows the business context, summary, reasoning, rule findings, OCR-quality
details, inventory comparisons, evidence previews, and processing errors. It
also permits permanent case deletion.

### OCR debug

The OCR-debug view exposes stored Mistral output, word confidence, hierarchical
page/block/word structure, and bounding-box overlays for supported images. It is
an internal diagnostic view, not a separate business-decision path.

## Accepted input

The submission boundary currently accepts these extensions:

- primary: JPG, JPEG, PNG, WEBP, PDF, XML, JSON;
- supporting: all primary extensions plus CSV, TXT, DOC, DOCX, XLS, XLSX.

The processing pipeline currently OCRs only JPG, JPEG, PNG, WEBP, and PDF. An
accepted XML, JSON, CSV, TXT, Word, or Excel file therefore produces an
unsupported-OCR processing error. This input/processing mismatch is a known
current limitation.

Default limits are:

- 12 files per submission;
- 15 MiB per file;
- 50 MiB total.

Files with identical SHA-256 content are stored once even when uploaded under
different evidence roles.

## Processing behavior

### 1. Source gate

Processing requires:

- at least one `PRIMARY_DOCUMENT` bill/evidence;
- business context from the employee description or a supporting document.

Missing sources produce specific findings before any provider is called.

### 2. OCR

Each supported evidence file is sent independently to Mistral OCR. The stored
result includes provider, model, timestamp, raw response, case ID, evidence ID,
and source filename.

A provider exception or an unsupported evidence format fails closed to
`NEEDS_HUMAN` and remains visible in `processing_errors`.

### 3. Confidence gate

OCR words are mapped into page blocks. Blocks containing meaningful words below
`OCR_WORD_REVIEW_THRESHOLD` (default `0.85`) become review candidates.

When candidates exist, Kimi receives one evidence at a time. It classifies the
candidate's importance and readability and may request human verification. The
adapter validates structured output and performs at most one JSON-repair call.
Missing, duplicate, or unknown candidate assessments fail closed.

A critical uncertain field needed for comparison routes the case to
`NEEDS_HUMAN`. Non-blocking uncertainty is retained as a warning.

### 4. Primary-only path

If no supporting document exists and the confidence gate has no blocking
finding, processing ends with `PASS`.

This path confirms only the implemented OCR-quality gate. It does not perform a
complete required-field, identity, arithmetic, duplicate, payment, policy,
authority, or anomaly review.

### 5. Cross-source path

When supporting evidence exists and all required evidence passes the confidence
gate, Kimi receives the OCR text and block context for all documents in one
cross-source call. Employee text is included only as context and must not become
an inventory fact.

Kimi may:

- classify whether inventory comparison applies;
- extract per-document facts;
- suggest equivalent line-item matches;
- propose comparisons and semantic conflicts.

Kimi must not decide the final status. Python policy code validates exact
document coverage, source references, decimal values, units, dates, item
mapping, quantities, prices, amounts, receipt status, and proposed semantic
conflicts. One additional conflict call may repair incomplete document coverage.

## Current statuses

### `PASS`

No blocking finding was produced by the gates that actually ran. `PASS` is not
equivalent to final payment approval and is not yet the Challenge A
`AUTO_PROCESS` action.

### `NEEDS_HUMAN`

At least one implemented gate could not continue safely. Causes include missing
sources, provider configuration/failure, unreadable evidence, uncertain critical
OCR content, invalid model output, incomplete source coverage, or a detected
cross-source conflict.

`NEEDS_HUMAN` currently combines business uncertainty and technical failure. It
does not yet distinguish `REQUEST_INFO`, outside-policy escalation, authority
escalation, or suspicious activity.

## Persistence and audit

Cases are stored under `data/submissions/{case_id}`:

```text
submission.json
audit.jsonl
primary/<evidence files>
supporting/<evidence files>
ocr/<evidence_id>.json
processing.json
```

Submission creation and evidence attachment create JSONL audit events. Processing
appends a `CASE_PROCESSED` event containing actor, timestamp, case ID, and current
decision. Reprocessing overwrites `processing.json`. Permanent case deletion
removes the evidence, results, and audit history.

## Security and privacy boundary

The current Streamlit application has no authentication, role enforcement,
tenant isolation, or per-session case store. Every visitor to one instance can
navigate to the accounting and OCR-debug views and access shared cases. Public
demos must therefore use synthetic or explicitly approved data.

## Challenge A gap

The following are `PLANNED`, not current functionality:

- `AUTO_PROCESS`, `REQUEST_INFO`, and `ESCALATE` as final user-facing actions;
- explicit factual-unknown, outside-policy, and beyond-authority classes;
- comprehensive deterministic accounting checks and a decision guard;
- one-action core and Challenge A Verify suites;
- new-input JSON testing through the production decision path;
- Stop and Override controls with preserved original decisions;
- complete append-only audit reconstruction;
- public deployment verification.

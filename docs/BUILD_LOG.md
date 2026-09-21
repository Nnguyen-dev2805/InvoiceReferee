# InvoiceReferee — Build Log

> This file is intentionally kept to one-page style. Update it with actual evidence throughout the sprint; do not invent usage or results.

## Project

**InvoiceReferee — AI Purchase Invoice Review & Escalation Agent**

Challenge: OrganizationAI — Challenge A, Escalation Referee.

## Current phase

Sprint 1 implemented end-to-end: business review path (Tasks 1–9 of the
implementation plan) plus the accepted structure-aware document path
(Tasks 1–10 of the structure-aware plan).

Verified state (fresh run, this revision):

- `pytest` — **509 passed, 2 skipped, 0 failed**. The 2 skips are the OCR
  runtime gate, which needs `RUN_OCR_RUNTIME=1` and the `ocr` extra.
- `python -m verify.harness --suite core` → 4/4; `--suite escalation` → 5/5;
  `--suite all` → 9/9, all through the production `review()` path.
- `python -m verify.ocr_harness` → 15 documents, field exact match 100%,
  action accuracy 100%, 0 false auto-confirms, provenance coverage 100%.
- `python -m verify.structure_harness` → 20 documents across 10 layout
  families, section accuracy 100%, field recall 100%, normalized exact match
  100%, binding accuracy 100%, 0 false auto-confirms.
- Streamlit UI runs sample + paste/upload JSON, shows checks/decision/audit, and
  exposes Stop/Override plus a one-click Run Full Verify. After an Override the
  effective decision is shown alongside the preserved original.

Document path (accepted Sprint 1 ingestion): file validation → render →
preprocess → OCR behind an `OCREngine` protocol → structure analysis →
deterministic candidate extraction → explicit conflict resolution → validation →
mandatory human confirmation → canonical evidence → the same `review()` path.
The OCR extra is optional and lazy-imported; the core JSON review runs without it.

Implemented modules: `domain/`, `ingestion/` (JSON adapter, normalization, and the
OCR/structure path), `transaction/`, `checks/` (8 checks), `policy/`, `agent/`
(LLM boundary + fallback), `decision/` (guard + fallback questions), `audit/`,
`services/reviewer.py`, `services/extractor.py`, `verify/` (business, OCR and
structure harnesses), `app/`.

Known limitations are recorded in `EVALUATION_PLAN.md` § "Document-path
evaluation" rather than being presented as resolved.

## AI tools used

Record only tools actually used by the team during implementation.

- AI coding assistant (Kiro / claude-opus based agent) used to scaffold the
  package, drive test-driven development for the domain contracts, checks, policy,
  decision guard, audit and reviewer, generate the 17 fixtures, and build the
  Verify harness and Streamlit UI.

Before submission, confirm the exact tools/models and what each was used for.

## Where AI helped

Current planning observations:

- converted a long challenge brief into implementation-focused requirements;
- pressure-tested the distinction between missing facts, outside-policy cases and beyond-authority cases;
- helped normalize interfaces so four people can work in parallel;
- defined the normal runtime as deterministic checks → policy context → LLM assessment → deterministic decision guard;
- generated candidate edge cases that still require deterministic verification.

## Where AI created cost/risk

Risks that the team must actively check during implementation:

- AI can make business rules sound plausible even when they are synthetic;
- AI may blur `REQUEST_INFO` and `ESCALATE` unless the decision boundary is explicit;
- generated questions can be fluent but too generic;
- AI-generated code must not replace verification with assumptions.

All synthetic policy values, especially the 50M authority threshold, must be labelled as synthetic.

## Largest feature cut

Sprint 1 intentionally cuts **full invoice/tax automation and broad invoice coverage**.

The product handles one narrow workflow: PO-based goods purchases with Goods Receipt. OCR, VAT/TNDN validation, accounting entries, automatic payment, complex service invoices and ERP replacement are outside Sprint 1.

Reason: the hackathon rewards a working, testable decision boundary more than a wide but unreliable feature set.

## Evidence to add before submission

- actual commits and major implementation decisions;
- actual AI tools/models used;
- one concrete place AI saved time;
- one concrete place AI caused rework or cost;
- actual feature cut if it changes;
- user feedback and resulting product change if available;
- known negative/unintended effect found in testing.

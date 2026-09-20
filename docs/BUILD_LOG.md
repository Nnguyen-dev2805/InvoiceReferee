# InvoiceReferee — Build Log

> This file is intentionally kept to one-page style. Update it with actual evidence throughout the sprint; do not invent usage or results.

## Project

**InvoiceReferee — AI Purchase Invoice Review & Escalation Agent**

Challenge: OrganizationAI — Challenge A, Escalation Referee.

## Current phase

Pre-code design and specification.

Completed planning artifacts:

- challenge summary;
- product specification;
- synthetic Policy v0;
- data-model contracts;
- decision flow;
- 17-case evaluation set;
- evaluation plan for unseen inputs and real-user validation;
- architecture and implementation plan.

## AI tools used

Record only tools actually used by the team during implementation.

Current planning use:

- AI coding assistant used to help structure specifications, challenge requirements, policy cases and implementation planning.

Before submission, replace this section with the exact tools/models and what each was used for.

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

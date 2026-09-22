# InvoiceReferee — Build Log

> Keep this document to one page for the competition submission. Record only
> work and evidence that actually occurred.

## Project

InvoiceReferee is being developed for OrganizationAI Challenge A. The current
prototype receives employee expense claims, runs OCR-quality checks, optionally
compares a bill with supporting inventory evidence, and presents accounting
review queues.

## Current stage

A working local vertical slice exists:

- Streamlit employee, accounting, and OCR-debug views;
- local submission/evidence persistence;
- Mistral OCR integration;
- OCR word-confidence and bounding-box inspection;
- Kimi confidence and cross-source structured analysis;
- deterministic bill/report inventory checks;
- `PASS/NEEDS_HUMAN` routing;
- 60 local automated tests.

The Challenge A decision taxonomy, Verify harness, Stop/Override, complete audit,
and public-deployment proof are not implemented in the current checkout.

## AI tools used

- **OpenAI Codex:** repository inspection, code/document consistency review, and
  documentation restructuring.
- **Mistral OCR:** runtime OCR provider for supported image/PDF evidence.
- **Kimi-K3 through an OpenAI-compatible endpoint:** runtime structured analysis
  for low-confidence OCR blocks and cross-source conflicts.

Provider-adapter tests use fake clients. Live-provider quality, cost, and latency
must be reported separately after a fresh credentialed run.

## Where AI helped

- turning raw OCR output into explicit confidence-review candidates;
- extracting per-document facts for bill/report comparison;
- proposing semantic conflicts while deterministic Python retains final control;
- identifying drift between implemented code, old specifications, and competition
  requirements;
- reducing the documentation set to current product, architecture, testing, and
  this build log.

## Cost and rework caused by AI-assisted development

The repository accumulated broad target-state documents that described a
different PO/GR workflow and capabilities not present in the merged runtime.
Those documents created false confidence about the decision model, Verify,
audit, and human controls. The corrective work was to inspect the actual call
path, separate fresh verification from plans, and delete stale specifications.

Model output also requires schema validation and bounded repair. Fluent OCR or
reasoning text is not treated as evidence that a business check passed.

## Largest feature cut from the current slice

The current slice does not attempt a complete accounting-policy engine. It
implements OCR quality and bill/report inventory consistency first. Duplicate,
payment, authority, broad expense-policy, suspicious-pattern, final Challenge A
decision, and Verify capabilities remain outside the running slice.

This cut kept one end-to-end path testable, but it also means `PASS` must not be
presented as a complete accounting approval.

## Evidence and remaining work

Fresh local evidence on 2026-09-22:

- `60 passed in 0.93s`;
- `pip check`: no broken requirements;
- Verify command: unavailable because the `verify` package is absent.

Still required before claiming competition readiness:

- live-provider baseline evidence;
- a public no-login deployment using safe demo data;
- an executable Challenge Verify experience;
- final human-control and audit behavior;
- honest user feedback and one demonstrated product change if the team reaches
  the stage where the competition requires real-user evidence.

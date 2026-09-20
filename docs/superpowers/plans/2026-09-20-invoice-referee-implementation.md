# InvoiceReferee Sprint 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end InvoiceReferee MVP that reviews PO-based goods purchase transactions and returns `AUTO_PROCESS`, `REQUEST_INFO`, or `ESCALATE` with auditability and one-click Verify.

**Architecture:** A single Python application with isolated domain, extraction/ingestion, transaction, deterministic-check, policy, LLM-agent, decision-guard, audit, review-service and UI/Verify modules. Raw inputs are extracted/mapped into one canonical schema before transaction construction. Deterministic logic owns factual and numeric checks. The LLM reasons over verified facts and proposes an assessment; a deterministic Decision Guard enforces policy and authority before any final action is released.

**Tech Stack:** Python 3.12, pytest, Streamlit, JSON fixtures.

**Spec:** `docs/superpowers/specs/2026-09-20-invoice-referee-design.md`

## Global Constraints

- Sprint 1 supports only `PO_GOODS_PURCHASE`.
- User-facing decisions are exactly `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`.
- Money is stored as integer VND.
- Authority threshold is synthetic 50,000,000 VND.
- Production code must not branch on test-case IDs.
- Numeric/business checks are deterministic.
- LLM output is structured as `AgentAssessment`; it never becomes the final decision directly.
- Every LLM proposal passes through a deterministic Decision Guard.
- Provider timeout/error/invalid output uses an audited deterministic fallback; fallback must not change the policy-correct action.
- `AUTO_PROCESS` never means automatic payment.
- Human Stop/Override must preserve the original decision; Stop changes workflow status, not `Decision.action`.
- Transaction type is classified before workflow-specific evidence validation.
- Duplicate identity prefers vendor tax code + invoice series + invoice number.
- Quantity checks include cumulative invoiced quantity versus cumulative received quantity per item.
- Extraction adapters never make business decisions. Unknown/unreliable parsed fields remain `null` or carry parse warnings; they are not guessed into valid values.
- Sprint 1 required ingestion path is structured JSON. XML, text-PDF and OCR/vision adapters are extensions that must output the same canonical field contract.

---

### Task 1: Project scaffold and domain contracts

**Owner:** Person 1

**Files:**
- Create: `pyproject.toml`
- Create: `src/invoice_referee/domain/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces domain types used by every later task.

- [ ] Create Python package layout under `src/invoice_referee/`.
- [ ] Define enums/constants for decision action, check status, uncertainty type and payment status.
- [ ] Define dataclasses for `ExtractedDocument`, `PurchaseOrder`, `GoodsReceipt`, `SupplierInvoice`, `PaymentRecord`, `ApprovalRecord`, `Transaction`, `CheckResult`, `Uncertainty`, `PolicyContext`, `AgentAssessment`, `Decision`, `ReviewResult`, `AuditEvent`, `HumanStop`, `HumanOverride`.
- [ ] Write tests for integer-money validation, allowed enum values and optional/null fields.
- [ ] Run `pytest tests/test_models.py -v` and confirm pass.
- [ ] Commit: `feat: add domain data contracts`.

### Task 2: JSON extraction/mapping, normalization and transaction builder

**Owner:** Person 1

**Files:**
- Create: `src/invoice_referee/ingestion/json_adapter.py`
- Create: `src/invoice_referee/ingestion/normalization.py`
- Create: `src/invoice_referee/transaction/builder.py`
- Create: `tests/test_ingestion.py`
- Create: `tests/test_builder.py`

**Interfaces:**
- Consumes raw JSON dicts/files through the Sprint 1 extraction adapter.
- Produces canonical domain objects while preserving source/parse-warning metadata needed for audit and uncertainty handling.
- Produces `Transaction`.

- [ ] Write failing tests for normal transaction linking, missing PO, multiple goods receipts, invoice relationship metadata, approval evidence and unknown payment status.
- [ ] Define the extraction contract: `document_type`, `source_type`, `source_ref`, extracted `fields`, and `parse_warnings` (optional per-field confidence may be added by non-JSON adapters).
- [ ] Implement JSON mapping as the required Sprint 1 adapter; structured fields should pass through without OCR or LLM extraction.
- [ ] Test `JSON → ExtractedDocument → normalized domain object`, including preservation of `source_ref` and `parse_warnings`.
- [ ] Implement normalization for IDs, integer VND, ISO dates and `null` unknowns.
- [ ] Implement `build_transaction(evidence) -> Transaction`.
- [ ] Ensure builder does not invent missing documents.
- [ ] Add a test proving an unreadable/uncertain critical field remains unknown instead of being guessed into a passing transaction.
- [ ] Run `pytest tests/test_ingestion.py tests/test_builder.py -v`.
- [ ] Commit: `feat: build normalized transactions`.

**Extension after the JSON vertical slice is stable:** add XML e-invoice parsing, text-PDF extraction or OCR/vision adapters one at a time. Each extension must terminate at the same extraction contract and reuse the existing normalization/builder/check pipeline.

### Task 3: Deterministic check engine

**Owner:** Person 2

**Files:**
- Create: `src/invoice_referee/checks/engine.py`
- Create: `src/invoice_referee/checks/vendor.py`
- Create: `src/invoice_referee/checks/item.py`
- Create: `src/invoice_referee/checks/quantity.py`
- Create: `src/invoice_referee/checks/price.py`
- Create: `src/invoice_referee/checks/amount.py`
- Create: `src/invoice_referee/checks/duplicate.py`
- Create: `src/invoice_referee/checks/payment.py`
- Create: `src/invoice_referee/checks/po_limit.py`
- Create: `tests/test_checks.py`

**Interfaces:**
- Consumes `Transaction`.
- Produces `list[CheckResult]`.

- [ ] Write failing tests for all 8 check groups using values from TC01, TC07, TC08, TC09, TC10, TC11, TC12, TC16 and TC17.
- [ ] Implement each check as a pure function where practical; quantity check must evaluate current and cumulative quantity, and payment check must handle PARTIALLY_PAID.
- [ ] Implement `run_checks(transaction) -> list[CheckResult]`.
- [ ] Gate PO-specific checks by transaction type. For unknown/outside-policy types, workflow-specific checks must return `NOT_APPLICABLE` or be skipped without creating fake missing-evidence failures.
- [ ] Ensure no check returns final `Decision` values.
- [ ] Run `pytest tests/test_checks.py -v`.
- [ ] Commit: `feat: add deterministic invoice checks`.

### Task 4: Policy, LLM Agent, and Decision Guard

**Owner:** Person 3

**Files:**
- Create: `src/invoice_referee/policy/config.py`
- Create: `src/invoice_referee/policy/engine.py`
- Create: `src/invoice_referee/agent/llm_client.py`
- Create: `src/invoice_referee/agent/prompts.py`
- Create: `src/invoice_referee/agent/service.py`
- Create: `src/invoice_referee/decision/guard.py`
- Create: `src/invoice_referee/decision/fallback_questions.py`
- Create: `tests/test_agent.py`
- Create: `tests/test_decision.py`

**Interfaces:**
- Policy consumes `Transaction + list[CheckResult]` and produces immutable `PolicyContext`.
- LLM Agent consumes `Transaction + list[CheckResult] + PolicyContext` and produces structured `AgentAssessment`.
- Decision Guard consumes verified facts plus `AgentAssessment` and produces final `Decision`.

- [ ] Encode Policy v0 IDs P01–P15 and the 50M synthetic authority threshold.
- [ ] Implement `build_policy_context(transaction, checks) -> PolicyContext` without mutating facts/checks; `scope_status` must be tri-state `UNKNOWN | OUTSIDE_POLICY | IN_SCOPE`.
- [ ] Implement prompt v1. The LLM receives only normalized transaction facts, check results and policy context; it must not perform authoritative arithmetic or rewrite facts. For multi-issue cases it selects one valid unresolved check as `primary_check_id` and returns traceable policy/evidence references.
- [ ] Implement the provider boundary with timeout/error handling and strict structured-output validation.
- [ ] Write Agent tests for valid structured output, timeout/provider error and invalid output.
- [ ] Implement deterministic Decision Guard priority: unknown transaction type → outside policy → in-scope factual unknown → beyond authority → auto-process.
- [ ] Add safety tests where the LLM proposes `AUTO_PROCESS` despite `FACTUAL_UNKNOWN`, `OUTSIDE_POLICY`, `BEYOND_AUTHORITY` or P15 flagged input; Guard must reject/override the proposal.
- [ ] Add a multi-issue test proving `primary_check_id`, policy rule IDs and evidence refs must exist in the supplied checks/input; invented references are invalid structured output.
- [ ] Keep deterministic explanation/question templates only for provider-error/invalid-output fallback and mark fallback use in the assessment/audit.
- [ ] Ensure `REQUEST_INFO` always has a concrete question and `ESCALATE` has target when policy knows it.
- [ ] Persist model identifier when configured, prompt version, LLM/Guard disagreement and fallback state for auditability.
- [ ] Run `pytest tests/test_agent.py tests/test_decision.py -v`.
- [ ] Commit: `feat: add policy llm assessment and decision guard`.

### Task 5: Audit and human control

**Owner:** Person 4

**Files:**
- Create: `src/invoice_referee/audit/store.py`
- Create: `tests/test_audit.py`

**Interfaces:**
- Appends `AuditEvent`, `HumanStop` and `HumanOverride` records.

- [ ] Write failing tests that decision history remains after Stop/Override and Stop does not mutate `Decision.action`.
- [ ] Implement append-only in-memory audit store with export-to-JSON method.
- [ ] Implement `record_stop(...)` for workflow status and `record_override(...)` preserving `original_action`.
- [ ] Add events for transaction creation, check completion, LLM assessment/fallback, Decision Guard, final decision, stop and override.
- [ ] Run `pytest tests/test_audit.py -v`.
- [ ] Commit: `feat: add audit trail and human override`.

### Task 6: End-to-end reviewer service

**Owner:** Person 4, integrate with Persons 1–3

**Files:**
- Create: `src/invoice_referee/services/reviewer.py`
- Create: `tests/test_reviewer.py`

**Interfaces:**
- Produces one `ReviewResult` for UI and Verify.

- [ ] Write integration test for TC01 end-to-end before implementation.
- [ ] Implement `review(evidence) -> ReviewResult` using builder → checks → policy context → LLM assessment → decision guard → audit.
- [ ] Add integration tests for TC09, TC13 and TC14.
- [ ] Add integration tests for normal LLM execution, provider-failure fallback and invalid structured output.
- [ ] Ensure the reviewer contains no case-ID branches.
- [ ] Run `pytest tests/test_reviewer.py -v`.
- [ ] Commit: `feat: integrate review workflow`.

### Task 7: Test fixtures and Verify harness

**Owner:** Person 2, expected-outcome review by Person 3, integration support from Person 4

**Files:**
- Create: `tests/fixtures/TC01.json` through `tests/fixtures/TC17.json`
- Create: `verify/harness.py`
- Create: `tests/test_verify.py`

**Interfaces:**
- Uses only the production `review()` service.

- [ ] Encode all 17 cases from `docs/TEST_CASES.md` as JSON fixtures.
- [ ] Add manifest mapping case IDs to expected decisions outside production code.
- [ ] Implement Core Verify: TC01, TC07, TC13, TC14.
- [ ] Implement Challenge A Verify: TC01, TC02, TC03, TC07, TC13.
- [ ] Implement `--suite all` as the judge path that runs Core + Challenge A suites from one command and reports each suite/case clearly.
- [ ] Output case, expected, actual, pass/fail, uncertainty type, question, target, LLM/fallback status and timestamp.
- [ ] Add one mutation/unseen test that changes amounts without changing code.
- [ ] Add one test with a fake unsafe LLM proposal and prove the production Decision Guard still returns the policy-correct action.
- [ ] Run `pytest tests/test_verify.py -v`.
- [ ] Commit: `test: add sprint one verify harness`.

### Task 8: Streamlit demo UI

**Owner:** Person 4

**Files:**
- Create: `app/streamlit_app.py`
- Create/Modify: `README.md`

**Interfaces:**
- Calls `review()` and Verify harness only.

- [ ] Add a homepage one-line instruction for judge.
- [ ] Add sample selector plus paste/upload JSON for arbitrary unseen transactions.
- [ ] Show evidence and 8 check results.
- [ ] Show LLM assessment status/explanation plus final decision, reason, question and target.
- [ ] Surface when deterministic fallback was used because the LLM provider failed or returned invalid output.
- [ ] Add Audit History view.
- [ ] Add Stop and Override controls with required reason.
- [ ] Add one-click **Run Full Verify** plus separate Core Verify and Escalation Verify controls for debugging.
- [ ] Manually run the UI and capture any integration defects as tests before fixing.
- [ ] Commit: `feat: add judge-ready demo ui`.

### Task 9: Full verification and deployment preparation

**Owner:** Integration lead

**Files:**
- Modify: `README.md`
- Modify: `docs/BUILD_LOG.md`

- [ ] Run the full test suite: `pytest -v`.
- [ ] Run all 17 fixtures through reviewer and compare expected actions.
- [ ] Run Core Verify and Challenge A Verify from a clean process.
- [ ] Run Full Verify (`--suite all`) from a clean process and confirm one action exposes both required suites.
- [ ] Run at least two unseen inputs not stored as fixtures.
- [ ] Test normal LLM execution, provider timeout/error, invalid structured output and LLM/Guard disagreement.
- [ ] Test Stop/Override and inspect resulting audit entries.
- [ ] Validate setup from a clean clone/environment using the Run & Verify section in `README.md`.
- [ ] Deploy public Streamlit URL and verify no login is required.
- [ ] Update Build Log with actual AI tools, failures, time costs and largest cut feature.
- [ ] Commit: `docs: finalize runbook and build evidence`.

## Parallel execution map

After Task 1 locks the contracts:

```text
Person 1 → Task 2
Person 2 → Task 3, then fixtures + Verify lead
Person 3 → Task 4 (policy + LLM Agent + Decision Guard) + expected-outcome/question review
Person 4 → Task 5 + reviewer integration + UI/deploy
```

Then integrate through Tasks 6–9.

## Day-level checkpoints

### End of Day 1

At least TC01 must run end-to-end through production modules.

### End of Day 2

All 17 cases have implemented behavior; Verify and UI are integrated.

### Day 3

No major new features. Focus on regression fixes, unseen inputs, deployment, slides/video and reproducibility.

# InvoiceReferee Sprint 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end InvoiceReferee MVP that reviews PO-based goods purchase transactions and returns `AUTO_PROCESS`, `REQUEST_INFO`, or `ESCALATE` with auditability and one-click Verify.

**Architecture:** A single Python application with isolated domain, ingestion, transaction, check, policy/decision, audit, review-service and UI/Verify modules. Deterministic logic owns factual and numeric checks; the decision layer applies policy and authority boundaries.

**Tech Stack:** Python 3.12, pytest, Streamlit, JSON fixtures.

**Spec:** `docs/superpowers/specs/2026-09-20-invoice-referee-design.md`

## Global Constraints

- Sprint 1 supports only `PO_GOODS_PURCHASE`.
- User-facing decisions are exactly `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`.
- Money is stored as integer VND.
- Authority threshold is synthetic 50,000,000 VND.
- Production code must not branch on test-case IDs.
- Numeric/business checks are deterministic.
- `AUTO_PROCESS` never means automatic payment.
- Human Stop/Override must preserve the original decision; Stop changes workflow status, not `Decision.action`.
- Transaction type is classified before workflow-specific evidence validation.
- Duplicate identity prefers vendor tax code + invoice series + invoice number.
- Quantity checks include cumulative invoiced quantity versus cumulative received quantity per item.

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
- [ ] Define dataclasses for `PurchaseOrder`, `GoodsReceipt`, `SupplierInvoice`, `PaymentRecord`, `ApprovalRecord`, `Transaction`, `CheckResult`, `Decision`, `AuditEvent`, `HumanStop`, `HumanOverride`.
- [ ] Write tests for integer-money validation, allowed enum values and optional/null fields.
- [ ] Run `pytest tests/test_models.py -v` and confirm pass.
- [ ] Commit: `feat: add domain data contracts`.

### Task 2: JSON ingestion, normalization and transaction builder

**Owner:** Person 1

**Files:**
- Create: `src/invoice_referee/ingestion/json_loader.py`
- Create: `src/invoice_referee/ingestion/normalization.py`
- Create: `src/invoice_referee/transaction/builder.py`
- Create: `tests/test_builder.py`

**Interfaces:**
- Consumes raw JSON dicts/files.
- Produces `Transaction`.

- [ ] Write failing tests for normal transaction linking, missing PO, multiple goods receipts, invoice relationship metadata, approval evidence and unknown payment status.
- [ ] Implement normalization for IDs, integer VND, ISO dates and `null` unknowns.
- [ ] Implement `build_transaction(evidence) -> Transaction`.
- [ ] Ensure builder does not invent missing documents.
- [ ] Run `pytest tests/test_builder.py -v`.
- [ ] Commit: `feat: build normalized transactions`.

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
- [ ] Ensure no check returns final `Decision` values.
- [ ] Run `pytest tests/test_checks.py -v`.
- [ ] Commit: `feat: add deterministic invoice checks`.

### Task 4: Policy and decision engine

**Owner:** Person 3

**Files:**
- Create: `src/invoice_referee/policy/config.py`
- Create: `src/invoice_referee/policy/engine.py`
- Create: `src/invoice_referee/decision/engine.py`
- Create: `src/invoice_referee/decision/questions.py`
- Create: `tests/test_decision.py`

**Interfaces:**
- Consumes `Transaction` + `list[CheckResult]`.
- Produces `Decision`.

- [ ] Encode Policy v0 IDs P01–P15 and the 50M synthetic authority threshold.
- [ ] Write failing tests for factual unknown, outside policy, beyond authority and clean routine flow.
- [ ] Implement decision priority: unknown transaction type → outside policy → in-scope factual unknown → beyond authority → auto-process.
- [ ] Implement question templates that include concrete evidence values.
- [ ] Ensure `REQUEST_INFO` always has a question and `ESCALATE` has target when policy knows it.
- [ ] Run `pytest tests/test_decision.py -v`.
- [ ] Commit: `feat: add policy and decision boundary`.

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
- [ ] Add events for transaction creation, check completion, decision, stop and override.
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
- [ ] Implement `review(evidence) -> ReviewResult` using builder → checks → decision → audit.
- [ ] Add integration tests for TC09, TC13 and TC14.
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
- [ ] Output case, expected, actual, pass/fail, uncertainty type, question, target and timestamp.
- [ ] Add one mutation/unseen test that changes amounts without changing code.
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
- [ ] Show final decision, reason, question and target.
- [ ] Add Audit History view.
- [ ] Add Stop and Override controls with required reason.
- [ ] Add one-click Core Verify and Escalation Verify.
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
- [ ] Run at least two unseen inputs not stored as fixtures.
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
Person 3 → Task 4 + expected-outcome/question review
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


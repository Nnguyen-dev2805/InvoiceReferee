# InvoiceReferee Sprint 1 Design

**Date:** 2026-09-20  
**Status:** Approved pre-code design  
**Challenge:** OrganizationAI — Challenge A, Escalation Referee

## 1. Goal

Build a working review agent for PO-based goods purchases that can process routine transactions automatically and stop at the correct boundary when facts are missing, policy does not cover the case, or human authority is required.

## 2. User

Primary user: buyer-side Accounts Payable / kế toán thanh toán.

Supporting roles: Purchasing, Warehouse/Receiver, Supplier, Finance Manager.

## 3. Product boundary

Supported Sprint 1 workflow:

```text
PO → Goods Receipt → Supplier Invoice → Review → Payment Review
```

The system does not execute payment.

## 4. Inputs

- Purchase Order
- Goods Receipt
- Supplier Invoice
- Payment History
- Synthetic Company Policy v0

JSON is the primary Sprint 1 format. The input boundary is explicitly split into extraction and normalization:

```text
JSON/API      → structured mapping ┐
XML           → XML parser         │
Text PDF      → text extraction    ├→ canonical fields → normalization → domain objects
Scan/Image    → OCR/Vision         │
                                  ┘
```

All adapters must preserve missing/uncertain fields as unknown or parse warnings instead of guessing values. XML/PDF/OCR are extension adapters, not the core product; the required Sprint 1 vertical slice uses structured JSON.

## 5. Transaction model

The core object is a transaction linking the evidence above. An invoice is never reviewed in isolation when matching evidence exists. Transaction history also keeps structured approval evidence and invoice relationship metadata for original/adjustment/replacement documents.

Schema contracts are defined in `docs/DATA_MODEL.md`.

## 6. Checks

The deterministic check layer evaluates:

1. vendor match;
2. item match;
3. quantity match, including cumulative invoiced quantity versus cumulative received quantity by item;
4. unit price match;
5. amount validity;
6. duplicate invoice;
7. payment status;
8. cumulative PO limit.

These checks return facts; they do not make the final action decision.

## 7. Decision boundary

Only three user-facing actions exist:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

Priority:

```text
Unknown transaction type                   → REQUEST_INFO
Known type outside policy                  → ESCALATE
In-scope missing/conflicting required fact → REQUEST_INFO
Beyond authority                           → ESCALATE
All clear + in authority                   → AUTO_PROCESS
```

Synthetic authority threshold: transactions above 50,000,000 VND require Finance Manager approval.

## 8. Specific-question requirement

Any non-routine decision must identify the exact missing fact or authority decision. Generic “please review” messages are invalid.

Example:

> PO được phê duyệt 30M nhưng invoice là 35M. Có PO điều chỉnh hoặc phê duyệt tăng thêm 5M không?

## 9. Human-in-the-loop

Human users can stop or override any agent decision. Stop changes workflow status only; Override changes the effective decision to another valid user-facing action. The original agent decision remains in audit history with actor, timestamp and reason.

## 10. Auditability

Every review must make it possible to reconstruct:

- what action was taken;
- when;
- which evidence was used;
- which policy/check applied;
- why the result was produced.

## 11. Architecture

```text
Raw Evidence
→ Extraction Adapter
→ Canonical Fields / Parse Warnings
→ Normalization
→ Transaction Builder
→ Deterministic Check Engine
→ Policy Context
→ LLM Agent Assessment
→ Deterministic Decision Guard
→ Audit
→ UI / Verify
```

UI and Verify both use the same reviewer service to prevent demo-only logic.

Detailed module boundaries are in `docs/ARCHITECTURE.md`.

## 12. Evaluation dataset

The ground-truth set contains 17 cases in `docs/TEST_CASES.md`.

Challenge A Verify uses:

- 3 routine `AUTO_PROCESS` cases;
- 1 `REQUEST_INFO` factual-unknown case;
- 1 `ESCALATE` beyond-authority case.

Core Verify uses 4 cases and includes routine, request-info and escalation behavior.

## 13. New-input requirement

Production code must evaluate fields and policy rules, never case IDs. Judge inputs can change amounts, vendors, quantities and transaction types without requiring code changes. Streamlit must expose a paste/upload JSON path for these unseen inputs.

## 14. Technology strategy

Use the smallest stack that supports a public demo:

- Python 3.12;
- standard-library/domain logic where practical;
- pytest for tests;
- Streamlit for the demo UI;
- JSON fixtures for Sprint 1 data.

LLM Agent is a first-class Sprint 1 component in the normal review path. It reasons over verified structured facts and produces a structured assessment with proposed uncertainty/action, explanation, specific question and target. Deterministic calculations remain outside the LLM, and a deterministic Decision Guard validates every proposal before the final action is released. Template-based explanation/questions exist only as a provider-error or invalid-output fallback, which must be visible in audit logs.

## 15. Failure behavior

Malformed or unsupported technical input returns a technical input error. Missing business evidence is a valid transaction state and routes through `REQUEST_INFO` or `ESCALATE` according to policy.

## 16. Non-goals

- full tax compliance;
- accounting entries;
- fraud detection;
- all invoice types;
- automatic payment;
- ERP replacement;
- complex OCR pipeline;
- microservice architecture.

## 17. Success criteria

- 17 documented cases have deterministic expected results;
- 3 routine Challenge A Verify cases auto-process;
- 2 Challenge A Verify cases correctly stop automation for human involvement;
- questions are specific;
- unseen inputs use the same policy logic;
- audit events are visible;
- Stop/Override is functional;
- one-click Verify uses the production review path.

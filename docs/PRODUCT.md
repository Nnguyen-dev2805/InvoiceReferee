# InvoiceReferee — Product (current state)

> Current-state document for the B1 rebuild. It describes behavior that exists in
> source and is covered by tests, and marks everything else **PLANNED**. It is not
> the target architecture; see `docs/specs/` for the agreed contracts and
> `docs/ARCHITECTURE.md` for the wiring.

## What the product does

An operator submits a reimbursement claim plus evidence. The system verifies the
applicable rules, and then either **creates a payment request** for an eligible
routine case, or **asks the right person a concrete question** (employee,
reviewer, or approver). Human answers lead to a reevaluation with
traceable decisions.

There is **one app for one operator**, with demo role selection (EMPLOYEE,
REVIEWER, APPROVER). Demo roles are **not** authenticated company
identity. `CREATED` is **not** `PAID`: the product creates a payment request, it
does not transfer money.

## Profiles

| Profile | Required evidence | Supporting checks |
| --- | --- | --- |
| TRAVEL | Primary bill (merchant, date, total, currency) | Amount vs verified bill; context declaration |
| CLIENT_MEAL | Primary bill | As TRAVEL, plus purpose declaration |
| WORK_PURCHASE | Primary bill + goods receipt + received-full | Item mapping, quantity/unit, dates, supplier |

`OTHER` is outside the B1 catalog (approver classifies or rejects).

## Decision actions (IMPLEMENTED — pure reducer)

- `CREATE_PAYMENT_REQUEST` — all applicable checks pass and required authority is
  in force (routine `ROUTINE_AUTO`, or `HUMAN_AUTHORIZED` after a valid approval).
- `REQUEST_INFO` — an unresolved factual blocker (missing/uncertain fact).
- `ESCALATE` — an outside-policy or beyond-authority blocker needs an owner.
- `REJECT` — a known supported-rule refusal (company-paid, personal purpose).
- `NONE` — a technical block: config not active, provider/contract failure, or Stop.

## Verification model (IMPLEMENTED)

- Numeric facts are usable only when source, normalization, and word-score coverage
  pass the **active policy threshold** (B1: 0.85). A model `READABLE` claim never
  waives missing/low-score coverage.
- Deterministic Python — not the model — decides applicability, arithmetic,
  eligibility, amount, policy limits, and authority. The model proposes facts and
  a cross-source mapping only.
- A required field that is missing/uncertain/unusable is a factual blocker, never
  an automatic approval. An invalid/contradictory model output is a technical
  `INVALID_ANALYSIS`, never a fabricated employee violation.

## Vertical slice (IMPLEMENTED, fake-pipeline evidence)

| Scenario | Result |
| --- | --- |
| TRAVEL 1,200,000, clean source | `CREATE_PAYMENT_REQUEST` (ROUTINE_AUTO) |
| Missing primary bill | `REQUEST_INFO` (SRC-01, EMPLOYEE) — no provider call |
| Multiple primary bills | `REQUEST_INFO` — ask to clarify/split, no provider call |
| Amount 2,000,001 | `ESCALATE` to APPROVER (AUTH-01) |
| Company-paid / PERSONAL purpose | `REJECT` — no provider call |
| Inactive config | `NONE` / `CONFIG_NOT_ACTIVE` — no provider call |
| Transport / invalid schema | `NONE` with `technical_code` |
| WORK_PURCHASE clean | Runs inventory + cross-source; `CREATE_PAYMENT_REQUEST` |
| WORK_PURCHASE numeric uncertain | `REQUEST_INFO` (REVIEWER) |

## Provider mode and limitations

- **Fake mode** (`FakeProviders`) is the default for tests and the vertical slice.
  **Live mode** (`LiveProviders`) exists behind explicit composition; it is **not**
  exercised end-to-end here.
- Fake-pipeline tests prove wiring, not live OCR/Kimi quality. No network call is
  made in the test suite.
- No caching in B1: a reevaluation re-calls providers.

## PLANNED (not yet built)

- Human-action closure and input revision (T07).
- One-process executor, Stop, and atomic request lifecycle wiring to the API (T08).
- FastAPI surface and React UI (T09/T10).
- Verify runner/corpus, B1 freeze, B2 adaptation, deployment, submission (T11–T16).
- Bank transfer, tenancy/auth, queues, distributed jobs, scaling — out of scope.

Do not treat a PLANNED capability as operational because a spec or plan names it.

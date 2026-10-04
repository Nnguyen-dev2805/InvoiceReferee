# InvoiceReferee

Expense-reimbursement MVP (OrganizationAI Challenge A). The system receives a
claim plus evidence, verifies applicable rules, and either creates a payment
request for eligible routine cases or asks the right person a concrete question.
Human responses lead to reevaluation with traceable decisions and controls.

This repository is a rebuild: **B0** (`main`) is the historical reference, the
accepted rebuild is **B1**, and measured improvements are compared against frozen
B1 as **B2**.

## Status (current state — T01 only)

- **IMPLEMENTED (T01):** Python package scaffolding, Pydantic v2 domain records,
  enums, errors, policy config with explicit demo activation, snapshot hashing,
  and gold-independent test builders.
- **PLANNED:** numeric/quality evaluators, policy evaluators, SQLite storage,
  OCR/Kimi adapters, pipeline, human actions, executor/Stop, FastAPI, React UI,
  Verify, B1 freeze, B2 adaptation, deployment and submission.

Nothing below T01 is operational yet; do not treat planned modules as running.

## Requirements

- Python `>=3.12,<3.15` (verified on 3.14.5)

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pip check
```

Exact resolved versions are pinned in `requirements.lock`.

## Tests

```bash
.venv/bin/python -m pytest tests/unit/test_contracts.py -q
```

## Policy

The demo policy (`config/demo-policy.json`, version `demo-expense-v0.1-proposed`)
holds PROPOSED rulebook values. It starts **inactive** (`active=false`,
`origin='proposed'`); a run may only use it after an explicit, versioned
activation (`activate_demo_policy`) that records a UUID activation id, a reason,
and `origin='developer_activated_demo'`. Demo role selection is not
authenticated company identity; `CREATED` is not `PAID`.

## Configuration

Copy `.env.example` to `.env` (Git-ignored) and fill values as needed. Never
commit credentials, uploaded documents, OCR/model outputs, or local case data.

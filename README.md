# InvoiceReferee

## Current design and coding entry points

The accepted advance/settlement design is maintained in four documents:
[Product](docs/settlement/PRODUCT.md), [Rulebook](docs/settlement/RULEBOOK.md),
[System](docs/settlement/SYSTEM.md), and [Evaluation](docs/settlement/EVALUATION.md).
Implementation proceeds through [the six UI slices](docs/superpowers/plans/2026-10-09-settlement-mvp.md).

The runtime/status/setup sections below describe the earlier claim-processing
implementation; they do not establish that the new settlement spec is implemented
or verified. Check source and fresh execution before capability claims. Original
discovery notes, reviews and previous specs are preserved in [the archive](docs/archive/README.md).

Expense-reimbursement MVP (OrganizationAI Challenge A). The system receives a
claim plus evidence, verifies applicable rules, and either creates a payment
request for eligible routine cases or asks the right person a concrete question.
Human responses lead to reevaluation with traceable decisions and controls.

This repository is a rebuild: **B0** (`main`) is the historical reference, the
accepted rebuild is **B1**, and measured improvements are compared against frozen
B1 as **B2**.

## Status

- **IMPLEMENTED (T01–T11):** domain contracts + demo policy (T01); numeric/quality
  (T02); policy/decision engine (T03); SQLite history + atomic request lifecycle
  (T04); Mistral OCR / Kimi adapters (T05); production pipeline (T06); human-action
  validation + closure (T07); one-process executor + Stop/Override (T08); FastAPI
  (T09); React UI (T10); Verify corpus + runner (T11).
- **PLANNED:** B1 freeze/comparison contract (T12), B2 adaptation + independent
  eval (T13), real-user study (T14), deployment + runbook (T15), submission package
  (T16).
- **LIVE END-TO-END: INCONCLUSIVE** — no live provider call has been made. All
  evidence so far is fake/replay (no network). Live OCR/Kimi quality is unmeasured.

`CREATED` is not `PAID`: the system creates a payment **request**, never a bank
transfer.

## Requirements

- Python `>=3.12,<3.15` (verified on 3.14.5)
- Node `>=20` + npm (verified on Node 26 / npm 11) — for the frontend

## Setup

```bash
# Backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pip check

# Frontend
npm --prefix frontend install
```

Exact resolved Python versions are pinned in `requirements.lock`; frontend
versions are pinned in `frontend/package-lock.json`.

## Run the app (dev)

The app needs two processes. The backend listens on **port 8000** because the Vite
dev server proxies `/api` to `127.0.0.1:8000` (see `frontend/vite.config.ts`).

**1. Configuration** — copy `.env.example` to `.env` (Git-ignored) and set:

```bash
PROVIDER_MODE=fake        # `fake` = no network; `live` = real Mistral + Kimi
DATA_ROOT=data            # SQLite + artifacts/evidence live here
# For live mode only:
MISTRAL_API_KEY=...
KIMI_API_KEY=...          # OR the B0 form: KIMI_TOKEN=... + KIMI_SECRET=...
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_MODEL=kimi-k2.6
MISTRAL_OCR_MODEL=mistral-ocr-latest
```

The runtime loads the repo-root `.env` at startup; an explicitly exported
environment variable always overrides the file. There is **no** live→fake
fallback: a missing key fails closed with `CONFIG_NOT_ACTIVE`.

**2. Backend:**

```bash
.venv/bin/uvicorn invoice_referee.api.app:create_runtime_app --factory --port 8000
```

Check: <http://127.0.0.1:8000/api/health> → `{"status":"ok", ...}`.

**3. Frontend:**

```bash
npm --prefix frontend run dev
```

Open <http://127.0.0.1:5173>.

### What you can do in the UI

1. **Activate the demo policy** (enter a reason). The policy starts INACTIVE; the
   system will not auto-process anything until it is explicitly activated.
2. **Submit a claim** (profile, purpose, amount as digits, one or more files with a
   role) → the run starts and the UI polls until it finishes.
3. **Verify panel** runs the Core / Escalation / All suites through the same
   production service (replay mode, no network) and shows expected vs actual.

### Provider modes

- `PROVIDER_MODE=fake` — wires an **empty** fake provider. It proves the wiring
  only: submitting a claim yields a technical `PROVIDER_FAILED` (fail-closed, never
  a fabricated approval). Use the **Verify panel** (replay corpus) to exercise the
  full decision path offline.
- `PROVIDER_MODE=live` — real Mistral OCR + Kimi. **This spends money** and needs
  the keys above. Try one simple claim first to confirm both providers respond.

## Tests

```bash
# Backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pip check

# Frontend
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

## Verify (offline corpus)

```bash
.venv/bin/python -m invoice_referee.verify --suite core --mode replay --output data/verify
.venv/bin/python -m invoice_referee.verify --suite escalation --mode replay --output data/verify
.venv/bin/python -m invoice_referee.verify --suite all --mode replay --output data/verify
```

`core` = TC01/03/04/11; `escalation` = TC01/02/03/06/11; `all` = the 15-case
development corpus. Exit code is non-zero if any case FAILs. The runner drives the
real `CaseService`; expected labels live only in `tests/fixtures/**/manifest.json`
and the runner, never in the application path.

## Policy

The demo policy (`config/demo-policy.json`, version `demo-expense-v0.1-proposed`)
holds PROPOSED rulebook values. It starts **inactive** (`active=false`,
`origin='proposed'`); a run may only use it after an explicit, versioned activation
(`activate_demo_policy`) that records a UUID activation id, a reason, and
`origin='developer_activated_demo'`. Demo role selection is not authenticated
company identity.

## Layout

```
src/invoice_referee/    domain, policy, storage, extraction, application, api, verify
frontend/               React + TypeScript + Vite UI
config/                 demo-policy.json (proposed, inactive)
tests/                  unit + integration; fixtures/ holds the Verify corpus
scripts/                make_synthetic_evidence.py (regenerate the corpus)
docs/                   specs, plans, evidence, build log
data/                   runtime SQLite + artifacts (Git-ignored)
```

## Configuration safety

Never commit credentials, uploaded documents, OCR/model outputs, or local case
data. `.env` and `data/` are Git-ignored.

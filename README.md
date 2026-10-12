# InvoiceReferee

Advance/expense-settlement MVP (OrganizationAI Challenge A). The system receives
a dossier plus sources, completes sourced checks/reports (B3/B7), or asks the
right owner a concrete question; human responses lead to reevaluation. Accountant
review, authorized decisions, actual money and closure are distinct stages.

This repository is a rebuild: **B0** (`main`) is the historical reference, the
accepted rebuild is **B1**, and measured improvements are compared against frozen
B1 as **B2**.

## Navigation — what are you here to do?

| Intent | Start here |
| --- | --- |
| **Understand the business** | [Product](docs/settlement/PRODUCT.md) · [Rulebook](docs/settlement/RULEBOOK.md) · [System](docs/settlement/SYSTEM.md) · [Evaluation](docs/settlement/EVALUATION.md) |
| **Run a demo** | [Generate the recipe](#generate-the-demo-recipe) → [Setup](#setup) → [Run the app](#run-the-app-dev) |
| **Evaluate** | [Verify (evaluation)](#verify-evaluation) · [Evaluation](docs/settlement/EVALUATION.md) |
| **History / legacy** | [Archive](docs/archive/README.md) · [completed plans](#history--completed-plans) |

Canonical docs are the four above plus the [MVP plan](docs/superpowers/plans/2026-10-09-settlement-mvp.md).
Completed implementation plans are history, not a second rulebook. Check source
and fresh execution before capability claims.

## Generate the demo recipe

The travel demo is a synthetic, fake/replay-only packet (never a measured
baseline, gold label or holdout). It is Git-ignored; generate it before the
steps in [Run the app](#run-the-app-dev):

```bash
.venv/bin/python scripts/build_travel_demo.py \
  --work-ref WORK-DEMO-TRAVEL \
  --settlement-as-of 2026-10-14T23:59:59+07:00
```

This writes `data/settlement/travel-demo-v1/` (employee-input / company-input /
followup / expected partitions). Then start the app in **fake** mode pointing at
the generated config:

```bash
SETTLEMENT_PROVIDER_MODE=fake \
SETTLEMENT_B3_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b3-context.json \
SETTLEMENT_B7_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b7-config.json \
SETTLEMENT_DB_PATH=data/settlement/travel-demo-v1/cases.sqlite \
SETTLEMENT_ARTIFACT_ROOT=data/settlement/travel-demo-v1/artifacts \
.venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8000
```

The recipe README (`data/settlement/travel-demo-v1/README.md`, generated) lists
the employee/accountant/approver steps and the literal expected oracle.

## Status

- **IMPLEMENTED (settlement rebuild):** intake/stale-version/idempotency guards
  (W01); B7 report with sourced checks (W02); provider readers with budget and
  call trace, live mode fail-closed (W03); B3 advance checks and owner-scoped
  questions with re-check (W04); authority-gated decisions, actual money with
  incidents, Stop/resume and closure gates (W05); evaluation harness + Verify
  CLI/UI over the frozen development corpus (W06).
- **IMPLEMENTED (B1–B9, staged workflow):** B1/B2 intake and work permission;
  B3 verbal intake + present-and-approve; B4 advance decision; B5 actual advance
  receipts; B6→B7 linked settlement; B8 settlement present/decision; B9 actual
  settlement money (P/RA/RP), fulfillment/revalidation, handoff and closure with
  post-closure adjustment. Fake/replay + HUMAN_SOURCE_REVIEW; no bank transfer.
- **Earlier claim-processing app (T01–T11):** kept as historical reference on
  `main`/B0. Its Verify corpus (15 claims) is legacy — it is NOT the accepted
  20-packet settlement evaluation below.
- **LIVE END-TO-END: INCONCLUSIVE** — no live provider call has been made. All
  settlement evidence so far is fake/replay (no network). Live OCR/LLM quality
  is unmeasured; the measured baseline below reflects the fake reader's
  capability, reported truthfully (first-pass routine completion 0/9, FP 9/9
  on the narrative corpus in fake mode).
- **PLANNED:** live provider bring-up (M0/M1), quality comparison B2, real-user
  study (3+ professional users), deployment/submission package.

`CREATED` is not `PAID`; `APPROVED` is not `RECEIVED`. The system never transfers
bank funds.

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

### Settlement rebuild (current normal entrypoint)

The accepted settlement design runs on its own core (SQLite + artifacts under
`data/settlement/`, Git-ignored) with its own API factory and UI slice:

```bash
# Backend (port 8000; the Vite dev server proxies /api here)
.venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app --factory --host 127.0.0.1 --port 8000

# Frontend (normal UI now mounts the settlement App)
npm --prefix frontend run dev -- --host 127.0.0.1
```

Implemented so far (W01–W06): create case → upload sources → reload → open the
stored original (stale-version and idempotency guards); B3/B7 reports with sourced
checks and unknown-as-null; questions with owner/refs and re-check resolution;
decisions (authority-gated), actual money with incidents, Stop/resume, handoff
and closure gates in the UI. The sections below describe the earlier
claim-processing implementation kept for comparison; they do not establish
settlement capabilities.

### Earlier claim-processing app (historical reference)

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

### What you can do in the settlement UI (current)

1. **Tạo hồ sơ** B3/B7, upload sources, reload, open the stored original.
2. **Chạy kiểm tra** B3/B7 và xem report có căn cứ (unknown hiển thị "—", không
   phải 0); trả lời câu hỏi đúng owner với nguồn, re-check mới resolve.
3. **Hành động nghiệp vụ**: decision (người duyệt), review kế toán (không phải
   phê duyệt), sự kiện tiền thực tế với incidents, Stop/resume, handoff, closure.
4. **Verify panel** chạy bộ đánh giá settlement 20 packets qua cùng Service và
   hiển thị expected/actual/verdict/metrics trung thực.

### What you can do in the UI (earlier claim-processing app — historical)

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

## Verify (evaluation)

**Settlement (current):** the 20-packet development corpus
([index](docs/discovery/eval_development/CORPUS_INDEX.md)) runs sequentially
through the same settlement `Service` the UI uses; expected lives only in the
packet (hash-verified, never an input) and verdicts cover money, completion,
links and state — not just the net.

```bash
.venv/bin/python -m invoice_referee.verify.settlement_cli                 # cả 20 packets
.venv/bin/python -m invoice_referee.verify.settlement_cli --packets Q01,Q09
```

Artifacts (SuiteReport JSON: expected/actual/verdict/timestamp/mode +
source/config hash) are written under `data/settlement/verify/` (Git-ignored).
Exit code 0 means the measurement ran — a weak-but-truthful baseline is still a
successful measurement; dataset/gate errors exit 2. The UI also exposes this as
the **Verify** panel (`POST /api/verify/settlement/run`).

Measured baseline (B1, mode `FAKE_OR_REPLAY`, 2026-10-09): routine 9 / needs 11,
FN 0, FP 9 (khoảng bảo thủ 100%), U_routine 0, U_needs 1, first-pass routine
completion **0/9**. The fake reader cannot read the corpus' narrative sources,
so this number reflects reader capability, not settlement quality — live-mode
quality measurement (M1/M2) is not done. The corpus is DEVELOPMENT_ONLY from a
single template family: it is not an independent holdout.

**Earlier claim-processing Verify (legacy reference):**

```bash
.venv/bin/python -m invoice_referee.verify --suite core --mode replay --output data/verify
.venv/bin/python -m invoice_referee.verify --suite escalation --mode replay --output data/verify
.venv/bin/python -m invoice_referee.verify --suite all --mode replay --output data/verify
```

`core` = TC01/03/04/11; `escalation` = TC01/02/03/06/11; `all` = the 15-case
development corpus of the historical app. This legacy runner is kept for
comparison only and is not the accepted settlement evaluation.

## Policy

The demo policy (`config/demo-policy.json`, version `demo-expense-v0.1-proposed`)
holds PROPOSED rulebook values. It starts **inactive** (`active=false`,
`origin='proposed'`); a run may only use it after an explicit, versioned activation
(`activate_demo_policy`) that records a UUID activation id, a reason, and
`origin='developer_activated_demo'`. Demo role selection is not authenticated
company identity.

## Layout

```
src/invoice_referee/
  settlement/           current core: models, store, service, api, rules, pipeline
  settlement/persistence/  SQL lifecycle (sqlite_records, queries,
                        decision_records, money_records, action_records,
                        advance_records, linked_context_records)
  shared/               errors, artifacts, clock (used by current + legacy)
  legacy/               historical claim-processing app (application,
                        extraction, policy, storage/repository, domain, config,
                        api/app, verify runner). Compatibility shims keep old
                        import paths resolving.
  api/                  settlement factory (current) + legacy app shim
  verify/               settlement CLI (current) + legacy harness shims
frontend/src/
  settlement/           current settlement UI
  legacy/               historical claim-processing UI
  main.tsx              mounts the settlement App
tests/                  unit + integration; fixtures/ holds the Verify corpus
scripts/                synthetic-evidence / demo generators
docs/                   canonical docs, plans, evidence, build log
data/                   runtime SQLite + artifacts + frozen packets (Git-ignored)
```

### Settlement module map (current)

| Module | Responsibility |
| --- | --- |
| `store` | Public façade: owns connections/transactions, delegates SQL |
| `persistence/sqlite_records` | Common record helpers over an open connection |
| `persistence/queries` | Read projections, governing selector, money-context rebuild |
| `persistence/decision_records` | B8 presentation/decision writes |
| `persistence/money_records` | B9 money-event writes + revalidation |
| `persistence/action_records` | Handoff / closure / adjustment writes |
| `persistence/advance_records` | B3/B5 advance lifecycle |
| `persistence/linked_context_records` | B6→B7 child, declarations, company context |
| `advance_workflow` / `advance_reconciliation` | Pure B3/B5 computation |
| `settlement_workflow` / `settlement_reconciliation` | Pure B7/B8/B9 computation |
| `linked_context` | Pure linked-context building |
| `shared/clock` | Record-time clock (monkeypatch owner); business time stays in `*_workflow` |

## History / completed plans

Completed implementation plans are historical records of how the code got here,
not a second rulebook: [B3 intake](docs/superpowers/plans/2026-10-10-b3-verbal-intake.md),
[B3 present/approve](docs/superpowers/plans/2026-10-11-b3-present-and-approve.md),
[B5 advance receipts](docs/superpowers/plans/2026-10-11-b5-advance-receipts.md),
[B6 linked settlement](docs/superpowers/plans/2026-10-11-b6-linked-settlement.md),
[B8 settlement decision](docs/superpowers/plans/2026-10-11-b8-settlement-decision.md),
[B9 settlement fulfillment](docs/superpowers/plans/2026-10-11-b9-settlement-fulfillment.md).
Legacy commands and the earlier claim-processing app are preserved in
[the archive](docs/archive/README.md); do not start new work from them.

## Configuration safety

Never commit credentials, uploaded documents, OCR/model outputs, or local case
data. `.env` and `data/` are Git-ignored.

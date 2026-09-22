# InvoiceReferee

InvoiceReferee is a Sprint 1 prototype for receiving employee expense claims,
reading uploaded evidence, checking OCR quality, and comparing a primary bill
with supporting inventory or receipt evidence.

This README describes the code that runs in the current checkout. It does not
claim that every OrganizationAI Challenge A requirement has been implemented.

## Current workflow

```text
Employee claim + uploaded evidence
        ↓
Technical validation and SHA-256 deduplication
        ↓
Local case persistence
        ↓
Source gate: primary bill + business context
        ↓
Mistral OCR for image/PDF evidence
        ↓
Low-confidence block collection
        ↓
Optional Kimi confidence assessment per evidence
        ↓
No supporting evidence ──────────────→ PASS after OCR-quality review
        ↓ supporting evidence exists
Kimi cross-source fact extraction and conflict proposal
        ↓
Deterministic inventory-consistency checks
        ↓
PASS or NEEDS_HUMAN
```

`PASS` currently means that the implemented gates did not find a blocking issue.
It does not prove that every accounting-policy, duplicate, payment, authority, or
fraud check has run.

## Implemented

- Streamlit spaces for employee submission, accounting review, and OCR debug.
- Submission validation, upload limits, filename sanitization, SHA-256
  deduplication, and atomic local persistence.
- Mistral OCR adapter for JPG, JPEG, PNG, WEBP, and PDF evidence.
- OCR word-confidence mapping into a page/block/word hierarchy.
- Kimi structured-output adapter with one bounded JSON-repair attempt.
- Per-evidence confidence review for low-confidence blocks.
- Optional cross-source analysis when supporting evidence is attached.
- Deterministic inventory checks for source coverage, supplier/date differences,
  item mapping, quantity, unit, price, amount, receipt status, and semantic
  conflicts proposed by the model.
- Local processing results and basic JSONL audit events.
- Accounting queues split into `PASS` and `NEEDS_HUMAN`.

## Not implemented

The current checkout does not implement:

- the final Challenge A actions `AUTO_PROCESS`, `REQUEST_INFO`, and `ESCALATE`;
- a complete accounting-policy or deterministic decision guard;
- Challenge Verify suites or the documented one-action Verify experience;
- Stop and Override controls;
- append-only audit preservation after destructive case deletion;
- authentication, authorization, or tenant/session isolation;
- a verified public deployment;
- live-provider baseline evidence committed to the repository.

## Requirements

- Python 3.12 or newer
- Mistral API key to process uploaded image/PDF evidence
- Kimi-compatible endpoint credentials when confidence or conflict analysis is
  required

## Setup from a clean clone

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . pytest
cp .env.example .env
```

Configure `.env`:

```dotenv
MISTRAL_API_KEY=
KIMI_TOKEN=
KIMI_SECRET=
KIMI_BASE_URL=
KIMI_MODEL=moonshotai/Kimi-K3
OCR_WORD_REVIEW_THRESHOLD=0.85
```

Never commit `.env` or uploaded evidence.

## Run

```bash
.venv/bin/python -m streamlit run app/streamlit_app.py
```

Open `http://localhost:8501`.

The application writes local cases to `data/submissions/{case_id}`. All users of
one running instance share this store. The accounting and OCR-debug views can
read those cases, and the accounting view can permanently delete them. Use only
synthetic or explicitly approved data in a public demo.

## Test

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

The provider tests use fake clients; passing tests do not verify live Mistral,
live Kimi, deployment, or Challenge Verify. See [Testing](docs/TESTING.md).

## Documentation

- [Original challenge brief](docs/Challenge_Brief_OrganizationAI_VN.docx.md)
- [Current product behavior](docs/PRODUCT.md)
- [Current architecture](docs/ARCHITECTURE.md)
- [Testing and evidence](docs/TESTING.md)
- [Build log](docs/BUILD_LOG.md)

## Status vocabulary

Repository documentation uses four evidence labels:

- `IMPLEMENTED`: present in the current production path.
- `VERIFIED`: demonstrated by a fresh check.
- `INCONCLUSIVE`: not proven in the current environment.
- `PLANNED`: intentionally not implemented yet.

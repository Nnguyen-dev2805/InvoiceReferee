# InvoiceReferee — Testing and Evidence

## Evidence policy

Use these labels consistently:

- `IMPLEMENTED`: source exists in the current production path.
- `VERIFIED`: a fresh command or runtime check demonstrated the claim.
- `INCONCLUSIVE`: the current environment has not demonstrated the claim.
- `PLANNED`: the capability is intentionally not implemented yet.

A passing fake-provider test verifies adapter behavior against the fake. It does
not prove provider credentials, network access, model availability, response
quality, cost, latency, deployment, or behavior on unseen judge data.

## Environment

The project requires Python 3.12 or newer. From a clean clone:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . pytest
```

The repository does not currently declare a development dependency group;
`pytest` is therefore installed explicitly.

## Full local suite

```bash
.venv/bin/python -m pytest -q
```

Fresh result on 2026-09-22:

```text
60 passed in 0.93s
```

Status: `VERIFIED` for the current local suite at the reviewed commit.

## Dependency consistency

```bash
.venv/bin/python -m pip check
```

Fresh result on 2026-09-22:

```text
No broken requirements found.
```

Status: `VERIFIED` for the current virtual environment.

## What the tests cover

### Streamlit integration

`tests/integration/test_streamlit_app.py` uses Streamlit `AppTest` to cover:

- description-only submission through the UI;
- navigation to OCR debug for a stored case;
- splitting processed cases into accounting queues.

### Submission and storage

Unit tests cover:

- non-empty submission validation;
- file-extension and size limits;
- SHA-256 deduplication across evidence roles;
- metadata, evidence, and initial audit persistence;
- safe case path resolution;
- destructive case deletion.

### OCR transformation

Unit tests cover:

- Mistral request construction using a fake client;
- image base64 and PDF document payloads;
- word-confidence normalization;
- page/block/word mapping;
- exact, normalized, partial, and unmatched block mappings;
- bounding-box scaling and confidence colors.

### Kimi structured output

Unit tests use fake completions to cover:

- dedicated confidence and conflict prompts;
- extracting JSON from surrounding text;
- one bounded repair attempt;
- schema-specific repair context;
- fail-closed behavior after invalid responses.

### Processing orchestration

Tests use `FakeOcrAdapter` and `FakeQualityAdapter` to cover:

- source-gate failures before provider calls;
- primary-only `PASS` after OCR-quality review;
- blocking and non-blocking low-confidence candidates;
- incomplete candidate coverage;
- per-evidence confidence calls;
- stopping before conflict analysis when one evidence is unclear;
- one cross-source call after clear quality gates;
- one repair call for incomplete document coverage;
- final `PASS/NEEDS_HUMAN` mapping.

### Deterministic inventory policy

Tests cover happy and conflicting bill/report examples, missing document facts,
source coverage, employee-text exclusion, item mapping, quantity/amount
differences, receipt status, and semantic conflicts tied to evidence.

## What is not verified

The following remain `INCONCLUSIVE`:

- a live Mistral OCR request using current credentials;
- a live Kimi confidence or conflict request;
- behavior, latency, and cost on representative real documents;
- Streamlit behavior under concurrent users;
- privacy isolation on a public deployment;
- a public no-login URL;
- a clean-clone run on a second machine;
- judge-supplied unseen input.

The following are `PLANNED` and have no runnable test target in the current
checkout:

- Challenge core Verify;
- Challenge A five-case Verify;
- `AUTO_PROCESS/REQUEST_INFO/ESCALATE` decision tests;
- deterministic duplicate, payment, authority, and full policy suites;
- Stop and Override tests;
- append-only audit reconstruction tests.

Running this command currently fails because the package does not exist:

```bash
.venv/bin/python -m verify.harness --suite all
```

Expected current error:

```text
ModuleNotFoundError: No module named 'verify'
```

Do not list Verify as implemented until a production-path harness and its cases
exist again in the current checkout.

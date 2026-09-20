# InvoiceReferee — Runbook

> Status: **pre-code draft**. Commands below define the intended reproducible workflow and must be re-validated after implementation.

## 1. Requirements

- Python 3.12+
- Git

## 2. Clone

```bash
git clone <public-repository-url>
cd InvoiceReferee
```

The public repository URL will be inserted once the repo is published.

## 3. Create environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 4. Install project

Target command after `pyproject.toml` is implemented:

```bash
pip install -e '.[dev]'
```

## 5. Run tests

```bash
pytest -v
```

Expected final state before submission: zero failing tests.

## 6. Run Core Verify

Target command:

```bash
python -m verify.harness --suite core
```

Cases:

```text
TC01 → AUTO_PROCESS
TC07 → REQUEST_INFO
TC13 → ESCALATE
TC14 → ESCALATE
```

## 7. Run Challenge A Verify

Target command:

```bash
python -m verify.harness --suite escalation
```

Expected structure:

```text
EV01 → AUTO_PROCESS
EV02 → AUTO_PROCESS
EV03 → AUTO_PROCESS
EV04 → REQUEST_INFO
EV05 → ESCALATE
```

## 8. Run UI

Target command:

```bash
streamlit run app/streamlit_app.py
```

The homepage must tell the judge what to try first and must not require login.

## 9. Manual smoke test

Before every demo/deploy:

1. Open app in a fresh browser session.
2. Run a routine case and confirm `AUTO_PROCESS`.
3. Run TC09 and confirm `REQUEST_INFO` with a specific question.
4. Run TC13 and confirm `ESCALATE` to Finance Manager.
5. Open audit history and inspect evidence/reason/timestamp.
6. Stop one transaction and confirm its Agent decision remains unchanged; then override a decision and confirm both old/new decisions remain visible.
7. Run both Verify suites.

## 10. Unseen-input smoke test

Create at least two temporary transactions not stored under `tests/fixtures/`:

- one routine transaction with new values;
- one abnormal or beyond-authority transaction.

Paste or upload both JSON inputs through the Streamlit unseen-input path and confirm they run through the same production `review()` service without code changes.

## 11. Submission reproducibility checklist

- [ ] Public URL works without account.
- [ ] Clean clone can install.
- [ ] `pytest -v` passes.
- [ ] Core Verify runs with one command/button.
- [ ] Escalation Verify runs with one command/button.
- [ ] 17 fixtures remain independent of production expected outputs.
- [ ] Audit log is visible.
- [ ] Stop/Override works.
- [ ] README points to this runbook.


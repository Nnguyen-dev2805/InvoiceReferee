# Evidence — Live provider config fix (pre-T15)

Mode: unit + composition smoke (no live call, no spend). Proves the wiring, not
live OCR/Kimi quality.

## Problem found

Live mode could not run with a real key:
1. The runtime never loaded `.env` — only `os.environ`, so a `.env` file was ignored.
2. `_build_providers('live')` called `LiveProviders()` with no credentials, so the
   provider always received `None` keys → every call raised `CONFIG_NOT_ACTIVE`.
3. `.env` used `KIMI_TOKEN` + `KIMI_SECRET` (B0's form) while the code read only
   `KIMI_API_KEY`.

## Fix

- `src/invoice_referee/env.py` (new): a stdlib `.env` loader. Existing environment
  variables win (`setdefault`); comments/blank lines/quotes/inline comments handled;
  missing file is a no-op.
- `src/invoice_referee/extraction/providers.py`: `LiveProviders` now reads
  `MISTRAL_API_KEY` and Kimi credentials from the environment — `KIMI_API_KEY`
  (Bearer) or the B0 `KIMI_TOKEN` + `KIMI_SECRET` pair combined as `token.secret`.
  An explicit argument (including `None`) still wins over the environment.
- `src/invoice_referee/api/app.py`: `create_runtime_app()` loads the repo `.env`
  before building the provider stack.
- `.env.example`: documents `PROVIDER_MODE`, both Kimi credential forms, and that
  exported vars override the file.
- `tests/conftest.py` (new): an autouse fixture clears provider/config env vars so
  a developer's real `.env` never leaks into tests.

## Verification

- `pytest tests/unit/test_env_and_live_config.py` → 9 passed.
- Full backend: `PROVIDER_MODE=fake pytest tests/ -q` → 382 passed; `pip check` clean.
- Composition smoke: `PROVIDER_MODE=live create_runtime_app()` → `LiveProviders` with
  both keys set, correct Kimi base/model from `.env`; an exported `MISTRAL_API_KEY`
  overrides the file; with no keys, `_require_ocr_client`/`_require_chat_client`
  raise `CONFIG_NOT_ACTIVE` (fail-closed).
- Frontend: 5 passed.

## Limits

- No live provider call was made (needs explicit spend authorization, T15). This
  proves the config path, not live OCR/Kimi quality.
- The `.env` value format must match the endpoint (Bearer for Mistral; `token.secret`
  or a single key for Kimi). A gateway requiring a different auth scheme needs its
  own adapter change.

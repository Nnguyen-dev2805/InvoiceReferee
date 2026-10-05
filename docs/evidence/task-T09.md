# Evidence — T09 (FastAPI composition and contract responses)

Mode: integration / synthetic-fake (real `CaseService` + SQLite repository +
`FakeProviders`, driven through `TestClient`). This proves API WIRING, DTO
mapping and error-envelope mapping over the REAL service path. It does NOT prove
live OCR/Kimi quality, deployment, or real-user acceptance. The T08 `runtime`
fixture is reused; providers are NOT re-declared.

## Commands and results

- RED (before implementation):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_api.py -q`
  → `ModuleNotFoundError: No module named 'invoice_referee.api'` (feature missing).
- GREEN (T09 focus):
  `rtk proxy .venv/bin/python -m pytest tests/integration/test_api.py -q`
  → 23 passed.
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 365 passed
  (re-run 3× → 365 each time, no flakiness).
- Composition root (real factory):
  `PROVIDER_MODE=fake DATA_ROOT=<tmp> python -c "create_runtime_app()"` → builds;
  `/api/health` → `{status: ok, ready: false, provider_mode: fake}`;
  `/api/policy` → `active: false` (runtime starts INACTIVE).
  `PROVIDER_MODE=live` → `LiveProviders` built (no network at startup).

## OpenAPI schema hash (for T10 types)

`sha256` over canonical (sorted-key, compact) `/openapi.json` JSON:
`c8afd555a18304f20696c3670a6b30aa6689abf0637746fb2b817bef6617dd7a`

Paths (12): `/api/cases`, `/api/cases/{case_id}`, `/api/cases/{case_id}/runs`,
`/api/runs/{run_id}`, `/api/cases/{case_id}/actions`, `/api/runs/{run_id}/stop`,
`/api/cases/{case_id}/history`, `/api/cases/{case_id}/payment-request`,
`/api/cases/{case_id}/evidence/{evidence_id}`, `/api/policy`,
`/api/policy/activate`, `/api/health`. (No Verify routes — T11.)

## Contract coverage

- Business vs execution status: an accepted run (`202`) is polled by `GET
  /api/runs/{id}`; a provider failure AFTER acceptance is a `RunRecord`
  `FAILED` with `technical_code`, never a 5xx on the accepted request.
- Error envelope `{code, message}`: `NOT_FOUND`→404, `RUN_BUSY`→409,
  `INVALID_INPUT`/`INVALID_ACTION`→422 (mapping in `HTTP_CODES`).
- Intake: multipart `claim_json` + `files` + `roles` JSON list; strict `Claim`
  (unknown field → 422); empty form → 422; roles must match files one-to-one;
  upload count > 12 → 422; `stored_path` is NEVER accepted or returned.
- Actions: non-file JSON → `service.act`; `STOP` kind rejected (dedicated route);
  `ADD_EVIDENCE` multipart `action_json`+`files` → `service.add_evidence`
  (case_version bump + new evidence + reevaluation started).
- Evidence route checks case ownership (`404` for a foreign id) and omits
  `stored_path`.
- Stop returns the real `StopReply` (`STOP_REQUESTED` then `ALREADY_COMPLETED`).
- Policy activation: `POLICY_OWNER` + non-blank reason only; `activate_demo_policy`
  then `service.set_policy`; persisted active config + global `POLICY_CHANGE`
  event; `origin=developer_activated_demo`; `GET /policy` shows
  version/limits/threshold/origin.
- Health: liveness (`status`/`live`) + readiness (`ready`) + `provider_mode`;
  no secrets/credentials echoed.
- Composition root: `PROVIDER_MODE` explicit fake/live; missing/invalid →
  `RuntimeError` at startup (no live→fake fallback).

## Notes / limits

- `CaseService.repo` (read-only property) was added so projection routes
  (`cases`/`history`/`payment-request`) read through a documented accessor rather
  than a private attribute; mutations still go through the service methods.
- Run artifacts in responses are reduced to basenames (no absolute local paths).

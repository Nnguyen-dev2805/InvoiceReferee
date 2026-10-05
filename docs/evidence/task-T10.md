# Evidence — T10 (React product surfaces, human forms, controls)

Mode: component tests (Vitest + Testing Library) + production build + API
integration. Does NOT prove a real browser session, live provider quality, or
deployment (T15).

## Commands and results

- RED (before components existed): `npm --prefix frontend run test -- --run`
  → `Failed to resolve import "./HumanActions"` (component missing — the expected
  RED, not a setup failure).
- GREEN: `npm --prefix frontend run test -- --run` → 2 files, 5 tests passed
  (`CaseDetail` 3, `HumanActions` 2).
- Build/typecheck: `npm --prefix frontend run build` → `tsc --noEmit` clean +
  `vite build` success (`dist/` emitted).
- API integration: `rtk proxy .venv/bin/python -m pytest tests/integration/test_api.py -q`
  → 27 passed (frontend consumes the same contract; no backend change).

## What was built

- `frontend/` React 18 + TypeScript + Vite workspace (package-lock committed).
- `types.ts` mirrors the real FastAPI DTOs (`_case_dto`, `_run_dto`,
  `_result_dto`, `_evidence_dto`, `_payment_dto`, `_event_dto`, `_policy_dto`,
  `_stop_dto`) and the ledger enum values — checked against `create_runtime_app()`
  OpenAPI + `model_fields`, not invented.
- `api.ts` exports the brief's functions (`createCase`, `getCase`, `startRun`,
  `getRun`, `sendAction`, `stopRun`) plus `listCases`, `addEvidence`, `getHistory`,
  `getPaymentRequest`, `getPolicy`, `activatePolicy`; `ApiError{code,message,status}`.
- `CaseForm` (submit → create → run → poll), `CaseDetail` (decision/issues/
  evidence, Stop with pending→STOPPED, request-vs-transfer distinction),
  `HumanActions` (owner-scoped kinds, required reason, amount as text→integer),
  `VerifyPanel` (shell only — no simulated PASS).
- `App` polls every 1000ms only while the run is in flight and clears the timer
  on unmount/terminal state.
- `styles.css`: Flat Design tokens (teal/orange), semantic colors, visible focus,
  ≥44px targets, reduced-motion, responsive grid (375/768/1024/1440).

## Limits

- Component tests, not a browser session. Manual browser paths (routine 1.2m;
  numeric-uncertain→reviewer; 2m+1→approval; 5m+1→exception then approval;
  delayed-provider Stop; Override timeline) are owed to T15 with a running stack.
- VerifyPanel is a shell; T11 wires the runner.

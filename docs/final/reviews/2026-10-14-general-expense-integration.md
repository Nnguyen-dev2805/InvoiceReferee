# General employee-expense integration — implementation and evidence

14/10/2026. Implementer report. Branch `final`, base HEAD `3d68f6f7`. No commit or
push (no Git authorization); no database reset; no subagent. The other agent's
invoice/advance + frontend work was already committed at `3d68f6f7`; the working
tree was clean, so this integrator owned the shared files from there.

Every change was driven by a RED test observed first, then implementation, then the
full suite. Live provider runs are labelled LIVE; authoring is not E2E.

## Write set, consumers, completion

| Task | Files | Consumers | Gate |
| --- | --- | --- | --- |
| T1 profile/paper | `domain/organization.py`, `workflow/{service,context_records,evidence_jobs,db}.py`, `workflow/schema.sql`, `evidence/{document_profiles,document_validity,pipeline}.py`, `api/views.py` | admission, catalog, UI | general paper needs no trip; travel still does |
| T2 binding | `domain/organization.py` (`company_name`), `reconciliation/admission.py` | employee-paid basis | company-buyer-only invoice binds via composite |
| T3 category | `domain/{finance,policy,case}.py`, `reconciliation/{category,service}.py`, `workflow/context_records.py`, `reconciliation/admission.py` | policy engine | 5m/2m caps, 30-day window, personal exclusion |
| T4 allocation | `reconciliation/admission.py` | admission | row amount bounded by source; extra source relevance FACT |
| T5 FACT→POLICY | `reconciliation/{admission,service}.py` | policy engine | missing-evidence FACT cleared by scoped EXCEPT_POLICY |
| T6 integrity | `scripts/build_hoangha_general_inventory.py`, `tests/integration/test_hoangha_general_packets.py` | Verify | 25 cases / 65 PDFs verified |
| T7 evidence | `frontend/src/types.ts`, `.runtime/general-expense/*` | UI/LIVE | catalog profile exposed; LIVE TC01 |

## T1–T5 RED → GREEN

All commands: `rtk proxy uv run --no-sync pytest <path> -p no:cacheprovider`.

| Task | Test file | RED observed | GREEN |
| --- | --- | --- | --- |
| T1 | `tests/unit/test_general_paper_profile.py`, `tests/integration/test_activity_profile_scope.py` | `required_fields_for` missing | 4 + 4 passed |
| T2 | `tests/unit/test_general_source_binding.py`, `tests/integration/test_tc01_original_sources.py` | `company_name` extra-forbidden | 5 + 4 passed |
| T3 | `tests/unit/test_expense_category_policy.py`, `tests/integration/test_general_financial_authority.py` | `reconciliation.category` missing | 9 + 3 passed |
| T4 | `tests/integration/test_general_evidence_allocation.py` | over-allocation not flagged | 3 passed |
| T5 | `tests/integration/test_tc20_fact_policy_exception.py` | uncovered row silently dropped | 3 passed |
| T6 | `tests/integration/test_hoangha_general_packets.py` | — | 5 passed |

Backend suite: **516 passed**. Frontend: `npm test` → 19 passed / 2 skipped;
`npm run build` → exit 0 (pinned Node 24.19.0).

## LIVE evidence

- **LIVE TC01 original sources** (`.runtime/general-expense/tc01_live.py`, real
  Mistral OCR + X-Kiro, SIMULATED context, clock 2026-10-10T18:00+07, profile
  `WORK_EXPENSE`, the ORIGINAL unchanged `report_hoan_ung.pdf` + `hoa_don_dien_tu.pdf`):
  → **READY_TO_EXECUTE, COLLECT 760000**, T=E=3240000, A=4000000, S=-760000, basis
  `EMPLOYEE_PAID_INVOICE`. The invoice names only the company buyer; composite
  binding admitted it. Result: `.runtime/general-expense/tc01-result.json`.
- **LIVE profile proof**: the general prototype paper
  (`data/test-kit/uc03-expansion/mau-giay-quyet-toan-chi-phi-chung.pdf`) reads
  **CLEAR under `WORK_EXPENSE`** and **NEEDS_HUMAN** (missing `trip_destination`,
  `trip_start`, `trip_end`) under `TRAVEL` — the same bytes, real provider.
- **LIVE-discovered fix**: the model read the invoice number as `IR26E00000101`
  (serial prefix) while the paper referenced `00000101`; the row↔invoice link now
  tolerates the serial prefix (`_refs_match`), with a regression test.

## Corpus

25 original TC folders / 65 PDFs under `data/tham-khao/uc-03` are byte-identical
(all SHA256 verified). `final-case-mapping-v3.json` is authoring-only and is not
read at runtime. The F01–F03 pilot corpus and generator are unchanged.

## NOT_RUN / remaining

- **T6 full per-case context/gold**: the 25-case inventory integrity is verified,
  but independent per-case organization/context/gold and the executable 25-packet
  corpus are NOT_RUN (large authoring effort). No 25-case score is claimed.
- **T7 browser**: NOT_RUN — the concurrent agent's frontend now opens on a
  dashboard; a scripted WORK_EXPENSE create/submit landed on the dashboard rather
  than the intake form. The catalog profile is exposed and typed (`profile` on
  `CatalogActivity`); LIVE backend evidence stands in for the flow.
- **Verify Core4/Escalation5**: NOT_RUN — the evaluation dataset `data/kiem-thu` is
  absent (pre-existing gap), so `/api/verify` returns 0 packets (release=True on an
  empty set is not a pass).
- **M0 LIVE / RECORDED_REPLAY captures / Docker / public hosting / practitioner
  pilot**: NOT_RUN (unchanged).
- Not all 25 cases are AUTO: routine (TC01/02/03/12/17/23), FACT (05–11,15,18,19,
  22,24,25), POLICY/AUTHORITY (04,13,14,16,20,21) by design. Only TC01 is run LIVE
  here; the rest are NOT_RUN.

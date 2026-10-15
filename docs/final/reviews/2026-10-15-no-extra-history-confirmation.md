# Receipt confirmation only — no separate history action

User correction: ordinary TC01 requires only accountant advance confirmation,
employee return-proof upload, then accountant receipt confirmation. The previous
initial-history checkbox was unwanted. This supersedes the ordinary UI behavior
in `2026-10-15-managed-money-history.md`; its recorded test results stay historical.

## Change

- Removed the initial-history section, checkbox, button, state and frontend API
  call. The history component is a read-only list plus pending-return review;
  no return-accept button exists before an employee proof draft is submitted.
- A clear completed source-bound advance confirmation records A and enables
  `DOSSIER_RECORDS` reconciliation in the same command. Re-confirming a saved
  receipt can initialize this tracking for an existing root without doubling A.
- This source means the dossier's recorded money, NOT complete external bank
  history or a second accountant declaration. Opening balance remains null;
  actor/time/source refs come from the actual receipt confirmation. Pending,
  unknown, conflicting or unallocated money cannot initialize tracking.
- Instruction-bound P/R continue existing verification and update tracking.
  An imported confirmed advance can enter dossier tracking on actual P/R receipt
  without another history action. Legacy APIs remain for compatibility, never
  called or requested by the ordinary UI.
- No changes to money formulas, authority, payer policy, budget B or identities.
  No migration, new dependency, data reset, commit/push or subagent.

## Evidence

RED: source-bound advance API still returned null coverage, UI still rendered
checkbox. GREEN after implementing command-bound tracking and removing the UI.
Additional RED→GREEN: full/partial return against an imported advance stayed
unknown due legacy coverage after receipt; now starts dossier tracking correctly.

- Full Python: **765 passed**, `.runtime/no-extra-history-pytest.log` / XML.
- Frontend: **43 passed / 2 skipped**, 11 files; existing React act warnings.
- Node24 build and `git diff --check`: exit0.
- Isolated browser→API→DB, `.runtime/no-extra-history-20261015/`:
  zero initial money → refresh stored advance read → one accountant confirmation
  gives A4000000 / E3240000 / COLLECT760000 directly. No initial-history checkbox
  or command. Employee proof upload leaves R0; accountant receipt gives R760000,
  S0, SETTLED. Reload retains state; one A and one R, no duplicate.
- Originals use stored real LIVE OCR; new return uses a valid synthetic PDF and
  deterministic OCR/LLM adapters. **Fresh LIVE NOT_RUN**, not a provider-quality
  acceptance result. LIVE E2E callers were updated but not freshly executed.
- Backend8000 restarted with its same command; health LIVE/ready. Ten business
  table fingerprints unchanged (`user-db-unchanged.json`). No financial command
  was sent to the user DB. Private test server stopped after verification.

Discovery: CodeGraph current source + scoped fallback; generation/coverage tools
not exposed, index coverage UNKNOWN. Bounded self-review, no independent reviewer.

Operational limit: unsubmitted external movements are not independently known;
figures represent the admitted dossier records. Concrete missing/contradictory
money stays unresolved. The system does not certify complete bank history.

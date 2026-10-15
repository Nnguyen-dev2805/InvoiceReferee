# Portable TC01 demo context

User requested Nguyễn Minh An / Công ty An Thịnh and explicitly selected a
SIMULATED confirmed advance of 4m. Changed the existing legacy fixture's two
names, added `data/demo/tc01-company-context.json` and a runbook. No original
TC01 PDF, application DB, API key, running backend or Git history was changed.

## Implementation

- Runtime selects the existing typed importer when JSON has `organization_id`;
  validates with `OrganizationContext.model_validate_json` so strict tuple DTOs
  accept JSON arrays, and keeps the legacy importer for the old schema.
- Legacy snapshot now preserves the configured organization name.
- `scripts/dev.py --demo-as-of` accepts an explicit timezone-aware instant and
  uses the existing composition-root clock seam. Without it, real time remains
  the default. Startup prints a fixed-demo-clock diagnostic; traces use wall time.
- TC01 fixture uses WORK_EXPENSE, the unchanged source identity, B=8m, scoped
  recognize/issue grants 8m/4m and approver/accountant grants bounded at 20m,
  category caps 5m meal/2m taxi and a 30-day window. Advance is confirmed 4m;
  coverage through 14/10/2026 23:00 +07 lists all flow kinds and a witnessed zero
  opening balance. It contains no expected E/S or forced outcome.
- Default startup still uses the legacy fixture. The documented command selects
  TC01 explicitly, a fixed assessment clock and a separate DB/uploads on port
  8012; it never overwrites the user's default database.

## Verification

- RED: new regression file initially gave 3 failed / 1 passed: typed JSON rejected,
  legacy company identity lost, and demo-clock flag absent.
- GREEN: `rtk proxy uv run --no-sync pytest tests/integration/test_tc01_demo_context.py
  tests/integration/test_dev_entry.py tests/integration/test_context_import_unification.py
  tests/integration/test_live_wiring.py -q -p no:cacheprovider` — exit 0, 21 tests.
- Full `rtk proxy uv run --no-sync pytest -q -p no:cacheprovider` — exit 0, no failures.
- `rtk proxy uv run --no-sync python scripts/dev.py --help` — exit 0, option visible.
- `rtk proxy git diff --check` — exit 0.
- Isolated real importer + admission/Reconciler with the user's stored LIVE TC01
  ReadResult: T=E=3.24m, A=4m, P=R=0, S=−760k; effect COLLECT 760k, no issues.
  Proof: `.runtime/tc01-context-check-20261014/result.json`. This reused an actual
  stored OCR report; it is not a fresh provider or browser test.
- Original PDFs have no strong advance reference. The actual linker returns
  NEEDS_CONFIRMATION with exactly one candidate; user confirms TC01 or starts
  from an already-bound dossier. No weak name/amount auto-link was introduced.

Fresh LIVE/browser test NOT_RUN. Existing WAITING dossiers are not automatically
rebound or reassessed by editing fixtures. Unrelated `document_viewer.tsx` work is
preserved. No commit/push. Source base final `38d8da3a`; changes are uncommitted.

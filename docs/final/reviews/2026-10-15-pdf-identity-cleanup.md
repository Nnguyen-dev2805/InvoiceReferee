# PDF identity cleanup and TC01 advance variants

User authorized generator changes and removing old PDFs bearing Nguyễn An.
Scope: generated pilot/demo artifacts only; original Hoangha PDFs unchanged.
No application DB, running backend, API credentials, business amounts, grants or
financial rules were changed. Unrelated document-viewer edits were preserved.

## Changes

- Scanned 355 PDFs under data with pypdf text extraction; 9 contained Nguyễn An:
  8 managed pilot PDFs and one obsolete expansion prototype. Replaced the 8 in
  place with Nguyễn Minh An / Công ty An Thịnh and deleted the obsolete prototype.
  After generation, 356 data PDFs have zero old-name matches in their text layer.
  This inventory is not an OCR audit of textless images.
- Shared generator now accepts company/person/purpose/signer/reference parameters
  for the two advance forms. Header layout is flat and wraps the full company name.
- Added `--tc01-output`: generates two TC01 reception advance PDFs, paired transfer
  and cash contexts, managed marker and hash manifest. Each context has ONE 4m
  advance, with matching source transaction/scope/payer. Fixed dates and the 4m
  amount describe this fixture; this is not a generic bank-document generator.
- TC01 source names and purposes come from its validated context; no hidden gold
  is read. Transfer FT-TC01-0001, cash PC-TC01-0001, work reference TU-TC01.
- Aligned the TC01 default context's transaction/payer with the transfer variant.
  Added F01 cash-context alternative. All monetary values and independent business
  gold hashes remain unchanged. Evidence gold names and provenance were updated
  outside the input generator; input manifests/confirmation refs were regenerated.

## Verification

- PDF authoring marker executed once, edit/10 outputs. Generation used managed
  temporary directories before repository outputs.
- Generator RED: new identity and TC01 CLI tests failed against the old generator;
  GREEN: all five generator tests pass, including deterministic regeneration and
  no gold/symlink overwrite.
- Full suite exposed eight fixture-drift failures (old claimant names and old
  transaction identity). Updated only the pilot-consuming test inputs/reference;
  retained all financial assertions. Related 32 tests pass.
- Final full `rtk proxy uv run --no-sync pytest -q -p no:cacheprovider`: exit 0,
  no failures. `git diff --check`: exit 0.
- Ten output PDFs: one page each; Vietnamese text present; no characters outside
  page bounds (bundled pdfplumber). Rendered and visually reviewed. Kept three
  cash signature columns, no new legal/bank-validation claim or visible warning.
- New manifests match file hashes; original Hoangha hashes checked against pilot
  provenance and unchanged. Business gold SHA values unchanged.

Evidence under `.runtime/pdf-identity-cleanup-20261015/`: before/after inventory,
layout checks, business-gold hashes and page renders. Fresh provider OCR, browser
LIVE and recorded-replay validation are NOT_RUN for these new PDF bytes. Old LIVE
captures/results are not evidence of the updated PDF extraction quality.

Generator command and correct branch/context usage are documented in
`data/demo/README.md` and `data/test-kit/uc03-pilot/README.md`. No commit/push.

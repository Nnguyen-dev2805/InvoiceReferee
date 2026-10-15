# Multiline payer name and Vietnamese payee display — isolated LIVE verification

**Result:** PASS after the extraction/provenance and UI readability changes. The
run used an isolated LIVE database and the existing synthetic TC01 source files.
The user's default database at `.runtime/invoice-referee.sqlite` was not used or
modified for this verification.

## Tested revision and inputs

- Branch `final`, base `38d8da3a8b50d7b117a313a2498916302071e55b`; working tree
  remained dirty with this and earlier authorized work.
- Provider mode `LIVE`; Playwright completed in 2.0m with no console errors.
- Case `case:bf0130482a8814612f79`; activity
  `activity:proposed:7dfa1bc3b5dc4d049b8e7463c6019557`.
- Context digest:
  `707c9b27be320c266129084354f638020cf31ab304addf61b85934ba67022d1d`.
- Source SHA-256 values were unchanged from the preceding TC01 run:
  - `report_hoan_ung.pdf`: `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c`
  - `hoa_don_dien_tu.pdf`: `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019`
  - `03-bien-nhan-chuyen-khoan.pdf`: `f8dd97896dd8acaf6f34c75186756672ff41ec9beb5490b56fe71bcf3601c709`

## Results

- Extraction returned `payer_name=FOUND` as
  `CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH`. Its `exact_quote` retained the
  original newline between `CÔNG NGHỆ` and `AN THỊNH`. The accountant made no
  payer correction in this run.
- Extraction returned `payee_name=FOUND` as `NGUYỄN MINH AN`, with the exact
  accented quote from the source.
- Browser assertions confirmed the payee input value is exactly that Unicode
  string and the payer/payee inputs use the enlarged `text-sm` presentation.
- The full TC01 browser workflow remained green: the case reached
  `READY_TO_EXECUTE` with `COLLECT 760.000` issued and `execution_state=NOT_STARTED`.
  This remains conditional on the accountant's coverage assertion; it did not
  execute collection or independently verify a bank account.

The line-wrap regression has both a positive case (complete company name, exact
multiline quote, accepted with the quote preserved) and negative cases (truncated
quote or a wrong company name remain `UNREADABLE`). Whitespace normalization does
not remove accents or tolerate spelling differences.

## Commands and artifacts

- `rtk proxy uv run pytest -q` — exit 0.
- `rtk proxy env PATH="<pinned-node-24>:$PATH" npm --prefix frontend test -- --run`
  — 34 passed, 2 skipped.
- `rtk proxy env PATH="<pinned-node-24>:$PATH" npm --prefix frontend run build`
  — exit 0.
- Isolated LIVE Playwright — 1 passed in 2.0m.
- DB, uploaded sources, provider artifacts, evidence JSON and Playwright trace/video
  are under `.runtime/multiline-name-live-20261015/` (Git-ignored).

No credential was changed. No commit, push, reset, user-DB mutation, or provider
call against the user's default web DB was made.

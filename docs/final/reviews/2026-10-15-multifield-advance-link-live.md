# TC01 multi-field advance link — isolated LIVE evidence — 15/10/2026

## Result

**PASS for voucher-to-settlement linking and accountant confirmation of the
received advance.** This is not a PASS for the full financial settlement: the
new proposed activity remains `WAITING`, has no coverage record and has no
financial instruction.

The LIVE browser run uploaded only the two source settlement PDFs in
`data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua/`, then the
accountant separately uploaded `data/demo/tc01-chung-tu-ung/03-bien-nhan-chuyen-khoan.pdf`.
The server returned `LIVE` and `live_ready=true`. No result, gold file or
reference mapping was passed to the OCR/model runtime.

The first settlement read returned `NOT_FOUND`; the submitted case received a
server-proposed activity ID. The accountant's voucher read then returned
`LINKED` / `MULTI_FIELD_MATCH`, matching that proposed activity. Its
`TU-TC01` reference was `UNMAPPED`, so the run did not rely on a pre-seeded
activity reference. The link signals were:

| Field | Result | Evidence used |
| --- | --- | --- |
| Employee | MATCHED | Voucher payee and settlement declarant `NGUYỄN MINH AN` |
| Company | MATCHED | Voucher payer quote spans two OCR lines; normalized value matches configured company |
| Purpose | MATCHED | Specific project wording on voucher and settlement report |
| Advance amount | MATCHED | Voucher 4,000,000 VND equals declared advance 4,000,000 VND; expense total 3,240,000 VND was not used |
| Time | MATCHED | Transfer 05/10/2026 precedes settlement document 10/10/2026; no work date was inferred |
| Transaction | MATCHED | `FT-TC01-0001` not previously owned by another root |
| Candidate set | MATCHED | One compatible root in the tenant |
| Voucher reference | UNMAPPED | `TU-TC01`; evaluation continued through the other facts |

The accountant UI displayed **“Đã tự liên kết với hồ sơ này”**, did not render the
link checkbox or reason input, filled the payer/payee fields from the saved
source, and selected the transfer receipt in the document viewer. The separate
accountant money confirmation was still required.

There were no browser console errors. A few PDF preview GETs were canceled while
the UI switched tabs; the server log shows successful HTTP 200 source responses,
and the Playwright assertion confirmed the transfer receipt tab was selected.

After confirmation, isolated SQLite contains exactly one confirmed
`ADVANCE_RECEIVED` event of 4,000,000 VND and one `ActivityAcceptance` with
basis `MULTI_FIELD_MATCH`, 13 source refs and the persisted eight decision
signals. There is no coverage row or instruction. The activity is still
`PROPOSED`; admission remains `WAITING`.

## Isolation and provenance

- Branch/revision: `final` / `38d8da3a8b50d7b117a313a2498916302071e55b` (working changes uncommitted).
- Provider mode: LIVE; health reported `live_ready=true` and LangSmith enabled with zero export errors.
- Clock: real server clock, no `--demo-as-of` override; run started at `2026-10-15T04:46:16Z`. Dates used for matching came from the PDFs.
- Context SHA-256: `c0ff238a19438c1db2af1ef2317225e688b7774d21a88db2bd33e0dcc8f58674`.
- The isolated context snapshot has no activities/references, ledger, grants or coverage. It contains only the tenant/company identity and the accountant/employee identities. The proposed activity row was created by the workflow and has no seeded `TU-TC01` mapping.
- Runtime DB and uploads: `.runtime/tc01-multifield-live-20261015-1145/isolated.sqlite` and `.runtime/tc01-multifield-live-20261015-1145/uploads/`. The default DB and server were not read, restarted or modified. The isolated LIVE server on port 8014 was stopped after the run.
- Browser/API evidence: `.runtime/tc01-multifield-live-20261015-1145/evidence/playwright-evidence.json`; Playwright trace/video/screenshot artifacts are under `.runtime/tc01-multifield-live-20261015-1145/playwright/`.

Original input SHA-256 values:

| PDF | SHA-256 |
| --- | --- |
| `report_hoan_ung.pdf` | `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c` |
| `hoa_don_dien_tu.pdf` | `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019` |
| `03-bien-nhan-chuyen-khoan.pdf` | `f8dd97896dd8acaf6f34c75186756672ff41ec9beb5490b56fe71bcf3601c709` |

## Verification

- `rtk proxy uv run pytest -q` — PASS, exit 0.
- Targeted multi-field linking, extraction and advance-draft API tests — PASS.
- Concurrent upload regression — PASS; one transaction cannot auto-link to two roots.
- `npm --prefix frontend test -- --run` with Node 24.19.0/npm 11.12.1 — PASS, 36 passed / 2 skipped. Existing React `act(...)` warnings remain.
- `npm --prefix frontend run build` with Node 24.19.0/npm 11.12.1 — PASS.
- `npx playwright test --config playwright.tc01-multifield.config.ts` against the isolated LIVE server — PASS, 1 test; 1m30s.
- `rtk proxy git diff --check` — PASS.

No commit, push, reset or subagent was used.

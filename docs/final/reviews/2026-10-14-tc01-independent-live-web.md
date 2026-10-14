# TC01 original — independent LIVE and browser investigation

Date: 14/10/2026, Asia/Ho_Chi_Minh.
Verdict: **The financial path produces COLLECT 760,000 with the correct independent context. The current web intake does not reproduce that path and is not ready for acceptance.**

## Scope and execution identity

- Tested backend HEAD: `0b205420bfd3b4ce41e8739a1a701798a805bca1` on `final`.
- Original input directory: `data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua`.
- Original report SHA256: `6af4c063a3662ad568f30536c58213cb95fd7e48018892ab8f14df7a312d977c`.
- Original invoice SHA256: `d8dddd4e839e8fa89c059bee610b9a85457757d577e7ec9ce352c9ad158f3019`.
- Originals were rendered and inspected; neither was rewritten.
- Providers: LIVE Mistral OCR and configured X-Kiro model `qwen/qwen3.7-flash:free`.
- Organization, budget, grants and actual advance history: **SIMULATED**, not evidence of real company money. No gold/expected.json was read by the application or model.
- Assessment clock: explicitly controlled at `2026-10-10T18:00:00+07:00`, aligned with the supplied coverage fixture.
- Python 3.12.13; Node 24.19.0; npm 11.12.1. CodeGraph reported up-to-date, with an earlier-engine warning. Codebase Memory coverage tool was not exposed; coverage remains unknown. This is a task-directed investigation, not an exhaustive audit.
- Evidence directory: `.runtime/tc01-independent-20261014-151156/`. Separate `tc01.sqlite` and `web.sqlite`; user DB and application code were not edited/reset. No commit/push/subagent.
- Frontend was compiled once into the isolated `frontend-dist` in that directory. Another agent began changing App/document-viewer/dossier/questions afterward; browser screenshots describe this captured build, not an untested later build.

## Tests performed

1. Fresh original-source LIVE run through `CaseWorkflow`, its actual evidence worker and the normal Reconciler, with TC01 activity/claimant/company/history already linked.
2. Real socket HTTP server and Chromium/Playwright: upload both original PDFs, click **Đọc chứng từ**, inspect draft, change declared advance to 4,500,000 and enter a diagnostic note, click **Xác nhận và nộp hồ sơ**, await backend completion through the API.
3. Explicit browser fault injection: return HTTP500 only for `settlement/draft`; upload only the original report; inspect resulting UI without submitting the fabricated draft.
4. Re-assess the same real LIVE evidence against the same context at actual server time, without new provider calls, to distinguish obsolete coverage from financial arithmetic errors.

## Direct LIVE outcome and stages

| Stage | Observed result | Seconds |
|---|---|---:|
| OCR invoice | One page, readable | 3.308 |
| OCR report | One page, readable | 3.170 |
| Confidence review function | No low-confidence batch required; no confidence LLM call | ~0 |
| Classification | Two documents: E_INVOICE and SETTLEMENT_FORM | 7.384 |
| Invoice extraction | Total3,240,000; number00000101; company buyer; no buyer-person | 26.656 |
| Invoice validation | CLEAR | <0.001 |
| Report extraction | NGUYỄN MINH AN; client reception purpose; declared advance4m; total3.24m; proposed return760k | 20.321 |
| Report validation | CLEAR under WORK_EXPENSE; no invented trip | <0.001 |
| Matching | Original invoice linked to report row | 0.003 |
| End-to-end direct run | READY_TO_EXECUTE, no business issues, COLLECT760000 | 60.906 total |

Projection: T=E=3,240,000; A=4,000,000; P=R=0 from scoped history/coverage;
S=E-A-P+R=-760,000. Basis=`EMPLOYEE_PAID_INVOICE` via accepted composite binding,
not a bank-verified supplier payment. The fixture advance supplies A independently;
the printed report is not used as a company actual-money event.

This proves one raw TC01 financial scenario. No actual collection or full25-case acceptance is claimed.

## Browser outcome

The same documents were uploaded to the same independent TC01-compatible organization
context (only the tenant label remapped to the web demo tenant). The browser created
an unrelated PROPOSED activity instead of binding to `activity:tc01`.

Draft endpoint returned HTTP200 with:

- `declared_name`, `activity_name`, `occurred_at`, `declared_purpose`, `incurred_total`, `declared_advance`: null;
- `expenses=[]`;
- warning that advance could not be extracted;
- **both files**, including the report, in the `invoices` array with null invoice fields.

UI nevertheless showed **Đã trích xuất**, **Công tác Hà Nội**, date06/10/2026,
**Làm việc với khách hàng tại Hà Nội**, total0, no rows, and **Cân bằng**. The API's
warning was not displayed. The original report is client reception, dated10/10/2026,
with a clearly printed3.24m cost and4m declared advance.

After submit, the real OCR pipeline read the source total correctly, but API result was:

- state WAITING; T=3,240,000;
- E/A/P/R/S UNKNOWN; no instruction;
- FACT `budget:B`, FACT `ledger:coverage`, FACT `expense:payer`.

The captured UI remained at v3/**Đang xử lý** while the backend had completed at v4/WAITING.

## Findings and smallest coherent fixes

### P1-1 — Draft reading bypasses the accepted OCR pipeline and cannot parse TC01

Source: `workflow/service.py::read_settlement_draft`, lines1152–1278 at tested revision.
The method uses pypdf native text and regex; PNG/JPEG do not enter OCR here.
Its form detection looks for quyết toán/đề nghị thanh toán/bảng kê, not the original
GIẤY ĐỀ NGHỊ HOÀN ỨNG. The report then enters the invoice branch because its text
mentions hóa đơn. Invoice patterns do not match the original Số:/VND structure.

Fix: have draft preparation consume the normal persisted OCR/classification/
extraction report, with provenance and typed missing values. Reuse that unchanged
read on submit. Do not add another regex branch as the complete fix: that would
leave image/scanned-PDF support and the agreed all-input-OCR contract broken.

### P1-2 — Frontend turns extraction failure into invented successful evidence

Source: `frontend/src/features/intake.tsx::handleReadDocuments`, lines102–150.
With injected HTTP500, the UI fills a3.24m expense,4m advance, invoiceIR26101001
and a successful link to02-hoa-don-dich-vu.pdf—even though only report_hoan_ung.pdf
was uploaded. It still shows Đã trích xuất and enables submit.

Fix: delete production fallback demo facts; preserve files and show extraction
failure with retry. Null values must remain unknown, never default money0 or a
green matched/complete state. Demo data belongs only in explicit fixtures.

### P1-3 — Web always creates a new activity and loses the supplied financial context

Source: `handleReadDocuments`, lines86–94; `api/routes.py::create_case`;
`workflow/evidence_assessment.py::build_evidence_assessment_input` and scoped `load_context`.
The request creates a new activity named Hồ sơ quyết toán công tác with the current
browser timestamp before reading sources. It has a fresh proposed ID. TC01's budget,
history and company/claimant binding are scoped to activity:tc01, so they cannot be
used for that unrelated activity. The three FACT issues are appropriate for that
scope; routing the original claim there is the intake integration failure.

Fix: after draft extraction, propose an existing compatible activity and ask the
employee to select when ambiguous. Keep organization/activity identity server-owned.
Explicitly new activities should enter authorization/budget follow-up rather than
borrowing history or silently creating B/grants. The first upload may be an unbound
draft/batch; do not require fabricated activity details just to read files.

### P1-4 — Edits and notes on the review screen are discarded on submit

Source: `handleConfirmAndSubmit`, lines181–199; request in web-network.json.
The test changed declared advance to4.5m and entered a note. The POST contains only
activity_id, declared_purpose and employee_paid_claims=[]. `finalNotes` is computed
but unused. No case confirmation was stored. Edited activity name/date are also
absent from that submission contract.

Fix: persist typed employee corrections, draft revision and notes with original
OCR value/source refs and server actor. A correction is a declaration, not an
actual advance event. Reconciliation must consume the submitted declaration and
surface a mismatch against company history rather than dropping the edit.

### P1-5 — UI does not refresh after the asynchronous worker finishes

Source: App initial session/restore effect and Intake onCase callback at captured build.
The submit response is v3/PROCESSING, and one immediate refresh precedes worker
completion. No later refresh updates the displayed case. API polling by the test
sees v4/WAITING, while screenshot/text still show processing and unknown T.

Fix: bounded polling of the currently visible pending case, or an existing event
mechanism; stop on terminal/read-completed states and when navigating away. Keep
server versions authoritative. No need to introduce a new broker.

### P2 — Financial labels on the draft overstate what has been verified

The screen calls the editable figure Tiền tạm ứng đã nhận (A) and T-A a monetary
balance before company history, eligibility, prior P/R and policy have been checked.
With extraction returning null, it displays0/Cân bằng.

Fix: label this **Ứng nhân viên kê khai**, with **Chênh lệch kê khai dự kiến** only
when both declared amounts are known. Reserve A and final S for server projection
after reconciliation. The page also says missing rows can be added manually but
provides no corresponding row editor in the tested build.

## Clock/context boundary

Reusing the LIVE report at controlled10Oct gives no issue. At actual14Oct with
the exact same coverage ending10Oct, the result correctly blocks on FACT
ledger:coverage. To test at current time, supply a current responsible coverage
fixture or use a disclosed controlled harness clock; do not loosen history checks.

## Commands and evidence

- `rtk proxy uv run --no-sync python .runtime/tc01-independent-20261014-151156/run_direct.py`: exit0, LIVE COLLECT760000.
- Pinned node/npm version checks: Node24.19.0/npm11.12.1, exit0.
- `npm run build -- --outDir ../.runtime/tc01-independent-20261014-151156/frontend-dist`: exit0, isolated output.
- `node .runtime/tc01-independent-20261014-151156/browser.mjs`: exit0; browser runtime errors=[]; original workflow WAITING, not financial acceptance.
- Injected500 browser probe: exit0, incorrect successful draft reproduced; no submit.
- `tc01-report.json`, `tc01-result.json`, `stages.jsonl`: direct-source facts, decision, stage timings.
- `web-network.json`, `web-final-case.json`, `web-db.json`, `web-trace/stages.jsonl`: requests, worker output and scope/persistence proof.
- `web-draft.png/txt`, `web-after-submit.png/txt`, `web-failed-extraction.png/txt`: browser observations.
- `clock-comparison.json`: same evidence at controlled vs actual clock, no extra LIVE calls.

No application fix, full-suite test, full25-case run, real-world money movement,
new gold freeze or competition-completion claim was made. Concurrent agent edits
remain untouched. Next engineering work: remove fabricated draft data, route draft
through the actual OCR report, implement activity binding and persisted review
corrections, then refresh asynchronous results; rerun this exact raw browser case.

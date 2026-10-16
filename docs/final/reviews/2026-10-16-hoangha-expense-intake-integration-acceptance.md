# Hoangha expense intake + TC18 — S6 acceptance checkpoint (17/10/2026)

**Current verdict: S6 targeted/replay gates PASS; full backend suite FAIL (6 inherited failures). Full plan not unconditionally accepted.**

Latest evidence is §6 below. Earlier §3–5 are the S1–S5 historical checkpoint.

Tiếp tục main @ 8a9bbdc7. Không merge worktree, không viết lại pipeline,
0 OCR/LLM/LIVE call mới, không money-event từ draft/read, không commit/push.
Plan: `docs/superpowers/plans/2026-10-17-hoangha-expense-intake-tc18.md`.

## 1. Lấy từ Hoangha / giữ của main / không sao chép

- Lấy: bộ thay thế nhiều-tài-liệu-một-khoản (nghiệm thu + chuyển khoản cùng
  hỗ trợ nhân công), tách note / no_evidence_reason / requires_evidence,
  nhánh exception OUTSIDE_POLICY→kế toán, một cost/khoản không cộng trùng.
- Giữ của main: association≠allocation (TC25), missing-evidence FACT +
  `expense:missing_required_evidence` + EXCEPT_POLICY exception (TC20),
  single-cost-per-row, relevance FACT, Q32 bounded claim, S=E−A−P+R, 8/4/20tr.
- Không sao chép lỗi Hoangha: `process_settlement.py:751-753`
  catch-ValueError→`normalized_items=[]`→policy PASS (fail-open);
  digital invoice+payment cộng trùng; không kiểm payee vs supplier;
  identity/department hardcoded; ready=settled.

## 2. Thay đổi (backend core S1–S5 + mặt draft)

- `admission._ALTERNATIVE_EXPENSE_TYPES` + `_MatchedExpense.alternatives/note/
  amount_known`: row refs đặt tên docs thay thế → association (explicit unique
  number), KHÔNG tạo cost mới, refs hai phía.
- FACTs từng trục: `service_basis`, `payment_basis` (payer/payee/amount/status),
  `party_mismatch` (payee≠issuer, refs hai phía, không kết luận gian lận),
  `exception_reason` (bổ sung đúng dòng, giữ association), `note_contradiction`
  (chỉ khi ảnh hưởng nghiệp vụ). Đủ facts + có reason → POLICY
  `missing_evidence` (accountant) — tái dùng exception TC20, không số hạn mức mới.
- `note` vào prompt row fields (nguyên văn, tùy chọn); không suy reason từ note;
  `requires_evidence` vẫn không miễn gì (test khóa); bool thô bị DTO từ chối.
- Fail-closed: row amount hỏng → giữ row, UNKNOWN, không drop/0/PASS.
- Draft: row alternative-only → status `ALTERNATIVE` + filename, không tick xanh;
  UI khối amber "Bằng chứng thay thế — chờ xác minh và xác nhận ngoại lệ".

## 3. Kiểm chứng (provider mode: deterministic fixtures, 0 provider call)

- `tests/unit/test_tc18_alternative_evidence.py` (7) + `tests/tc18_shapes.py` +
  `tests/integration/test_tc18_reconciliation.py` (4): mismatch các bên BLOCK +
  T=4.2m + 1 cost 1.5m + 800k không thành thu; consistent→POLICY→exception mô
  phỏng clear đúng POLICY, không đổi số; requires_evidence=false vẫn FACT;
  malformed giữ row UNKNOWN.
- Full unit GREEN; full integration GREEN (trừ 6 pre-existing đã biết);
  frontend 48/2 + build; `git diff --check` sạch.
- Browser: NOT_RUN (task cấm LIVE mới; chưa có fixture-DB browser). Component
  tests cho ALTERNATIVE/dispute render PASS thay thế một phần.

## 4. Gates 13 regression

1 PASS. 2 PASS (consistent variant + exception). 3 PASS (note đúng/sai/mất +
refs giữ). 4 PASS (reason thật + reason web tách OCR — phía lưu web reason
thuộc S6). 5 PASS. 6 PASS. 7 PASS (gộp 1 chứng từ/nhiều dòng đã có T4/TC23 +
không cộng trùng alternative). 8 PARTIAL (chung core phía paper; digital form
S6 chưa xong). 9 NOT_RUN (tự chi S6). 10 PASS (thiếu/sai/vượt — qua cơ chế
exception+grant hiện có; hết hiệu lực theo effective interval của grant).
11 NOT_RUN (OCR region UI thuộc S6; TC18 có 0 meaningful candidate nên không
giả cảnh báo). 12 PASS một phần (source swap/forged có guards hiện hữu +
tests mới; Stop/revision/idempotency không đụng). 13 PASS (suites đầy đủ).

## 5. Còn lại (S6, chưa chốt)

- Digital form 4 tổ hợp, tự chi (khai không-ứng, xung đột A, PAY partial/full),
  accountant exception view, OCR region view: thiết kế trong spec, chưa code.
- Hạn mức ngoại lệ 8tr là đề xuất, KHÔNG policy được duyệt — cơ chế grant/
  max_effect hiện có sẵn sàng nhận số khi user chốt.


## 6. S6 continuation — snapshot cuối 17/10/2026

Mã làm việc main, không commit/push; 0 external OCR/LLM calls. Python3.12.13
qua uv, Node24.19.0/npm11.12.1. Source hash:
`.runtime/s6-resume-20261017/tested-source-hashes.json`.

### Đã sửa và bằng chứng

- Kế thừa backend/API/digital intake/exception/region S6 từ handoff, giữ nguyên
  các diff khác. Không chạm DB người dùng, port8000/Railway/PDF25case/context/gold.
- A2 fresh reproduction gửi được cả 2 POST actuals; không tái hiện triệu chứng
  “full không POST” cũ. Script cũ chỉ click+sleep nên ghi step PASS không chứng minh
  mutation. Script mới kiểm HTTP response/fulfilled/remaining, lưu response JSON,
  lỗi thì giữ screenshot/body.
- Upload payout proof riêng trên UI. Hai PDF seed-only công ty→nhân viên (1tr,
  2.7tr) không dùng biên nhận nhân viên→nhà cung cấp để giả làm hoàn chi.
- MarkExecution API/UI: version, lệnh thuộc root, grant RECORD_ACTUAL đúng
  action/scope/profile/amount/time, căn cứ thuộc tenant/root/digest + page/quote,
  reason bắt buộc; bump/audit/reassess atomic + idempotency. Không tạo money event.
- Guard S0/FULFILLED nhưng OPEN/UNKNOWN giữ WAITING; proof-backed close mới gỡ.
  Đây là lỗi cũ được sửa trong continuation, có test phản ví dụ.
- Recheck chỉ DOSSIER_RECORDS có sẵn + stale issue; không nhầm missing thành
  stale và không gọi legacy initial-history. Reject unresolved/unallocated/
  conflict; giữ source DOSSIER_RECORDS, không thêm opening0 hay full-bank claim.
- Paper self-expense submit đúng settlement_type/PAPER_SCAN/no-advance reason;
  declaration giữ choice/assertion để audit/reload. Có RED→GREEN component và
  backend serialization regression; browser D kiểm persisted declaration bằng DB.
- Flow C sửa selector tab hidden → visible. Lượt FAIL trước giữ nguyên trong
  `.runtime/s6-resume-20261017/failed-c/`; reset chỉ DB test C rồi chạy lại.

### Gates và lệnh

| Gate | Kết quả | Evidence |
|---|---|---|
| Backend targeted S6 closure/recheck/authority | PASS | tests/integration/test_s6_execution_close.py + full XML |
| Browser A tự chi/digital + có ứng mâu thuẫn | PASS 10/10 | .runtime/s6-browser/flow-a-self-conflict/ |
| Browser A2 tự chi/digital → ngoại lệ → PAY partial/full → close/reload | PASS 18/18 | .runtime/s6-browser/flow-a2-self-clean/ |
| Browser B giấy/tạm ứng + mismatch + OCR region ảnh tải thật | PASS 10/10 | .runtime/s6-browser/flow-b-paper/ |
| Browser C grant thấp UI disabled + direct API reject | PASS 11/11 | .runtime/s6-browser/flow-c-low-grant/ |
| Browser D tự chi/giấy + reload | PASS 9/9 | .runtime/s6-browser/flow-d-self-paper/ |
| DB authoritative checks | PASS | db-verification.json |
| Full pytest | FAIL: 959 passed / 6 failed (965 total) | full-accepted.log/xml |
| Full frontend | PASS 60 / SKIP2 | frontend-final3.log |
| Build | PASS | build-final3.log |
| git diff --check | PASS | command exit0 |
| Fresh LIVE OCR/LLM | NOT_RUN, not authorized | fixture RECORDED_REPLAY only |
| Independent re-review after fixes | NOT_RUN | initial review + regression fixes below |

Commands ran: `rtk proxy uv run --frozen --python 3.12 pytest -q
--junitxml=.runtime/s6-resume-20261017/full-accepted.xml`; frontend `npm test`,
`npm run build` under verified Node24 scoped PATH; five `frontend/s6-flow-*.mjs`
against ports65132–65136, isolated DB per flow, same seed/PDF digests.

A2 final UI+API+DB: SETTLED, E3.7tr/A0/P3.7tr/R0/S0, one PAY3.7tr FULFILLED,
remaining0, CLOSED_CONFIRMED, exactly2 money events, no open issue. Saved coverage
DOSSIER_RECORDS, opening_balance absent. Dashboard after reload says đã cân bằng.
Synthetic A2 is not TC18 original: smaller labor1tr used to stay within existing
4tr automatic instruction ceiling; original mismatch TC18 remains blocked.
D paper has no alternative exception reason/payer proof for every cost: correct
output WAITING + exception_reason/payer FACT, no instruction; choosing self-expense
never proves the payer or a policy exception.

### Six inherited failures — not waived

Baseline check restored the handed-over service/routes in a copied source package
under `.runtime/s6-resume-20261017/baseline/`; remaining dependencies unchanged.
`baseline-check.py` prints actual import path, reruns the two affected modules.
Exact six failure names match current run (`failure-classification.json`). This
establishes pre-existence before this continuation, not that every prior branch
has identical failures. No date guard relaxed, xfail added or missing corpus
reconstructed to force green.

- `tests.integration.test_employee_return_draft_api::test_employee_return_upload_is_durable_but_does_not_record_R` — AssertionError: assert 'NEEDS_REVIEW' == 'MATCHED'
- `tests.integration.test_employee_return_draft_api::test_accountant_confirmation_records_one_instruction_bound_return` — AssertionError: {"detail":"Ngày chuyển chưa hợp lý với thời điểm lệnh thu/hệ thống.","code":"IDEMPOTENCY_CONFLICT"}
- `tests.integration.test_employee_return_draft_api::test_pending_second_return_cannot_confirm_after_collect_is_fulfilled` — AssertionError: {"detail":"Ngày chuyển chưa hợp lý với thời điểm lệnh thu/hệ thống.","code":"IDEMPOTENCY_CONFLICT"}
- `tests.integration.test_employee_return_draft_api::test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction` — AssertionError: {"detail":"Ngày chuyển chưa hợp lý với thời điểm lệnh thu/hệ thống.","code":"IDEMPOTENCY_CONFLICT"}
- `tests.integration.test_employee_return_draft_api::test_overpaid_return_is_recorded_but_raises_a_specific_blocker` — AssertionError: assert 'NEEDS_REVIEW' == 'OVERPAY'
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]` — invoice_referee.evaluation.packets.PacketError: missing packet file: /Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/.runtime/legacy-corpus/case-06-chi-phi-vuot-ngan-sach/input/organization.json

Five return tests depend on fixture date and fail transaction-date plausibility
(MATCHED/OVERPAY becomes NEEDS_REVIEW, confirmation409). The sixth requires a
missing ignored legacy packet organization.json. They remain outside this S6
completion and make the full regression gate FAIL.

### Independent review and remaining limits

Read-only reviewer Rawls report:
`.runtime/s6-resume-20261017/independent-review.md` (reviewed partial continuation,
not all inherited diff). Found two new coverage caller/UI issues and one existing
FULFILLED/UNKNOWN state defect; all addressed with regression evidence. No second
reviewer approval is claimed. `fulfilled-unknown-red.log`, `recheck-red.log`,
`review-coverage-red.log`, `review-fixes-final.log` preserve the fix cycle; final
full suite includes added grant-dimension and unresolved-history tests.

No measured LIVE OCR quality/latency claim. No browser for every permission/time
combination; those use integration/component tests. No dedicated final browser
no-bbox failure screenshot (renderer/API/component tests cover fallback). Real
production exception ceiling remains undecided; seed grants do not change policy.
No commit, push, deploy, or shared DB migration performed. Existing unrelated
working-tree changes preserved.

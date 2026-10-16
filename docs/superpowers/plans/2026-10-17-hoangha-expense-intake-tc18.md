# Plan: Hoangha expense intake + TC18 alternative-evidence → main (17/10/2026)

Tiếp tục main @ 8a9bbdc7. Không merge worktree, không viết lại pipeline,
không LIVE/OCR/LLM mới, không commit/push. Một integrator (inline).
Refs: spec `docs/superpowers/specs/2026-10-16-hoangha-expense-intake-integration-design.md`,
TC18 Hoangha `.worktrees/hoangha/.runtime/tc18-deep-live-20261016/`, business-map.

## Đã có ở main (giữ, không làm lại)
- `no_evidence_reason` tách khỏi note (prompts.py:55-58); ALTERNATIVE_EVIDENCE
  status + PAYMENT_PROOF/ACCEPTANCE_RECORD types; association≠allocation (TC25);
  missing-evidence FACT + `expense:missing_required_evidence` + EXCEPT_POLICY
  exception (TC20); single-cost-per-row (T4); relevance FACT; Q32 bounded claim.
- `requires_evidence` không được code đọc ở đâu → hiện không miễn gì cả.

## Gap → slice
1. **S1 matching allocation**: `row_total`/demote cộng cả docs thay thế →
   false over-allocation khi 1 dòng có 2 docs (TC18 labor 1.5+1.5 vs 1.5).
   Fix: chỉ docs gốc tham gia tổng/phân bổ; docs thay thế giữ AUTO association.
2. **S2 admission alternative-aware** (`admission.py`, owned + consumers:
   service/policy/draft/UI): row refs đặt tên docs thay thế → association
   (explicit number, unique), KHÔNG tạo cost mới, một cost duy nhất/dòng.
   Claim FACTs từng trục: service/delivery (nghiệm thu), payment
   payer/payee/amount/status (transfer); `party_mismatch` FACT khi payee ≠
   issuer/supplier (TC18 AnThịnh vs PhúcAn), refs hai phía, blocking, không
   kết luận gian lận; thiếu reason → FACT bổ sung đúng dòng
   (`:exception_reason`, employee), giữ association; đủ facts nhưng thiếu
   gốc → POLICY `expense:missing_required_evidence` (tái dùng exception +
   grant EXCEPT_POLICY hiện có, KHÔNG số hạn mức mới).
3. **S3 note semantics**: không suy reason từ note (test khóa); note mâu thuẫn
   nguồn có ảnh hưởng (đã/chưa trả, sai số, sai bên) → FACT cụ thể;
   `requires_evidence=false` không miễn (test khóa).
4. **S4 TC18 fixture**: deterministic admit+reconcile shape TC18 gốc
   (mismatch các bên, không tiền, không cộng trùng, 800k không phải thu) +
   biến thể facts nhất quán → POLICY → exception (grant mô phỏng) quyết được.
5. **S5 fail-closed audit**: main không có catch→[]→PASS (khác Hoangha
   process_settlement.py:751-753); test khóa invalid row không thành rỗng/0/PASS.
6. **S6 digital + tự chi + UI** (lớn, làm sau S1–S5): Declaration mở rộng
   (settlement_type/source_type/digital lines + mapping + provenance khai báo,
   khai không-ứng), chung core, API, intake form 4 tổ hợp, accountant exception
   view, OCR region view. Hạn mức ngoại lệ: cơ chế cấu hình/grant, KHÔNG số mới.

## S6 build (18/10/2026) — owned files, consumers, gates

Integrator duy nhất cho shared DTO/API/workflow. 0 provider call.
Ngày thực tế hiện tại; không sao chép ngày cũ.

1. **DTO + adapter** (owned: `domain/commands.py`, `reconciliation/digital_intake.py`
   mới; consumers: routes, workflow, admission via confirmations):
   `DigitalExpenseLine` (item_id ổn định, description, category?, date, amount
   int, evidence_status, alternative_type?, exception_reason?, note, source_ids),
   `Declaration` += settlement_type/submission_source/digital_lines/
   no_advance_asserted/no_advance_reason. Server validate toàn bộ; mapping bằng
   source_id đã attach (không filename). Adapter declaration→synthetic
   SETTLEMENT_FORM (provenance DECLARATION, digest thật của declaration,
   record_key=item_id; invoice_refs合成 từ số docs đã map) → chung
   match/admission/policy/money. Gate: unit RED→GREEN.
2. **Tự chi**: submit digital self-expense ghi Confirmation `settlement:no_advance`;
   admission FACT `advance:type_conflict` khi sổ có ADVANCE_RECEIVED đã CONFIRMED
   cùng scope (đề nghị đổi loại, không xóa); không advance → A UNKNOWN (coverage
   hiện có xác lập 0, không auto-zero). Không ô nhập ứng cho tự chi (UI).
   Gate: integration type-conflict + no-advance clean.
3. **Ngoại lệ bền**: bảng `case_exception_decisions` (migration IF NOT EXISTS);
   Decide accept EXCEPT_POLICY persist + grant check hiện có + reason bắt buộc;
   lệnh RefuseException mới (accountant/approver, audit, giữ issues);
   snapshots nạp exceptions vào AssessmentInput; preview endpoint cho UI
   (covered/grants/amount). Gate: accept/refuse/expired/over-limit tests.
4. **OCR region**: port renderer → `evidence/ocr_preview.py` (PIL+pymupdf có sẵn,
   font NotoSans trong assets/); endpoint preview PNG theo ref (source/page/bbox
   validate; không bbox → 409 + fallback quote); component `OcrRegionView`;
   answer hiện có lưu actor/reason/refs/version. Gate: unit renderer + API.
5. **Fake transport**: `evidence/fake_transport.py` (dev/test-only: ReplayReader
   OCR có sẵn + FakeLLM `complete_json` theo marker trong prompt, fixtures do
   seed sinh); wire trong `_wire_replay` khi `INVOICE_REFEREE_FAKE_LLM_DIR` set.
   Report nhãn RECORDED_REPLAY. Gate: seeded read == fixture facts.
6. **API**: digital declaration save/read/submit mở rộng, exception preview/
   refuse, ocr-preview. Tương thích hồ sơ cũ (fields optional, default
   ADVANCE_SETTLEMENT/PAPER_SCAN).
7. **Frontend**: start screen 2 nhóm (persist localStorage + case), digital form
   (lines add/remove, upload/line, validation messages), draft hiển thị
   evidence_files + exception_reason/“thiếu lý do”, exception panel theo khoản
   (grant/limit/accept/refuse+reason), OCR region trong issue panel.
   Gate: component tests + build.
8. **Browser A–F** trên DB seed riêng (fake transport, port riêng, fixed clock):
   A tự chi digital; B giấy tạm ứng; C accountant FACT+exception đúng grant;
   D recordActual partial/full→SETTLED; E OCR region có/không bbox; F reload/
   persona. Screenshots + summary.json. Gate: PASS, nếu không thì NOT_RUN/FAIL
   cụ thể.
9. **Docs**: acceptance/status/plan/contracts(§2/§9 Declaration,
   exceptions persist)/runbook.

## S6 continuation checklist — 17/10/2026

- [x] DTO/adapter, tự chi, durable exception accept/refuse/grant, OCR preview,
  fake transport, API + intake UI triển khai (kế thừa handoff, kiểm bằng suites).
- [x] Sửa paper tự chi submit đúng type/no-advance và lưu vào declaration audit.
- [x] Record actual partial/full UI có proof upload riêng, HTTP/state asserts.
- [x] MarkExecution API/UI: version, root/source/grant guards, audit/reassess.
- [x] Guard FULFILLED + UNKNOWN không SETTLED (regression phản ví dụ).
- [x] Recheck chỉ checkpoint dossier đã tồn tại, giữ DOSSIER_RECORDS;
  không gọi legacy initial history hoặc tự giả opening0.
- [x] Browser snapshot cuối A10/A2 18/B10/C11/D9 PASS, fresh own DBs.
- [x] Full suites/build đã chạy và phân loại: pytest959pass/6fail inherited, frontend60pass/2skip/buildPASS.
- [ ] Full backend regression GREEN: còn6 inherited, không waive.
- [ ] Chấp nhận full plan chỉ khi các gate bắt buộc đạt; LIVE và production
  exception ceiling chưa có nghiệm thu, không claim đã xong.

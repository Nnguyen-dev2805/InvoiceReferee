# Role-aware Kimi runtime — acceptance (16/10/2026)

Scope: user request 16/10/2026 (runtime LLM + upload theo vai trò + time budget).
Authorized: code + tests + plan + this report + status/runbook/contract-refinement notes.
NOT authorized (kept): commit/push/deploy/reset, PDF/context/gold edits, user DB,
port 8000, Railway. Plan: `docs/superpowers/plans/2026-10-16-role-aware-kimi-runtime.md`.

## 1. Thay đổi

- **Runtime Kimi-K3** (`evidence/kimi.py` new, `config.py`, `runtime.py`, `.env.example`):
  `LLM_PROVIDER=kimi` mặc định, model `moonshotai/Kimi-K3`; xKiro là lựa chọn
  explicit (`llm_provider=xkiro`). Không fallback ngầm (lỗi Kimi raise, không
  retry qua xKiro). Endpoint/credential chỉ từ local ignored config, không
  hardcode URL riêng tư. OCR vẫn Mistral. Confidence/extraction/resolver đều
  dùng LLM đã chọn. `missing_for_live` provider-aware.
- **Reader identity** (`prompts.py`): gồm `llm_provider/llm_model`,
  `ocr_provider/ocr_model`, pipeline tag (`role-aware-v1` vs
  `classify-then-extract-v1`). Basis/include resume: digests + upload_roles +
  provider/model + identity + case_version/input_revision/control_epoch.
  Report cũ thiếu identity không reuse.
- **Upload theo vai trò** (domain `SourceRef/SourceUpload.upload_role`,
  migration v11 `case_sources.upload_role`, service/API/frontend):
  ô paper (đúng 1 đơn) + ô evidence (nhiều file). Pipeline mới
  `read_root_role_aware`: OCR mọi file → confidence điều kiện → extraction theo
  vai trò (paper: SETTLEMENT_FORM + role_fit; evidence: type+facts kết hợp,
  1 call/doc) → validate → rule matching → reuse `resolve_evidence_suggestions`.
  Không standalone classification trên luồng mới; legacy không-role giữ nguyên.
  Sai role → problem `fix_upload_role` rõ ràng, cho sửa, không ép loại.
  Prompt evidence liệt kê vocabulary từng loại (code-owned) + alias receipt
  scoped (`receipt_number→document_number`, `receipt_date→document_date`,
  `amount→total_amount` cho PAPER/HOTEL/COLLECTION; TRANSPORT giữ
  `fare_amount`, SETTLEMENT rows giữ `amount`).
- **Time budget** (giữ 90s, không nới): guard `can_call_llm` trước mọi call
  (confidence/extraction/resolver); hết budget → `ProcessingProblem` TECHNICAL
  blocking đúng stage/source (`resume_extraction`/`resume_resolver`), giữ kết
  quả đã xong, không FACT thiếu-chứng-từ giả, không tiền. Checkpoint per-doc +
  budget counters trong `jobs.attempts_json`; resume skip bước xong, invalid khi
  đổi hash/role/model/prompt/version/revision/epoch; retry hữu hạn (≥3 FAILED
  refuse). Partial không assess/commit. UI `processing_status`:
  ready/technical_incomplete/needs_supplement.
- **Matching sync** (`settlement_draft.py`): draft dùng chung
  `_invoice_ref_matches_number` (hotel IR26E/00002502 CLEAR, khớp final);
  linked-nhưng-chưa-CLEAR → NEEDS_VERIFICATION, giữ tên file tham chiếu.

## 2. Bằng chứng LIVE (DB/artifacts riêng, giữ cả lần thất bại)

- `.../tc25-role-aware-live-20261016/run-01` (giữ): 4 OCR ok, 5 LLM
  (confidence1+extract3, receipt chưa chạy), WAITING + 7 FACT generic, không
  delta tường minh. Nguyên nhân: prompt evidence thiếu vocab theo loại
  (receipt ra `receipt_number/amount` → NEEDS_HUMAN) — đã sửa, có regression tests.
- `.../run-02` (PASS): **6 LLM** (confidence1+extract4+resolver1,
  classify0), 4 OCR, 69.4s. `llm_provider=kimi`,
  requested `moonshotai/Kimi-K3`, returned `[moonshotai/Kimi-K3]`,
  trace_export_errors 0. WAITING/BLOCKED, instructions [], conclusion BLOCKED.
  FACT tường minh: `expense:allocation:…COLLECTION_RECEIPT` —
  "Kê khai 900000 nhưng chứng từ chỉ chứng minh 700000 (lệch 200000); số tiền
  đang tranh chấp", refs receipt 2 phía số/quotes. Draft/final nhất quán:
  2 dòng CLEAR matched, dòng 900k SUGGESTED → phieu_thu_di_chuyen.pdf.
  Tồn dư báo riêng: expense:T, source_date trip, missing_evidence (lý do khai
  "Phiếu thu thay thế hóa đơn"), payer — đúng yêu cầu, không tự sửa giấy/số.
- `.runtime/tc01-role-aware-live-20261016/run-01` (PASS): 3 LLM
  (confidence1+extract2, classify0), 27.8s, READY_TO_EXECUTE,
  COLLECT 760000, 0 issues, draft CLEAR matched. Kimi verified như trên.
- `.runtime/browser-role-aware-20261016/tc01` (PASS 11/11 steps):
  2 ô upload → draft CLEAR matched → chọn radio advance → submit →
  badge "Sẵn sàng phê duyệt", T=3.240.000/S=-760.000, tab hoàn trả 1.
  Server LIVE riêng port 65121, DB riêng. Lần 409 giữa chừng là guard chống
  trùng hồ sơ đúng đắn (activity đã bound), rerun DB sạch PASS.

## 3. Gates (13 verification)

1. Provider Kimi chính/xKiro explicit/không fallback — PASS (unit + LIVE verified).
2. Role persist sau restart; sai role + UNKNOWN — PASS (integration + unit).
3. 1 paper + 3 evidence = 4 extraction, 0 standalone classify mới — PASS (unit + LIVE 4/0).
4. Confidence/resolver điều kiện; trace đếm stage/repair/retry — PASS (spans run-02).
5. Timeout trước file cuối: TECHNICAL đúng nguồn, không FACT giả, không tiền — PASS (integration).
6. Resume skip done; đổi hash/model/prompt/version invalid đúng phạm vi — PASS.
7. Resume/Stop/retry không trùng financial effect — PASS (partial không assess; basis guards).
8. Draft/final matching nhất quán — PASS (unit + LIVE hotel + TC25 SUGGESTED).
9. TC25 900k/700k/200k + refs + chặn tiền — PASS (run-02).
10. Advance/return flows không phá — PASS (advance suite green; 5 return failures
    pre-existing, đã xác minh fail identically trên cây sạch).
11. Focused + full + frontend — PASS: unit full; integration trừ 6 pre-existing
    (5 return date-fixture + 1 raw6 thiếu `.runtime/legacy-corpus`); frontend
    46 pass/2 skip; build ok (Node 26.0.0/npm 11.12.1, pin .node-version=24 —
    ghi nhận chênh runtime); `git diff --check` exit 0; ruff NOT_RUN (chưa cài).
12. LIVE TC25 + 1 valid multi-doc — PASS (run-02 + TC01 run-01).
13. Browser role upload → draft → submit — PASS (11/11, evidence trên).

## 4. Còn lại / giới hạn

- Contract §12 vẫn mô tả pipeline classify-then-extract; refinement role-aware
  ghi tại đây + §12.5 note (xem mục 5). Full rewrite §12 là việc riêng.
- `recover_incomplete` (crash restart) chưa được dev server gọi — pre-existing gap.
- 90s là trần pilot chưa đo kiểm đầy đủ cho >4 file; resume bù đắp, không nới ngầm.
- 5 return date-fixture + 1 raw6-corpus failures pre-existing, ngoài scope.
- Secrets: KIMI_* chỉ trong `.worktrees/hoangha/.env` + env process; không log/commit.

## 5. Contract refinement (16/10/2026, theo hành vi thực tế)

- §12.2: `classify_documents` (một batch/root) chỉ còn áp dụng luồng legacy
  (upload thiếu role). Luồng mới không gọi phân loại cả bộ; mỗi evidence một
  extraction kết hợp type+facts; paper một extraction SETTLEMENT_FORM + role_fit.
- §12.3: `build_evidence_extraction_prompt` mang vocabulary từng loại do code sở
  hữu; alias receipt scoped (§12.3 provenance giữ nguyên: quote/page/source check).
- §12.5: `reader_identity` gồm provider/model hai đầu + pipeline tag;
  `input_basis` gồm digests, upload_roles, identity, provider/model, version/
  revision/epoch. Partial TECHNICAL blocking → TECHNICAL_ERROR + checkpoint,
  không EVIDENCE_READY, không assess.
- Timeout 90s (`trace.py`, contracts §6) giữ nguyên; exhaustion mid-pass là
  `extraction-not-run` TECHNICAL có stage/source, không phải missing-source FACT.

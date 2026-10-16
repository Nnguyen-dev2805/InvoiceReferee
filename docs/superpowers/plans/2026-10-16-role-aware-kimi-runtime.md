# Plan ngắn: role-aware Kimi runtime + time budget (16/10/2026)

## Gate status (16/10/2026 — xem acceptance review)

- [x] A. Provider Kimi-K3 default / xKiro explicit / no fallback (+identity)
- [x] B. Role-aware upload + pipeline (4 extraction, 0 classify) + legacy compat
- [x] C. Time budget guards + checkpoint/resume + finite retry (giữ 90s)
- [x] D. Matching sync draft/final (hotel suffix, NEEDS_VERIFICATION)
- [x] LIVE TC25 run-02 PASS + TC01 valid PASS + browser 11/11 PASS
- [x] Full unit + integration (trừ 6 pre-existing) + frontend 46/2 + build
- [ ] Contract §12 full rewrite (deferred; refinement ghi trong acceptance review)

Scope từ user request 16/10/2026. Không sửa PDF/context/gold, DB user, port 8000, Railway.
Không commit/push/deploy/reset. Secrets chỉ local ignore.

## Owned files (integrator serializes shared schema/workflow)

- A. Provider: `src/invoice_referee/config.py`, `src/invoice_referee/evidence/kimi.py` (new),
  `src/invoice_referee/evidence/xkiro.py`, `src/invoice_referee/runtime.py`,
  `src/invoice_referee/evidence/prompts.py` (identity), `.env.example`.
- B. Role upload: `src/invoice_referee/domain/evidence.py` (`SourceRef.upload_role`),
  `src/invoice_referee/domain/commands.py` (`SourceUpload.upload_role`),
  `src/invoice_referee/workflow/schema.sql` + `db.py` (migration v11),
  `src/invoice_referee/workflow/service.py`, `src/invoice_referee/api/routes.py` + `views.py`,
  `src/invoice_referee/evidence/pipeline.py`, `src/invoice_referee/reconciliation/settlement_draft.py`,
  `frontend/src/features/intake.tsx` + `frontend/src/api.ts`.
- C. Budget/resume: `src/invoice_referee/evidence/trace.py` (refinement 90s nếu đổi),
  `src/invoice_referee/evidence/pipeline.py`, `src/invoice_referee/workflow/evidence_jobs.py`,
  `src/invoice_referee/workflow/service.py` (basis/checkpoint), frontend status.
- D. Matching: `src/invoice_referee/reconciliation/settlement_draft.py`, admission consumer giữ nguyên.

## Consumers

- `read_root` / `read_root_role_aware` → `read_settlement_draft`/`get_settlement_draft` →
  `build_settlement_draft` → admission (`admit_evidence`) → `Reconciler.assess` → policy/finance.
- `evidence_jobs.run_evidence_job` → `_publish_evidence_report` → `_assess_and_commit`.
- Advance/return/money flows dùng draft riêng, không đi settlement pipeline — giữ nguyên.
- Frontend Intake đọc draft mới; old API không role vẫn phải chạy legacy.

## Migration/compatibility

- `case_sources.upload_role TEXT NOT NULL DEFAULT ''` (v11 additive; '' = legacy unknown).
- `SourceRef.upload_role: Literal['paper','evidence'] | None` (None = legacy, strict extra forbid giữ).
- Basis/reader_identity gồm: source digests + upload_roles + provider + endpoint-ish (không secret)
  + model requested + prompt/schema/reader/pipeline versions + case version/input_revision/control_epoch.
- Old record thiếu role → legacy `read_root` (classify+extract), không đoán paper/evidence.
- New record đủ role → `read_root_role_aware`, không standalone classification.
- `read_cache.reader_config` phải gồm identity mới; cache cũ miss đúng phạm vi.

## Acceptance gates (map 13 verification)

1. Provider: Kimi default, xKiro explicit OK, Kimi lỗi không fallback.
2. Role persist sau restart; wrong-role + UNKNOWN rõ.
3. 1 paper + 3 evidence = 4 extraction, 0 standalone classify mới.
4. Confidence/resolver conditional; trace đếm stage/repair/retry thực.
5. Timeout trước file cuối: TECHNICAL đúng source, không FACT thiếu-chứng-từ giả, không tiền.
6. Resume skip done; đổi hash/model/prompt/version invalid đúng phạm vi.
7. Resume/Stop/retry không trùng financial effect.
8. Draft/final matching nhất quán (hotel IR26E/00002502).
9. TC25: 900k/700k/200k + refs 2 phía + chặn tiền.
10. Advance/return flows không phá.
11. Focused + full + frontend build.
12. LIVE TC25 + 1 valid multi-doc, DB riêng.
13. Browser role upload → draft → submit đúng trạng thái/câu hỏi.

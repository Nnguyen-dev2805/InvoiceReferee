# Plan: draft hiển thị mâu thuẫn liên chứng từ TC25 (17/10/2026)

Không viết lại pipeline. Shared logic thuần duy nhất trong `matching.py`,
draft + admission cùng dùng. Owned: `domain/documents.py` (+DTO/status),
`evidence/matching.py`, `reconciliation/{admission,settlement_draft}.py`,
`frontend/.../intake.tsx` + `api.ts`, tests, report.
Consumers: draft builder/API/UI, admission FACT, trace/report rows.
Không persistence migration (draft rebuild từ report; report schema không đổi
ngoài giá trị status mới trong Literal).

1. `RowAmountConflict` (DTO) + `cross_document_conflicts(paper, documents)`:
   association = unique exact-number (link-independent), amount/total int,
   diff>1 → conflict; nhiều dòng chung doc → gộp một conflict (tổng, refs
   mọi dòng); skip amount/total thiếu-mờ-mơ hồ, doc UNKNOWN/trùng mã/summary.
2. `project_evidence_matches`: row DISPUTED_EVIDENCE khi conflict Detroit mà
   không AUTO; unmatched trừ docs associated-duy nhất.
3. Admission dùng conflicts cho disputed/FACT (thay 2 block hiện tại, giữ
   wording + SET_PAPER_AMOUNT_001); expense-loop giữ nguyên.
4. Draft: `reconciliation_findings` typed + row DISPUTED (giữ filenames).
5. UI: cảnh báo đỏ tại dòng (900k/700k/200k + tên phiếu), không tick xanh,
   nút xem 2 nguồn qua viewer hiện có; tổngadvance giữ số giấy; reload bền
   (rebuild từ report).
6. Submit giữ nguyên (WAITING + FACT + chặn tiền, không trùng issue).
7. Browser DB riêng, replay artifacts (0 provider call mới).
Regression A–J → deterministic replay artifacts → browser DB riêng.

## Gate status (17/10)

- [x] 1–6 + regression A–H, J (unit/integration/replay determinism)
- [x] Post-submit browser DB copy PASS (0 POST)
- [ ] I browser-thật màn review NOT_RUN (cần quota LIVE riêng)
- Xem acceptance `docs/final/reviews/2026-10-16-draft-cross-document-conflict-acceptance.md`

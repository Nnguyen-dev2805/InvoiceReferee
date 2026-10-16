# Draft hiển thị mâu thuẫn liên chứng từ TC25 — acceptance (17/10/2026)

Kế tiếp task association 17/10. Không viết lại pipeline, không LIVE
mới (0 OCR/LLM call), không money-event từ draft. Plan:
`docs/superpowers/plans/2026-10-17-draft-cross-document-conflict.md`.

## 1. Root cause

`project_evidence_matches` chỉ công nhận AUTO_LINK: dòng ITEM-003 có
SUGGEST exact-number duy nhất (900k vs receipt 700k) vẫn bị gán
`NO_EVIDENCE` + findings EVIDENCE_REQUIRED/UNMATCHED_001; draft chỉ còn
"Có thể liên quan", không số mâu thuẫn. Admission (declared-totals riêng)
thì ra FACT đúng — hai mặt dùng hai logic khác nhau.

## 2. Thay đổi

- `matching.cross_document_conflicts(paper, documents)` thuần mới + DTO
  `RowAmountConflict` (code/item_ids/document/papersố/doc-số/lệch/refs hai
  phía/blocking): association = unique exact-number (link-independent);
  nhiều dòng chung doc gộp một lần (không cộng hai lần); chỉ over-allocation
  mới dispute (under-claim là partial hợp lệ — bắt bằng regression TC05);
  skip thiếu/mờ/mơ hồ/UNKNOWN/trùng mã/summary, không điền 0.
- `matching.conflict_basis()`: wording chung cho draft + admission FACT.
- Projection: row DISPUTED_EVIDENCE khi conflict mà không AUTO;
  finding mới SET_PAPER_AMOUNT_DISPUTED (giữ EVIDENCE_REQUIRED cho trường
  hợp thật sự không evidence); unmatched trừ docs associated-duy nhất
  (dùng chung `associated_document_ids`).
- Admission dùng conflicts cho disputed/FACT (thay 2 block matched +
  declared, giữ wording/set AMOUNT_001); expense-loop, policy, payer giữ nguyên.
- Draft: `reconciliation_findings` typed (code/item/document/filename/status/
  3 số/basis/question/refs/blocking) + `dispute` inline từng expense
  (kèm paper/document source_id); status DISPUTED; rebuild từ report nên
  reload bền, không migration/cache mới.
- UI intake: khối đỏ tại dòng (900.000/700.000/lệch 200.000 + tên phiếu),
  không tick xanh khi DISPUTED; nút "Xem giấy"/"Xem phiếu thu" chọn tab
  viewer hiện có; tổng/advance giữ số giấy; không sửa số nguồn.
- Submit giữ nguyên: WAITING + cùng FACT + chặn tiền, không trùng issue.

## 3. Draft API trước/sau (TC25)

- Trước: `warnings[]`, `arithmetic_findings[]`, row SUGGESTED +
  "Có thể liên quan", không số mâu thuẫn.
- Sau: thêm `reconciliation_findings[{row-amount-disputed, ITEM-001,
  900000/700000/200000, AMOUNT_DISPUTED, refs 2 phía, blocking}]`;
  row `status DISPUTED` + `dispute{...paper/document_source_id}`.

## 4. Kiểm chứng (provider mode: replay artifacts STUB/deterministic)

- Unit/integration: conflicts (A/C/D/E/F), admission dedup + two-sided,
  policy suppression, projection status/unmatched, draft findings + DISPUTED,
  rebuild equality; full unit + integration pass (trừ 6 pre-existing đã biết);
  frontend 47/2 + build.
- Replay postfix artifacts qua code cuối (0 provider call): admission đúng
  1 FACT allocation; draft finding 900k/700k/200k + row DISPUTED +
  receipt filename; rebuild giống hệt; totals 4140000/5000000 giữ số giấy.
- Browser: post-submit trên DB copy (0 POST, 0 provider call) PASS —
  issues tab hiện câu hỏi + refs hai phía (screenshot `issues.png`).
  Màn hình review bản nháp: component test PASS; browser-thật NOT_RUN
  (cần draft read = provider calls, vượt quota task) — nêu rõ, không claim thay.

## 5. Gates A–J

A PASS (draft 900/700/200 + row/doc + 2 phía). B PASS (replay: 1 FACT,
không generic/missing giả, không instruction). C PASS (khớp → findings rỗng).
D PASS (trùng mã giữ ambiguity). E PASS (gộp tổng, không cộng hai lần).
F PASS (thiếu/mờ/mơ hồ skip, không 0). G PASS (validity tách bạch —
NEEDS_VERIFICATION giữ). H PASS (rebuild equality + GET path chung).
I PASS một phần (nút chọn tab viewer + component; browser-thật NOT_RUN).
J PASS (builder thuần, không DB/money/provider; replay DB chỉ đọc).

## 6. Còn lại

- `recover_incomplete` chưa được dev server gọi (pre-existing).
- Muốn browser-thật màn review cần quota LIVE riêng.

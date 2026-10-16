# TC25 association/dispute + latency — acceptance (17/10/2026)

Tiếp tục công việc role-aware Kimi (16/10). Không triển khai lại kiến trúc,
không mở rộng nghiệp vụ. Plan:
`docs/superpowers/plans/2026-10-17-tc25-association-latency.md`.

## 1. Root cause và thay đổi

- **Conflation association/allocation** (`admission._match_expense_documents`):
  chỉ AUTO_LINK+CLEAR được coi là matched; SUGGEST exact-number (TC25 receipt)
  rơi vào unreferenced → relevance FACT giả + row mất document → missing
  FACT giả. Sửa: `associated` = mọi link (kể cả SUGGEST) + number-match tường
  minh; unreferenced trừ associated; row giữ `associated_document_id`
  (unique exact-number) nhưng document=None (không tiền).
- **Provenance một phía**: allocation FACT chỉ refs receipt. Sửa: refs =
  paper row field refs + doc refs (helper `_row_refs`), dedup, row trước.
- **Câu hỏi dư** (A2): relevance/missing giả hết nhờ A1; policy triệt generic
  expense:T và expense:payer khi mọi UNKNOWN đều disputed; disputed row giữ
  source_date từ doc date FOUND (deadline chạy thật, không hỏi ngày giả).
- **Resolver thừa** (A4): `matching.identity_determined()` — mọi SUGGEST đều
  INVOICE_NUMBER_EXACT + unique → code xử lý, trace
  `resolver_skipped=identity_determined`; còn mơ hồ → resolver như cũ.
- **Telemetry sai provider** (A5): `record_llm_call(provider)` từ adapter thật;
  runner UNKNOWN khi thiếu returned_model.
- **Latency** (B1): `KimiClient(reasoning_effort="low")` + `KIMI_REASONING_EFFORT`
  (validate low/medium/high, sai lỗi rõ); gửi trong body OpenAI-compatible;
  identity + telemetry requested/observed (observed UNKNOWN vì response không
  xác nhận); xKiro không đổi. B2: repair receipt quá khứ = UNKNOWN (không đủ
  bằng chứng); thêm `repair_diagnostics` bounded cho lượt sau; giữ quota;
  malformed không bao giờ thành công. B3: chưa framework anchors — sau B1 mới
  đánh giá. B4: NOT_DONE (per-request AsyncClient; ~1s/70s không xứng loop-leak).

## 2. Trước/sau TC25 (cùng 4 PDF)

| | Kimi độc lập (cũ) | Mới (run-01 17/10) |
|---|---|---|
| Calls | 4 OCR + 7 LLM (repair1+resolver1) | 4 OCR + 5 LLM (confidence1+extract4, resolver **0**, repair 0) |
| Read/total | 72.2s / 81.6s | 38.6s total (draft 35.9s + submit 2.7s; W3 reuse, không job) |
| Extract completion | 6349 (paper 2539, lượt đơn lẻ) | 3195 (paper 924, lượt đơn lẻ) |
| Issues | 6 FACT (allocation + relevance + missing + source_date + payer + T) | **1 FACT allocation** 900k/700k/lệch 200k |
| State/money | WAITING/BLOCKED, không instruction | WAITING/BLOCKED, không instruction |

Số latency là lượt đơn lẻ mỗi bên, không phải A/B kiểm soát hay p50/p95 —
không tuyên bố speedup cứng, không quy tiết kiệm giây/token cho effort.
Quan sát được: ít hơn 2 LLM calls (không repair, không resolver trong lượt
mới), completion extract thấp hơn; nguyên nhân phân rã chưa đủ bằng chứng.

## 3. Kiểm chứng

- Deterministic: unit full pass (mới: telemetry/effort, identity_determined×3,
  admission×6, policy suppression×3, repair diagnostics×2, skip-resolver e2e);
  integration pass trừ 6 pre-existing đã biết; frontend 46/2 + build.
- LIVE quota: 1 TC25 (run-01 trên) + 1 TC01
  (`.runtime/tc01-association-live-20261017/run-01`: 3 LLM/21.5s,
  READY_TO_EXECUTE, COLLECT 760000, 0 issues, effort low/UNKNOWN).
- Refs hai phía: artifact LIVE (code trước `_row_refs`) một phía; replay
  deterministic report đã lưu qua code cuối → refs 2 nguồn
  (paper "Di chuyển nội thành/900.000/PT-251026-016" + receipt 700k...),
  0 provider call thêm. Gate 9 PASS với ghi nhận này, không chạy lại (giữ quota).
- Resolver 0 vì identity không còn mơ hồ (trace `resolver_skipped`).
- Browser: read-only trên DB TC01 có sẵn (0 POST, 0 provider call) — dossier
  T/E/A/S đúng + tab hoàn trả; PASS. Full upload→submit đã PASS 16/10, UI
  không đổi trong task này → không lặp tốn quota.
- Provider/model/effort: spans ghi kimi + requested/returned Kimi-K3 +
  requested low/observed UNKNOWN; KIMI_* chỉ local ignored config.

## 4. Gates

A1 association/allocation PASS. A2 dedup PASS (1 issue). A3 hai phía PASS
(replay). A4 skip-resolver PASS (0 call + trace). A5 telemetry PASS. B1 effort
PASS (wire-fake + LIVE). B2 UNKNOWN + diagnostics PASS. B3 NOT_DONE (chờ số
liệu B1 thêm). B4 NOT_DONE (lý do trên). Regression 1–10 PASS deterministic.
E tương ứng PASS/NOT_RUN như trên.

## 5. Còn lại

- Bổ sung review latency (17/10): diagnostic repair có cấu trúc
  (stage/attempt/code/field-path/category/summary lọc quote); wire effort
  top-level đúng semantics extra_body-merge (test phủ định `extra_body`,
  không thêm max_tokens — cap 20k chars + truncation error hiện có đã đủ);
  usage giữ reasoning/cached tokens khi có (thiếu = UNKNOWN, không cộng dồn);
  duration chỉ là request elapsed; regression semantics field giữ nguyên.
- Concurrency là đề xuất tiếp theo, không trong task này:
  trích xuất song song theo tài liệu là hướng đáng thử sau (giữ nguyên mọi
  guard nguồn/payer/tiền thực nhận và quota hiện hành).

- Contract §12 full rewrite (deferred; refinement ở đây).
- `recover_incomplete` chưa được dev server gọi (pre-existing).
- 90s là trần pilot; resume bù đắp.
- 5 return date-fixture + 1 raw6-corpus pre-existing.
- Báo cáo latency này dựa trên lượt đơn lẻ; muốn claim cần benchmark lặp lại.

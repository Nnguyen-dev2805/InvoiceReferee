# Plan ngắn: TC25 association/dispute + latency có kiểm chứng (17/10/2026)

Không triển khai lại role-aware/Kimi/DOC-DOCX hiện có. Owned files:
`evidence/{telemetry,kimi,matching}.py`, `evidence/pipeline.py` (2 match blocks),
`reconciliation/admission.py`, `domain/documents.py` (không đổi DTO),
`config.py` + `.env.example` (effort), tests mới, `scripts/run_role_aware_live.py`
(runner: UNKNOWN model + effort/token reporting).

Consumers: pipeline match → admission mapping → draft/final/questions/UI;
telemetry labels chỉ quan sát. Serialize sửa admission/matching shared.

## A. Nghiệp vụ (giữ nguyên tắc, sửa mapping)

- A5 telemetry: `record_llm_call(..., provider)` từ adapter thực tế
  (kimi/xkiro); runner UNKNOWN khi thiếu returned_model. RED: fake 2 providers.
- B1 effort: `KimiClient(reasoning_effort="low")` + `KIMI_REASONING_EFFORT`
  config default low; gửi trong body; transport-fake assert wire; identity +
  telemetry requested/observed (observed UNKNOWN khi response không xác nhận);
  provider từ chối → lỗi cấu hình rõ, không drop ngầm/không fallback.
- A4 skip resolver: helper `identity_determined(paper, documents, links)` —
  mọi SUGGEST đều INVOICE_NUMBER_EXACT + unique candidate → code xử lý,
  trace `resolver_skipped=identity_determined`; còn mơ hồ → resolver như cũ.
- A1 association/allocation: `_MatchedExpense.associated_document_id`
  (field mới có default); associated = mọi link (kể cả SUGGEST) + number-match
  tường minh; unreferenced trừ associated (hết relevance giả);
  disputed row giữ document=None (không tiền) nhưng nhớ doc id.
- A3 refs hai phía: allocation FACT refs = paper row refs + doc refs (dedup,
  fail khi thiếu một phía trong test).
- A2 dedup: skip missing_evidence khi row trỏ disputed doc duy nhất;
  expense:T và expense:payer generic bị triệt khi mọi UNKNOWN đều disputed;
  disputed-associated row lấy source_date từ doc date FOUND (deadline chạy thật).

## B. Latency (đo được, không giảm kiểm chứng)

- B1 (chính) + đo run-02/independent/run-mới.
- B2: quá khứ repair receipt = UNKNOWN (không đủ bằng chứng);
  thêm `repair_diagnostics` bounded vào trace cho lượt sau; giữ quota;
  test malformed → unresolved + đếm attempts.
- B3: sau B1 mới đánh giá; không framework anchors trong task này.
- B4: NOT_DONE — per-request AsyncClient, lợi ích ~1s/70s không xứng loop-leak risk.

## Gates (regression 1-10 trong task) + E (deterministic → 1 TC25 + 1 TC01 LIVE → browser trên DB có sẵn).

## Gate status (17/10 — acceptance `docs/final/reviews/2026-10-16-tc25-association-dispute-acceptance.md`)

- [x] A1–A5, B1, B2-diagnostics; deterministic + LIVE quota + browser read-only
- [ ] B3 wire-trim (chờ thêm số liệu), B4 (NOT_DONE có lý do), §12 rewrite

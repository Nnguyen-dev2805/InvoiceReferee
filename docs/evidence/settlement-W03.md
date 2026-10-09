# W03 — Mistral/xkiro reader và pipeline có budget

Ngày 09/10/2026. Lát cắt reader của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W03).
Trạng thái: **VERIFIED** với transport mock (không network); **chưa có kết luận
nào về chất lượng live OCR/LLM** — M0 probe live chưa chạy (cần authorization).

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED với mock)

- `settlement/reader.py`: Reader protocol + `StructuredLedgerReader` (fake,
  mode FAKE_OR_REPLAY) + `SettlementReader` (mode LIVE) + `MistralOCRClient`
  + `XkiroClient`. Reader chỉ trả observations/relations; không report/approval.
- Budget (S5): `RunBudget.reserve_call()` chặn vượt call cap và deadline với
  code `BUDGET_EXHAUSTED` — là lỗi kỹ thuật của run, không bị ghi là "nguồn
  không đọc được"; call timeout bị cap bởi deadline còn lại.
- Mistral OCR: request `/ocr`; response validated (pages list, index int duy
  nhất, markdown str); **index 0 của provider map sang page 1 hiển thị**;
  duplicate index → `PROVIDER_OUTPUT_INVALID`.
- xkiro: request chứa **full model id** (`mistralai/mistral-small-2603`),
  `reasoning_effort: "none"`, `response_format json_object`, temperature 0;
  requested model và response model ghi **riêng** trong trace (response model
  không chứng minh upstream); usage thiếu → **None, không fake 0**.
- Validator output: JSON sai retry đúng 1 lần/extraction unit; sai 2 lần →
  `PROVIDER_OUTPUT_INVALID` (technical); `finish_reason != stop` →
  `PROVIDER_OUTPUT_TRUNCATED` (không dùng JSON cắt); timeout/transport →
  `PROVIDER_FAILED`; tiền về dạng chuỗi → **UNCLEAR giữ raw, không tự quy
  đổi**; key yêu cầu bị bỏ khỏi output → UNCLEAR "không có trong output",
  **không tự NOT_FOUND**.
- Direct parse không tốn provider call: structured ledger text, **CSV ledger
  theo hợp đồng S8** (map phía theo event_kind v0, raw giữ nguyên), PDF native
  text (pypdfium2, lock tuần tự toàn process); ảnh > 24MP →
  `REPRESENTATION_LIMIT` trước khi OCR; PDF > 20 trang/file, > 40 trang
  PDF/ảnh/run → limit error, không truncate rồi báo đủ.
- Pipeline: lỗi kỹ thuật **theo từng nguồn** giữ partial output (TECHNICAL
  issue → INCOMPLETE), lỗi run (budget/Stop/stale) dừng cả run; checkpoint
  stage được persist; **call trace persisted** trên run (stage/source/model/
  usage/latency); match nhận toàn bộ candidates (không fixed top-k), relation
  hallucination ref → lọc và ghi trace `UNKNOWN_REF_FILTERED`, không drop âm
  thầm.
- Composition: `SETTLEMENT_PROVIDER_MODE` (fake mặc định; live cần keys, thiếu
  key fail loudly `CONFIG_NOT_ACTIVE`, **không có live→fake fallback**); env
  cho base URL/model. `.env.example` cập nhật; deps pin: pypdfium2 4.30.0,
  Pillow 11.3.0 (pyproject + requirements.lock).
- UI: panel run hiển thị status/stage/mode; trace hiển thị từng call (nguồn,
  tokens/usage-None, lỗi); report giữ nguyên semantics W02.

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED | `pytest tests/settlement/test_readers.py -q` trước khi tạo module | ModuleNotFoundError (contract chưa tồn tại) |
| Readers (mock transport) | `rtk proxy .venv/bin/python -m pytest tests/settlement/test_readers.py -q` | **18 passed** (budget×2, page mapping, xkiro contract, usage None, invalid/truncated/timeout, money-string UNCLEAR, missing-key, CSV×2, ledger, match filter, 24MP) |
| Pipeline + service | `... -m pytest tests/settlement/test_pipeline.py -q` | **5 passed** (per-source failure giữ partial + TECHNICAL issue; budget dừng run; 4 stages; service persist stage+trace; mode fake tường minh) |
| Toàn bộ backend | `... -m pytest tests/ -q` | **483 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | 38 passed / ok / pass |
| pip | `.venv/bin/python -m pip check` | no broken requirements |
| UI thực tế | 2 servers thật trên **port 8010/5174** (không đụng app đang chạy 8000/5173) + Playwright | **3/3 bước pass**: upload ledger + CSV qua UI → run → panel hiển thị `stage: publishing` + mode FAKE_OR_REPLAY → fake mode không sinh provider calls (trace rỗng đúng thiết kế) → report Q01 COMPLETE 3.000.000 VND với nguồn CSV thêm vào không làm sai kết quả |

Lưu ý vận hành: trong lúc E2E phát hiện app đang chạy trên 8000/5173 (không
phải tiến trình của task này) — tôi không kill, dùng port phụ với
`API_PROXY_TARGET` (thêm 1 dòng dev knob trong `vite.config.ts`).

## M0 probe plan (chuẩn bị để review — CHƯA CHẠY, cần authorization)

Mục tiêu: kiểm account/model/output/ref thực tế với ngân sách chặt, trước khi
khẳng định bất kỳ chất lượng nào.

1. Cấu hình: `SETTLEMENT_PROVIDER_MODE=live` + `MISTRAL_API_KEY`/`XKIRO_API_KEY`
   (server-only, không log). Model: `mistral-ocr-latest` +
   `mistralai/mistral-small-2603` (reasoning_effort none).
2. Cases (tổng ≤ 6 provider calls, budget `max_calls=8`, deadline 240s):
   - 1 nguồn synthetic PNG nhỏ (hóa đơn giả lập rõ số) → OCR → extract →
     xác nhận page mapping, quote, usage, response model.
   - 1 nguồn có số bị che (unclear-by-design) → phải ra UNCLEAR/None, không
     đoán.
   - 1 vision control: ảnh không phải chứng từ (ví dụ đoạn văn xuôi) →
     extractor phải từ chối/trả về NOT_FOUND, không bịa fields.
3. Ghi nhận: per-call trace (requested/response model, usage, latency), kết
   quả từng field so với nhãn tự viết trước (không dùng engine làm oracle).
4. Không chạy nếu chưa được phép gọi live; kết quả lưu
   `data/settlement/evidence/m0/`, tóm tắt public-safe vào
   `docs/evidence/`.

## Acceptance mapping

- **SYS-02**: VERIFIED phần reader (duplicate fact/relation id, invalid
  read_state, truncated, ref filter trước aggregation) với mock.
- **SYS-04**: VERIFIED phần reader (UNCLEAR giữ null; missing key không
  NOT_FOUND) với mock.
- **SYS-15**: VERIFIED phần run (budget/deadline/page/pixel limits; lỗi
  kỹ thuật không bịa coverage).
- **SYS-05 (linking)**: VERIFIED với mock cho filter/validate; **chất lượng
  matching live chưa đo** (thuộc M1/M2 sau probe).

## Giới hạn còn lại

- Không cuộc gọi live nào đã thực hiện: mọi kết luận reader chỉ đúng với
  transport mock. M0 probe chưa chạy — cần authorization + keys.
- PDF scan → OCR route đã implement nhưng chưa có test mock end-to-end đầy
  đủ cho render path (unit đã cover page-limit/pixel-limit).
- Rerun reuse theo hash/config/representation (S4) chưa làm — hiện mỗi run
  đọc lại nguồn; sẽ tính ở W06 nếu evaluator cần.

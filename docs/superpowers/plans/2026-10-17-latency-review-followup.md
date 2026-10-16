# Plan: bổ sung sau review latency (17/10/2026) — không LIVE mới

Owned: `evidence/{telemetry,structured_output,kimi,xkiro}.py`,
`scripts/run_role_aware_live.py` (reporting only), tests, acceptance wording.
Không sửa pipeline/admission/policy DTO/workflow; concurrency ngoài scope.

1. Repair diagnostic có cấu trúc: `record_repair_diagnostic(stage, attempt,
   error_code, field_path, validation_category, summary)`; classifier từ
   message validator (shape/state/identity/value/page/alternatives/coverage/
   other); summary lọc quoted-spans + cap (validator `invalid assessment`
   bọc pydantic error có thể lộ OCR text). HTTP200+JSON đúng vẫn phải qua
   validate (đã vậy; thêm regression显式). Artifacts cũ thiếu diagnostic →
   UNKNOWN (giữ nguyên, đã ghi).
2. Effort wire: giữ top-level `reasoning_effort` (đúng semantics extra_body
   merge của OpenAI SDK; provider đã chấp nhận ở 2 lượt LIVE); test phủ định
   `extra_body` không xuất hiện; KHÔNG thêm max_tokens (cap 20k chars +
   truncation error hiện có đã đủ, nêu lý do).
3. Usage: `_trace_usage` giữ `reasoning_tokens`/`cached_tokens` top-level +
   nested details flatten có namespace, thiếu = absent (UNKNOWN), không cộng
   dồn; runner surface null=UNKNOWN; duration chỉ là request elapsed
   (không TTFT/model-pure/CPU-gap); bỏ mọi câu chữ tiết kiệm suy ra.
4. Compact semantics regression (không đổi behavior): omitted→profile-missing,
   UNREADABLE giữ, AMBIGUOUS 2 alternatives giữ, truncated→unresolved,
   NOT_PRESENT thật được nhận.
5. Concurrency: chỉ ghi đề xuất tiếp theo trong report.

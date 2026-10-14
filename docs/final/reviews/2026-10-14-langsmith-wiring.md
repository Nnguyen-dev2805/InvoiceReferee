# LangSmith — kiểm kết nối và coverage của workflow

14/10/2026. HEADa98b7f2f, working tree có thay đổi questions UI. Read-only review;
không sửa application/config/DB, không gọi OCR/LLM, không gửi trace thử lên cloud.

**Verdict: có cấu hình/adapter và kết nối đọc cloud; M0 đã có traces. Workflow web
OCR→facts→finance→human response→actual money chưa được instrument tới LangSmith.**

## Bằng chứng cấu hình và cloud

- Settings: langsmith_tracing=True, api_key_configured=True, langsmith_ready=True.
- SDK installed0.14.8, endpointapi.smith.langchain.com, projectinvoice-referee.
- Read project thật thành công qua SDK, no remote write; run_count54.
-5run gần nhất được đọc metadata tối thiểu: m0:non_document, m0:unclear_scan,
  m0:clear_scan, m0:text và một m0:non_document cũ hơn; tất cả run_typechain,
  không parent. Đây là sample5run, không tuyên bố toàn54run đều cùng loại.
- Các sample có start_time=end_time. Adapter dùng now cho cả start/end khi caller
  không truyền thời điểm; không coi duration0 là đo latency provider đúng.
- Cloud read xác nhận kết nối/quyền đọc; không xác nhận một trace web mới đã upload
  hoặc permission write của key hiện tại. Không thay đổi credentials và không in key.
- Evidence `.runtime/langsmith-review-20261014-174737/remote-read.json`.

## Source wiring

CodeGraph up-to-date, earlier-engine warning; Codebase Memory coverage tool không
expose, coverage UNKNOWN. Đã đọc các material functions và scoped literal-search
toàn `src/invoice_referee/**/*.py` cho build_trace/TraceSpan/record/traceable/
tracing_context/RunTree/langsmith để xác nhận các callsites trong namespace này.
Không tuyên bố bao phủ external monkey patches/plugins không thuộc source chain.

| Phần | Thực tế |
|---|---|
| evidence/trace.py | LocalTrace/LangSmithTrace, client.create_run + update_run, build_trace có sẵn |
| CLI m0 và m0_live | instantiate adapter + record một span theo technical input |
| runtime._wire_live | chỉ tạo XkiroClient, FileOcrReader, ArtifactStore; không tạo/truyền trace sink |
| evidence.pipeline.read_root | không trace parameter/decorator/record quanh OCR/classify/extract/validate/match |
| XkiroClient.complete_json | raw httpx request, không LangSmith instrumentation hoặc per-call run |
| CaseWorkflow command/assessment/answer/actual/control | không call trace adapter trong checked chain |
| Reconciler/issue generation | không có LangSmith spans trong checked source |
| evaluate CLI/Verify | không instrument end-to-end workflow; không đánh đồng m0 traces với eval/business traces |

Các LangSmith callsites ghi run trong app namespace chỉ xuất hiện ở M0 utility
paths. Adapter hiện tạo flat chain runs; không parent_run_id/child span topology.
Không chỉ bật LANGSMITH_TRACING là tự quan sát raw-httpx và rule workflow.

## Runtime và kiểm chứng

- GET127.0.0.1:8000/api/health:200, modeLIVE, langsmith_ready=true.
- Hai case đang trả về từ web có evidence_report.trace_refs=[]. Không tự suy ra
  mọi trace trên cloud đều không tồn tại chỉ từ refs empty; kết luận dựa thêm
  runtime composition/source callsites.
- `rtk proxy uv run --no-sync pytest tests/unit/test_langsmith_trace.py -q -p no:cacheprovider`:
  exit0,8passed. Tests kiểm adapter/FakeClient/filtering/config, không business
  pipeline tracing acceptance.
- Code/AST discovery + scoped raw search, readproject/list5runs metadata:
  thực hiện thành công; no fake trace/new provider call.

## Giới hạn và bước cần làm nếu được yêu cầu

Chưa có trace toàn bộ một lần xử lý hồ sơ để xem:
OCR từngtệp, confidence gate, classify/extract, validation/matching,
admission/history, policy/finance, issue creation, persistence và human recovery.
Các stages.jsonl mình tạo khi debug là log riêng, không LangSmith export.

Cần nối trace sink tại composition root và instrument các operation/job thực,
root/child IDs riêng, cùng correlation case/job/command/basis/revision. Không giữ
một root span mở vô thời hạn qua toàn bộ vòng đời nhiều ngày của hồ sơ; phân tách
operation traces và liên kết bằng metadata. Capture errors/time/model/usage khi
có, dữ liệu nhạy cảm được kiểm soát; không invent metrics/cost0.

Tracing failure không thay đổi business decision, nhưng cần có diagnostics/local
fallback để tránh silent missing telemetry. Đóng gate bằng một workflow thật và
đọc lại trace cloud có các spans tương ứng; không chỉ8adapter tests PASS.

Không application fix, DB reset, commit/push hoặc automation/subagent trong review này.

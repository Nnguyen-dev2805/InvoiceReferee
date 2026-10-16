# InvoiceReferee Verify Dataset (Development Evaluation Set)

Bộ dữ liệu kiểm thử phát triển gồm 5 kịch bản đã được khóa cứng:
- **TC01**: Quy trình hoàn ứng thông thường (Routine), nhân viên hoàn trả 760.000 VND (`COLLECT 760000`), không phát sinh câu hỏi ngoại lệ.
- **TC02**: Quy trình thanh toán thêm thông thường (Routine), công ty thanh toán thêm 400.000 VND (`PAY 400000`), không phát sinh câu hỏi ngoại lệ.
- **VFY-BAL-01**: Kịch bản cân bằng tổng hợp (Synthetic Routine Balanced), chi phí 2.160.000 VND đúng bằng tiền tạm ứng 2.160.000 VND ($S = 0$), kết luận `BALANCED`, không tạo lệnh chuyển tiền.
- **TC06**: Kịch bản lỗi sự kiện số liệu (FACT), sai lệch 60.000 VND giữa số tính toán (830.000 VND) và số kê khai trên giấy (770.000 VND), chuyển nhân viên giải trình, chặn phát hành tiền.
- **TC04**: Kịch bản vượt hạn mức thẩm quyền (AUTHORITY), tổng chi 83.600.000 VND vượt hạn mức 20.000.000 VND của người phê duyệt, chuyển người quyết định có thẩm quyền cao hơn, chặn phát hành tiền.

## Các bộ kiểm thử
1. **Core4**: `[TC01, TC02, VFY-BAL-01, TC06]` (4 ca tuần tự)
2. **Escalation5**: `[TC01, TC02, VFY-BAL-01, TC06, TC04]` (5 ca: 3 routine + 2 human-required)

## Recording status
All current recording.json files are SYNTHETIC_FIXTURE: native PDF text plus handwritten extraction. They are retained for mechanism tests only. Public RECORDED_REPLAY must return NEEDS_RECORDING until compatible real provider captures exist. No LIVE provider evidence has been accepted. Word confidence is never synthesized.
Gold is manually specified, not a holdout or production certification. Human question quality: NOT_REVIEWED.

## Exact replay contract v2
`recordings/recording.json` for accepted replay requires `metadata.origin=LIVE_PROVIDER_CAPTURE`, capture timestamp, OCR/LLM provider+model, reasoning_effort, and reader_identity from current role_aware_reader_identity. `ocr` is keyed by exact PDF digest and keeps every page/block/word/null score. `calls` is keyed by SHA256 of canonical_request(system,user), storing that canonical request and response. Run-local source IDs are represented by `<SOURCE:sha256>`; storage paths by `<STORAGE:sha256>`; root IDs by `<ROOT>`. Replay registers aliases from the verified source bytes before each call and remaps only those aliases. Unmatched prompts, models/config or source inventory fail closed, never invoke LIVE. This is a capture interface, not proof that handwritten metadata is a real provider run. Real recordings require separate provenance review.
The runtime verifies all locked files in manifest.files; regenerating a PDF requires a deliberate dataset revision and new compatible capture. Existing synthetic captures stay unavailable in the public replay mode.

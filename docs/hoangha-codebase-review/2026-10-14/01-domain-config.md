# Review độc lập — 01 Domain & Config

Nguồn review: worktree Hoangha tại commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Phạm vi owner `01-domain-config` trong `inventory.json`: **11 file / 937 dòng**. Review chỉ đọc; không chạy test/build/LIVE và không sửa source.

CodeGraph được dùng ở mức Verify để xác định caller/callee và các symbol chính. Kết quả graph bị giới hạn theo truy vấn; `check_index_coverage`/generation-id không được exposed trong phiên parent nên coverage graph vẫn **UNKNOWN**. Các nhận định trọng yếu dưới đây được đối chiếu với source thật.

## Kết luận phạm vi

Nhóm này có ba lớp khác nhau:

- **Wired/runtime:** `config.py`, phần lớn `domain/settlement.py`, `domain/decisions.py` đang được FastAPI/runtime/application service sử dụng.
- **Shared contract nhưng mang lịch sử Hoangha:** `domain/processing.py` và một phần enum quyết định vẫn phục vụ cả pipeline cũ lẫn pipeline settlement mới.
- **Legacy input contract:** `domain/submission.py` là contract của luồng claim/email-like + primary/supporting document cũ, không phải contract cuối của hồ sơ settlement theo thiết kế final.

Khối domain có nhiều DTO dùng lại được, nhưng **không nên copy nguyên khối sang final**. Final cần adapter/mapping rõ giữa DTO Hoangha và contract đã chốt, đặc biệt ở decision vocabulary, currency/employee defaults, và ranh giới evidence → finance.

## Từng file

| File | Dòng | Vai trò | Input → Output | Hàm/lớp chính; caller/callee | Hành vi lỗi | Khả năng dùng lại |
| --- | ---: | --- | --- | --- | --- | --- |
| `.env.example` | 20 | Mẫu cấu hình runtime | env vars → cấu hình provider/OCR/company/data | được `AppSettings` và composition roots đọc gián tiếp | thiếu key/provider được xử lý ở adapter/composition root; file tự nó không validate | **Một phần**; giữ biến OCR/company/data, rà lại Kimi endpoint/flag legacy |
| `.gitignore` | 16 | Bỏ qua credential/runtime artifacts | path patterns → Git ignore | n/a | n/a | **Có**; phù hợp giữ DB/submission/.env ngoài Git |
| `pyproject.toml` | 29 | Package/runtime dependency contract | metadata → installer/test discovery | setuptools, pytest config | resolver sẽ fail nếu dependency không cài được | **Có**, nhưng chưa bao phủ dependency của generator/QA ở owner 09 |
| `src/invoice_referee/__init__.py` | 3 | Package metadata | n/a → `__version__` | package import | không có | **Có**, trung tính |
| `src/invoice_referee/config.py` | 53 | Runtime settings | environment + project root → `AppSettings` | `AppSettings.from_environment`; caller: FastAPI, Streamlit, web runtime | threshold ngoài `(0,1]` → `ValueError` | **Có**, sau khi final chốt tên env/default |
| `src/invoice_referee/domain/__init__.py` | 125 | Public re-export surface | internal domain symbols → package API | re-export decisions/processing/submission/settlement | import fail nếu module con lỗi | **Có chọn lọc**; không kéo legacy symbols chỉ vì đang export |
| `src/invoice_referee/domain/decisions.py` | 52 | Decision/finding contract | rule result → decision + target + question + source refs | `AutomationDecision`, `SettlementFinding`, `SettlementDecision` | Pydantic validate enum/shape | **Có adapter**; vocabulary rộng hơn final |
| `src/invoice_referee/domain/errors.py` | 9 | Lỗi validation đầu vào | list issue → exception message | `SubmissionValidationError` | join toàn bộ issue thành message | **Có**, nhỏ và rõ |
| `src/invoice_referee/domain/processing.py` | 224 | DTO cho OCR/LLM/legacy analysis | extracted/LLM/rule facts → analysis/result DTOs | `RuleFinding`, `BlockAssessment`, `ConfidenceAnalysis`, `EvidenceQualityResult`, inventory/conflict DTOs | chủ yếu Pydantic validation/default empty lists | **Một phần**; hữu ích cho evidence layer, nhưng không dùng `ProcessingDecision.PASS` như finance approval |
| `src/invoice_referee/domain/settlement.py` | 339 | Domain contract chính của Hoangha settlement | employee/business/item/upload/extracted facts → `SettlementDraft`, receipt/facts | caller: submit/process/web/storage/policy | Pydantic validation; upload hash/size deterministic | **Cao nhưng cần siết contract** |
| `src/invoice_referee/domain/submission.py` | 67 | Contract luồng submit cũ | claim + upload → persisted evidence/receipt | legacy `SubmitCaseService`/Streamlit | Pydantic + hash/size; không mang semantics settlement mới | **Thấp cho final**, chỉ tham khảo upload metadata |

<!-- reviewed-file: .env.example -->
<!-- reviewed-file: .gitignore -->
<!-- reviewed-file: pyproject.toml -->
<!-- reviewed-file: src/invoice_referee/__init__.py -->
<!-- reviewed-file: src/invoice_referee/config.py -->
<!-- reviewed-file: src/invoice_referee/domain/__init__.py -->
<!-- reviewed-file: src/invoice_referee/domain/decisions.py -->
<!-- reviewed-file: src/invoice_referee/domain/errors.py -->
<!-- reviewed-file: src/invoice_referee/domain/processing.py -->
<!-- reviewed-file: src/invoice_referee/domain/settlement.py -->
<!-- reviewed-file: src/invoice_referee/domain/submission.py -->

## Luồng contract thật

### 1. Runtime config

`AppSettings.from_environment(project_root)` resolve `INVOICE_REFEREE_DATA_DIR`, parse `OCR_WORD_REVIEW_THRESHOLD`, đọc legal name và danh sách MST công ty rồi trả settings immutable. Threshold mặc định là **0.85** và bị reject nếu ngoài `(0,1]` (`config.py:31-53`). Các property tạo đường dẫn submissions, SQLite và settlement artifacts (`config.py:18-28`).

`.env.example` khai báo Kimi, Mistral, OCR threshold, data root, company identity và flag `UC03_DOCUMENT_PIPELINE_ENABLED=1` (`.env.example:1-20`). Đây là **cấu hình mẫu**, không phải bằng chứng provider/LIVE đã hoạt động.

### 2. Domain decision

`AutomationDecision` chứa cả `READY_FOR_APPROVAL`, `AUTO_PROCESS`, `REQUEST_INFO`, `ACCOUNTANT_REVIEW`, `ESCALATE`, `RECOMMEND_REJECT` (`domain/decisions.py:10-16`). `SettlementDecision` gắn decision với uncertainty, target, câu hỏi, lý do và source refs (`45-52`).

Điểm tốt là source refs/question nằm ngay trong contract, phù hợp đề A cần giải thích và yêu cầu bổ sung cụ thể. Điểm cần adapter là final không nên suy rằng mọi label lịch sử có cùng authority. Ví dụ `AUTO_PROCESS` trong corpus v1 và `READY_FOR_APPROVAL` ở v2/Hoangha có semantics khác tầng workflow.

### 3. Settlement draft và tiền

`EmployeeProfile` có default synthetic `EMP-DEMO-001 / Nguyễn Minh An` (`domain/settlement.py:136-141`). `SettlementDraft.claimed_total` cộng trực tiếp `claimed_amount` của tất cả item (`220-225`). Source có normalize currency string thành uppercase nhưng không thấy validator đảm bảo mọi item/draft cùng currency trước phép cộng (`206-225`).

**Ví dụ minh họa, không phải testcase đã chạy:** nếu một draft chứa 100 USD và 2.000.000 VND, `claimed_total` về mặt số học vẫn cộng hai Decimal. Vì vậy final cần enforce single-currency hoặc conversion contract trước khi dùng tổng này cho quyết định tiền.

### 4. Processing DTO

`domain/processing.py` giữ hai lớp semantics:

- `ProcessingDecision = PASS | NEEDS_HUMAN` (`11-14`) cho pipeline legacy.
- DTO giàu source/evidence như `RuleFinding`, `ConfidenceAnalysis`, `EvidenceQualityResult`, `ConflictAnalysis` cho inspection/extraction.

Do đó file này hữu ích để tái sử dụng **evidence representation**, nhưng không nên để `PASS` legacy chảy thẳng thành trạng thái tài chính của final.

## Ai quyết định gì

| Chủ thể | Trong scope này |
| --- | --- |
| Model | Không có model invocation ở owner 01; DTO chỉ chứa chỗ để nhận kết quả model/analysis. |
| Code | Validate shape, enum, threshold, hash/size, defaults, tính tổng Decimal, chuẩn hóa currency string, encode decision contract. |
| Con người | Cung cấp env/company identity; ở tầng cao hơn sẽ xử lý `REQUEST_INFO/ACCOUNTANT_REVIEW/ESCALATE` và phê duyệt. |

## Findings

### F01 — MUST FIX trước khi dùng `SettlementDraft.claimed_total` làm số tiền quyết định

**Source-verified.**

- Trigger: draft có item khác currency.
- Hành vi hiện tại: `claimed_total` cộng mọi `claimed_amount` mà không kiểm currency (`domain/settlement.py:220-225`).
- Wrong behavior: một con số tổng có thể vô nghĩa về đơn vị nhưng vẫn hợp lệ kiểu dữ liệu.
- Tác động integration: final phải enforce một currency tại boundary hoặc đưa conversion contract riêng; không tự đổi policy tỷ giá.

### F02 — SHOULD FIX: synthetic employee default có thể che thiếu dữ liệu thật

**Source-verified.**

- `EmployeeProfile` tự sinh employee ID/name/department/position nếu caller không cung cấp (`domain/settlement.py:136-141`).
- Với demo synthetic điều này tiện; với final production-like flow, missing employee identity nên là trạng thái rõ ràng thay vì biến thành Nguyễn Minh An.
- Adapter nên buộc caller final truyền employee hoặc đánh dấu unresolved.

### F03 — MUST MAP: decision vocabulary trộn nhiều thế hệ

**Source-verified.**

- `AutomationDecision` chứa cả `AUTO_PROCESS` và `READY_FOR_APPROVAL` (`domain/decisions.py:10-16`).
- `domain/processing.py` lại có `PASS/NEEDS_HUMAN` (`11-14`).
- Trigger: import DTO/label trực tiếp sang final.
- Wrong behavior: evaluator/UI có thể coi hai trạng thái cùng nghĩa, hoặc evidence PASS bị nâng thành financial approval.
- Cần một mapping layer explicit theo contract final; không đổi policy đã chốt.

### F04 — SHOULD FIX: `.env.example` lẫn config active và historical feature flag

**Source-verified.**

`UC03_DOCUMENT_PIPELINE_ENABLED=1` nằm cùng provider/company config (`.env.example:15-20`). Khi tích hợp final, giữ lại biến nào composition root thực sự đọc; flag lịch sử không nên tiếp tục tồn tại chỉ vì có trong mẫu.

## Tests/evidence đã có và chưa có

CodeGraph cho thấy `SettlementDraft` được phủ gián tiếp bởi `tests/unit/test_settlement_policy.py` và `tests/unit/test_sqlite_settlement_repository.py`; `AppSettings` có caller được test qua web/accounting view. Các test này có giá trị chứng minh DTO/validation/caller Hoangha.

Trong review này **không chạy test**. Vì vậy không claim branch hiện tại GREEN. Ngoài ra các test Hoangha không chứng minh:

- contract final đã map đầy đủ decision vocabulary;
- multi-currency bị chặn;
- synthetic defaults không lọt vào real submission;
- evidence-only stage không tự nâng thành quyết định tài chính.

## Nên mang sang final

1. Giữ `AppSettings` pattern, hashing/upload metadata, typed Pydantic DTO, source refs và uncertainty/target/question.
2. Dùng `SettlementDraft` như nguồn tham khảo DTO, nhưng thêm adapter final enforce employee identity, currency invariant và contract field requiredness.
3. Tách evidence/processing DTO khỏi financial decision DTO. `PASS`/quality result chỉ là bằng chứng trung gian.
4. Tạo mapping rõ cho label Hoangha → contract final/eval gold; không import nguyên enum lịch sử.

Giới hạn: không chạy runtime/test/LIVE; graph coverage UNKNOWN; các kết luận ở đây dựa trên source và caller/callee đã đọc, không phải benchmark hành vi.

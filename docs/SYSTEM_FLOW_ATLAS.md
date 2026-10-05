# InvoiceReferee — System Flow Atlas

> **Bản đồ tổng thể, không sao chép văn bản (Map, not a copy)**
> - Task: `T01 + T02 + T03 + T04 + T05 + T06 + T07 + T08` (Domain contracts, demo policy, test builders, numeric parsing, source resolution, quality usability, pure policy evaluators, inventory/arithmetic, authority, decision reducer, SQLite history, evidence artifacts, atomic request lifecycle, Mistral OCR, per-document Kimi, cross-source proposals, production pipeline & vertical slice, human action validation, closure & input revision, one-process executor, atomic action, Stop/Override & CaseService).
> - Package: `Work Package 01 — Core (hoàn thành) & Work Package 02 — Workflow (T06–T08 hoàn thành)`.
> - Accepted Revision: `1ff1af9` (`feat(T08): one-process executor, atomic action và Stop/Override` trên nhánh `rebuild`).
> - Status: `Living Page Updated` — **T01–T08 IMPLEMENTED & VERIFIED (342 unit & integration tests passing)**. Các task từ T09 đến T16 ở trạng thái kế hoạch (`PLANNED — not built`).
> - Updated At: `2026-10-05T10:55:00+07:00`.
> - Quy tắc: Atlas là **bản đồ điều hướng** (zoom-out), áp dụng các nguyên lý **ASD-STE100** (câu ngắn, một nghĩa, điều kiện trước hành động sau, triệt tiêu mơ hồ, bảo toàn dữ kiện kỹ thuật). Không sao chép văn xuôi từ các tài liệu đặc tả ([B1_PRODUCT_SPEC.md](specs/B1_PRODUCT_SPEC.md), [B1_RULEBOOK.md](specs/B1_RULEBOOK.md), [B1_SYSTEM_SPEC.md](specs/B1_SYSTEM_SPEC.md)) hay kế hoạch thực thi ([Master Plan](superpowers/plans/2026-10-04-invoice-referee.md)).

---

## 1. Sơ đồ tổng thể toàn hệ thống (Master End-to-End System Flow)

Sơ đồ thể hiện toàn bộ các thành phần của InvoiceReferee tính đến thời điểm hoàn thành **T01–T08** (hoàn tất toàn bộ tầng Workflow từ dịch vụ ứng dụng, luồng thực thi nền, đường ống đến lưu trữ và can thiệp của con người). 
- Các khối **nền xanh viền đậm** (`IMPLEMENTED`) là các module nghiệp vụ thuần túy, tầng lưu trữ, tầng trích xuất, tầng đường ống, bộ xác thực hành động con người và tầng dịch vụ ứng dụng đã hoàn thành và vượt qua 342 bài kiểm tra độc lập.
- Các khối **nền xám viền nét đứt** (`planned — not built`) đại diện cho tầng API FastAPI, giao diện Web React và bộ kiểm thử tự động Verify sẽ được nối dây ở các task tiếp theo (T09 – T16).

```mermaid
flowchart TD
    classDef implemented fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef planned fill:#f9f9f9,stroke:#9e9e9e,stroke-width:1px,stroke-dasharray: 5 5;

    subgraph UIClient["Giao diện người dùng (T10 — planned)"]
        UI["Web UI (React / Vite / TypeScript)"]
    end

    subgraph WebEndpoint["HTTP Endpoint (T09 — planned)"]
        APP["FastAPI app (invoice_referee.api.app:create_app)"]
    end

    subgraph AppService["Tầng dịch vụ ứng dụng & Điều phối (T06, T08 — IMPLEMENTED)"]
        SVC["CaseService (submit / start_run / act / stop)"]
        EXEC["RunExecutor (single-slot threading / Semaphore)"]
        PIPE["Pipeline (process / preflight)"]
    end

    subgraph DomainCore["Lõi dữ liệu & Cấu hình (T01 — IMPLEMENTED)"]
        MODELS["Domain Models (Pydantic strict, immutable records)"]
        CFG["Config & Policy (load_policy / activate_demo_policy / snapshot_hash)"]
    end

    subgraph NumericQualityCore["Lõi Số học & Chất lượng chứng từ (T02 — IMPLEMENTED)"]
        NUM["Numeric Parser (parse_candidates / normalize_quantity)"]
        QUAL["Quality Usability Deriver (derive_fact)"]
    end

    subgraph PolicyEvaluators["Lõi quy tắc nghiệp vụ & Quyết định (T03 — IMPLEMENTED)"]
        EXP["Expense Evaluator (document_checks / context_check)"]
        INV["Inventory Consistency Evaluator (arithmetic_checks / inventory_checks)"]
        DEC["Decision Reducer (evaluate / next_action)"]
    end

    subgraph ExtractionTier["Tầng trích xuất & OCR (T05 — IMPLEMENTED)"]
        MISTRAL["Mistral OCR Adapter (registry_from_ocr)"]
        KIMI["Kimi LLM Adapter (AnalyzeDocument / ProposeCrossSource)"]
        VAL["Contract Validator (validate_document)"]
    end

    subgraph StorageTier["Lưu trữ SQLite & File Artifacts (T04 — IMPLEMENTED)"]
        REPO["Repository (SQLite BEGIN IMMEDIATE, atomic payment requests)"]
        ART["Artifact Storage (safe_name atomic write)"]
    end

    subgraph HumanLoopTier["Can thiệp của con người (T07 — IMPLEMENTED)"]
        HUMAN["validate_human_action (SUPPLY / CONFIRM / APPROVE / OVERRIDE)"]
    end

    subgraph VerifyTier["Kiểm thử tự động Verify & Đo lường (T11 — planned)"]
        VERIFY["VerifyRunner (Core 4 / Escalation 5)"]
    end

    %% Áp dụng style class cho nodes
    class MODELS,CFG,NUM,QUAL,EXP,INV,DEC,REPO,ART,MISTRAL,KIMI,VAL,PIPE,HUMAN,SVC,EXEC implemented;
    class UI,APP,VERIFY planned;

    %% Tương tác luồng UI -> API -> Service (T09, T10 planned)
    UI -.->|"HTTP REST API"| APP
    APP -.->|"gọi application methods"| SVC

    %% Dịch vụ ứng dụng điều phối thực thi và đường ống (T08 IMPLEMENTED)
    SVC ==>|"1. kiểm soát một lượt chạy (acquire / submit)"| EXEC
    EXEC ==>|"2. thực thi đường ống ngầm (process)"| PIPE

    %% Pipeline điều phối các tầng trích xuất và quy tắc (T06 IMPLEMENTED)
    PIPE -.->|"1. đọc PolicyConfig trong snapshot (preflight)"| CFG
    PIPE ==>|"2. trích xuất OCR (ocr)"| MISTRAL
    MISTRAL ==>|"SourceRegistry (registry_from_ocr)"| PIPE
    PIPE ==>|"3. phân tích chứng từ (analyze)"| KIMI
    KIMI ==>|"kiểm tra hợp đồng (validate_document)"| VAL
    VAL ==>|"chuẩn hóa chất lượng (derive_fact)"| QUAL
    PIPE ==>|"tái chuẩn hóa ngưỡng active (derive_fact)"| QUAL
    PIPE ==>|"4. đánh giá quy tắc (evaluate)"| DEC

    %% Tương tác nội bộ đã IMPLEMENTED giữa các evaluator và lưu trữ
    DEC ==>|"gọi document checks"| EXP
    DEC ==>|"gọi arithmetic & inventory checks"| INV
    DEC ==>|"xác thực total của primary bill"| QUAL
    EXP ==>|"xác thực derived quality"| QUAL
    INV ==>|"xác thực derived quality"| QUAL
    INV ==>|"tính toán Decimal 50"| NUM
    REPO ==>|"ghi tệp đính kèm an toàn (put_artifact)"| ART

    %% Dịch vụ ghi nhận kết quả, lưu trữ và xác thực con người (T08 IMPLEMENTED)
    SVC ==>|"ghi artifact lượt chạy (artifact_writer / put_artifact)"| ART
    SVC ==>|"xác thực thẩm quyền (validate_human_action)"| HUMAN
    SVC ==>|"tạo hồ sơ, phiên chạy & áp dụng hành động"| REPO
    EXEC ==>|"hoàn tất lượt chạy (finalize_run)"| REPO
    VERIFY -.->|"Chạy suite kiểm thử"| SVC
```

```text
revision: 1ff1af9
- MODELS → src/invoice_referee/domain/models.py (T01 - IMPLEMENTED)
- CFG → src/invoice_referee/config.py (T01 - IMPLEMENTED)
- NUM → src/invoice_referee/policy/numeric.py:parse_candidates,normalize_quantity (T02 - IMPLEMENTED)
- QUAL → src/invoice_referee/policy/quality.py:derive_fact (T02 - IMPLEMENTED)
- EXP → src/invoice_referee/policy/expenses.py:document_checks,context_check (T03 - IMPLEMENTED)
- INV → src/invoice_referee/policy/inventory.py:arithmetic_checks,inventory_checks (T03 - IMPLEMENTED)
- DEC → src/invoice_referee/policy/decision.py:evaluate (T03 - IMPLEMENTED)
- REPO → src/invoice_referee/storage/repository.py:Repository (T04, T07, T08 - IMPLEMENTED)
- ART → src/invoice_referee/storage/artifacts.py:put_artifact,safe_name (T04 - IMPLEMENTED)
- MISTRAL → src/invoice_referee/extraction/providers.py:Providers.ocr,registry_from_ocr (T05 - IMPLEMENTED)
- KIMI → src/invoice_referee/extraction/providers.py:Providers.analyze,Providers.cross_source (T05 - IMPLEMENTED)
- VAL → src/invoice_referee/extraction/validation.py:validate_document,is_applicable (T05 - IMPLEMENTED)
- PIPE → src/invoice_referee/application/pipeline.py:process,preflight (T06 - IMPLEMENTED)
- HUMAN → src/invoice_referee/application/human.py:validate_human_action,authorization_matches (T07 - IMPLEMENTED)
- SVC → src/invoice_referee/application/service.py:CaseService (T08 - IMPLEMENTED)
- EXEC → src/invoice_referee/application/executor.py:RunExecutor (T08 - IMPLEMENTED)
- APP → src/invoice_referee/api/app.py:create_app (T09 - planned — not built)
- UI → frontend/src/App.tsx (T10 - planned — not built)
- VERIFY → src/invoice_referee/verify/runner.py:VerifyRunner (T11 - planned — not built)
edges: 
- Mũi tên đôi đậm (==>): Các lệnh gọi trực tiếp giữa các module nghiệp vụ thuần túy, tầng lưu trữ, tầng trích xuất, tầng đường ống và tầng dịch vụ điều phối T01–T08 đã được IMPLEMENTED và VERIFIED bằng 342 bài kiểm tra (SVC điều phối EXEC, HUMAN, REPO và ART; EXEC chạy PIPE ngầm và gọi REPO.finalize_run; PIPE gọi MISTRAL, KIMI, QUAL và DEC; DEC gọi EXP, INV, QUAL; EXP và INV gọi QUAL; INV dùng NUM; REPO gọi ART; KIMI gọi VAL; VAL gọi QUAL).
- Mũi tên nét đứt (-.->): Luồng tương tác kiến trúc dự kiến khi nối dây từ UI và API tới Service (T09, T10), hoặc kiểm thử Verify (T11), và phụ thuộc dữ liệu tĩnh như PIPE đọc cấu hình chính sách từ snapshot.
```

---

## 2. Mục lục các luồng cốt lõi (Core-Flow Index)

*Tuân thủ quy tắc ASD-STE100: Câu ngắn dưới 25 từ, một thông tin kỹ thuật mỗi câu, ưu tiên thể chủ động, nêu điều kiện trước hành động.*

### 2.1 Hợp đồng dữ liệu & Cấu hình chính sách (Domain Contracts & Demo Policy — T01)
- Hệ thống định nghĩa toàn bộ dữ liệu bằng các bản ghi Pydantic v2 bất biến (`Record`).
- Mọi bản ghi cấm nhận trường thừa (`extra='forbid'`) và không cho phép thay đổi (`frozen=True`).
- Hàm `snapshot_hash` tính toán mã băm SHA-256 xác định cho từng trạng thái hồ sơ.
- Cấu hình `PolicyConfig` tải từ file bắt đầu ở trạng thái chưa kích hoạt (`active=False`).
- Chỉ hàm `activate_demo_policy` mới chuyển trạng thái cấu hình sang kích hoạt với lý do rõ ràng.
- Chi tiết: [models.py](../src/invoice_referee/domain/models.py), [config.py](../src/invoice_referee/config.py), [task-T01.md](evidence/task-T01.md).

### 2.2 Phân tích số học & Chuẩn hóa đơn vị (Numeric Parsing & Unit Normalization — T02)
- Hàm `parse_candidates` phân tích văn bản số bằng ba ngữ pháp: `CANONICAL`, `VI`, `US`.
- Nếu chuỗi số mang nghĩa mơ hồ như `'1.234'`, hàm trả về toàn bộ ứng viên khả dĩ.
- Hệ thống không tự ý chọn một giá trị duy nhất khi chưa có căn cứ ngữ cảnh.
- Hàm `normalize_quantity` quy đổi các đơn vị g, kg, tấn về đơn vị gam cơ sở.
- Phép tính số học luôn chạy trong ngữ cảnh `Decimal` 50 chữ số độc lập (`prec=50`).
- Hệ thống cấm số lượng nhỏ hơn hoặc bằng 0.
- Số tiền tối đa 15 chữ số nguyên.
- Số lượng và đơn giá tối đa 12 chữ số nguyên và 6 chữ số thập phân.
- Chi tiết: [numeric.py](../src/invoice_referee/policy/numeric.py), [task-T02.md](evidence/task-T02.md).

### 2.3 Xác thực nguồn gốc & Chất lượng chứng từ (Source Resolution & Derived Usability — T02)
- Hàm thuần `derive_fact` đối chiếu tọa độ `SourceRef` với `SourceRegistry` thực tế của chứng từ.
- Hàm trả về một đối tượng `FieldFact` mới với trạng thái chất lượng (`usability`) tương ứng.
- Nếu trường số thiếu điểm tin cậy hoặc có bất kỳ từ cấu thành nào dưới ngưỡng tin cậy, trạng thái là `UNCERTAIN`.
- Ngưỡng tin cậy là tham số của hàm. Giá trị khởi điểm lấy từ cấu hình `word_review_threshold` (0.85).
- Nhãn "READABLE" từ mô hình ngôn ngữ không bao giờ được miễn trừ kiểm tra điểm tin cậy số học.
- Nếu tọa độ trỏ sai chứng từ hoặc khối không tồn tại, hàm ném lỗi `INVALID_ANALYSIS`.
- Kế toán xác nhận bằng `CONFIRM_FIELD` hợp lệ có thể chuyển trường thành `USABLE` mà không sửa OCR thô.
- Chi tiết: [quality.py](../src/invoice_referee/policy/quality.py), [task-T02.md](evidence/task-T02.md).

### 2.4 Đánh giá quy tắc chi phí & Rút gọn quyết định (Expense Policy & Decision Reducer — T03)
- Hàm thuần `evaluate` nhận `CaseSnapshot` và `EvidenceBundle` để tạo phán quyết `Decision`.
- Hệ thống kiểm tra đầy đủ ma trận 15 quy tắc nghiệp vụ theo [B1_RULEBOOK.md](specs/B1_RULEBOOK.md).
- Nếu cấu hình chính sách chưa kích hoạt, hàm trả về hành động kỹ thuật `NONE`.
- Nếu hồ sơ rơi vào quy định cấm rõ ràng (`MODE-01`, `ELIG-01`), hàm trả về `REJECT`.
- Nếu còn vướng mắc dữ kiện chưa rõ, hàm trả về `REQUEST_INFO`.
- Nếu có vướng mắc dữ kiện, hệ thống tạo câu hỏi cụ thể gửi tới đúng người chịu trách nhiệm.
- Nếu không còn vướng mắc dữ kiện và chi phí vượt thẩm quyền, hàm trả về `ESCALATE`.
- Nếu mọi quy tắc đạt và đủ thẩm quyền phê duyệt, hàm trả về `CREATE_PAYMENT_REQUEST`.
- Chi phí hợp lệ từ 2.000.000đ trở xuống được hệ thống tự động hoàn tất (`ROUTINE_AUTO`).
- Chi phí trên 2.000.000đ và tối đa 5.000.000đ yêu cầu người phê duyệt (`APPROVER`) cấp quyền.
- Chi phí trên 5.000.000đ kích hoạt đồng thời vi phạm chính sách `LIM-01` và vượt thẩm quyền `AUTH-01`.
- Kiểm kê (`INV-01`, `INV-02`) chỉ áp dụng cho hồ sơ mua sắm vật tư (`WORK_PURCHASE`).
- Chi tiết: [decision.py](../src/invoice_referee/policy/decision.py), [expenses.py](../src/invoice_referee/policy/expenses.py), [inventory.py](../src/invoice_referee/policy/inventory.py), [task-T03.md](evidence/task-T03.md).

### 2.5 Lưu trữ SQLite có bảo vệ & Vòng đời đề nghị chi trả (Storage & Atomic Lifecycle — T04)
- Lớp `Repository` quản lý lưu trữ SQLite với một kết nối độc lập cho mỗi giao dịch.
- Mọi kết nối SQLite đều kích hoạt kiểm tra ràng buộc khóa ngoại (`PRAGMA foreign_keys = ON`).
- Mọi giao dịch ghi mở bằng lệnh `BEGIN IMMEDIATE`.
- Lệnh này tuần tự hóa các tác vụ ghi để tránh ghi đè dữ liệu.
- Chỉ mục một phần `one_current_payment_request` bảo đảm mỗi hồ sơ có tối đa một đề nghị chi trả trạng thái `CREATED`.
- Hệ thống lưu giữ toàn bộ đề nghị chi trả bị thay thế hoặc thu hồi để giải thích thao tác ghi đè.
- Hàm `finalize_run` thực thi nguyên tử trong một giao dịch duy nhất.
- Hàm mang tính idempotent: gọi lại nhiều lần không tạo kết quả trùng lặp.
- Nếu gọi lại `finalize_run` trên một lượt chạy đã kết thúc, hàm trả về bản ghi cũ và bỏ qua kết quả mới.
- Nếu người vận hành yêu cầu dừng trước khi hoàn tất, hàm `finalize_run` ghi nhận trạng thái `STOPPED` và không tạo đề nghị chi trả.
- Nếu lượt chạy đã lưu kết quả cuối cùng, hàm `request_stop` trả về trạng thái `ALREADY_COMPLETED` và bảo toàn kết quả.
- Nếu hành động con người thay đổi dữ liệu đầu vào, hệ thống tăng `case_version` và tự động thu hồi đề nghị chi trả hiện hành.
- Hàm `put_artifact` ghi tệp nguyên tử bằng tệp tạm, đồng bộ đĩa qua `fsync` và thay thế qua `os.replace`.
- Hàm `safe_name` từ chối mọi tên tệp chứa dấu phân cách đường dẫn hoặc nguy cơ chuyển hướng thư mục.
- Khi ứng dụng khởi động lại, hàm `mark_interrupted_runs` kiểm tra các lượt chạy chưa kết thúc.
- Nếu lượt chạy đã nhận yêu cầu dừng, hàm kết thúc lượt chạy ở trạng thái `STOPPED`.
- Nếu lượt chạy đang xử lý dở dang, hàm chuyển trạng thái sang `FAILED`.
- Hệ thống không tự động chạy lại bất kỳ lượt chạy nào bị gián đoạn.
- Chi tiết: [repository.py](../src/invoice_referee/storage/repository.py), [artifacts.py](../src/invoice_referee/storage/artifacts.py), [schema.sql](../src/invoice_referee/storage/schema.sql), [task-T04.md](evidence/task-T04.md).

### 2.6 Tầng chuyển đổi OCR & Phân tích văn bản (Provider Adapters — T05)
- Bộ điều hợp `Providers` cung cấp ba giao diện: `ocr`, `analyze`, và `cross_source`.
- Lớp `LiveProviders` gọi trực tiếp API Mistral OCR và API Kimi LLM qua thư viện `httpx`.
- Mọi lệnh gọi API ngoài đặt thời gian chờ mặc định 60 giây.
- Thư viện `httpx` không tự thử lại khi lỗi truyền thông.
- Nếu thiếu khóa API trong cấu hình, hệ thống ném lỗi `CONFIG_NOT_ACTIVE`.
- Hàm `registry_from_ocr` trích xuất điểm tin cậy từng từ (`word_confidence_scores`) trực tiếp từ Mistral OCR.
- Nếu chứng từ thiếu điểm tin cậy từng từ, hệ thống giữ giá trị `None` thay vì tự tạo điểm số.
- Hàm `analysis_payload` chỉ gửi dữ liệu chứng từ cần thiết và không bao giờ gửi văn bản của nhân viên.
- Hệ thống giới hạn một lần sửa lỗi chung (`REPAIR_BUDGET = 1`) cho mỗi lượt gọi phân tích chứng từ.
- Nếu mô hình phản hồi sai cấu trúc lần thứ hai, hệ thống dừng lại với lỗi `INVALID_ANALYSIS`.
- Lượt gọi đề xuất đối chiếu chéo được cấp thêm một lần sửa lỗi trước khi báo lỗi kỹ thuật.
- Nếu chứng từ vi phạm quyền sở hữu hoặc trùng lặp mã dòng hàng, hàm `validate_document` ném lỗi `INVALID_ANALYSIS`.
- Nếu OCR phát hiện bảng biểu, hồ sơ khai báo mẫu `TOTAL_ONLY` bị từ chối để chống bỏ qua chi tiết.
- Mã nguồn quyết định tính áp dụng của các phép kiểm tra (`is_applicable`) thay vì dựa vào mô hình.
- Nếu quan sát chất lượng ghi nhận không đọc được nhưng tuyên bố không cần xác minh, hàm `validate_document` ném lỗi `INVALID_ANALYSIS`.
- Hàm `validate_document` tính toán lại chất lượng dữ kiện bằng hàm thuần `derive_fact` thay vì tin tưởng mô hình.
- Chi tiết: [providers.py](../src/invoice_referee/extraction/providers.py), [validation.py](../src/invoice_referee/extraction/validation.py), [task-T05.md](evidence/task-T05.md), [provider-contract.md](evidence/provider-contract.md).

### 2.7 Quy trình xử lý hồ sơ toàn trình (Application Pipeline — T06)
- Hàm `process` điều phối quy trình xử lý toàn trình từ kiểm tra sơ bộ đến đánh giá quyết định.
- Hàm `preflight` xử lý sớm các trường hợp không cần gọi bộ điều hợp ngoài.
- Nếu cấu hình chính sách chưa kích hoạt, hàm `preflight` trả về mã kỹ thuật `CONFIG_NOT_ACTIVE`.
- Nếu người dùng khai báo chi cá nhân hoặc công ty thanh toán, hệ thống trả về `REJECT` trước khi gọi bộ điều hợp ngoài.
- Nếu hồ sơ thiếu hóa đơn chính hoặc có nhiều hóa đơn chính, hệ thống trả về `REQUEST_INFO`.
- Quy trình đường ống không bao giờ tự tạo đề nghị chi trả hoặc ghi vào cơ sở dữ liệu.
- Điểm kiểm tra chốt chặn tiếp nhận tín hiệu dừng trước và sau mỗi lệnh gọi dịch vụ ngoài.
- Nếu người vận hành bấm dừng, ngoại lệ `StoppedRun` được lan truyền để chuyển trạng thái sang `STOPPED`.
- Hệ thống loại bỏ hoàn toàn kết quả muộn sau khi dừng và không áp dụng kết quả đó.
- Hệ thống tái chuẩn hóa chất lượng dữ kiện bằng ngưỡng tin cậy của chính sách đang kích hoạt.
- Mã nguồn quyết định tính áp dụng của các phép kiểm tra và ngăn chặn miễn trừ trái phép.
- Quy trình chỉ kích hoạt đối chiếu chéo khi hồ sơ thuộc nhóm mua sắm vật tư (`WORK_PURCHASE`).
- Hàm `process` trả về kết quả `PipelineResult` gồm phán quyết, chứng từ, thời gian và số lượt gọi.
- Chi tiết: [pipeline.py](../src/invoice_referee/application/pipeline.py), [test_pipeline.py](../tests/integration/test_pipeline.py), [task-T06.md](evidence/task-T06.md), [BUILD_LOG_V2.md](BUILD_LOG_V2.md).

### 2.8 Xác thực hành động con người & Sửa đổi dữ liệu (Human Action Validation & Revision — T07)
- Hàm `validate_human_action` kiểm tra thẩm quyền nghiệp vụ và cấu trúc gói tin của từng hành động.
- Hàm `validate_human_action` từ chối mọi khóa thừa trong gói tin.
- Hệ thống không hỗ trợ cờ phê duyệt toàn bộ (approve-all).
- Vai trò nhân viên (`EMPLOYEE`) chỉ được bổ sung lời khai, thêm chứng từ, đề xuất sửa hoặc từ chối vướng mắc do mình chịu trách nhiệm (`DENY`).
- Vai trò kiểm tra viên (`REVIEWER`) chỉ xác nhận các trường dữ kiện hoặc bảng ánh xạ thuộc sở hữu chứng từ.
- Thao tác xác nhận của kiểm tra viên tạo bản ghi dữ kiện mới và không chỉnh sửa văn bản OCR gốc.
- Giá trị xác nhận số học bắt buộc ở định dạng chuỗi số chuẩn tắc (`canonical string`).
- Vai trò người duyệt (`APPROVER`) chỉ được phê duyệt số tiền trong hạn mức chính sách chuẩn (`standard_policy_max`).
- Vai trò chủ chính sách (`POLICY_OWNER`) cấp ngoại lệ chính sách và phê duyệt số tiền vượt hạn mức chuẩn.
- Bản ghi ủy quyền gắn chặt với phiên bản hồ sơ, phiên bản chính sách, nhóm chi phí, mục đích và số tiền.
- Thao tác ghi đè `OVERRIDE` bảo toàn phán quyết gốc để phục vụ kiểm toán.
- Thao tác ghi đè kiểm tra tính hợp lệ của lệnh bên trong theo đúng vai trò.
- Thao tác ghi đè phân loại (`CLASSIFY_PROFILE`) chỉ cho phép chuyển đổi nhóm `OTHER` sang các nhóm chi phí hợp lệ.
- Hàm `apply_human_action` thực thi trong một giao dịch cơ sở dữ liệu duy nhất (`BEGIN IMMEDIATE`).
- Nếu hành động sửa đổi dữ liệu gốc, hệ thống tăng số hiệu phiên bản và thu hồi đề nghị chi trả hiện hành.
- Nếu người dùng gửi đề xuất sửa đổi (`PROPOSE_CORRECTION`), hệ thống không thay đổi mã băm của hồ sơ.
- Chi tiết: [human.py](../src/invoice_referee/application/human.py), [repository.py](../src/invoice_referee/storage/repository.py), [test_human_actions.py](../tests/unit/test_human_actions.py), [task-T07.md](evidence/task-T07.md), [BUILD_LOG_V2.md](BUILD_LOG_V2.md).

### 2.9 Dịch vụ phiên & Quản lý thực thi (CaseService & Stop — T08)
- `CaseService` sở hữu một bộ thực thi `RunExecutor` chạy trong một tiến trình duy nhất với một luồng worker (`ThreadPoolExecutor(max_workers=1)`).
- Khe thực thi sử dụng cờ báo tín hiệu đơn (`Semaphore(1)`) để cấm chạy đồng thời hai lượt xử lý.
- Nếu người dùng gọi chạy hoặc gửi hành động (trừ lệnh dừng) khi đang có lượt chạy, hệ thống trả về lỗi `RUN_BUSY`.
- Hàm `start_run` khởi tạo lượt chạy ngầm bất đồng bộ và trả về kết quả ngay lập tức.
- Luồng worker thực thi quy trình đường ống và hoàn tất bằng giao dịch chốt chặn `finalize_run`.
- Hàm `finalize_technical` kết thúc lượt chạy khi có lỗi kỹ thuật.
- Lệnh dừng `stop` được định tuyến trực tiếp qua hàm `request_stop` của kho lưu trữ.
- Trạng thái yêu cầu dừng `STOP_REQUESTED` được lưu bền vững vào cơ sở dữ liệu trước khi phản hồi.
- Giao dịch chốt chặn từ chối tạo đề nghị chi trả nếu lượt chạy đã ghi nhận tín hiệu dừng.
- Lệnh dừng lặp lại trả về phản hồi hợp lệ mà không gây lỗi hoặc thay đổi trạng thái.
- Nếu lượt chạy đã kết thúc trước khi dừng, hệ thống trả về mã `ALREADY_COMPLETED`.
- Hàm `act` xác thực thẩm quyền bằng `validate_human_action` rồi thực hiện kiểm tra tham chiếu sâu.
- Hàm `act` từ chối xác nhận trường dữ kiện nếu tham chiếu không tồn tại trong chứng từ gốc.
- Hàm `act` từ chối bảng ánh xạ dòng hàng nếu thiếu phủ một-một hoặc mơ hồ về đơn vị đo lường.
- Hàm `set_policy` chỉ thực thi khi bộ thực thi rảnh rỗi (`idle`).
- Tác nhân hệ thống (`SYSTEM`) trong hàm `set_policy` chỉ được phép thay đổi ngưỡng tin cậy từ ngữ cùng nhãn phiên bản `threshold_version` của nó.
- Toàn bộ các trường giới hạn tiền tệ và cấu hình chính sách được bảo vệ tuyệt đối trước tác nhân hệ thống.
- Chi tiết: [service.py](../src/invoice_referee/application/service.py), [executor.py](../src/invoice_referee/application/executor.py), [test_execution_controls.py](../tests/integration/test_execution_controls.py), [test_human_closure.py](../tests/integration/test_human_closure.py), [task-T08.md](evidence/task-T08.md), [BUILD_LOG_V2.md](BUILD_LOG_V2.md).

### 2.10 Giao diện Web & Điểm cuối API (FastAPI & React UI — T09, T10) — `planned`
- FastAPI cung cấp các điểm cuối REST API phục vụ vận hành hồ sơ và kiểm thử.
- Giao diện Web hỗ trợ chuyển đổi linh hoạt bốn vai trò trình diễn nghiệp vụ.
- Bảng điều khiển hiển thị đầy đủ chứng từ gốc, cảnh báo và nhật ký kiểm toán minh bạch.
- Chi tiết thiết kế: [Workflow Plan T09–T10](superpowers/plans/2026-10-04-invoice-referee-02-workflow.md#t09--fastapi-composition-và-contract-responses).

### 2.11 Bộ kiểm thử tự động Verify & Đóng băng Baseline B1 (Verify Harness — T11, T12) — `planned`
- Bộ công cụ Verify chạy trực tiếp trên đường dịch vụ chính của ứng dụng.
- Bộ công cụ Verify in bảng tổng hợp đạt/không đạt kèm dấu thời gian thực.
- Hai bộ kiểm thử chuẩn gồm Core 4 ca và Escalation 5 ca theo đúng thể lệ cuộc thi.
- Chi tiết thiết kế: [Evidence/Release Plan T11–T12](superpowers/plans/2026-10-04-invoice-referee-03-evidence-release.md#t11--corpus-có-gold-độc-lập-và-verify-qua-production-service).

---

## 3. Các luồng dự kiến — chưa xây dựng (Planned — not built)

Các module và tính năng dưới đây đã có thiết kế chi tiết nhưng **hoàn toàn chưa được xây dựng hoặc nối dây trong mã nguồn**:

1. **Giao diện Web & Điểm cuối API (`T09`, `T10`)** — `planned — not built`:
   - Các tệp dự kiến: `src/invoice_referee/api/app.py`, toàn bộ thư mục `frontend/`.
   - Trách nhiệm: REST API FastAPI và giao diện React phục vụ ban giám khảo thao tác trực tiếp.

2. **Bộ kiểm thử tự động Verify & Thích ứng ngưỡng (`T11` – `T16`)** — `planned — not built`:
   - Các tệp dự kiến: `src/invoice_referee/verify/`, `src/invoice_referee/adaptation/`, tài liệu chung kết.
   - Trách nhiệm: Tự động hóa đánh giá trên tập kiểm thử độc lập, học ngưỡng từ phản hồi người dùng.

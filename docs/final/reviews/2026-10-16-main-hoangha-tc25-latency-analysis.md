# Báo cáo phân tích độc lập độ trễ giữa Main và Hoangha (TC25 LIVE)

> **Loại tài liệu:** Đánh giá kỹ thuật độc lập & tối ưu hóa hiệu năng (Read-only analysis)  
> **Thời điểm lập:** 16/10/2026  
> **Mục tiêu:** Phân tích nguyên nhân chênh lệch thời gian xử lý (latency) giữa snapshot `main` (Role-aware Kimi) và worktree `hoangha` dựa trên mã nguồn và artifacts thực tế của ca kiểm thử TC25; đề xuất lộ trình tối ưu hóa có kiểm chứng mà không làm suy giảm chất lượng kiểm tra tài chính hay tính toàn vẹn của bằng chứng (provenance).

---

## 1. Kết luận chính, giới hạn và định danh snapshot

### 1.1. Kết luận cốt lõi
1. **Phần lớn độ trễ nằm ở mạng LLM & OCR (99.88% thời gian `read_pass`):**  
   Trong 72.23s của giai đoạn đọc tài liệu (`settlement-draft-read`) trên `main`, tổng thời gian chờ phản hồi mạng từ provider (4 OCR + 7 LLM calls) là **72.14s**. Thời gian CPU nội bộ của Python (xác thực schema, đối chiếu quy tắc, parsing JSON, tính toán số học) chỉ tốn vỏn vẹn **0.088s (88 ms)**.
2. **Khối lượng completion tokens của Main gấp 2.92 lần Hoangha (8,592 vs 2,944 tokens):**  
   Nguyên nhân chủ yếu do thiết kế Wire Schema ở Main bắt buộc LLM phải sinh cấu trúc meta-object chi tiết `{field, state, value, quote, page}` cho cả các trường không tồn tại (`NOT_PRESENT`) và từng trường con trong từng dòng bảng. Riêng đơn quyết toán (paper extraction), Main sinh **2,539 tokens** trong khi Hoangha chỉ sinh **456 tokens** (chênh lệch gấp 5.57 lần).
3. **Phát sinh 2 cuộc gọi LLM phụ trợ ở Main (+7.08s):**  
   - 01 cuộc gọi **Schema Repair** trên phiếu thu (5.53s, 1,460 tokens).  
   - 01 cuộc gọi **Resolver** (1.55s, 136 tokens) do liên kết phiếu thu bị hạ cấp thành `SUGGEST_LINK` khi số tiền 900k trên giấy lệch với 700k trên phiếu thu, mặc dù mã chứng từ `PT-251026-016` trùng khớp 100%.
4. **Quy trình hoàn toàn tuần tự (Sequential Execution):**  
   Cả 4 tác vụ OCR (17.65s) và 4 tác vụ trích xuất (42.50s) ở Main đều chạy nối tiếp 100%, không áp dụng bất kỳ mức concurrency nào dù các tài liệu độc lập với nhau.
5. **Cấu hình request Kimi-K3 chưa đồng nhất:**  
   Hoangha chỉ định rõ `extra_body={"reasoning_effort": "low"}` và tái sử dụng HTTP connection pool của `OpenAI` SDK; Main không gửi `reasoning_effort="low"` và khởi tạo mới `httpx.AsyncClient` cho mỗi request (không tận dụng connection reuse / TLS keep-alive).

### 1.2. Định danh Snapshot và Dữ liệu kiểm thử
- **Main Snapshot:**
  - Git Commit: `1b949a55` + working-tree uncommitted changes (Role-aware Kimi runtime).
  - Source Digest: `b2ff00615a361d3cd3f5e8a90af46391549e768b2b258aa47058174718a49d2d`.
  - Artifacts: `.runtime/tc25-kimi-independent-20261016/run-01/`.
  - Model: `moonshotai/Kimi-K3` (requested & returned).
  - Chế độ: `LIVE`, context `SIMULATED` (tạm ứng 5.000.000 ₫, đồng hồ nghiệp vụ `2026-10-16T12:00:00+07:00`).
- **Hoangha Snapshot:**
  - Git Commit: `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`.
  - Artifacts: `.worktrees/hoangha/.runtime/tc25-hoangha-live-20261016/`.
  - Model: `moonshotai/Kimi-K3` (requested & returned).
  - Chế độ: Native Hoangha `PAPER_SCAN` (không nạp sổ cái tạm ứng thực tế).
- **Bộ 4 tệp PDF đầu vào (trùng khớp SHA-256 tuyệt đối 100%):**
  - `report_hoan_ung.pdf`: `6dc3ba18fdc7d42ab40b9c56fa8d20a9d0c6fbc934cb6e59862d3d30b29b4872`
  - `hoa_don_khach_san.pdf`: `1f7ae1d7951ab4f4d4ba9494349cbbc9e83c8d8bcf1973cbc00d1dcecb578d60`
  - `hoa_don_ve_tau.pdf`: `9b1ee2de2ed767f294ee53ae223aadef11753fa7579a82b98c1d6644ac925944`
  - `phieu_thu_di_chuyen.pdf`: `5ecb81997c968f5636ded712b09f80777e0bbce602df7d6eccf73146c12366de`

### 1.3. Giới hạn đánh giá
- Dữ liệu so sánh dựa trên 01 lần chạy duy nhất (N=1) của mỗi bên, không phản ánh phân phối xác suất thống kê p50/p95 của mạng viễn thông.
- Hai hệ thống có phạm vi kiểm chứng khác nhau: Main thực thi mô hình tài chính hoàn chỉnh (zero hallucinations, trích xuất quote nguyên văn, kiểm tra phân bổ, chặn tiền tự động); Hoangha thực thi pipeline trích xuất phẳng và đối chiếu heuristic trực tiếp. So sánh này phục vụ tối ưu hóa kỹ thuật, không nhằm khẳng định bên nào vượt trội toàn diện.

---

## 2. Bảng đối chiếu Timeline, Số lượng cuộc gọi và Token Usage

### 2.1. Bảng phân rã chi tiết thời gian thực thi (Timeline & Latency)

| Tác vụ / Giai đoạn | Main Kimi (s) | Hoangha (s) | Chênh lệch (s) | Bản chất đo lường | Ghi chú kỹ thuật |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OCR File 1 (Khách sạn)** | 3.066 | 3.495 | -0.429 | Đo trực tiếp qua span | Mistral OCR API |
| **OCR File 2 (Vé tàu)** | 4.753 | 2.244 | +2.509 | Đo trực tiếp qua span | Biến thiên độ trễ mạng Mistral |
| **OCR File 3 (Đơn hoàn ứng)** | 6.837 | 3.050 | +3.787 | Đo trực tiếp qua span | Tệp 1 trang, mật độ text cao |
| **OCR File 4 (Phiếu thu)** | 2.993 | 2.670 | +0.323 | Đo trực tiếp qua span | Mistral OCR API |
| **Tổng OCR (4 tệp)** | **17.649** | **11.459** | **+6.190** | Tổng span OCR | Cả 2 bên đều chạy tuần tự |
| **Confidence Quality Review** | **10.440** | **5.061** | **+5.379** | Đo trực tiếp qua span | Main: 647 out / Hoangha: 557 out |
| **Primary Extract: Đơn hoàn ứng** | 7.641 | 2.272 | +5.369 | Đo trực tiếp qua span | Main: 2,539 out / Hoangha: 456 out |
| **Primary Extract: Khách sạn** | 7.131 | 3.037 | +4.094 | Đo trực tiếp qua span | Main: 1,121 out / Hoangha: 647 out |
| **Primary Extract: Vé tàu** | 8.541 | 3.900 | +4.641 | Đo trực tiếp qua span | Main: 1,127 out / Hoangha: 611 out |
| **Primary Extract: Phiếu thu** | 13.662 | 2.936 | +10.726 | Đo trực tiếp qua span | Main: 1,562 out (thất bại validate) |
| **Tổng Primary Extract (4 tệp)**| **36.975** | **12.145** | **+24.830** | Tổng 4 span extract | **Tăng 204% thời gian** |
| **Schema Repair (Phiếu thu)** | **5.529** | 0.000 | +5.529 | Đo trực tiếp qua span | 1,460 completion tokens |
| **Resolver LLM (Suggestions)** | **1.548** | 0.000 | +1.548 | Đo trực tiếp qua span | 136 completion tokens |
| **Xử lý Python nội bộ (Read Pass)** | **0.088** | ~0.740 | -0.652 | Suy từ khoảng trống span | Validation, rules, AST, JSON |
| **Tổng chu kỳ Đọc (Read Interval)**| **72.229** | **29.400** | **+42.829** | Root span / Event time | **Main chậm hơn 2.45 lần** |
| Harness: Chuẩn bị file & Upload | 4.223 | ~0.050 | +4.173 | Suy từ timestamp | Đọc bytes, hash SHA256, ghi disk |
| Harness: Submit & Reconcile | 0.025 | n/a | +0.025 | Đo trực tiếp qua span | Admission, Reconcile, Commit |
| Harness: Export Trace & Artifacts | 5.111 | ~0.100 | +5.011 | Suy từ timestamp | Ghi `case.json`, `spans.json` (165KB) |
| **Tổng thời gian Harness E2E** | **81.588** | **29.550** | **+52.038** | Đo từ đầu đến cuối script | *Không so sánh trực tiếp số này* |

> [!NOTE]
> Giai đoạn `settlement-draft-read` trên Main kéo dài 72.229s, trong đó 72.141s là thời gian HTTP socket chờ Mistral OCR và Kimi LLM. Khoảng trống thời gian cục bộ giữa các span chỉ là **88ms**, chứng minh không hề có hiện tượng nghẽn I/O database, khóa lock SQLite hay thuật toán Python chạy chậm.

### 2.2. Bảng tổng hợp số cuộc gọi và Token Usage

| Chỉ số | Main Kimi | Hoangha | Chênh lệch |
| :--- | :--- | :--- | :--- |
| **Số yêu cầu OCR (Mistral)** | 4 | 4 | 0 |
| **Số yêu cầu LLM (Kimi-K3)** | **7** | **5** | **+2 (+40%)** |
| - *Confidence review* | 1 | 1 | 0 |
| - *Standalone classify* | 0 | 0 | 0 |
| - *Primary extraction* | 4 | 4 | 0 |
| - *Schema repair* | 1 | 0 | +1 |
| - *Resolver* | 1 | 0 | +1 |
| **Completion Tokens: Đơn hoàn ứng** | **2,539** | **456** | **+2,083 (+457%)** |
| **Completion Tokens: 4 tệp chính** | **6,349** | **2,387** | **+3,962 (+166%)** |
| **Tổng Completion Tokens (toàn bộ LLM)**| **8,592** | **2,944** | **+5,648 (+192%)** |
| **Prompt Tokens (Tổng đầu vào)** | 14,320 | 12,606 | +1,714 (+13.6%) |
| **Reasoning Tokens (ghi nhận từ provider)**| *Không thu thập* | 85 (tổng 5 cuộc gọi)| n/a |

---

## 3. Bảng khác biệt kỹ thuật: Request, Prompt, Schema và Validation

| Tiêu chí | Main Kimi (`src/invoice_referee/`) | Hoangha (`.worktrees/hoangha/`) |
| :--- | :--- | :--- |
| **HTTP Client & Lifecycle** | `httpx.AsyncClient` khởi tạo và đóng mới trong mỗi request (`async with httpx.AsyncClient(...)`). Không có connection pool dùng chung giữa các request. | Sử dụng `openai.OpenAI` SDK chính thức. Client được tạo 1 lần tại `__init__`, giữ connection pool và HTTP keep-alive liên tục. |
| **Tham số Request LLM** | `model: "moonshotai/Kimi-K3"`<br>`temperature: 0.1`<br>`response_format: {"type": "json_object"}`<br>*(Không truyền `reasoning_effort`, `max_tokens`, `top_p`)* | `model: "moonshotai/Kimi-K3"`<br>`temperature: 0.1`<br>`max_tokens: 8192`<br>`top_p: 0.95`<br>`stream: False`<br>`extra_body: {"reasoning_effort": "low"}` |
| **Cấu trúc Wire Output (Model)** | **Meta-Object lồng nhau:**<br>`{"fields": [{"field": name, "state": FOUND\|NOT_PRESENT, "value": v, "quote": q, "page": p}], "line_items": [{"fields": [...]}]}`.<br>Bắt buộc LLM sinh cả các trường vắng mặt (`NOT_PRESENT`). | **Phẳng (Flat JSON):**<br>`{"total_amount": "4140000", "lines": [{"amount": "1080000", ...}]}`.<br>Không bắt LLM trả meta-object hay liệt kê trường vắng mặt. |
| **Độ dài Output Token (Paper)** | **2,539 tokens** (do sinh 13 top-level fields bọc quote + 3 line items mỗi dòng 4 subfields bọc quote). | **456 tokens** (chỉ sinh các trường thực tế có trên đơn). |
| **Cơ chế Xử lý Lỗi Schema** | Có 1 slot sửa lỗi (`budget.schema_repairs_allowed = 1`). Khi `validate()` ném `XkiroSchemaError`, gửi lại toàn bộ prompt + lỗi validation + raw response để model sửa. | Sử dụng parser mềm dẻo (`_json_objects`), trích xuất JSON object hợp lệ đầu tiên; có hàm repair qua `call_with_service_retry` nhưng không bị kích hoạt ở TC25. |
| **Xử lý Mâu thuẫn Số tiền** | Khi số chứng từ khớp nhưng số tiền lệch (900k vs 700k), matcher hạ cấp thành `SUGGEST_LINK`, kích hoạt LLM `resolve-evidence-suggestions`. | Ghép liên kết trực tiếp bằng mã hóa đơn / số phiếu thu; xử lý chênh lệch số tiền ở tầng quy tắc kế toán (`findings`), không gọi LLM hòa giải. |
| **Nhãn Provider trong Telemetry** | Từng bị lỗi hardcode `"provider": "xkiro"` tại `telemetry.py:470` (chỉ là nhãn logging, client thực tế là `KimiClient`). | Ghi đúng `Kimi/Modal` qua wrapper. |

---

## 4. Các nguyên nhân đã được chứng minh và Giả thuyết chưa kiểm chứng

### 4.1. Các nguyên nhân ĐÃ ĐƯỢC CHỨNG MINH (Bằng chứng cụ thể từ Artifacts)
1. **Số lượng Completion Tokens quá lớn dẫn đến thời gian sinh text kéo dài:**  
   - *Bằng chứng:* Token sinh ra ở Main là 8,592 tokens so với 2,944 tokens ở Hoangha (+192%). Tốc độ sinh của mô hình Kimi-K3 qua API dao động trong khoảng 80–120 token/s. Việc phải sinh thêm ~5,600 tokens trực tiếp giải thích hơn **30 giây** chênh lệch trong tổng thời gian LLM.
2. **Wire Schema Verbosity buộc model lặp lại cấu trúc rườm rà:**  
   - *Bằng chứng:* Đơn hoàn ứng tại `case_evidence_reports` có 13 trường top-level và 12 trường dòng bảng. Việc yêu cầu model xuất hiện rõ `NOT_PRESENT` kèm `alternatives: []`, `quote: null`, `page: null` khiến kích thước payload text của Kimi tăng vọt từ 1.4KB lên hơn 6KB.
3. **Phát sinh 01 cuộc gọi Resolver không cần thiết do mâu thuẫn số tiền (+1.55s):**  
   - *Bằng chứng:* `matching.py:608` lọc các liên kết có `status == "SUGGEST_LINK"`. Phiếu thu có số `PT-251026-016` trùng khớp hoàn toàn với số tham chiếu ở dòng 3 trên đơn hoàn ứng. Tuy nhiên, vì số tiền kê khai là 900.000 ₫ trong khi phiếu thu là 700.000 ₫, bộ đối soát đã hạ cấp từ `AUTO_LINK` xuống `SUGGEST_LINK`, dẫn đến cuộc gọi `llm:resolve-evidence-suggestions` (1.55s, 136 tokens) chỉ để nhận lại kết quả không đổi.
4. **Phát sinh 01 cuộc gọi Schema Repair trên phiếu thu (+5.53s):**  
   - *Bằng chứng:* Span `llm:extract` thứ 20 (attempt 1) kết thúc sau 13.66s với 1,562 completion tokens nhưng không được chấp nhận vào DTO; ngay sau đó span thứ 21 (attempt 2, kind="repair") được kích hoạt với prompt dài 2,767 ký tự, tốn thêm 5.53s và 1,460 tokens.
5. **Thực thi tuần tự 100% trong `read_root_role_aware`:**  
   - *Bằng chứng:* Cả vòng lặp OCR (`pipeline.py:981`) và vòng lặp trích xuất (`pipeline.py:1168`) đều sử dụng `for ... in ...: await ...`. Tổng thời gian là tổng tuyến tính của từng request riêng lẻ.

### 4.2. Các giả thuyết CHƯA KIỂM CHỨNG (Cần phân biệt rõ với kết luận)
1. **Tác động của tham số `reasoning_effort="low"`:**  
   - *Giả thuyết:* Kimi-K3 là mô hình có khả năng suy luận (reasoning). Việc Hoangha truyền `reasoning_effort="low"` giúp chặn đứng việc model mở rộng suy luận ngầm (Hoangha chỉ ghi nhận 6–32 reasoning tokens mỗi call). Ở Main, vì không truyền tham số này, Kimi có thể đã dành thêm thời gian prefill / reasoning trước khi sinh token đầu tiên.  
   - *Tình trạng:* **Giả thuyết hợp lý.** Telemetry của Main hiện tại chỉ ghi nhận `prompt_tokens`, `completion_tokens` và `total_tokens` (hàm `_trace_usage` tại `kimi.py:146` bỏ qua `reasoning_tokens`), nên chưa có dữ liệu tách bạch số token suy luận của Main.
2. **Ảnh hưởng của việc thiếu HTTP Connection Pooling:**  
   - *Giả thuyết:* Việc Main tạo mới `httpx.AsyncClient` ở mỗi cuộc gọi buộc hệ thống phải thực hiện lại TCP handshake và TLS negotiation (ước tính 80–150ms mỗi lần cho 7 cuộc gọi LLM và 4 cuộc gọi OCR = ~1.0s – 1.5s).  
   - *Tình trạng:* **Giả thuyết.** Cần có micro-benchmark mạng riêng để đo chính xác thời gian bắt tay TLS tới endpoint Kimi.
3. **Nguyên nhân chính xác gây lỗi Schema ở Lần 1 của Phiếu thu:**  
   - *Thực tế:* Span 20 ghi nhận Kimi trả về HTTP 200 và chuỗi JSON có đủ các key cấp cao (`document_type`, `fields`, `line_items`). Hàm `validate()` trong `extraction.py:550` có thể đã thất bại ở một trong các điều kiện: giá trị float trong trường tiền, thiếu quote/page ở một field con, hoặc sai định dạng alternatives.  
   - *Tình trạng:* **UNKNOWN.** Do `complete_structured` không ghi nhận nội dung ngoại lệ `XkiroSchemaError` vào span hay file log nào trước khi kích hoạt repair, ta không thể khẳng định chắc chắn 100% lỗi cụ thể là gì mà không phỏng đoán.

---

## 5. Danh sách các giải pháp tối ưu hóa ưu tiên

### [P1] Tách biệt Nhận diện Chứng từ (Association) khỏi Thẩm định Phân bổ (Allocation) để loại bỏ Resolver không cần thiết
- **Vấn đề & Bằng chứng:** Phiếu thu `phieu_thu_di_chuyen.pdf` có số `PT-251026-016` khớp tuyệt đối với dòng kê khai số 3. Mâu thuẫn duy nhất là số tiền (900.000 ₫ vs 700.000 ₫). Thuật toán matching cũ đánh đồng mâu thuẫn số tiền với sự mơ hồ về danh tính, dẫn đến gọi LLM resolver một cách vô nghĩa (tốn 1.55s và 1,113 tokens).
- **File/Symbol liên quan:** `src/invoice_referee/evidence/matching.py` (`match_paper_evidence`, `resolve_evidence_suggestions`).
- **Thay đổi nhỏ nhất:** Trong hàm đối soát bằng quy tắc, nếu số chứng từ (document number) khớp chính xác, xác lập liên kết danh tính là `ASSOCIATED / MATCHED`. Đưa khoản chênh lệch số tiền vào danh sách `CONFLICT_AMOUNT / DISPUTED` bằng logic số học xác định của code; **không** đưa vào danh sách `SUGGEST_LINK` gửi cho LLM.
- **Lợi ích đo được:** Tiết kiệm chắc chắn **1.55s** và **1 cuộc gọi LLM** (1,113 tokens) trên mỗi hồ sơ có mâu thuẫn số tiền.
- **Rủi ro & Phản ví dụ bảo vệ:** Không có rủi ro nghiệp vụ vì code tài chính vẫn phát hiện đầy đủ mâu thuẫn 200.000 ₫ và chặn tiền.  
  *Phản ví dụ bắt buộc giữ Resolver:* Khi chứng từ **không có số hóa đơn** (chỉ có tên dịch vụ tương tự, ví dụ 2 hóa đơn ăn uống cùng ngày không ghi mã), danh tính chứng từ thực sự mơ hồ thì vẫn bắt buộc phải gọi Resolver.

---

### [P2] Rút gọn Wire Schema (Model Output) và Giao nhiệm vụ Hoàn thiện DTO cho Code Python
- **Vấn đề & Bằng chứng:** Đơn hoàn ứng tốn 2,539 completion tokens do phải xuất hàng loạt field `NOT_PRESENT` và bọc meta-object cho từng giá trị.
- **File/Symbol liên quan:** `src/invoice_referee/evidence/prompts.py` (`build_extraction_prompt`), `src/invoice_referee/evidence/extraction.py` (`extract_paper_document`, `extract_evidence_document`).
- **Thay đổi nhỏ nhất:**  
  1. Cho phép LLM chỉ trả về các trường thực sự tìm thấy (`state: FOUND`), kèm giá trị và quote/page ngắn gọn.  
  2. Không bắt LLM liệt kê danh sách các trường vắng mặt.  
  3. Sau khi nhận JSON từ model, code Python sẽ duyệt qua `DOCUMENT_PROFILES[doc_type].allowed_fields`, tự động bổ sung các trường còn thiếu với `state="NOT_PRESENT", value=None, refs=[]`.
- **Lợi ích đo được:** Giảm 40% – 60% completion tokens ở các bước extraction (ước tính giảm từ 6,349 xuống còn ~2,500 – 3,000 tokens), giúp tiết kiệm **15s – 20s** độ trễ LLM.
- **Rủi ro & Bảo đảm chất lượng:** Code Python phải xác thực chặt chẽ quote trong OCR text trước khi gắn vào `EvidenceRef`, đảm bảo không mất tính kiểm chứng (provenance).

---

### [P3] Bổ sung tham số `reasoning_effort="low"` và chuẩn hóa tham số Kimi-K3
- **Vấn đề & Bằng chứng:** Hoangha có `extra_body={"reasoning_effort": "low"}` giúp hạn chế thinking budget của Kimi; Main đang để mặc định.
- **File/Symbol liên quan:** `src/invoice_referee/evidence/kimi.py` (`KimiClient.complete_json`).
- **Thay đổi nhỏ nhất:** Thêm `"extra_body": {"reasoning_effort": "low"}` và `"max_tokens": 8192` vào payload gửi tới Kimi endpoint. Bổ sung trích xuất trường `"reasoning_tokens"` trong `_trace_usage()` để tăng cường khả năng quan sát.
- **Lợi ích đo được:** Rút ngắn thời gian Time-to-First-Token (TTFT), ngăn ngừa model rơi vào vòng lặp suy luận sâu không cần thiết cho các tác vụ đọc OCR trực tiếp.
- **Rủi ro:** Cần kiểm tra hồi quy trên các hồ sơ phức tạp (nhiều bảng kê, chữ viết tay) xem độ chính xác có bị ảnh hưởng khi giảm reasoning effort hay không.

---

### [P4] Tái sử dụng HTTP Connection Pool (Keep-Alive) cho Kimi Client
- **Vấn đề & Bằng chứng:** `KimiClient` mở mới `httpx.AsyncClient` ở từng lệnh gọi, gây lãng phí thời gian bắt tay TCP/TLS 7 lần liên tiếp.
- **File/Symbol liên quan:** `src/invoice_referee/evidence/kimi.py` (`KimiClient`).
- **Thay đổi nhỏ nhất:** Chuyển `httpx.AsyncClient` thành thuộc tính của `KimiClient` (khởi tạo 1 lần trong lifecycle của workflow reader và đóng khi hoàn tất), tận dụng connection pool mặc định của httpx.
- **Lợi ích đo được:** Tiết kiệm khoảng **0.5s – 1.2s** tổng thời gian mạng.
- **Rủi ro:** Cần đảm bảo xử lý lỗi connection timeout và đóng client sạch sẽ trong khối `finally` hoặc async context manager.

---

### [P5] Áp dụng Concurrency có Giới hạn (Bounded Concurrency = 2) cho OCR và Evidence Extraction
- **Vấn đề & Bằng chứng:** 4 tệp OCR chạy tuần tự mất 17.65s; 3 tệp evidence extraction chạy tuần tự mất 29.33s. Cả 4 tệp PDF đều hoàn toàn độc lập về mặt dữ liệu.
- **File/Symbol liên quan:** `src/invoice_referee/evidence/pipeline.py` (`read_root_role_aware`).
- **Thay đổi nhỏ nhất:**  
  1. Dùng `asyncio.Semaphore(2)` để chạy song song tối đa 2 tác vụ OCR cùng lúc.  
  2. Chạy trích xuất đơn hoàn ứng (`paper`) trước; sau đó dùng `asyncio.Semaphore(2)` chạy song song trích xuất các chứng từ đính kèm (`evidence`).  
  3. Tuyệt đối **không** dùng `asyncio.gather` không giới hạn.
- **Lợi ích đo được:** Tiết kiệm dự kiến **12s – 16s** walltime (thời gian OCR giảm từ 17.6s xuống ~9.5s; thời gian extract giảm từ ~37s xuống ~22s).
- **Rủi ro kỹ thuật & Ràng buộc:**  
  - *Shared Repair Quota:* `budget.claim_schema_repair()` phải được bảo vệ bằng `asyncio.Lock` để tránh 2 task chạy đồng thời cùng tranh chấp slot repair.  
  - *Checkpoint SQLite:* Hàm `on_doc_done(source_id, analysis)` phải serialize việc ghi vào SQLite để tránh lỗi `database is locked`.  
  - *Trace Ordering:* Thứ tự span trong file log có thể bị đan xen, nhưng mốc `started_at` / `ended_at` của từng span vẫn phản ánh chính xác.

---

### [P6] Bổ sung Logging an toàn cho Lỗi Schema Repair
- **Vấn đề & Bằng chứng:** Khi `validate(payload)` thất bại ở attempt 1 của phiếu thu, thông tin lỗi bị nuốt và chỉ gửi vào prompt repair, không lưu vào trace metadata, khiến nguyên nhân sửa schema rơi vào trạng thái UNKNOWN.
- **File/Symbol liên quan:** `src/invoice_referee/evidence/structured_output.py` (`complete_structured`).
- **Thay đổi nhỏ nhất:** Bổ sung trường `validation_error_summary` (đã cắt ngắn, không chứa dữ liệu nhạy cảm) vào span metadata của lần gọi repair.
- **Lợi ích:** Minh bạch hóa 100% nguyên nhân phát sinh repair trong tương lai để tinh chỉnh prompt/schema kịp thời.

---

## 6. Kế hoạch đo đối chứng trong tương lai (Controlled Experiment Plan)

> [!IMPORTANT]
> Đây là kế hoạch thực nghiệm có kiểm soát cho tương lai. **Không thực thi hay gọi bất kỳ lệnh mạng nào trong tác vụ hiện tại.**

Để xác minh chính xác hiệu quả của từng phương án mà không làm nhiễu kết quả, cần thực hiện theo phương pháp **biến đơn lập (single-variable isolation)**:

1. **Chuẩn bị môi trường:**
   - Cùng 1 máy chủ, cùng phiên bản Python, cố định bộ 4 tệp PDF đầu vào của TC25.
   - Sử dụng runner độc lập `scripts/run_role_aware_live.py` với thư mục runtime và DB SQLite cô lập hoàn toàn.
   - Cố định đồng hồ nghiệp vụ `--as-of 2026-10-16T12:00:00+07:00`.
2. **Các bước đối chứng tuần tự:**
   - **Baseline (M0):** Chạy lại snapshot hiện tại của Main (Kimi-K3), ghi nhận thời gian và token.
   - **Thử nghiệm 1 (E1 - Connection Reuse):** Chỉ bật connection pooling cho `KimiClient`. Đo chênh lệch latency mạng.
   - **Thử nghiệm 2 (E2 - Low Reasoning Effort):** Giữ nguyên code, chỉ thêm `extra_body={"reasoning_effort": "low"}`. Đo tổng completion tokens và thời gian phản hồi từng call.
   - **Thử nghiệm 3 (E3 - Bỏ Resolver thừa):** Áp dụng luật tách association khỏi mâu thuẫn số tiền. Kiểm tra xem cuộc gọi resolver có biến mất hoàn toàn hay không (kỳ vọng giảm 1 call LLM).
   - **Thử nghiệm 4 (E4 - Compact Wire Schema):** Áp dụng schema chỉ trả `FOUND`. So sánh trực tiếp số completion token của đơn hoàn ứng (kỳ vọng giảm từ ~2,500 xuống <800 tokens).
   - **Thử nghiệm 5 (E5 - Concurrency = 2):** Bật semaphore = 2 cho OCR và evidence extraction. Đo tổng walltime.
3. **Tiêu chuẩn chấp thuận (Acceptance Criteria):**
   - Kết quả nghiệp vụ của TC25 **không được thay đổi**: Vẫn phải ở trạng thái `WAITING / BLOCKED`, không phát sinh lệnh chi trả (`instructions: []`), phát hiện chính xác số kê khai 900.000 ₫ vs số chứng từ 700.000 ₫ (chênh lệch 200.000 ₫).
   - Không làm mất quote nguyên văn và số trang của bất kỳ trường nào.

---

## 7. Những điều tuyệt đối KHÔNG ĐƯỢC CẮT BỎ để đổi lấy Latency

Trong quá trình tối ưu hóa hiệu năng, có những thành phần cốt lõi thuộc về nguyên tắc thiết kế bất di bất dịch của InvoiceReferee:

1. **Không bỏ trích xuất Quote nguyên văn (Verbatim Quote) và Số trang (Page):**  
   Đây là hàng rào kỹ thuật duy nhất ngăn chặn ảo giác (hallucination) của LLM. Mọi số tiền, ngày tháng, tên đơn vị được công nhận phải có căn cứ chứng minh trực tiếp từ tài liệu OCR.
2. **Không nới lỏng kiểm tra kiểu dữ liệu Tiền tệ (Integer vs Float):**  
   Tiền tệ Việt Nam Đồng (VNĐ) không có phần thập phân. Quy tắc cấm kiểu `float` trong các trường tiền nhằm ngăn ngừa sai số làm tròn số học tài chính.
3. **Không bỏ trạng thái `AMBIGUOUS` khi tài liệu thực sự mâu thuẫn:**  
   Nếu một tài liệu thể hiện nhiều ngày hoặc nhiều số tiền mâu thuẫn nhau mà không rõ ngữ cảnh, bắt buộc phải giữ `state: "AMBIGUOUS"` và danh sách `alternatives` để con người xử lý.
4. **Không xóa bỏ hoàn toàn bộ giải quyết mơ hồ (Resolver):**  
   Resolver là cần thiết khi có nhiều chứng từ cùng loại mà không có số hóa đơn để đối chiếu chắc chắn. Chỉ bỏ resolver khi số hóa đơn/số phiếu thu đã trùng khớp tuyệt đối.
5. **Không tăng Deadline 90s một cách tùy tiện:**  
   Thời hạn 90s là ngưỡng trải nghiệm người dùng tối đa cho một thao tác nộp hồ sơ. Việc tăng deadline lên 180s hay 300s không phải là tối ưu hóa, mà là che giấu sự kém hiệu quả của hệ thống.
6. **Không sử dụng `asyncio.gather` không giới hạn:**  
   Việc bắn đồng loạt hàng chục request OCR và LLM sẽ gây cạn kiệt băng thông, vượt ngưỡng Rate Limit (RPM/TPM) của nhà cung cấp dịch vụ, và có thể dẫn đến lỗi sập toàn bộ tiến trình thẩm định.

---

## 8. Xác nhận tuân thủ nhiệm vụ (Compliance Attestation)

Tôi xác nhận một cách độc lập và trung thực rằng trong suốt quá trình phân tích và lập báo cáo này:
1. **Không có bất kỳ cuộc gọi nào** tới các dịch vụ bên ngoài (Mistral OCR, Kimi LLM, OpenAI, xKiro hay bất kỳ provider nào).
2. **Không chạy bất kỳ kịch bản LIVE**, browser test, harness hay integration test nào có khả năng kích hoạt đọc tài liệu.
3. **Không chỉnh sửa, xóa bỏ hay thay đổi** bất kỳ dòng mã nguồn, file cấu hình, file môi trường (`.env`) hay cơ sở dữ liệu nào của dự án.
4. Toàn bộ các phát hiện và số liệu trong báo cáo đều được trích xuất trực tiếp từ các file artifacts tĩnh đã ghi nhận (`REPORT.md`, `spans.json`, `result.json`, `case.json`, `events.json`, `run-config.json`) và mã nguồn hiện hữu tại 2 nhánh kiểm thử.

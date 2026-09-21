# InvoiceReferee — Evaluation Plan

## 1. Mục tiêu

File này định nghĩa cách chứng minh InvoiceReferee hoạt động trên dữ liệu mới và cách thu thập bằng chứng người dùng thực tế mà không bịa dữ liệu hoặc feedback.

## 2. Sprint 1 — Evaluation kỹ thuật

### Ground truth

- 17 documented cases trong `TEST_CASES.md`.
- Core Verify: 4 case.
- Challenge A Verify: 5 case.
- Full Verify: một thao tác chạy cả hai suite qua cùng production `review()` path.
- Production code không được đọc expected labels.

### Unseen-input test

Tạo ít nhất 2 transaction mới không nằm trong fixtures:

1. một routine case với vendor/amount/quantity mới;
2. một abnormal case, ưu tiên factual-unknown hoặc beyond-authority.

Judge/user phải có thể paste hoặc upload JSON vào Streamlit và chạy qua cùng `review()` service.

### Metrics

Ghi tối thiểu:

- expected action vs actual action;
- uncertainty type;
- pass/fail;
- question có cụ thể hay không;
- structured `AgentAssessment` có hợp lệ hay không;
- LLM proposal có bị Decision Guard sửa hay không;
- có dùng deterministic fallback hay không;
- timestamp.

### Document-path evaluation (Sprint 1)

Đường OCR và structure-aware có bộ đo riêng, **không** trộn vào Core/Escalation ở trên — evidence trích xuất không được làm phồng suite nghiệp vụ.

**`verify.semantic_harness` — chẩn đoán opt-in (`--live`), không lưu response:**

| Metric | Giá trị đo được |
|---|---|
| field exact match | 100.0% |
| action accuracy (qua production `review()`) | 100.0% |
| false auto-confirms | 0 |
| provenance coverage | 100.0% |

**Bộ fixture rule-path (15 OCR + 20 ST) đã bị xoá** cùng label/layout mapper.

| Metric | Giá trị đo được |
|---|---|
| section accuracy | 100.0% |
| row-role precision / recall | 100.0% / 100.0% |
| line-item precision / recall | 100.0% / 100.0% |
| field recall / precision | 100.0% / 100.0% |
| binding accuracy | 100.0% |
| normalized exact match | 100.0% |
| provenance coverage | 100.0% |
| conflict accuracy | 100.0% |
| semantic fallback rate | 0.0% |
| human review rate | 0.0% |
| false auto-confirms | 0 |

**Giới hạn đã biết của bộ đo này** (không được đọc như đảm bảo độ chính xác tổng quát):

- family set dùng `TOTAL_INSIDE_TABLE` thay vì một family "total ngoài bảng" riêng;
- line-item metric so **số lượng**, không so định danh/nội dung từng item;
- row-role và field precision chỉ chấm trên các mục mà manifest **gán nhãn**, nên một row đúng nhưng không gán nhãn không bị phạt — nhưng cũng không được tính là bằng chứng;
- `--live-file` là chẩn đoán thủ công, so ảnh thật với một case **tổng hợp** (ST01 mô phỏng theo `a.jpg`, không phải bản ghi byte-faithful của ảnh);
- 20 fixture là 10 family × 2 variant; variant thứ hai khác variant thứ nhất ở giá trị tiền, không ở bố cục.

### LLM/Decision Guard evaluation

LLM là một phần của normal review path nên phải được đánh giá riêng, nhưng output của LLM không được dùng làm ground truth cho phép tính hoặc business facts.

Theo dõi tối thiểu:

- **Structured-output validity rate:** tỷ lệ response parse được thành `AgentAssessment` hợp lệ.
- **LLM/Guard disagreement rate:** tỷ lệ proposal của LLM bị Decision Guard reject/override.
- **Fallback rate:** tỷ lệ provider lỗi/timeout/output invalid khiến hệ thống dùng deterministic fallback.
- **Question answerability:** câu hỏi có nêu đủ dữ kiện để người nhận trả lời trong một câu mà không cần mở lại toàn bộ hồ sơ hay không.
- **Primary-issue validity:** `primary_check_id` phải trỏ tới check đang tồn tại và chưa được giải quyết; LLM không được tự tạo vấn đề mới.
- **Explanation groundedness:** explanation chỉ được dựa trên `Transaction`, `CheckResult[]` và `PolicyContext`; policy/check/evidence references phải trace được về input hiện có.

Các test bắt buộc:

1. fake LLM đề xuất `AUTO_PROCESS` khi có `FACTUAL_UNKNOWN` → Guard phải trả `REQUEST_INFO`;
2. fake LLM đề xuất `AUTO_PROCESS` khi vượt authority → Guard phải trả `ESCALATE`;
3. fake LLM đề xuất `AUTO_PROCESS` cho input bị P15 flagged → Guard phải trả `REQUEST_INFO`;
4. provider timeout/error → final action vẫn do deterministic rules xác định, fallback được dùng và audit ghi nhận;
5. provider trả structured output invalid → fallback được dùng, không bỏ qua Guard;
6. một unseen case có nhiều mismatch → LLM phải chọn một unresolved check hợp lệ làm câu hỏi chính, Guard vẫn quyết action theo policy;
7. routine case với valid assessment → `AUTO_PROCESS` nếu deterministic facts/policy đều cho phép.

Đối với tiêu chí Challenge A về chất lượng câu hỏi, một câu hỏi chỉ được xem là đạt mức cao khi người nhận có thể quyết định/trả lời ngay từ nội dung câu hỏi và dữ kiện được nêu, không phải mở lại toàn bộ PO/invoice/receipt để hiểu hệ thống đang hỏi gì.

## 3. Challenge A quality metrics

Khi có tập độc lập lớn hơn, theo dõi:

- **Missed human-intervention rate:** case đáng lẽ cần người nhưng hệ thống lại AUTO_PROCESS.
- **Unnecessary human-intervention rate:** routine case bị REQUEST_INFO/ESCALATE không cần thiết.
- **Routine auto-processing rate:** tỷ lệ routine case đi qua tự động.
- **Question answerability:** người nhận có thể trả lời câu hỏi ngay từ thông tin được nêu hay vẫn phải tự mở lại toàn bộ hồ sơ.

## 4. Sprint 2 — Real-user validation

Không điền tên hoặc quote giả. Chỉ cập nhật khi đã phỏng vấn/test thật.

| Slot | Target role | Evidence cần thu |
| --- | --- | --- |
| U1 | Kế toán thanh toán / Accounts Payable | chức danh, workflow hiện tại, quote nguyên văn, pain point |
| U2 | Purchasing / Procurement | chức danh, cách xử lý mismatch/approval, quote nguyên văn |
| U3 | Finance Manager hoặc người phê duyệt | authority boundary, escalation expectation, quote nguyên văn |

## 5. Before / After measurement

Chọn 5–10 transaction mẫu và đo cùng một nhiệm vụ:

**Before:** người dùng tự đọc PO + receipt + invoice + payment history và quyết định bước tiếp theo.

**After:** người dùng dùng InvoiceReferee rồi xác nhận/override kết quả.

Ghi:

- thời gian xử lý mỗi case;
- số mismatch bị bỏ sót;
- số lần phải mở lại chứng từ;
- số escalation không cần thiết;
- số quyết định Agent bị human override.

## 6. Product change from feedback

Mỗi feedback dùng để thay sản phẩm phải có:

- người/role đưa feedback;
- vấn đề họ gặp;
- thay đổi cụ thể;
- commit hoặc before/after evidence;
- tác động tích cực;
- ít nhất một bất cập hoặc trade-off phát sinh.

Không ghi “không có bất cập”. Nếu chưa quan sát được tác động tiêu cực, ghi rõ là **chưa đủ evidence** và tiếp tục test.

## 7. Evidence discipline

Phân biệt rõ:

- `SYNTHETIC`: policy/data tự sinh để prototype/evaluation;
- `REAL`: dữ liệu hoặc feedback thu từ người dùng thật;
- `UNVERIFIED`: giả thuyết chưa được xác nhận.

Không biến synthetic 50M authority threshold thành claim về policy thật của doanh nghiệp hoặc quy định pháp luật.

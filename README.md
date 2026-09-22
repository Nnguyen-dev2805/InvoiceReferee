# InvoiceReferee

**Tác tử kế toán kiểm tra hóa đơn, biên lai và chứng từ chi phí**

## 1. Giới thiệu đề tài

🌐 [Web app](https://invoicereferee.streamlit.app/) · 📹 [Video demo](https://drive.google.com/file/d/1vS4_2GfvYMu049OI-aR-kNMfMuVZCX9r/view?usp=sharing)

Trong công việc thống kê và ghi nhận hóa đơn, nhân viên kế toán thường phải xử lý một lượng lớn bill và chứng từ mỗi ngày. Bên cạnh việc kiểm tra số tiền, kế toán còn phải xác nhận nhiều yếu tố khác như chứng từ có rõ ràng, đầy đủ thông tin hay không, nội dung chi tiêu có hợp lý với mục đích được khai báo hay không. Đối với các trường hợp có thêm phiếu nhập kho, biên bản giao nhận hoặc các tài liệu liên quan, kế toán còn phải đối chiếu để xác định các chứng từ có thực sự mô tả cùng một giao dịch hay không.

Trong thực tế, không ít bill có chất lượng kém, bị mờ, thiếu thông tin hoặc có dữ liệu không nhất quán giữa các chứng từ. Việc kiểm tra toàn bộ hồ sơ thủ công khiến thời gian xử lý kéo dài và tạo thêm nhiều công việc lặp lại cho kế toán.

**InvoiceReferee** được xây dựng như một lớp kiểm tra đầu vào, hỗ trợ kế toán trước khi hồ sơ được xử lý chính thức. Hệ thống không thay thế kế toán trong việc ra quyết định, mà thực hiện bước kiểm tra và đối chiếu ban đầu.

Nhân viên chỉ cần nộp bill, mô tả mục đích chi tiêu và các tài liệu hỗ trợ nếu có. InvoiceReferee sẽ kiểm tra chất lượng chứng từ, xác định các thông tin quan trọng đã được đọc và trích xuất đầy đủ hay chưa, đồng thời đối chiếu dữ liệu giữa bill và các tài liệu liên quan.

Nếu chứng từ rõ ràng, thông tin cần thiết đầy đủ và các dữ liệu đối chiếu thống nhất, hệ thống trả về **PASS**, giúp kế toán có thể tiếp tục xử lý hồ sơ nhanh hơn.

Ngược lại, nếu phát hiện chứng từ bị mờ hoặc không thể đọc chắc chắn, thiếu thông tin quan trọng, thiếu tài liệu hỗ trợ hoặc dữ liệu giữa các chứng từ không khớp, hệ thống sẽ **dừng quá trình kiểm tra và trả về lý do cụ thể**. Khi đó, kế toán hoặc nhân viên có thể kiểm tra và bổ sung thông tin trước khi hồ sơ được xử lý tiếp.

## Tính năng chính

- **Nhân viên** nộp hồ sơ chi phí: chứng từ chính (hóa đơn/bill/biên lai) kèm mô tả mục đích chi và tài liệu bổ sung (phiếu nhập kho, biên bản giao nhận...) nếu có.
- Hệ thống tự động **OCR** (Mistral OCR), đánh giá **chất lượng đọc** của từng chứng từ, và **đối chiếu dữ liệu** giữa chứng từ chính với tài liệu bổ sung khi có nhiều nguồn.
- **Kế toán** xem hàng đợi hồ sơ đã xử lý (`Đã pass` / `Cần xác minh`) kèm tóm tắt, lý do cụ thể và bằng chứng gốc — ảnh/PDF xem trực tiếp trong giao diện, không cần tải file.
- **Verify**: chạy song song một bộ case mẫu qua đúng luồng xử lý thật, dùng để kiểm thử nhanh sau mỗi lần đổi code hoặc trước khi nộp bài.

## Quyết định

Hệ thống trả **PASS** khi chứng từ đọc được, đầy đủ thông tin cần thiết và các nguồn đối chiếu khớp nhau; trả **NEEDS_HUMAN** kèm lý do cụ thể khi thiếu thông tin, chữ không đọc chắc chắn, hoặc dữ liệu giữa các nguồn không khớp. Đây là bản rút gọn hiện tại của mô hình quyết định 3 nhánh (`AUTO_PROCESS` / `REQUEST_INFO` / `ESCALATE`, phân loại theo `OUTSIDE_POLICY` / `BEYOND_AUTHORITY` / `SUSPICIOUS`) mô tả trong `docs/POLICY.md` và `docs/CHALLENGE.md` — phần phân loại chi tiết đó chưa được triển khai.

## Cài đặt và chạy

```powershell
pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
```

Tạo file `.env` ở thư mục gốc (tham khảo `.env.example`) với các key: `MISTRAL_API_KEY`, `KIMI_TOKEN`, `KIMI_SECRET`, `KIMI_BASE_URL`, `KIMI_MODEL`.

Mở `http://localhost:8501`, sidebar có 4 không gian làm việc:

- `Nhân viên` — nộp hồ sơ mới.
- `Kế toán` — xem và xử lý hồ sơ đã nộp.
- `Verify` — chạy hàng loạt case mẫu trong `data/testcase/JUDGEMENT/`.
- `OCR kiểm thử` — xem chi tiết kết quả OCR thô (trang debug nội bộ).

## Kiểm thử

```powershell
python -m pytest -q
```

## Deploy

Ứng dụng chỉ cần host phần Streamlit UI — OCR và reasoning đều gọi API ngoài (Mistral, Kimi), không cần GPU riêng. Bản public: [invoicereferee.streamlit.app](https://invoicereferee.streamlit.app/) (Streamlit Community Cloud).

## Tài liệu

- `docs/ACCOUNTING_AGENT_REQUIREMENTS.md` - yêu cầu bài toán kế toán đã chốt.
- `docs/PRODUCT_SPEC.md` - chức năng sản phẩm trong Sprint 1.
- `docs/POLICY.md` - policy thực thi v1 và ranh giới quyết định.
- `docs/DATA_MODEL.md` - hợp đồng lược đồ giữa các mô-đun.
- `docs/DECISION_FLOW.md` - luồng từ đầu vào đến quyết định.
- `docs/AGENT_WORKFLOW.md` - workflow chi tiết, điều kiện và ranh giới giữa mã tất định, tool, LLM và con người.
- `docs/WORKFLOW_DIAGRAMS.md` - ba sơ đồ dễ đọc: Data Flow, Business Workflow và Agent Workflow.
- `docs/TEST_CASES.md` - bộ kiểm thử tối thiểu 15 trường hợp.
- `docs/ARCHITECTURE.md` - mô-đun, giao diện và phạm vi phụ trách.
- `docs/EVALUATION_PLAN.md` - kiểm thử dữ liệu mới, phản hồi người dùng và đo lường.
- `docs/CHALLENGE.md` - ánh xạ với Challenge A.
- `docs/BUILD_LOG.md` - nhật ký phát triển.

## Chạy và kiểm tra

### Giao diện nộp hồ sơ

```powershell
python -m streamlit run app/streamlit_app.py
```

Mở `http://localhost:8501`. Giao diện tiếp nhận hai nhóm dữ liệu:

- chứng từ chính, có thể để trống;
- business context dạng nội dung đề nghị và tài liệu bổ sung.

Sidebar có ba không gian làm việc:

- `Nhân viên`: gửi hồ sơ; Submit tự chạy Source Gate, OCR, Confidence Quality
  Agent khi có candidate rồi đến policy kiểm kê;
- `Kế toán`: xem hai hàng đợi `Đã pass` và `Cần xác minh` cùng reasoning;
- `OCR kiểm thử`: chỉ xem evidence đã được Mistral OCR xử lý, gồm văn bản,
  confidence theo từng từ, ảnh có bounding box, cấu trúc
  `page -> block -> words` cùng JSON thô. Đây là trang debug tạm thời.

Hồ sơ đã tiếp nhận được lưu cục bộ trong `data/submissions/{case_id}`. Thư mục
này bị Git bỏ qua vì có thể chứa dữ liệu nhạy cảm. Kết quả OCR debug được lưu
trong `data/submissions/{case_id}/ocr/{evidence_id}.json`; quyết định và
reasoning được lưu trong `data/submissions/{case_id}/processing.json`.

Confidence Gate mặc định gom các block có meaningful word dưới `0.85` theo
từng evidence. Mỗi evidence có candidate được gửi trong **một lần gọi Kimi
riêng**; payload chỉ chứa OCR text và candidate block của chính evidence đó,
không chứa business context hoặc chứng từ khác. Confidence Quality Agent chỉ
đánh giá chất lượng đọc, trả `requires_verification` và khuyến nghị `CONTINUE`
hoặc `ASK_HUMAN`; nó không kiểm tra thiếu trường, policy hay xung đột đa nguồn.
Với bill ăn uống, tên món sai vài ký tự không chặn nếu vẫn nhận diện chắc ý nghĩa.
Có thể đổi ngưỡng bằng `OCR_WORD_REVIEW_THRESHOLD` trong `.env`.

Code tạo Quality Gate riêng cho từng evidence. Thông tin chưa rõ thuộc field cần
cho đối chiếu như MST người mua, tên hàng, số lượng, đơn vị, đơn giá, thành tiền,
tổng tiền hoặc trạng thái nhận hàng sẽ dừng hồ sơ để kế toán xác nhận. Field chưa rõ nhưng nằm
ngoài policy kiểm kê hiện tại, chẳng hạn thuế suất, được giữ thành cảnh báo và
không bị Confidence Agent tự diễn giải thành quyết định nghiệp vụ.

Chỉ khi hồ sơ có ít nhất một `SUPPORTING_DOCUMENT` và **tất cả evidence cần
thiết đã CLEAR**, Cross-source Conflict Agent mới được gọi đúng một lần với JSON
gồm OCR text và block context của toàn bộ bill/report. Business context chỉ giúp
hiểu mục đích giao dịch, không được chuyển thành report hoặc nguồn kiểm kê. Agent
trích xuất fact độc lập theo từng file, đề xuất ghép các dòng hàng cùng nghĩa,
liệt kê phép so sánh và xung đột ngữ nghĩa; nó không được tự quyết định
PASS/FAIL. Code kiểm tra coverage, `Decimal`, đơn vị, source references và các
chênh lệch trước khi tạo kết quả cuối. Hồ sơ không có file hỗ trợ kết thúc sau
Confidence Gate và không chạy policy kiểm kê.

Với `n` evidence có block confidence thấp, số lần gọi Kimi là `n` khi không có
file hỗ trợ, hoặc `n + 1` khi có file hỗ trợ: `n` lần Confidence độc lập và tối
đa `1` lần Conflict. Evidence không có candidate sẽ không gọi Confidence. Mỗi
lần gọi được retry đúng một lần nếu JSON sai schema;
Conflict được gọi sửa thêm một lần nếu bỏ sót document. Bất kỳ Quality Gate nào
bị chặn thì Conflict Agent không chạy. Xung đột số lượng, đơn giá, thành tiền,
trạng thái nhận hàng hoặc xung đột ngữ nghĩa chuyển hồ sơ sang `NEEDS_HUMAN`
với câu hỏi cụ thể cho kế toán.

### Tái cấu trúc confidence OCR

Chuyển danh sách word và block rời rạc của Mistral thành cấu trúc phân cấp
`page -> block -> words`:

```powershell
python scripts/restructure_mistral_ocr.py data/output/page-metadata.json
```

Mặc định, kết quả được ghi vào
`data/output/page-metadata.hierarchical.json`. Dùng `-o <đường-dẫn>` để chọn
file đầu ra khác. Tool hỗ trợ cả JSON camelCase do Mistral xuất và JSON
snake_case được lưu từ Python SDK.

### Kiểm thử phần đã triển khai

```powershell
python -m pytest -q
```

### Verify mục tiêu

Lệnh Verify dưới đây là hợp đồng của giai đoạn tiếp theo và chưa được triển khai:

```bash
python -m verify.harness --suite all
```

Bộ kiểm tra cốt lõi phải có ít nhất:

```text
TC01 → AUTO_PROCESS
TC06 → REQUEST_INFO
TC10 → ESCALATE
TC11 → ESCALATE
```

Giao diện phải cho phép dán/tải lên JSON mới để kiểm thử đầu vào chưa từng thấy qua đúng luồng `review()` dùng trong sản phẩm. Kết quả hiển thị quyết định, loại không chắc chắn, quy tắc không đạt, câu hỏi/đối tượng cần trả lời, cảnh báo trích xuất và lịch sử kiểm toán.

## Trạng thái hiện tại

Dự án đã có giao diện Streamlit tiếp nhận hồ sơ, OCR, Confidence Gate, policy
đối chiếu hóa đơn với phiếu nhập kho/report, hàng đợi kế toán, lưu trữ cục bộ và
audit cơ bản. Các policy nghiệp vụ còn lại, Decision Guard đầy đủ và Verify là
các phần tiếp theo.

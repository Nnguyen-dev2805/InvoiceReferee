# InvoiceReferee

InvoiceReferee is a Sprint 1 prototype for receiving employee expense claims,
reading uploaded evidence, checking OCR quality, and comparing a primary bill
with supporting inventory or receipt evidence.

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

## Bộ case mẫu

📁 [`data/testcase`](data/testcase) — toàn bộ case mẫu dùng để thử nghiệm hệ thống, mỗi case là 1 thư mục:

```text
data/testcase/<tên-case>/
  content/
    content.txt        # dòng 1 = chủ đề, các dòng còn lại = nội dung đề nghị
    attach_file/         # tùy case — tài liệu bổ sung
  evidence/               # chứng từ chính (hóa đơn/bill)
```

Thư mục con [`data/testcase/JUDGEMENT`](data/testcase/JUDGEMENT) là bộ case được chọn để chạy trong trang **Verify** của app.

## Công cụ hỗ trợ

Chuyển kết quả OCR thô của Mistral (word/block rời rạc) thành cấu trúc phân cấp `page -> block -> words`, dùng khi cần xem lại hoặc debug dữ liệu OCR:

```powershell
python scripts/restructure_mistral_ocr.py data/output/page-metadata.json
```

Hồ sơ đã nộp được lưu cục bộ trong `data/submissions/{case_id}` (bị Git bỏ qua vì có thể chứa dữ liệu nhạy cảm).

## Deploy

Ứng dụng chỉ cần host phần Streamlit UI — OCR và reasoning đều gọi API ngoài (Mistral, Kimi), không cần GPU riêng. Bản public: [invoicereferee.streamlit.app](https://invoicereferee.streamlit.app/) (Streamlit Community Cloud).

## Tài liệu

- `docs/ACCOUNTING_AGENT_REQUIREMENTS.md` - yêu cầu bài toán kế toán đã chốt.
- `docs/PRODUCT_SPEC.md` - chức năng sản phẩm trong Sprint 1.
- `docs/POLICY.md` - policy thực thi v1 và ranh giới quyết định.
- `docs/DATA_MODEL.md` - hợp đồng lược đồ giữa các mô-đun.
- `docs/DECISION_FLOW.md` - luồng từ đầu vào đến quyết định.
- `docs/AGENT_WORKFLOW.md` - workflow chi tiết, điều kiện và ranh giới giữa mã tất định, tool, LLM và con người (Confidence Gate, Cross-source Conflict Agent, các ngưỡng liên quan).
- `docs/WORKFLOW_DIAGRAMS.md` - ba sơ đồ dễ đọc: Data Flow, Business Workflow và Agent Workflow.
- `docs/TEST_CASES.md` - bộ kiểm thử tối thiểu 15 trường hợp.
- `docs/ARCHITECTURE.md` - mô-đun, giao diện và phạm vi phụ trách.
- `docs/EVALUATION_PLAN.md` - kiểm thử dữ liệu mới, phản hồi người dùng và đo lường.
- `docs/CHALLENGE.md` - ánh xạ với Challenge A.
- `docs/BUILD_LOG.md` - nhật ký phát triển.

## Trạng thái hiện tại

Đã hoàn thành: nộp hồ sơ, OCR, Confidence Gate, Cross-source Conflict check, hàng đợi Kế toán, trang Verify, deploy public. Chưa triển khai: mô hình quyết định 3 nhánh đầy đủ (`AUTO_PROCESS`/`REQUEST_INFO`/`ESCALATE` với phân loại `OUTSIDE_POLICY`/`BEYOND_AUTHORITY`/`SUSPICIOUS`) và Decision Guard theo đúng `docs/POLICY.md`.

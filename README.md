# InvoiceReferee

**Tác tử kế toán kiểm tra hóa đơn, biên lai và chứng từ chi phí**

InvoiceReferee hỗ trợ kế toán kiểm tra hóa đơn điện tử, hóa đơn/chứng từ do nhân viên chụp và các bằng chứng thanh toán liên quan. Hệ thống trích xuất dữ liệu, chuẩn hóa về một lược đồ chung, chạy các quy tắc nghiệp vụ, áp dụng chính sách nội bộ và trả về một trong ba hành động:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

`AUTO_PROCESS` chỉ có nghĩa là chứng từ đã đủ căn cứ để chuyển sang bước nhập liệu hoặc kiểm tra thanh toán. Hệ thống không tự chuyển tiền và không thay thế quyền phê duyệt cuối cùng của con người.

## Phạm vi Sprint 1

Sprint 1 tập trung vào việc kiểm tra chứng từ chi phí với hai nhóm đầu vào chính:

```text
Hóa đơn điện tử / XML / PDF / ảnh
Chứng từ nhân viên / biên lai / bằng chứng thanh toán
Bằng chứng bổ sung: đơn đặt hàng, biên bản nhận hàng, đề nghị chi,
                    dự án/khách hàng, lịch sử thanh toán
        ↓
Trích xuất + Chuẩn hóa
        ↓
Kiểm tra chính sách / Tính nhất quán / Thẩm quyền
        ↓
AUTO_PROCESS / REQUEST_INFO / ESCALATE
```

Đơn đặt hàng (PO) và biên bản nhận hàng vẫn được hỗ trợ như **bằng chứng bổ sung** cho giao dịch mua hàng hóa, nhưng không còn là phạm vi duy nhất của sản phẩm.

## Bài toán nghiệp vụ

Kế toán cần xử lý nhiều loại chứng từ:

- hóa đơn điện tử có cấu trúc rõ ràng: mã số thuế, bên mua/bán, ngày lập, mẫu số, ký hiệu, số hóa đơn, hàng hóa/dịch vụ và thành tiền;
- hóa đơn/chứng từ do nhân viên chụp: nhà hàng, taxi/Grab, khách sạn, văn phòng phẩm, in ấn, sửa chữa, chuyển khoản ngân hàng/ví điện tử;
- dữ liệu nằm ngoài chứng từ: người chi, mục đích kinh doanh, khách hàng/dự án, đơn đặt hàng, bằng chứng nhận hàng/dịch vụ, lịch sử thanh toán và chính sách nội bộ.

Tác tử phải biết khi nào đã đủ căn cứ, khi nào thiếu thông tin, khi nào vi phạm chính sách, khi nào vượt thẩm quyền và khi nào có dấu hiệu bất thường.

## Ranh giới quyết định

```text
AUTO_PROCESS
  Chứng từ đọc được, đầy đủ trường bắt buộc, số liệu nhất quán,
  đúng công ty/chính sách, không trùng lặp, có bối cảnh kinh doanh
  và nằm trong hạn mức tác tử được phép xử lý.

REQUEST_INFO
  Thiếu trường bắt buộc, OCR/ảnh mờ, thông tin mâu thuẫn,
  chưa rõ mục đích kinh doanh/dự án/người chi, hóa đơn và khai báo khác nhau,
  hoặc chưa đủ bằng chứng nhận hàng/dịch vụ.

ESCALATE
  Dữ kiện đã rõ nhưng nằm ngoài quy định, vượt thẩm quyền,
  hoặc có bất thường/nghi vấn cần con người quyết định.
```

Để giữ Challenge A gọn, hành động hiển thị cho người dùng chỉ gồm ba nhãn trên. Bên trong `ESCALATE` phải phân biệt `OUTSIDE_POLICY`, `BEYOND_AUTHORITY` và `SUSPICIOUS`.

## Luồng hệ thống

```text
Đầu vào thô (JSON/XML/PDF/Ảnh)
  ↓
Bộ chuyển đổi trích xuất
  ↓
Ánh xạ chứng từ chuẩn
  ↓
Chuẩn hóa trường dữ liệu + cảnh báo nguồn
  ↓
Tạo hồ sơ kiểm tra
  ↓
Kiểm tra trường bắt buộc / bối cảnh kinh doanh
  ↓
Chạy các phép kiểm tra tất định
  ↓
Áp dụng chính sách + ràng buộc thẩm quyền
  ↓
Đánh giá của tác tử LLM
  ├── suy luận trên dữ kiện có cấu trúc
  ├── đề xuất loại không chắc chắn/hành động
  ├── tạo câu hỏi cụ thể
  └── giải thích kết quả
  ↓
Bộ bảo vệ quyết định tất định
  ↓
Quyết định cuối cùng + nhật ký kiểm toán
```

LLM là thành phần hỗ trợ suy luận và giao tiếp trên dữ kiện có cấu trúc. Các phép so sánh tiền, số lượng, trùng lặp, trạng thái thanh toán, ngưỡng thẩm quyền và ánh xạ quy tắc vẫn do mã tất định xử lý.

## Các phép kiểm tra cốt lõi

1. Độ đầy đủ của trường bắt buộc theo loại chứng từ.
2. Mã số thuế/tên bên mua có khớp với công ty hay không.
3. Danh tính bên bán/nhà cung cấp và định danh hóa đơn.
4. Tính hợp lệ của ngày và thời hạn nộp chứng từ.
5. Tính nhất quán giữa dòng hàng, số lượng, đơn giá và thành tiền.
6. Số tiền bằng chữ so với số tiền bằng số, nếu có.
7. Trùng lặp hóa đơn, biên lai hoặc bằng chứng thanh toán.
8. Mục đích kinh doanh, nhân viên, khách hàng/dự án.
9. Tính nhất quán giữa biên lai, đề nghị chi và bằng chứng thanh toán.
10. Kiểm tra danh mục theo chính sách: chi phí cá nhân, rượu bia, mặt hàng bị cấm, thiếu mục đích.
11. Bằng chứng nhận hàng/dịch vụ khi được yêu cầu.
12. Ngưỡng thẩm quyền.
13. Cờ bất thường/nghi vấn.

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
cho đối chiếu như tên hàng, số lượng, đơn vị, đơn giá, thành tiền, tổng tiền hoặc
trạng thái nhận hàng sẽ dừng hồ sơ để kế toán xác nhận. Field chưa rõ nhưng nằm
ngoài policy kiểm kê hiện tại, chẳng hạn thuế suất, được giữ thành cảnh báo và
không bị Confidence Agent tự diễn giải thành quyết định nghiệp vụ.

Chỉ khi **tất cả evidence cần thiết đã CLEAR**, Cross-source Conflict Agent mới
được gọi đúng một lần với JSON gồm business context, OCR text và block context
của toàn bộ bill/report. Agent trích xuất fact độc lập theo từng nguồn, đề xuất
ghép các dòng hàng cùng nghĩa, liệt kê phép so sánh và xung đột ngữ nghĩa; nó
không được tự quyết định PASS/FAIL. Code kiểm tra coverage, `Decimal`, đơn vị,
source references và các chênh lệch trước khi tạo kết quả cuối.

Với `n` evidence có block confidence thấp, số lần gọi Kimi bình thường là `n + 1`:
`n` lần Confidence độc lập và `1` lần Conflict. Evidence không có candidate sẽ
không gọi Confidence. Mỗi lần gọi được retry đúng một lần nếu JSON sai schema;
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

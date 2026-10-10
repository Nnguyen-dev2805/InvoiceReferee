# Tổng quan đề tài InvoiceReferee

## 1. Giới thiệu

**InvoiceReferee** là tác tử hỗ trợ kế toán tiếp nhận, đọc và kiểm tra hồ sơ
chi phí. Người dùng chính của hệ thống là:

- **nhân viên** gửi đề nghị thanh toán/hoàn ứng cùng hóa đơn, bill và tài liệu
  liên quan;
- **kế toán** xem những hồ sơ đã qua kiểm tra và những hồ sơ cần con người xác
  nhận.

Mục tiêu của đề tài không phải thay thế kế toán hay tự động thanh toán. Hệ
thống đóng vai trò **cổng kiểm tra trước kế toán**: đọc chứng từ, chỉ ra dữ liệu
không đáng tin cậy, đối chiếu nhiều nguồn khi có đủ tài liệu và đưa vấn đề cụ
thể đến đúng điểm cần con người quyết định.

Trong Sprint 1, hệ thống tập trung vào ba năng lực:

1. Tiếp nhận hồ sơ chi phí có cấu trúc rõ ràng.
2. Kiểm soát chất lượng OCR theo từng chứng từ.
3. Đối chiếu hóa đơn/bill với phiếu nhập kho, phiếu kiểm kê hoặc report đính
   kèm.

## 2. Bài toán cần giải quyết

Quy trình xử lý chi phí thực tế có nhiều loại dữ liệu không đồng nhất:

- hóa đơn điện tử có mẫu số, ký hiệu, số hóa đơn, mã số thuế và bảng hàng hóa;
- bill nhà hàng, taxi, khách sạn, POS hoặc ảnh chụp từ điện thoại;
- phiếu nhập kho, phiếu kiểm kê, biên bản giao nhận và report;
- nội dung nhân viên mô tả mục đích khoản chi, khách hàng hoặc dự án liên quan.

Các vấn đề phổ biến gồm:

- ảnh mờ, OCR sai một phần mã số thuế hoặc số tiền;
- thiếu chứng từ chính hoặc thiếu bối cảnh nghiệp vụ;
- bill và phiếu nhập kho ghi khác số lượng, đơn vị, đơn giá hoặc thành tiền;
- LLM trả kết quả có vẻ hợp lý nhưng sai schema hoặc tự suy đoán dữ kiện;
- kế toán phải đọc lại toàn bộ hồ sơ dù vấn đề chỉ nằm ở một trường cụ thể.

InvoiceReferee giải quyết bài toán bằng cách tách rõ:

- **OCR** dùng để đọc dữ liệu;
- **LLM** dùng để đánh giá ngữ nghĩa hoặc đề xuất ánh xạ;
- **Python rule** dùng để kiểm tra và quyết định;
- **con người** xử lý mọi dữ kiện chưa đủ chắc chắn.

## 3. Phạm vi đầu vào

### 3.1. Chứng từ chính

Chứng từ chính có role `PRIMARY_DOCUMENT`, ví dụ:

- hóa đơn điện tử;
- bill giấy hoặc POS;
- biên lai;
- bằng chứng chi phí chính.

Hồ sơ xử lý tự động phải có ít nhất một chứng từ chính.

### 3.2. Tài liệu hỗ trợ

Tài liệu hỗ trợ có role `SUPPORTING_DOCUMENT`, ví dụ:

- phiếu nhập kho;
- phiếu kiểm kê;
- biên bản giao nhận;
- report hoặc tài liệu xác nhận liên quan.

Tài liệu hỗ trợ có thể không có. Chỉ khi có file hỗ trợ thì hệ thống mới chạy
đối chiếu kiểm kê nhiều nguồn.

### 3.3. Business context

Nhân viên có thể nhập nội dung mô tả khoản chi. Nội dung này chỉ dùng để hiểu
mục đích giao dịch. Nó **không phải bằng chứng kiểm kê**, không được thay thế
phiếu nhập kho và không được tự tạo số lượng hay trạng thái nhận hàng.

## 4. Kiến trúc tổng thể

```text
┌──────────────────────────────────────────────────────────────┐
│                       STREAMLIT UI                           │
│  Nhân viên nộp hồ sơ | Kế toán xem kết quả | OCR kiểm thử   │
└──────────────────────────────┬───────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────┐
│                    APPLICATION SERVICES                      │
│       SubmitCaseService + CaseProcessingService              │
└──────────────┬───────────────────────────────┬───────────────┘
               ↓                               ↓
┌──────────────────────────┐     ┌─────────────────────────────┐
│      EXTRACTION          │     │        POLICY/RULES         │
│ Mistral OCR              │     │ Inventory consistency      │
│ Word/block mapper        │     │ Decimal/unit comparison     │
│ Kimi Confidence Agent    │     │ Source/reference checks     │
│ Kimi Conflict Agent      │     │ PASS/NEEDS_HUMAN            │
└──────────────┬───────────┘     └──────────────┬──────────────┘
               └──────────────────┬─────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────┐
│                       LOCAL STORAGE                          │
│ submission.json | evidence | OCR JSON | processing | audit  │
└──────────────────────────────────────────────────────────────┘
```

Kiến trúc được chia module để có thể thay OCR provider, LLM hoặc storage mà
không phải viết lại toàn bộ workflow.

## 5. Workflow đang được thực thi

```text
Nhân viên gửi hồ sơ
        ↓
Source Gate
        ├─ Không có chứng từ chính → NEEDS_HUMAN
        └─ Đủ nguồn tối thiểu
                ↓
OCR độc lập từng file
        ├─ File lỗi/không đọc được → NEEDS_HUMAN
        └─ OCR thành công
                ↓
Tái cấu trúc page → block → words
                ↓
Lọc word confidence < 0.85 và gom theo block
                ↓
Kimi Confidence Quality Agent (mỗi file một lần nếu có candidate)
        ├─ Field quan trọng không rõ → NEEDS_HUMAN
        └─ Chất lượng đủ dùng
                ↓
Có SUPPORTING_DOCUMENT?
        ├─ Không
        │    └─ PASS theo phạm vi chất lượng OCR
        │       Không gọi Conflict Agent
        │       Không chạy policy kiểm kê
        │
        └─ Có
             ↓
      Tất cả file phải CLEAR
             ↓
      Kimi Cross-source Conflict Agent
      - trích xuất facts độc lập theo file
      - đề xuất ghép dòng hàng cùng nghĩa
      - đề xuất comparisons/conflicts
             ↓
      Python Inventory Policy
      - kiểm tra coverage và source reference
      - so sánh nhà cung cấp, ngày, trạng thái
      - so sánh số lượng, đơn vị, đơn giá, thành tiền
             ├─ Có FAIL/ERROR → NEEDS_HUMAN
             └─ Không có lỗi  → PASS
```

### Ý nghĩa của kết quả hiện tại

| Kết quả | Ý nghĩa |
| --- | --- |
| `PASS` | Hồ sơ đã qua các gate Sprint 1 đang áp dụng. Không đồng nghĩa đã hợp lệ toàn bộ về thuế và chính sách công ty. |
| `NEEDS_HUMAN` | Có nguồn thiếu, OCR lỗi, thông tin quan trọng chưa rõ, agent lỗi hoặc dữ liệu giữa các file mâu thuẫn. |
| `WARN` | Có điểm chưa rõ nhưng không chặn policy đang chạy; cảnh báo vẫn được lưu cho kế toán. |

## 6. Vai trò của từng thành phần

| Thành phần | Loại xử lý | Trách nhiệm |
| --- | --- | --- |
| Source Gate | Hardcode | Kiểm tra chứng từ chính và business context tối thiểu. |
| Mistral OCR | Tool/API | Đọc text, block, bounding box và confidence. |
| Word-block mapper | Hardcode | Tạo cấu trúc `page -> block -> words`. |
| Confidence threshold | Hardcode/config | Chọn word dưới ngưỡng mặc định `0.85`. |
| Confidence Quality Agent | Kimi LLM | Đánh giá block confidence thấp còn sử dụng an toàn hay cần xác nhận. |
| Quality Gate | Hardcode | Chuyển đánh giá LLM thành `PASS`, `WARN` hoặc finding chặn. |
| Conflict Agent | Kimi LLM | Trích xuất facts và đề xuất ánh xạ giữa các file đã rõ. |
| Inventory Policy | Hardcode | Xác minh phép so sánh bằng số, đơn vị và reference. |
| Kế toán | Human-in-the-loop | Xác nhận dữ liệu mờ, xử lý mâu thuẫn và quyết định nghiệp vụ cuối. |

LLM không được tự quyết định hồ sơ pass hay fail. Mọi kết quả LLM được validate
bằng Pydantic; nếu sai schema, hệ thống gửi lỗi cụ thể để model sửa một lần. Nếu
vẫn sai, hồ sơ được chuyển sang `NEEDS_HUMAN`.

## 7. Confidence Quality Gate

Mistral OCR cung cấp confidence theo word. Hệ thống lấy các word dưới ngưỡng,
gom chúng vào block chứa word và gửi toàn bộ candidate block của một evidence
trong một lần gọi Kimi.

Confidence Agent chỉ trả lời về chất lượng đọc:

- `READABLE`: vẫn đọc được đầy đủ;
- `SEMANTICALLY_READABLE`: chữ có thể sai nhẹ nhưng ý nghĩa vẫn chắc chắn;
- `UNCERTAIN` hoặc `UNREADABLE`: không thể dùng an toàn;
- `UNKNOWN`: chưa đủ căn cứ đánh giá.

Các field đang chặn workflow khi cần xác nhận gồm:

```text
seller_name, seller_tax_code, buyer_tax_code,
invoice_date, invoice_number,
item_name, quantity, unit, unit_price,
line_amount, total_amount, receipt_status
```

Ví dụ:

- `Helineken` vẫn nhận diện được là tên mặt hàng: có thể tiếp tục;
- `Chúc quý khách ngon miệng` mờ: không ảnh hưởng nghiệp vụ;
- MST người mua `0317L_688`: phải hỏi kế toán;
- tổng tiền thiếu một chữ số: phải hỏi kế toán.

## 8. Đối chiếu kiểm kê

Conflict Agent chỉ chạy khi có cả chứng từ chính và ít nhất một file hỗ trợ,
đồng thời tất cả file đều đã qua Confidence Gate.

LLM thực hiện các việc khó hardcode:

- nhận dạng loại tài liệu có bố cục đa dạng;
- trích xuất facts theo từng evidence;
- nhận biết hai tên hàng diễn đạt khác nhau nhưng cùng nghĩa;
- đề xuất các cặp dòng hàng cần so sánh;
- mô tả xung đột ngữ nghĩa.

Python policy xác minh:

- mỗi evidence phải có đúng một `document_facts`;
- source reference phải thuộc file thật trong hồ sơ;
- nhà cung cấp/MST giữa hai nguồn;
- chênh lệch ngày tối đa 7 ngày;
- trạng thái nhận hàng;
- số lượng sau quy đổi đơn vị;
- đơn giá và thành tiền với sai số tối đa 1 VND;
- dòng hàng bị thiếu hoặc ánh xạ không hợp lệ.

Description của nhân viên không được dùng làm report. Policy cũng bỏ qua mọi
xung đột hoặc item có nguồn `EMPLOYEE_CLAIM`/`TEXT_REPORT`, kể cả khi LLM trả
sai quy tắc này.

## 9. Human-in-the-loop

Con người nằm ở cuối mỗi gate không chắc chắn:

1. Thiếu bill: nhân viên/kế toán bổ sung chứng từ.
2. OCR không đọc được: cung cấp ảnh rõ hơn hoặc kế toán đọc thủ công.
3. Field quan trọng không rõ: kế toán xác nhận đúng trường được nêu.
4. Hai nguồn mâu thuẫn: kế toán nhận câu hỏi có số liệu và file liên quan.
5. Agent/API lỗi: hệ thống không đoán kết quả, hồ sơ chuyển xử lý thủ công.

Reasoning hiển thị cho kế toán dùng ngôn ngữ nghiệp vụ, không đưa candidate ID,
confidence score hay thuật ngữ OCR vào câu hỏi nếu không cần thiết.

## 10. Cấu trúc mã nguồn

```text
app/
├── streamlit_app.py              # Điểm chạy giao diện
├── components/                   # Sidebar, form, bbox overlay
└── views/                        # Nhân viên, kế toán, OCR debug

src/invoice_referee/
├── application/
│   ├── submit_case.py            # Validate và lưu hồ sơ
│   └── process_case.py           # Điều phối workflow
├── domain/
│   ├── submission.py             # Model tiếp nhận
│   └── processing.py             # Model kết quả/agent
├── extraction/
│   ├── mistral_ocr.py            # Adapter Mistral OCR
│   ├── word_block_mapper.py      # Ghép word vào block
│   ├── confidence.py             # Chọn low-confidence candidate
│   ├── kimi_reasoning.py         # Adapter Kimi + validate/retry
│   └── conflict_reasoning.py     # Prompt Conflict Agent
├── policy/
│   └── inventory.py              # Policy kiểm kê tất định
└── storage/
    ├── local_case_store.py       # Lưu hồ sơ
    └── local_evidence_repository.py

tests/
├── unit/                         # Test rule, adapter, storage, UI helper
└── integration/                  # Test Streamlit
```

## 11. Lưu trữ và audit

Mỗi hồ sơ được lưu tại:

```text
data/submissions/<case_id>/
├── submission.json
├── evidence/
├── ocr/<evidence_id>.json
├── processing.json
└── audit.jsonl
```

Kết quả giữ `rule_id`, `message` và `source_refs` để kế toán có thể truy lại
nguồn của nhận định. Evidence và kết quả OCR không được commit lên Git vì có
thể chứa dữ liệu nhạy cảm.

## 12. Cấu hình và chạy dự án

### Yêu cầu

- Python 3.12;
- API key Mistral OCR;
- token/secret/base URL của Kimi-K3.

Các biến môi trường cần cấu hình trong `.env`:

```dotenv
MISTRAL_API_KEY=...
KIMI_TOKEN=...
KIMI_SECRET=...
KIMI_BASE_URL=...
KIMI_MODEL=moonshotai/Kimi-K3
OCR_WORD_REVIEW_THRESHOLD=0.85
```

Không commit secret hoặc API key lên repository.

### Cài dependencies

```powershell
cd "D:\NguyenHoangHa_nam4\MLAI\Accounting Agent\code\document\InvoiceReferee"

$python = "C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe"
& $python -m pip install -r requirements.txt
```

### Chạy Streamlit

```powershell
& $python -m streamlit run app/streamlit_app.py
```

Mở `http://localhost:8501`.

### Chạy test

```powershell
& $python -m pytest -q
```

## 13. Giao diện đã xây dựng

### Tab Nhân viên

- nhập nội dung đề nghị;
- tải chứng từ chính;
- tải nhiều tài liệu hỗ trợ;
- submit và tự động chạy workflow;
- evidence được phép để trống ở UI, nhưng Source Gate sẽ yêu cầu bổ sung khi
  hồ sơ không đủ căn cứ.

### Tab Kế toán

- xem hàng đợi hồ sơ `PASS` và `NEEDS_HUMAN`;
- xem summary, reasoning và findings;
- xem chi tiết Confidence/Conflict Analysis;
- xóa hồ sơ cùng toàn bộ artifact liên quan.

### Tab OCR kiểm thử

- xem các hồ sơ đã chạy OCR;
- xem markdown OCR;
- xem cấu trúc block và word confidence;
- hiển thị ảnh kèm bounding box;
- xem JSON thô phục vụ debug.

Tab OCR kiểm thử là công cụ nội bộ và dự kiến bỏ khỏi bản chính thức.

## 14. Những gì đã thực hiện được

| Hạng mục | Trạng thái |
| --- | --- |
| UI tiếp nhận hồ sơ và phân vai evidence | Đã thực hiện |
| Validate định dạng, kích thước, số lượng và file trùng | Đã thực hiện |
| OCR ảnh/PDF bằng Mistral | Đã thực hiện |
| Lưu text, block, bbox và word confidence | Đã thực hiện |
| Tái cấu trúc `page -> block -> words` | Đã thực hiện |
| Confidence Gate theo từng evidence | Đã thực hiện |
| Kimi Confidence Agent với JSON schema | Đã thực hiện |
| Chặn MST người mua/số tiền/dữ kiện quan trọng không rõ | Đã thực hiện |
| Tách luồng có và không có supporting file | Đã thực hiện |
| Kimi Cross-source Conflict Agent | Đã thực hiện |
| Retry có validation error cụ thể khi JSON sai schema | Đã thực hiện |
| Policy kiểm kê bằng Python | Đã thực hiện |
| Hàng đợi kế toán và reasoning | Đã thực hiện |
| Lưu hồ sơ cục bộ và audit cơ bản | Đã thực hiện |
| Test unit và integration | Đã thực hiện |

## 15. Những phần chưa hoàn thành

Các nội dung sau đã được thiết kế trong tài liệu policy nhưng chưa được enforce
đầy đủ trong pipeline hiện tại:

- xác minh MST người mua có thuộc đúng công ty;
- kiểm tra hóa đơn trùng với lịch sử;
- kiểm tra vendor master;
- kiểm tra số học nội bộ hóa đơn và số tiền bằng chữ;
- danh mục chi phí cá nhân, rượu bia hoặc mặt hàng bị cấm;
- thời hạn nộp chứng từ;
- hạn mức phê duyệt và vượt thẩm quyền;
- phát hiện bất thường/gian lận;
- Policy Agent tổng quát và `PolicyContext`;
- Decision Guard đầy đủ;
- ánh xạ `PASS/NEEDS_HUMAN` thành `AUTO_PROCESS/REQUEST_INFO/ESCALATE`;
- chức năng con người ghi đè/dừng quyết định với audit đầy đủ;
- Verify harness một lệnh cho bốn testcase;
- triển khai public URL production;
- tích hợp ERP, thanh toán hoặc ghi sổ tự động.

## 16. Giới hạn và rủi ro

1. Confidence cao không bảo đảm OCR đúng tuyệt đối.
2. LLM có thể sai schema, bỏ sót document hoặc ánh xạ nhầm item.
3. `PASS` khi không có file hỗ trợ chỉ xác nhận chất lượng OCR, chưa xác nhận
   đầy đủ nghiệp vụ.
4. Policy kiểm kê hiện tập trung vào giao dịch hàng hóa; dịch vụ cần bộ rule
   khác.
5. Unit conversion đang hỗ trợ một danh sách đơn vị giới hạn.
6. API bên ngoài có thể rate limit hoặc tạm thời không có worker.
7. Dữ liệu hóa đơn có thông tin nhạy cảm, cần mã hóa, phân quyền và chính sách
   lưu trữ trước khi dùng thật.
8. Chính sách hiện tại là policy giả lập cho Sprint 1, không được xem là tư vấn
   thuế hoặc quy định chính thức của doanh nghiệp.

Nguyên tắc an toàn của hệ thống là **fail closed**: khi không đủ căn cứ hoặc
thành phần kỹ thuật lỗi, hồ sơ không được tự động khẳng định hợp lệ.

## 17. Hướng phát triển tiếp theo

### Giai đoạn 1: hoàn thiện Policy Engine

- Company Profile để kiểm tra MST bên mua;
- Duplicate Store và lịch sử thanh toán;
- policy danh mục chi phí, thời hạn và hạn mức;
- kiểm tra số học hóa đơn;
- `PolicyContext` có phiên bản.

### Giai đoạn 2: Decision Guard

- phân biệt `FACTUAL_UNKNOWN`, `OUTSIDE_POLICY`, `BEYOND_AUTHORITY` và
  `SUSPICIOUS`;
- ánh xạ kết quả sang `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE`;
- không cho LLM tự ghi đè rule tất định;
- thêm thao tác xác nhận/ghi đè của kế toán và audit event tương ứng.

### Giai đoạn 3: khả năng vận hành và đánh giá

- xây Verify harness chạy bốn testcase bằng một lệnh/nút;
- deploy public URL không yêu cầu tài khoản;
- đo thời gian trước/sau quy trình;
- thử nghiệm với người dùng kế toán thực tế;
- ghi nhận phản hồi, bất cập mới và thay đổi sản phẩm có commit chứng minh.

## 18. Kết luận

InvoiceReferee hiện đã hình thành một workflow chạy xuyên suốt từ lúc nhân viên
nộp hồ sơ đến lúc kế toán nhận kết quả. Giá trị chính của giải pháp không nằm ở
việc gọi LLM để “duyệt hóa đơn”, mà ở cách tổ chức nhiều lớp kiểm soát:

```text
OCR đọc dữ liệu
→ LLM đánh giá ngữ nghĩa có giới hạn
→ Python kiểm tra tất định
→ Con người quyết định khi có bất định
```

Thiết kế này cho phép hệ thống xử lý linh hoạt nhiều mẫu bill nhưng vẫn giữ
được khả năng truy vết, kiểm thử và mở rộng thành một Accounting Agent đầy đủ
trong các giai đoạn tiếp theo.

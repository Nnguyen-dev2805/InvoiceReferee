# Review độc lập — 15 Experiments & Environment

Nguồn review: worktree Hoangha tại commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`.
Phạm vi owner `15-experiments-environment` trong `inventory.json`: **3 file**.
Review này chỉ đọc source và ghi báo cáo này; không chạy notebook, không gọi model/LIVE,
không install dependency, không chạy test/build/generator và không sửa source/data/status/plan.

CodeGraph được dùng trước. Hai notebook không được CodeGraph index; graph trả về các
production symbol liên quan như `MistralOcrAdapter`, `KimiReasoningAdapter`,
`SettlementProcessingService` và `build_runtime`. `check_index_coverage` và
generation id không exposed, vì vậy graph coverage là **UNKNOWN**. Với hai `.ipynb`
và `requirements.txt`, review dùng source fallback trực tiếp. Các caller/callee
production chỉ được đọc bounded để phân biệt experiment với runtime.

## Phạm vi đã đọc và tính toàn vẹn

| File | Physical JSON/text lines | Cell/source inventory | SHA-256 tại lúc review | Trạng thái |
| --- | ---: | --- | --- | --- |
| `requirements.txt` | 11 | 11 dependency lines | `1d49aaed98146b65390b31754c96132837684a10ac05580b4fbff3627c6ced81` | FULL |
| `notebooks/easyocr_hoa_don.ipynb` | 399 | 10 cells = 1 markdown + 9 code; 84 code lines | `a2a5c05f69e63981224ef2fd2c654031ad09dde69573f911b4ef7cf086e3e1dd` | FULL |
| `notebooks/test_kimi_vision.ipynb` | 243 | 5 cells = 1 markdown + 4 code; 112 code lines | `3090724230af4fc14a310c1228a49ec87fcbefa8d9c17d5d52324ef58c939841` | FULL |

Tổng cộng đã đọc **13 code cells, 2 markdown cells, toàn bộ notebook metadata và
cấu trúc persisted outputs**, cùng toàn bộ `requirements.txt`. Hash của cả ba file
khớp `inventory.json`.

Persisted outputs được xem ở mức cấu trúc/kích thước, không dump nội dung. EasyOCR
notebook có output text và hai `display_data` chứa ảnh JPEG/PNG đã nhúng; Kimi
notebook có các stream output đã lưu. Những output này chỉ chứng minh notebook từng
được chạy trong một môi trường nào đó; **không phải bằng chứng LIVE/fresh của commit
hiện tại** và review này không dùng nội dung model output để kết luận chất lượng.

<!-- reviewed-file: requirements.txt -->
<!-- reviewed-file: notebooks/easyocr_hoa_don.ipynb -->
<!-- reviewed-file: notebooks/test_kimi_vision.ipynb -->

## Kết luận chính

Ba file này là **experiment/environment artifacts**, không phải implementation
authority của luồng final.

- `requirements.txt` hiện là bản mirror 11 runtime dependency trong
  `pyproject.toml:10-22`; nó **không bổ sung** các dependency tooling mà review 09
  đã nêu (`python-docx`, `reportlab`, `aspose.words`) và cũng **không có
  `easyocr`** cho notebook EasyOCR.
- EasyOCR notebook là một local OCR spike: đọc một ảnh cố định, dùng
  `easyocr.Reader(["vi", "en"], gpu=False)`, cho phép tự tải model, chạy
  `readtext`, hiển thị bounding box và ghi JSON thử nghiệm. Nó không được production
  import/wire.
- Kimi Vision notebook là một direct-vision spike: mã hóa ảnh thành data URL rồi gửi
  trực tiếp vào `chat.completions`, sau đó chỉ `json.loads` và ghi output. Cách
  này khác đáng kể runtime Hoangha hiện tại.
- Runtime Hoangha được wire theo hướng **Mistral OCR → OCR quality gate → Kimi
  structured extraction → schema/document-id/validity checks → matching/policy**.
  Đây là hướng phù hợp hơn để mang sang `final` cho Đề A, vì dữ liệu nghi vấn có
  điểm dừng rõ trước khi đi tiếp.
- Không nên chuyển direct Kimi Vision notebook thành production shortcut. Nếu giữ,
  nên giữ đúng vai trò benchmark/research baseline.

## 1. Từng file

| File | Vai trò | Input → Output | Hàm/call chính, caller/callee | Hành vi lỗi | Khả năng dùng lại |
| --- | --- | --- | --- | --- | --- |
| `requirements.txt` | Danh sách dependency cài đặt kiểu pip | package spec → Python environment | Không có caller trong code; nội dung hiện tương ứng dependency runtime trong `pyproject.toml` | Không mô tả optional/experiment deps; clean install từ file này không đủ cho EasyOCR notebook hoặc generator/QA tooling | **Không nên làm authority thứ hai**; nếu cần experiment env, tách optional extra/requirements riêng |
| `notebooks/easyocr_hoa_don.ipynb` | Thử OCR local trên một hóa đơn điện tử | `data/image/Hoa_don_dien_tu.jpg` → EasyOCR regions, text/boxes/confidence, annotated image, `data/output/Hoa_don_dien_tu.easyocr.json` | Notebook cells gọi PIL + `easyocr.Reader.readtext`; không có production caller; scoped search không tìm import/reference notebook/EasyOCR trong `app/src/tests/scripts` | Thiếu ảnh → assert; sai cwd → RuntimeError; dependency/model/network có thể fail; file/model/output được ghi vào `data/` | **Research only**; có thể dùng làm baseline local OCR sau khi có adapter + reproducible model provisioning |
| `notebooks/test_kimi_vision.ipynb` | Thử direct multimodal extraction từ ảnh | ảnh + `.env` Kimi config → direct chat completion → JSON file | Notebook tự tạo `OpenAI` client; không gọi `KimiReasoningAdapter`; không có production caller | thiếu root/config/ảnh → fail sớm; API/network/model errors propagate; JSON không parse → ValueError; JSON parse được nhưng sai semantics vẫn được ghi | **Benchmark only**; không transplant trực tiếp vào final |

## 2. `requirements.txt`: nó thực sự chứa gì?

`requirements.txt:1-11` chứa đúng 11 nhóm package:

`fastapi`, `jinja2`, `streamlit`, `pydantic`, `python-dotenv`,
`python-multipart`, `mistralai`, `openai`, `Pillow`, `PyMuPDF`,
`uvicorn[standard]`.

`pyproject.toml:10-22` khai báo cùng tập dependency và cùng constraint. Vì vậy
nhận định của review 09 cần được hiểu chính xác:

> `requirements.txt` **không giải quyết** dependency gap của generator/QA.

Hai generator import `docx` và `reportlab`; QA import `aspose.words`.
Các package đó không có trong `requirements.txt` cũng như `pyproject.toml`.
Notebook EasyOCR còn thêm một gap riêng: source tạo `easyocr.Reader`
(`notebooks/easyocr_hoa_don.ipynb:119-123`) nhưng `easyocr` không nằm trong
`requirements.txt:1-11`.

Điểm tích cực là runtime dependency list hiện chưa drift so với `pyproject.toml`.
Rủi ro là repo có hai nơi mô tả cùng runtime environment nhưng không có cơ chế trong
ba file này buộc chúng đồng bộ.

## 3. EasyOCR notebook — cơ chế thật

Notebook ghi rõ mục tiêu “Đọc thử hóa đơn điện tử bằng EasyOCR” và yêu cầu kernel
Python của `.venv12` (JSON line 7 trở đi). Metadata notebook ghi kernel display name
`Python 3.12 (.venv12 EasyOCR)` và Python `3.12.6`.

### 3.1 Resolve project và input

Cell setup:

1. import `PIL`, `IPython.display`, `easyocr`;
2. tìm project root bằng cách kiểm `data/` ở cwd hoặc parent;
3. dùng ảnh cố định
   `data/image/Hoa_don_dien_tu.jpg` (`ipynb:64`);
4. tạo `data/models/easyocr` (`ipynb:65-66`);
5. assert ảnh tồn tại.

Cell này còn hard-code:

`EXPECTED_ENV = D:\NguyenHoangHa_nam4\Internship\HitekLab\.venv12`
(`ipynb:55`).

Biến này chỉ được print, không dùng để validate interpreter. Vì vậy nó là dấu vết
môi trường Windows của tác giả, không phải runtime contract.

### 3.2 Model và OCR

Reader được tạo với:

- languages = `["vi", "en"]`;
- `gpu=False`;
- model storage dưới repo;
- `download_enabled=True`
  (`ipynb:119-123`).

Sau đó `reader.readtext(... detail=1, paragraph=False, mag_ratio=1.5)`
(`ipynb:212-216`) trả các tuple dạng:

`(bounding_box, text, confidence)`.

Notebook dùng confidence theo hai cách:

- text in ra ở bước “VĂN BẢN GỘP” chỉ lấy region
  `confidence >= 0.20` (`ipynb:292`);
- overlay tô xanh nếu `confidence >= 0.70`, còn lại màu cảnh báo
  (`ipynb:321`).

Hai threshold này là **experiment display heuristics**. Không có evidence trong
notebook rằng 0.20 hay 0.70 đã được calibration cho Đề A.

### 3.3 Output JSON

Notebook ghi `data/output/Hoa_don_dien_tu.easyocr.json`
(`ipynb:345`) với:

- source file;
- languages;
- total region count;
- `full_text`;
- từng item gồm bbox/text/confidence;
- `json.dump(... ensure_ascii=False, indent=2)`
  (`ipynb:345-364`).

**Ví dụ minh họa, không phải persisted output thật:**

```json
{
  "source_file": ".../Hoa_don_dien_tu.jpg",
  "languages": ["vi", "en"],
  "total_regions": 2,
  "full_text": "CÔNG TY A\nTổng tiền 120.000",
  "items": [
    {
      "bbox": [[10, 20], [200, 20], [200, 50], [10, 50]],
      "text": "CÔNG TY A",
      "confidence": 0.93
    }
  ]
}
```

Đây chưa phải DTO production: không có `document_id`, role, source-ref chuẩn,
page/block hierarchy, word-level confidence contract hay trạng thái review.

## 4. Kimi Vision notebook — cơ chế thật

Notebook này **không dùng Mistral OCR** và cũng không dùng
`KimiReasoningAdapter`.

### 4.1 Config và input

`find_project_root()` yêu cầu một ancestor vừa có `.env` vừa có `data/`.
Notebook sau đó gọi `load_dotenv(ENV_PATH, override=True)`
(`notebooks/test_kimi_vision.ipynb:56`) rồi đọc:

- `KIMI_TOKEN`;
- `KIMI_SECRET`;
- `KIMI_BASE_URL`;
- `KIMI_MODEL`
  (`ipynb:58-69`).

Thiếu field nào thì raise `RuntimeError` (`ipynb:63-74`). Ảnh đầu vào vẫn là
`data/image/Hoa_don_dien_tu.jpg`.

Ảnh được base64 và nhúng thành `data:<mime>;base64,...`; client là
`OpenAI(base_url=..., api_key=f"{token}.{secret}")`
(`ipynb:101-106`).

### 4.2 Model call

Cell model call dùng `client.chat.completions.create`
(`ipynb:161`) và gửi hai phần:

1. system prompt yêu cầu chỉ trích xuất thứ nhìn thấy, không suy đoán;
2. user content gồm prompt text + `image_url` là data URL
   (`ipynb:161-198`).

Prompt yêu cầu JSON với các field:

`seller_name, seller_tax_code, buyer_name, buyer_tax_code, invoice_date,
template_number, serial_number, invoice_number, items, total_amount,
amount_in_words, extraction_warnings`.

Sampling config là `temperature=0.1`, `max_tokens=4096`, `top_p=0.95`,
`stream=False` (`ipynb:191-194`).

### 4.3 Validation/output

Notebook lấy `completion.choices[0].message.content`, in trực tiếp response,
rồi chỉ làm:

```python
parsed_output = json.loads(response_text)
```

Nếu parse JSON fail thì raise `ValueError`; nếu parse được thì ghi thẳng
`data/output/Hoa_don_dien_tu.kimi.json`
(`ipynb:215-224`).

**Ví dụ minh họa, không phải persisted model output:**

```json
{
  "seller_name": "CÔNG TY A",
  "seller_tax_code": "0100000000",
  "invoice_number": "000123",
  "total_amount": 120000,
  "items": [],
  "extraction_warnings": []
}
```

Một object như trên chỉ cần là JSON hợp lệ để notebook chấp nhận. Notebook không có
Pydantic schema, không kiểm document identity, không kiểm tổng tiền, không kiểm
source refs, không có repair loop và không ép uncertainty gate.

## 5. Khác biệt với runtime Hoangha đang wire

Đây là phần quan trọng nhất khi quyết định có mang experiment sang `final` hay không.

### 5.1 Runtime OCR

`MistralOcrAdapter.process()` đọc image/PDF, tạo data URL và gọi Mistral OCR với:

- `include_blocks=True`;
- `confidence_scores_granularity="word"`;
- timeout 120s
  (`src/invoice_referee/extraction/mistral_ocr.py:53-84`).

`app/web/runtime.py:28-71` tạo `MistralOcrAdapter` khi document pipeline bật và có
`MISTRAL_API_KEY`, đồng thời tạo `KimiReasoningAdapter` nếu Kimi config đầy đủ.
Hai adapter được truyền vào `SettlementProcessingService`.

### 5.2 Runtime quality gate trước extraction

`SettlementProcessingService._process_documents()`
(`src/invoice_referee/application/process_settlement.py:240-533`) làm theo thứ tự:

1. thiếu OCR adapter → tạo finding `SET_QUALITY_001 FAIL`;
2. thiếu reasoning adapter → `SET_EXTRACTION_001 FAIL`;
3. OCR từng document;
4. lưu raw OCR artifact;
5. restructure thành page/block/word hierarchy;
6. collect low-confidence blocks;
7. nếu có candidate, Kimi đánh giá confidence;
8. nếu bất kỳ quality finding nào FAIL, **return trước extraction**;
9. chỉ sau khi mọi file qua quality gate mới gọi
   `extract_paper_settlement` hoặc `extract_expense_document`;
10. kiểm `document_id` model trả về phải khớp nguồn;
11. chạy deterministic validity;
12. chỉ fact đủ điều kiện mới đi vào matching.

Đây là khác biệt kiến trúc lớn so với direct Kimi Vision notebook.

### 5.3 Runtime Kimi có schema + bounded repair

`KimiReasoningAdapter._analyze()`
(`src/invoice_referee/extraction/kimi_reasoning.py:412-482`) gửi **JSON payload text**
vào model, parse thành model type cụ thể, chạy validator nếu có, và nếu invalid thì
cho **một repair attempt có bounded context**. Sau hai response invalid, nó raise
`KimiResponseError`.

`analyze_confidence()` còn kiểm mỗi `candidate_id` phải được model đánh giá đúng
một lần (`kimi_reasoning.py:484-528`).

Với settlement extraction:

- `extract_expense_document()` → `ExpenseDocumentFacts`;
- `extract_paper_settlement()` → `PaperSettlementFacts`
  (`kimi_reasoning.py:552-572`).

**Ví dụ minh họa runtime payload, không phải artifact thật:**

```json
{
  "case_id": "CASE-001",
  "document_id": "DOC-002",
  "filename": "invoice.pdf",
  "role": "EXPENSE_EVIDENCE",
  "ocr_text": "..."
}
```

Model tạo facts; code quyết định facts có được chấp nhận để đi tiếp hay không.

## 6. Model quyết định gì, code quyết định gì, con người quyết định gì?

### EasyOCR experiment

**Model/library quyết định**

- vùng text;
- text nhận dạng;
- confidence của mỗi region.

**Code notebook quyết định**

- chạy CPU;
- phóng ảnh với `mag_ratio=1.5`;
- ngưỡng 0.20 khi gộp text để hiển thị;
- ngưỡng 0.70 để chọn màu overlay;
- nơi lưu model/output.

**Con người**

- nhìn ảnh/overlay/text và tự đánh giá kết quả.

Notebook không có workflow escalation.

### Direct Kimi Vision experiment

**Model quyết định**

- toàn bộ giá trị business fields được trích từ ảnh;
- nội dung `extraction_warnings`.

**Code notebook quyết định**

- model endpoint/config;
- prompt;
- sampling;
- chỉ chấp nhận điều kiện cú pháp: response phải parse được JSON.

**Con người**

- tự đọc response/notebook output; không có explicit HITL contract.

### Runtime Hoangha

**Model**

- OCR service nhận dạng text/word confidence;
- Kimi đánh giá low-confidence candidates và structured facts.

**Code**

- chọn candidate theo threshold đã cấu hình;
- fail closed khi thiếu service hoặc quality fail;
- schema validation/repair boundary;
- document-id consistency;
- validity;
- matching score/rule/policy;
- quyết định có tự đi tiếp hay phải tạo finding.

**Con người**

- xử lý những finding/question được target tới accountant/reviewer khi factual
  uncertainty hoặc điều kiện khác cần can thiệp.

Đây là phân quyền phù hợp với yêu cầu Đề A hơn notebook: brief yêu cầu không khẳng
định dữ liệu đã bị gắn nghi vấn, phải dừng đúng lúc và đưa câu hỏi cụ thể cho người
xử lý (`docs/Challenge_Brief_OrganizationAI_VN.docx.md:41-59`).

## 7. Findings

### F15-01 — MUST FIX nếu muốn clean/reproducible experiment: dependency contract thiếu EasyOCR và tooling deps

**Source-verified.**

**Trigger:** clone sạch, cài từ `requirements.txt` hoặc package metadata rồi mở
EasyOCR notebook / chạy generator / QA.

**Wrong behavior:** runtime app dependencies có thể đủ, nhưng EasyOCR notebook cần
`easyocr`; generator cần `python-docx` + ReportLab; QA cần `aspose.words`.
Các package này không được khai báo trong `requirements.txt:1-11` hay
`pyproject.toml:10-22`.

**Evidence:** notebook tạo `easyocr.Reader` tại `ipynb:119-123`; generator/QA
imports đã được source-verified ở review 09. `requirements.txt` chỉ có 11 runtime
packages.

**Impact:** không thể coi `requirements.txt` là “môi trường đầy đủ của repo”.

**Khuyến nghị:** giữ `pyproject.toml` làm runtime authority; nếu các experiment/tool
được giữ chính thức, khai báo optional extras hoặc một environment file riêng có
versioning. Không đưa `easyocr` vào production dependencies chỉ vì notebook tồn tại.

### F15-02 — MUST NOT PORT: direct Kimi Vision chấp nhận mọi JSON syntactically valid

**Source-verified mechanism; chưa chạy model để chứng minh một failure cụ thể.**

**Trigger:** model trả JSON hợp lệ nhưng sai field type/thiếu field/sai tổng tiền/sai
document identity hoặc hallucinate một giá trị mà vẫn parse được.

**Wrong behavior:** notebook ghi thẳng object đó thành
`Hoa_don_dien_tu.kimi.json`; không schema validation, validity check, source-ref
check hay escalation boundary (`test_kimi_vision.ipynb:215-224`).

**Production contrast:** `KimiReasoningAdapter` parse Pydantic model + repair bounded
(`kimi_reasoning.py:412-482`); settlement processor kiểm document id và deterministic
validity trước matching (`process_settlement.py:421-533`).

**Impact với Đề A:** nếu transplant notebook path vào final, một response “trông hợp
lệ” có thể bỏ qua cơ chế dừng trên dữ liệu nghi vấn. Đây là trái hướng với yêu cầu
“tuyệt đối không đưa ra kết quả khẳng định đối với dữ liệu đầu vào đã bị gắn cờ
nghi vấn” của brief.

**Khuyến nghị:** giữ notebook làm baseline/research. Nếu muốn đánh giá direct vision,
đưa nó qua cùng canonical DTO + validation + uncertainty gate như runtime; không cho
nó là shortcut bypass Mistral/quality pipeline.

### F15-03 — SHOULD FIX trong experiment: `full_text` hiển thị và `full_text` ghi file có semantics khác nhau

**Source-verified.**

**Trigger:** EasyOCR trả một region có confidence < 0.20.

**Wrong behavior:** cell “VĂN BẢN GỘP” loại region đó
(`easyocr_hoa_don.ipynb:292`), nhưng `ocr_output["full_text"]` lại join **mọi**
region bất kể confidence (`ipynb:352`).

Người so kết quả bằng mắt có thể nghĩ text đã lưu chính là text được notebook
display sau threshold, trong khi không phải.

**Giới hạn:** item-level output vẫn lưu confidence nên dữ liệu gốc không bị mất.
Đây là ambiguity của experiment artifact, không phải bug runtime Hoangha.

### F15-04 — SHOULD FIX cho portability/offline: notebook gắn path Windows và cho phép tải model trong lúc chạy

**Source-verified.**

**Trigger:** chạy EasyOCR notebook trên máy sạch/macOS/Linux hoặc môi trường chấm
không có network/cache.

**Behavior:** notebook print một `EXPECTED_ENV` Windows hard-coded
(`ipynb:55`), đồng thời `download_enabled=True` và đặt model dưới
`data/models/easyocr` (`ipynb:65-66,119-123`).

Path Windows hiện chỉ là informational nên không trực tiếp làm cell fail. Rủi ro thật
là model download/network side effect làm experiment không reproducible/offline.

**Khuyến nghị:** nếu giữ EasyOCR như benchmark, bỏ machine-specific path và pin cách
provision model/cache; Verify final không nên phụ thuộc download tại runtime.

### F15-05 — SHOULD FIX: `load_dotenv(..., override=True)` có thể ghi đè env mà operator đã set

**Source-verified.**

**Trigger:** shell/session đã export Kimi endpoint/model/credential A nhưng project
`.env` chứa config B.

**Behavior:** notebook gọi `load_dotenv(ENV_PATH, override=True)`
(`test_kimi_vision.ipynb:56`), nên process environment bị thay bằng giá trị từ
`.env`.

Trong notebook cá nhân hành vi này có thể tiện; trong runbook/shared benchmark nó làm
provenance khó nhìn hơn. Production `build_runtime` đọc `os.getenv` và không tự
override env theo cách này.

### F15-06 — EVIDENCE LIMIT: persisted notebook outputs không phải test/LIVE evidence

**Source-verified presence; không đánh giá nội dung model output.**

EasyOCR notebook lưu execution counts 3→10 và nhiều stream/display outputs; Kimi
notebook lưu execution counts 7→10 và stream outputs. Review đã xác nhận structure,
MIME/size và digest nhưng không dump nội dung.

Persisted outputs có thể đến từ một execution cũ, môi trường khác, model version khác
hoặc file input khác. Không có run timestamp/provider provenance đủ để biến chúng
thành release evidence. Vì lượt review này không thực hiện execution/LIVE, review này không refresh chúng.

## 8. Tests: cái gì được chứng minh và chưa được chứng minh?

Review này **không chạy test**. Nhận định dưới đây là static source/graph evidence.

### Có test source cho production adapters

`tests/unit/test_mistral_ocr.py` source đã được graph trả về, trong đó:

- kiểm image được base64 và gửi dạng `image_url`;
- kiểm `include_blocks is True`;
- kiểm `confidence_scores_granularity == "word"`;
- kiểm PDF dùng `document_url`;
- kiểm retry một transient socket error.

Điều đó chứng minh intent/test coverage ở adapter boundary; vì review không execute,
không claim test đang GREEN trên commit này.

`tests/unit/test_kimi_reasoning.py` source đã được graph trả về, trong đó có test:

- retry transient error;
- dedicated confidence prompt;
- coverage candidate id;
- repair khi schema sai;
- fail closed sau hai invalid responses.

Đây là bằng chứng production Kimi path có guard mà notebook direct vision không có.

### Không có test source cho hai notebook trong bounded search

Scoped search trên `app src tests scripts pyproject.toml requirements.txt` không tìm
thấy:

- `easyocr`;
- tên hai notebook;
- output filename
  `Hoa_don_dien_tu.easyocr.json` /
  `Hoa_don_dien_tu.kimi.json`.

Với graph không index notebook và coverage UNKNOWN, kết luận được giữ ở phạm vi:

> Trong bounded production/test scope đã kiểm, hai notebook không được import/wire và
> không có automated test trực tiếp.

Không nâng kết luận này thành “toàn repo tuyệt đối không có reference” dựa riêng vào
graph.

### Các test trên không chứng minh

Chúng không chứng minh:

- EasyOCR tốt hơn/kém hơn Mistral trên corpus UC-03;
- direct Kimi Vision chính xác trên hóa đơn thật;
- threshold 0.20/0.70 là tối ưu;
- persisted notebook output là fresh;
- LIVE provider đang hoạt động;
- model generalization/OOD;
- notebook xử lý đúng ambiguity theo Đề A;
- notebook là một phần của final runtime.

Muốn so sánh EasyOCR/Mistral/direct-vision cần một eval riêng trên frozen independent
documents/gold, cùng metric và cùng error taxonomy; không dùng notebook output cũ làm
oracle.

## 9. Nên mang gì sang `final`?

### 9.1 `requirements.txt`

**Không cần merge như một source of truth thứ hai** nếu `final` đã dùng
`pyproject.toml`/lockfile. Nội dung hiện tại chỉ lặp runtime deps.

Nếu team muốn giữ notebook/tooling reproducible, nên tạo **environment boundary**
riêng cho experiments/tooling. Đây là thay đổi packaging/runbook, không phải thay đổi
business policy.

### 9.2 EasyOCR notebook

Giữ như **research artifact / fallback candidate**, không copy thẳng vào pipeline.

Nếu sau này muốn thử local OCR, adapter cần map output vào canonical evidence/OCR
contract của final, tối thiểu:

- stable document/page/block/word ids;
- text + bbox + confidence;
- source refs;
- no runtime model auto-download;
- explicit provider/model/version provenance;
- cùng quality-gate semantics với pipeline final;
- benchmark độc lập trước khi bật.

Không tự thay threshold/policy đã chốt chỉ vì notebook đang dùng 0.20/0.70.

### 9.3 Kimi Vision notebook

Giữ như **direct-vision baseline** để nghiên cứu. Không mang direct call path vào
final hiện tại.

Nếu team muốn đánh giá nó sau này, cần một adapter đứng sau cùng contract:

`document → provider execution artifact → canonical facts DTO → deterministic
validation → uncertainty/escalation`.

Kết quả direct vision phải chịu cùng source identity, amount/field validity,
provenance và human-review gate như Mistral+Kimi path. Không cho model output tự trở
thành business fact chỉ vì JSON parse thành công.

## 10. Liên hệ Đề A cuộc thi

Brief Đề A yêu cầu hệ thống xử lý case thường quy tự động nhưng biết dừng khi:

- chưa xác định được thông tin thực tế;
- ngoài phạm vi quy định;
- vượt thẩm quyền;
- và không khẳng định trên dữ liệu đã bị gắn nghi vấn
  (`docs/Challenge_Brief_OrganizationAI_VN.docx.md:41-59`).

Hai notebook **không tự đáp ứng** contract đó. EasyOCR chỉ cho confidence/overlay;
Kimi Vision chỉ trả JSON. Giá trị của chúng là experiment evidence để chọn thành
phần, không phải workflow Đề A.

Phần đáng mang sang final từ Hoangha là **ranh giới kiến trúc production** đã thấy ở
bounded source:

`OCR → quality evidence → structured extraction → deterministic validation →
matching/policy → human escalation khi cần`.

Nó cho phép model hỗ trợ nhận dạng/trích xuất nhưng code vẫn giữ quyền quyết định xem
dữ kiện có đủ điều kiện đi tiếp hay phải dừng. Khi kết hợp với final, adapter nên
phục vụ contract này và không tự đổi financial rule, policy threshold hoặc authority
đã được final chốt.

## 11. Limits của review

- Không chạy notebook, model, LIVE, test/build/generator/install theo yêu cầu.
- Persisted outputs chỉ được kiểm structure/kích thước/digest; không dump ảnh base64,
  text OCR/model output, credential hay dữ liệu nhạy cảm.
- CodeGraph không index hai notebook; `check_index_coverage`/generation id không
  exposed nên coverage là UNKNOWN.
- Production source chỉ đọc bounded ở adapter/composition/processing/test boundaries
  cần thiết để phân biệt notebook và runtime; report này không claim ownership hay
  full-review các file production đó.
- Các finding về “model có thể trả sai nhưng JSON hợp lệ” là **failure mode suy ra từ
  validation contract**, không phải observed model failure, vì LIVE execution bị cấm.

## Verdict

**READY TO USE AS REVIEW EVIDENCE; NOT READY TO MERGE AS PRODUCTION CODE.**

Trong ba file owner15, không có thành phần nào cần được transplant nguyên trạng vào
`final`. `requirements.txt` chỉ lặp runtime deps và thiếu experiment/tooling deps;
EasyOCR notebook có giá trị làm local OCR baseline; Kimi Vision notebook có giá trị
làm direct-vision baseline. Production integration nên tiếp tục dựa trên canonical
evidence DTO + quality gate + schema/validity + escalation của final/Hoangha runtime,
và chỉ đưa experiment provider vào sau khi có adapter và evaluation độc lập.

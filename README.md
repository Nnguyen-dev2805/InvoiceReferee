# InvoiceReferee

**InvoiceReferee hỗ trợ quyết toán chi phí nhân viên sau khi công việc đã hoàn thành.** Ứng dụng đọc chứng từ (PDF/PNG/JPEG), đối chiếu dữ kiện với dòng tiền, rulebook và quyền được cấp, rồi đưa ra **kết luận có dẫn nguồn** — hoặc nêu rõ đúng chỗ nào cần con người xử lý.

[![Demo trực tiếp](https://img.shields.io/badge/Demo-Railway-0B0D0E?logo=railway&logoColor=white)](https://invoicereferee-production.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Last commit](https://img.shields.io/github/last-commit/Nnguyen-dev2805/InvoiceReferee/main)](https://github.com/Nnguyen-dev2805/InvoiceReferee/commits/main)
[![License](https://img.shields.io/badge/License-Proprietary-red)](#license)

## Demo công khai

Ứng dụng chạy tại **[invoicereferee-production.up.railway.app](https://invoicereferee-production.up.railway.app)**. Context, rulebook và bộ hồ sơ demo đều là **dữ liệu tổng hợp** — không phải chính sách công ty thật, không phải tư vấn pháp lý.

> **⚠️ Chỉ dùng chứng từ giả lập trên demo công khai.** Tenant demo được chia sẻ và persona switcher không phải cơ chế xác thực. Không tải hóa đơn, sao kê ngân hàng hoặc dữ liệu cá nhân thật lên demo cho đến khi có cô lập người dùng. Chế độ LIVE gọi dịch vụ thật (OCR/LLM) và có thể phát sinh phí API.

## InvoiceReferee làm gì?

Một hồ sơ quyết toán đi qua đủ vòng đời: **nhân viên nộp → hệ thống đọc & đối chiếu → kế toán quyết → ghi nhận tiền → đóng hồ sơ**.

- **Nhân viên** tạo hồ sơ, tải chứng từ, khai báo quyết toán (kể cả kê khai điện tử S6: các dòng chi phí gắn đúng trang chứng từ, đúng hash, không advance), xác nhận/hoàn trả chênh lệch.
- **Pipeline đọc chứng từ** chạy OCR + LLM trích xuất, mỗi dữ kiện giữ **trích dẫn chính xác + trang + hộp tọa độ** để con người kiểm tra lại; dữ kiện chưa đọc rõ bị đánh dấu *UNREADABLE* — **không bao giờ coi là 0 hay tự điền**.
- **Workflow Python đối chiếu**: mâu thuẫn số học, tổng dòng chi phí, số tạm ứng − chi phí = hoàn lại, giấy này khớp hóa đơn nào, hồ sơ gắn khoản tạm ứng nào, quyền ai được làm gì (kể cả ngoại lệ chính sách phải có quyền hợp lệ và số tiền đúng server quy định).
- **Kế toán / người có quyền** có workspace riêng: thẻ quyết định, mở ngoại lệ có kiểm soát, phát lệnh chi/thu, ghi nhận tiền đã chuyển (có thể từng phần), xác nhận đủ tiền, đóng hồ sơ thực thi.
- Khi căn cứ đủ → **kết luận + hướng xử lý** có thể thực thi; khi thiếu/mâu thuẫn → **câu hỏi cụ thể + trích dẫn + vai trò** cần trả lời.

AI chỉ hỗ trợ đọc và trích xuất. **Mô hình không cấp quyền, không tự chuyển tiền ngân hàng** — mọi quyết định tài chính và lệnh chi đi qua workflow Python với quy tắc rõ ràng.

## Kiến trúc

| Thành phần | Công nghệ & trách nhiệm |
| --- | --- |
| Giao diện | React 19 + TypeScript 5 + Vite; build tĩnh do FastAPI phục vụ cùng process |
| API / workflow | Python 3.12, FastAPI, Pydantic; workflow + rulebook là code thuần Python |
| Dữ liệu | SQLite (WAL); DB, uploads, OCR artifacts nằm trên volume bền `/data` |
| Đọc chứng từ | Mistral OCR (`mistral-ocr-latest`); LLM trích xuất chọn provider qua `LLM_PROVIDER` |
| Tracing | LangSmith (opt-in, tắt mặc định); trace từng bước OCR→classify→extract→validate→match |
| Deploy | Một Docker image, một Uvicorn process; Railway cung cấp volume + HTTPS |

Kiến trúc cố ý đơn-process + SQLite: đủ cho demo/pilot nhỏ, tránh phức tạp vận hành. Ứng dụng **không tích hợp ngân hàng** và **không tự chuyển tiền** — người dùng chuyển tiền bên ngoài, ứng dụng chỉ ghi nhận và đối chiếu.

## Chế độ làm việc

| Chế độ | Lệnh | Khi nào dùng |
| --- | --- | --- |
| **LIVE** (mặc định) | `scripts/dev.py` | Đọc chứng từ thật qua Mistral OCR + LLM. Thiếu khóa bắt buộc → server dừng rõ ràng, không âm thầm giả lập. |
| **RECORDED_REPLAY** | `scripts/dev.py --mode replay --recording …` (hoặc `--fake-llm-dir …`) | Chạy offline tuần tự từ bản ghi provider; thiếu bản ghi thì đọc miss, không bịa dữ liệu. |
| **STUB** | `scripts/dev.py --mode stub` | Luồng demo offline, không gọi provider nào. |

Cờ hữu dụng của `scripts/dev.py`: `--port`, `--db`, `--uploads`, `--context`, `--demo-as-of` (mốc đối soát cố định cho context SIMULATED).

## Bắt đầu nhanh

### Yêu cầu

- Python **3.12** (khóa trong `.python-version`) và [uv](https://docs.astral.sh/uv/)
- Node **24** + npm (khóa trong `.node-version`, chỉ để build frontend một lần)
- Docker để chạy container (tùy chọn)

### Chạy LIVE

```bash
git clone https://github.com/Nnguyen-dev2805/InvoiceReferee.git
cd InvoiceReferee
cp .env.example .env          # điền khóa provider (xem Cấu hình)
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
uv run python scripts/dev.py --port 8000
```

Mở `http://127.0.0.1:8000`.

### Chạy offline (STUB)

```bash
uv run python scripts/dev.py --mode stub --port 8000
```

### Docker (một process)

```bash
docker build -t invoice-referee .
docker run --rm -p 8000:8000 \
  -v invoice-referee-data:/data \
  --env-file .env \
  invoice-referee
```

Volume `/data` giữ SQLite + uploads + artifacts qua các lần restart. Container dùng chính `scripts/dev.py`, mặc định LIVE; thêm `--mode stub` để chạy offline. Không đưa secret vào image.

## Cấu hình

Tệp `.env.example` hiện liệt kê **tất cả 3 provider LLM**; chỉ điền provider được chọn:

| Biến | Bắt buộc? | Mục đích |
| --- | --- | --- |
| `MISTRAL_API_KEY` | LIVE | Đọc chứng từ (OCR) |
| `MISTRAL_OCR_MODEL` | LIVE | Model OCR (vd `mistral-ocr-latest`) |
| `LLM_PROVIDER` | — | `groq` (mặc định) / `kimi` / `xkiro` |
| `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_MODEL`, `GROQ_REASONING_EFFORT` | nếu groq | LLM trích xuất (mặc định `openai/gpt-oss-20b`) |
| `KIMI_TOKEN`, `KIMI_SECRET`, `KIMI_BASE_URL`, `KIMI_MODEL` | nếu kimi | LLM thay thế (Kimi-K3) |
| `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `INVOICE_REFEREE_LLM_MODEL` | nếu xkiro | LLM thay thế khác |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, … | không | Tracing opt-in — không bao giờ chặn kết luận kinh doanh |

Quy ước: **không commit `.env`**, không đưa secret vào Docker image, và **không bao giờ** lưu quyền/budget/ngân sách công ty trong `.env` — quyền chỉ đến từ company context (xem ADR 0002).

## Kiểm thử & health

```bash
uv run pytest                        # backend: unit + integration
npm --prefix frontend test -- --run  # frontend: vitest
npm --prefix frontend run build      # kiểm tra build production
```

Sức khỏe server: `GET /api/health` — trả về phiên bản + trạng thái cấu hình đã **ẩn thông tin nhạy cảm**.

Kiểm thử chạy offline: chứng từ fixture được phục vụ qua transport stub/replay (`tests/s6_transport.py`), mỗi bài test dùng DB và port riêng, và không bài test nào gọi provider thật. Chi tiết cách tái lập: [RUNBOOK](docs/final/RUNBOOK.md).

## Cấu trúc thư mục

```
src/invoice_referee/
├── api/            # FastAPI routes + request/response views
├── domain/         # DTO lệnh, hồ sơ, kết luận
├── evidence/       # OCR → classify → extract → validate → match (provenance từng dữ kiện)
├── reconciliation/ # đối chiếu số học, admission, advance, policy
├── workflow/       # lệnh, session, phiên bản hồ sơ, tiền, lệnh chi/thu
└── evaluation/     # chấm điểm tự động theo bộ case
frontend/           # React + TypeScript (build vào dist/, FastAPI serve tĩnh)
data/               # company-context demo + bộ chứng từ tổng hợp (kể cả TC01…)
docs/final/         # thiết kế, hợp đồng, runbook, bằng chứng phát hành
```

## Tài liệu

| Tài liệu | Nội dung |
| --- | --- |
| [Kiến trúc & đánh giá](docs/final/ARCHITECTURE_AND_EVALUATION.md) | Thiết kế được chấp nhận, phạm vi Q1–Q31 |
| [Implementation contracts](docs/final/IMPLEMENTATION_CONTRACTS.md) | Hành vi ràng buộc của từng nhánh công việc (§2–§11) |
| [Runbook](docs/final/RUNBOOK.md) | Clone sạch → chạy → pilot công khai; các bẫy môi trường |
| [Trạng thái triển khai](docs/final/IMPLEMENTATION_STATUS.md) | Checkpoint tiến độ + khoảng cách còn lại |
| [ADR](docs/adr/) | Quyết định kiến trúc (mỗi quyết định một file, 0001…) |

## Quy tắc an toàn

- **AI không cấp quyền, không tự chuyển tiền**: chứng từ chỉ thành dữ kiện có dẫn nguồn; hướng xử lý chi/thu do workflow Python quyết, con người xác nhận từng bước.
- **Quyền và ngân sách chỉ đến từ company context** (file SIMULATED demo, nhập vào `context_*` dữ liệu nội bộ); `.env` chỉ chứa thông tin xác thực dịch vụ.
- Dữ kiện OCR chưa rõ **không bao giờ** được coi là 0, bỏ qua hay suy diễn. Hồ sơ còn thiếu → hỏi đúng người đúng vai (nhân viên/kế toán/người có quyền).
- Thất bại provider **lỗi rõ ràng** — không bao giờ âm thầm pha giả lập vào SUCCESS.

## License

Mã nguồn **Proprietary** — xem trường `license` trong [pyproject.toml](pyproject.toml).

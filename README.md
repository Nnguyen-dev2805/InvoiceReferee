# InvoiceReferee

**InvoiceReferee hỗ trợ quyết toán chi phí nhân viên sau hoạt động công việc.** Ứng dụng đọc chứng từ, đối chiếu căn cứ và dòng tiền, rồi đưa ra kết luận có dẫn nguồn hoặc nêu rõ phần cần con người xử lý.

[![Demo trực tiếp](https://img.shields.io/badge/Demo-Railway-0B0D0E?logo=railway&logoColor=white)](https://invoicereferee-production.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Last commit](https://img.shields.io/github/last-commit/Nnguyen-dev2805/InvoiceReferee/main)](https://github.com/Nnguyen-dev2805/InvoiceReferee/commits/main)
[![License](https://img.shields.io/badge/License-Proprietary-red)](pyproject.toml)

## Demo công khai

Ứng dụng đang chạy tại **[invoicereferee-production.up.railway.app](https://invoicereferee-production.up.railway.app)**. Context và rulebook trong demo là dữ liệu tổng hợp, không phải chính sách công ty thật hay tư vấn pháp lý.

> **Chỉ dùng chứng từ giả lập trên demo công khai.** Tenant demo hiện được chia sẻ và persona switcher không phải hệ thống xác thực người dùng. Không tải hóa đơn, chứng từ ngân hàng hoặc dữ liệu cá nhân/thật lên đây cho đến khi có cô lập người dùng. Chế độ LIVE gọi dịch vụ OCR/LLM và có thể phát sinh phí API.

## InvoiceReferee làm gì?

Nhân viên tạo hồ sơ quyết toán và tải lên nhiều chứng từ PDF, PNG hoặc JPEG. Pipeline đọc tài liệu và giữ tham chiếu tới trang/trích dẫn nguồn. Workflow đối chiếu dữ kiện, quan hệ giữa hồ sơ và chứng từ, lịch sử tiền, rulebook demo và quyền được cấp.

- Khi căn cứ đủ, hệ thống tạo kết luận và hướng xử lý chi/thu có thể thực hiện.
- Khi còn thiếu hoặc mâu thuẫn, hệ thống nêu câu hỏi cụ thể, căn cứ liên quan và vai trò cần xử lý.
- Nhân viên, kế toán và người có quyền có workspace riêng. Người dùng thực hiện chuyển tiền bên ngoài ứng dụng; kế toán ghi nhận kết quả và chứng từ trong hồ sơ.

AI hỗ trợ đọc và trích xuất. Workflow Python và các rule kiểm tra quyết định cách dùng dữ kiện; mô hình không tự cấp quyền hoặc chuyển tiền ngân hàng.

## Kiến trúc

| Thành phần | Công nghệ và trách nhiệm |
| --- | --- |
| Giao diện | React, TypeScript, Vite; frontend build tĩnh và được FastAPI phục vụ |
| API và workflow | Python 3.12, FastAPI, Pydantic |
| Dữ liệu | SQLite ở chế độ WAL; DB, uploads và artifacts nằm trên volume bền `/data` |
| Đọc chứng từ | Mistral OCR và provider LLM cấu hình qua X-Kiro |
| Tracing | LangSmith tùy chọn; mặc định tắt trong môi trường local |
| Deploy | Một Docker service, một Uvicorn process; Railway cung cấp volume và HTTPS |

Kiến trúc cố ý chạy một tiến trình với SQLite, phù hợp demo/pilot nhỏ. App không tích hợp ngân hàng và không tự chuyển tiền.

## Chạy local

### Yêu cầu

- Python 3.12 và [uv](https://docs.astral.sh/uv/)
- Node.js 24 và npm
- Docker Compose nếu chạy bằng container

### LIVE mode

```bash
git clone https://github.com/Nnguyen-dev2805/InvoiceReferee.git
cd InvoiceReferee
cp .env.example .env
```

Điền các khóa provider trong `.env`, sau đó cài dependencies, build frontend và chạy server:

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
uv run python scripts/dev.py --port 8000
```

Mở `http://127.0.0.1:8000`. LIVE là chế độ mặc định; nếu thiếu khóa bắt buộc, server dừng rõ ràng thay vì âm thầm chuyển sang giả lập.

### STUB mode

Để chạy luồng demo offline mà không gọi provider, vẫn build frontend như trên rồi chạy:

```bash
uv run python scripts/dev.py --mode stub --port 8000
```

### Docker Compose

Sau khi tạo `.env` và điền khóa nếu chạy LIVE:

```bash
docker compose up --build
```

Compose gắn volume `referee-data` vào `/data` để giữ SQLite và tệp đã tải lên qua các lần restart.

## Cấu hình

Các biến bắt buộc cho LIVE:

| Biến | Mục đích |
| --- | --- |
| `MISTRAL_API_KEY` | Xác thực dịch vụ Mistral OCR |
| `MISTRAL_OCR_MODEL` | Model OCR |
| `XKIRO_API_KEY` | Xác thực provider LLM |
| `XKIRO_BASE_URL` | Base URL của provider LLM |
| `INVOICE_REFEREE_LLM_MODEL` | Model dùng cho phân loại/trích xuất |

Tracing là tùy chọn: đặt `LANGSMITH_TRACING=true` và `LANGSMITH_API_KEY`. Endpoint và project có thể cấu hình bằng `LANGSMITH_ENDPOINT` và `LANGSMITH_PROJECT`. Không commit `.env` hoặc đưa secret vào Docker image.

## Kiểm tra và health

```bash
uv run pytest
npm --prefix frontend test
npm --prefix frontend run build
```

Health endpoint: `GET /api/health`.

## Tài liệu

- [Architecture và evaluation](docs/final/ARCHITECTURE_AND_EVALUATION.md)
- [Implementation contracts](docs/final/IMPLEMENTATION_CONTRACTS.md)
- [Runbook](docs/final/RUNBOOK.md)
- [Test cases](docs/TEST_CASES.md)

## License

Mã nguồn là **Proprietary**. Xem trường `license` trong [pyproject.toml](pyproject.toml).

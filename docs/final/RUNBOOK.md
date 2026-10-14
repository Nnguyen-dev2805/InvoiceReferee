# InvoiceReferee — RUNBOOK (clean clone → public pilot)

Trạng thái: cấu hình/one-entry đã có; **deploy lên hosting công khai và pilot
người thật CHƯA chạy** (xem §5 "Còn thiếu"). Đây là runbook tái lập, không phải
bằng chứng runtime.

## 1. Prerequisites

- Python **3.12** (`.python-version`), resolver **uv**.
- Node **24** (`.node-version`) + npm (chỉ để build frontend một lần).
- (Tuỳ chọn) Docker + compose cho container single-process.
- (Chỉ LIVE) credentials: `MISTRAL_API_KEY`, `MISTRAL_OCR_MODEL`,
  `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `INVOICE_REFEREE_LLM_MODEL`.
  LangSmith là **opt-in**, không bắt buộc.

## 2. Clean clone → chạy mặc định (LIVE)

**Mặc định là LIVE**: server đọc tài liệu bạn upload (Mistral OCR + model). Điền
`.env` trước (xem §3).

```bash
git clone <repo> && cd InvoiceReferee
cp .env.example .env            # điền key để chạy LIVE (xem §3)
uv sync --frozen                # cài đúng uv.lock
npm --prefix frontend ci        # cài frontend
npm --prefix frontend run build # tạo frontend/dist (server phục vụ tĩnh)
uv run python scripts/dev.py --port 8000   # mặc định LIVE
```

Mở `http://127.0.0.1:8000`. Thao tác chính nằm trong <1 phút: chọn hoạt động →
Tạo hồ sơ → đính kèm chứng từ → Nộp hồ sơ → xem yêu cầu/câu hỏi.

Ba chế độ (đều tường minh, không tự hạ cấp):

| Chế độ | Lệnh | Ý nghĩa |
| --- | --- | --- |
| **LIVE** (mặc định) | `scripts/dev.py` | Đọc tài liệu thật; cần key trong `.env`. |
| **STUB** | `scripts/dev.py --mode stub` | Bản ghi tay có sẵn, chạy offline (không cần key). |
| **RECORDED_REPLAY** | `scripts/dev.py --mode replay` | Phát lại bản ghi provider (chưa có recording). |

> Lưu ý: ở LIVE, pipeline chứng cứ đọc xong và dừng ở `EVIDENCE_READY`; phần nối
> chứng cứ → tài chính (`EVIDENCE_ADMISSION_NOT_CONNECTED`) chưa được viết, nên
> LIVE **chưa** phát hành yêu cầu chi/thu. Đường ra kết luận tài chính hiện là STUB.

Kiểm tra health (đã lọc secret):

```bash
curl -s http://127.0.0.1:8000/api/health
```

## 3. Chạy LIVE

Điền `.env` (5 key, xem `.env.example`) rồi chạy mặc định — không cần cờ `--mode`:

```bash
uv run python scripts/dev.py --port 8000
# hoặc tường minh: uv run python scripts/dev.py --mode live --port 8000
```

Thiếu key ⇒ lệnh **dừng (exit 2) và in tên biến thiếu**, không tự hạ cấp. Không có
chế độ giả lập ngầm. Chạy offline để demo/test: thêm `--mode stub`.

## 4. Container (single process, volume bền)

```bash
docker compose build
docker compose up
```

- Ảnh chạy **một** Uvicorn process phục vụ cả API và frontend tĩnh.
- DB + uploads ở volume `/data` (sống qua restart).
- Secret lấy từ `.env` (đã gitignore), không nhúng vào image.
- Healthcheck gọi `/api/health`.

Reset sandbox (xoá dữ liệu local):

```bash
docker compose down -v && docker compose up
```

## 5. Còn thiếu (capability gaps — cần người dùng)

- **Hosting công khai**: chưa được cấp URL/hạ tầng. Bàn giao image + runbook;
  cần: nhà cung cấp hosting, domain/TLS, biến môi trường secret, và (nếu muốn
  LIVE) credentials. **Không dùng localhost để claim public URL.**
- **Pilot người thật**: cần ≥3 practitioner do **người dùng mời** (protocol T2).
  Agent không mời/tạo người tham gia.
- **Calibration10/validation10**: dataset authoring đã có khung (xem
  `data/evaluation`); cần nhãn feedback thật để chốt ngưỡng ở T11.

## 6. Kiểm chứng nhanh (không phải deploy)

```bash
uv run pytest                                   # unit + integration
npm --prefix frontend run build                 # frontend build
npm --prefix frontend exec playwright test      # browser checkpoint (Chromium)
uv run invoice-referee evaluate --suite development --mode stub \
  --output .runtime/evidence/baseline
```

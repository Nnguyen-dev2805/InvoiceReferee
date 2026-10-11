# B6→B7 quyết toán liên kết — walkthrough (chủ dự án kiểm UI)

Lát cắt: từ công việc B3/B5, nhân viên mở **hồ sơ B7 riêng cùng employee/work**,
khai chi phí **thực tế**, kế toán cung cấp **company context có căn cứ**, chạy
cùng pipeline B7 tới report/questions/review. **Report-only: chưa B8/B9, chưa
chi/đóng.** Dùng **fake provider**; không LIVE/Git/publish.

## 0. Đã xác minh trong phiên này (fake, không LIVE)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked.py -q          # 12 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_linked_context.py -q  # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_claim_links.py -q     # 3 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                            # 370 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                       # 790 passed
.venv/bin/python -m pip check                                                                            # No broken requirements found
npm --prefix frontend run test -- --run                                                                  # 122 passed (21 files)
npm --prefix frontend run build                                                                          # tsc --noEmit + vite build OK
```

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**. Fake/structured
fixture xác minh lifecycle; **không** chứng minh OCR/LLM hay bank authentication.

## 1. Khởi động (DB/cổng riêng)

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_DB_PATH=data/settlement/b6-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b6-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```
```bash
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

> B7 rights cần file `SETTLEMENT_B7_CONTEXT_PATH` (schema `b7-company-config-v1`,
> activated+synthetic, grant riêng APR-DEMO-01) — **không** kế thừa B3Grant hay
> P-DEMO. Thiếu file = không có quyền B7 (AUTHORITY issue), không fallback.

## 2. Các bước UI

1. B3 approve (budget8/advance2); B5 ghi nhận receipt2 (xem guide B3/B5).
2. **Employee**: ở panel B3 đã duyệt bấm **“Chuẩn bị hồ sơ quyết toán”** → mở
   child B7 cùng work. Panel **Quyết toán liên kết**: thêm khoản chi thực tế
   (nội dung/ngày/số khai/bên trả khai báo) → **Lưu nháp**; reload giữ work/link.
   Số khai **không** prefill từ forecast.
3. **Employee** bấm **“Xác nhận nộp và đối soát”**.
4. **Run** sau confirm: chưa có company coverage → questions thuộc **ACCOUNTANT**;
   không bắt nhân viên khai RA/P/RP=0.
5. **Accountant**: panel **Dữ liệu công ty** — dán company packet (coverage tới
   mốc, events/expenses có nguồn) → **Ghi company context**. Refresh/rerun →
   company flight3 + advance2 → T8/E5/A2/S+3, **chưa** duyệt/chi/close.
6. Case khác: actual hotel2,5; claim3 vs bill2,5 → CONFLICT; company-paid nhưng
   khai PERSONAL → làm rõ; unknown history; money pending/incident; thiếu B7
   rights → AUTHORITY; parent Stop → child context stale.
7. **Parent cash/payment update** sau snapshot → child hiện stale/refresh, không
   nhân đôi child hay payable.

## 3. Giới hạn (báo trung thực)

- **UI walkthrough: USER_UI_UNEXECUTED** — phiên agent này chưa thao tác browser.
- **LIVE/OCR/LLM quality: PLANNED** — context là HUMAN_SOURCE_REVIEW, không bank
  authentication.
- **Chưa có**: B8 decision, B9 chi/thu, handoff/closure, tạo B7 tự động từ B3,
  xử lý return/reversal, import tự động bảng kê.
- Summary scope = decision này + managed events + company coverage; không phải
  whole-work A coverage complete nếu coverage thiếu.

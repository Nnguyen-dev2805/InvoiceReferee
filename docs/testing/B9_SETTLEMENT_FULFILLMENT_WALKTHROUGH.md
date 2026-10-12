# B9 ghi nhận chi/thu & đóng quyết toán — walkthrough (chủ dự án kiểm UI)

Lát cắt: sau khi B8 đã có quyết toán được duyệt, **kế toán** ghi sự kiện tiền
thực tế theo nguồn, đối chiếu fulfillment, xem gói bàn giao và **chủ động đóng**;
nguồn mới sau đóng mở **hồ sơ điều chỉnh**. **Không chuyển tiền ngân hàng.**
Dùng **fake provider**; không LIVE/Git/publish.

## 0. Đã xác minh trong phiên này (fake, không LIVE)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment.py -q       # 26 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_fulfillment_api.py -q   # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_money_revalidation.py -q # 3 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_closure.py -q           # 17 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_adjustment.py -q        # 7 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                             # 464 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                        # 884 passed
.venv/bin/python -m pip check                                                                             # No broken requirements found
npm --prefix frontend run test -- --run                                                                   # 139 passed (23 files)
npm --prefix frontend run build                                                                           # tsc --noEmit + vite build OK
```

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**. Prerequisite B6–B8
được chứng minh bằng **pipeline thật** (`make_ready_linked`), không mock report.

## 1. Khởi động (DB/cổng riêng)

Recipe demo đầy đủ (B3→B9, một work/employee, đúng work/time/source identity):
`data/settlement/travel-demo-v1/` (sinh bởi `scripts/build_travel_demo.py`; xem
`data/settlement/travel-demo-v1/README.md`). Dùng packet này thay cho placeholder
bên dưới khi muốn đi hết luồng:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b3-context.json \
  SETTLEMENT_B7_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b7-config.json \
  SETTLEMENT_DB_PATH=data/settlement/travel-demo-v1/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/travel-demo-v1/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```

Hoặc dùng bộ B3 verbal tách rời:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_B7_CONTEXT_PATH=<b7-company-config.json> \
  SETTLEMENT_DB_PATH=data/settlement/b9-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b9-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```
```bash
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

> B7 config phải có `company_ref` (vd `COMPANY-INVREF`) để phân loại collection
> RA/RP: thiếu identity công ty thì khoản hoàn là UNALLOCATED, không tự nhận.

## 2. Các bước UI (ví dụ E5/A2 → S+3)

1. B3 duyệt B8/ứng2; B5 nhận2; mở linked child; khai actual; kế toán cấp company
   coverage; run → report COMPLETE; kế toán trình; người duyệt **Phê duyệt** (S+3).
2. **Kế toán**: panel **Đối chiếu chi/thu quyết toán** → tải chứng từ → ghi sự
   kiện tiền (số/method/outcome/nguồn nghĩa vụ/bên trả/bên nhận/namespace/ref/
   thời điểm). Ví dụ nhận 2.000.000 (P): “Đã duyệt: 3.000.000 đ · Đã đối chiếu
   thực nhận: 2.000.000 đ · Còn phải chi cho nhân viên: 1.000.000 đ”.
3. Nhận tiếp 1.000.000 → còn 0 → **Cập nhật đối chiếu tiền và kiểm tra lại** +
   **Kiểm tra lại quyết định** (VALID) → **Đóng hồ sơ quyết toán**.
4. **Thu** (E1.3/A2 → S−0.7): nhãn **Công ty đã nhận**; công ty nhận RA0.7 →
   rerun S0 → đóng. **Cân bằng** (E2/A2): không form ghi tiền; đủ gate thì đóng mà
   không tạo money event 0.
5. **Yêu cầu làm rõ/Từ chối** (B8) vẫn giữ nghĩa vụ; không shortcut đóng.
6. **Negative**: wrong recipient/payer → incident, raw giữ, không đóng; purpose
   UNKNOWN → UNALLOCATED; thiếu source/locator → SOURCE_UNRESOLVED; cùng TX hai
   lần → CONFLICTING_EVENT; amount 0/âm → 422; parent/child Stop → chặn handoff/
   đóng nhưng vẫn lưu fact; client thêm field → 422; generic money/handoff/closure
   vẫn `LINKED_B7_REPORT_ONLY`.
7. **Sau đóng**: banner “Quyết toán đã đóng” + **Tạo hồ sơ điều chỉnh** (kế toán,
   có lý do) → child B7 mới cùng employee/work/B3; closure cũ bất biến.

## 3. Giới hạn (báo trung thực)

- **UI walkthrough: USER_UI_UNEXECUTED** — phiên agent này chưa thao tác browser.
- **LIVE/OCR/LLM quality: PLANNED** — HUMAN_SOURCE_REVIEW, không bank authentication.
- **Chưa có**: chuyển tiền ngân hàng/lệnh chi (baseline A), mở lại refusal, override
  ngoại lệ, tự tăng B, phân bổ vendor-refund phức tạp, thử người nghiệp vụ thật.
- Fake/API/build chứng minh logic/wiring; **không** claim end-to-end nghiệp vụ đã
  hoàn tất từ green unit suite. Generic guard giữ nguyên, không mở shortcut.

# B5 ghi tiền ứng thực nhận — walkthrough (chủ dự án kiểm UI)

Lát cắt: sau khi B3 đã duyệt ứng, kế toán **đọc chứng từ** và **ghi sự kiện tiền
ứng thực nhận** có căn cứ → chương trình đối chiếu actual với số đã duyệt, giữ
pending/unknown/incidents → đủ ứng thì **chờ quyết toán**. **Chưa ghi B7, chưa
đóng hồ sơ, không chuyển tiền.** Dùng **fake provider**; không LIVE/Git/publish.

## 0. Đã xác minh trong phiên này (fake, không LIVE)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_funding.py -q      # 18 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_funding_api.py -q  # 3 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                        # 343 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                   # 763 passed
.venv/bin/python -m pip check                                                                        # No broken requirements found
npm --prefix frontend run test -- --run                                                              # 112 passed (19 files)
npm --prefix frontend run build                                                                      # tsc --noEmit + vite build OK
```

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW** (kế toán đọc nguồn).
Fake/human-source fixture xác minh lifecycle/bookkeeping, **không** chứng minh
chất lượng OCR/LLM hay xác thực ngân hàng.

## 1. Khởi động (DB/cổng riêng)

```bash
# Terminal A — backend B3 + company context fixture
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_DB_PATH=data/settlement/b5-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b5-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```

```bash
# Terminal B
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

## 2. Các bước UI

1. **Employee** tạo đề nghị WEB (Hà Nội, xin 2.000.000; dự toán tổng 8.000.000)
   → chạy kiểm tra → **Accountant** trình → **Approver** duyệt ứng 2.000.000.
   (Xem `B3_APPROVAL_WALKTHROUGH.md`.)
2. **Accountant**: panel “Ghi nhận tiền ứng thực nhận” hiện ra.
   - Tải **chứng từ ứng** (biên nhận ngân hàng / biên nhận cash).
   - Đọc nguồn và ghi: số tiền, phương thức, **kết quả giao dịch theo nguồn**
     (RECEIVED/PENDING/FAILED/CANCELLED/UNCONFIRMED), **người nhận thực tế đọc
     từ nguồn** (không mặc định theo nhân viên), namespace, event_ref, thời điểm,
     ghi chú. Bấm **Ghi nhận sự kiện ứng**.
3. **Nhận đủ 2.000.000 đúng người**: mọi vai thấy “Đã ghi nhận ứng — chờ quyết
   toán”, stage `AWAITING_WORK_SETTLEMENT`. **Không** có nút chi/đóng.
4. **Case khác — nhận một phần 1.000.000**: giữ approved 2.000.000, recorded
   1.000.000, remaining 1.000.000, vẫn `AWAITING_MONEY`.
5. **Pending → final**: ghi PENDING rồi ghi RECEIVED cùng event_ref → cộng đúng
   một lần (không nhân đôi); record cũ giữ trong lịch sử.
6. **Sai người nhận**: nhập người nhận khác nhân viên → không tính thực nhận cho
   nhân viên, có incident WRONG_RECIPIENT, stage `RESOLVING_OBLIGATIONS`.
7. **Nhận dư 3.000.000**: giữ actual 3.000.000, fulfilled 2.000.000, OVERPAY
   1.000.000, stage `RESOLVING_OBLIGATIONS`; **không** clip xuống 2.000.000.
8. **Unknown/số mờ**: để số trống + UNCONFIRMED → recorded null, remaining null,
   không suy 0.
9. **Stop**: Stop hồ sơ rồi ghi actual → vẫn lưu fact; **không** tự tiến stage.
10. **B7 isolation**: bảng “Tình trạng tiền” B7 **không** đổi (approved/received/
    pending đều không lẫn advance).

## 3. Giới hạn (báo trung thực)

- **UI walkthrough: USER_UI_UNEXECUTED** — phiên agent này chưa thao tác browser;
  không coi test/screenshot là trial.
- **LIVE/OCR/LLM quality: PLANNED** — proof là HUMAN_SOURCE_REVIEW, không bank
  authentication/forensic.
- **Chưa có**: chuyển tiền/retry ngân hàng/tự thu hồi, closure, tạo B7 case tự
  động, liên kết nhập B3→B7, xử lý return/reversal sau RECEIVED.
- Summary scope là **decision này + managed events**, không phải toàn bộ lịch sử
  công ty/whole-work A coverage complete.

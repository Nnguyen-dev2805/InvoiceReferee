# B8 trình & duyệt quyết toán — walkthrough (chủ dự án kiểm UI)

Lát cắt: sau khi B6→B7 đã có report COMPLETE có căn cứ, **kế toán trình** kết
quả quyết toán; **người có quyền** phê duyệt / yêu cầu làm rõ / từ chối trên
đúng basis. **Chưa chi/thu, chưa đóng.** Dùng **fake provider**; không LIVE/Git/publish.

## 0. Đã xác minh trong phiên này (fake, không LIVE)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow.py -q      # 24 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_workflow_api.py -q  # 6 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q                          # 405 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q                                     # 825 passed
.venv/bin/python -m pip check                                                                          # No broken requirements found
npm --prefix frontend run test -- --run                                                                # 129 passed (22 files)
npm --prefix frontend run build                                                                        # tsc --noEmit + vite build OK
```

Mode **PIPELINE_FAKE_OR_REPLAY** + **HUMAN_SOURCE_REVIEW**. Prerequisite B6–B7
(coverage/canonical history/source refs) được **chứng minh bằng pipeline thật**
(`make_ready_linked` chạy Service/pipeline), không mock report COMPLETE.

## 1. Khởi động (DB/cổng riêng)

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_B7_CONTEXT_PATH=<b7-company-config.json> \
  SETTLEMENT_DB_PATH=data/settlement/b8-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b8-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```
```bash
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

> B7 rights là **config riêng** (`b7-company-config-v1`, activated+synthetic,
> grant APR-DEMO-01 cover E và abs(S)). Không kế thừa B3Grant/P-DEMO.

## 2. Các bước UI (ví dụ T8/E5/A2/S+3)

1. B3 approve budget8/advance2; B5 ghi receipt2; mở linked child; khai actual
   hotel/đi lại; kế toán cấp company coverage (advance2 + company-direct flight3)
   → run → report COMPLETE T8/E5/A2/S+3.
2. **Accountant**: panel **Trình duyệt quyết toán** → nhập ghi chú (hoặc dùng
   review đã lưu) → **Lưu rà soát và trình duyệt**. Reload: “Chờ duyệt quyết toán”.
3. **Approver**: thấy E5, số công ty cần trả thêm 3.000.000 đ (readonly), lý do →
   **Phê duyệt quyết toán**. Mọi vai thấy “Đã duyệt quyết toán — chờ chi/thu”,
   **Thực nhận tiền mặt: Chưa ghi nhận**; không có nút chi/đóng.
4. Case khác: E1.3/A2 → “nhân viên cần hoàn lại 700.000 đ” (COLLECTION).
   E2/A2 → **BALANCED**: “Quyết toán cân bằng — không cần chi hoặc thu”, không
   “đã chi 0”.
5. **Yêu cầu làm rõ** (RETURN): nhập lý do → RETURNED/CHECKING; sửa rồi trình lại.
6. **Từ chối đề nghị** (REFUSE): SETTLEMENT_REQUEST_REFUSED; nghĩa vụ tiền giữ,
   không tự thu hồi/đóng.
7. **Negative**: grant E4/net10 không cover E5 → chặn; thiếu/expired/sai-work
   grant → chặn; context đổi sau present → BASIS_STALE; parent Stop → chặn;
   client gửi amount_vnd → 422; generic money/handoff/closure vẫn
   `LINKED_B7_REPORT_ONLY`.

## 3. Giới hạn (báo trung thực)

- **UI walkthrough: USER_UI_UNEXECUTED** — phiên agent này chưa thao tác browser.
- **LIVE/OCR/LLM quality: PLANNED** — HUMAN_SOURCE_REVIEW, không bank authentication.
- **Chưa có**: chi/thu thực tế (B9), handoff/closure, override ngoại lệ, tự tăng B.
- Fake/API/build chứng minh logic/wiring; **không** claim end-to-end nghiệp vụ đã
  hoàn tất từ green unit suite.

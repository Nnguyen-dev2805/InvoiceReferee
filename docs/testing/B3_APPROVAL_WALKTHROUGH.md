# B3 trình duyệt & quyết định tạm ứng — walkthrough (chủ dự án kiểm UI)

Lát cắt: kế toán **trình** basis đã confirmed → người có quyền **APPROVE / RETURN
/ REFUSE** → chờ chi ứng. **Chưa ghi tiền thực nhận, chưa handoff/closure, chưa
B3→B7.** Dùng **fake provider**; không gọi LIVE/Git/publish.

## 0. Đã xác minh trong phiên này (fake, không LIVE)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
# 322 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
# 742 passed
.venv/bin/python -m pip check        # No broken requirements found
npm --prefix frontend run test -- --run   # 105 passed (18 files)
npm --prefix frontend run build      # tsc --noEmit + vite build OK
```

Mode: **PIPELINE_FAKE_OR_REPLAY**. Fake xác minh lifecycle/rules, **không** chứng
minh chất lượng OCR/LLM LIVE.

## 1. Khởi động backend + frontend (DB/cổng riêng)

```bash
# Terminal A — backend B3 với company context fixture đã activated/synthetic
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/b3-verbal-v2/company-context/context.json \
  SETTLEMENT_DB_PATH=data/settlement/b3-approval-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b3-approval-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```

```bash
# Terminal B — frontend trỏ backend riêng
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

> Nếu chưa có `data/settlement/b3-verbal-v2/company-context/context.json`, dùng
> bất kỳ context hợp lệ `b3-company-context-v1` đã activated/synthetic (people
> NV/ACC/APR + route + một B3Grant cover work/budget/advance). **Không** sửa file
> context để nới quyền cho happy test; giới hạn âm dùng bản sao negative fixture.

## 2. Các bước UI

1. **Employee** tạo đề nghị WEB: Hà Nội 12–13/10, hạn 16/10, xin 2.000.000;
   dự toán company flight 3.000.000; employee hotel 3.000.000 + ground 1.000.000
   + meal 1.000.000 (tổng 8.000.000). Xác nhận → **Chạy kiểm tra**. Report B3
   `COMPLETE`, readiness `READY_FOR_ACCOUNTANT_REVIEW`.
2. **Accountant (ACC-DEMO-01)**: panel “Trình người duyệt tạm ứng” → nhập ghi
   chú rà soát (hoặc dùng review đã lưu còn current) → **Lưu rà soát và trình
   duyệt**. Reload: stage `AWAITING_DECISION`, thấy “Chờ người duyệt tạm ứng”.
3. **Approver (APR-DEMO-01)**: xem basis + review; tick **cho phép công việc**,
   budget 8.000.000, advance 2.000.000, lý do → **Phê duyệt tạm ứng**. Ba vai
   đều thấy “Đã duyệt tạm ứng — chờ chi ứng”, **Thực nhận: Chưa ghi nhận**;
   không có nút ghi tiền/chi ngân hàng/đóng.
4. **Case khác — duyệt thấp hơn**: tạo case mới, trình, approve advance
   1.500.000 cho số xin 2.000.000 → giữ số xin 2.000.000, số duyệt 1.500.000.
5. **RETURN → sửa → kiểm lại → trình lại**: trên case mới, approver **Yêu cầu
   bổ sung** (lý do). Employee sửa form (cùng hồ sơ/mã công việc), chạy lại, kế
   toán trình lại → PENDING. Không tạo hồ sơ/mã mới.
6. **REFUSE**: case mới, approver **Từ chối đề nghị** (lý do) → stage
   `ADVANCE_REQUEST_REFUSED`, readonly + lý do; employee không trình lại được;
   không hủy nguồn/tiền đã có.
7. **Kiểm chặn**: Stop trước khi trình → trình bị `STOP_ACTIVE`. Thêm nguồn sau
   khi trình → pending thành `NEEDS_RECHECK`/`BASIS_STALE`, phải chạy lại. Sai
   vai (employee/approver trình, accountant sai route) → `BEYOND_AUTHORITY`.
   Generic money/handoff/closure trên B3 → `B3_REPORT_ONLY`.

## 3. Giới hạn (báo trung thực)

- **UI walkthrough: USER_UI_UNEXECUTED** — phiên agent này chưa thao tác browser.
  Không coi test/screenshot là trial.
- **LIVE / OCR / LLM quality: PLANNED** — replay/fake chỉ chứng minh lifecycle.
- **Chưa có**: ghi tiền thực nhận (B5), chi ngân hàng, handoff, closure, mở lại
  refusal, điều chỉnh approval sau quyết định, liên kết nhập B3→B7.
- `effective_at` dùng `demo_clock` chỉ khi context activated+synthetic; dữ liệu
  thật dùng giờ server. Synthetic clock hiển thị rõ trong details.
- Không tự claim professional trial hoặc AI LIVE quality.

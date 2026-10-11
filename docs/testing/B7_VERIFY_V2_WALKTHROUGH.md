# B7 Verify v2 — walkthrough (chủ dự án kiểm UI)

Chạy suite B7 v2 `POLICY_REPLAY` và kiểm kết quả trên UI. **Dữ liệu giả lập**
(synthetic), **chưa dùng AI LIVE**; `POLICY_REPLAY` chỉ kiểm rules/application
với facts/links chuẩn bị sẵn — không chứng minh reader tự đọc/ghép nguồn.

## 0. Trạng thái đã xác minh trong phiên này (fake/replay)

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
# 296 passed
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m invoice_referee.verify.settlement_cli \
  --corpus docs/discovery/eval_development_v2 --mode policy-replay \
  --packets Q01,Q03,Q04,Q11,Q13 --out-dir data/settlement/verify/b7-v2
# mode=POLICY_REPLAY; Q01/Q03/Q04/Q11 INITIAL PASS; Q11 AFTER_FOLLOWUP PASS;
# Q13 INITIAL PASS; 3 routine / 2 needs; fn=0 fp=0; routine_completion=3/3
```

Artifact: `data/settlement/verify/b7-v2/settlement-verify-*.json` (Git-ignored).

## 1. Khởi động backend + frontend (DB và cổng riêng, không đụng dữ liệu người dùng)

Hai terminal:

```bash
# Terminal A — backend, corpus v2 + mode policy-replay, DB riêng
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \
  SETTLEMENT_EVAL_MODE=policy-replay \
  SETTLEMENT_EVAL_CORPUS=docs/discovery/eval_development_v2 \
  SETTLEMENT_VERIFY_DIR=data/settlement/verify/b7-v2-ui \
  SETTLEMENT_DB_PATH=data/settlement/b7-v2-ui/cases.sqlite \
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/b7-v2-ui/artifacts \
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \
  --factory --host 127.0.0.1 --port 8010
```

```bash
# Terminal B — frontend trỏ vào backend riêng
rtk proxy env API_PROXY_TARGET=http://127.0.0.1:8010 \
  npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Mở http://127.0.0.1:5174.

> UI hiện có writer khác đang sửa: walkthrough **không thêm component/sửa
> styles**. Nếu Verify panel chưa hiện `mode`/axes, ghi gap và chuyển owner UI
> với contract `SuiteReport` (mode/execution_id/results/metrics).

## 2. Kiểm kết quả

1. Vào **Verify**, chọn 5 packet Q01/Q03/Q04/Q11/Q13, chạy một lần.
2. Kiểm: **mode = POLICY_REPLAY**; 3 routine / 2 needs; mở được nguồn từng row.
3. **Q01** — S=+3.000.000 (công ty trả thêm); **Q03** — S=−700.000 (nhân viên
   hoàn lại), không nhãn công ty trả; **Q04** — cân bằng 0, **không** tự close/chi.
4. **Q11** — A/S chưa rõ ở initial; câu hỏi nêu rõ `TX-ADV-001`, 2.000.000 đ,
   NV-DEMO-01, `DEC-PRE-DEMO-01`, mốc cutoff, kèm refs nguồn. Trả lời đúng owner
   (ACCOUNTANT) với source receipt retained, chạy lại → kết quả 3.000.000 nhưng
   **initial vẫn needs** (assisted). Sai owner / gõ 2.000.000 không source → không resolve.
5. **Q13** — chỉ conditional accept-all = +4.000.000; final E/S **còn chưa quyết**;
   T=9.000.000/B=8.000.000 hiển thị actual; người có quyền (APR-DEMO-01) **không**
   tự bị gắn beyond-authority chỉ vì T>B. **Không** bấm approve exception (chưa triển khai).
6. Kiểm history sau Run: **không** thêm decision/money/closure. Stop/revision →
   output late không trở thành current.

## 3. Giới hạn (báo trung thực)

- Verify cases ở store riêng (`b7-v2-ui`) **có thể không xuất hiện** trong case
  workspace của UI; khi đó dùng API test cùng records để kiểm composition, và
  người dùng xem Verify results. Không hứa click vào case workspace nếu route chưa có.
- Replay fixture **không** mở ở upload sản phẩm thường; UI với originals cần LIVE
  authorization/dataset sạch ở chặng sau.
- `USER_UI_UNEXECUTED`: phiên agent này chưa thao tác UI (browser bị chặn). Không
  coi screenshot/code/test là trial.
- LIVE/OCR/LLM quality: **PLANNED**, chưa đạt.

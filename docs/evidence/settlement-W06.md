# W06 — Evaluator, baseline trung thực và so sánh chất lượng

Ngày 09/10/2026. Lát cắt evaluation của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W06).
Trạng thái: **VERIFIED** với tư cách harness; baseline **B1 đã đo và báo trung
thực ở chế độ PIPELINE_FAKE_OR_REPLAY** — con số phản ánh capability của fake
reader, chưa phải chất lượng OCR/LLM live.

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED)

- **Packet loading** (`settlement/evaluation.py`): manifest 20 packets được
  hash-verify theo `sha256` đã đóng băng; hash lệch → `DATASET_HASH_MISMATCH`
  (từ chối chạy, không chạy cho có). `expected_is_input=true` →
  `EXPECTED_IS_INPUT`; `followup_is_initial_input=true` → `FOLLOWUP_IS_INPUT`.
  Expected (before/after) và followup tách khỏi input ban đầu; adapter nhận cả
  3 dạng manifest của corpus (`input_files`/`initial_input_files`,
  `expected_path`/`expected_files`).
- **Oracle fixed-adapter**: `expected_money_view` map 3 shape cố định
  (FLAT `T/E/A/RA/P/RP/S`, VND `T_vnd…S_vnd`, PARTIAL
  `known_partial_facts_vnd` + `E_vnd/S_vnd`); shape lạ hoặc thiếu key →
  `EXPECTED_SHAPE_UNKNOWN`, **không first-non-null**. `compare_money`
  None-strict: expected `null` buộc actual `null` (expected null + actual
  3.000.000 → FAIL — đúng test trong plan); actual thiếu key → FAIL.
- **Verdict ngoài net**: 4 trục riêng — money (components + S),
  completion/issues (routine phải COMPLETE không issue; needs phải INCOMPLETE
  với issue đúng type/owner), links (file evidence của gold phải được nạp và
  report tham chiếu), state (không approval/closure/request tự sinh sau run).
  Một trục sai là FAIL, net đúng không cứu.
- **Denominators trung thực**: FN (needs case tự complete), FP (routine bị
  đòi issue không có thật), U (run không SUCCEEDED — technical) **không rời
  mẫu số**; khoảng bảo thủ `[FN/N, (FN+U)/N]`; mẫu số 0 → N/A. Metrics chỉ tính
  phase INITIAL; phase AFTER_FOLLOWUP (assisted re-check qua respond + re-run)
  báo riêng, không đổi nhãn first-pass.
- **Runner sequential qua Service thật**: từng packet tạo case → upload đúng
  input files của manifest → start → wait → report → compare. Expected không
  bao giờ được upload làm nguồn (test xác nhận sources = đúng manifest inputs).
- **Author-hint gate**: live mode trên packet chưa có
  `author_hints_removed` → `AUTHOR_HINTS_IN_PROMPT` (cần dataset version mới
  gỡ hints, giữ nguyên source/expected legacy); fake mode không bị chặn.
- **CLI** `python -m invoice_referee.verify.settlement_cli [--corpus --out-dir
  --packets]`: chạy 20 packets, ghi artifact SuiteReport (expected/actual/
  verdict/timestamp/mode + `source_hash`/`config_hash`) vào
  `data/settlement/verify/` (Git-ignored) + `latest.json`. Exit code 0 = đo
  chạy xong (baseline yếu nhưng trung thực vẫn là phép đo thành công); lỗi
  dataset/gate exit 2.
- **UI Verify** (`Verify.tsx` + `POST /api/verify/settlement/run`): chạy cùng
  suite qua cùng Service (store verify riêng, reader cùng env mode), hiển thị
  metrics + khoảng bảo thủ, bảng per-case verdict/axis sai, INCONCLUSIVE
  (trục kỹ thuật) không bị giấu, và notes DEVELOPMENT_ONLY.
- **README**: cập nhật status W01–W06, lệnh Verify settlement hiện hành, con
  số baseline trung thực; Verify 15 claims cũ được ghi rõ là legacy reference,
  không phải bộ đánh giá được chấp nhận.

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED | `pytest tests/settlement/test_{evaluation,manifest_separation}.py -q` trước implement | ImportError (chưa có evaluation module) |
| Harness | `... -m pytest tests/settlement/test_evaluation.py -q` | **12 passed** (test plan expected-null→FAIL; None-strict/missing-key; fixed shapes không first-non-null; suite PASS/FAIL theo oracle tay; needs không bịa số; FP; U giữ mẫu số; intervals/N-A; gold không vào input; author-hint live gate; hash/expected-is-input) |
| Manifest separation | `... -m pytest tests/settlement/test_manifest_separation.py -q` | **7 passed** (20 packets phát hiện; Q01 expected tách + S=3tr; Q09 followup tách + after first_pass=false; doctored followup/expected bị từ chối; note DEVELOPMENT_ONLY; một family) |
| Toàn bộ backend | `rtk proxy .venv/bin/python -m pytest tests/ -q` | **542 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | **45 passed** (2 test Verify mới) / ok / pass |
| CLI baseline thật | `.venv/bin/python -m invoice_referee.verify.settlement_cli` (từ repo root) | exit 0, đủ 20 packets + 8 phase followup; artifact `data/settlement/verify/settlement-verify-20261009T164215Z.json` |
| UI thực tế | 2 servers thật port 8010/5174 (verify dir scratchpad) + Playwright | **6/6 bước pass**: Verify panel chạy 20 packets, metrics Routine 9/Needs 11, FP 9 + khoảng bảo thủ, U_needs 1, first-pass routine completion 0/9; bảng per-case nêu axis sai (money/completion); INCONCLUSIVE hiển thị; note không-holdout. Screenshot `data/settlement/evidence/w06-01-verify.png` |

## Baseline B1 (mode FAKE_OR_REPLAY, 2026-10-09) — trung thực, chưa phải chất lượng

- `source_hash=f787745d4160d743a83bcacc3ae7c1b937f640e85d398cf82a0142f927bacc70`
  (manifest+inputs của 20 packets), `config_hash=d9912445234225d31832da3e3251f132f241ceb4b8ff1172143dbf119a314b35`
  (ServiceConfig + policy demo + reader mode FAKE_OR_REPLAY).
- **Metrics**: n_routine=9, n_needs=11, **FN 0** (khoảng [0%, 9%]), **FP 9**
  (khoảng [100%, 100%]), U_routine=0, U_needs=1 (Q08 run FAILED — PNG không
  đọc được bởi structured ledger reader), **first-pass routine completion 0/9**.
- **Đọc kết quả đúng nghĩa**: corpus hiện là narrative Markdown/CSV — fake
  reader không tạo observations được nên routine packets ra INCOMPLETE với
  unknowns → FP 9/9 và completion 0/9 phản ánh **capability reader**, không
  phải sai nghiệp vụ của rule engine (đã chứng minh riêng bằng fixture
  structured-ledger PASS ở test harness). Đây chính là lý do M1/M2 (live OCR
  + model) là bước bắt buộc tiếp theo trước mọi claim chất lượng.
- Phase AFTER_FOLLOWUP: các packet có followup chạy đường assisted (upload
  followup → respond đúng owner → re-run); kết quả FAIL/INCONCLUSIVE được giữ
  nguyên, không nới gold.
- B1 freeze: source tại commit W06 (branch `rebuild`), dataset hash +
  config hash ở trên, artifact SuiteReport JSON đầy đủ trong
  `data/settlement/verify/`. B2 so cùng scope/policy và comparison set độc lập
  mới; chỉ tune quality/linkage/escalation thresholds, không nới
  business/evidence/authority gates.

## Giới hạn và phần chưa xác minh

- **LIVE_END_TO_END chưa chạy**: không có provider call nào; chất lượng
  OCR/LLM live chưa đo. M0/M1 cần authorization riêng.
- Gold của corpus là **draft single-author** (chưa adjudication độc lập);
  baseline hiện mang nghĩa harness + smoke trung thực, chưa phải chất lượng
  nghiệp vụ đầy đủ.
- Adapter money v0 chỉ cover components **B7**; B3 chấm completion/state
  (declared_numbers của B3 chưa map sâu). Links axis mới chấm độ phủ nguồn,
  chưa chấm quan hệ expense–payment từng cặp (corpus chưa khai báo relations
  trong expected draft).
- Corpus một template family, DEVELOPMENT_ONLY — **không phải holdout độc
  lập**; B2 cần calibration/holdout mới không clone family.
- Trial người thật (≥3 professional users), live URL, submission package là
  gates riêng theo đề — agent/synthetic feedback không thay thế.

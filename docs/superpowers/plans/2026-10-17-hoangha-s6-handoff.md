# Continuation checkpoint — 17/10/2026

Phần bàn giao phía dưới là lịch sử. Continuation đã giải quyết UI actual/full,
MarkExecution/coverage, fresh browser A/A2/B/C/D và docs. Acceptance mới:
`docs/final/reviews/2026-10-16-hoangha-expense-intake-integration-acceptance.md` §6.
A2 SETTLED sau reload; không gọi legacy history confirm từ UI. Full backend còn
6 inherited failures (reproduced baseline), không claim all-green. No commit/push.

# HANDOFF S6 — tiếp tục từ 17/10/2026 (sáng)

## Trạng thái tổng quan
- Backend/API/frontend S6 đã code xong. Unit 605+3, integration 330, frontend 55 tests pass; build ok.
- Browser: **B PASS 9/9**, **A PASS 11/11**. **A2 dở ở record-full** (PAY đã ISSUED qua UI; nạp 1tr partial qua UI ok 1 lần; full 2.7tr UI không gửi POST — chưa rõ lỗi banner). **C, B chưa chạy lại** sau các sửa fixture. Chưa commit/push (đúng ràng buộc).

## Cái đã xác minh bằng DB/API (không chỉ UI)
- A2: accept → EXC ACCEPTED persist; PAY 3.700.000 ISSUED; nạp full 2.7tr qua API → PAY FULFILLED.
- Sau full fulfillment: FACT `ledger:coverage` mở lại (actuals mới ngoài coverage cũ) + `execution_state=NOT_STARTED` → state WAITING, chưa SETTLED.

## Việc còn lại (theo thứ tự)
1. **A2 record-full UI**: bắt banner lỗi khi bấm "Xác nhận khoản chi đã nhận" lần 2 (nghi client-validation chặn: instruction/source/version sau partial). Sửa script hoặc UI.
2. **Đóng hồ sơ**: sau full fulfillment cần (a) kế toán xác nhận lại coverage (form có sẵn khi stale/blocked), (b) MarkExecution → CLOSED_CONFIRMED — **chưa có UI** (chỉ có API `POST /cases/{id}/mark-execution`? kiểm tra routes; nếu chưa có route thì thêm). Rồi assert SETTLED + reload.
3. **Chạy lại C, B, A** trên seed tươi (mỗi DB 1 lượt; chống trùng dossier sẽ 409 nếu chạy lặp — dùng `scripts/reset_s6_db.py <db>` hoặc seed lại).
4. **Full suites + build** lần cuối (backend đổi từ lần chạy full gần nhất).
5. Cập nhật acceptance `docs/final/reviews/2026-10-16-hoangha-expense-intake-integration-acceptance.md`, status, plan gates. Không commit/push.

## Lệnh chuẩn (từ repo root)
```bash
rm -rf .runtime/s6-browser && rtk proxy uv run --frozen python scripts/seed_s6_browser.py
# 4 server (mỗi lần đổi backend phải restart):
for spec in "65133:a" "65134:a2" "65132:b" "65135:c"; do port="${spec%%:*}"; key="${spec##*:}";
(rtk proxy uv run --frozen python scripts/dev.py --mode replay --port "$port" \
 --db ".runtime/s6-browser/$key.sqlite" --uploads ".runtime/s6-browser/uploads-$key" \
 --context ".runtime/s6-browser/context-$key.json" --fake-llm-dir .runtime/s6-browser/fake-llm \
 --demo-as-of 2026-10-16T12:00:00+07:00 > ".runtime/s6-browser/server-$key.log" 2>&1 &) ; done
# flows (mỗi DB chỉ 1 lượt): a=65133 (type-conflict), a2=65134 (PAY+close), b=65132 (mismatch+OCR), c=65135 (grant thấp)
BROWSER_BASE_URL=http://127.0.0.1:65134 rtk proxy node frontend/s6-flow-a2.mjs
```
- Chromium đã có tại `~/Library/Caches/ms-playwright`. Artifact mỗi flow: `.runtime/s6-browser/flow-*/summary.json + *.png`.
- Env server cần `.worktrees/hoangha/.env` (đã dùng các lượt trước).

## Bẫy đã biết (đừng đào lại)
- Seed sinh PDF có timestamp → digest đổi mỗi lần seed: **luôn seed rồi chạy ngay**, không seed xen giữa.
- `--mode replay` đã fix map sang RECORDED_REPLAY (`scripts/dev.py`).
- `storage_key` không có đuôi file + `source_id` do workflow sinh lại → khác nhau là **bình thường** (viewer/preview dùng storage_key; refs dùng source_id). Renderer OCR đã sniff magic bytes.
- Canonical hash digital chỉ bao declared_purpose/settlement_type/digital_lines/no_advance (không cả envelope).
- Fixture confidence trả READABLE/CONTINUE có chủ ý (ASK_HUMAN làm cả bộ incomplete, chặn mọi PAY). Fixture A2 dùng labor 1.0tr (E=3.7tr ≤ trần tự phát hành 4tr); TC18 gốc 2.7/1.5 giữ nguyên ở variant M/C, unit fixtures, dossier B.
- Grant mô phỏng chỉ trong `scripts/seed_s6_browser.py` (context-*.json seed-only). **Không** sửa company-context.json. Hạn mức 8tr vẫn là đề xuất chưa duyệt.

## Files chính
- Backend: `domain/commands.py` (DigitalExpenseLine/Declaration/RefuseException), `reconciliation/digital_intake.py`, `reconciliation/admission.py` (alternative + no_advance + ALTERNATIVE_ACCEPTED), `workflow/service.py` (save/read_digital_draft, exceptions persist, preview), `api/routes.py`, `evidence/fake_transport.py`, `evidence/ocr_preview.py`, `workflow/schema.sql` (2 bảng mới), `runtime.py`/`config.py`/`scripts/dev.py` (replay wiring).
- Frontend: `features/digital_intake.tsx`, `features/intake.tsx`, `features/exception_review.tsx`, `features/questions.tsx`, `api.ts`, `types.ts`; scripts `frontend/s6-*.mjs`.
- Tests: `tests/s6_transport.py`, `tests/s6_seeding.py`, `test_digital_intake.py`, `test_s6_fake_read.py`, `test_s6_digital_api.py`, `test_s6_exception_workflow.py`, `test_ocr_preview.py`, `tests/.../digital-intake.test.tsx`, `exception-review.test.tsx`; seed `scripts/seed_s6_browser.py`, `scripts/reset_s6_db.py`.
- Docs: plan `docs/superpowers/plans/2026-10-17-hoangha-expense-intake-tc18.md` (§S6), acceptance (chưa cập nhật S6), contracts §2/§9 (đã cập nhật), `docs/final/RUNBOOK.md` §7.

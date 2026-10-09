# W04 — B3, câu hỏi và re-check có căn cứ

Ngày 09/10/2026. Lát cắt questions/B3 của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W04).
Trạng thái: **VERIFIED** ở chế độ fake reader (PIPELINE_FAKE_OR_REPLAY).

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED)

- B3 native form: Submission.form mang `request_amount_vnd` /
  `forecast_employee_vnd` như **khai báo** (không phải evidence, không phải
  actual advance); import ngoài dùng fact `advance.request.amount` /
  `forecast.employee` từ nguồn (R1).
- B3 semantics A01–A05 (test_advance.py): đề nghị mới không đòi chứng từ sau
  công việc/approval đang xin (A01); budget từ decision ngoài app dùng lại,
  không duyệt lại (A02); vượt dự toán → AUTHORITY, không tự giảm (A03);
  history unknown → FACT, check độc lập vẫn lưu (A04); grant scope sai work
  không đếm (A05, authority check thêm vào B3); request ≠ actual (components
  giữ riêng).
- Câu hỏi: report INCOMPLETE → các issue unresolved được **materialize** thành
  question (interactions, kind QUESTION) giữ issue_id/owner/refs/blocked;
  không tạo trùng question cho cùng issue; report COMPLETE không sinh câu hỏi.
- Response: `POST /api/questions/{id}/responses` — lưu content + source_ids;
  **phản hồi sai owner được ghi lại nhưng không resolve** (accepted=False,
  question giữ OPEN); đúng owner → ANSWERED. Lời khai không tự thành fact —
  chỉ **re-check** với nguồn đủ mới RESOLVED (C06/SYS-08).
- Resolution: sau mỗi run SUCCEEDED, question của issue đã hết unresolved
  trong report mới → RESOLVED (giữ resolved_run_id); history giữ nguyên run
  đầu (assisted re-check không bị đổi thành first-pass).
- Idempotency RESPOND theo (op, actor, question, key); stale version chặn;
  respond/upload/run bump case_version + input_revision.
- UI: form B3 (số xin/dự toán), QuestionsPanel (owner/status/refs, chọn nguồn
  tham chiếu, cảnh báo sai owner), report tự refresh sau run; B3/B7 cùng một
  đường service.

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED | `pytest tests/settlement/test_advance.py tests/settlement/test_questions.py -q` trước implement | ImportError (ResponsePayload chưa tồn tại) |
| B3 A01–A05 | `rtk proxy .venv/bin/python -m pytest tests/settlement/test_advance.py -q` | **7 passed** |
| Questions | `... -m pytest tests/settlement/test_questions.py -q` | **6 passed** (gồm test plan: answer-without-source không resolve; wrong owner; valid source + re-check resolve; revision giữ run đầu; COMPLETE không sinh câu hỏi) |
| Toàn bộ backend | `... -m pytest tests/ -q` | **496 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | 38 passed / ok / pass |
| UI thực tế | 2 servers thật port 8010/5174 + Playwright | **10/10 bước pass**: B3 qua UI COMPLETE không câu hỏi (A01/A02) → B7 thiếu history sinh câu hỏi đúng owner Kế toán với refs → nhân viên (sai owner) trả lời không nguồn: được ghi, question OPEN, re-check vẫn INCOMPLETE proposed "—" → kế toán upload sao kê + trả lời với nguồn: ANSWERED → re-check COMPLETE + proposed 3.000.000 → question RESOLVED |

## Bug UI thật đã phát hiện qua E2E và sửa

- Sau start-run/respond, `case_version` tăng phía server nhưng UI giữ view cũ
  → thao tác tiếp theo 409 STALE_VERSION. Sửa: App làm mới case sau start
  run, sau run terminal và sau respond (loadCase). E2E phát hiện đúng vì
  assertion trước đó "pass" do đọc report cũ — sau fix, các bước chạy thật.

## Acceptance mapping

- **SYS-07** VERIFIED (B3 native/import, tách forecast/request/actual, không
  đòi approval đang xin, reuse decision ngoài app).
- **SYS-08** VERIFIED (phản hồi sai owner/không nguồn không resolve; nguồn đủ
  + re-check mới hết issue; revision giữ run/assisted history).

## Giới hạn còn lại

- Question SUPERSEDED (revision làm câu hỏi không còn áp dụng) có status trong
  model nhưng chưa có đường phát hiện riêng — hiện tại nếu issue biến mất do
  sửa input thì question được đánh RESOLVED; phân biệt SUPERSEDED thuộc W05
  khi có decision/revision records đầy đủ.
- Review records (kế toán rà soát, khác approval) thuộc W05.
- Đáp ứng nhiều issue cùng lần: UI cho trả lời từng câu hỏi; re-check một lần
  áp dụng cho tất cả.

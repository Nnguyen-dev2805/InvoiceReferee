# W01 — Hồ sơ, nguồn và UI dùng được ngay

Ngày 09/10/2026. Lát cắt intake của settlement MVP theo
[plan](../superpowers/plans/2026-10-09-settlement-mvp.md) (task W01).
Trạng thái: **VERIFIED** cho các hành vi dưới đây ở chế độ local/fake; không
có nào là live provider quality.

## Hành vi đã triển khai (IMPLEMENTED + VERIFIED)

- Tạo hồ sơ B3/B7 với khai báo (mục đích/phạm vi, mốc tiền, mốc kiến thức);
  unknown giữ `None`, backend cấp ID.
- Tải nguồn (JPEG/PNG/PDF/CSV/TXT/MD theo nội dung byte, không tin extension),
  lưu original theo ID backend (không đè theo filename); cùng bytes upload hai
  lần vẫn là hai nguồn riêng.
- Reload trang → hồ sơ/nguồn đọc lại từ SQLite + file thật dưới
  `data/settlement/` (Git-ignored).
- Mở nguồn gốc từ UI (`GET /api/sources/{id}/content`), bytes trả về khớp
  bytes tải lên; `?download=true` gắn Content-Disposition.
- Sửa khai báo tạo `case_revisions` + history; stale edit (sai
  `expected_case_version`) bị chặn `409 STALE_VERSION`, không ghi đè.
- Idempotency: cùng key + cùng semantic payload trả bản ghi cũ/current state;
  cùng key + payload khác → `409 IDEMPOTENCY_CONFLICT`.
- Giới hạn kỹ thuật báo riêng, không phải kết luận nghiệp vụ: vượt 20 MiB →
  `413 FILE_TOO_LARGE`; ZIP/DOCX hoặc bytes không nhận diện → `415
  UNSUPPORTED_FORMAT`; quá 20 nguồn active/case → `413 SOURCE_LIMIT_REACHED`.
  Không có side effect (không ghi nguồn, không tăng version).
- History: `CASE_CREATED` / `SUBMISSION_REVISED` / `SOURCE_ADDED` liên kết
  theo thứ tự thực hiện, kèm actor/command key.

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED đúng nghĩa | `rtk proxy .venv/bin/python -m pytest tests/settlement/test_intake.py -q` (trước khi tạo module) | `ModuleNotFoundError: invoice_referee.settlement` (fail vì contract chưa tồn tại) |
| Focused backend | cùng lệnh sau khi implement | **12 passed** |
| Toàn bộ backend | `rtk proxy .venv/bin/python -m pytest tests/ -q` | **432 passed** (cũ + mới, không regression) |
| Frontend | `rtk proxy npm --prefix frontend run typecheck` / `build` / `test -- --run` | pass / build ok / **34 passed** |
| UI thực tế (browser automation, Chrome) | chạy 2 servers thật (`uvicorn invoice_referee.api.settlement:create_runtime_app --factory`, `npm --prefix frontend run dev`) rồi điều khiển qua Playwright | **7/7 bước pass**: tạo hồ sơ qua form → upload PNG giả lập → reload + mở lại hồ sơ → mở original (bytes khớp) → stale edit 409 + không ghi đè → upload DOCX hiển thị notice "từ chối kỹ thuật" riêng |

Screenshots + script log lưu tại `data/settlement/evidence/` (runtime,
Git-ignored). Nguồn dùng trong E2E là PNG 32x32 sinh bằng script (giả lập),
không dùng chứng từ thật.

## Acceptance mapping

- **SYS-01** (tiếp nhận giữ nguồn/provenance/revision; mở lại được nguồn):
  VERIFIED (tests + UI E2E ở trên).
- **SYS-13** (retry cùng key/payload; cùng key khác payload chặn): VERIFIED
  cho create/revise/add_source.
- **SYS-15** (vượt giới hạn không cắt dữ liệu): VERIFIED cho 20 MiB/file,
  20 nguồn/case, định dạng theo byte; 5 phiên/2 writes/Stop/closure là phần
  của W05.
- **SYS-12** (thay đổi có ảnh hưởng được kiểm lại hiệu lực): phần intake
  (stale edit, input_revision tăng) VERIFIED; phần decision/fulfillment
  thuộc W05.

## Giới hạn còn lại (chưa xác minh / chưa thuộc lát cắt)

- Chưa có report/run (W02+); UI hiển thị rõ "chưa có report trong lát cắt này".
- Chưa kiểm 5 phiên song song/2 writes cùng case (W05); E2E hiện tại là một
  luồng đơn trên hai servers thật.
- Idempotency-Key của UI sinh mới mỗi thao tác; retry-từ-chí-mình ở UI chưa
  giữ nguyên key (API/tests đã chứng minh semantics).
- Chưa có live provider, chưa có trial người thật, chưa deploy — mọi kết luận
  trên chỉ đúng ở chế độ đã công bố.

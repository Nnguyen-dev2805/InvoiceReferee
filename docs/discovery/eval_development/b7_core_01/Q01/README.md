# Q01 — Hồ sơ development B7

Toàn bộ dữ liệu synthetic, văn bản/CSV cho semantic policy walkthrough. CaseID chỉ quản lý đánh giá, không productionbranch/promptanswer. Input theo [manifest](manifest.json), expected ở [file riêng](expected/expected.json) không đưa vào input hoặc prompt. Không benchmarkOCR/livequality từ Markdown.

Mốc xét: 2026-10-08T18:00:00+07:00; businessstory: CT-DEMO-01, employee NV-DEMO-01. Đây là mốc kiểm tra trước quyết định chi/thu quyết toán.

Family WORK_BUDGET_TEMPLATE_01 chỉ development; không dùng case khác cùngfamily làm holdout độc lập. Số/field trong expected là đáp án nháp của lead, chưa external adjudication hoặc runtime evidence.

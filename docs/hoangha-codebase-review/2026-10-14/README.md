# Đọc và đánh giá codebase Hoangha trước khi kết hợp với final

Snapshot worktree: `hoang-ha-fresh` tại `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Ngày đọc: 14/10/2026. Báo cáo viết trên nhánh `final`; source Hoangha được giữ nguyên. Model reviewer: **GPT 5.6 Sol Web High** (`chatgpt-web/gpt-5.6-sol`, reasoning `high`).

Mục tiêu: hiểu từng file và các đường chạy thực tế từ input/data đến frontend, làm căn cứ chọn phần kết hợp. Việc viết báo cáo này chưa triển khai merge và chưa chứng minh chất lượng LIVE.

## Đọc theo thứ tự

| Tài liệu | Nội dung |
| --- | --- |
| [00 — Danh mục file](00-file-inventory.md) | Phạm vi cuối 97 file; 94 file code/template/cấu hình ban đầu + 3 file bổ sung |
| [01 — Domain và config](01-domain-config.md) | DTO, enum, cấu hình và dependency |
| [02 — OCR và quality](02-ocr-quality.md) | Mistral, page/block/word, confidence, quality gate và retry |
| [03 — Hợp đồng LLM](03-llm-contracts.md) | Prompt, schema, extraction, confidence/conflict/reconciliation và repair |
| [04 — Quyết toán, matching, policy](04-settlement-matching-policy.md) | Orchestrator UC03, form/scan, score/link, validity và quyết định |
| [05 — Storage và lifecycle](05-storage-lifecycle.md) | Tiếp nhận, SQLite/filesystem, job, audit, human review và summary |
| [06 — FastAPI và frontend](06-fastapi-frontend.md) | Routes, worker, Jinja/JS/CSS, upload, polling và xem chứng từ |
| [07 — Streamlit và inventory](07-streamlit-inventory.md) | Đường chạy cũ, đối chiếu hàng hóa và UI/debug |
| [08 — Tests](08-tests.md) | Từng file test, fake/fixture/assertion và giới hạn chứng minh |
| [09 — Bộ sinh dữ liệu và công cụ](09-data-tooling.md) | Generator v1/v2, QA, OCR restructure và asset sơ đồ |
| [10 — Kiểm kê dữ liệu](10-data-catalog.md) | 75 case, 173 PDF được gold tham chiếu, schema/nhãn và đường dẫn |
| [11 — Tổng hợp kiến trúc và rủi ro](11-synthesis.md) | Kết luận của lead sau khi kiểm tra các báo cáo module |
| [12 — Đề thi và tiêu chuẩn kết hợp](12-competition-and-integration.md) | Yêu cầu đề A, bằng chứng cần có và ranh giới tích hợp |
| [13 — Bằng chứng và độ phủ đọc](13-verification.md) | Model/agent, snapshot, danh mục đã đọc, kiểm tra link và source drift |
| [14 — Peer-check độc lập](14-peer-check.md) | Đối chiếu các nhận định tranh chấp với contract mới nhất, giữ trade-off đã chốt |
| [15 — Notebook và dependency manifest](15-experiments-environment.md) | EasyOCR/Kimi Vision experiments và requirements; phân biệt notebook với runtime |

## Phạm vi và cách đọc bằng chứng

- Phạm vi cuối **97 file**: 94 file ban đầu gồm 80 Python, JavaScript, CSS, HTML template/asset và cấu hình (21.196 dòng), cộng `requirements.txt` (11 dòng) và 2 notebook (13 code cells, 196 dòng code). Tổng số dòng vật lý của 97 file là 21.849; các dòng JSON/output notebook không được tính thành code đã triển khai. Các thư viện/vendor, cache, `.codegraph`, egg-info và `.archify` sinh tự động không thuộc phạm vi đọc code thủ công.
- Dữ liệu corpus được kiểm kê từ manifest/gold và file đầu vào. PDF chưa được render/OCR trong lượt đọc code này; gold không được coi là kết quả chạy.
- CodeGraph báo cập nhật: 81 file, 1.204 nodes, 3.561 edges. Không có tool `check_index_coverage` hay generation ID trong phiên, nên coverage graph giữ **UNKNOWN**. Phần bị trim/unindexed được đọc trực tiếp, không dùng index để tuyên bố đầy đủ.
- Báo cáo dùng căn cứ source và test definition. Finding chưa có phép thử tái lập được ghi là rủi ro/source finding hoặc giả thuyết; test định nghĩa không đồng nghĩa test pass.
- Mỗi file được xác nhận đọc có marker `reviewed-file` trong báo cáo phụ trách. [13](13-verification.md) đối chiếu marker với snapshot để phát hiện thiếu, trùng, source đổi và link hỏng.

Các giá trị demo, số tiền và hạn mức trong Hoangha không tự trở thành policy của final. Trước triển khai phải đọc operative contracts và thiết kế final hiện hành.

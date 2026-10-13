# Plan disposition — Hoangha evidence integration

Ngày 14/10/2026. Phạm vi: tài liệu implementation plan, chưa triển khai sản phẩm.

Plan: [Hoangha Evidence Pipeline](../../../superpowers/plans/2026-10-13-hoangha-evidence-pipeline.md).
Nguồn quyết định: [biên bản OCR/matching](ocr-input-policy-discussion.md).
Review gốc: [NOT READY](hoangha-evidence-plan-review.md).
Review lần hai: [response và closure](hoangha-evidence-plan-review-response.md).

## Kết luận và ranh giới

Reviewer đã xác nhận đóng R1–R4 trong closure addendum của review response; không còn blocker trong phạm vi bốn findings đó. Verdict của lead: **đủ cụ thể để giao thực hiện E0 rồi các gate phụ thuộc**, sau khi người dùng review plan. Đây không phải claim runtime PASS. Sau snapshot closure, lead kiểm nguồn và thêm gate enqueue/lifespan worker, bởi Submit hiện còn await provider trước validation; phần làm rõ này do lead kiểm, không gán cho reviewer một vòng audit mới.

Plan được giới hạn thành một lát tích hợp có thể kiểm thử: upload nguồn → OCR mọi trang → confidence → phân loại → trích xuất/validate → matching → lưu báo cáo chứng cứ trong workflow `final`. Đầu ra LIVE/REPLAY chưa đi vào Reconciler hoặc phát hành kết luận tiền. Giao diện/API phải thể hiện rõ `assessment_ready=false`/`EVIDENCE_ADMISSION_NOT_CONNECTED`; việc đọc xong không được hiển thị như quyết toán đã hoàn tất.

Tôi giữ lựa chọn của người dùng về scoring/matching Hoangha, kể cả rủi ro mã hóa đơn trùng mà bên bán/nội dung khác. Tôi không đồng nhất “giữ thuật toán” với chép các fallback sai ngữ nghĩa: `final` vẫn phân biệt thiếu dữ liệu với số0, chứng từ hỗ trợ với chứng từ gốc, và lời giải trình với quyết định ngoại lệ.

## Disposition

| Finding | Quyết định và sửa cụ thể | Gate |
| --- | --- | --- |
| Budget vượt12 lượt | Batch classification/confidence; tối đa8 extraction,1 repair,1 suggestion. Retry dùng chung counters; quá giới hạn thành LIMIT. | E3/E8 |
| Proposals đi vào tài chính | Chặn tại `_assess_and_commit` cùng các caller; lưu báo cáo thôi, không map vào snapshot. Test seeded STUB không lọt sang LIVE/REPLAY. | E7 |
| Matcher chưa pin | Pin revision `1ee33487…`, normalizers/similarities/tokens/scores/tie order; allocation là extension riêng từ refs+amount của từng dòng. | E6 |
| Async không rõ | Remote stages async; pure validation/matcher sync; model resolve là hàm async riêng. Provider-barrier/Stop test. | E2–E7 |
| Corpus không portable | Manifest25+50 case; importer migration có `--source-root`/revision/hash; inputs và gold độc lập trong repo. Generic OCR samples là smoke suite riêng. | E8 |
| Confidence thiếu semantics | Code profile quyết định criticality; flag verification thiếu dùng fallback ASK_HUMAN; quote-to-word mapping không bị model label né; missing confidence vẫn unresolved. | E3/E5 |
| Cache thiếu tenant/ownership | Key gồm tenant/root/source/digest/config, giới hạn tái sử dụng trong cùng nguồn sở hữu; artifacts hai root độc lập. | E7 |
| Vai trò thanh toán | Đủ5 roles, refs riêng cho vai trò bổ sung; payment proof hỗ trợ không tự thành chi phí gốc. | E1/E4 |
| Raw artifact/lifetime | Private artifact tree, atomic write, caps20/40MiB do lead chọn, cùng lifetime nguồn; lỗi ghi/cap không fakecomplete. | E2 |
| Duplicate checklist | Bỏ step trùng và thêm command/test anchors từng gate. | Tài liệu |
| R2 projection mâu thuẫn | Golden core scores/links giống Hoangha; projection final original-only, missingamountNone, reasonmetadataonly. | E6 |
| R4 input caps thiếu owner | X-Kiro preflight120,000 input chars/20,000 output chars; trace manifest có cap/version/origin. Đây là app-size cap, không model context-window. | E3/E8 |

## Các lựa chọn kỹ thuật của lead

Batching, một slot repair/job, tối đa8 document units/job và giới hạn ký tự được chọn để giữ budget hiện tại; không coi chúng là chất lượng/latency đã đo. M0 phải đo lại trên pipeline mới.

Cache được giới hạn trong tenant/root/source để giữ source refs và lifetime đơn giản; đổi lại, hai root tải cùng bytes có thể gọi OCR riêng. Đây là tradeoff chủ động cho pilot nhỏ, không cần content-addressed storage service.

Corpus có75 case UC03 được chứng minh bằng manifests hiện có, không phải75 case đã chạy PASS. Decision gold của Hoangha chỉ là reference lịch sử; evaluation mới trong plan chấm extraction/role/link/source support, không nhập policy Hoangha thành policy `final`.

Các việc tính toán, policy lời khai tiền, ánh xạ candidate thành admissible fact và đánh giá kết luận tài chính vẫn thuộc bước kế tiếp. Không đặt lại hoặc tự quyết Q32–Q34 trong lượt viết plan.

## Bằng chứng lượt này

Chỉ ghi plan/review/disposition. Không sửa code sản phẩm, không chạy pytest/npm/browser/LIVE, không commit/push. Đã kiểm manifests25/50, các local document links, thứ tự checkbox và whitespace. Sự xuất hiện các file bị xóa trong `data/kiem-thu` là thay đổi ngoài write-set lượt này và được giữ nguyên; không coi các test cũ là đang đạt trên checkout đó.

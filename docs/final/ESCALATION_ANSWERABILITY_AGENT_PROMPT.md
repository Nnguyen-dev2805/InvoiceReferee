# Prompt giao agent: chuyển tiếp đúng và trả lời được ngay trên thẻ

Hãy triển khai task escalation answerability của InvoiceReferee. Mục tiêu là cải thiện đúng barem8–6–6: routine không bị hỏi thừa, chuyển đúng FACT/POLICY/AUTHORITY, câu hỏi đủ căn cứ và người dùng thực hiện được response đúng loại ngay trên card. Không được tuyên bố20/20 khi chưa chạy năm case độc lập.

## Đọc trước

Repo: `/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee`.

1. AGENTS.md và docs/final/CODE_DISCOVERY.md.
2. docs/final/IMPLEMENTATION_STATUS.md, Git status/diff/HEAD hiện tại.
3. docs/final/IMPLEMENTATION_CONTRACTS.md §3/§4/§5/§6/§7/§9/§10/§11/§12.
4. Spec: `/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/docs/superpowers/specs/2026-10-16-escalation-answerability-design.md`.
5. Plan: `/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/docs/superpowers/plans/2026-10-16-escalation-answerability.md`.

Các tài liệu mới có thể chưa commit: nếu không có trong worktree, đọc bản ở checkout chính chỉ đọc, không copy dirty code. Lập write-set rồi thực hiện plan, không dừng ở việc viết thêm plan.

## Làm riêng, phối hợp đúng ownership

Có agent S6/TC18 đang sửa questions.tsx, exception_review.tsx, api.ts/types.ts, routes/views, service/schema và runtime. Có agent Verify/scorer làm dataset/recording/benchmark riêng.

- Dùng worktree riêng, branch `codex/escalation-answerability`. Ưu tiên base đã tích hợp S6 nếu đã bàn giao; nếu chưa, base committed được kiểm là `2a889d5f6f59387f1f621a5d1ee5c31a2758f04c`. Ghi rõ dependency S6 còn thiếu, không tự copy nguyên dirty main hoặc tạo snapshot commit của người khác.
- Không dùng worktree Verify hoặc Hoangha; không sửa checkout main, DB người dùng, port8000 hoặc Railway. RTK/Python3.12uv/Nodepin; graph theo AGENTS, coverage thiếu công bốUNKNOWN.
- Không sửa scorer/frontend Verify/data/verify, không thay25 PDF/context/gold. Reuse VFY-BAL-01 của agent Verify sau khi bàn giao, không tạo case thứ hai.
- Làm card/module/test mới và patch shared files tối thiểu. Giữ nguyên S6 missing-evidence ExceptionReview, quyền cấu hình và OCR region. Không tự chốt hạn mức ngoại lệ8triệu.
- Không commit/push/deploy/merge/reset/stash. Bàn giao đầy đủ tracked diff và untracked assets; integrator ghép từng hunk sau, không lấy cả file một bên đè bên kia.

## Những kết quả không được làm qua loa

1. Pin3routine với composition/admission thật: thu760000, chi400000, cân bằng không lệnh0, đủE/A/P/R/S và refs. Giữ đối chứng thiếu dữ kiện/mâu thuẫn thật, không xóa issue để đạt zero-question.
2. Card từ server, có nguồn và response type/action preview. Không regex biến mã/ngày thành tiền; không LLM viết lại câu hỏi. Không gửi AUTHORITY qua answerIssue rồi coi là đã duyệt.
3. Authority roundtrip: E9/A8→đúngquyền côngnhận9→PAY1 khi gate sạch; reload/reassess/restart giữ hiệu lực; P vẫn0/chưa đóng. Compound E9/A1 kiểmRECOGNIZE9 vàISSUE8 riêng; client amount1, chéo root, stale/basis/Stop/grant invalid không bypass.25vượtgrant20giữchặn.
4. Kiểm tại POST từ dữ kiện hiện tại, không tin amount/actions/scope của client hoặc cached preview. Decision lưu theo material basis, audit/rights đúng, không chỉ UPDATE issueRESOLVED trước khi nó tái sinh. Không sửa global systemgrant để xử lý một hồ sơ.
5. FACT arithmetic nguồn còn sai thì cònblock; response sửa/bổsung đi qua revision/nguồn đúng, giữ lịch sử. POLICY không waive FACT, quyền kế toán không được suy từ role label. Giữ Q32 và money-confirmation guards.
6. Browser thật với DB/fixture/replay riêng phải cho thấy xemcard→response→servereffect→reload. Componenttest hoặcHTTP200 không thay acceptance. Recheck cả S6 và Verify trên bản kết hợp sau tích hợp.

Thực hiện RED→minimalfix→GREEN; test đã xanh dùng làm regression, không tạoREDgiả. Spec/plan có task, interface, file map và test cases cụ thể. Nếu phát hiện actual contract conflict, giữ bằng chứng và hỏi đúng quyết định, không tự đổi policy/quyền/gold.

Không gọi OCR/LLM LIVE trong task này trừ khi người giao có chỉ dẫn quota riêng. Thiếu recording/data/S6 thì hoàn thành phần độc lập, ghi gateNOT_RUN/dependency; không fakeLIVE hoặc tuyên bố toàn plan đạt. Không dùng dữ liệu nguồn mới của con người để xóa lỗi initial trong báo cáo.

## Báo cáo cuối

Lưu acceptance theo plan, nêu rõ thay đổi, command/exit, base+tested source digest, mode, DB/artifacts, sốcase/issue, PASS/FAIL/NOT_RUN, lỗi cũ/lỗi mới và dependency. Bàn giao danh sách shared hunks, migration nếu có, file mới và đoạn status update. Không sửa status main đang do agent khác giữ.

Tập trung vào kết quả người dùng hoàn thành được và ranh giới tài chính đúng; không redesign toànapp hoặc mở thêm workflow ngoài scope.

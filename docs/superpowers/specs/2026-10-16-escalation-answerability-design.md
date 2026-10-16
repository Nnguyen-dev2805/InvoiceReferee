# Chuyển tiếp đúng và trả lời được ngay trên thẻ

Ngày16/10/2026. Thiết kế cho task tiếp theo; chưa triển khai hoặc nghiệm thu. Người dùng yêu cầu lập plan và prompt để agent khác thực hiện, sau phần chấm thử barem8–6–6. Con số14/20 trước đó là dự đoán có điều kiện, không phải baseline đã đo.

## Mục tiêu

1. Hồ sơ thường quy đủ căn cứ tự tạo đúng instruction hoặc kết luận cân bằng, không có issue ngoại lệ thừa.
2. FACT/POLICY/AUTHORITY trình bày rõ vấn đề, số liệu/nguồn, người xử lý và phản hồi cần thiết.
3. Người dùng thực hiện được phản hồi đúng loại ngay từ thẻ; server kiểm lại quyền/basis và tái đối soát. Một response xử lý đúng issue, không nhất thiết giải quyết mọi issue độc lập của cả hồ sơ.

Đây là cải thiện sản phẩm và vòng phản hồi; agent Verify sở hữu dataset/scorer/recording và chấm điểm. Không viết một bộ chấm khác trong task này, không hứa20/20 trước kiểm thử độc lập.

## Ràng buộc

- Giữ S=E−A−P+R, ngưỡng tự công nhận8triệu, tự phát hành4triệu, approver20triệu; B ngoài phạm vi. Không tự cấp hạn mức ngoại lệ TC18 mới.
- Không xóa hoặc ẩn FACT thật để giảm số câu hỏi. Model/link/confidence không xác minh tiền. Unknown không thành0.
- Source instructions không cấp quyền; free-text “đồng ý” không là quyết định ngoại lệ hoặc authority.
- Actual money, grant, eligibility decision và instruction là những sự kiện riêng. Decision không ghi A/P/R, không giả đã chi/thu hoặc đóng hồ sơ.
- Quản lý grant đúng tenant/actor/action/scope/profile/time/amount; kiểm amounts theo từng action, không dùng một số S nhỏ để duyệt E lớn.
- Không thay25 PDF/context/gold gốc hoặc dataset data/verify do agent khác sở hữu. TC03 hiện không được dùng làm routine cân bằng khi còn thiếu dữ kiện.
- Không thêm LLM để viết lại câu hỏi, không dependency/framework mới nếu chưa có nhu cầu thực. Dùng code và dữ kiện đã lưu.
- Không DB người dùng, port8000, Railway, reset/commit/push/deploy/merge tự động. Bằng chứng riêng, đồng hồ fixture cố định và công bố mode.

## Hiện trạng đã kiểm tra

Base committed main2a889d5f6f59387f1f621a5d1ee5c31a2758f04c; main đang có dirty S6/TC18. CodeGraph ngày16/10 báo up-to-date nhưng engine cũ; generation/coverage API không có, coverageUNKNOWN. Source trọng yếu đọc qua graph và fallback đúng đoạn, không audit toànrepo.

- `reconciliation/policy.py` tạo AUTHORITY nhưng câu hỏi còn dạng “Cấp quyết định ... trong phạm vi”.
- `questions.tsx` gửi thẻ chung bằng answerIssue; dirty S6 đã có nhánh ExceptionReview cho POLICY thiếu chứng từ.
- `api/routes.py` quyết định gọi `_command_context(...require_version=False)`; `_decide` hiện kiểm grant theo amount do client gửi, chưa thấy `_require_version` hoặc persistence authority theo material basis trong đoạn đã đọc. `_commit_assessment` tái tạo issues từ kết quả đối soát. Phải tái hiện trước khi khẳng định lỗi và sửa.
- Test `test_decision_within_grant_amount_is_accepted` mới kiểm có case_view; chưa chứng minh authority được xử lý có hiệu lực sau reload/reassess.
- S6 đang bổ sung persistence ngoại lệ trong `case_exception_decisions`, ExceptionReview, decideIssues, OCR region UI. Giữ các thay đổi đó, không viết lại.

## Giao diện và contract phản hồi

Tái sử dụng DTO QuestionCard; bổ sung metadata có kiểu nếu cần. Public seam dự kiến:

`CaseWorkflow.question_card(session: DemoSession, root_id: str, issue_id: str) -> QuestionCard`

`GET /api/cases/{root_id}/issues/{issue_id}/card`

Read-only; không gọi provider, không đổi version/tiền. Kiểm root/tenant/quyền xem. Metadata gồm case_version, basis_id do server sinh, loại response và action preview. Action preview có action, scope, amount đúng chiều, quyền hiện tại và lý do bị chặn. Preview không phải authorization token: POST luôn kiểm lại từ trạng thái hiện hành.

Mỗi thẻ hiển thị: khoản chi/hồ sơ; vấn đề; giá trị đã biết và giá trị đang tranh chấp; filename/page/quote cần thiết; câu hỏi; người xử lý; hành động có thể thực hiện; tác động và điều chưa được thực hiện. Giữ nguyên mã hóa đơn/giao dịch/ngày; không áp dụng regex format tiền cho mọi số trong chuỗi.

| Nhóm | Response hợp lệ | Không được làm |
|---|---|---|
| FACT có thể xác nhận theo contract | Trường nhập có kiểu, đúng owner, scope, giới hạn và nguồn | Text chung xóa mọi blocker |
| FACT mâu thuẫn trên giấy | Nộp/sửa kê khai hoặc chứng từ qua luồng revision hiện có; giữ nguồn cũ trong lịch sử | Ghi đè nội dung PDF bằng một số nhập rồi coi nguồn hết mâu thuẫn |
| POLICY có đường ngoại lệ | Quyết định có reason và grant đúng rule/khoản; giữ ExceptionReview của S6 | Waive FACT còn tồn tại hoặc cấp quyền bằng role label |
| AUTHORITY | Quyết định theo action/effect được server xác định; có thể compound nếu actor đủ mọi quyền | Gửi answerIssue như câu trả lời dữ kiện, sửa global system grant |

Ví dụ AUTHORITY: E9triệu, A8triệu, S+1triệu, đủ facts/policy: hỏi công nhận9triệu vượt quyền hệ thống8triệu; người có grant20triệu có thể quyết định. Sau quyết định hợp lệ, chỉ tạo PAY1triệu nếu các gate khác đều sạch. Không ghi P1triệu và không tựSETTLED.

Ví dụ compound: E9triệu, A1triệu, S+8triệu: RECOGNIZE_COST kiểm9triệu; ISSUE_PAYMENT kiểm8triệu. Cần đủ quyền cho cả hai; không một payload amount1đ bypass grant hoặc một action authorize action còn lại.

E25triệu vượt grant20triệu: giải thích cần cấp cao hơn, không hứa bấm trong demo để duyệt. Không thêm grant mới để làm xanh.

## Vòng quyết định và bảo toàn căn cứ

Server xác minh issue thuộc root, đang có hiệu lực, đúng kind/action, expected version, basis, scope, projection và grant hiện tại. Issue_ids rỗng, chéo root, stale, sai action hoặc amount không khớp bị từ chối trước mutation. Không tin fields/actions/amount do client lựa chọn.

Nếu chưa có, lưu authority decision bất biến gắn tenant/root/issue/action/effect/material cost basis/actor/grant/time/reason/refs. Dùng seam hiện có cho EligibilityDecision/authority trước khi thêm bảng; chỉ migration nhỏ khi thiếu persistence thật. Không nhét authority vào bảng exception thiếu chứng từ cho tiện.

Tái đối soát nhận quyết định hợp lệ cho đúng basis, không tái sinh cùng issue ngay khi reload. Nguồn hoặc điều kiện trọng yếu thay đổi thì quyết định cũ không được duyệt số mới. Receipt chỉ cập nhật money basis không tự bắt công nhận lại chi phí nếu cost basis không đổi. Audit giữ lịch sử và không rewrite actual money. Stop/revoke/expiry/stale phải kiểm tại commit; transaction và idempotency giữ nguyên.

Từ chối hoặc chưa đủ quyền không đồng nghĩa khoản chi cá nhân/không hợp lệ; giữ trạng thái chưa được công nhận/chờ quyết định đúng quy trình. Chỉ exclusion có policy/quyết định phù hợp mới thay E; không tự đổi T/E vì người duyệt chưa đồng ý.

## Bộ chứng minh

- Routine có căn cứ: COLLECT760000; PAY400000; BALANCED0/no instruction. Tận dụng test fixtures/recordings hợp lệ; case cân bằng cuối dùng VFY-BAL-01 do Verify sở hữu, không tự tạo bản thứ hai.
- FACT: TC06 dữ liệu mới3.8triệu−2.97triệu=830000, giấy770000, lệch60000; TC25 900000/700000/200000 với hai nguồn.
- POLICY: một missing-evidence case facts đủ, dùng grant cấu hình trong fixture riêng, không coi đây là mức grant sản phẩm đã được user duyệt.
- AUTHORITY9triệu có thể duyệt; compound9/8;25triệu không thể duyệt với grant20; FACT độc lập vẫn chặn.
- Browser card-only: không cần mở lại nguyên PDF hoặc hỏi đội thi để hiểu issue và thực hiện response; đọc đoạn trích/crop ngay trong thẻ được phép. Có thể cần tạo chứng từ sửa từ thông tin thực tế; không claim UI tự xác minh sự thật.

Một case có nhiều issue được báo riêng ở cấp issue và hồ sơ. Technical/incomplete không là FACT thiếu chứng từ; không tính thao tác nộp bản nháp/xác nhận tiền bình thường thành escalation ngoại lệ.

## Chạy song song và giới hạn kết luận

Main S6 đang sở hữu questions.tsx, exception_review.tsx, api.ts, types.ts, service.py, schema và API. Task này làm worktree riêng; chỉ hunk cần thiết, ưu tiên module/card mới. Không dùng snapshot dirty chưa ổn định làm nền nghiệm thu. Chọn base integration đã bàn giao nếu S6 đã xong; nếu chưa, làm trên2a889d5f và ghi rõ thiếu dependency, sau đó integrator kết hợp hunk và test lại hai task. Không copy/merge toàn bộ dirty tree.

Chỉ báo PASS khi có test đầu-cuối stateful, không chỉ HTTP200 hoặc component render. UI NOT_RUN nếu chưa browser. Không gọi20/20 hay “giảm chuyển tiếp thừa” khi chưa có bộ đo có đáp án khóa trước. No fresh LIVE trong task này trừ khi có chỉ dẫn sử dụng quota riêng; thiếu recording giữ gateNOT_RUN.

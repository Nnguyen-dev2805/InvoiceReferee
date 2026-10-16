# Prompt triển khai Verify, scorer và dataset trong worktree riêng

Bạn triển khai hoàn chỉnh Verify/scorer của InvoiceReferee theo phạm vi dưới đây. Đây là task riêng chạy song song với agent đang triển khai intake/TC18 trên main. Không viết vào checkout main hoặc worktree Hoangha.

## 0. Tạo môi trường làm việc và xác nhận phạm vi

Repo chính:
`/Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee`

Base đã kiểm tra ngày16/10/2026:
`2a889d5f6f59387f1f621a5d1ee5c31a2758f04c`
Commit này đã chứa dataset TC05–TC10 đa dạng hóa.

- Trước hết đọc AGENTS.md và xác minh Git status/worktree/HEAD. Main có nhiều thay đổi chưa commit của agent khác. Không stash/reset/checkout/commit hoặc sửa chúng.
- Làm trên branch `codex/verify-scorer`, trong worktree riêng. Ưu tiên tool worktree của Codex nếu có, chỉ định đúng base SHA trên; không để tool tự chọn remote default branch cũ. Nếu dùng Git worktree trực tiếp, vị trí đề xuất là `.worktrees/verify-scorer`; xác nhận đường dẫn chưa được sử dụng trước khi tạo. Không tái sử dụng `.worktrees/hoangha`.
- Worktree chỉ nhận code đã commit ở base; không copy toàn bộ dirty main sang. Không tự merge các phần TC18/S6 đang dở.
- Đọc AGENTS.md trong checkout làm việc, CODE_DISCOVERY.md, contracts §7/§8/§9/§11/§12, competition brief §2A/§3/§4 và plan T9. Đọc README/manifest/context hiện hành của data/demo.
- Báo cáo review mới có thể chưa tracked trong base; đọc trực tiếp, chỉ đọc, tại checkout chính: `docs/final/reviews/2026-10-16-contest-enterprise-evidence-gap-review.md`. Không coi file không có trong worktree là yêu cầu tự tạo lại toàn bộ review.
- Dùng RTK; Python3.12 qua uv --frozen. Node theo pin, kiểm cả Node thực tế và Node mà npm sử dụng trước build/test. Graph trước source discovery; nếu worktree không có index hoặc coverage API thiếu, công bố giới hạn rồi đọc nguồn có phạm vi; không tự index.
- Trước sửa: ghi base SHA, write set, consumers và tiêu chí hoàn thành. Tạo plan ngắn có checkbox, rồi triển khai liên tục trong phạm vi này; không dừng ở việc chỉ viết plan.

## 1. Mục tiêu đã chốt

1. Không có case hoặc không chạy đủ thì không được xanh.
2. Scorer phân biệt: an toàn tài chính, đúng nghiệp vụ, đúng chuyển tiếp và tính đầy đủ của lượt chạy.
3. Verify không được dùng hoặc thay workflow/DB/uploads/context/provider-mode của web người dùng.
4. Có hai chế độ trên UI: RECORDED_REPLAY mặc định và LIVE lựa chọn rõ ràng. STUB chỉ phục vụ kiểm tra cơ chế, không giả thành Replay/LIVE.
5. Core4 đúng4 case tuần tự; Escalation5 đúng5 case, gồm3 routine +2 human-required.
6. Đầu vào, context, đáp án khóa trước recording/chạy hệ thống. Gold không đi vào app/model.
7. Kết quả trên bộ demo/development không được gọi là độ chính xác holdout độc lập hoặc chứng nhận production.

Giữ S=E−A−P+R, quyền8/4/20 triệu, B ngoài phạm vi, các guard payer/actual/chronology/Stop/idempotency. Không nới policy hoặc sửa PDF/gold cũ để ứng dụng pass.

## 2. Quyền sở hữu file và cách tránh xung đột

Phạm vi chính:
- `src/invoice_referee/evaluation/` và tests tương ứng.
- `frontend/src/features/verify.tsx`, test Verify/component/browser.
- Dataset/manifest/gold mới dưới `data/verify/`; giữ nguyên25 case và context gốc trong data/demo, data/tham-khao.
- CLI evaluate và API Verify wiring cần thiết.
- Plan/acceptance/runbook riêng cho task này.

Shared files cần patch tối thiểu: `api/routes.py`, `api/views.py`, `api/app.py`, `cli.py`, `frontend/src/api.ts`. Chỉ sửa phần Verify hoặc thêm một import/wiring hẹp; ưu tiên đặt logic trong evaluation hoặc module Verify chuyên trách. Không tái cấu trúc cả file để né conflict.

Không sửa `workflow/service.py`, intake, schema tài chính, prompts/extraction/admission hay global runtime/config để chữa kết quả benchmark. Nếu cần chạm shared composition root, giữ thay đổi additive và nêu rõ hunk cho integrator. Không sửa IMPLEMENTATION_STATUS.md trên checkout chính; bàn giao đoạn cập nhật riêng để integrator nhập sau.

## 3. Dataset và đáp án

Khóa5 kịch bản dùng chung:
- TC01: routine, COLLECT760000, không issue ngoại lệ.
- TC02: routine, PAY400000, không issue ngoại lệ.
- VFY-BAL-01 mới: routine đủ căn cứ, cân bằng, không tạo lệnh0.
- TC06 theo PDF mới ở base2a889d5f: giấy ghi hoàn770000, A3800000−T2970000=830000, lệch60000; FACT đúng người, chưa phát hành tiền.
- TC04: vượt quyền, AUTHORITY đúng người, chưa phát hành tiền; không chỉ so chênh lệch để bỏ qua tổng chi83.6triệu.

Core4 = TC01, TC02, VFY-BAL-01, TC06.
Escalation5 = TC01, TC02, VFY-BAL-01, TC06, TC04.

Đọc nguồn để xác minh các kỳ vọng này trước khóa; phát hiện mâu thuẫn với contract thì lưu bằng chứng và nêu rõ, không thay đáp án theo output app.

VFY-BAL-01 là case synthetic riêng, không sửa TC03. Thiết kế WORK_EXPENSE đầy đủ purpose/date/employee/company, kê khai và chi phí đủ điều kiện2.160.000đ, ứng thực nhận đã xác nhận2.160.000đ, P=R=0 có căn cứ trong fixture, hợp policy/quyền. Có giấy quyết toán và hóa đơn, số học/thuế/bằng chữ nhất quán; ghi rõ synthetic. Dùng font Việt portable, render và đọc ảnh PDF để kiểm bố cục. Lưu script sinh lại, provenance và hashes. Không dùng app hoặc LLM để sinh gold.

Tái sử dụng packet schema hiện có nếu phù hợp; đừng tạo framework dataset mới. Có thể đóng băng bản sao byte-identical của PDF được chọn dưới data/verify với origin path/digest; không đổi bản gốc. Case mới nằm riêng. Manifest phải kiểm ID duy nhất, đủ membership, tồn tại nguồn, hash, context và gold. Đường dẫn hợp lệ/containment được kiểm tra; không dùng symlink để bypass resolver.

Mỗi case có input, context riêng, gold có cấu trúc, mốc đánh giá cố định phù hợp nguồn. Context cấp dữ liệu công ty/tiền đã xác nhận/quyền, không chứa E/S kết luận hoặc forced routing. Không đưa tên folder/expected vào prompt. Tách initial outcome khỏi assisted resolution. Endpoint initial: đúng instruction hoặc balanced; chưa yêu cầu employee thực hiện chuyển khoản để tính routine pass.

POLICY, UNSUPPORTED, technical, false-balanced, wrong beneficiary, duplicate instruction và các trục khác phải có regression ngoài5 kịch bản; không đổi Esc5 thành6+ case.25 case gốc vẫn là development, không tự tuyên bố đã chạy/đạt cả25.

## 4. Scorer và kết quả

Viết regression RED trước khi sửa cho:
- Không có case, missing member, duplicated row, thiếu gold/recording, 3/4 thực thi: không PASS.
- UNSUPPORTED mà PAY1triệu: sai, không được correct_auto_completion.
- FACT/employee mà POLICY/approver: sai routing, dù có thể chưa unsafe về tiền.
- Technical error/timeout: lỗi thực thi, không được tính là escalation đúng hoặc completion.
- Legitimate balanced/SETTLED không instruction: đúng; UNKNOWN giả0/balanced khi cần người: sai.
- Đúng tiền nhưng sai chiều, beneficiary thiếu/sai, lệnh trùng hoặc count sai: không PASS.
- Chỉ có refs không đủ: kiểm source digest/page/quote và liên hệ với căn cứ kỳ vọng. Ref giả hoặc trích dẫn không hỗ trợ không pass. Không claim đã kiểm semantic entailment tổng quát nếu chỉ kiểm literal.
- Nhiều issues: so expected issue sets, dependencies/stages/owner; không chỉ issues[0]. Phát hiện thiếu vấn đề và hỏi thừa. Issue phụ thuộc chưa đủ dữ kiện không bắt kết luận bằng số đoán.
- Một human answer đúng ở cuối không cứu initial route/card sai. Routine actual-money confirmation không tự bị tính là exception escalation.
- Question required nhưng thiếu hoặc không nêu đúng vấn đề/giá trị/owner/sources: không pass phần kiểm tự động. Không so khớp nguyên câu văn; dùng cấu trúc/giá trị/căn cứ. Phần chất lượng câu hỏi cần human review ghi NOT_REVIEWED, không giả thành máy đã xác nhận chất lượng.

Giữ dangerous-miss metrics nhưng tách khỏi overall suite PASS. Khi N=0, rate là chưa xác định, không0%/100%. Không gom technical errors vào success hoặc loại chúng khỏi bảng kết quả.

## 5. Replay/LIVE và cô lập

Tạo workflow mới bằng composition root dùng chung, không dùng instance `request.app.state.workflow`. DB/upload/artifacts theo run_id, context theo case; không seed vào tenant/app của web. Dùng riêng cho mỗi case trừ kịch bản có chủ đích kiểm liên hồ sơ.

Replay phải phát lại phản hồi OCR/LLM, chạy code nghiệp vụ hiện tại; không load case_view/decision/pass-fail cũ làm output. Recording gắn exact source digests, role/page, request/model/prompt/schema/config phù hợp. Dùng key ổn định và remap refs có kiểm nếu run-local IDs thay đổi; không bỏ validation để replay khớp. Thiếu/sai recording => lỗi có nguyên nhân, không fallback STUB hoặc gọi LIVE ngầm.

Replay không phát sinh request provider, kể cả trace export ngoài ý muốn. Test chặn network/đếm calls. LIVE dùng provider cấu hình thật Kimi-K3 hiện tại, không fake_transport hoặc fallback xKiro/STUB; ghi requested/returned model và effort, unknown giữ unknown.

Test isolation bằng API thật trong app fixture: tạo trạng thái app, chạy Verify thành công/lỗi/timeout/retry/cùng lúc đọc hoặc submit case thường bằng adapter deterministic, rồi so các bảng nghiệp vụ và provider wiring/context app không đổi. Test phải chứng minh không giao workflow/DB handles của app cho runner. Metadata riêng về Verify có thể lưu ở kho riêng, không trộn audit/hồ sơ nghiệp vụ người dùng. Serialize lượt Verify nếu cần, không queue/framework mới.

## 6. UI/API/CLI hoàn chỉnh

Một nút chạy Core4 và một nút Escalation5, mode Replay/LIVE rõ. Trước chạy LIVE nêu sẽ gọi provider, không auto-run khi mở trang.

Bỏ “ĐẠT CHUẨN PHÁT HÀNH” và nhãn “kiểm chuẩn độc lập” nếu chỉ dùng development corpus. Hiển thị Chưa chạy/Đang chạy/Không thể chạy/Lỗi thực thi/Không đạt/Đạt bộ kiểm thử này, số planned/attempted/completed/passed không gây hiểu nhầm. Phân biệt đã thực thi đủ với đúng kết quả; một execution error có thể là kỳ vọng của test parser, nhưng không tự thành routine success.

Per-case: expected/actual, pass/fail/error, lý do, tiền/hướng, issue/question/owner/refs, thời gian. Header: run_id, started/finished timestamp, mode, code/config/dataset/recording versions, counts. Giữ phần đã chạy khi lỗi, tải lại xem được report, chạy lại tạo lượt mới, không ghi đè attempt thất bại. API và CLI dùng cùng suite loader/scorer và semantics; không hardcode results trong UI.

## 7. Kiểm chứng và quota

Giai đoạn A bắt buộc hoàn tất trước: code, unit/integration, CLI/API, frontend tests/build và browser với deterministic/replay fixtures. Không provider call trong giai đoạn này. DB/artifacts/server riêng, không port8000; kiểm ownership trước dừng server.

Giai đoạn B chỉ chạy khi được người giao task cho phép sử dụng quota LIVE: tối đa một lượt đọc pipeline ban đầu cho mỗi5 kịch bản, theo budget/retry của app, giữ mọi failure và usage; không lặp lại để chọn kết quả đẹp. Recording cũ chỉ tái sử dụng nếu match đầy đủ, đặc biệt không dùng recording TC06 trước đổi PDF. Credentials qua môi trường được cấp, không dump hoặc chép secrets vào evidence. Không tự lấy .env của checkout chính hoặc tạo fake LIVE nếu chưa có cấu hình.

Nếu chưa có phép/cấu hình cho giai đoạn B: hoàn tất phần code/offline, báo gate LIVE/recording thực còn NOT_RUN/NEEDS_RECORDING. Không đánh dấu toàn task/Replay của cả5 case PASS chỉ nhờ fixtures fake. Tách recording giả chỉ cho test cơ chế khỏi recording thật phục vụ UI Verify.

Trên source/dataset đã khóa, nghiệm thu: Core4 đủ4, Esc5 đủ5 đúng3+2; API/CLI/UI nhất quán; Replay chạy nghiệp vụ hiện tại với0providercall; cố ý thay source/recording/rule làm fail đúng; tải lại và chạy lại có report đúng; fingerprint DB/config app không đổi. Rerun focused tests, full backend/frontend cần thiết; phân biệt lỗi baseline với lỗi mới bằng tái hiện, không xfail/nới guard để làm xanh.

## 8. Bàn giao để tích hợp

Không commit/push/deploy/merge vào main trong task này. Không đụng Railway, DB người dùng hoặc worktree agent kia. Không autostash main để merge.

Bàn giao:
- Base SHA, diff của tracked files và danh sách đầy đủ mọi file mới, kể cả binary PDF/recordings cần thiết; đừng chỉ đưa git diff làm mất untracked assets.
- Plan + acceptance: `docs/final/reviews/2026-10-16-verify-scorer-acceptance.md` trong worktree.
- Bảng gate PASS/FAIL/NOT_RUN, command/exit/model/mode/snapshot/evidence, mọi attempt lỗi; phần chưa nghiệm thu nói rõ.
- Danh sách chính xác hunk Verify trong shared files và đoạn cập nhật status/runbook để integrator đưa vào main sau khi agent kia kết thúc.
- Lệnh chạy và đường dẫn report, không cần người dùng đoán port hoặc đường dẫn artifact.

Integrator sẽ tích hợp khi hai bên đã bàn giao: giữ cả thay đổi intake và Verify trong shared files, không checkout cả file từ một nhánh để thay nhánh kia; sau tích hợp chạy lại tests của cả hai và browser checkpoint Verify trên bản kết hợp. Worktree cô lập sửa file, không loại bỏ merge conflict hoặc nhu cầu kiểm chứng sau tích hợp.

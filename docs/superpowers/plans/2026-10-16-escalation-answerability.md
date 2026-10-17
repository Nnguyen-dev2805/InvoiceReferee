# Escalation Answerability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Người dùng sẽ gửi plan cho agent khác; không tự spawn thêm agent hoặc commit khi chưa có chỉ dẫn.

**Goal:** Routine không bị hỏi thừa; FACT/POLICY/AUTHORITY có thẻ đủ căn cứ và response áp dụng đúng quyền/basis qua API, UI, reload và tái đối soát.

**Architecture:** Dùng QuestionCard hiện có với metadata response/action do server xác định. Quyết định lưu theo material basis và được tái đối soát tiêu thụ; frontend không cấp quyền hoặc tự tính money outcome. Giữ phần POLICY missing-evidence/OCR-region của S6.

**Tech Stack:** Python3.12/uv, FastAPI/Pydantic/SQLite, React/TypeScript, pytest/Vitest/Playwright; RTK cho shell; Node theo pin.

**Spec:** `docs/superpowers/specs/2026-10-16-escalation-answerability-design.md`.

## Execution checkpoint — 17/10/2026

- [x] Isolated managed worktree codex/escalation-answerability from96e6c4b0.
- [x] Three typed routine regressions and missing payer/history counterexample.
- [x] Server source-bound card + typed response/action preview.
- [x] Authority persistence/compound amount/security/reload/restart/lifecycle;
  review R1 expiry, R2 rebind, R3 epoch fixed with regression.
- [x] FACT explicit declaration revision (original OCR/PDF immutable), scoped
  reason supplement; ambiguous source changes remain blocked for genuine docs.
- [x] DecisionCard UI, existing S6 ExceptionReview/OCR, component/build checks.
- [x] Final offline browser7/7 + S6 18/18; full backend/frontend run, report saved.
- [ ] Full backend GREEN:6baseline failures remain, not waived.
- [ ] Real provider/compatible-recording and independent practitioner/rubric
  acceptance. No20/20 claim. No commit/merge/deploy authorization inferred.

Detailed original checklists below are the design task inventory, not a claim
that every source-correction/UI/provider variant was executed. Current evidence
and remaining limits are in acceptance, not the old dirty-main/base notes.

## Global Constraints

- S=E−A−P+R;8/4/20triệu; B ngoài phạm vi. Không đổi model/policy/grant sản phẩm để làm test xanh.
- Không suppress issue thật, giả0, waive FACT qua quyết định, hay biến instruction thành tiền đã nhận/đã chi.
- Không LLM viết câu hỏi; không provider call trong test/browser offline; không ngầm dùng recording cũ không khớp nguồn/config.
- Không sửa evaluation/scorer, frontend Verify, data/verify hoặc25 case gốc; các phần đó do task Verify sở hữu.
- Không ghi vào checkout/DB người dùng, port8000 hoặc Railway; không reset/stash/commit/push/deploy/merge. Bàn giao đầy đủ untracked assets.
- Base phải có SHA và dirty inventory. S6/interface thay đổi chưa commit không phải dependency đã được tích hợp.

## Review Focus

1. HTTP200/ANSWERED nhưng issue tái sinh sau reassess: test phải kiểm đúng hiệu lực, reload/restart và audit.
2. Compound E9/S8 bị duyệt bằng client amount nhỏ: derive từng action9/8 tại server, reject payload lách quyền và issue chéo root.
3. FACT arithmetic nhận text nhưng nguồn vẫn mâu thuẫn: giữ blocker; response sửa nguồn tạo revision thật, không sửa PDF hoặc history bằng SQL.
4. Routine xanh do thiếu issues bị che hoặc fixture bỏ qua admission: kiểm known E/A/P/R/S, refs, costs và active instructions qua composition thực.
5. UI mới ghi đè S6 hoặc metadata cũ vẫn duyệt sau Stop/source/grant đổi: kiểm cả luồng TC18 và stale/basis/epoch tại POST.

## File ownership và discovery

Primary: `domain/issues.py`, `reconciliation/policy.py`, module mới `workflow/question_cards.py`, module decision mới nếu persistence hiện có không đủ, tests mới mang prefix escalation/decision-card; frontend card mới và test riêng.

Shared hunks: `workflow/service.py` (_answer_issue/_decide/_build_assessment_input/_case_view), `workflow/evidence_assessment.py`, `api/routes.py`/`views.py`, `domain/case.py`/commands khi thật cần, schema migration nếu thật thiếu; `questions.tsx`, `types.ts`, `api.ts`. Không refactor toàn file. Không sửa/xóa ExceptionReview hoặc OcrRegionView của S6. Dùng file API client riêng cho card mới nếu giảm hunk chung.

Discovery đã có: QuestionCard→answerIssue→POST answers→_answer_issue; ExceptionReview→decideIssues→POST decisions→_decide→_assess_and_commit→_commit_assessment. Policy sinh AUTHORITY. Evidence path nạp exceptions từ S6. CodeGraph main có enginewarning, coverageUNKNOWN; executor kiểm lại trong worktree, fallback đọc exact source. Không suy tất cả đường hỗ trợ authority từ tên test hoặc có endpoint.

### Task 0: Khóa base và các dependency đang song song

**Files:** Create `.runtime/escalation-answerability/<run>/baseline.json`; không sửa main.

- [ ] Đọc spec/AGENTS/status/contracts; xác minh HEAD và worktree. Ưu tiên worktree mới branch `codex/escalation-answerability` từ commit tích hợp S6 đã bàn giao; nếu chưa có, dùng2a889d5f6f59387f1f621a5d1ee5c31a2758f04c, ghi rõ S6 chưa tích hợp. Không tự copy dirty main.
- [ ] Ghi ownership/shared hunks, graph limitations, toolchain và evidence paths; đọc các tests hiện có về questions, answer_loop, authority_scope, TC23 và S6 nếu có ở base.
- [ ] Chạy focused baseline, giữ failures. Không sửa baseline/date guard để làm xanh. Gate: biết code nào mình thực sự đang sửa và phần nào sẽ cần integration.

### Task 1: Khóa hành vi thường quy và phản ví dụ hỏi thừa

**Files:** Create `tests/integration/test_escalation_routine_regressions.py`; reuse current tests/helpers; chỉ sửa admission/policy nếu test tái hiện lỗi thuộc scope.
**Interfaces:** Consumes workflow command surface và source-backed ReadResult/context; produces initial CaseView assertions cho3 routine và các counterexamples.

- [ ] Viết literal expected cho E3240000/A4000000/P0/R0⇒COLLECT760000; E5400000/A5000000⇒PAY400000; E=A2160000⇒BALANCED, no instruction. Tất cả facts/policy/grants/identity đủ, có refs; input không chứa expected route/E đã ép từ gold.
- [ ] Chạy test và phân loại baseline. Test hiện xanh vẫn giữ làm regression; không tạo RED giả bằng xóa guard. Nếu có lỗi hỏi thừa, test phải fail ở chính issue không cần thiết trước khi sửa.
- [ ] Thêm đối chứng: UNKNOWN A vẫn unresolved, mâu thuẫn payer vẫn FACT, hai activity thật sự không phân biệt được vẫn cần xác nhận; fake TECHNICAL không được đổi thành FACT hoặc AUTO. Không nới linker chỉ để đạt zero-question.
- [ ] Sửa nhỏ nhất tại nguồn gây lỗi đã tái hiện; chạy lại routine+đối chứng. Gate: outcome/tiền/refs đúng, không chỉ issues=[];2routine có1 active instruction, balanced không lệnh0.

### Task 2: Thẻ có nguồn và response/action có kiểu, do server tạo

**Files:** Modify `domain/issues.py`; create `workflow/question_cards.py`, `tests/unit/test_escalation_question_cards.py`; minimal service/API wiring; frontend types/API client theo seam.
**Interfaces:** `CaseWorkflow.question_card(session: DemoSession, root_id: str, issue_id: str) -> QuestionCard`; read-only GET `/api/cases/{root_id}/issues/{issue_id}/card`. QuestionCard giữ fields hiện có, thêm case_version/basis_id/response_kind và typed actions có action/scope/amount/authorized/unavailable_reason khi cần. Legacy payload tương thích, thiếu capability không tự mặc định được phép.

- [ ] RED: FACT TC06 hiển thị3800000/2970000/830000/770000/60000 và đúng nguồn; TC25 có900000/700000/200000 và hai nguồn. AUTHORITY E9/A8 có action RECOGNIZE_COST9, giới hạn hệ thống8, actorgrant20 nếu đủ; không nhầm S1 với amount cần duyệt9.
- [ ] RED: giữ nguyên `00000101`, `PT-251026-016`, ngày06/10/2026; formatter không chèn ký hiệu tiền vào mã/ngày. Card bị thiếu metadata không được bịa quote/crop hoặc cấp action.
- [ ] Implement deterministic presenter từ dữ liệu hiện hành; không parse câu tiếng Việt để xác định quyền hoặc arithmetic. Reuse issue basis/refs và projection/structured findings. Message nói rõ quyết định không ghi nhận tiền.
- [ ] Integration test GET không provider/network calls, không mutation/version bump và không đọc root/issue ngoài phạm vi. Gate: card đủ dữ kiện và quyền action được server xác định, chưa phải authorization vĩnh viễn.

### Task 3: Quyết định authority thực sự có hiệu lực và không bypass FACT

**Files:** Create `tests/integration/test_escalation_decision_roundtrip.py`; modify service/API narrow hunks; add decision persistence module/migration nếu thiếu, thêm input consumption đúng đường evidence và STUB.
**Interfaces:** Reuse `Decide(root_id, DecisionCommand)` và POST decisions. `decision.actions` chỉ chọn action đang được yêu cầu cho issue/root này; effect amount từng action được server derive. Single amount cũ chỉ là assertion phải khớp khi áp dụng; compound không dùng một amount do client gửi để kiểm mọi action. Không mở endpoint ghi tùy ý system grant.

- [ ] RED: initial E9/A8/P=R0, đủ facts/policy ⇒AUTHORITY/no instruction. Approver cógrant20 quyết định công nhận9 ⇒issue đó hết, PAY1 chỉ khi các gate còn lại sạch; reload/reassess/restart giữ quyết định, P vẫn0, chưaSETTLED.
- [ ] RED: E9/A1 compound RECOGNIZE_COST9 + ISSUE_PAYMENT8. Thiếu một quyền thì không partial mutation; amount client1/sai scope/sai profile/issue chéo root/kind-action sai/empty issues đều bị từ chối và không instruction/decision hiệu lực.
- [ ] RED:25triệu với grant20 vẫn chặn và giải thích cần cấp cao hơn; unresolved FACT độc lập vẫn chặn sau quyết định. Authority “chưa phê duyệt” không tự loại chi hoặc sửa T/E.
- [ ] RED: stale expected version/basis, Stop, source đổi và grant revoked/expired không được áp dụng preview cũ. Receipt đúng chỉ đổi money basis không tự yêu cầu công nhận lại E nếu cost basis hợp lệ không đổi.
- [ ] Implement validation và persistence dựa trên các seam domain/decision sẵn có; không chỉ UPDATE issue status trước reassess. Nếu thêm migration, chọn version sau integration hiện có, test upgrade DB và dữ liệu cũ; không sửa migration đã phát hành hoặc cấp systemgrant rộng hơn.
- [ ] Pin audit actor/issue/action/effect/basis/reason/grant/ref; quyết định cùng command replay không trùng, mọi gate kiểm lại ở commit. Chạy authority_scope, controls_races, financial_verification và TC23. Gate: hiệu lực stateful được chứng minh, không chỉ HTTP200.
- [ ] Cập nhật test authority_scope cũ đang dùng issueFACT để kiểm quyết định trong hạn mức: giữ kiểm max20triệu inclusive nhưng dùng fixtureAUTHORITY đúng action/basis; bổ sung test FACT không được quyết định chung waive. Không xóa test quyền hoặc gọi expectation mới lỏng hơn là baseline fix.

### Task 4: FACT/POLICY response đúng loại và không thành phê duyệt chung

**Files:** Create `tests/integration/test_escalation_fact_policy_roundtrip.py`; narrow answer/decision guards; reuse S6 missing-evidence tests khi tích hợp.
**Interfaces:** FACT hợp lệ dùng AnswerIssue hoặc evidence/declaration revision hiện có; POLICY/authority dùng Decide với scope/rights. `/answers` không được xử lý POLICY/AUTHORITY như financial fact hoặc báo đã giải quyết trong khi chưa áp dụng.

- [ ] RED: answer kind/owner/basis không khớp bị từ chối; Q32 invoice-scoped giữ đúngamount/employee/invoice/refs bounds. Text “đồng ý” không waive arithmetic/payer hoặc tạo grant.
- [ ] RED: TC06 nguồn vẫn mâu thuẫn thì vẫn blocker; một response có chứng từ/kê khai sửa hợp lệ tạo revision, đọc lại qua adapter deterministic rồi tái đối soát; nguồn/audit cũ giữ lịch sử, không còn dùng số cũ làm effective basis. Nếu correction flow hiện chưa đủ, bổ sung đúng seam này, không force-resolve issue bằng SQL.
- [ ] Pin one issue resolved không được xóa issue độc lập. Technical/incomplete có hướng retry/bổ sung thích hợp, không giả câu hỏi dữ kiện.
- [ ] Reuse S6 ExceptionReview/preview/persistence cho missing-evidence; grant trong test chỉ là fixture riêng, không hạn mức sản phẩm mới. Facts còn mâu thuẫn thì accept không làm phát hành tiền. Gate: FACT và POLICY độc lập, reason đúng rule/khoản, response không ghi A/P/R.

### Task 5: UI thẻ quyết định, rõ hành động và giới hạn

**Files:** Create `frontend/src/features/decision_card.tsx`, `frontend/tests/decision-card.test.tsx`; narrow changes questions.tsx, API client/types. Giữ ExceptionReview/OcrRegionView của S6 sau integration.
**Interfaces:** Card nhận QuestionCard do server trả và current case; dùng đúng expected_version/basis, gọi endpoint theo response_kind; cập nhật từ server response, không optimistic financial settlement.

- [ ] RED component tests: FACT nhập trường phù hợp hoặc bổ sung nguồn; AUTHORITY có số cần công nhận/phát hành, giới hạn/quyền và reason; gọi decisions thay vì answers; không có quyền thì disabled kèm lý do; preview stale khi case đổi phải refresh.
- [ ] RED: compound có thể quyết định một lần đúng mọi action; không nút “duyệt tất cả” waive blockers. E25 vượt quyền20 không hiện lời hứa duyệt; không suy refusal thành personal expense. Correct refs/quotes luôn nhìn được trong card, không bắt mở toànPDF để hiểu câu hỏi.
- [ ] Implement card và error handling tiếng Việt; giữ invoice IDs/ngày; không LLM request; không đổi UI Verify hoặc intake. Render TC18/S6 exception và OCR region như cũ.
- [ ] Chạy Vitest nhóm cards/questions/intake và production build đúng Nodepin. Gate: kiểm đúng payload/action, component không được thay browser acceptance.

### Task 6: Browser, integration và bằng chứng barem8–6–6

**Files:** Create `frontend/e2e/escalation-answerability.spec.ts`, fixture-DB seed dưới scripts/tests scope riêng; acceptance `docs/final/reviews/2026-10-16-escalation-answerability-acceptance.md`.
**Interfaces:** Dùng app/runtime thực với fixture/replay adapter offline, DB/uploads/artifacts và port riêng. Không endpoint test nào nhận gold để ép state; seed nguồn/context là test input, ghi mode rõ.

- [ ] Browser3routine: đầu vào đủ ⇒thu760k/chi400k/cân bằng, không issue thừa; draft confirmation và accountant actual-money confirmation không bị đếm thành escalation ngoại lệ. Khi data/verify/VFY-BAL-01 đã bàn giao, reuse manifest/recording đúnghash để nghiệm thu integration; chưa có thì ghi dependencyNOT_RUN, không tạo dataset trùng.
- [ ] Browser card-only: FACT hiển thị hai phía/đúngowner; response sửa hợp lệ đi đúngrevision. AUTHORITY9 córeason→decision→PAY1→reload vẫn đúng;25khôngduyệt. POLICY exception dùng S6 đi đúng decision, không phá facts. Giữ screenshots, network request metadata an toàn và JSON/DB trước-sau.
- [ ] Tự đánh giá checklist câu hỏi: hiểu vấn đề, biết cần làm gì, thấy nguồn/số, thực hiện response không cần giải thích từ đội thi. Đây là engineering rehearsal; không gọi là3 practitioner hoặc human UX proof.
- [ ] Sau khi tích hợp S6 + task này + Verify: chạy focused của cả ba, full backend/frontend/build và browser checkpoints trên cùng SHA/digest. Source thay sau test thì nghiệm thu lại phần bị ảnh hưởng. Không merge main dirty/overwrite wholefile; integrator duy nhất xử lý shared hunks.
- [ ] Báo số case/issue và các gate PASS/FAIL/NOT_RUN. Giữ failures, không dùng scorer Verify chưa chốt làm oracle của tests. LIVE và năm case mới giám khảo vẫn NOT_RUN nếu chưa thực hiện; không tuyên bố20/20.

## Handoff

- Bàn giao base SHA, tracked diff, mọi untracked module/test/asset và migration dự kiến, shared-hunk map, đoạn status/runbook update để integrator nhập sau.
- Agent Verify giữ ownership suite/scorer/data/recordings; agent S6 giữ baseline integration của intake/exception/OCR. Task này sở hữu question-card/authority response loop, không viết song song cùng hunk.
- Chỉ đánh dấu checkbox theo bằng chứng. Acceptance tách code/offline/browser/combined/LIVE; lỗi baseline ghi tên và tái hiện, không waive lỗi mới.
- Không commit/push/deploy/merge trong task này. Plan/spec này là tài liệu mới; không thay code ứng dụng ở lượt lập kế hoạch.

## Self-review của người viết plan

- Scope/spec: routine và đối chứng→Task1; nội dung/card→Task2; authority có hiệu lực→Task3; FACT/POLICY→Task4; responseUI→Task5; browser/bản kết hợp→Task6.
- Không tự trừ điểm từ case chưa chạy; không coi3routine fixtures là holdout hoặc practitioner evidence. Đích20/20 vẫn cần bài kiểm độc lập sau này.
- File ownership: evaluation/data/Verify không thuộc task; S6 có dependency và hunk map, không snapshot/commit dirty code của agent khác.
- ReviewFocus1–5 đều có regression cụ thể trong tasks; receipt/cost basis, compound amount, stale/source/Stop/grant và source correction không bị bỏ qua.
- Các seam mới là thiết kế giao agent, chưa gọi là implementation. Chỉ schema/migration khi seam persistence hiện có thật sự thiếu; không áp đặt số migration trước tích hợp S6.

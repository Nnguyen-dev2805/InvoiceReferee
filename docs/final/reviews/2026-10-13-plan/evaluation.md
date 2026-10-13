# Independent review — competition proof, evaluation and adaptive feedback

Ngày review: 13/10/2026. Vai trò: independent plan reviewer (evaluation/contest), **không phải implementer**.

**Verdict duy nhất: REVISE BEFORE IMPLEMENTATION DISPATCH (sửa hợp đồng chứng minh, giữ kiến trúc và phạm vi đã chốt).**

Plan đã chứa đường thực hiện phù hợp để chứng minh đề A, nhưng còn **4 chỗ chưa khóa đủ điều kiện để coding agent xây một phép đánh giá tái lập và kết luận đúng**: recovery selection, tính tương đương counterfactual của H/R, phép đo gain khi kích hoạt threshold, và release gate unsafe conclusion. Tôi không coi việc chưa chạy M0/Verify, chưa có 3 practitioner, hay chưa có public URL là blocker của *bản kế hoạch*: đó là công việc/bằng chứng phải làm ở T5/T9–T13. Những điểm này chỉ được tuyên bố đạt sau khi có chứng cứ chạy.

## Source boundary và phương pháp

- Snapshot kiểm đúng: [plan](../../../superpowers/plans/2026-10-13-invoice-referee-final.md) SHA-256 **5656076bbe90c5ef138ef2672b82a3576b4f960d2468ade6744f143865f59637**; [contracts](../../IMPLEMENTATION_CONTRACTS.md) SHA-256 **b459b1a99df2a019527da5cfc75b58c5f4a386f5c5ec33bf5451e11ac44a0893**.
- Source of authority: [brief gốc](../../../Challenge_Brief_OrganizationAI_VN.docx.md), [thiết kế Q1–Q31](../../ARCHITECTURE_AND_EVALUATION.md), [disposition](../2026-10-13/SYNTHESIS.md). Đối chiếu đặc biệt T4–T5/T9–T13 và card/execute UI ở T6–T8.
- **Document-only Verify tier** theo giới hạn dispatch. Parent CodeGraph explicit projectPath trả “This project has nothing indexed”; không có list_projects/index_status/check_index_coverage khả dụng; generation/coverage **unknown**. Tôi chỉ đọc nguồn tài liệu non-code, không gọi graph/code/call-chain, không kiểm app/runtime, không tuyên bố toàn bộ repo đã được chứng minh.
- Severity: **P1 / plan-blocking** = hai implementer có thể xây hai phép chấm/route khác nhau mà cả hai vẫn có thể tuyên bố tuân plan; cần khóa hợp đồng/acceptance trước khi dispatch. **P2 / builder acceptance** = bổ sung fixture/test/gate khi triển khai, không đòi chạy xong trước khi cho phép lập plan. **External unknown** = kết quả/điều kiện ngoài repo; không dùng suy đoán làm bằng chứng.

## Findings

### EV-P01 — [P1 / plan-blocking] Release gate dùng “human miss” có thể báo xanh khi đã khẳng định sai mà không tạo instruction

**Nguồn:** [brief:55–59](../../../Challenge_Brief_OrganizationAI_VN.docx.md#L55-L59) cấm kết luận khẳng định ở input nghi vấn; [synthesis:86–103](../2026-10-13/SYNTHESIS.md#L86-L103) đã yêu cầu union; [contracts:201–208](../../IMPLEMENTATION_CONTRACTS.md#L201-L208) định nghĩa unsafe_action, unsafe_affirmative_conclusion, union_dangerous_miss; [plan:225–233](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L225-L233) có test false S0, nhưng [plan:275–279](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L275-L279) chỉ đặt holdout target “0/10humanmiss”.

**Counterexample tối thiểu:** Trong 10 human-required roots, 9 hỏi đúng, 1 thiếu history coverage nhưng app tuyên bố “đã cân bằng S=0” và không tạo instruction. unsafe_action=0/10; unsafe_affirmative_conclusion=1/10; union_dangerous_miss=1/10. Nếu T12 chỉ so “human miss” theo định nghĩa [architecture:322–337](../../ARCHITECTURE_AND_EVALUATION.md#L322-L337) (đã phát hành action), báo cáo có thể hiện “0/10 miss” dù vi phạm cấm kết luận.

**Sửa tối thiểu:** Khóa hai chỉ số và gate riêng: (i) missed-human-by-action, (ii) dangerous union (action OR affirmative unsupported, de-duplicate **theo dossier**), route/owner errors thêm chỉ số riêng. **Release critical gate phải fail khi union >0**; zero instruction không tự là abstention đúng. Báo cả numerator/denominator, processing failures trong toàn submissions, trạng thái abstain/technical riêng. Không đổi policy/quyền/luồng tiền đã chốt.

**Acceptance:** Unit fixture 10 human-required, 1 false S0/no instruction: action-miss=0, affirmative-miss=1, union=1 và release verdict **FAIL**. Fixture phát cả instruction sai + khẳng định sai trên cùng root cho union=1, không đếm hai. Lặp gate trên LIVE holdout; không tuyên bố chứng minh khi N=0.

### EV-P02 — [P1 / plan-blocking] Một opportunity có nhiều eligible reads nhưng thuật toán score → bước R chưa xác định duy nhất

**Nguồn:** [contracts:210–215](../../IMPLEMENTATION_CONTRACTS.md#L210-L215) gán mức 1/.75/.5/.25 cho bốn representation, “R=one eligible extra read”; [contracts:36](../../IMPLEMENTATION_CONTRACTS.md#L36), [contracts:269–270](../../IMPLEMENTATION_CONTRACTS.md#L269-L270) có eligible_steps/AllowedStep; [plan:254–269](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L254-L269) yêu cầu choose_action nhưng không khóa tổ hợp score, precedence, ties và step ID.

**Counterexample tối thiểu:** Một issue có đồng thời native text từ source khác (score 1) và ảnh khác (score .5), native text mâu thuẫn số tiền với ảnh hiện tại. Implementer A dùng max=1, đọc native; implementer B lấy representation chưa từng đọc, thử ảnh; cả hai đều có thể nói đã dùng “score 1/.5”, nhưng resulting outcome/calls/threshold flip khác nhau. Nếu không pin step trước branch, scorer không xác định được đối chứng nào đã được đo.

**Sửa tối thiểu:** Định nghĩa hàm quyết định từ **frozen eligible-step set** → một (score, selected_step_id) hoặc H; luật xử lý multi-step/tie, thứ tự/chi phí, threshold comparator (>= hay >), loại bước không còn quyền/trong ngân sách, tiêu chí “đã đọc rồi”, và identity của representation/page/fields. Bảo toàn guard chất lượng: score là ưu tiên *thử đọc*, không biến conflicting output thành KNOWN. Đây là lựa chọn kỹ thuật của lead, không phải yêu cầu đổi business rules.

**Acceptance:** Parametric fixture đủ cả bốn mức, equality tại threshold, multi-step và tie; hai lần đánh giá cùng pre-state ra cùng action, selected source/page/fields và score; conflicting 450/480 sau R vẫn FACT, không tự kết luận 450. Candidate threshold đổi action chỉ ở opportunity có score đúng ngưỡng.

### EV-P03 — [P1 / plan-blocking] “Same initial snapshot” trong paired H/R chưa khóa số lượt/cơ hội recovery còn lại

**Nguồn:** [contracts:153–156](../../IMPLEMENTATION_CONTRACTS.md#L153-L156) ReadSet có versions nhưng không mô tả budget; [contracts:177–185](../../IMPLEMENTATION_CONTRACTS.md#L177-L185) quy định counters dùng chung preview/submit/resume; [contracts:216–218](../../IMPLEMENTATION_CONTRACTS.md#L216-L218) paired H/R; [plan:178–180](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L178-L180) có test counters; [plan:257–268](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L257-L268) frozen initial read-set/sources nhưng không nêu snapshot **remaining RunBudget/recovery usage** trong pair.

**Counterexample tối thiểu:** Preview đã dùng hết OCR attempts trên một root; current submit chỉ được phép H. Offline candidate R chạy trên DB sandbox khởi tạo budget mới (10 OCR attempts) và đọc được số tiền, còn H chạy đúng exhausted budget. Paired output báo R tự giải quyết dù route đó **không thể chạy** từ trạng thái production ban đầu.

**Sửa tối thiểu:** Trước khi chọn R/H lưu immutable opportunity snapshot gồm ReadSet, source digests/representations, issue/dependencies, eligibility, **attempt counters/remaining budget, recovery-per-field key, deadline state**, pinned model/prompt/policy/read-config. Fork cả hai từ **cùng** snapshot và điều kiện gọi provider; không reset budget/recovery theo branch, không tái sử dụng nguồn mà H mới bổ sung (điểm cuối đã được plan giữ đúng). Phân biệt counterfactual REPLAY policy-only với tác dụng LIVE thực đo.

**Acceptance:** Test preview exhausted -> R ineligible cả real và replay; test preview→submit→Resume cùng material basis không hồi phục quyền đọc; test H cung cấp nguồn mới nhưng R paired initial không thấy source đó. Report xuất comparator snapshot digest và các trường được pin cho từng pair; diff chỉ ở action được thử.

### EV-P04 — [P1 / plan-blocking] Activation có flip và gain tổng, nhưng chưa buộc gain phát sinh từ route thực sự đổi

**Nguồn:** [synthesis:104–124](../2026-10-13/SYNTHESIS.md#L104-L124) yêu cầu đối chứng/changed routing đúng; [contracts:216–232](../../IMPLEMENTATION_CONTRACTS.md#L216-L232) đặt 10 calibration, 10 validation, ≥1 flip và ≥1 extra correct completion **hoặc** giảm unnecessary questions; [plan:266–269](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L266-L269) paired/frozen recordings và gate nhưng chưa khóa gain ở **changed opportunities**, hay rubric “câu hỏi tránh được” với initial uncertainty.

**Counterexample tối thiểu:** Candidate flip một opportunity FACT→R nhưng R vẫn thiếu proof rồi hỏi người. Một case thứ hai giữ nguyên R ở cả thresholds, provider LIVE ngẫu nhiên đọc tốt hơn trong lần candidate; aggregate completion tăng một. Điều kiện “≥1 flip” + “≥1 completion tăng” có thể đều xanh dù threshold không tạo ích lợi nhân quả. Tương tự, H có thể bị ghi “unnecessary” chỉ vì latent answer tồn tại, dù tại initial snapshot không có cách đọc đủ căn cứ.

**Sửa tối thiểu:** Preregister chính xác đơn vị **opportunity before R/H**, cách bucket bốn mức được gán khi nhiều steps, comparator fixed 0.75 vs candidate, và paired ledger từng root: same snapshot, baseline action/outcome, candidate action/outcome, evidence support, question necessity, calls/time, invariant failure. **Activation gain phải có ít nhất một safe, supported, beneficial changed opportunity** theo replay counterfactual; aggregate và tài nguyên là gates bổ sung, không thay điều kiện này. Một H question chỉ “avoidable” nếu paired eligible R thực tế tạo bằng chứng đủ trong quota; hỏi khi raw chưa đủ căn cứ tự nó không phải false escalation. Calibration chọn threshold; validation chỉ chấm một threshold đã khóa, không thử lại sau khi nhìn validation.

**Acceptance:** Fixture nêu trên (flip vô ích + gain do noise trên unchanged route) bị reject. Fixture flip H→R, R thu được source-supported fact, không hỏi owner, không unsafe, có counts/calls thật thì có thể pass các *candidate gates*; vẫn cần verified human feedback + independent validation mới **activate**. In ra changed/unchanged opportunity counts và denominator riêng; nếu support/flip/gain thiếu, fixed vẫn active và Sprint2 adaptation **unmet**.

### EV-P05 — [P2 / builder acceptance] Core4 dùng “personal/noadvance rejection” nhưng chưa khóa dạng từ chối quan sát được

**Nguồn:** [brief:171–173](../../../Challenge_Brief_OrganizationAI_VN.docx.md#L171-L173) bắt buộc Core4 có ≥1 reject/escalation; [plan:225–241](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L225-L241) chọn ba routine + personal/noadvance rejection; [architecture:114–140](../../ARCHITECTURE_AND_EVALUATION.md#L114-L140) cho S=0 đủ căn cứ được kết luận cân bằng; [contracts:26–37](../../IMPLEMENTATION_CONTRACTS.md#L26-L37) chưa quy định observable outcome từ chối cụ thể trong CaseView.

**Counterexample tối thiểu:** Khoản cá nhân đã xác minh, A=P=R=0 và ledger coverage đủ → E=0, S=0. UI trả “Đã cân bằng, không tạo yêu cầu” giống routine zero-balance, không cho giám khảo thấy **từ chối hoàn khoản chi cá nhân**. Nếu một bảng Verify gọi đó là REJECT bằng case ID/hardcoded label, đáp ứng brief chưa được chứng minh.

**Sửa tối thiểu:** Giữ Core4 composition đã chọn; đóng đinh expected observable: khoản yêu cầu nào bị loại, lý do/căn cứ và kết luận không hoàn khoản đó; không false “nguồn thiếu = từ chối”, không cần phát minh REJECTED workflow state mới. Scorer kiểm actual business decision/expense exclusion từ workflow/DB, không trust tên case.

**Acceptance:** Trên public Core4 sau fresh session, case thứ tư có expense rejection + refs/rule đúng và ledger đủ, no payment instruction; case balanced legitimate khác thể hiện “đủ căn cứ S0” mà không bị chấm nhầm là reject. Một click chạy cả bốn tuần tự và bảng PASS/FAIL/expected/actual/mode/timestamp.

### EV-P06 — [P2 / builder acceptance] Card-only một phản hồi chưa có browser acceptance đủ cả FACT/POLICY/AUTHORITY

**Nguồn:** [brief:49–77](../../../Challenge_Brief_OrganizationAI_VN.docx.md#L49-L77) yêu cầu ba nhóm, hỏi cụ thể đủ một câu trả lời; [contracts:207–208](../../IMPLEMENTATION_CONTRACTS.md#L207-L208) rubric card; [plan:165–183](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L165-L183) T6 headed UI chủ yếu routine/FACT; [plan:233–242](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L233-L242) Esc5 cho FACT + AUTHORITY, POLICY tách sang development; [plan:279–282](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L279-L282) user trials card-only nói chung.

**Counterexample tối thiểu:** POLICY T>B và cho phép ngoại lệ; card chỉ hỏi “Có đồng ý ngoại lệ không?” nhưng không hiện rule, chênh lệch, affected expenses, scope hay basis. Manager phải quay về mở hồ sơ gốc để quyết định; backend test route POLICY và button Decide vẫn có thể xanh. Hoặc AUTHORITY card nói “Cần phê duyệt” mà không nêu action là RECOGNIZE_COST hay ISSUE_PAYMENT và mức cần cấp quyền.

**Sửa tối thiểu:** Pin 3 card-only scenarios ở T9/T10/T12, ít nhất một per FACT/POLICY/AUTHORITY trong development hoặc Verify (không bắt đổi Esc5 3+2 đã chọn). Người đúng vai trò nhận question, known facts + crop/excerpt + refs/rule + exact decision/amount/effect scope; thực hiện **một response hợp lệ để giải quyết issue đó** và recheck những issue phụ thuộc, không giả phải giải quyết toàn dossier bằng một câu.

**Acceptance:** Browser flow với actor chỉ nhìn card (không mở tài liệu gốc), quyết định được fact/exception/action; wrong actor/expired scope không resolve; after answer history/refs/basis audit còn nguyên, issued effect chỉ khi toàn gates đã đạt. Human rubric có positive và false-pass (card chung chung) probes; LLM judge nếu dùng chỉ được calibrated supporting, không thay rule/oracle tiền.

### EV-P07 — [P2 / builder acceptance] Gold observable đã được thiết kế đúng hướng, nhưng thiếu assert cho “guess đúng latent, sai căn cứ”

**Nguồn:** [synthesis:127–135](../2026-10-13/SYNTHESIS.md#L127-L135) phân biệt latent vs observable; [plan:127–143](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L127-L143) generator + visual adjudication; [contracts:189–206](../../IMPLEMENTATION_CONTRACTS.md#L189-L206) gold3 lớp và không thưởng đoán đúng vì latent; [plan:227–236](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L227-L236) scorer tests tập trung false S0/ref/owner.

**Counterexample tối thiểu:** PDF nhân tạo ghi 450.000 nhưng khi render mờ còn có thể đọc thành 480.000; latent.json giữ 450.000. Model tự khẳng định 450.000 đúng ngẫu nhiên, refs dẫn đến vùng mờ. Scorer so trị số với latent sẽ cho pass, dù gold.observable phải là CONFLICT/UNREADABLE, allowed là FACT và không commit tiền.

**Sửa tối thiểu:** T4 tạo manifest nguồn/gold trước runtime, adjudication observable **từ trang render** và ghi rõ ambiguous quality (blind với seed nếu khả thi; ít nhất ghi lựa chọn và reason). T9 test against allowed + observable support first; latent only dùng đối chiếu thử nghiệm, không đủ để chấm known-money pass. Synthetic là hợp lệ theo brief, không đòi invoice người thật.

**Acceptance:** Exact-match guessed 450 vẫn FAIL unsupported affirmative; safely asking “450 hay 480?” PASS issue/owner/card; raw scan có text layer450 nhưng ảnh480 bắt contradiction, không mặc nhiên ưu tiên native. Dữ liệu run ghi rõ raw/gold synthetic, packet digest, model/mode.

### EV-P08 — [P2 / builder acceptance] Chặn contamination theo family/layout/issuer muộn hơn thời điểm freeze holdout

**Nguồn:** [architecture:314–321](../../ARCHITECTURE_AND_EVALUATION.md#L314-L321) yêu cầu group by origin/family/layout/issuer; [plan:129–143](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L129-L143) T4 mới test root/economic clone; [plan:274–278](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L274-L278) T12 mới test family cross-split sau development/baseline/T11.

**Counterexample tối thiểu:** 15 dev + 20 holdout đều từ cùng 1 invoice template/issuer và cùng layout, chỉ đổi số/người/file digest; root/economic keys khác nên T4 PASS. Đến T12 mới phát hiện leakage, lúc đó holdout đã được xem/chạy và model/threshold có thể đã chọn trên cấu trúc gần trùng.

**Sửa tối thiểu:** Chuyển thêm guard group/family/layout/issuer và manifest digest **sang T4 pre-M0**; ở T12 xác nhận lại snapshot freeze, không coi phép check cuối là lần đầu. Ghi rõ mức độ độc lập thực tế nếu nguồn gốc template không thể tách sâu; không khẳng định ngoài family đã thử.

**Acceptance:** Hai packets giữ root/economic distinct nhưng chung family bị group-split guard phát hiện; holdout author/freeze log trước việc chọn model/threshold, việc thay gold hoặc dùng để tune invalidates holdout. Giữ 15/20 denominator unique roots; mutations hoặc scans cùng nghĩa vụ không được đếm thêm.

### EV-P09 — [P2 / builder acceptance] Issue-stage scorer cần test dependency qua hai revision, tránh một nhãn initial che cả quá trình

**Nguồn:** [contracts:201–208](../../IMPLEMENTATION_CONTRACTS.md#L201-L208) đặt issue-stage/dependencies/owner; [architecture:129–140](../../ARCHITECTURE_AND_EVALUATION.md#L129-L140) FACT trước AUTHORITY phụ thuộc; [plan:235–237](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L235-L237) ghi “dependency sets/timelines” nhưng không có test concrete cho stage transition; [plan:140–141](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L140-L141) holdout có co-occurrence/stages.

**Counterexample tối thiểu:** Payer ban đầu UNKNOWN, sau một Answer FACT có căn cứ, E vượt 8 triệu nên phát sinh AUTHORITY. Nếu scorer chỉ chấm trạng thái initial FACT là “correct escalation” và assisted cuối ra đúng số, có thể bỏ qua việc app không tạo AUTHORITY sau recheck, hoặc đếm AUTHORITY chưa thể yêu cầu ở stage đầu là miss.

**Sửa tối thiểu:** Test issue-stage ledger theo (root, material revision, issue/dependency): expected enabled/blocked set, group, owner, actionable card, resolved/pending; điểm routine/human denominator ở **dossier**, issue-stage là phụ trợ có mẫu số khác. Không cho human-assisted final che initial; không phạt issue phụ thuộc chưa sẵn ở stage trước.

**Acceptance:** Two-stage fixture FACT→AUTHORITY được chấm đúng từng bước; route chỉ hỏi FACT rồi dừng và claim SETTLED bị FAIL; AUTHORITY hỏi sai owner FAIL; resumed valid grant/rule recheck đúng thì mark assisted, không cộng thêm independent dossier.

### EV-P10 — [P2 / builder acceptance] Calibration cần human-verified labels; validation cần independent oracle và raw manifests rõ ràng

**Nguồn:** [contracts:196–199](../../IMPLEMENTATION_CONTRACTS.md#L196-L199) định danh ≥10 calibration + ≥10 validation root opportunities distinct, origin; [plan:127–143](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L127-L143) T4 author development/holdout; [plan:244–251](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L244-L251) T10 thu labels; [plan:254–270](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L254-L270) T11 chọn/validate threshold, nhưng chưa gán substep chịu trách nhiệm author/freeze manifests của hai tập và mapping feedback ↔ opportunity pre-decision.

**Counterexample tối thiểu:** Pilot có 3 practitioner với 20 clicks, chỉ 4 unique roots hoặc feedback chủ yếu là “đồng ý”/hậu human correction. Nếu coi clicks là 20 calibration samples, report xanh dù thiếu 10 root opportunities có human-verified feedback; nếu dùng cùng bốn roots để validation thì chứng cứ độc lập cũng hỏng. Plan đã viết fallback fixed; cần test giữ nguyên fallback, không giả activation.

**Sửa tối thiểu:** Giao T10/T11 bước author/source-freeze calibration & validation raw/context/observable/allowed, group-split preselect, link each verified human assertion ở **calibration** với initial basis + source/correction/actor/provenance; khóa **10 calibration distinct roots có verified feedback** và **10 validation distinct roots có independent gold**, không trùng nhau hoặc holdout. Validation có thể dùng oracle độc lập mà không phải tự nhận có human feedback trên cả 10. Không buộc 3 practitioner sinh 20 cases; có thể có internal real feedback (claim giới hạn), hoặc giữ fixed. Gold-scoring, model-generated feedback, clicks và simulated labels không tự thành verified human evidence.

**Acceptance:** Test 20 feedback clicks/4 roots, invented identity, click approval, feedback after source update, unverifiable correction đều không làm đủ **calibration** support; 10 calibration roots verified + 10 separate validation roots independently adjudicated mới có thể vào activation gate. Report model/config/threshold selection IDs/validation IDs/reason for reject/rollback; không dùng final holdout chọn threshold.

## Điểm mạnh đã kiểm từ tài liệu

1. **Đường raw → result thực sự được đặt làm acceptance:** T4 yêu cầu raw PDF/images, model chỉ nhận input, gold sau run; T5 LIVE scan/hybrid, T9 runner đi qua preview/Submit/job/DB, Core4/Esc5 dùng cùng workflow. [Plan:127–162](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L127-L162), [225–242](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L225-L242). Đây là cách đúng để kiểm khả năng nhận input mới; chỉ cần thực hiện và chứng minh.
2. **Fail closed với nguồn/tiền và lỗi kỹ thuật:** Không dùng expected trong app; false S0 được đưa vào scorer; provider NOT_READ/ERROR không tính thành MISSING hoặc “escalation tốt”; bản ghi raw/draft/assisted và human wrong-owner tách. [Contracts:43–66](../../IMPLEMENTATION_CONTRACTS.md#L43-L66), [189–208](../../IMPLEMENTATION_CONTRACTS.md#L189-L208), [plan:227–236](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L227-L236).
3. **Ranh giới autonomous có thể quan sát:** Routine phát instruction đúng scope, execution/actual riêng; question card gắn owner/basis; Stop/Override/audit có browser và race checkpoints. [Plan:165–219](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L165-L219). Không cần bắt nhân viên duyệt lại từng routine.
4. **Phân loại evidence trung thực:** Fixed fallback nếu feedback insufficient; paired offline không giả observed counterfactual; recorded replay khác LIVE; practitioner thật và negative burden là gate riêng. [Contracts:216–232](../../IMPLEMENTATION_CONTRACTS.md#L216-L232), [plan:244–285](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L244-L285). Đây là nền phù hợp hơn việc báo tỷ lệ thành công của một judge cùng hệ thống.
5. **Giữ phạm vi đã quyết định:** Synthetic company, travel trước; local meeting conditional T13; brief cho synthetic nếu disclosure rõ. [Brief:33–39](../../../Challenge_Brief_OrganizationAI_VN.docx.md#L33-L39), [plan:286–295](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L286-L295). Tôi không đề nghị mở FX/vendor refund/multi-claim workflows, hay đổi 8/4/20.

## Evidence phải có lúc build/release — chưa thể xác nhận từ plan

| Phạm vi | Runtime artifact phải xuất | Claim hợp lệ khi chưa đủ |
| --- | --- | --- |
| M0 + baseline T5/T9 | 4 raw probes, LIVE attempt log (errors cũng giữ), effective model/prompt/schema/cost usage hoặc unknown, p50/p95/N, nguồn/refs/observed support; candidate cùng tập dev | “Chưa kiểm live”, không gắn STUB/replay thành kết quả provider |
| Core4/Esc5 T9/T10 | Public clean-browser, no signup, one action Core4 tuần tự 4 ca ≥1 explicit reject/escalation; Esc5 3auto/2human; expected/actual source-supported/owner/card, DB result, time/mode, end-to-end wall clock (Core target120s, Esc target90s) | Nếu suite quá thời hạn hoặc key lỗi: FAIL/LIMIT thật; thiết kế parallelism không phải proof latency |
| Two unseen raw cases / control T10/T13 | Mỗi case qua chính entry intake/context, source không biết trước; trace/Stop/Override/audit basis/result trong clean tenant; no special case-ID branches | Demo fixed packets không chứng minh generalized input |
| Holdout T12 | 20 distinct frozen roots 10/10; union harms, action misses, route/owner/card, unnecessary questions, correct auto outcomes, false-known/support, processing failures/N, limits/resource; only one clean LIVE run at locked version | 0/10 observed **trong tập synthetic pilot** không là 0 production risk |
| Real feedback/adaptation T10–T12 | Human-written/verified calibration feedback cho 10 distinct roots; independent gold validation cho 10 roots khác; paired opportunity ledger, changed-route gain + accepted/failed gate, rollback, code/version diff | Không đủ support: fixed + adaptation unmet; internal humans ≠ 3 practitioner impact |
| Practitioner impact T2/T10/T12 | ≥3 người làm nghiệp vụ thật/role/consent, matched counterbalanced manual/app tasks, time hands-on/wait/elapsed + mọi actor, onboarding, correction/rework, negative effects, verbatim feedback, một product change traceable | Không có người thật/baseline đối chứng: không claim Sprint2/ROI |

**External unknown (không đánh thành lỗi plan):** Tình trạng vòng thi, quyền hợp lệ, lịch và submission history, URL/host/credentials, mô hình thật khả dụng, 3 người tham gia và phản hồi đều chưa thể suy từ các tài liệu. Plan T13 có preflight [plan:291–295](../../../superpowers/plans/2026-10-13-invoice-referee-final.md#L291-L295). Brief gốc ghi khóa 15/10/2026 và Demo Day 17/10/2026 [brief:231–242](../../../Challenge_Brief_OrganizationAI_VN.docx.md#L231-L242); đó là **lịch trong nguồn**, không chứng minh tình trạng thực tế hiện tại/được gia hạn.

## Minimal repair / handoff order

1. **Trước giao task coding:** sửa EV-P01–P04 trong plan+contract: release unsafe union gate; deterministic eligibility/step selection; paired immutable budget snapshot; changed-route-specific activation evidence. Dùng fixture phản ví dụ trong findings làm acceptance, không thêm framework hoặc đổi business policy.
2. **Gắn vào bước code/test hiện có:** EV-P05–P10 ở T4/T6/T9/T10/T11/T12. Đưa split guard sớm, scorer phản ví dụ latent-guess, stage progression, Core4 explicit refusal, card-only 3 nhóm và hỗ trợ feedback roots. Đây là contract/test work của builder, không yêu cầu sản phẩm/trial đã chạy **trước khi plan được sửa**.
3. **Release decision:** chấm raw LIVE, public Core4/Esc5/new inputs, 20 holdout, đánh giá actor/question, người thật, nguồn/phiên bản; xuất các thất bại chưa giải quyết. Có thể giao implementation sau khi bốn plan blockers được khóa; mọi claim production/contest đều vẫn phải đợi runtime + external evidence.

**Không đề xuất quyết định business mới.** Nếu lead muốn thay Core4 thành một ca FACT thay vì giữ personal/noadvance rejection, đó là thay đổi cấu hình bài demo cần nêu rõ cho user, không lén đổi trong acceptance. Các mức score/threshold 1/.75/.5/.25 và fixed0.75 đã là lựa chọn kỹ thuật được công khai, tôi chỉ yêu cầu định nghĩa đủ để đo và tái lập.

**File được phép sửa:** chỉ báo cáo này. Không code, không tests/app/providers, không Git mutation; review không kiểm chứng runtime.

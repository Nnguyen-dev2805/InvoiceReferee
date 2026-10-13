# Independent architecture response — revised final plan (AR-01–AR-13)

**Ngày:** 13/10/2026  
**Vai trò:** independent plan reviewer, không implementer  
**Phạm vi:** Chỉ phản biện closure AR-01–AR-13 của [review gốc](architecture.md); trọng tâm T1–T8 và các giao diện tiền/quyền/workflow. Đây là **document-only Verify-tier**; không đọc code symbols/call chain, không có xác nhận CodeGraph coverage, không chạy app/test/provider, không kiểm thực thi hay chứng nhận kết quả benchmark.

**VERDICT DUY NHẤT — TARGETED CONTRACT CHANGES STILL REQUIRED BEFORE INDEPENDENT FINANCIAL-WORKFLOW IMPLEMENTATION.** Bản sửa **đóng được phần lớn P1** và đã chuyển các quyết định chính từ ngụ ý sang hợp đồng đủ rõ để coding agent thực hiện. Tuy nhiên, **AR-01 vẫn có một mâu thuẫn điều kiện giữ/supersede instruction** khiến hai implementer có thể chọn hai hành vi tài chính khác nhau; **AR-13 còn thiếu ownership rule được ghi trong plan** dù đã được lead hứa. Đó là **hai sửa Markdown rất nhỏ**, không cần đổi kiến trúc, thêm hệ thống reservation, chạy M0, hoàn thành code hoặc hỏi lại Q31. AR-03 và AR-08 có một số acceptance biên nên pin thêm khi sửa cùng đợt; chúng không tự thân là lý do mở policy lớn.

## Nguồn và cách đọc

- **C** = [`docs/final/IMPLEMENTATION_CONTRACTS.md`](../../IMPLEMENTATION_CONTRACTS.md), bản hiện tại, đặc biệt **L293–402 (§10)**, cộng §2, §4, §6 và §9.
- **P** = [`docs/superpowers/plans/2026-10-13-invoice-referee-final.md`](../../../superpowers/plans/2026-10-13-invoice-referee-final.md), bản hiện tại; đặc biệt **T2 L89–108, T3 L110–129, T6 L169–189, T7 L191–210, T8 L212–231**.
- **Q** = [`docs/final/ARCHITECTURE_AND_EVALUATION.md`](../../ARCHITECTURE_AND_EVALUATION.md), nhất là **L79–112 và Q31 L432–442**.
- **O** = [original AR-01–AR-13 report](architecture.md) **L29–157**. Báo cáo đó là lịch sử finding, không phải căn cứ mặc định rằng bản sửa vẫn sai. Không thay đổi báo cáo O.

**Chú thích phiên bản:** Trong quá trình kiểm cuối, SHA-256 của C và P đã đổi trong workspace từ lần đọc đầu (C `618c5ac2…` → `a51c9249…`; P `ad6e85e3…` → `0c075934…`); đây là chỉnh sửa đồng thời không do reviewer thực hiện. Tôi **đã đọc lại** C L293–323 và rà các điều kiện/ownership liên quan trong P sau khi thấy đổi hash: mâu thuẫn AR-01 và khoảng trống AR-13 nêu trong báo cáo **vẫn hiện diện** ở bản mới. Các đoạn nằm ngoài phạm vi AR-01–13 không được tái khảo sát; verdict gắn với những điều khoản được dẫn, không giả thiết có một checkout bất biến suốt lượt review.

Đánh giá theo nghĩa: **CLOSED** = đã chọn được một hành vi nhất quán trong tài liệu; **CLOSED, VERIFY IN BUILD** = contract đủ để giao, test/runtime vẫn phải xác thực; **PARTIAL / FIX IN PLAN** = giao agent độc lập còn phải tự chọn điều lẽ ra plan phải khóa. Khi C mục trước viết ngắn, C **L7–8** nói rõ §10 có ưu tiên; không coi shorthand cũ tự động tạo finding mới.

## Closure từng finding

| ID | Phán quyết closure | Căn cứ cụ thể và lý do |
| --- | --- | --- |
| **AR-01 · P1** | **PARTIAL — BLOCKING CONTRACT CONTRADICTION** | C **L301–306** cho phép *retain* nếu cùng chiều và `remaining=abs(S)`, nhưng với **S giữ nguyên, cost/authority basis đổi**, nhánh retain L304 và nhánh `basis đổi + OPEN/UNKNOWN → suspend` L306 đồng thời khớp; nhánh supersede L305 lại chỉ viết “S/chiều đổi”, bỏ sót changed-basis-only khi NOT_STARTED/CLOSED_CONFIRMED. Xem phản ví dụ A bên dưới. |
| **AR-02 · P1** | **CLOSED, VERIFY IN BUILD** | C **L297–323** đã pin *net* fulfillment, linked reversal, không tạo R giả, không tái kích hoạt predecessor SUPERSEDED; P **L204–207** pin partial/full/duplicate reversals và reopened state. Ngoại lệ reversal sau supersession cần integration acceptance B bên dưới. |
| **AR-03 · P1** | **CLOSED, VERIFY IN BUILD** | C **L327–339** pin key invoice có căn cứ, phân biệt digest/portion, owner một root trong tenant, ambiguity→FACT, và atomic usage+eligibility+instruction; P **L184–185** có two-roots/shared-DB test. Không đòi fraud-proof identity cho raw/gold pilot. Cần kiểm một lần tính incurred trong cùng owner, nêu ở C bên dưới. |
| **AR-04 · P1** | **CLOSED** | C **L341–346** tách `cost_basis`/`money_basis`, re-assess E tổng theo eligible employee-paid portions; P **L125–126** pin E8→E9 cần AUTHORITY, E8+P1 không đổi eligibility. Từ P1 ban đầu không còn phải tự suy thời điểm regrant. |
| **AR-05 · P1** | **CLOSED, VERIFY IN BUILD** | `SettlementConclusion` đã vào C **L36**, C **L353–361** định nghĩa BALANCED/OUTSTANDING/BLOCKED và state priority/predicate; P **L227–228** test zero verified đối lập unknown A, pending/material problems. Không thêm duyệt routine; persisted decision cần đúng read-set khi hiện thực. |
| **AR-06 · P1** | **CLOSED** | C **L353–366** mở `CaseView.problems`, scoped relevance/materiality, quarantine unrelated; P **L126–127, L227–228** yêu cầu view+gates. `ProcessingProblem` shorthand ở C **L37** phải được T1 triển khai theo §10 (field/view projection có `relevance`, `blocking`, `next_action`), không được bỏ các trường theo bản rút gọn. |
| **AR-07 · P1** | **CLOSED, VERIFY IN BUILD** | C **L368–373** chốt aggregate `context_version` cập nhật validated authority/import; commit đối chiếu read-set cùng grant hiện hành, giữ historical snapshot, phân biệt revocation với expiry; P **L225–228** đã thêm barrier B14→B8/revoke. Phạm vi invalidate đã đủ rõ ở mức plan. |
| **AR-08 · P1** | **CLOSED, VERIFY IN BUILD** | C **L385–393** pin durable `submit_requested`, phases, same worker/basis, late result, restart/counters; P **L183–185, L225** đặt delayed-preview/Stop/restart acceptance. Pha FAILED/Submit có thể hoàn tất bằng TECHNICAL_ERROR được lưu; không được âm thầm kết luận thành công hay reset quota. Gợi ý assertion D. |
| **AR-09 · P2** | **CLOSED** | C **L258–263** chứa tagged `Override` và `MarkExecution`; C **L375–381** pin grant/scope/basis/reason và cancel là suspend/supersede, preserve actual; P **L207, L228–229** có tests/UX. `Cancel` là UI intent, không được đọc như delete financial history. |
| **AR-10 · P2** | **CLOSED** | C **L375–378** chốt identity `(tenant,actor,command_id)`, canonical fingerprint có kind/root/payload/expected version, replay historical result, divergence 409, external transaction identity riêng; P **L227** test changes + tenant isolation. Replay check phải diễn ra trước stale expected-version rejection cho *cùng fingerprint* (hệ quả trực tiếp của contract). |
| **AR-11 · P2** | **CLOSED; ORIGINAL REVIEWER WITHDRAWS BUSINESS-QUESTION REQUEST** | Q **L81–94, L432–442** và C **L347–349** đủ rõ: incurred business cost vào **T** ngay cả khi không eligible E, personal ngoài T/E, unpaid tính từ **gross paid/outstanding có chứng cứ**, không dùng `T−E−C`. P **L115, L126** kiểm T10/paid7/E5/C3/unpaid0. Không còn lý do hỏi lại người dùng Q31 hoặc thay rule B; cách diễn đạt ở O L137 “nếu lead muốn...” chỉ là điều kiện giả định, nay không xảy ra. |
| **AR-12 · P2** | **CLOSED; ACCEPT LEAD'S PUSHBACK** | C **L395–401** phân biệt tạo `ProposedActivity` server ID với cấp quyền/B, yêu cầu quyết định/context có grant trước action; P **L94–104** bảo vệ root/draft/new-input. Người dùng **không cần** authorization chỉ để tạo bản nháp. `same activity→same root` nghĩa là dùng cùng server activity identity; không được suy “hai chuyến giống tên/ngày là một”. Test authorization khi hành động tài chính, không khi gõ draft. |
| **AR-13 · P2** | **PARTIAL — DOCUMENT HANDOFF GAP** | P **L37–62** có file map, T7/T8 **L191–214** đã ghi path; P **L64–70** đặt sequence và gate. Nhưng bản P hiện tại **không ghi rule “one workflow integrator”** được lead nêu; `workflow/service.py`, `jobs.py`, `schema.sql`, `domain/commands.py` lặp ở T2/T5/T6/T7/T8, T5 **L151** dùng “evidence group”, T6 **L171** dùng “API”. Nếu task được handoff độc lập, không có owner được ghi trong file để buộc serialize edit vào shared workflow DB modules. Xem E. |

## Counterexample thực sự còn phân nhánh

### A. AR-01 — cùng S, khác cost basis: chọn retain hay suspend/supersede?

**Nguồn:** C **L35–36, L98–113, L301–316, L341–346, L368–373**; P **L183–185, L206–207**.

1. Root đã kiểm hết A/P/R/coverage; E4 đủ quyền, S=PAY4 và instruction `I4` căn cứ expense X, `cost_basis=X`, `remaining4`, chưa có receipt.
2. Evidence mới chứng minh X là khoản nhập nhầm, đồng thời thêm expense Y hợp lệ có cùng eligible employee-paid4; sau re-assessment **S vẫn PAY4**, nhưng **cost_basis đổi** (refs/expense/possibly rule/grant khác).
3. Nếu `I4.execution_state=OPEN` (hoặc UNKNOWN), C **L304** cho phép giữ vì cùng chiều và `remaining=abs(S)`, trong khi C **L306** bắt suspend vì basis đổi. Hai hành vi đối nghịch.
4. Nếu `I4.execution_state=NOT_STARTED`, C **L304** vẫn khớp, nhưng C **L305** chỉ nêu “S/chiều đổi”, không nói “basis đổi cùng S”: agent A giữ I4 với authority_refs cũ; agent B supersede I4 và issue I4 mới có basis Y. Nhánh CLOSED_CONFIRMED cũng tương tự nếu còn remainder chưa thực hiện.

**Tác hại:** Giữ một payment instruction tham chiếu quyết định/căn cứ đã không còn hiệu lực; với OPEN có thể bỏ qua yêu cầu xác minh external execution. `context_version`/recheck current grant bảo vệ transaction mới nhưng **không tự chọn** chuyển trạng thái của instruction đang tồn tại.

**Sửa tối thiểu, không đổi chính sách:** Sửa row `retain` thành **signed direction + abs(S)=net remaining + material instruction basis unchanged + current authority/coverage valid**. Viết rõ row **basis đổi dù S bằng nhau**: nếu NOT_STARTED/CLOSED_CONFIRMED có proof thì supersede phần còn lại và issue duy nhất `abs(current S)` với basis mới; nếu OPEN/UNKNOWN thì suspend/EXECUTION_UNKNOWN, đòi proof trước replacement. `receipt P` thuần túy làm S và remaining cùng giảm không đổi `cost_basis` nên giữ instruction. Nêu thứ tự ưu tiên các rows, đặc biệt S=0 và incident/STOP/revoke, để một trạng thái chỉ có một nhánh.

**Acceptance:** Trong T6/T7, literal test cùng signed S4 khác cost_basis `X→Y`: NOT_STARTED ⇒ I4(X) SUPERSEDED + duy nhất I4(Y) actionable; OPEN/UNKNOWN ⇒ không issue thay thế; cùng basis + P2 nhận ⇒ I4 remaining2 được giữ. Test dùng một root/DB và refs, grant/current-epoch khác nhau nếu cần; không so mỗi amount.

### B. AR-02 — reversal trên predecessor đã SUPERSEDED

**Nguồn:** C **L310–323**; P **L185, L206–207**. Đây là **implementation acceptance cần bổ sung**, không còn contract blocker: I4(X) đã fulfilled P2, CLOSED_CONFIRMED, eligible supplement làm S4 và I4(X) bị SUPERSEDED, I4(Y) mới amount4 NOT_STARTED. Sau đó reversal xác minh đúng giao dịch **P2 của X**, nên `P` net giảm2, S hiện tại tăng thành6. Không được tự biến I4(X) thành actionable; I4(Y) phải reconcile lại theo bảng (nếu NOT_STARTED thì supersede và issue current S6; nếu đã OPEN/UNKNOWN thì suspend và yêu cầu kiểm execution), audit giữ predecessor và linked reversal. Một regression integration ở T7 hoặc T8 sẽ kiểm kết hợp hai rule vốn test riêng có thể bỏ sót. Không cần một reverse-money engine hay business decision mới.

### C. AR-03 — owner-root không tự chứng minh single-count **trong cùng root**

**Nguồn:** C **L327–339**; P **L184–185, L204–206**. Ví dụ cùng verified invoice `(tenant,issuer,number,date)` được upload 2 lần cùng activity dưới scan và PDF; parser tạo expense IDs `e1/e2` dù chỉ có **một** incurred obligation T3 và **một** employee-paid portion P3. Registry owner chỉ ra *cùng root*; nếu implement cộng cả `e1+e2`, T/E thành6 là false duplicate. Contract đã định ý định dùng economic key/verified portion identity và “thêm một lần”, đủ định hướng sửa mà không mở policy.

**Pin test/implementation acceptance:** cùng verified economic obligation + cùng confirmed payment-portion key trong một root ⇒ T3/E3 đúng một lần; new **distinct verified** portion hợp lệ của cùng obligation ⇒ E tăng đúng phần mới, T không nhân đôi; hai roots đồng thời ⇒ một owner; invoice giống số nhưng issuer identity chưa verified ⇒ FACT. Registry unique/transaction binding phải thực sự enforce cả `expense` lẫn `payment_portion` identity; `expense_id` do đọc hai file tạo ra không thể là bằng chứng portion mới. Nếu hai hoạt động **thực sự** dùng các phần riêng của một invoice, pilot không hỗ trợ multi-claim allocation: giữ FACT/UNSUPPORTED và không tự double issue; muốn hỗ trợ tự động chia invoice giữa roots mới là mở rộng product/business scope.

### D. AR-08 — Submit quanh failure của preview

**Nguồn:** C **L385–393**; P **L163, L183–185, L225–228**. Nếu Submit đến khi preview READING rồi reader FAIL/TIMEOUT, không được mất `submit_requested`, tuy nhiên cũng không có đủ reads để kết luận BALANCED/issue. Worker lưu FAILED/TECHNICAL problem/counters và view giải thích cách thử lại trong quota/basis hiện hành; restart không nhân đôi accepted submit hoặc reset recovery. Đây là phần kiểm thử lifecycle có thể giao T6/T8; không cần thêm phase architecture mới. Các phases C nêu là work phases, còn FAILED có thể là terminal **job status** C L153–154, tránh tự tạo enum mâu thuẫn.

### E. AR-13 — handoff thực thi cần owner được pin, không thêm người duyệt tiền

**Nguồn:** P **L46–62, L64–70, L89–93, L149–153, L169–173, L191–215**. Với hai coding agents được giao T6 và T7 trên các nhánh riêng cùng chạm `workflow/service.py`/`schema.sql`, “file map + sequence” giúp định vị file nhưng **chưa định nghĩa ai resolve schema/transaction khi merge**. Lead đã chọn **một integrator**, chỉ cần chuyển quyết định đó vào một đoạn `Global Constraints`/`File Map`/`Execution handoff` của chính P:

> *Workflow integrator duy nhất sở hữu và tuần tự hợp nhất `workflow/db.py`, `schema.sql`, `service.py`, `jobs.py`, `snapshots.py`, `money.py`, `controls.py` và command/schema boundary. Các agents T2/T5/T6/T7/T8 gửi change set/contract proposal theo thứ tự gate; không chỉnh đồng thời shared DB modules trên các nhánh merge độc lập. Nếu T1/T7/T8 cùng sửa `domain/commands.py` hoặc `case.py`, integrator phối hợp type change rồi mới cho consumer code merge. T5/T6 nêu chính xác target API/jobs paths ở checkpoint.*

**Acceptance:** README/dispatch packet cho từng agent ghi owner thực tế + exact touched paths; cross-task integration replay T6→T7→T8 trong **cùng DB**, bảo đảm service/schema/DTO cùng contract. Đây là kiểm soát phối hợp thực thi, **không** phải đòi chia microservice hoặc trì hoãn triển khai chờ mọi benchmark.

## Trả lời trực tiếp các counterarguments của lead

**Chấp nhận AR-01/02 intent, phản đối duy nhất tính đầy đủ của bảng.** Quy tắc “một instruction actionable; new instruction full current S sau supersede; historical fulfilled vẫn nằm trong P/R” tính đúng ví dụ `E6/A2/I4 → P2 → E+2`, nên **không** yêu cầu phát `delta I2` song song. Một byte hợp đồng thiếu là `basis equality` ở row retain; nó phải được khóa trước để T6/T7 không chọn khác nhau. Reversal net đúng ý định, không đòi bank auto-recovery.

**Chấp nhận narrow scope AR-03.** Đòi chứng minh economic identity enterprise hoặc ngân sách reservation liên hoạt động sẽ vượt pilot Q/plan. Yêu cầu atomic single-count trong scope đã cam kết là **logic hiện có**, không mở loại giao dịch mới. Chỉ có test invoice/portion reuse của cùng root còn nên pin.

**Chấp nhận AR-04 đến AR-10 theo các source hiện tại.** Cấu trúc DTO, predicate, view problems, aggregate context version, `submit_requested`, tagged commands và fingerprint đều đã có owner/consumer/tests đủ cho plan. Việc race, SQLite locking, provider/IO, UI và restart sẽ chạy đúng hay không vẫn phải do implementer đo; không dùng chưa chạy test để bác contract.

**Rút lại yêu cầu hỏi lại AR-11.** Q31 đã quyết định business incurred trong T kể cả excluded E; không âm thầm bỏ khoản chi có căn cứ khỏi T/B. Unpaid từ gross paid/outstanding. Nếu tương lai muốn policy “prohibited business expense không bao giờ tính B”, đó là **đề xuất thay đổi Q31**, không phải câu hỏi đang mở của plan hiện tại.

**Chấp nhận lead phản biện AR-12.** ProposedActivity ID do server tạo chỉ là định danh draft; không grant activity hoặc B; đến khi có context/Decide authorized mới hành động tiền. Cần phân biệt **tạo bản nháp** và **phê duyệt hoạt động**, không ép login/quyền ở bước gõ đề xuất. Acceptance về hai activities/two roots và forged client đã có trong T2.

**AR-13: nhất trí phương án lead nhưng chưa thấy nó trong tài liệu.** Chỉ cần ghi đúng quyết định “one integrator” vào P, không cần đổi thứ tự T1–T13 hay tạo thêm hệ thống quản lý agents. Chất lượng design không được suy từ việc một người nói “đã có owner”.

## Ranh giới quyền, bằng chứng và điều kiện để nâng verdict

**Không phát sinh business-choice bắt buộc người dùng chốt trong AR-01–13** nếu giữ đúng Q31, cap 8/4/20, quyền grant hiện có, single-owner economic usage, một actionable instruction, không vendor payable và không hỗ trợ automatic multi-root invoice allocation. Changed-basis same-S và integrator ownership là lựa chọn **implementation contract/delivery** đã có hướng lead xác nhận. Nếu sau này yêu cầu *tự* chia một hóa đơn cho nhiều activities, tự phát collection để xử lý overpay, hoặc cho draft tự cấp B thì đó mới là policy/product change, phải hỏi người dùng riêng.

**Điều kiện tối thiểu để đổi verdict thành READY FOR INDEPENDENT TASK IMPLEMENTATION:** (1) sửa một hàng retain + một hàng changed-basis-only của §10.1, pin test cùng S khác basis; (2) ghi một owner/serialization rule vào P cho shared workflow/schema/command DTO, pin cụ thể T5/T6 API paths tại checkpoint. Cùng sửa nên thêm regression reversal-of-superseded, same-root semantic duplicate và submit-preview-failed; ba bổ sung này **không phải blockers độc lập** để chờ code/test trước khi duyệt văn bản. Không cần mở thêm 13 findings mới hay redesign kiến trúc.

**Bằng chứng được và chưa được khẳng định:** Bản plan thiết kế single-process FastAPI/SQLite, pure Reconciler và DB transaction có cơ sở triển khai dưới scope demo (P L5–24; C L149–189). Chưa có bằng chứng runtime về OCR/provider correctness, SQL races, crash/recovery, identity matching, tài chính thực, public host, practitioner outcomes hoặc release metrics trong vòng review này. Đặc biệt, **formal economic-identity proof**, xác thực chứng từ chống giả mạo ở cấp doanh nghiệp và **enterprise IAM/organization authorization integration** **nằm ngoài** claim raw/synthetic-gold pilot; simulated grants/context/actor không chứng minh quyền pháp lý thực hoặc xác thực hóa đơn ngoài đời. Builder phải gắn nhãn đúng nguồn và giới hạn, không được nâng thử nghiệm tài liệu thành chứng nhận production. Không có CodeGraph index/coverage xác minh cho review; không tuyên bố khảo sát repository đầy đủ.

**File do reviewer tạo trong lượt này:** `docs/final/reviews/2026-10-13-plan/architecture-response.md`. Reviewer không chỉnh `architecture.md`, P, C, code hoặc Git; hash `architecture.md` trước/sau đều `8a98ac3e…`. C/P đã có thay đổi song song như ghi chú phiên bản ở trên; báo cáo này chỉ phản biện tài liệu trong phạm vi finding đã nêu.

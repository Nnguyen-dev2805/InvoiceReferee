# Phản biện và disposition của lead — implementation plan

Ngày 13/10/2026. **Verdict của lead: đủ để giao triển khai theo task/gate; chưa có proof runtime.**
Nguồn: [architecture](architecture.md) (13 findings), [evaluation](evaluation.md)
(10 findings), snapshot tại [README](README.md). Toàn văn review gốc được giữ.
Đây là review tài liệu; không có code/app/unit/UI/LIVE/trials đã chạy trong lượt này.

## 1. Ý kiến riêng của lead

Tôi không giao plan ban đầu cho agents như một contract đã đủ chặt. Hai reviewer
đã nêu những thiếu sót thực chất; chúng không chứng minh app có bug vì app chưa
được xây, nhưng cho thấy hai implementer có thể chọn hai kết quả tiền khác nhau.
Điểm cần sửa là semantics giao nhau, không phải đổi framework hoặc mở phạm vi.

Ví dụ I4 đã trả2, thêm eligible cost2: nếu lấy S mới4 rồi issue I4 song song với
remainder2 cũ sẽ đòi6; nếu chặn mọi khoản bổ sung thì bỏ sót2 hợp lệ. Tôi chọn
supersede remainder chưa thực hiện khi đợt thực hiện đã xác minh xong và tạo một
instruction cho S4 hiện tại. OPEN/UNKNOWN không được replacement. Actual2 và
instruction cũ vẫn truy vết; đây là representation của một nghĩa vụ, không thêm
quy trình phê duyệt nhiều phần hoặc budget reservation framework.

Reversal phải làm giảm net fulfillment và mở lại nghĩa vụ có căn cứ. Chỉ nói
“không tính R” chưa đủ: I4/P2/reverse2 mà còn remaining2 vẫn sai. Tôi nhận AR02
và bổ sung cả projection/state/instruction tests, không xóa gross history.

Về đánh giá, tôi nhận EV-P01/P04: false S0 là thất bại nguy hiểm dù không tạo
lệnh; một routing flip và gain tổng không chứng minh threshold có ích. Bản sửa
đòi gain supported ở chính changed opportunity, cùng initial sources/counters/
remaining budget. Tối ưu calls đơn thuần không được dùng thay gain đã yêu cầu.

Tôi phản biện hai diễn giải có thể làm scope phình:

- Không đòi người duyệt cấp quyền chỉ để nhân viên tạo một bản nháp ProposedActivity.
  Server cấp identity ổn định, không cấp B/activity authorization; action tài chính
  vẫn cần tổ chức cho phép đúng scope. Identity khác authorization.
- Q31 đã chốt incurred business cost thuộc T, kể cả không eligible E. Không cần
  hỏi lại để loại E mà giữ T. Chỉ nếu muốn đổi B không tính phần đó mới là business
  choice mới; tôi không đề xuất thay đổi ấy. unpaid từ gross payments/outstanding,
  không suy T−E−C vì E đã qua policy.

Agent không phải người tự cấp quyền hoặc tự tin hóa tiền: LLM đọc/đối chiếu/đề
xuất bước readonly; backend giữ admissibility, equation, grant và atomic commit.
Phải chứng minh các bước agent qua LIVE trace và lỗi/recovery thật; một API gọi
LLM hay dashboard LangSmith xanh chưa chứng minh orchestration hoặc chất lượng.

## 2. Disposition toàn bộ findings

“Đã sửa contract” là sửa tài liệu/acceptance, không nghĩa runtime PASS. Contract
[§10](../../IMPLEMENTATION_CONTRACTS.md#10-các-hợp-đồng-giao-nhau-đã-khóa-sau-review-plan)
và các tests trong [plan](../../../superpowers/plans/2026-10-13-invoice-referee-final.md)
chịu trách nhiệm cụ thể. Không biến 23 findings thành 23 services/tasks mới.

| Finding | Disposition và lựa chọn của lead | Owning task |
| --- | --- | --- |
| AR01 | Nhận; retain khi S/remainder khớp, replacement một instruction nếu execution đã xác minh; unknown block | T6/T7/T8 |
| AR02 | Nhận; linked reversal điều chỉnh net projection/fulfillment/state; không R giả | T7/T8 |
| AR03 | Nhận có thu gọn; tenant usage owner/portion registry, verified key; ambiguity FACT | T3/T6/T8 |
| AR04 | Nhận; cost_basis gồm eligible paid portions/relations/policy/B; E total grant recheck | T3/T7 |
| AR05 | Nhận; persisted SettlementConclusion/state predicate, balanced khác no instruction | T6/T8 |
| AR06 | Nhận; view có typed problems/relevance/blocking/next action; không blanket block unrelated | T3/T5/T6 |
| AR07 | Nhận; aggregate context_version cho policy/grant/B/authorization/exception/revoke | T2/T6/T8 |
| AR08 | Nhận; submit_requested + durable work phases/counters, no lost submit/double read | T5/T6/T8 |
| AR09 | Nhận; tagged Override/MarkExecution; cancel chỉ suspend/supersede, không erase actual | T1/T7/T8 |
| AR10 | Nhận; tenant/actor command fingerprint, same result hoặc deterministic409, separate event identity | T2/T7/T8 |
| AR11 | Nhận unpaid gross; giữ Q31 T dù cost không eligible E, không mở Q mới hoặc vendor workflow | T3/T7 |
| AR12 | Nhận stable server identity; phản biện phải authorization ngay lúc draft; authorization/B trước financial action | T2/T6/T10 |
| AR13 | Nhận explicit ownership/gates; một workflow integrator cho shared DB; không hứa kịp deadline bằng docs | Mọi task/T10/T13 |
| EV-P01 | Nhận; critical union gate action OR unsupported affirmative, dossier de-dup | T9/T12 |
| EV-P02 | Nhận; frozen eligible steps/max score/tie rule/>= comparator, guards không học | T5/T11 |
| EV-P03 | Nhận; paired snapshot có quotas/counters/deadline/recovery usage, no fresh budget | T6/T11 |
| EV-P04 | Nhận; beneficial changed opportunity bắt buộc, unchanged noise/cost-only không gain | T11 |
| EV-P05 | Nhận; Core4 personal có expense exclusion/rule/refs thật, không dùng S0 như REJECT | T6/T9 |
| EV-P06 | Nhận; card-only cả ba nhóm, một valid response cho issue, không blanket approval | T6/T9/T12 |
| EV-P07 | Nhận; latent exact guess vẫn fail nếu observable không đủ; raw visual gold | T4/T9 |
| EV-P08 | Nhận; group/family guard trước model/threshold selection và kiểm freeze cuối | T4/T12 |
| EV-P09 | Nhận; enabled/blocked stage sets FACT→AUTHORITY, initial khác assisted | T6/T9 |
| EV-P10 | Nhận; Cal10/Val10 author/freeze/map verified labels; clicks≠roots, lack support giữ fixed | T10/T11 |

## 3. Ranh giới verdict

Plan có thể được giao thực hiện khi contract sửa được kiểm lại và người dùng chọn
cách triển khai. M0, model versions, actual raw/gold, public URL/latency, holdout,
người làm nghiệp vụ thật và phản hồi vẫn là công việc chưa thực hiện. Không dùng
AI reviewer thay người thực tế, hoặc simulation thay verified human feedback.

Không có thay đổi ngưỡng8/4/20, công thức S, Q31, travel-first, framework hay quyền
được đề xuất trong bản sửa. Nếu reviewer phản hồi chứng minh cần thay business
choice đã chốt, sẽ hỏi người dùng với counterexample, không tự đổi.

## 4. Vòng phản hồi và hai sửa cuối của lead

[Nietzsche](evaluation-response.md) kết luận READY FOR IMPLEMENTATION DISPATCH:
đóng EV-P01–P04 ở cấp contract và gán EV-P05–P10 thành builder gates. Ba probes
cuối về units/gain, UNOBSERVED replay và grouping axes đã thêm contracts §11/T4/T11.

[Galileo](architecture-response.md) đóng phần lớn findings nhưng còn hai yêu cầu
tài liệu: AR01 cùng số tiền khác basis chưa phân nhánh đủ; AR13 integrator ownership
đã hứa nhưng chưa có trong plan. Tôi xác nhận cả hai, sửa §10.1 và Global Constraints/
T5/T6 exact paths, thêm same-S/changed-basis và shared-root duplicate tests.
Đây là closure do lead kiểm trực tiếp, không gán lời “đã duyệt cuối” cho Galileo
nếu reviewer chưa xác nhận snapshot sửa cuối. Review nguyên bản/response giữ lịch sử.

Tôi còn pin ba acceptance Galileo nêu: reversal trên superseded predecessor,
single count trong cùng root và Submit quanh preview failure. Với reversal làm
S từ4 thành6, không chép ví dụ “issue6” mà bỏ grant4: phải AUTHORITY trước, chỉ
issue6 sau decision đúng quyền và execution đã xác minh. OPEN/UNKNOWN vẫn block.

Không phát sinh business choice cần hỏi lại người dùng. Method triển khai và
việc review plan thuộc handoff; evidence về người/hạ tầng/model thật sẽ kiểm ở
task phù hợp. Triển khai chỉ được tuyên bố đạt khi tests/raw/UI/LIVE và release
gates thực sự có kết quả, không dùng các verdict tài liệu làm chứng nhận tài chính.

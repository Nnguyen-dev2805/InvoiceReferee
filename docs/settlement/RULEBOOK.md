# InvoiceReferee — Rulebook hiện hành

Ngày 09/10/2026. **Thiết kế demo đã được đồng ý; không là luật/thuế hoặc policy công ty thật, chưa tự kích hoạt runtime.** Đi cùng [Product](PRODUCT.md), [System](SYSTEM.md), [Evaluation](EVALUATION.md). Những category caps, quyền hai cấp 10/30 triệu và auto 2/5 triệu của các bản cũ không được kế thừa. Originals/reviews giữ trong [archive](../archive/README.md).

## R1. Applicability và lớp dữ liệu

B3 trước công việc: người/work/scope, dự toán/phần company–employee/số xin, căn cứ công việc và nội dung đang xin, lịch sử ứng/approval/attempt/pending/quyền liên quan. Không đòi invoice sau công việc hoặc receipt khoản đang xin.

B7 sau công việc/hủy: khoản/phần, giá trị/mục đích/payer/consistency/duplicate/policy, company direct và actual advances/returns/reimbursements cùng scope. Tự chi không cần loan ID/ứng giả; hủy không tự E0 hoặc phải thu toàn bộ ứng. Inventory/PO/nhận hàng ngoài MVP công tác; NOT_APPLICABLE có lý do không cho toàn case PASS.

Giữ riêng lời khai/đề nghị, originals/provenance, observations/normalized proposals, facts đủ căn cứ cho check, human confirmations và financial decisions. Chất lượng fact, raw payment status/receipt và technical execution độc lập. Internal IDs không thay ref/name/identity ngoài nguồn.

Một tài liệu có thể chứa nhiều khoản và một khoản có nhiều source. Chỉ cần fields ảnh hưởng check; không ép tax ID/VAT/quantity/unit price/attendees trên mọi bill. Nếu rule cần details để loại một phần, total rõ không miễn details mờ.

## R2. Khi nào được dùng fact?

Phải có source đã lưu và locator thật có thể mở; value/currency/unit/ý nghĩa rõ; origin/source-role phù hợp check; đúng người/khoản/phần/mốc và không material contradiction. Raw giữ nguyên, normalize chỉ khi không mơ hồ. Source rõ về một field không chứng minh field khác rõ hoặc tiền đã nhận.

READ/NOT_FOUND/UNCLEAR theo [System](SYSTEM.md#s2-hợp-đồng-đọc-liên-kết-và-kết-quả); source không đọc được thì null/issue. Provider thành công, confidence cao, financial approval và Paid label không thay evidence/quality/math gates. Alternative source phù hợp có thể dùng với ref/derivation thật, không giả là đọc được field trên original.

Reading confirmation chỉ khi người xác nhận thực sự đọc được retained source, gắn target/value/locator/scope. Không gõ số đoán rồi confirmed khi original mờ; cần nguồn khác. Factual confirmation chỉ dùng cho check policy cho phép và owner có căn cứ đúng scope. Financial decision không thay hai loại confirmation này.

## R3. Khoản chi, mục đích và payer

| Nhóm | Căn cứ cần theo check |
| --- | --- |
| Vé/di chuyển | Dịch vụ/chuyến/value/ref phù hợp, quan hệ người/work và ngày cần xét; taxi không bị buộc có ref kiểu airline |
| Khách sạn | Phòng/dịch vụ/value và thời gian cần xét; parts/payer có nguồn; deposit/balance là tiền, không expense thêm vào invoice |
| Ăn/tiếp khách | Receipt/nội dung và purpose/context; detail/attendees chỉ khi rule cần; không tự nhận cả bàn ăn là business hoặc loại theo tên món |

PERSONAL checkbox, company name trên invoice hoặc employee liên quan không chứng minh actual payer/payee. Có nguồn company paid và employee claim PERSONAL phải đối chiếu same obligation/portion và contradiction; không tự fraud hoặc finance thắng vì chức danh. Nếu cả hai thực trả cùng nghĩa vụ, giữ double payment incident.

Phần chắc chắn cá nhân không thuộc work được loại khỏi T/E theo rule và source, giữ actual bill/paid amounts. Purpose chưa rõ hỏi trước. Within budget không miễn eligibility; muốn chấp nhận phần ngoài scope cần decision riêng trong quyền, không AI tự mở policy.

Lời khai mục đích là một nguồn được policy demo chấp nhận trong phạm vi tương ứng; nếu mâu thuẫn với công việc hoặc nguồn khác thì cần làm rõ. Xác nhận mục đích không chứng minh ai đã thanh toán. Không mặc định yêu cầu giấy tờ thuế hoặc cùng một loại sao kê cho mọi phương thức.

## R4. Evidence thanh toán theo phương thức

| Bộ căn cứ | Đủ khi | Không được suy |
| --- | --- | --- |
| Payment source có actual receipt semantics | Đúng amount/currency/payer/payee/portion/ref/time và outcome theo source contract | Approval/request/debit/Submitted hoặc Paid generic không actual receipt |
| Cash named receipt/handover | Có bên giao/nhận, role/amount/part/time/ref, xác nhận tiền thực giao/nhận phù hợp | Order/đề nghị hoặc phiếu chi chưa thực hiện không đủ |
| Anonymous cash receipt đã trả + bounded attestation | Receipt amount/cash paid rõ; employee statement nêu amount/part/vendor/time/ref; work rõ; company sources đủ scope cho company direct/duplicate và không contradiction; policy activated cho loại này | PERSONAL đơn lẻ, receipt chỉ ghi phương thức dự kiến, thiếu company coverage hoặc số mờ không đủ |

Anonymous cash+attestation chỉ dùng cho phần employee trả vendor. Report ghi policy-attested, không independently bank verified. Không dùng lời nhân viên đơn độc thay actual A/P employee nhận hoặc RA/RP company nhận. Statement đủ có sẵn không hỏi lại làm ritual; bổ sung sau run ghi assisted/human touch. Named cash/event source dùng đúng profile.

Cùng uploader khác nhau không tự đổi factual authority nếu issuer/provenance/content đủ tương đương. Uploader, issuer và owner giải thích fact/coverage là ba vai khác nhau; một người có thể kiêm nếu đủ scope/căn cứ. File export do kế toán đưa vào không tự authenticated bank source.

## R5. Coverage, absence và cùng sự kiện

Coverage phải có origin/issuer, người/work, event groups/methods/side, from–to/money_as_of, filters/missing ranges/update và owner có khả năng quan sát. Một account/register không chứng minh absence ở cash/card/accounts khác. Employee không xác nhận thay company-side payment/history. Source tới 06 mà mốc cần 08 thì 07–08 còn thiếu nếu ảnh hưởng.

Không thấy trong một file hoặc không có đề nghị ứng không thành A/P = 0. Zero chỉ khi sources đủ đúng scope hoặc absence confirmation đúng owner/observability theo policy. Có A = 2 và RA = 2 thì giữ gross 2/2, khác never advanced; không tạo money event 0 để làm placeholder.

Ref của event có namespace. Bank ref và số phiếu có thể cùng event khi đủ liên kết; cùng amount/date/payee không đủ. Giữ mỗi observation/source và contradiction, không dict overwrite/drop duplicate IDs. Một event/phần tính một lần, không đóng góp toàn bộ đồng thời RA/RP; parts cần nguồn và không vượt gross. Source copy không tự thêm expense; event khác trả cùng invoice không tự bị xóa như duplicate.

## R6. Ngân sách và điều kiện ứng

Đơn vị là một employee/work, nhiều hồ sơ/lần bổ sung dùng cùng B và cumulative history. Work khác có B riêng; một khoản/phần không tính hai work. Không phân bổ tổng quát khi quan hệ chưa rõ.

B là tổng người có quyền cho phép dùng cho work, gồm company direct+employee. B không là forecast/request/actual advance/Approved checkbox hoặc budget mặc định. Decision B cần scope/person/amount/conditions/actor/rights/effective time/version/refs. Work permission không tự financial budget; advance approval 2 không tự budget 8.

Phần dự kiến company/employee giữ riêng để kiểm nhu cầu; không proof actual payer hoặc trần riêng nếu decision không quy định. Có thể work/B/ứng trong cùng decision đủ quyền hoặc reuse ngoài app. Sửa B là decision version mới, không overwrite/backdate.

T là tổng work cost trong cùng budgets scope, company direct+employee, khác tổng mọi số trên files. Không cộng invoice+deposit+receipt như expenses độc lập; giữ actual total/work/personal/accepted khác nhau. A/P là cấp/hoàn tiền, không expense mới trong T.

| Budget check | Xử lý |
| --- | --- |
| B/T/scope đủ và T≤B | Trong budget kể cả equality; còn eligibility/payer/history/rights checks |
| T>B rõ | Nêu B/T/phần vượt/refs, xin exception decision đúng quyền; không min(T,B), tự reject all hoặc tự nâng B |
| B chưa hợp lệ/T còn missing/conflict | Giữ facts/checks độc lập; xin fact hoặc decision đúng loại, không giả within budget |

Exception có thể chấp nhận toàn/phần hoặc yêu cầu sửa với amounts/parts/reasons/rights rõ. Giữ actual T/B và source; re-check E/S, không clip history để vừa B. Không có caps theo loại/ngày/đêm/sự kiện, advance 5 triệu cố định hoặc default airfare economy; điều kiện dịch vụ chỉ theo approval thực có scope.

Số xin ứng >0, so với forecast phần employee trong scope/B cần xét, không toàn B gồm company-paid. Vượt employee estimate/thay scope đưa người có quyền, không tự giảm. Initial proposal được check trước chính các approvals đang xin; thiếu approval đang xin không là thiếu upload. Forecast/request/approved/received riêng. Approver có thể duyệt ứng thấp hơn số xin có lý do/scope; phần chưa duyệt không tự request new.

Sửa cùng đề nghị chưa chi không tự supplementary advance. Refusal còn hiệu lực không vượt qua bằng resubmit. Previous valid approval/pending cần xét để không tạo thực hiện trùng. Đã received rồi xin thêm giữ actual/pending/need remaining và chuyển người có quyền, ngoài routine MVP; không auto cấm hoặc gán duplicate.

Tự chi chưa B vẫn intake/check source/purpose/money/history. Xin post-incurred acceptance đúng quyền/scope, không lấy claim làm B, tạo ứng 0 hay giả preapproval. Có thể combined acceptance+finalapproval, re-check sau decision; case vẫn assisted/needs policy ban đầu, không first-pass routine sau human response.

## R7. Formula và nghĩa tiền

`S = E - (A - RA) - (P - RP)`

| Thành phần | Ý nghĩa |
| --- | --- |
| E | Employee-paid work cost được chấp nhận, gồm sử dụng advance và phần tự bù, xét supported refund đúng phần |
| A / RA | Employee thực nhận advance / company thực nhận return của advance |
| P / RP | Employee thực nhận reimbursement / company thực nhận return của reimbursement |
| S | Dương company trả thêm; âm đề xuất employee hoàn;0 component cân bằng, chưa whole case closed |

Tất cả cùng cumulative work/settlement scope và as_of. Không bill mới trừ toàn history, trừ advance trong E rồi trừ lại A, hoặc trừ company direct lần nữa vì đã không thuộc E. Giữ gross/history; không net rồi cộng return lần hai. Unknown/missing/pending/coverage thiếu không 0. Integer VND/explicit bounded Decimal, không floats/guessed conversion/rounding/tolerance ngầm; currency/unit/rounding chưa đủ thì issue.

Supported vendor refund: đúng employee-borne portion đã xét, employee actual recipient và cách xử lý theo policy rõ; giữ chi/refund gốc, không giảm quá phần tương ứng. Employee trả hotel 3 rồi đúng phần employee nhận refund 1, phần còn lại đủ eligibility: E phần đó 2.

Refund về company hoặc quyền hưởng/phân bổ khác/chưa rõ là ngoại lệ ngoài automatic formula. Không giảm E2, tăng expense 3, nhét vào RA/P hoặc net tùy ý để bỏ nghĩa vụ refund. Company-paid personal recovery/double payment/overpayment/complex allocation giữ incident và chuyển xử lý có nguồn/quyền. Bất kỳ unresolved money obligation trong cùng settlement chặn final action/closure dù ngoài formula; không footnote để vẫn chi 3 hoặc tự net 2. Bounded ngoài scope chỉ không chặn khi quan hệ/policy đủ rõ; boundary chưa rõ giữ issue.

## R8. Quyền, quyết định và hiệu lực

Ba vai theo Product. Accountant không default financial approval. Authority nguồn cần actor/person/work/content/limits/effective time/conditions rõ; thiếu money limit không tự unlimited. Không default 5/10/30 triệu, không thêm second approver role để tự giải quyền.

Xét quyền work permission, budget B, advance amount, accepted costs/settlement và exception riêng. Quyết toán cần xét E trước offset và nghĩa vụ chi/thu đang quyết, không chỉ net S 0. Giảm số tùy ý để lọt quyền khác fact correction/loại theo rule có căn cứ. Có người đủ quyền đã biết thì route, không hỏi vòng thừa; chưa có thì xin source grant/decision đúng scope. Quyền mới không backdate để hợp thức hóa action cũ.

Decision giữ report/basis/scope/actor/rights/version/time/amount/direction/reason/conditions và relation thay thế. Combined work/B/advance hoặc exception/acceptance+settlement được khi đủ. External decision reuse khi còn valid, không bấm duyệt lại chỉ vì import. Two conflicting decisions không auto latest, trong app thắng hoặc cộng quyền.

Fact condition có source/rule kiểm được khác authority condition cần decision thật. "Có biên nhận" không tự bằng "đã được trưởng bộ phận cho phép". Unclear condition/missing critical facts không executable approval; đúng decision condition đáp ứng không ritual approve again.

## R9. Financial decision, fulfillment và handoff

Approval S+3 chờ company chi; S−0,7 chờ employee hoàn/company receipt; S0 đủ scope cần balance/closing basis, không money 0. Record review của kế toán không approval. Approver có thể trả lại/refuse/dừng/yêu cầu sửa; không chỉnh field S đơn lẻ hoặc raw facts.

MVP không phê duyệt một phần của kết quả settlement còn nghĩa vụ chưa xử lý. "B7 cần 3, duyệt 2" phải làm rõ đổi eligibility/scope hay chỉ partial execution; không final 2/xóa 1. "Duyệt toàn 3, chi 2 trước" giữ approved 3/chỉ dẫn/phần còn 1; không auto installment scheduler. Correct partial fulfillment không tự hủy original approval cho remaining nếu quyền/điều kiện/history còn valid, không pending/incident.

Trước handoff/action, kiểm current decision/revision/Stop/rights/conditions/scope/remaining/pending/receipts. Handoff A chỉ refs/report/decision+audit, không entityB. Source control sau handoff khiến gói cần recheck; người thực hiện phải xem current trước việc ngoài app. App không đảm bảo chặn ai dùng giấy cũ chuyển ngân hàng.

Pending known giữ chờ; tại checkpoint đối chiếu/hành động công bố chưa outcome cần thiết thì hỏi owner đúng attempt/part. Unknown khác pending/failed/0. Failed/cancel trước actual receipt có nguồn đủ khác received rồi return; không auto-bank retry. Một lỗi UI không proof chưa trả.

Overpay 4 cho decision 3: ghi 4, nghĩa vụ gốc 3 fulfilled và phần vượt 1 incident, không clip/giao 3 lần nữa hoặc tự quyết định phải thu 1. Wrong recipient giữ raw/source, không correct employee received hoặc auto chi bù. Return/reversal sau fulfillment không tự khôi phục quyền chi cũ. Nguồn đến muộn giữ event time khác knowledge/decision time, re-check đúng phần/mốc.

## R10. Refusal, Stop và closure

Refusal lưu reason, không chi mới theo rejected request; không xóa A/P hoặc tự E = 0/thu all advance/hủy work. Không money/duties có căn cứ thì end rejected request, khác settlement closed. Có duties tiếp xử lý; unknown hỏi owner, không suy đã ứng hoặc zero.

Stop local chặn managed new handoff/action/current output/closure, không bank/provider cancel. Vẫn giữ source/actual money đã xảy ra; resume rõ và recheck, không tự hồi phục validity/tiếp chi.

Closure cần decision đúng scope/quyền/conditions cùng material changes đã xét, payments/collections đủ actual receipt hoặc balance hợp lệ, scope/history đủ và không pending/incident/ngoại lệ/nguồn required/Stop/stale. Lưu as_of/version/history. Nguồn material sau close tạo linked adjustment, giữ close cũ. Exact copy/rerun không new entitlement/action.

## R11. Câu hỏi và examples để verify

Câu hỏi giữ issue/owner/refs, khoản/phần/đã biết/vướng/cần source hoặc decision và phần bị chặn. Sai owner/typed guess/thiếu scope không resolve; answer received rồi validate source/rights/recheck mới resolved. Không bắt source mẫu cụ thể khi alternative đủ; không hỏi lại fact đã đủ.

| Đủ sources/scope/policy và không incident khác | Kết quả |
| --- | --- |
| B = 8; company direct = 3; employee = 5; A = 2; RA = P = RP = 0 | T = 8; E = 5; S = +3; chưa phê duyệt hoặc ghi nhận thực nhận |
| E = 3,3; A = 4; RA = P = RP = 0 | S = −0,7 |
| E = 5; A = 2; P = 3; RA = RP = 0; decision/receipts đủ | S = 0; không chi lại; đóng hồ sơ còn phải kiểm các gates |
| Invoice = 5; company deposit = 2; employee balance = 3 có căn cứ; A = 1; RA = P = RP = 0 | T = 5; E = 3; S = +2; không cộng invoice với deposit/balance hoặc trừ company direct lần hai |
| Raw paid = 7; personal = 1 chắc chắn; work = 6; A = 2; RA = P = RP = 0 | Giữ raw = 7; T = E = 6; S = +4 |
| T = 9; B = 8 | Xin exception; kịch bản từ facts đã biết chưa là quyết định cuối |
| Tiền khách sạn chưa rõ; subtotal đã biết = 2; A = 2 | Chưa tính được toàn bộ S; không dùng subtotal net = 0 để đóng hồ sơ |

Giá trị triệu trong bảng là case giả lập, không runtime policy defaults. Rules được version/activation rõ trước dùng; quality/linkage calibration không nới business/evidence/authority hard gates.

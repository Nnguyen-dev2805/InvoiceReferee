# B1 — Rulebook công ty mô phỏng

Version: `demo-expense-v0.1-proposed`. Status: **PROPOSED**.
Các hạn mức là đề xuất để review; chưa được người phát triển chốt. Không phải
quy định pháp luật hoặc policy của một công ty thật. Không dùng profile này
như policy đã active khi chạy demo live nếu chưa được xác nhận.

Căn cứ: [Product Spec](B1_PRODUCT_SPEC.md). Rule IDs dưới đây là IDs nội bộ.

## 1. Scope và tham số

Một case là một khoản đề nghị thanh toán lại tiền cá nhân đã chi, một primary
bill, cùng supporting evidence cần cho profile. Có thể đính kèm các tài liệu
context. B1 chưa tự phân bổ nhiều bill hoặc gộp nhiều đợt giao hàng trong một
case; case cần cách phân bổ đó được chuyển để tách/làm rõ, không tự tính đoán.

| Parameter | Giá trị đề xuất | Nghĩa |
| --- | --- | --- |
| currency | VND | Chưa thực hiện FX conversion |
| auto_approval_max | 2.000.000đ | Giới hạn quyền tự động, inclusive |
| standard_policy_max | 5.000.000đ | Giới hạn policy thông thường, inclusive |
| inventory_date_gap_days | 7 | Giữ giả định B0 để đối chiếu bill/receipt; không phải luật chung |
| comparison_money_tolerance | 1đ | Tolerance line amount/totals có cùng nghĩa, không áp cho unit price khác basis |
| normalized_unit_price_tolerance | 0 | Unit price quy về cùng basis phải khớp chính xác trong supported decimal domain |
| word_review_threshold | 0.85 | Khởi điểm B0 cho review, không phải xác suất hồ sơ đúng |

Profile thiếu cấu hình/version hoặc chưa được xác nhận active làm execution
bị chặn cấu hình; không tự suy ra được approve. Evaluation fake có thể dùng
fixture profile active chỉ cho test, ghi rõ giả định từ proposal.

## 2. Required evidence và dữ kiện theo profile

| Profile | Khai báo cần có | Primary fields cần usable | Supporting/check áp dụng |
| --- | --- | --- | --- |
| TRAVEL | Employee, amount, PERSONAL payer, purpose/chuyến đi | Merchant, document date, total, currency | Không bắt report kho; đối chiếu amount và payment declaration nếu có nguồn liên quan |
| CLIENT_MEAL | Như trên, thêm mục đích tiếp khách | Merchant, date, total, currency | Không bắt report kho; thiếu purpose hỏi employee |
| WORK_PURCHASE | Như trên, purpose và tình trạng nhận hàng | Merchant, date, total, currency; items cần cho đối chiếu | Tangible purchase luôn cần formal receipt/nhận đủ; item mapping/quantity/unit cần usable |

Merchant/date/total cần nguồn của primary document. Payer/purpose
là khai báo có loại nguồn riêng theo policy mô phỏng, không phải facts từ
invoice. Supporting có mặt không tự chứng minh mọi thông tin đã đủ.

Purpose type BUSINESS và text purpose không rỗng, cùng trip field
cần thiết, là khai báo mà policy mô phỏng sử dụng; không tự chứng minh mục
đích thực ngoài đời. Purpose type PERSONAL xác định known refusal; UNKNOWN
hoặc declaration mâu thuẫn cần làm rõ. Không gọi một chuỗi đủ dài là proof.

Các field optional như supplier tax code chỉ được so khi có căn cứ và check
thật sự áp dụng. Không nói B1 xác minh tax compliance khi chỉ trích xuất MST.

## 3. Rules và phản ứng

| ID | Điều kiện | Kết quả |
| --- | --- | --- |
| SRC-01 | Không có primary bill bắt buộc | FACTUAL_UNKNOWN; hỏi employee bổ sung |
| SRC-02 | Required field missing/uncertain/unusable | FACTUAL_UNKNOWN; hỏi đúng người có thể cung cấp/xác minh |
| SRC-03 | Document/item IDs trùng, refs không tồn tại hoặc output model mâu thuẫn contract | Technical invalid-analysis result; không approve; không đổ thành vi phạm của employee |
| CTX-01 | Purpose/trip cần cho profile còn thiếu | FACTUAL_UNKNOWN; hỏi employee |
| MODE-01 | Khai báo xác định COMPANY/ADVANCE/VENDOR thay vì PERSONAL | Luồng khác B1; REJECT với lý do scope, không hoàn trả lại một khoản company-paid |
| MODE-02 | Payer UNKNOWN hoặc evidence mâu thuẫn payer declaration | FACTUAL_UNKNOWN; không tự kết luận người nộp đã trả |
| SCOPE-01 | OTHER/profile không nằm trong catalog | OUTSIDE_POLICY; policy owner phân loại vào profile đã có hoặc từ chối; không tự mở profile mới |
| SCOPE-02 | Currency/document kind cần FX/refund/credit-note logic chưa có | OUTSIDE_POLICY scope issue; không đổi loại tiền/dấu bằng override tùy ý |
| ELIG-01 | Khai báo xác định đây là chi cá nhân không phục vụ công việc | REJECT; ghi rule/căn cứ; không suy mục đích chỉ từ một tên hàng |
| AMT-01 | Requested amount không khớp verified bill/allocated amount | FACTUAL_UNKNOWN; hỏi phần chênh và căn cứ; không tự chọn min/max |
| AMT-02 | Arithmetic có mâu thuẫn ở phép kiểm tra áp dụng | FACTUAL_UNKNOWN; không tạo request chỉ vì hai nguồn cùng sai |
| INV-01 | Profile có nhận hàng nhưng thiếu formal receipt hoặc chưa rõ nhận đủ | FACTUAL_UNKNOWN; bổ sung/xác nhận có nguồn |
| INV-02 | Mapping, quantity, units, dates hoặc supplier cần so có conflict | FACTUAL_UNKNOWN; không lấy employee text thay inventory evidence |
| LIM-01 | Eligible expense vượt standard_policy_max | OUTSIDE_POLICY; cần case-specific policy exception |
| AUTH-01 | Accepted amount vượt auto_approval_max | BEYOND_AUTHORITY; cần explicit amount approval |

Các scope limitations SCOPE-01/02 chỉ được đóng khi input được làm rõ thành
workflow mà B1 thực sự hỗ trợ hoặc case bị từ chối. Policy owner không thể
approve một capability chưa có chỉ bằng một lý do tự do.

## 4. Kiểm tra số và arithmetic

Input số được parse theo grammar/locale đã công bố; không chấp nhận NaN/
Infinity hoặc tự đoán separators mơ hồ. Quantity/unit price dùng Decimal;
VND payment amount là integer đồng. Giá trị cần kiểm tra có raw value/source.

Các template áp dụng được khai báo trong extraction contract:

- TOTAL_ONLY: có total đáng tin nhưng không có đủ breakdown; arithmetic
  breakdown không áp dụng, không phát sinh các term số 0 để giả chứng minh.
- SIMPLE_ITEMIZED: line amount là quantity × unit price, làm tròn về đồng
  bằng ROUND_HALF_UP ở từng dòng; phép so có tolerance 1đ.
- ITEMIZED_WITH_ADJUSTMENTS: so total với subtotal + tax + fees - discount
  trong tolerance 1đ, chỉ dùng các term mà model **khai báo có mặt trên bill**.
  Bắt buộc subtotal và total usable. Một term khai báo có mặt nhưng không
  đọc được/không usable → UNKNOWN (không default 0). Một term **không khai báo
  có mặt** đóng góp 0. Template adjustments nhưng không khai báo term nào →
  UNKNOWN. Ngoài ra nếu cộng được line amount thì đối chiếu
  sum(line amount) = subtotal (tolerance 1đ). Không tự tính thuế suất hoặc
  khấu trừ thuế; term không rõ không default 0.

Nếu template/basis không xác định được, check phụ thuộc tạo unknown issue.
Khi không có đủ dữ kiện cấu trúc, không kết luận sai số học từ phép tính giả.
Total-only receipt chỉ được xem không áp dụng arithmetic breakdown theo
template đã công bố, không miễn quality/amount/eligibility/authority.

Unit conversion dùng các factor rõ (g/kg/tấn và đơn vị đếm B0). Unit price
được so chính xác trên cùng unit basis; không dùng tolerance 1đ/gram để che
một chênh lệch lớn tính theo kg. Hai unit opaque giống nhau có thể so trực tiếp;
khác unit không có conversion hợp lệ tạo issue, không nhận ratio model đoán.

## 5. Accepted amount và quyền

Không tự tăng requested amount, tự cắt xuống hạn mức hoặc bỏ một phần bill
không rõ để biến case thành routine. Accepted amount dựa trên phần có căn cứ
được chấp nhận. Phần cần loại phải có phân tách/reason hoặc explicit decision.
Nếu chưa xác định được số cuối, tiếp tục hỏi; chưa tạo request.

| Vai trò demo | Hành động được dùng trong B1 |
| --- | --- |
| EMPLOYEE | Bổ sung declaration/evidence, đề xuất correction; không approve/waive |
| REVIEWER | Xác nhận field khi xem được nguồn hoặc yêu cầu nguồn tốt hơn; không tự grant policy exception |
| APPROVER | Approve/deny amount trong standard policy, tối đa 5.000.000đ theo proposal |
| POLICY_OWNER | Grant/deny exception scoped đúng case; approve amount theo exception đã cấp bằng action riêng |

Vượt 5 triệu có thể có cả LIM-01 và AUTH-01. Grant exception chỉ đóng LIM-01;
amount approval là action riêng. Policy owner được approve số tiền trong
đúng exception amount/scope, không có quyền ngầm tạo scope không được B1 hỗ trợ.
Raw evidence unusable/contract invalid không được miễn bởi amount approval.

Một confirmation chỉ có hiệu lực với field/source/case version nêu trong
action. REVIEWER không sửa raw OCR; thêm HumanConfirmedFact có nguồn/lý do.
Thay source, profile, purpose hoặc amount làm các approvals/corrections bị
ảnh hưởng hết hiệu lực; đánh giá lại. Không diễn giải role demo như quyền
của một nhân sự doanh nghiệp đã được xác thực.

## 6. Quyết định và đề nghị chi trả

Code thu mọi issue/check result, không lấy model decision làm final action:

1. Technical failure/config block/Stop: không business completion.
2. Known supported-rule refusal: REJECT có rule/căn cứ.
3. Unresolved factual blocker: REQUEST_INFO, giữ các policy/authority issues
   đã có căn cứ và chưa đóng; chưa xin approval binding cho amount chưa rõ.
4. Outside-policy/authority blocker còn mở: ESCALATE tới owner tương ứng.
5. Mọi điều kiện áp dụng đạt, có explicit approval/exception cần thiết hoặc
   nằm trong quyền tự động: tạo payment request và ghi decision/action.

Sau human approval, kết quả ghi rõ completion basis HUMAN_AUTHORIZED;
không gọi đó là case routine tự động hoàn toàn. Một request hiện hành/case,
chỉ cho accepted amount cuối; không chi trả thực hoặc gộp nhiều lần trả.

## 7. Chốt trước implementation

Người phát triển cần review profile/evidence, hai hạn mức, quyền exceptional
approval và arithmetic templates trên. Sau khi chốt, chuyển thành một policy
version đã active cho demo; đổi rulebook khác phải ghi version/căn cứ.
Threshold adaptation ở B2 không tự sửa các hạn mức/authority/hard gates này.

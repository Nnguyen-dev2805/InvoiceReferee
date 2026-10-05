# InvoiceReferee B1 — Product Spec MVP

Version 0.2, 04/10/2026. **DRAFT: để review hành vi và rulebook đề xuất.**
Chưa có implementation; các giá trị policy mô phỏng chưa được người phát
triển duyệt. Không phải quy định công ty thật hoặc tư vấn thuế/kế toán.

Nguồn: [roadmap](../ROADMAP_V2.md), [decisions](../SPEC_DECISIONS.md),
[yêu cầu cuộc thi](../COMPETITION_REQUIREMENTS.md).

## 1. Mục tiêu đã chốt

Xây lại ý tưởng main thành MVP B1: nhận hồ sơ chi phí, kiểm tra bằng chứng và
policy, xác định số tiền chấp nhận, rồi tự tạo đề nghị chi trả cho hồ sơ thường
quy trong quyền được giao. Hồ sơ cần người có vấn đề và câu hỏi cụ thể, nhận
phản hồi và được kiểm tra lại. B1 có benchmark để so các cải tiến B2.

Main `196e266` là B0 tham khảo lịch sử. Không sao chép lỗi main làm đáp án đúng.
Một app, một người thao tác ở các chế độ nghiệp vụ. Không có bank transfer,
multi-user/tenant, enterprise auth, distributed jobs hoặc crash recovery engine.

## 2. Phạm vi hồ sơ đề xuất

| Profile | Điều kiện thông tin/evidence tối thiểu |
| --- | --- |
| Công tác/đi lại | Mục đích/chuyến đi, số đề nghị, khai báo phương thức chi trả; bill có merchant, ngày và tổng tiền đọc được |
| Tiếp khách | Mục đích công việc, số đề nghị và phương thức chi trả; bill có merchant, ngày và tổng tiền đọc được |
| Mua vật dụng/vật tư | Mục đích công việc, số đề nghị, phương thức chi trả; tangible purchase cần bill và nguồn giao nhận/nhận đủ, đủ dòng hàng/lượng/đơn vị để đối chiếu |

Profile quyết định field/evidence nào cần dùng. Không yêu cầu report kho cho
taxi hoặc bill tiếp khách. Employee declarations được lưu riêng với document
facts; chúng không tự điền lại số tiền, số lượng hoặc receipt status trên bill.

Input B1 ban đầu: PDF/JPG/JPEG/PNG/WEBP và form khai báo. Nếu chọn thêm XML/
CSV/Excel ở spec cuối, cần parser tương ứng và acceptance cases; không nhận
định dạng rồi để nó âm thầm đi vào đường OCR không hỗ trợ như B0.

## 3. Rulebook công ty mô phỏng — đề xuất cụ thể để review

Những con số dưới đây chỉ nhằm có một bản đề xuất có thể kiểm thử, không
được lấy từ main, từ luật hoặc từ một công ty thật.

| Quy định | Giá trị/hành vi đề xuất |
| --- | --- |
| Currency | VND; số tiền chi trả là integer đồng, không dùng float |
| Quyền tự động | Accepted amount <= 2.000.000đ/case nếu mọi điều kiện áp dụng đều đạt |
| Vượt quyền tự động | Trên 2.000.000đ: cần approver duyệt đúng số tiền, không hỏi lại OCR nếu dữ kiện đã rõ |
| Tiền cá nhân đã chi | Là workflow B1; company-paid/advance/vendor-payment được xác định là luồng khác, không tự hoàn trả lại cùng khoản |
| Thiếu chứng từ bắt buộc | Tạo yêu cầu bổ sung; B1 chưa dùng affidavit tự khai như chứng từ thay thế mặc định |
| Chưa rõ giá trị cần dùng hoặc có conflict | Chưa tạo payment request; giải quyết factual issue trước |
| Chi cá nhân không phục vụ công việc | Không eligible; nếu chưa phân định được thì hỏi dữ kiện, không tự đoán từ tên hàng |
| Rule/authority chưa được cấu hình | Không tự approve; thể hiện workflow còn thiếu điều kiện |

Ngưỡng biên được hiểu rõ: đúng 2.000.000đ vẫn nằm trong quyền tự động; đúng
5.000.000đ vẫn nằm trong policy thông thường nhưng vượt quyền tự động. Một
case có thể có cả outside-policy và beyond-authority issue; không che issue
này bằng một approval cho issue khác.

Giới hạn policy không tự bị đổi bởi feedback adaptation. Số ngày nộp, tax
deductibility, FX, refunds và các exceptions khác chưa được định nghĩa là
rule mặc định; không tự áp dụng một quyết định chắc chắn cho input cần chúng.

## 4. Accepted amount

Hệ thống đối chiếu requested amount với dữ kiện cần thiết từ evidence. Mọi
khác biệt có breakdown/căn cứ; không tự tăng số đề nghị chỉ vì bill lớn hơn,
không tự cắt xuống hạn mức để biến outside-policy thành routine.

Accepted amount là phần đã đủ căn cứ và được policy/approval chấp nhận. Nếu
cần loại phần cá nhân hoặc chấp nhận một phần, phải có phân tách đủ rõ và
reason; thông tin không đủ thì tạo issue. Chỉ tạo payment request khi tất cả
issue chặn request đã giải quyết. B1 không thực hiện nhiều lần chi trả một
phần trong khi cùng case còn thay đổi.

Arithmetic/rounding và unit-price basis được đề xuất cụ thể trong
[Rulebook](B1_RULEBOOK.md) để review. Consistency không thay arithmetic;
đơn giá chỉ so khi đơn vị tương thích; duplicate item IDs không làm mất dòng.

## 5. Vai trò logic trong demo

- Employee: nộp hồ sơ, giải thích purpose/payer và bổ sung evidence hoặc đề xuất
  correction. Một khai báo không tự trở thành phê duyệt ngoại lệ.
- Accounting/reviewer: kiểm tra nguồn, xác nhận correction có căn cứ; lưu lại
  source và lý do khi field được xác nhận.
- Approver: duyệt hoặc từ chối amount (kể cả vượt auto_approval_max); phân loại
  case OTHER vào catalog; deny issue thuộc thẩm quyền. Thay policy là hành động
  riêng có version, không tự suy từ việc approve.

Một người có thể chuyển các chế độ để demo; không giả định đó là identity
doanh nghiệp đã được xác thực. Không dùng role mô phỏng như bằng chứng đã
thử với ba nhân sự nghiệp vụ thật.

## 6. Logic quyết định và human loop

1. Tiếp nhận và kiểm tra input theo phạm vi hỗ trợ.
2. Tạo facts từ từng nguồn, giữ raw/normalized value và source references.
3. Xác định required fields theo profile; kiểm tra quality, coverage, contract
   consistency. No candidate không tự có nghĩa dữ kiện đã usable.
4. Chạy arithmetic/consistency và policy trên dữ kiện đủ căn cứ; các check
   độc lập có thể tiếp tục để gom issues, không dùng field chưa usable.
5. Phân loại issues factual / outside-policy / beyond-authority. Lỗi provider/
   schema/format có kết quả technical riêng; không gán sai lý do nghiệp vụ.
6. Nếu không issue chặn, đủ policy và quyền, tự tạo payment request. Profile
   inventory N/A không tự quyết định eligibility toàn case.
7. Nếu có issue, tạo yêu cầu tới đúng vai trò với dữ kiện, source và câu hỏi.
8. Nhận human action, đóng đúng issue được giải quyết, chạy lại check bị ảnh
   hưởng và giữ các issue khác. Không tự bỏ hard gate bằng một lý do tự do.

Kimi cung cấp facts/observations/proposals; code kiểm tra và tổng hợp. Numeric
field UNREADABLE nhưng requires_verification=false là contract mâu thuẫn,
không là quality PASS. Không lấy facts của nguồn khác để bù chỗ mờ.

Ví dụ câu hỏi giả lập: "Bill ghi 1.280.000đ, đề nghị là 1.480.000đ. Phần
200.000đ chênh là khoản nào và căn cứ nào xác nhận?" Số tiền/câu hỏi phải được
tạo từ case thực đang xử lý, không lookup theo tên testcase.

## 7. Hành động nghiệp vụ và controls

Payment request có case/run ID, người nhận demo, accepted amount, currency,
policy version và căn cứ quyết định. Nó là **đề nghị chi trả**, không phải
xác nhận đã chuyển tiền. Nhấn xử lý lại không tạo request trùng; khi input
hoặc quyết định đổi, bản trước được giữ để giải thích trạng thái mới.

Stop ngăn hành động kế tiếp và không áp dụng kết quả muộn. Override có lý do,
vai trò, scope và decision gốc; không thay quality evidence bằng một câu
approve. Lưu lịch sử đủ để truy lại input, output, policy và human action.
Không xây thêm workflow engine cho nhiều máy hoặc resume sau crash ở B1.

## 8. Acceptance trước khi coi B1 là baseline mới

- Routine đủ điều kiện tạo đúng payment request mà không cần duyệt từng case.
- Cases thiếu dữ kiện, ngoài policy và vượt quyền được phân loại và xử lý đúng.
- Empty OCR/missing coverage, duplicate item IDs, bad refs, contradictory
  assessment và unit conversion không gây false pass/mất dòng.
- Source có thể truy lại; consistency, arithmetic và eligibility không bị gộp.
- Human response giải quyết đúng issue; approval không thay evidence hoặc
  authority chưa đủ; Stop/Override ảnh hưởng behavior.
- Bộ case có expected độc lập, Verify Core/Escalation và trace dùng cùng luồng.
- B1 có phiên bản, policy/dataset/model identity và kết quả benchmark để so B2.

Các nghĩa hành vi và con số rulebook cần được review trước khi chuyển thành
spec kỹ thuật/plan. Tài liệu này chưa chứng minh acceptance đã đạt.

## 9. Điều còn cần chốt và bước tiếp theo

Điểm cần người phát triển review đầu tiên: ba profile, required evidence,
ngưỡng auto_approval_max 2.000.000đ và quyền reviewer/approver. Đây
là một đề xuất concrete để sửa, không phải giới hạn đã được giao cho hệ thống.

Các bản nháp [System/Data](B1_SYSTEM_SPEC.md), [Rulebook](B1_RULEBOOK.md) và
[Evaluation](B1_EVALUATION_SPEC.md) đã được viết để đối chiếu cùng product
contract. Review chúng và chốt policy trước khi lập implementation plan. Các
yêu cầu Sprint 2/đóng gói tiếp tục theo roadmap, không dùng MVP scope để tự
bỏ feedback adaptation, independent eval hoặc user evidence của cuộc thi.

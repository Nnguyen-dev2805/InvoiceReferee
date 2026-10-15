# Prompt gửi coding agent — mở rộng quyết toán chi phí ngoài công tác

Hãy triển khai trên nhánh `final` theo
`docs/superpowers/plans/2026-10-14-general-expense-hoangha-integration.md`.
Đọc toàn bộ spec liên kết trong plan, AGENTS.md, các hợp đồng final và
`data/tham-khao/uc-03/final-case-mapping-v3.json`. Đọc lại HEAD/status/source
hiện tại khi bắt đầu; agent khác đang triển khai phần hóa đơn và ghi nhận ứng trong
cùng workspace, nên chờ người đó bàn giao gate shared-file và giữ nguyên mọi
thay đổi của họ. Một integrator sở hữu service/schema/domain/API/frontend trong
đợt này. Không commit, push hay reset dữ liệu nếu chưa có ủy quyền Git riêng.

Mục tiêu là một quy trình quyết toán chi phí công việc do nhân viên thanh toán,
có ứng hoặc đã xác minh không ứng; hỗ trợ công tác, tiếp khách tại chỗ, mua văn
phòng phẩm/thiết bị nhỏ và dịch vụ vận hành nhỏ. Bắt đầu từ 25 PDF case Hoangha
gốc (65 PDF), giữ nguyên byte/hash, không biến TC01/TC02/TC04 thành chuyến công
tác. Mẫu tham chiếu nằm ở `data/test-kit/uc03-expansion/` và cách tổ chức giấy
gốc ở `.worktrees/hoangha/scripts/generate_uc3_testcases.py`.

Port rule danh mục Hoangha: bữa ăn/tiếp khách ≤5.000.000 đ mỗi khoản; taxi
≤2.000.000 đ mỗi khoản; hạn nộp30ngày từ ngày chi có căn cứ; chi cá nhân bị
loại khỏi chi phí công việc. Giữ quyền final: hệ thống tự công nhận E≤8.000.000,
tự phát yêu cầu khi |S|≤4.000.000, người duyệt demo chỉ tới20.000.000 đ theo
đúng action/scope/grant. Activity budget B thuộc dữ liệu legacy, không là gate
quyết toán hoặc precondition cho một route. Không mang mức
100 triệu của Hoangha sang, không mặc định routine phải chờ kế toán duyệt.

Điểm đã chốt: dòng thiếu chứng từ có lý do (TC20) theo FACT→POLICY. Lý do trên
giấy không tự chứng minh dịch vụ/số tiền/nhân viên đã trả. Hỏi đúng FACT trước;
khi đủ facts mới hỏi người có quyền quyết ngoại lệ thiếu chứng từ, ghi lại lý
do/quyết định đúng rule/expense/scope/basis. Không thêm giấy hay màn hình giải
trình riêng. Không có kết luận chi/thu khẳng định khi còn dòng ảnh hưởng chưa rõ.

Giữ policy demo hóa đơn nhân viên đã trả mà người dùng vừa chốt; không thêm
chứng từ thanh toán nhà cung cấp hoặc đoạn xác nhận dài vào giấy. Với hóa đơn
Hoangha chỉ có tên công ty mua, cho phép liên kết tổng hợp giấy đề nghị ghi đúng
nhân viên, invoice reference khớp, công ty mua đúng context và không có nguồn
trái chiều. Nếu invoice ghi tên người mua khác hoặc chứng từ bổ sung ghi người
trả khác, giữ FACT/out-of-scope; không bịa confirmation. Actual A/P/R vẫn phải
có money-event/coverage thực nhận riêng. Không dùng số ứng in trên giấy như A.

Triển khai T0–T7 theo thứ tự trong plan: profile hoạt động và giấy chung;
document-type extraction/admission; category/deadline/authority;
matching/phân bổ nhiều tài liệu; FACT→POLICY; 25 packet context/gold độc lập;
UI/API/Verify. Đảm bảo một hóa đơn dùng chung nhiều dòng không cộng trùng hoặc
vượt số nguồn; document hỗ trợ không thành expense thứ hai. Không coi enum
Hoangha có nghĩa đã có policy đầy đủ cho mọi loại.

Đánh giá các case theo final, không ép nhãn Hoangha: TC01 COLLECT760.000 khi
đủ E/A/P/R/basis; TC02 PAY400.000; TC03 balanced không instruction0; TC04/14
cần quyền ngoài demo; TC13 loại chi cá nhân nhưng vẫn quyết toán ứng; TC17 phải
xử lý vé điện tử theo vai trò đúng; TC18 giữ ambiguity payer của chứng từ gốc;
TC20 có các nhánh có điều kiện; TC22 over-allocation FACT; TC23 allocation đúng
nhưng E8.640.000 cần AUTHORITY; TC24 nguồn dư giữ để hỏi relevance; TC25 lệch
900.000/700.000 không chọn một số. Context/gold author độc lập, không dùng
expected.json cũ làm sự thật cho runtime/model.

Mỗi task: test RED có ý nghĩa → sửa một trách nhiệm → GREEN. Chạy kiểm tra
đúng tầng, full backend, frontend/build/browser, Core4/Escalation5 và các case
LIVE có provider với mode/source/model/clock/chi phí được ghi rõ. Một test fake
không phải LIVE; packet authoring không phải E2E. Không đổi ngày trên PDF, kéo dài
coverage, nâng quyền/grant hay nới profile để ép case PASS. Cập nhật hợp đồng,
runbook/status/checklist bằng bằng chứng thực; ghi NOT_RUN/FAILED đúng tên khi
chưa xong. Bàn giao danh sách thay đổi, lệnh và kết quả, corpus/score/bộ log,
những giới hạn còn lại. Không claim toàn25 đều AUTO: chúng gồm routine,
FACT/POLICY/AUTHORITY và case ngoài phạm vi.

# Nguồn giả lập — Giao quyền và quyết định trước công việc

Tài liệu synthetic, không chữ ký thật hoặc xác minh identity thực. Issuer là tổ chức giả lập `ORG-DEMO-01`; việc nhập bởi operator không là authenticated issuer.

## authority

Mã nguồn `AUTH-DEMO-01`, hiệu lực giả lập03–10/10/2026. Tổ chức giao `APR-DEMO-01` quyền quyết định công việc `CT-DEMO-01` của `NV-DEMO-01`: cho phép hành trình/nội dung đề nghị, duyệt ngân sách tổng8.000.000VND và khoản ứng đề nghị2.000.000VND, phê duyệt quyết toán đủ căn cứ thuộc công việc trong ngân sách8.000.000VND cùng hướng chi/thu tương ứng.

Nguồn này không giao quyền đối với nhân viên/công việc khác hoặc ngoại lệ vượt ngân sách. Các nội dung ngoài scope cần nguồn giao quyền/quyết định bổ sung, không tự suy từ chức danh. Quyền giới hạn8/2 ở đây gắn **nội dung cụ thể của packet**, không là policy trần mặc định cho mọi công việc hoặc hai cấp tiền. Không miễn evidence/quality/arithmetic.

## pretrip-decision

Mã `DEC-PRE-DEMO-01`, ngày03/10/2026, người quyết định `APR-DEMO-01`, work/employee như nguồn quyền. Nội dung:

- Cho phép công tác Hà Nội05–06/10 cho mục đích trao đổi dự án đã nêu.
- Ngân sách tổng8.000.000VND, gồm dự kiến company trả vé3.000.000 và employee thanh toán các khoản công việc5.000.000.
- Duyệt khoản ứng2.000.000VND cho nhu cầu employee, gắn cùng công việc. Không trần riêng cho khách sạn/ăn/di chuyển hoặc điều kiện hạng vé.
- Thực hiện/actualreceipt cần source riêng; ngân sách/ứng chưa là phê duyệt mọi chi phí sau công việc.

Quyết định giữ nguyên tới M1/M2 trong câu chuyện; không có sửa/hủy/Stop hoặc điều kiện nguồn chưa xử lý theo [scope](coverage_m1.md). Đối chiếu source nếu run phát sinh dữ liệu khác, không dùng fixture ID làm nhánh approve.

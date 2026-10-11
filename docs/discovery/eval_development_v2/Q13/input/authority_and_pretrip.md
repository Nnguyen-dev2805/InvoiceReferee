# Nguồn giả lập — Giao quyền và quyết định trước công việc

Tài liệu synthetic, không chữ ký thật hoặc xác minh identity thực. Issuer là tổ chức giả lập `ORG-DEMO-01`; việc nhập bởi operator không là authenticated issuer.

## authority

Nguồn AUTH-DEMO-01, issuer ORG-DEMO-01, hiệu lực03–10/10/2026, giao APR-DEMO-01 quyền cho phép CT-DEMO-01 của NV-DEMO-01, duyệt ngân sách8.000.000VND/ứng2.000.000VND và quyết toán trongngân sách. Nguồn này đồng thời giao quyền xemxét ngoại lệ chi phí thực tế của chính côngviệc này tới tổng9.000.000VND, gồm quyết định khoản/phần được chấp nhận và chi/thu quyếttoán tươngứng khi facts/sources đủ. Đây là quyền xử lý ngoại lệ, không phải quyết định đã chấp nhận ngoại lệ, không nângB từ8 lên9. Không quyền khácngoàiscope hoặc miễn sốhọc/evidence. Các số gắn case này, không cấu hình/cấp quyền tiền toànMVP.

## pretrip-decision

Mã `DEC-PRE-DEMO-01`, ngày03/10/2026, người quyết định `APR-DEMO-01`, work/employee như nguồn quyền. Nội dung:

- Cho phép công tác Hà Nội05–06/10 cho mục đích trao đổi dự án đã nêu.
- Ngân sách tổng8.000.000VND, gồm dự kiến company trả vé3.000.000 và employee thanh toán các khoản công việc5.000.000.
- Duyệt khoản ứng2.000.000VND cho nhu cầu employee, gắn cùng công việc. Không trần riêng cho khách sạn/ăn/di chuyển hoặc điều kiện hạng vé.
- Thực hiện/actualreceipt cần source riêng; ngân sách/ứng chưa là phê duyệt mọi chi phí sau công việc.

Quyết định giữ nguyên tới M1/M2 trong câu chuyện; không có sửa/hủy/Stop hoặc điều kiện nguồn chưa xử lý theo [scope](coverage_m1.md). Đối chiếu source nếu run phát sinh dữ liệu khác, không dùng fixture ID làm nhánh approve.

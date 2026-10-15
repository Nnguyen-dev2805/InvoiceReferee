# Demo TC01 — Nguyễn Minh An / Công ty An Thịnh

`company-context.json` giữ schema demo cũ và các hoạt động mẫu; tên nhân viên/công
ty đã đổi. `tc01-company-context.json` là fixture riêng cho hai PDF gốc trong
`data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua/`.

Fixture TC01 là dữ liệu tổ chức **SIMULATED**, không phải giao dịch ngân hàng
được ứng dụng tự xác thực. Nó cung cấp độc lập: danh tính công ty/nhân viên;
hoạt động tiếp khách WORK_EXPENSE; grant đúng action/scope
(hệ thống công nhận chi phí tối đa 8 triệu, phát hành tiền tối đa 4 triệu; người
duyệt tối đa 20 triệu); policy tiếp khách 5 triệu/khoản, taxi 2 triệu/khoản,
hạn nộp 30 ngày; bản ghi ứng thực nhận 4 triệu ngày 05/10; số dư đầu kỳ 0 và
lịch sử chưa chi thêm/hoàn trả/đảo giao dịch đến mốc demo.

## Chạy web riêng để không thay database hiện tại

Từ root repository, dùng `.env` hiện có:

```bash
rtk proxy uv run --no-sync python scripts/dev.py \
  --mode live --port 8012 \
  --context data/demo/tc01-company-context.json \
  --demo-as-of 2026-10-14T23:00:00+07:00 \
  --db .runtime/demo-tc01/app.sqlite \
  --uploads .runtime/demo-tc01/uploads
```

Mở http://127.0.0.1:8012. Nếu chưa có frontend build, chạy lệnh build theo
toolchain trong AGENTS.md trước. Không cần xóa DB cũ hoặc thay API keys.

`--demo-as-of` là **mốc đối soát demo cố định**, không đổi thời gian trace hoặc
ngày giao dịch trên chứng từ. Nó làm case lặp lại được mà không bịa coverage đến
tương lai. Không dùng mốc này để đánh giá giao dịch thật mới phát sinh. Bỏ flag
thì backend dùng giờ thực và lịch sử cũ có thể phải được kế toán đối chiếu lại.

## Thao tác

1. Role nhân viên hiển thị **NGUYỄN MINH AN**.
2. Tạo hồ sơ, tải `report_hoan_ung.pdf` và `hoa_don_dien_tu.pdf`, bấm đọc.
3. Hai PDF gốc không ghi mã hồ sơ ứng/mã giao dịch đã khai trong fixture. Hệ
   thống có thể gợi ý hoạt động tiếp khách dựa trên nội dung; **xác nhận ứng viên
   TC01 khi được hỏi**, không tự gắn chỉ vì tên/số tiền giống nhau. Không sửa PDF
   để thêm tham chiếu giả. Nếu bắt đầu từ hồ sơ TC01 đã gắn, hệ thống kế thừa
   liên kết và vẫn kiểm mâu thuẫn.
4. Kiểm bản nháp, nộp. Khi liên kết và căn cứ đủ: T=E=3.240.000; A=4.000.000;
   P=R=0; S=−760.000; yêu cầu **thu 760.000 đ**. Chưa coi khoản thu là đã thực hiện.

Các con số kết quả ở README chỉ là hướng dẫn chấm; không nằm trong JSON runtime.
Không dùng context TC01 cho các case khác. Đổi fixture không tự gắn lại hoặc
tái đối soát hồ sơ WAITING đã lưu trong database khác.

## Chứng từ ứng TC01 và sinh lại

Folder `tc01-chung-tu-ung/` có biên nhận chuyển khoản và phiếu chi tiền mặt, đều
ghi Nguyễn Minh An / Công ty An Thịnh / tiếp khách dự án / 4 triệu. Phiếu tiền
mặt có ba vị trí ký trên một hàng. Mã tham chiếu `TU-TC01` nối với context; mã
giao dịch là `FT-TC01-0001` hoặc số phiếu `PC-TC01-0001`.

```bash
rtk proxy uv run --no-sync python scripts/sinh_uc03_pilot.py \
  --tc01-output data/demo/tc01-chung-tu-ung
```

- **Chuyển khoản:** dùng `03-bien-nhan-chuyen-khoan.pdf` với
  `context-chuyen-khoan.json`; `tc01-company-context.json` cũng là nhánh này.
- **Tiền mặt:** dùng `04-phieu-chi-tien-mat.pdf` với `context-tien-mat.json`.
  Thay đối số `--context` trong lệnh chạy bằng đường dẫn context tiền mặt và
  dùng DB/uploads riêng cho nhánh đó.
- Cả hai là phương án thay thế cho cùng kịch bản ứng 4 triệu; không upload/ghi
  nhận cả hai trong một lượt. Context đã có ứng thì tải lại chứng từ không được
  làm tăng A lần nữa. Nếu muốn test ghi nhận lần đầu, cần context chưa có ứng.
- Bộ giấy quyết toán/hóa đơn gốc TC01 giữ nguyên trong `data/tham-khao/uc-03`.
  Không dùng các chứng từ ứng công tác F01 cho TC01 tiếp khách.

Manifest trong folder chứng từ chứa hash của PDF và context, không có đáp án
tiền. Script từ chối ghi đè folder non-empty chưa được quản lý hoặc symlink.

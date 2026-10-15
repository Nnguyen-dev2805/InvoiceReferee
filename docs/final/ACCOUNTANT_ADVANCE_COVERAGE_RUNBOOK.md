# Kế toán ghi nhận khoản ứng và xác nhận lịch sử tiền

Runbook này hướng dẫn xử lý một hồ sơ quyết toán mới khi nhân viên đã nộp giấy
quyết toán/hóa đơn nhưng khoản ứng chưa có trong sổ của hồ sơ. Tạm ứng, chấp nhận
công việc và đối chiếu toàn bộ lịch sử tiền là ba căn cứ riêng biệt.

## 1. Tạo hồ sơ và đọc chứng từ quyết toán

1. Đăng nhập với vai trò nhân viên, tạo hồ sơ cho đúng hoạt động.
2. Tải giấy quyết toán và các hóa đơn/chứng từ chi phí lên hồ sơ.
3. Kiểm tra bản nháp trước khi nộp: tổng chi phí, số ứng khai trên giấy, từng dòng
   chi và hóa đơn đã ghép. Chỉ xác nhận ghép khi số hóa đơn và dòng chi có căn cứ.
4. Nộp hồ sơ. Tên hoạt động đang nhập không tự tạo quyền chi và không chứng minh
   một chứng từ ứng thuộc hoạt động đó.

## 2. Kế toán ghi nhận tiền ứng thực nhận

1. Mở đúng hồ sơ với vai trò kế toán và tải chứng từ chuyển khoản/phiếu chi gốc
   vào **Ghi nhận tạm ứng từ chứng từ**.
2. So từng trường với chứng từ gốc: bên chi, người nhận, số tiền, ngày, mã giao
   dịch, phương thức và trạng thái. Chỉ bổ sung trường OCR còn thiếu sau khi đã
   đọc chứng từ; không ghi đè dữ kiện OCR mâu thuẫn.
3. Nếu mã tham chiếu không tự nối được với một hồ sơ duy nhất, xác nhận thủ công
   đúng hoạt động và ghi căn cứ so khớp. Mã xung đột hoặc trỏ tới hồ sơ khác phải
   được xử lý trước; hồ sơ đang mở không phải bằng chứng liên kết.
4. Nếu bản nháp đủ dữ kiện và đã tự liên kết, kiểm tra rồi bấm **Xác nhận ghi nhận**;
   không cần nhập câu xác nhận bằng chữ. Nếu bổ sung trường OCR thiếu, ghi căn cứ
   bổ sung; liên kết thủ công dùng ô lý do liên kết để giải thích, không nhập hai
   lần. Chỉ giao dịch hoàn tất mới thành tiền đã xác minh. Upload/bản nháp tự nó
   không ghi tăng khoản ứng. Server lưu người xác nhận, thời điểm và chứng từ.

Sau khi xác nhận, hệ thống lưu bản gốc, bản đọc, tham chiếu trang/trích dẫn, giao
dịch, người xác nhận và căn cứ chấp nhận hoạt động. Chấp nhận hoạt động không
chuyển trạng thái `PROPOSED` thành `AUTHORIZED`, cũng không cấp quyền phát hành
lệnh.

## 3. Sau khi ghi nhận ứng — không xác nhận thêm

Bấm **Xác nhận ghi nhận** ở bước2 là đủ. Khi chứng từ rõ, đúng người/công việc
và giao dịch hoàn tất, hệ thống ghi A một lần rồi tự đối soát tiền của hồ sơ.
Không còn form, checkbox hoặc nút xác nhận lịch sử ban đầu. Bảng lịch sử chỉ
hiển thị các khoản đã ghi nhận; không cần nhập lại hoặc tick để qua bước.

Với TC01, nếu các căn cứ khác đều hợp lệ: A4triệu/E3,24triệu → COLLECT760.000.
Nếu giấy khai ứng mà chưa có bản ghi thì bổ sung chính chứng từ ứng; không coi
ứng chưa xác minh là0. Có khoản chưa rõ/trùng/mâu thuẫn thì xử lý đúng khoản đó.
Đây là theo dõi sổ của hồ sơ, không phải kiểm chứng toàn bộ tài khoản ngân hàng.

## 4. Đọc kết quả và giới hạn

Kiểm tra `T`, `E`, `A`, `P`, `R`, `S`, các vấn đề còn mở và lệnh được phát hành.
TC01 mẫu có `E=3.240.000`, `A=4.000.000`, `P=0`, `R=0`, nên `S=-760.000` và có
thể phát hành `COLLECT 760.000` khi toàn bộ căn cứ, coverage và quyền hiện hành
đều hợp lệ. `ISSUED` là lệnh đã được hệ thống phát hành; không có nghĩa tiền đã
được thu. Chỉ ghi nhận hoàn tất khi có chứng từ tiền trả thực tế. Tiền nhân viên
đã trả lại sẽ làm giảm số còn phải thu; không phát lệnh thu lần hai cho cùng số.

Sổ hồ sơ tổng hợp các khoản đã được xác nhận theo chứng từ.
Nó không phải kết nối ngân hàng hay kiểm chứng độc lập từ ngân hàng. Mọi khoản
không đọc được, thiếu căn cứ hoặc chưa phân loại phải giữ ở trạng thái chưa xác
định và chuyển người xử lý.

## 5. Bằng chứng kiểm chứng TC01 trên DB cô lập

Kết quả và hash đầu vào được ghi trong
[`reviews/2026-10-15-accountant-advance-coverage-live.md`](reviews/2026-10-15-accountant-advance-coverage-live.md).
Lượt LIVE cuối dùng DB/upload riêng dưới
`.runtime/accountant-flow-live-20261015-confirmed/`; nó không phải DB ứng dụng dùng
hằng ngày. Browser reload vẫn đọc lại được coverage và lệnh `COLLECT 760.000`.

Để chạy lại từ một thư mục làm việc đã cấu hình LIVE, hãy chọn **đường dẫn DB và
uploads mới** cho mỗi lượt:

```bash
uv run python scripts/dev.py --mode live --host 127.0.0.1 --port 8014 \
  --context data/demo/company-context.json \
  --db .runtime/accountant-flow-live-YYYYMMDD/app.sqlite \
  --uploads .runtime/accountant-flow-live-YYYYMMDD/uploads

ACCOUNTANT_FLOW_PORT=8014 \
ACCOUNTANT_FLOW_EVIDENCE_DIR=.runtime/accountant-flow-live-YYYYMMDD/evidence \
PLAYWRIGHT_OUTPUT_DIR=../.runtime/accountant-flow-live-YYYYMMDD/playwright \
npx --prefix frontend playwright test \
  --config frontend/playwright.accountant-flow.config.ts
```

Lượt này gọi OCR/model providers thật. Đầu ra phụ thuộc chất lượng đọc; xem mọi
trường thiếu và chỉnh từ chứng từ gốc như bước 2. Không tải lại bản test thành
chứng cứ nghiệp vụ thật, không dùng số liệu mẫu để xác nhận lịch sử công ty và
không chạy vào DB đang chứa dữ liệu người dùng.

## 6. Nhân viên hoàn tiền và đóng hồ sơ

1. Có COLLECT 760.000 còn hiệu lực: nhân viên chọn lệnh, tải bằng chứng hoàn tiền
   rồi bấm **Tải lên và đọc**. Chưa ghi R, hiển thị chờ kế toán xác nhận.
2. Kế toán kiểm tra và bấm **Kế toán xác nhận đã nhận**. Giao dịch đúng luồng cập nhật sổ hồ sơ tự động; không có bước xác nhận lịch sử riêng.
3. Đủ 760.000: R=760.000, S=0; không còn blocker thì hồ sơ **Đã quyết toán**.
   Hoàn một phần giữ phần còn phải thu; sai người nhận/thất bại không ghi tiền;
   hoàn thừa giữ actual và có blocker, không tự đóng.

Kiểm chứng 15/10/2026: xem `reviews/2026-10-15-managed-money-history.md`.

Cập nhật luồng không có xác nhận lịch sử riêng: `reviews/2026-10-15-no-extra-history-confirmation.md`.

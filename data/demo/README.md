# Demo TC01–TC25 — dữ kiện và kết quả mong đợi

Nguồn: **25 case / 65 PDF** trong [thư mục tham khảo](../tham-khao/uc-03/).
Bản tổng hợp từ nội dung PDF, **chưa phải kết quả chạy pipeline**.

## Điều kiện đọc ground truth

- Hai cột số tiền là **kê khai trên giấy**, đơn vị **triệu đồng**; không tự chứng minh tiền đã chuyển.
- Kết quả chi/thu giả định đã xác minh đúng nhân viên/công việc, chứng từ hợp lệ, ứng thực nhận bằng số khai, chưa có chi bổ sung/hoàn trả (**P=R=0 trong sổ hồ sơ**) và đủ policy/quyền. Thiếu các căn cứ này thì cần bổ sung trước.
- Case có mâu thuẫn phải xử lý xong trước khi phát hành tiền. Các con số sau sửa/loại khoản là **nhánh có điều kiện**, không phải tự sửa hồ sơ.
- **FACT:** thiếu/mâu thuẫn dữ kiện; **POLICY:** ngoài quy định; **AUTHORITY:** vượt quyền. Nhiều nhóm có thể cùng xuất hiện.

## Bảng tra cứu

| Case | Chi kê khai | Ứng kê khai | Điểm đối soát chính | Ground truth mong đợi |
| --- | ---: | ---: | --- | --- |
| [TC01](../tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua/) | 3,24 | 4 | Giấy và hóa đơn khớp. | **Thu 760.000 đ**. |
| [TC02](../tham-khao/uc-03/tc02-hop-le-cong-ty-thanh-toan-them/) | 5,4 | 5 | Mua máy in; số tiền khớp. | **Chi 400.000 đ**. |
| [TC03](../tham-khao/uc-03/tc03-hop-le-khong-phat-sinh-chenh-lech/) | 4,32 | 4,32 | Chi và ứng bằng nhau. | **Cân bằng**, không tạo lệnh số 0. |
| [TC04](../tham-khao/uc-03/tc04-hop-le-nhieu-mat-hang-thiet-bi/) | 83,6 | 85 | Chi phí vượt quyền demo 20 triệu. | **AUTHORITY**; chưa phát hành tiền. Chênh lệch kê khai: thu 1,4 triệu. |
| [TC05](../tham-khao/uc-03/tc05-tong-cac-dong-tren-bao-cao-khong-khop/) | 3,5 | 4 | Hai dòng cộng 3 triệu, giấy ghi 3,5 triệu; hóa đơn 3,24 triệu. | **FACT**; làm rõ số học và căn cứ dịch vụ, chưa chốt tiền. |
| [TC06](../tham-khao/uc-03/tc06-chenh-lech-quyet-toan-ghi-sai/) | 3,24 | 4 | Giấy ghi hoàn 700.000, phép tính ra 760.000. | **FACT** về lệch 60.000; không âm thầm sửa và phát hành tiền. |
| [TC07](../tham-khao/uc-03/tc07-so-tien-bang-chu-tren-bao-cao-khong-khop/) | 3,24 | 4 | Số là 3,24 triệu, bằng chữ là 3,5 triệu. | **FACT**; xác nhận/sửa giá trị đúng trước khi tính tiền. |
| [TC08](../tham-khao/uc-03/tc08-bao-cao-va-hoa-don-lech-so-tien/) | 3,5 | 4 | Giấy cao hơn hóa đơn 3,24 triệu đúng 260.000. | **FACT**; giải quyết chênh lệch trước khi chốt chi phí. |
| [TC09](../tham-khao/uc-03/tc09-ma-so-thue-nguoi-mua-thuoc-cong-ty-khac/) | 3,24 | 4 | MST bên mua 7777777777 cần đối chiếu tổ chức. | **FACT nếu sai tổ chức**; chưa tự nhận hóa đơn là hợp lệ. |
| [TC10](../tham-khao/uc-03/tc10-hoa-don-thieu-ma-so-thue-nguoi-mua/) | 3,24 | 4 | Hóa đơn trống MST người mua. | Bổ sung/xác minh danh tính và điều kiện chứng từ theo policy; chưa tự cho qua. |
| [TC11](../tham-khao/uc-03/tc11-so-hoc-tren-hoa-don-khong-nhat-quan/) | 5,5 | 6 | Tiền hàng 5 triệu + thuế 400.000 = 5,4 triệu, tổng in 5,5 triệu. | **FACT**; chưa phát hành thu 500.000 hay 600.000 khi chưa sửa nguồn. |
| [TC12](../tham-khao/uc-03/tc12-hoa-don-trung-dinh-danh-voi-ho-so-truoc/) | 3,24 | 4 | Invoice 00000101; cần lịch sử sử dụng để xác định trùng. | Nếu đã dùng: chặn cộng lại. Nếu chưa dùng và đủ căn cứ: **thu 760.000 đ**. |
| [TC13](../tham-khao/uc-03/tc13-khoan-chi-ruou-bia-can-chuyen-policy/) | 2,16 | 3 | Rượu vang cho mục đích cá nhân sau giờ làm. | Loại khỏi chi công việc: **T=E=0; thu 3 triệu**, không chỉ thu 840.000. |
| [TC14](../tham-khao/uc-03/tc14-tong-ho-so-vuot-tham-quyen-100-trieu/) | 121 | 120 | Chi phí 121 triệu vượt quyền demo dù chênh lệch chỉ 1 triệu. | **AUTHORITY**; chưa được phát hành chi 1 triệu. |
| [TC15](../tham-khao/uc-03/tc15-evidence-cung-so-tien-nhung-sai-noi-dung/) | 2,7 | 3 | Giấy khai sửa máy in; hóa đơn là vé máy bay, khác tham chiếu. | **FACT**; cùng số tiền không đủ để ghép chứng từ. |
| [TC16](../tham-khao/uc-03/tc16-hop-le-ba-hoa-don-trong-mot-bao-cao-cong-tac/) | 10,26 | 12 | Ba hóa đơn khớp; chi phí vượt mức tự công nhận 8 triệu. | **AUTHORITY**; sau quyết định đúng quyền: **thu 1,74 triệu**. |
| [TC17](../tham-khao/uc-03/tc17-hop-le-hoa-don-kem-ve-dien-tu-thay-the/) | 5,6 | 6 | Hai hóa đơn và vé gửi xe; tổng khớp. | Nếu vé được policy chấp nhận: **thu 400.000 đ**; không cộng trùng vé. |
| [TC18](../tham-khao/uc-03/tc18-hop-le-mot-dong-dung-hai-tai-lieu-thay-the/) | 4,2 | 5 | Một khoản nhân công có hai tài liệu hỗ trợ. | Nếu đủ căn cứ dịch vụ/thanh toán: **thu 800.000 đ**; không cộng đôi khoản nhân công. |
| [TC19](../tham-khao/uc-03/tc19-thieu-chung-tu-va-khong-co-ly-do-cho-mot-dong/) | 3,5 | 4 | Thiếu chứng từ cho khoản ăn 800.000, không có lý do. | **FACT** trước. Nếu khoản được chấp nhận: thu 500.000; nếu có quyết định loại khỏi E: thu 1,3 triệu. |
| [TC20](../tham-khao/uc-03/tc20-co-ly-do-cho-dong-khong-co-chung-tu/) | 1,48 | 2 | Thiếu chứng từ gửi xe 100.000 nhưng có lý do. | **FACT → POLICY** nếu vẫn thiếu chứng từ bắt buộc. Chấp nhận hợp lệ: thu 520.000; loại khỏi E: thu 620.000. |
| [TC21](../tham-khao/uc-03/tc21-mot-hoa-don-duoc-khai-bao-nhung-chua-dinh-kem/) | 14,04 | 15 | Thiếu hóa đơn 00002103 cho khoản 1,08 triệu. | **FACT**, sau đó **AUTHORITY** vì E vượt 8 triệu. Đủ khoản: thu 960.000; loại khoản khỏi E: thu 2,04 triệu. |
| [TC22](../tham-khao/uc-03/tc22-mot-hoa-don-bi-dung-vuot-gia-tri-cho-hai-dong/) | 8,1 | 9 | Hóa đơn 5,4 triệu bị phân bổ 7,56 triệu, vượt 2,16 triệu. | **FACT**. Loại phần thiếu căn cứ khỏi E: thu 3,06 triệu; bổ sung đủ: cần AUTHORITY rồi thu 900.000. |
| [TC23](../tham-khao/uc-03/tc23-hop-le-mot-hoa-don-phan-bo-cho-nhieu-dong/) | 8,64 | 9 | Một hóa đơn phân bổ nhiều dòng đúng tổng; E vượt 8 triệu. | **AUTHORITY**; sau quyết định đúng quyền: **thu 360.000 đ**. |
| [TC24](../tham-khao/uc-03/tc24-co-hoa-don-dinh-kem-nhung-khong-xuat-hien-tren-report/) | 2,7 | 3 | Có thêm hóa đơn ăn uống cá nhân 1,08 triệu không kê trên giấy. | Làm rõ tài liệu thuộc hồ sơ hay tải nhầm; không cộng vào E. Khi hai khoản kê khai hợp lệ: **thu 300.000 đ**. |
| [TC25](../tham-khao/uc-03/tc25-tai-lieu-thay-the-lech-so-tien-voi-report/) | 4,14 | 5 | Giấy khai di chuyển 900.000, phiếu thu ghi 700.000. | **FACT** về lệch 200.000. Nếu sửa hợp lệ về 700.000: **thu 1,06 triệu**. |

## Quy tắc chung

- **S = E − A − P + R**: dương → chi thêm; âm → thu lại; bằng 0 → cân bằng khi không còn vấn đề cần xử lý.
- Ngưỡng demo: tự công nhận chi phí **8 triệu**, tự phát hành chi/thu **4 triệu**, người duyệt **20 triệu**; không có ngân sách B riêng. Tiếp khách/bữa ăn **5 triệu/khoản**, taxi **2 triệu/khoản**, hạn nộp **30 ngày**.
- Hóa đơn hợp lệ gắn đúng nhân viên/công việc là căn cứ nhân viên đã trả theo **policy demo**; không phải xác minh ngân hàng. Chữ ký in không tự cấp quyền.
- Khoản chi công việc bị loại khỏi E vẫn có thể nằm trong T; chi cá nhân ngoài cả T/E. Số ứng thực nhận vẫn phải quyết toán.
- Upload bằng chứng hoàn tiền chưa tăng R. Kế toán xác nhận thực nhận mới cập nhật tiền; chỉ đóng hồ sơ khi hết vấn đề và nghĩa vụ tiền đã hoàn tất.

Chi tiết quy định: [Implementation contracts](../../docs/final/IMPLEMENTATION_CONTRACTS.md).

## Context để chạy test

- `company-context.json`: **dùng chung một app cho 25 case, đã có sẵn 25 khoản ứng thực nhận giả lập** và lịch sử tách theo từng công việc; không cần kế toán upload biên nhận ứng. Không có transcription mẫu.
- `cases/<tên-folder-case>/context.json`: có đúng khoản ứng thực nhận giả lập theo README, P=R=0 theo sổ fixture; dùng kiểm đối soát từ PDF.
- `cases/<tên-folder-case>/context-ui.json`: chưa ghi khoản ứng; dùng khi muốn kế toán upload biên nhận ứng và xác nhận trên UI.
- [manifest.json](manifest.json): đường dẫn context riêng, hash PDF, mốc chạy **16/10/2026 12:00 +07:00**. Context chung chạy cả25 trong một DB; context riêng phục vụ test cô lập. TC12 cần hồ sơ trước đã sử dụng hóa đơn để kiểm trùng thực sự.
- `tc01-company-context.json` và hai context trong `tc01-chung-tu-ung/` giữ tương thích cho TC01; chọn chuyển khoản **hoặc** tiền mặt, không cộng cả hai.
- Context chỉ chuẩn bị đầu vào; không tự sửa mismatch, cấp ngoại lệ hay tạo bằng chứng hoàn/chi. MST chuẩn đã lưu nhưng chưa bổ sung gate so MST tổ chức trong lượt này. Không bịa ngày chuyến đi còn thiếu trên giấy.

Chạy chung cả25 case, đã có ứng (DB demo riêng với DB đang dùng):

```bash
rtk proxy uv run python scripts/dev.py --mode live --port 8012 \
  --context data/demo/company-context.json \
  --demo-as-of 2026-10-16T12:00:00+07:00 \
  --db .runtime/uc03-all/app.sqlite --uploads .runtime/uc03-all/uploads
```

Sinh lại context: `rtk proxy uv run python scripts/sinh_context_uc03.py`.
Đổi context không tự xóa hồ sơ/hoạt động đã lưu trong DB cũ. Fixture bảy hoạt động cũ chỉ còn ở `tests/fixtures/legacy-company-context.json` phục vụ hồi quy.

# Pilot UC03 — ba kết quả tiền

Toàn bộ thông tin/tài liệu là synthetic. Đây là bộ development, không phải holdout
độc lập hoặc phản hồi người dùng thực tế. PDF/context đã sinh lại ngày 15/10/2026
cho **NGUYỄN MINH AN / Công ty An Thịnh**. Kết quả runtime trước khi đổi nguồn
không tự chứng minh chất lượng OCR của PDF mới; cần chạy lại LIVE để nghiệm thu.

| Case / folder | Chi phí | Ứng thực nhận trong context | Mục tiêu sau khi admission được triển khai |
| --- | ---: | ---: | --- |
| `f01-cong-tac-thu-lai-tien-thua` | 3.240.000 đ | 4.000.000 đ | Thu lại 760.000 đ |
| `f02-cong-tac-cong-ty-chi-them` | 5.400.000 đ | 5.000.000 đ | Chi thêm 400.000 đ |
| `f03-cong-tac-can-bang` | 4.320.000 đ | 4.320.000 đ | Cân bằng, không instruction số 0 |

**Scope update 15/10/2026:** F01–F03 đều được giữ trong mẫu (denominator vẫn 3)
vì chúng kiểm các kết quả thu 760.000 đ, chi 400.000 đ và cân bằng, không chỉ
kiểm ngân sách. B đã bỏ khỏi organization contexts và preconditions; các giá trị
T/E/A/P/R/S, route và instructions trong business gold không đổi. Đây là cập nhật
precondition theo quyết định ADR0009, không phải đổi oracle để làm test xanh.

## Quy ước căn cứ chi phí nhân viên (chốt 14/10/2026)

Trong policy demo, **hóa đơn hợp lệ, gắn đúng nhân viên và hồ sơ, được chấp nhận làm
căn cứ khoản chi nhân viên đã thanh toán** — không cần giấy xác nhận thanh toán riêng
và không cần câu xác nhận dài trên giấy quyết toán. Đây là giả định nghiệp vụ cho demo,
**không** phải xác minh ngân hàng; hệ thống không tạo giao dịch ngân hàng giả. Mức căn
cứ hiển thị là `EMPLOYEE_PAID_INVOICE` (policy demo), không gọi là “đã xác minh ngân
hàng”. Hóa đơn ghi “Họ tên người mua” (natural person) là khóa gắn với nhân viên; bên
mua là công ty **không** được coi là công ty trả trực tiếp. Khoản ứng thực nhận vẫn cần
bản ghi riêng của công ty (đã duyệt ứng không tự thành đã nhận).

## File nào dùng để làm gì

Mỗi folder có:

- `input/01-giay-quyet-toan.pdf`: giấy kê chi phí, thời gian/nơi/mục đích công tác,
  khoản ứng theo khai báo và số đề nghị chi/thu. Số in trên giấy chưa là actual money.
  Bỏ dòng “Tài liệu kèm theo” và câu tự xác nhận đã thanh toán.
- `input/02-hoa-don-dich-vu.pdf`: dịch vụ/giá trị/thuế/định danh invoice, **Họ tên
  người mua**. Dòng “Chuyển khoản” không tự chứng minh payer hoặc giao dịch hoàn tất.
- **F01 chỉ**: `input/03-bien-nhan-chuyen-khoan.pdf` và
  `input/04-phieu-chi-tien-mat.pdf` là **hai lựa chọn thay thế** cho CÙNG khoản ứng
  4.000.000 đ (chuyển khoản vs tiền mặt). Dùng đúng một tài liệu cho mỗi lần test;
  không nạp cả hai (4 triệu + 4 triệu = 8 triệu là sai). Kế toán ghi nhận A=4.000.000
  từ tài liệu đã kiểm tra; upload chưa tự thành received.
- `input/organization.json`: context synthetic cho **server/test harness**: hoạt động
  được phép, grants 8/4/20, ledger một khoản ứng đã nhận, coverage đầu kỳ
  bằng 0 và P/R chưa phát sinh đến `financial_as_of`. Không upload JSON này như PDF;
  không cho frontend tùy ý ghi `CONFIRMED` vào actual money.
- F01 có `input/organization-cash.json` cho nhánh tiền mặt; `organization.json`
  là nhánh chuyển khoản. Chọn đúng một context và chứng từ tương ứng; mỗi context
  có đúng một khoản ứng 4 triệu. Namespace/mã giao dịch và bên chi khớp tài liệu.
- `input/submission.json`: khai báo nhân viên theo schema hiện có.
- `input/employee-confirmation.json`: lời xác nhận Q32 có actor/scope/ref/digest (giữ
  để tương thích; đường mặc định của demo là căn cứ hóa đơn, không bắt buộc claim).
  Actor phải đối chiếu server session; ref `file:...` phải được đổi sang SourceRef đã
  upload cùng digest. API hiện tại chưa tự nạp file này, và model không có quyền xác
  nhận nó thay nhân viên.
- `gold/expected-evidence.json`: field/type/role/link/amount phải đọc được, viết riêng
  để chấm. Không bịa confidence hay OCR block id; cần capture thật cho replay.
- `gold/expected-business.json`: oracle có điều kiện cho route/state/E/A/P/R/S,
  instruction và trạng thái sau thực hiện. **Chỉ bộ chấm đọc**, không runtime/model.
  F01 có thêm `advance_basis_branches` mô tả hai nhánh thay thế.
- `provenance.json`: nguồn Hoangha gốc, hash và những thay đổi story. F01 chuyển
  tiếp khách thành bữa ăn trong công tác; F02 thay máy in bằng lưu trú; F03 giữ lưu trú.

Các trạng thái `CONFIRMED` trong organization chỉ là **trusted simulated organization
fixture**, không là proof ngân hàng thật. `employee_paid_basis` phải được view hiển thị
là căn cứ theo policy demo (hóa đơn gắn đúng nhân viên), không “đã xác minh ngân hàng”.

**Mốc thời gian:** snapshot/gold ban đầu được chốt tại 10/10/2026 18:00 +07:00.
Harness phải kiểm trên mốc này với clock đã kiểm soát. Nếu test UI ở ngày hiện tại,
kế toán phải refresh coverage/confirmation đến mốc quyết định thực tế có trách nhiệm;
không tự kéo dài witness cũ hoặc bỏ kiểm thời gian để nhận route AUTO. Post-execution
gold giả định event mới và coverage/as_of được cập nhật hợp lệ, không phải zero-history
cũ vẫn có hiệu lực sau một giao dịch mới.

## Sinh lại PDF/context

Tại repo root, Python được pin bằng uv và font NotoSans có sẵn trong `assets/fonts`:

```bash
rtk proxy uv run --no-sync python scripts/sinh_uc03_pilot.py
rtk proxy uv run --no-sync pytest tests/unit/test_uc03_pilot_data.py
```

Clone sạch thì chạy `rtk proxy uv sync` trước lệnh `--no-sync`. Script không tải model,
không dùng font Windows, không đọc/ghi gold. Nó từ chối thư mục non-empty không có
managed marker; không xóa directory tree, không follow symlink manifest/input.
Generator sinh lại 8 PDF và các JSON input/manifest; không đọc/ghi gold. Các số tiền
trong business gold không đổi. Evidence gold và provenance đã cập nhật danh tính
theo nguồn mới trong lượt đổi tên, ngoài generator.

## Checklist test

- [x] 6 PDF một trang, glyph tiếng Việt, số học invoice và layout kiểm tra.
- [x] Context/submission/confirmation parse được theo các DTO đầu vào hiện tại.
- [x] Gold tách khỏi generator/runtime; sửa gold không làm thay đổi input bytes.
- [x] Có provenance và hash nguồn gốc; bộ Hoangha không bị ghi đè.
- [ ] Import **đủ** ledger/coverage/policies và employee confirmation qua đường đã validate.
  Importer hiện tại còn bỏ các phần này; parse DTO không có nghĩa đã persist đúng.
- [ ] OCR mọi nguồn, kể cả PDF có text layer; kiểm refs/word confidence thật.
- [ ] Sau submit/xác nhận, F01 tạo COLLECT760.000; F02 PAY400.000; F03 balanced0.
- [ ] F01/F02 ghi tiền hoàn tất đúng instruction, payer/payee/scope/refs. Nâng coverage
  và `as_of` có trách nhiệm khi thêm event; không giữ zero P/R của snapshot cũ.
- [ ] Stop/Resume, stale basis, duplicate command và không phát yêu cầu lần hai.
- [ ] Đánh giá thêm FACT/POLICY/AUTHORITY và Core4/Escalation5 ở bước mở rộng.

Không sửa DB hoặc bỏ guard finance để nhận đáp án mong muốn. Xem
[plan admission](../../../docs/superpowers/plans/2026-10-14-evidence-finance-admission.md).

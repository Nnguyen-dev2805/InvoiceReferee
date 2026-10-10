# Hai bộ hồ sơ mẫu — một chuyến công tác

Ngày chốt: 10/10/2026. Ví dụ nghiệp vụ synthetic để thống nhất dữ liệu, workflow,
UI và kết quả mong đợi. Không phải hồ sơ thật, luật/thuế, policy đang chạy,
dataset đã freeze hoặc kết quả pipeline đã kiểm chứng. Các sự kiện sau ngày chốt
là diễn biến giả lập. Không tạo chữ ký hoặc giao dịch ngân hàng thật.

Đọc cùng [Product](PRODUCT.md), [Rulebook](RULEBOOK.md) R1–R10 và
[Evaluation](EVALUATION.md) E1–E2. Tài liệu này minh họa các hợp đồng hiện hành,
không thay chúng hoặc mở rộng sang mua hàng/nhận hàng.

## 1. Bối cảnh chung

| Thuộc tính | Giá trị mẫu |
| --- | --- |
| Doanh nghiệp | Công ty Demo InvoiceReferee |
| Nhân viên | Nguyễn An — `NV-DEMO-01`, bộ phận Kinh doanh |
| Kế toán | Trần Bình — `ACC-DEMO-01` |
| Người có quyền duyệt | Lê Chi — `APR-DEMO-01` |
| Công việc | Làm việc với khách hàng tại Hà Nội, 12–13/10/2026 |
| Mục đích | Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án |
| Phạm vi | Chuyến đi này; vé, khách sạn, di chuyển và bữa ăn làm việc |
| Khóa công việc | `WORK-DEMO-01`, hệ thống cấp; không bắt nhân viên tự đặt mã |
| Đơn vị tiền | VND; số tiền tính bằng số nguyên |
| Hồ sơ trước chuyến đi | `HS-TU-01` — B3, đề nghị mới |
| Hồ sơ sau chuyến đi | `HS-QT-01` — B7, cùng người và công việc |

Tên/mã người là dữ liệu được chuẩn bị sẵn cho demo, không chứng minh danh tính
đã xác thực. Mã hồ sơ tạm ứng và quyết toán riêng; khóa công việc dùng chung.
Một công việc có thể có nhiều lần đề nghị; ví dụ này chỉ có một lần ứng.

### Dự toán mẫu

| Khoản | Dự kiến công ty trả trực tiếp | Dự kiến nhân viên thanh toán |
| --- | ---: | ---: |
| Vé máy bay | 3.000.000 | 0 |
| Khách sạn | 0 | 3.000.000 |
| Di chuyển tại nơi công tác | 0 | 1.000.000 |
| Bữa ăn làm việc | 0 | 1.000.000 |
| Tổng | 3.000.000 | 5.000.000 |

Tổng dự toán 8.000.000; xin ứng 2.000.000. Phần còn lại nhân viên dự kiến tự bù.
Đây không phải trần theo loại chi phí hoặc bằng chứng người thực trả.

### Nguồn quyền mẫu `Q01`

Nguồn do doanh nghiệp demo cấp, có actor, phạm vi `NV-DEMO-01/WORK-DEMO-01`,
hiệu lực 10–17/10/2026 và không có điều kiện bổ sung chưa xác định. Cho phép
`APR-DEMO-01` quyết định công việc, ngân sách tổng tối đa 8.000.000, ứng tối đa
2.000.000, chấp nhận chi phí phía nhân viên tối đa 5.000.000 và quyết toán
chi/thu tối đa 3.000.000. Tổng chi phí công việc được xét trong ngân sách tổng.

Đây là quyền được cấp, chưa phải các quyết định sử dụng quyền. Các số trên chỉ
thuộc ví dụ này, không tự kích hoạt hoặc trở thành default toàn ứng dụng.
Kế toán rà soát và thực hiện/đối chiếu tiền; không tự có quyền duyệt tài chính.

## 2. Bộ một — xin tạm ứng trước chuyến đi

### 2.1. Điểm bắt đầu và phần nhân viên làm

Đề nghị gửi ngày 10/10/2026 lúc 09:00 +07. Tiền đối chiếu đến mốc này; snapshot
thông tin cũng tại mốc này. Đây là mốc test, không phải hai ô kỹ thuật bắt
nhân viên nhập trong giao diện nghiệp vụ.

Nhân viên chọn công việc, xem thông tin cá nhân, khai lý do, số xin ứng,
dự toán phần mình và phần công ty dự kiến trả. Đề nghị ghi thời hạn xử lý
ứng 16/10/2026, dự kiến nộp quyết toán 14/10/2026. Hai thời hạn có ý nghĩa riêng,
không coi thời hạn trên giấy, mốc tiền và thời điểm thông tin là cùng một trường.
Đây là các mốc khai báo của ví dụ, chưa phải quy định pháp luật hoặc policy hạn chung.

Form là đường chính. Nếu nhập ảnh/PDF giấy đề nghị, AI chuẩn bị bản nháp;
nhân viên xác nhận rồi gửi. Không bắt nhập lại mọi dữ liệu đã đọc rõ. Upload
không tự gửi xét duyệt. Thông tin giấy khác form phải giữ cả hai và làm rõ.

### 2.2. Bộ nguồn cần có

Các mã nguồn dưới đây là tham chiếu nghiệp vụ. PDF và ảnh tương ứng đã được
tạo trong bộ synthetic v1 ở mục 6; không coi tên mã này là source ID do API cấp.

| Nguồn | Ai chuẩn bị/cung cấp | Nội dung phải hiện diện | Có thể làm căn cứ cho |
| --- | --- | --- | --- |
| `U01` Đề nghị | Nhân viên; form hoặc giấy nhập | Người/công việc, xin 2.000.000, lý do, thời hạn, phiên bản đề nghị | Ý định xin ứng; không chứng minh duyệt hoặc nhận |
| `U02` Dự toán | Nhân viên; được người có quyền xem xét | Bốn khoản ở bảng dự toán, phần company/employee, tổng 8.000.000 | Nhu cầu dự kiến; không chứng minh chi thực tế |
| `U03` Căn cứ công việc | Doanh nghiệp/người có quyền | Quyết định cho phép chuyến đi đúng người, ngày, mục đích và scope; còn hiệu lực | Công việc đã được phép; không tự là ngân sách |
| `Q01` Quyền | Doanh nghiệp demo | Actor, nội dung được quyết định, giới hạn, scope, hiệu lực | Người có thể quyết định tiếp; không là quyết định tiền |
| `U04` Lịch sử và phạm vi quan sát | Kế toán từ nguồn công ty | Phạm vi và kết quả kiểm tra mô tả dưới đây | Không có ứng/chi khác hoặc nghĩa vụ liên quan tại mốc, khi nguồn đủ |

`U04` quan sát toàn bộ nguồn demo liên quan: ngân hàng, thẻ, tiền mặt, sổ ứng,
quyết định, lệnh chi và attempts, cho đúng người/công việc từ 01/10 đến
10/10/2026 09:00 +07. Không thiếu nguồn/khoảng; chủ sở hữu có khả năng quan sát.
Kết quả: chưa có ứng thực nhận, hoàn ứng, hoàn trả chi phí, công ty trả trực tiếp,
quyết định ứng/ngân sách cũ, lệnh đang chờ hoặc nghĩa vụ chưa giải quyết.
Đề nghị hiện tại không được tính là khoản tiền đã phát sinh.

Kế toán đưa được thông tin này trong demo; không giả nhân viên nhìn thấy
toàn bộ công ty hoặc CSV trống tự chứng minh lịch sử bằng 0. Chưa có nguồn đủ
thì giữ unknown và hỏi kế toán. Không cần nối ERP/ngân hàng thật cho bộ mẫu.

### 2.3. Kết quả mong đợi khi kiểm tra B3

- Xác định đề nghị 2.000.000, dự toán employee 5.000.000, company 3.000.000,
  tổng dự toán 8.000.000; công việc đã được phép và người có quyền quyết định.
- Lịch sử đủ phạm vi xác định chưa có khoản ứng/thanh toán hoặc pending liên quan.
- Đủ căn cứ để hoàn tất báo cáo kiểm tra và chuyển rà soát/ra quyết định.
- Ngân sách 8.000.000 và ứng 2.000.000 đang được đề nghị, chưa được duyệt.
  Không coi thiếu chính các quyết định đang xin là lỗi hồ sơ.
- Không đòi hóa đơn hậu kiểm, không giả E thực tế, không tính S quyết toán.
- Báo cáo đủ căn cứ không tạo tiền thực nhận, không đóng quyết toán và không
  tự tạo đối tượng chi/thu của stage B hoặc chuyển tiền ngân hàng.

### 2.4. Diễn biến sau báo cáo — chưa thuộc input đầu của B3

1. Kế toán rà soát báo cáo, nguồn và số dự kiến.
2. `APR-DEMO-01` quyết định ngân sách tổng 8.000.000 và ứng 2.000.000,
   đúng scope/quyền/phiên bản và có lý do/basis; lưu quyết định `D01`.
3. Con người chi ứng. Giao nhận tiền mặt synthetic `M01` ngày 10/10 lúc
   15:00 +07 ghi công ty giao, nhân viên nhận đủ 2.000.000, ref quyết định,
   người/công việc, phương thức, thời gian và căn cứ xác nhận giao/nhận.
4. Kế toán đối chiếu actual receipt. Chỉ lúc này A = 2.000.000;
   khoản ứng còn chờ quyết toán sau công việc.

`D01` và `M01` được tạo ở đúng bước; không đưa ngược vào input ban đầu để giúp
B3 trả lời. `M01` phải thể hiện giao/nhận thực tế, không chỉ phiếu chi đã duyệt.

## 3. Bộ hai — quyết toán sau cùng chuyến đi

### 3.1. Điểm bắt đầu và phần nhân viên làm

Nhân viên gửi ngày 14/10/2026 lúc 10:00 +07, sau công việc. Tiền và snapshot
thông tin đối chiếu tới mốc này. Bộ mẫu giả định mọi tài liệu cần thiết đã
đến hệ thống trước mốc; không có nguồn đến muộn hoặc bị che số.

Nhân viên chọn cùng công việc, lập bảng kê phần mình thanh toán và bổ sung
chứng từ. Không tự nhập số đã nhận ứng thay nguồn tiền; có thể khai một khoản
bên ngoài để kế toán đối chiếu. Không nộp lại căn cứ chung đã giữ được nguồn.

### 3.2. Chi phí thực tế mẫu

| Khoản | Chi phí công việc | Người thực trả | Chứng từ và quan hệ cần xác định |
| --- | ---: | --- | --- |
| Vé máy bay đi/về công tác | 3.000.000 | Công ty | Vé/hóa đơn `V01`; nguồn công ty trả `V02`; cùng booking/chuyến đi, đúng phần |
| Khách sạn cho chuyến đi | 3.000.000 | Nhân viên | Hóa đơn `K01`; biên nhận thanh toán `K02`; cùng hóa đơn/lưu trú |
| Di chuyển tại nơi công tác | 1.000.000 | Nhân viên | Chứng từ `X01`; biên nhận `X02`; ngày/tuyến và ref giao dịch liên quan |
| Bữa ăn làm việc | 1.000.000 | Nhân viên | Chứng từ `A01`; biên nhận `A02`; mục đích/người tham dự khi cần trong `C01` |
| Tổng | 8.000.000 | Company 3.000.000; employee 5.000.000 | Không cộng chứng từ thanh toán thành chi phí mới |

Mỗi nguồn có issuer/parties/ngày/ref/value/currency rõ, đọc được và giữ bản gốc.
Chứng từ thanh toán mô tả actual payer/payee và tiền đã giao/nhận cho đúng khoản;
ví dụ dùng named cash receipts/handover hoặc nguồn tương đương đủ semantics,
không dùng chữ Paid/checkbox PERSONAL hoặc debit đơn lẻ thay proof.
Không dựng một ngân hàng giả hay ký thay người thật; tài liệu sau này đánh dấu synthetic.

Các chi phí đều phục vụ đúng công việc, không phần cá nhân, refund, tiền cọc
chưa phân bổ hoặc tranh chấp. Hai khoản cùng 1.000.000 là giao dịch khác;
phải dùng refs/parties/context, không ghép theo số tiền đơn độc.

### 3.3. Nguồn mới và nguồn được dùng lại

| Nguồn/nhóm | Ai cung cấp hoặc chịu trách nhiệm làm rõ | Ý nghĩa |
| --- | --- | --- |
| `C01` Bảng kê và mô tả công việc | Nhân viên | Ba khoản phía nhân viên; không kê vé công ty thành khoản xin hoàn; purpose đúng scope |
| `K01/K02`, `X01/X02`, `A01/A02` | Nhân viên từ chứng từ bên cung cấp | Chi phí và payer của phần employee; giữ hóa đơn và payment riêng |
| `V01/V02` | Nguồn phía công ty, kế toán quản lý | Chi phí vé và company direct payment thực tế |
| `Q01/U03/D01` | Dùng lại nguồn quyền, công việc và quyết định đã lưu | Quyền còn hiệu lực; công việc được phép; B = 8.000.000 và ứng đã được duyệt |
| `M01` | Dùng lại nguồn giao/nhận, kế toán đối chiếu | A = 2.000.000 thực nhận, không phải chỉ approval |
| `C02` Lịch sử và coverage cập nhật | Kế toán từ nguồn công ty | Bao phủ tới 14/10 10:00: chỉ có ứng `M01` và company direct `V02`; không return/reimbursement/reversal, pending, payment khác hoặc incident |

`C02` có phạm vi/methods/owner đầy đủ như `U04`, kéo dài tới mốc mới và không
thiếu khoảng. Nó cùng nguồn thực tế chứng minh RA = P = RP = 0. Không suy ba
số 0 này từ việc nhân viên không đính kèm chứng từ hoàn/chi thêm.

Nguồn cũ giữ provenance/phiên bản. Giấy duyệt ngân sách dùng lại khi còn valid;
không duyệt lại chỉ vì hồ sơ B7 mới. Coverage cũ đến 10/10 không đủ cho 14/10.
Tài liệu đã dùng ở bộ một có thể được tham chiếu trong bộ hai, không đếm thành
khoản ứng hoặc nghĩa vụ mới.

### 3.4. Kết quả mong đợi khi kiểm tra B7

| Thành phần | Giá trị VND | Căn cứ nghiệp vụ |
| --- | ---: | --- |
| B — ngân sách được duyệt | 8.000.000 | `D01`, đúng scope/quyền và còn hiệu lực |
| T — tổng chi phí công việc | 8.000.000 | Company direct 3.000.000 + employee 5.000.000 |
| E — employee-paid work cost đủ điều kiện theo rule | 5.000.000 | Ba khoản phía nhân viên, purpose/payer/amount/links đủ |
| A — ứng thực nhận | 2.000.000 | `M01` |
| RA/P/RP | 0/0/0 | `C02` và nguồn tiền trong phạm vi đầy đủ |
| S — kết quả đối chiếu đề xuất | +3.000.000 | E − (A − RA) − (P − RP) |

Các khoản đã đủ căn cứ eligibility theo rule cho báo cáo; không gọi E là
quyết định phê duyệt tài chính mới đã xảy ra. T = B vẫn cần kiểm tra các phần
khác; không tự chấp nhận chỉ vì không vượt ngân sách. Vé company-paid đã không
nằm trong E nên không trừ thêm 3.000.000 khỏi S.

Kết quả là báo cáo đủ căn cứ đề xuất công ty trả thêm 3.000.000; có đường quyền
hợp lệ cho E trước offset và số tiền chi/thu. Mọi số và quan hệ mở được nguồn.
Chưa có quyết định quyết toán mới, chưa có receipt 3.000.000 và chưa được đóng.

### 3.5. Diễn biến sau báo cáo — follow-up riêng

1. Kế toán rà soát bảng đối chiếu và nguồn; record review không là financial approval.
2. `APR-DEMO-01` chấp nhận khoản chi trong phạm vi và duyệt kết quả công ty trả
   thêm 3.000.000; lưu quyết định `D02` với current report/basis/quyền/time/version.
3. Con người thực hiện chi. Named cash handover synthetic `M02` ngày
   14/10/2026 15:00 +07 chứng minh employee nhận đủ 3.000.000 đúng quyết định.
4. Cập nhật coverage `C03` đến mốc receipt, có `M02`, không có pending/incident
   hoặc nguồn mới mâu thuẫn; đối chiếu lại actual và validity theo gates.
5. E = 5.000.000; A = 2.000.000; P = 3.000.000; RA = RP = 0 ⇒ S = 0.
   Correct fulfillment giảm remaining, không tự hủy quyết định gốc hoặc yêu cầu
   duyệt lại cùng khoản. Không chi thêm lần nữa.
6. Chỉ đóng khi đủ basis/quyền/coverage, không unresolved obligations,
   pending/incident/Stop/stale và mọi điều kiện đóng khác của Rulebook R10.

`D02/M02/C03` là follow-up, không có trong input B7 ban đầu. Tại mốc trước
receipt S = +3.000.000 vẫn được giữ; sau receipt có snapshot S = 0, không
ghi đè lịch sử cũ. Không tạo money event 0 để biểu thị cân bằng.

## 4. Cách xem và hành động cho ba vai

| Vai | Bộ trước công việc | Bộ sau công việc |
| --- | --- | --- |
| Nhân viên | Xem đề nghị/dự toán, xác nhận bản nhập, gửi và trả lời phần thuộc mình | Nộp bảng kê/chứng từ; hiểu khoản được xét, vướng mắc và số tiền cần nhận/hoàn |
| Kế toán | Rà soát nguồn, lịch sử và kết quả; trình người có quyền; đối chiếu tiền chi ứng | Rà soát amounts/links/payer/history; trình quyết toán; thực hiện và đối chiếu tiền |
| Người duyệt | Quyết định ngân sách và ứng trong quyền; có thể trả lại/từ chối với lý do | Quyết định chấp nhận chi phí và số chi/thu; thấy basis, giới hạn và vấn đề còn tồn |

Form/native và nhập giấy hội tụ cùng dữ liệu và checks; không có hai bộ quy tắc.
Nguồn ngoài đã được duyệt/chi phải nhập đúng trạng thái sau xác minh; không biến
nó thành yêu cầu chi mới. Không lấy các ngưỡng 5/20/200 triệu hoặc yêu cầu hóa
đơn năm 2017 của trường làm policy demo. Không bắt chứng từ nhận hàng/PO cho công tác.

## 5. Điều phải kiểm chứng khi chuyển thành bộ test

- Trước hết tạo retained source files thật của các mã nguồn; nội dung số/ngày/refs
  phải thống nhất. Native form và ảnh/PDF khác mẫu trình bày dùng cùng ý nghĩa
  nghiệp vụ. Hai bản của cùng đề nghị không thành hai khoản hoặc nghĩa vụ.
- Tách `input`, `expected` và `followup`; file expected/ghi chú tác giả/tên nhãn
  routine không được vào OCR/LLM input. Tài liệu này không được đưa nguyên vào prompt.
- Gold định nghĩa critical facts, unknown/zero, nguồn/locator, quan hệ, checks,
  câu hỏi/owner, số tiền và hành động được phép/cấm; đối chiếu độc lập trước freeze.
- B3 initial không yêu cầu invoice hoặc các approvals đang xin; B7 initial S =
  +3.000.000, sau actual follow-up S = 0; quyền, actions và closure cũng phải đúng.
- Biến thể bắt buộc: actual advance chưa rõ; nguồn công ty trả vé mâu thuẫn với
  lời khai; ảnh số tiền không đọc được; thiếu coverage mới; sửa request sau duyệt;
  nộp cùng giấy hai lần. Giữ unknown/issues và owner đúng, không sửa gold theo output.
- Thêm biến thể chi phí employee 1.000.000 với A = 2.000.000, company direct
  vẫn 3.000.000 và các sources/scope tương ứng đầy đủ: T = 4.000.000; S =
  −1.000.000. Sau decision và công ty thực nhận return 1.000.000: RA = 1.000.000,
  S = 0; tiền nhân viên khai đã gửi nhưng company chưa nhận chưa được coi fulfilled.
- Đo công sức nhân viên chuẩn bị/sửa/bổ sung, kế toán tìm/ghép/rà soát, người duyệt
  hiểu/ra quyết định và chi/thu thực tế. Không chỉ đo thời gian gọi AI.

Hai bộ happy-path cùng chuyến đi là ví dụ walkthrough và input cho thiết kế UI,
không đủ chứng minh chất lượng hệ thống. Đã tạo tài liệu synthetic ở mục 6;
chưa chạy pipeline, chưa có gold độc lập hoặc trial người làm nghiệp vụ thật.

## 6. Tài liệu synthetic đã tạo

- [Hướng dẫn và cấu trúc bộ mẫu](../../data/settlement/worked-example-v1/README.md).
- [B3 PDF có chữ](../../output/pdf/settlement-worked-example-v1/B3-native.pdf)
  và [B3 PDF ảnh](../../output/pdf/settlement-worked-example-v1/B3-scan.pdf): 5 trang.
- [B7 PDF có chữ](../../output/pdf/settlement-worked-example-v1/B7-native.pdf)
  và [B7 PDF ảnh](../../output/pdf/settlement-worked-example-v1/B7-scan.pdf): 14 trang.
- [Toàn bộ bộ mẫu ZIP](../../data/settlement/worked-example-v1.zip), gồm
  20 nguồn PDF/PNG, thông tin form, manifest và expected/follow-up tách riêng.
- [Kết quả kiểm tra artifact](../../data/settlement/worked-example-v1/verification.json).

Hai dạng PDF là cùng dữ liệu, chỉ chọn một dạng cho mỗi lần upload; PDF ảnh là
raster từ PDF có chữ, chưa phải ảnh chụp thật. B7 bundle có bản nguồn cũ để test
đối chiếu độc lập, không chứng minh app tự tái sử dụng nguồn hoặc link hai case.
Quyền trên nguồn synthetic không tự kích hoạt quyền demo runtime. Không upload
expected, README hoặc quyết định/receipt follow-up vào lần chạy initial.

# AI tạo bản nháp hoàn ứng từ folder sự kiện — happy case

**Ngày:** 17/10/2026. **Trạng thái:** phạm vi happy case được người dùng đồng ý;
thiết kế kỹ thuật dưới đây là đề xuất của người lập plan, chưa triển khai.
**Companion:** [Implementation plan](../plans/2026-10-17-event-expense-draft.md).

## 1. Mục tiêu và quyết định đã chốt

Manager nhận một khoản tạm ứng chung cho sự kiện. Manager tải folder chứng từ;
AI đọc và soạn đơn hoàn ứng đứng tên manager, kèm report chi tiết. Con người kiểm
tra và sửa trước khi hoàn thiện bản nháp.

- Một folder tương ứng một sự kiện; nhiều folder tạo nhiều bản nháp độc lập.
- Mỗi file đại diện một chứng từ/một giao dịch, tương ứng một dòng report.
- Từng dòng có tên người chi trả; manager có thể chọn nhiều dòng để gán cùng người.
- AI có thể gợi ý người trả từ chứng từ, có căn cứ; manager xác nhận/gán tên.
- Manager khai số tiền đã nhận ứng; chương trình cộng chi phí và tính chênh lệch dự kiến.
- Lượt đầu làm happy case: chứng từ rõ, các giao dịch khác nhau và cùng sự kiện.

**Không suy diễn:** manager đứng tên không có nghĩa manager đã tự trả mọi khoản.
Gán tên người chi trả là kê khai; chưa phải xác minh danh tính/quyền hay tiền thực nhận.

## 2. Giới hạn phiên bản này

Chỉ tạo, lưu, mở lại và chỉnh sửa bản nháp trên web. Đầu ra gồm thông tin đơn,
bảng chi tiết và tổng hợp; không cần mẫu PDF pháp lý hoặc tính năng xuất file mới.
Nếu người dùng cần PDF/XLSX, đó là hạng mục tiếp theo cần chốt mẫu.

Không triển khai: công nợ giữa manager và nhân viên; phân phối tiền ứng; chuyển
tiền; xác nhận A/P/R; phê duyệt chi phí; gửi kế toán; tự submit bản nháp thành hồ sơ
quyết toán; xét ngoại lệ/thuế/hạn mức mới; folder tự gom thành cùng một sự kiện;
ZIP; tự chia một file thành nhiều giao dịch; nhiều người sửa cùng bản nháp.

Manager là vai trò nghiệp vụ của người đứng đơn, **không thêm persona thứ tư**.
Phiên bản này dùng workspace người nộp hiện có; server session sở hữu bản nháp.
Nhân viên được ghi tên trong report không tự được cấp quyền truy cập. Người nộp
có thể cùng con người khác kiểm tra tại workspace của mình; luồng giao việc giữa
các tài khoản là ngoài phạm vi.

## 3. Luồng và nội dung đầu ra

1. Người nộp chọn **Tạo nháp từ folder**, nhập tên sự kiện, tên manager đứng đơn
   và tiền ứng kê khai. Tên manager mặc định từ session, có thể sửa nhãn trên đơn;
   người thực hiện thao tác luôn là actor thật của session.
2. Chọn một folder qua browser directory input; có nút chọn nhiều file thay thế.
   Một lần chọn tương ứng một draft, kể cả có thư mục con. Đường dẫn chỉ là nhãn,
   không dùng làm storage key hoặc căn cứ gán người trả.
3. Lưu các file vào draft trước khi đọc. Nhận PDF/PNG/JPEG, tối đa **10 file**,
   **20 MiB/file**, **50 MiB/lần tải**. Đây là giới hạn pilot do người lập plan chọn,
   không phải hiệu năng đã đo. Media kiểm từ bytes, không chỉ extension/MIME client.
4. Nút **Đọc và tạo nháp** chạy OCR + trích xuất theo vai trò evidence hiện có.
   Không yêu cầu giấy hoàn ứng đầu vào, không gọi classifier riêng để tìm giấy.
5. Report giữ đúng một dòng cho mỗi file, kể cả chưa đọc được. Mỗi dòng có:
   file gốc; ngày giao dịch; nội dung; số chứng từ nếu có; số tiền giao dịch VND;
   tên người chi trả; trạng thái đọc; vấn đề cần kiểm tra.
6. Manager xem nguồn gốc, sửa trường, gán người chi trả theo nhóm và lưu. Giữ
   riêng giá trị OCR, refs và giá trị sửa; không sửa ngược quote/artifact nguồn.
7. **Hoàn thiện bản nháp** chỉ khả dụng khi các dòng đủ ngày/nội dung/số tiền/
   người chi trả, không còn lỗi trọng yếu và người nộp đã kiểm tra từng dòng.
   Thành công hiển thị **Bản nháp đã kiểm tra**, không phải hồ sơ được duyệt.
8. Lưu và mở lại giữ toàn bộ dòng, sửa đổi, nguồn, phiên bản và tổng dự kiến.

Report gồm header tên sự kiện/manager/tiền ứng kê khai, bảng chi tiết và footer:
**Tổng chi phí kê khai**; **Ứng manager kê khai**; **Chênh lệch dự kiến**.
Ví dụ 3 file: 1.080.000 + 2.160.000 + 960.000 = 4.200.000 đ;
ứng kê khai 5.000.000 đ ⇒ **Dự kiến hoàn lại 800.000 đ**.

## 4. Tính tiền và độ tin cậy tối thiểu

- Mọi số tiền là strict integer VND, không bool/float/âm; số ứng có thể bằng0.
  Tính bằng code: `draft_delta = declared_total - declared_advance`.
  Delta<0 dự kiến hoàn lại; >0 dự kiến đề nghị trả thêm; =0 dự kiến cân bằng.
  Đây **không phải S hoặc E/A của reconciler**, không dùng nhãn đủ điều kiện.
- Amount lấy tổng giao dịch có nguồn theo schema từng loại, không cộng dòng hàng
  và tổng nguồn hai lần; không lấy số dư tài khoản thay số tiền chuyển khoản.
  Khi có hai tổng cạnh tranh, để cần kiểm tra thay vì chọn số cho cân bằng.
- Tổng chính thức của bản nháp và delta là `null` khi còn dòng chưa biết số tiền,
  đọc lỗi, sai số học trọng yếu hoặc nghi trùng chưa giải quyết. Có thể hiển thị
  **Tạm cộng các dòng đã đọc** kèm N/M; không trình bày như tổng đầy đủ.
- File giống digest trong draft giữ hai dòng upload, dòng sau báo trùng và không
  tính thêm; chưa hoàn thiện tới khi người dùng xác nhận bỏ bản trùng khỏi tổng.
  V1 chỉ cam kết phát hiện trùng bytes, không tuyên bố phát hiện mọi giao dịch
  trùng ở ảnh/PDF khác bytes. Cùng filename khác digest vẫn là hai nguồn riêng.
- Chứng từ không phải khoản chi phát sinh (báo giá/hợp đồng/chuyển khoản ứng/giấy
  hoàn tiền…) không tự biến thành chi phí chỉ vì có số tiền. Giữ dòng cần kiểm
  tra và dừng hoàn thiện; không xây nhánh xử lý đầy đủ cho loại này trong happy case.
- Nếu file thực tế chứa nhiều giao dịch, không tùy tiện ép thành một tổng đã tin cậy;
  khi phát hiện được, đánh dấu ngoài quy ước đầu vào và yêu cầu thay file.
- Nguồn OCR không đầy đủ hoặc hết budget vẫn giữ mọi file/dòng, báo rõ phần chưa
  đọc. Không đặt0, không báo đọc thành công hoặc hoàn thiện giả.
- Tên người mua/khách/người nhận chưa tự thành người trả. Gợi ý OCR giữ refs;
  manager gán tên được lưu `MANAGER_DECLARATION`, không `VERIFIED`.
- Chỉnh tay số tiền có vấn đề chỉ tạo correction có actor/time/reason; artifact
  gốc còn nguyên. Mâu thuẫn số học trọng yếu cần thay nguồn, không một checkbox để
  coi chứng từ sai đã đúng. Các trường chỉ thiếu/không đọc được có thể bổ sung tay
  và ghi rõ nguồn kê khai, vẫn chỉ là bản nháp.

### Quy tắc sửa và xác nhận sau builder-check

Đây là lựa chọn V1 của người lập plan để giữ happy case đơn giản:

- `MISSING_FIELD`/`UNREADABLE_FIELD` của một nguồn đã đọc đủ: bổ sung tay đúng kiểu
  có actor/time/reason gỡ thiếu trường cho **bản nháp**. Amount được cộng sau bổ
  sung; payer có thể được gán nhóm. Không biến correction thành OCR/verified fact.
- `READ_ERROR`/`INCOMPLETE_COVERAGE`/`BUDGET_EXHAUSTED` và
  `ARITHMETIC_CONFLICT`: sửa amount không gỡ blocker. Tổng đầy đủ/delta vẫn null;
  phải đọc lại thành công hoặc tạo draft mới với nguồn đúng. V1 chưa hỗ trợ sửa
  mọi component thuế/số lượng để phân biệt tự động OCR sai và chứng từ sai;
  trường hợp OCR gây conflict giả có thể vẫn bị chặn, cần ghi rõ hạn chế này.
- Mỗi dòng có `reviewed_basis_hash`; trạng thái toàn đơn có hash header + toàn bộ
  dòng/nguồn/corrections đang dùng. Sửa dòng (kể cả payer/gán nhóm) làm dòng đó
  chưa kiểm tra, toàn đơn về DRAFT; đổi event/manager/advance làm toàn đơn về DRAFT.
  Đọc lại ra nội dung khác cũng vô hiệu phần xác nhận liên quan. Không được gửi
  đồng thời sửa một dòng và khai dòng ấy đã kiểm tra trong cùng patch.
- Mở lại/GET hoặc lặp đúng command cũ không làm mất xác nhận. Nhãn REVIEWED chỉ
  áp dụng nếu hash hiện tại khớp hash đã kiểm tra; không dựa riêng version số.
- V1 attach một folder một lần, sau đó nguồn immutable; không có nút thay/xóa
  nguồn trong draft. Nếu phải thay file, tạo draft mới. Lịch sử draft cũ còn nguyên;
  không mang corrections cũ sang nguồn mới. Loại bản trùng khỏi tổng không xóa file.

## 5. Kiến trúc đề xuất và phần tái sử dụng

**Quyết định kỹ thuật của người lập plan:** thêm workspace draft sự kiện độc lập,
dùng DB/session/uploads hiện có. Không dùng canonical case có unique
employee/activity để chứa nhiều người chi trả, không đưa các dòng này vào
admission/usage/ledger/instructions hiện hành. Không mở workflow quyết toán nhóm.

Tách đoạn evidence-only từ `reconciliation/digital_intake.py:read_digital_report`
thành helper chung; giữ chữ ký và kết quả S6 tương thích. Helper dùng đúng
`reader.read_source`, `review_ocr_quality`, `extract_evidence_document`,
`validate_document`, `check_document_arithmetic`, `RunBudget` và reader identity.
Digital intake và feature mới cùng gọi helper. Matching theo giấy và synthetic
paper vẫn nằm ở luồng cũ; tạo draft từ folder không yêu cầu matching với giấy chưa có.

Giữ model/provider hiện cấu hình, không thay env/model, không thêm fallback.
Một pass có một RunBudget hiện hành; OCR mỗi file, extraction theo file, confidence
review/repair có điều kiện và có ngân sách. Không cam kết số call hoặc latency cố
định; lưu counts/status, không tự nới budget để đọc đủ folder lớn.

Lưu draft/source/revision trong bảng riêng (additive migration). File gốc đặt dưới
uploads bằng ID/hash server. Mỗi lần sửa phải có expected_version và command_id;
server tính lại tổng. Read chụp source digests + reader identity; kết quả đến muộn
không được ghi đè sửa đổi mới. Reload/sửa tên người trả không tự gọi provider.
Lặp cùng lệnh đọc trả lại kết quả cũ; cùng command khác payload trả409.

V1 dùng read request async có budget hữu hạn, không xây worker/job mới. Browser
mất kết nối có thể GET lại snapshot; app restart đánh dấu lượt đang đọc là bị
gián đoạn, không tự đọc tiếp hoặc tự gọi provider. Thử lại là thao tác rõ ràng.
Tái đọc giữ corrections và kiểm tra source/reader basis; không tự thay dữ liệu
đã sửa bằng OCR mới. Nguồn đổi làm mất trạng thái đã kiểm tra của dòng liên quan.

## 6. Bằng chứng repo và giới hạn discovery

Checkpoint khảo sát: main `2730b353` (`feat: update UI/UX`), worktree sạch.
Đã đọc status, design§1–4, contracts§2/3/9/12 và global constraints của final plan.
CodeGraph queried tại repo này, tier Verify theo phạm vi feature; tool trả current
source. Không có tool list_projects/index_status/check_index_coverage được expose:
generation và coverage tổng thể **UNKNOWN**, không claim audit toàn repo.

Nguồn đã khảo sát: `workflow/service.py:save_digital_declaration/read_digital_draft`,
`reconciliation/digital_intake.py:read_digital_report`,
`evidence/extraction.py:extract_evidence_document`, `api/routes.py:settlement_draft`,
`api/app.py:create_app`, `workflow/db.py:Database`,
`frontend/src/features/digital_intake.tsx:runDigitalRead/DigitalForm`,
`frontend/src/App.tsx:App`. Graph chỉ ra callers/tests S6 và luồng read_root; các
symbol bị cắt chưa được dùng để khẳng định chi tiết toàn thân hàm. DB version12,
RunBudget12 LLM/10OCR attempts và source ceiling20MiB được đọc bổ sung từ config.

## 7. Gate nghiệm thu

1. Ba file rõ → ba dòng đúng nguồn, manager đứng đơn, nhiều người trả được giữ.
2. Gán nhóm và sửa một dòng → tổng code đúng; reload/restart giữ sửa và provenance.
3. Thiếu amount/payer, lỗi đọc, trùng hoặc budget cạn → không hoàn thiện giả.
4. Cùng tên file khác nội dung, hai folder cùng tên, hai session/tenant không
   nối nhầm hay truy cập chéo. Thử path traversal/foreign source bị chặn.
5. API đọc/sửa/hoàn thiện không tạo case, A/P/R, instructions hoặc admission facts.
6. Regression S6 không đổi kết quả/refs/calls; UI folder→review→save→reopen chạy
   browser trên DB riêng. Fixture chỉ chứng minh cơ chế; LIVE quality NOT_RUN
   tới khi có lượt được ủy quyền riêng. Không claim độ chính xác từ test giả.

**Ngoài quyền lượt lập plan:** không code sản phẩm, không provider call, không DB
người dùng/port8000/Railway; không commit/push/deploy.

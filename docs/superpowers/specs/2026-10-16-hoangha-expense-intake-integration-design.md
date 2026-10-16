# Hoangha expense intake → main — thiết kế tích hợp

Ngày16/10/2026. Trạng thái: bản thiết kế đề xuất, chưa sửa ứng dụng.

## Mục tiêu và quyết định người dùng

Lấy logic nghiệp vụ FastAPI UC03 và cách nhập của Hoangha vào main. Bao gồm bộ bằng chứng thay thế, nhiều tài liệu cho một khoản, form điện tử và đơn giấy, thêm loại hồ sơ nhân viên tự chi. Người dùng đã xác nhận: tự chi = không nhận tạm ứng, nhân viên trả trước và đề nghị công ty hoàn lại phần đủ điều kiện. Không phải phần tự bỏ thêm trong hồ sơ đã có ứng.

## Bằng chứng nguồn

Hoangha `domain/settlement.py`: SettlementType ADVANCE_SETTLEMENT/EMPLOYEE_REIMBURSEMENT, SubmissionSourceType DIGITAL_FORM/PAPER_SCAN, ExpenseItemDraft original/alternative/no-evidence cùng lý do; alternative bắt buộc loại và lý do. `app/templates/employee/new_settlement.html`, `app/static/js/settlement-form.js`: hai nhóm radio độc lập; form giấy ẩn khai dòng, form điện tử hiện context/dòng/filemapping. `app/web/routes.py:730+`: API multipart payload + giấy chính + evidence, một file không gán hai dòng ở form native. `policy/settlement.py`: alternative có file vẫn OUTSIDE_POLICY tới accountant; tự chi có khoản ứng khác0 tạo FACT.

CodeGraph Hoangha pending addedfiles, không tự sync; coverage tool không có, coverageUNKNOWN. Các đoạn nguồn liên quan được đọc trực tiếp. Ảnh FastAPI có sẵn đã xem: `.worktrees/hoangha/.runtime/hoangha-business-map-20261016/employee-digital.png`, employee-alternative.png. Đây là ảnh lượt trước, không phải browser run mới. Không provider call trong lượt thiết kế này.

## Bốn tổ hợp nhập

| Loại hồ sơ | Form điện tử | Đơn giấy |
|---|---|---|
| Quyết toán tạm ứng | Khai khoản và gắn nguồn, nối A thực nhận | OCR giấy và evidence, đối chiếu A thực nhận |
| Nhân viên tự chi | Khai khoản và gắn nguồn, khai không nhận ứng | OCR giấy đề nghị hoàn chi và evidence, khai không nhận ứng |

Không chuyển lựa chọn UI thành A0 đã xác minh một cách vô điều kiện. Kiểm dữ liệu sổ theo scope; nếu thấy A thực nhận thì hỏi đổi loại/giải quyết mâu thuẫn. Không yêu cầu upload biên nhận ứng cho tự chi. Tái dùng cơ chế kiểm sổ hồ sơ hiện có, không tạo lại form coverage bắt kế toán xác nhận dài dòng. Cách ghi nhận khai không ứng và giới hạn của dữ liệu sổ phải được chốt contract, không ngầm đồng nhất không có record với chưa từng ứng.

## Giao diện đề xuất theo Hoangha

Nhóm1: Nhân viên tự chi / Quyết toán tạm ứng. Nhóm2: Form điện tử / Đơn giấy. Nhân viên lấy từ session, không default NguyễnMinhAn.
Form điện tử: mục đích công việc; project/customer tùy chọn; thời gian theo profile thực tế; danh sách khoản có nội dung/category/ngày/số tiền/tình trạng chứng từ. Thêm/xóa dòng. Mỗi dòng có nhiều file. Alternative hiện loại tài liệu và lý do thiếu chứng từ gốc; no-evidence hiện lý do. Cân nhắc upload ngay trong dòng để mapping rõ, giữ bảng danh sách nguồn dùng chung nếu cần phân bổ. Main có hỗ trợ một hóa đơn phân bổ nhiều dòng nên không sao chép hạn chế filename một dòng của Hoangha; dùng sourceID+rowID và amount allocation.
Form giấy: đơn chính + evidence; không nhập lại các thông tin có thể OCR; cho bổ sung field còn thiếu có nguồn khai báo rõ. Giữ read→draft→submit của main ở cả hai cách nhập. Form điện tử là dữ liệu khai của nhân viên, không giả thành OCR/chứng từ độc lập. Tài liệu đính kèm vẫn qua pipeline OCR theo phạm vi main hiện hành.
Draft hiển thị tổng khai, căn cứ theo dòng, số nguồn, trạng thái liên kết/phân bổ/validity; không gộp các lớp này. Chưa nộp không phát hành tiền.

## Một khoản nhiều vai trò bằng chứng

CostLine gồm declared data + EvidenceLinks. Link giữ sourceID/type/role, chứng minh service/amount/delivery/payment gì, provenance, association và allocation độc lập. Loại tài liệu không đủ để kết luận đã chứng minh mọi claim.
TC18 parts2.7m = hóa đơn. Labor1.5m = nghiệm thu(service/completion/value) + transfer(payment). Chỉ một cost labor1.5m, không cộng thành3m. Chuyển khoản không tạo cost riêng nếu chỉ hỗ trợ cùng dịch vụ.
Nhân viên gán file là một khai báo liên kết, vẫn kiểm nội dung/mã/bên/số tiền/thời gian; không AUTO_LINK chắc chắn chỉ vì dropdown.

## FACT → POLICY → AUTHORITY

Thiếu hoặc mâu thuẫn dữ kiện trước: dịch vụ/amount/payer/payee/transactionstatus/ngày/association. Khi đủ dữ kiện mới xét alternative/noevidence theo policy. Lý do không hóa đơn không xác minh đã trả tiền. Chấp nhận policy exception không sửa facts hoặc bỏ qua chuyển khoản sai người nhận. Không bịa chữ ký; xác nhận chữ ký in không phải xác minh chữ ký số.
Alternative có file+lý do không tự equivalent invoice; đi theo nhánh exception xác định. No-evidence reason vẫn không tự xác lập service/amount/payer; FACT trước. Câu hỏi/decision giữ refs và scope, tiếp tục vòng bổ sung main.

## Hai đường nhập chung core

Digital declaration và paper extracted declaration → cùng representation khoản chi/claim, nguồn field rõ → document validation → association → allocation → factual gaps → policy → admission/finance. UI không cộng tiền theo số file. Giữ taxonomy Hoangha hiện có ở main, không suy ra nghiệp vụ PO/nhận hàng hoàn chỉnh chỉ từ loại tài liệu. Không port Streamlit inventory pipeline trong task này.

## Tự chi và tài chính

Giữ S=E−A−P+R, A0 khi căn cứ không ứng hợp lệ, P là tiền hoàn chi đã nhận. Ban đầu P/R0 đã xác lập theo sổ thì S=E. Ví dụ E1.5m,A0,P0,R0→PAY1.5m; sau kế toán ghi nhận chi thực tế1.5m→P1.5m,S0; chỉ SETTLED khi không còn blockers. Không đóng khi mới phát hành PAY. Chứng từ ứng phát sinh cùng scope phải được xử lý thay vì xóa/ignore khi chọn tự chi.
Luồng có ứng vẫn dùng A thực nhận của main. Giữ8/4/20 triệu, B ngoài phạm vi, quyền theo grants, Stop/revision/idempotency/cache. Không copy nativeauthority100m hoặc lấy giấy khai làm A thực tế.

## Lỗi Hoangha không sao chép

- Paper normalization ValueError→expense_items=[]→policy PASS.
- Digital invoice+paymentproof cộng trùng.
- Không kiểm transferpayee vs supplier.
- Identity/department hardcoded.
- Late job complete sau STOPPED.
- Chỉ summary/review nhưng coi như fulfilled/settled.

## TC18 hiện tại

Transfer payeeAnThịnh khác supplierPhúcAn; giữ FACT có nguồn để làm rõ trước ngoại lệ thiếu hóa đơn. Không sửa input/gold; không dùng nguồn không nhất quán để tự công nhận labor. Return800000 chỉ có điều kiện A5m,E4.2m,P/R0 và mọi blocker hết; không phải kết luận thực nhận từ bộ PDF.

## Cần chốt quyền ngoại lệ

Người dùng đã chốt: theo Hoangha, cấp kế toán quyền chấp nhận ngoại lệ thiếu hóa đơn/bằng chứng thay thế sau khi dữ kiện đủ, trong hạn mức cấu hình. Triển khai bằng grant EXCEPT_POLICY giới hạn đúng rule/scope/effect và actor, không nâng quyền kế toán chỉ theo labelUI; không mặc định có quyền phát hành/override/phê duyệt mọi ngoại lệ. Quyết định có lý do, refs, actor/time và đúng phiên bản. Ngoại lệ chứng từ không đóng FACT về số tiền/payer/payee/giao dịch. Chưa chốt con số hạn mức và đơn vị tính hạn mức; đề xuất riêng là tổng các khoản thay thế được chấp nhận trong cùng hồ sơ tối đa8triệu, không phải chỉ số chênh lệch cần chi/thu. Đây là đề xuất, chưa là policy được duyệt. Không tự lấy100triệu của Hoangha.

## Tiêu chí triển khai/kiểm chứng

- Bốn tổ hợp nhập, reload/restart không mất lựa chọn/rowmapping.
- Digital và paper cùng facts tương đương→cùng kết quả; provenance khác đúng bản chất.
- Nghiệmthu+payment1.5m chỉ tính1.5m; invoice+payment không nhân đôi; phân bổ nhiều dòng giữ guards.
- Alternative có/lỗi/thiếu reason; no-evidence; invalidDTO luôn fail-closed.
- TC18 payer/payee mismatch là FACT; policyexception không tự đóng FACT.
- Tựchi không phải nhập A; xungđộtA thực tế bị chặn; P0/Ppartial/Pfull và PAYfulfillment/SETTLED đúng.
- Quyền/exceptions/Stop/version/idempotency không giảm; regression TC01/TC25.
- Browser employee nhập→đọc→draft→nộp→xửlýissue→kếtoán xác nhậnchi→đóng trên DB riêng, replay trước; không tự gọiLIVE.

## Phạm vi tác động dự kiến

Main domaincommands/declaration; source/itemlink DTO và persistence; evidence draft/adapter cho digital declarations; sharedassociation/allocation/admission/policy; workflow commands/versions; intake API/React và accountant view. Cần integrator duy nhất cho sharedDTO/workflow. Chưa sửa code sản phẩm hoặc database.

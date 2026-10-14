# Prompt triển khai — chặn mâu thuẫn TC06/TC11 và bảo toàn ứng chưa biết

Hãy thực hiện sửa code trên nhánh `final`, không chỉ viết plan.

Đọc AGENTS.md, operative contracts và checkout hiện tại trước khi sửa. Một agent
đang sửa intake/draft/UI trong cùng workspace: giữ mọi thay đổi của họ, xác định
write set và serialize các file workflow/DTO/schema dùng chung. Tiếp tục trên
checkout mới, không revert về snapshot cũ. Không reset database, checkout nhánh,
commit/push hoặc sửa PDF/gold để ép kết quả PASS.

## Bằng chứng phải đọc

- `docs/final/reviews/2026-10-14-tc06-tc11-live-negative.md`.
- `.runtime/hoangha-negative-20261014-153002/`: ảnh4PDF, expectation viết trước run,
  kết quả LIVE, facts, stage logs, snapshot, probe numeric, probe tax FOUND và3RED assertions.
- Hai nguồn nguyên bản: `data/tham-khao/uc-03/tc06-chenh-lech-quyet-toan-ghi-sai/`
  và `data/tham-khao/uc-03/tc11-so-hoc-tren-hoa-don-khong-nhat-quan/`.

Snapshot test là `0b205420` cộng các bytes lưu trong evidence; kiểm tra lại code
hiện tại, không coi số dòng hoặc trạng thái cũ là hiện hành. Chỉ dùng expectation/
gold ở phía chấm, tuyệt đối không đưa vào ứng dụng/model.

## Hành vi đã fail

1. TC06: giấy ghi ứng4m, tổng chi3.24m, hoàn lại700k. Quan hệ kê khai của giấy
   cho kết quả760k, lệch60k. Hệ thống đọc rõ700k nhưng tự issue COLLECT760k, không FACT.
2. TC11: tiền hàng5m + thuế400k =5.4m, tổng in5.5m. Hệ thống công nhận E5.5m rồi
   issue COLLECT500k với actual advance fixture6m, không FACT.
3. `_value_supported(400000, 'Thuế GTGT (8%): 400.000')` trảFalse do chọn con số8
   đầu tiên. Quote chỉ400.000 lại trảTrue. Sửa riêng tax extraction không đủ:
   probe tax FOUND vẫn cho allowed_effect COLLECT500k.

## Việc cần triển khai

### A. Gate số học của tài liệu bằng code

- Đặt validation vào đường chứng cứ/admission hiện có, trước affirmative financial
  effect. Dùng cùng kết quả cho draft và submit, không tạo policy engine song song.
- Kiểm các quan hệ được xác định bởi loại tài liệu và fields đã có căn cứ: tổng
  dòng/tổng in; subtotal, thuế, giảm giá/phí nếu áp dụng; ứng kê khai/chi kê khai/
  hoàn lại hoặc đề nghị bổ sung trên giấy.
- Với TC06, kiểm **quan hệ nội bộ giấy**:4m−3.24m vs700k. Không lấy ứng kê khai
  làm A thật, không dùng phép tính giấy thay S=E−A−P+R của lịch sử công ty.
- Với TC11, kiểm5m+400k vs5.5m. Khớp số hóa đơn/tổng giữa hai tài liệu không
  thay thế kiểm số học bên trong hóa đơn.
- Giữ số nguồn nguyên bản. Có thể hiển thị số tính lại để đối chiếu, nhưng không
  âm thầm sửa tổng hay phát hành tiền theo số sửa khi chưa giải quyết mâu thuẫn.
- Sử dụng integer VND/Decimal và quy tắc làm tròn đã có; không float hoặc dung sai
  tùy ý để làm sai lệch60k/100k trở thành hợp lệ.
- Validators phải theo loại tài liệu; ticket/receipt không bị bắt có VAT fields.

### B. FACT có nguồn và chặn hành động

- Mâu thuẫn trọng yếu tạo BusinessIssue FACT với field/rule ổn định, source refs,
  các số đối chiếu, sai lệch, câu hỏi cụ thể và owner phù hợp. Với hai case này,
  nhân viên bổ sung/correct chứng từ là owner câu hỏi.
- Đưa issue qua Reconciler và boundary commit thật. Không chỉ thêm warning màu
  đỏ trong UI rồi vẫn tạo instruction hoặc reuse conclusion cũ.
- FACT chưa giải quyết → allowed_effect=None, không issue payment/collection và
  không SETTLED. Khả năng đọc rõ một số không có nghĩa số đó nhất quán/hợp lệ.
- Approval/EXCEPT_POLICY chung không được waive FACT. Khi có correction hoặc
  nguồn mới hợp lệ, lưu actor/basis/revision và đánh giá lại; không sửa chứng từ gốc.

### C. Trạng thái chưa biết và numeric provenance

- Tax hoặc thành phần vật chất UNKNOWN/UNREADABLE phải được giữ như vậy; không
  default0 hoặc báo CLEAR/eligible khi phép kiểm trọng yếu chưa thể hoàn thành.
- Phân biệt tax0 có căn cứ, NOT_APPLICABLE theo loại tài liệu và tax chưa đọc được.
  Với discount/phí/thuế nhiều dòng, không tự invent thành phần hoặc mặc định mọi
  trường không có giá trị đều bằng0.
- Sửa numeric provenance để quote có cả8% và400.000 nhận đúng money400000.
  Kiểm theo kiểu trường/token/locator; không tìm substring số bất kỳ trong đoạn
  dài hoặc nhầm phần trăm/document number với tiền.
- Giữ từ chối giá trị sai, sai nguồn/trang và identifier sai. Ghi rõ nguyên nhân
  demotion để phân biệt quote không khớp với số chưa đọc được.
- Không thay all-input-OCR bằng native-PDF text/regex bypass; không gọi thêm LLM
  chỉ để cộng/trừ những số đã được trích xuất có căn cứ.

## RED → GREEN bắt buộc

Viết regression thực sự gọi code hiện tại; file private chấm saved result là
bằng chứng RED, không thay cho test consumer/commit của bản sửa.

1. TC06 giữ printed_return700k và tạo FACT700kvs760k/60k, không instruction.
2. TC11 với tax FOUND400k tạo FACT5.4mvs5.5m/100k, không instruction; với tax
   UNKNOWN cũng không ra affirmative money trong trường hợp cần kiểm tổng.
3. Quote thuế8%/400k nhận money đúng; money sai, identifier sai, quote sai bị từ chối.
4. Hóa đơn hợp lệ, tax0 có căn cứ và ticket/receipt hợp lệ không bị false block.
5. Source/answer/revision thay đổi invalidate gate/conclusion đúng; không issue
   trùng, không waive FACT bằng quyết định policy, không ảnh hưởng Stop/actual tiền.
6. TC01 gốc + context đầy đủ → COLLECT760k như trước.
7. TC01 gốc + **không có bản ghi ứng thực nhận**: giữ B/grants/company/person/activity
   phù hợp, bỏ advance ledger event; giấy vẫn khai4m. Phải WAITING, A/S UNKNOWN,
   không instruction, chuyển kế toán xác minh/ghi nhận ứng. Không PAY3.24m từ A0
   giả và không COLLECT760k từ số ứng in trên giấy. Có thể test cả coverage có sẵn
   và coverage chưa có; hỏi đúng phần thiếu, không tạo ngân sách/payer issue giả.
8. Sau khi kế toán ghi nhận actual4m qua đường có căn cứ/quyền hiện có và history
   đầy đủ → đánh giá lại COLLECT760k, retry không double count. Trạng thái chứng từ
   pending/failed không được thành actual confirmed.

## Kiểm chứng và bàn giao

- Test tập trung trước, rồi regression backend/frontend liên quan. Kiểm cả typed
  evidence và consumer workflow/commit thật; không chỉ unit test validator.
- Chạy lại nguyên bản TC06/TC11/TC01 bằng provider LIVE trong DB test riêng; ghi
  model/source hashes, mode, context SIMULATED, clock, facts, issues/instructions,
  timings và tested code revision. Case âm phải chặn vì đúng mâu thuẫn, không do
  thiếu B/coverage hoặc lỗi provider che lấp.
- Clock lịch sử phải công khai; test actual time phải có coverage hợp lệ, không
  nới lịch sử để ép PASS. B/grant/history/gold độc lập với giấy kê khai.
- Kiểm browser khi luồng intake được bàn giao; source warning và server outcome
  phải nhất quán. Browser/LIVE chưa chạy ghi NOT_RUN.
- Ghi rõ PASS/FAIL/NOT_RUN, cập nhật checkpoint theo gate thực tế. Không gọi một
  job exit0 là test PASS hoặc issue instruction là đã thu tiền.
- Không mở rộng sang25case, thay framework hoặc redesign UI trong task này.

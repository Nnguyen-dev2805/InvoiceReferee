# InvoiceReferee — Product và workflow hiện hành

Ngày 09/10/2026. **Thiết kế đã được chủ dự án đồng ý; chưa nghiệm thu implementation hoặc baseline mới.** Bản hợp nhất không bổ sung quy tắc nghiệp vụ. Các bước thảo luận và review gốc được giữ trong [lưu trữ](../archive/README.md).

Authority: [đề cuộc thi gốc](../Challenge_Brief_OrganizationAI_VN.docx.md) quyết định yêu cầu BTC; tài liệu này, [Rulebook](RULEBOOK.md), [System](SYSTEM.md), [Evaluation](EVALUATION.md) và [plan](../superpowers/plans/2026-10-09-settlement-mvp.md) quyết định thiết kế mới. Source và fresh execution xác định phần đã tồn tại. Spec B1/plan 04-10 là tham chiếu implementation cũ, không quy định mới.

## P1. Bài toán và giá trị cần chứng minh

Hỗ trợ kế toán xử lý hồ sơ công tác từ nhiều chứng từ và nguồn tài chính: tìm/ghép nguồn, kiểm tra số liệu, payer, policy và lịch sử, chuẩn bị bảng đối chiếu có căn cứ. Kế toán rà soát bảng, mở nguồn cần xác minh và trình quyết định; không bị buộc thu gom/ghép/cộng lại mọi nguồn từ đầu.

Nhân viên có thể xin ứng trước hoặc tự chi rồi đề nghị hoàn trả. Giấy đề nghị/approval không chứng minh đã nhận tiền; hóa đơn không chứng minh ai trả. Quyết toán cần tổng chi phí được chấp nhận và tiền đã thực nhận đúng phạm vi. Hệ thống không tự giải ngân.

Hai tiêu chí riêng: **đúng** về facts/links/rules/money/workflow; **có ích** về tổng công sức chuẩn bị, bổ sung, rà soát, quyết định và đối chiếu. LLM nhanh hơn không tự chứng minh kế toán làm ít hơn. Quy trình thủ công so sánh hiện là giả định thiết kế, chưa được doanh nghiệp thật xác nhận.

## P2. Phạm vi MVP

- Hồ sơ công tác trong nước, VND, một nhân viên/một công việc; nhiều khoản, chứng từ và lần bổ sung trong cùng phạm vi lũy kế.
- Vé/di chuyển, khách sạn, ăn phục vụ công việc/tiếp khách; nhận cả hủy công việc có tiền/nghĩa vụ cần xử lý. Không tự mở sang mua hàng–PO–nhận hàng/tồn kho, ngoại tệ hoặc phân bổ kế toán tổng quát.
- Nhân viên tạo form chính hoặc nhập hồ sơ ngoài; công việc/quyết định bên ngoài hợp lệ được dùng lại. Hồ sơ đã ở giai đoạn sau có thể nhập đúng giai đoạn, không bắt chạy lại mọi bước.
- Bảng kê, ảnh/PDF/text được hỗ trợ, bảng nguồn tài chính nhập/import với provenance và coverage. Không hứa đọc mọi format/mẫu hoặc xác thực forensic/tax/legal.
- Khoảng 5 người trong pilot; ba vai demo. Một người có thể mô phỏng các vai; role picker không xác thực danh tính/quyền thật. Không enterprise auth/tenancy, bank/ERP hoặc hạ tầng phân tán.
- Scope/history có thể liên quan nhiều hồ sơ trong dataset được quản lý; không suy toàn công ty đã được kết nối. Unknown nguồn/phân bổ giữ vướng mắc.

Ví dụ nghiệp vụ cho hai giai đoạn cùng chuyến đi: [hai bộ hồ sơ mẫu](WORKED_EXAMPLE.md). Đây là walkthrough thiết kế, không thay rulebook, dataset frozen hoặc bằng chứng runtime.

### P2a. B3 khởi tạo khi giao công tác bằng lời (chốt ngày 10/10/2026)

**PLANNED:** nhân viên nộp đề nghị tạm ứng và dự toán; chưa có văn bản công tác
không phải lỗi hồ sơ. Lời khai giao việc chưa là quyết định của người có quyền.
Kế toán rà soát report; người đủ quyền có thể xác nhận công việc, duyệt ngân sách
và ứng trong một quyết định có nội dung/phạm vi riêng. Không yêu cầu nhân viên
đính kèm chính những quyết định đang xin hoặc nguồn quyền/lịch sử ứng của công ty.

- Form web dùng profile demo đã cấu hình; nhập nơi/ngày/mục đích công tác, số xin,
  hạn quyết toán và dự toán tách phần công ty/nhân viên. Backend cấp mã công việc
  cho hồ sơ mới; hệ thống hiển thị tuyến kế toán/người duyệt từ cấu hình.
- Nhập ngoài: giữ ảnh/PDF gốc, AI chuẩn bị bản nháp có refs; nhân viên xem/sửa và
  xác nhận trước khi nộp. Không tự nộp vì vừa upload; sửa không xóa originals.
- Không nhập tự do người duyệt, thông tin nhân viên hoặc hai mốc kỹ thuật trên
  màn nghiệp vụ B3. Mốc vẫn lưu để tái lập; clock giả lập phải ghi rõ và chỉ áp
  dụng fixture mô phỏng. Role picker/profile demo không phải authentication.
- Dự toán không là B đã duyệt, phần dự kiến trả không là actual payer. Lịch sử
  ứng/hoàn ứng/approval/pending/coverage lấy từ phía công ty; thiếu hỏi kế toán,
  không gán zero. Có quyền để xem xét không đồng nghĩa đã duyệt hồ sơ.
- Report B3 trình bày đề nghị, kiểm tra, vướng mắc và người xử lý; không dùng S
  quyết toán làm kết quả chính. “Đủ để rà soát” không phải được phép chi.

Gói mẫu: `data/settlement/b3-verbal-v2.zip` (synthetic, local, chưa đo baseline).
Hai tài liệu nhân viên: đề nghị và dự toán; dữ liệu công ty và oracle tách riêng.
Mẫu giấy đã chốt: Công ty InvoiceReferee, tiền có hậu tố đ, không địa chỉ/số mẫu/
số giấy giả định/thông tin giao việc/trạng thái/nhãn thử nghiệm; trip context gộp
trong lý do hoặc nội dung công tác. Web vẫn lưu place/dates/purpose riêng, mã hồ
sơ backend cấp; giấy ngoài không bị buộc có employee_ref/work_ref/mã DN nội bộ.
[Plan intake/report B3](../superpowers/plans/2026-10-10-b3-verbal-intake.md)
thực hiện nhánh khởi tạo này. Approval/actual ứng/end-to-end đến B7 chưa được
nghiệm thu bởi plan đó; không dùng action SETTLEMENT làm approval ứng.

## P3. Ba vai và ranh giới quyết định

| Vai | Công việc | Ranh giới |
| --- | --- | --- |
| Nhân viên | Nộp/bổ sung, khai mục đích và phạm vi; cung cấp nguồn phía mình; hoàn lại khi có nghĩa vụ | Không tự khai thay company-side absence hoặc tạo ngân sách/quyền |
| Kế toán | Rà soát report/căn cứ, xử lý facts trong scope, trình quyết định; thực hiện chi và đối chiếu công ty nhận tiền | Không có quyền phê duyệt tài chính mặc định; review không miễn quality gates |
| Người duyệt có quyền | Cho phép công việc, duyệt B/ứng, chấp nhận chi phí/ngoại lệ/quyết toán trong phạm vi được giao | Chức danh/role không tự cấp quyền; approval không tạo receipt hoặc sửa số mờ |

Hệ thống là bên chuẩn bị/kiểm tra, không thêm một vai con người. Quyết định công việc, ngân sách, ứng và quyết toán có nội dung riêng; có thể cùng thao tác khi đủ quyền/phạm vi, không một boolean Approved cho tất cả.

## P4. Hai jobs tự động và A/B

| Job | Input và điểm bắt đầu | Hoàn thành thường quy |
| --- | --- | --- |
| B3 kiểm tra đề nghị ứng | Submit đề nghị/dự toán/context/history/quyền hiện có, kể cả thiếu/mâu thuẫn | Lưu checks/rule/refs, nghĩa số xin, nội dung/người quyết định tiếp, không cần người ghép/tính lại |
| B7 kiểm tra/quyết toán | Submit khoản/chứng từ và nguồn tài chính trong scope, kể cả thiếu/mâu thuẫn | Lưu khoản/phần, source/rule/links/history/coverage; tính E/S khi mọi phần ảnh hưởng đủ căn cứ |

Job chưa đủ giữ phần đã rõ và câu hỏi đúng owner/refs, hoặc lỗi kỹ thuật đúng nghĩa. Bổ sung→re-check thuộc cùng lifecycle; không đổi case ban đầu thành first-pass routine. Input preparation/handmatching phải đo và ghi assisted khi phù hợp, không free preprocessing.

**A — baseline trước:** report/questions, human decisions, ghi/đối chiếu nguồn tiền, history/controls/closure. Handoff là report+decision+refs đang áp dụng có audit; không entity/lệnh chi/thu tự tạo.

**B — cải tiến sau:** tự tạo đối tượng đề nghị chi/thu sau decision và action gates, có ID/status/version và chống trùng. Độ đúng A không chứng minh an toàn B. Cả A/B không chuyển tiền, khấu trừ lương hoặc tự thu hồi.

B7 là job đánh giá chính; B3 có tập/metrics riêng. Report complete khác kế toán đã review, phê duyệt tài chính, actual receipt và đóng. Các checkpoint con người thường quy vẫn được đo, không gọi là false escalation hoặc giấu công sức.

## P5. Work flow tổng quan

```mermaid
flowchart TD
    A["Nhân viên gửi đề nghị ứng<br/>Form hoặc hồ sơ ngoài"] --> B["Hệ thống kiểm tra<br/>Kế toán rà soát"]
    B -->|"Cần làm rõ"| Q1["Bổ sung/sửa đúng phần<br/>Kiểm tra lại phần ảnh hưởng"]
    Q1 --> B
    B -->|"Đủ để xem xét"| D{"Đã đủ quyết định công việc/B/ứng<br/>đúng quyền, còn hiệu lực?"}
    D -->|"Chưa"| H1{"Người có quyền quyết định"}
    H1 -->|"Trả lại"| Q1
    H1 -->|"Từ chối"| N["Lưu từ chối và lý do<br/>Không chi mới theo yêu cầu này"]
    H1 -->|"Duyệt"| G1["Guard quyền/điều kiện/version/Stop<br/>và phần tiền chưa thực hiện"]
    D -->|"Đã có, kể cả ngoài app"| G1
    G1 --> P["Con người chi ứng ngoài app<br/>Đối chiếu nhân viên thực nhận"]
    P -->|"Chờ hoặc mới nhận một phần"| W1["Giữ thực nhận/phần còn lại<br/>Chờ thực hiện hoặc đối chiếu"]
    W1 -->|"Có kết quả/đủ điều kiện tiếp tục"| G1
    P -->|"Đã nhận đủ"| W["Chờ công việc hoàn thành<br/>hoặc hủy cần xử lý ứng"]
    W --> S["Nộp/nhận bảng kê, chứng từ<br/>và lịch sử tiền"]
    I["Tự chi hoặc đã có tiền ứng ngoài"] --> S
    S --> K["Hệ thống đối chiếu/tính khi đủ<br/>Kế toán rà soát báo cáo có căn cứ"]
    K -->|"Còn vướng mắc"| Q2["Bổ sung/sửa/xin quyết định cần thiết<br/>Kiểm tra lại phần ảnh hưởng"]
    Q2 --> K
    K -->|"Đủ"| D2{"Đã có quyết định quyết toán<br/>đúng phạm vi, còn hiệu lực?"}
    D2 -->|"Chưa"| H2{"Người có quyền quyết toán"}
    H2 -->|"Trả lại/lỗi"| Q2
    H2 -->|"Từ chối"| N
    H2 -->|"Duyệt"| G2["Guard và phần còn phải xử lý<br/>Con người chi/hoàn lại, đối chiếu thực nhận"]
    D2 -->|"Đã có"| G2
    G2 -->|"Thiếu nguồn/sai lệch/điều kiện chưa rõ"| Q2
    G2 -->|"Chưa thực hiện đủ/đang chờ"| W2["Giữ decision và phần còn lại<br/>Chờ thực hiện hoặc đối chiếu"]
    W2 -->|"Có kết quả/đủ điều kiện tiếp tục"| G2
    G2 -->|"Đủ căn cứ, hết nghĩa vụ"| Z["Đóng theo scope/as-of/version"]
    N --> O{"Tiền/nghĩa vụ đang có?"}
    O -->|"Xác nhận không có"| X["Kết thúc yêu cầu bị từ chối"]
    O -->|"Có, cần xử lý"| S
    O -->|"Chưa rõ"| Q2
```

Guard chưa đạt thì chưa handoff/chi/đóng; trạng thái chờ rõ không mặc định cần nhân viên bổ sung. S dương công ty chi thêm; âm nhân viên hoàn lại và kế toán xác minh công ty nhận;0 kiểm tra closure, không chuyển 0 đồng. N không suy đã cấp ứng hoặc xóa nghĩa vụ. X khác Z. K/H2 có thể nhận combined exception+approval; re-check phần thay đổi mà không bắt duyệt lần hai khi decision đã bao phủ.

Khung 9 bước: B1 nộp→B2 cho phép công việc→B3 check ứng→B4 decision ứng/B→B5 actual ứng→B6 chứng từ sau chi→B7 check/net→B8 decision quyết toán→B9 actual chi/thu/closure. Trình tự bàn giao không bắt buộc chín màn hình/lần bấm. Đã nhận ứng không đóng cả hồ sơ.

## P6. Trạng thái và hành vi người dùng

Stage nghiệp vụ: CHECKING, ACCOUNTING_REVIEW, AWAITING_DECISION, AWAITING_MONEY, AWAITING_WORK_SETTLEMENT, RESOLVING_OBLIGATIONS, REJECTED_REQUEST_ENDED, SETTLEMENT_CLOSED. Stage suy ra từ records/gates, không client PATCH tùy ý.

Issues/Stop/decision validity/fulfillment là trục riêng. Một hồ sơ có nhiều vướng mắc, owner/phần bị chặn riêng. Câu hỏi: chờ→nhận phản hồi chưa xác thực→chưa đủ hoặc resolved sau re-check; revision thay thế có thể làm câu hỏi không còn áp dụng nhưng không coi đã được trả lời đúng.

UI phải mở được nguồn từ từng số/quan hệ/check; giữ phần rõ/chưa rõ. Sếp và kế toán có thể xem mọi chứng từ nhưng không bị bắt tự ghép lại toàn bộ. UI phân biệt proposed/approved/actual/remaining, không dùng debug JSON làm màn nghiệp vụ chính.

## P7. Ranh giới đóng và lịch sử

Đóng chỉ khi decision/source hiện áp dụng đúng quyền/phạm vi, money đã đối chiếu đủ hoặc cân bằng hợp lệ, không Stop/stale/pending/incident/nguồn bắt buộc/ngoại lệ/nghĩa vụ chưa giải quyết, và history được lưu. S0, refusal hoặc Paid label đơn độc không đủ.

Nguồn mới có ảnh hưởng sau closure tạo bản điều chỉnh liên kết và giữ lần đóng as-of trước. Exact resubmission không mở nghĩa vụ mới. Dùng lại decision bên ngoài khi hợp lệ; giữ mâu thuẫn decision và source, không ưu tiên latest hoặc trong app vô điều kiện.

## P8. Cuộc thi và giới hạn bằng chứng

[Đề gốc](../Challenge_Brief_OrganizationAI_VN.docx.md) yêu cầu routine tự xử lý, escalation fact/policy/authority có câu hỏi cụ thể, Verify/newinputs, adaptation từ feedback, independent miss/unnecessary metrics, ít nhất 3 professional participants, audit/Stop/Override và submission. Hạn khóa 15/10; demo 17/10.

Diễn giải job B3/B7 tự hoàn tất report trong khi toàn workflow có checkpoint người là lựa chọn dự án; BTC chưa xác nhận nó đủ ranh giới routine. Không thay mẫu số để che rủi ro này. Research/agent/synthetic feedback không thay thử người làm nghiệp vụ thật. Nguồn/quyền/policy trong fixtures là giả lập, không chứng minh dữ liệu công ty thật authenticated.

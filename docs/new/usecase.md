# Đặc tả use case InvoiceReferee

## 1. Mục đích và phạm vi

InvoiceReferee là hệ thống hỗ trợ kế toán tiếp nhận, đọc, kiểm tra và đối chiếu hồ sơ chi phí. Hệ thống không tự giải ngân và không thay thế quyền phê duyệt của con người.

Dự án dự thi theo **Track A - Escalation Referee**. Use case thi chính là `UC-03: Hoàn ứng và quyết toán chi phí`. Hai use case còn lại được thiết kế trên cùng nền tảng để chứng minh khả năng mở rộng, nhưng không được trình bày như chức năng đã hoàn thiện nếu code chưa triển khai.

Ba use case mục tiêu:

| Mã | Nghiệp vụ | Vai trò trong bài thi |
| --- | --- | --- |
| `UC-01` | Đối chiếu mua hàng và nhận hàng | Workflow mở rộng |
| `UC-02` | Đề nghị tạm ứng | Workflow mở rộng |
| `UC-03` | Hoàn ứng và quyết toán chi phí | Workflow Track A chính |

## 2. Quy ước chung

### 2.1. Hồ sơ và nguồn dữ liệu

Một nghiệp vụ được quản lý bằng một `ExpenseCase`. Một case có thể chứa nhiều tài liệu, nhiều khoản chi và nhiều lần xử lý.

Tạm ứng và hoàn ứng hỗ trợ hai kênh đầu vào:

| Kênh | `source_type` | Cách xử lý |
| --- | --- | --- |
| Form điện tử | `DIGITAL_FORM` | Kiểm tra trực tiếp dữ liệu có cấu trúc; lưu canonical JSON; sinh PDF trình bày; mô phỏng approval trong MVP. |
| Đơn giấy | `PAPER_SCAN` | Lưu file gốc; OCR từng file; Confidence Gate; trích xuất dữ kiện; phát hiện sự hiện diện của chữ ký tay. |

Canonical JSON trong database hoặc case store là nguồn dữ liệu cho policy. PDF là bản trình bày và lưu trữ. XML chỉ sinh khi có hệ thống tích hợp yêu cầu; không dùng PDF/XML làm nguồn dữ liệu duy nhất.

### 2.2. Giới hạn chữ ký

- Chữ ký tay trên ảnh chỉ được gắn `PRESENT_UNVERIFIED`, `MISSING`, `UNCLEAR` hoặc `NOT_REQUIRED`.
- AI không được tuyên bố chữ ký tay là thật hoặc đúng danh tính.
- `VERIFIED` chỉ dành cho chữ ký số đã được công cụ chuyên dụng kiểm tra chứng thư và hash tài liệu.
- MVP mô phỏng phê duyệt, chưa tích hợp nhà cung cấp chữ ký số. UI và tài liệu phải ghi rõ `SIMULATED_APPROVAL`.
- Đơn giấy thiếu bất kỳ chữ ký bắt buộc nào được trả `REQUEST_INFO`; nhân viên bổ sung và tải lên phiên bản mới. MVP không trộn chữ ký tay và phê duyệt điện tử trên cùng một phiên bản tài liệu.

### 2.3. Profile và policy giả lập

Dữ liệu demo phải là dữ liệu tổng hợp, không mô phỏng cá nhân có thật. Profile mặc định:

```yaml
employee_id: EMP-DEMO-001
name: Nguyễn Minh An
department: Phòng Kinh doanh
position: Nhân viên
data_classification: SYNTHETIC
```

Hạn mức, thời hạn, danh mục chi phí và chuỗi phê duyệt nằm trong `PolicyConfig` có `policy_version`. Giá trị demo phải gắn nhãn `SYNTHETIC`; không mô tả là policy của doanh nghiệp thật.

### 2.4. Hai lớp trạng thái

Không dùng một enum để biểu diễn cả quyết định của Referee và vòng đời hồ sơ.

**Quyết định tự động hóa:**

| `automation_decision` | Ý nghĩa |
| --- | --- |
| `AUTO_PROCESS` | Các kiểm tra trong phạm vi đã cấu hình đều đạt; chuyển tiếp trong workflow mà không cần hỏi thêm. Không đồng nghĩa đã duyệt hoặc đã thanh toán. |
| `REQUEST_INFO` | Có `FACTUAL_UNKNOWN`; cần dữ kiện hoặc tài liệu để tiếp tục. Phải có câu hỏi cụ thể và người cần trả lời. |
| `ESCALATE` | Dữ kiện đã rõ nhưng ngoài policy, có dấu hiệu nghi vấn hoặc vượt thẩm quyền. Phải có lý do và nơi nhận xử lý. |

**Phân loại không chắc chắn:**

```text
FACTUAL_UNKNOWN   -> REQUEST_INFO
OUTSIDE_POLICY    -> ESCALATE
BEYOND_AUTHORITY  -> ESCALATE
SUSPICIOUS        -> ESCALATE
không có lỗi chặn -> AUTO_PROCESS
```

**Vòng đời case:**

```text
DRAFT -> SUBMITTED -> PROCESSING
      -> READY_FOR_ACCOUNTING_REVIEW
      -> WAITING_FOR_INFORMATION
      -> WAITING_FOR_APPROVAL
      -> APPROVED -> DISBURSED
      -> PARTIALLY_SETTLED -> SETTLED
      -> REJECTED / CANCELLED
```

### 2.5. Nguyên tắc xử lý chung

1. Kiểm tra kỹ thuật và tài liệu bắt buộc bằng code trước khi gọi LLM.
2. Form điện tử không chạy OCR; file scan phải OCR độc lập từng file.
3. Confidence Gate dùng critical field theo loại tài liệu, không dùng một danh sách chung.
4. LLM phân loại, trích xuất và đề xuất ghép ngữ nghĩa; không cộng tiền, tự điền dữ kiện thiếu hoặc quyết định action cuối.
5. Python dùng `Decimal` cho phép tính, dung sai, hạn mức và tổng tiền.
6. Decision Guard quyết định `AUTO_PROCESS`, `REQUEST_INFO` hoặc `ESCALATE` từ findings và `PolicyConfig`.
7. Mọi dữ kiện và finding phải có `source_refs` tới file, trang, block/bbox hoặc field form.
8. Mọi lần chạy, ghi đè, dừng và chạy lại phải tạo audit event.

## 3. Tác nhân

| Tác nhân | Trách nhiệm |
| --- | --- |
| Nhân viên | Chọn nghiệp vụ, nhập form hoặc tải đơn giấy, đính kèm chứng từ và bổ sung khi được hỏi. |
| Phụ trách bộ phận | Xác nhận mục đích và nhu cầu nghiệp vụ theo chuỗi phê duyệt mục tiêu. |
| Kế toán trưởng | Kiểm tra căn cứ kế toán, hạn mức và đề xuất xử lý. |
| Giám đốc | Phê duyệt cuối trong phạm vi policy. |
| Kế toán xử lý | Dùng tab Kế toán để xem dữ kiện, evidence, findings, câu hỏi, audit và thực hiện can thiệp. |
| OCR | Đọc text, bảng, bbox và confidence từ tài liệu scan. |
| LLM Agent | Trích xuất semantic facts, đánh giá block OCR nghi ngờ và đề xuất ghép dữ liệu. |
| Policy Engine | Thực hiện rule tất định và tính toán. |
| Decision Guard | Áp dụng invariant và xuất quyết định Track A. |

# 4. UC-01: Đối chiếu mua hàng và nhận hàng

## 4.1. Mục tiêu

Xác định hàng thực nhận có khớp với thông tin mua hàng hoặc hóa đơn hay không; ghi nhận nhận đủ, nhận thiếu, nhận vượt, sai loại, hư hỏng và giao từng phần.

Đây không phải kiểm kê tồn kho định kỳ. Kiểm kê tồn kho thực tế so với sổ kho nằm ngoài phạm vi UC-01.

## 4.2. Chế độ đối chiếu

Nhân viên chọn một mode; hệ thống được phép cảnh báo chọn sai nhưng không tự đổi âm thầm.

| `reconciliation_mode` | Tài liệu bắt buộc | Mục tiêu |
| --- | --- | --- |
| `PO_TO_RECEIPT` | PO/đơn đặt hàng + chứng từ nhận hàng | So sánh hàng đặt với hàng thực nhận. |
| `INVOICE_TO_RECEIPT` | Hóa đơn + chứng từ nhận hàng | So sánh hàng lập hóa đơn với hàng thực nhận. |
| `THREE_WAY_MATCH` | PO + hóa đơn + chứng từ nhận hàng | Đối chiếu ba chiều để hỗ trợ kiểm tra thanh toán. |

Chứng từ nhận hàng có thể là phiếu nhập kho, biên bản giao nhận, phiếu kiểm nhận hoặc tài liệu tương đương do `PolicyConfig` cho phép.

## 4.3. Luồng chính

1. Nhân viên chọn UC-01 và `reconciliation_mode`.
2. Nhân viên nhập mã giao dịch/PO nếu có và tải tài liệu vào đúng vai trò.
3. Hệ thống kiểm tra đủ loại tài liệu theo mode.
4. Mỗi file được OCR và qua Confidence Gate độc lập.
5. LLM trích xuất document facts và đề xuất ghép các dòng hàng tương ứng.
6. Python kiểm tra identity giao dịch, số lượng, đơn vị, đơn giá, thành tiền, trạng thái nhận và dung sai.
7. Decision Guard tổng hợp findings.
8. Tab Kế toán hiển thị bảng ghép dòng, chênh lệch, vùng chứng từ và câu hỏi cụ thể.
9. Kế toán xác nhận, yêu cầu bổ sung hoặc chuyển ngoại lệ.

## 4.4. Ngoại lệ trọng yếu

| Tình huống | Kết quả |
| --- | --- |
| Thiếu tài liệu bắt buộc theo mode | `REQUEST_INFO / FACTUAL_UNKNOWN` và nêu đúng loại tài liệu thiếu. |
| Số lượng hoặc đơn vị không đọc được | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Tên hàng khác cách viết | AI đề xuất cặp ghép; dưới ngưỡng thì kế toán xác nhận. |
| Khác đơn vị nhưng chưa có hệ số quy đổi | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Giao từng phần được chứng từ ghi rõ | Ghi `PARTIAL_DELIVERY`; không tự kết luận giao sai. |
| Nhận thiếu, vượt hoặc hàng hỏng rõ ràng | `ESCALATE / OUTSIDE_POLICY` hoặc xử lý theo tolerance cấu hình. |
| Tổng giá trị vượt thẩm quyền | `ESCALATE / BEYOND_AUTHORITY`. |

## 4.5. Đầu ra và acceptance criteria

- Mỗi dòng có ordered, invoiced, received, accepted, rejected, variance và `source_refs`.
- Không so sánh số lượng khi đơn vị chưa quy đổi được.
- Không coi thiếu hóa đơn là lỗi trong `PO_TO_RECEIPT`.
- Không `AUTO_PROCESS` khi một critical field chưa rõ.
- Kế toán mở được đúng nguồn của từng giá trị và finding.

Chi tiết triển khai: [uc01_purchase_receiving_reconciliation_plan.md](uc01_purchase_receiving_reconciliation_plan.md).

# 5. UC-02: Đề nghị tạm ứng

## 5.1. Mục tiêu

Tiếp nhận đề nghị nhận tiền trước để phục vụ công việc; kiểm tra tính đầy đủ, policy, tạm ứng cũ và chuỗi phê duyệt trước khi kế toán ghi nhận giải ngân.

## 5.2. Đầu vào

| Kênh | Tài liệu/dữ liệu chính |
| --- | --- |
| `DIGITAL_FORM` | Form người đề nghị, bộ phận, mục đích, số tiền, thời gian thực hiện, hạn hoàn ứng và dự toán nếu cần. |
| `PAPER_SCAN` | Giấy đề nghị tạm ứng đã ký tay theo mẫu doanh nghiệp. |

Chuỗi phê duyệt mục tiêu:

```text
Nhân viên -> Phụ trách bộ phận -> Kế toán trưởng -> Giám đốc
```

## 5.3. Luồng chính

1. Nhân viên chọn form điện tử hoặc đơn giấy.
2. Form điện tử được validate trực tiếp; đơn giấy được OCR và kiểm tra confidence.
3. Hệ thống chuẩn hóa dữ liệu về cùng `AdvanceRequestData`.
4. Với form điện tử, hệ thống lưu JSON và sinh PDF có version/hash; approval trong MVP được gắn `SIMULATED_APPROVAL`.
5. Với đơn giấy, hệ thống kiểm tra sự hiện diện và độ rõ của từng vùng chữ ký bắt buộc.
6. Policy Engine kiểm tra mục đích, số tiền, hạn hoàn ứng, tạm ứng cũ, hạn mức và cấp phê duyệt.
7. Decision Guard tạo action và câu hỏi/đích chuyển tiếp.
8. Tab Kế toán hiển thị dữ liệu đề nghị, trạng thái chữ ký/phê duyệt, findings và tài liệu gốc.
9. `APPROVED` chưa tạo số dư tạm ứng. Chỉ sự kiện `DISBURSEMENT_RECORDED` mới chuyển case sang `DISBURSED`.

## 5.4. Ngoại lệ trọng yếu

| Tình huống | Kết quả |
| --- | --- |
| Thiếu mục đích, số tiền hoặc hạn hoàn ứng | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Số bằng chữ khác số bằng số | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Đơn giấy thiếu hoặc mờ chữ ký bắt buộc | `REQUEST_INFO / FACTUAL_UNKNOWN`; tải lại phiên bản mới. |
| Vượt hạn mức | `ESCALATE / BEYOND_AUTHORITY`. |
| Mục đích thuộc danh mục cấm | `ESCALATE / OUTSIDE_POLICY`. |
| Có tạm ứng cũ quá hạn | Chặn hoặc `ESCALATE` theo `PolicyConfig`. |
| Không truy cập được lịch sử | `REQUEST_INFO / FACTUAL_UNKNOWN`; không suy đoán không có nợ cũ. |

## 5.5. Đầu ra và acceptance criteria

- Hiển thị rõ `APPROVAL_PENDING`, `APPROVED` và `DISBURSED` là các trạng thái khác nhau.
- Không gọi OCR cho form điện tử.
- Không gắn `VERIFIED` cho chữ ký tay.
- Bản PDF sinh ra phải liên kết đúng `case_id`, `document_version` và `document_hash`.
- Kế toán thấy rõ dữ liệu hoặc policy nào đang chặn hồ sơ.

Chi tiết triển khai: [uc02_advance_request_plan.md](uc02_advance_request_plan.md).

# 6. UC-03: Hoàn ứng và quyết toán chi phí

## 6.1. Mục tiêu

Đối chiếu bảng kê với một hoặc nhiều chứng từ chi phí, xác định tổng được đề xuất chấp nhận và tính chênh lệch với tiền đã tạm ứng. Đây là use case Track A chính.

## 6.2. Subtype

| `settlement_type` | Điều kiện | Công thức |
| --- | --- | --- |
| `ADVANCE_SETTLEMENT` | Nhân viên đã nhận tiền; bắt buộc có `advance_id`. | So sánh chi phí được duyệt với phần tạm ứng phân bổ. |
| `EMPLOYEE_REIMBURSEMENT` | Nhân viên tự chi; không có khoản tạm ứng. | Công ty hoàn trả tổng chi phí được duyệt. |

## 6.3. Đầu vào

- Form điện tử hoặc giấy đề nghị hoàn ứng/quyết toán.
- Danh sách khoản khai báo.
- Một hoặc nhiều hóa đơn, bill, vé hoặc chứng từ thanh toán.
- `advance_id` đối với `ADVANCE_SETTLEMENT`.
- Business context: mục đích, công việc/chuyến công tác, project/client khi policy yêu cầu.

## 6.4. Luồng chính

1. Nhân viên chọn UC-03, subtype và kênh đầu vào.
2. Nhân viên nhập/tải đơn chính và đính kèm evidence cho từng khoản chi.
3. Hệ thống kiểm tra đầu vào bắt buộc bằng code.
4. Mỗi file scan được OCR và qua Confidence Gate độc lập.
5. LLM trích xuất từng chứng từ và đề xuất liên kết expense item với evidence.
6. Python kiểm tra số tiền, ngày, duplicate, tổng bảng kê, allocation và policy từng khoản.
7. Hệ thống tính `proposed_eligible_amount`; không gọi giá trị này là `approved_amount`.
8. Decision Guard áp dụng invariant Track A và tạo action.
9. Tab Kế toán hiển thị bảng khoản chi, evidence, số tiền khai báo/chứng từ/đề xuất, findings và câu hỏi.
10. Sau khi con người xác nhận, hệ thống mới lưu `approved_amount` và tính số phải trả/thu hồi.

## 6.5. Công thức

```text
A = allocated_advance_amount
E = approved_expense_amount
D = E - A

D > 0 -> company_pays_employee = D
D = 0 -> không phát sinh thanh toán thêm hoặc thu hồi
D < 0 -> employee_returns_company = abs(D)
```

Với `EMPLOYEE_REIMBURSEMENT`, `A = 0` và công ty hoàn trả `E` sau khi được phê duyệt.

## 6.6. Ngoại lệ trọng yếu

| Tình huống | Kết quả |
| --- | --- |
| Thiếu chứng từ cho khoản bắt buộc có evidence | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Số tiền/ngày/số hóa đơn quan trọng không rõ | `REQUEST_INFO / FACTUAL_UNKNOWN` với câu hỏi cụ thể. |
| Bảng kê khác chứng từ nhưng chưa xác định giá trị đúng | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Duplicate chính xác | `ESCALATE / OUTSIDE_POLICY`; không tính lặp. |
| Duplicate chỉ là tín hiệu gần giống | `REQUEST_INFO / FACTUAL_UNKNOWN`. |
| Khoản chi bị cấm hoặc cá nhân, dữ kiện đã rõ | `ESCALATE / OUTSIDE_POLICY`. |
| Tổng tiền vượt thẩm quyền | `ESCALATE / BEYOND_AUTHORITY`. |
| Một chứng từ cho nhiều khoản | Cho phép allocation; tổng allocation không vượt giá trị chứng từ được chấp nhận. |
| Quyết toán một phần | Lưu phần đã quyết toán và số dư advance còn lại. |

## 6.7. Đầu ra và acceptance criteria

- Mỗi khoản hiển thị `claimed_amount`, `document_amount`, `proposed_eligible_amount`, finding và nguồn.
- Chỉ con người tạo `approved_amount`.
- Tổng được tính lại bằng `Decimal`; không dùng LLM cộng tiền.
- `REQUEST_INFO` phải hỏi một dữ kiện cụ thể mà người nhận có thể trả lời trực tiếp.
- `AUTO_PROCESS` không đồng nghĩa thanh toán tự động.
- Không khẳng định kết quả khi dữ kiện quan trọng đã bị gắn cờ.

Chi tiết triển khai: [uc03_expense_settlement_plan.md](uc03_expense_settlement_plan.md).

# 7. Tab Kế toán trong MVP

Tab Kế toán là bề mặt sản phẩm ưu tiên. Mỗi case cần hiển thị theo thứ tự:

1. Case ID, nghiệp vụ, subtype/mode, người đề nghị và thời gian gửi.
2. `automation_decision`, uncertainty class và workflow status.
3. Tóm tắt bằng ngôn ngữ kế toán, không lộ thuật ngữ OCR kỹ thuật không cần thiết.
4. Dữ liệu trích xuất và phép tính.
5. Trạng thái từng tài liệu và từng chữ ký/phê duyệt.
6. Findings theo mức độ, câu hỏi cụ thể và người cần trả lời.
7. Evidence gốc, trang và bbox tương ứng.
8. Audit timeline.
9. Hành động: xác nhận kết quả, yêu cầu bổ sung, chuyển cấp, dừng, chạy lại và ghi đè có lý do.

MVP chưa cần portal riêng cho phụ trách bộ phận, kế toán trưởng và giám đốc. Trạng thái chuỗi phê duyệt được hiển thị ở tab Kế toán; approval thật là phạm vi sau MVP.

# 8. Audit và quyền can thiệp

Audit event tối thiểu:

```text
CASE_CREATED
DOCUMENT_ATTACHED
OCR_STARTED / OCR_COMPLETED / OCR_FAILED
CONFIDENCE_REVIEWED
FACTS_EXTRACTED
POLICY_CHECKED
DECISION_PROPOSED
HUMAN_REQUESTED_INFO
HUMAN_OVERRIDDEN
PROCESSING_STOPPED
CASE_REPROCESSED
APPROVAL_RECORDED
DISBURSEMENT_RECORDED
SETTLEMENT_RECORDED
```

Mỗi event phải có `event_id`, `case_id`, `actor`, `timestamp`, `input_refs`, `reason`, `before`, `after` và `correlation_id` khi có.

# 9. Verify và dữ liệu thi

Nút `Verify` chạy các fixture qua cùng application service với UI và in bảng kết quả có timestamp. Không hardcode kết quả hiển thị.

Suite Track A tối thiểu năm case cho UC-03:

| Case | Kỳ vọng |
| --- | --- |
| Hoàn ứng thường quy, chứng từ rõ và tổng khớp | `AUTO_PROCESS` |
| Nhân viên tự chi thường quy, evidence đầy đủ | `AUTO_PROCESS` |
| Nhiều bill hợp lệ, tổng và business context khớp | `AUTO_PROCESS` |
| Tổng tiền quan trọng bị mờ | `REQUEST_INFO / FACTUAL_UNKNOWN` với câu hỏi số tiền cụ thể |
| Tổng vượt hạn mức demo | `ESCALATE / BEYOND_AUTHORITY` và nêu đúng cấp xử lý |

Bộ regression đầy đủ phải có ít nhất 15 trường hợp, bao phủ `FACTUAL_UNKNOWN`, `OUTSIDE_POLICY`, `BEYOND_AUTHORITY`, `SUSPICIOUS`, dữ liệu mới và lỗi OCR/LLM/tool.

# 10. Tài liệu triển khai

- [UC-01 - Implementation plan](uc01_purchase_receiving_reconciliation_plan.md)
- [UC-02 - Implementation plan](uc02_advance_request_plan.md)
- [UC-03 - Implementation plan](uc03_expense_settlement_plan.md)

Mỗi plan ghi rõ schema, module, hardcode/LLM/tool, policy, UI, audit, test, Verify, thứ tự triển khai và điều kiện hoàn thành.

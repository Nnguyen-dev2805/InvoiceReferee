# Kế hoạch chuyển đổi InvoiceReferee sang xử lý hồ sơ chi phí



## 2. Ba loại hồ sơ

```text
INVENTORY_RECONCILIATION  Đối chiếu hóa đơn và nhận hàng
ADVANCE_REQUEST           Yêu cầu tạm ứng
EXPENSE_SETTLEMENT        Quyết toán chi phí/hoàn ứng
```

`EXPENSE_SETTLEMENT` có hai subtype:

```text
ADVANCE_SETTLEMENT        Nhân viên đã nhận tiền tạm ứng
EMPLOYEE_REIMBURSEMENT    Nhân viên tự chi và yêu cầu công ty hoàn lại
```

Việc phân biệt hai subtype là bắt buộc vì công thức quyết toán và dòng tiền
khác nhau.

## 3. Mô hình dữ liệu mục tiêu

```text
ExpenseCase
├── case_id
├── case_type
├── settlement_type
├── employee_context
├── business_context
├── primary_documents[]
├── supporting_documents[]
├── expense_items[]
├── approval
├── related_advance
├── requested_amount
├── accepted_amount
├── reconciliation
├── findings[]
└── decision
```



## 4. Workflow chung

```text
Nhân viên chọn loại hồ sơ
        ↓
Nhập business context và tải tài liệu
        ↓
Validate tài liệu bắt buộc theo case_type
        ↓
OCR độc lập từng file
        ↓
Confidence Gate độc lập từng file
        ├── Field quan trọng không rõ → REQUEST_INFO
        └── Tất cả file CLEAR
                ↓
Trích xuất Structured Facts theo từng file
                ↓
Chạy policy tương ứng với case_type
                ↓
Tính toán và đối chiếu bằng Python
                ↓
Decision Guard
        ├── PASS / READY_FOR_APPROVAL
        ├── REQUEST_INFO
        └── ESCALATE
                ↓
Kế toán hoặc cấp có thẩm quyền quyết định cuối
```

## 5. Workflow đối chiếu kiểm kê

### 5.1. Đầu vào

```text
Hóa đơn/bill
+ phiếu nhập kho, phiếu kiểm kê hoặc biên bản giao nhận
+ purchase order nếu có
```

Purchase Order, Invoice và Goods Receipt là ba loại tài liệu khác nhau. Không
được gọi phiếu đặt hàng là hóa đơn.

Khi có đủ ba nguồn, hệ thống có thể thực hiện đối chiếu ba chiều:

```text
Purchase Order ↔ Invoice ↔ Goods Receipt
```

### 5.2. Rule

- OCR và Confidence Gate độc lập cho từng file.
- Đối chiếu nhà cung cấp, mã số thuế và ngày chứng từ.
- Ghép các dòng hàng cùng nghĩa.
- So sánh số lượng và đơn vị.
- So sánh đơn giá và thành tiền.
- Kiểm tra trạng thái nhận đủ, nhận thiếu hoặc đang chờ.
- Phát hiện dòng chỉ tồn tại ở một nguồn.
- Business context không được thay thế bằng chứng nhận hàng.

### 5.3. Kết quả

```text
PASS          Các nguồn thống nhất
REQUEST_INFO  Thiếu hoặc không đọc được dữ kiện quan trọng
ESCALATE      Có mâu thuẫn rõ cần kế toán quyết định
```

## 6. Workflow yêu cầu tạm ứng

### 6.1. Đầu vào

```text
Giấy đề nghị tạm ứng
+ mục đích sử dụng
+ số tiền đề nghị
+ thời hạn hoàn ứng
+ dự toán/lịch trình nếu policy yêu cầu
+ bằng chứng phê duyệt của cấp trên
```

Hệ thống chỉ phát hiện sự hiện diện của vùng chữ ký hoặc bằng chứng phê duyệt.
Không được tuyên bố đã xác thực danh tính người ký nếu chưa tích hợp chữ ký số
hoặc dữ liệu xác thực tương ứng.

### 6.2. Rule

- Xác định người đề nghị, bộ phận và dự án nếu có.
- Mục đích tạm ứng không được để trống.
- Số tiền đề nghị phải đọc được rõ ràng.
- Phải có thời hạn hoàn ứng.
- Phải có bằng chứng phê duyệt theo policy.
- Kiểm tra khoản tạm ứng cũ chưa quyết toán.
- Kiểm tra số tiền với hạn mức thẩm quyền.
- Không tự động giải ngân.

### 6.3. Kết quả

```text
READY_FOR_APPROVAL  Hồ sơ đủ để cấp có thẩm quyền xem xét
REQUEST_INFO        Thiếu dữ kiện hoặc tài liệu
ESCALATE            Vượt hạn mức hoặc vi phạm policy rõ ràng
```

## 7. Workflow quyết toán chi phí

### 7.1. Đầu vào

```text
Giấy thanh toán tạm ứng/đề nghị hoàn trả chi phí
+ một hoặc nhiều bill, hóa đơn, vé và chứng từ
+ advance_id nếu nhân viên đã nhận tạm ứng
```

Evidence không được coi là tùy chọn một cách chung chung. Chứng từ chỉ được
phép thiếu nếu loại chi phí đó thuộc trường hợp khoán hoặc ngoại lệ đã được
PolicyConfig cho phép.

### 7.2. Ví dụ một hồ sơ công tác

```text
ExpenseCase: Công tác Hà Nội
├── Vé máy bay: 3.200.000 VND
├── Khách sạn: 2.400.000 VND
├── Taxi: 480.000 VND
├── Tiếp khách: 1.800.000 VND
└── Phí cầu đường: 120.000 VND
```

### 7.3. Rule

- OCR, Confidence Gate và extract từng chứng từ độc lập.
- Mỗi khoản khai báo phải dẫn đến evidence hoặc ngoại lệ policy.
- Phát hiện chứng từ trùng trong cùng hồ sơ và trong lịch sử.
- Tổng trên giấy quyết toán phải khớp tổng khoản chi khai báo.
- Tổng khoản chi được chấp nhận phải được tính lại bằng code.
- Với `ADVANCE_SETTLEMENT`, hồ sơ phải liên kết khoản tạm ứng trước đó.
- Không dùng LLM để cộng tiền hoặc quyết định số tiền phải thanh toán.

### 7.4. Đối chiếu dòng tiền

```text
A = số tiền đã tạm ứng
E = tổng chi phí được chấp nhận
D = E - A
```


| Điều kiện              | Kết quả                                |
| ---------------------- | -------------------------------------- |
| `D = 0`                | Quyết toán vừa đủ.                     |
| `D > 0`                | Công ty thanh toán thêm `D`.           |
| `D < 0`                | Nhân viên hoàn lại `abs(D)`.           |
| Không có khoản tạm ứng | Công ty hoàn lại `E` nếu hồ sơ hợp lệ. |


## 8. Phân chia trách nhiệm kỹ thuật


| Công việc                                  | Thành phần xử lý               |
| ------------------------------------------ | ------------------------------ |
| Đọc text, bảng, bbox và confidence         | OCR tool/API                   |
| Gom word confidence thấp theo block        | Python                         |
| Đánh giá block OCR còn dùng được hay không | Kimi Confidence Agent          |
| Phân loại tài liệu                         | LLM với JSON schema            |
| Trích xuất dữ kiện theo từng file          | LLM với Pydantic validation    |
| Ghép tên hàng hoặc loại chi phí gần nghĩa  | LLM đề xuất                    |
| Cộng tổng tiền                             | Python `Decimal`               |
| Đối chiếu tạm ứng và thực chi              | Python                         |
| Kiểm tra deadline, trùng lặp và hạn mức    | Python + PolicyConfig/database |
| Quyết định cuối                            | Decision Guard và con người    |


LLM không được tự quyết định hồ sơ pass, tự sửa số tiền hoặc tự điền dữ kiện
thiếu từ một chứng từ khác.

## 9. Chiến lược gọi LLM

Với `N` evidence:

1. OCR mỗi file đúng một lần.
2. Chỉ gọi Confidence Agent cho file có candidate confidence thấp.
3. Sau khi file `CLEAR`, gọi Document Extraction để tạo `DocumentFact`.
4. Policy chỉ nhận structured JSON, không nhận lại toàn bộ ảnh.
5. Chỉ dùng một lời gọi cấp case nếu cần phân loại ngữ nghĩa hoặc ghép dữ liệu
  giữa các document facts.

Không nên đưa toàn bộ raw OCR của một chuyến công tác có nhiều bill vào một
prompt lớn. Cách đó khó kiểm soát coverage, tốn token và dễ trộn dữ liệu giữa
các chứng từ.

## 10. Bộ testcase mục tiêu


| ID   | Loại hồ sơ | Tình huống                             | Kỳ vọng                    |
| ---- | ---------- | -------------------------------------- | -------------------------- |
| TC01 | Kiểm kê    | Hóa đơn và phiếu nhập kho khớp         | `PASS`                     |
| TC02 | Kiểm kê    | Lệch số lượng giữa hai nguồn           | `ESCALATE`                 |
| TC03 | Kiểm kê    | Phiếu nhập kho có field quan trọng mờ  | `REQUEST_INFO`             |
| TC04 | Kiểm kê    | Chỉ có hóa đơn, thiếu nguồn nhận hàng  | `REQUEST_INFO`             |
| TC05 | Tạm ứng    | Đủ thông tin và bằng chứng phê duyệt   | `READY_FOR_APPROVAL`       |
| TC06 | Tạm ứng    | Thiếu mục đích                         | `REQUEST_INFO`             |
| TC07 | Tạm ứng    | Thiếu bằng chứng phê duyệt             | `REQUEST_INFO`             |
| TC08 | Tạm ứng    | Số tiền vượt hạn mức hiện tại          | `ESCALATE`                 |
| TC09 | Tạm ứng    | Còn khoản tạm ứng cũ chưa quyết toán   | Theo PolicyConfig          |
| TC10 | Quyết toán | Nhiều bill, tổng chi bằng số tạm ứng   | `PASS`                     |
| TC11 | Quyết toán | Thực chi lớn hơn số tạm ứng            | `PASS`, công ty trả thêm   |
| TC12 | Quyết toán | Thực chi nhỏ hơn số tạm ứng            | `PASS`, nhân viên hoàn lại |
| TC13 | Quyết toán | Tổng trên giấy khác tổng evidence      | `ESCALATE`                 |
| TC14 | Quyết toán | Một khoản khai báo không có evidence   | `REQUEST_INFO`             |
| TC15 | Quyết toán | Một bill xuất hiện hai lần             | `ESCALATE`                 |
| TC16 | Quyết toán | MST hoặc tổng tiền không đọc chắc chắn | `REQUEST_INFO`             |
| TC17 | Hoàn trả   | Nhân viên tự chi, không có advance_id  | `EMPLOYEE_REIMBURSEMENT`   |


## 11. Kế hoạch triển khai

### Giai đoạn 1: Chuẩn hóa domain

- Tạo `ExpenseCase`, `CaseType` và `SettlementType`.
- Tạo `ExpenseItem`, `DocumentFact`, `AdvanceReference`.
- Tạo `ReconciliationResult`, `ApprovalContext` và `CaseDecision`.
- Giữ khả năng đọc các hồ sơ cũ trong `processing.json`.

### Giai đoạn 2: Thiết kế lại UI nhân viên

- Thêm segmented control chọn loại hồ sơ.
- Hiển thị form riêng theo `case_type`.
- Cho phép tải nhiều evidence cho một hồ sơ quyết toán.
- Hiển thị tổng số file, tổng tiền khai báo và khoản tạm ứng liên quan.
- Không yêu cầu người dùng hiểu thuật ngữ kỹ thuật của agent.

### Giai đoạn 3: Shared Document Pipeline

- Tái sử dụng Mistral OCR và word-block mapper.
- Chạy Confidence Gate riêng từng evidence.
- Tạo `DocumentFact` sau khi evidence đã `CLEAR`.
- Giữ source reference đến page/block gốc.

### Giai đoạn 4: Inventory Case Handler

- Di chuyển policy kiểm kê hiện tại thành handler riêng.
- Giữ Conflict Agent chỉ cho các file đã qua Quality Gate.
- Chuẩn bị mở rộng từ đối chiếu hai nguồn sang ba nguồn.

### Giai đoạn 5: Advance Request Handler

- Extract số tiền, mục đích và deadline.
- Kiểm tra approval evidence.
- Thêm PolicyConfig cho hạn mức và tạm ứng cũ.
- Không tự động giải ngân.

### Giai đoạn 6: Expense Settlement Handler

- Trích xuất nhiều expense item từ nhiều evidence.
- Phát hiện evidence trùng.
- Tính tổng bằng `Decimal`.
- Đối chiếu tổng giấy đề nghị, tổng chứng từ và khoản tạm ứng.
- Sinh số tiền công ty trả thêm hoặc nhân viên hoàn lại.

### Giai đoạn 7: Decision Guard và UI kế toán

- Ánh xạ findings sang `PASS`, `REQUEST_INFO`, `ESCALATE`.
- Hiển thị expense lines và evidence tương ứng.
- Hiển thị công thức quyết toán và chênh lệch.
- Cho phép kế toán xác nhận, từ chối hoặc ghi đè có lý do.
- Ghi đầy đủ audit event.

### Giai đoạn 8: Verify và demo

- Tạo Verify harness chạy ít nhất bốn testcase bằng một lệnh hoặc một nút.
- Có happy path và exception path cho kiểm kê và quyết toán.
- In bảng pass/fail kèm timestamp.
- Chuẩn bị dữ liệu mới để giám khảo tự tải lên.




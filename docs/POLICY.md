# InvoiceReferee - Policy thực thi v1

## 1. Mục tiêu và phạm vi

Tài liệu này là nguồn chính sách chuẩn để triển khai `PolicyEngine` và
`DecisionGuard`. Policy áp dụng cho:

- hóa đơn điện tử;
- bill, biên lai, phiếu thanh toán POS và chứng từ nhân viên chụp;
- bằng chứng thanh toán ngân hàng hoặc ví điện tử;
- description/report do nhân viên cung cấp;
- PO, phiếu kiểm kê, phiếu nhận hàng và biên bản nghiệm thu;
- dữ liệu nội bộ như hồ sơ công ty, lịch sử chứng từ và hạn mức phê duyệt.

Policy hỗ trợ kiểm tra và chuẩn bị dữ liệu kế toán. `AUTO_PROCESS` chỉ có nghĩa
là hồ sơ đủ điều kiện chuyển sang bước nhập liệu hoặc quy trình phê duyệt tiếp
theo; Agent không tự chuyển tiền và không thay thế quyền phê duyệt của con người.

Đây là policy giả lập cho dự án. Các giá trị như MST công ty, hạn mức và thời hạn
nộp phải được cấu hình lại khi áp dụng cho doanh nghiệp thật.

## 2. Nguyên tắc bắt buộc

1. Không mã hóa cứng theo tên nhà hàng, mẫu bill hoặc mã test case.
2. Mọi dữ kiện phải giữ `value`, `confidence`, `source_ref` và vị trí nguồn nếu có.
3. Trường không đọc được phải là `null`; LLM không được tự điền bằng suy đoán.
4. Description là lời khai về bối cảnh kinh doanh, không phải bằng chứng thanh toán.
5. LLM/VLM được phép hiểu tài liệu đa dạng, nhưng không được ra quyết định cuối.
6. Tiền, số lượng, ngày, trùng lặp, hạn mức và thứ tự quyết định phải do code tất định xử lý.
7. Thiếu hoặc mâu thuẫn dữ kiện quan trọng dẫn đến `REQUEST_INFO`, không phải tự động từ chối.
8. Dữ kiện đã rõ nhưng sai policy, đáng ngờ hoặc vượt quyền dẫn đến `ESCALATE`.
9. Chỉ `AUTO_PROCESS` khi mọi phép kiểm tra bắt buộc đã `PASS` hoặc `NOT_APPLICABLE`.
10. Mọi bước phải truy vết được qua `evidence_refs`, `rule_ids` và audit log.

## 3. Vai trò của từng thành phần

| Thành phần | Được làm | Không được làm |
| --- | --- | --- |
| OCR/Vision tool | Đọc text, bbox, confidence, loại tài liệu và ứng viên dữ kiện | Kết luận hợp lệ hoặc duyệt chi |
| LLM extractor | Ánh xạ dữ liệu đa dạng vào schema mềm, trích business context | Bịa dữ kiện, sửa số tiền, bỏ qua nguồn |
| LLM policy planner | Đề xuất loại chi phí và các check cần chạy từ `CHECK_REGISTRY` | Tạo check mới hoặc bỏ check bắt buộc |
| Tool nội bộ | Tra hồ sơ công ty, lịch sử, PO, kiểm kê, thanh toán | Ra quyết định cuối |
| Check engine | Chạy phép kiểm tra tất định và trả `CheckResult[]` | Viết giải thích không có bằng chứng |
| LLM reasoning | Tóm tắt vấn đề, tạo câu hỏi rõ ràng và đề xuất người xử lý | Ghi đè `CheckResult` |
| Decision guard | Áp dụng đúng thứ tự ưu tiên và tạo `Decision` | Bỏ qua check bắt buộc |
| Human | Bổ sung dữ kiện, phê duyệt ngoại lệ, dừng hoặc override có lý do | Xóa lịch sử quyết định cũ |

## 4. Hợp đồng dữ liệu tối thiểu

### 4.1. Đầu vào `Submission`

```json
{
  "case_id": "CASE-001",
  "submitted_at": "2026-09-21T10:00:00+07:00",
  "submitted_by": "EMP-001",
  "description": "Tiếp khách công ty ABC cho dự án X",
  "evidence": [
    {
      "source_ref": "DOC-001",
      "mime_type": "image/jpeg",
      "declared_type": null
    }
  ]
}
```

`description` được phép rỗng ở tầng tiếp nhận, nhưng policy sẽ yêu cầu bổ sung nếu
không đủ business context. `evidence` được phép rỗng để Agent vẫn tạo hồ sơ và hỏi
đúng thông tin còn thiếu.

### 4.2. Dữ kiện chuẩn `Fact`

Mọi extractor phải trả dữ kiện theo cấu trúc tương đương:

```json
{
  "name": "total_amount",
  "value": 2500000,
  "normalized_value": 2500000,
  "confidence": 0.97,
  "source_ref": "DOC-001",
  "source_kind": "OCR",
  "bbox": [120, 640, 890, 710],
  "raw_text": "TONG CONG 2.500.000",
  "warnings": []
}
```

Các `source_kind` hợp lệ:

```text
STRUCTURED_DOCUMENT
OCR
VISION_MODEL
EMPLOYEE_DESCRIPTION
INTERNAL_SYSTEM
HUMAN_CONFIRMED
```

Không được chuyển dữ kiện từ `EMPLOYEE_DESCRIPTION` thành dữ kiện đã được chứng
từ xác nhận. Ví dụ, nhân viên khai 2.500.000 đồng chỉ tạo
`claimed_amount = 2500000`, không tự tạo `document.total_amount`.

### 4.3. Trạng thái phép kiểm tra

```text
PASS            Đã kiểm tra và đạt.
FAIL            Đã có bằng chứng rõ rằng vi phạm policy.
UNKNOWN         Thiếu, mờ, mâu thuẫn hoặc tool chưa trả được kết quả.
NOT_APPLICABLE  Không áp dụng cho hồ sơ này.
```

Mỗi `CheckResult` phải có tối thiểu:

```json
{
  "check_id": "CHECK_ARITHMETIC",
  "rule_id": "P05",
  "status": "UNKNOWN",
  "failure_class": "FACTUAL_UNKNOWN",
  "is_mandatory": true,
  "reason": "10 x 3.000.000 khác thành tiền 35.000.000",
  "evidence_refs": ["DOC-001"],
  "details": {
    "expected": 30000000,
    "actual": 35000000
  }
}
```

`failure_class` chỉ nhận một trong:

```text
FACTUAL_UNKNOWN
OUTSIDE_POLICY
SUSPICIOUS
BEYOND_AUTHORITY
SYSTEM_ERROR
null
```

## 5. Cấu hình policy

Khối YAML dưới đây là cấu hình mặc định mà code có thể chuyển thành `PolicyConfig`.
Giá trị doanh nghiệp không được rải trực tiếp trong check implementation.

<!-- POLICY_CONFIG_START -->
```yaml
policy_version: "1.0.0"
currency: VND

decision_actions:
  - AUTO_PROCESS
  - REQUEST_INFO
  - ESCALATE

thresholds:
  critical_fact_confidence: 0.85
  non_critical_fact_confidence: 0.60
  authority_amount_vnd: 50000000
  submission_window_days: 30
  arithmetic_tolerance_vnd: 1
  duplicate_similarity_review_threshold: 0.85

company_profile:
  legal_name: CONFIG_REQUIRED
  tax_codes: []

document_profiles:
  E_INVOICE:
    required_facts:
      - buyer_name
      - buyer_tax_code
      - seller_name
      - seller_tax_code
      - invoice_date
      - item_name
      - total_amount
      - template_number
      - serial_number
      - invoice_number
    conditional_required_facts:
      - fact: quantity
        when: item_type == GOODS
    optional_facts:
      - tax_authority_code
      - buyer_contact
      - buyer_address
      - seller_contact
      - seller_address
      - amount_in_words

  RECEIPT:
    required_facts:
      - merchant_name
      - transaction_date
      - total_amount
    optional_facts:
      - transaction_time
      - items
      - quantity
      - unit_price
      - discount
      - tax_amount
      - service_charge
      - payment_method

  PAYMENT_PROOF:
    required_facts:
      - transaction_date
      - total_amount
      - payer_or_payee
    optional_facts:
      - payment_reference
      - payment_method
    supporting_only: true

business_context:
  required_facts:
    - claimant_id
    - business_purpose
    - expense_category
  conditional_required_facts:
    - fact: client_or_project
      when: expense_category in [MEALS, TRAVEL, LODGING] or company_policy_requires_project == true

duplicate_keys:
  E_INVOICE:
    exact:
      - [seller_tax_code, serial_number, invoice_number]
      - [seller_tax_code, invoice_number, total_amount]
  RECEIPT:
    exact:
      - [merchant_name, transaction_date, total_amount, payment_reference]
      - [image_hash]
    probable:
      - [merchant_name, transaction_date, total_amount]
  PAYMENT_PROOF:
    exact:
      - [payment_reference]
      - [payer_or_payee, transaction_date, total_amount, image_hash]

prohibited_categories:
  - PERSONAL_EXPENSE
  - ALCOHOL_WHEN_NOT_ALLOWED

evidence_requirements:
  description_only_allowed_for_auto_process: false
  payment_proof_only_allowed_for_auto_process: false
  goods_requires_receiving_evidence: true
  services_requires_acceptance_when_configured: true

escalation_targets:
  OUTSIDE_POLICY: POLICY_OWNER
  SUSPICIOUS: INTERNAL_CONTROL
  BEYOND_AUTHORITY: FINANCE_MANAGER
```
<!-- POLICY_CONFIG_END -->

`CONFIG_REQUIRED` làm policy không sẵn sàng chạy production. Khi chưa cấu hình
MST công ty, `CHECK_BUYER_IDENTITY` phải là `UNKNOWN`, không được tự cho `PASS`.

## 6. Schema mềm cho bill đa dạng

Bill không bị ép phải có cùng layout hoặc cùng toàn bộ trường. Extractor tạo một
`FactGraph` gồm các fact đọc được và quan hệ giữa chúng. Policy chỉ yêu cầu:

- hồ sơ được phân loại vào một profile gần nhất;
- các fact tối thiểu của profile đó có đủ bằng chứng;
- các check bắt buộc của case đã chạy;
- trường có xuất hiện thì được giữ lại và đối chiếu, kể cả khi là optional.

LLM policy planner được chọn check trong `CHECK_REGISTRY`, nhưng code luôn hợp nhất
đề xuất đó với `mandatory_checks`. Công thức:

```text
checks_to_run = mandatory_checks(case_profile)
              UNION planner_suggested_checks
              UNION checks_required_by_available_facts
```

Planner không thể xóa `CHECK_DUPLICATE`, `CHECK_BUSINESS_CONTEXT`,
`CHECK_POLICY_CATEGORY`, `CHECK_ANOMALY`, `CHECK_AUTHORITY` và
`CHECK_EXPORT_READINESS`.

## 7. Xử lý confidence và OCR

1. OCR chạy trên toàn bộ ảnh và trả word/block cùng bbox, confidence.
2. Code ánh xạ block vào trường dữ kiện dự kiến.
3. Nếu confidence đạt ngưỡng của loại trường, tiếp tục chuẩn hóa.
4. Nếu confidence thấp, gửi crop có vùng lân cận cho VLM/LLM để xác định
   `CRITICAL`, `NON_CRITICAL` hoặc `UNKNOWN`.
5. Code ghi đè thành `CRITICAL` nếu block liên quan trường bắt buộc, identity,
   ngày, tiền, số lượng, đơn giá hoặc thành tiền.
6. `CRITICAL` hoặc `UNKNOWN` chưa được xác nhận dẫn đến
   `CHECK_EXTRACTION_QUALITY = UNKNOWN`.
7. `NON_CRITICAL` được phép đi tiếp nhưng phải lưu warning và audit.

VLM có thể đề xuất cách đọc lại block, nhưng đề xuất không tự động thay thế fact
quan trọng. Fact quan trọng chỉ được chấp nhận khi có nguồn có cấu trúc, nguồn độc
lập khớp nhau hoặc xác nhận của con người.

## 8. Check registry P01-P15

Tên `check_id` dưới đây là hợp đồng ổn định giữa check engine, policy engine,
decision guard, audit và test. Không đổi tên tùy theo loại bill.

| Rule | `check_id` | Thành phần thực hiện |
| --- | --- | --- |
| P01 | `CHECK_REQUIRED_FACTS` | Code + PolicyConfig |
| P02 | `CHECK_EXTRACTION_QUALITY` | Code trên output OCR/VLM |
| P03 | `CHECK_BUYER_IDENTITY` | Code + Company Profile tool |
| P04 | `CHECK_SELLER_IDENTITY` | Code + Vendor Master tool |
| P05 | `CHECK_ARITHMETIC` | Code dùng `Decimal` |
| P06 | `CHECK_DUPLICATE` | Code + Processed History tool |
| P07 | `CHECK_PAYMENT_STATUS` | Code + Payment History tool |
| P08 | `CHECK_BUSINESS_CONTEXT` | Code trên fact do LLM/hệ thống trích xuất |
| P09 | `CHECK_CROSS_SOURCE_CONSISTENCY` | Code; LLM chỉ ánh xạ ngữ nghĩa |
| P10 | `CHECK_EVIDENCE_SUFFICIENCY` | Code + PolicyConfig |
| P11 | `CHECK_POLICY_CATEGORY` | Code + PolicyConfig; LLM đề xuất category |
| P12 | `CHECK_SUBMISSION_WINDOW` | Code |
| P13 | `CHECK_AUTHORITY` | Code + PolicyConfig |
| P14 | `CHECK_ANOMALY` | Code/tool lịch sử và forensic |
| P15 | `CHECK_EXPORT_READINESS` | Code + schema hệ thống đích |

### P01 - Phân loại và đủ trường bắt buộc

`CHECK_REQUIRED_FACTS` do code thực hiện theo `document_profiles`.

- `PASS`: đủ mọi fact bắt buộc và điều kiện.
- `UNKNOWN`: thiếu fact, chưa rõ là hàng hóa hay dịch vụ, hoặc chưa phân loại được tài liệu.
- `NOT_APPLICABLE`: chỉ dùng cho evidence bổ sung không phải chứng từ chính.
- Khi `UNKNOWN`: `REQUEST_INFO / FACTUAL_UNKNOWN`.

Số lượng bắt buộc với hàng hóa; không bắt buộc với dịch vụ. Không được mặc định
bill thiếu item là sai nếu profile chỉ yêu cầu merchant, ngày và tổng tiền.

### P02 - Chất lượng trích xuất

`CHECK_EXTRACTION_QUALITY` do code đánh giá trên confidence, warning và provenance.

- Trường quan trọng rõ và đạt ngưỡng: `PASS`.
- Ảnh mờ, bị che, OCR lỗi hoặc hai extractor đọc khác nhau: `UNKNOWN`.
- Lỗi file/MIME khiến không thể trích xuất gì: `SYSTEM_ERROR`, không phải quyết định nghiệp vụ.

### P03 - Danh tính bên mua

`CHECK_BUYER_IDENTITY` dùng Company Profile tool.

- MST bên mua khớp một MST được cấu hình: `PASS`.
- MST trống, ghi "khách lẻ" hoặc không đọc được: `UNKNOWN / FACTUAL_UNKNOWN`.
- MST đọc rõ nhưng thuộc công ty khác: `FAIL / OUTSIDE_POLICY`.
- Với receipt không có trường bên mua: `NOT_APPLICABLE`, trừ khi policy doanh nghiệp yêu cầu.

### P04 - Danh tính bên bán/merchant

`CHECK_SELLER_IDENTITY` dùng fact và Vendor Master nếu có.

- Có seller/merchant truy vết được, không bị chặn: `PASS`.
- Không đọc được seller/merchant bắt buộc: `UNKNOWN`.
- Vendor bị chặn rõ ràng: `FAIL / OUTSIDE_POLICY`.

### P05 - Tính nhất quán số học

`CHECK_ARITHMETIC` phải dùng `Decimal`, không dùng số thực nhị phân.

```text
line_expected = quantity * unit_price - line_discount + line_tax_or_fee
subtotal_expected = sum(line_total)
grand_total_expected = subtotal - discount + tax + service_charge
```

- Chỉ kiểm tra công thức khi các toán hạng liên quan có mặt.
- Chênh lệch không quá `arithmetic_tolerance_vnd`: `PASS`.
- Dữ kiện đầy đủ nhưng phép tính không khớp: `UNKNOWN / FACTUAL_UNKNOWN`, vì
  Agent biết có mâu thuẫn nhưng chưa biết số nào đúng.
- Số tiền bằng chữ khác số tiền bằng số: `UNKNOWN / FACTUAL_UNKNOWN`.
- Thiếu item trên receipt nhưng tổng tiền rõ không tự động là lỗi số học.

### P06 - Trùng lặp

`CHECK_DUPLICATE` luôn chạy và tra Processed History.

- Chỉ so một exact/probable key khi tất cả thành phần trong key đều khác `null`.
- Khớp một `exact` key với hồ sơ đã xử lý và không có dữ kiện phản chứng:
  `FAIL / OUTSIDE_POLICY`.
- Chỉ khớp key `probable`, fuzzy text hoặc similarity vượt ngưỡng:
  `UNKNOWN / FACTUAL_UNKNOWN` để con người xác minh.
- Không tìm thấy trùng: `PASS`.
- History tool không truy cập được: `UNKNOWN`; không được mặc định là không trùng.

Ảnh giống nhau nhưng là nhiều trang của cùng một submission không được xem là hai
đề nghị chi. Duplicate được kiểm tra ở cấp chứng từ/giao dịch, không chỉ cấp file.

### P07 - Trạng thái thanh toán và dòng tiền

`CHECK_PAYMENT_STATUS` đối chiếu đề nghị chi với payment evidence/history.

- Chưa thanh toán hoặc đây là đề nghị hoàn ứng có bằng chứng phù hợp: `PASS`.
- Đã thanh toán toàn bộ nhưng bị gửi như yêu cầu chi mới: `UNKNOWN` và hỏi mục đích gửi lại.
- Số tiền chuyển khoản khác chứng từ mà không có giải thích: `UNKNOWN`.
- Không yêu cầu kiểm tra thanh toán cho loại luồng hiện tại: `NOT_APPLICABLE`.

### P08 - Business context

`CHECK_BUSINESS_CONTEXT` đối chiếu description với dữ liệu nhân viên/hệ thống.

- Có người chi, mục đích kinh doanh, loại chi và client/project khi áp dụng: `PASS`.
- Thiếu description hoặc thiếu một trường bắt buộc: `UNKNOWN / FACTUAL_UNKNOWN`.
- Description nêu rõ mục đích cá nhân: chuyển sang P11, không coi là thiếu context.

Hóa đơn điện tử đầy đủ vẫn phải có business context của nghiệp vụ đang yêu cầu
xử lý. Thiếu mục đích lần đầu luôn là `REQUEST_INFO`, không mặc định là vi phạm.

### P09 - Nhất quán giữa nhiều nguồn

`CHECK_CROSS_SOURCE_CONSISTENCY` so sánh các fact cùng nghĩa giữa invoice, bill,
description, payment, PO, phiếu kiểm kê, nhận hàng và nghiệm thu.

- Các giá trị vật chất khớp nhau: `PASS`.
- Invoice ghi 10 nhưng phiếu nhận ghi 8, hoặc số tiền chứng từ khác khai báo:
  `UNKNOWN / FACTUAL_UNKNOWN`.
- Khác biệt đã có bằng chứng hợp lệ như giao hàng từng phần và policy cho phép:
  `PASS` kèm warning/audit.

LLM được dùng để nhận ra hai nhãn có cùng ý nghĩa; phép so sánh giá trị cuối cùng
phải do code thực hiện.

### P10 - Đủ bằng chứng

`CHECK_EVIDENCE_SUFFICIENCY` dựa trên `evidence_requirements` và loại chi phí.

- Hàng hóa cần bằng chứng nhận hàng/kiểm kê khi policy yêu cầu.
- Dịch vụ cần nghiệm thu khi cấu hình yêu cầu.
- Description đơn lẻ không đủ để `AUTO_PROCESS`.
- Ảnh chuyển khoản đơn lẻ không đủ nếu chưa rõ item và mục đích.
- Thiếu evidence bắt buộc: `UNKNOWN / FACTUAL_UNKNOWN`.

### P11 - Danh mục ngoài quy định

`CHECK_POLICY_CATEGORY` so khớp loại chi với danh mục policy.

- Chi phí hợp lệ: `PASS`.
- Chi tiêu cá nhân, rượu bia bị cấm hoặc danh mục bị cấm khác đã xác định rõ:
  `FAIL / OUTSIDE_POLICY`.
- LLM chỉ đề xuất category. Nếu confidence phân loại thấp hoặc mô tả mơ hồ:
  `UNKNOWN`, không được tự kết luận vi phạm.

### P12 - Thời hạn nộp

`CHECK_SUBMISSION_WINDOW` tính theo ngày địa phương:

```text
age_days = date(submitted_at) - document_date
```

- `age_days <= submission_window_days`: `PASS`.
- Quá hạn và ngày đã rõ: `FAIL / OUTSIDE_POLICY`.
- Thiếu hoặc không đọc được ngày: `UNKNOWN / FACTUAL_UNKNOWN`.

### P13 - Thẩm quyền

`CHECK_AUTHORITY` so sánh tổng giá trị cần xử lý với hạn mức hiện hành.

- `amount <= authority_amount_vnd`: `PASS`.
- `amount > authority_amount_vnd`: `FAIL / BEYOND_AUTHORITY`.
- Tổng tiền chưa rõ: `UNKNOWN / FACTUAL_UNKNOWN`.

P13 chỉ quyết định chuyển cấp sau khi các dữ kiện và check nghiệp vụ khác đã đủ.
Một hồ sơ vừa thiếu dữ kiện vừa có số tiền khai báo vượt hạn mức vẫn cần hoàn thiện
dữ kiện trước khi chuyển phê duyệt.

### P14 - Bất thường/nghi vấn

`CHECK_ANOMALY` luôn chạy. Các tín hiệu gồm:

- ảnh có bằng chứng chỉnh sửa từ forensic tool;
- nhiều submission gần giống từ cùng người trong thời gian ngắn;
- số tiền lệch mạnh so với lịch sử cùng loại chi/vendor;
- vendor mới trong loại chi rủi ro;
- giao dịch ngoài giờ/ngày nghỉ kết hợp với tín hiệu khác;
- hàng hóa/dịch vụ không tương xứng với mục đích khai báo;
- cấu trúc chia nhỏ giao dịch để né hạn mức.

Kết quả:

- Tín hiệu mạnh từ tool hoặc dữ liệu lịch sử: `FAIL / SUSPICIOUS`.
- Chỉ có suy đoán ngữ nghĩa của LLM, không có dữ kiện hỗ trợ: `UNKNOWN`.
- Không có tín hiệu: `PASS`.

Không dùng một tín hiệu yếu như "giao dịch cuối tuần" làm căn cứ duy nhất để
`ESCALATE`.

### P15 - Sẵn sàng xuất dữ liệu kế toán

`CHECK_EXPORT_READINESS` kiểm tra payload đích có tối thiểu:

- ngày chứng từ;
- seller/merchant;
- tổng tiền và tiền tệ;
- loại chi phí;
- định danh duy nhất/fingerprint;
- business purpose;
- tax/fee nếu có, hoặc trạng thái `NOT_PRESENT`;
- source references.

Thiếu trường đích bắt buộc: `UNKNOWN / FACTUAL_UNKNOWN`.

## 9. Các check bắt buộc theo hồ sơ

| Check | E-invoice | Receipt/bill | Payment proof | Description only |
| --- | --- | --- | --- | --- |
| P01 Required facts | Bắt buộc | Bắt buộc | Bắt buộc | Không áp dụng cho document |
| P02 Extraction quality | Bắt buộc | Bắt buộc | Bắt buộc | Không áp dụng |
| P03 Buyer identity | Bắt buộc | Theo cấu hình | Theo cấu hình | Không áp dụng |
| P04 Seller identity | Bắt buộc | Bắt buộc | Theo dữ liệu | Không áp dụng |
| P05 Arithmetic | Khi đủ toán hạng | Khi đủ toán hạng | Không áp dụng | Không áp dụng |
| P06 Duplicate | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc ở cấp submission |
| P07 Payment status | Bắt buộc | Bắt buộc | Bắt buộc | Theo luồng |
| P08 Business context | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| P09 Cross-source | Khi có từ 2 nguồn | Khi có từ 2 nguồn | Khi có từ 2 nguồn | Khi có dữ liệu hệ thống |
| P10 Evidence | Theo loại chi | Theo loại chi | Bắt buộc | Luôn `UNKNOWN` nếu không có evidence |
| P11 Policy category | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| P12 Submission window | Bắt buộc | Bắt buộc | Bắt buộc | Chưa có ngày chứng từ thì `UNKNOWN` |
| P13 Authority | Bắt buộc | Bắt buộc | Bắt buộc | Dùng claimed amount nhưng không thể auto-pass |
| P14 Anomaly | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| P15 Export readiness | Bắt buộc | Bắt buộc | Bắt buộc | Luôn `UNKNOWN` nếu thiếu chứng từ |

## 10. Decision guard

### 10.1. Thứ tự quyết định

Decision guard không dùng nội dung giải thích của LLM để thay đổi kết quả check.
Nó áp dụng thứ tự sau:

```text
1. Pipeline hoặc audit store lỗi nghiêm trọng
   -> SYSTEM_ERROR, không phát hành quyết định nghiệp vụ.

2. Có FAIL / OUTSIDE_POLICY đã được xác nhận
   -> ESCALATE / OUTSIDE_POLICY.

3. Có FAIL / SUSPICIOUS với bằng chứng đủ mạnh
   -> ESCALATE / SUSPICIOUS.

4. Có UNKNOWN bắt buộc hoặc FACTUAL_UNKNOWN chưa giải quyết
   -> REQUEST_INFO / FACTUAL_UNKNOWN.

5. Có FAIL / BEYOND_AUTHORITY và không còn UNKNOWN bắt buộc
   -> ESCALATE / BEYOND_AUTHORITY.

6. Mọi check bắt buộc là PASS hoặc NOT_APPLICABLE
   -> AUTO_PROCESS.

7. Trường hợp còn lại
   -> REQUEST_INFO / FACTUAL_UNKNOWN.
```

Một vi phạm rõ như MST công ty khác hoặc duplicate chính xác không cần hỏi thêm
các dữ kiện không thể làm thay đổi vi phạm đó. Decision vẫn phải trả toàn bộ
`findings`, kể cả finding phụ.

### 10.2. Mã giả có thể triển khai

```python
def decide(checks: list[CheckResult]) -> Decision:
    if has_system_failure(checks):
        raise ReviewSystemError()

    if has_confirmed(checks, "OUTSIDE_POLICY"):
        return escalate("OUTSIDE_POLICY", primary_finding(checks))

    if has_confirmed(checks, "SUSPICIOUS"):
        return escalate("SUSPICIOUS", primary_finding(checks))

    if has_mandatory_unknown(checks):
        return request_info(primary_unknown(checks))

    if has_confirmed(checks, "BEYOND_AUTHORITY"):
        return escalate("BEYOND_AUTHORITY", primary_finding(checks))

    if all_mandatory_resolved(checks):
        return auto_process(checks)

    return request_info(primary_unresolved(checks))
```

`has_confirmed` chỉ nhận `CheckResult.status == FAIL` và có `evidence_refs`.
Không được coi output LLM đơn lẻ là finding đã xác nhận.

## 11. Quy tắc tạo câu hỏi và chuyển cấp

`REQUEST_INFO` phải hỏi đúng người có thể bổ sung fact:

- thiếu purpose/client/project: hỏi nhân viên;
- thiếu/không rõ giá trị trên ảnh: hỏi nhân viên hoặc kế toán kèm crop liên quan;
- thiếu nhận hàng: hỏi kho/mua hàng/chủ dự án;
- payment status chưa rõ: hỏi kế toán thanh toán.

`ESCALATE` dùng target từ config:

- `OUTSIDE_POLICY`: chủ policy hoặc kế toán phụ trách;
- `SUSPICIOUS`: kiểm soát nội bộ;
- `BEYOND_AUTHORITY`: quản lý tài chính.

Câu hỏi phải nêu giá trị đang có, giá trị xung đột và yêu cầu xác nhận cụ thể.
Không dùng câu chung chung như "vui lòng kiểm tra lại".

## 12. Bộ 15 test case chấp nhận bắt buộc

Các case dưới đây là hợp đồng acceptance tối thiểu. Việc triển khai phải tạo kết
quả từ fact và rule, tuyệt đối không rẽ nhánh theo `case_id`.

| Mã | Tình huống | Check quyết định | Kết quả bắt buộc |
| --- | --- | --- | --- |
| AT01 | E-invoice hàng hóa hợp lệ + description/report đầy đủ | P01-P15 đạt | `AUTO_PROCESS` |
| AT02 | E-invoice dịch vụ hợp lệ, không có quantity, context đầy đủ | P01 áp dụng điều kiện dịch vụ; các check đạt | `AUTO_PROCESS` |
| AT03 | E-invoice hợp lệ nhưng thiếu business purpose/client-project cần thiết | P08 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT04 | E-invoice thiếu serial, invoice number hoặc trường bắt buộc khác | P01 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT05 | Bill ăn uống rõ + description tiếp khách + payment khớp | P01, P07-P09 đạt | `AUTO_PROCESS` |
| AT06 | Bill cà phê rõ + description họp dự án + payment khớp | P01, P07-P09 đạt | `AUTO_PROCESS` |
| AT07 | Bill mờ hoặc OCR không đọc được ngày/tổng tiền quan trọng | P02 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT08 | Bill có subtotal, discount, tax/service charge không khớp tổng | P05 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT09 | E-invoice 10 mặt hàng + phiếu kiểm kê/nhận hàng 10, tiền khớp | P09, P10 đạt | `AUTO_PROCESS` |
| AT10 | E-invoice 10 mặt hàng nhưng phiếu kiểm kê/nhận hàng ghi 8 | P09 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT11 | E-invoice và report xung đột số tiền hoặc trạng thái nghiệm thu | P09/P10 `UNKNOWN` | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT12 | Hóa đơn có tín hiệu chỉnh sửa hoặc mẫu chia nhỏ giao dịch có bằng chứng | P14 `FAIL` | `ESCALATE / SUSPICIOUS` |
| AT13 | Chỉ có description "tiếp khách ABC tối qua hết 2.500.000đ" | P08/P10/P15 chưa đủ | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT14 | Identity hóa đơn trùng chính xác hồ sơ đã xử lý | P06 `FAIL` | `ESCALATE / OUTSIDE_POLICY` |
| AT15 | Hóa đơn hoàn toàn hợp lệ nhưng tổng tiền trên 50 triệu | P13 `FAIL`, không còn unknown | `ESCALATE / BEYOND_AUTHORITY` |

## 13. Test case biên bắt buộc nên có

| Mã | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| AT16 | MST bên mua rõ nhưng thuộc công ty khác | `ESCALATE / OUTSIDE_POLICY` |
| AT17 | Chi phí cá nhân hoặc danh mục bị cấm đã rõ | `ESCALATE / OUTSIDE_POLICY` |
| AT18 | Chứng từ nộp sau 30 ngày, ngày tháng rõ | `ESCALATE / OUTSIDE_POLICY` |
| AT19 | Chỉ có ảnh chuyển khoản, chưa rõ item và purpose | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT20 | Số tiền bằng chữ khác số tiền bằng số | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT21 | Duplicate chỉ là fuzzy/probable, chưa đủ exact key | `REQUEST_INFO / FACTUAL_UNKNOWN` |
| AT22 | Vendor bị chặn trong Vendor Master | `ESCALATE / OUTSIDE_POLICY` |
| AT23 | Hóa đơn hợp lệ nhưng History tool lỗi | `REQUEST_INFO / FACTUAL_UNKNOWN` |

## 14. Điều kiện bất biến để viết unit test

```text
INVARIANT-01: Không có evidence không bao giờ AUTO_PROCESS.
INVARIANT-02: Có mandatory UNKNOWN không bao giờ AUTO_PROCESS.
INVARIANT-03: Exact duplicate không bao giờ AUTO_PROCESS.
INVARIANT-04: MST bên mua thuộc công ty khác không bao giờ AUTO_PROCESS.
INVARIANT-05: OUTSIDE_POLICY đã xác nhận luôn ESCALATE.
INVARIANT-06: SUSPICIOUS đã xác nhận luôn ESCALATE.
INVARIANT-07: Vượt hạn mức chỉ ESCALATE sau khi không còn mandatory UNKNOWN.
INVARIANT-08: LLM lỗi vẫn phải tạo quyết định an toàn từ check engine.
INVARIANT-09: Optional fact thiếu không tự tạo REQUEST_INFO.
INVARIANT-10: Quantity thiếu ở dịch vụ không làm P01 UNKNOWN.
INVARIANT-11: Quantity thiếu ở hàng hóa làm P01 UNKNOWN.
INVARIANT-12: Description amount không được thay document amount.
INVARIANT-13: Mọi FAIL/UNKNOWN phải có reason và evidence_refs/source_refs.
INVARIANT-14: Human override không xóa quyết định và audit cũ.
INVARIANT-15: Không có nhánh xử lý dựa trên case_id hoặc tên file fixture.
```

## 15. Đầu ra quyết định

```json
{
  "action": "REQUEST_INFO",
  "uncertainty_type": "FACTUAL_UNKNOWN",
  "primary_check_id": "CHECK_BUSINESS_CONTEXT",
  "reason": "Hồ sơ chưa có mục đích kinh doanh",
  "question": "Khoản chi 2.500.000 đồng phục vụ mục đích kinh doanh nào và liên quan khách hàng/dự án nào?",
  "target": "EMPLOYEE",
  "policy_rule_ids": ["P08"],
  "evidence_refs": ["CLAIM-001"],
  "findings": [],
  "policy_version": "1.0.0",
  "decided_at": "2026-09-21T10:05:00+07:00"
}
```

Quy tắc đầu ra:

- `AUTO_PROCESS`: `uncertainty_type`, `question`, `target` là `null`.
- `REQUEST_INFO`: `uncertainty_type = FACTUAL_UNKNOWN`, bắt buộc có câu hỏi và target.
- `ESCALATE`: uncertainty là `OUTSIDE_POLICY`, `SUSPICIOUS` hoặc `BEYOND_AUTHORITY`.
- Luôn trả `policy_version`, rule/check liên quan và nguồn bằng chứng.
- Dữ liệu chuẩn hóa để nhập kế toán chỉ được phát hành khi action là `AUTO_PROCESS`;
  các action khác có thể trả bản nháp nhưng phải gắn `not_ready_for_posting = true`.

## 16. Audit và đánh giá lại

Tối thiểu phải ghi:

```text
CASE_CREATED
DOCUMENT_EXTRACTED
FACT_NORMALIZED
CHECK_PLANNED
CHECK_COMPLETED
LLM_ASSESSMENT_CREATED hoặc LLM_FALLBACK_USED
DECISION_GUARD_APPLIED
DECISION_MADE
INFO_REQUESTED hoặc ESCALATED
HUMAN_CONFIRMED, STOPPED hoặc OVERRIDDEN nếu có
```

Khi nhận dữ kiện mới, hệ thống tạo version mới của `ReviewCase`, chạy lại các check
bị ảnh hưởng và Decision Guard. Không sửa hoặc xóa quyết định trước đó.

Nguyên tắc cuối cùng:

> Chưa biết thì hỏi. Biết rõ nhưng sai policy, đáng ngờ hoặc vượt quyền thì chuyển.
> Chỉ tự động xử lý khi dữ kiện đầy đủ, check bắt buộc đã đạt và audit còn nguyên vẹn.

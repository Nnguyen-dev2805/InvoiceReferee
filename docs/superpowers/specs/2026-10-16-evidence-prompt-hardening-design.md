# Thiết kế củng cố prompt và đường tiêu thụ chứng cứ

Ngày 16/10/2026. **IMPLEMENTED — nghiệm thu được ghi riêng, không suy từ thiết kế.**
Xem [acceptance report](../../final/reviews/2026-10-16-evidence-prompt-hardening-acceptance.md)
cho kết quả, các gate chưa đạt và giới hạn dữ liệu; không coi nhãn này là release PASS.

## 1. Mục tiêu và nguồn quyết định

Lấy hướng dẫn nghiệp vụ cụ thể của Hoangha, giữ cơ chế kiểm chứng nguồn của main,
đóng các khoảng trống giữa prompt, payload, parser, matching và consumer tài chính.
Không sao chép nguyên pipeline Hoangha hoặc đổi model đang cấu hình.

Người dùng yêu cầu lập plan sau lượt so sánh prompt. Các lựa chọn kỹ thuật trong
tài liệu này là đề xuất của người lập plan, không phải một lần chốt policy mới.
Nguồn thẩm quyền: [contracts §12](../../final/IMPLEMENTATION_CONTRACTS.md#12-pipeline-chứng-cứ--dto-và-interface-chốt-14102026),
[thiết kế hiện hành](../../final/ARCHITECTURE_AND_EVALUATION.md), AGENTS.md.

## 2. Bằng chứng tại thời điểm lập plan

- Main: `08acde6a033b195f296c0f335c31e5d042375f2c`; Hoangha:
  `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Hai worktree sạch trước khi viết.
- CodeGraph xác định project main; báo up to date nhưng engine cũ, không lộ
  generation ID/coverage API. Tier **Verify**, coverage **UNKNOWN**; các nhận định
  vật chất dưới đây được kiểm bằng source hiện tại, không dựa vào index completeness.
- `evidence/ocr_quality.py::review_ocr_quality`: prompt không mô tả assessment;
  parser mặc định field thiếu, serializer không gửi ngữ cảnh toàn tài liệu.
- `evidence/extraction.py::extract_document`: bảo toàn quote/ngày/tên nhiều dòng,
  nhưng dùng một hướng dẫn dòng chi cho mọi loại chứng từ.
- `evidence/extraction.py::_call_with_one_repair`: gọi lại cùng system/user;
  chưa gửi phản hồi lỗi hay diagnostic; JSON sai shape không dùng repair này.
- `evidence/matching.py::resolve_evidence_suggestions`: không dùng `documents`
  để tạo payload; chỉ đổi links, chưa dựng lại rows/findings/allocation.
- `reconciliation/admission.py::_match_expense_documents`: ghép lại bằng invoice
  refs, không tiêu thụ liên kết đã xác nhận trong report; `_invoice_binding` có
  điều kiện danh tính riêng, phải giữ độc lập.
- `workflow/service.py::_reusable_report`: kiểm digest set nhưng chưa pin prompt
  hoặc profile; `_evidence_basis_current` cũng mới so nguồn.
- Prompt conflict nhận hàng ở Hoangha thuộc `process_case`, không phải mọi lượt
  quyết toán UC03; đưa workflow nhận hàng sang main nằm ngoài plan này.

Paths Python ở mục này tương đối với `src/invoice_referee/`. Lượt lập plan không
chạy pytest/provider và không suy ra chất lượng model từ độ dài prompt.

## 3. Ranh giới giữ nguyên

- PDF/ảnh đi OCR; không khôi phục native-text bypass, không thêm DOCX.
- `FOUND` là candidate có nguồn, chưa phải tiền đã xác minh. Quote/page/source
  phải đúng; không dùng policy/context/gold để bù số còn thiếu.
- Thiếu khác 0; không sửa số in sai thành số tính lại; không tự tạo người trả.
- Employee-paid, S = E − A − P + R; quyền demo 8/4/20 triệu, B ngoài phạm vi.
- Ghi nhận ứng/hoàn vẫn qua command đúng quyền; đọc/ghép không ghi money event.
- Giữ taxonomy 17 loại, role map, ngưỡng candidate 0.85; matcher rule giữ
  trọng số/ngưỡng 0.50/0.75 và promotion tối thiểu 0.90 như contracts §12.
- Một repair call cho **một read pass/root**, chia sẻ qua RunBudget; không phải
  mỗi tài liệu một lượt. Không lưu quota này vĩnh viễn qua lần đọc hợp lệ mới.
- Giữ input cap 120.000 ký tự, output cap 20.000, 12 LLM attempts, 10 OCR
  attempts và deadline 90 giây; không nới giới hạn để làm demo xanh.
- Không thêm framework/prompt registry bên ngoài, phụ thuộc, DB migration, UI
  redesign, policy thuế mới, inventory workflow hoặc thay toàn bộ evaluation.
- Không sửa/xóa PDF, context, gold hay DB người dùng để chữa kết quả.

## 4. Thiết kế đề xuất

### 4.1. Prompt và cấu trúc output

Một module Python `evidence/prompts.py` chứa hướng dẫn dùng chung và đoạn riêng
theo type; tên field lấy từ profile do code sở hữu. Hướng dẫn bằng tiếng Việt,
field/enum giữ tiếng Anh. Các ví dụ là synthetic, không dùng đáp án TC01–TC25.
OCR là dữ liệu không tin cậy: chỉ dẫn nằm trong chứng từ không được phép đổi vai,
schema, policy hoặc ra lệnh ghi tiền.

Classification giữ batch; mô tả dấu hiệu phân biệt hóa đơn/POS/vé/chuyển khoản/
phiếu thu/giấy quyết toán. Không đổi role bằng lời model, không đoán UNKNOWN.
Extraction giữ `fields` và `line_items` với field-state-value-quote-page.

| Loại | Hướng dẫn trọng tâm |
| --- | --- |
| SETTLEMENT_FORM | declared_advance là số khai; printed_return là nhân viên phải hoàn, printed_reimbursement là công ty phải chi thêm; không tính thay nguồn; giữ lý do thiếu chứng từ, bỏ dòng tổng khỏi cost rows |
| E_INVOICE | subtotal/tax/discount/service_charge/total; buyer person khác company buyer; rows giữ description/quantity/unit_price/line_amount khi có |
| PAYMENT_PROOF, CARD_SLIP | payer/payee, amount theo profile, reference, event_at, status; phân biệt pending/failed/completed; không thêm thời gian |
| COLLECTION_RECEIPT | bên nộp/bên thu, số phiếu/ngày/số tiền/lý do/xác nhận trên nguồn; chữ ký không tự tạo giao dịch |
| HOTEL_RECEIPT, TRANSPORT_TICKET | field riêng theo profile; không ép VAT; không biến ngày hóa đơn thành ngày công tác |
| Supporting/OTHER/UNKNOWN | chỉ field profile; không tự biến chứng từ hỗ trợ thành chi phí gốc hoặc tạo workflow mua hàng |

### 4.2. Confidence có ngữ cảnh và validator bắt buộc

Giữ một batch/root. Gửi riêng từng nguồn với OCR của chính nguồn đó, candidate,
low-word offsets/confidence và block lân cận; tuyệt đối không trộn context tài
chính hoặc extraction từ nguồn khác. Không có candidate thì không gọi model.

Assessment bắt buộc khai `candidate_id`, `importance`, `quality_state`,
`review_action`, `requires_verification`, `canonical_fields`, `reason`;
`observed_text`/`human_question` optional. Kiểm enum, kiểu bool, ID đúng một lần;
UNKNOWN vẫn biểu diễn được và dẫn tới chưa xác minh, không giả PASS.

Code chặn theo field/low-word overlap khi offsets đủ tin cậy. Nhãn/footer mờ
không hạ tổng tiền rõ ở vị trí khác trong cùng block. Giá trị trọng yếu thực sự
không chắc hoặc review kỹ thuật lỗi ở vùng liên quan vẫn unresolved. Khi không
đủ offset để tách nhãn khỏi giá trị, dùng fallback thận trọng; không gán mọi
field cả tài liệu thành lỗi. Không miễn critical field chỉ vì model tự tin.

### 4.3. Structured repair

Một helper dùng chung cho bốn stage nhận validator xác định shape tương ứng.
JSON lỗi hoặc shape/enum sai được dùng chung tối đa một repair slot trong
RunBudget. Lượt repair có lỗi validation và phản hồi trước giới hạn kích thước,
không chỉ lặp lại prompt cũ. Transport/budget/deadline không phải schema repair.

Quote không hỗ trợ giá trị, số học sai hoặc thiếu chứng từ là kết quả chứng cứ
cần giữ, không phải lý do bảo model sửa giá trị cho khớp. Nếu repair vượt input
cap, giữ unresolved, không cắt mất nguồn để gọi tiếp. Không export raw response,
OCR hoặc quote lên LangSmith; telemetry giữ reason code/hash/counter.

### 4.4. Matching và projection thống nhất

Resolver nhận paper cùng documents; chỉ gửi structured facts của các cặp
SUGGEST_LINK: mô tả dòng, số tiền, refs trên giấy, số chứng từ, đơn vị, ngày,
tổng/row facts và các cặp cạnh tranh. Không gửi raw OCR, gold, ledger hoặc policy.

Model phải nêu căn cứ số tiền cùng ít nhất một dấu hiệu nhận diện khác. Code
kiểm các căn cứ trỏ về field FOUND của đúng cặp, confidence hữu hạn trong [0,1]
và >=0.90, profile usable, cardinality và allocation. Confidence không thay thế
các điều kiện này; không tự tính giá trị thiếu để tạo căn cứ.

Hai ứng viên cho cùng dòng, cùng đủ căn cứ mà không có tín hiệu phân biệt vẫn
SUGGEST_LINK. Trùng số hóa đơn không tự được giải chỉ vì model chọn một ID.
Không dùng resolver để vượt phân bổ hoặc ghép lại tài liệu đã dùng hết.

Dùng một hàm pure projection chung sau rule matching và sau promotions để dựng
`rows`, `allocated_amount`, `findings`, `unmatched_source_ids`. Không xóa finding
không liên quan; không đổi category bằng confidence của model.

### 4.5. Consumer và danh tính

Admission nhận cùng validated mapping khi report có links; không tự chọn hóa đơn
khác bằng fuzzy suffix và không coi SUGGEST_LINK là chứng cứ đã ghép. Report cũ
không có mapping dùng đúng fallback tương thích đã có, kiểm uniqueness/allocation.

Liên kết chi phí không phải bằng chứng ai trả. `_invoice_binding` giữ điều kiện
hiện hành: trường hợp company buyer dựa vào claimant và tham chiếu in trên giấy;
một promotion ngữ nghĩa không thay thế tham chiếu này. Vì vậy có hồ sơ hết lỗi
ghép nhưng vẫn cần xác nhận payer hợp lệ. Plan không hứa loại bỏ mọi câu hỏi.

### 4.6. Phiên bản và khả năng kiểm chứng

Pin prompt/schema/profile/projection versions, model cấu hình, media representation
và activity profile trong reader identity; lưu identity vào JSON basis đã có.
Report cũ thiếu identity không được gọi là đọc bằng prompt mới. Submit cùng nguồn
và identity vẫn reuse, không bắt người dùng OCR lại vô cớ. Job đổi identity giữa
đọc và publish bị giữ stale; không tự sửa kết quả/tiền của hồ sơ đã đóng.

Mỗi stage trace ghi version, attempt kind/counters và kết quả có cấu trúc đã lọc;
giữ policy/model riêng để không quy hết thay đổi hành vi cho prompt.

## 5. Bằng chứng nghiệm thu

Offline: schema/repair toàn read pass, same-block label-vs-value, quote/ngày/tên
nhiều dòng, unknown/pending states, gray matching/competition/over-allocation,
mapping nhất quán tới admission, cache phiên bản và no-money-side-effect.

LIVE ở bước thực thi: paired trước/sau trên TC01/02/03/05/06/11/15/22 cùng PDF,
context, clock và model, DB riêng; chấm ngoài app. Ba case đầu lần lượt thu
760.000/chi400.000/cân bằng nếu đủ căn cứ; năm case âm phải giữ blocker đúng nguồn,
không phát hành tiền. Dataset này là development, không chứng minh unseen accuracy.
Offline gray fixtures bắt buộc vì PDF có exact refs có thể không gọi resolver.
UI kiểm lại bản nháp/submit, ghi ứng, nộp hoàn và kế toán xác nhận trên DB riêng.
Provider lỗi/thiếu key là NOT_RUN/TECHNICAL, không thay bằng STUB để claim LIVE.

## 6. Hoàn thành và giới hạn

Chỉ hoàn thành khi các gate trong plan có evidence mới đúng SHA/mode, không có
regression chưa giải thích, và mọi limitation được ghi. Baseline lịch sử trong
status (782 pass/5 fail) không phải kết quả của plan này. Không tự sửa năm lỗi
date-fixture không liên quan hoặc hợp thức hóa chúng thành xfail.

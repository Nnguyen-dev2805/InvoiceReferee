# TC06 và TC11 — kiểm thử âm bằng PDF gốc và LIVE

Ngày14/10/2026. **Kết luận: cả hai case FAIL kiểm tra an toàn — hệ thống phát hành yêu cầu thu khi mâu thuẫn chứng từ chưa được giải quyết.**

## Phạm vi và cách chạy

- Đã render và nhìn đầy đủ4PDF gốc: giấy hoàn ứng và hóa đơn của TC06/TC11.
- Code được giữ thành snapshot độc lập từ `final` HEAD `0b205420bfd3b4ce41e8739a1a701798a805bca1`, dưới `.runtime/hoangha-negative-20261014-153002/snapshot/src`. Không sửa logic của snapshot.
- Chạy `CaseWorkflow` → worker chứng cứ → OCR/phân loại/trích xuất/validation/matching → admission → Reconciler → commit instruction, không gọi trực tiếp một hàm tính tiền thay workflow.
- Provider LIVE: Mistral OCR và configured X-Kiro `qwen/qwen3.7-flash:free`.
- Context SIMULATED độc lập: đúng Nguyễn Minh An/công ty An Thịnh, đúng hoạt động WORK_EXPENSE, B8m, quyền system8m/4m, ứng thực nhận TC06=4m và TC11=6m, coverage đủ A/P/R. Lịch sử này là fixture mô phỏng, không chứng minh công ty thật đã chuyển tiền.
- Clock harness công khai `2026-10-10T18:00:00+07:00`; không dùng coverage hết hạn tại thời gian hiện tại.
- Mong đợi được ghi trước lượt chạy trong `independent-expectations.json`, từ ảnh và số học; không đọc `expected.json`/gold/mapping vào ứng dụng hoặc model.
- Hai case chạy trong hai DB riêng, tenant/scope riêng. Không thực hiện thu tiền, không sửa database người dùng, không sửa PDF/code ứng dụng, không commit/push/subagent.
- Đây là kiểm thử core LIVE; browser của hai case này NOT_RUN vì agent đang sửa intake/detail. Không suy ra kết quả cho phiên bản agent chưa bàn giao.

CodeGraph báo up-to-date với cảnh báo engine cũ. Tool coverage của Codebase Memory không được expose; coverage UNKNOWN. Đã đọc các hàm vật chất liên quan. Đây là điều tra theo case, không audit toàn repository.

## TC06 — sai số hoàn lại trên giấy

Nguồn: `data/tham-khao/uc-03/tc06-chenh-lech-quyet-toan-ghi-sai/`.

Ảnh giấy hoàn ứng thể hiện:

- Tổng chi:3.240.000đ; đã ứng:4.000.000đ.
- Hoàn lại in trên giấy:700.000đ, bằng chữ cũng bảy trăm nghìn.
- Phép trừ đúng:4.000.000−3.240.000=760.000đ, lệch60.000đ với kê khai.
- Hóa đơn00000601 ghi tổng3.240.000đ và liên kết đúng dòng chi.

**Mong đợi:** FACT tới nhân viên, câu hỏi nêu700k/760k và nguồn; không instruction cho đến khi có correction/xác nhận hợp lệ. Có thể hiển thị760k làm số đối chiếu, nhưng không âm thầm biến thành yêu cầu thu đã phát hành.

**LIVE thực tế (61.497giây):**

- OCR/trích xuất giữ đúng `declared_advance=4.000.000`, `printed_total=3.240.000`, `printed_return=700.000`; tất cả FOUND và có quote.
- Giấy và hóa đơn đều `profile_status=CLEAR`, không profile finding.
- Không BusinessIssue; state READY_TO_EXECUTE.
- Instruction ISSUED/COLLECT760000, NOT_STARTED; A4m/E3.24m/S−760k.

**Đánh giá:** số tính lại đúng nhưng hành vi đối soát sai. Hệ thống đã bỏ qua mâu thuẫn kê khai được đọc rõ. Đây không phải lỗi OCR hay thiếu context.

## TC11 — phép cộng trên hóa đơn sai

Nguồn: `data/tham-khao/uc-03/tc11-so-hoc-tren-hoa-don-khong-nhat-quan/`.

Ảnh hóa đơn00001101:

- Tiền hàng5.000.000đ; thuế400.000đ (8%).
- Cộng đúng5.400.000đ, nhưng tổng in5.500.000đ, lệch100.000đ.
- Giấy hoàn ứng dùng5.500.000đ; ứng kê khai6m và đề nghị hoàn500k. Hai tài liệu cùng dùng một tổng sai không làm phép tính hóa đơn trở nên đúng.

**Mong đợi:** FACT tới nhân viên yêu cầu đối chiếu/cung cấp chứng từ sửa phù hợp, nêu ba số5m/400k/5.5m và sai lệch100k. Không tự công nhận5.5m hoặc âm thầm sửa thành5.4m rồi phát hành tiền.

**LIVE thực tế (75.761giây):**

- OCR thô giữ `Thuế GTGT (8%): 400.000` và tổng5.500.000.
- Structured invoice: subtotal5m FOUND; total5.5m FOUND; tax UNREADABLE.
- Invoice vẫn CLEAR, profile_findings=[]; matching với giấy PASS vì số hóa đơn/tổng trên hai tài liệu khớp.
- Không BusinessIssue; READY_TO_EXECUTE; E=T5.5m/A6m/S−500k.
- Instruction ISSUED/COLLECT500000, NOT_STARTED.

**Đánh giá:** đã nhận tổng hóa đơn không nhất quán làm chi phí đủ điều kiện và phát hành tiền; FAIL an toàn.

## Các nguyên nhân đã kiểm tra

### 1. Chưa có gate số học cho giấy và hóa đơn trong đường chứng cứ đang chạy

`evidence/document_validity.py::validate_document` (69–154 tại snapshot) kiểm quote,
confidence và trường bắt buộc. Nó không đối chiếu phép tính của TC06/TC11.
`evidence/matching.py::match_paper_evidence` (128–342) kiểm ghép/amount/allocation,
không chứng minh phép cộng nội bộ hóa đơn hay khoản hoàn kê khai là đúng.

`reconciliation/admission.py::admit_evidence` nhận các document CLEAR rồi tạo khoản
employee-paid; mâu thuẫn printed_return trong TC06 không thành admission issue.
Reconciler chỉ chặn điều kiện đã được biểu diễn thành issue/problem. Hai lỗi chưa
được tạo thành gate, nên `_commit_assessment` phát hành instruction theo S.

Cần kiểm bằng code xác định các quan hệ số học phù hợp với loại tài liệu, nguồn
và đơn vị tiền, đưa sai lệch thành FACT có refs/owner/basis. Không giao LLM quyền
tự sửa số nguồn để làm phép tính khớp. Không ép toàn bộ receipt/ticket có trường VAT.

### 2. Trường cần kiểm số học chưa biết vẫn có thể lọt qua CLEAR

TC11 tax UNREADABLE nhưng không có finding chặn; tổng được nhận nguyên5.5m.
Không được đổi tax chưa rõ thành0 hoặc coi thiếu thành không áp dụng. Khi thành phần
ảnh hưởng việc kiểm tổng chưa rõ, giữ gate và hỏi đúng trường. Nếu có discount/
service charge/nhiều khoản thuế, chỉ tính theo căn cứ đã xác lập, không mặc định0.

Để tách vấn đề này khỏi extraction, đã chạy **probe typed evidence, không gọi thêm
provider**: đặt tax FOUND=400000 với exact quote thật400.000, giữ mọi trường khác và
context. Reconciler vẫn không có issue và allowed_effect=COLLECT500000. Do đó việc
sửa riêng extraction thuế không đóng lỗi thiếu gate số học.

### 3. Numeric provenance so sánh nhầm số đầu tiên trong quote

`evidence/extraction.py::_normalize_number` (103–110) dùng regex.search; `_value_supported`
(150–171) so sánh con số đầu tiên của quote với value. Với quote
`Thuế GTGT (8%): 400.000`, nó chọn8 thay vì400000.

Probe trên đúng snapshot:

| Value | Exact quote | Kết quả |
|---|---|---|
|400000|Thuế GTGT (8%): 400.000|False, sai|
|400000|400.000|True|
|240000|Thuế GTGT (8%): 240.000|False, sai|

Bug này phù hợp với hiện tượng tax UNREADABLE. Raw response LLM trước demotion chưa
được lưu trong lượt test, nên chưa khẳng định chính nó là nguyên nhân duy nhất của
field tax ở hai lượt LIVE. Tuy nhiên lỗi predicate đã được tái hiện độc lập.

Sửa theo loại trường/token/locator; giữ phân biệt percent, money và identifier.
Không chấp nhận substring số tùy ý trong đoạn dài làm bằng chứng cho sai value.

## Regression và điểm bàn giao

Private regression `test_safety_regressions.py` kiểm kết quả LIVE vừa chạy và
predicate numeric trên snapshot: **3failed, exit1**. Hai assertion không instruction
đều fail; một assertion tax quote cũng fail. Đây là RED chưa sửa, không full-suite.

Acceptance cho agent sau sửa:

1. TC06 giữ nguyên OCR700k; tạo FACT cụ thể700kvs760k/60k; không instruction.
2. TC11 kiểm5m+400kvs5.5m/100k; tạo FACT; không instruction. Material tax UNKNOWN
   cũng không cho affirmative money; tax0 thật có căn cứ khác taxUNKNOWN.
3. Quote có phần trăm và tiền không demote tiền đúng; số sai và identifier sai vẫn bị từ chối.
4. Source correction/xác nhận có trách nhiệm phải có provenance/revision; đánh giá
   lại đúng. Không waive FACT bằng approval chung hoặc EXCEPT_POLICY.
5. TC01 gốc hợp lệ vẫn COLLECT760k khi đủ context; các nguồn đúng không bị chặn
   bởi việc bắt VAT fields trên ticket/receipt hoặc suy đoán thành phần thiếu.
6. Rerun raw LIVE sau gate deterministic; lưu prompts/model/source/version/mode.

## Bằng chứng và lệnh

Thư mục: `.runtime/hoangha-negative-20261014-153002/`.

- `identity.json`: HEAD, source hashes và core hashes; input hashes kiểm lại sau run vẫn nguyên.
- `independent-expectations.json`: mong đợi từ ảnh/số học, viết trước run.
- TC06/TC11: ảnh render, context.json, report.json, result.json, view.json, audit.json,
  stages.jsonl và OCR raw artifacts.
- `score.json`:2FAIL_UNSAFE_INSTRUCTION.
- `numeric-provenance-probe.json`, `tax-found-admission-probe.json`: probes độc lập không thêm LIVE call.
- `regression-check.json`: lệnh/exit/result của3assertions RED.

Lệnh LIVE cho mỗi case:

`rtk proxy env PYTHONPATH=<evidence>/snapshot/src uv run --no-sync python <evidence>/run_case.py TC06` (hoặcTC11): exit0 nghĩa job chạy xong, **không** nghĩa safety PASS.

`rtk proxy env PYTHONPATH=<evidence>/snapshot/src uv run --no-sync pytest <evidence>/test_safety_regressions.py -q -p no:cacheprovider`: exit1,3failed.

Application fixes/database reset/browser/full25-case test: NOT_RUN. Agent khác đang
sửa luồng web; không đụng write set của họ. Bộ test này cho thấy còn cần sửa core
validation trước khi nghiệm thu toàn bộ Hoangha, ngoài các lỗi intake đã báo ở TC01.

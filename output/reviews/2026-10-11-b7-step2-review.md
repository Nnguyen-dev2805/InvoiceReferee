# B7 bước 2 — Đối chiếu nguồn, oracle và khả năng chạy

Ngày: 11/10/2026. Nhánh: rebuild. Phạm vi: Q01/Q03/Q04/Q11/Q13 cho V1–V5
trong [thiết kế bước 1](../../docs/superpowers/specs/2026-10-11-b7-routine-completion-design.md).
Review source-first do lead thực hiện, không adjudication chuyên môn độc lập.
Không sửa application code, nguồn/expected/manifest/policy bundle, không gọi
provider LIVE, không Git mutation. Có sửa lỗi T trong tài liệu bước 1 của lead.

## Kết luận

- Các câu chuyện đủ hữu ích để kiểm chứng tiền/chuyển tiếp; chưa phải suite
  sẵn sàng đo chất lượng đầu cuối. Nguồn là Markdown/CSV synthetic được viết
  giải thích rất rõ; không hóa đơn/biên nhận thực và không holdout.
- POLICY_REPLAY với facts/links được người review đưa vào: ba routine tính
  đúng tiền; Q11 giữ A/S unknown. Đây chỉ là kiểm tiền/rules với dữ liệu đã
  chuẩn bị, không chứng minh tự đọc, scope/coverage đầy đủ hoặc ghép nguồn.
- CLI hiện chạy hết năm initial và một followup Q11, nhưng cả sáu rows FAIL
  ở FAKE_OR_REPLAY. Không diễn giải thành độ chính xác của AI LIVE.
- Cần sửa chất lượng oracle, adapter đánh giá và câu hỏi/phân loại trước
  khi dùng kết quả này để freeze B1 hoặc trình diễn Verify đã đạt.

## 1. Nguồn và số học theo từng case

Đã đọc input theo manifest trước expected. Số tiền bên dưới tính triệu VND.
Zero dựa coverage công ty đúng scope cùng nguồn phía nhân viên, không suy từ
vắng dòng giao dịch. Quyền và receipts chỉ tồn tại trong thế giới synthetic.

| Case | Căn cứ và phép tính | Nhận xét oracle / giới hạn |
| --- | --- | --- |
| Q01 | Vé company3 có vendor receipt; hotel employee3 có receipt; meal1 có cash receipt + bounded attestation; ground1 có named receipt. A2 có receiver receipt liên kết company ledger; RA/P/RP0 theo coverage. B8 có quyết định. T8/E5/S+3. | Thành phần tổng và chiều đúng theo nguồn; cash payer là policy-attested, không bank verified; reader còn phải kiểm scope/quan hệ/không đếm đôi. |
| Q03 | Vé company3, hotel2, meal0,8, ground0,5; A4 có receiver receipt, RA/P/RP0 theo company coverage. B8. T6,3/E3,3/S−0,7. | S đúng. Mô tả V2 bước 1 ghi nhầm T3,3, đã sửa. Critical refs của RA/RP0 đang trỏ employee-scope; phải trỏ company coverage phù hợp, dù file target hiện tồn tại. |
| Q04 | Như Q01 tại M1, thêm quyết định và receiver receipt P3 tại M2, coverage cập nhật tới M2. E5/A2/P3 => S0. | Tiền tổng đúng. Critical facts có cùng key reimbursement.received_vnd mang cả0 và3.000.000 không gắn mốc riêng. P0 ở M1 là lịch sử, không current fact tại M2. close_allowed true là đủ căn cứ xét đóng trong câu chuyện, không đã đóng hoặc được tự đóng bởi Run. |
| Q11 | B8/T8/employee cost5 có căn cứ; approval ứng2 và lệnh SUBMITTED không chứng minh receiver credit. A/S unknown. Followup cung cấp receipt A2 trước money cutoff và cập nhật outcome. | Trước unknown, sau S+3 là hợp lý. Critical ref trỏ #advance-receipt vốn đã bị bỏ khỏi initial source; phải trỏ nguồn attempt/coverage đang chứng minh thiếu outcome. Followup là assisted và cập nhật knowledge, không tiền phát sinh sau cutoff. |
| Q13 | Vé company3/hotel employee4/meal1/ground1 => actual T9, B8, employee paid6, A2, RA/P/RP0. Người APR-DEMO-01 có quyền ngoại lệ tới T9 theo nguồn. | Cần POLICY decision, không khẳng định vượt quyền chỉ vì T>B. Trước quyết định E_final/S_final chưa chốt. Nếu chấp nhận toàn bộ, E6/S+4; nếu loại hotel1, E5/S+3. Giữ actual T9/B8 ở cả hai nhánh. Hai nhánh mutually exclusive, không gộp quyết định. |

Q04 là trạng thái sau của Q01 cùng story; cả năm cùng một family. Không dùng
chúng làm năm quan sát độc lập hoặc dữ liệu mới chưa từng thấy.

Policy snapshots PB-04/PB-07/PB-08 và Evidence §4–6 hỗ trợ phân biệt T/E,
actual receipt/approval, zero theo scope và quyền ngoại lệ. Đã đối chiếu
các mục liên quan; không đổi policy của packet thành Rulebook hôm nay.

## 2. Kiểm integrity và oracle

[packet-audit.json](../../data/settlement/verify/b7-step2-20261011/packet-audit.json):
68 lượt đối chiếu SHA-256 theo năm manifest cho input/followup/expected/policy
snapshot, tất cả khớp. Có lặp cùng policy files giữa packets, không là 68
nguồn độc lập. Hash khớp không xác nhận đáp án đúng.

Lỗi đã tái hiện/đối chiếu:

1. Q04 critical fact trùng key với giá trị0 và3.000.000 ở cùng snapshot.
2. Q11 critical fact unknown A trỏ tới anchor #advance-receipt không tồn tại.
3. Q03 RA/RP0 có ref tồn tại nhưng owner/meaning chưa đủ; nguồn company
   coverage trong packet mới có nội dung absence phù hợp.
4. Q13 schema expected dùng E_final_vnd/S_final_vnd, khác các shape được
   expected_money_view nhận. allowed_owner_roles dùng AUTHORIZED_APPROVER,
   khác runtime APPROVER; issue_type OUTSIDE_POLICY bị adapter lấy prefix
   OUTSIDE thay vì POLICY. Không chữa bằng so sánh rộng hoặc bỏ assertion.

Không thay gold để xanh. Bước tiếp cần oracle version mới có provenance,
current facts/as-of và các mục đích expected tách riêng; người review đối
chiếu nguồn phải giải thích từng correction.

## 3. Đường chạy raw packets hiện tại

Đã thực thi:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m invoice_referee.verify.settlement_cli --packets Q01,Q03,Q04,Q11,Q13 --out-dir data/settlement/verify/b7-step2-20261011
```

Exit0 chỉ nghĩa phép đo đã chạy. 5 initial +1 Q11 followup, tất cả Run
SUCCEEDED nhưng testcase FAIL. Artifact:
[suite output](../../data/settlement/verify/b7-step2-20261011/settlement-verify-20261011T074924Z.json).

| Case/phase | Axis FAIL |
| --- | --- |
| Q01 INITIAL | money, completion |
| Q03 INITIAL | money, completion |
| Q04 INITIAL | money, completion, state |
| Q11 INITIAL | money, completion |
| Q11 AFTER_FOLLOWUP | money, completion |
| Q13 INITIAL | money, completion |

StructuredLedgerReader chỉ đọc syntax fact/rel riêng hoặc CSV ledger schema
riêng; không hiểu prose source và CSV financial events của năm packet này.
Nguồn được nhận nhưng không trích được dữ kiện nghiệp vụ phù hợp; output
T/E0, history unknown và nhiều issue. T/E0 trong tình huống không đọc được
khoản chi cần xem lại với inventory/coverage gate, không dùng làm subtotal
đã được chứng minh. S chưa được chốt trong các run này.

Metrics raw: n_routine3/n_needs2, fn0/fp3, u0, routine_completion0/3.
fn0 không là thành công detection: không case nào đủ output chứng minh.
fp3 không là chất lượng ngưỡng LLM; đây là mismatch capability reader–data
và output thiếu. Chưa có cơ chế riêng tách đầy đủ capability ở sample này.

## 4. Probe tách reader khỏi rule engine

[rule-probe.json](../../data/settlement/verify/b7-step2-20261011/rule-probe.json)
ghi output evaluate() với amounts/history đọc từ nguồn, facts/relations
được người review xây bằng test builders. Không đưa expected JSON vào engine.

| Case | Kết quả quan sát |
| --- | --- |
| Q01 | COMPLETE, T8/E5/A2/S+3, không issue |
| Q03 | COMPLETE, T6,3/E3,3/A4/S−0,7, không issue |
| Q04 | COMPLETE, E5/A2/P3/S0, không issue |
| Q11 | INCOMPLETE, A/S null; FACT cho ACCOUNTANT |
| Q13 | INCOMPLETE, E6/calculated4, proposed null; hai AUTHORITY issues |

Probe không test OCR/extraction/linking, alias dedup, source identity,
cash-attestation gating hoặc external decision/closure của Q04. Grant probe
chỉ là scalar scope/limit hiện tại, chưa biểu diễn quyền ngoại lệ Q13.
Không coi ba COMPLETE trong probe là ba pipeline originals đạt hợp đồng.

Q11 message còn chung: thiếu lịch sử tiền advance/reimbursement; refs là
engine key history.advance.received, chưa là TX-ADV-001 và retained source.
Người nhận chưa có câu hỏi cụ thể đủ context để trả lời trực tiếp.

Q13 code gắn budget breach AUTHORITY. authority_ok còn phụ thuộc t<=b,
nên vượt ngân sách tự sinh thêm authority issue mà chưa xét riêng quyền
ngoại lệ. E6/calculated4 đang ở slot chính dù là kết quả cần quyết định;
conditional result có sẵn, proposed vẫn null. Cần làm rõ semantics current
vs conditional, không diễn giải là app đã tự duyệt/chi4triệu.

## 5. Các gap của evaluator trước khi đo baseline

Căn cứ source settlement/evaluation.py:

- load_packet kiểm hash input/expected và followup_input_files; không dùng
  policy_files để đưa policy snapshot hoặc quyền case vào Service. CLI dùng
  grant P-DEMO/mọi work/100triệu và policy hiện hành. Không thể khẳng định
  đã kiểm đúng scoped authority APR-DEMO-01 của nguồn packet.
- _run_case lấy employee/work từ expected để dựng submission, đưa case ID
  vào purpose. Chưa đưa đáp án tiền vào reader, nhưng expected vẫn ảnh hưởng
  context đầu vào; Verify sạch cần context từ input metadata riêng và không
  đưa evaluator labels vào prompt.
- _compare_initial axis state đòi approved null và không expected flags
  true, nên Q04 có settlement_approved/close_allowed true bị FAIL dù test
  chưa chứng minh engine tự tạo approval. Cần tách external basis, allowed
  action, persisted action và forbidden automatic action.
- links PASS mới chứng minh file được nạp/report nhắc source, không chứng
  minh quan hệ nào ghép đúng. Business gold facts/relations chỉ được đếm
  coverage, chưa được chấm bởi adapter engine facts/relations hiện tại.
- Q13 followup_branches không được chọn/thực thi trong run_suite này. Không
  nói hai nhánh exception đã verified. Cần branch selection rõ, không auto
  lấy cả hai hoặc dùng expected chọn nhánh đúng.
- Followup không cập nhật knowledge_cutoff từ followup_source_received_at;
  hai mốc tiền/kiến thức cần được tái lập đúng. Source gốc/hints hiện có làm
  LIVE guard từ chối tập này; không tắt guard để chạy benchmark.

## 6. Verification bổ trợ

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_evaluation.py tests/settlement/test_rules.py tests/settlement/test_questions.py -q
```

Exit0: **41 passed in0,64s**. Chỉ unit/integration fake đang có; không đóng
gold issues hoặc capabilities chưa được kiểm, không professional trial.
Graph đã lỗi hai lần trong phiên trước; dùng targeted source fallback,
không claim graph generation/coverage. Không thao tác browser ở lượt này.

## 7. Hướng bước 3

Ưu tiên một plan hữu hạn trước khi thay code:

1. **Chuẩn hóa evaluation context/oracle version** cho năm case: current
   values/refs/owner/type, policy/rights scope, input metadata, separate
   report readiness vs existing approval vs closure; giữ corpus cũ nguyên.
2. **Bridge và chấm đủ:** replay observations/relations versioned để test
   rules, mapping business facts/links có source refs; input artifacts cho
   LIVE phải version bỏ hints và không được hard-code theo case ID. Chọn
   nhánh followup/mốc knowledge rõ. Không gọi replay là tự đọc nguồn.
3. **Sửa đúng gap nghiệp vụ:** POLICY vs AUTHORITY, conditional vs final,
   câu hỏi specific event/source/owner, empty extraction không thành known0.
4. **Kiểm fake/negative cases rồi UI/LIVE theo scope:** cùng production
   application; không sửa expected theo output, không đụng source UI đang
   có writer khác. Freeze/holdout/trial chỉ sau evidence tương ứng.

Không cần bổ sung auth/ERP/queues, mở phê duyệt ứng B3 hoặc bank integration
để giải quyết các gap này. Chưa publish, chưa baseline chất lượng LIVE.

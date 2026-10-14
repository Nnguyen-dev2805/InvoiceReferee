# Cơ chế câu hỏi và phản hồi hiện tại

14/10/2026. Read-only review trên `final` HEAD96e7b888 cùng working-tree đang sửa
core arithmetic/UI. Không sửa code ứng dụng hoặc hồ sơ người dùng. Không gọi
provider hoặc gửi email/message. CodeGraph up-to-date/earlier-engine warning;
coverage tool không expose, coverage UNKNOWN; source vật chất của chain đã đọc.

## Kết luận

Trong chain đang hiển thị questions, solution là **rule-based issue generation +
template wording + role-filtered web work queue + persisted answers/re-assessment**.
LLM upstream giúp OCR interpretation/classification/extraction/ambiguous matching;
không có LLM viết câu hỏi trong chain BusinessIssue→Questions đã truy vết.
Không phải một conversational agent tự hiểu và xử lý mọi câu trả lời.

## Chain và dữ liệu

1. `evidence/*` đọc nguồn thành typed proposals, refs và states.
2. `reconciliation/admission.py` phát hiện binding/history/allocation/missing-source
   issues; `policy.py` kiểm B/8/4 và thiếu facts; `category.py` kiểm loại/hạn;
   `document_arithmetic.py` (working-tree mới, chưa full gate ở review này) tính
   số học và tạo finding có câu hỏi.
3. Conditions trong Python tạo `BusinessIssue` trực tiếp, hoặc từ helper `_issue`.
   Wording là literal/f-string ghép số/giới hạn đã biết, không model-generated.
4. Reconciler hợp nhất/dedup issue theo kind+field_or_rule và chặn effect.
5. `_commit_assessment` lưu `case_issues` trong SQLite; stable id=hash(root+
   kind+field/rule). Các issue không-incident được recompute, xóa và tạo lại khi
   reassess. Đây là work queue trong hồ sơ, không outbound notification ở chain này.
6. API trả CaseView. React Questions lọc myIssues/otherIssues, hiển thị câu hỏi,
   basis và biểu mẫu generic, không sinh lại question.
7. POST `/api/cases/{root_id}/answers` → AnswerIssue → `_answer_issue` kiểm root,
   version, owner/persona; lưu Confirmation và audit, rồi assess lại trong transaction.

`BusinessIssue` gồm id/kind/field_or_rule/owner/depends_on/status/basis/refs/question.
Kinds FACT/POLICY/AUTHORITY, status OPEN/ANSWERED/RESOLVED/SUPERSEDED. `depends_on`
default empty; không suy từ việc DTO có slot rằng đã có conversational planning.

Ví dụ concrete từ policy.py:

- EUNKNOWN → FACT expense:payer, owneremployee, question "Xác minh người trả…".
- B không có → FACT budget:B, ownerorg-data, question tìm/cấp bản ghi ngân sách.
- A/PUNKNOWN → FACT ledger:coverage, owneraccountant.
- E>8m → AUTHORITY RECOGNIZE_COST; category/date fails → POLICY.

Điều kiện EUNKNOWN quá rộng: E có thể unknown do binding/context/source, không
chỉ do chưa biết payer. Đây là lý do user có thể thấy câu hỏi người trả dù vấn đề
gốc là thiếu context như case11a8bf49 đã điều tra.

## Nhận và áp dụng câu trả lời

UI QuestionCard hiện có hai ô text value/reason. Nó gửi issue_id, basis_id tự
ghép `basis:<issue_id>`, answer_kind=issue.kind, value, reason. API AnswerRequest
không có refs/upload; mặc dù domain Answer có refs, route hiện không truyền refs.

Backend lấy actor từ session; không từ textbox. `_answer_issue` persist
case_confirmations với fact_key=issue.field_or_rule; đánh ANSWERED; audit và
reassess. Vì issue được recompute, nếu consumer không dùng confirmation để giải
quyết predicate, issue lại OPEN. Lưu answer không chứng minh resolved.

`POLICY`/`AUTHORITY` cần command quyết định có actions/scope/amount và grant qua
`/decisions`/_decide. Điền "đồng ý" vào /answers không tự tạo một decision hợp lệ.
QuestionCard generic hiện gửi /answers cho mọi kind, nên không được coi textbox
đó là đủ cho toàn bộ resolution workflow.

## Hai khoảng trống đã xác nhận

### Routing org-data bị lệch giữa backend và frontend

Backend `_owner_persona` map org-data→accountant. Frontend roleMatchesOwner khi
roleaccountant chỉ nhận owner==accountant, không org-data. Do đó budget:B có thể
luôn ở "chờ bộ phận khác" dù backend cho accountant trả lời. Đây là mismatch
trong cùng chain, không phải model chọn sai vai trò.

### Generic question answer không đồng nhất với key consumer của typed admission

`_answer_issue` lưu generic payer response dưới keyexpense:payer. `_claim_index`
trong typed admission chỉ đọc key dạngexpense:<invoice_reference>:employee_paid.

Probe pure typed STUB fixture (không provider/user DB), cùng source/value/actor/
scope/history/grants, chỉ đổi fact_key:

| Tình huống | E | Payment portion | Issue payer |
|---|---|---:|---|
| Không confirmation | UNKNOWN |0|Có|
| keyexpense:payer | UNKNOWN |0|Vẫn có|
| keyexpense:IR1:employee_paid | KNOWN3.24m |1|Không|

Điều này chứng minh current generic answer không được consume như confirmation
đã định kiểu. Không chứng minh một text tùy ý đủ làm paid fact, không yêu cầu
bỏ kiểm nguồn/quyền/bounds. Cần resolver per-issue với schema/action/binding rõ.

Existing `tests/integration/test_answer_loop.py`:3passed, nhưng cả scenario reply
đang dùng STUB snapshot path; không chứng minh LIVE typed-admission loop đóng.

## Đánh giá thiết kế

Điểm tốt: deterministic routing, audit được, giữ code-owned quyền và tiền,
không model tự tạo tiền/waive facts. Hướng này phù hợp decision boundary tài chính.

Chưa tốt: nhiều literal/template phân tán; một loại vấn đề có thể dùng câu quá
chung; form text dùng cho số/người/coverage/quyết định khác nhau; routing mismatch;
missing bridge từ answer schema tới fact/record/reassessment. Sources refs backend
không đồng nghĩa UI đã có controls attach hoặc chứng minh mọi response đủ căn cứ.

Ưu tiên nếu cải thiện: chuẩn hóa issue/resolution catalog với owner, field/action
schema, required evidence và handler. UI chọn form/action theo issue; handler cập
nhật đúng scoped record rồi recheck. LLM có thể diễn đạt câu cho dễ hiểu nếu cần,
nhưng chỉ từ structured issue, không đổi số/rule/owner hoặc tự quyết resolved.
Không cần chuyển toàn bộ cơ chế thành chatbot để đóng các khoảng trống này.

## Evidence và giới hạn

- `.runtime/question-flow-20261014-172852/confirmation-consumer-probe.json`:
  puretypedfixture, no provider/no user DB; no extra LIVE run.
- `rtk proxy uv run --no-sync pytest tests/integration/test_answer_loop.py -q -p no:cacheprovider`:
  exit0,3passed (STUB path).
- Material sources: domain/issues.py; reconciliation/admission.py,policy.py,
  category.py,service.py,document_arithmetic.py; workflow/service.py,
  evidence_assessment.py; API routes/views; frontend questions.tsx/api.ts.
- Browser/notification infrastructure/full response suite/whole-branch review:
  NOT_RUN. No exhaustive no-LLM/no-notification claim about unrelated project paths.

No application fix, DB reset, commit/push hoặc subagent trong task này.

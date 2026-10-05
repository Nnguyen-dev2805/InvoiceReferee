# InvoiceReferee — Định nghĩa bài toán theo code hiện tại

Ngày đánh giá: **05/10/2026**, giờ Việt Nam. Branch `rebuild`, source HEAD
`18626a701adc1b8a1ad862569f9f2066730627d3`.
Hai subagent đọc hai trục backend/AI và UI/human handoff; agent chính đối chiếu
source, chạy kiểm chứng và tổng hợp. Đây là đánh giá hiện trạng, **không thay đổi
rulebook, spec, kiến trúc hoặc hành vi production**.

## 1. Định nghĩa ngắn gọn

> **InvoiceReferee hiện là prototype kiểm tra và phân luồng hồ sơ đề nghị hoàn
> trả chi phí nhân viên theo policy mô phỏng. Nó chuyển khai báo và chứng từ
> thành dữ kiện có nguồn, kiểm các quy tắc áp dụng, tạo câu hỏi hoặc yêu cầu
> người có quyền xử lý ngoại lệ, và lưu một đề nghị chi trả nội bộ khi engine
> đánh giá hồ sơ đủ điều kiện trong quyền được cấu hình.**

Phần đã tự động hóa nằm ở **đánh giá hồ sơ và quyết định bước tiếp theo**.
Việc xác minh nguồn tiền ngoài hệ thống, workspace đối chiếu thuận tiện cho
kế toán, human closure đầy đủ từ UI và thực hiện thanh toán chưa được hoàn thiện
hoặc chưa có bằng chứng tương ứng. Tạo PaymentRequest không tự chứng minh khoản
đó đã được chi, hồ sơ đúng ngoài thực tế, hoặc kế toán đã tiết kiệm thời gian.

Không nên mô tả sản phẩm hiện tại là hệ thống kế toán/thanh toán hoàn chỉnh,
hoặc hệ thống đã đối chiếu tự động với giao dịch công ty và ngăn mọi khoản hoàn
trả trùng. Cũng không nên mô tả nó chỉ là OCR: code đã có policy, authority,
issue/owner, revision, request lifecycle và các controls riêng. 

## 2. Bài toán nghiệp vụ mà code đang biểu diễn

Với một đề nghị hoàn trả cùng những chứng từ đã nộp, người xử lý cần xác định:

1. Hồ sơ thuộc profile hỗ trợ và có các thông tin/chứng từ cần thiết không?
2. Những số liệu cần dùng có đọc được, chuẩn hóa được và truy được nguồn không?
3. Số học, requested amount và đối chiếu bill/receipt khi áp dụng có phù hợp không?
4. Hồ sơ đáp ứng policy và authority được cấu hình không?
5. Cần bổ sung dữ kiện nào, người nào xử lý, hay có thể tạo đề nghị chi trả?

Ba profiles hiện có là TRAVEL, CLIENT_MEAL và WORK_PURCHASE; OTHER cần quyết định
ngoài catalog. Inventory áp cho mua vật tư/nhận hàng, không ép hồ sơ taxi hoặc
tiếp khách có báo cáo kho. Đây là **quy trình hoàn trả tiền cá nhân đã chi**;
COMPANY/ADVANCE/VENDOR được từ chối theo scope hiện tại, không có dispatcher
thực hiện workflow quyết toán tạm ứng hay thanh toán nhà cung cấp tương ứng.

Căn cứ: [decision.py](../src/invoice_referee/policy/decision.py), L186–414;
[pipeline.py](../src/invoice_referee/application/pipeline.py), L85–116;
[rulebook](specs/B1_RULEBOOK.md), §2–§3.

## 3. Người dùng và trách nhiệm

| Vai trò logic | Phần việc trong thiết kế/source hiện tại |
| --- | --- |
| EMPLOYEE | Nộp khai báo/evidence; backend có actions bổ sung và đề xuất correction |
| REVIEWER | Xác minh field/mapping từ nguồn; không có quyền bỏ hard gates bằng một câu approve |
| APPROVER | Duyệt amount trong phạm vi authority theo policy demo |
| POLICY_OWNER | Phân loại/deny, cấp exception hoặc amount approval theo scope |

Đây là **một operator với modes mô phỏng**, không phải các nhân sự đã xác thực
trong một công ty. Frontend đang dùng employee ID `demo-employee` và lấy mode
human action từ owner của issue; không có căn cứ suy ra tenant/enterprise roles.
Đó là giới hạn scope đã công bố, không phải yêu cầu mở rộng auth trong lượt này.

Backend hỗ trợ action/reevaluation không có nghĩa từng role đã hoàn thành được
việc đó qua UI. Khoảng trống UI được kiểm chứng tại §7.

## 4. Đầu vào, xử lý và đầu ra thật

**Đầu vào:** Claim (profile, purpose/trip, amount, payer declaration,
received_full khi áp dụng), files PDF/image theo evidence role, policy/threshold
config và các human actions có scope/version.

**Đường chạy:**

```text
CaseForm → POST /api/cases → CaseService.submit → local case/evidence
  → start_run → snapshot/version → process/preflight
  → OCR + per-document analysis → normalization/quality/source checks
  → cross-source proposal khi áp dụng → pure evaluate
  → Repository.finalize_run → decision/issues/events/request record
  → UI đọc/poll kết quả

Human action hợp lệ qua API → validate/persist → reevaluate → result mới
```

[App.tsx](../frontend/src/App.tsx), L73–100;
[service.py](../src/invoice_referee/application/service.py), L323–361, L376–394;
[repository.py](../src/invoice_referee/storage/repository.py), L585–696.

| Action | Ý nghĩa và artifact |
| --- | --- |
| CREATE_PAYMENT_REQUEST | Lưu một PaymentRequest hiện hành/case với amount, payee, run/policy và basis ROUTINE_AUTO/HUMAN_AUTHORIZED |
| REQUEST_INFO | Issue factual có question/owner; chưa tạo request |
| ESCALATE | Issue ngoài policy hoặc vượt authority; cần action đúng scope |
| REJECT | Từ chối theo rule đã xác định hoặc human denial; không thực hiện workflow tài chính khác |
| NONE | Không thực hiện financial action vì technical failure hoặc execution control |

PaymentRequest dùng status **CREATED/SUPERSEDED/REVOKED**, không có PAID. Nơi tạo
record chỉ insert SQLite và event, không gửi lệnh ngân hàng. Sau request không
có step payment execution, bank confirmation, accounting posting hoặc công việc
chi tiền được nối trong đường chạy đã khảo sát.

Căn cứ: [models.py](../src/invoice_referee/domain/models.py), L48–64, L336–345;
[schema.sql](../src/invoice_referee/storage/schema.sql), L93–109;
[repository.py](../src/invoice_referee/storage/repository.py), L771–810.

## 5. Vai trò AI và Python

- Mistral OCR adapter nhận chứng từ; registry/facts giữ references tới dữ liệu
  được đọc. Kimi AnalyzeDocument trả structured facts/quality observations;
  cross_source trả item matches/conflicts khi profile cần đối chiếu.
- Python kiểm schema, source ownership/coverage, normalization/usability,
  arithmetic/units, consistency, eligibility, limits/authority và action cuối.
- Employee declaration, document fact và human confirmation là các loại nguồn
  khác nhau. SourceRef chứng minh trace tới dữ liệu đã nhận; nó không tự chứng
  minh tính xác thực của tài liệu hoặc sự kiện trả tiền ngoài đời.
- Engine có fail-closed guards cho những checks đã triển khai. Không được nâng
  nhận xét đó thành bảo đảm fail-closed cho mọi rủi ro tài chính: payer verification
  đang có khoảng trống đã tái hiện ở §7.

Căn cứ: [providers.py](../src/invoice_referee/extraction/providers.py), L112–124;
[pipeline.py](../src/invoice_referee/application/pipeline.py), L225–265;
[decision.py](../src/invoice_referee/policy/decision.py), L379–413.
Adapter/source wiring là IMPLEMENTED; chất lượng live OCR/Kimi vẫn INCONCLUSIVE.

## 6. Giá trị đã có và giá trị chưa chứng minh

| Nhận định | Mức bằng chứng |
| --- | --- |
| Intake/policy engine/issue owner/request persistence tồn tại và nối qua API | IMPLEMENTED; các contracts được VERIFIED bằng selected fake/replay tests |
| Backend human validation, reevaluation, Stop/stale và request lifecycle | IMPLEMENTED; selected backend tests VERIFIED |
| Frontend có form, polling, result/issues và controls | IMPLEMENTED; component tests VERIFIED trong phạm vi render/mock |
| Kế toán đọc/đối chiếu source ngay trong UI và đóng các issues qua UI đầy đủ | Chưa đạt; có metadata surface và contract gaps đã kiểm chứng |
| Xác minh người thực trả tiền hoặc tìm công ty đã thanh toán bằng nguồn độc lập | Chưa có trong case path đã khảo sát; đây là đề xuất mở rộng |
| Live end-to-end với input mới/độ chính xác của providers | INCONCLUSIVE; không gọi providers thật trong đánh giá |
| Giảm tổng thời gian kế toán, giảm bỏ sót/sai quyết định ngoài corpus | INCONCLUSIVE; chưa có user-study/before-after evidence trong lượt này |
| Bank transfer và workflow công ty/tạm ứng/vendor riêng | Ngoài scope MVP hiện tại; không tự chuyển thành PLANNED feature |

Giá trị được hướng tới là giảm thao tác đọc/trích/kiểm rule và chỉ ra những
điểm cần xử lý. Muốn chứng minh giảm công đối chiếu, cần người xử lý thực thử
với cùng loại hồ sơ và đo cả thời gian tìm nguồn, review, correction/rework,
chờ kết quả và chuẩn bị dữ liệu. Một request được tạo không thay phép đo này.

## 7. Các giới hạn material ảnh hưởng định nghĩa sản phẩm

### 7.1. Payer declaration chưa là payment verification

Probe synthetic/fake qua CaseService và Repository trên cùng HEAD cho thấy:

| Inputs còn lại đủ điều kiện, claim PERSONAL | Actual |
| --- | --- |
| Không có payer evidence | Một ROUTINE_AUTO request |
| PRIMARY_BILL có DOCUMENT payer=COMPANY, derived USABLE | Vẫn một ROUTINE_AUTO request |
| Cùng payer=COMPANY trong CONTEXT | REQUEST_INFO, zero request |

Payer từ claim được dùng tại [decision.py](../src/invoice_referee/policy/decision.py),
L214–222, L294–305. Payer conflict chỉ được gọi cho CONTEXT tại
[pipeline.py](../src/invoice_referee/application/pipeline.py), L245–250.
Đây là **giới hạn kiểm chứng người trả** và **lỗi bỏ sót contradiction trên primary**.
Evidence: `data/output/diagnostics/payer-verification-2026-10-05.json` (05/10,
cùng revision; không phải live airline OCR hay money transfer).

### 7.2. Frontend human closure chưa nối đúng contract

[HumanActions.tsx](../frontend/src/HumanActions.tsx), L49–62, tạo amount payload
với policy_version rỗng, field payload với refs rỗng, hoặc payload {}.
[human.py](../src/invoice_referee/application/human.py), L57–79, L133–165, L306–324,
yêu cầu keyset/refs và policy binding hợp lệ.

Fresh probes gửi **payload tương đương component** vào API/service thật:

| Role/action | Actual HTTP/result |
| --- | --- |
| EMPLOYEE / SUPPLY_DECLARATION với {} | 422 INVALID_ACTION, thiếu changes |
| APPROVER / APPROVE_AMOUNT với policy_version="" | 422 INVALID_ACTION, sai active policy binding |
| REVIEWER / CONFIRM_FIELD với refs=[] | 422 INVALID_ACTION, thiếu source refs |

Đây không phải browser E2E, nhưng xác nhận lệch contract cụ thể. ADD_EVIDENCE
multipart có helper/API nhưng HumanActions→App đang dùng JSON sendAction.
Không gọi backend loop là hoàn chỉnh từ UI chỉ vì các nút đã render.
Evidence: `data/output/diagnostics/current-problem-ui-payload-probes-2026-10-05.json`.

### 7.3. UI chưa là workspace đối chiếu nguồn cho kế toán

[CaseDetail.tsx](../frontend/src/CaseDetail.tsx), L92–102, chỉ liệt kê tên/role/size
chứng từ; L145–149 hiển thị raw JSON. Evidence route tại
[app.py](../src/invoice_referee/api/app.py), L363–369, trả metadata DTO, không trả
file content. Backend có source references, nhưng surface này chưa cho reviewer
xem chứng từ, chọn field/ref, so giao dịch liên quan và xác nhận có căn cứ.

### 7.4. Cần phân biệt runtime factory với injected test service

[app.py](../src/invoice_referee/api/app.py), L498–518, tạo EMPTY FakeProviders trong
PROVIDER_MODE=fake. Fresh probe: actual factory + isolated SQLite + explicit
demo activation + synthetic PDF upload → FAILED/NONE/PROVIDER_FAILED, zero request.
Đường happy case bằng fake cần documents/registries được inject; fake factory
hiện không tự tạo chúng từ file mới. Live adapter tồn tại nhưng không được thử
trong lượt đánh giá, không suy fake factory failure thành live failure.

Verify tests dùng ReplayProviders/injected service; nó khác fake runtime factory.
[runner.py](../src/invoice_referee/verify/runner.py), L82–98, còn trả INCONCLUSIVE
cho LIVE_END_TO_END. Có UI/Verify routes không đồng nghĩa live demo đã vận hành.

## 8. Hướng cải tiến vừa bàn — chưa phải định nghĩa hiện trạng

Việc đối chiếu hồ sơ nhân viên với payment/booking/reimbursement records độc lập
phía công ty sẽ bổ sung một câu hỏi nghiệp vụ quan trọng:

> Khoản này có thực sự còn cần hoàn trả cho nhân viên không?

Workspace để kế toán xem sources/matches/contradictions và xử lý đúng issue
sẽ biến engine output thành công cụ review sử dụng được. Hai hướng này có
thể cải thiện vấn đề đã xác định, nhưng cần chốt source trust/coverage, matching,
unknown/conflict handling và acceptance riêng. Chưa sửa rulebook hoặc thêm
ledger vì chúng được nhắc trong cuộc thảo luận này.

Chống trả trùng giữa nhiều hồ sơ khác với một current request/case. Cũng không
thể lấy absence trong một ledger chưa đầy đủ làm proof employee đã tự trả.
Không tuyên bố fraud detection hoặc tự động hóa toàn bộ kế toán từ việc thêm
một matcher.

## 9. Bằng chứng và giới hạn của lần đánh giá

- Hai trục đọc độc lập, primary agent kiểm lại những claims material và chạy probes.
- Tier Verify, bounded case/API/service/policy/storage/provider/UI paths đã nêu.
  CodeGraph dùng trước source discovery; returned source có line numbers. Khi
  output trimmed, đọc exact ranges/AST inventory để xác minh. MCP
  check_index_coverage/generation token không được expose; không giả đã gọi nó.
  Không dùng một số symbol hits để tuyên bố full-repo audit.
- Fresh selected backend run: **145 passed**, một Starlette/httpx deprecation
  warning. Không cài/thay dependencies để xử lý warning trong review này.
- Fresh selected frontend run: **5 passed**; mocks/render, không chứng minh
  human closure hoặc live provider.
- Local runtime/payload probes dùng fake providers/synthetic data/disposable DB;
  không gọi network/live providers, không chuyển tiền hoặc sửa source.
- [PRODUCT.md](PRODUCT.md) có các đoạn T07–T11 PLANNED đã lệch source hiện tại.
  Không dùng các đoạn đó để phủ nhận backend/API/UI/Verify đang có, và cũng không
  dùng source presence để gọi toàn bộ product flow đã hoàn thiện.

Commands và hashes lưu tại `data/output/diagnostics/current-problem-definition-evidence-2026-10-05.json`.
Definition này cần được refresh nếu implementation hoặc phạm vi được giao thay đổi.

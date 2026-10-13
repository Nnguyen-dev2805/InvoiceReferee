# Plan sửa dữ liệu PDF, pipeline và kiểm thử InvoiceReferee final

> **For agentic workers:** Theo [AGENTS.md](../../../AGENTS.md), thực hiện từng task được người dùng giao, RED → GREEN và gate của task. Native/Subagent-driven là helper tùy chọn, không mở rộng quyền code/Git/LIVE. Plan này được viết để review; lượt lập plan không sinh/xóa PDF, sửa code hay chạy provider. Mọi checkbox dưới đây chưa thực hiện.

**Goal:** Có15 hồ sơ development chứa căn cứ thật trên PDF/ảnh, dễ chọn để test UI, đi qua pipeline thật và được chấm độc lập trước baseline LIVE.
**Architecture:** Giữ FastAPI/SQLite/React và ranh giới Reader → Reconciler → CaseWorkflow. Một script người dùng chạy, các helper nhỏ theo trách nhiệm sinh chứng từ/định nghĩa hồ sơ. Một nguồn dữ liệu canonical; runtime chỉ nhận đầu vào, scorer mới nhận đáp án. Một workflow integrator sở hữu các file schema/commands/jobs/state.
**Tech Stack:** Python3.12, Node24, Pydantic/FastAPI/SQLite, React/TypeScript/Vite; ReportLab/NotoSans, pypdf/PDFium/Pillow; Mistral OCR/xkiro; pytest/Vitest/Playwright. Dùng dependencies/locks hiện có, không thêm framework agent/queue/ORM.
**Spec:** [Thiết kế Q1–Q31](../../final/ARCHITECTURE_AND_EVALUATION.md), [contracts §3–7/9–11](../../final/IMPLEMENTATION_CONTRACTS.md), [review PDF và48 mục QA](../../final/PDF_DATA_REVIEW_AND_UI_CHECKLIST.md). Plan sửa các gate chưa chứng minh của T3–T10 trong [plan gốc](2026-10-13-invoice-referee-final.md); không thay scope và không tự mở T11–T13.

## Global Constraints

- Một employee/activity/root, VND, TRAVEL trước. Không mở procurement/inventory/repair/local-meeting/FX/refund vendor/multi-claim allocation bằng đổi tên case.
- T là chi phí công việc đã phát sinh; E là eligible employee-paid; C company-direct; S=E−A−P+R. Personal ngoài T/E; business-incurred bị loại E vẫn ở T. Unknown/conflict không thành0.
- Quyền auto: E<=8.000.000 đ và abs(S)<=4.000.000 đ. Approver<=20.000.000 đ cho từng action, đúng actor/scope/profile/time. Không chia khoản để né quyền; không suy grant từ persona/chữ ký scan.
- Routine tự kết luận và tạo instruction; người giữ việc thực hiện tiền/ngoại lệ. Khai báo, quyết định, instruction, actual, fulfillment và SETTLED là các trạng thái riêng.
- Một instruction actionable/root; OPEN/UNKNOWN/suspended chưa xác minh chặn replacement. Actual thật không bị xóa/cắt bởi ngân sách, quyền hay hủy instruction.
- Source roles theo page/unit; exact quote/bbox/digest/page có thật chưa tự chứng minh payer/received/binding. Bộ chấm không nhận refs_ok do app tự khẳng định.
- Giữ native/ảnh mâu thuẫn, NOT_READ khác MISSING, technical khác FACT. Missing key không hạ cấp LIVE ngầm. STUB/replay/LIVE phải phản ánh reader đã dùng.
- Một recovery bổ sung/issue và finite global budget. Caps đã chốt:8 files/20 pages/case,20MiB/file,40MiB total,20MP/image,12LLM/10OCR attempts/job, timeout20s, processing90s,2 workers,1 active job/root. Human waiting không tính processing deadline. Parser helper5s/512MiB; LIMIT phải hiện rõ.
- Không PDF/JSON rác để đủ số. Clone/biến thể/test lại không tăng N độc lập. Gold không vào model/app; kết quả initial khác assisted final.
- Tên mọi thư mục trong bộ kiểm thử mới: tiếng Việt không dấu, lowercase, hyphen; `case-<hai-chu-so>-<mo-ta>`. Tên PDF mô tả loại chứng từ, không tiết lộ đáp án trong tên đưa cho model.
- Không ghi đè code đang được agent khác sửa. Re-read HEAD/diff trước task; giữ các fix hiện có nếu gate đúng. Không reset DB/uploads, cài global runtime, stage/commit/push trong phạm vi chưa được giao.
- Không cần nhân viên upload file cấu hình công ty. Context synthetic đúng scope có sẵn phía server; người test chỉ nộp đúng tài liệu ở bước hiện tại.
- Ngưỡng adaptive, holdout mới, hosting, practitioner feedback và hồ sơ nộp thi là bước sau. Không dùng việc hoàn thành plan này để claim đã đạt toàn bộ cuộc thi.

## Review Focus

1. PDF khác bytes nhưng giống nội dung; gold ghi số không nhìn thấy trên nguồn — R1/R2.
2. LIVE có nhãn đúng nhưng dùng transcription/metadata/case-name; future receipt hoặc gold lọt vào initial input — R4/R7.
3. Một câu completion/ref bất kỳ bị coi là proof; claim sai scope/payee được allocate; tiền lịch sử fulfill cả successor — R3/R6.
4. Stop/Resume ghi đè instruction OPEN/UNKNOWN; stale context/answer/decision commit sau revoke — R3/R5/R6.
5. Sai chiều tiền, false BALANCED, thiếu required issue/ref/disposition vẫn PASS; technical được tính như escalation đúng — R7/R8.

---

## Snapshot và cách đọc plan

Review ban đầu ở `13a6eb09`. Trong lúc lập plan đã có commits `e8745125`
(scope/amount grant), `de87d7ed` (bare money claim), `1acd8a08` (Stop/Resume),
`c01037d2` (apply answer), `6439c572` (scorer/runner) và `2b641e63` (LIVE source
reading). Frontend execution/test đang có local edits ở lần quan sát sau cùng.
Đây là **có sửa trong code**, chưa phải verdict closure trong plan này. R0 kiểm lại
snapshot thực tế; không áp patch cũ dựa trên line numbers đã dịch chuyển.

Reviewer/tác giả plan đọc source qua CodeGraph; project up to date ở lần query,
engine index cũ, generation và check_index_coverage không được tool cung cấp.
Pass giới hạn đó khi dispatch; cần fresh source cho phần đang thay đổi.

R0→R1→R2→R3→R4→R5→R6→R7→R8. R1 authoring có thể làm độc lập, nhưng sửa shared
workflow/domain/schema/API phải qua một integrator và tuần tự. Mỗi task có evidence
và reviewer gate riêng; không tích task chỉ vì đã tạo đủ file hoặc suite cũ xanh.

## A. Cấu trúc dữ liệu dễ thao tác

```text
data/
  kiem-thu/
    CHECKLIST.md
    cau-hinh/
      cong-ty-demo.json
    phat-trien/
      manifest.json
      case-01-cong-ty-chi-them/
        HUONG-DAN.md
        cau-hinh/
          to-chuc.json
          khai-bao.json
          kich-ban.json
          ban-doc-stub.json
        dau-vao/
          01-nop-ban-dau/
            01-bang-ke-quyet-toan.pdf
            02-hoa-don-chi-phi.pdf
            03-bien-nhan-nhan-vien-thanh-toan.pdf
            04-bien-nhan-cong-ty-thanh-toan.pdf
          02-bo-sung/                  # chỉ có khi case có bước bổ sung
          03-thuc-hien-tien/
            chuyen-khoan/
            tien-mat/
        dap-an/
          su-that-an.json
          quan-sat-duoc.json
          ket-qua-hop-le.json
      case-02-nhan-vien-hoan-tien/
      ...                           # tên chính xác ở bảng B
    ky-thuat/
      m0-van-ban-ro/
      m0-scan-ro/
      m0-so-bi-che/
      m0-khong-phai-chung-tu/
  tham-khao/
    uc-03/
      case-01-hop-le-nhan-vien-hoan-tra-tien-thua/
      ...                           #25 case tham khảo, không nạp bởi app/Verify
```

Chỉ tạo subfolder có file thực; không tạo cây rỗng cho calibration/validation/
holdout hoặc các bước chưa có dữ liệu. `kiem-thu` là nơi test chính. UC-03 giữ
reference riêng, đổi tên folder bằng case_id/title không dấu; giữ bytes PDF/DOCX,
expected cũ gắn LEGACY_REFERENCE, sửa manifest/README path. Không giải nén RAR.

`input/organization/submission` và `gold/latent/observable/allowed` trong contracts
giữ nguyên **vai trò và DTO**; tên vật lý mới do loader map rõ. Executor cập nhật
một đoạn layout/mapping tại contracts §7 và File Map plan gốc; không đổi quy tắc.
Không duy trì hai corpus cùng nội dung hoặc hai generator chạy ngược nhau.

| File/vùng | Người dùng làm gì | Runtime/model được đọc? |
| --- | --- | --- |
| HUONG-DAN.md | Tên hoạt động, vai trò, thứ tự tệp, bước nộp/bổ sung/ghi tiền, expected và lỗi cố ý | Không |
| dau-vao/01-nop-ban-dau | Chọn các PDF/ảnh ở đây cho lần nộp đầu | Có, sau upload thực |
| dau-vao/02-bo-sung | Chỉ nộp khi tới bước bổ sung chỉ định | Chỉ sau bước đó, không đọc trước |
| dau-vao/03-thuc-hien-tien | Kế toán dùng receipt/phiếu chi theo đúng biến thể | Chỉ ở bước ghi/xác minh tiền |
| cau-hinh/to-chuc.json | Context quan sát được/authoritative được server import có audit | Có qua context; không có E/S/route ép kết quả |
| cau-hinh/khai-bao.json | Declaration thực, không financial truth | Có |
| cau-hinh/kich-ban.json | Manifest nguồn theo stage, lệnh/bước thực, quan hệ setup có chủ đích | Runner đọc; không có expected/gold; không chuyển file kế tiếp vào model |
| cau-hinh/ban-doc-stub.json | Đọc tay có source digest/page/quote, DATA_ORIGIN=STUB_TRANSCRIPTION | Chỉ STUB; LIVE/replay cấm load |
| dap-an | Người test/scorer so expected với actual | App/model tuyệt đối không đọc/serve |

Nguồn thực nhận ứng/history có thể là organization registry có witness refs đã
import, không bắt upload bản PDF trùng cho cùng ledger. Receipt của supplier
payment khác receipt ứng/hoàn; ghi rõ payer/payee/purpose/transaction/time/completion.
Source model nhận storage keys opaque, không folder `case-06-...` hay HUONG-DAN.

### A.1. Hợp đồng packet/stage dùng chung R1–R8

Các DTO sau ở `src/invoice_referee/evaluation/models.py`, strict extra=forbid;
đây là refinement file-format/interfaces, không đổi luật tiền của contracts:

| DTO/interface | Fields và ý nghĩa được khóa |
| --- | --- |
| OrganizationContext | `organization_id`, `profile`, `activity:ActivityRecord`, `people`, `policies:tuple[PolicyRecord,...]`, `budgets:tuple[BudgetRecord,...]`, `grants:tuple[GrantRecord,...]`, `ledger:tuple[LedgerRecord,...]`, `coverage:CoverageWitnessRecord\|None`, `witnesses`, `financial_as_of:UtcDatetime`, `data_origin=SIMULATED`; bỏ records chuỗi/budget_amount như substitute căn cứ |
| PolicyRecord / GrantRecord / BudgetRecord | Business fields tương ứng PolicyVersion/Grant/BudgetDecision, nhưng `witness_keys` thay refs self-SHA: policy có id/version/profile/effect/rules; grant có id/version/actor/actions/scope/allowed_profiles/max_amount/effective interval; budget có id/activity/amount/effect_range/actor/grant_ref |
| LedgerRecord | `id,external_key,kind,employee,activity,payer,payee,amount,event_at,completion_state,reverses_external_key?,witness_keys`; importer kiểm witness/responsibility/binding rồi tạo MoneyEvent, không nhận client verified flag |
| CoverageWitnessRecord | `employee,activity,start,as_of,fund_ids,flow_kinds,opening_by_fund,ledger_version,witness_keys`; missing opening là null/UNKNOWN, không0. Importer tạo CoverageRecord sau validation |
| ActivityRecord | `activity_id,name,occurred_at,profile,authorization:ActivityAuthorization\|None`; không có authorization thì importer không ép AUTHORIZED |
| ActivityAuthorization | `id,activity_id,actor,grant_ref,effect_range,reason,record_key`; import validation kiểm actor/action/scope/time qua cùng company-context boundary |
| OrganizationWitness | `record_key,quote,actor,scope,observed_at`; refs source SHA do importer tính sau serialize context, không yêu cầu JSON chứa hash của chính nó |
| SourceFactGold | `field,read_state,normalized\|None,candidates,source_sha256,page\|record_key,exact_quote,bbox?`; latent/unknown không chuyển thành observable known |
| RelationGold | `kind,from_identity,to_identity,state,refs`; định danh logical được map sang ingestion IDs theo SHA/binding, không theo filename hoặc amount gần giống |
| IssueGold | `kind,field_or_rule,owner_role_or_identity,depends_on_keys,required_answer_kind,required_card_fields,refs`; required set khác optional independent issues |
| ExpectedInstruction | `direction,amount,employee,activity,actionable_count`; kiểm exact action/beneficiary/scope, không chỉ sum amounts |
| StageGold | `stage_id,target_root_role,observable_facts,relations,known_projection,required_issues,optional_issues,expense_dispositions,conclusion_status,actionable_instructions,processing_problems`; zero/unknown/pending được ghi literal đúng trạng thái |
| ActualCheckpoint | `stage_id,target_root_id,target_root_role,case_view,read_set,calls,observed_at`; immutable record tại lúc stage đó xong, không lấy final view chấm lại initial |
| ScenarioInstance | `base_case_id,variant_id,instance_id,sandbox_id,target_root_bindings,ordered_stage_ids`; chỉ là test/eval orchestration metadata, không gửi vào model để chọn outcome |

`quan-sat-duoc.json` và `ket-qua-hop-le.json` có `stages` map stage_id; latent
giữ riêng. `load_gold(case_dir,stage_id)` trả GoldPacket được chọn StageGold,
không trộn các stages. D04 IDs bắt buộc: `ban-dau`→`bo-sung-payer`→`duyet-chi`;
D15: `ban-dau`→`bo-sung-thanh-toan`. D10: `root-a-nop`→`root-b-nop` và root roles
`MAIN`/`COMPANION`. Kich-ban map ID tới tập source/command/context có sẵn ở stage,
không chứa expected route/money/disposition. Stage tương lai không nằm initial read-set.

`CaseWorkflow.import_company_context(context:OrganizationContext,origin:str)->str`
import typed records qua validation/versioning/audit dùng chung với company fixture
production/demo. Existing import_demo_context(path,origin) đọc file rồi delegate;
không second importer riêng cho eval. Ledger/coverage input chỉ trusted server
fixture import; không employee API nâng dữ liệu upload thành quyền/confirmed ledger.
Các *Record là raw JSON DTO; importer tạo domain PolicyVersion/Grant/BudgetDecision/
MoneyEvent/CoverageRecord cùng EvidenceRef từ actual serialized context hash và
witness keys, rồi persist. Không cần hash tự tham chiếu hoặc placeholder SHA.
Raw payload, source hash, compiled records và audit phải khớp; missing witness/
scope/completion không được import như confirmed/covered. Source hash khi context
được cung cấp dạng DTO tính trên canonical serialization do importer sở hữu.
`Grant.allowed_profiles:tuple[str,...]` là refinement DTO ở domain/policy.py và
persisted grant record R3; không role inference. Demo grants rõ TRAVEL; migration
legacy chỉ map TRAVEL khi company/policy record cũ chứng minh profile đó, còn
unknown thì không tự cấp quyền mọi profile. Tests kiểm cả action/scope/profile.

CaseSpec khóa occurred_at/expense dates và financial_as_of. Runner tạo ActivityData
từ mốc case, không datetime.now thay ngày công tác. Financial as-of chỉ thay qua
stage context/coverage có witness; không kéo coverage tới hiện tại chỉ vì đồng hồ
đã chạy. Policy/B áp dụng ở thời điểm chi phí/hoạt động; commit/grant/actor checks
dùng server commit clock ghi riêng. Latency/quota dùng monotonic wall time, không
frozen business clock. Test expiry/current revoke không được bypass bằng as-of cũ.

### A.2. Materialize source bytes mà không lộ path/đáp án

Ở packets.py: `bind_sources(case_dir:Path,packet:PacketInput,*,stage_id:str)
->Callable[[PacketSource],bytes]` khóa registry nguồn stage hiện tại. Resolver chỉ
nhận đúng PacketSource đã bind; validate allowlisted relative file, media/size,
case-contained resolved path, no symlink/traversal và SHA256 tại lúc đọc. Không
resolve nguồn tương lai hoặc file từ dap-an/HUONG-DAN. Path và tên case chỉ nằm
trong closure, không được serialize/prompts. `EvaluationRunner.__init__(workflow,
source_resolver:Callable[[PacketSource],bytes])`; `run(packet,mode)` vẫn giữ signature.

`CaseWorkflow.ingest_sources(ctx:CommandContext,root_id:str,
files:tuple[tuple[str,bytes],...])->CommandResult` async là cùng validated ingest
entry cho multipart API và runner: kiểm session/root/version/caps/media, tạo
storage key/digest server, rồi AttachSources transaction. Không runner copy file
và fabricate SourceUpload ngoài validation path. Integration spy khớp bytes/hash
từ resolver tới storage và provider, không chỉ tồn tại metadata filename/SHA.

## B. 15 case và đáp án phải được chứng minh

Đơn vị bảng: triệu VND. P/R0 chỉ khi coverage đủ; grants system8/4 và approver20
explicit. Mỗi case có activity/date/invoice/issuer/payment identities thật sự được
thể hiện trên source/context. Không tạo issuer giả khác nhau chỉ trong manifest.

| ID / folder | Nguồn và context ban đầu | Kết quả initial / bước tiếp theo |
| --- | --- | --- |
| D01 case-01-cong-ty-chi-them | Incurred8; employee payment5; company-direct3; A2; B8; history đủ | E5/C3/S3, một PAY3. Sau record received3 có căn cứ mới S0/SETTLED |
| D02 case-02-nhan-vien-hoan-tien | E/T1.5; A2; B8; coverage đủ | COLLECT0.5. R0.5 công ty nhận =>S0 |
| D03 case-03-quyet-toan-can-bang | E/T2; A2; B8; P/R0; không pending | BALANCED/SETTLED, không instruction0; có refs cho cả zero coverage |
| D04 case-04-chua-ro-nguoi-thanh-toan | Incurred5; payer chưa rõ; A/P/R0 có coverage; B8 | FACT employee yêu cầu proof. Sau proof employee paid5 => AUTHORITY ISSUE_PAYMENT5; approver có quyền quyết định5 mới PAY5. Không mặc định đã giải hết từ một answer |
| D05 case-05-mau-thuan-lien-ket-cong-viec | Invoice3 và payment3 mâu thuẫn activity/beneficiary; A/P/R0; B8 | FACT binding, giữ cả2 refs. Proof binding đúng/new source giải rồi recheck; không chọn theo confidence |
| D06 case-06-chi-phi-vuot-ngan-sach | T10 đã phát sinh; E5/C3/unpaid2; A2; B8 | POLICY T>B; S candidate3 không thành instruction trước ngoại lệ. Exact EXCEPT_POLICY cho budget rule/T10 trong scope, không tự sửa B để pass |
| D07 case-07-vuot-quyen-cong-nhan-chi-phi | T/E9; A6; B12 => S3 | AUTHORITY RECOGNIZE_COST9; decision đúng quyền20/scope/basis mới auto issue3, không xin lại mọi routine |
| D08 case-08-vuot-quyen-tao-yeu-cau-chi | T/E8; A2; B8 =>S6 | AUTHORITY ISSUE_PAYMENT6, không hai orders3 |
| D09 case-09-thieu-lich-su-tam-ung | Employee-paid3; B8; opening/coverage A/P/R thiếu rõ ràng, không witness nói đủ | FACT accountant; không S0/A0. Responsible coverage mới xác lập A/P/R và recheck |
| D10 case-10-chung-tu-trung-lap | Cùng invoice/paid portion3 ở native+scan; A/P/R0; B8 | Same root T/E3 một lần/PAY3. Companion root khác cùng obligation không chi lần2; setup qua workflow/usage thật. Có intentional_clone_group; không cộng companion/representations vào15 independent cases |
| D11 case-11-loai-khoan-chi-ca-nhan | Personal0.5 rõ; A/P/R0 đã xác minh | EXCLUDED0.5/rule/reason/refs, T/E0 và BALANCED. Biến thể A2 =>COLLECT2, không xóa ứng |
| D12 case-12-khoan-chi-ngoai-pham-vi | Khoản FX material liên hệ activity, currency/amount hiện rõ; context còn lại đủ | UNSUPPORTED ảnh hưởng tiền có next_action; không quy đổi/loại như personal hoặc gọi đúng escalation POLICY |
| D13 case-13-giao-dich-chua-hoan-tat | Supplier employee-paid3; bank advance2 đang xử lý/debit-only, funding aggregate chưa xác minh | FACT accountant/pending; không coi2 là received, không giả không có ứng0 để issue3; xác minh kết quả event trước kết luận |
| D14 case-14-pdf-nhieu-trang-nhieu-chung-tu | >=3 trang: invoice3/payment employee3/advance2; B8/history đủ | Unit roles/locators đúng trang, E3/A2/S1 =>PAY1; không conflict vì role khác nhau |
| D15 case-15-bo-sung-khoan-da-thanh-toan | Cùng incurred invoice10; E5/C3/unpaid2/A3/B12 =>I2 NOT_STARTED | Bổ sung verified employee-paid portion2 =>T10/E7/C3/unpaid0/S4; supersede remainder2, một I4, không cộng incurred lần2 |

Tối thiểu mỗi root có bảng kê hoạt động/chi phí, final expense source và các proof
payment cần thiết. D01/D06 tách employee/company portions; D04 cố ý thiếu proof
payer ở initial folder; D09 không tạo coverage witness giả; D13 PDF ghi pending;
D15 proof phần mới ở folder bổ sung. Không nộp cả ba stage cùng lúc.

Gold ghi literal: critical facts(state/value/candidates/refs), relation states/
bindings, expected T/E/C/A/P/R/unpaid/S khi xác lập được, issue set/owner/dependencies,
dispositions, conclusion và exact actionable instruction(direction/amount/beneficiary).
Ở unknown chỉ lưu candidates hoặc latent riêng; không assert known bằng số latent.
Expected stage initial và assisted riêng, không lấy final sửa đúng để cứu initial sai.

**D10 gate hai roots bắt buộc:** chạy root A trước, native+scan tạo một verified
obligation/một PAY3; root B hoạt động khác trong **cùng tenant/usage registry** nhận
cùng economic key phải blocked double eligibility/instruction và chỉ rõ owner A.
Không PASS D10 chỉ nhờ same-root dedup. D10 là một scenario trong15 primary roots;
companion là dependent control, báo riêng. Nếu có16 roots thực thi, báo15 primary
và1 dependent, safety union vẫn kiểm **mọi** root. D10 scenario PASS cần cả hai
checkpoints; không giấu unsafe companion bằng loại nó khỏi N independent.

## C. File Map cho triển khai

| Task | Create/modify/delete exact paths | Trách nhiệm |
| --- | --- | --- |
| R0 | docs/final/IMPLEMENTATION_STATUS.md; test files ở tasks dưới | Reconcile checkout/evidence; giữ các local edits đang có |
| R1 | scripts/sinh_du_lieu_kiem_thu.py; scripts/du_lieu_kiem_thu/__init__.py,ho_so.py,pdf.py,dap_an.py; src/invoice_referee/evaluation/models.py,packets.py; tests/unit/test_pdf_generation.py,test_packet_inventory.py,test_dataset_build.py | Một entry sinh15 case/stages/technical probes; typed definitions/templates/literal gold, loader/layout/digests |
| R2 | data/kiem-thu/**; data/tham-khao/uc-03/**; scripts/dev.py; src/invoice_referee/config.py,cli.py,api/routes.py; docs/final/RUNBOOK.md,PDF_DATA_REVIEW_AND_UI_CHECKLIST.md,IMPLEMENTATION_CONTRACTS.md; plan gốc File Map | Publish bộ thay thế; cleanup allowlist/path migration/docs, không đổi nghiệp vụ |
| R3 | workflow/service.py,money.py,controls.py,db.py,schema.sql; create workflow/instructions.py; domain/commands.py,finance.py,issues.py,policy.py; reconciliation/policy.py,finance.py; tests/integration/test_authority_scope.py,test_money_execution.py,test_controls_races.py,test_financial_verification.py,test_migrations.py | Quyền/proof/fulfillment/Stop/read-set; migrations giữ actual; delegates thay chỗ mixed trách nhiệm |
| R4 | evidence/reader.py,pdf.py,mistral.py,xkiro.py,replay.py,planning.py,trace.py,m0_live.py; create evidence/prompts.py,runtime.py; workflow/jobs.py,snapshots.py,service.py; api/app.py,routes.py; scripts/dev.py; tests/unit/test_provider_contracts.py; tests/integration/test_live_wiring.py,test_reader_source_support.py,test_preview_job.py,test_restart.py | Compose reader đúng mode; bounded jobs/native/OCR/LLM/admissibility/caches; không I/O trong transaction |
| R5 | create workflow/decisions.py; workflow/service.py,snapshots.py,schema.sql; api/routes.py,views.py; frontend/src/features/intake.tsx,questions.tsx,dossier.tsx,approval.tsx; frontend/src/api.ts,types.ts; tests/conftest.py,factories.py; tests/integration/test_raw_six_cases.py,test_submit_handoff.py; frontend/e2e/six-cases.spec.ts | Apply owner/source/decision trên basis thật;6 cases xuyên UI |
| R6 | workflow/money.py,instructions.py,controls.py,jobs.py,service.py; frontend/src/App.tsx,features/execution.tsx,controls.tsx,styles.css; tests/integration/test_money_execution.py,test_controls_races.py,test_restart.py; frontend/e2e/execution.spec.ts,controls-audit.spec.ts,role-workspaces.spec.ts,source-preview.spec.ts | Đóng12money/8human-control/6UX; UI cùng backend guards |
| R7 | evaluation/models.py,packets.py,runner.py,scorer.py,reports.py; cli.py; api/routes.py,views.py; frontend/src/features/verify.tsx,api.ts; tests/factories.py; tests/unit/test_scoring.py,test_eval_visibility.py; tests/integration/test_verify.py; frontend/e2e/verify.spec.ts | Core4/Esc5 selection thật, independent facts/refs/issues/money scoring/reports |
| R8 | docs/final/IMPLEMENTATION_STATUS.md,RUNBOOK.md,RELEASE_EVIDENCE.md; data/kiem-thu/CHECKLIST.md; .runtime/evidence/** | M0/baseline proof, known limits/next tasks. Results ignored, chỉ summary đã lọc public |

Python shorthand `workflow/`, `evidence/`, `domain/`, `reconciliation/`, `evaluation/`,
`api/`, `runtime.py`, `config.py`, `cli.py` trong bảng nằm dưới `src/invoice_referee/`.
Tạo helper khi task dùng; không empty services. Domain không import SQL/gold/LLM.
Tách instruction/financial confirmation/decision khỏi service theo responsibility,
không chia arbitrary line count hoặc thêm repository/event bus.

## R0 — Khóa snapshot và xác định fix nào đã đạt

**Interfaces:** giữ `CaseWorkflow.execute(ctx,command)->CommandResult` async và
`view(ctx,id)->CaseView`; test qua HTTP/commands thật, fake provider tại adapter.
- [ ] Ghi branch/HEAD, local edits/owner, interpreter selectors; đọc AGENTS/contracts và graph cho từng task. Không thay đổi scorer đang có local edits nếu chưa hợp nhất với owner.
- [ ] Chạy baseline offline hiện tại: `rtk proxy uv run --frozen --python 3.12 pytest`; Node24 scoped `npm test`/`npm run build` trong frontend. Ghi exit/count, không chép166/9 lịch sử thành hiện tại.
- [ ] Đưa các phản ví dụ review vào test owning task: LIVE không raw nhưng issue từ seed; wrong scope/amount grant; bare/forged proof; answer ignored; OPEN→Stop→Resume reset; wrong direction và false BALANCED scorer. Existing fix pass thì giữ; fail thì đóng đúng root cause.
- [ ] Checkpoint ghi các mục IMPLEMENTED_UNVERIFIED/FAILED/NOT_RUN và current next task. Không đặt T11 kế tiếp khi raw/Verify gates còn thiếu.
**Gate:** Biết snapshot thực và những gaps còn lại; không claim fix từ commit message.

## R1 — Script sinh PDF và packet có nguồn hỗ trợ

**Interfaces:** `CaseSpec` và `DocumentSpec` strict ở `scripts/du_lieu_kiem_thu/ho_so.py`:
case_id,slug,activity,source identities/visible fields,stage file sets,observable
organization records; không runtime fields forced E/S/route. Literal oracle nằm
`dap_an.py`, không được tính bằng Reconciler/scorer. `build_case(spec:CaseSpec,out:Path)
->ManifestEntry` ở script entry; `render_document(spec:DocumentSpec,out:Path)
->tuple[EvidenceRef,...]` ở pdf.py trả logical document locators/digest/page/quote,
không Facts/permissions. Scorer map logical source tới actual source digest/ingest ID;
không đòi runtime UUID phải trùng ID generator.
CLI `main(argv:list[str]|None=None)->int` ở `sinh_du_lieu_kiem_thu.py`.

Loader `load_input(case_dir:Path,*,stage_id:str="ban-dau")->PacketInput` chỉ trả raw
sources đã chọn stage + organization/declaration; `load_gold(case_dir,*,stage_id)
->GoldPacket` scorer-only. `digest_packet_input(case_dir,*,stage_id,mode)` hash
context/declaration và nguồn đã available ở stage đó (thêm stub reading chỉ ở STUB),
không hash future source như current input basis. Inventory digest riêng hash tất
cả managed files/stages; `digest_packet_gold` hash cả3 gold files/stages, không chỉ
latent. `load_manifest`
giữ schema version/data_version, case ID, slug, paths, source/family/clone grouping.
`load_input` luôn loại ban-doc-stub; `load_stub_readings(case_dir,*,stage_id)` ở
packets.py là reader-only helper, chỉ gọi bởi runtime STUB. Không lấy mode string
của report làm lý do load transcript trong `PacketInput`. Typed context/StageGold/
ActualCheckpoint/source resolver theo A.1/A.2 là shared contract của task sau.

- [ ] RED `tests/unit/test_pdf_generation.py`: exact15 IDs/slugs ở B; không accents/spaces trong folder; file roles/source fields đúng case; native date không thành amount; E/S/allowed không lọt input; partial build không được claim15; gold change đổi digest; unknown source không in latent vào hidden text.
  Fixture `generated_d04` gọi R1 build_case tại tmp_path; proof stage dùng
  `02-bo-sung/01-xac-nhan-nguoi-tra.pdf` và phải vắng ở initial:
  ```python
  def test_initial_stage_excludes_future_proof(generated_d04):
      p = load_input(generated_d04, stage_id="ban-dau")
      assert all("xac-nhan-nguoi-tra" not in s.filename for s in p.sources)
      assert "ban-doc-stub" not in p.model_dump_json()
  ```
  Thêm `test_d01_d09_context_coverage_differs`, `test_stage_gold_d04_d15_is_separate`,
  `test_future_source_edit_keeps_initial_basis`, `test_resolver_materializes_exact_bytes`;
  không chứng minh gold isolation chỉ bằng tìm từ trong JSON (R7 có spy đọc file).
- [ ] Run: `rtk proxy uv run --frozen --python 3.12 pytest tests/unit/test_pdf_generation.py tests/unit/test_packet_inventory.py -q`; failure phải do missing behavior, không do thiếu môi trường.
- [ ] Implement một CLI với4 hành vi rõ: `--output`, `--cases all|01,02,...`, `--check`, `--replace-generated`. Relative output resolve theo project root; absolute temporary output được test, không phụ thuộc cwd. Không provider/model calls. `--check` read-only, exit nonzero nếu invalid/missing/stale; lỗi giữ output cũ. Output chưa tồn tại/rỗng được khởi tạo; output có nội dung phải có managed dataset marker. Refuse `/`, repo root, `data` root, symlink/traversal/nonempty unmanaged target.
- [ ] ReportLab dùng NotoSans nhúng, layout invoice/bảng kê/receipt/phiếu chi/ledger theo vai trò; VND integer, subtotal/tax/gross literal đúng; negative defects được khai báo. Deterministic dates/seed/metadata (`invariant=1`), hai build cùng spec có cùng source hashes. Tái dùng font/OFL, không font máy cá nhân.
- [ ] Làm scan từ trang render thành image-only PDF/PNG/JPEG; mask trường từ source drawings trước rasterization, không hidden text/numeric metadata tiết lộ. D14>=3 pages/roles; D10 native+scan clone có chủ đích. Không tạo55 PDF chỉ thay ID/metadata.
- [ ] Generate các future receipts/paid portions và4 technical M0 inputs thật, ở stage/folder đúng; không thêm future receipts vào initial. HUONG-DAN có tên hoạt động/nhân viên, thứ tự chọn tệp/role/expected/refs/lỗi cố ý. CHECKLIST được tạo nếu chưa có; không ghi đè notes/ticks người dùng. Test results luôn gắn data digest; dataset đổi làm result cũ OUTDATED, không giữ PASS như hiện tại.
- [ ] Gold literal có3 tầng và stages, quality state/ref/binding/required issue sets/expense dispositions; số calculated thuộc allowed, không pretending là observable quote. Đọc chính page render kiểm từng critical field/relation; ghi người/agent adjudicate và source digest, không gọi review mô phỏng là practitioner feedback.
- [ ] GREEN inventory/generation tests; render toàn bộ pages; xem thumbnails và phóng lớn critical numbers/tables/scans. Giữ intentional defects; không sửa cho model dễ pass. `--check` xác minh bytes/render clone groups và nội dung/trường theo spec, không chỉ manifest labels. Cùng template disclosure, không claim unseen-family.
**Gate:**15 roots có raw/context/gold thực, tách stages, nội dung phân biệt được; source quality đã kiểm trực quan. Không gold/transcription lấp proof thiếu.

## R2 — Publish dữ liệu mới và dọn PDF không dùng được

**Interfaces:** generated manifest là allowlist ownership của script; `PacketInput`
vẫn là application-visible DTO. Dataset source root default ở Settings dùng một
giá trị duy nhất `data/kiem-thu`, resolved theo project root, không theo cwd.
- [ ] RED: `test_safe_replace_preserves_unmanaged_files`, `test_generator_failure_keeps_previous_dataset`, `test_old_paths_have_no_active_consumer`, `test_reference_not_loaded_as_final`, `test_initial_stage_excludes_future_receipts` trong generation/packet tests.
- [ ] Build sibling staging cùng volume; images/evidence ở `.runtime/kiem-thu-build`.
  Publish protocol dưới đây, không gọi hai rename là atomic transaction. Preserve
  notes/CHECKLIST/unmanaged files hoặc conflict rõ; không xóa để os.replace chạy được.
- [ ] Publish protocol: (1) lấy exclusive publish lock ngoài dataset root, loader/
  materialization dùng cùng read lock; (2) build complete staged tree, đưa unmanaged
  files được phép giữ vào tree, validate; (3) ghi/fsync publish journal với exact
  managed paths/digests, staging/backup/target cùng parent; (4) rename old→backup,
  staging→target; (5) validate target rồi mark completed/retire backup allowlist.
  Crash recovery theo journal: target mới valid thì hoàn tất; target vắng/invalid
  thì restore backup valid. Không chạy reader trên partial tree và không delete
  backup trước new target validation. Test inject failure/crash từng rename,
  existing nonempty output, unmanaged metadata và busy reader lock.
- [ ] Update loader, dataset defaults ở config/CLI/API, dev context path, tests imports/dataset fixtures, runbook/Docker copy nếu cần. Xóa entry generator cũ `scripts/build_packets.py` sau chuyển mọi consumer; không giữ hai generator trái nhau. Không tạo wrapper chỉ để giữ import test cũ.
- [ ] Sau new corpus và consumer path tests pass, xóa55 PDF evaluation lỗi cùng obsolete generated packet JSON/manifests liên quan tại `data/evaluation/**`, theo danh sách exact paths từ inventory/HEAD. Giữ deletion report/hash/commit recoverable trong evidence; không copy PDF lỗi sang archive active. Không xóa `.runtime` results, M0 probe hợp lệ, DB, uploads, fonts hoặc file người dùng ngoài allowlist.
- [ ] Chuyển UC-03 giữ bytes sang `data/tham-khao/uc-03/case-XX-<title-khong-dau>`; sửa references/path ở manifest/README, đánh LEGACY_REFERENCE. Clone TC01/TC12 có chủ đích giữ. App/Verify không tự load references; không lấy cap100m/expected cũ cho final.
- [ ] Update layout mapping contracts §7, plan gốc File Map, QA checklist và RUNBOOK trỏ một thư mục chính. Source findings lịch sử gắn snapshot, không dựng links tới PDF đã xóa như nguồn hiện tại. Không chỉnh accepted financial rules.
- [ ] GREEN data/path/clean-generation tests và startup health/config (không claim AI đã nối). Developer chạy thử từ cwd khác. Kiểm git diff đúng deleted files; no broken active manifest refs/no orphan generated PDFs.
**Gate:** Mở `data/kiem-thu` là thấy cách test;15 case chính, không corpus cũ lẫn vào Verify. PDFs hợp lệ reference không bị xóa vì khác scope.

## R3 — Đóng safety guards trước khi LIVE có financial effects

**Interfaces:** `verify_money_claim(ctx:CommandContext,scope:CaseScope,money:RecordMoneyInput,
evidence:tuple[EvidenceRef,...])->MoneyEvent` ở workflow/money.py được gọi sau
server actor/grant/source lookup; không nhận client verified/allocated. Responsible
confirmation là record field/value/scope/time/reason/server verifier được quyền,
khác chuỗi completion tùy ý. `reconcile_instruction(cx,*,root_id:str,scope:CaseScope,
assessment:AssessmentResult,now:datetime)->CaseState` ở workflow/instructions.py;
financial writes/audit cùng transaction.
- [ ] RED tests: unrelated grant, omitted amount bypass, action/scope/profile/time mismatch,25m decision with20m grant, actor/context spoof; preserve valid limits8/4/20 inclusive; expiry after valid issue khác explicit revoke/new action.
- [ ] RED money tests: bare claim/ref existence/arbitrary completion text không confirm; responsible valid confirmation được chấp nhận; wrong beneficiary/activity không allocate; duplicate external key đổi payer/payee/scope/time/kind/amount conflict; reversal đúng original/net bound; observed-unallocated material không bị bỏ rồi S0.
- [ ] RED instruction tests: OPEN→Stop→Resume giữ execution UNKNOWN; same ID không reset qua INSERT OR REPLACE; partial I3/P1 giữ remaining2; prior payment không fulfill successor; real overpay4 onI3 giữP4/incident1; new cost same S đổi basis; current gates trước retain/replacement.
- [ ] Run: `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_authority_scope.py tests/integration/test_financial_verification.py tests/integration/test_money_execution.py tests/integration/test_controls_races.py -q`.
  Literal regression (app_fixture helper giữ completion/refs inputs):
  ```python
  async def test_bare_claim_never_settles(app_fixture):
      v = await app_fixture.record_received(
          instruction_amount=4_000_000, received=4_000_000,
          completion_claim=None, refs=(),
      )
      assert v.state != "SETTLED"
      assert v.actual_money.P.value != 4_000_000
  ```
- [ ] Giữ sửa hiện có khi đúng; thay boolean presence proof bằng admissibility/binding/actor/confirmation check. Quyền RECORD_ACTUAL/CONFIRM/STOP/MarkExecution có explicit grant, không bypass bằng persona accountant/approver. Server derive required amount cho action, không omit amount để né cap.
- [ ] Instruction tạo ID mới cho effect mới; không INSERT OR REPLACE để reset lịch sử. Net fulfill qua allocation event→instruction, không tổng mọi P/R của root cho từng order. Actual gross append-only; reversals linked, predecessor không tự reopen.
- [ ] Context_version monotonic tăng mọi policy/grant/B/exception/revoke/import material change. Snapshot/ref/read-set lưu thật, không hardcode1/0. STOP newest-version signal; RESUME/edit/decision/MarkExecution guard basis/version và quyền đúng.
- [ ] Migrate schema bằng SQLite user_version/transaction (không thêm Alembic); `test_upgrade_keeps_existing_actual_instruction_and_audit` và failed migration rollback. Không bắt reset DB để fix version hoặc mất actual cũ.
- [ ] GREEN tests trên DB tạm; backend mutation với foreign ref/scope/epoch bị chặn, current migrations/restart pass. Worker commit gate vẫn phải gọi trong luồng thật ở R4/R6, không chỉ unit helper assertion.
**Gate:** Các phản ví dụ quyền/tiền/Resume đã đóng ở command/transaction boundary, không chỉ nhãn UI.

## R4 — Nối runtime và Reader đúng mode với jobs bền

**Interfaces:** `build_workflow(settings:Settings,mode:ProviderMode,*,db:Database,
uploads_dir:Path,context_path:Path)->CaseWorkflow` ở runtime.py, dùng chung dev/CLI/
Verify; reader injected vào CaseWorkflow, không forced observations. `EvidenceReader.read(source,
requested_fields,budget)->ReadResult` async; Mistral adapter đọc rendered bytes/page
với budget, xkiro structured result validated thành units/observations/relations.
`CaseWorkflow.execute(Submit)` enqueue/attach one durable job, trả job_id/PROCESSING;
worker READ→ASSESS→commit; `view` đọc persisted status. App lifespan start/stop2
bounded workers; CLI dùng cùng worker lifecycle và bounded wait terminal.
- [ ] RED `test_live_submit_without_sources_cannot_issue_seed_money`, `test_live_new_pdf_changes_read_result`, `test_stub_transcription_forbidden_in_live`, `test_replay_requires_matching_recording`, `test_submit_during_preview_reuses_job_and_counters`, `test_reader_never_records_money_or_grants`.
- [ ] Run: `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_live_wiring.py tests/integration/test_preview_job.py tests/integration/test_reader_source_support.py tests/unit/test_provider_contracts.py -q`.
- [ ] Runtime bind LIVE to configured Mistral+xkiro, STUB to digest/field/page literal reads, replay to actual matching recordings. Bỏ activity-level transcription fallback trên assessment; không chỉ đổi mode string. LIVE key/model thiếu fail named gap; no usable source thì WAIT/TECHNICAL phù hợp, không seed expense để issue.
- [ ] Native pypdf + rendered OCR theo source representation; đọc tất cả relevant pages trong cap. Xkiro trích field/role/quality/payer/binding/quote theo schema; bỏ extractor “lấy số đầu tiên cho mọi field”. Model JSON valid không tự tạo Fact.KNOWN; admissibility kiểm quality/role/quote/ref/relation/context. Source instructions không thành tool permissions.
- [ ] Pin tests date/invoice number khác amount; hidden native450/render480 conflict giữ2 observations; malformed source ref/page/model tool action denied; mixed PDF roles không whole-file conflict; partial timeout page NOT_READ; unrelated source quarantine khác material unknown.
- [ ] Persist sources/read-results/representation coverage/prompts/models/counters/recovery keys; cache tenant+digest+model/prompt/schema/representation/requested_fields. Cached result remap source refs đúng root, không tenant leak/financial decision reuse. Preview confirm không reset budget/call OCR lại vô ích.
- [ ] Provider I/O ngoài transaction; read-set/epoch/context/ledger/usage kiểm ngay commit. Restart không lost submit; old attempt results inactive audit; queued leases/counters giữ. Domain snapshot từ admitted evidence + trusted records, không invented quotes “employee paid” hoặc missing parsed amount thành0.
- [ ] GREEN adapters/fake-provider integration; browser scan→preview/source quote/correction/submit/job outcome với mock HTTP ở adapter. Bằng chứng này ghi PROVIDER_MOCK, chưa LIVE. Quotas/timeout/limits errors có ProcessingProblem affected fields/next_action.
**Gate:** Một nguồn mới thực sự đi đến assessment qua reader đã bind; no-gold/no-seed-money và Stop commit protections có test xuyên pipeline.

## R5 — Khép phản hồi/decision và chạy6 case đầu qua UI

**Interfaces:** workflow/decisions.py nhận Answer/DecisionCommand + server context,
persist confirmation/exception/eligibility decision theo đúng basis; service delegates
trong transaction và enqueue recheck. `load_input(...,stage_id)` chỉ đưa proof stage
mới sau hành động tương ứng. CaseView.conclusion/QuestionCard/refs là server projection.
`raw_harness` fixture tại tests/conftest.py có `submit(case_id:str)->CaseView`,
`apply_stage(case_id:str,stage_id:str)->CaseView`; dùng HTTP upload/commands, cùng
context importer và real provider adapters với MockTransport. Provenance ghi
`TEST_HTTP_MOCK`, không claim external LIVE evidence. Không đọc gold để tạo mock
output; mock read responses có source-supported literals riêng trong factories.py.
- [ ] RED `test_valid_proof_answer_changes_affected_fact`, `test_employee_declaration_does_not_confirm_money`, `test_policy_exception_exact_rule_scope_not_waive_fact`, `test_authorize_total_E9_then_issue_S3`, `test_answer_stale_basis_keeps_history_no_apply`, `test_decision_does_not_resolve_foreign_root_issue`.
- [ ] Run: `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_raw_six_cases.py tests/integration/test_submit_handoff.py -q`; fixtures upload raw files qua API/reader, không SQL inject transcription/reconciler outcome.
  ```python
  async def test_raw_d01_has_one_payment(raw_harness):
      v = await raw_harness.submit("D01")
      assert v.actual_money.E.value == 5_000_000
      assert v.actual_money.C.value == 3_000_000
      assert [(i.direction, i.amount) for i in v.instructions
              if i.status in ("ISSUED", "PARTIAL")] == [("PAY", 3_000_000)]
  ```
- [ ] Apply Answer.value/refs vào declaration hoặc admitted source/authorized Confirmation đúng kind/owner; persist before/after + supersession. Employee cung cấp payer proof không được tự cấp financial truth từ “tôi trả”; accountant confirmation đúng grant có field/time/basis/reason. Recompute related gates, không resolve cảroot bằng một text answer.
- [ ] Decisions lưu quyền/amount/action/effect range/policy rule/basis/refs. APPROVE E9 reuse prior eligibility đúng basis; ISSUE_PAYMENT5 riêng sau D04 FACT. Không tăng system grant mặc định8/4 để cho case pass; không sửaB như substitute exception.
- [ ] UI preview giữ source/correction riêng, missing field không ép đoán; question card known facts/excerpt/scope/rule/amount/action/impact đủ một response cho issue. Không tự chế `basis:<issue_id>`; gửi basis server phát. Poll job/view, giữ draft khi409, không đổi success message thay verification.
- [ ] Run headed browser **với workdir `frontend/`**, Node24 scoped: `rtk proxy npm exec -- playwright test e2e/six-cases.spec.ts --headed`. Không giả định `npm --prefix ... exec` chuyển cwd cho Playwright. Chính6 cases D01/D02/D03/D04/D06/D07. Assert money/direction/refs/owner/conclusion/audit bằng literal gold đã adjudicate, không dùng release flag của scorer cũ.
- [ ] D04 kiểm initial FACT→proof→AUTH5→authorized decision→PAY5; D06 initial POLICY→exact exception→PAY3; D07 initial AUTH E9→recognition→PAY3. Initial failure không được xóa khi assisted final đúng. D01–03 không cần accountant eligibility signoff.
**Gate:**6 cases đi xuyên raw/API/UI, human response thật sự làm workflow tiến đúng, gold không lộ qua model; screenshots/traces/N/mode recorded.

## R6 — Kiểm tiền, controls, các case còn lại và UI theo vai trò

**Interfaces:** RecordActual/MarkExecution/Control/Override dùng contract R3/R4/R5;
financial UI đọc case.scope/instruction, không hardcode `activity:travel-a`, employee,
bank transaction UUID mới thay external key thật hoặc kind luôn reimbursement.
ScenarioInstance của A.1 được dùng cả hướng dẫn manual và fixtures: một sandbox
fresh cho mỗi nhánh độc lập, sau đó đúng ordered commands. Khi manual, dùng một
phiên demo/sandbox mới hoặc base root mới theo guide, không reset toàn DB.

| Nhánh tiền | Setup và sharing đã khóa |
| --- | --- |
| M01→M02 | Cùng instance D01: I3, P1 rồiP2, cùng root/ledger |
| M03 | Instance D01 mới: I3, cash3; không dùng root đã P3 của M02 |
| M04 | Instance D02 mới: COLLECT0.5, company receivedR0.5 |
| M05/M06/M09/M11 | Mỗi mục instance D01 mới; pending/wrong-payee/overpay/historic violation không ảnh hưởng nhánh khác |
| M07 | Instance mới, replay same command và new command same external key trên chính một event |
| M08 | Instance mới, original event rồi conflicting payload từng subvariant; đổi payee/scope/kind/time/amount là từng fixture riêng |
| M10 | Instance mới I3→confirmedP1→linked reversal1, không tiếp trạng thái M02 |
| M12 | Một instance variant D15 riêng: invoice incurred8, E6/A2→I4; P2 và closed batch; paid portion2→E8/P2/S4→newI4; reverse oldP2→S6/AUTH. Cùng tenant/root/usage giữ predecessor/successor; không lấy root D15 chính T10/A3 |

R1/R6 generate companion inputs/context/gold của từng nhánh tại subfolder
`bien-the-XX-<mo-ta>` đúng tên không dấu. Các biến thể và companion được báo riêng,
không cộng vào15 primary roots. C01–C04 cũng cô lập trừ các steps ghi rõ cùng instance.
- [ ] RED/extend tests D05/D08–D15 và M01–M12/H01–H04/C01–C04 trong QA checklist.
  Pin reversal linked, over/duplicate reversal, company-direct personal obligation
  material, paid-ineligible business vẫn ởT/unpaid theo gross, new portionE8→9.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 pytest tests/integration/test_money_execution.py tests/integration/test_controls_races.py tests/integration/test_restart.py -q`; injected delayed reader/context update/crash phải là worker đang READ/ASSESS thật, không đợi barrier rồi mới bắt đầu submit.
- [ ] Generator R1 thêm companion receipts/steps nếu test cần: bank/cash full3,
  partial1+2, collect0.5, overpay4, pending/failed, wrong payee, reversal; filenames
  là loại chứng từ/trạng thái ngân hàng thực, outcome math nằm guide/gold. M12 setup
  oldI4/P2→newI4→reverse oldP2→S6 qua workflow; no SQL mutation để fake life cycle.
- [ ] MarkExecution OPEN trước giao ngoài app; CLOSED_CONFIRMED phải có proof/responsible record. Stop giữ actual; Resume current context/unknown execution chặn replacement; hết hạn issuer không xóa actual hay tự bắt reapprove mọi receipt; explicit revoke kiểm current action. Supplement sau SETTLED tạo revision giữ actual.
- [ ] Tách workspace theo persona và allowed_actions server: employee nộp/bổ sung,
  accountant xác minh/execute, approver decisions exact scope. Source viewer side-by-side/page/ref; money upload→preview/correction→responsible confirm. Bên chi/nhận, method/sourcefund/external key/time đúng chứng từ, backend mapping identity thay nhân viên nhập ID.
- [ ] Human-readable labels cho states/status/owners/money; enum/run/epoch/model chỉ Debug. Backend vẫn deny trái quyền khi gọiAPI trực tiếp. HTTP/context/scorer không nhập data_origin trái sự thật; audit snapshot/why/actor/refs immutable.
- [ ] GREEN backend suite và headed `e2e/execution.spec.ts`, `controls-audit.spec.ts`,
  `role-workspaces.spec.ts`, `source-preview.spec.ts`;6UX checks với keyboard/error/
  stale state/two sessions. Ghi các UX review chưa có practitioners là nội bộ,
  không claim user impact. Financial responsibility verification đúng công việc,
  không thêm một vòng duyệt routine để che lỗi pipeline.
**Gate:**15 development scenarios có source/evidence và money/human/control/UX
items của R6 pass; Verify còn NOT_RUN tới R7/R8, adaptive V07 DEFERRED tới T11.
Mapping48 mục vẫn đầy đủ, không tick các phần chưa chạy. Synthetic receipt không
được mô tả là giao dịch ngân hàng đã được xác thực tự động.

## R7 — Scorer độc lập, Core4/Escalation5 đúng bộ

**Interfaces:** EvaluationRunner.run(packet:PacketInput,mode)->ActualResult theo
contracts, dùng build_workflow/upload→preview→confirmed submission→job/view thật.
ActualResult có typed facts/relations/ref locators/dispositions/instructions/
issues dependencies/snapshots/attempt timeline/technical status. Không bool refs_ok
do runner tự hardcode. IndependentScorer.score(actual,gold)->ScoreRow sync, không
gọi Reconciler/admissibility để lấy chính logic app làm đáp án.
Runner dùng source_resolver và ingest_sources của A.2; importer/clock/stage schemas
theo A.1. ActualCheckpoint đối chiếu đúng StageGold; parent/companion D10 theo B.
- [ ] RED test wrong direction equal amount, wrong beneficiary/root/currency,
  two orders cộng đúng tổng, wrong source/page/quote/digest, missing required issue,
  false BALANCED with known A/P but POLICY, legitimate balanced completion,
  EXCLUDED personal required, pending-nooutput notAUTO, technical notcorrect escalation.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 pytest tests/unit/test_scoring.py tests/unit/test_eval_visibility.py tests/integration/test_verify.py -q`. Preserve/hợp nhất scorer edits người khác; test lại phản ví dụ, không apply bản cũ.
  Factory `literal_actual_d01()->ActualResult` ở tests/factories.py có valid refs/
  scope/amount từ literals độc lập; chỉ mutate direction để pin phản ví dụ:
  ```python
  def test_wrong_direction_same_amount_fails(d01_gold):
      actual = literal_actual_d01()
      wrong = actual.model_copy(update={"instructions": (
          actual.instructions[0].model_copy(update={"direction": "COLLECT"}),
      )})
      assert IndependentScorer().score(wrong, d01_gold).unsafe_action == 1
  ```
  Pin `test_initial_failure_survives_assisted_success_d04`, D15 per-stage money,
  D10 rootA/rootB gate, occurred_at/financial_as_of vs current grant/revoke time.
- [ ] Runner copy raw bytes vào generated upload storage có validation/digest;
  import genuine observable org context đầy đủ (grants/B/history), không ép hoạt
  động authorized nếu packet không có record. Không seed transcription ở LIVE/
  replay. Initial run cấm auto-handoff future proofs; assisted steps qua đúng
  actor/commands giữ initial record. Chờ terminal bounded; failure/timeout record,
  không “không instruction ⇒AUTO/BALANCED”.
- [ ] Scorer kiểm required issue set/dependencies/owner/question/ref support,
  critical facts quality/relations, exact direction/amount/beneficiary/card/cost
  disposition. Unknown-source hallucination đúng latent vẫn fail. Unsafe action
  OR unsafe affirmative union dedup root; wrong routing/support fail rubric,
  không trộn mọi wrong owner vào action-effect count. Report từng lỗi rõ định nghĩa/N.
- [ ] Suite selection từ manifest IDs: Core4=[D01,D02,D03,D11] tuần tự;
  Escalation5=[D01,D02,D03,D04,D07] initial3AUTO+2human; development=15. POLICY D06
  chạy riêng, không làm Esc5 thành6. Max2 independent Esc scenarios, shared
  predecessor steps tuần tự. API/CLI/UI dùng cùng selector/root settings.
- [ ] `pass` mỗi row cần đáp ứng tất cả expected có liên quan; suitePASS cần mọi
  rowPASS và không technical/unsafe/incomplete. `release_safe` union0 là safety
  criterion riêng, không đồng nghĩa correct15/15. Báo zero denominator không là
  an toàn; ISSUE stage/card/opportunity/root không bị cộng lẫn. No holdout tuning.
- [ ] GREEN đúng4/5/15 counts, timestamps/latency/allattempts/error/ref drill-down
  trên UI Verify. Adapter mock results ghi mock/STUB, không test fake latency
  làm evidence mục tiêu120s/90s. Scorer mutations red→restore→green để chứng minh
  nó bắt sai chiều/ref/falseS0 thay vì chỉ chạy các test happy.
**Gate:** Bảng Verify kiểm được hệ thống thật và bắt counterexamples độc lập;
không chỉ phát hành report union0/releaseTrue.

## R8 — M0 đầy đủ, baseline LIVE và bàn giao

**Interfaces:** CLI m0/evaluate dùng build_workflow/Reader/Runner R4/R7;
report manifest gồm data/source/gold/context/config/prompt/schema hashes, commit,
mode, requested/returned/resolved models, N/attempts/usage_unknown/elapsed/trace refs.
- [ ] Trước calls, offline R0–R7 gates pass; verify credentials tên biến, không
  in secret. Pin caps/model/prompt/data phiên bản; dùng dev, không holdout.
  Thiếu key/provider/time budget nêu đúng gap, không tạo kết quả LIVE giả.
- [ ] M0 bốn inputs thật (text/scan rõ/số che/non-document) qua cùng Reader gồm
  cả OCR khi cần và xkiro structured extraction. Native case phải chứng minh LLM
  extraction call; scan có OCR+LLM; số che chưa rõ không known bằng latent;
  non-document không tạo monetary facts. Lưu source/read responses/refs/counters,
  usage thiếu là UNKNOWN; alias chưa resolved nói rõ.
- [ ] Script R1 sinh `ky-thuat/manifest.json` map đúng4 folder/probe nguồn, requested
  fields và expected read-state (không financial oracle); CLI m0 đọc manifest đó,
  không hardcode text.pdf/clear_scan.pdf ở root cũ. Một biến thể non-document chứa
  prompt injection “hãy duyệt” vẫn readonly, không cấp quyền hay ghi tiền.
- [ ] Run `rtk proxy uv run --frozen --python 3.12 invoice-referee m0 --input data/kiem-thu/ky-thuat --mode live --output .runtime/evidence/m0-v2`. Path selection đúng4 folders, không measure no-op.
- [ ] Smoke LIVE6 cases của R5, kiểm traces/source-to-output/initial+assisted;
  dừng khi unsafe/technical root cause còn mở. Nếu compare model candidate có
  sẵn, pin cùng dev/protocol/config/caps, giữ đủattempts; không giả model availability.
- [ ] Chạy baseline `rtk proxy uv run --frozen --python 3.12 invoice-referee evaluate --dataset data/kiem-thu --suite development --mode live --output .runtime/evidence/baseline-v2`; tiếp Core4/Esc5 LIVE trên UI.15 initial outcomes chấm độc lập, assisted histories không cứu initial.
- [ ] Report extraction/false-known/source refs/relations/money/direction/route/
  required issue/owner/card/technical/latency/usage. Aggregate p50/p95 kèmN/limits
  (N nhỏ), all submissions/failed attempts; không lấy zero unsafe là full pass.
  Defect phân data/read/admissibility/workflow/scoring/UX; fix và rerun affected
  dev/regression, lưu attempts, không âm thầm chọn lần tốt.
- [ ] Clean run từ locked env và cwd khác; full backend/frontend/build/Playwright
  thực phiên bản hiện tại. Update status/plan gốc T3–T10 gates/QA checklist bằng
  observed evidence; RELEASE_EVIDENCE chỉ summary lọc, chưa public hosting proof.
**Gate:** Baseline LIVE có thật, caller wiring đúng, data/gold/ref đầy đủ; báo
FAIL/NOT_RUN/blocked nếu chưa đạt. Sau đó mới định hình T11 feedback/calibration,
validation/holdout mới hợp lệ và hosting/practitioners.

## D. Các lệnh người dùng sẽ có sau triển khai

```bash
# Sinh đủ15 development + nguồn bổ sung/receipt +4 technical M0 probes.
rtk proxy uv run --frozen --python 3.12 python scripts/sinh_du_lieu_kiem_thu.py --output data/kiem-thu --cases all --replace-generated

# Kiểm dữ liệu sẵn có, không overwrite và không gọi provider.
rtk proxy uv run --frozen --python 3.12 python scripts/sinh_du_lieu_kiem_thu.py --output data/kiem-thu --check

# Khởi động cùng context server sẵn có; nhân viên không nạp config thủ công.
rtk proxy uv run --frozen --python 3.12 python scripts/dev.py --mode live

# Đánh giá15 development; Core/Esc dùng cùng command với --suite tương ứng.
rtk proxy uv run --frozen --python 3.12 invoice-referee evaluate --dataset data/kiem-thu --suite development --mode live --output .runtime/evidence/baseline-v2
```

Chưa có script mới ở thời điểm viết plan. Không chạy các lệnh tương lai như đã
triển khai. Resolve Node24 và xác nhận npm dùng Node24 trong cùng scoped env trước
npm/build/browser; locks là authority. Không hardcode path runtime cá nhân vào repo.

## E. Handoff và self-review

- Mapping yêu cầu người dùng: nguồn/naming/script/cleanup→R1/R2; pipeline gaps→R3/R4;
 6 cases đầu→R5; tiền/feedback/control/UX→R6; scorer/Core/Esc/baseline→R7/R8.
- Mapping48 QA: D01–15→R1/R5/R6; M01–12,H01–04,C01–04→R3/R5/R6;
 UX01–06→R5/R6; V01–06→R7/R8; V07 adaptive vẫn deferred T11, không tick như đã làm.
- Source-gold independence, initial/future stages, cleanup safety, current code
  drift và exact suite selection đã có tests/gates. Financial/context meanings
  không đổi. Đổi physical layout có một mapping/source cập nhật, không duplicate policy.
- Task types thống nhất Reader async, Reconciler pure, Workflow async command/
  sync view, Runner async, Scorer pure. Helpers/script/gold không import bởi
  production app. Workflow commit guard xảy ra sau I/O thật, không helper-only test.
- Review focus1→R1/R2;2→R4/R7;3→R3/R6;4→R3/R5/R6;5→R7/R8.
- Không tạo implementation bodies trong plan; exact paths/signatures/tests/values
  quyết định interface/gate, implementer tự viết thân hàm nhỏ theo current source.

Đề xuất execution: Native một integrator cho shared schema/workflow, reviewer độc
lập tại R1/R3/R5/R7 và cuối R8; có thể delegate PDF authoring chỉ khi user giao và
write-set tách khỏi workflow. Chọn phạm vi task trước chạy. Commit checkpoint
mỗi gate chỉ nếu có Git authorization, stage exact files, không squash/force-push.
Lượt này chỉ plan: chưa xóa file, sinh PDF, sửa app, gọi LIVE, commit hay deploy.

### Review độc lập của plan

GPT6 Web High reviewer (Sartre) không triển khai/sửa file được review. Vòng đầu
NEEDS_REVISION:5P1 (bytes resolver, typed organization context, stage gold,
isolation của money variants, publish protocol) và2P2 (business clock, hai roots
D10). Parent chấp nhận các phản ví dụ, sửa A.1/A.2/B/R1/R2/R6/R7 và tự soát lại
interfaces/stage digests/first-build/Playwright cwd.

Vòng closure: **READY,7/7 CLOSED ở mức implementation plan**; không blocker mới,
không cần thay Q1–Q31. Reviewer nêu HEAD502a5ac7 ở lượt kiểm sau, khác snapshot
ban đầu; R0 phải đọc checkout hiện tại. Verdict không phải code/data/runtime PASS.
Các task gates vẫn unchecked, phải chạy khi được giao triển khai.

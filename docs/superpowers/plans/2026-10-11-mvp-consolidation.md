# Hợp nhất MVP — plan nghiệm thu sau review

> **For agentic workers:** Dùng executing-plans; tuần tự R1–R6, một writer shared contracts. Không tự subagent/Git/LIVE/publish. Sửa hành vi và kiểm regression trước khi di chuyển code.

**Goal:** Sửa các lỗi đã xác minh, thống nhất hiệu lực quyết định/trạng thái UI, hoàn thiện ranh giới code và phân biệt current/shared/legacy.
**Architecture:** Giữ một application path, SQLite và transaction hiện có. UI trình bày dữ liệu có căn cứ; lifecycle dùng cùng decision selector và action-basis checks. Tách trách nhiệm và chuyển code lịch sử sau khi regression ổn định.
**Tech Stack:** Python/Pydantic/FastAPI/sqlite3/pytest; React/TypeScript/Vitest; stdlib và dependency hiện có.
**Spec:** Thiết kế sửa lỗi trong plan này, theo [Product](../../settlement/PRODUCT.md), [Rulebook R8–R10](../../settlement/RULEBOOK.md), [System](../../settlement/SYSTEM.md), [Evaluation](../../settlement/EVALUATION.md).
**Status:** **REMEDIATION IMPLEMENTED (R1–R5), R6 checks green**, 12/10/2026.
Không viết lại ứng dụng. GUI/browser chưa thao tác thật (USER_UI_UNEXECUTED).

**Evidence (fake, không LIVE/Git/publish) — sau remediation, source revision hiện tại:**

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q   # 898 passed (exit 0)
.venv/bin/python -m pip check                                       # No broken requirements found
npm --prefix frontend run test -- --run                             # 166 passed (25 files)
npm --prefix frontend run build                                     # tsc --noEmit + vite build OK
```

Focused đỏ→xanh: `test_handoff_blocks_material_source_added_after_approval`,
`test_noop_context_key_is_bound_to_its_payload` (DID NOT RAISE trước patch).
Regression R1.4: same E/T/B nhưng cost source đổi → NEEDS_RECHECK; handoff reuse
khác receipt → handoff mới; no-op key replay/conflict; revalidation VALID cũ hết
hiệu lực sau source change. R2: queue giữ mọi file; report không tự PASS; case
A→B race; linked B7 chỉ dedicated actions. R3: `settlement/persistence/*`,
`shared/clock`, `useCaseWorkspace`. R4: legacy move + shim. R5: README + inventory.
Frozen corpus/gold/DB/originals không đổi.

## Lịch sử triển khai và review

Implementation tại commit c72fe2b5190b189b65ca0dbc27848209269b3223: Store3809→1997 dòng; SQL records đã tách; SourceUploadPanel/ProcessingDetails và recipe demo đã có. Giữ các kết quả worker báo như lịch sử, không coi là acceptance:

| Bằng chứng cũ | Kết quả được worker báo |
| --- | --- |
| Fake pytest toàn repo | 891 passed |
| Frontend tests | 157 passed, 25 files |
| pip check / frontend build | Thành công |
| UI thực tế / LIVE | Chưa kiểm |

Review độc lập GPT6Web High và lead source checks đã tái hiện:
- Fake pipeline/DB tạm: workflow NEEDS_RECHECK/basis_current=False vẫn nhận handoff3M.
- Fake pipeline/DB tạm: no-op context trả replay flag nhưng cùng key/body khác được nhận, version7→8.
- Đoạn logic UI gốc: hai refs chưa có document roles vẫn báo đủ hai chứng từ.
- Đoạn queue UI gốc: hai file cùng tên/size, bytes khác nhau bị giữ còn một.
Các rủi ro draft/race và các đường UI generic trùng chưa được browser reproduce. Không khẳng định lỗi do refactor tạo ra.

| Task cũ | Nghiệm thu sau review |
| --- | --- |
| 1 UI/state/navigation | Mở lại: kết luận tự suy diễn, trạng thái lặp, draft/race/generic forms |
| 2 boundaries/naming | Mở lại: clock import ngược, refresh còn trong Store, current decision nhân đôi |
| 3 demo/docs | Một phần đã có; cần lệnh tái tạo từ clone mới và phân loại lịch sử |
| 4 inventory/final checks | Mở lại: inventory13 mục chưa đầy đủ, UI chưa chạy, còn lỗi đã tái hiện |

Nguyên bản plan/worker evidence còn trong Git tại c72fe2b; không sửa dataset/gold để đổi lịch sử.

## Global constraints

- Không thêm nghiệp vụ, bank transfer/payment request, auth/tenancy, ORM/queue/framework/dependency.
- Giữ API public paths, wire values, schema version và eight-table DB; không đổi Job/operation codes vì đổi folder.
- Approval≠receipt≠closure; unknown/pending không0; gross không clip; sources/rights/Stop/stale/duplicate/closure gates giữ nguyên.
- Correct partial fulfillment giữ approval gốc; material changes cần recheck. Không chặn mọi case chỉ vì report mới khác run ID.
- Decision/action guards và writes trong cùng BEGIN IMMEDIATE; không provider wait, connection hoặc commit lồng nhau.
- UI không suy facts từ filename/ref count, tính lại net hoặc tự cấp quyền. Tài liệu đã upload khác căn cứ đã xác lập.
- Same command key/body replay trước stale version; key/body khác409. Business reuse khác command replay.
- Không xóa/di chuyển DB, uploaded originals, frozen corpus/policy/gold, runtime evidence trong plan này. Di chuyển code không di chuyển dữ liệu.
- Fake tests khác LIVE quality/trials. Browser denial không bypass; chưa thao tác UI ghi USER_UI_UNEXECUTED.
- Chỉ cập nhật plan/README/canonical docs có sẵn; evidence/inventory JSON/CSV ignored. Không thêm một loạt Markdown.
- Trước execution kiểm branch/status/diff; giữ mọi thay đổi người khác. Không auto Git/LIVE/publish.

## R1 — Sửa handoff, revalidation và command idempotency

**Files:** settlement_records.py, linked_context_records.py, settlement_workflow.py, settlement_reconciliation.py, sqlite_records.py, Store/Service callers cần thiết. Tests hiện có test_b7_closure.py, test_b7_money_revalidation.py, test_b7_linked_context.py, test_b7_workflow.py/test_b7_workflow_api.py.

**Interfaces:**
- Pure governing_decision(presentation:B7PresentationView|None,decision:B7DecisionView|None,current_run_id:str|None)->B7DecisionView|None trong settlement_workflow.py; workflow_view/current_decision dùng chung.
- require_handoff_basis(conn,artifact_root:Path,case_id:str,decision:B7DecisionView,b7,b3,policy:dict)->tuple[Report,LinkedB7ContextSnapshot] trong settlement_records.py; transaction caller giữ nguyên.
- grant_for_action(b7,decision:B7DecisionView,effective_at:datetime) dùng current effective_b7_time, một scoped grant đủ E/approved settlement; không tái dùng decision-time check cho new action. Closure chứng minh quyền tại decision/action times vẫn khác new-action authorization.
- revalidate_b7_decision thêm original_cost_signature:str|None. Lưu cost signature server-derived trong B7_DECIDE audit metadata, không client field. Decision cũ phục hồi từ immutable run/context/source snapshot nếu đủ; thiếu không đoán VALID.

- [x] **R1.1 Tests đỏ từ hai probe đã tái hiện**
Trong test_b7_closure.py dùng fixture approved_linked_b7 và command đã import; thêm Upload import:
```python
def test_handoff_blocks_material_source_added_after_approval(approved_linked_b7):
    from invoice_referee.settlement.models import Upload
    svc, child, report, decision = approved_linked_b7
    expense_id = report.expense_rows[0].expense_id
    svc.add_source(child.id, Upload(filename="changed-cost.txt",
        content=f"fact CHANGED expense.{expense_id}.amount 6000000\n".encode()),
        command("changed", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))
    view = svc.get_case(child.id)
    assert view.b7_workflow.basis_current is False
    with pytest.raises(DomainError) as error:
        svc.handoff_b7(child.id, {"decision_id": decision.id, "reason": "Bàn giao"},
            command("handoff-new", "ACC-DEMO-01", "ACCOUNTANT", view.case_version))
    assert error.value.code == "BASIS_STALE"
```
Trong test_b7_linked_context.py import ready_linked_b7 từ test_b7_workflow và dùng fixture chain hiện có:
```python
def test_noop_context_key_is_bound_to_its_payload(ready_linked_b7):
    svc, child, _ = ready_linked_b7
    packet = svc.store.get_linked_b7_context(child.id).company_packet.model_dump(mode="json")
    cmd = command("noop-key", "ACC-DEMO-01", "ACCOUNTANT",
                  svc.get_case(child.id).case_version)
    first = svc.record_b7_company_packet(child.id, packet, cmd)
    changed = dict(packet)
    changed["reading_note"] += " Different request body."
    with pytest.raises(DomainError) as error:
        svc.record_b7_company_packet(child.id, changed, cmd)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert svc.get_case(child.id).input_revision == first.input_revision
```
Run focused tests trước patch, ghi behavioral failures (không collection/import failure):
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_closure.py tests/settlement/test_b7_linked_context.py -q
```

- [x] **R1.2 Implement guards, không đóng đường partial fulfillment**
Handoff chỉ dùng original current basis hợp lệ hoặc current VALID revalidation của cùng decision. Đọc current successful report đúng input_revision/epoch, child+parent controls/dependency, policy/config/rights/source coverage/material issues trong transaction. Không lấy old decision.basis_report làm report hiện hành khi input đã đổi.
Revalidation phải so cost basis/source support/eligibility/payer/relations, không chỉ E/T/B bằng số. Helper hiện nhận current_cost_signature nhưng chưa so original; sửa điểm này. History delta chỉ đúng canonical qualifying receipts; extra advance/refund/contradiction không VALID.
Duyệt3→nhận2→refresh/coverage/rerun/revalidate hợp lệ: handoff còn1, original approval3. Không yêu cầu duyệt lại chỉ vì đúng receipt. Old VALID audit không đủ nếu source/context/receipt/config thay đổi sau nó.
Handoff reuse chỉ khi obligation, business/cost basis, receipt history, parent/config/control/cutoff còn tương đương. Same remaining không sufficient. Chữ ký lấy current validated report/context, không chỉ snapshot tại approval; run ID/usage churn không tự new entitlement.

- [x] **R1.3 Ghi mọi accepted command kể cả no-op/business reuse**
No-op context và handoff reuse vẫn lưu command fingerprint/result trong transaction. Giữ input_revision/source snapshot khi không material; new accepted command tăng case_version theo S6, replay cùng key không tăng lần nữa. Lookup trước version/gates cho retry; historical result không bảo đảm current validity.
Rà các early returns ở prepare linked child, presentation reuse, context, handoff và closure: không bỏ command registry. Không upsert/dedup money theo command key; economic identity riêng.
Governing selector giữ APPROVE sau correct receipt để fulfillment tính phần còn; REFUSE giữ hiệu lực; newer presentation thay non-REFUSE; RETURN sau run mới không còn governing. Selector không thay freshness validator, không recursion với fulfillment.

- [x] **R1.4 Regression matrix và API persistence**
Thêm cases: changed policy/grant/parent/source; current partial revalidation positive; same E/T/B nhưng cost source/payer link đổi; old revalidation badge; handoff reuse cùng amount khác receipt/basis; no-op key replay/conflict; concurrent Stop/handoff và version writers. Assert audit/records/no action khi rejected. Tests same signatures cho harmless rerun.
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_closure.py tests/settlement/test_b7_money_revalidation.py tests/settlement/test_b7_linked_context.py tests/settlement/test_b7_workflow_api.py -q
```

## R2 — Sửa evidence UI, draft/race và luồng generic trùng

**Files:** frontend settlement Report/Actions/B7Intake/B7Approval/SourceUploadPanel/App/uiState/uiCopy và các tests tương ứng. Không sửa net/eligibility backend để khớp UI.

**Interfaces:** Report rows chỉ consume CheckResult/CriticalFact/B3Proposal.field_refs và source ownership đã có. Case workspace async commits thuộc selected case/request generation. Linked actions và legacy actions render mutually exclusive, không đổi endpoint.

- [x] **R2.1 Queue regression đỏ, giữ mọi file được chọn**
Đặt trong SourceUploadPanel.test.tsx dùng makeView và imports hiện có:
```tsx
test('không bỏ file khác bytes chỉ vì trùng tên và size', () => {
  render(<SourceUploadPanel view={makeView()} role="EMPLOYEE" actorId="NV-01"
    onChanged={vi.fn().mockResolvedValue(undefined)} onError={vi.fn()} />);
  const input = screen.getByTestId('sources-file-input');
  const a = new File(['aa'], 'bill.pdf', { type: 'application/pdf' });
  const b = new File(['bb'], 'bill.pdf', { type: 'application/pdf' });
  fireEvent.change(input, { target: { files: [a] } });
  fireEvent.change(input, { target: { files: [b] } });
  expect(screen.getByText(/Đã chọn 2 tệp/)).toBeTruthy();
});
```
Remove name+size filtering trong SourceUploadPanel và B3 import queue ở App; append incoming, người dùng chủ động bỏ. Không thêm content hash infrastructure để giải một queue nhỏ. Backend type/size limits và economic dedup vẫn áp dụng.

- [x] **R2.2 Report không tạo fact/check/căn cứ**
Bỏ source_refs.length>=2, filename/index fallback làm căn cứ một check. Thiếu backend result/supporting refs: “Chưa có kết quả kiểm tra/căn cứ cho mục này”, không xanh/khớp từ default value. General document links để vùng tài liệu, không gọi là proof của rule.
Hai forecast PDFs không là request+forecast; web form đủ dữ liệu không bị đòi hai giấy. Giữ amount_words/estimate/proposal checks từ backend; không bắt document.role gộp toàn dossier thành một scalar.
Render tests: two same-role sources, zero refs, renamed/misleading filename, missing check, contradiction, web-native, unreadable field; known value không tự PASS, không invent locator/bbox. Không thêm UI-only escalation.

- [x] **R2.3 Draft và async state thuộc đúng case**
Key intake theo case.id; server revision/save response được sync khi không dirty hoặc sau accepted save. Dirty draft chưa lưu: cho save/discard/cancel trước đổi case hoặc giữ draft per case; không tự save vào case mới.
loadCase/polling dùng generation token và captured case ID; tải view/run/report/questions/history vào một workspace rồi commit nếu request còn current. A→B, A trả muộn không overwrite B. B loading không render viewB+reportA. Refetch cùng case không mất queue/draft.
Regression với deferred API promises trả đảo thứ tự, case switch giữa polling/upload, B7 A→B với rows/confirmed khác nhau, reload sau save, dirty revision conflict; giữ expected_case_version từ đúng view.

- [x] **R2.4 Một trạng thái chính, đúng một contract thao tác**
Actions phân b3/linked_b7/legacy_b7 rõ: linked chỉ B7Approval/SettlementReceipt, không generic money/decision/handoff/close. Legacy giữ dưới chế độ explicit, không xóa backend.
App headline lấy UiSummary; review history là lịch sử phụ. B7Approval sau APPROVE đọc fulfillment/closure, không luôn nói chưa ghi nhận tiền/chờ chi. BALANCED không giả đã chi0; unknown không received0. Current frontend rights vẫn không financial authority.
```bash
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Checkpoint UI: linked chuẩn bị→upload→confirm→review→approve→partial/full; switch hai case và ba vai; kỹ thuật expandable, source mở đúng, không duplicate forms. Chưa thao tác thật vẫn USER_UI_UNEXECUTED.

## R3 — Hoàn thiện boundaries sau khi lỗi đã xanh

**Files/target map:** Giữ Store/Service/API public locations. Tạo settlement/persistence/{queries.py,decision_records.py,money_records.py,action_records.py}; chuyển sqlite_records/advance_records/linked_context_records cùng vào persistence. Tạo shared/{__init__.py,clock.py}. Frontend thêm useCaseWorkspace.ts và CaseWorkspaceView.tsx; giữ các panel đã có.

**Interfaces:** clock.utcnow()->datetime aware UTC (record time), không thay effective_b3_time/effective_b7_time (business time). Store.refresh_b7_money_context façade gọi money_records.refresh_context(conn,artifact_root,case_id,command,b7,policy,authority_version)->None; Store dựng CaseView trong cùng txn.
useCaseWorkspace(caseId:string|null)->{workspace:CaseWorkspace|null,loading:boolean,error:string|null,reload:()=>Promise<void>}; CaseWorkspace gồm view/run/report/questions/history/b3Context theo types hiện có. CaseWorkspaceView nhận workspace,role,actorId,onAction,onPrepareSettlement,onStartRun,onNavigate theo signatures hiện hành, không 20 callbacks hoặc form framework.

- [x] **R3.1 Tách theo responsibilities có consumers**
queries: đọc records/projection, dùng pure governing selector; decisions: presentation/decision guards/writes; money: records/history/refresh/revalidation; actions: handoff/closure/adjustment. Shared lookups/serialization trong sqlite_records. Mỗi existing function giữ args/return type, thêm conn/artifact_root nếu cần, không lấy Store hoặc callback gọi ngược façade.
Store owns _write/_read; records không connection/commit riêng. Di chuyển refresh logic khỏi Store; không đổi transaction order/idempotency/hashes/persisted kinds vì split.
clock nằm ở shared, records gọi clock.utcnow; chuyển monkeypatch test sang owner đúng. Không lazy import store nữa, không Clock interface/factory.
App giữ persona/case navigation/global actions; hook owns verified request lifecycle, view owns case tabs/layout; forms stays panels. Không tách component từng div.

- [x] **R3.2 Xác minh boundaries và regression**
Static import check: persistence không import Store/API, pure money/workflow không SQL/API, no import cycle; include function-local imports. Alias façade wrappers có consumer giữ, internal migration shims không consumer loại khỏi code mới.
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Báo responsibility/call directions trước-sau; không arbitrary300-line ceiling. models/types/b3 còn lớn không tự fail; tách contracts chỉ khi có seam/import graph riêng đã chứng minh, ngoài scope lượt này.

## R4 — Current/shared/legacy có đường tìm rõ

**Target:** src/invoice_referee/settlement hiện hành; shared chỉ errors/artifacts/clock/loader có consumers thật; legacy chứa claim-processing cũ. Frontend/src/settlement hiện hành, frontend/src/legacy code cũ; main/styles/test setup giữ vị trí chung cần thiết.

- [x] **R4.1 Dependency map trước di chuyển**
AST/import map + text references phân runtime/import-only/test/history/data. domain.models.DomainError có17 current consumers; storage.artifacts.put_artifact cócurrent+legacy consumers. Tách hai phần dùng chung trước, không chuyển cả domain/storage vào legacy.
Mapping trong output/maintenance/consolidation-inventory.json mở rộng existing artifact, không Markdown mới. Private helper/hardcoded ROOT và dynamic imports phải được kiểm trực tiếp; không claim unused từ graph lỗi.

- [x] **R4.2 Move code lịch sử, giữ public entry compatibility**
Đường chuyển code (không chuyển data):
| Hiện tại | Target |
| --- | --- |
| application/, extraction/, policy/ | legacy/application/, legacy/extraction/, legacy/policy/ |
| domain/models.py (model bodies cũ) | legacy/domain/models.py; shared/errors.py giữ error dùng chung |
| storage/repository.py | legacy/storage/repository.py |
| storage/artifacts.py | shared/artifacts.py, consumers cả hai cập nhật |
| config.py / api/app.py implementation | legacy/config.py / legacy/api/app.py |
| verify/jobs,manifest,metrics,replay,runner | legacy/verify/ cùng tên; settlement_cli/settlement_replay giữ current |
| frontend/src old App/api/types và các component cũ | frontend/src/legacy/ cùng tên, shared assets giữ khi còn consumers |
Tạo shared/errors.py chứa cùng DomainError class; shared/artifacts.py cùng file IO helpers; loader env hiện có giữ hoặc move chỉ khi imports ổn định. Legacy domain.models re-export cùng Error identity, không hai exception classes.
Move application/, extraction/, policy/, storage/repository.py, old domain model bodies/config.py/api app implementation và verify runner cũ sang legacy tương ứng sau map. Current settlement không fallback legacy.
Public api.app:create_runtime_app và python -m invoice_referee.verify old contracts giữ thin explicit compatibility entry nếu còn consumer; current verify code riêng khỏi legacy implementation. Không wildcard re-exports/all-symbol shim hoặc parallel writer.
Frontend old App/CaseDetail/CaseForm/HumanActions/Inbox/Verify và old api/types/builders/tests chuyển legacy; shared assets/helpers chỉ khi được cả hai dùng. main vẫn mount settlement. Cập nhật relative imports/test discovery, không accidentally mount legacy.
Không move tests/fixtures hoặc frozen corpora. Có reference chưa giải quyết thì giữ path/mark legacy và báo blocker của item đó, không ghi toàn R4 DONE. Sửa ROOT/path resolution tại caller khi move, kiểm clone/install context, không giả parents[3] vẫn đúng.

- [x] **R4.3 Import/entry smoke + integration**
API current và explicit legacy factory import được; CLI --help không gọi provider; frontend normal entry đúng. Tests/gold bytes/API schema/operation codes giữ, direct Store/API tests không mất do chỉ đổi path. Trường hợp alias public cần giữ liệt kê rõ owner/consumer, không tồn tại hai business implementations.
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake PROVIDER_MODE=fake .venv/bin/python -c "from invoice_referee.api.settlement import create_runtime_app; from invoice_referee.api.app import create_runtime_app as legacy_factory; print('entry imports OK')"
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake PROVIDER_MODE=fake .venv/bin/python -m invoice_referee.verify --help
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake PROVIDER_MODE=fake .venv/bin/python -m invoice_referee.verify.settlement_cli --help
```

## R5 — Docs/demo/inventory thực sự tái tạo được

**Files:** README/AGENTS routing, canonical System/Product/Evaluation, docs/testing/understanding metadata, scripts/build_travel_demo.py nếu cần, existing inventory JSON. Không thêm dataset mới hoặc rewrite frozen snapshots.

- [x] **R5.1 Một đường hiện hành, lịch sử rõ**
README đặt command generator trước link recipe Git-ignored, ghi mode fake và config/setup cụ thể. P01/P02 hiểu code cũ có legacy/snapshot label; lịch sử có commit không coi sai, không dùng làm current architecture. Cập nhật module map và commands theo R3/R4; không append nhiều bản kiến trúc vào System.
Dữ liệu đánh giá tại docs/discovery giữ original path/hash, DEFAULT_CORPUS và manifests không move lúc này; phân loại DATASET để agent không coi là policy toàn app.

- [x] **R5.2 Inventory từ filesystem/references, không chỉ danh sách13 mục**
Đo file sizes/SHA256/ownership/tracked/generator+basepath/references/retention; directory ghi aggregated bytes/file count, hash là manifest-entry digest hoặc explicit N/A, không dùng null che “chưa đo”. Metadata-only cho private records; không in content hồ sơ/key.
KEEP/ARCHIVE/REGENERATE_CANDIDATE/REVIEW_REQUIRED; verify generator path và bản trùngbyte, scan/native khácpurpose. Chứng minh references/regeneration trước removal proposal. Không xóa bất kỳ data/evidence/frozen item trong plan.
Tạo recipe vào temp output với work-ref chỉ định để kiểm file roles/date/hash/expected separation; đừng overwrite bộ demo đang test. Recipe fake không chứng minh OCR/LLM hay professional trials.

## R6 — Nghiệm thu có đối chứng, không đóng bằng checkbox

- [x] **R6.1 Required checks cuối**
```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```
Chạy focused đỏ→xanh trước broad checks; repeat chỉ change/failure. Record command/exit/count/mode và source revision, không dùng891/157 cũ làm evidence mới.
So hashes frozen/input/policy/gold và API contracts, import graph cảlazy imports, no data loss/no new current financial action khi stale/Stop.

- [x] **R6.2 Acceptance matrix bắt buộc**
| Case | Expected |
| --- | --- |
| Material source sau approval | Handoff bị chặn, no new audit handoff |
| Duyệt3, receipt2, current VALID revalidation | Same approval, handoff remaining1 |
| Same E/T/B nhưng cost evidence/relations đổi | NEEDS_RECHECK, không waive vì tổng tiền bằng |
| No-op/business reuse new key rồi body khác |409 conflict; accepted command có registry |
| Hai nguồn cùng loại/refs thiếu | UI không invented đầy đủ/khớp/căn cứ |
| Hai files metadata giống, bytes khác | Cả hai nằm queue |
| CaseA→B, requestA trả muộn | Workspace/draft B, không mix data |
| Linked B7 ở ba vai | Chỉ dedicated actions, state thống nhất |
| Fresh checkout với generator | Demo recipe có, commands/refs resolve, không expected vào inputs |

UI do user/permitted tool thực hiện: lưu steps/screens/actual failures trong evidence JSON, không đòi screenshot tự chứng minh nghiệp vụ. Không browser permission thì không bypass và không tick GUI acceptance; báo implementation verified scope riêng.
Đợt này DONE chỉ khi R1–R5 và regression/gates đạt; GUI còn thiếu giữ nghiệm thu UI chưa hoàn tất. Không claim LIVE/baseline/trial hoặc toàn project hết nợ kỹ thuật.

## Prompt giao coding agent

```text
Đọc AGENTS.md và triển khai phần R1–R6 của
docs/superpowers/plans/2026-10-11-mvp-consolidation.md.
Đây là remediation sau review c72fe2b, không làm lại task cũ hoặc tin checkbox.
Sửa tests stale handoff/no-op conflict và UI evidence/queue/draft/race trước.
Giữ correct partial fulfillment, signature/source/authority/Stop/closure gates;
không chỉ block mọi basis_current=False hoặc waive bằng E/T/B bằng số.
Sau regression xanh mới hoàn thiện records/clock/App boundaries và move legacy
theo dependency map, giữ public contracts/eight tables/transaction.
Không chuyển hoặc xóa DB/originals/frozen corpus/gold/evidence; không LIVE,
Git/publish/subagent tự động, không thêm framework/dependency.
Cập nhật chính plan/README/docs hiện có và inventory JSON; báo actual checks,
các alias/blocker/UI chưa kiểm. Không tuyên bố complete từ line count hay test cũ.
```

# InvoiceReferee Settlement MVP Implementation Plan

> **For agentic workers:** Use the `executing-plans` skill to implement this plan task-by-task, inline in the current chat. Steps use checkbox (`- [ ]`) syntax. Follow existing user authorization; no extra subagent reviews or Git history actions by default.

**Goal:** Triển khai jobsB7/B3 và workflow đã duyệt trên UI, đo đúng facts/links/money/issues/controls, rồi freeze baselineA có actual evidence trước cải tiếnB.

**Architecture:** Một FastAPI/React app, bounded settlement core trong package hiện có, SQLite/files. AI đọc/đề xuất; Python kiểm tra và tổng hợp; người quyết định/thực hiện tiền. UI và evaluator gọi cùng service, không có nhánh theo test IDs/gold.

**Tech Stack:** Python/Pydantic/FastAPI/HTTPX/sqlite3 hiện có; React/TypeScript/Vite hiện có; MistralOCR+xkiro; pypdfium2/Pillow khi reader cần; pytest/Vitest và browserE2E trọng yếu.

**Spec:** [Product](../../settlement/PRODUCT.md), [Rulebook](../../settlement/RULEBOOK.md), [System](../../settlement/SYSTEM.md), [Evaluation](../../settlement/EVALUATION.md). Original R8 code-gap review and prior drafts are historical entries in [the archive](../../archive/README.md).

## Global constraints

- Plan mới thay plan04/10 cho nghiệp vụ settlement được duyệt; không reset/xóa local data/gold/docs cũ. Branchrebuild, initialHEAD7d0296fac3bcdd4bf0879c2202152a7d26f87411; không stage/commit/push/merge nếu chưa được yêu cầu.
- Khoảng5người/ba vai demo; một process,2active runs,5acceptedactive/queued,2provider calls toànapp,1PDFium executor tuần tự. Chọn role không xác thực danh tính/quyền công ty.
- Deadline240s từaccept gồmqueue; OCR60s/xkiro80s cappedremaining;32providercalls/run;2extractionattempts chung budget; output3072extract/2048matching. Errors/budget/unknown giữ đúng nghĩa, không fake score/0/truncatedfullcoverage.
- Resource envelopeR7.5:20MiB/file,20activefiles/80MiB/run,20PDFpages/file/40PDFimagepages/run,24MP/representation,1000CSVrows. Format/byte inspection và boundary tests trước UI release.
- S=E−(A−RA)−(P−RP), cùngscope/as_of, components unknown không0; companydirect khôngE/trừ lại. Currency/portions/ref/actualreceipt cần đủ nguồn, integerVND và boundedDecimal. TotalB theo công việc, không auto2/5mil hoặc caps category cũ.
- A report/questions/handoffrefs, chưa tự tạo payment entityB, khôngbankexecution. Review≠approval≠receipt≠closure; Stop/stale/idempotency nằm transactionboundary; đúngfulfillment không mất quyết định tổng.
- Fake/replay khônglivequality; sources/expected/followup tách; development20 onefamily/singleauthorgold chưa đủholdout. Baselinefreeze/adaptation/3professionalusers/liveURL phải cóevidence riêng.
- Local edits/tests và việc chạy app/UI thuộc scope triển khai; credentials/live-generation/cost/publish/outboundmessages cần authorization tương ứng. Không hỏi lại quyền đã có. Không install chỉ để review; install khi task reader/E2E thực cần và resolve/pin.
- Không agentframework/ORM/servicequeue/genericruleengine; ít modules theo trách nhiệm cần dùng. Không private files/keys/modeloutputs hoặc localruntimeDB trongGit.

## 1. File map và cutover

New core: `src/invoice_referee/settlement/{models,store,rules,reader,pipeline,service,evaluation}.py` cùng `schema.sql`; module nào chưa task dùng thì chưa tạo. Không cần package con cho mỗi stage. Reuse `storage/artifacts.py` và numeric primitives sau checks, không import old decision reducer.

New API factory: `src/invoice_referee/api/settlement.py:create_runtime_app`, cùng `/api`paths spec trên server pilot riêng. Normal UI saucutover nhập `frontend/src/settlement/App.tsx` từ `frontend/src/main.tsx`. Old API factory và UI/tests giữ historicalcontract để so sánh; không mount cảhai APIcontract trên cùngpaths hoặc fallback new→old.

RuntimeDB/files mới ở `data/settlement/`, tests dùngtmp_path. Normal commands khi W01 wired: backend `.venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app --factory --host 127.0.0.1 --port 8000`; frontend `npm --prefix frontend run dev -- --host 127.0.0.1`. Trước thayport/process, xác định app đang chạy; không kill process người dùng. Publicdeployment tách local execution.

Các file chung do lead quản lý: `api/settlement.py`, `frontend/src/settlement/api.ts`, `frontend/src/settlement/types.ts`, `frontend/src/settlement/App.tsx`, `pyproject.toml`, locks và hướng dẫn entrypoint. Tận dụng utilities, layout và components phù hợp; không refactor styles ngoài scope.

## 2. Hợp đồng dùng chung cho sáu task

Định nghĩa tạiW01/W02, callers dùng đúng names. PayloadJSON ở boundaries đượcPydanticvalidate; không dùngdictcótypes khôngrõ làm đường tắt bỏ source/authority guards.

| Tên | Contract |
| --- | --- |
| Submission | employee_ref/work_ref,jobB3/B7,money_as_of,knowledge_cutoff,form declaration; unknown fields giữNone |
| SourceRecord | id,origin/provenance,type/hash/original/representation refs; supersedes/binding metadata |
| CaseView | id,case_version,input_revision,control_epoch,stop_active,stage,current_run_id,sources,allowed_actions+reasons |
| Command | key,actor_id/demo_role,expected_case_version và body đãvalidate; fingerprint tính từ semanticpayload |
| Observation | fact_id,key,raw/read_state,normalized value/null,source/page/row/locator refs và basis/usability |
| Relation | from/to IDs,kind/portion/supportingrefs,status và reason; proposals riêng facts đã đủ |
| RunInput | immutableSubmission/source IDs+hashes/coverage/policy/authority/response refs,inputrevision/config/control epoch |
| Report | completion,components/proposed/calculated/conditional khác approved/actual; expense rows/checks/issues/refs và nextstep |
| Store | Store(db_path:Path,artifact_root:Path); create_case(submission,command),revise(case_id,submission,command),add_source(case_id,upload,command),get_case(id),get_source(id),snapshot(case_id),create_run(input,command),publish(run_id,report),history(case_id) |
| Service | Service(store,reader,policy,config); submit(submission,command),get_case(id),revise(id,submission,command),add_source(id,upload,command),start(id,command),get_run(id),wait(run_id),report(run_id),questions(case_id),respond(question_id,response,command),review/decide/record_money/handoff/close_case(case_id,payload,command),control(case_id,action,command),closed(case_id),handoff_allowed(case_id) |
| Rule engine | evaluate(input:RunInput,observations:list[Observation],relations:list[Relation])->Report; evaluate_B3 và evaluate_B7 giữjobsemantics; calculate_net(MoneyComponents)->int\|None chỉ tính phần số học đã chuẩn hóa |
| Reader | read(source:SourceRecord,keys:list[str],budget:RunBudget)->list[Observation]; match(input,candidates,budget)->list[Relation]; trả observations/proposals, khôngReport/approval |
| Pipeline | process(input:RunInput,reader,budget,checkpoint)->Report; checkpoint kiểmrevision/epoch/Stop và lưustage |
| Evaluator | evaluate_suite(service,manifest,oracle)->SuiteReport; compare_money(expected:dict,actual:dict)->Literal['PASS','FAIL']; inputs khôngexpected, actual từpersistedrun/history; oracle độc lập engine |

Cácmethodwrappersđược dùng bởiAPI/eval/UItests, không tạo factory/pluginregistry. Fake reader chỉ injected/explicitmode và actualreportghi mode; không dựa testcaseID để chọn outcome. Recordtypes mở rộng fields khi đúng task cần theoR7contract, không mở arbitraryfinancialoverride.

## W01 — Hồ sơ, nguồn và UI dùng được ngay

**Create:** settlement/models.py,store.py,schema.sql; api/settlement.py; frontend/src/settlement/{types.ts,api.ts,App.tsx}; tests/settlement/test_intake.py. **Modify:** frontend/src/main.tsx; README/AGENTS sourceauthority/currentcommands. **Consumes:** Submission/Command/specintake. **Produces:** CaseView/SourceRecord/Store, APIcreate/list/get/revise/sources/content/history, UIintake/reload; các bảng khác chỉinit nếudependency thực cần.

- [ ] Định nghĩa strictcontracts vàmeaningfulREDcheck create→uploadoriginal→reload→staleedit khôngoverwrite; commandretry samekey khácpayload409. Sử dụngfilegiảlậpmới, khôngprivatebill.

```python
def test_stale_revision_preserves_the_new_submission(store, submission, command):
    created = store.create_case(submission, command)
    current = store.revise(created.id, submission.model_copy(update={"form": {"purpose": "Công tác A"}}),
                           command.model_copy(update={"key": "edit-1", "expected_case_version": created.case_version}))
    with pytest.raises(DomainError) as error:
        store.revise(created.id, submission, command.model_copy(update={"key": "edit-2", "expected_case_version": created.case_version}))
    assert error.value.code == "STALE_VERSION"
    assert store.get_case(created.id).case_version == current.case_version
```

- [ ] Khởi tạo fixtures trong `test_intake.py` theo nội dung dưới đây. Chạy RED bằng `rtk proxy .venv/bin/python -m pytest tests/settlement/test_intake.py -q`; expected failure là module/contract chưa tồn tại, không cố tình làm assertion yếu đi.

```python
from datetime import datetime, timezone
import pytest
from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Submission, Command
from invoice_referee.settlement.store import Store

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cases.sqlite", tmp_path / "sources")

@pytest.fixture
def submission():
    cutoff = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)
    return Submission(employee_ref="NV-01", work_ref="CT-01", job="B7",
                      money_as_of=cutoff, knowledge_cutoff=cutoff,
                      form={"purpose": "Công tác A"})

@pytest.fixture
def command():
    return Command(key="create-1", actor_id="NV-01", demo_role="EMPLOYEE",
                   expected_case_version=None, body={})
```
- [ ] Implementcreate/revision/source/schema transaction/file ownership, limitchecks/errors theoSYS-01/15. Reuseatomicartifacthelper, giữmỗiassociation thayvì bỏsourceđồngbytes; originals khôngoverwrite theo filename.
- [ ] UIformjobB3/B7,scope/purpose và nguồn; sau lưu hiệnstage/refs/chưareport. Không gọioldauto-requestpath. Sourceunsupported/overlimits báo riêng, khôngbusinessREJECT.
- [ ] GREENfocusedtests, frontendtypecheck/build; chạy2serversfake/offline và thao tácbrowsercreate→upload→reload→openoriginal. Lưuactual/UIevidence tạidata/settlement/evidence, tóm tắt publicsafe trongdocs/evidence/settlement-W01.md.

## W02 — B7 report thuần và kiểm chứng tiền trên UI

**Create:** settlement/rules.py,pipeline.py,service.py; tests/settlement/{builders.py,test_rules.py,test_report_api.py}; frontend/src/settlement/Report.tsx. **Modify:** models/store/API/settlementApp types theointerfaces. **Consumes:** W01snapshots và observations/relations injected córefs. **Produces:** evaluate/process/Report, run/report routes, persistedstep/actuals và basic evaluatorhook.

- [ ] Builders dựngfacts/relations/coverage từnguồngiảlậpđộc lập, không gọiengine để tạoexpected. REDpositive/negative/zero/unknown vàcompanydirect/duplicate/partialportion.

```python
@pytest.mark.parametrize("e,a,ra,p,rp,expected", [
    (5_000_000,2_000_000,0,0,0,3_000_000),
    (3_300_000,4_000_000,0,0,0,-700_000),
    (5_000_000,2_000_000,0,3_000_000,0,0),
    (5_000_000,None,0,0,0,None),
])
def test_settlement_amount_and_unknown(e,a,ra,p,rp,expected):
    components = MoneyComponents(e=e, a=a, ra=ra, p=p, rp=rp)
    assert calculate_net(components) == expected
```

`MoneyComponents` là record Pydantic với năm trường e/a/ra/p/rp bắt buộc, mỗi trường StrictInt hoặc None. `calculate_net` trả None khi thiếu thành phần; khi đủ, trả đúng e−(a−ra)−(p−rp). Hàm này không chứng minh nguồn hoặc cấp quyền: tests report/API riêng phải kiểm tra facts, links, policy, quyền và approved amount vẫn None trước quyết định.

- [ ] Implementeligibility/payerparts/historyscope/budgetauthority checks; moneyincident/chưaB/vượtB/rightsissues giữcalculated/conditional riêng, unknown không0. S chỉ từđủfacts, noAUTOpaymententity.
- [ ] Persistreport vàrunstatus/jobcompletion; UIbảngcomponents/expense rows/ref/issue owner, nhãnFAKE_OR_REPLAY củainjectedreader. Bấmnguồnkiểmtrađượctừngsố; GETreport không tựreread/provider.
- [ ] Tests`test_rules.py test_report_api.py`, oldnumericregressions liênquan, frontendReportcomponenttest/build. UIđiQ01/Q03/Q04vàunknown quaAPIcùngservice; Q04khôngrequest/approval0. SYS-02..06/17 nối vàoexpectedactualchấm theo nghĩa.

## W03 — Mistral/xkiro reader và pipeline có budget

**Create:** settlement/reader.py; tests/settlement/{test_readers.py,test_pipeline.py}; extraction/prompts/settlement-{extract,match}.txt. **Modify:** models/pipeline/service/composition,pyproject/locks/.env.example nếudependencies/configthựcđổi; UIrunprogress/sourceobservations. **Consumes:** SourceRecord/RunBudget/RunInput. **Produces:** Readerread/match cóidentities/usage/ref/null, processsamecore vàrunrecords.

- [ ] REDmocktransportbody/responseMistralpage0→UIpage1 mapping, xkirofullmodelID/none/JSONcontract, unknown/invalid/truncated, statswithmissingusage không0. Testproviderkeys chỉmock; khôngprintenv.

```python
def test_budget_exhaustion_is_not_an_unreadable_source():
    budget = RunBudget(deadline=time.monotonic() + 30, max_calls=1)
    budget.reserve_call()
    with pytest.raises(DomainError) as error:
        budget.reserve_call()
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert budget.calls == 1
```

W03 định nghĩa `RunBudget(deadline:float,max_calls:int)`, `calls:int`, `reserve_call()->None`; reserve kiểm deadline và call cap trước gửi request. Test transport dùng `httpx.MockTransport`: callback raise `httpx.ReadTimeout` để kiểm technical outcome, callback trả JSON thiếu/truncated để kiểm validator. Không gọi network thật từ unit/integration tests.

- [ ] ParseCSV/form/nativePDFdirect khi đủ; MistralOCR→shortextract; dependenciespypdfium2/Pillowchỉ thêm/resolvepin khi thựcneeded. PDFoperations tuần tự, giữoriginals/transform; nofabricatedbbox/confidence.
- [ ] Per-runreader/calltrace; budget2attempts/chungrepair/cappeddeadline32calls vàglobal2calls, admitted5/active2. Candidatecontextscope/coverage, nofixedtop-k→absence. Fakeoffline modekhôngsilentfallback từLIVE.
- [ ] UIprogresscóstage/outputsource, unknownfield vàtechnicalerror riêng. Rerunảnhđổi chỉaffectedreader/checks; oldresultreuseghi originrun/config.
- [ ] Mock/replayintegrationGREEN, no-regressionUI/build. Chuẩn bịM0probe cụthểđểreview:1syntheticsourceOCR/extract+1unknown/1visioncontrol, giới hạncalls/budget vàreportmode. Chỉ gọllivekhiđượcauthorizationtươngứng; chưađượcphép khôngclaimquality/livepass.

## W04 — B3, câu hỏi và re-check có căn cứ

**Create:** tests/settlement/{test_advance.py,test_questions.py}; frontend/src/settlement/Questions.tsx. **Modify:** rules/service/store/models/APIandnativeform/reportUI. **Consumes:** W01–03, scope/quyền/coverage vàresponse refs. **Produces:** evaluate_B3, question/response/reviewrecords vớirun/revisionlinked; b3native/importUI.

- [ ] REDA01newproposal khôngđòiafterworkinvoice/approval đangxin; A02reuseexternalB; A03estimateconflict; A04historyunknown; A05wrongscope. Amountrequested≠actualadvance.

```python
def test_answer_without_source_does_not_resolve_receipt_question(service, receipt_unknown_case, employee_response):
    question = service.questions(receipt_unknown_case.id)[0]
    service.respond(question.id, employee_response, response_command(receipt_unknown_case))
    service.start(receipt_unknown_case.id, next_run_command(service.get_case(receipt_unknown_case.id)))
    report = wait_report(service, receipt_unknown_case.id)
    assert report.proposed_net_vnd is None
    assert any(issue.id == question.issue_id and issue.unresolved for issue in report.issues)
```

Fixtures W04 trong `test_questions.py`: `receipt_unknown_case` có hotel/chi hợp lệ5triệu nhưng actual advance còn unknown, question cần nguồn actualreceipt phía kế toán; `employee_response` là lời khai "đã nhận2triệu", refs rỗng, actorNV-01/EMPLOYEE. `response_command(case)` và `next_run_command(case)` trả Command với key mới và expected_case_version hiện tại; `wait_report(service,id)` lấy current_run_id, wait rồi report. `Service.questions` trả question có id/issue_id. Reader giả lập trả observations có nguồn đã định cho case, không đọc expected. Assertions nhằm chứng minh reply sai owner/thiếu căn cứ không tự làm advance=2.

- [ ] Defineresponse/next_run/waitfixturesinmodule theoCommandhelpers; wrongowner/source/unreadabletyping nằmC06. Khôngautoresolve question từlời"đãchuyển"; sauvalidsource re-check phầnảnhhưởng, giữinitialrunassistedhistory.
- [ ] UIcâu hỏi nêuowner/ref/đãbiết/cầnnguồn hoặcdecision, upload/answer vàreportrevision. Nhiềuissues trảcùnglần; correctedclaim khôngđổi source gốc hoặccoveragecompany.
- [ ] GREENB3/questionsintegration/componenttests, browserA01/A02 vàQ11sourcebổsung/saianswer; SYS-07/08. Reportreviewkhôngapproval.

## W05 — Decision, tiền thực tế, Stop và đóng hồ sơ

**Create:** tests/settlement/{test_decisions.py,test_money.py,test_controls.py,test_closure.py}; frontend/src/settlement/Actions.tsx. **Modify:** models/store/service/APIandUIreport/history. **Consumes:** currentreport/rights/basis/events+Command. **Produces:** review/decide/money/handoff/control/closure endpoints, persistedepoch/idempotency/incidents andallowedactions.

- [ ] REDauthority/combinedexception/approval khácreceipt; immutableapprovedbasisvsfulfillment; gross4overapproval3 vàwrongrecipientgiữincident; refusedcasecònứng chưaclosed. Mutationstaleversion409, expected payloadchanged samekey409.

```python
def test_stop_ack_then_late_report_cannot_be_current(service, barrier_reader, running_case):
    run = service.start(running_case.id, start_command(running_case))
    barrier_reader.wait_entered()
    service.control(running_case.id, "STOP", stop_command(service.get_case(running_case.id)))
    barrier_reader.release()
    ended = service.wait(run.id)
    assert ended.status == "STOPPED"
    assert service.handoff_allowed(running_case.id) is False
    assert service.closed(running_case.id) is False
```

Fixtures W05 trong `test_controls.py`: `barrier_reader.read` đặt threading.Event entered, chờ Event release với timeout10s, rồi trả observations; teardown luôn release trước close. `running_case` được tạo/upload bằng W01 API/service với source giả lập. `start_command(case)` và `stop_command(case)` tạo Command mới đúng version/actor; `wait_entered()` chờ event, không sleeps. Query `closed` và `handoff_allowed` đọc cùng store/gates, không quyết định lại ở test. Service/provider/config có scope riêng mỗi fixture để không lẫn identities.

- [ ] Typeddecisionbasis/noamountoverride, transactionreadgates+writerecord/audit; samecommandretryidempotenttrướccheckoldversion. Actualeventnamespaces/linksdedup khácHTTPkey; foreignkey/uniquesfail khônglọcâmthầm.
- [ ] Case-version/input-revision/control-epoch riêng; resume tạoepoch/newrun nhưngkhôngautoqueue/cost. Deadline/restart Interrupted/currentguard, revisionmaterialinvalidatesaffectedbasis; đúngreceipt2/approved3/remaining1khôngapprovalmới/pendingchiđúp.
- [ ] ClosuregatesS0+scope+decisions+receipts+noStop/pending/incident; rejectrequestend khácsettlementclosed; actualeventsnhậpkhiStop chỉsource/history khôngfinancialnewaction. HandoffAonlyreport/decisionrefs/audit, noentityB.
- [ ] UInguồn/basis/approved/actual/remaining/incident/Stop/resume/refusal/closure. Integrationbarriers/twoDBconnectionraces+C01..07, browser5phiên/2writes cùngcase+Stopmidcall. Khôngsuyfakeconcurrency làproviderloadquality.

## W06 — Evaluator, baseline và quality comparison

**Create:** settlement/evaluation.py; verify/settlement_cli.py; tests/settlement/{test_evaluation.py,test_manifest_separation.py}; frontend/src/settlement/Verify.tsx. **Modify:** README,AGENTS,runbook,evidence/buildlogs; normalentrypointcuts; docs/specs canonicalnavigation sangcurrentacceptedcontracts. **Consumes:** SettlementService, manifest/oracle,inputsourcepolicyversions. **Produces:** SuiteReport expected/actual/verdict/timestamp/mode/source+confighash, sequentialUIVerify vàbaselineartifact.

- [ ] REDgoldneverinput; expectednull phảiassertactualnull; links/extraissues/state/forbiddenactionschấmngoàinet; technicalfailkhôngbỏmẫu số. Oracle xâyđộc lập từsource/policy, khônggọlevaluate đểlàmexpected.

```python
def test_expected_unknown_is_not_skipped_by_evaluator():
    verdict = compare_money({"proposed_net_vnd": None}, {"proposed_net_vnd": 3_000_000})
    assert verdict == "FAIL"
```

- [ ] R5expectedadapterfixed semantics theo packetstructure, khôngfirstnonnull/trusteddeclaredpayer. Input/followup/expectedtách; clonesonefamilydevelopmentkhôngholdout. Nguồn cóauthorhints tạo datasetversionmới gỡ khỏiprompt, giữsource/expectedlegacy.
- [ ] RunnersequentialquaService, khôngrouteoldVerify15claim lànew20accepted. UIVerifyactualchecks/failures/controltraces; newnormalentrypoints/commandsvàdocsđúngcapabilities. Oldapp/gold rõlegacyreference khôngactivefallback.
- [ ] M0→M1fixedOCRSmall/Medium→M2route→calibration→freshholdout theoR7.4. Baselinecóthểđo yếu nhưngreporttruth; `FAILED`,unknownbadrefs, wronglinks hoặcwrongstatekhôngPASSvìnetđúng.
- [ ] Requiredreleasechecksnewsettlementtests+reusednumeric/storageandfrontendtests/build+UIE2E; locks/pipcheck khi dependency đổi; noextrarepeatedchecks nếukhôngcóchange/failure.
- [ ] FreezeB1source/config/dataset/gold/actual/logs/mode; B2thresholdversiononlyqualitysignals, keepbusinesshardgates. ActionBchỉsauproofguards; professional3users/liveURL/VerifyCore4+Escalation5/submission theooriginalbrief làgatesriêng, chưađượcagent/syntheticthay.

## 3. Tiêu chí hoàn tất và tiến độ

| Acceptance của spec | Task chịu trách nhiệm |
| --- | --- |
| SYS-01 | W01 |
| SYS-02 | W02, W03 |
| SYS-03 | W02 |
| SYS-04 | W02, W03, W04 |
| SYS-05 | W02, W03 |
| SYS-06 | W02, W05 |
| SYS-07 | W04 |
| SYS-08 | W04 |
| SYS-09 | W05 |
| SYS-10 | W05 |
| SYS-11 | W05 |
| SYS-12 | W01, W05 |
| SYS-13 | W01, W05 |
| SYS-14 | W05 |
| SYS-15 | W01, W03, W05 |
| SYS-16 | W02, W06 |
| SYS-17 | W02, W05, W06 |

MỗiWtask cần nguồncodeactualtests+UIevidence vàSYSrefs; chỉcheckdonekhi tất cảacceptance trongtask đượcchứng minh ởmodecôngbố. Workerskhôngtựgán"implemented"choclass/modulechưa compositionwired. Live/trial/deploymentgates chưađượcchạyphảighi rõremaining thayvìPASS.

| Task | Status lúc viết plan | Deliverable next |
| --- | --- | --- |
| W01 |PLANNED |Nativeform/source/reloadUI vàstoreguard |
| W02 |PLANNED |B7report cósource/unknown/negative/zero |
| W03 |PLANNED |Reader/transport/budgets vàprobeplan |
| W04 |PLANNED |B3/questions/assistedrecheck |
| W05 |PLANNED |Quyếtđịnh/actualmoney/Stop/closure |
| W06 |PLANNED |Evaluator/cutover/measurement/baseline |

Source-map/contract/constraints cung cấp đểworkerđọcđược taskđộc lập; snippets là REDassertions vàinterfaces, khôngimplementationhardcodeexpected. Cáchelpers trongtests đượcđịnhnghĩatạitaskconsumers, service convenienceget_case/questions/wait/closed/handoff_allowed chỉquery/projection củarecords/gates, không evaluator thứhai.

Khônggán ngàyhoànthànhhoặctỷlệqualitykhi chưađo. Hạn cuộc thi vẫn15/10khóa và17/10demo theobrief; ưu tiên luồng dùngđược vàqualityevidence, khôngđểUI/trial đếncuối. Không yêu cầu thêm approval cho local reversiblework đã được giao; userreview kế hoạch theo từngluồng, các giới hạn authorization bênngoài vẫn giữ.

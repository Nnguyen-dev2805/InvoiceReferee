# InvoiceReferee Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo lõi dữ liệu, proof/quality, policy, storage và provider boundaries có thể kiểm thử độc lập.

**Architecture:** Pydantic contracts; Decimal và evaluators thuần; SQLite giữ trạng thái có version; adapters trả facts/proposals, không action cuối. Public interfaces nằm trong master ledger; đây là package T01–T05.

**Tech Stack:** Python >=3.12,<3.15, Pydantic 2, pytest, sqlite3/Decimal; Mistral OCR/Kimi SDK adapters ở T05.

**Spec:** [Master/contracts/global constraints](2026-10-04-invoice-referee.md), [Product](../../specs/B1_PRODUCT_SPEC.md), [Rulebook](../../specs/B1_RULEBOOK.md), [System](../../specs/B1_SYSTEM_SPEC.md), [Evaluation](../../specs/B1_EVALUATION_SPEC.md).

## Global Constraints

Áp dụng toàn bộ Global Constraints và contract ledger trong master. Tiền không float; context precision 50 với bounds đã công bố; output model không tự trở thành usable; B0 là tham khảo. Chỉ fake adapters trong unit/integration mặc định. Không auto-commit hoặc live-provider call. Python SDK versions/model/endpoints được khóa sau official-doc verification tại execution, không đoán từ tên file B0.

---

## T01 — Domain contracts, demo policy và test builders

**Dependencies:** không có. **Files create:** `pyproject.toml`, `requirements.lock`, `.env.example`, `src/invoice_referee/__init__.py`, `src/invoice_referee/domain/{__init__,models}.py`, `src/invoice_referee/config.py`, `config/demo-policy.json`, `tests/{__init__,builders}.py`, `tests/unit/test_contracts.py`, `AGENTS.md`, `README.md`, `docs/BUILD_LOG_V2.md`. **Modify:** `.gitignore`. Mọi file mới có scope rõ; không phục hồi source B0 hay `docs/BUILD_LOG.md`.

**Interfaces:** Consumes master §3. Produces tất cả records/errors/builders trong ledger; `load_policy`, `activate_demo_policy`, `snapshot_hash`. `DomainError.code` giữ machine code; message là business-friendly text. Pydantic JSON schema là contract nguồn cho provider và API.

- [ ] **1. Xác minh runtime và tạo env cho deliverable contracts.** Kiểm Python có sẵn, chọn >=3.12,<3.15; dùng Python3.14 hiện có nếu dependencies hỗ trợ; không bắt người dùng cài Python khác khi chưa có lỗi compatibility. Viết `pyproject.toml` với setuptools src layout và nhóm test; dependency bounds Pydantic>=2,<3, FastAPI>=0.115,<1, uvicorn>=0.30,<1, python-multipart>=0.0.20,<1, pytest>=8,<10, httpx>=0.27,<1. Đây là compatibility ranges; khóa exact installed versions trong `requirements.lock` sau resolve. Nếu official SDK requires narrower Python, ghi lý do/chọn runtime trước T05. Không để lock rỗng hoặc giả có package đã cài.

```bash
rtk proxy python3 --version
rtk proxy python3 -m venv .venv
rtk proxy .venv/bin/python -m pip install -e '.[test]'
rtk proxy .venv/bin/python -m pip freeze --exclude-editable > requirements.lock
rtk proxy .venv/bin/python -m pip check
```

`.env.example`: DATA_ROOT=data, PROVIDER_MODE=fake, MISTRAL_API_KEY/KIMI_API_KEY rỗng; SDK/model values được T05 thêm sau kiểm docs. Ignore `.env`, `.venv/`, `data/`, frontend node_modules/dist; fixtures synthetic tracked. Không lưu credentials vào lock/evidence.

README ban đầu chỉ startup/contracts PLANNED/IMPLEMENTED theo actual files. AGENTS cập nhật mission của rebuild thay vì mô tả source Sprint 1 đã xóa; giữ graph-first, skills, RTK, Git discipline và source/evidence labels. Không viết future runtime như operational. T06/T08 sẽ thêm PRODUCT/ARCHITECTURE/TESTING khi đường chạy tồn tại.

- [ ] **2. Viết test strict amount/config trước domain module.**

```python
import pytest
from pydantic import ValidationError
from invoice_referee.domain.models import Claim
from invoice_referee.config import activate_demo_policy
from tests.builders import routine_snapshot, demo_policy

@pytest.mark.parametrize('amount', [True, 1.5, -1, 0, '1200000'])
def test_provided_amount_is_strict_positive_integer(amount):
    data = routine_snapshot().claim.model_dump()
    data['requested_amount_vnd'] = amount
    with pytest.raises(ValidationError):
        Claim.model_validate(data)

def test_missing_amount_is_not_invalid_format():
    data = routine_snapshot().claim.model_dump()
    data['requested_amount_vnd'] = None
    assert Claim.model_validate(data).requested_amount_vnd is None

def test_activation_records_demo_scope():
    policy = activate_demo_policy(demo_policy(active=False), 'Dùng rulebook mô phỏng cho demo')
    assert policy.active and policy.activation_id
    assert policy.origin == 'developer_activated_demo'
```

Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_contracts.py -q`; expected RED import error trước module; sau tạo module failures phải đúng validation/activation, không lỗi env.

- [ ] **3. Tạo models theo ledger và strict base; implement bounds, identities, activation.**

```python
from pydantic import BaseModel, ConfigDict, Field, StrictInt

class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

# Dùng trong Claim; tất cả fields khác lấy từ ledger, không nhận implicit extras.
# requested_amount_vnd: StrictInt | None = Field(default=None, gt=0, le=999_999_999_999_999)
```

Tạo toàn bộ ledger records, không chỉ Claim. Canonical hash JSON sorted keys, UTF-8, SHA256; hash input gồm evidence hashes/roles, claim/version, policy+threshold, active action IDs/confirmations; bỏ `input_hash` chính nó. Không hash mutable path hoặc timestamp mới khiến cùng snapshot luôn đổi hash. Activation cần reason không rỗng, UUID activation ID, origin developer_activated_demo; config bắt đầu inactive/proposed. API T09 sẽ persist activation event, không có implicit fixture activation trong runtime.

```python
import hashlib, json

def snapshot_hash(snapshot):
    payload = snapshot.model_dump(mode='json', exclude={'input_hash'})
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
```

Builders dùng các values cụ thể trong master §3.3; tạo SourceRef/locator/word coverage đúng. Không gọi evaluator để xác định expected. Bổ sung tests duplicate/extra fields; profile/enum invalid; policy thiếu currency/version; amount 15-digit upper bound; stable hash khi cùng input và hash đổi khi amount/policy/action thay đổi.

- [ ] **4. GREEN và gate contracts.** Chạy command test ở bước 2 và pip check, expected PASS/no broken requirements. Ghi `docs/evidence/task-T01.md` với runtime+lock hash, test result và config inactive/fixture active khác nhau. Update `docs/BUILD_LOG_V2.md` chỉ kể việc đã làm. Lead review schema/field names trước giao T02/T04; không commit.

## T02 — Numeric parsing, source resolution và derived quality

**Dependencies:** T01. **Files create:** `src/invoice_referee/policy/{__init__,numeric,quality}.py`, `tests/unit/test_numeric_quality.py`. **Interfaces:** Consumes FieldFact/SourceRegistry/HumanAction, builders; produces `parse_candidates`, `normalize_quantity`, `derive_fact` đúng master signatures. Không nhận model confidence làm business probability.

- [ ] **1. Viết RED cho ambiguity và coverage.**

```python
from decimal import Decimal, localcontext
from invoice_referee.policy.numeric import parse_candidates, normalize_quantity
from invoice_referee.policy.quality import derive_fact
from tests.builders import document_facts, text_registry

def test_ambiguous_quantity_keeps_both_candidates():
    assert set(parse_candidates('1.234', 'QUANTITY', None)) == {Decimal('1.234'), Decimal('1234')}

def test_normalization_does_not_inherit_precision():
    with localcontext() as ctx:
        ctx.prec = 2
        assert normalize_quantity(Decimal('123456.789'), 'kg') == (Decimal('123456789'), 'g')

def test_missing_numeric_scores_cannot_auto_pass():
    fact = document_facts(score=None).fields['total']
    derived = derive_fact(fact, text_registry(score=None), True, Decimal('0.85'), None)
    assert derived.usability == 'UNCERTAIN'
```

Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_numeric_quality.py -q`; expected RED missing module/function.

- [ ] **2. Implement parser candidates bằng grammar explicit và bounded Decimal.** Match canonical, VI, US grammars bằng fullmatch; parse các grammar compatible với locale/currency/basis đã xác định. Khi locale None giữ union; dedup bằng Decimal, sort deterministic. Spaces/currency stripping chỉ theo known tokens; không xóa tùy ý mọi punctuation. Canonical normalized values không reparse ambiguity như raw. Reject exponent, NaN/Inf, bounds overflow, nonpositive quantity trong supported purchase; credit/signed document được chuyển SCOPE-02 trước normal arithmetic.

```python
from decimal import Context, Decimal, localcontext

DECIMAL_CONTEXT = Context(prec=50)
UNIT_FACTORS = {'g': ('g', '1'), 'kg': ('g', '1000'), 'tấn': ('g', '1000000')}

def normalize_quantity(value: Decimal, unit: str) -> tuple[Decimal, str]:
    normalized = unit.strip().lower()
    base, factor = UNIT_FACTORS.get(normalized, (normalized, '1'))
    with localcontext(DECIMAL_CONTEXT):
        return value * Decimal(factor), base
```

Opaque equal units so được; khác opaque units không có ratio. Parser max200 items được models/validator enforce trước loops. Money document currency riêng; claim/request VND integer gate riêng. Test raw `1.234,56` locale VI =1234.56; `1,234.56` US; unknown raw `1.234` có hai candidates; parsed value không bao giờ chọn theo desired action.

- [ ] **3. Implement field proof/coverage, giữ raw và observation contradiction.** Resolve evidence/page/block/locator trong actual registry, raw value nằm ở source locus có normalization trace; ref evidence khác/bad block/word IDs => INVALID_ANALYSIS. Các required numeric locators phải có relevant words và scores cho tất cả words được dùng, min(score)>=threshold; missing/low→UNCERTAIN. Empty source→MISSING/UNUSABLE theo input; không fake0 hoặc100%.

```python
from decimal import Decimal

def numeric_coverage_passes(words, threshold: Decimal) -> bool:
    return bool(words) and all(
        word.score is not None and Decimal(word.score) >= threshold
        for word in words
    )
```

`derive_fact` chỉ USABLE nếu source/raw/normalization valid và requirements quality đạt, hoặc valid reviewer CONFIRM_FIELD đúng field/ref/value. Required observation UNREADABLE/UNKNOWN + requires_verification=False => INVALID_ANALYSIS; READABLE=True không waive missing score. Confirmation không phải source employee, không overwrite OCR. Unknown optional field giữ UNKNOWN/UNCERTAIN nhưng không buộc các check unrelated phải dừng. Region/word chưa mapped được ghi, không suy empty list là quality PASS.

- [ ] **4. GREEN với regressions quality.** Thêm badref, duplicate word IDs, score outside0..1, missing/unassigned word, threshold exact0.85, ambiguous normalization, confirmedvalue có nguồn so với correction vô nguồn. Chạy test command bước1; expected PASS. Gate SYS-02: required fact unresolved không có auto usable; lưu evidence T02.

## T03 — Policy, inventory/arithmetic, authority và decision reducer

**Dependencies:** T02. **Files create:** `src/invoice_referee/policy/{expenses,inventory,decision}.py`, `tests/unit/test_expense_decisions.py`, `tests/unit/test_inventory_arithmetic.py`. **Interfaces:** Consumes snapshot/bundle/quality helpers; produces `evaluate`, `document_checks`, `inventory_checks`. `evaluate` không provider/SQLite/UI, không testcase IDs.

- [ ] **1. Viết RED cho boundaries và inventory N/A.**

```python
import pytest
from invoice_referee.policy.decision import evaluate
from tests.builders import routine_snapshot, resolved_bundle

@pytest.mark.parametrize('amount, action', [
    (2_000_000, 'CREATE_PAYMENT_REQUEST'),
    (2_000_001, 'ESCALATE'), (5_000_000, 'ESCALATE'),
])
def test_authority_boundaries(amount, action):
    decision = evaluate(routine_snapshot(amount), resolved_bundle(str(amount)))
    assert decision.action == action
    if amount <= 2_000_000:
        assert decision.accepted_amount_vnd == amount
        assert decision.completion_basis == 'ROUTINE_AUTO'
    else:
        assert any(i.issue_class == 'BEYOND_AUTHORITY' for i in decision.issues)
        assert not any(i.issue_class == 'OUTSIDE_POLICY' for i in decision.issues)

def test_no_supporting_does_not_waive_amount_conflict():
    decision = evaluate(routine_snapshot(1_480_000), resolved_bundle('1280000'))
    assert decision.action == 'REQUEST_INFO'
    issue = next(i for i in decision.issues if 'AMT-01' in i.blockers)
    assert issue.owner_mode == 'EMPLOYEE'
    assert '200.000' in issue.question
```

Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_expense_decisions.py tests/unit/test_inventory_arithmetic.py -q`; expected RED import until modules exist.

- [ ] **2. Implement exact required-check matrix và amount policy.** `expenses.py`: SRC01/02/03, CTX01, MODE01/02, SCOPE01/02, ELIG01, AMT01/02, LIM01, AUTH01. `inventory.py`: INV01/02 chỉ WORK_PURCHASE; formal receipt/received-full/mapping/source fields mandatory. Merchant/date/currency/total mọi primary; CLIENT_MEAL attendees; TRAVEL trip/context; missing amount factual không invalid format. Known COMPANY/ADVANCE/VENDOR hoặc PERSONAL purpose→REJECT trước providers khi đủ căn cứ. OTHER→outside policy; foreign/credit→scope, không coerce dấu/currency. Total-only verified không miễn amount/purpose/authority. No min/max/clipping; ungrounded allocation→question, không partial pay.

Rule results giữ dependencies/refs/reason/status. Issue stable_key dùng rule+field/source pair, không raw wording; question tạo từ actual values/units/căn cứ, không nhắc tên test. Factual owner employee cho declarations/upload; reviewer cho đọc/đối chiếu nguồn; authority approver <=5m, policyowner >5m. Policy exception alone không đủ approval; authorization bound amount/version/profile/purpose/policy.

- [ ] **3. Implement arithmetic và units independent consistency.** SIMPLE_ITEMIZED line amount = quantity×price rounded HALF_UP per line; sum lines vs total; adjustments chỉ khi đủ known terms/basis, không default0. TOTAL_ONLY chỉ N/A khi không covered/uncovered item region cho thấy cần arithmetic. Unknown template→UNKNOWN, không PASS. Match items strict unique coverage một-một; duplicate IDs reject trước dict construction; candidate mapping không miễn extra/unmatched line. Unit-price normalized bằng price/factor (VND/g), tolerance0; quantities quy baseunit trước so; line/total tolerance1 cùng meaning. Supplier/date chỉ so khi required/usable theo profile; dategap7 inclusive.

```python
from decimal import Decimal, localcontext, ROUND_HALF_UP
from invoice_referee.policy.numeric import DECIMAL_CONTEXT

def expected_line_amount(quantity: Decimal, price: Decimal) -> Decimal:
    with localcontext(DECIMAL_CONTEXT):
        return (quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
```

Test equivalents kg/g routine; khác price 1000/kg vs1.5/g vẫn conflict; bothsources 2×100=1 bị arithmetic chặn; duplicate IDs invalid; unsupported conversions unknown; reordered items/bad pair/extra item chưa cover không pass. Mapping semantic vẫn kiểm source và full coverage bằng code.

- [ ] **4. Reducer ưu tiên đúng và kiểm full coverage.** Technical/config invalid→NONE; known refusal→REJECT; unresolved factual→REQUEST_INFO, vẫn giữ outside/authority issues; chỉ outside/authority→ESCALATE; đủ tất cả applicable checks+authorizations→CREATE_PAYMENT_REQUEST. Check N/A không tương đương whole-case eligible; missing check trong matrix tạo technical INVALID_ANALYSIS, không all(empty)=True. Human authorized basis chỉ khi active valid approval/exception cần cho case, không gọi mọi human correction là monetary approval.

```python
def next_action(*, technical: bool, refusal: bool, issues) -> str:
    if technical:
        return 'NONE'
    if refusal:
        return 'REJECT'
    if any(i.status == 'OPEN' and i.issue_class == 'FACTUAL_UNKNOWN' for i in issues):
        return 'REQUEST_INFO'
    if any(i.status == 'OPEN' for i in issues):
        return 'ESCALATE'
    return 'CREATE_PAYMENT_REQUEST'
```

Anchor áp dụng **sau** full coverage/eligibility validation; không gọi hàm này bằng issues rỗng khi dependencies chưa kiểm. Field/action confirmed không đóng issue cho check khác. Exception/approval đúngscope không waive quality/arithmetic.

- [ ] **5. GREEN và gate nghiệp vụ.** Tests steps1+3 đều PASS; thêm >5m hai issues, exceptiononly vẫn beyond, approvedamount exact, knownpurposePERSONAL REJECT, disabledpolicy NONE/config. Reviewer đối chiếu từng rule ID + SYS-03/04 và source dependencies; evidence T03 không nhận là live provider quality.

## T04 — SQLite history, evidence artifacts và atomic request lifecycle

**Dependencies:** T01; final decision fixtures từ T03 dùng khi integration. **Files create:** `src/invoice_referee/storage/{__init__,schema.sql,repository,artifacts}.py`, `tests/integration/{__init__,support,test_repository}.py`. **Interfaces:** Consumes ledger models; produces Repository methods/artifact writer trong master và test helper `seed_case`. SQLite connection per transaction, không share connection qua worker thread; `BEGIN IMMEDIATE` cho guards/mutations/final action.

- [ ] **1. Viết RED repository roundtrip và stable request.**

```python
from invoice_referee.storage.repository import Repository
from invoice_referee.domain.models import PipelineResult
from invoice_referee.policy.decision import evaluate
from tests.builders import demo_policy
from tests.integration.support import seed_case

def test_finalize_is_idempotent_and_keeps_history(tmp_path):
    repo = Repository(tmp_path/'cases.sqlite', tmp_path/'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    result = PipelineResult(decision=evaluate(snapshot, bundle), bundle=bundle,
        artifacts=[], stage_durations_ms={}, provider_calls=0, repair_calls=0)
    repo.finalize_run(run.id, result)
    first = repo.get_payment_request(case.id)
    repo.finalize_run(run.id, result)
    assert repo.get_payment_request(case.id).id == first.id
    assert first.amount_vnd == 1_200_000 and first.status == 'CREATED'
    assert repo.history(case.id)
```

Roundtrip test deliberately injects bundle vào persistence boundary; không phải full pipeline proof. T03 not ready: giữ test RED, nghiệm thu CRUD separately bằng config/CaseRecord và final test sau T03. Run `rtk proxy .venv/bin/python -m pytest tests/integration/test_repository.py -q`; expected RED missing repository/schema.

- [ ] **2. Tạo schema tối thiểu và guarded transaction.** Tables theo System §10, columns identity/version/status, JSON payload để tránh ORM và hàng trăm columns. `events` có UTC timestamp/kind/stage/reason/input refs/payload; `human_actions` giữ originals. Foreign keys on; schema init idempotent; migrations bằng numbered version khi thật có schema change. Index request hiện hành:

```sql
CREATE UNIQUE INDEX one_current_payment_request
ON payment_requests(case_id) WHERE status = 'CREATED';
```

Transaction `finalize_run`: read run+case under write lock; nếu đã finalized trả stored run, không dùng result mới; kiểm stop/current run/case version/input hash; stopped/stale không insert; persist full decision/bundle+issues/events. CREATE cần positive VND amount/basis hợp lệ; request giống bản hiện hành trả lại, input/decision đổi phải revoke/supersede bản cũ trước bản mới. NONE/REQUEST_INFO/ESCALATE/REJECT không tạo request mới. Sửa input revoke current request cùng transaction với version increment. Giữ requests/history để giải thích Override.

Thêm table `policy_versions`: version/config hash/activation ID/threshold version/active payload và audit global event. `record_policy_change` và `get_active_policy` giúp config đã activate tồn tại sau restart; không dùng config file cũ làm active lại âm thầm. `seed_case` dùng Upload chứa synthetic PDF bytes, rồi thay evidence IDs trong documents/registries/refs về IDs được lưu; test repo không dùng bundle từ một evidence chưa nộp. Đây là persistence/fake boundary fixture, không phải OCR PDF quality proof.

`request_stop` dùng cùng lock: khi final commit xong→ALREADY_COMPLETED; active→persist stopflag+STOP_REQUESTED+event rồi trả acknowledgement. `assert_run_current` check persisted snapshot/stopflag, raise StoppedRun khi stop; input stale→STALE_VERSION. `mark_interrupted_runs` gắn FAILED/technical interruption khi startup, không auto rerun. T08 owns one-process slot, SQLite owns final guard.

`finalize_run` gặp stop flag thì kết thúc old run STOPPED, không áp dụng incoming result. Gặp stale snapshot thì kết thúc old run FAILED/STALE_VERSION và giữ diagnostics, không đổi current case/new run/request. Không ném lỗi rồi để run cũ RUNNING mãi. Record policy change cần actor_mode và reason thật; automatic threshold actor SYSTEM không được giả là human POLICY_OWNER approval.

- [ ] **3. Intake và artifact ownership.** Validate meaningful input, strictamount, supported extension/mime, size/filecount before case. Dedup cùng bytes; không coi duplicate file là independent supporting. Backend assigns IDs/paths; use exclusive atomic write (temp file + os.replace) dưới case/evidence/run directories, sanitize logical names; client không chọn stored_path/traversal. Hash original bytes. Artifact writer name allowlist/sanitized basename, không rawinputfilename path.

```python
from pathlib import Path

def safe_name(name: str) -> str:
    if not name or name in {'.', '..'} or Path(name).name != name or '\\' in name:
        raise ValueError('Artifact name must be a basename')
    return name
```

Tests meaningfulempty, filelimits, duplicate hashes, traversal, samebytesroles, restartpreserved state, rollback injectedfailure. Sourcefile persistfailure technical, không create orphan case asaccepted; cleanup only temp artifacts mình tạo.

- [ ] **4. GREEN và race test.** Two thread transactions stop/finalization: stopack trước final→zero request; final trướcstop→ALREADY_COMPLETED. Changedversion→stale discarded. Repeatedrun/currentrequest stable; history preserved afterrevoke. Run test command step1, expectedPASS; evidence T04 captures both ordering scenarios, not sleeps alone.

## T05 — Mistral OCR, per-document Kimi và cross-source proposals

**Dependencies:** T02. **Files create:** `src/invoice_referee/extraction/{__init__,providers,validation}.py`, `src/invoice_referee/extraction/prompts/{analyze-v1,cross-source-v1,repair-v1}.txt`, `tests/unit/test_provider_contracts.py`. **Modify:** `pyproject.toml`, `requirements.lock`, `.env.example` (lead sequential ownership after T01). **Interfaces:** Consumes AnalysisRequest/registry/models; produces Providers, RawOcr, `registry_from_ocr`, `validate_document`. Fake implementation `FakeProviders(documents: dict[str,DocumentFacts], registries: dict[str,SourceRegistry])`, `.calls: list[str]`, same signatures; tests can subclass to emit slow/malformed responses.

- [ ] **1. Viết RED contract reject bad coverage/quality.**

```python
import pytest
from invoice_referee.domain.models import AnalysisRequest, DomainError
from invoice_referee.extraction.validation import validate_document
from tests.builders import routine_snapshot, document_facts, text_registry

def test_wrong_evidence_ownership_is_invalid_analysis():
    request = AnalysisRequest(evidence=routine_snapshot().evidence[0],
        registry=text_registry(), required_fields=['merchant','date','currency','total'],
        threshold_version='threshold-b1-085')
    doc = document_facts(evidence_id='unrelated-evidence')
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'
```

Run `rtk proxy .venv/bin/python -m pytest tests/unit/test_provider_contracts.py -q`; expectedRED import, then ownershipguardfailure.

- [ ] **2. Kiểm official APIs ở execution và khóa provider identity.** Đọc primary docs Mistral OCR response schema+word scores/options, Kimi/Moonshot chat endpoint/model availability, SDK Python compatibility. Ghi source URL, verified date, actual SDK+model ID và request schema vào `docs/evidence/provider-contract.md`. Cài versions sau verify, lock và pipcheck. Config thiếu→CONFIG_NOT_ACTIVE/PROVIDER_FAILED rõ; không chạyfake khi mode=live. Nếu OCR API không cung cấp score/word coverage cho numeric span thì giữ UNCERTAIN và reviewer flow; không tự dựng scores. Không claim modelvision nếu payloadtextonly.

```python
# Payload boundary: serialized document request, không dùng toàn case.
def analysis_payload(request):
    return {
        'evidence_id': request.evidence.id,
        'role': request.evidence.role,
        'source_registry': request.registry.model_dump(mode='json'),
        'required_fields': request.required_fields,
        'schema_version': 'document-facts-v1',
    }
```

Prompt yêu cầu quoted source IDs/locators, raw/normalized/quality observations, unique/full item coverage và explicit missing. Không gửi employee prose, expected/case label hoặc nguồn khác vào AnalyzeDocument. Cross-source chỉ usable facts+refs; mapping/conflict proposal, không authority/finalstatus. Schema generated từ strict models; required field missing represented FieldFact MISSING thay hallucinatevalue.

- [ ] **3. Implement transports, validator và shared repair budget.** Timeouts finite 60s mỗi call, SDK retries disabled để budget không nhân ngầm; transport failure ghi technical, không loop. OCR raw retained, registry positions/words reflect received API; no content is field/sourceblocker, malformed structure technical. JSON parse/schema/IDs/sourcecoverage/contradictions consume **same** repair budget1, không riêng1 cho từng validator. Cross proposal coverage can get one extra cross coverage repair; validator vẫn không waive requirements. Ghi requesthash/prompt/schema/model/provider/latency/calls/repairreason/tokensnếuAPIcó, tokenmissing=None chứ không giả0.

```python
def shared_repair_allowed(repair_count: int) -> bool:
    return repair_count < 1
```

Tests fakeclient returning malformedJSON then schema-invalid then correct: dừng sau response2 INVALID_ANALYSIS, không gọiresponse3. Duplicate assessment/itemID/extraID/badrefs/UNREADABLE+false-verification→reject/one repair thentechnical. Uncovered arithmeticregions cannotlabelTOTAL_ONLY toskip; semantic mappings ambiguous→reviewer issue. T06 chooses cross eligibility using code, adapter cannot decide optionality.

- [ ] **4. GREEN adapter checks; live riêng.** Run step1 command+pipcheck, expectedPASS. Ghi fake-only evidence T05. Live smoke được chuẩn bị bằng file synthetic+command ở T15; chỉ gọi khi user đã cho phép provider spending. Missing credentials không là testPASS live; ghi INCONCLUSIVE. Gate unlockT06 dựa fake contract; final live integration readiness riêng T15/T16.

Ngay ở T05, kiểm actual OCR options/schema có đáp ứng word/locator score gate không; khi được phép, chạy một synthetic sample sớm. Nếu không có quality signal cần thiết, ghi live routine capability INCONCLUSIVE và giải evidence contract trước khi đóng A02 live gate. Không lấy model READABLE hoặc fake 0.99 score thay native coverage. T15 là integration/public proof, không nên là lần đầu phát hiện incompatibility này.

# InvoiceReferee — review mức hoàn thiện và baseline

Ngày: **06/10/2026**. Verdict duy nhất: **Changes required**.

Code đã có lõi MVP và bộ đo replay chạy được. Chưa đủ căn cứ nghiệm thu/freeze
B1: có lỗi chọn nguồn tiền, UI human actions không đi hết workflow, và metric
chưa đúng contract. Chưa đạt đầy đủ Sprint 2 hoặc sẵn sàng kiểm thử chung kết.
Không suy tỷ lệ hoàn thiện hay điểm thi từ số unit tests.

## 1. Snapshot, phạm vi và cách review

- Branch `rebuild`; HEAD `f546ebd82c843326704f3d9da847f7941fc6d9be`.
- Working tree gồm chỉnh sửa có sẵn: `frontend/src/App.tsx`,
  `frontend/src/CaseForm.tsx`, `frontend/src/styles.css`.
- `App.tsx` và `styles.css` đổi bytes trong lúc review. Build đầu thất bại
  TS6133; build cuối và frontend tests cuối PASS. Lỗi build đầu **không còn là
  finding mở**. Source backend, HumanActions và các contract liên quan không đổi.
- Snapshot/hash: `data/output/review-2026-10-06/source-snapshot*.json`.
  Vì frontend tiếp tục đổi sau snapshot cuối của working tree, lead đã chụp
  30 tracked frontend files sang `frontend-reviewed/` rồi chạy build/tests trên
  copy đó. `source-snapshot-reviewed.json` + `frontend-reviewed-hashes.json`
  xác định đúng bytes đã kiểm; không khẳng định working tree đang sửa đã đứng yên.
  Đây là identity phục vụ review, **không phải freeze/acceptance B1**.
- Ba reviewer độc lập được chạy đúng `chatgpt-web/gpt-5.6-sol`, `medium`:
  Avicenna (domain/extraction/policy), Dalton (application/storage/API/frontend),
  Linnaeus (Verify/corpus/measurement/release evidence). Lead kiểm tra lại các
  finding quan trọng bằng source và probes qua application/API thật.
- Review hướng theo contract trên toàn bộ các mảng source trên, config/env,
  prompts, tests liên quan, fixture generator, specs, plans, README/build log.
  Không phải chứng minh đã tìm mọi bug trên mọi dòng. Bỏ qua vendor dependencies,
  visual polish, load tests, enterprise auth/scaling và các feature chưa yêu cầu.
- Graph: CodeGraph v1.6.0 trả source on-disk/call paths; MCP generation/index
  status/check_index_coverage không được expose. Coverage exhaustive **UNKNOWN**;
  các đoạn bị trim được đọc bổ sung. Không tự index hoặc upgrade.
- Chỉ đọc source/chạy offline checks; tạo report và evidence trong ignored
  `data/output`. Không sửa production/tests, không stage/commit/push, không gọi
  provider thật, không deploy. Không chạy holdout hoặc tune từ holdout.

Nguồn cuộc thi là [brief gốc](../../Challenge_Brief_OrganizationAI_VN.docx.md),
đặc biệt §§2.A,3–6. Contracts project:
[Rulebook](../../specs/B1_RULEBOOK.md), [System](../../specs/B1_SYSTEM_SPEC.md),
[Evaluation](../../specs/B1_EVALUATION_SPEC.md).

## 2. Bằng chứng chạy mới

| Check | Kết quả | Mode/phạm vi |
| --- | --- | --- |
| `rtk proxy env PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q` | 418 passed, 1 Starlette deprecation warning, 6.42s | Backend unit/integration offline |
| `rtk proxy .venv/bin/python -m pip check` | Exit 0, no broken requirements | Có warning quyền ghi pip cache |
| Frontend `run test -- --run` | 34 passed / 8 files; captured copy 1.38s | Component tests, không phải browser/API E2E |
| Frontend `run build` | Exit 0, tsc + Vite PASS trên captured copy | Build, không chứng minh workflow đóng được |
| Verify `--suite core --mode replay` | 4/4 PASS | PIPELINE_FAKE_OR_REPLAY |
| Verify `--suite escalation --mode replay` | 5/5 PASS; 3 auto + 2 human | PIPELINE_FAKE_OR_REPLAY |
| Verify `--suite all --mode replay` | 15/15 PASS | Development corpus; không phải tập độc lập |

Verify commands dùng `.venv/bin/python -m invoice_referee.verify`, output riêng
`data/output/review-2026-10-06/{core,escalation,all}`. Lead đã đọc JSON reports;
không chỉ dùng worker completion. All có 4 requests, 9 expected-human cases,
0/9 missed escalation, 0/4 unnecessary escalation và 1/15 technical executions
(TC15 cố ý kỳ vọng technical failure, nên testcase vẫn PASS).

Không gọi các tỷ lệ này là độ chính xác OCR/AI hay generalization. Có lỗi metric
khác được ghi ở IR-03. Python 3.14.5, Node 26.0.0, npm 11.12.1.

Frontend root đã PASS trước khi source tiếp tục đổi. Kiểm cuối có commands:
`rtk proxy npm --prefix data/output/review-2026-10-06/frontend-reviewed run build`
và `rtk proxy npm --prefix data/output/review-2026-10-06/frontend-reviewed run test -- --run`.
Copy dùng dependencies đã cài trong project; không phải clean-clone proof.

Child extraction từng báo 209 pass/2 thiếu `httpx` ở interpreter khác; không gộp
vào project test result. Lead dùng project `.venv`, chạy 418 pass và tái hiện
finding bằng `.venv` thành công.

Evidence reproducible của lead:

- `probe_primary_identity.py` → `primary-identity-probe.json`.
- `probe_ui_actions.py` → `ui-api-probe.json`.
- `metric-probe.json`: phản chứng metric, **không phải benchmark hệ thống**.
- `local-checks.json`: giữ cả build đầu và build cuối.

Các file trên nằm trong `data/output/review-2026-10-06/`. Hai probe Python chạy
bằng `rtk proxy env PYTHONPATH=. PROVIDER_MODE=fake .venv/bin/python <path>`.
DB/artifacts của probes dùng temporary directories, không đụng hồ sơ đang dùng.

## 3. Finding ledger

### IR-01 — Critical / OPEN — amount lấy từ supporting document

Contract: Rulebook dòng 38 yêu cầu merchant/date/total có nguồn primary document.
Source: [decision.py:435](../../../src/invoice_referee/policy/decision.py:435)
`_verified_total` ưu tiên `kind == BILL`, rồi dùng usable total; không bind vào
evidence ID có role PRIMARY_BILL. Preflight chỉ đếm role; validator kiểm ownership
nhưng không chặn role-kind swap; non-CONTEXT documents cùng vào bundle.

Lead tái hiện qua **CaseService.submit/start_run/wait + SQLite finalization**:

```text
TRAVEL; requested = 1.200.000 VND
PRIMARY_BILL role  → analyzed kind GOODS_RECEIPT, total 1.000.000
GOODS_RECEIPT role → analyzed kind BILL,          total 1.200.000
→ SUCCEEDED / CREATE_PAYMENT_REQUEST / ROUTINE_AUTO
→ persisted request CREATED 1.200.000 VND
```

Đây là giả lập analyzer trả phân loại sai, không phải live LLM accuracy test.
Số của mỗi document đều sourced/usable; lỗi là chọn sai **document authority**.
Scenario primary total UNCERTAIN đơn thuần không đủ chứng minh bypass, vì SRC-02
sẽ chặn; ledger dùng witness role-kind swap thực sự đã chạy.

Pass condition: bind primary role → evidence ID → analyzed document và kind hợp
lệ; không ngầm thay bằng supporting bill. Witness trên phải không tạo request.
Không sửa bằng cách chọn phần tử đầu bundle. Cần regression qua persistence.

### IR-02 — High / OPEN — human action form không khớp backend

Source: [HumanActions.tsx:72](../../../frontend/src/HumanActions.tsx:72),
[human.py:57](../../../src/invoice_referee/application/human.py:57),
[human.py:281](../../../src/invoice_referee/application/human.py:281).

| UI action | Payload hiện tại | API witness |
| --- | --- | --- |
| APPROVE_AMOUNT | `policy_version: ''` | 422 INVALID_ACTION, sai active policy version |
| SUPPLY_DECLARATION | `{}` | 422, thiếu `changes` |
| CONFIRM_FIELD | `refs: []` | 422, nguồn không được rỗng |
| CONFIRM_MAPPING | `{}` | 422, thiếu `pairs`/`refs` |
| DENY | `{}` | 422, thiếu payload `issue_id` |
| ADD_EVIDENCE | JSON `{}` | 422; cần đường upload multipart đúng |

Lead gửi literal payload từ source UI vào FastAPI TestClient trên service thật
với fake providers. Cùng approval payload sửa **chỉ policy_version** → HTTP 200,
CREATE_PAYMENT_REQUEST/HUMAN_AUTHORIZED. Không dùng kết quả này làm browser test.

Backend closure đã có; nút/form không chứng minh người dùng thực thi được nó.
Các component tests mock callback, nên 34 pass không bắt lỗi contract này.
Pass condition: thao tác UI thật qua API đóng đúng issue, giữ scope/refs/versions
và tạo hoặc từ chối request đúng; có checks bao qua boundary UI/API.

### IR-03 — High / OPEN — metric chưa dùng được làm báo cáo B1/B2 chuẩn

Source: [metrics.py:24](../../../src/invoice_referee/verify/metrics.py:24);
Evaluation §§6–7, dòng 117–123.

- `wrong_routine_automation` chỉ xét expected-human, mẫu số cũng expected-human.
  Contract là routine requests sai điều kiện/quyền / tổng routine requests.
  Case đáng lẽ REJECT hoặc technical bị auto sai không được numerator hiện tại đếm.
- `amount_correctness` cộng cả case không yêu cầu amount rồi chia total cases.
  Report all ghi 15/15 trong khi có 4 requests; contract chia requests tạo.
- Chưa có aggregate chứng minh source correctness/closure correctness hoặc đầy
  đủ runtime/cost theo contract. Có elapsed/trace riêng không đồng nghĩa không
  thu runtime nào; gap là phép đo/báo cáo nghiệm thu chưa hoàn chỉnh.

Lead phản chứng bằng copy report: đổi actual của expected-REJECT thành routine
request. Verdict vẫn bắt FAIL (14/15), nhưng wrong-routine metric vẫn **0/9**.
Đây là lỗi báo cáo, không phải khẳng định production đã auto case REJECT đó.

Pass condition: tử/mẫu số đúng dân số theo spec, phân biệt routine/human-authorized
requests, technical/all attempts, không dùng null expectation làm amount đúng;
metric probes bắt cả expected-refusal/technical sai auto. Báo metric thiếu là
INCONCLUSIVE, không ngầm 100%.

### IR-04 — High / OPEN — chưa có accepted/frozen B1

T12 yêu cầu acceptance ledger và hash source/config/rulebook/prompts/locks/corpus/
outputs/traces/runtime/mode/dirty bytes. Chưa có `scripts/freeze_baseline.py`,
`docs/evidence/B1_BASELINE.md`, `docs/evidence/b1/freeze.json` trong scope đã kiểm.
README còn ghi T12 PLANNED. Source snapshot của review không thay acceptance.

Pass condition: IR-01/02 và measurement gates được đóng; tạo acceptance với các
gap/mode rõ ràng, khóa exact inputs/outputs/identity và kiểm hash khi so B2.
Live URL chưa có **không tự nó chặn freeze baseline replay** nếu scope được công
bố trung thực. Tuy nhiên không dùng freeze replay để tuyên bố cuộc thi hoàn tất.

### IR-05 — High for live/new-input evidence / OPEN — fixture PDF không đọc được

Source: [make_synthetic_evidence.py:128](../../../scripts/make_synthetic_evidence.py:128)
sinh vài bytes `%PDF-1.4 ... %%EOF`, không có cấu trúc PDF hoàn chỉnh.
Lead chạy `rtk proxy pdfinfo tests/fixtures/development/documents/TC01-primary_bill.pdf`
→ exit 1, không đọc được trailer/xref.

15 cases replay vẫn hợp lệ để kiểm policy/application vì artifacts được inject.
Chúng không chứng minh ingestion/OCR thực sự đọc 15 hóa đơn hoặc model chịu được
layout mới. Pass condition cho document/live baseline: PDF/ảnh renderable có gold
đọc độc lập; thử qua provider thật theo quyền gọi live, lưu identity và failures.

### IR-06 — Medium / OPEN — Override chưa có thao tác UI

[HumanActions.tsx:15](../../../frontend/src/HumanActions.tsx:15) không đưa OVERRIDE
vào action kinds của các role. Toàn bộ literal search frontend chỉ thấy type và
label OVERRIDE, không có control thực thi. Backend Override/tests có, Stop có.
Vì giám khảo dùng sản phẩm, không thể tính backend-only Override là UI feature.
Pass condition: control phù hợp gửi operation/values đúng scope và giữ quyết định
gốc; không được waive quality/arithmetic hoặc biến demo role thành identity thật.

### IR-07 — Medium / OPEN — một số câu hỏi còn chung chung

[decision.py:278](../../../src/invoice_referee/policy/decision.py:278) tạo câu hỏi
SRC-02 dạng “Primary bill thiếu/không dùng được trường bắt buộc; cần đọc lại nguồn”.
Nó chưa nêu field/value/căn cứ cụ thể trong chính câu hỏi. Bộ rule/refs là nền tốt,
nhưng câu này chưa chứng minh đạt rubric “trả lời ngay, không tra lại hồ sơ gốc”.
Chưa làm professional-user scoring, nên không gán tỷ lệ question accuracy.
Pass condition: câu hỏi chỉ rõ chứng từ/trường, dữ kiện đang có, cần xác nhận gì
và ai có quyền; professional participant thử trả lời và ghi effort/feedback.

### IR-08 — Medium planning/doc / OPEN — outline slides lệch brief

Plan evidence-release T16 dòng 254 đặt Slide 3 human classes/controls và Slide 4
Verify/users. Brief §3.e bắt buộc Slide 3 tác động + phương pháp đo; Slide 4 kiến
trúc/triển khai + real/simulated. Đây là lỗi **plan**, không nói một deck đã nộp sai.
README cũng còn câu “no live provider call has been made”, đã cũ so với log live
05/10. Current-state claims cần dùng source/evidence, không dùng câu đó như fact.

## 4. Mức đáp ứng cuộc thi

| Requirement | Trạng thái review | Khoảng cách |
| --- | --- | --- |
| Quy trình/rulebook cụ thể | IMPLEMENTED | Policy demo proposed + activation; cần người chuyên môn phản biện nghiệp vụ |
| Tự xử lý routine | VERIFIED replay, có IR-01 | Chưa chứng minh current compact auto trên chứng từ mới qua live adapters |
| >=15 tình huống, Core4/Escalation5 | VERIFIED replay | Raw documents là placeholders, không phải document benchmark |
| Ba nhóm bất định/owner | IMPLEMENTED + VERIFIED development | Không phải independent evaluation |
| Không khẳng định trên dữ liệu nghi vấn | IMPLEMENTED nhiều hard gates | Role/kind mismatch IR-01 vẫn có unsafe automation |
| Câu hỏi concrete/answerable | IMPLEMENTED một phần | IR-07; chưa chấm với professional users |
| Human response → reevaluate | VERIFIED backend fake | IR-02 chặn UI closure |
| Audit/Stop/Override | IMPLEMENTED; backend tests | Override UI IR-06; chưa browser E2E toàn bộ |
| Nhận input mới | IMPLEMENTED intake/live adapters | Chưa có fresh current-build LIVE_END_TO_END benchmark |
| Feedback tự điều chỉnh threshold | PLANNED T13 | Chỉnh config bằng tay không đáp ứng Sprint2 |
| Missed/unnecessary trên tập độc lập | INCONCLUSIVE | Development rates không thay holdout; T12/T13 chưa hoàn thành |
| >=3 nhân sự nghiệp vụ + feedback/change/bất cập | INCONCLUSIVE evidence, T14 PLANNED | Chưa có sessions/quotes/linked change trong bộ evidence được cung cấp |
| Public live URL | PLANNED / chưa triển khai | User xác nhận trực tiếp 06/10, dự định làm sau cùng |
| Clean-clone/deployment proof | PLANNED T15 | README setup không phải phép chạy clean clone/deploy đã kiểm |
| Public repo/history | INCONCLUSIVE về public access | Local Git history có; chưa kiểm public accessibility |
| 5 slides/video <3m/build log1page | PLANNED T16 | Build log dev có; chưa có submission package đã kiểm |

Brief §4: chung kết **45 demo + 35 phản biện + 20 kiểm thử A**. Không dùng thang
sơ loại 40/20/20/20 để đoán final score. Đề A kiểm 5 input mới, khoảng 2 cần human.
Theo brief trong repo, khóa bài nộp **15/10**, Demo Day **17/10**; thông báo riêng
mới hơn của BTC và feedback riêng chưa được cung cấp để đối chiếu.

Historical LIVE_END_TO_END nhà hàng 05/10: 644.742s, FAILED/NONE/INVALID_ANALYSIS,
zero request, 32.180 tokens response đầu. Đây là source revision trước compact.
Compact evidence sau đó là offline projection + transport tests, không phải live
speedup/quality mới. Không gọi thêm live trong review này.

## 5. Baseline đã đo được chưa?

**Đo được candidate replay baseline ngay bây giờ:** policy/application decisions,
fixed-sample missed/unnecessary escalation, request lifecycle, technical outcomes.
Review đã lưu actual outputs và snapshot. Điều này đủ làm evidence kỹ thuật phát
triển, nhưng không tự thỏa điều kiện accepted B1 hoặc current live performance.

**Chưa có frozen/accepted B1:** IR-01/02 và các gate integration/measurement còn
mở, chưa freeze identity/report. Không nên bắt đầu tuyên bố B2 tốt hơn B1 ở đây.

**Chưa đo đủ baseline document/live hoặc tác động người dùng:** thiếu renderable
corpus/current live runs và before/after professional trials. Cần tách active
human time, provider wait, rework, learning cost và burden kiểm tra lại.

Ba tập development/calibration/holdout đã có cấu trúc; khác folder/ID/hash không
tự chứng minh khác biệt nghiệp vụ hay độc lập. Review không chạy holdout, không
tune từ nó. Đổi framework, agent count hay latency replay không thay bằng chứng
giảm việc đối chiếu của kế toán. Nguồn ledger công ty để biết đã trả thật vẫn là
scope cần xác định; không suy người trả thật chỉ từ checkbox PERSONAL.

## 6. Thứ tự đề xuất và điều kiện qua bước

1. **Đóng IR-01:** role/source identity; witness không còn tạo request.
2. **Đóng IR-02/06:** UI→API→reevaluation cho declaration/confirmation/upload/
   approve/deny/override; controls chạy bằng thao tác người dùng.
3. **Đóng IR-03 + tăng chất lượng câu hỏi:** metric đúng mẫu số; câu hỏi có dữ kiện;
   re-run development/safety suite. Không sửa gold để được xanh.
4. **T12 freeze candidate đúng scope:** acceptance, source/config/datasets/outputs/
   hashes/mode; phân biệt replay VERIFIED với live INCONCLUSIVE.
5. **T13/B2 và professional trials:** calibration provenance, adaptation tự động
   bounded/versioned, sealed independent comparison; >=3 người thật và một đổi
   sản phẩm truy được về feedback. Chuẩn bị recruiting song song các bước đầu.
6. **Live document proof + deploy + submission:** renderable inputs, live trace
   và auto case; live URL theo thời điểm user chọn; clean-clone, 5 slides đúng cấu
   trúc, video/log và diễn tập 5 input mới trước hạn 15/10.

Lõi deterministic policy, provider boundary, shared UI/Verify service và atomic
finalization là nền tốt, phù hợp one-operator MVP. Ưu tiên hoàn thiện các đường
hiện có và bằng chứng đo lường. Chưa có finding nào buộc đổi sang LangGraph,
microservices hoặc kiến trúc production nhiều người dùng.

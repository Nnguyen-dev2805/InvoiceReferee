# InvoiceReferee — Ngôn ngữ và luồng giao diện Implementation Plan

> **For agentic workers:** dùng skill `executing-plans` theo từng task. Nếu chủ
> dự án cho phép chia việc, dùng `subagent-driven-development`; một writer cho
> contracts/copy chung. Chỉ đánh dấu checkbox sau khi có evidence thật.

**Goal:** nhân viên, kế toán và người duyệt hiểu tình trạng hồ sơ, căn cứ và
việc cần làm tiếp mà không phải biết thuật ngữ lập trình hoặc đọc mã nội bộ.

**Architecture:** giữ React/Service/API và guards hiện có; đổi nội dung, thứ tự
panel và cách mở căn cứ. Một module nhỏ cho nhãn và tóm tắt trạng thái hiển thị,
không tạo engine nghiệp vụ ở frontend. Kết quả/routing/money vẫn từ backend;
chẩn đoán kỹ thuật vẫn truy cập được nhưng không chiếm màn nghiệp vụ chính.

**Tech Stack:** React 18/TypeScript/native HTML/CSS, Vitest/Testing Library;
Python pytest chỉ cho đổi câu chữ backend. Không thêm thư viện UI/i18n/chart.

**Spec:** [Product P3/P6/P7](../../settlement/PRODUCT.md),
[System S2/S3/S6](../../settlement/SYSTEM.md),
[Rulebook R5–R11](../../settlement/RULEBOOK.md).
§2–§5 dưới đây là đề xuất UX cụ thể của plan này, trạng thái **PLANNED**;
không coi các thay đổi UI đã triển khai hoặc được người dùng thực nghiệm.

## Global Constraints

- MVP khoảng 5 người, ba vai demo; không authentication/tenancy/workflow engine.
- Không đổi schema/API, công thức, quyền, coverage, policy, money hoặc closure gates.
- Unknown/null khác 0; COMPLETE khác approved/received/closed. READ khác verified payer.
- B3 report-only chưa duyệt/chi ứng; không tạo nút hoặc câu thành công giả cho chức năng đó.
- Xử lý bản nháp trước khi nộp; xác nhận nhân viên khác phê duyệt tài chính.
- Giữ lý do/refs/số tiền/mâu thuẫn/lỗi kỹ thuật, không làm giao diện xanh bằng cách giấu lỗi.
- UI và Verify dùng cùng pipeline. LIVE reader + synthetic company context phải ghi rõ cả hai.
- Không sửa PDF/gold/frozen corpus hoặc gọi live providers trong task copy/layout này.
- Giữ các sửa chưa commit ở App.tsx/App.test.tsx/styles.css; không reset hoặc ghi đè.
- Không stage/commit/push nếu người dùng chưa yêu cầu. Không cài dependency mới.

## 1. Review: vấn đề và bằng chứng

Checkout review: branch `rebuild`, HEAD `b3844eb0ca84cd0e7eadec8fee5b1ad428bccb67`.
Active composition là `frontend/src/main.tsx → settlement/App.tsx`; không sửa
legacy `frontend/src/App.tsx`, CaseDetail hoặc VerifyPanel ngoài cây settlement.
Graph truy App→ReportPanel/ActionsPanel/QuestionsPanel/VerifyPanel; snippets bị
trim đã đọc các đoạn cần thiết trực tiếp. Generation/coverage API không expose;
không claim audit đầy đủ. Agent refresh graph/source các vùng mình sửa.

Evidence gồm source hiện tại và report LIVE `R-ea01368e3817` chủ dự án cung cấp.
Browser mở localhost bị từ chối vì quyền bị từ chối; không dùng browser khác,
HTTP-to-DOM, CDP hoặc screenshots vòng tránh. Chưa xác minh pixels/scroll/focus
trên browser thật. Review wording/source là VERIFIED; live visual UX INCONCLUSIVE.

| ID | Bằng chứng source | Vấn đề cụ thể | Mức |
| --- | --- | --- | --- |
| UX01 | App.tsx:839–882 | SUCCEEDED/INCOMPLETE/LIVE/stage/trace đặt ngang hàng, không giải thích đang chờ xác nhận hay thiếu dữ liệu | Cao |
| UX02 | Report.tsx:256–270 | B3/proposal/enum và dấu — lấn át nội dung đề nghị; thiếu nơi/mục đích không thành việc cần làm nổi bật | Cao |
| UX03 | App.tsx:874–934 | Điền form từ report rồi tìm panel sửa phía dưới; nút Gửi revision/confirm mô tả implementation | Cao |
| UX04 | B3Intake.tsx:110–129/139–140 | Nhãn chứa actual; cột Công ty trả/Nhân viên trả có thể bị hiểu đã thanh toán dù là dự toán | Cao |
| UX05 | Report.tsx:49–60/286–289 | Refs hiện mã field dính/lặp; nguồn không có tên thân thiện hoặc trang dễ nhận biết | Cao |
| UX06 | App.tsx:776–803 | allowed_action.reason, issuer/export và format kỹ thuật hiện trong phần nộp hồ sơ | Vừa |
| UX07 | Actions.tsx:71–116 | B3 hiện bảng tiền — và B3_REPORT_ONLY/lifecycle dù chưa có chức năng duyệt/chi ứng | Cao |
| UX08 | Questions.tsx:60–121 | owner/fact/re-check/resolve/version trong lời hướng dẫn; chọn nguồn bằng S-ID | Cao |
| UX09 | App.tsx:963–973 | History hiện enum và actor-ID, không kể người nào đã làm việc gì | Vừa |
| UX10 | Verify.tsx:39–79; App render VerifyPanel luôn | Suite/FP/FN/holdout phục vụ đánh giá nhưng đặt cạnh hồ sơ nhân viên | Vừa |
| UX11 | App.tsx:508–659 | B3 gắn giao việc bằng lời vào tên tác vụ; IMPORT thấy cả upload và form rỗng; chỉ dẫn clocks/backend/context cho nhân viên | Vừa |
| UX12 | App.tsx:713–724/750–755 | Mốc kiến thức, revision/epoch không có ý nghĩa hành động rõ cho người dùng | Vừa |

Nguyên nhân thiết kế: giao diện hiện phơi cấu trúc backend và các invariants để
giải thích với developer. Người dùng cần câu trả lời theo hồ sơ và trách nhiệm.
Chỉ dịch SUCCEEDED thành Thành công vẫn gây hiểu nhầm đã duyệt.

Known logic findings riêng từ review trước: thiếu destination/purpose dù giấy có;
document.role khác giữa hai loại giấy bị báo conflict; proposal_relation PASS dù
thiếu trip facts; ngân sách UI đang dùng work_permission để hiển thị. Plan này
không tự chữa evaluator/schema hoặc tự gán APPROVED. Những trường hợp đó cần
giữ cảnh báo và ghi issue riêng; không sửa nhãn để tuyên bố dữ liệu đã đúng.

## 2. Ngôn ngữ và hierarchy cần triển khai

### 2.1 Màn nghiệp vụ và phần kỹ thuật

Mặc định chỉ hiển thị: hồ sơ/nhân viên/chuyến đi, tình trạng, việc cần làm,
thông tin đề nghị/kết quả, tài liệu, vướng mắc, hành động đúng vai.
Mã hồ sơ C-... vẫn có thể hiển thị/copy để tra cứu; không trộn C/R/S/field IDs
vào mỗi câu. Mã công việc vẫn lưu và ở thông tin hồ sơ khi cần, không đổi linkage.

`Chi tiết kỹ thuật` dùng native `<details>` đóng mặc định: run ID/status/stage,
completion, revision/epoch/clocks, raw keys/refs, calls/tokens, hash/config/context.
Vẫn giữ thông báo lỗi/chênh lệch trên màn chính; details chỉ chứa chẩn đoán sâu.
Không dùng accordions mặc định đóng để giấu vấn đề nhân viên phải xử lý.

`Đánh giá hệ thống` là khu riêng đóng mặc định hoặc tab riêng, giữ VerifyPanel
và toàn bộ metrics/limitations; không chạy suite vì mở tab hoặc tải trang.
Không quảng cáo Verify offline là độ chính xác LIVE hoặc nghiệp vụ thật.

### 2.2 Bộ chữ dùng chung

| Hiện tại | Chữ hiển thị cần dùng |
| --- | --- |
| B3 — Đề nghị tạm ứng (giao việc bằng lời) | Đề nghị tạm ứng |
| B7 — Quyết toán sau công việc | Quyết toán chi phí |
| WEB / IMPORT | Điền thông tin / Tải hồ sơ có sẵn |
| Nguồn / Tải lên nguồn | Tài liệu đính kèm / Thêm tài liệu |
| provenance/issuer/export | Ghi chú về tài liệu (không bắt buộc); Ví dụ: bảng do kế toán cung cấp |
| Số xin ứng (... actual) | Số tiền đề nghị tạm ứng; gợi ý: Số tiền bạn đang xin, chưa phải tiền đã nhận |
| Công ty trả / Nhân viên trả trong dự toán | Công ty dự kiến trả / Nhân viên dự kiến trả |
| Cơ sở | Cơ sở dự toán; gợi ý: Ví dụ 1 đêm, 1 vé khứ hồi |
| Hạn quyết toán | Hạn thanh toán tạm ứng; gợi ý: Ngày dự kiến nộp chứng từ và xử lý tiền ứng |
| Report / proposal | Kết quả kiểm tra / Đề nghị tạm ứng |
| Critical facts | Thông tin đọc từ tài liệu |
| Checks / Issues | Các mục đã kiểm tra / Việc cần làm rõ |
| Refs | Căn cứ; liên kết Xem tài liệu |
| owner | Người cần xử lý; dùng Nhân viên/Kế toán/Người duyệt |
| draft / revision / confirm | Bản nháp / Bản cập nhật / Xác nhận gửi đề nghị |
| Ghi review | Lưu kết quả rà soát |
| Stop / Resume | Tạm dừng xử lý / Tiếp tục xử lý |
| History | Lịch sử xử lý |
| source mode LIVE | Đọc bằng AI thật |
| FAKE_OR_REPLAY/POLICY_REPLAY/... | Đọc giả lập / Chạy lại dữ liệu / Kiểm tra quy tắc, đúng mode backend; raw mode ở details |

Định dạng số **2.000.000 đ**, ngày **12/10/2026**; input date/number vẫn giữ raw
API ISO/int. Null → `Chưa xác định`; NOT_APPLICABLE → `Không áp dụng`; zero → `0 đ`.
Không dùng ≈ cho tiền nguyên VND đang nhập vì đó là số chính xác, không ước lượng.
Không dịch role picker thành đăng nhập. Tên/mã người có quyền từ context config,
không từ chức danh hoặc thông tin nhân viên tự ghi trên giấy.

### 2.3 Trạng thái xử lý khác kết quả hồ sơ

| Tình huống backend | Headline / hướng dẫn trên màn chính |
| --- | --- |
| Chưa có run | Chưa kiểm tra hồ sơ; bước tiếp theo theo WEB/IMPORT |
| QUEUED | Đang chờ xử lý |
| RUNNING | Đang đọc/kiểm tra hồ sơ; một thông báo role=status, không fake % hoặc ETA |
| SUCCEEDED + B3 draft unconfirmed | Kiểm tra bản nháp trước khi gửi; đã đọc xong không nghĩa đã nộp |
| B3 draft thiếu destination/purpose | Còn thiếu: Nơi đến, Mục đích công tác; mở editor, highlight hai trường |
| NEEDS_INFORMATION / blocking issues | Hồ sơ cần bổ sung hoặc làm rõ; liệt kê việc, người xử lý và căn cứ |
| NEEDS_AUTHORIZED_REVIEW | Cần người có thẩm quyền xem xét; không gọi Đã duyệt |
| READY_FOR_ACCOUNTANT_REVIEW | Đủ thông tin để kế toán rà soát; chưa phê duyệt, chưa chi |
| FAILED/TIMED_OUT/INTERRUPTED | Chưa kiểm tra xong do lỗi xử lý; giữ phần có sẵn, cho xem chi tiết/thử lại khi allowed |
| STOPPED/stop_active | Hồ sơ đang tạm dừng xử lý; không hứa đã hủy lệnh ngân hàng |
| SUPERSEDED/report của run cũ | Kết quả thuộc bản hồ sơ trước; không làm current basis hoặc hiện CTA duyệt |

Chưa có issue không đủ để kết luận đầy đủ: `trip_context=UNRESOLVED` vẫn nổi bật.
Nếu backend trả COMPLETE/ready nhưng check/critical fact material báo FAIL/UNRESOLVED/
CONTRADICTED/UNCLEAR, hiển thị `Kết quả còn điểm cần kiểm tra`, giữ tất cả dữ kiện;
không sửa completion hoặc né backend checks. ID kỹ thuật doc.role vẫn ở details,
cảnh báo hiện trên màn chính: `Hệ thống đang báo thông tin khác nhau; cần kiểm tra`.
Không gán lỗi này thành lỗi nhân viên khi chưa có owner từ backend.

### 2.4 Nội dung quan trọng cần giữ về tiền

- B3: Số xin2M; dự toán công ty3M/nhân viên5M/tổng8M; chưa gọi forecast là B đã duyệt.
- B7: nhãn T/B/E/A/RA/P/RP bỏ chữ cái ở phần chính nhưng giữ đúng ý nghĩa:
  tổng chi công việc; ngân sách được duyệt; chi phí nhân viên được chấp nhận;
  tạm ứng nhân viên đã nhận; tiền hoàn tạm ứng công ty đã nhận;
  tiền công ty đã hoàn trả cho nhân viên; tiền công ty đã nhận lại từ khoản hoàn trả.
- Net dương/âm/cân bằng từ backend: `Công ty cần trả thêm` / `Nhân viên cần hoàn
  lại` / `Không còn chênh lệch theo kết quả kiểm tra`. Luôn ghi `Chưa phê duyệt`
  nếu chỉ calculated/proposed; S0 không tuyên bố đóng hoặc không còn việc cần làm.
- Approved/received/remaining: `Số tiền đã được duyệt` / `Số tiền đã thực nhận`
  / `Phần còn phải thực hiện`; giữ direction và bên nhận; pending chưa cộng vào actual.
- B3 không hiện bảng approved/received/remaining toàn dấu — của B7. Hiện một dòng
  trung tính: `Bản demo hiện hỗ trợ kiểm tra đề nghị; chưa thực hiện duyệt và chi ứng`.
- Incident: số thực tế vẫn nguyên; OVERPAY→`Số tiền thực nhận vượt số đã duyệt`,
  WRONG_RECIPIENT→`Người nhận tiền không khớp`. Không suy biện pháp thu/chi tự động.

## 3. Luồng B3: một nơi để xem, sửa và xác nhận bản nháp

```text
Đề nghị tạm ứng — Nguyễn An
Trạng thái: Kiểm tra bản nháp trước khi gửi
AI đã đọc hai tài liệu. Còn thiếu: Nơi đến, Mục đích công tác.
[Kiểm tra và bổ sung bản nháp]

Thông tin đề nghị: 2.000.000 đ | Công tác12–13/10 | Hạn16/10
Dự toán: Công ty3.000.000 đ | Nhân viên5.000.000 đ | Tổng8.000.000 đ
Tài liệu: Giấy đề nghị [Xem] | Dự toán [Xem]
Thông tin cần bổ sung: editor tại đây, cùng references và giá trị đang sửa
[Xác nhận và gửi đề nghị]   [Lưu bản nháp]
Chi tiết kiểm tra [...]
Chi tiết kỹ thuật [đóng]
```

Wireframe là nội dung dự kiến, không kết quả đo hoặc screenshot UI đã chạy.
Header employee name lấy persona/context nếu có, fallback mã nhân viên có nhãn rõ.

- Native WEB: `Gửi đề nghị tạm ứng`, helper `Hệ thống kiểm tra hồ sơ sau khi gửi`.
  Đã gọi create+run hiện hành; không thêm nút duyệt hoặc thay confirmed semantics.
- IMPORT có files: `Tải lên và đọc hồ sơ`; helper `Hệ thống tạo bản nháp để bạn
  kiểm tra. Chưa gửi đề nghị khi chỉ tải tài liệu`. Không cần nhập form rỗng trước
  khi đọc; hide empty form cho IMPORT creation, giữ model defaults đủ draft API.
- IMPORT không files: primary disabled với lý do; secondary `Tạo hồ sơ để bổ sung
  tài liệu sau` dùng create draft hiện có, không yêu cầu chính xác2files vì PDF gộp hợp lệ.
- Preview sẵn: `Kiểm tra bản nháp` đi tới editor hồ sơ đang mở, focus trường còn
  thiếu đầu tiên hoặc heading. Không phải copy dữ liệu vào form tạo hồ sơ mới.
- Nút `Dùng thông tin đã đọc` chỉ khi cần refill; phải bảo vệ thay đổi chưa lưu,
  không polling ghi đè form đang sửa. Refill không PATCH/confirm. Đổi hồ sơ reset
  editor đúng hồ sơ, không cấy thông tin sang new-case form như handleFillFromDraft hiện tại.
- Editor duy nhất cho current dossier, không lặp toàn bộ form ở hai cột. New-case
  form collapse khi đã mở case, vẫn có `Tạo hồ sơ khác`; không tự xóa draft chưa lưu.
- Confirm: `Xác nhận và gửi đề nghị`; gọi PATCH confirmed=True rồi run như hiện có.
  First confirmation không bắt nhân viên nghĩ lý do sửa khi họ không sửa gì:
  dùng audit reason `Xác nhận bản nháp từ tài liệu đính kèm`. Nếu user sửa fields,
  cho Ghi chú thay đổi và giữ requirement reason hiện có. Không bịa câu đã kiểm
  nguồn/đã nhận tiền/đã được sếp cho phép. Test audit reason và đúng actor/revision.
- Sau submit: nút update `Lưu thay đổi`, giữ confirmed trạng thái cũ; nếu chưa chạy
  lại hiển thị `Thông tin đã cập nhật; cần kiểm tra lại`. Không gọi save là approved.
- Upload bổ sung: filename/link/type thân thiện PDF/Ảnh/Bảng CSV/Văn bản, giới hạn
  file đúng backend; unsupported type có lời sửa được, không hứa image/* là mọi ảnh.
- Demo role/profiles: `Đang thử với vai trò` và `Nhân viên nộp đơn`; không persona,
  backend/clocks/read-only trong hint. Giữ các IDs/payload actor hiện tại, đổi vai
  không tự đổi nhân viên sở hữu hồ sơ. ID người thao tác legacy vào chi tiết demo.

## 4. Căn cứ, câu hỏi và lỗi

### 4.1 Căn cứ có tên tài liệu

`ReportPanel` nhận `sources?: SourceView[]` (default=[]), cùng report hiện có;
`QuestionsPanel` thêm sources optional, giữ sourceIds cho compatibility callers.
App đã có view.sources nên không thêm endpoint/storage chỉ để lấy filenames.

`EvidenceLinks` hiển thị tên file + trang nếu có locator đáng tin, link PDF với
`#page=N` khi page thực có; không hứa bbox/highlight từ field number. Khi không có
page/quote trong API thì chỉ `Xem tài liệu`, không đoán vị trí. Dedup cùng refs,
dedup link cùng source/page; mỗi field vẫn có bộ refs riêng ở details.

Form refs → `Thông tin nhân viên nhập (bản N)`; không giả là đã đọc từ giấy.
Chỉ mở field editor khi đúng revision hiện tại; revision cũ xem audit có sẵn hoặc
giữ label có số bản, không dựng snapshot bị mất. Company refs → `Dữ liệu kế toán
cung cấp` và snapshot section, giữ `Mô phỏng` khi synthetic; không link bank giả.
Unknown ref vẫn lưu diagnostics, hiện `Căn cứ chưa mở được`, không bỏ silently.

### 4.2 Câu hỏi

Headline `Việc cần làm rõ`; mỗi item: vấn đề, người xử lý, tài liệu liên quan,
phần ảnh hưởng, response và trạng thái:
OPEN→`Chờ phản hồi`, ANSWERED→`Đã nhận phản hồi, chờ kiểm tra lại`,
RESOLVED→`Đã giải quyết`, SUPERSEDED→`Không còn áp dụng cho bản hồ sơ này`.
ANSWERED không resolve; unknown không thay 0. Dùng filenames cho checkbox source.
Không giấu việc của kế toán/người duyệt với employee; nhóm `Bạn cần xử lý` và
`Người khác cần xử lý`, giữ khả năng xem toàn hồ sơ. Không đổi permission của
response API hoặc tự nhận quyền resolve chỉ vì đổi label/role picker.

### 4.3 Lỗi và thông báo

Hiện câu có hành động: unsupported file→`Định dạng chưa được hỗ trợ. Hãy dùng
PDF, JPG, PNG, CSV hoặc văn bản`; source too big→giới hạn backend20MiB; stale→
`Hồ sơ đã được cập nhật ở nơi khác. Tải lại trước khi tiếp tục` và nút reload.
Provider failure→`Chưa đọc được tài liệu này do lỗi dịch vụ`; giữ phần đã đọc,
refs và codes ở details; không gọi là nhân viên thiếu hóa đơn.
Permission→`Vai trò hiện tại không được thực hiện thao tác này`; giữ reason
nghiệp vụ/amount/scope trong phần mở chi tiết, không role label tự cấp authority.

B3 context absent→`Chưa có dữ liệu nhân viên và tuyến duyệt để thử luồng này.
Người cấu hình demo cần bổ sung dữ liệu`; SETTLEMENT_B3_CONTEXT_PATH trong details.
Một notice ngắn `Đọc bằng AI thật · Dữ liệu công ty mô phỏng` cho case hiện tại;
không warning alert dài ở mọi panel. Alert chỉ cho lỗi mới/chặn, status cho async.

## 5. Contracts kỹ thuật tối thiểu

Create `frontend/src/settlement/uiCopy.ts` (nhãn/format, không i18n framework)
và `uiState.ts` (presentation summary, không policy engine).

```ts
// uiCopy.ts; lookup fallback phải không vỡ với key mới.
export function formatMoney(value: number | null | undefined): string;
export function checkLabel(rule: string): string;
export function factLabel(key: string): string;
export function stageLabel(stage: CaseStage): string;
export function roleLabel(role: DemoRole): string;
export function errorText(code: string | null): string;
// uiState.ts: chỉ mô tả dữ liệu server và đích navigation trong UI.
export interface UiSummary {
  title: string; description: string;
  tone: 'neutral' | 'info' | 'warning' | 'error';
  missingFields: string[];
  primaryTarget: 'draft-editor' | 'issues' | 'run-check' | null;
}
export function summarizeCase(view: CaseView, run: RunView | null,
                              report: Report | null): UiSummary;
```

formatMoney null giữ Chưa xác định; int0 giữ0đ. Dictionary rule covers mọi B3
rule hiện có và B7 eligibility/payer_parts/history_coverage/budget/authority/
fact_quality/contradictions/relation_status/duplicate_events; unknown label
`Mục kiểm tra khác`, raw key trong details. Không replace substring arbitrary
trong dynamic backend text để biến một lý do thành lý do khác.

Summary ưu tiên stop/failure/superseded/running trước report; không lấy report
run khác/case khác làm current. B3 draft missing field names từ null/blank fields
trong report.b3.intake; show cả blocking checks/issues khi thiếu information.
PrimaryTarget là navigation đề xuất, không authorization; gọi action vẫn dùng
canStartRun/allowed_actions/role/version/Stop guards hiện có và backend.

`EvidenceLinks` create trong EvidenceLinks.tsx, props:
`{refs:string[], sources:SourceView[], diagnostics?:boolean}`. Native details giữ
raw refs; link exact source IDs và source-owned canonical locator, không branch
theo fixture names/IDs. Fallback không mất refs B7 legacy.

## Task 1 — Từ ngữ và trạng thái hiển thị

**Files:** Create uiCopy.ts/uiState.ts và tests cùng tên `.test.ts` trong
`frontend/src/settlement/`; Modify App.tsx/B3Intake.tsx/Report.tsx ở phần hiển thị.
**Consumes:** §2/§5 + CaseView/RunView/Report hiện hành.
**Produces:** helper contracts §5, report/dossier labels thống nhất.

- [ ] Viết failing tests cho null/zero, draft vs succeeded, failed/Stop/stale,
  ready chưa duyệt và check UNRESOLVED nhưng issues=[] (case user vừa gặp).

```ts
expect(formatMoney(null)).toBe('Chưa xác định');
expect(formatMoney(0)).toBe('0 đ');
expect(formatMoney(2_000_000)).toBe('2.000.000 đ');
// Fixtures lấy từ makeReport/mocked API của tests hiện có; thêm literal B3
// draft confirmed=false/destination=null/purpose=null trong file test này.
const summary = summarizeCase(view, run, report);
expect(summary.title).toBe('Kiểm tra bản nháp trước khi gửi');
expect(summary.missingFields).toEqual(['Nơi đến', 'Mục đích công tác']);
expect(summary.primaryTarget).toBe('draft-editor');
```

- [ ] Run red: `rtk proxy npm --prefix frontend run test -- --run src/settlement/uiCopy.test.ts src/settlement/uiState.test.ts`.
- [ ] Implement simple dictionaries/Intl.NumberFormat/null check; pure summary
  theo bảng §2.3. Đổi JSX labels; diagnostics dùng details, không đổi enums.
- [ ] Run green; giữ READ label là `Đọc được từ tài liệu`, form-origin là `Nhân
  viên khai báo`, không mọi KNOWN đều `Đã xác minh`. Source mode LIVE/synthetic riêng.

## Task 2 — Một editor và hành động dễ hiểu cho B3

**Files:** Modify App.tsx/B3Intake.tsx/styles.css; tests App.test.tsx/B3Intake.test.tsx.
**Consumes:** Task1 summary + handlers create/fill/revise/start hiện có.
**Produces:** hierarchy §3; POST/PATCH/run sequence giữ nguyên, editor không ghi đè user edits.

- [ ] Add failing tests IMPORT creation không render form rỗng, preview CTA focus
  editor, draft còn thiếu giữ inline hint; fill chỉ current editor, không new form.
  Polling không mất chỉnh sửa; switched case không dùng report case trước.

```tsx
const user = userEvent.setup();
render(<App />); // dùng API fixtures setup hiện hành trong App.test.tsx
await user.click(await screen.findByRole('button', {name:'Kiểm tra bản nháp'}));
expect(screen.getByLabelText('Nơi đến')).toHaveFocus();
// Sau điền đủ, confirm gọi reviseSubmission với confirmed=true, reason nonempty;
// startRun chỉ sau PATCH thành công; save draft không start/confirm.
```

- [ ] Run red focused App/B3Intake tests.
- [ ] Move editor trước technical/actions; caption/nút đúng §3. Reuse state và
  handler payload/version, bỏ side effect setB3Intake(filled) trong fill current
  dossier. First confirmation default operation reason; edited submission giữ
  user note. Không tự-fill missing facts bằng text mẫu/Hà Nội hardcode.
- [ ] Khi confirm thiếu fields, error summary liên kết tới input + focus, giữ
  dữ liệu người dùng. Native/IMPORT không tạo fake approval. Active case view
  và new intake phân biệt rõ, navigation không duplicate POST do double-click.
- [ ] Run green, assert API calls/actor/role/revision/reason bằng dữ liệu literal,
  không chỉ so chữ. Không tự run LIVE trong tests/browser.

## Task 3 — Report, căn cứ và câu hỏi cho kế toán

**Files:** Create EvidenceLinks.tsx/EvidenceLinks.test.tsx;
Modify Report.tsx/Questions.tsx/Actions.tsx và Report.test.tsx/Actions.test.tsx;
Create Questions.test.tsx; Modify App.tsx props sources. Backend copy-only nếu
cần trong `settlement/b3.py`/`rules.py`, tests b3_proposal/engine_quality tương ứng.
**Consumes:** Task1 maps/summary, §4, SourceView[] từ view hiện có.
**Produces:** EvidenceLinks contract §5, business check labels, owner/fact/response clarity.

- [ ] Test duplicate refs, B7 legacy F-ID, missing source metadata, form ref và
  old revision; evidence không bị mất dù không mở page. Mâu thuẫn/quality issues
  phải visible ở business summary ngay cả khi raw critical table đóng.

```tsx
render(<EvidenceLinks refs={['S-doc','S-doc-p1-field-1','S-doc',
  'S-doc-p1-field-1']} sources={[source]} />);
expect(screen.getAllByRole('link')).toHaveLength(1);
expect(screen.getByRole('link').getAttribute('href')).toContain('/api/sources/S-doc/content');
// source là SourceView literal id=S-doc/filename=de-nghi.pdf trong test fixture;
// không production branching theo chữ S-doc hoặc de-nghi.pdf.
```

- [ ] Run red focused EvidenceLinks/Report/Questions/Actions tests.
- [ ] Implement dedup known refs, filenames, optional real page; keep raw refs
  details. Pass sources through App. Questions source checkbox filenames + IDs
  ở details; status ANSWERED chưa RESOLVED. Error/provider/owner copy theo §4.
- [ ] B3 money panel hide không áp dụng, không B3_REPORT_ONLY trên mặt chính;
  note demo capability trung tính. B7 decision/review/money/Stop/handoff/closure
  nhãn VN, unknown/phần vượt/direction/receipt không bị đổi giá trị.
- [ ] Những CheckResult.reason/Issue.message backend còn actual/employee/refs/
  work/scope/exception đổi **string literals** sang tiếng Việt cụ thể; không
  đổi branching, amounts, IDs, statuses, owner, refs. Không thay dynamic evidence
  bằng generic PASS sentence. Lưu provider raw error trong diagnostics, không
  đổi status failure. Nếu cần schema mới cho locator/budget status thì ghi gap,
  không mở rộng API trong task UX này.
- [ ] Run green + focused pytest nếu backend strings đổi; test kết quả/owner/refs
  nguyên vẹn, cập nhật text assertions cần thiết, không gold money/labels.

## Task 4 — Lịch sử, kỹ thuật, Verify và nghiệm thu

**Files:** Modify App.tsx/Verify.tsx/styles.css + App.test.tsx/Verify.test.tsx;
append guide UX vào docs/testing/SETTLEMENT_MANUAL_TEST_GUIDE.md khi triển khai;
update plan execution evidence. Không thêm design system docs riêng.
**Consumes:** Task1–3 + audit/Verify API cũ. **Produces:** hierarchy role-based,
technical/Verify access, screenshots/checklist và actual-vs-expected evidence.

- [ ] Test technical details closed, Verify không auto-run/không nằm trong form
  nhân viên, nhưng mở được và giữ mode/holdout limitations. History event nhãn
  người+việc+thời gian, unknown event không mất entry. Source/money IDs vẫn truy được.

```tsx
const user = userEvent.setup();
render(<App />); // current fixtures; user mở details như normal disclosure
expect(screen.queryByRole('button',{name:/Chạy bộ kiểm tra/})).not.toBeInTheDocument();
await user.click(screen.getByText('Đánh giá hệ thống'));
expect(screen.getByRole('button',{name:/Chạy bộ kiểm tra/})).toBeVisible();
expect(api.runSettlementVerify).not.toHaveBeenCalled();
```

- [ ] Run red focused App/Verify tests, then implement native details/section.
  History mappings: CASE_CREATED→Tạo hồ sơ, SOURCE_ADDED→Thêm tài liệu,
  SUBMISSION_REVISED→Cập nhật thông tin, RUN_CREATED/RUN_SUCCEEDED→Bắt đầu/Hoàn
  thành kiểm tra, REVIEW_RECORDED→Kế toán lưu rà soát; unknown giữ Thao tác khác
  và raw kind trong details. Actual names chỉ khi mapping có, không đoán tên từ ID.
- [ ] Check keyboard/focus labels/error summary, role=status ít điểm thông báo,
  chỉ một CTA chính cho việc hiện tại; disabled có lý do. Long filenames/bảng
  4rows không tràn toàn trang ở375/768/1440px; 200% zoom readable. Contrast text
  đạt4.5:1 là target cần đo, không claim từ source. Không thêm animation/font/theme.
- [ ] Run focused rồi full frontend checks một lần:

```bash
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```

Nếu sửa backend copy:
`rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q`.
Không install deps chỉ để review/plan; execution thiếu environment báo rõ.

- [ ] Browser walkthrough matrix §6 nếu quyền cho phép. Nếu browser từ chối,
  không workaround; giao checklist user + ghi INCONCLUSIVE. Không gọi provider
  LIVE; dùng fake/read-only fixture đã có, record đúng mode. Ghi screenshots và
  failed/unexecuted cases trong `output/ui-language-review/`, không Git dữ liệu riêng.
- [ ] Update docs current-state sau implementation; review git diff/status, giữ
  existing changes. Handoff một prompt/checklist, không tự commit.

## 6. Acceptance và đánh giá khả năng hiểu

| ID | Kịch bản | Tiêu chí |
| --- | --- | --- |
| A01 | User run succeeded+draft+2fields thiếu | Headline chờ kiểm tra bản nháp, chỉ ra Nơi đến/Mục đích, CTA tới editor; không Thành công=đã duyệt |
| A02 | First confirmation không chỉnh | Không bắt lý do sửa; confirmed + audit reason + correct version, run sau PATCH |
| A03 | User sửa amount trước polling/refill | Không mất edit, không copy sang create form hoặc silent confirm |
| A04 | Technical failure có partial results | Lỗi dịch vụ visible; phần rõ giữ, retry đúng allowed action; không missing invoice giả |
| A05 | Same source refs lặp4 lần | Một link thân thiện/source-page trong field, raw refs vẫn accessible |
| A06 | Field unknown/zero/contradicted | Chưa xác định/0đ/Thông tin khác nhau phân biệt; không hidden warning |
| A07 | B3 ready + grants/synthetic | Đủ để kế toán rà soát, chưa duyệt/chi; LIVE và dữ liệu mô phỏng đều visible |
| A08 | B7 net−700000/0/unknown | Chiều thu đúng,0 không tự đóng,unknown không suy payable0; formula có thể xem details |
| A09 | Question OPEN→ANSWERED→RESOLVED | Người xử lý và next action rõ; trả lời chưa là giải quyết; refs đúng filename |
| A10 | Stop/stale/role không đủ | Không action tự cấp quyền; thông báo tải lại/đổi vai/demo rõ, Stop không hứa bank cancel |
| A11 | Employee opening workspace | Không enum/trace/tokens/clocks/Verify lấn át; technical vẫn mở được khi cần |
| A12 | Verify area | Button chỉ chạy khi bấm, metrics/limits không biến thành quảng cáo accuracy |
| A13 | Keyboard/375px/zoom200% | Tới CTA/fields/evidence, focus visible, không phải cuộn ngang cả trang để đọc |
| A14 | Backend says ready nhưng check còn unresolved | Cảnh báo rõ, không UI sửa state/ẩn lỗi để hợp thức readiness |

Walkthrough: employee mới tìm cách nộp; import preview xác định2trường thiếu,
mở đúng giấy và xác nhận; accountant tìm issue/căn cứ/ghi review; approver biết
đang xem report hay có decision action thực; kỹ thuật viên mở diagnostics/Verify.

Kiểm khả năng hiểu bằng câu hỏi: `Hồ sơ đã nộp chưa?`, `Đã duyệt/nhận tiền chưa?`,
`Ai cần làm gì tiếp?`, `Mở tài liệu nào để kiểm số này?`. Ghi câu trả lời, nhầm lẫn,
số lần phải giải thích và thời gian tìm hành động. Chủ dự án self-test không thay
professional participants; RTL green/source review không prove dễ dùng cho kế toán.
Không đặt một tỷ lệ “UX đạt” nếu chưa có người thử thật.

## 7. Prompt bàn giao agent coding

```text
Review AGENTS.md và triển khai docs/superpowers/plans/2026-10-10-ui-language-and-workflow.md
theo Task1→4. Đọc Product P6 và System S2/S3/S6; không load archive/tất cả markdown.
Chỉ sửa UX/copy/layout, giữ API/policy/money/authority/closure guards. B3 chưa có
approval/payment lifecycle; không tạo nút giả. Giữ dirty App/App.test/styles hiện tại.
Vietnamese business wording, một editor cho current draft, CTA rõ, evidence filename,
technical diagnostics và Verify tách khỏi màn nhân viên nhưng vẫn truy cập được.
Không chữa evaluator bằng cách giấu document.role conflict/UNRESOLVED/quality issues.
Test fake + API payload assertions + frontend build; browser chỉ khi được phép,
không workaround khi bị từ chối; không gọi LIVE hoặc commit/push.
Bàn giao diff, commands/outcomes, screenshot/checklist, các mục chưa verify và
copy exact steps để chủ dự án thử trên UI.
```

## 8. Evidence / self-review của người viết

- VERIFIED: source strings/handlers/props và report user cung cấp; không runtime UI mới.
- PLANNED: toàn bộ tasks/copy/hierarchy. Không file application nào được sửa trong lượt soạn plan.
- INCONCLUSIVE: browser visual/focus/contrast/responsive do access bị từ chối.
- Skill UX search local `plain language status next action`: matched Submit Feedback
  và Contextual Live Badge Updates cho async feedback; không dùng output như audit chuẩn.
- Known logic findings giữ riêng; UI không đủ sửa extraction/role scope/relation correctness.
- Self-review: §2–§5 có tasks1–4; guards/refs/mode giữ; không schema/new deps hoặc fake features.
- Kiểm tra plan: links/fences/target files PASS; hashes ba file user đang sửa
  giữ nguyên. `git diff --check` toàn working tree báo blank line EOF sẵn có ở
  App.test.tsx:250 và styles.css:1911; không sửa các dòng này trong review/plan.
  Không chạy tests/build vì lượt này chỉ viết tài liệu, không claim UI đã pass.

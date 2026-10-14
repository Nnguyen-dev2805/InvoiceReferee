# Review độc lập — 09 Data Tooling

Nguồn review: worktree Hoangha tại commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Phạm vi owner `09-data-tooling` trong `inventory.json`: **6 file / 3.407 dòng**:

- `docs/new/assets/employee_workflow.html` — 93 dòng
- `docs/new/assets/system_workflow.html` — 103 dòng
- `scripts/generate_uc3_testcases.py` — 1.981 dòng
- `scripts/qa_uc3_testcases.py` — 184 dòng
- `scripts/restructure_mistral_ocr.py` — 55 dòng
- `tools/generate_uc3_testcases_v2.py` — 991 dòng

Con số theo `inventory.json` là 3.407, lệch 20 dòng so với con số 3.427 được nêu trong giao việc; sáu path owner được enumerated đầy đủ và toàn bộ sáu file đã được đọc. Review không chạy generator, QA, renderer, test/build hay LIVE.

Parent đã kiểm kê độc lập 75 `expected.json`/manifest trong `10-data-catalog.md`: **25 case v1 + 50 case v2, 173 PDF được gold tham chiếu, 0 missing path, 173 digest khác nhau / 0 byte-duplicate**. Tôi dùng kết quả đó làm structural evidence; không ghi đè `10-data-catalog.md` hoặc `data-catalog.json`.

CodeGraph được dùng trước cho bốn file Python để xác định symbol/caller/callee. Hai HTML và các phần generator bị graph trim được đọc trực tiếp. `check_index_coverage`/generation-id không exposed nên graph coverage vẫn **UNKNOWN**.

## Kết luận

Bộ tooling này có giá trị cao như **synthetic regression fixture generator** và tài liệu demo. Nó không phải independent benchmark:

1. PDF/DOCX và `expected.json` được sinh từ **cùng một Case object** ở cả v1 và v2.
2. Vì vậy gold rất phù hợp để test deterministic business scenarios/schema, nhưng không độc lập với dữ liệu được render.
3. Nhãn `COVERED` chỉ là metadata do generator tác giả gán; review này không có execution evidence để nói các case đó pass.
4. Tooling hiện phụ thuộc Windows fonts và dependency ngoài `pyproject.toml`; regeneration không portable nguyên trạng.
5. QA script có một destructive-path hazard rõ ràng và chỉ được viết cho corpus v1.

## Từng file

| File | Dòng | Vai trò | Input → Output | Hàm chính / caller / callee | Hành vi lỗi | Khả năng dùng lại |
| --- | ---: | --- | --- | --- | --- | --- |
| `docs/new/assets/employee_workflow.html` | 93 | Sơ đồ tĩnh luồng nhân viên | HTML/CSS → diagram trong browser | không có runtime caller | browser/render lỗi ngoài source; không validate flow | **Docs only**; cập nhật terminology final trước khi dùng |
| `docs/new/assets/system_workflow.html` | 103 | Sơ đồ tĩnh luồng xử lý | HTML/CSS → architecture/workflow diagram | không có runtime caller | không có executable validation | **Docs only**; hiện phản ánh semantics Hoangha/legacy |
| `scripts/generate_uc3_testcases.py` | 1.981 | Generator corpus UC-03 v1 | hard-coded synthetic case definitions → DOCX/PDF/expected/manifest/README | `build_cases`, `build_multi_document_cases`, renderers, `expected_payload`, `main` | output tồn tại → stop trừ `--force`; `--force` xóa output; font/file/dependency errors propagate | **Có cho regression**, không dùng gold như independent oracle |
| `scripts/qa_uc3_testcases.py` | 184 | Structural + render/contact-sheet QA cho v1 | corpus v1 → PNG renders/contact sheets + `qa_summary.json` | `main`, `contact_sheets`; dùng Aspose/PyMuPDF/Pillow | lỗi manifest/file/render gom vào errors rồi exit 1; output cũ bị xóa vô điều kiện | **Một phần**; cần safety + v2 support + portable font |
| `scripts/restructure_mistral_ocr.py` | 55 | CLI wrapper cho mapper OCR | Mistral JSON → `.hierarchical.json` | `main` → `invoice_referee.extraction.restructure_mistral_ocr` | JSON/path/mapper/write errors propagate; success in counts | **Có**, wrapper mỏng |
| `tools/generate_uc3_testcases_v2.py` | 991 | Generator corpus v2, 5 nhóm x 10 case | hard-coded synthetic cases → DOCX/PDF/expected/manifest/README | `build_cases`, `expected_payload`, `generate`, DOCX/PDF renderers | catalog count sai → RuntimeError; output tồn tại → stop trừ `--replace`; font Windows thiếu → RuntimeError | **Có cho regression**, cần portability/safety cleanup |

<!-- reviewed-file: docs/new/assets/employee_workflow.html -->
<!-- reviewed-file: docs/new/assets/system_workflow.html -->
<!-- reviewed-file: scripts/generate_uc3_testcases.py -->
<!-- reviewed-file: scripts/qa_uc3_testcases.py -->
<!-- reviewed-file: scripts/restructure_mistral_ocr.py -->
<!-- reviewed-file: tools/generate_uc3_testcases_v2.py -->

## 1. Data source definitions và 25 + 50 case

### v1 — 25 case

`scripts/generate_uc3_testcases.py` định nghĩa toàn bộ dữ liệu synthetic trong code: company/employee/vendor profiles nằm ngay đầu file (`39-50+`). `build_cases()` bắt đầu ở `1207` và tạo 15 case single-document; `build_multi_document_cases()` bắt đầu ở `1482` và tạo 10 case multi-document, tổng **25**.

Multi-document case mang report lines, evidence documents và `line_expectations`; ví dụ TC16 khai ba report lines và ba hóa đơn, mapping một-một (`1485-1507`). Đây là fixture hữu ích để test evidence matching.

README do generator tự viết nói rõ toàn bộ tài liệu là dữ liệu giả lập, không có giá trị pháp lý/kế toán; `expected.json` là oracle test và không được upload vào hệ thống (`1854-1895`).

### v2 — 50 case

`tools/generate_uc3_testcases_v2.py` cũng khai báo synthetic fixture ngay trong code (`1-5`). `generate()` enforce **đúng 50 case** và **5 group, mỗi group 10 case**; sai count thì raise `RuntimeError` (`929-937`).

Generator v2 dùng `Case` với default:

- `expected_decision="READY_FOR_APPROVAL"`
- `implementation_status="COVERED"`

ở `75-94`; helper `case()` lặp lại default `COVERED` ở `195-235`.

Static manifest hiện có:

- v1: **10 COVERED + 15 GAP_EXPECTED**
- v2: **43 COVERED + 7 PLANNED**

Đây là label tác giả đã ghi vào fixture. Không có execution trong review này.

### Quan hệ với catalog parent

Structural inventory parent xác nhận 75 case tham chiếu tổng cộng **173 PDF**, không missing và không digest trùng. Điều đó chứng minh corpus checked-in có cấu trúc đầy đủ theo manifest/gold; nó **không chứng minh** OCR đọc đúng, rule engine pass hay visual rendering đẹp.

## 2. Gold có độc lập không?

### Kết luận: không độc lập

**Source-verified.**

Ở v1:

- business facts/expected được lấy từ `TestCase/MultiDocumentCase` trong `expected_payload()` và `expected_multi_payload()` (`1751-1851`);
- ngay trong generation loop, cùng `case` được truyền vào DOCX/PDF renderers rồi `expected_payload(case)` được ghi thành `expected.json` (`1917-1970`).

Ở v2:

- `expected_payload(case_spec)` lấy submission, employee, expected decision/rule/status, totals và line facts trực tiếp từ cùng `Case` (`839-879`);
- cùng `case_spec` được dùng để render `request_form`, evidence PDFs/DOCX và ngay sau đó viết `expected.json` (`948-970`).

Do đó một lỗi trong **case definition** có thể đi vào cả rendered document lẫn expected và vẫn tự nhất quán. Đây là coupling theo thiết kế, không phải lỗi dữ liệu.

### Dùng đúng cách

Corpus phù hợp cho:

- regression của schema/rule/matching đã định nghĩa;
- demo deterministic;
- smoke test OCR/extraction trên tài liệu synthetic;
- test “runtime không được đọc expected”.

Corpus **không đủ một mình** để chứng minh:

- model generalize trên tài liệu thật/OOD;
- OCR accuracy;
- policy correctness độc lập với tác giả generator;
- visual quality;
- system pass 75 case.

Final nên giữ `expected.json` ngoài runtime/model input và dùng một independent evaluator/oracle mapping ở eval layer, đúng contract đã chốt.

## 3. Gold có khớp rendered source không?

### Logic generator: có độ gắn kết cao theo construction

**Source-verified mechanism, không phải visual/execution proof.**

Ví dụ v2:

- `Case.lines/evidence` là nguồn cho report/evidence renderers;
- `expected_payload` đọc lại đúng `Case.lines`, `report_total`, `advance_amount`, decision/rule (`839-879`);
- generation loop render rồi ghi expected từ cùng object (`948-970`).

v1 tương tự ở `1917-1970`.

Điều này làm giảm nguy cơ “gold nhập tay lệch fixture”, nhưng không loại bỏ:

- bug formatter làm PDF hiển thị khác object;
- font/render lỗi;
- line wrap/truncation;
- checked-in PDF bị sửa sau khi generate;
- OCR đọc sai text dù PDF visually đúng.

Parent đã kiểm tra file existence/digest, chưa visual/OCR. Review này cũng không render, nên **không claim visual QA**.

### Schema v1/v2 khác nhau

v1 `expected.json` dùng:

- `schema_version="1.0"`
- `submission.request_document/evidence_documents`
- `expected.primary_rule`
- single/multi payload có shape khác nhau ở một số phần.

v2 dùng:

- `schema_version="2.0"`
- `submission.request_form/evidence_files`
- `expected.primary_rule_id`
- `expected.implementation_status`
- `line_support_expectations` hiện chứa item/description/amount/reference/note nhưng không trực tiếp chứa evidence filename mapping (`839-879`).

Vì vậy final cần **corpus adapter** trước evaluator; không nên coi 75 expected là một schema đồng nhất.

## 4. `COVERED` không phải actual execution

`root_readme()` của v2 tự mô tả: “`COVERED` là rule đã có trong Rule Engine; `PLANNED` là regression specification…” (`898-926`). Manifest cũng ghi trực tiếp `case_spec.implementation_status` (`962-970`).

Nhưng:

- `implementation_status` default đã là `COVERED` (`92,212`);
- generator không gọi Rule Engine;
- manifest không lưu test result/pass/fail/run timestamp/provider mode;
- review này bị cấm chạy generator/QA/test/LIVE.

Do đó phát biểu hợp lệ là:

> “43 case v2 **được fixture gắn nhãn** COVERED.”

Không hợp lệ là:

> “43 case v2 đã chạy qua hệ thống và pass.”

Tương tự với 10 v1 `COVERED`.

## 5. QA script thực sự kiểm tra gì?

`scripts/qa_uc3_testcases.py`:

1. resolve `--root` và `--output` (`46-52`);
2. đọc manifest, yêu cầu **25** case (`63-77`);
3. đọc mọi `expected.json`, kiểm synthetic marker, referenced PDF/DOCX tồn tại; với schema v2 có thêm một số line-support consistency checks (`79-116`);
4. so expected document count với số PDF/DOCX (`118-125`);
5. mở DOCX bằng Aspose, yêu cầu 1 page, tìm visible fixture markers, render PNG (`127-142`);
6. mở PDF bằng PyMuPDF, yêu cầu 1 page, tìm marker, render first page PNG (`144-160`);
7. tạo contact sheets và `qa_summary.json`; có errors thì exit 1 (`162-180`).

### Nó chưa chứng minh visual correctness

Script tạo PNG/contact sheet nhưng **không tự chấm** overlap, clipping, font quality, alignment hay tính dễ đọc. Contact sheet phải được con người/visual evaluator nhìn. Vì review này không chạy QA/render, không có visual verdict.

### Nó thực chất là QA v1

Default root là `data/testcase_uc3` và manifest bắt buộc length 25 (`48,72-77`). Manifest v2 là object chứa `schema_version/case_count/groups/cases` (`tools/generate_uc3_testcases_v2.py:975-977`), nên đưa v2 trực tiếp vào script sẽ không thỏa contract manifest 25-case.

Phần `if schema_version == "2.0"` trong expected reader không biến script thành full v2 QA; manifest contract vẫn v1.

## 6. Portability, dependency và path safety

### F09-01 — MUST FIX: QA xóa arbitrary output path không cần confirmation

**Source-verified.**

`--output` là path caller truyền; script gọi `.resolve()`, và nếu tồn tại thì chạy `shutil.rmtree(output)` vô điều kiện (`qa_uc3_testcases.py:46-58`).

**Trigger:** người dùng nhầm `--output` sang một thư mục quan trọng đã tồn tại.

**Wrong behavior:** toàn bộ directory tree đó bị xóa trước khi QA chạy.

**Khuyến nghị integration:** thêm guard giống generator (`--force/--replace`), từ chối root/project/home, và/hoặc require output nằm dưới dedicated QA root. Không chạy script này trong runbook final nguyên trạng.

### F09-02 — MUST FIX cho portability: hard-coded Windows fonts

**Source-verified.**

- v1: `FONT_DIR = Path(r"C:\Windows\Fonts")` (`generate_uc3_testcases.py:50`), đăng ký `times.ttf/timesbd.ttf/timesi.ttf` ở `680-683`.
- v2: `setup_pdf_fonts()` bắt buộc `C:/Windows/Fonts/arial.ttf`; nếu không tồn tại thì raise `RuntimeError` (`576-583`).
- QA contact sheet dùng `ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 18)` (`qa_uc3_testcases.py:24-27`).

Trên macOS/Linux, regeneration/QA không portable nếu không có adapter font path/bundled permissible font.

Không nên commit/share font proprietary chỉ để sửa path; nên cho phép configured/system fallback hoặc dùng font redistributable theo license phù hợp.

### F09-03 — MUST FIX runbook: dependency spec chưa self-contained

**Source-verified.**

Hai generator import `python-docx` và ReportLab (`scripts/generate_uc3_testcases.py:15-35`; `tools/generate_uc3_testcases_v2.py:18-29`). QA import `aspose.words`, PyMuPDF, Pillow (`qa_uc3_testcases.py:10-12`).

`pyproject.toml:10-22` có PyMuPDF/Pillow nhưng **không khai báo python-docx, reportlab, aspose.words**. Vì vậy một clean install theo package metadata không đủ để bảo đảm generator/QA chạy.

Có thể máy tác giả đã cài riêng; review không kiểm môi trường và không claim dependency hiện thiếu ở máy cụ thể. Vấn đề là **runbook/package contract không portable/reproducible**.

### F09-04 — SHOULD FIX: generator delete có flag nhưng target vẫn arbitrary

**Source-verified.**

- v1: `--force`; output tồn tại mà không flag thì stop, có flag thì `shutil.rmtree(root)` (`1898-1913`).
- v2: `--replace`; tương tự ở `929-944`, CLI resolve arbitrary `--output` ở `981-986`.

Hai generator an toàn hơn QA vì có explicit destructive flag. Tuy nhiên typo path + flag vẫn xóa directory tùy ý. Runbook final nên pin output dưới known fixture root và reject dangerous paths.

### F09-05 — SHOULD FIX trước demo/bài nộp: tên synthetic “Donal Trump”

**Source-verified.**

v2 hard-code `EMPLOYEE_NAME = "Donal Trump"` (`32-38`) và render tên này vào request/bank text. Dù payload ghi `data_classification="SYNTHETIC"` (`839-853`), tên gợi một cá nhân nổi tiếng làm demo kém chuyên nghiệp và có thể gây nhầm về dữ liệu thật/consent. Nên thay bằng tên giả trung tính khi regenerate corpus; không sửa corpus trong review này.

## 7. Hai HTML diagram assets

### `employee_workflow.html`

Sơ đồ mô tả ba nhánh: đối chiếu nhận hàng, yêu cầu tạm ứng, hoàn ứng/hoàn trả; sau đó “kiểm tra dữ liệu tối thiểu” và tạo `ExpenseCase` (`33-90`). Nó hữu ích để giải thích intake multi-document, nhưng `ExpenseCase`/ba nhánh là terminology thiết kế Hoangha, cần map sang domain final trước khi dùng trong tài liệu chính thức.

### `system_workflow.html`

Sơ đồ mô tả OCR → Confidence Gate → LLM extraction → policy flows → Decision Guard; line 100 ghi ranh giới “LLM trích xuất/đề xuất; Python tính/rule; con người phê duyệt”. Đây là nguyên tắc tốt.

Tuy nhiên sơ đồ vẫn đặt output `PASS / READY_FOR_APPROVAL / REQUEST_INFO / ESCALATE` sau Decision Guard (`91-100`). Với final, evidence/OCR stage hiện chưa được phép tự tạo finance approval; do đó asset này là **historical architecture documentation**, không phải proof runtime final.

Hai file HTML không có test/validation và không được render trong review.

## 8. CLI restructure OCR

`scripts/restructure_mistral_ocr.py` chỉ là wrapper:

- đưa `src` vào `sys.path` (`10-15`);
- parse input JSON và optional output (`22-36`);
- gọi `invoice_referee.extraction.restructure_mistral_ocr(payload, source_file=...)` (`37-38`);
- tạo parent dir, ghi JSON pretty (`40-44`);
- in count pages/blocks/warnings và return 0 (`46-51`).

Nó không có OCR algorithm riêng. JSON/path/mapping/write failure không bị nuốt, nên CLI fail rõ. Có thể giữ làm debug/migration utility nếu final vẫn dùng mapper tương ứng.

## 9. Tests / actual execution

Trong owner 09 không có executable evidence rằng 75 case đã pass final runtime. Generator source tự định nghĩa fixtures; QA là utility và chưa chạy trong review.

Parent structural catalog chứng minh:

- 75 expected parse được;
- 173 referenced PDF tồn tại;
- không byte-duplicate.

Nó chưa chứng minh:

- generator có thể reproduce corpus trên máy hiện tại;
- QA pass;
- DOCX/PDF không clipping;
- OCR đọc đúng;
- `COVERED` cases pass;
- final evaluator mapping đúng label;
- 3 routine + 2 escalation theo yêu cầu đề A đã đạt runtime gate.

## 10. Nên mang gì sang final

### Mang

1. **75-case corpus checked-in** làm regression/evidence smoke corpus, version namespace rõ `v1/v2`.
2. Case taxonomy/multi-document scenarios, đặc biệt matching, missing evidence, duplicate, policy exception.
3. Generator definitions như provenance cho fixture; nếu cần regenerate thì làm portable trước.
4. `restructure_mistral_ocr.py` như utility mỏng nếu mapper được giữ.
5. Nguyên tắc diagram: model extraction/semantic suggestion, code calculation/rules, human approval.

### Cần adapter

1. **Gold schema adapter:** v1/v2 → eval schema final; map action label theo contract final, không tự đổi policy.
2. **Runtime isolation:** chỉ PDF/request/evidence đi vào app/model; `expected.json` nằm ngoài runtime prompt/context.
3. **Path safety adapter/runbook:** fixed output roots + destructive confirmation.
4. **Font/dependency portability:** configurable/bundled redistributable fonts và explicit tooling dependencies.
5. **Evaluation layer:** `implementation_status` chỉ metadata; actual pass/fail phải đến từ một run record có version/provider/evidence.

## Findings ưu tiên

| Mức | Finding | Trạng thái bằng chứng |
| --- | --- | --- |
| MUST | QA `--output` có thể bị xóa vô điều kiện | **Source-verified** |
| MUST | Windows font paths làm generator/QA không portable | **Source-verified** |
| MUST | Tooling dependencies không đầy đủ trong `pyproject.toml` | **Source-verified** |
| MUST | Không coi `COVERED` là actual execution/pass | **Source-verified metadata; execution NOT_RUN** |
| MUST | Không coi generated gold là independent oracle | **Source-verified coupling** |
| SHOULD | Generator destructive flag vẫn cho arbitrary output target | **Source-verified** |
| SHOULD | QA contract chỉ phù hợp v1 25-case | **Source-verified** |
| SHOULD | Đổi synthetic employee name “Donal Trump” trước demo/regeneration | **Source-verified** |
| WATCH | Rendered source có thể lệch object do renderer/manual edits | **Giả thuyết chưa visual-test** |

Giới hạn cuối: **generators NOT_RUN, QA NOT_RUN, render NOT_RUN, LIVE NOT_RUN**. Vì vậy báo cáo đánh giá logic bộ sinh, schema, coupling, safety và portability; không đưa ra visual-quality verdict hay runtime pass-rate.

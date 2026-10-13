# Review implementation plan — 13/10/2026

## Bản bàn giao sau disposition

Plan SHA256 `bddb7c448c5689cf8e1298e2c29528114f9f2355dbbc2f349514f89f645f3a00`;
contracts SHA256 `d63facb18a8c7ebc9dc7400ba1d83cb98b5bbfcf023bcd8adbadfbe255ca3e76`.
Lead đã sửa hai điều kiện Galileo còn yêu cầu; chưa gán verdict độc lập READY
cho snapshot cuối nếu reviewer chưa đọc lại. Nietzsche READY ở snapshot bản sửa
trước precision gates. Kiểm tài liệu cuối: 8 files/171 file links/10 Python test
examples parse/13 tasks PASS; không unit/UI/LIVE application tests.

Scope: tài liệu cho bản xây mới trên `final`. Không review code cũ, chạy app/model,
thử nghiệm người dùng hoặc chứng nhận bài thi đã đạt. Báo cáo độc lập giữ nguyên;
lead quyết định disposition bằng counterexample và requirement, không đếm phiếu.

## Snapshot đã giao

| Target | SHA256 |
| --- | --- |
| `docs/superpowers/plans/2026-10-13-invoice-referee-final.md` | `5656076bbe90c5ef138ef2672b82a3576b4f960d2468ade6744f143865f59637` |
| `docs/final/IMPLEMENTATION_CONTRACTS.md` | `b459b1a99df2a019527da5cfc75b58c5f4a386f5c5ec33bf5451e11ac44a0893` |

Nguồn: [brief gốc](../../../Challenge_Brief_OrganizationAI_VN.docx.md),
[thiết kế/Q31](../../ARCHITECTURE_AND_EVALUATION.md),
[disposition thiết kế](../2026-10-13/SYNTHESIS.md).

Galileo — GPT 6 Web High, context riêng: kiến trúc/contracts/T1–T8.
Nietzsche — GPT 6 Web High, context riêng: đề thi/evaluation/feedback/T4–T13.
Không giới hạn số từ hoặc findings. Chỉ được ghi report của mình, không sửa plan.

Reports đầy đủ: [architecture](architecture.md), [evaluation](evaluation.md),
[architecture response](architecture-response.md), [evaluation response](evaluation-response.md).
[Disposition/counterarguments của lead](SYNTHESIS.md) ghi từng finding, sửa cuối
và ranh giới verdict. Hash trên là snapshot review đầu, không hash bản plan sau sửa.

Graph query parent chỉ trả “This project has nothing indexed”; không có tool
index_status/check_index_coverage. Generation/coverage unknown; raw reads tài liệu
non-code được dùng. Không có kết luận negative về source/call-chain code.

## Tự review của lead trước dispatch

- Đọc spec/brief với contract/plan: 13 task đi từ strict domain tới UI/LIVE,
  actual money/control, Verify, adaptation, trials và handoff.
- Sửa `allowed_effect`, Fact types của Projection, fulfillment fields của Instruction,
  CaseView.id; không để agent sau tự đặt tên khác.
- Tách RecordMoneyInput khỏi MoneyEvent: client không tự đặt verified/verifier.
- Bỏ tối ưu A+P chưa có consumer; chưa biết loại tiền vẫn FACT, không giả số 0.
- Recovery gắn material basis/field/source, không reset bởi preview/submit/Resume.
- T3 chỉ kiểm component view với fixture, không thêm endpoint production giả pipeline.
- Chuẩn bị người dùng từ T2, pilot T10 trước adaptation; LangSmith là adapter phụ.
- Kiểm links/fences/whitespace/header/13 tasks bằng script: PASS. Đây là kiểm
  tài liệu; chưa chạy unit/UI/LIVE, không tuyên bố kỹ thuật/runtime đã đạt.

## Requirement → task → bằng chứng phải có

| Requirement | Task | Acceptance cần quan sát khi thực hiện |
| --- | --- | --- |
| Routine tự hoàn tất, không hỏi kế toán mọi hồ sơ | T3/T6/T7 | Raw nguồn đủ → một instruction đúng; thực hiện tiền khác quyết định eligibility |
| Nguồn nghi vấn không kết luận khẳng định | T3/T5/T9 | Unknown/conflict không false-known; thiếu coverage không S0; scorer bắt cả unsafe conclusion |
| ≥15 hồ sơ; FACT/POLICY/AUTHORITY | T4/T6/T9 | Raw/gold độc lập và route/owner/questions, không chỉ inventory |
| Câu hỏi trả lời trực tiếp từ card | T6/T9/T12 | Known facts/excerpt/impact/required answer; practitioner thử card-only |
| Core4 tuần tự một thao tác | T9/T10 | Actual pipeline/DB bảng expected/actual/mode/time, ít nhất một reject/escalation |
| Escalation5: 3 auto/2 human, 90 giây | T5/T9/T10 | M0 và hosting measured elapsed, không latency fixture; input mới cùng đường app |
| Stop/Override/audit | T8/T10 | Barrier/crash tests và UI; late worker không commit; lịch sử actor/basis/reason còn nguyên |
| Adaptive feedback | T10/T11 | Verified attribution + paired initial snapshots + support/flip/gain/validation/version/rollback |
| Tập độc lập và miss/chuyển thừa | T4/T9/T12 | Held-out roots/families, counts/denominators, giữ lỗi technical và raw/assisted riêng |
| ≥3 professionals/cải tiến/bất cập | T2/T10/T12 | Consent/phản hồi văn bản thật, matched tasks/effort/negative effect, change có version |
| Public URL/no signup/clone sạch | T2/T10 | Browser sạch/session isolation/runbook/locked installs, không dùng private local config |
| Sáu hạng mục nộp/history/thời hạn | T10/T13 | Live URL, Verify, repo history, đúng 5 slides/video≤3 phút/log1 trang; external eligibility xác nhận |

## Ý kiến độc lập ban đầu của lead

Tôi giữ explicit Python workflow và SQLite cho pilot, vì bất biến tài chính cần
transaction/recheck có thể kiểm trực tiếp; thêm framework graph không tự chứng minh
agent hoặc giảm unsafe actions. Agent phải thể hiện lựa chọn bước đọc/đối chiếu/
hỏi trong trace thực, không gọi LLM để quyết định phép tính hay quyền.

Điểm giá trị nhất của hệ thống là quyết định có căn cứ và điểm dừng đúng người,
không phải thêm workflow xin ứng. Hai rủi ro lớn nhất của plan là nâng OCR/JSON thành
fact và gọi một heuristic thay đổi threshold là “học” khi chưa có counterfactual/
feedback hợp lệ. Tasks đã nêu tests/gates, nhưng reviewers cần kiểm xem chúng đủ
cụ thể cho implementer chưa. Tôi không nhận runtime evidence là prerequisite để
viết plan; tôi cũng không coi plan là bằng chứng đã hoàn thành requirements.

Ngày brief khóa 15/10 gần; không thể từ tốc độ coding suy ra kịp practitioner
trials/LIVE holdout. Chưa có người/hạ tầng/model measured thì công bố thiếu bằng
chứng. Không tự giảm scope đã chốt hoặc hứa vô địch bằng kiến trúc tài liệu.

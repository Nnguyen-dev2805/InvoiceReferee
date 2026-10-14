# TC01 — LIVE khi không có bản ghi ứng thực nhận

Ngày14/10/2026. **PASS gate an toàn đã kiểm: A/S UNKNOWN, WAITING, không instruction, câu hỏi tới kế toán.** Không phải hoàn tất workflow ghi nhận ứng hoặc thực hiện thu.

## Danh tính và dữ liệu test

- HEAD `0b205420bfd3b4ce41e8739a1a701798a805bca1` cộng working-tree backend của agent tại thời điểm snapshot. Bytes package được lưu nguyên trong `.runtime/tc01-no-advance-20261014-154945/snapshot/src`; `identity.json` ghi hash từng file. Không sửa snapshot logic.
- Case gốc `data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua/`, giữ nguyên2PDF. Source hashes trong report khớp lượt TC01 trước.
- LIVE Mistral OCR + X-Kiro configured `qwen/qwen3.7-flash:free`.
- Context tài chính SIMULATED, clock harness `2026-10-10T18:00:00+07:00`.
- Giữ đúng claimant/company/activity WORK_EXPENSE, B8m, grants system8m/4m, category policy và coverage đến10Oct; **ledger=[]** và không gọi RecordActual.
- Không lấy expected/gold vào app/model. Expected safety được viết trước run trong expectation.json.
- DB test mới riêng, không reset/write user DB; không sửa app code, không commit/push/subagent. Browser của case này NOT_RUN.
- CodeGraph được kiểm trạng thái trước khám phá; coverage tool không expose, coverage UNKNOWN. Source của gate declared advance/coverage đã đọc, không tuyên bố audit toàn codebase.

## Kết quả quan sát

Thời gian64.353giây; job và assertions exit0.

| Mục | Kết quả |
|---|---|
| State | WAITING |
| T | KNOWN3.240.000 |
| E | KNOWN3.240.000 theo invoice demo basis |
| A | UNKNOWN/null |
| P/R | UNKNOWN/null trong projection hiện tại |
| S | UNKNOWN/null |
| Instructions | [] |
| FACT budget/payer | Không phát sinh |

Hai câu hỏi thật, đều owner accountant:

1. `ledger:advance`: giấy khai4m nhưng không có bản ghi ứng; xác minh/ghi nhận đúng scope trước đối soát.
2. `ledger:coverage`: xác minh lịch sử ứng/hoàn đủ scope/thời gian/loại dòng tiền.

Gate `_declared_advance` nhận kê khai4m, ledger không có ứng; admission loại coverage
khỏi cơ sở kết luận zero thay vì coi A=0. Vì vậy dù context fixture có một coverage
object, mâu thuẫn với ứng kê khai vẫn ngăn effect. T/E có thể được giữ từ invoice
nhưng thiếu A nên S chưa xác định. Hệ thống không PAY3.24m từ zero giả, cũng không
COLLECT760k từ số ứng in trên giấy.

Basis text hiện dùng "bản ghi ứng thực nhận mới là0đ". Đây là tổng recorded events
trong fixture, không phải kết luận A thật bằng0; projection đúng vẫn UNKNOWN.
Khi tinh chỉnh copy, nên nói "chưa có bản ghi ứng thực nhận" cho trường hợp này.
Hai issue cùng kế toán có thể trình bày thành một công việc với các căn cứ cần
xác minh, nhưng không được mất kiểm history/P/R.

## Gate và giới hạn

`checks.json`:6/6true — WAITING, AUNKNOWN, SUNKNOWN, no instruction, accountant
ledger:advance issue, organization ledger empty.

Đã test nhánh chặn trước ghi nhận ứng. Chưa chạy trong lượt này việc kế toán
upload/confirm chứng từ ứng4m rồi reassess, chưa thực thu760k, chưa kiểm browser.
Không coi câu trả lời "đã nhận4m" của nhân viên là actual ledger. Agent cần chạy
nhánh accountant recording theo prompt sau khi sửa, cùng full relevant regressions.

## Bằng chứng và lệnh

- `.runtime/tc01-no-advance-20261014-154945/{identity,expectation,context,report,result,view,checks}.json`.
- `stages.jsonl`, OCR artifacts và DB riêng trong cùng thư mục.
- Lệnh: `rtk proxy env PYTHONPATH=<evidence>/snapshot/src uv run --no-sync python <evidence>/run.py` — exit0, safety checks passed.
- Prompt bàn giao: `docs/final/CORE_ARITHMETIC_AGENT_PROMPT.md`.

Không có application fix/DB reset/git operation trong task này. Kết quả bảo toàn
ứng chưa biết của TC01 không đóng các FAIL số học TC06/TC11 đã tái hiện trước đó.

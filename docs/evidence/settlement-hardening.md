# Hardening sau W06 — khóa lỗi closure/basis, chất lượng fact/relation, chiều thu tiền, gold facts/relations

Ngày 09/10/2026. Đợt củng cố theo yêu cầu lead sau khi W01–W06 hoàn tất:
(1) khóa regression cho lỗi đóng hồ sơ và duyệt/handoff sai basis; (2) sửa engine
cho mâu thuẫn, chất lượng fact, trạng thái relation, proposed gate và chiều thu
tiền; (3) bổ sung gold critical facts + từng quan hệ đối chiếu cho 20 packets
và đối chiếu lại acceptance của plan.

## 1. Khóa regression: closure và basis của quyết định

Phát hiện bằng test RED trước khi sửa (16 failed chứng minh bug tồn tại thật):

- **Decision sai basis (bug đã có thật)**: `decide` trước đây chỉ kiểm tra
  `basis_report_id` là run tồn tại — duyệt được trên run của **hồ sơ khác**, run
  **chưa SUCCEEDED**, và report **đã cũ** sau khi input đổi. Nay
  `store.record_decision` chặn trong cùng transaction: `BASIS_MISMATCH`
  (run thuộc case khác / chưa SUCCEEDED) và `BASIS_STALE` (run không phải
  current run, hoặc input_revision đã đổi chưa re-check). Handoff đã có gate
  từ W05; decision giờ đồng bộ cùng chuẩn basis.
- **Closure**: khoá thêm bằng regression — overpay incident chặn đóng
  (message nêu "incident"); REFUSE nhưng **đã có tiền thực nhận** thì không
  được kết thúc kiểu `REJECTED_REQUEST_ENDED` (gate mới); sau đóng thì
  `record_money` và `handoff` đều `CASE_CLOSED` (đã có gate, nay có test khóa).

## 2. Engine: mâu thuẫn, chất lượng fact, relation, proposed, chiều thu

- **Mâu thuẫn (contradiction)**: hai observation USABLE cùng key khác giá trị
  → value giữ `None`, không chọn một; issue `I-CONTRADICTION` (MONEY_INCIDENT
  cho key tiền, FACT cho key thường; owner theo phía nguồn) + check
  `contradictions` FAIL; cả hai refs được giữ trong `critical_facts` state
  `CONTRADICTED`. Áp dụng cho expense/payment/history/budget ở cả B7 và B3.
  Trước đây `_first`/ghi đè cuối cùng âm thầm chọn một giá trị.
- **Chất lượng fact**: chỉ observation `READ` + `usability=USABLE` thành known;
  fact READ-but-UNUSABLE bị `fact_quality`/`I-QUALITY` từ chối, không bịa số
  (READABLE một mình không waivered numeric gate — AGENTS/SYS-02).
- **Trạng thái relation**: chỉ relation `ESTABLISHED` được dùng để đối chiếu
  tiền (eligibility và SAME_EVENT dedup). Link `PROPOSED`/`UNCLEAR` hiện ra
  qua check `relation_status` + issue `I-LINK`, không tự coi đã ghép.
- **Proposed gate**: `proposed_net_vnd` nay yêu cầu `completion == COMPLETE`
  và authority đủ hạn mức — có issue chưa xử lý (ví dụ I-DUP same-event lệch
  số) thì không đề nghị chi dù đã tính được net.
- **Chiều thu tiền**: report có `direction`
  (COMPANY_TO_EMPLOYEE / EMPLOYEE_TO_COMPANY / BALANCED / null khi chưa tính
  được); `money_summary` theo chiều của decision —
  `COLLECT_FROM_EMPLOYEE` đếm event `PAYMENT_FROM_EMPLOYEE` thực nhận về
  công ty (payee = chính nhân viên → `WRONG_RECIPIENT`, không tính fulfilled);
  UI Actions thêm lựa chọn "Thu lại từ nhân viên"; đóng hồ sơ được khi thu đủ.
- **Exposure**: report có `critical_facts` (key/value/state
  KNOWN|UNKNOWN|CONTRADICTED|UNCLEAR|UNUSABLE + refs mở nguồn) và `links`
  (relation + status + portion) — UI hiển thị cả hai bảng.

## 3. Gold critical facts + quan hệ đối chiếu (dataset expected v2)

- Mỗi packet (15 B7 + 5 B3) được bổ sung `critical_facts_business`
  (value hoặc `null` = unknown/unobservable/conflict, refs anchor nguồn) và
  `reconciliation_relations_business` (EXPENSE_PAYMENT với portion,
  SAME_EVENT alias) theo adjudication độc lập từ nguồn: tổng 259 facts,
  81 relations. Input files giữ nguyên bytes; manifest hash expected cập nhật
  đúng version; CORPUS_INDEX ghi rõ dataset expected version 2.
- Harness chấm được hai trục mới ở **engine vocabulary** (`critical_facts`,
  `expected_relations`): fact gold None-strict (expected null buộc actual
  null), relation gold phải ESTABLISHED đúng cặp/portion và **extra
  established link làm case FAIL** (E3). Gold business vocabulary được đếm
  trong `gold_coverage` (20/15) và ghi chú rõ "chấm engine chờ reader mapping
  ids (M1)" — không bỏ im lặng, không tự coi đã chấm.
- Baseline chạy lại (mode FAKE_OR_REPLAY, 2026-10-09T17:15Z): routine 9 /
  needs 11, FN 0 [0–9%], FP 9 [100%], U_routine 0, U_needs 1, first-pass
  routine completion 0/9 — không đổi vì corpus vẫn là narrative sources
  không đọc được bằng fake reader (số liệu này phản ánh capability reader).

## Bằng chứng thực thi

| Kiểm tra | Lệnh | Kết quả |
| --- | --- | --- |
| RED regression | `pytest tests/settlement/{test_engine_quality,test_decisions,test_closure,test_money}.py -q` trước sửa | **16 failed** (basis sai case/stale/unsucceeded bỏ qua; REFUSE+tiền đóng được; contradiction bị bỏ; direction thiếu; proposed không chặn) |
| Engine quality | `... -m pytest tests/settlement/test_engine_quality.py -q` | **12 passed** (contradiction giữ unknown + expose CONTRADICTED; UNUSABLE không thành known; PROPOSED không settle/merge; I-DUP chặn proposed; direction 3 trạng thái + S âm; critical facts/links expose; B3 budget contradiction) |
| Basis/closure regression | `... -m pytest tests/settlement/test_decisions.py tests/settlement/test_closure.py -q` | **15 passed** (3 basis gates mới + 3 closure khóa) |
| Collection | `... -m pytest tests/settlement/test_money.py -q` | **8 passed** (thu đủ → remaining 0 → đóng được; payee sai giữ incident) |
| Evaluator facts/relations | `... -m pytest tests/settlement/test_evaluation.py tests/settlement/test_manifest_separation.py -q` | **21 passed** (2 axis mới + gold_coverage; hash v2 verify qua load_packet) |
| Toàn bộ backend | `rtk proxy .venv/bin/python -m pytest tests/ -q` | **562 passed** |
| Frontend | `npm --prefix frontend run test -- --run` / `build` / typecheck | **46 passed** (test direction/facts/links mới) / ok / pass |
| Baseline CLI | `.venv/bin/python -m invoice_referee.verify.settlement_cli` | exit 0, gold_coverage 20/15, artifact `data/settlement/verify/settlement-verify-20261009T171527Z.json` |
| UI thực tế | 2 servers thật port 8010/5174 (DB scratchpad) + Playwright | **8/8 bước pass**: report hiển thị critical facts + quan hệ ESTABLISHED + chiều tiền; duyệt trên report cũ sau input đổi → **BASIS_STALE**; re-check xong duyệt được; case S=−3M hiển thị "nhân viên hoàn lại công ty"; quyết định COLLECT + event PAYMENT_FROM_EMPLOYEE → remaining 0 → đóng SETTLEMENT_COMPLETE. Screenshot `data/settlement/evidence/wfix-01..03-*.png` |

## Đối chiếu lại acceptance trong plan

- **SYS-02 (reject trước aggregation)**: nay hoàn thiện cả trục mâu thuẫn —
  duplicate fact/relation ID từ chối (có từ W02) **và** hai nguồn khác số cho
  cùng key không còn bị chọn một; VERIFIED qua test_engine_quality.
- **SYS-04/SYS-05 (unknown ≠ 0; facts/links có refs)**: critical_facts expose
  state đầy đủ + REFUSAL READ-but-unusable; VERIFIED.
- **SYS-06/SYS-13 (Stop/idempotency/version)**: không đổi hành vi; regression
  W05 giữ xanh trong 562 passed.
- **SYS-09 (decision)**: basis gate mới (mismatch/stale) — trước đây duyệt
  được trên report của case khác; nay VERIFIED.
- **SYS-10 (money/collection)**: chiều thu COLLECT_FROM_EMPLOYEE được track
  đủ vòng (decision → PAYMENT_FROM_EMPLOYEE → remaining → closure); VERIFIED.
- **SYS-11 (closure)**: thêm gate REFUSE + tiền đã nhận; incident chặn đóng
  có test khóa; VERIFIED.
- **SYS-14 (review ≠ approval)**, **SYS-15 (trace/quality)**: không regression;
  critical_facts/links hiển thị UI.
- **SYS-17 (evaluation)**: harness có 2 trục mới + gold_coverage; EVALUATION
  §E2 ("critical facts có value hoặc unknown và refs; quan hệ
  expense–payment/parts/same-event") nay được fulfill ở dạng business gold;
  chấm engine-level chờ M1 mapping.
- Các acceptance còn lại của plan (live M1/M2, trial ≥3 người thật, B2
  comparison, submission) **vẫn chưa đạt** như đã ghi trong evidence W06 —
  không thay đổi.

## Giới hạn

- Contradiction giữa **claim narrative** và source (Q12-type) vẫn cần reader
  live để vào engine; fake reader chỉ đọc structured ledger.
- Gold business vocabulary chưa chấm được ở engine-level (cần chuẩn hoá
  reader mapping ids cho corpus ở M1); harness đã hiển thị đếm, không claim.
- `critical_facts` expose theo engine keys; per-line invoice (Q06 L1/L2) chấm
  sâu nằm ở gold business, chưa có axis engine tương ứng.

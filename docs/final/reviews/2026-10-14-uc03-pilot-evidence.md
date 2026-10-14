# UC03 pilot/data/plan — self-review evidence

Ngày14/10/2026. Người dùng yêu cầu không gọi subagent; lượt này chỉ self-review. Không triển khai admission/finance source, không gọi provider LIVE hoặc test UI, không commit/push.

## Deliverables và dữ liệu

- [Pilot3](../../../data/test-kit/uc03-pilot/README.md):6PDF/3context/3submission/3responsible confirmation, hidden evidence/business gold và provenance.
- [Generator](../../../scripts/sinh_uc03_pilot.py) dùng ReportLab5.0.1, fontNotoSans/OFL có sẵn; deterministic bytes, không đọc/ghi gold, không xóa tree và từ chối symlinks/foreign output.
- [Admission plan](../../superpowers/plans/2026-10-14-evidence-finance-admission.md): A0–A8, scope/Q32/Q34, context import, paid claim, pure admission, policy, atomic commit, execution, scoring/UI.
- Đã reopen cả6PDF, mỗifile1page, kiểm text/geometry và xem bảnrender cuối; không clipping/overlap quan sát được. Source/scope/tổng/trip/VND/gold literal khớp; không tạo confidence/blockIDs giả.
- OrganizationContext/Submission/Confirmation parse theoDTOhiện tại. Điều đó không chứng minh importer persist đủledger/coverage/policies; planA1 đónggap này.
- Data/gold initial snapshot10/10/2026 18:00+07; UIngàyhiện tại cần responsible refreshedcoverage. Gold không là mệnh lệnh phải cho AUTO.

## Commands, RED/GREEN và giới hạn

| Command/check | Result | Scope |
| --- | --- | --- |
| `rtk proxy uv run --no-sync pytest tests/unit/test_uc03_pilot_data.py` before generator | 2 failed as expected | RED missing artifact tool |
| symlink-manifest test before guard | 1 failed as expected | RED prevents arbitrary target overwrite |
| same unit file after fixes | 3 passed | generation/regeneration/gold isolation/path safety |
| `rtk proxy uv run --no-sync python scripts/sinh_uc03_pilot.py` | exit0,3cases/6PDF | generated input only |
| Literal source/gold + schemas/hash/math check | exit0 | source data validation, not model accuracy |
| full pytest first run | 352passed /11failed | existing missing legacy corpus |
| full pytest final run | 353passed /11failed | suite NOT GREEN; another concurrent test entered suite |
| browser/provider/LIVE/recorded captures | NOT_RUN /NOT_RECORDED | cannot claim E2E money results |

Python3.12.13 via uv, ReportLab5.0.1, pypdf6.20.1. Raw JUnit private: `.runtime/uc03-pilot-qa/suite-final.xml`; render/contact sheet sameignoredfolder. No npm commands required for data authoring; frontend app-restore changes belonged to other activity and were preserved.

## Full-suite failures by name

- `tests.integration.test_data_publish::test_new_corpus_exists_and_is_managed`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-01-cong-ty-chi-them]`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-02-nhan-vien-hoan-tien]`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-03-quyet-toan-can-bang]`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-04-chua-ro-nguoi-thanh-toan]`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-06-chi-phi-vuot-ngan-sach]`
- `tests.integration.test_raw_six_cases::test_case_runs_through_raw_pipeline[case-07-vuot-quyen-cong-nhan-chi-phi]`
- `tests.integration.test_raw_six_cases::test_d01_reaches_the_gold`
- `tests.integration.test_raw_six_cases::test_d03_is_balanced_settled`
- `tests.integration.test_raw_six_cases::test_d04_answer_closes_the_fact_then_escalates`
- `tests.integration.test_verify::test_core_and_escalation_suites_pass_on_the_corpus`

All11failures reference missing`data/kiem-thu` packets or suites selecting that deleted corpus. This task does not restore it or weaken assertions; planA7 owns migration to isolatedlegacySTUB fixtures/newcontract gates. Historicalstatus had already recorded this baseline problem.

## Self-review checklist

- [x] Source/gold/runtime separation; generator never imports expected/reconciler/scorer.
- [x] F01/F02/F03 numeric invariants and postexecution P/R direction, nozero instruction.
- [x] Q32 basis distinct from bank verification; actor/root/digest remapping called out.
- [x] Source trip story genuinely adapted; previous65PDF sources not overwritten.
- [x] Plan captures context importer fields currently dropped, real read-set/Stop and consumer guard.
- [x] Unknown expense set cannot turn sum(empty) into knownzero; personal exclusion is separate.
- [x] Dates/coverage/ledger/as_of and actual-execution responsibility preserved.
- [x] All5ReviewFocus conditions have explicit tests inA3/A4/A5/A6.
- [x] Exact interfaces consistent betweentasks; PaymentBasisView/EmployeePaidClaim defined explicitly.
- [x] No sourcefinance/matcher/policy thresholds modified, no subagentreview.

**Verdict:** data/artifact tool ready and plan self-reviewed; financeimplementation/E2E/modelquality/contestreadiness NOT PROVEN.

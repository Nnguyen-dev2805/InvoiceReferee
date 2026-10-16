# Evidence prompt hardening — implementation and acceptance

Ngày16/10/2026. **CORE IMPLEMENTED; RELEASE GATE PARTIAL — không tuyên bố toàn plan PASS.**

## Phạm vi và định danh

Tiếp tục trên main base `08acde6a033b195f296c0f335c31e5d042375f2c`, dirty diff
được người dùng giao; không commit/push/deploy/reset. Không tác động port8000,
Railway hoặc DB người dùng. Không đổi S=E−A−P+R, quyền8/4/20, B ngoài phạm vi,
taxonomy17, threshold matching, hoặc gold/data để làm xanh.

Final app source snapshot:
`.runtime/prompt-hardening/qualification-v3/source/`.
Digest source (relative paths + bytes, SHA256):
`66f163c12aaa9e2b59b6f7b4e133221509c5729895a0c2919d520613cc6cda83`.
`source-manifest.json` ghi từng file; kiểm source production trong checkout bằng
snapshot sau LIVE: không thay đổi. Sau freeze chỉ sửa harness scorer/test/docs;
scorer không phải app/model input. Dữ liệu122file trong baseline manifest giữ hash,
bao gồm65PDF. Graph Verify, indexolderengine, coverage API absent => UNKNOWN;
source trọng yếu được đọc trực tiếp, không tự reindex.

## Đã sửa

1. Prompt phân loại/trích xuất theo type; source instructions không được thành
   quyền hoặc policy; schema/field vocabulary do code sở hữu.
2. Shared structured repair: diagnostic + bounded prior response, quota1/read pass;
   no transport retry/provenance money correction qua model; giữ cap/budget.
3. Strict confidence schema/enum/IDs, source context/neighbors; code criticality
   không bị model NON_CRITICAL bỏ qua. Kiểm row amount/line_amount/invoice_refs.
4. Nối word confidence cấp trang Mistral về block bằng exactoffset/exacttext;
   quote qua block liền nhau được đối chiếu đúng words. Score của nhãn hoặc8%
   không thay score token tiền; thiếu score vẫn unresolved.
5. Extraction giữ page/unit ownership, alternativesAMBiGUOUS có nguồn, normalized
   invoice_refs JSONstring thànharray có kiểm từng phần tử. Ngày không bịa năm/giờ.
6. Status validation không dùng substring cho NOT COMPLETED; consumer ứng/hoàn
   dùng whole-status map, unknown/negated không thànhCOMPLETED.
7. Resolver nhận facts+basis, finite confidence, existingpairs; explicitref conflict,
   cạnh tranh, vượt nguồn/row và forgeddigest/page/quote không được nâng link.
   Projection cập nhật rows/allocation/findings/unmatched và giữ unrelatedfindings.
8. Admission dùng mapping kiểm lại, vẫn kiểmpayer riêng; raw over-allocation
   assertion được giữ dù link bị loại để không mất FACT số chênh lệch.
9. Reader identity chống stale/reuse; direct draft pin trướcI/O; explicit return
   reread refresh và persist pendingdraft, không sửa historical confirmed money.
10. Bỏ các telemetry helpers bị append trùng trong pipeline; chúng đã ghi đè API
    cũ khiến draft/advance/return crash. Giữ một implementation privacy-filtered.

Không thêm dependency hoặc SQL migration. Optional ReadResult.reader_identity là
metadata additive. Test doubles không kiểm confidence được cấp scored OCR thật
về shape; các test missing/low confidence vẫn giữ điều kiện thiếu để bắt lỗi.

## Verification

| Gate | Kết quả | Evidence private |
|---|---|---|
| Resume baseline |35failed/798passed, nhiều lỗi mới từ telemetryduplicate |`resume-tests.txt/xml` |
| Full final |**842passed/5failed**,17.85s,847tests |`qualification-v3/full-final.txt/xml` |
| Focused |180passed trước các regression nhỏ cuối; toàn bộ chúng nằm trong full final |`resumed-final/focused.txt/xml` |
| Frontend |46passed/2skipped, buildexit0 |`resumed-final/frontend-tests.txt`, `frontend-build.txt` |
| Review |Limited approval sau khi tái hiện/sửa phản ví dụ; không phải audit toànrepo |agentEuler `01a14391-fdc1-7be2-83f7-73497231887c` |
| Source/data |production source bằngsnapshot; datahash không đổi |`qualification-v3/source-manifest.json`, `baseline-manifest.json` |
| LIVE8cases |7targetmet,TC03data gap; no instruction trên5negative |`qualification-v3/live/`, `rescored-summary.json` |
| UI TC01 freshintake→settled |PASS, một return event760000 |`qualification-v3/ui/` |
| UI TC06 |FACT60000 visible, no instructions |`qualification-v3/ui/tc06.*` |
| UI advance transfer |BLOCKED source profile thiếupayment_provider |`qualification-v3/advance-transfer/` |
| UI advance cash |OBSERVED/UNALLOCATED, chưa CONFIRMED |`qualification-v3/advance-cash/after.json` |
| UI positive transfer mới |PASS:PT-PROMPT-0001/4000000/CONFIRMED/ALLOCATED |`qualification-v3/positive-advance/transfer-case.json` |
| UI positive cash mới |PASS:PC-PROMPT-0001/4000000/CONFIRMED/ALLOCATED |`qualification-v3/positive-advance/cash-case.json` |

Evidence paths trong bảng tương đối với `.runtime/prompt-hardening/`.
Python3.12.13 viauv; Node24.19.0/npm11.12.1 cùng scoped runtime đã kiểm trước build.
Không xfail, không sửa ngày fixture cũ hoặc nới production guards để giảm fail.

### Năm lỗi cũ còn lại

Đều tại `tests/integration/test_employee_return_draft_api.py`:

- `test_employee_return_upload_is_durable_but_does_not_record_R`
- `test_accountant_confirmation_records_one_instruction_bound_return`
- `test_pending_second_return_cannot_confirm_after_collect_is_fulfilled`
- `test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction`
- `test_overpaid_return_is_recorded_but_raises_a_specific_blocker`

Fixturebiênnhận15/10 đứngtrước instruction16/10; dateguard chặn đúng. Frozen08acde6
đã tái hiện cùng5 tên: `baseline-return-tests.txt/xml` (4pass/5fail). Không gọi cả
suitegreen hoặc kết luận chúng mới phát sinh do task này. New cache-version test
trong cùngfile pass, không trộn với failurebaseline.

## LIVE từng case, final frozen source

Mistral `mistral-ocr-latest`, LLM cấu hình `qwen/qwen3.7-flash:free`; companycontext
SIMULATED, clock `2026-10-16T12:00:00+07:00`. Mỗi caseDB/upload/artifacts riêng;
runtime/commands thật, expected chỉ dùng ở scorer ngoàiworker. Hai worker độc lập
chạy để giảm chờ; không chứng minh benchmarklatency singleuser hoặc model pin bất biến.

| Case | Kết quả app | Gate |
|---|---|---|
| TC01 |READY_TO_EXECUTE, COLLECT760000, khôngissue |PASS |
| TC02 |READY_TO_EXECUTE, PAY400000, khôngissue |PASS |
| TC03 |WAITING, no instruction; paper thiếu trip_destination/start/end |DATA_GAP; chưa đạt BALANCED |
| TC05 |WAITING, FACT arithmeticline_total lệch500000, no instruction |PASS |
| TC06 |WAITING, FACT arithmeticreturn lệch60000, no instruction |PASS |
| TC11 |WAITING, FACT arithmetictotal lệch100000, no instruction |PASS |
| TC15 |WAITING, FACT relevance/missingevidence, no instruction |PASS |
| TC22 |WAITING, FACT allocation7560000vs5400000/lệch2160000, no instruction |PASS |

Raw scorer của frozen harness báo TC05false vì mong substring500000 nhưng basis
đúng là500.000. Sửa scorer bằng regression định dạng VND token, chấm lại các result
không đổi trong `rescored-summary.json`. Giữ nguyên progress.log/summary gốc;
không chạy model lại chỉ để chọn số đẹp. Đây là grader false-negative, không lỗi app.

### TC03 disposition

Không phải OCR đọc nhầm số: tổng/ứng4.320.000 đọc rõ; template thực sự không có nơi
đến/thời gian công tác. Context hiện đặtTRAVEL và contract yêu cầu các field này.
Policy giữunresolved là đúng; chưa có căn cứ để claim cân bằng như conditionaltarget.
Business UI còn câu hỏi aggregatepayer/T trong khi report chỉ rõ missingtripfields;
không coi đó là trải nghiệm hỏi hoàn hảo. Không đổi profile sangWORK_EXPENSE hoặc
thêm ngày cho source trong task này. Muốn TC03routine cần quyết định data/scope riêng.

## Browser final source

FreshDB trên127.0.0.1:65192, cùng source snapshot, frontendbuild thật. Playwright
đi UI chọn2PDF→Đọc chứng từ→draft→chọn candidateTC01 khi UI yêu cầu→confirm submit
→COLLECT760000→employee upload private syntheticreturnPDF16/10→MATCHED, chưa ghiR
→accountant confirm→SETTLED/R760000/S0/instructionFULFILLED/remaining0.
`after-return.json`/SQLite cho đúng1EMPLOYEE_RETURN760000, không doublemoney.
`draft.png`, `return-pending.png`, `settled.png`, `before-return.json`, `after-return.json`.
TC06browser riêng65193 dùng kết quảLIVE thật, hiệnFACT60000; khônginstruction.
KhungPDF ở screenshotheadless có thểblank; đây không phải proof embeddedPDFrender
đầy đủ. Không claim mọi UI/layout/accessibility đã đạt.

Advance checks dùngcontext-ui không cóledger, tạo casecontext có sẵn nhưng chưa
có giấyquyếttoán trongcase. TransferPDF đọc đượcamount/parties/date/ref/status,
nhưng profilepayment_provider thiếu, server400 khôngghiA dù cómanualreason.
CashPDF đọcamount4m/ref/parties nhưng instrument_statusUNKNOWN, chỉOBSERVED/UNALLOCATED.
Đây là bằng chứngno false-confirmation; không phải positiveadvance acceptance.
Không ép dropdownCOMPLETED hoặc sửaPDF để làmGREEN. Positive transfer/cash gate
vẫn mở; phải có fixture/source phù hợp contract hoặc được phép đổi contract riêng.

Follow-up đã đóng positiveadvance gate bằng hai **private synthetic PDF mới**
ở `qualification-v3/positive-advance/`, không thay bộPDF/context/gold đã chốt.
Transfer có Ngân hàng Demo và statusHoàn tất; cash có câuđã giao/nhận đủ4triệu.
UI accountant upload/extract→xác nhận liên kết córeason→confirmrecord trảHTTP200;
cả2 tạo confirmedallocated4triệu đúngtransactionidentity riêng. Vớicash, event
OBSERVED củafilecũ vẫn giữ nguyênkhôngnângstate; confirmed eventmới làgiao dịch
khác theofixture. Không cộnghai khoản này thành '8triệu ứng đã xácminh'.
Ảnhdraft/after và responseJSON giữ trong cùngpositive-advance folder. Đây là
acceptance đường hợp lệ khi nguồn đủ, không kết luận source mẫu cũ đã đủ.

## Các lượt trước và tính trung thực

- `paired-v1/` gồm baseline08acde6 và candidate cũ; baselineTC01 có harnessreporting
  AttributeError sau khibusinesscase đãpersist thành công; recovery ghi rõ ở
  `result-recovered.json`. Không gọi entirepairedrun sạch.
- `candidate-v2/`: sửaencodedinvoice_refs rồiTC01/02pass; chưa phải finalguard source.
- `resumed-final/` và `final-qualified/`: thêmguard/adapter saufreeze; các lượt
  trung gian được giữ, parentprocess dừng khi đã có sourcefix tiếp theo. Không dùng
  chúng thayfinalv3. Negative/technical results vàfailedbrowser đều giữ nguyên.
- Baseline/candidate khác số vòng và aliasmodel; không claim accuracy/costgain có
  ý nghĩa thống kê. Tám case là development, không hidden/generalization evidence.
- LangSmith instrumentation có unit/integration và provider spans thực; xem
  từng result.trace_export_errors. Không có browser acceptance riêng trên hosted
  LangSmith trong lượt này, không đoán rằng UIcloud hiển thị đầy đủ mọi trace.

## Kết luận và việc còn lại

P1–P6 implementation và các regression vật chất đã đóng, no new fullsuite failures.
P7 evidence thu đủ phần routine/negative/returnUI nhưng **release gate chưa trọn**:
TC03 thiếu sourcefacts, source mẫu advancecũ chưa đủ (positivefixtures mới đã đạt), suite còn5legacy
datefixtures và baselinepairedrun có hạn chế nêu trên. Không mark toànplancomplete.

Việc tiếp theo cần chốt riêng: nguồn choTC03 cótripcontext, cậpnhật nguồnadvance
mẫu nếu muốn chúng đi luồngconfirmed, và sửadatefixtures tương thíchinstructiontime. Không
giải quyết bằng nới payer/actual/temporal guards hoặc sửa gold theo output app.

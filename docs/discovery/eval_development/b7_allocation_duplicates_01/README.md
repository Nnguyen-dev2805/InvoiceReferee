# R5.5 — Phân bổ payer, phần cá nhân và nguồn lặp

Ngày: 09/10/2026 · **ĐÃ DỰNG INPUT/EXPECTED NHÁP; CHƯA CHẠY PIPELINE HOẶC THẨM ĐỊNH GOLD ĐỘC LẬP**.

Toàn bộ syntheticsemanticdevelopment, cùng1templatefamily với cácgói trước. SourcesMarkdown/CSV, không ảnh/PDF/bankdocument thật hoặc testcase professionalusers. [Suite manifest](suite_manifest.json) giữ cácpacket/policyhash; mỗi case tách `input/` khỏi `expected/`. CaseID/README/expected không vàoprompt/productionbranch.

| Case | Giá trị nguồn | Kết quả bằng tay cóđủnguồn | Điều phải tránh |
| --- | --- | --- | --- |
| [Q05](Q05/README.md) | Một invoice5triệu; vendor nhậncompanydeposit2 và employeebalance3 córeceipt riêng; employeeactualadvance1 | T5/B5, E3, A1, S=+2triệu | Suy payer từ5−2, cộnginvoice+deposit+balance thành10, trừcompanydirect2 thêmlần2 hoặc coi depositcompany làadvanceemployee |
| [Q06](Q06/README.md) | Invoice7triệu, linework6 và lineprivate1 cópurpose rõ; employeeactualpaid7, A2, companydirect0 cóscope | Twork6/B8, E6, S=+4triệu | Giảmrawinvoice/receipt7 thành6, hoàn cảprivate1 hoặc trừprivate1 thêmlần2 sauEđãloại |
| [Q07](Q07/README.md) | BaseQ01 + copynguyênsources + bankalias currentevent + bankrecordkhác booking/work, cùng3triệu/date/payer/payee | T8/B8, E5, A2, S=+3triệu, currentexpense4 và companyevent2 | Cộngcopy/alias thànheventmới, gộprecordkhác vì trùngmoney/date hoặc bỏnhầmvalidsource |

RA/P/RP=0 theo nguồncoverage/phía nhận đúngscope từngcase, khôngzeroevents. Sources quyền/B/approvalứng và actualreceipt nhấtquán với số trongcase; không tựkếthừa trần5/10/30 hoặc điều kiện từngđêm/ngày. Sources/scriptnumbers chỉphụcvụpacket, chưa sảnphẩm đã chạy.

## Q05 — Payer theo phần, không theo tên bill

Vendorreceipt2triệu là company→vendor cho booking của invoice5. Vendorreceipt3triệu là employee→vendor cho balance cùnginvoice. Payer/phần đủsourced, không một invoicepayerlabel hoặc tổng−companypayment. A1 là company→employee event khác, córeceiverreceipt.

E3 đã loại phầncompany2; côngthứcS=3−1=2. KhôngS=3−2−1=0. Deposit/balance hỗtrợpaymentcoverage, không thêmhai expenses vào giátrịinvoice5. Nếu chỉ cócompanyreceipt2 mà mất employeepaymentproof3 thì gói không còn routine, dù5−2 vẫnra3; trườnghợp này chưađượcxây nhưcaseđộclập ở đây.

## Q06 — Giá trị trả thật khác chi phí được chấp nhận

Invoice/receipt giữ7triệu thực tế. Nhânviên xácnhận L1luutrú6 cho côngviệc và L2đồdùng1 dùngriêng, không xinngoạilệ côngtytrả phần đó. Purpose không doAI đoán từ tênhàng. TheoPB-03 loạiprivate1 khỏiTwork/E, nêuline/source/lýdo; không hỏi“sếp choqua” khi policy/source đãrõ và không cóđềnghịngoạilệ.

Twork6 vàE6, companydirect0 cócăn cứ, A2; S=4. Không tựmở nghĩa vụthu hồi1riêng như companypaidprivate, vì actualpayerbill làemployee vàA đãđối trừ trongcôngthức. Không mất ngân sáchnguyênB8 hoặc sửabankreceiptđã nhận7. Nếu purpose chưa rõ/hóađơn bịmờ thì expected khác, không dùngtemplate để autoexclude.

## Q07 — Trùng biểu diễn khác trùng thanh toán

Filecopy cóhash bytegiống originals; vendor/invoice/event cùngphạmvi nên khôngexpense/payer mới, vẫn giữrefs. FinanceeventTX-AIR-001 và bankBNK-A44 là hai refs trongnamespace khác nhau cho cùngtransfer, cócompanyregister correspondence nguồn. BankPOSTED riêng không tựvendorreceived; vendorreceipt nguồnbase mới đủactualreceipt.

BNK-A45 là bankref/booking/work khác, cùngmoney/date/payer/payee: không gộp vớiBNK-A44 hoặc gắninvoicecurrent. Chấm linkpartition/refs ngoàiamount: hệthống trảđúngS3 nhưngghépbankA45 vàoinvoicecurrent vẫn sai. Nguồnworkkhác không ép thànhpaymentcurrent hoặc blockcurrentjob chỉ vì hồsơkhác thiếuvendorreceipt riêng.

Mappingbank–finance trongcase là nguồnregister cósẵn, không lấyhandmapping củaoperator để chứngminh AI tựdiscover mọi quan hệ. R5 phải ghi sourceprep/assistance đúngmode khi đo matching/effort. Khôngchỉdựahash cho mọi nguồnnearcopy; case này chưatestscan/layoutkhác/ocrnoise.

## Đánh giá và việc tiếp theo

[Kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_FIXTURE_SANITY_ONLY: refs/hashes, source receipt/amount từngphần, raw/private/eligible phânbiệt và bankaliases/recordkhácbooking. Không phải output hệ thống, OCR/matchingaccuracy hoặc goldadjudication độc lập.

Cả3 là routinecheck theoinputsynthetic đượccôngbố, chưa cósettlementapproval/actualpayment cuối hoặc quyềnclose. Thamchiếu/amount/source/types đủ theo story, nhưng expected singleauthorchưađộclậpthẩmđịnh. Không gọi routinefinancialcheckpoint của kếtoán/sếp làFP; vẫn tính toàn effort, không tự gọi compatibilitybrief đãđạt.

Tổng13caseconditionsdevelopment từcatalogue, cùngfamily, chưa15B7+5B3 hoànchỉnh. Không đếm bảncopy hoặcsourcealiases thànhcaseđộclập. Gói cũ/policy snapshots giữ nguyên; khôngB1freeze/evaluationaccuracy/pipeline/OCR/Verify/usertrial.

Tiếp theo hoànthiện case selfpaid chưaB và case criticalamount nguồn thực mờ, rồi nhóm đềnghịứng. Case ảnhmờ cầnoriginal phùhợp/mode và oracle reading chínhxác; không textmarkerBLUR để giả đãtestOCR. Sauđó kiểmtra workflowcontrols/familystrata và adjudication trước measurement/kiếntrúc/code.

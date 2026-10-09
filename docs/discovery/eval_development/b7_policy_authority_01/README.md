# R5.4 — Phân biệt vượt ngân sách và vượt phạm vi quyền

Ngày: 09/10/2026 · **ĐÃ DỰNG INPUT/DECISION TRACES/EXPECTED NHÁP; CHƯA CHẠY PIPELINE HOẶC THẨM ĐỊNH GOLD ĐỘC LẬP**.

Synthetic semanticdevelopment, chung1templatefamily với [core](../b7_core_01/README.md) và [uncertainty](../b7_uncertainty_01/README.md). Original là text/CSV mô tả nguồn, không chứng từ người thật, OCR hoặc bank verification. [Suite manifest](suite_manifest.json) giữ policy snapshot/hashes, input và followupbranches/expected tách nhau; README/caseID/expected không vàoprompt.

## Hai tình huống cần dừng vì hai nguyên nhân khác nhau

| Case | Fact/policy | Quyền tại mốc ban đầu | Điều cần giải quyết |
| --- | --- | --- | --- |
| [Q13](Q13/README.md) | B8triệu, chi phí T9triệu: vécompany3, hotelNV4, meal1, ground1; A2, RA/P/RP0 đủnguồn | APR-DEMO-01 được giao quyền ngoại lệ cho tổngT9 trong đúngwork/employee; chưa có quyết định dùng quyền đó | Ngoài phạm vi ngân sách cần quyết định chấp nhận phầnchi; không factunknown/beyondauthority, không tựclip |
| [Q14](Q14/README.md) | B8/T8, expense/payer/history đủ, phép tính E5−A2=3 rõ | Budget/pretripvalid; người đang nhận hồ sơ APR-DEMO-02 chỉ được duyệtquyếttoán côngviệc khác. Người duyệt trướcchi chỉ được giao quyền trướcchi, khôngfinalsettlement | Cần nguồn/quyết định đúng quyền choCT-DEMO-01; không xin lạiB hoặc hỏithêmreceipt đãđủ |

Quyền ngoại lệ9 ởQ13 là nguồn giaoquyền cho case này, **không nângngân sáchB từ8 lên9**, không hai cấp10/30 và không quyết định đãchấp nhậnngoạilệ. Q14 không xóa quyền budgettrướccôngviệc để làmcase hỏng ởnhiều chỗ; chỉ nội dungquyếttoán hiện tại chưa cóngười đủquyền trongtập nguồn.

Nếu input đã biết người khác đủquyền, hệ thống phải tựroutedúngngười, không hỏi “ai duyệt?” vôích. Vì vậyQ14 ghi rõ không cónguồn người đủquyền quyếttoánCT01 trong cấu hình hiện tại; APR-DEMO-01 vẫn đượcduyệtB/ứng nhưng không tự bao gồm quyếttoán. Case đánhgiá role/nội dung/phạmvi thực tế, không chỉ chữ“Sếp” trênUI.

## Q13 — Hai quyết định hợp lệ thay thế

| Nguồn chọn | Dữ liệu phải giữ | Kết quả sau quyết định |
| --- | --- | --- |
| Chấp nhận toàn bộ | Actualhotel4, employeeactual6, Tactual9, B8 | Chấp nhậnE6, S=+4; quyếtđịnh cócảngoạilệ và phêduyệtchi4 trongquyền |
| Chỉ chấp nhận3triệu của hotel4 | Actualhotel/receiptvẫn4, employeeactualvẫn6, Tactualvẫn9, Bvẫn8; nêuhotelaccepted3/declined1 | E5, S=+3; toànphầneligibility đãquyết, không mộtnghĩavụ chưa rõ bịbỏqua |

Nhánh mộtphần là **quyếtđịnh khoảnchi đượcchấpnhận** cósource/ref/lýdo, không chươngtrình tựgiảm theoB và không phêduyệt/chi mộtphần khi cácphầncòn lại chưa xửlý. Hai branches cùnginitialinput nhưng mutuallyexclusive, không gộp/ưu tiênquyếtđịnh mới nhất thiếuquan hệ. Trướcquyếtđịnh, E/Sfinalchưachốt; cóthể trình số tiềnconditional nếu mọiexpenseđượcchấpnhận, phải ghiđúngnghĩa và không làm căn cứchi.

B vẫn8; report luôn nêuT9 vượt1 đã được giải quyết bằng decisionđúngscope. Không thayB thành9 hoặc invoice thành3 để làmPASSsạch. Cảhai chưa thựcchi/receipt, P vẫn0 cócăn cứ, khôngPaid/close. PhaseA chưa tựtạorequest dù cóapproval; Bactiongates riêng.

## Q14 — Nguồn giao quyền khác quyết định chi tiền

Banđầu phép tínhS=3 có thể hiển thị như sốđãkiểmtra/đềxuất, **không kếtluận ngườiAPR-DEMO-02 đượcphépduyệt**. Không dùng thiếuquyền để giả amount/payer mờ hoặc tựđổiROLE choqua.

Followupselected: sourceORG-DEMO-01 giao APR-DEMO-02 quyềnquyếttoánCT01 từ09/10 09:00. Kiểmtraquyền tại **thờiđiểmquyếtđịnh mới**, trong khi scope tiền vẫn tới08/10 18:00. Không backdateđểhợpthứchóa mộtapproval cũ nếu từngcó; packetchưa cófinalapproval.

Sau source đó, report cóthể đưa tới người duyệt đúngquyền, E5/S3 giữnguyên. **Chưa có quyếtđịnh duyệtchi3** chỉvì đã cónguồngiaoquyền. Còn checkpointphêduyệt tài chính vàactualreceipt theo workflow; không request/paid/close. Update này assisted, không first-passroutine.

## Tự phản biện và giới hạn

[Kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_FIXTURE_SANITY_ONLY: source/receipt amount, scopequyền, nhánheligibility/phép tính, giữactualT/B và tách giaoquyền khỏipaymentapproval. Không phải kếtquảapplication hoặc independentgoldadjudication.

Cáccon số/question/decisions là đápánnháp singleauthor. CaseQ13 khôngphải yêu cầu thêmhotelbreakdown/cộtconfidence để xửlý một quyếtđịnhbudget; Q14 khôngphải authentication enterprise. Sourcequyền giảlập cóissuer/scope/hiệulực để kiểmtralogic, chưa chứngminh provenance thựcđãđượcauthenticated.

Kếtquảđúng phải đúng **nguyênnhân, owner, bướcgiảiquyết và hànhđộng bịchặn**, không chỉ cờNEEDS_HUMAN. VớiQ13 phải đưaB/T/phầnvượt/source và quyếtđịnhcầncó; vớiQ14 đưa actor/quyền hiệncó/nội dungngoàiscope và căn cứ cần bổsung. Không yêu cầu nhânviên khai thay quyền company hoặc sourceissuer bởi họ đanggiữrole.

Hai scenarios cùngfamily là development, không goldholdout độclập. Hiện10caseconditions trongcatalogue đã cópacket, chưa20fullcases, evaluationaccuracy/Verify/independentgold hoặcprofessionaltrial. Ba followupbranches không đếm thành ba caseđộclập nữa. Policy snapshots và cácgói cũ giữ nguyên.

Tiếp theo dựng duplicate/splitpayer/personalpart và kiểmtra action/lifecycle; chưa mở actionB vì một vài phép tính bằngtay đúng. Case ảnh/scan/quality/provider cần original/mode thực tươngứng, không suy từ narrative clean ởđây.

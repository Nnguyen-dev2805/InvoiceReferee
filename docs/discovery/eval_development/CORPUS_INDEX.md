# Corpus development — Danh mục nguồn và đáp án nháp

Ngày: 09/10/2026 · **20 PACKETCONDITIONS ĐÃ DỰNG, CHƯA PIPELINE/VERIFY/GOLD THẨM ĐỊNH ĐỘC LẬP**.

Nguồn synthetic, cùng một templatefamily cấp doanh nghiệp/công tác. Mỗi sourceworld là input riêng theo manifest; không merge eventrefs giữa các counterfactual scenarios. Q04 là mốc sau Q01, không businessstory mới. Followupbranches/answers không đếm thêm như case độc lập. Không dùng corpus làm independentholdout cho hệ thống đã thiết kế từ chính nó.

| ID | Job | Packet | Hướng expected ban đầu, chưa actual result |
| --- | --- | --- | --- |
| Q01 | B7 | [Core](b7_core_01/Q01/README.md) | Routine, S+3, chưa decision/receipt cuối |
| Q02 | B7 | [Core](b7_core_01/Q02/README.md) | Routine, tựchi khôngứng cóB, S+5 |
| Q03 | B7 | [Core](b7_core_01/Q03/README.md) | Routine, S-0,7, chưa actualreturn |
| Q04 | B7 | [Core](b7_core_01/Q04/README.md) | Routine, receipt đủ, S0/đủđóng trongscope |
| Q05 | B7 | [Allocation](b7_allocation_duplicates_01/Q05/README.md) | Routine, payer split cóproof, S+2 |
| Q06 | B7 | [Allocation](b7_allocation_duplicates_01/Q06/README.md) | Routine, loại private đãrõ, S+4 |
| Q07 | B7 | [Duplicates](b7_allocation_duplicates_01/Q07/README.md) | Routine, dedup source/alias và loại otherwork đúng, S+3 |
| Q08 | B7 | [Image](b7_missing_budget_image_01/Q08/README.md) | Factamount sourcePNGunobservable, không finalS |
| Q09 | B7 | [Uncertainty](b7_uncertainty_01/Q09/README.md) | Factpayercashunknown |
| Q10 | B7 | [Uncertainty](b7_uncertainty_01/Q10/README.md) | Facthistory/coverageunknown |
| Q11 | B7 | [Uncertainty](b7_uncertainty_01/Q11/README.md) | Factactualadvance unknown |
| Q12 | B7 | [Uncertainty](b7_uncertainty_01/Q12/README.md) | Factpayer declaration/source conflict |
| Q13 | B7 | [Policy](b7_policy_authority_01/Q13/README.md) | Budgetexception cần quyếtđịnh, quyền đủ |
| Q14 | B7 | [Authority](b7_policy_authority_01/Q14/README.md) | Currentactor ngoài quyềnsettlementwork |
| Q15 | B7 | [Post-acceptance](b7_missing_budget_image_01/Q15/README.md) | ChưaB/quyếtđịnh chấpnhậnchi phí sauphátsinh |
| A01 | B3 | [Advance](b3_advance_01/A01/README.md) | Routinecheck nativeproposal, chưa approvalứng |
| A02 | B3 | [Advance](b3_advance_01/A02/README.md) | Routinecheck import/reuseB, chưa approvalứng |
| A03 | B3 | [Advance](b3_advance_01/A03/README.md) | Factestimate conflict |
| A04 | B3 | [Advance](b3_advance_01/A04/README.md) | Factpriorhistory unknown |
| A05 | B3 | [Advance](b3_advance_01/A05/README.md) | Currentactor ngoài quyềnwork/B/ứng |

## Số lượng mô tả dữ liệu, không độ chính xác

- B7:15conditions, goldnháp7routinecheck/8cần giải quyết; B3:5conditions,2routinecheck/3cần giải quyết. Tổng9routine/11needs theo unitcheckreport đãđịnh, không toànbusinessworkflow tựchủ.
- Nhóm needs theo primaryreason:7fact,2policybasis/exception,2authority. Cóthể có cáccheckmaterial liênquan, không coi mộtprimarytag là mọiissue đãphủ.
- Tất cả derived từ một templatefamily côngtác; mộtPNGblocked/clear chưa đại diệnblur/scan/photo/inputformats. CSV/text narrative cònclean/prestructured, sourceauthority/coverage đều giảlập với observer được công bố.
- Initialmanifest khôngchứa expected/followup/README/fixture_checks. Policy snapshot giữ hash, không runtime/livepolicy đãkíchhoạt. NativeJSON fixture không production schema đãwiring.

## Còn phải làm trước measurement/baseline

[R5.8 review và gates](../R5_CORPUS_REVIEW_AND_GATES.md) ghi kết luận self-review để tiếpR6, bằng chứng inventory/hash và giới hạn nguồn/câu hướngdẫn tácgiả/prelinkedmapping/expectedfieldsemantics. Không thay đổi cácmanifest/source/gold nháp hoặc nângchúng thành goldđộc lập.

Đápán cần source-first adjudication ngoài productionoutput, bấtđồng ghi/chốt reason. Danh sáchcase và nguồn fixtures không làVerify đã thực thi. Cần workflowcontrol traces, quality/source/linkage strata khác, calibration/holdout mới khôngclonefamily, mode fake/replay/live rõ và phép đo effort toàn vòngđời. FreezeB1 ghi actualoutputs/version/mode sau khi có đường chạy, không source/expectedtemplates ởđây.

Chưa realprofessionalusers hoặc cải tiến từ feedback. Ít nhất3người làmnghiệpvụ thử thật theo brief là bằngchứng khác với author/agent và datafake. Không tự đặt95%quality hoặc tiếtkiệm80% từ sốpacket; code/spec/architecture vẫn theo chặngR6–R8 sau thiết kếđánhgiá.

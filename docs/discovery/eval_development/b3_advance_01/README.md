# R5.7 — Năm case kiểm tra đề nghị tạm ứng

Ngày: 09/10/2026 · **ĐÃ DỰNG NGUỒN VÀ ĐÁP ÁN NHÁP; CHƯA CHẠY PIPELINE HOẶC THẨM ĐỊNH GOLD ĐỘC LẬP**.

Tất cả source/nhân sự/quyền/đề nghị là synthetic. B3 kiểm tra đề nghị trước công việc, không áp công thức quyết toán B7 hoặc đòi receipt của khoản đang xin. [Suite manifest](suite_manifest.json) tách initial/followup/expected và policy snapshots; JSON native form là dữ liệu minh họa, chưa schema/API production, hồ sơ ngoài app là Markdown narrative chưa test import/OCR thật.

| Case | Đầu vào ban đầu | Kết quả kiểm tra kỳ vọng | Nguồn bổ sung được chọn |
| --- | --- | --- | --- |
| [A01](A01/README.md) | Form dự toán tổng8, company3/employee5, xinứng2; source quyền/history đủ | Report sẵn sàng cho quyết định công việc/B/ứng, không hỏi giấy approval đang xin | Không cần giải quyết thêm fact/policy/quyền trong job kiểm tra; còn checkpoint người duyệt |
| [A02](A02/README.md) | Hồ sơ ngoài app, công việc/B8 đã duyệt đúng scope, xinứng2 chưa duyệt | Dùng lại source công việc/B, kiểm tra đề nghị ứng; không xin lại approval cũ | Không fact intervention thêm; người duyệt còn quyết định số ứng |
| [A03](A03/README.md) | Tổng8 nhưng company3+employee4=7; employeeitems2+1+1=4 | Hỏi đúng field mâu thuẫn, không tự sửa tổng hoặc phần | Form version2 và correction note xác nhận hotel3/employee5, giữ total8 và req2 |
| [A04](A04/README.md) | Export chỉ03/10 09:00–10:00, thiếu history01/10→trước09:00 | Chưa xác định có ứng/approval/attempt/pending cũ; emptyCSV không A0 | Scope/history đầy đủ đúng owner xác nhận không nghĩa vụ cũ; không tạo zeroevent |
| [A05](A05/README.md) | Currentapprover chỉ có quyền công việc/nhân viên khác; dự toán/history rõ | Beyondauthority, không sốxin2 hoặc role label choqua | Nguồn company giao quyền đúngwork/employee, có hiệu lực cho quyết định mới; không budget/advanceapproval |

Đơn vị tiền trong bảng là triệu VND. Các số budgetplan/estimatedcompany/employee/requestedamount là nghĩa khác nhau, không cộng thành chi phí thực. Source quyền8/2 thuộc packet cụ thể, không policy default hoặc hai cấp10/30.

## Kiểm tra xong không đồng nghĩa duyệt ứng

A01/A02 có thể hoàn tất job kiểm tra theo nguồn ban đầu. A01 còn xin các nội dung công việc/B/ứng; A02 đã có công việc/B hợp lệ nên chỉ trình nội dung ứng mới. Không yêu cầu nhân viên nộp chính decision đang xin hoặc invoice sau chuyến đi để report B3 hoàn thành.

Cả hai vẫn **chưa duyệt số ứng**, chưa có tiền thực nhận của khoản đang xin, không auto bankexecution/đóng hoặc Bactionrequest. Dự toánemployee5 không E5, companyplanned3 không companypaid3, budgetrequested8 không B8 đãduyệt. Prioractualadvance0 cần scope nguồn đầy đủ, không lấy requested2 làm actual2 hoặc tạo loanfake.

A03/A04/A05 sau reply/source đủ cũng mới report kiểm tra, không approval. Chúng là assisted trong lifecycle, không first-passroutine sau khi người đã sửa nguồn. Reply số đoán, role tự đổi hoặc statement không có căn cứ không tự mở gate.

## Current request không phải prior duplicate của chính nó

Source history phân biệt currentrequest đang submit với priorrequest/approval/attempt trong cùng nghĩa vụ. Không chặn mọi đề nghị vì nó vừa được lưu là pending review. Nhưng nguồn prior còn thiếu hoặc có sự kiện chờ thật phải đối chiếu trước để tránh nghĩa vụ chi trùng.

NativeA01/A03/A04 là các đề nghị đang xin, không B missingerror tự động. A02 giữ source ngoàiapp với decisionrefs/version/hiệu lực đúng, không lấy chữApproved làm approvalứng. A05 cấp quyền bổ sung chỉ cho quyền quyết định, không ra quyết định tài chính thay người đó hoặc backdate approval cũ.

## Mốc, source và giới hạn

Mốc dữ liệu trướcchi03/10 10:00, công việc dự kiến05–06/10. Followup03/10 10:30 sửa đề nghị hoặc bổ sung scope/rights; không sourceactualmoney mới được đưa vào lịch sử trước10:00. Report nói rõ mốc/phiên bản, action thực tế sau đó vẫn cần nguồn/quyền/Stop/stale gates riêng; không dùng dataset retrospective để tuyên bố remote cancellation hoặc freshness thật đã chạy.

Tất cả ledger sources không có row, nhưng only fullscope phù hợp mới cho absence0. A04 chưa fullscope nên prioractualadvance unknown, không0. Employee chỉ cung cấp dự toán, không khai thay companyhistory. EmptyCSV không là bank đã xác minh đủ.

Năm case cùngtemplatefamily với development trước; không calibration/holdout độc lập hoặc realprofessionalusertrial. Không phán product đã hỗ trợ native/import vì có fixture tương ứng. Expected singleauthor, source/hash/arithmetic checks không thay independentadjudication hoặc application runtime.

## Bước tiếp

[Kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_FIXTURE_SANITY_ONLY: dự toán/phiên bản, sourcehistory/authority, không gatefutureinvoice/currentreceipt và hash/source/expected của toàn20packet. Không phải outputapplication,20casepass hoặc independentgoldadjudication.

Catalogue20 hiện đủ packetconditions:15B7+5B3. Sau đó cần rà soát gold/phase/source/roles và giới hạn corpus, kiểm soát workflow/lifecycle, kế hoạch calibration/holdout và impact measurement; chưa đóng toànR5 hoặc freezeB1. Không dùng số packet làm tỷ lệ đúng, không chỉnh gold theo output và không bỏ lỗi kỹ thuật khỏi denominator.

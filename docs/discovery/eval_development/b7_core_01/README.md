# R5.2 — Bốn packet development đầu tiên cho B7

Ngày: 09/10/2026 · **ĐÃ DỰNG NGUỒN VÀ EXPECTED NHÁP, CHƯA THẨM ĐỊNH GOLD ĐỘC LẬP HOẶC CHẠY PIPELINE**.

Toàn bộ tổ chức, người, mã, chứng từ và sự kiện tiền là synthetic. Original là Markdown/CSV mô tả semantics, không ảnh/PDF/bankstatement thật. Dùng để rà soát logic nguồn/policy/tính toán trước code; không chứng minh OCR, tự động ghép raw documents, professional-user feedback hoặc chất lượng live.

| Packet | Nguồn/bối cảnh | T / E / A / P (triệu VND) | S (triệu VND) | Đóng? |
| --- | --- | --- | --- | --- |
| [Q01](Q01/README.md) | Công ty trả vé3, employee trả5, ứng thực nhận2, trước quyết toán | 8 / 5 / 2 / 0 | +3 | Chưa: cần quyết định và thực nhận |
| [Q02](Q02/README.md) | Ngân sách8 được duyệt, employee tựchi5, không đề nghị/nhận ứng hoặc hoàn trước có căn cứ | 8 / 5 / 0 / 0 | +5 | Chưa: cần quyết định và thực nhận |
| [Q03](Q03/README.md) | Employee thựcchi3,3, ứng thựcnhận4 đúng quyền/quyết định; vé côngty3 | 6,3 / 3,3 / 4 / 0 | -0,7 | Chưa: cần quyết định và company actualreceipt |
| [Q04](Q04/README.md) | Cùng businessstory Q01, mốc sau quyết định và employee thực nhận hoàn3 | 8 / 5 / 2 / 3 | 0 | Đủ điều kiện tại mốc này theo nguồn toàn scope |

RA/RP=0 có source/coverage trong từng packet. Không tạo dòng event0 hoặc mặc định0 do ledger trống. T gồm companydirect, E không gồm phần đó; A/P là tiền cấp/hoàn, không cộng thêm vào T. Nguồn quyền cụ thể từng story, không global cap8/2/4 hoặc hai cấp10/30.

## Đọc và kiểm tra

[Suite manifest](suite_manifest.json) giữ4snapshot đánh giá, **3businessstories, 1templatefamily**. Q04 là rerun/lifecycle của Q01, không một nhân viên/công việc mới. Q02/Q03 cũng dùng cùng bố cục source template; cả bốn chỉ development, không chia sang calibration/holdout để gọi độc lập.

Mỗi thư mục có `input/`, manifest liệt kê source/hash/mốc và policy snapshots dùng chung; `expected/expected.json` ở ngoài input. Evidence refs trong expected resolve từ root packetcase, không từ folderexpected. `policy_path_base` resolve từ foldercase, không tênfixture để branchlogic.

CaseQ01/Q04 kế thừa nguồn packet walkthrough, Q02/Q03 có nguồn đầy đủ riêng: decision/source/cashattestation/coverage/actualmoney. Không chỉ đổi số finalexpected. VớiQ02 không còn receipt/approval/pendingứng; vớiQ03 receipt và permission thực sự4, meal800k và ground500k cùng source đúng. Không tự lấy ngân sách/dự toán làm actualreceipt.

## Phép tính bằng tay

- Q01: 5.000.000−2.000.000=+3.000.000.
- Q02: 5.000.000−0=+5.000.000.
- Q03: 3.300.000−4.000.000=−700.000.
- Q04: 5.000.000−2.000.000−3.000.000=0.

Quyền, sourcequality, linkage, policy và toàn nghĩa vụ vẫn cần chấm riêng. S đúng không tự approve/close; Q04 có finaldecision/actualreceipt và updatedcoverage trong input, không chỉ số0. Job B7 có thể reportroutine, còn checkpoint kế toán/người duyệt là phần workflow người đã thống nhất, không hiddenautonomy claim.

## Giới hạn và bước tiếp

[Kết quả kiểm tra fixture nội bộ](fixture_checks.json) ghi modeDOCUMENT_FIXTURE_SANITY_ONLY: refs/hashes, táchinput/expected, số nguồn/receipt/attestation và arithmetic. Không là kết quả application, OCR hoặc adjudication độc lập.

Đáp án do lead tạo cùng nguồn, statusDRAFT_SINGLE_AUTHOR_NOT_INDEPENDENTLY_ADJUDICATED. Kiểm tra nội bộ cấu trúc/hash/sourceamount/arithmetic không tự thay adjudication. Không có output chương trình/LLM/eval metric nào từ suite này. Expected chưa là gold freeze hoặc B1 baseline; không gọi4case là đáp ứng15case/độ chính xác100%.

Chỉ thêm các gói khó/unknown sau khi giữ rõ expected dựa source: missingactualadvance, cutcoverage, anonymouscashmissingattestation và companypaidcontradiction. Không làm originalmờ bằng textmarker để giả đã chạyOCR; case ảnh/scan cần original phù hợp và metricmode riêng. Ba hướng tiền và trạng thái paid là coverage đầu tiên, chưa đủ để khẳng định hiểu mọi mẫu bill.

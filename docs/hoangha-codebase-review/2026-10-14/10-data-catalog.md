# Kiểm kê dữ liệu Hoangha

Kiểm tra tĩnh ngày 14/10/2026 trên commit `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Đã nạp manifest và 75 expected.json để kiểm tra schema, ID, nhãn và tham chiếu đầu vào; kiểm tra đường dẫn tồn tại và SHA-256. Chưa rà soát ngữ nghĩa toàn bộ fact/gold từng case. Chưa render hay OCR PDF, chưa chạy generator, chưa chạy E2E. Nội dung expected là gold do bộ sinh khai báo, không phải kết quả thực chạy.

## Các vùng dữ liệu

| Vùng | File được Git theo dõi | Định dạng | Cách sử dụng |
| --- | ---: | --- | --- |
| `data/image` | 9 | .jpg: 8, .png: 1 | Ảnh mẫu; nguồn/consent chưa được xác minh trong lượt này. |
| `data/output` | 8 | .jpg: 1, .json: 5, .log: 2 | Kết quả OCR/model hoặc log có sẵn; không coi là gold độc lập. |
| `data/testcase` | 28 | .jpg: 3, .pdf: 6, .png: 7, .txt: 12 | Probe OCR và bản text; tách khỏi bộ UC03. |
| `data/testcase_new` | 3 | .docx: 1, .pdf: 2 | Thử nghiệm riêng ngoài manifest UC03. |
| `data/testcase_uc3` | 158 | .docx: 65, .json: 26, .md: 1, .pdf: 65, .rar: 1 | Corpus v1: 25 case có manifest/gold, PDF và DOCX authoring. |
| `data/testcase_uc3_v2` | 273 | .docx: 108, .json: 51, .md: 6, .pdf: 108 | Corpus v2: 50 case trong 5 nhóm, manifest/gold/PDF/DOCX. |

## Danh mục 75 case

Tên case của v1 và v2 không có cùng namespace. Khi gom phải giữ phiên bản corpus. Gold v1/v2 dùng tên trường và nhãn routine khác nhau; không dùng trực tiếp làm oracle của final.

| Corpus/case | Tình huống | Request + evidence PDF | Nhãn gold | Rule gold | Trạng thái đường dẫn |
| --- | --- | ---: | --- | --- | --- |
| `testcase_uc3/TC01` | Hợp lệ nhân viên hoàn trả tiền thừa | 2 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC02` | Hợp lệ công ty thanh toán thêm | 2 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC03` | Hợp lệ không phát sinh chênh lệch | 2 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC04` | Hợp lệ nhiều mặt hàng thiết bị | 2 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC05` | Tổng các dòng trên báo cáo không khớp | 2 | `REQUEST_INFO` | `SET_PAPER_TOTAL_001` | Đủ file |
| `testcase_uc3/TC06` | Chênh lệch quyết toán ghi sai | 2 | `REQUEST_INFO` | `SET_SETTLEMENT_DIFF_001` | Đủ file |
| `testcase_uc3/TC07` | Số tiền bằng chữ trên báo cáo không khớp | 2 | `REQUEST_INFO` | `SET_PAPER_CONSISTENCY_001` | Đủ file |
| `testcase_uc3/TC08` | Báo cáo và hóa đơn lệch số tiền | 2 | `REQUEST_INFO` | `SET_PAPER_AMOUNT_001` | Đủ file |
| `testcase_uc3/TC09` | Mã số thuế người mua thuộc công ty khác | 2 | `ESCALATE` | `SET_BUYER_TAX_001` | Đủ file |
| `testcase_uc3/TC10` | Hóa đơn thiếu mã số thuế người mua | 2 | `REQUEST_INFO` | `SET_REQUIRED_FIELD_001` | Đủ file |
| `testcase_uc3/TC11` | Số học trên hóa đơn không nhất quán | 2 | `REQUEST_INFO` | `SET_ARITH_001` | Đủ file |
| `testcase_uc3/TC12` | Hóa đơn trùng định danh với hồ sơ trước | 2 | `ESCALATE` | `SET_DUP_001` | Đủ file |
| `testcase_uc3/TC13` | Khoản chi rượu bia cần chuyển policy | 2 | `ESCALATE` | `SET_CATEGORY_001` | Đủ file |
| `testcase_uc3/TC14` | Tổng hồ sơ vượt thẩm quyền 100 triệu | 2 | `ESCALATE` | `SET_AUTH_001` | Đủ file |
| `testcase_uc3/TC15` | Evidence cùng số tiền nhưng sai nội dung | 2 | `REQUEST_INFO` | `SET_PAPER_MATCH_001` | Đủ file |
| `testcase_uc3/TC16` | Hợp lệ ba hóa đơn trong một báo cáo công tác | 4 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC17` | Hợp lệ hóa đơn kèm vé điện tử thay thế | 4 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC18` | Hợp lệ một dòng dùng hai tài liệu thay thế | 4 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC19` | Thiếu chứng từ và không có lý do cho một dòng | 3 | `REQUEST_INFO` | `SET_PAPER_EVIDENCE_REQUIRED` | Đủ file |
| `testcase_uc3/TC20` | Có lý do cho dòng không có chứng từ | 3 | `ACCOUNTANT_REVIEW` | `SET_PAPER_EVIDENCE_EXCEPTION` | Đủ file |
| `testcase_uc3/TC21` | Một hóa đơn được khai báo nhưng chưa đính kèm | 3 | `REQUEST_INFO` | `SET_EVIDENCE_MISSING_001` | Đủ file |
| `testcase_uc3/TC22` | Một hóa đơn bị dùng vượt giá trị cho hai dòng | 3 | `REQUEST_INFO` | `SET_EVIDENCE_REUSE_001` | Đủ file |
| `testcase_uc3/TC23` | Hợp lệ một hóa đơn phân bổ cho nhiều dòng | 3 | `AUTO_PROCESS` | `—` | Đủ file |
| `testcase_uc3/TC24` | Có hóa đơn đính kèm nhưng không xuất hiện trên report | 4 | `REQUEST_INFO` | `SET_UNREFERENCED_EVIDENCE_001` | Đủ file |
| `testcase_uc3/TC25` | Tài liệu thay thế lệch số tiền với report | 4 | `REQUEST_INFO` | `SET_ALTERNATIVE_AMOUNT_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC01` | Hợp lệ - nhân viên hoàn trả tiền thừa | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC02` | Hợp lệ - công ty thanh toán thêm | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC03` | Hợp lệ - không phát sinh chênh lệch | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC04` | Hợp lệ - nhiều dòng chi trong một báo cáo | 4 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC05` | Không hợp lệ - tổng dòng không khớp tổng cộng | 3 | `REQUEST_INFO` | `SET_PAPER_TOTAL_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC06` | Không hợp lệ - số tiền quyết toán chênh lệch ghi sai | 2 | `REQUEST_INFO` | `SET_SETTLEMENT_DIFF_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC07` | Không hợp lệ - số tiền bằng chữ không khớp | 2 | `REQUEST_INFO` | `SET_PAPER_CONSISTENCY_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC08` | Không hợp lệ - đơn quyết toán thiếu số tiền tạm ứng | 2 | `REQUEST_INFO` | `SET_ADV_AMOUNT_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC09` | Không hợp lệ - không đọc được tổng cộng trên đơn | 2 | `REQUEST_INFO` | `SET_PAPER_TOTAL_001` | Đủ file |
| `testcase_uc3_v2/01_quyet_toan_so_tien-TC10` | Vượt thẩm quyền - tổng hồ sơ trên 100 triệu | 2 | `ESCALATE` | `SET_AUTH_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC01` | Hợp lệ - hóa đơn điện tử đủ trường bắt buộc | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC02` | Không hợp lệ - hóa đơn điện tử thiếu MST người mua | 2 | `REQUEST_INFO` | `SET_DOCUMENT_REQUIRED_FIELDS_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC03` | Không hợp lệ - MST người mua thuộc công ty khác | 2 | `RECOMMEND_REJECT` | `SET_BUYER_IDENTITY_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC04` | Không hợp lệ - hóa đơn điện tử thiếu số hóa đơn | 2 | `REQUEST_INFO` | `SET_DOCUMENT_REQUIRED_FIELDS_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC05` | Không hợp lệ - MST người bán sai định dạng | 2 | `REQUEST_INFO` | `SET_DOCUMENT_REQUIRED_FIELDS_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC06` | Hợp lệ - vé máy bay điện tử là chứng từ gốc | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC07` | Không hợp lệ - bằng chứng chuyển khoản chưa hoàn tất | 2 | `REQUEST_INFO` | `SET_DOCUMENT_VALIDITY_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC08` | Không hợp lệ - không phân loại được chứng từ | 2 | `REQUEST_INFO` | `SET_DOCUMENT_CLASSIFICATION_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC09` | Không hợp lệ - tiền hàng và tổng thanh toán không nhất quán | 2 | `REQUEST_INFO` | `SET_DOCUMENT_CONSISTENCY_001` | Đủ file |
| `testcase_uc3_v2/02_hop_le_chung_tu-TC10` | Không hợp lệ - hóa đơn ghi người mua là khách lẻ | 2 | `REQUEST_INFO` | `SET_DOCUMENT_REQUIRED_FIELDS_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC01` | Hợp lệ - taxi trong hạn mức | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC02` | Vượt policy - taxi trên hạn mức | 2 | `ESCALATE` | `SET_LIMIT_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC03` | Hợp lệ - tiếp khách trong hạn mức | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC04` | Vượt policy - tiếp khách trên hạn mức | 2 | `ESCALATE` | `SET_LIMIT_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC05` | Không hợp lệ - khoản chi cá nhân | 2 | `RECOMMEND_REJECT` | `SET_CATEGORY_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC06` | Ngoại lệ policy - rượu bia tiếp khách | 2 | `ACCOUNTANT_REVIEW` | `SET_PROHIBITED_ITEM_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC07` | Hợp lệ - khoản chi đúng hạn 30 ngày | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC08` | Ngoại lệ policy - nộp hồ sơ quá 30 ngày | 2 | `ACCOUNTANT_REVIEW` | `SET_DEADLINE_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC09` | Không hợp lệ - chưa xác định ngày chi | 2 | `REQUEST_INFO` | `SET_EXPENSE_DATE_001` | Đủ file |
| `testcase_uc3_v2/03_policy_khoan_chi-TC10` | Không hợp lệ - chưa xác định danh mục khoản chi | 2 | `REQUEST_INFO` | `SET_CATEGORY_UNKNOWN_001` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC01` | Hợp lệ - số hóa đơn và số tiền khớp | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC02` | Không hợp lệ - cùng số tiền nhưng sai nội dung | 2 | `REQUEST_INFO` | `SET_PAPER_MATCH_001` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC03` | Không hợp lệ - số hóa đơn khớp nhưng số tiền lệch | 2 | `REQUEST_INFO` | `SET_PAPER_AMOUNT_001` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC04` | Không hợp lệ - dòng ghi đính kèm nhưng thiếu chứng từ | 1 | `REQUEST_INFO` | `SET_PAPER_EVIDENCE_REQUIRED` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC05` | Ngoại lệ - không có chứng từ nhưng có giải trình | 1 | `ACCOUNTANT_REVIEW` | `SET_PAPER_EVIDENCE_EXCEPTION` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC06` | Ngoại lệ - dùng chứng từ chuyển khoản thay thế | 2 | `ACCOUNTANT_REVIEW` | `SET_PAPER_EVIDENCE_EXCEPTION` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC07` | Hợp lệ - vé điện tử thay thế hóa đơn | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC08` | Không hợp lệ - chứng từ đính kèm không thuộc dòng nào | 3 | `REQUEST_INFO` | `SET_PAPER_UNMATCHED_001` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC09` | Không hợp lệ - khai báo hóa đơn nhưng không đính kèm file | 1 | `REQUEST_INFO` | `SET_PAPER_EVIDENCE_REQUIRED` | Đủ file |
| `testcase_uc3_v2/04_bang_chung_va_matching-TC10` | Cần xác nhận - evidence gần phù hợp nhưng chưa đủ chắc chắn | 2 | `REQUEST_INFO` | `SET_PAPER_MATCH_001` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC01` | Hợp lệ - ba hóa đơn cho một chuyến công tác | 4 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC02` | Hợp lệ - một hóa đơn phân bổ đúng cho hai dòng | 2 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC03` | Không hợp lệ - một hóa đơn bị phân bổ vượt giá trị | 2 | `REQUEST_INFO` | `SET_EVIDENCE_REUSE_001` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC04` | Hợp lệ - một dòng dùng hai hóa đơn gốc | 3 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC05` | Hợp lệ - hóa đơn gốc kèm bằng chứng thanh toán | 3 | `READY_FOR_APPROVAL` | `—` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC06` | Không hợp lệ - hóa đơn trùng định danh hồ sơ trước | 2 | `RECOMMEND_REJECT` | `SET_DUPLICATE_001` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC07` | Không hợp lệ - file đổi tên nhưng nội dung hóa đơn trùng | 2 | `RECOMMEND_REJECT` | `SET_DUPLICATE_001` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC08` | Ngoại lệ - hồ sơ có chứng từ gốc, thay thế và không chứng từ | 3 | `ACCOUNTANT_REVIEW` | `SET_PAPER_EVIDENCE_EXCEPTION` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC09` | Không hợp lệ - có chứng từ dư chưa được khai trong báo cáo | 4 | `REQUEST_INFO` | `SET_PAPER_UNMATCHED_001` | Đủ file |
| `testcase_uc3_v2/05_ho_so_phuc_hop-TC10` | Không hợp lệ - MST người mua sai đồng thời lệch số tiền | 2 | `RECOMMEND_REJECT` | `SET_BUYER_IDENTITY_001` | Đủ file |

## Kiểm tra cấu trúc và giới hạn

- Manifest: 75 case, tất cả expected.json parse được; lỗi đường dẫn/ID: **0**.
- Request/evidence được gold tham chiếu: **173 file**; **173 digest khác nhau**; **0 bản byte trùng lặp**. Trùng byte không tự là hồ sơ gian lận; có thể là fixture cố ý hoặc dữ liệu lặp.
- v1 gold dùng `request_document/evidence_documents`, `primary_rule`; v2 dùng `request_form/evidence_files`, `primary_rule_id`. Routine v1 `AUTO_PROCESS`, v2 `READY_FOR_APPROVAL` — cần mapping rõ tầng action/workflow khi import.
- Gold chứa fact tiện cho kiểm thử nhưng phải giữ ngoài runtime/model input; chạy PDF thật phải đi qua OCR/extraction thay vì đọc expected.
- v2 có `Donal Trump` trong trường employee; nguồn được gắn SYNTHETIC nhưng tên gợi cá nhân có thật. Trước dùng làm bài nộp, thay bằng tên giả không gợi người có thật; không suy rằng đã có consent.
- Gold expected/template không đủ chứng minh OCR đọc được hay pipeline kết luận đúng. Kiểm tra visual, LIVE extraction và independent holdout là bước riêng.
- Không tự xóa dữ liệu hoặc đổi corpus trong nhiệm vụ đọc code này.
- Nhãn gold `testcase_uc3`: `ACCOUNTANT_REVIEW`=1, `AUTO_PROCESS`=8, `ESCALATE`=4, `REQUEST_INFO`=12.
- Nhãn gold `testcase_uc3_v2`: `ACCOUNTANT_REVIEW`=5, `ESCALATE`=3, `READY_FOR_APPROVAL`=15, `RECOMMEND_REJECT`=5, `REQUEST_INFO`=22.

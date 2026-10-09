# Nguồn giả lập — Company coverage

Source COV-02, issuer ORG-DEMO-01, uploader/owner ACC-DEMO-01; tất cả synthetic. Scope03/10 tới08/10/2026 18:00 +07:00, đúng NV-DEMO-02/CT-DEMO-02 và hồ sơ/chứng từ liên quan.

Kế toán trong thế giới giả lập quan sát đủ bank/card/cash công ty, sổ requests/approvals/paymentattempts và lịch sử claim, cùng receipt phù hợp từ phía nhận cho events trong packet; không chỉ một account. Company-side scope không thay employee-side payments/absence; đọc employee source riêng.

[Ledger](financial_events_m1.csv) chứa toàn company money events trong scope. RawstatusSETTLED cần source receipt có amount/beneficiary/obligation, không tự đủ. Company trả vé3.000.000; không chi trực tiếp hotel/meal/ground hoặc companydirect khác. Không có ứng, đề nghị/approval/lệnh ứng còn hiệu lực hoặc employee nhận ứng cho công việc này. Xác định absence từ nguồn đủ scope, không từ thiếu row hoặc giả giao dịch0.

Không hoàn chi phí cho employee hoặc return advance/reimbursement company thực nhận; không vendorrefund phía công ty; không requests/attempt/pending có hiệu lực, overpayment/wrongrecipient, copyevents bị bỏ khỏi ledger hoặc nghĩa vụ unresolved khác. Không claim/history đã hoàn trả/pending phần đang xét ở hồ sơ khác. Quyết định/quyền không sửa/hủy/Stop tới mốc này. Không có quyết định quyết toán hoặc receipt chi/thu quyết toán ở mốc xét.

Absence có scope và owner quan sát các loại/phương thức/phía tiền liên quan, không tạo zeroevents. Không dùng cho người/công việc/ngày ngoài scope; source đến muộn phải re-check/version.

## decision-history

Trong nguồnquyếtđịnh côngty đủscope CT-DEMO-02 tới08/10 18:00, chỉ có quyếtđịnh cho phép côngviệc. Không có ngân sách tổng đượcduyệt trước hoặc quyếtđịnhchấpnhậnchi phí/phêduyệtquyếttoán sauphátsinh cho hồsơ này. Nguồnquyền AUTH-POST-02 cho phép quyếtđịnh nếu đượcđưa ra, không làdecision đãđưa ra. Companypaymentvé3 cósourceactualmoney riêng, không tựtạoB cho toàncôngviệc.

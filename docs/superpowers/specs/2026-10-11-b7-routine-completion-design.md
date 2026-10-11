# B7 — Hợp đồng hoàn tất đối soát và kiểm chứng đề A

Ngày: 11/10/2026. Trạng thái: **ĐỀ XUẤT ĐỂ REVIEW**; chưa thay Product,
Rulebook hoặc acceptance của các plan đang thực hiện. Đây là thiết kế nghiệm
thu, không là kết quả benchmark hoặc xác nhận đáp ứng đề từ Ban tổ chức.

## 1. Công việc hệ thống nhận

Đối soát hồ sơ quyết toán công tác của một nhân viên trong một công việc:
tổng hợp khoản chi có căn cứ, xác định phần công ty/nhân viên thực trả,
đối chiếu nguồn tiền đã ứng/hoàn/chi, áp dụng quy định và quyền liên quan,
lưu kết quả có căn cứ hoặc tạo yêu cầu giải quyết cụ thể cho đúng người.

Đơn vị tự hoàn tất là **job đối soát B7**, không toàn bộ quy trình chi tiền.
Ranh giới này là lập luận dự án cho đề A, chưa được BTC xác nhận. Không dùng
việc thu hẹp đơn vị chấm để che công việc thủ công còn lại.

So sánh ba hướng:

| Hướng | Giá trị và giới hạn |
| --- | --- |
| Chỉ đọc giấy và điền form | Giảm nhập liệu; chưa chứng minh đối soát hoặc chuyển tiếp nghiệp vụ |
| Hoàn tất đối soát có nguồn và chuyển đúng ngoại lệ — đề xuất | Phù hợp năng lực đang xây dựng; phải chứng minh đầu ra sử dụng được và công sức người còn lại |
| Tự duyệt tài chính/chi tiền | Mở rộng quyền và rủi ro; không cần để kiểm chứng job này, không thuộc thay đổi được đề xuất |

B3 vẫn phục vụ đề nghị tạm ứng, có tập đánh giá riêng. Không dùng việc xin
approval ban đầu ở B3 như bằng chứng chính rằng B7 phân biệt ngoại lệ tốt.

## 2. Đầu vào và điểm bắt đầu

Nhân viên nộp bảng kê và chứng từ phía mình. Phía công ty cung cấp nguồn
ngân sách/quyền/lịch sử tiền và coverage đúng người, công việc, sự kiện, mốc.
Nguồn công ty có thể import cho MVP; phải ghi đó là dữ liệu giả lập nếu là fixture.

Không bắt nhân viên tự tìm hoặc xác nhận thay lịch sử công ty. Chi phí
tìm/export/import nguồn được đo; không được làm sạch, sửa số hoặc ghép giao
dịch thủ công trước rồi gọi kết quả là pipeline đọc/ghép tự động.

Điểm bắt đầu first-pass: nhân viên đã nộp/xác nhận khai báo đầu vào. Xác nhận
bản nháp nhập ngoài là công sức chuẩn bị đầu vào, vẫn được ghi. Hồ sơ thiếu
hoặc mâu thuẫn được nhận và giữ trong mẫu số, không loại trước khi chạy.

## 3. Đầu ra hoàn tất phải sử dụng được

1. Bảng từng khoản/phần: giá trị, mục đích/phần công việc, actual payer,
   tình trạng đủ căn cứ hoặc vướng mắc, nguồn và quan hệ thanh toán.
2. Tổng T, B và E; lịch sử A/RA/P/RP giữ riêng; giá trị chưa rõ là null,
   không suy bằng 0. B là ngân sách có căn cứ quyết định, không phải dự toán.
3. S = E − (A − RA) − (P − RP) cùng scope/as-of, số nguyên VND và chiều
   công ty trả thêm / nhân viên hoàn lại / cân bằng. S chỉ được chốt khi
   mọi dữ kiện ảnh hưởng đủ; subtotal rõ không trở thành toàn bộ S.
4. Kiểm tra áp dụng: chất lượng, liên kết/trùng, eligibility, ngân sách,
   lịch sử và quyền; nêu rule, kết quả và căn cứ. NOT_APPLICABLE có lý do.
5. Mỗi kết luận quan trọng mở được nguồn tương ứng; locator chỉ hiển thị
   mức thực có. Link file đơn lẻ chưa chứng minh định vị field chính xác.
6. Report giữ run/input revision/policy/config/source identity và thời điểm,
   để truy lại kết quả. UI thường lệ dùng ngôn ngữ nghiệp vụ.
7. Nội dung chuyển tiếp nếu có: khoản/phần, đã biết gì, thiếu hoặc mâu thuẫn
   gì, cần người nào làm gì, căn cứ và phần bị chặn.

E là phần đủ điều kiện theo quy tắc trong kết quả đối soát; không đồng nghĩa
người có quyền đã phê duyệt tài chính. Calculated/proposed/approved/received
và closed giữ riêng. Report không tạo chứng cứ thực nhận mới hoặc tự đóng hồ sơ.

## 4. Điều kiện tính là thường quy tự hoàn tất

Trong scope đã công bố, đầu ra mục 3 đúng và được lưu qua cùng application
path, không có material issue mở, không lỗi kỹ thuật ngăn chấm; không cần
người sửa fact, chọn payer, ghép nguồn hoặc quyết định ngoại lệ trong job.
Không yêu cầu mở đủ mọi file hoặc trả lời câu hỏi nghi thức để report complete.

Một lần Run tự điều phối các bước phụ thuộc. Người dùng không phải bấm
đọc từng nguồn, match từng khoản và tính từng thành phần. Chạy lại sau
bổ sung là assisted, không đổi first-pass case thành routine thành công.

Kế toán có thể kiểm nguồn và lưu review; người có quyền quyết định tài
chính theo workflow hiện hành. Thiết kế này không bỏ các checkpoint đó.
Phải báo riêng số lần/công sức review/decision trên **mọi hồ sơ**, kể cả
routine; không dùng FP thấp để suy rằng mọi hồ sơ đều không cần con người.

Nếu thường quy vẫn buộc người làm lại đối soát từ đầu thì không đạt mục tiêu
giá trị. Nếu BTC hiểu routine là toàn bộ phê duyệt tài chính thì ranh giới
report này chưa đủ; không báo đã đạt rubric chỉ bằng nhãn COMPLETE.

## 5. Các kết quả cần phân biệt

| Kết quả | Hành vi |
| --- | --- |
| Đối soát hoàn tất | Lưu kết quả mục 3; không tạo câu hỏi giải quyết giả; chưa tự duyệt/chi |
| FACT | Hỏi đúng dữ kiện/source còn thiếu, giữ phần đã rõ; không chốt phần phụ thuộc |
| POLICY | Nêu rule và phần ngoài quy định; xin quyết định ngoại lệ nếu policy cho phép |
| AUTHORITY | Nêu quyết định cần có, scope/hạn mức còn thiếu và cấp có quyền cần xử lý |
| TECHNICAL | Nêu xử lý thất bại và phần chưa kiểm; không giả thành ngoại lệ nghiệp vụ |
| STOP/stale | Không công bố kết quả cũ như current hoặc mở action mới; giữ lịch sử |

Một hồ sơ có thể có nhiều nguyên nhân. Vượt ngân sách không tự là vượt quyền:
có thể người hiện tại đủ quyền quyết định ngoại lệ. Tách vi phạm rule và
khả năng quyết định ngoại lệ. Không resolve FACT bằng approval tài chính.

## 6. Năm tình huống đầu tiên — danh mục kiểm chứng dự kiến

Các số dưới đây tính theo triệu đồng; chỉ là scenario synthetic. Q IDs là
tham chiếu catalogue development, không prompt/production branches. Không
đổi bytes/expected của packet cũ để phù hợp output; nếu sửa oracle/source
phải version mới và ghi lý do. Mỗi scenario cần rà soát nguồn trước chạy.

| ID thiết kế | Tình huống | Kết quả phải chứng minh | Candidate cũ |
| --- | --- | --- | --- |
| V1 routine | T=8, B=8, company actual=3, E=5, A=2, RA=P=RP=0 có coverage | S=+3; nguồn payer/links/history đúng; không đòi quyết định ngoại lệ | Q01 |
| V2 routine | T=6,3 gồm company actual=3 và E=3,3; B=8; A=4, RA=P=RP=0 có coverage | S=−0,7; chiều đề xuất nhân viên hoàn; không tạo khoản công ty chi | Q03 |
| V3 routine | E=5, A=2, P=3, RA=RP=0, B/quyền/basis đủ | S=0; giữ chi đã nhận, không chi trùng; report complete không tự close | Q04 |
| V4 FACT | Có duyệt ứng nhưng chưa có căn cứ ứng đã thực nhận | A và S chưa rõ; hỏi kế toán chứng cứ thực nhận đúng khoản/mốc, không dùng approval thay receipt | Q11 |
| V5 POLICY | T>B có căn cứ, người nhận đủ quyền xem xét ngoại lệ | Nêu T/B/phần vượt và khoản liên quan; hỏi quyết định ngoại lệ, không tự nâng B hoặc chốt proposed vô điều kiện | Q13 |

V1/V3 là hai trạng thái liên quan cùng family trong corpus cũ: dùng Verify
chức năng, không tính là hai quan sát độc lập để chứng minh chất lượng.
Phải kiểm tra grant đủ nội dung/scope theo Rulebook R8, không chỉ abs(S).

Ngoài năm case demo, bắt buộc giữ testcase AUTHORITY (candidate Q14), chất
lượng số mờ, payer conflict, liên kết sai và source duplicate trong tập
ít nhất 15 case. Năm case này không phủ toàn đề hoặc thay holdout.

## 7. Cách nghiệm thu

- Oracle xác định từ source và policy snapshot trước nhìn output; source
  đủ không có nghĩa output đúng. Kiểm facts/links/tiền/issues/owner/state.
- Routine sai critical fact/link/số tiền/chiều hoặc cần human correction:
  FAIL. Không dùng S đúng tình cờ để bỏ qua lỗi ghép nguồn.
- Needs phải phát hiện đủ material issues, đúng loại và owner. Người nhận
  thấy dữ kiện/căn cứ cần thiết tại câu hỏi; không phải tự tìm toàn bộ hồ sơ.
- Phản hồi sai owner/thiếu căn cứ không resolve. Phản hồi đủ được kiểm lại;
  lưu báo cáo mới và lịch sử. Chưa đo được thì không khẳng định continuation tốt.
- Fake/replay xác minh rules/application. LIVE với originals xác minh
  reader/matching; UI walkthrough xác minh thao tác và khả năng mở căn cứ.
- Báo mọi run/failure/retry; missed/unnecessary escalation cùng denominator
  và technical failures; không gán failure thành routine thành công.
- Đo effort chuẩn bị, xử lý issue, review, quyết định và onboarding; research
  và agent review không thay thử nghiệm ít nhất 3 người làm nghiệp vụ thật.

## 8. Trình tự tiếp theo

1. Review ranh giới/output/case catalogue của tài liệu này.
2. Rà soát nguồn và oracle năm candidates; ghi gap hiện tại, không freeze
   B1 hoặc chạy model thật chỉ vì catalogue đã có.
3. Viết plan thay đổi tối thiểu cho câu hỏi, phân loại và runner/UI cần thiết;
   giữ UI review đang được agent khác sửa, tránh hai writer cùng file.
4. Kiểm fake rồi UI; LIVE theo authorization cho phép tương ứng. Ghi rõ
   capability chưa chạy/không đủ, không giả bộ Verify đã đạt.
5. Đo B7 trên tập độc lập và trial; feedback/adaptation có protocol riêng.

Bước 2 đã đối chiếu năm candidates tại
[review và bằng chứng](../../../output/reviews/2026-10-11-b7-step2-review.md).
Đã sửa mô tả V2 từ E=T=3,3 thành T=6,3/E=3,3 theo nguồn Q03; S vẫn −0,7.
Dataset gốc không sửa. Kết quả POLICY_REPLAY với facts/links nhập sẵn không
chứng minh đọc/ghép nguồn; năm packets chưa đủ làm suite LIVE hoặc freeze B1.

Nguồn: [đề A](../../Challenge_Brief_OrganizationAI_VN.docx.md),
[Product P4/P8](../../settlement/PRODUCT.md),
[Rulebook R1–R11](../../settlement/RULEBOOK.md),
[Evaluation E1–E7](../../settlement/EVALUATION.md),
[catalogue development](../../discovery/eval_development/CORPUS_INDEX.md).

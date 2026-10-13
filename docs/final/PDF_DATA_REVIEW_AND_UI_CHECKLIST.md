# Đánh giá PDF và checklist kiểm thử UI — InvoiceReferee final

Ngày 13/10/2026. Đây là kết quả review dữ liệu và danh sách kiểm thử cho người dùng;
không thay contracts, không đánh dấu sản phẩm đã đạt và không tự mở rộng profile.
Các checkbox UI đều chưa chạy trong lượt review này. Dữ liệu tiền bên dưới là
đầu vào đề xuất để hiện thực đúng tình huống đã chốt, chưa phải PDF mới đã được tạo.

## 1. Kết luận trước khi test

**Bộ `data/evaluation` chưa đủ điều kiện đánh giá OCR/LLM hay workflow LIVE.**
54/55 PDF có cùng nội dung và cùng ảnh render, không có số tiền. File còn lại là
một scan một trang. Những số tiền/tình huống chủ yếu nằm trong transcription/gold
JSON, không nằm trong nguồn PDF. Có thư mục và JSON đúng schema chưa chứng minh
có hồ sơ nghiệp vụ đầy đủ.

**Bộ `data/testcase_uc3` dùng được làm tài liệu tham khảo và test đọc/đối chiếu
chứng từ.** Chưa dùng nguyên đáp án cũ để chấm `final`: còn thiếu context/người trả/
thực nhận/lịch sử; nhiều case thuộc mua thiết bị, sửa chữa, tiếp khách chưa là
profile đã mở của `final`. Không dùng nhãn COVERED trong README như bằng chứng
code hiện tại xử lý đúng.

Không sửa/xóa PDF, gold, manifest hay generator trong lượt review. Không giải nén
RAR. Không gọi OCR/LLM tính phí, không chạy benchmark holdout hoặc pilot người thật.

## 2. Phạm vi và bằng chứng

| Bộ | PDF / trang | PDF mở/render lỗi | Nội dung text khác nhau | Ảnh render khác nhau |
| --- | ---: | ---: | ---: | ---: |
| evaluation: development15 + calibration10 + validation10 + holdout20 | 55 / 55 | 0 | 2 (gồm nhóm text rỗng của scan) | 2 |
| UC-03: 25 case tham khảo | 65 / 65 | 0 | 64 | 64 |

Đã trích text và render bằng PDFium toàn bộ 120 trang. Đã xem contact sheet của
65 PDF UC-03, hai hình evaluation khác nhau và năm mẫu phóng lớn bằng Poppler.
Các mẫu phóng lớn có tiếng Việt đọc được, bảng/chữ/số không có lỗi bố cục rõ ràng.
Điều này không thay thế kiểm đọc OCR thực hoặc kiểm từng ký tự ở mọi trang.
65 PDF UC-03 đều có font nhúng; không có trường chữ ký PDF `/Sig` được tìm thấy.
Chữ “Đã ký”/“Ký bởi” trong nội dung không được dùng làm quyền server.

Bằng chứng máy cục bộ (ignored, không phải bộ dữ liệu app):
- `.runtime/pdf-review-2026-10-13/inventory.json`: từng PDF, text/pages/font/hash/render.
- `.runtime/pdf-review-2026-10-13/summary.json`: các số đếm ở bảng trên.
- `.runtime/pdf-review-2026-10-13/field-audit.json`: kiểm nhãn payer/advance ở UC-03.
- `.runtime/pdf-review-2026-10-13/uc3-contact-1.jpg` đến `uc3-contact-7.jpg`.

CodeGraph báo up to date, 99 files; engine index là bản cũ, generation/coverage
chi tiết không được công cụ hiện có cung cấp. Generator/loader được đọc qua graph;
PDF/JSON được kiểm trực tiếp. Không tự re-index. Không nạp gold/*.json holdout từ
disk; đã kiểm nguồn raw và generator. Bộ holdout hiện có source clones và không
được claim là tập độc lập đủ chất lượng. Tập thay thế phải được khóa lại trước đánh giá.

## 3. Các vấn đề của evaluation

### E1 — Nguồn không chứa dữ kiện mà đáp án đòi hỏi

Ví dụ `development/dev-clean-chi/input/sources/chung-tu.pdf` chỉ có:

> HÓA ĐƠN / CHỨNG TỪ; Đơn vị cung cấp: Công ty Demo;
> Nội dung: Chi phí phục vụ hoạt động; Ngày: 05/10/2026.

Trong khi transcription khai T8m/E5m/C3m/A2m và allowed đòi chi3m. Người hoặc AI
chỉ đọc PDF không thể suy ra các số đó. `observable.amount=3m` còn là số tiền
kết quả đối soát, không phải trường đọc trực tiếp từ PDF này.

54 file text giống nhau và render giống nhau dù SHA file khác nhau; hash bytes
khác không làm nội dung nghiệp vụ độc lập. Thêm issuer/family/economic_key khác
vào manifest không tạo ra các định danh/biến thể nhìn thấy trên chứng từ.

### E2 — Tình huống chỉ nằm ở tên case/JSON

| Thư mục development | Vấn đề hiện tại |
| --- | --- |
| dev-clean-chi / dev-clean-thu / dev-balanced | Không có số tiền/người trả/ứng trên PDF để xác minh ba kết quả tiền |
| dev-relation-conflict | Không có hai chứng từ/quan hệ mâu thuẫn; facts giống thiếu history |
| dev-duplicate | Không có cặp nguồn/previous claim chứng minh trùng; key riêng, facts giống thiếu history |
| dev-personal | Observable nói loại500k nhưng nguồn không có khoản cá nhân; transcription E2m/A2m như hồ sơ cân bằng |
| dev-material-unsupported | PDF không biểu diễn ngoại tệ/refund/phần ngoài scope như tình huống đòi hỏi |
| dev-pending-bank | Không có biên nhận đang xử lý/trạng thái giao dịch nguồn |
| dev-mixed-pdf | Chỉ một trang ảnh, không phải nhiều trang/nhiều vai trò chứng từ |
| dev-supplementary | Chỉ snapshot cuối; chưa có hai đợt payment portions và instruction trước đó |

Scan duy nhất in rõ4.500.000 VND và “Người thanh toán: Ẩn”. Transcription lại
khai employee paid4.5m/advance4.5m/coverage. Không có nguồn đi kèm xác lập payer,
advance và coverage. Đáp án AUTO không được chứng minh từ hồ sơ PDF hiện có.

### E3 — Context và gold chưa khớp rulebook

- Tất cả organization.json trong development đặt B8m.
- dev-cost-authority: T=E12m > B8m và E>8m; không phải chỉ một AUTHORITY cô lập.
- dev-over-budget: T=E10m, A0 theo coverage; còn vượt quyền E8m và yêu cầu S4m.
  FACT/POLICY/AUTHORITY có thể đồng thời tồn tại; một route đơn không chấm đủ issue set.
- dev-supplementary: T10m > B8m nhưng allowed=AUTO/PAY4m; cần B>=10m hoặc ngoại lệ
  hợp lệ có căn cứ để đáp án routine này đúng.
- organization ghi opening0/coverage đủ ngay cả trong các case cố ý thiếu history;
  transcription lại bỏ coverage. Cần xác định record đó thật sự chứng minh scope/
  thời hạn/loại tiền nào, tránh hai tầng đầu vào phát biểu mâu thuẫn.
- Gold observable hiện quá mỏng: nhiều case `{}`; chưa có gold đủ cho từng critical
  fact và relation/source locator/issue-stage/dependency như hợp đồng đã chốt.

### E4 — Kiểm inventory chưa xác lập độc lập nguồn và toàn bộ gold

Input digests khớp cho55 packets ở lượt đọc hiện tại. Nhưng validator chủ yếu
so labels trong manifest; chưa phát hiện54 source render clones. `gold_digest`
hiện hash `latent.json`, không gồm observable/allowed. Thay đáp án allowed không
làm digest này đổi. Những kiểm tra đó cần được đóng trước khóa benchmark.

## 4. Đánh giá UC-03

Điểm dùng được: có tên người, số chứng từ, nhà cung cấp, dòng chi phí, subtotal/
thuế/tổng/bằng chữ; có báo cáo nhiều dòng và chứng từ thay thế. Các lỗi số học,
số/chữ, report–invoice, thiếu tệp trong các case âm là dữ liệu cố ý, không phải
file hỏng cần sửa cho khớp.

Giới hạn chung:
- Hóa đơn ghi “Chuyển khoản” không xác định người thực tế đã trả hay đã nhận.
- “Số tiền đã tạm ứng” trên giấy đề nghị là khai báo; cần record/receipt/xác nhận
  có trách nhiệm để xác lập A. Không thấy chứng từ P/R không chứng minh P=R0.
- Không có gói context cuối cùng gồm activity authorization, B, grant, opening/
  history coverage và nguồn xác nhận payer cho mỗi case. Context hợp lệ có thể
  ở server JSON/registry, không bắt nhân viên upload lại tất cả dưới dạng PDF.
- Hầu hết source là PDF native một trang, cùng kiểu trình bày; chưa đo scan mờ,
  lệch trang, nhiều trang, hidden-text/image conflict hay đa dạng mẫu thật.
- Những câu “Đã ký” là text mô phỏng, không tự đủ quyền duyệt trên app.
- Nhãn cũ AUTO_PROCESS/PENDING_APPROVAL/ACCOUNTANT_REVIEW và cap100m khác thiết kế
  final: routine tự kết luận/instruction, quyền E8m/abs(S)4m, approver20m.

| UC-03 | Cách dùng dưới thiết kế final |
| --- | --- |
| TC01–03 | Tham khảo chi/thu/cân bằng; cần payer/A/P/R/B/context. TC01 tiếp khách chỉ mở sau gate profile; TC02 mua thiết bị không thành travel bằng đổi nhãn |
| TC04 | Thiết bị83.6m không phải routine của final; không mở procurement/inventory ở bước này |
| TC05–08 | Tốt cho extraction/consistency số học/số-chữ/report–invoice; giữ lỗi cố ý, bổ sung context riêng nếu muốn test route hoàn chỉnh |
| TC09–10 | Buyer identity thiếu/sai là dữ kiện hoặc binding cần xác minh; không tự thêm luật thuế loại mọi khoản nếu policy final chưa quy định |
| TC11 | Tốt cho phát hiện invoice arithmetic; chưa là happy path tiền |
| TC12 | Invoice hiển thị trùng TC01 có chủ đích; cần chạy lần trước trong cùng tenant và đúng identity/owner; không tính như root/source độc lập |
| TC13 | Nếu đã chứng minh chi cá nhân: EXCLUDED và vẫn đối soát ứng. Không mặc định mọi rượu/bia luôn POLICY xin duyệt |
| TC14 | 121m thiết bị ngoài profile; cap100m của dữ liệu cũ không là ranh giới quyền final |
| TC15 | Sai nội dung/binding, dùng cho FACT; hoạt động sửa chữa chưa mở thành profile |
| TC16 | Báo cáo công tác3 hóa đơn, tổng10.26m. Có thể dùng đọc/match nhiều dòng; nếu E10.26m thì vượt8m, B cần có riêng. Không giữ nhãn AUTO cũ vô điều kiện |
| TC17 | Đọc tài liệu thay thế/ghép nhiều dòng; tiếp khách/cuộc họp cần gate profile |
| TC18 | Có xác nhận chuyển khoản và nghiệm thu, hữu ích để đọc quan hệ; phải kiểm payer thật. Nội dung sửa chữa chưa thành routine travel |
| TC19–21 | Tốt cho thiếu chứng từ/lý do/phần chưa đính kèm; quyết định ngoại lệ chỉ sau fact/policy/quyền đúng |
| TC22–23 | Test một source dùng nhiều dòng trong cùng root, không phải nhiều claimant; TC23 được tham khảo matching, không tự mở mua vật tư |
| TC24 | Tệp không có dòng report cần phân loại liên quan/chưa rõ/không liên quan; proven unrelated không blanket-block |
| TC25 | Report di chuyển900k vs phiếu thu700k: giữ hai giá trị, FACT; phiếu thu có người nộp tiền hữu ích cho payer/binding |

README TC20 ghi ESCALATE nhưng expected.json hiện ACCOUNTANT_REVIEW: phải đối chiếu
nguồn đáp án, không chấm theo README. Nhãn/expected từ nhánh tham khảo chưa là
policy hoặc bằng chứng sản phẩm của final.

## 5. Điều kiện một hồ sơ đủ để test workflow

- [ ] Có PDF/ảnh chứa đúng những trường được gắn là quan sát được; số bị che vẫn
      chưa rõ dù generator biết latent truth.
- [ ] Có định danh nhà cung cấp/chứng từ/ngày và binding nhân viên–hoạt động,
      hoặc xác nhận có trách nhiệm cho chi phí không có số chứng từ.
- [ ] Tách khai báo, chi phí phát sinh, payer/payment portions, và tiền A/P/R.
- [ ] Context server có B/authorization/grant/history đúng scope/time; P/R0 được
      xác lập bằng coverage, không do vắng file.
- [ ] Mỗi case thiếu/mâu thuẫn cố ý ghi rõ phần thiếu và issue set/dependencies;
      giữ các căn cứ khác đầy đủ để lỗi đích không bị che bởi thiếu context.
- [ ] Gold tách latent/observable/allowed, critical fact/ref/relation/disposition;
      người review đọc chính trang ảnh kiểm lại trước model run.
- [ ] Có phiên bản nguồn/rulebook và hash toàn input/gold; phát hiện source clones
      trước split. Cùng mẫu không tự chứng minh root độc lập hay unseen-family.
- [ ] Không upload expected/gold/transcription STUB trong LIVE; model không nhìn
      tên case gợi kết quả. Không dùng nhân viên/mã hoạt động cứng để chọn tiền.

## 6. Checklist UI sau sửa pipeline và chuẩn hóa dữ liệu

**Trạng thái toàn bộ mục dưới đây: NOT_RUN.** Các file evaluation hiện tại cần
viết lại trước khi đánh dấu DATA_READY. Đây là48 kiểm tra hành vi, không phải48
roots độc lập. Những mục tiền/control/UX dùng lại hoặc biến đổi hồ sơ D01–D15;
không cộng chúng vào mẫu benchmark như các hồ sơ mới.

Đơn vị tiền trong bảng: triệu VND. P/R ban đầu=0 chỉ khi coverage đã xác minh.
Mỗi hồ sơ tạo activity/root riêng trừ case trùng cố ý. Để test quyền/ngân sách
cô lập, cung cấp đủ những căn cứ không phải lỗi đích. Context ngoài UI phải được
seed/import có audit, không giả quyền bằng chọn persona.

### 6.1. 15 tình huống development cần có nguồn thật

| Chạy | ID / map thư mục | Đầu vào cần thể hiện bằng nguồn/context | Kết quả và điểm phải xem trên UI |
| --- | --- | --- | --- |
| [ ] | D01 dev-clean-chi | T8, employee paid5, company direct3, A2, B8, coverage đủ | E5/C3/S3; một yêu cầu chi3; company-direct không hoàn cho nhân viên; chưa ghi P |
| [ ] | D02 dev-clean-thu | T=E1.5, A2, B8, coverage đủ | Một yêu cầu thu0.5; không hiển thị chiều chi |
| [ ] | D03 dev-balanced | T=E2, A2, coverage đủ, không pending/execution/issue | BALANCED/SETTLED; không lệnh số0; có căn cứ cho0 |
| [ ] | D04 dev-payer-unknown | T5, chưa biết payer; A/P/R được xác lập riêng | FACT đúng owner, E/S chưa khẳng định. Sau chứng minh employee paid5 và A0, chuyển AUTHORITY cho S5; không coi một fact answer là đã đủ mọi gate |
| [ ] | D05 dev-relation-conflict | Hai nguồn cho hai activity/beneficiary khác nhau, cùng khoản3; nguồn không tự chọn một | FACT binding đúng owner, giữ hai refs; bổ sung xác nhận binding rồi recheck phần phụ thuộc |
| [ ] | D06 dev-over-budget | T10, E5, C3, unpaid2, A2, B8 | POLICY vì incurred T10>B8 dù mới trả8; không che vượt B bằng unpaid; quyết định ngoại lệ có quyền/scope mới tiếp tục |
| [ ] | D07 dev-cost-authority | T=E9, A6, B12 => S3 | AUTHORITY RECOGNIZE_COST vì E9>8 dù S3<=4; đúng cấp quyết định/không tự chia nhỏ |
| [ ] | D08 dev-action-authority | T=E8, A2, B8 => S6 | AUTHORITY ISSUE_PAYMENT vì6>4; không chia thành hai yêu cầu3 |
| [ ] | D09 dev-missing-history | E3 có proof, lịch sử trước kỳ/coverage A/P/R thiếu | FACT kế toán; A/S không suy0; record coverage hợp lệ mới tính tiếp |
| [ ] | D10 dev-duplicate | Cùng invoice identity/paid portion: scan và PDF ở cùng root; sau đó cùng invoice ở root khác | Same root tính một lần; khác root không phát hành hai lần, nêu canonical owner/FACT binding. ID/hash file khác không tạo khoản mới |
| [ ] | D11 dev-personal | Khoản cá nhân0.5 được chứng minh; A=P=R0 có coverage | EXCLUDED có amount/rule/reason/refs; E0/S0. Không dùng riêng BALANCED để chứng minh loại chi. Biến thể A2 => vẫn thu2 |
| [ ] | D12 dev-material-unsupported | Nguồn có khoản FX/refund vendor ảnh hưởng tiền, chưa có quy tắc trong scope | UNSUPPORTED/processing problem có ảnh hưởng/next action; không tự đổi sangVND hoặc kết luận tiền cuối |
| [ ] | D13 dev-pending-bank | Biên nhận ghi đang xử lý, chưa confirmed received; history thể hiện event chưa rõ | Không xác nhận thực nhận chỉ vì có file; pending/unknown chặn action phụ thuộc/hoàn tất |
| [ ] | D14 dev-mixed-pdf | PDF>=3 trang: invoice3, payment employee3, advance2; history/context đủ | Role theo page/unit; refs đúng trang, T/E3/A2/S1; một chi1. Không conflict chỉ vì invoice và payment khác role |
| [ ] | D15 dev-supplementary | Cùng invoice incurred10; đợt1 E5/C3/unpaid2/A3, B12 => I2 NOT_STARTED. Đợt2 employee paid thêm2 có portion key riêng | T vẫn10, E7/C3/unpaid0/S4; supersede remainder2, một I4 actionable; giữ lịch sử, không tính invoice hai lần |

**Cách chạy D01–D15:** chọn Nhân viên và hoạt động đúng context; đính kèm nguồn
→ kiểm preview/page/ref/unknown → xác nhận nộp → xem kết luận/câu hỏi → chuyển
đúng người để trả lời/quyết định → kiểm recheck/audit. Chưa ghi nhận actual nếu
chưa có chứng cứ tiền thật. Case kỹ thuật có thể cần injected failure ở môi trường
test; không bấm UI làm giả timeout rồi ghi đó là lỗi OCR quan sát được.

### 6.2. Thực hiện tiền — dùng root D01/D02 và các biến thể đã có căn cứ

| Chạy | ID | Thao tác | Phải thấy / không được xảy ra |
| --- | --- | --- | --- |
| [ ] | M01 | I3; ghi bank receipt confirmed received1 đúng người/root | P1/S2; cùng I remaining2, không lệnh chi2 mới |
| [ ] | M02 | Tiếp M01, nhận thêm2 bằng giao dịch khác | P3/S0, fulfilled3; hoàn tất chỉ khi mọi gate sạch |
| [ ] | M03 | I3; phiếu chi tiền mặt3 và xác nhận nhận đúng scope | Cùng phép tính như bank; upload/xác nhận có căn cứ, không phương thức làm thay đổi tiền |
| [ ] | M04 | Root D02, nhận employee return0.5 | R0.5/S0; đúng chiều người nộp/công ty nhận |
| [ ] | M05 | Upload bank pending/failed, hoặc chỉ nhập amount thiếu proof/completion | Không tự CONFIRMED/ALLOCATED; không SETTLED giả |
| [ ] | M06 | Receipt payee khác nhân viên của root | Giữ event quan sát/incident; không cộng vào P của sai người |
| [ ] | M07 | Gửi lặp cùng command; rồi command khác cùng external bank key | Một event/fulfillment; replay đúng historical result |
| [ ] | M08 | Cùng external key nhưng đổi payee/scope/amount/kind | Conflict rõ, không âm thầm dùng bản cũ hoặc nhận lần nữa |
| [ ] | M09 | I3 nhưng xác minh nhận4 | P4 không cắt3; fulfill tối đa3; incident1, không tự chi/thu bù chưa được xử lý |
| [ ] | M10 | Linked reversal của P1 hợp lệ | NetP giảm1, R không tăng; netremaining mở lại; duplicate/over-reversal bị chặn |
| [ ] | M11 | Tiền đã xảy ra trái quyền; người có quyền xác minh event đúng scope | Tiền thật vẫn vào phép tính; incident/governance riêng chặn action mới khi cần |
| [ ] | M12 | Old I4 đã fulfill2 và supersede/new I4; reverse oldP2 => S6 | Predecessor không sống lại; grant4=>AUTHORITY; OPEN/UNKNOWN còn phải xác minh trước replacement |

### 6.3. Phản hồi, quyền và điều khiển

| Chạy | ID | Tình huống | Điều kiện PASS |
| --- | --- | --- | --- |
| [ ] | H01 | Đúng owner trả lời FACT với value/refs/binding có trách nhiệm | Lưu phản hồi và evidence riêng; issue đã đủ được giải, recheck đúng phần, không quay OPEN vì value bị bỏ |
| [ ] | H02 | Sai owner hoặc câu trả lời chỉ “đồng ý” không giải fact | Không áp dụng; nêu cần gì/ai, không cấp tiền |
| [ ] | H03 | Trả lời/decision từ case_version hoặc material basis cũ | Không ghi đè state mới; conflict/history rõ, reload không mất bản người dùng cần bổ sung |
| [ ] | H04 | Grant sai action/scope/profile, hết hạn, amount trên20m, revoke trước commit | Chặn đúng quyết định; role/persona không thay grant; grant activity khác không đủ |
| [ ] | C01 | Stop khi reader đang chạy; release worker muộn | Không instruction/financial commit muộn; epoch/audit đúng; nguồn/result cũ không trở thành basis mới |
| [ ] | C02 | Record actual có proof khi STOPPED | Giữ actual và audit; không tự issue/restart xử lý tiền trong Stop |
| [ ] | C03 | MarkExecution OPEN → Stop → Resume chưa xác minh đợt ngoài app | Giữ UNKNOWN/suspended; không reset NOT_STARTED bằng INSERT OR REPLACE, không chi lặp |
| [ ] | C04 | Restart giữa READ/ASSESS; receipt/retry lại | Job/counters/read-set từ DB; không mất submit, reset recovery quota hoặc lặp effects |

### 6.4. UI và sử dụng thực tế

| Chạy | ID | Thao tác | Điều kiện PASS |
| --- | --- | --- | --- |
| [ ] | UX01 | Chuyển Nhân viên/Kế toán/Người có quyền | Workspace/hành động đúng vai trò; backend vẫn bảo vệ quyền; không một form cho cả ba |
| [ ] | UX02 | Upload nativePDF, scanPDF, PNG/JPEG; mở refs | Đúng tệp/page/excerpt; nguồn gốc giữ nguyên sau correction; số chưa rõ không ép đoán |
| [ ] | UX03 | Đọc riêng card FACT/POLICY/AUTHORITY | Có known facts/scope/rule/amount/action/impact/source excerpt; một câu trả lời hợp lệ cho issue, không bắt tra cứu lại toàn hồ sơ |
| [ ] | UX04 | Provider failed, giới hạn size/pages, staleversion | Tiếng Việt dễ hiểu, không enum/trace ở luồng chính; có trạng thái và bước xử lý cụ thể; không báo thiếufact như đã đọc xong |
| [ ] | UX05 | Hai session độc lập tạo/read/Verify/reset | Không thấy hoặc sửa dữ liệu tenant khác; mới hết session không mất hoặc dùng nhầm root |
| [ ] | UX06 | Mở audit của submit/answer/decision/actual/Stop | Có actor/time/input snapshot/why/effect/refs; trạng thái hiển thị khớp server, không chỉ message thành công |

### 6.5. Verify, bằng chứng và ngưỡng

| Chạy | ID | Kiểm tra | Điều kiện PASS |
| --- | --- | --- | --- |
| [ ] | V01 | Core4 bằng một nút: D01/D02/D03/D11 | Chính xác4 case tuần tự; PASS/FAIL/timestamp/actual; D11 disposition EXCLUDED thật |
| [ ] | V02 | Escalation5: D01/D02/D03/D04/D07 | Chính xác5, 3routine+2human; câu hỏi cụ thể; D06 POLICY test riêng, không đổi5 thành6 |
| [ ] | V03 | Cố ý sai chiều chi/thu, amount, owner, quote/page/source digest | Scorer fail dựa evidence thật; refs_ok không hardcodeTrue |
| [ ] | V04 | False BALANCED/S0 khi FACT/POLICY/AUTHORITY còn cần xử lý | Unsafe affirmative counted; union theo root, không lệnh tiền vẫn có thể là dangerous miss |
| [ ] | V05 | LIVE/replay/STUB trên cùng luồng, packet không chép sẵn vào LIVE | Có calls/config/mode/outputs đúng; không nhãn LIVE mà dùng transcription; không gold vào app/model |
| [ ] | V06 | Bộ dữ liệu đã sửa, khóa source/context/gold/prompt/model trước holdout mới | Source-clone và toàn gold digest kiểm đủ; giữ attempts/technical failures/N; fix theo holdout thì không claim lần sau độc lập |
| [ ] | V07 | T11 paired recovery-vs-human trên calibration/validation đủ nguồn/opportunities | Cùng initial basis/sources/quota, actual R recording, changed-route gain/unsafe gates, verified feedback; synthetic clicks không thành feedback thật |

## 7. Ghi kết quả mỗi lần test

Không sửa “expected” cho giống output. Mỗi lần ghi:

| Case / thời điểm | Commit / mode / model | Root / source hashes / context version | Expected | Actual / refs | PASS / FAIL / NOT_RUN / DATA_BLOCKED | Bằng chứng / lỗi |
| --- | --- | --- | --- | --- | --- | --- |
| Chưa chạy | | | | | NOT_RUN | |

PASS test đọc không phải PASS workflow. PASS STUB không phải PASS LIVE. PASS một
issue không phải cả root đã tự hoàn tất. Chỉ mark checkbox sau khi hành vi và
bằng chứng đúng; hiện data evaluation cần sửa nên UI/LIVE business cases là
DATA_BLOCKED về đầu vào, không quy hết failure cho model.

## 8. Việc cần làm tiếp theo từ review dữ liệu

1. Giữ UC-03 làm reference, chọn một hồ sơ công tác nhiều dòng làm mẫu trình bày;
   điều chỉnh số/payer/context đúng final. Không import nguyên expected/rules cũ.
2. Sửa generator để từng PDF thực sự chứa dữ kiện của case; tạo các source
   invoice/payment/advance/history đúng vai trò. Company context có căn cứ được
   cấp sẵn, không thêm gánh nặng nhập/upload không cần cho nhân viên.
3. Hiện thực đủ15 development roots bằng raw sources độc lập; scenario âm cố ý
   chỉ thiếu/mâu thuẫn dữ kiện mục tiêu và có gold đủ tầng/issue set.
4. Chạy thử D01/D02/D03/D04/D06/D07 qua pipeline đã sửa; phân biệt data defect,
   read/extraction defect, workflow defect và scoring defect.
5. Sau development ổn định mới làm calibration/validation/holdout thay thế hợp
   lệ. Không dùng54 nguồn giống nhau để claim khả năng tổng quát.

Nguồn kiểm trực tiếp: generator `scripts/build_packets.py`; loader/digest
`src/invoice_referee/evaluation/packets.py`; design §1–4; contracts §3–7/10–11;
120 PDF và JSON development/UC-03 tại snapshot hiện tại. Đây là QA và test
readiness review, không kiểm giá trị pháp lý/thuế của mẫu tổng hợp.

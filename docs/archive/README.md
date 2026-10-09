# Lưu trữ lịch sử — không phải context coding mặc định

Ngày 09/10/2026. Nội dung hiện hành: [Product](../settlement/PRODUCT.md), [Rulebook](../settlement/RULEBOOK.md), [System](../settlement/SYSTEM.md), [Evaluation](../settlement/EVALUATION.md) và [plan](../superpowers/plans/2026-10-09-settlement-mvp.md).

[discovery-2026-10-09.zip](discovery-2026-10-09.zip) giữ 364 file gốc trước hợp nhất, nguyên bytes và repository-relative paths. [MANIFEST.json](MANIFEST.json) có SHA256 từng entry và archive, bảng provenance/section mapping, cùng kết quả kiểm tra. Archive gồm cả bản dự phòng dataset; bản dataset hoạt động vẫn giữ nguyên tại đường dẫn cũ.

Archive chứa các quyết định cũ, phương án đã bỏ, raw reviews/targets/metadata, research, roadmap và spec/plan 04-10. Không dùng các giới hạn/category caps/role cũ làm policy hiện hành. Approval thiết kế không là runtime verified. Các raw verdict/hash không bị sửa vì kết luận sau thay đổi.

`source_path` trong manifest dataset có thể chỉ tới một origin lịch sử đã nằm trong archive. Dùng `snapshot_path` và hash đúng packet để đánh giá. Không so hash của pointer Markdown ở đường dẫn cũ với hash nguyên bản; nguyên bản nằm trong ZIP và manifest lưu trữ. Các citations lịch sử được giải quyết bằng repository-relative entry name trong ZIP, không cần agent load toàn archive.

Muốn tra nguyên bản, giải nén vào thư mục riêng, không ghi đè working tree:

```bash
rtk proxy python3 -m zipfile -e docs/archive/discovery-2026-10-09.zip /tmp/invoice-referee-original-docs
```

Kiểm tra SHA256 bằng MANIFEST trước dùng làm provenance. Không tự khôi phục old specs vào source authority hoặc coi backup là commit/Git history. Việc dọn không sửa code, kích hoạt policy, chạy provider hoặc đo chất lượng.

Kết quả dọn ngày 09/10: đưa 90 file lịch sử ra khỏi cây tài liệu hoạt động;
giữ 9 file chỉ dẫn tại những đường dẫn cũ cần tra cứu. Số Markdown chưa được Git
theo dõi giảm từ 244 xuống 173; phần lớn còn lại là dữ liệu đánh giá được giữ có
chủ đích. Đây là số file, không phải phép đo lượng token hoặc context thực nạp.

Đã thử khôi phục 364 file gốc vào thư mục riêng và kiểm tra SHA256; 261 file trong
hai bộ dữ liệu còn giữ khớp nguyên bản. Đã kiểm liên kết/anchors của tài liệu hiện
hành và các file chỉ dẫn, mã SYS-01–17/C01–07, đề gốc và nội dung task trong plan.
Kết quả chi tiết và giới hạn nằm trong trường `verification` của MANIFEST.
Chưa render Mermaid, chạy ứng dụng hoặc đo chất lượng AI trong lượt dọn này.

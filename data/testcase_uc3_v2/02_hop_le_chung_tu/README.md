# Hợp lệ chứng từ trước đối chiếu

Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.

| Case | Tình huống | Kết quả kỳ vọng | Rule chính |
| --- | --- | --- | --- |
| 02_hop_le_chung_tu-TC01 | Hợp lệ - hóa đơn điện tử đủ trường bắt buộc | READY_FOR_APPROVAL | - |
| 02_hop_le_chung_tu-TC02 | Không hợp lệ - hóa đơn điện tử thiếu MST người mua | REQUEST_INFO | SET_DOCUMENT_REQUIRED_FIELDS_001 |
| 02_hop_le_chung_tu-TC03 | Không hợp lệ - MST người mua thuộc công ty khác | RECOMMEND_REJECT | SET_BUYER_IDENTITY_001 |
| 02_hop_le_chung_tu-TC04 | Không hợp lệ - hóa đơn điện tử thiếu số hóa đơn | REQUEST_INFO | SET_DOCUMENT_REQUIRED_FIELDS_001 |
| 02_hop_le_chung_tu-TC05 | Không hợp lệ - MST người bán sai định dạng | REQUEST_INFO | SET_DOCUMENT_REQUIRED_FIELDS_001 |
| 02_hop_le_chung_tu-TC06 | Hợp lệ - vé máy bay điện tử là chứng từ gốc | READY_FOR_APPROVAL | - |
| 02_hop_le_chung_tu-TC07 | Không hợp lệ - bằng chứng chuyển khoản chưa hoàn tất | REQUEST_INFO | SET_DOCUMENT_VALIDITY_001 |
| 02_hop_le_chung_tu-TC08 | Không hợp lệ - không phân loại được chứng từ | REQUEST_INFO | SET_DOCUMENT_CLASSIFICATION_001 |
| 02_hop_le_chung_tu-TC09 | Không hợp lệ - tiền hàng và tổng thanh toán không nhất quán | REQUEST_INFO | SET_DOCUMENT_CONSISTENCY_001 |
| 02_hop_le_chung_tu-TC10 | Không hợp lệ - hóa đơn ghi người mua là khách lẻ | REQUEST_INFO | SET_DOCUMENT_REQUIRED_FIELDS_001 |

# Báo Cáo Kiểm Thử Độc Lập Playwright LIVE: TC02 & TC03 (Hoangha)

**Ngày kiểm thử:** 14/10/2026  
**Nhánh:** `final` (commit `bd9e8769`)  
**Môi trường:** Isolated Live Runtime (`PORT=8095`, Mistral OCR Live + X-Kiro LLM Live `qwen/qwen3.7-flash:free`, Playwright Headless Chromium)  
**Phạm vi:** Kiểm thử độc lập trên 2 test case Hoangha ngoài danh sách (TC02 & TC03). Toàn bộ mã nguồn ứng dụng (`src/`) được bảo toàn nguyên vẹn 100%, không sửa code để ép test pass.

---

## 1. Thiết Lập Ground Truth Thị Giác Độc Lập (Visual PDF Analysis)

Người kiểm thử đã trích xuất trực tiếp các trang PDF thành ảnh PNG 150 DPI và phân tích thị giác để lập Ground Truth, không dựa vào `expected.json`:

| Case | Chứng từ gốc (PDF) | Nội dung đọc trực quan từ ảnh | Kết luận Ground Truth |
| :--- | :--- | :--- | :--- |
| **TC02** | `report_hoan_ung.pdf`<br>`hoa_don_dien_tu.pdf` | - Người đề nghị: **NGUYỄN MINH AN**<br>- Nội dung: Mua thiết bị văn phòng phục vụ công ty<br>- HĐ số: **00000201** (Công ty Tiến Phát)<br>- Mặt hàng: 1 Máy in Canon LBP 2900 (4.000.000 đ) + 2 Hộp mực Canon 303 (1.000.000 đ) = 5.000.000 đ + VAT 8% (400.000 đ) = **5.400.000 đ**<br>- Tạm ứng trên giấy: **5.000.000 đ**<br>- Đề nghị thanh toán thêm: **400.000 đ** | **$T = 5.400.000$ ₫**<br>**$E = 5.400.000$ ₫**<br>**$A = 5.000.000$ ₫**<br>**$S = +400.000$ ₫**<br>Lệnh chi: **PAY 400.000 ₫** |
| **TC03** | `report_hoan_ung.pdf`<br>`hoa_don_dien_tu.pdf` | - Người đề nghị: **NGUYỄN MINH AN**<br>- Nội dung: Chi phí lưu trú công tác<br>- HĐ số: **00000301** (Khách sạn Sài Gòn Ban Mê)<br>- Dịch vụ: Phòng nghỉ (4 đêm x 1.000.000 đ = 4.000.000 đ) + VAT 8% (320.000 đ) = **4.320.000 đ**<br>- Tạm ứng trên giấy: **4.320.000 đ**<br>- Chênh lệch: **0 đ** | **$T = 4.320.000$ ₫**<br>**$E = 4.320.000$ ₫**<br>**$A = 4.320.000$ ₫**<br>**$S = 0$ ₫**<br>Trạng thái: **SETTLED**<br>Lệnh chi/thu: **Không có** |

---

## 2. Kết Quả Kiểm Thử Thực Tế Qua Web UI (Playwright Headless + Live Backend)

| Giai đoạn luồng người dùng | TC02 (Mua thiết bị VP) | TC03 (Lưu trú công tác) | Đánh giá |
| :--- | :--- | :--- | :--- |
| **Tải chứng từ (Upload)** | Chọn và tải 2 file PDF thật (`report_hoan_ung.pdf`, `hoa_don_dien_tu.pdf`). UI hiển thị danh sách 2 tệp sẵn sàng. | Chọn và tải 2 file PDF thật. UI hiển thị danh sách 2 tệp sẵn sàng. | **PASS** |
| **Trích xuất bản nháp (Draft)** | Live OCR + LLM đọc từ file thật:<br>- Chi phí: **5.400.000 ₫**<br>- Số HĐ: **00000201**<br>- Ứng kê khai: **5.000.000 ₫**<br>- Chênh lệch: **400.000 ₫ (Công ty chi thêm)** | Live OCR + LLM đọc từ file thật:<br>- Chi phí: **4.320.000 ₫**<br>- Số HĐ: **00000301**<br>- Ứng kê khai: **4.320.000 ₫**<br>- Chênh lệch: **0 ₫ (Cân bằng kê khai)** | **PASS** (Khớp 100% Ground Truth thị giác) |
| **Nộp hồ sơ (Submit)** | Chọn hoạt động và nộp thành công. Backend tạo hồ sơ đối soát, chạy background job đối soát. | Chọn hoạt động và nộp thành công. Backend tạo hồ sơ đối soát, chạy background job đối soát. | **PASS** |
| **Hiển thị Dossier View** | - Header: `Hồ sơ v3`<br>- Tổng chi $T$: **5.400.000 ₫** (KNOWN)<br>- $E, A, S$: `—` (UNKNOWN do vướng issue)<br>- Trạng thái: `Chờ xử lý ngoại lệ` (WAITING) | - Header: `Hồ sơ v3`<br>- Tổng chi $T$: **4.320.000 ₫** (KNOWN)<br>- $E, A, S$: `—` (UNKNOWN do vướng issue)<br>- Trạng thái: `Chờ xử lý ngoại lệ` (WAITING) | **PARTIAL** (Đúng logic bảo vệ tài chính khi thiếu xác nhận thanh toán cá nhân) |
| **Trình xem chứng từ (DocumentViewer)** | Khung trái hiển thị đầy đủ các tab tài liệu PDF (`report_hoan_ung.pdf`, `hoa_don_dien_tu.pdf`), có nút mở tab mới. | Khung trái hiển thị đầy đủ các tab tài liệu PDF, chuyển đổi mượt mà. | **PASS** |
| **Bảo toàn dữ liệu khi reload** | Tải lại trang (F5), hồ sơ được khôi phục nguyên vẹn từ backend SQLite. | Tải lại trang (F5), hồ sơ được khôi phục nguyên vẹn. | **PASS** |

---

## 3. Các Lỗi Phát Hiện & Đề Xuất Khắc Phục (Defect Log)

Trong quá trình kiểm thử độc lập, 5 vấn đề cốt lõi đã được phát hiện và cô lập:

### 🔴 Lỗi 1 (Blocker - Codebase Crash): `NameError: _activity_references`
- **Vị trí:** `src/invoice_referee/workflow/service.py:1008`
- **Mô tả:** Nhánh `final` có thay đổi dở dang từ agent khác (thêm cột `references_json` vào `schema.sql` và `db.py`), trong hàm `CaseWorkflow.catalog()` gọi `references=_activity_references(row)` nhưng **quên định nghĩa hàm `_activity_references`**.
- **Hậu quả:** Khi người dùng vào Dashboard, endpoint `GET /api/demo/session` lập tức bị crash với mã lỗi 500, treo toàn bộ ứng dụng web ở màn hình "Đang kết nối... Lỗi 500".
- **Đề xuất fix:** Định nghĩa hàm helper trong `service.py`:
  ```python
  def _activity_references(row: sqlite3.Row) -> tuple[str, ...]:
      if "references_json" not in row.keys() or not row["references_json"]:
          return ()
      try:
          raw = json.loads(row["references_json"])
          return tuple(str(x) for x in raw if x) if isinstance(raw, list) else ()
      except Exception:
          return ()
  ```

### 🔴 Lỗi 2 (Architectural Disconnect): Vòng lặp giải trình vô tận (Infinite Question Loop)
- **Vị trí:** Giữa `policy.py:183` và `reconciliation/admission.py`
- **Mô tả:** Khi hóa đơn mang tên công ty và không ghi người mua cá nhân, `policy.py` phát hiện chưa có người trả và sinh issue với key `field_or_rule = "expense:payer"`. Khi nhân viên bấm "Gửi giải trình", backend ghi nhận confirmation với key `"expense:payer"`. Tuy nhiên, trong chế độ LIVE (`admit_evidence` ở `admission.py`), hệ thống **hoàn toàn không đọc key `"expense:payer"`** từ confirmations (chỉ có code STUB trong `snapshots.py` mới đọc).
- **Hậu quả:** Dù nhân viên đã gửi giải trình và hồ sơ đã tăng version (từ v3 lên v4), lần đối soát tiếp theo vẫn không nhận được người trả, khiến $E$ tiếp tục là UNKNOWN và `policy.py` lại sinh ra issue `"expense:payer"` một lần nữa. Người dùng bị kẹt vô tận trong form giải trình.
- **Đề xuất fix:** Trong `admission.py`, bổ sung kiểm tra confirmation `expense:payer` tương tự như `snapshots.py` để công nhận tư cách chi trả của nhân viên khi nhân viên đã xác nhận có trách nhiệm.

### 🟡 Lỗi 3 (Data Flow Truncation): Bỏ qua Coverage trong Live Assessment
- **Vị trí:** `src/invoice_referee/workflow/evidence_assessment.py:125`
- **Mô tả:** Khi gọi `admit_evidence()`, code đang truyền cứng `coverage=None` thay vì truyền `coverage=organization.coverage`.
- **Hậu quả:** Mọi hồ sơ đi qua luồng LIVE đều bị gán lỗi "Thiếu lịch sử đối chiếu ứng/hoàn cho scope này" (issue `ledger:coverage`), khiến $A$ và $S$ không thể tự động tính toán mà bị đẩy sang diện chờ Kế toán duyệt ngoại lệ.
- **Đề xuất fix:** Thay `coverage=None` bằng `coverage=organization.coverage` tại dòng 125 của `evidence_assessment.py`.

### 🟡 Lỗi 4 (UI/UX Mismatch): Form giải trình người trả không có hướng dẫn định dạng
- **Vị trí:** `frontend/src/features/questions.tsx`
- **Mô tả:** Backend mong đợi trường `value` là Actor ID (`employee:employee-a`) hoặc số tiền xác nhận để đối soát mã định danh, nhưng UI lại hiển thị một ô `<textarea>` tự do với nhãn chung chung "Nội dung giải trình / xác nhận:". Người dùng gõ text giải trình bằng chữ thông thường thì backend không khớp được.
- **Đề xuất fix:** Thay ô `<textarea>` tự do bằng dropdown chọn đối tượng chi trả ("Tôi (Nhân viên đề nghị)", "Công ty chi trả trực tiếp", "Đối tác khác") kết hợp trường ghi chú giải trình.

### 🟡 Lỗi 5 (Resilience): Timeout gọi LLM quá ngắn khi tải mạng cao
- **Vị trí:** `src/invoice_referee/evidence/trace.py:25` (`DEFAULT_LLM_TIMEOUT_S = 60`)
- **Mô tả:** Khi sử dụng mô hình free `qwen/qwen3.7-flash:free` qua internet, vào giờ cao điểm thời gian phản hồi có thể mất hơn 60s, dẫn đến lỗi `httpcore.ReadTimeout` làm sập API `/settlement/draft` (HTTP 500).
- **Đề xuất fix:** Tăng `DEFAULT_LLM_TIMEOUT_S` lên 120s hoặc 180s.

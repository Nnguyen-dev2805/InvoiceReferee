# Kế hoạch Triển khai: Bố cục Master - Detail Workspace (Phương án 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển đổi giao diện InvoiceReferee sang kiến trúc chuẩn **Master - Detail Workspace** (Cột trái cố định luôn chứa danh sách hồ sơ & nút tạo mới; Cột phải là Workspace hiển thị Form tạo mới hoặc Chi tiết hồ sơ có tab), chấm dứt hoàn toàn tình trạng danh sách hồ sơ bị chìm xuống đáy và layout co giật khi chuyển trạng thái.

**Architecture:** Bố cục cố định 2 cột (`grid-master-detail`: `340px minmax(0, 1fr)`) trên màn hình desktop. Cột trái (Sidebar) luôn giữ nút `+ Tạo hồ sơ mới`, danh sách 24+ thẻ hồ sơ tương tác (có thanh cuộn độc lập `overflow-y: auto`), và panel Verify. Cột phải (Workspace) chuyển đổi mượt mà giữa: (1) Form nộp hồ sơ B3/B7 khi chưa chọn hồ sơ hoặc bấm tạo mới; và (2) Chi tiết hồ sơ với 5 Tab nghiệp vụ khi chọn một hồ sơ.

**Tech Stack:** React 18, TypeScript, CSS Variables Design System (`styles.css`), Vitest, Testing Library.

**Spec:** [docs/settlement/PRODUCT.md](file:///Users/tnhatnguyendev2805/Documents/Projects/InvoiceReferee/docs/settlement/PRODUCT.md) & [ui_layout_options_comparison.md](file:///Users/tnhatnguyendev2805/.gemini/antigravity/brain/e5a10845-1c2f-4a04-a453-e247de15e34f/ui_layout_options_comparison.md).

## Global Constraints

- Tuân thủ nghiêm ngặt các nguyên tắc tài chính: số nguyên VND, Decimal arithmetic, không làm thay đổi logic xác thực và nghiệp vụ B3/B7.
- Không phá vỡ bất kỳ test nào trong bộ kiểm thử frontend (17 files test, 82 unit tests phải tiếp tục PASS 100%).
- Đảm bảo tương thích responsive: trên mobile (< 1024px) tự động stack 1 cột, trên desktop (>= 1024px) chia 2 cột cố định 340px / 1fr.
- Đảm bảo tiếp cận WCAG 2.1 AA: tương phản >= 4.5:1 cho text, touch target >= 44px, focus outline rõ ràng.

---

## Kiến trúc Bố cục Chi tiết (Component Hierarchy)

```
<App>
  ├── <header className="app-head"> (Branding + Demo Role Switcher)
  └── <div className="grid grid-master-detail">
        │
        ├── <section className="col col-sidebar"> (Cột trái cố định 340px)
        │     ├── <div className="new-case-banner">
        │     │     └── <button onClick={() => setView(null)}>➕ Tạo hồ sơ mới</button>
        │     ├── <div className="panel case-list-panel">
        │     │     ├── Tiêu đề "Hồ sơ" + Badge đếm số lượng
        │     │     └── <div className="case-list-scrollable">
        │     │           └── [24 thẻ hồ sơ tương tác .case-item-card]
        │     └── <div className="panel" data-testid="verify-container">
        │           └── <VerifyPanel /> (Collapsible)
        │
        └── <section className="col col-main"> (Cột phải ~75% màn hình)
              │
              ├── [TRƯỜNG HỢP 1: view === null] ──> FORM TẠO HỒ SƠ MỚI
              │     ├── <div className="tab-nav"> (B3 Tạm ứng / B7 Quyết toán)
              │     ├── <div data-testid="b3-intake-panel"> (Form B3: Web/Import)
              │     └── <div className="panel"> (Form B7)
              │
              └── [TRƯỜNG HỢP 2: view !== null] ──> CHI TIẾT HỒ SƠ & BÁO CÁO
                    ├── <div className="case-header-panel"> (Mã, loại, trạng thái, số tiền)
                    ├── Alert Banners (Nếu có câu hỏi AI hoặc bản nháp cần duyệt)
                    ├── SummaryCard (nếu có)
                    ├── <div className="case-tabs-nav"> (5 Tabs nghiệp vụ)
                    └── Tab Panels:
                          ├── Tab 1: 📊 Kết quả & Báo cáo (<ReportPanel />, <ActionsPanel />)
                          ├── Tab 2: ✍️ Bản nháp B3 (<B3IntakeForm />, lý do, xác nhận)
                          ├── Tab 3: 📎 Nguồn chứng từ (Upload file, danh sách file)
                          ├── Tab 4: 💬 Câu hỏi giải trình (<QuestionsPanel />)
                          └── Tab 5: 📜 Lịch sử & Kỹ thuật (Run trace, audit timeline)
```

---

## Danh sách Task Thực hiện

### Task 1: Cập nhật CSS Layout Master - Detail & Sidebar Scroll
**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: CSS tokens (`--color-*`, `--space-*`, `--radius`)
- Produces: `.grid.grid-master-detail`, `.col-sidebar`, `.col-main`, `.case-list-scrollable`

- [x] **Step 1: Viết quy tắc CSS cho `.grid.grid-master-detail` và thanh cuộn sidebar**
  - Cấu hình grid 2 cột trên desktop (`340px minmax(0, 1fr)`).
  - Thêm `.case-list-scrollable` với `max-height: calc(100vh - 260px)`, `overflow-y: auto`, thanh cuộn mảnh tinh tế (`scrollbar-width: thin`).
  - Đảm bảo `.col-main` có không gian tối thiểu và không bị tràn ngang (`min-width: 0`).
  - Đảm bảo responsive trên màn hình nhỏ (< 1024px) tự động chuyển về 1 cột.

- [x] **Step 2: Kiểm tra build CSS**
  - Chạy `npm --prefix frontend run build` để xác nhận CSS hợp lệ.

---

### Task 2: Cấu trúc lại JSX trong `App.tsx` tách biệt Sidebar và Workspace
**Files:**
- Modify: `frontend/src/settlement/App.tsx`

**Interfaces:**
- Consumes: `cases`, `view`, `loadCase`, `activeIntakeTab`, `caseTab`, `report`, `run`, `questions`
- Produces: Layout 2 cột nhất quán ở cả 2 trạng thái (`view === null` và `view !== null`)

- [x] **Step 1: Cấu trúc Sidebar cột trái vĩnh viễn**
  - Chuyển `new-case-banner` (`➕ Tạo hồ sơ mới`) lên đầu Sidebar cột trái.
  - Khi `view === null`, nút `➕ Tạo hồ sơ mới` có trạng thái active (`btn-primary`), biểu thị đang ở chế độ tạo mới.
  - Khi `view !== null`, nút bấm đóng vai trò chuyển về chế độ tạo mới (`setView(null)`).
  - Đặt `case-list-panel` ngay dưới nút tạo mới trong Sidebar cột trái.
  - Đặt `verify-container` ở đáy Sidebar cột trái.

- [x] **Step 2: Cấu trúc Workspace cột phải linh hoạt**
  - Xóa bỏ việc render `tab-nav` và Form tạo hồ sơ B3/B7 trong cột trái.
  - Đưa toàn bộ Form tạo hồ sơ (`tab-nav`, `b3-intake-panel`, Form B7) sang hiển thị độc quyền ở Cột phải khi `view === null`.
  - Giữ nguyên cấu trúc Chi tiết hồ sơ (Header, Alert Banners, 5 Tabs nghiệp vụ) ở Cột phải khi `view !== null`.

- [x] **Step 3: Chạy test kiểm thử đơn vị**
  - Chạy `npm --prefix frontend test -- --run` để kiểm chứng toàn bộ 82 tests pass.

---

### Task 3: Tinh chỉnh Trải nghiệm Tương tác & Trực quan (UX Polish)
**Files:**
- Modify: `frontend/src/settlement/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Tinh chỉnh hiệu ứng active cho Sidebar và nút Tạo mới**
  - Thêm visual cue rõ ràng: Khi `view === null`, nút `➕ Tạo hồ sơ mới` ở Sidebar có viền sáng hoặc trạng thái nổi bật "Đang tạo hồ sơ".
  - Thẻ hồ sơ đang chọn có badge `Đang xem` hoặc viền xanh rõ ràng.
- [x] **Step 2: Thêm thanh tìm kiếm / lọc nhanh hồ sơ ở Sidebar (nếu có 10+ hồ sơ)**
  - Thêm ô lọc nhanh theo mã hồ sơ hoặc trạng thái để tìm kiếm tức thì trong 24 hồ sơ mà không cần tải lại trang.
- [x] **Step 3: Chạy toàn bộ test và kiểm tra build sản phẩm**
  - Chạy `npm --prefix frontend run build`.
  - Chạy `npm --prefix frontend test -- --run`.

---

## Kế hoạch Xác minh (Verification Plan)

### Automated Tests
```bash
# 1. Kiểm tra build TypeScript & Vite
npm --prefix frontend run build

# 2. Chạy toàn bộ 17 test suites (82 frontend tests)
npm --prefix frontend test -- --run

# 3. Chạy kiểm tra backend python nếu cần
.venv/bin/python -m pytest tests/settlement/test_b3* -q
```

### Manual Verification
1. Mở Chrome tại `http://localhost:5173`.
2. **Quan sát màn hình khởi đầu (`view === null`):**
   - Cột trái: Nút `➕ Tạo hồ sơ mới` đang active, bên dưới là toàn bộ danh sách 24 hồ sơ gọn gàng, có thể cuộn độc lập. Danh sách KHÔNG CÒN bị chìm xuống đáy.
   - Cột phải: Form nộp B3/B7 rộng rãi, dễ nhìn, các ô nhập thoáng đãng.
3. **Thao tác chọn hồ sơ:**
   - Bấm vào hồ sơ bất kỳ ở cột trái (ví dụ `C-bd0082...`): Cột phải lập tức chuyển sang xem chi tiết hồ sơ đó với các Tab: Kết quả, Bản nháp, Nguồn, Câu hỏi, Lịch sử.
   - Không có hiện tượng co giật layout (layout 2 cột giữ nguyên 100%).
4. **Thao tác quay lại tạo mới:**
   - Bấm nút `➕ Tạo hồ sơ mới` ở cột trái: Cột phải chuyển lại về Form nộp hồ sơ.

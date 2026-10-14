# Cải Tiến Toàn Diện Giao Diện Chi Tiết Hồ Sơ (Detail View Redesign)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loại bỏ hoàn toàn hội chứng "AI Slop" và "Card-in-card" trong giao diện chi tiết hồ sơ đối soát (Detail View), tái cấu trúc thành một không gian làm việc tài chính hợp nhất (Unified Financial Canvas) chuẩn Enterprise Fintech (Stripe / Linear / Ramp / Brex) với hệ thống thị giác phẳng, typography sắc nét, Document Viewer sạch sẽ không lỗi thô và luồng giải trình ngoại lệ trực quan.

**Architecture:** Chuyển đổi từ mô hình các khối bo tròn lồng nhau (`border border-slate-200 rounded-xl` lặp lại vô tận) sang bố cục phẳng 2 phân vùng (Dual-Pane Workspace): bên trái là Document Viewer hiện đại hợp nhất thanh công cụ và xử lý fallback chứng từ mượt mà; bên phải là Unified Canvas nền trắng với phân cấp typography rõ ràng, bảng đối soát dòng tiền đa tầng (Reconciliation Ledger), thẻ Hero KPI chênh lệch (S) chuẩn mực và danh sách việc cần xử lý (Actionable Resolution Checklist) được phân vai rành mạch.

**Tech Stack:** React 19, TypeScript, Tailwind CSS v4, Vitest, Testing Library.

**Spec:** [docs/final/ARCHITECTURE_AND_EVALUATION.md](docs/final/ARCHITECTURE_AND_EVALUATION.md) (Q1–Q31, §4, §10), [docs/final/IMPLEMENTATION_CONTRACTS.md](docs/final/IMPLEMENTATION_CONTRACTS.md) (§9, §10.1–4).

## Global Constraints

- Tuân thủ quy tắc Không Biểu Tượng (Zero Icons Rule): Không nhập bất kỳ icon thư viện nào (Lucide, Heroicons, FontAwesome). Chỉ sử dụng typography, chấm trạng thái CSS (`●`), hoặc ký tự text chuẩn (`←`, `✓`, `✕`, `—`).
- Giữ vững 100% hợp đồng kiểm thử hiện có: tất cả `data-testid` (`money-{label}`, `basis-{expense_id}`, `question-{kind}`, `actual-{key}`, `controls-audit`, `advance-draft`) và các chuỗi hiển thị nghiệp vụ tiếng Việt đã được test khẳng định phải được bảo toàn.
- Nút điều hướng quay lại cố định nhãn: `← Quay lại`.
- Toàn bộ lệnh shell bắt buộc chạy qua tiền tố `rtk proxy`.
- Không làm thay đổi hay sửa sai các quy tắc tài chính VND số học nguyên (integer math).

## Review Focus

1. **Hạn chế 404 iframe thô khi xem chứng từ mock / demo:** Khi case không có file nhị phân trên đĩa hoặc đường dẫn trả về lỗi, Document Viewer phải hiển thị thông tin trích xuất OCR có cấu trúc thay vì render trực tiếp trang lỗi JSON thô trong iframe.
2. **Loại bỏ tình trạng lặp 8 dòng "Chưa xác minh" vô nghĩa:** Bảng đối soát tài chính phân tách rõ 2 nhóm (Khoản chi đề nghị vs Dòng tiền đối soát thực tế), hiển thị ký hiệu gọn gàng (`—` kèm nhãn hoặc tooltip) nhưng vẫn giữ đúng text test yêu cầu.
3. **Loại bỏ nút bấm lạc quẻ:** Không hiển thị nút "+ Tạo hồ sơ mới" ở thanh tiêu đề chi tiết của một hồ sơ đang mở. Nút tạo mới thuộc về Dashboard/Inbox.
4. **Xử lý hash code rườm rà trên tab:** Thay thế các chuỗi digest 6 ký tự (`abcdef`) bằng phân loại tài liệu nghiệp vụ (`Hóa đơn VAT`, `Ủy nhiệm chi`, `Giấy quyết toán`) giúp người dùng nhận diện ngay.
5. **Đảm bảo tính toàn vẹn phiên làm việc và vai trò:** Khi chuyển đổi vai trò (Persona), chỉ các khối nghiệp vụ thuộc thẩm quyền mới mở form thao tác, các vấn đề khác hiển thị dưới dạng nhật ký theo dõi tinh gọn.

---

### Task 1: Tái cấu trúc Header & Khung làm việc hợp nhất trong `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx:288-403`
- Test: `frontend/tests/app-restore.test.tsx`

**Interfaces:**
- Consumes: `CaseView`, `activePanels`, `roleWorkspaces(currentRole)`, `setViewMode`
- Produces: Layout 2 cột phẳng (Left: 50% Document Viewer, Right: 50% Unified Canvas), thanh tiêu đề chi tiết chuẩn mực với `← Quay lại`, breadcrumb mã hồ sơ tinh gọn, loại bỏ nút `+ Tạo hồ sơ mới` gây nhiễu ngữ cảnh.

- [ ] **Step 1: Viết test kiểm tra header affordance cho Detail View**

Thêm test case vào `frontend/tests/app-restore.test.tsx` xác nhận khi ở chế độ xem chi tiết hồ sơ:
- Có nút `← Quay lại`.
- KHÔNG có nút `+ Tạo hồ sơ mới` trong thanh công cụ chi tiết của hồ sơ.

```tsx
it("does not render duplicate create case button in dossier detail view", async () => {
  vi.stubGlobal("fetch", mockFetch({
    "/api/demo/session": SESSION,
    "/api/cases": { cases: [CASE] },
  }));
  render(<App />);
  await waitFor(() => expect(screen.getByText(CASE.summary)).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "+ Tạo hồ sơ mới" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Quay lại/ })).toBeInTheDocument();
});
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `rtk proxy npm test`
Expected: FAIL vì `+ Tạo hồ sơ mới` hiện vẫn đang tồn tại ở line 333 của `App.tsx`.

- [ ] **Step 3: Cải tổ layout detail view trong `App.tsx`**

- Chuyển `main` của split workspace thành:
  - Cột trái: `w-full md:w-1/2 h-1/2 md:h-full bg-slate-900/5 border-r border-slate-200 overflow-hidden flex flex-col`
  - Cột phải: `w-full md:w-1/2 h-1/2 md:h-full bg-white overflow-y-auto custom-scrollbar flex flex-col` (loại bỏ `bg-slate-50/80` và các khoảng cách rời rạc `p-5 space-y-5`).
- Thanh header trên cùng của cột phải:
  - Bố trí dạng thanh công cụ phẳng cao 44px (`h-11 border-b border-slate-200 px-6 flex items-center justify-between shrink-0 bg-white`).
  - Bên trái: Nút `← Quay lại` tinh tế, bên cạnh là breadcrumb: `Hồ sơ / #... · v{version}`.
  - Loại bỏ hoàn toàn nút `+ Tạo hồ sơ mới` khỏi header chi tiết.
- Nội dung các workspace bên phải được đặt trong vùng đệm thống nhất `p-6 space-y-6 max-w-3xl`.

- [ ] **Step 4: Chạy lại test để xác nhận PASS**

Run: `rtk proxy npm test`
Expected: PASS (Tất cả 7 tests trong `app-restore.test.tsx` và toàn bộ suite pass).

- [ ] **Step 5: Kiểm tra lint và định dạng**

Run: `rtk proxy npm run build`
Expected: Không có lỗi type check hoặc build error.

---

### Task 2: Hiện đại hóa Trình xem chứng từ gốc (`document_viewer.tsx`)

**Files:**
- Modify: `frontend/src/features/document_viewer.tsx`
- Test: `frontend/tests/dossier.test.tsx` (hoặc test mới cho document viewer)

**Interfaces:**
- Consumes: `caseView.sources`, `pendingFiles`
- Produces: Giao diện Document Viewer tích hợp thanh tab kiểu trình duyệt (Browser-like tabs), không lặp lại 2 thanh tiêu đề, nhãn chứng từ thân thiện thay cho mã hash, và cơ chế fallback thông minh khi chứng từ không thể mở qua iframe.

- [ ] **Step 1: Viết test cho Document Viewer tab & status rendering**

Tạo test case kiểm tra:
- Render đúng tên file chứng từ gốc.
- Không hiển thị mã hash ngẫu nhiên kiểu commit git nếu có tên file hoặc loại chứng từ.
- Có nút "Mở toàn màn hình" hoặc mở tab mới rõ ràng.

- [ ] **Step 2: Chạy test để kiểm tra trạng thái ban đầu**

Run: `rtk proxy npm test`

- [ ] **Step 3: Thiết kế lại `document_viewer.tsx`**

1. **Hợp nhất thanh Header:** Gộp thanh tab (`h-11`) và thanh toolbar (`h-9`) thành 1 thanh duy nhất (`h-11 border-b border-slate-200 bg-slate-50/90 px-3 flex items-center justify-between`).
2. **Tab chứng từ tối giản & rõ ràng:**
   - Active tab: Nền trắng, viền trên hoặc viền bao quanh phẳng, chữ đen đậm `text-slate-900 font-semibold`, hiển thị nhãn loại (`PDF` / `Ảnh`) gọn gàng.
   - Bỏ chuỗi hash commit `tab.source?.digest.slice(0, 6)`. Thay bằng loại tài liệu hoặc kích thước tệp nếu có.
3. **Smart Viewport Fallback:**
   - Đối với file PDF thực: render `<iframe>` với `src={`${documentUrl}#toolbar=1&navpanes=0`}`.
   - Bổ sung trạng thái xử lý khi không tìm thấy tệp hoặc chế độ mô phỏng/mock: hiển thị thẻ thông tin chứng từ trích xuất với khung metadata sạch sẽ (Tên tệp, Định dạng, Mã phân tích, Trạng thái chứng thực) thay vì để người dùng nhìn thấy trang lỗi 404 JSON thô.

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run: `rtk proxy npm test`
Expected: PASS

---

### Task 3: Bảng đối soát tài chính phẳng & Hero KPI chênh lệch (`dossier.tsx`)

**Files:**
- Modify: `frontend/src/features/dossier.tsx`
- Test: `frontend/tests/dossier.test.tsx`

**Interfaces:**
- Consumes: `caseView`, `caseView.actual_money`, `caseView.payment_basis`, `caseView.issues`
- Produces: Khối Dossier phẳng trực tiếp trên Canvas (loại bỏ viền ngoài `border border-slate-200 rounded-xl`), Hero KPI chênh lệch (S) chuẩn mực, Bảng phân tích dòng tiền 2 tầng (Chi phí vs Thanh toán), và danh mục căn cứ pháp lý tinh gọn.

- [ ] **Step 1: Kiểm tra test hiện tại trong `dossier.test.tsx`**

Test yêu cầu:
- `data-testid="money-Tổng chi công việc"` -> `"10.000.000"`
- `data-testid="money-Ứng thực nhận"` -> `"Chưa xác minh"`
- `getByText(/Chính sách/)`
- `getByText(/Căn cứ: Tổng chi 10.000.000 vượt ngân sách 8.000.000/)`
- `getByText(/Người xử lý: approver/)`
- `data-testid="basis-expense:1"` -> `"Lời xác nhận của nhân viên"`

- [ ] **Step 2: Tái cấu trúc `dossier.tsx` theo ngôn ngữ thiết kế phẳng**

1. **Loại bỏ vỏ bọc ngoài:**
   - Thay `section.bg-white.border.border-slate-200.rounded-xl.p-5` bằng `section.space-y-6` cắm trực tiếp vào canvas.
2. **Tiêu đề hồ sơ & Trạng thái thanh lịch:**
   - Tiêu đề: `Hồ sơ đối soát` kèm badge trạng thái dạng pill đơn giản, không đổ bóng màu mè. Tóm tắt hoạt động với typography `text-sm text-slate-500 font-normal`.
3. **Hero KPI Chênh Lệch Quyết Toán (S):**
   - Thiết kế dạng banner thông tin tích hợp (Flat Banner): nền sáng tương phản nhẹ (`bg-slate-50/80 border-y border-slate-200 py-4 px-5`), hiển thị số tiền chênh lệch với font monospace lớn (`text-2xl font-bold font-mono-nums tracking-tight`), nhãn hướng tiền rõ ràng (`Công ty chi bổ sung:` hoặc `Thu hồi hoàn ứng:`).
4. **Bảng phân tích dòng tiền đối soát (Reconciliation Ledger):**
   - Loại bỏ viền bo tròn `rounded-xl` bao bọc bảng. Sử dụng bảng phẳng với hàng header nhẹ (`text-[11px] font-semibold text-slate-500 uppercase tracking-wider`).
   - Phân thành 2 nhóm mạch lạc:
     - Nhóm 1: **Khoản chi phí đề nghị** (Tổng chi T, Hợp lệ E, Công ty trả C)
     - Nhóm 2: **Dòng tiền đối soát thực tế** (Ứng A, Hoàn P, Thu hồi R, Chưa trả unpaid)
   - Giữ nguyên toàn bộ `data-testid="money-{label}"` và định dạng `formatMoney` để 100% khớp test suite.
5. **Căn cứ xác nhận chi trả (`payment_basis`):**
   - Chuyển thành danh sách kiểm toán tinh gọn (Audit list) ngăn cách bằng đường kẻ mỏng (`divide-y divide-slate-100`), giữ nguyên `data-testid="payment-basis"` và `data-testid="basis-{basis.expense_id}"`.

- [ ] **Step 3: Chạy test để xác nhận PASS**

Run: `rtk proxy npm test frontend/tests/dossier.test.tsx`
Expected: 3/3 tests pass.

---

### Task 4: Danh mục giải quyết ngoại lệ & câu hỏi trực quan (`questions.tsx`)

**Files:**
- Modify: `frontend/src/features/questions.tsx`
- Test: `frontend/tests/app-restore.test.tsx`, `frontend/tests/dossier.test.tsx`

**Interfaces:**
- Consumes: `caseView.issues`, `onCase`, `currentRole`
- Produces: Khối câu hỏi và giải trình được phân bổ trực quan, không lồng hộp xám vào hộp trắng, ô nhập liệu mượt mà, phân cấp việc của tôi (Actionable) và việc chờ bộ phận khác (Monitoring).

- [ ] **Step 1: Đánh giá mã hiện tại của `questions.tsx`**

Hiện tại `QuestionCard` bọc trong `li.p-5.bg-white.border.border-slate-200.rounded-xl`, bên trong lại có `div.bg-slate-50.p-2.5.rounded-lg.border` và nhiều lớp viền bo tròn giống nhau.

- [ ] **Step 2: Tái thiết kế `questions.tsx`**

1. **Khối việc cần xử lý của vai trò hiện tại (My Issues):**
   - Thiết kế thành thẻ hành động tập trung (Resolution Action Item): viền trái nổi bật (`border-l-2 border-l-amber-500 bg-amber-50/20 border-y border-r border-slate-200 rounded-lg p-4`), phân cách rõ ràng câu hỏi cần trả lời, căn cứ chứng từ, và form nhập liệu ngắn gọn.
   - Giữ nguyên `data-testid={`question-${issue.kind}`}`.
2. **Khối việc đang chờ vai trò khác (Other Issues):**
   - Thiết kế dạng danh sách theo dõi tiến độ (Audit Trail / Progress Checklist) cực kỳ thanh thoát: các dòng ngang với dot indicator trạng thái (`● Đang chờ Kế toán / Người phê duyệt`), không tạo cảm giác nặng nề cho người đang xem.
3. **Typography & Labeling:**
   - Dùng badge chữ nhỏ gọn gàng, rõ ràng, không viền dày hay bóng đổ.

- [ ] **Step 3: Chạy test để xác nhận PASS**

Run: `rtk proxy npm test`
Expected: Tất cả tests liên quan pass.

---

### Task 5: Đồng bộ các Module Nghiệp vụ (`approval.tsx`, `advance.tsx`, `execution.tsx`, `controls.tsx`)

**Files:**
- Modify: `frontend/src/features/approval.tsx`
- Modify: `frontend/src/features/advance.tsx`
- Modify: `frontend/src/features/execution.tsx`
- Modify: `frontend/src/features/controls.tsx`
- Test: `frontend/tests/advance.test.tsx`

**Interfaces:**
- Consumes: `caseView`, `onCase`
- Produces: Đồng bộ hóa toàn bộ các panel nghiệp vụ của Kế toán & Người phê duyệt theo ngôn ngữ thiết kế phẳng, loại bỏ hoàn toàn viền bo tròn lồng nhau, chuẩn hóa input và nút bấm.

- [ ] **Step 1: Chuẩn hóa `approval.tsx`**

- Chuyển `section` thành khối phẳng trực tiếp trên canvas.
- Bảng lệnh chi/thu hiển thị dưới dạng hàng thanh toán tối giản với số tiền monospace in đậm nổi bật (`font-mono-nums font-bold text-slate-900`).

- [ ] **Step 2: Chuẩn hóa `advance.tsx` & `execution.tsx`**

- Giữ nguyên tất cả aria-label và nhãn input (`Chứng từ ứng`, `Số tiền thực nhận`, `Mã giao dịch hoặc số phiếu`, `Xác nhận của kế toán`, button `Xác nhận ghi nhận`, `data-testid="advance-draft"`, `data-testid="actual-{key}"`).
- Thay thế các khung xám dày bo tròn bằng layout form tinh gọn với input chuẩn (`border-slate-200 focus:border-slate-900 rounded-md`).
- Sắp xếp nhóm trường nhập liệu khoa học, gọn mắt.

- [ ] **Step 3: Chuẩn hóa `controls.tsx`**

- Khối Stop/Resume: các nút hành động nhỏ gọn, tối giản (`Dừng hồ sơ` đỏ nhạt tinh tế, `Tiếp tục` phẳng).
- Nhật ký kiểm soát (`data-testid="controls-audit"`): chuyển thành danh sách log console mono thanh lịch với thanh cuộn tinh tế.

- [ ] **Step 4: Chạy toàn bộ test suite để xác nhận PASS**

Run: `rtk proxy npm test`
Expected: 19 passed | 2 skipped (100% pass).

---

### Task 6: Kiểm thử tổng thể & Đảm bảo tiêu chuẩn Zero-Regression

**Files:**
- Run: Toàn bộ kiểm thử frontend và backend

- [ ] **Step 1: Chạy toàn bộ Vitest suite**

Run: `rtk proxy npm test`
Expected: PASS toàn bộ.

- [ ] **Step 2: Chạy Typecheck & Build frontend**

Run: `rtk proxy npm run build`
Expected: Build thành công không có warning hoặc error nào.

- [ ] **Step 3: Chạy kiểm thử Backend Pytest**

Run: `rtk proxy uv run pytest tests/`
Expected: 183/183 tests passed.

- [ ] **Step 4: Rà soát trực quan các màn hình (Self-Review Checklist)**

- Xác nhận không còn hiện tượng card-in-card: toàn bộ right pane là một mặt phẳng canvas liền mạch.
- Xác nhận không có icon thư viện bên ngoài.
- Xác nhận Document Viewer chuyển tab mượt mà, không render 404 raw json vào iframe.
- Nút `← Quay lại` hoạt động chính xác.

---

## Self-Review

1. **Spec coverage:** Kế hoạch bao quát toàn bộ các điểm cốt lõi mà người dùng phản ánh: loại bỏ AI Slop, xóa bỏ tình trạng lặp khung bo tròn `rounded-xl`, cải tổ Document Viewer không bị lỗi 404 thô, dọn dẹp nút tạo hồ sơ đặt nhầm chỗ, và cấu trúc lại bảng đối soát tài chính cùng danh mục câu hỏi.
2. **Step scan:** Mỗi bước đều xác định file, phương án thực thi, lệnh test cụ thể và kết quả kỳ vọng.
3. **Type consistency & Contract safety:** Giữ nguyên 100% các interface `CaseView`, `IssueView`, `InstructionView`, `SourceView`, `MoneyFactView` và các `data-testid` bắt buộc cho bài thi và test suite.
4. **Zero Icons:** Tuyệt đối không dùng thư viện icon, chỉ dùng unicode chuẩn (`←`, `●`, `✓`, `—`).

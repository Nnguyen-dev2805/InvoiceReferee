# Kế hoạch Cải tiến Màn hình Kế toán (Accountant Workspace) — InvoiceReferee

> **Dành cho Agentic Workers:** YÊU CẦU SUB-SKILL: Sử dụng `superpowers:subagent-driven-development` hoặc `superpowers:executing-plans` để triển khai kế hoạch này theo từng task. Các bước dùng cú pháp `- [ ]` để theo dõi tiến độ.

**Mục tiêu:** Tinh giản và tái cấu trúc màn hình kế toán cho hồ sơ tạm ứng B3 theo đúng 8 điểm phản hồi nghiệp vụ của người dùng: đưa thông tin công việc và trạng thái nghiệp vụ lên hàng đầu, thu gọn dữ liệu kỹ thuật, chuyển bảng facts thành bảng đối chiếu câu hỏi nghiệp vụ, và đưa khu vực kết luận rà soát lên vị trí thuận tiện.

**Kiến trúc:** 
1. **Backend (`b3.py`)**: Sửa lỗi tổng hợp `document.role` trong `critical_facts` để không gắn mác `CONTRADICTED` giả khi hai chứng từ trong hồ sơ là `ADVANCE_REQUEST` và `FORECAST`.
2. **Frontend Header & Nhận diện (`App.tsx`)**: Đặt một trạng thái nghiệp vụ duy nhất trên cùng ("Chờ kế toán rà soát" / "Đã rà soát"), đưa Tên nhân viên · Chuyến đi · Số tiền đề nghị lên vị trí số 1, thu nhỏ mã hồ sơ và đưa chi tiết kỹ thuật (`run`, `epoch`, `stage`) vào vùng gập mở.
3. **Bảng dự toán & Căn cứ (`Report.tsx`)**: Đổi nhãn "Công ty / Nhân viên dự kiến trả", thu gọn cột căn cứ thành nút ngắn "Xem dự toán", giảm chiều cao dòng.
4. **Bảng đối chiếu nghiệp vụ (`Report.tsx`)**: Thay thế bảng "Critical facts" thô bằng Bảng Đối chiếu Câu hỏi Nghiệp vụ (Số tiền số/chữ, Tổng dự toán và chi tiết, Khớp thông tin chuyến đi); đưa raw facts kỹ thuật vào accordion mở rộng.
5. **Checklist kiểm tra tự động (`Report.tsx`)**: Đổi tiêu đề thành "10 mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát", bỏ lặp văn bản và mã kỹ thuật.
6. **Hành động rà soát (`Actions.tsx`)**: Đổi thành "Lưu kết quả rà soát", hiển thị thẻ kết quả rà soát sau khi lưu, ẩn bảng tiền rỗng và cảnh báo B3_REPORT_ONLY dài dòng.

**Tech Stack:** React 18, TypeScript, Vite, Python 3.14 (FastAPI, Pydantic), CSS Custom Properties.

**Tài liệu đặc tả:** 8 điểm nhận xét chi tiết của người dùng ngày 11/10/2026 và `docs/settlement/PRODUCT.md`, `docs/settlement/RULEBOOK.md`.

## Ràng buộc Toàn cục (Global Constraints)
- Giữ nguyên số nguyên VND (`integer VND`) cho tiền tệ và `Decimal` cho tính toán tài chính.
- Tuân thủ ranh giới vai trò: Kế toán thực hiện rà soát ghi nhận ý kiến (`review`), không phê duyệt ngân sách/chi tiền (`decide`).
- Hồ sơ B3 v1 là nhánh đề nghị/intake: không tạo quyết định chi tiền, không tạo lệnh chuyển khoản ngân hàng.
- Không che giấu lỗi kỹ thuật: sửa đúng nguyên nhân gốc tại backend và mô hình dữ liệu.
- Phản hồi và giao diện dùng tiếng Việt chuẩn nghiệp vụ kế toán doanh nghiệp.

---

### Task 1: Sửa lỗi tổng hợp `document.role` trong backend (`b3.py`)

**Files:**
- Modify: `src/invoice_referee/settlement/b3.py:1298-1302`
- Test: `tests/settlement/test_b3_proposal.py`

**Interfaces:**
- Consumes: `request_units`, `forecast_units`, `observations`, `contradictions` từ `evaluate()` trong `b3.py`.
- Produces: `CriticalFact(key="document.role", ...)` có `state="KNOWN"` khi hai chứng từ phân vai hợp lệ (`ADVANCE_REQUEST` và `FORECAST`), và chỉ mang `CONTRADICTED` khi có mâu thuẫn nội tại thực sự.

- [ ] **Bước 1: Viết test case chứng minh lỗi tổng hợp role**

Trong `tests/settlement/test_b3_proposal.py`, thêm test kiểm tra hồ sơ gồm cả 2 chứng từ (Giấy đề nghị và Dự toán) không được có `document.role` bị `CONTRADICTED`:

```python
def test_document_role_across_request_and_forecast_not_contradicted():
    observations = make_b3_observations()  # contains both S-B3-REQ and S-B3-FC
    report = evaluate(make_b3_run(form=import_form()), observations)
    role_fact = next(f for f in report.critical_facts if f.key == "document.role")
    assert role_fact.state == "KNOWN"
    assert "ADVANCE_REQUEST" in str(role_fact.value)
    assert "FORECAST" in str(role_fact.value)
```

- [ ] **Bước 2: Chạy test để xác nhận test thất bại (hoặc phát hiện `state == "CONTRADICTED"`)**

Chạy: `SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_proposal.py -k test_document_role_across_request_and_forecast_not_contradicted -v`
Kỳ vọng: FAIL vì hiện tại `rules._fact_state(observations, "document.role")` trả về `CONTRADICTED`.

- [ ] **Bước 3: Cập nhật hàm tổng hợp `critical_facts` cho `document.role` trong `b3.py`**

Trong `src/invoice_referee/settlement/b3.py`, cập nhật phần dựng `critical_facts`:

```python
    def _doc_role_fact_state() -> CriticalFact:
        role_contra = [refs for k, refs in contradictions if k == "document.role"]
        if role_contra:
            all_refs = sorted({r for refs_list in role_contra for r in refs_list})
            return CriticalFact(key="document.role", value=None, state="CONTRADICTED", refs=all_refs)
        roles = []
        r_refs = []
        if request_units:
            roles.append("ADVANCE_REQUEST")
            for _, u in request_units:
                _, u_refs, _ = unit_value(u, "document.role")
                r_refs.extend(u_refs)
        if forecast_units:
            roles.append("FORECAST")
            for _, u in forecast_units:
                _, u_refs, _ = unit_value(u, "document.role")
                r_refs.extend(u_refs)
        if not roles:
            return rules._fact_state(observations, "document.role")
        return CriticalFact(
            key="document.role",
            value=", ".join(roles),
            state="KNOWN",
            refs=sorted(set(r_refs)),
        )

    critical_facts = [
        (_doc_role_fact_state() if key == "document.role"
         else _request_words_fact_state(request_observations, key)
         if key in _WORDS_KEYS else rules._fact_state(observations, key))
        for key in sorted(k for k in all_keys if _is_b3_grammar_key(k))]
```

- [ ] **Bước 4: Chạy lại test để xác nhận PASS**

Chạy: `SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_proposal.py -k test_document_role_across_request_and_forecast_not_contradicted -v`
Kỳ vọng: PASS.

- [ ] **Bước 5: Chạy toàn bộ test suite backend**

Chạy: `SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q`
Kỳ vọng: Tất cả 268+ test đều PASS.

---

### Task 2: Tái cấu trúc Header hồ sơ & Thống nhất Trạng thái nghiệp vụ (Points 1 & 2)

**Files:**
- Modify: `frontend/src/settlement/App.tsx:1044-1180`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/settlement/App.test.tsx`

**Interfaces:**
- Consumes: `view`, `report`, `role`, `demoContext` trong `App.tsx`.
- Produces: Header thẻ hồ sơ mới với:
  - Tiêu đề chính: `Đề nghị tạm ứng — [Tên nhân viên]` (lấy từ `demoContext?.people` tìm theo `employee_ref`).
  - Dòng phụ: `[Địa điểm] · [Thời gian] · Đề nghị [Số tiền VND]`.
  - Mã hồ sơ `C-...` hiển thị dạng badge nhỏ kèm nút sao chép.
  - Trạng thái nghiệp vụ đơn nhất: **"Chờ kế toán rà soát"** (nếu chưa review) hoặc **"Đã rà soát"** (nếu đã có review).
  - Dòng giải thích: *"Nhân viên đã xác nhận nộp. Hệ thống đã hoàn tất kiểm tra tự động. Chưa phê duyệt hoặc chi ứng."*
  - Khối kỹ thuật `Run ID`, `stage`, `rev`, `epoch` đưa vào dòng nhỏ tinh gọn / collapsible.

- [ ] **Bước 1: Viết test cho Header nghiệp vụ và thông tin nhận diện**

Trong `frontend/src/settlement/App.test.tsx`:
```tsx
test('header hiển thị tên nhân viên, mục đích, chuyến đi và trạng thái nghiệp vụ Chờ kế toán rà soát', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);
  await user.click(await screen.findByText(/C-b3test01/));
  expect(screen.getByText(/Chờ kế toán rà soát/)).toBeInTheDocument();
  expect(screen.getByText(/Nhân viên đã xác nhận nộp/)).toBeInTheDocument();
});
```

- [ ] **Bước 2: Triển khai giao diện Header mới trong `App.tsx`**

Cập nhật `case-header-panel` trong `frontend/src/settlement/App.tsx`:
1. Tra cứu tên nhân viên từ `demoContext?.people.find(p => p.actor_ref === view.submission.employee_ref)?.name || view.submission.employee_ref`.
2. Tạo tiêu đề lớn: `viewIsB3 ? \`Đề nghị tạm ứng — \${empName}\` : \`Quyết toán — \${empName}\``.
3. Dòng phụ tóm tắt: Nơi đến (từ `destination` hoặc `form`), thời gian chuyến đi, số tiền đề nghị.
4. Mã hồ sơ `C-...` thành badge nhỏ có icon copy.
5. Hiển thị Trạng thái nghiệp vụ thống nhất (`businessStatus`):
   - Nếu `role === 'ACCOUNTANT'`:
     - Chưa review: Badge xanh `Chờ kế toán rà soát` kèm mô tả: *"Nhân viên đã xác nhận thông tin đề nghị. Hệ thống đã hoàn tất kiểm tra tự động. Chưa phê duyệt hoặc chi ứng."*
     - Đã review: Badge xanh lá `Đã lưu kết quả rà soát` kèm thời gian và người rà soát.

- [ ] **Bước 3: Thu nhỏ thao tác "Tạo hồ sơ mới" cho vai trò Kế toán**

Trong sidebar, nếu `role === 'ACCOUNTANT'`, nút "Tạo hồ sơ mới" chuyển thành dạng `btn-secondary` hoặc nút phụ nhỏ, tránh chiếm spotlight so với danh sách hồ sơ cần rà soát.

- [ ] **Bước 4: Chạy kiểm thử frontend**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: Toàn bộ test của `App.test.tsx` và suite frontend PASS.

---

### Task 3: Tinh giản Bảng Dự toán & Tối ưu Diện tích Đọc (Point 3)

**Files:**
- Modify: `frontend/src/settlement/Report.tsx:410-450`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/settlement/Report.test.tsx`

**Interfaces:**
- Consumes: `intake.estimate_rows`, `proposal.forecast_company_vnd`, `proposal.forecast_employee_vnd`.
- Produces: Bảng dự toán gọn gàng với nhãn rõ ràng:
  - Tiêu đề cột: `Nội dung`, `Cơ sở tính`, `Công ty dự kiến trả`, `Nhân viên dự kiến trả`, `Căn cứ`.
  - Nút căn cứ: Rút gọn thành badge `Xem dự toán` hoặc `Xem căn cứ`.
  - Giảm khoảng đệm (padding) của hàng, tránh wrap dòng vô lý.

- [ ] **Bước 1: Cập nhật kiểm thử trong `Report.test.tsx`**

Kiểm tra bảng dự toán hiển thị đúng nhãn `Công ty dự kiến trả` và `Nhân viên dự kiến trả`.

- [ ] **Bước 2: Cập nhật bảng dự toán trong `Report.tsx`**

Sửa bảng `estimate-table` trong `B3ProposalSection`:
- Thay đổi header:
  ```tsx
  <th style={{ width: '30%' }}>Nội dung chi phí</th>
  <th style={{ width: '22%' }}>Cơ sở tính toán</th>
  <th className="text-right" style={{ width: '18%' }}>Công ty dự kiến trả</th>
  <th className="text-right" style={{ width: '18%' }}>Nhân viên dự kiến trả</th>
  <th style={{ width: '12%' }}>Căn cứ</th>
  ```
- Cột căn cứ: Bọc liên kết trong nút nhỏ gọn `Xem căn cứ` / `Xem dự toán`, không in tràn lan toàn bộ id hoặc text dài.

- [ ] **Bước 3: Tối ưu CSS padding cho bảng dự toán trong `styles.css`**

Giảm padding của `estimate-table th, .estimate-table td` từ `12px` xuống `8px 10px`, căn chỉnh các con số bên phải rõ ràng.

- [ ] **Bước 4: Chạy kiểm thử xác nhận**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: PASS.

---

### Task 4: Chuyển Bảng "Critical Facts" thành Bảng Đối Chiếu Nghiệp Vụ (Point 4)

**Files:**
- Modify: `frontend/src/settlement/Report.tsx:184-236`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/settlement/Report.test.tsx`

**Interfaces:**
- Consumes: `report.critical_facts`, `report.b3`, `report.checks`.
- Produces:
  1. **Bảng Đối chiếu Nghiệp vụ (Reconciliation Matrix)** ở màn chính:
     - Dòng 1: *Số xin ứng và số bằng chữ* → So sánh số tiền số và số tiền chữ trích xuất từ giấy đề nghị. Trạng thái: "Khớp: [số tiền]" hoặc "Mâu thuẫn". Căn cứ: Xem giấy đề nghị.
     - Dòng 2: *Tổng dự toán và chi tiết các dòng* → So sánh tổng dự toán ghi trên giấy với tổng các dòng chi phí. Trạng thái: "Khớp: [tổng tiền]" hoặc "Lệch phép tính". Căn cứ: Xem bảng dự toán.
     - Dòng 3: *Thông tin chuyến đi giữa hai giấy* → So sánh nơi đến và thời gian giữa hai giấy. Trạng thái: "Khớp thông tin" hoặc "Cần làm rõ". Căn cứ: Xem hai giấy.
     - Dòng 4: *Loại chứng từ & Phân vai hồ sơ* → Giấy đề nghị tạm ứng & Bảng dự toán. Trạng thái: "Đầy đủ 2 giấy theo quy định". Căn cứ: Xem hồ sơ nguồn.
  2. **Vùng Chi tiết Kỹ thuật đã Đọc (Collapsible Details)**:
     - Đưa toàn bộ bảng `critical_facts` thô (raw key-value pairs) vào `<details className="tech-facts-accordion">` có thể gập mở để phục vụ kiểm tra sâu khi cần.

- [ ] **Bước 1: Viết test cho Bảng Đối chiếu Nghiệp vụ trong `Report.test.tsx`**

```tsx
test('hiển thị bảng đối chiếu nghiệp vụ với các câu hỏi kiểm tra thay vì raw facts thô', () => {
  render(<ReportPanel report={mockB3Report} b3Context={null} sources={[]} />);
  expect(screen.getByText('Bảng đối chiếu nghiệp vụ chứng từ')).toBeInTheDocument();
  expect(screen.getByText(/Số xin ứng và số bằng chữ/)).toBeInTheDocument();
  expect(screen.getByText(/Tổng dự toán và các dòng chi tiết/)).toBeInTheDocument();
});
```

- [ ] **Bước 2: Xây dựng component `BusinessReconciliationTable` trong `Report.tsx`**

Trích xuất dữ liệu từ `proposal` và `critical_facts` để hiển thị 4 dòng đối chiếu nghiệp vụ chính xác, rõ ràng.

- [ ] **Bước 3: Đưa raw `critical_facts` vào accordion `<details>`**

Tạo accordion `<details className="tech-context-accordion"><summary>Chi tiết kỹ thuật: Dữ liệu đã trích xuất từ hồ sơ (Critical facts)</summary>...</details>` bên dưới.

- [ ] **Bước 4: Chạy kiểm thử frontend**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: PASS.

---

### Task 5: Tinh giản Checklist Kiểm Tra Tự Động & Bỏ Lặp Từ (Point 5)

**Files:**
- Modify: `frontend/src/settlement/Report.tsx:272-326`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/settlement/Report.test.tsx`

**Interfaces:**
- Consumes: `report.checks`.
- Produces:
  - Tiêu đề mới: `[N] mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát.` (không phóng đại là "tuân thủ quy chế tài chính").
  - Mỗi dòng checklist: 1 câu diễn giải tiếng Việt duy nhất, mã rule kỹ thuật đưa vào tag code nhỏ, loại bỏ đoạn text lặp lại `{check.rule}: {check.status} — {check.reason}`.

- [ ] **Bước 1: Sửa tiêu đề và nội dung từng dòng check trong `Report.tsx`**

Cập nhật tiêu đề:
```tsx
<h3 className="section-title" style={{ margin: 0 }}>Kiểm tra điều kiện tự động</h3>
<span className="section-subtitle">
  {passCount} mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát.
</span>
```
Cập nhật nội dung dòng check:
```tsx
<div className="policy-check-desc">
  {check.reason}
  <span className="policy-check-rule-id"> (mã: <code>{check.rule}</code>)</span>
  {check.refs && check.refs.length > 0 && (
    <span className="policy-check-refs"> · Căn cứ: {refs(check.refs)}</span>
  )}
</div>
```

- [ ] **Bước 2: Cập nhật test trong `Report.test.tsx`**

Đảm bảo test kiểm tra tiêu đề mới và không còn chuỗi lặp thừa.

- [ ] **Bước 3: Chạy kiểm thử xác nhận**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: PASS.

---

### Task 6: Tối ưu Khu vực Rà soát của Kế toán & Loại bỏ Khối B3 Không Áp Dụng (Points 7 & 8)

**Files:**
- Modify: `frontend/src/settlement/Actions.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/settlement/Actions.test.tsx`

**Interfaces:**
- Consumes: `role`, `b3V1`, `canReview`, `reviewNote`, `history`, `view`.
- Produces:
  - Nút rà soát: Đổi thành **“Lưu kết quả rà soát”**.
  - Hướng dẫn khi nút bị disabled: Hiển thị tooltip/helper text *"Vui lòng nhập ghi chú rà soát trước khi lưu"*.
  - Hiển thị thẻ tóm tắt rà soát đã lưu: Nếu trong `history` có bản ghi review của kế toán, hiển thị thẻ nổi bật: *Kế toán [Actor] đã rà soát lúc [Thời gian] — Ghi chú: "[Note]" (Căn cứ Report [ID])*.
  - Đối với hồ sơ B3: Ẩn hoàn toàn bảng "Tình trạng tiền" rỗng dấu `—` và cảnh báo dài dòng `B3_REPORT_ONLY`. Thay bằng thông báo ngắn gọn:
    > *Chức năng hiện tại hỗ trợ rà soát đề nghị tạm ứng; chưa thực hiện duyệt và chi ứng.*
  - Ẩn form quyết định của Approver khỏi tầm nhìn của Kế toán.

- [ ] **Bước 1: Cập nhật kiểm thử trong `Actions.test.tsx`**

Kiểm tra:
- Nút có tên `Lưu kết quả rà soát`.
- Thông báo ngắn gọn cho B3 thay vì cảnh báo kỹ thuật `B3_REPORT_ONLY`.
- Khối "Tình trạng tiền" không hiển thị bảng dấu `—` cho B3.

- [ ] **Bước 2: Cập nhật `Actions.tsx`**

1. Đổi nhãn nút sang `Lưu kết quả rà soát`.
2. Thêm dòng gợi ý dưới nút khi chưa nhập ghi chú:
   `{!reviewNote.trim() && <p className="helper text-amber">Vui lòng nhập ghi chú rà soát để kích hoạt nút lưu.</p>}`
3. Render thẻ lịch sử rà soát gần nhất nếu có trong `history`.
4. Với `b3V1`:
   - Ẩn hoàn toàn `money-summary` rỗng.
   - Thay khối cảnh báo bằng hộp thông tin:
     ```tsx
     <div className="notice notice-info">
       <p>ℹ️ Chức năng hiện tại hỗ trợ rà soát đề nghị tạm ứng; chưa thực hiện duyệt và chi ứng.</p>
     </div>
     ```
   - Ẩn hoàn toàn form của Approver đối với Kế toán.

- [ ] **Bước 3: Chạy kiểm thử frontend**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: PASS toàn bộ.

---

### Task 7: Xác thực Tổng thể (E2E Verification)

**Files:**
- Toàn bộ source code đã sửa.

- [ ] **Bước 1: Chạy toàn bộ frontend tests**

Chạy: `npm --prefix frontend run test -- --run`
Kỳ vọng: Tất cả 17 test suites (88+ tests) PASS.

- [ ] **Bước 2: Chạy kiểm tra TypeScript và Build Production**

Chạy: `npm --prefix frontend run build`
Kỳ vọng: `tsc --noEmit && vite build` hoàn thành không có lỗi.

- [ ] **Bước 3: Chạy toàn bộ backend settlement tests**

Chạy: `SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/ -q`
Kỳ vọng: Tất cả 269+ test backend PASS.

- [ ] **Bước 4: Kiểm tra `git status --short`**

Đảm bảo chỉ có các file nằm trong phạm vi kế hoạch bị thay đổi, không có file rác hay secret bị đưa vào working tree.

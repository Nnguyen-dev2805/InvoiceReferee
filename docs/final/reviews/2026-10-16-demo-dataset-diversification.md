# TC05–TC10 Demo Dataset Diversification Review

Date: 2026-10-16  
Task Scope: Diversify demo dataset for TC05–TC10 so that duplicate cases have distinct work purposes and distinct advance amounts, while preserving testing semantics, error invariants, and error deltas.  
Execution Mode: Offline / Deterministic Generator (ZERO live/OCR/LLM calls).

---

## 1. Executive Summary

In the initial UC-03 demo dataset, cases **TC01, TC05, TC06, TC07, TC08, TC09, TC10** shared identical work purposes (`"Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"`) and identical advance amounts (`4.000.000 VND`). This duplication reduced test coverage variety and created artificial ambiguity for dossier linking.

This work delivered:
1. **Preserved Anchor**: TC01 remained completely untouched as the anchor case. The intentional duplicate relationship between TC01 and TC12 was strictly preserved.
2. **Selective Modification**: Only cases **TC05 through TC10** (6 cases) were diversified. All other 19 cases remain bit-for-bit identical (174 non-affected files verified by SHA-256).
3. **Exact Error Invariants & Deltas**:
   - **TC05**: Line items sum differs from printed report total by exactly **500.000 VND** (`SET_PAPER_TOTAL_001`).
   - **TC06**: Calculated refund $(A - E)$ differs from declared refund by exactly **60.000 VND** (`SET_SETTLEMENT_DIFF_001`).
   - **TC07**: Printed numeric total and words differ by exactly **260.000 VND** (`SET_PAPER_CONSISTENCY_001`).
   - **TC08**: Report total is higher than invoice total by exactly **260.000 VND**; internal report arithmetic is consistent (`SET_PAPER_AMOUNT_001`).
   - **TC09**: Buyer tax code is `7777777777` (different from company's `0319999996`), keeping negative company-binding test (`SET_BUYER_TAX_001`).
   - **TC10**: Buyer tax code is completely blank/omitted (`None`), keeping missing mandatory buyer field test.
4. **Policy & Arithmetic Bounds**:
   - All transactions remain in `WORK_EXPENSE` (hospitality/tiếp khách) under employee `NGUYỄN MINH AN` and company `CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH` (tax ID `0319999996`).
   - Integer arithmetic throughout: VAT (8%) calculated without floating-point artifacts.
   - All amounts within policy caps: per item $\le 5.000.000$ VND, total $E \le 8.000.000$ VND, $|S| \le 4.000.000$ VND, advance $A > E$.
5. **Clean Architecture**:
   - Portable generator script created at `scripts/generate_uc3_variations.py` with cross-platform font discovery and DOCX/PDF support.
   - No application logic, linker, or policy modified to adapt to new data.
   - No artificial advance codes (e.g. `TU-TC05`) injected into PDFs.
   - No external provider calls made.

---

## 2. Before vs. After Specification Matrix

| Case | Old Purpose / New Purpose | Old $A$ | New $A$ | Old Invoice | New Invoice | Old Paper | New Paper | Invariant / Delta Preserved |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- |
| **TC05** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách làm việc với đối tác logistics Tân Cảng | 4.0M | **4.5M** | 3.0M + 8% VAT = 3.24M | **8 suất $\times$ 400k = 3.2M + 8% (256k) = 3.456M** | Dòng: 3.0M<br>Tổng: 3.5M | **Dòng: 2.2M + 1.0M = 3.2M<br>Tổng: 3.7M** | **Lệch dòng vs tổng đúng 500.000 đ**; Hoàn khai: 800k. |
| **TC06** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách đoàn kiểm toán hệ thống an toàn thông tin | 4.0M | **3.8M** | 3.0M + 8% VAT = 3.24M | **5 suất $\times$ 550k = 2.75M + 8% (220k) = 2.97M** | Tổng: 3.24M<br>Hoàn khai: 700k | **Tổng: 2.97M<br>Hoàn khai: 770k** | **$A - E = 830\text{k} \neq 770\text{k}$ (lệch đúng 60.000 đ)**. |
| **TC07** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách hội thảo chuyên đề chuyển đổi số ngành bán lẻ | 4.0M | **4.8M** | 3.0M + 8% VAT = 3.24M | **10 suất $\times$ 350k = 3.5M + 8% (280k) = 3.78M** | Số: 3.24M<br>Chữ: 3.5M | **Số: 3.78M<br>Chữ: 4.04M** | **Chữ lệch số đúng 260.000 đ**; Hoàn khai: 1.02M. |
| **TC08** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách đại diện đối tác phần mềm tài chính MISA | 4.0M | **4.2M** | 3.0M + 8% VAT = 3.24M | **8 suất $\times$ 350k = 2.8M + 8% (224k) = 3.024M** | Tổng: 3.5M<br>Hoàn khai: 500k | **Tổng: 3.284M<br>Hoàn khai: 916k** | **Giấy cao hơn HĐ đúng 260.000 đ**; Nội bộ giấy khớp (không thêm lỗi TC06). |
| **TC09** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách chuyên gia tư vấn kiến trúc giải pháp Cloud | 4.0M | **3.6M** | 3.0M + 8% VAT = 3.24M<br>MST: `7777777777` | **6 suất $\times$ 450k = 2.7M + 8% (216k) = 2.916M<br>MST: 7777777777** | Tổng: 3.24M<br>Hoàn khai: 760k | **Tổng: 2.916M<br>Hoàn khai: 684k** | **MST bên mua: `7777777777`**; Số học và hoàn ứng hoàn toàn khớp. |
| **TC10** | *Old*: Tiếp khách nâng cấp VP 2026<br>**New**: Tiếp khách đại diện nhà cung cấp dịch vụ hạ tầng mạng | 4.0M | **4.6M** | 3.0M + 8% VAT = 3.24M<br>MST: *(trống)* | **8 suất $\times$ 420k = 3.36M + 8% (268.8k) = 3.6288M<br>MST: (trống)** | Tổng: 3.6288M<br>Hoàn khai: 971.2k | **Tổng: 3.6288M<br>Hoàn khai: 971.2k** | **MST bên mua: Trống hoàn toàn (`None`)**; Số học và hoàn ứng hoàn toàn khớp. |

---

## 3. Files Created and Modified

### Staging and Authoring Tool
- `scripts/generate_uc3_variations.py`: Created portable variation generator supporting macOS, Linux, and Windows font resolution, table layouts matching original templates, integer VAT calculation, and deterministic expected/DOCX/PDF output.
- `.runtime/backup-uc03-tc05-tc10/`: Pre-generation backup of all original files and inventory manifest.
- `.runtime/staging-uc03-variations/`: Staged files, verified via `pypdf` and rendered to 2x resolution PNGs via `pypdfium2` prior to deployment.

### Deployed Testcases (`data/tham-khao/uc-03/`)
For each folder `tc05-...` through `tc10-...`:
- `expected.json`: Updated `accounting_facts` and `rationale` to match the new deterministic ground truth.
- `report_hoan_ung.pdf` & `report_hoan_ung.docx`: Updated with case-specific purpose, itemization, advance, and invariant.
- `hoa_don_dien_tu.pdf` & `hoa_don_dien_tu.docx`: Updated with case-specific invoice quantities, amounts, and buyer tax codes.

### Contexts and Catalogs (`data/demo/`)
- `data/demo/README.md`: Updated table rows for TC05 to TC10 reflecting new declared cost and advance amounts.
- `data/demo/company-context.json`: Regenerated via `scripts/sinh_context_uc03.py` with 6 distinct activities and 6 distinct advance ledger records.
- `data/demo/manifest.json`: Updated case context links and PDF SHA-256 digests.
- `data/demo/cases/tc05-.../` to `tc10-.../`: Regenerated `context.json` and `context-ui.json` for each case.
- `data/tham-khao/uc-03/final-case-mapping-v3.json`: Updated `source_purpose` and `source_pdf_refs[].sha256` for TC05–TC10.

### Tests
- `tests/integration/test_uc03_demo_contexts.py`: Updated `ADVANCES` constant for indices 4 through 9 to match new advance amounts.

---

## 4. Verification Evidence

### 4.1 Non-Affected Files Integrity (SHA-256)
Verified using `scratch/verify_untouched.py` against `.runtime/backup-uc03-tc05-tc10/inventory_before.json`:
- **174 non-affected files** in `data/demo` and `data/tham-khao/uc-03` checked: **100% bit-for-bit identical**.
- TC01 (anchor) and TC12 (duplicate target) remain completely untouched.

### 4.2 Invariant & Delta Verification
Verified using `scratch/verify_staged.py`:
- TC05: `report_total (3.7M) - report_line_sum (3.2M) == 500.000` (PASS).
- TC06: `(A - E) (830.000) - declared_difference (770.000) == 60.000` (PASS).
- TC07: Words ("Bốn triệu không trăm bốn mươi nghìn đồng", 4.04M) vs numbers (3.78M) delta is `260.000` (PASS).
- TC08: `report_total (3.284M) - invoice_total (3.024M) == 260.000` (PASS); declared refund `916.000` matches paper total.
- TC09: `buyer_tax_code == "7777777777"` extracted from invoice text (PASS).
- TC10: `buyer_tax_code is None` and buyer tax code line in invoice is empty (PASS).
- Advance code check: Verified that none of the 6 reports contain artificial `TU-` codes.

### 4.3 Automated Test Suite Results
- `pytest tests/integration/test_hoangha_general_packets.py`: **5 passed in 0.02s** (All 25 cases & 65 PDFs match registered SHA-256).
- `pytest tests/integration/test_uc03_demo_contexts.py`: **6 passed in 0.64s** (All 25 advances with independent history verified).
- `pytest tests/integration/test_prompt_hardening_audit.py`: **5 passed in 0.16s** (Negative audit scoring passes with preserved 500k and 60k deltas).
- `pytest tests/unit/test_dossier_linking.py`: **20 passed in 0.01s**.
- `pytest tests/integration/test_document_arithmetic_gate.py tests/unit/test_document_arithmetic.py`: **47 passed in 0.09s**.
- Core UC/Demo integration tests: **62 passed in 2.11s**.
- Frontend test suite (`npm --prefix frontend test -- --run`): **11 test files passed, 48 passed, 2 skipped in 2.39s**.

### 4.4 External Worktree Integrity
Checked via `git -C .worktrees/hoangha status --short`:
- `.worktrees/hoangha` source files remain completely untouched.

---

## 5. Reproduction Instructions

To reproduce the generator and context regeneration from scratch:
```bash
# 1. Generate staged variations
rtk proxy uv run --with python-docx python scripts/generate_uc3_variations.py --output .runtime/staging-uc03-variations

# 2. Deploy to data/tham-khao/uc-03/
rtk proxy uv run python -c '
import shutil
from pathlib import Path
staging = Path(".runtime/staging-uc03-variations")
target = Path("data/tham-khao/uc-03")
for c in sorted(staging.iterdir()):
    if not c.is_dir() or not c.name.startswith("tc"):
        continue
    dest_dir = target / c.name
    for item in c.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_dir / item.name)
'

# 3. Update final-case-mapping-v3.json hashes and README.md
# (handled in scripts/sinh_context_uc03.py context generation)

# 4. Regenerate contexts and manifest
rtk proxy uv run python scripts/sinh_context_uc03.py

# 5. Run integrity tests
rtk proxy uv run pytest tests/integration/test_hoangha_general_packets.py tests/integration/test_uc03_demo_contexts.py
```

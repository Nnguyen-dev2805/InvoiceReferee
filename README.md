# InvoiceReferee

**AI Purchase Invoice Review & Escalation Agent**

InvoiceReferee hỗ trợ kế toán bên mua kiểm tra các giao dịch mua hàng có PO và Goods Receipt. Hệ thống gom bằng chứng của cùng một transaction, chạy các kiểm tra deterministic, áp dụng policy và trả một trong ba quyết định:

```text
AUTO_PROCESS
REQUEST_INFO
ESCALATE
```

`AUTO_PROCESS` chỉ có nghĩa là hồ sơ routine đã đủ căn cứ để đi tiếp sang bước payment review; hệ thống không tự chuyển tiền.

## Sprint 1 scope

```text
Purchase Order
→ Goods Receipt
→ Supplier Invoice
→ Review
→ Payment Review
```

Sprint 1 chỉ bao phủ **PO-based goods purchases có Goods Receipt**.

## Core checks

1. Vendor match
2. Item match
3. Quantity match, gồm cumulative quantity theo item
4. Unit price match
5. Amount check
6. Duplicate invoice
7. Payment status
8. Cumulative PO limit

## Documentation

- `docs/CHALLENGE.md` — đề thi yêu cầu gì và judge kiểm tra thế nào
- `docs/PRODUCT_SPEC.md` — sản phẩm Sprint 1 phải làm gì
- `docs/POLICY.md` — decision boundary và policy v0
- `docs/DATA_MODEL.md` — schema contract giữa các module
- `docs/DECISION_FLOW.md` — flow từ input đến decision
- `docs/TEST_CASES.md` — 17 test cases + Verify cases
- `docs/ARCHITECTURE.md` — module, interface và ownership
- `docs/EVALUATION_PLAN.md` — kế hoạch unseen tests, user feedback và đo lường Sprint 2
- `docs/superpowers/specs/2026-09-20-invoice-referee-design.md` — design spec tổng hợp
- `docs/superpowers/plans/2026-09-20-invoice-referee-implementation.md` — implementation plan
- `RUNBOOK.md` — cách chạy và verify
- `BUILD_LOG.md` — nhật ký phát triển

## Current state

Project đang ở giai đoạn **pre-code specification**. Các tài liệu cốt lõi đã được chốt trước khi bắt đầu implementation.


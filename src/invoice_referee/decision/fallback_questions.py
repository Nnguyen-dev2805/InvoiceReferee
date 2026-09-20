"""Deterministic explanation/question templates.

Used only when the LLM provider fails, times out, or returns invalid output.
Templates stay specific (they cite concrete facts) but are less flexible than the
normal LLM path. Fallback use must be recorded in the assessment/audit.
"""

from __future__ import annotations

from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.policy.engine import PolicyOutcome


def _check(checks: list[m.CheckResult], check_id: Optional[str]) -> Optional[m.CheckResult]:
    if check_id is None:
        return None
    for c in checks:
        if c.check_id == check_id:
            return c
    return None


def build_question(
    outcome: PolicyOutcome, tx: m.Transaction, checks: list[m.CheckResult]
) -> str:
    """Return a specific, answerable question for a non-routine outcome."""
    if outcome.action is m.DecisionAction.AUTO_PROCESS:
        return ""

    rules = set(outcome.policy_rule_ids)
    inv = tx.invoice
    po = tx.po

    if outcome.uncertainty_type is m.UncertaintyType.OUTSIDE_POLICY:
        return (
            "Giao dịch này không thuộc workflow PO-based goods purchase mà policy hiện tại "
            "bao phủ. Ai là người có thẩm quyền xử lý loại giao dịch này?"
        )

    if outcome.uncertainty_type is m.UncertaintyType.BEYOND_AUTHORITY:
        amount = inv.total_amount if inv and inv.total_amount is not None else (po.approved_total if po else None)
        return (
            f"Giao dịch {amount} vượt ngưỡng tự xử lý {50_000_000}. "
            "Finance Manager có phê duyệt giao dịch này không?"
        )

    # FACTUAL_UNKNOWN branches, most specific first.
    if "P01" in rules and po is None:
        return "Không tìm thấy Purchase Order cho invoice này. PO ID hoặc PO liên quan là gì?"
    if "P04" in rules:
        return "Chưa có xác nhận nhận hàng cho PO này. Goods Receipt tương ứng ở đâu?"
    if "P15" in rules:
        return "Số tiền trên invoice chưa đọc được chắc chắn. Giá trị chính xác là bao nhiêu?"

    cr = _check(checks, outcome.primary_check_id)
    if cr is not None:
        cid = cr.check_id
        if cid == "CHECK_VENDOR":
            return (
                f"Supplier trên PO là {cr.expected} nhưng invoice được phát hành bởi {cr.actual}. "
                "Có thay đổi supplier đã được phê duyệt không?"
            )
        if cid == "CHECK_ITEM":
            return "Invoice có item chưa xuất hiện trong PO. Có PO điều chỉnh hoặc phê duyệt bổ sung item này không?"
        if cid == "CHECK_QUANTITY":
            return (
                f"Goods Receipt xác nhận đã nhận {cr.expected} đơn vị nhưng tổng invoice tính {cr.actual} đơn vị. "
                "Có biên bản nhận bổ sung hoặc điều chỉnh nào chưa được cung cấp không?"
            )
        if cid == "CHECK_PRICE":
            return (
                f"PO phê duyệt đơn giá {cr.expected} nhưng invoice dùng {cr.actual}. "
                "Có phê duyệt điều chỉnh đơn giá không?"
            )
        if cid == "CHECK_AMOUNT":
            return (
                f"PO được phê duyệt {cr.expected} nhưng invoice là {cr.actual}. "
                "Có PO điều chỉnh hoặc phê duyệt tăng thêm không?"
            )
        if cid == "CHECK_DUPLICATE":
            return "Invoice này đã xuất hiện trong lịch sử xử lý. Đây là bản gửi lại của invoice cũ hay một invoice mới hợp lệ?"
        if cid == "CHECK_PAYMENT":
            status = cr.actual
            if status == "PARTIALLY_PAID":
                paid = 0
                for rec in tx.payment_history:
                    if inv and rec.invoice_id == inv.invoice_id:
                        paid = rec.paid_amount
                total = inv.total_amount if inv else None
                remaining = (total - paid) if (total is not None) else None
                return (
                    f"Invoice là {total} và đã thanh toán {paid}. "
                    f"Có phải phần còn lại {remaining} vẫn đang chờ thanh toán không?"
                )
            if status == "PAID":
                return (
                    "Payment history cho thấy invoice này đã được thanh toán. "
                    "Có lý do hợp lệ nào để đưa invoice trở lại payment review không?"
                )
            return "Chưa xác định được trạng thái thanh toán của invoice này. Invoice hiện là UNPAID, PARTIALLY_PAID hay PAID?"
        if cid == "CHECK_PO_LIMIT":
            return (
                f"Tổng các invoice cho PO này sẽ đạt {cr.actual}, vượt PO {cr.expected}. "
                "Có PO amendment hoặc phê duyệt bổ sung không?"
            )

    return outcome.reason or "Cần bổ sung thông tin để tiếp tục xử lý giao dịch này."

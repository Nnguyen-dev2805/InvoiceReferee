"""Human-readable accounting summary derived from normalized settlement facts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _money(value: Decimal, currency: str) -> str:
    formatted = f"{value:,.0f}".replace(",", ".")
    return f"{formatted} {currency}"


def build_settlement_business_summary(case: Mapping[str, Any]) -> dict[str, str | None]:
    """Build deterministic cash-flow and business-context labels for accountants."""

    currency = str(case.get("currency") or "VND")
    total = _decimal(case.get("claimed_total"))
    advance = _decimal(case.get("allocated_advance_amount"))
    settlement_type = str(case.get("settlement_type") or "")

    if settlement_type == "ADVANCE_SETTLEMENT":
        difference = abs(total - advance)
        if total > advance:
            cash_flow = f"Công ty thanh toán thêm {_money(difference, currency)}"
            cash_flow_direction = "COMPANY_PAYS_EMPLOYEE"
        elif total < advance:
            cash_flow = f"Nhân viên hoàn trả công ty {_money(difference, currency)}"
            cash_flow_direction = "EMPLOYEE_RETURNS_COMPANY"
        else:
            cash_flow = "Đã quyết toán đủ, không phát sinh khoản phải thanh toán thêm"
            cash_flow_direction = "NO_DIFFERENCE"
    else:
        difference = total
        cash_flow = f"Công ty hoàn lại cho nhân viên {_money(total, currency)}"
        cash_flow_direction = "COMPANY_REIMBURSES_EMPLOYEE"

    account_number = str(case.get("bank_account_number") or "").strip() or None
    beneficiary_name = str(case.get("beneficiary_name") or "").strip() or None
    bank_name = str(case.get("bank_name") or "").strip() or None
    payment_account = None
    if account_number:
        account_parts = [account_number]
        if bank_name:
            account_parts.append(bank_name)
        if beneficiary_name:
            account_parts.append(beneficiary_name)
        payment_account = " · ".join(account_parts)
    account_label = (
        "Thông tin tài khoản trên hồ sơ"
        if cash_flow_direction == "EMPLOYEE_RETURNS_COMPANY"
        else "Tài khoản nhận tiền"
    )

    return {
        "employee": str(case.get("employee_name") or "Chưa xác định"),
        "department": str(case.get("department") or "Chưa xác định"),
        "purpose": str(case.get("purpose") or "").strip() or "Chưa nêu mục đích",
        "total": _money(total, currency),
        "advance": _money(advance, currency) if settlement_type == "ADVANCE_SETTLEMENT" else None,
        "difference": _money(difference, currency),
        "cash_flow": cash_flow,
        "cash_flow_direction": cash_flow_direction,
        "payment_account": payment_account,
        "account_label": account_label,
    }


def build_settlement_success_reason(case: Mapping[str, Any]) -> str:
    """Create the concise queue/detail reason shown for a passed case."""

    summary = build_settlement_business_summary(case)
    parts = [
        f"{summary['employee']} ({summary['department']})",
        str(summary["cash_flow"]),
        f"Tổng chi phí {summary['total']}",
    ]
    if summary["advance"]:
        parts.append(f"Đã tạm ứng {summary['advance']}")
    parts.append(f"Mục đích: {summary['purpose']}")
    if summary["payment_account"]:
        parts.append(f"{summary['account_label']}: {summary['payment_account']}")
    return ". ".join(parts) + "."

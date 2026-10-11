from invoice_referee.application.settlement_summary import (
    build_settlement_business_summary,
    build_settlement_success_reason,
)


def _case(**overrides):
    case = {
        "employee_name": "Nguyễn Văn A",
        "department": "Phòng Kỹ thuật",
        "purpose": "Công tác triển khai hệ thống",
        "settlement_type": "ADVANCE_SETTLEMENT",
        "claimed_total": "8500000",
        "allocated_advance_amount": "10000000",
        "currency": "VND",
        "beneficiary_name": None,
        "bank_account_number": None,
        "bank_name": None,
    }
    case.update(overrides)
    return case


def test_advance_summary_states_employee_return_amount() -> None:
    summary = build_settlement_business_summary(_case())

    assert summary["cash_flow"] == "Nhân viên hoàn trả công ty 1.500.000 VND"
    assert summary["total"] == "8.500.000 VND"
    assert summary["advance"] == "10.000.000 VND"


def test_advance_summary_states_company_additional_payment() -> None:
    summary = build_settlement_business_summary(
        _case(claimed_total="12500000")
    )

    assert summary["cash_flow"] == "Công ty thanh toán thêm 2.500.000 VND"


def test_reimbursement_reason_includes_context_and_optional_bank_account() -> None:
    reason = build_settlement_success_reason(
        _case(
            settlement_type="EMPLOYEE_REIMBURSEMENT",
            claimed_total="3200000",
            allocated_advance_amount="0",
            beneficiary_name="NGUYỄN VĂN A",
            bank_account_number="0123456789",
            bank_name="Ngân hàng Demo",
        )
    )

    assert "Nguyễn Văn A (Phòng Kỹ thuật)" in reason
    assert "Công ty hoàn lại cho nhân viên 3.200.000 VND" in reason
    assert "Công tác triển khai hệ thống" in reason
    assert "0123456789 · Ngân hàng Demo · NGUYỄN VĂN A" in reason

from decimal import Decimal

from invoice_referee.application.decision_guard import build_settlement_decision
from invoice_referee.domain import (
    AutomationDecision,
    BusinessContext,
    ExpenseCategory,
    ExpenseItemDraft,
    SettlementDraft,
    SettlementType,
    SubmissionSourceType,
    UncertaintyType,
)
from invoice_referee.policy import evaluate_settlement_policy


def _draft(
    *,
    purpose: str = "Gặp khách hàng dự án Demo",
    category: ExpenseCategory = ExpenseCategory.CLIENT_MEAL,
    amount: str = "1200000",
    evidence_names: list[str] | None = None,
) -> SettlementDraft:
    return SettlementDraft(
        settlement_type=SettlementType.EMPLOYEE_REIMBURSEMENT,
        source_type=SubmissionSourceType.DIGITAL_FORM,
        business_context=BusinessContext(purpose=purpose),
        expense_items=[
            ExpenseItemDraft(
                item_id="ITEM-001",
                category=category,
                description="Tiếp khách",
                claimed_amount=Decimal(amount),
                evidence_names=evidence_names or [],
            )
        ],
    )


def test_complete_routine_case_is_ready_for_accounting() -> None:
    findings = evaluate_settlement_policy(
        _draft(evidence_names=["bill.jpg"]),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.AUTO_PROCESS
    assert decision.uncertainty_type == UncertaintyType.NONE


def test_missing_context_and_evidence_requests_information() -> None:
    findings = evaluate_settlement_policy(
        _draft(purpose=""),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.REQUEST_INFO
    assert decision.uncertainty_type == UncertaintyType.FACTUAL_UNKNOWN
    assert decision.target.value == "EMPLOYEE"


def test_clear_personal_expense_escalates_outside_policy() -> None:
    findings = evaluate_settlement_policy(
        _draft(
            category=ExpenseCategory.PERSONAL,
            evidence_names=["bill.jpg"],
        ),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.ESCALATE
    assert decision.uncertainty_type == UncertaintyType.OUTSIDE_POLICY


def test_amount_above_authority_escalates_to_director() -> None:
    findings = evaluate_settlement_policy(
        _draft(
            category=ExpenseCategory.OTHER,
            amount="60000000",
            evidence_names=["contract.pdf"],
        ),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.ESCALATE
    assert decision.uncertainty_type == UncertaintyType.BEYOND_AUTHORITY
    assert decision.target.value == "DIRECTOR"

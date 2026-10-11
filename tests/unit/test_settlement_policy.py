from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_referee.application.decision_guard import build_settlement_decision
from invoice_referee.domain import (
    AlternativeEvidenceType,
    AutomationDecision,
    BusinessContext,
    ExpenseCategory,
    ExpenseEvidenceStatus,
    ExpenseItemDraft,
    SettlementDraft,
    SettlementFinding,
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
    evidence_status: ExpenseEvidenceStatus = ExpenseEvidenceStatus.ORIGINAL_EVIDENCE,
    alternative_evidence_type: AlternativeEvidenceType | None = None,
    evidence_exception_reason: str | None = None,
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
                evidence_status=evidence_status,
                alternative_evidence_type=alternative_evidence_type,
                evidence_exception_reason=evidence_exception_reason,
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


def test_pending_signature_approval_does_not_block_a_clear_case() -> None:
    decision = build_settlement_decision(
        [
            SettlementFinding(
                rule_id="SET_APPROVAL_001",
                status="PENDING_APPROVAL",
                message="Hồ sơ đang chờ kế toán xác nhận chữ ký.",
            )
        ]
    )

    assert decision.automation_decision == AutomationDecision.AUTO_PROCESS
    assert decision.uncertainty_type == UncertaintyType.NONE


def test_advance_settlement_accepts_declared_amount_without_advance_id() -> None:
    draft = _draft(evidence_names=["bill.jpg"])
    draft.settlement_type = SettlementType.ADVANCE_SETTLEMENT
    draft.advance_id = None
    draft.allocated_advance_amount = Decimal("4000000")

    findings = evaluate_settlement_policy(draft, has_paper_form=False)
    advance_finding = next(
        finding for finding in findings if finding.rule_id == "SET_ADV_001"
    )

    assert advance_finding.status == "PASS"


def test_digital_advance_settlement_requires_only_a_positive_amount() -> None:
    draft = _draft(evidence_names=["bill.jpg"])
    draft.settlement_type = SettlementType.ADVANCE_SETTLEMENT
    draft.advance_id = None
    draft.allocated_advance_amount = Decimal("0")

    decision = build_settlement_decision(
        evaluate_settlement_policy(draft, has_paper_form=False)
    )

    assert decision.automation_decision == AutomationDecision.REQUEST_INFO
    assert decision.primary_finding_code == "SET_ADV_001"


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
            amount="110000000",
            evidence_names=["contract.pdf"],
        ),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.ESCALATE
    assert decision.uncertainty_type == UncertaintyType.BEYOND_AUTHORITY
    assert decision.target.value == "DIRECTOR"


def test_alternative_evidence_is_routed_to_accountant_for_exception_review() -> None:
    findings = evaluate_settlement_policy(
        _draft(
            evidence_names=["chuyen-khoan.png"],
            evidence_status=ExpenseEvidenceStatus.ALTERNATIVE_EVIDENCE,
            alternative_evidence_type=AlternativeEvidenceType.PAYMENT_PROOF,
            evidence_exception_reason="Nhà cung cấp cá nhân không xuất hóa đơn.",
        ),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.ESCALATE
    assert decision.primary_finding_code == "SET_ALT_EVIDENCE_001"
    assert decision.target.value == "ACCOUNTANT"


def test_no_evidence_with_reason_is_routed_to_accountant() -> None:
    findings = evaluate_settlement_policy(
        _draft(
            evidence_status=ExpenseEvidenceStatus.NO_EVIDENCE,
            evidence_exception_reason="Người cung cấp dịch vụ không cấp chứng từ.",
        ),
        has_paper_form=False,
    )

    decision = build_settlement_decision(findings)

    assert decision.automation_decision == AutomationDecision.ESCALATE
    assert decision.primary_finding_code == "SET_NO_EVIDENCE_001"


def test_alternative_or_missing_evidence_requires_reason() -> None:
    with pytest.raises(ValidationError):
        _draft(
            evidence_status=ExpenseEvidenceStatus.ALTERNATIVE_EVIDENCE,
            alternative_evidence_type=AlternativeEvidenceType.PAYMENT_PROOF,
        )
    with pytest.raises(ValidationError):
        _draft(evidence_status=ExpenseEvidenceStatus.NO_EVIDENCE)

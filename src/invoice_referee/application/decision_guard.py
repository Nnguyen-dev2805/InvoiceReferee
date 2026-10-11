"""Deterministic final routing for Track A findings."""

from __future__ import annotations

from invoice_referee.domain import (
    AutomationDecision,
    DecisionTarget,
    SettlementDecision,
    SettlementFinding,
    UncertaintyType,
)


CLEAR_REJECTION_RULES = frozenset(
    {
        "SET_CATEGORY_001",
        "SET_BUYER_IDENTITY_001",
        "SET_DUPLICATE_001",
    }
)


def _decision_for_finding(finding: SettlementFinding) -> AutomationDecision:
    if finding.rule_id in CLEAR_REJECTION_RULES:
        return AutomationDecision.RECOMMEND_REJECT
    if finding.uncertainty_type == UncertaintyType.SUSPICIOUS:
        return AutomationDecision.ACCOUNTANT_REVIEW
    if finding.uncertainty_type == UncertaintyType.FACTUAL_UNKNOWN:
        return AutomationDecision.REQUEST_INFO
    if (
        finding.uncertainty_type == UncertaintyType.BEYOND_AUTHORITY
        or finding.target
        in {
            DecisionTarget.DEPARTMENT_MANAGER,
            DecisionTarget.CHIEF_ACCOUNTANT,
            DecisionTarget.DIRECTOR,
        }
    ):
        return AutomationDecision.ESCALATE
    return AutomationDecision.ACCOUNTANT_REVIEW


def _finding_priority(finding: SettlementFinding) -> int:
    decision = _decision_for_finding(finding)
    if decision == AutomationDecision.RECOMMEND_REJECT:
        return 0
    if finding.uncertainty_type == UncertaintyType.SUSPICIOUS:
        return 1
    if decision == AutomationDecision.REQUEST_INFO:
        return 2
    if decision == AutomationDecision.ESCALATE:
        return 3
    return 4


def build_settlement_decision(
    findings: list[SettlementFinding],
    *,
    success_reason: str | None = None,
) -> SettlementDecision:
    blocking = [finding for finding in findings if finding.status == "FAIL"]
    if not blocking:
        source_refs = list(
            dict.fromkeys(
                source_ref
                for finding in findings
                for source_ref in finding.source_refs
            )
        )
        return SettlementDecision(
            automation_decision=AutomationDecision.READY_FOR_APPROVAL,
            uncertainty_type=UncertaintyType.NONE,
            target=DecisionTarget.ACCOUNTANT,
            reason=success_reason or (
                "Hồ sơ đã vượt qua các kiểm tra bắt buộc trong phạm vi policy "
                "demo và sẵn sàng để kế toán xem xét."
            ),
            source_refs=source_refs,
        )

    primary = min(blocking, key=_finding_priority)
    return SettlementDecision(
        automation_decision=_decision_for_finding(primary),
        uncertainty_type=primary.uncertainty_type,
        primary_finding_code=primary.rule_id,
        target=primary.target,
        question=primary.question,
        reason=primary.message,
        source_refs=primary.source_refs,
    )

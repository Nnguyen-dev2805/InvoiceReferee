"""Deterministic final routing for Track A findings."""

from __future__ import annotations

from invoice_referee.domain import (
    AutomationDecision,
    DecisionTarget,
    SettlementDecision,
    SettlementFinding,
    UncertaintyType,
)


def build_settlement_decision(
    findings: list[SettlementFinding],
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
            automation_decision=AutomationDecision.AUTO_PROCESS,
            uncertainty_type=UncertaintyType.NONE,
            target=DecisionTarget.ACCOUNTANT,
            reason=(
                "Hồ sơ đã vượt qua các kiểm tra bắt buộc trong phạm vi policy "
                "demo và sẵn sàng để kế toán xem xét."
            ),
            source_refs=source_refs,
        )

    priority = (
        UncertaintyType.OUTSIDE_POLICY,
        UncertaintyType.SUSPICIOUS,
        UncertaintyType.FACTUAL_UNKNOWN,
        UncertaintyType.BEYOND_AUTHORITY,
    )
    primary = next(
        finding
        for uncertainty in priority
        for finding in blocking
        if finding.uncertainty_type == uncertainty
    )
    decision = (
        AutomationDecision.REQUEST_INFO
        if primary.uncertainty_type == UncertaintyType.FACTUAL_UNKNOWN
        else AutomationDecision.ESCALATE
    )
    return SettlementDecision(
        automation_decision=decision,
        uncertainty_type=primary.uncertainty_type,
        primary_finding_code=primary.rule_id,
        target=primary.target,
        question=primary.question,
        reason=primary.message,
        source_refs=primary.source_refs,
    )

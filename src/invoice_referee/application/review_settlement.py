"""Human review actions for UC-03."""

from __future__ import annotations

from invoice_referee.domain import (
    AutomationDecision,
    DecisionTarget,
    SettlementDecision,
    UncertaintyType,
)
from invoice_referee.storage import SQLiteSettlementRepository


class ReviewSettlementService:
    def __init__(self, repository: SQLiteSettlementRepository) -> None:
        self.repository = repository

    def record_action(
        self,
        *,
        case_id: str,
        action_type: str,
        reason: str,
        override_decision: str | None = None,
        actor_id: str = "ACCOUNTANT-DEMO-001",
    ) -> None:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("Kế toán phải nhập lý do cho thao tác.")

        if action_type == "REPROCESS_CASE":
            self.repository.requeue_case(
                case_id=case_id,
                actor_id=actor_id,
                reason=normalized_reason,
            )
            return
        if action_type == "REQUEST_MORE_INFO":
            decision = SettlementDecision(
                automation_decision=AutomationDecision.REQUEST_INFO,
                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                primary_finding_code="HUMAN_REQUEST_INFO",
                target=DecisionTarget.EMPLOYEE,
                question=normalized_reason,
                reason="Kế toán yêu cầu nhân viên bổ sung thông tin.",
            )
            workflow_status = "WAITING_EMPLOYEE"
        elif action_type == "ESCALATE_CASE":
            decision = SettlementDecision(
                automation_decision=AutomationDecision.ESCALATE,
                uncertainty_type=UncertaintyType.BEYOND_AUTHORITY,
                primary_finding_code="HUMAN_ESCALATION",
                target=DecisionTarget.CHIEF_ACCOUNTANT,
                reason=normalized_reason,
            )
            workflow_status = "ESCALATED"
        elif action_type == "OVERRIDE_DECISION":
            if override_decision not in {
                AutomationDecision.AUTO_PROCESS.value,
                AutomationDecision.REQUEST_INFO.value,
                AutomationDecision.ESCALATE.value,
            }:
                raise ValueError("Quyết định override không hợp lệ.")
            automation_decision = AutomationDecision(override_decision)
            uncertainty = (
                UncertaintyType.NONE
                if automation_decision == AutomationDecision.AUTO_PROCESS
                else UncertaintyType.FACTUAL_UNKNOWN
            )
            decision = SettlementDecision(
                automation_decision=automation_decision,
                uncertainty_type=uncertainty,
                primary_finding_code="HUMAN_OVERRIDE",
                target=DecisionTarget.ACCOUNTANT,
                reason=normalized_reason,
            )
            workflow_status = "UNDER_REVIEW"
        elif action_type == "STOP_PROCESSING":
            decision = None
            workflow_status = "STOPPED"
        else:
            raise ValueError("Thao tác kế toán không được hỗ trợ.")

        self.repository.record_human_action(
            case_id=case_id,
            action_type=action_type,
            actor_id=actor_id,
            reason=normalized_reason,
            workflow_status=workflow_status,
            new_decision=decision,
        )

"""Append-only audit store and human-control recording.

Logically append-only: past events are never removed, even when a later human
override changes the effective decision. Stop changes workflow status only;
Override preserves the original agent decision. Sprint 1 keeps events in memory
with a JSON export for the demo.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from invoice_referee.domain import models as m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    def __init__(self, transaction_id: Optional[str] = None):
        self.transaction_id = transaction_id
        self._events: list[m.AuditEvent] = []
        self._seq = 0

    @property
    def events(self) -> tuple[m.AuditEvent, ...]:
        """The append-only event history, exposed read-only.

        Returning a tuple keeps the log append-only: a caller cannot clear,
        pop, or reassign an entry without going through ``append``.
        """
        return tuple(self._events)

    # --- core append ---------------------------------------------------------

    def append(
        self,
        event_type: str,
        *,
        actor: str = "InvoiceReferee",
        rule_id: Optional[str] = None,
        input_refs: Optional[list[str]] = None,
        result: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> m.AuditEvent:
        self._seq += 1
        event = m.AuditEvent(
            event_type=event_type,
            actor=actor,
            event_id=f"AUD-{self._seq:04d}",
            transaction_id=self.transaction_id,
            timestamp=_now(),
            rule_id=rule_id,
            input_refs=list(input_refs or []),
            result=result,
            reason=reason,
            details=dict(details or {}),
        )
        self._events.append(event)
        return event

    # --- typed helpers -------------------------------------------------------

    def record_transaction_created(self, tx: m.Transaction) -> m.AuditEvent:
        return self.append("TRANSACTION_CREATED", reason=f"Transaction {tx.transaction_id} created")

    # --- extraction / OCR events ---------------------------------------------

    def record_document_uploaded(
        self, document: m.UploadedDocument, *, actor: str = "InvoiceReferee"
    ) -> m.AuditEvent:
        return self.append(
            "DOCUMENT_UPLOADED",
            actor=actor,
            input_refs=[document.document_id],
            details={
                "filename": document.filename,
                "mime_type": document.mime_type,
                "size_bytes": document.size_bytes,
                "sha256": document.sha256,
            },
        )

    def record_document_validated(
        self, document: m.UploadedDocument, *, actor: str = "InvoiceReferee"
    ) -> m.AuditEvent:
        return self.append("DOCUMENT_VALIDATED", actor=actor, input_refs=[document.document_id])

    def record_ocr_completed(self, document: m.OCRDocument) -> m.AuditEvent:
        return self.append(
            "OCR_COMPLETED",
            input_refs=[document.document_id],
            details={
                "engine": document.engine,
                "engine_version": document.engine_version,
                "block_count": len(document.blocks),
                "processing_ms": document.processing_ms,
            },
        )

    def record_field_event(
        self,
        event_type: str,
        candidate: m.FieldCandidate,
        *,
        actor: str = "InvoiceReferee",
        reason: Optional[str] = None,
        alternatives: Optional[list[m.FieldCandidate]] = None,
    ) -> m.AuditEvent:
        """Record a field extraction/flag/confirm/correct event with provenance.

        Raw document bytes are never included; only block IDs, field values, and
        method/scores. ``alternatives`` captures the non-selected candidates for
        a conflict- or audit-aware record.
        """
        alternatives = list(alternatives or [])
        return self.append(
            event_type,
            actor=actor,
            input_refs=list(candidate.evidence_block_ids),
            result=candidate.status.value,
            reason=reason,
            details={
                "field_name": candidate.field_name,
                "raw_text": candidate.raw_text,
                "normalized_value": candidate.normalized_value,
                "original_normalized_value": candidate.original_normalized_value,
                "page_number": candidate.page_number,
                "selected_method": candidate.extraction_method,
                "provider_confidence": candidate.provider_confidence,
                "mapping_score": candidate.mapping_score,
                "section_role": candidate.section_role,
                "evidence_block_ids": list(candidate.evidence_block_ids),
                "alternative_count": len(alternatives),
                # Record the rejected values, not just how many there were, so a
                # conflict can be reconstructed from the audit trail alone.
                "alternatives": [
                    {
                        "value": alt.normalized_value,
                        "method": alt.extraction_method,
                        "evidence_block_ids": list(alt.evidence_block_ids),
                    }
                    for alt in alternatives
                ],
                "conflict": candidate.status is m.FieldStatus.CONFLICTING,
            },
        )

    def record_extraction_reviewed(
        self, result: m.InvoiceExtractionResult, *, actor: str = "InvoiceReferee"
    ) -> m.AuditEvent:
        return self.append(
            "EXTRACTION_REVIEWED",
            actor=actor,
            input_refs=[result.document_id],
            result=result.status.value,
        )

    def record_check(self, check: m.CheckResult) -> m.AuditEvent:
        return self.append(
            "CHECK_COMPLETED",
            rule_id=check.policy_rule_id,
            input_refs=check.evidence_refs,
            result=check.status.value,
            reason=check.reason,
            details={"check_id": check.check_id},
        )

    def record_assessment(self, assessment: m.AgentAssessment) -> m.AuditEvent:
        return self.append(
            "LLM_ASSESSMENT_CREATED",
            result=assessment.proposed_action.value,
            reason=assessment.explanation,
            details={
                "model": assessment.model,
                "prompt_version": assessment.prompt_version,
                "primary_check_id": assessment.primary_check_id,
                "fallback_used": assessment.fallback_used,
            },
        )

    def record_fallback_used(self, reason: str) -> m.AuditEvent:
        return self.append("LLM_FALLBACK_USED", reason=reason)

    def record_decision_guard(self, proposed_action: Optional[str], final_action: str) -> m.AuditEvent:
        return self.append(
            "DECISION_GUARD_APPLIED",
            result=final_action,
            details={
                "proposed_action": proposed_action,
                "final_action": final_action,
                "proposal_overridden": proposed_action is not None and proposed_action != final_action,
            },
        )

    def record_decision(self, decision: m.Decision) -> m.AuditEvent:
        return self.append(
            "DECISION_MADE",
            rule_id=None,
            result=decision.action.value,
            reason=decision.reason,
            details={
                "question": decision.question,
                "target": decision.target,
                "policy_rule_ids": list(decision.policy_rule_ids),
            },
        )

    # --- human controls ------------------------------------------------------

    def record_stop(self, tx: m.Transaction, actor: str, reason: str) -> m.HumanStop:
        previous = tx.workflow_status
        stop = m.HumanStop(
            actor=actor,
            previous_workflow_status=previous,
            new_workflow_status=m.WorkflowStatus.STOPPED,
            reason=reason,
            timestamp=_now(),
            stop_id=f"STOP-{len(tx.human_stops) + 1:03d}",
        )
        # Stop changes workflow status only; the agent decision is untouched.
        tx.workflow_status = m.WorkflowStatus.STOPPED
        tx.human_stops.append(stop)
        self.append(
            "STOPPED",
            actor=actor,
            reason=reason,
            details={
                "previous_workflow_status": previous.value,
                "new_workflow_status": m.WorkflowStatus.STOPPED.value,
            },
        )
        return stop

    def record_override(
        self, tx: m.Transaction, actor: str, overridden_action, reason: str
    ) -> m.HumanOverride:
        # HumanOverride enforces that overridden_action is a valid DecisionAction
        # (STOPPED is rejected there).
        original = tx.decision.action if tx.decision else None
        override = m.HumanOverride(
            actor=actor,
            original_action=original,
            overridden_action=overridden_action,
            reason=reason,
            timestamp=_now(),
            override_id=f"OVR-{len(tx.human_overrides) + 1:03d}",
        )
        tx.human_overrides.append(override)
        # Override changes only the effective action; the agent decision stays.
        tx.effective_action = override.overridden_action
        self.append(
            "OVERRIDDEN",
            actor=actor,
            reason=reason,
            details={
                "original_action": original.value if original else None,
                "overridden_action": override.overridden_action.value,
            },
        )
        return override

    # --- export --------------------------------------------------------------

    def export_json(self, *, indent: Optional[int] = 2) -> str:
        return json.dumps([asdict(e) for e in self.events], ensure_ascii=False, indent=indent)

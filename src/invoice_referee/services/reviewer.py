"""Production review orchestrator.

Single entry point used by both the UI and the Verify harness:

    build_transaction -> run_checks -> build_policy_context -> assess -> guard

with audit events recorded at each step. The final action is always decided by
the deterministic Decision Guard. This module contains no test-case-ID branches;
it evaluates fields and policy only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from invoice_referee.checks.engine import run_checks
from invoice_referee.policy.engine import build_policy_context
from invoice_referee.agent.service import assess
from invoice_referee.agent.llm_client import LLMClient
from invoice_referee.decision.guard import guard
from invoice_referee.audit.store import AuditStore


def review(
    evidence: dict[str, Any],
    client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    audit: Optional[AuditStore] = None,
) -> m.ReviewResult:
    tx = build_transaction(evidence)

    # Continue an existing audit timeline (e.g. from the OCR extraction phase)
    # so extraction, review, and human-control events share one ID sequence.
    if audit is None:
        audit = AuditStore(transaction_id=tx.transaction_id)
    elif audit.transaction_id is None:
        audit.transaction_id = tx.transaction_id
    elif audit.transaction_id != tx.transaction_id:
        raise ValueError("audit store transaction_id does not match the reviewed transaction")
    audit.record_transaction_created(tx)

    checks = run_checks(tx)
    tx.checks = checks
    for check in checks:
        audit.record_check(check)

    policy_context = build_policy_context(tx, checks)

    assessment = assess(tx, checks, policy_context, client=client, model=model)
    audit.record_assessment(assessment)
    if assessment.fallback_used:
        audit.record_fallback_used("LLM unavailable or returned invalid/untraceable output")

    decision = guard(assessment, tx, checks, policy_context)
    audit.record_decision_guard(
        proposed_action=assessment.proposed_action.value if assessment else None,
        final_action=decision.action.value,
    )
    audit.record_decision(decision)

    tx.decision = decision
    tx.effective_action = decision.action
    tx.audit_log = list(audit.events)
    tx.updated_at = datetime.now(timezone.utc).isoformat()

    return m.ReviewResult(
        transaction=tx,
        checks=checks,
        policy_context=policy_context,
        agent_assessment=assessment,
        decision=decision,
        audit_events=list(audit.events),
    )

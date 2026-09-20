"""Deterministic Decision Guard.

The Guard is the final authority. It recomputes the policy-correct action from
verified facts (via ``resolve_action``) and only borrows the LLM's question/
explanation when the LLM proposal matches that action. Any unsafe proposal
(e.g. AUTO_PROCESS despite a factual unknown or beyond-authority amount) is
overridden. The LLM can never change facts, arithmetic, or the final action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.policy.engine import resolve_action, PolicyOutcome
from invoice_referee.decision import fallback_questions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uncertainty(outcome: PolicyOutcome) -> Optional[m.Uncertainty]:
    if outcome.uncertainty_type is None:
        return None
    return m.Uncertainty(type=outcome.uncertainty_type, reason=outcome.reason)


def guard(
    assessment: Optional[m.AgentAssessment],
    tx: m.Transaction,
    checks: list[m.CheckResult],
    ctx: m.PolicyContext,
) -> m.Decision:
    outcome = resolve_action(tx, checks, ctx)

    # Decide whether the LLM proposal is compatible with the policy-correct action.
    proposal_matches = (
        assessment is not None and assessment.proposed_action is outcome.action
    )

    question: Optional[str] = None
    if outcome.action is not m.DecisionAction.AUTO_PROCESS:
        if proposal_matches and assessment.question and assessment.question.strip():
            question = assessment.question.strip()
        else:
            question = fallback_questions.build_question(outcome, tx, checks) or None

    target = outcome.target
    if proposal_matches and assessment.target and outcome.action is not m.DecisionAction.AUTO_PROCESS:
        # Trust the LLM target only when policy did not pin one.
        target = outcome.target or assessment.target

    return m.Decision(
        action=outcome.action,
        reason=outcome.reason,
        uncertainty=_uncertainty(outcome),
        question=question,
        target=target,
        policy_rule_ids=list(outcome.policy_rule_ids),
        decided_at=_now(),
    )

"""Recovery selection: pick one read-only step or ask the owner (contracts §5, §7, §10.5).

`AllowedStep` can only be a read/cross-check/ask — never a money, policy, SQL
or URL action. `propose_step` is deterministic: the highest-score eligible step
wins, ties break by fewer provider calls then stable identity; below the fixed
threshold it asks the owner instead.
"""

from __future__ import annotations

from typing import Literal

from invoice_referee.domain.common import Id, StrictModel
from invoice_referee.evidence.trace import RunBudget

StepKind = Literal["READ_FIELDS", "CROSS_CHECK", "ASK_OWNER"]


class AllowedStep(StrictModel):
    """One permitted, read-only step. Money/policy/SQL/URL actions are not a
    kind here, so a model cannot propose them."""

    kind: StepKind
    issue_id: Id
    source_ids: tuple[Id, ...] = ()
    fields: tuple[str, ...] = ()
    reason: str
    score: float = 0.0


class Opportunity(StrictModel):
    """A frozen decision point: sources, fields, eligible steps and budget."""

    id: Id
    root_id: Id
    issue_id: Id
    field: str
    source_ids: tuple[Id, ...] = ()
    page: int | None = None
    eligible_steps: tuple[AllowedStep, ...] = ()
    attempted_recovery_keys: tuple[str, ...] = ()
    remaining_budget: RunBudget | None = None


def propose_step(opportunity: Opportunity, budget: RunBudget) -> AllowedStep:
    """Choose one eligible read-only step, or ASK_OWNER. Deterministic."""
    allowed_sources = set(opportunity.source_ids)
    eligible: list[AllowedStep] = []
    for step in opportunity.eligible_steps:
        if not set(step.source_ids) <= allowed_sources:
            raise ValueError(
                f"step for issue {step.issue_id} reads a source outside this root"
            )
        if step.score >= budget.threshold and budget.can_call_llm():
            eligible.append(step)

    if not eligible:
        return AllowedStep(
            kind="ASK_OWNER",
            issue_id=opportunity.issue_id,
            source_ids=(),
            fields=(opportunity.field,),
            reason="no eligible read-only step above threshold",
            score=0.0,
        )

    # Highest score; tie by fewer sources (fewer provider calls), then stable id.
    chosen = sorted(
        eligible,
        key=lambda s: (-s.score, len(s.source_ids), s.source_ids, s.fields, s.reason),
    )[0]
    return chosen

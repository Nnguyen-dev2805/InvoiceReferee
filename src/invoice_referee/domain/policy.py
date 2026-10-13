"""Policy versions, grants and authorizing decisions (contracts §2, §3, §5).

Policy eligibility follows the expense time; a grant follows the action or
commit time. Both carry an effective interval so a decision can be traced to
the version that was in force.
"""

from __future__ import annotations

from datetime import datetime

from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, Vnd


class PolicyVersion(StrictModel):
    id: Id
    version: str
    effective_from: datetime
    effective_to: datetime | None = None
    profile: str
    rules: tuple[str, ...] = ()


class Grant(StrictModel):
    """A scoped authority to act. `max_amount` is per action, not per role."""

    id: Id
    version: str
    actor: Id
    actions: tuple[str, ...]
    scope: str
    max_amount: Vnd
    effective_from: datetime
    effective_to: datetime | None = None


class BudgetDecision(StrictModel):
    """A verified budget B for one activity over an explicit effect range."""

    id: Id
    activity: Id
    amount: Vnd
    effect_range: tuple[datetime, datetime | None]
    actor: Id
    grant_ref: Id | None = None
    refs: tuple[EvidenceRef, ...] = ()


class ExceptionDecision(StrictModel):
    """A scoped exception: exact rule, expenses, action and maximum effect."""

    rule_id: str
    expense_ids: tuple[Id, ...]
    activity: Id
    max_effect: Vnd
    actions: tuple[str, ...]
    actor: Id
    grant_ref: Id | None = None
    decided_at: datetime
    effect_range: tuple[datetime, datetime | None]
    refs: tuple[EvidenceRef, ...] = ()
    reason: str

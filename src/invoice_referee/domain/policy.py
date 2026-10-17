"""Policy versions, grants and authorizing decisions (contracts §2, §3, §5).

Policy eligibility follows the expense time; a grant follows the action or
commit time. Both carry an effective interval so a decision can be traced to
the version that was in force.
"""

from __future__ import annotations

from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, UtcDatetime, Vnd


class PolicyVersion(StrictModel):
    id: Id
    version: str
    effective_from: UtcDatetime
    effective_to: UtcDatetime | None = None
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
    effective_from: UtcDatetime
    effective_to: UtcDatetime | None = None
    # Profiles this grant is valid for; empty means profile-agnostic (plan R3).
    allowed_profiles: tuple[str, ...] = ()


class BudgetDecision(StrictModel):
    """Legacy activity budget record; accepted for import, ignored by decisions."""

    id: Id
    activity: Id
    amount: Vnd
    effect_range: tuple[UtcDatetime, UtcDatetime | None]
    actor: Id
    grant_ref: Id | None = None
    refs: tuple[EvidenceRef, ...] = ()


class CategoryPolicy(StrictModel):
    """A versioned per-item category cap and submission window (T3).

    Imported from Hoangha's accepted rules: work/client meal <=5,000,000 VND per
    canonical expense, taxi/ride <=2,000,000 VND per canonical expense, and a
    30-calendar-day submission window from the established expense date. A
    category with no explicit cap still passes the ordinary policy, evidence and
    authority gates; it is never an implicit unlimited PASS. Bound to a policy
    version and scope.
    """

    id: Id
    version: str
    effective_from: UtcDatetime
    effective_to: UtcDatetime | None = None
    profile: str | None = None
    # category -> per-item cap (VND). A category absent from this map has no
    # separate cap (only the ordinary gates apply).
    per_item_caps: dict[str, Vnd] = {}
    submission_window_days: int | None = None
    # Categories explicitly excluded from business recognition (e.g. PERSONAL).
    excluded_categories: tuple[str, ...] = ()


class ExceptionDecision(StrictModel):
    """A scoped exception: exact rule, expenses, action and maximum effect."""

    rule_id: str
    expense_ids: tuple[Id, ...]
    activity: Id
    max_effect: Vnd
    actions: tuple[str, ...]
    actor: Id
    grant_ref: Id | None = None
    decided_at: UtcDatetime
    effect_range: tuple[UtcDatetime, UtcDatetime | None]
    refs: tuple[EvidenceRef, ...] = ()
    reason: str


class ActionAuthorization(StrictModel):
    """A local human decision for one material basis, never a standing grant."""
    id: Id
    action: str
    amount: Vnd
    activity: Id
    actor: Id
    grant_ref: Id
    issued_at: UtcDatetime | None = None
    remaining_issued: Vnd | None = None
    grant_fingerprint: str
    basis: str
    decided_at: UtcDatetime
    reason: str
    refs: tuple[EvidenceRef, ...] = ()

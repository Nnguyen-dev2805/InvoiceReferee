"""Policy/authority assessment: issues and the proposed effect (contracts §2, §4–§5).

A question must be answerable and go to the right owner. Grants are per action
and per scope/time. E <= 8m self-recognizes; abs(S) <= 4m self-issues; the
approver covers <= 20m. Policy eligibility follows the expense time; a grant
follows the commit time.
"""

from __future__ import annotations

from datetime import timedelta

from invoice_referee.domain.case import AssessmentInput
from invoice_referee.domain.policy import BudgetDecision, Grant
from invoice_referee.reconciliation.policy import evaluate_policy
from invoice_referee.reconciliation.service import Reconciler
from tests.factories import (
    ACTIVITY,
    APPROVER,
    DEFAULT_AS_OF,
    EMPLOYEE,
    coverage,
    default_grants,
    ref,
    scope,
    snapshot,
)


def _assess(**kwargs):
    return Reconciler().assess(snapshot(**kwargs))


def _issue_kinds(result) -> set[str]:
    return {issue.kind for issue in result.issues}


def test_incurred_budget_not_paid_budget() -> None:
    r = _assess(T=10_000_000, E=5_000_000, C=3_000_000, A=2_000_000, P=0, R=0, B=8_000_000)
    assert r.projection.T.value == 10_000_000
    assert any(i.kind == "POLICY" for i in r.issues)
    assert r.allowed_effect is None


def test_balanced_zero_has_no_effect() -> None:
    r = _assess(T=2_000_000, E=2_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000)
    assert r.projection.S.value == 0
    assert r.allowed_effect is None
    assert "POLICY" not in _issue_kinds(r)


def test_recognized_employee_paid_produces_pay_effect() -> None:
    # E8, A2, no P/R: S = 6m -> company pays 6m; E<=8m and abs(S)>4m so ISSUE
    # needs authority (approver 20m covers it).
    r = _assess(T=8_000_000, E=8_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000)
    assert r.projection.S.value == 6_000_000


def test_authority_when_E_over_8m() -> None:
    # E12/A11/B14 => S1, but E exceeds the 8m self-recognition limit.
    r = _assess(T=14_000_000, E=12_000_000, C=0, A=11_000_000, P=0, R=0, B=14_000_000)
    assert "AUTHORITY" in _issue_kinds(r)
    assert r.allowed_effect is None


def test_authority_when_issue_over_4m_without_grant() -> None:
    # S = 6m exceeds the 4m self-issue limit and there is no approver grant.
    no_issue_grant = tuple(
        g for g in default_grants() if "ISSUE_PAYMENT" not in g.actions
    )
    r = Reconciler().assess(
        snapshot(T=8_000_000, E=8_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000,
                 grants=no_issue_grant)
    )
    assert "AUTHORITY" in _issue_kinds(r)
    assert r.allowed_effect is None


def test_budget_boundary_is_inclusive() -> None:
    # T == B is within budget; T = B + 1 is over.
    at_b = _assess(T=8_000_000, E=8_000_000, C=0, A=8_000_000, P=0, R=0, B=8_000_000)
    assert "POLICY" not in _issue_kinds(at_b)
    over_b = _assess(T=8_000_001, E=8_000_000, C=0, A=8_000_000, P=0, R=0, B=8_000_000)
    assert "POLICY" in _issue_kinds(over_b)


def test_missing_coverage_blocks_zero_conclusion() -> None:
    r = Reconciler().assess(
        snapshot(T=0, E=0, C=0, A=0, P=0, R=0, B=8_000_000, coverage=False)
    )
    assert r.projection.S.state != "KNOWN" or "FACT" in _issue_kinds(r)


def test_expired_grant_is_not_authority() -> None:
    # A grant whose effective interval ended before the decision is not usable.
    expired = Grant(
        id="grant:approver:20m",
        version="v1",
        actor=APPROVER,
        actions=("RECOGNIZE_COST", "ISSUE_PAYMENT", "ISSUE_COLLECTION"),
        scope=ACTIVITY,
        max_amount=20_000_000,
        effective_from=DEFAULT_AS_OF - timedelta(days=30),
        effective_to=DEFAULT_AS_OF - timedelta(days=10),
    )
    r = Reconciler().assess(
        snapshot(T=14_000_000, E=12_000_000, C=0, A=11_000_000, P=0, R=0,
                 B=14_000_000, grants=(expired,))
    )
    assert "AUTHORITY" in _issue_kinds(r)


def test_missing_budget_is_a_fact_issue() -> None:
    # No B record at all: an org-data FACT issue, not a fabricated zero B.
    r = Reconciler().assess(
        snapshot(T=1_000_000, E=1_000_000, C=0, A=1_000_000, P=0, R=0, B=8_000_000,
                 budget=())
    )
    assert "FACT" in _issue_kinds(r)


def test_e8_to_e9_requires_total_authority() -> None:
    # Growing the eligible portion across the 8m boundary requires authority,
    # not a silent top-up of a prior grant.
    r = _assess(T=9_000_000, E=9_000_000, C=0, A=0, P=0, R=0, B=9_000_000)
    assert "AUTHORITY" in _issue_kinds(r)


def test_new_paid_portion_requires_total_authority() -> None:
    # Isolate the recognition limit (S=0 so the issue limit is not involved):
    # E8 self-recognizes, but a new paid portion lifting E to 9m crosses the
    # 8m limit, so the whole E must be re-authorized (not topped up).
    within = _assess(T=8_000_000, E=8_000_000, C=0, A=8_000_000, P=0, R=0, B=8_000_000)
    assert "AUTHORITY" not in _issue_kinds(within)
    across = _assess(T=9_000_000, E=9_000_000, C=0, A=9_000_000, P=0, R=0, B=9_000_000)
    assert "AUTHORITY" in _issue_kinds(across)


def test_grant_scoped_to_another_activity_does_not_authorize() -> None:
    # A grant whose scope is a different activity must not cover this scope
    # (contracts §5: system grant has an explicit scope). E6/A2 => S4 would
    # self-issue, but the only ISSUE grant is scoped elsewhere, so it needs
    # authority and must not produce an allowed effect.
    other_scope = tuple(
        g.model_copy(update={"scope": "activity:other"}) for g in default_grants()
    )
    r = Reconciler().assess(
        snapshot(T=6_000_000, E=6_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000,
                 grants=other_scope)
    )
    assert r.allowed_effect is None
    assert "AUTHORITY" in _issue_kinds(r)


def test_grant_scope_matches_activity_is_authorized() -> None:
    # The committed demo grant is scoped to this activity and self-issues.
    r = _assess(T=6_000_000, E=6_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000)
    assert r.allowed_effect is not None
    assert r.allowed_effect.amount == 4_000_000


def test_prior_eligibility_basis_unchanged_by_pure_receipt() -> None:
    # A pure confirmed receipt (P) moves S and the money basis but must not
    # change the cost basis, so a prior eligibility decision is still reusable.
    base = Reconciler().assess(
        snapshot(T=8_000_000, E=8_000_000, C=0, A=2_000_000, P=0, R=0, B=8_000_000)
    )
    with_receipt = Reconciler().assess(
        snapshot(T=8_000_000, E=8_000_000, C=0, A=2_000_000, P=1_000_000, R=0, B=8_000_000)
    )
    assert with_receipt.cost_basis == base.cost_basis
    assert with_receipt.money_basis != base.money_basis

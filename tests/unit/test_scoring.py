"""Independent scoring (contracts §7, §11). Literal factories, no Reconciler.

The scorer grades an ActualResult against an independent GoldPacket. A false
affirmative (asserting a balanced/zero conclusion without coverage) is a
dangerous miss; a technical failure is not a business escalation; a wrong
ref/owner fails even when the money is right.
"""

from __future__ import annotations

from invoice_referee.evaluation.scorer import IndependentScorer
from tests.factories import (
    actual_affirmed_zero_without_coverage,
    actual_routine_pay,
    gold_requires_fact,
    gold_routine_pay,
)


def test_balanced_false_claim_is_dangerous() -> None:
    s = IndependentScorer().score(
        actual_affirmed_zero_without_coverage(), gold_requires_fact()
    )
    assert s.unsafe_affirmative_conclusion == 1
    assert s.union_dangerous_miss == 1


def test_correct_routine_is_not_dangerous() -> None:
    s = IndependentScorer().score(actual_routine_pay(), gold_routine_pay())
    assert s.union_dangerous_miss == 0
    assert s.correct_auto_completion == 1


def test_technical_failure_is_not_a_true_escalation() -> None:
    from tests.factories import actual_technical_error, gold_requires_fact

    s = IndependentScorer().score(actual_technical_error(), gold_requires_fact())
    # A technical failure counts as a completion failure, never as a correct
    # business escalation.
    assert s.technical_failure == 1
    assert s.correct_auto_completion == 0


def test_wrong_owner_fails_even_with_right_money() -> None:
    from tests.factories import actual_fact_wrong_owner, gold_requires_fact

    s = IndependentScorer().score(actual_fact_wrong_owner(), gold_requires_fact())
    # The right route but the wrong owner is not a correct escalation.
    assert s.unsafe_affirmative_conclusion == 0
    assert s.union_dangerous_miss == 1


def test_wrong_ref_fails_even_with_right_money() -> None:
    from tests.factories import actual_routine_bad_ref, gold_routine_pay

    s = IndependentScorer().score(actual_routine_bad_ref(), gold_routine_pay())
    assert s.union_dangerous_miss == 1


def test_lucky_latent_guess_is_not_rewarded() -> None:
    # Output equals the latent truth by luck but the observable source was
    # ambiguous: FAIL (contracts §7).
    from tests.factories import actual_lucky_guess_450, gold_ambiguous_450_480

    s = IndependentScorer().score(actual_lucky_guess_450(), gold_ambiguous_450_480())
    assert s.unsafe_affirmative_conclusion == 1


def test_grounded_fact_card_passes() -> None:
    from tests.factories import actual_grounded_fact_450_480, gold_ambiguous_450_480

    s = IndependentScorer().score(
        actual_grounded_fact_450_480(), gold_ambiguous_450_480()
    )
    assert s.unsafe_affirmative_conclusion == 0
    assert s.union_dangerous_miss == 0


def test_issue_stage_progression() -> None:
    # An initial payer UNKNOWN enables FACT; a verified E9 enables AUTHORITY.
    # The scorer grades the initial route independently of any later assistance.
    from invoice_referee.evaluation.scorer import ActualIssue
    from tests.factories import _actual, _gold

    initial = _actual(
        state="WAITING", issues=(ActualIssue(kind="FACT", owner="employee"),)
    )
    gold_initial = _gold("FACT", owner="employee")
    s_initial = IndependentScorer().score(initial, gold_initial)
    assert s_initial.union_dangerous_miss == 0

    # A verified E9 that only escalates for AUTHORITY is graded on that route.
    escalated = _actual(
        state="WAITING", issues=(ActualIssue(kind="AUTHORITY", owner="approver"),)
    )
    gold_auth = _gold("AUTHORITY", owner="approver")
    s_auth = IndependentScorer().score(escalated, gold_auth)
    assert s_auth.union_dangerous_miss == 0


def test_assisted_grant_does_not_hide_initial_route_error() -> None:
    # The initial route was wrong (auto-issued without the required fact); a
    # later assisted grant must not rescue the initial error.
    from invoice_referee.evaluation.scorer import ActualInstruction
    from tests.factories import _actual, _gold

    wrong_initial = _actual(
        state="READY_TO_EXECUTE",
        instructions=(ActualInstruction(direction="PAY", amount=9_000_000),),
    )
    gold_fact = _gold("FACT", owner="accountant")
    s = IndependentScorer().score(wrong_initial, gold_fact)
    assert s.union_dangerous_miss == 1

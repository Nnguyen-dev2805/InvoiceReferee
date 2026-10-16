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


def test_wrong_direction_fails_even_with_right_amount() -> None:
    # The company should PAY 3m; issuing a COLLECT of 3m is the wrong money
    # direction and must be a dangerous miss even though the amount matches
    # (contracts §4, §7).
    from invoice_referee.evaluation.scorer import ActualInstruction
    from tests.factories import _actual, gold_routine_pay

    wrong_direction = _actual(
        state="READY_TO_EXECUTE",
        instructions=(ActualInstruction(direction="COLLECT", amount=3_000_000),),
    )
    s = IndependentScorer().score(wrong_direction, gold_routine_pay())
    assert s.union_dangerous_miss == 1
    assert s.correct_auto_completion == 0


def test_correct_direction_passes() -> None:
    from tests.factories import actual_routine_pay, gold_routine_pay

    s = IndependentScorer().score(actual_routine_pay(), gold_routine_pay())
    assert s.union_dangerous_miss == 0
    assert s.correct_auto_completion == 1


def test_balanced_conclusion_when_human_required_is_unsafe() -> None:
    # Gold requires a POLICY question, but the app asserted a BALANCED (settled)
    # conclusion with no instruction and no issue: that affirmative conclusion
    # is a dangerous miss even though no money moved (contracts §7, §11).
    from tests.factories import _actual, _gold

    balanced = _actual(state="SETTLED", conclusion_status="BALANCED")
    s = IndependentScorer().score(balanced, _gold("POLICY", owner="approver"))
    assert s.unsafe_affirmative_conclusion == 1
    assert s.union_dangerous_miss == 1


def test_wrong_beneficiary_fails_even_with_right_amount() -> None:
    # The company should PAY the employee 3m; paying another beneficiary is a
    # dangerous miss even though direction and amount match (contracts §7).
    from invoice_referee.evaluation.scorer import ActualInstruction
    from tests.factories import _actual, _gold

    wrong = _actual(
        state="READY_TO_EXECUTE",
        instructions=(
            ActualInstruction(direction="PAY", amount=3_000_000, owner="vendor:other"),
        ),
    )
    gold = _gold("AUTO", expected_amounts={"PAY": 3_000_000}, owner="employee:employee-a")
    s = IndependentScorer().score(wrong, gold)
    assert s.unsafe_action == 1


def test_two_orders_summing_to_the_total_is_not_one_action() -> None:
    # Gold expects a single PAY 6m; two PAY 3m is not the same instruction.
    from invoice_referee.evaluation.scorer import ActualInstruction
    from tests.factories import _actual, _gold

    split = _actual(
        state="READY_TO_EXECUTE",
        instructions=(
            ActualInstruction(direction="PAY", amount=3_000_000),
            ActualInstruction(direction="PAY", amount=3_000_000),
        ),
    )
    gold = _gold("AUTO", expected_amounts={"PAY": 6_000_000})
    s = IndependentScorer().score(split, gold)
    assert s.unsafe_action == 1


def test_missing_required_issue_is_unsafe() -> None:
    # Gold requires a FACT issue; the app auto-completed with no issue at all.
    from tests.factories import _actual, _gold

    no_issue = _actual(state="SETTLED", affirmed_zero_without_coverage=True)
    s = IndependentScorer().score(no_issue, _gold("FACT", owner="employee"))
    assert s.union_dangerous_miss == 1


def test_runner_refs_reflect_reality() -> None:
    # The runner must report whether an issue/instruction actually carries
    # evidence refs, never a default True (contracts §7).
    from invoice_referee.evaluation.runner import actual_from_view
    from invoice_referee.evaluation.models import PacketInput, OrganizationContext, Submission

    packet = PacketInput(
        root_id="case:r",
        profile="TRAVEL",
        organization=OrganizationContext(tenant="tenant:demo", profile="TRAVEL"),
        submission=Submission(employee="employee:a", activity="activity:x", declared_purpose="p"),
    )

    from invoice_referee.domain.case import CaseView, Instruction
    from invoice_referee.domain.finance import Projection
    from invoice_referee.domain.common import Fact
    from invoice_referee.domain.issues import BusinessIssue

    empty_projection = Projection(
        T=Fact[int](key="T", state="UNKNOWN"),
        E=Fact[int](key="E", state="UNKNOWN"),
        C=Fact[int](key="C", state="UNKNOWN"),
        A=Fact[int](key="A", state="UNKNOWN"),
        P=Fact[int](key="P", state="UNKNOWN"),
        R=Fact[int](key="R", state="UNKNOWN"),
        unpaid=Fact[int](key="unpaid", state="UNKNOWN"),
        S=Fact[int](key="S", state="UNKNOWN"),
    )
    ungrounded = CaseView(
        id="case:r",
        version=1,
        state="WAITING",
        summary="x",
        issues=(
            BusinessIssue(
                id="issue:1", kind="FACT", field_or_rule="expense:payer",
                owner="employee", basis="b", question="q",
            ),
        ),
        instructions=(
            Instruction(
                id="i:1", root_id="case:r", direction="PAY", amount=1,
                status="ISSUED", basis="b", remaining=1, execution_state="NOT_STARTED",
            ),
        ),
        actual_money=empty_projection,
    )
    actual = actual_from_view(ungrounded, packet, mode="STUB", elapsed_ms=0.0)
    assert actual.issues[0].refs_ok is False
    assert actual.instructions[0].refs_ok is False


def test_empty_suite_fails_release_gate() -> None:
    # An empty run (total=0) must never be marked release: True
    report = IndependentScorer().release_gate([], total_human=0)
    assert report.release is False
    assert report.dangerous_miss_rate is None
    assert report.completion_rate is None


def test_missing_member_fails_release_gate() -> None:
    from tests.factories import actual_routine_pay, gold_routine_pay

    row = IndependentScorer().score(actual_routine_pay(), gold_routine_pay())
    # Expected 4 cases, but only 1 ran -> release must be False
    report = IndependentScorer().release_gate([row], total_human=0, expected_count=4)
    assert report.release is False


def test_unsupported_route_with_payment_is_unsafe_action() -> None:
    from invoice_referee.evaluation.scorer import ActualInstruction
    from tests.factories import _actual, _gold

    wrong = _actual(
        state="READY_TO_EXECUTE",
        instructions=(ActualInstruction(direction="PAY", amount=1_000_000),),
    )
    gold = _gold("UNSUPPORTED")
    s = IndependentScorer().score(wrong, gold)
    assert s.unsafe_action == 1
    assert s.correct_auto_completion == 0
    assert s.passed is False


def test_wrong_route_fact_vs_policy_fails_completion() -> None:
    from invoice_referee.evaluation.scorer import ActualIssue
    from tests.factories import _actual, _gold

    actual = _actual(
        state="WAITING",
        issues=(ActualIssue(kind="POLICY", owner="approver"),),
    )
    gold = _gold("FACT", owner="employee")
    s = IndependentScorer().score(actual, gold)
    assert s.actual_route == "POLICY"
    assert s.expected_route == "FACT"
    assert s.correct_auto_completion == 0
    assert s.passed is False


def test_technical_error_blocks_release() -> None:
    from tests.factories import actual_technical_error, gold_requires_fact

    row = IndependentScorer().score(actual_technical_error(), gold_requires_fact())
    report = IndependentScorer().release_gate([row], total_human=1)
    assert report.release is False


def test_legitimate_balanced_zero_with_coverage_passes() -> None:
    from tests.factories import _actual, _gold

    actual = _actual(
        state="SETTLED",
        conclusion_status="BALANCED",
        money_states={axis: "KNOWN" for axis in ("E","A","P","R","S")},
        money_values={"S":0},
    )
    gold = _gold("AUTO", expected_amounts={})
    s = IndependentScorer().score(actual, gold)
    assert s.union_dangerous_miss == 0
    assert s.correct_auto_completion == 1
    assert s.passed is True


def test_question_required_without_question_fails() -> None:
    from invoice_referee.evaluation.scorer import ActualIssue
    from tests.factories import _actual, _gold

    actual = _actual(
        state="WAITING",
        issues=(ActualIssue(kind="FACT", owner="employee", question=""),),
    )
    gold = _gold("FACT", owner="employee", question_required=True)
    s = IndependentScorer().score(actual, gold)
    assert s.passed is False


def test_nonempty_question_without_structured_oracle_is_not_certified() -> None:
    from invoice_referee.evaluation.scorer import ActualIssue
    from tests.factories import _actual, _gold

    actual = _actual(
        state="WAITING",
        issues=(
            ActualIssue(
                kind="FACT",
                owner="employee",
                question="Số tiền hoàn ứng thực tế là bao nhiêu?",
            ),
        ),
    )
    gold = _gold("FACT", owner="employee", question_required=True)
    s = IndependentScorer().score(actual, gold)
    assert s.passed is False
    assert s.correct_auto_completion == 0

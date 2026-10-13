"""Gold visibility and the union release gate (contracts §7, §11).

The app only receives the input layer; gold is loaded by the scorer after the
actual result exists. A single unsafe affirmative over ten human roots fails
release; the union counts action-miss and affirmative-miss per dossier.
"""

from __future__ import annotations

from invoice_referee.evaluation.scorer import IndependentScorer
from tests.factories import (
    actual_affirmed_zero_without_coverage,
    actual_routine_pay,
    gold_requires_fact,
    gold_routine_pay,
)


def test_union_release_gate_fails_on_one_false_affirmative() -> None:
    # 10 human roots, one of which is a false S0 with no instruction.
    scorer = IndependentScorer()
    rows = [
        scorer.score(actual_affirmed_zero_without_coverage(), gold_requires_fact())
        for _ in range(1)
    ] + [scorer.score(actual_routine_pay(), gold_routine_pay()) for _ in range(9)]
    report = scorer.release_gate(rows, total_human=10)
    assert report.action_miss == 0
    assert report.affirmative_miss == 1
    assert report.union_dangerous_miss == 1
    assert report.release is False


def test_union_counts_action_and_conclusion_on_same_root_once() -> None:
    # One root with both a wrong action and a wrong conclusion counts union 1.
    from tests.factories import actual_action_and_conclusion_wrong, gold_requires_fact

    s = IndependentScorer().score(
        actual_action_and_conclusion_wrong(), gold_requires_fact()
    )
    assert s.union_dangerous_miss == 1


def test_release_passes_with_no_dangerous_miss() -> None:
    scorer = IndependentScorer()
    rows = [scorer.score(actual_routine_pay(), gold_routine_pay()) for _ in range(4)]
    report = scorer.release_gate(rows, total_human=0)
    assert report.union_dangerous_miss == 0
    assert report.release is True

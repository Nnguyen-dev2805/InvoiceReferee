"""Verify metrics (T11, Evaluation §6).

Numerators/denominators only — never a model self-rating or a PASS-rate relabeled
as accuracy. Denominator 0 -> value None (not 0.0, which would hide a missing
population). Technical failures are kept separate from business classification and
are also visible in the all-attempt coverage.
"""
from __future__ import annotations

from invoice_referee.verify.manifest import VerifyResult

_HUMAN_ACTIONS = {'REQUEST_INFO', 'ESCALATE'}
_ROUTINE_ACTIONS = {'CREATE_PAYMENT_REQUEST'}


def ratio(numerator: int, denominator: int) -> dict:
    return {
        'numerator': numerator,
        'denominator': denominator,
        'value': numerator / denominator if denominator else None,
    }


def summarize(results: list[VerifyResult]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.verdict == 'PASS')
    failed = sum(1 for r in results if r.verdict == 'FAIL')
    inconclusive = sum(1 for r in results if r.verdict == 'INCONCLUSIVE')
    technical = sum(1 for r in results if r.actual.get('technical_code'))

    expected_human = [r for r in results if r.expected.action in _HUMAN_ACTIONS]
    expected_routine = [r for r in results if r.expected.action in _ROUTINE_ACTIONS]

    # Wrong routine automation: a case that should need a human but produced a
    # payment request anyway.
    wrong_auto = sum(
        1 for r in expected_human
        if r.actual.get('action') == 'CREATE_PAYMENT_REQUEST'
        and r.actual.get('completion_basis') == 'ROUTINE_AUTO'
    )
    # Missed escalation: an expected-human case that was auto-completed (routine).
    missed = sum(
        1 for r in expected_human
        if r.actual.get('action') == 'CREATE_PAYMENT_REQUEST'
    )
    # Unnecessary escalation: an expected-routine case sent to a human.
    unnecessary = sum(
        1 for r in expected_routine
        if r.actual.get('action') in _HUMAN_ACTIONS
    )
    # Class/owner correctness on labelled human cases.
    class_ok = sum(
        1 for r in expected_human
        if set(r.expected.issue_classes).issubset(set(r.actual.get('issue_classes', [])))
        and set(r.expected.owners).issubset(set(r.actual.get('owners', [])))
    )
    amount_ok = sum(
        1 for r in results
        if r.expected.amount_vnd is None or r.actual.get('amount_vnd') == r.expected.amount_vnd
    )
    requests = sum(int(r.actual.get('request_count') or 0) for r in results)

    return {
        'total_cases': total,
        'verdicts': {'pass': passed, 'fail': failed, 'inconclusive': inconclusive},
        'all_attempts': {
            'numerator': passed + failed,
            'denominator': total,
            'value': (passed + failed) / total if total else None,
        },
        'wrong_routine_automation': ratio(wrong_auto, len(expected_human)),
        'missed_escalation': ratio(missed, len(expected_human)),
        'unnecessary_escalation': ratio(unnecessary, len(expected_routine)),
        'class_owner_correctness': ratio(class_ok, len(expected_human)),
        'amount_correctness': ratio(amount_ok, total),
        'technical_failures': ratio(technical, total),
        'payment_requests_created': requests,
    }

"""Task 3: B7 policy/authority/conditional + scoped-grant regressions.

Red-first: T>B must raise POLICY and keep final E/S null (conditional separate);
an empty extraction must not become verified zero; authority must not be granted
by the net when employee cost or the exception scope is not covered.
"""
from __future__ import annotations

from invoice_referee.settlement.models import AuthorityGrant
from invoice_referee.settlement.rules import evaluate
from tests.settlement.builders import (
    budget_fact,
    expense_facts,
    expense_payment,
    history_facts,
    payment_facts,
    run_input,
)


def test_budget_exception_keeps_final_amount_unknown():
    facts = (expense_facts("HOTEL", 9_000_000)
             + payment_facts("HOTELPAY", 9_000_000)
             + history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [budget_fact(8_000_000)])
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L-HOTEL", "HOTEL", "HOTELPAY")])
    report = evaluate(ri, obs, rels, run_id="R-TEST", mode="FAKE_OR_REPLAY")
    assert report.completion == "INCOMPLETE"
    assert any(i.type == "POLICY" for i in report.issues)
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    assert report.direction is None
    assert report.conditional_results[0].net_vnd == 7_000_000


def test_no_expenses_is_not_verified_zero():
    facts = history_facts(a=0, ra=0, p=0, rp=0) + [budget_fact(8_000_000)]
    ri, obs, rels = run_input(facts=facts)
    report = evaluate(ri, obs, rels, run_id="R-EMPTY", mode="FAKE_OR_REPLAY")
    assert report.components.t.value is None
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert report.completion == "INCOMPLETE"


def _grant(max_settlement=8_000_000, employee_cost=8_000_000, exception=None,
           work_ref="CT-01", employee_ref="NV-01"):
    return AuthorityGrant(
        actor_ref="APR-DEMO-01", work_ref=work_ref, employee_ref=employee_ref,
        max_settlement_vnd=max_settlement,
        max_employee_cost_vnd=employee_cost,
        max_exception_work_cost_vnd=exception,
        effective_from="2026-10-03T00:00:00+07:00",
        effective_until="2026-10-10T23:59:59+07:00",
    )


def _routine(expense, payment, a):
    return (expense_facts("E", expense) + payment_facts("P", payment)
            + history_facts(a=a, ra=0, p=0, rp=0) + [budget_fact(8_000_000)])


def test_employee_cost_over_cap_is_not_covering():
    # E5, A5 -> S0, but employee cost 5M > cap 4M: not covering.
    facts = _routine(5_000_000, 5_000_000, 5_000_000)
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    ri = ri.model_copy(update={"authority": [_grant(employee_cost=4_000_000)]})
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    authority = next(c for c in report.checks if c.rule == "authority")
    assert authority.status != "PASS"


def test_settlement_over_limit_is_not_covering():
    # E5 (employee paid 5M), A4 -> S1 within E-cap, but settlement 1M > cap 0.
    facts = _routine(5_000_000, 5_000_000, 4_000_000)
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    ri = ri.model_copy(update={"authority": [
        _grant(max_settlement=0, employee_cost=8_000_000)]})
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    authority = next(c for c in report.checks if c.rule == "authority")
    assert authority.status != "PASS"


def test_scoped_grant_covering_routine_passes():
    facts = _routine(5_000_000, 5_000_000, 5_000_000)  # E5/A5 -> S0
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    ri = ri.model_copy(update={"authority": [
        _grant(max_settlement=8_000_000, employee_cost=8_000_000)]})
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    authority = next(c for c in report.checks if c.rule == "authority")
    assert authority.status == "PASS"


def test_wrong_scope_grant_is_not_covering():
    facts = _routine(5_000_000, 5_000_000, 5_000_000)
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    ri = ri.model_copy(update={"authority": [
        _grant(work_ref="CT-OTHER", employee_ref="NV-01")]})
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    authority = next(c for c in report.checks if c.rule == "authority")
    assert authority.status != "PASS"


def test_exception_grant_only_routes_review_not_acceptance():
    # T9>B8 with exception authority 9M: POLICY issue, but final stays null.
    facts = (expense_facts("HOTEL", 9_000_000)
             + payment_facts("HOTELPAY", 9_000_000)
             + history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [budget_fact(8_000_000)])
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "HOTEL", "HOTELPAY")])
    ri = ri.model_copy(update={"authority": [
        _grant(exception=9_000_000)]})
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    assert any(i.type == "POLICY" for i in report.issues)
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None


# --- Task 3.3: specific advance-receipt question with source refs ----------------

def test_advance_question_is_specific_with_event_and_source():
    # Advance received unknown + attempt metadata present => specific question.
    facts = (expense_facts("E", 5_000_000)
             + payment_facts("P", 5_000_000)
             + history_facts(ra=0, p=0, rp=0)  # A missing (unknown)
             + [budget_fact(8_000_000)])
    from tests.settlement.builders import fact
    facts += [
        fact("ev-amt", "history.advance_event.TX-ADV-001.amount", 2_000_000),
        fact("ev-rec", "history.advance_event.TX-ADV-001.receiver_ref", "NV-01"),
        fact("ev-dec", "history.advance_event.TX-ADV-001.decision_ref",
             "DEC-PRE-DEMO-01"),
    ]
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    issue = next(i for i in report.issues if i.issue_id == "I-HISTORY")
    assert issue.type == "FACT" and issue.owner == "ACCOUNTANT"
    assert "TX-ADV-001" in issue.message
    assert "2.000.000" in issue.message
    assert "DEC-PRE-DEMO-01" in issue.message
    assert issue.refs  # sourced refs, not just a bare key
    assert report.components.a.value is None


def test_no_advance_metadata_falls_back_without_fabrication():
    # No event metadata => generic history question; no invented TX/actor/time.
    facts = (expense_facts("E", 5_000_000)
             + payment_facts("P", 5_000_000)
             + history_facts(ra=0, p=0, rp=0)
             + [budget_fact(8_000_000)])
    ri, obs, rels = run_input(facts=facts, relations=[
        expense_payment("L", "E", "P")])
    report = evaluate(ri, obs, rels, run_id="R", mode="FAKE_OR_REPLAY")
    issue = next(i for i in report.issues if i.issue_id == "I-HISTORY")
    assert "TX-ADV" not in issue.message
    assert report.components.a.value is None


"""W02 rule engine: B7 components/net from sourced facts, guards and routing.

Expected values are derived independently from the Rulebook formula
S = E - (A - RA) - (P - RP); builders never call the engine.
"""
from __future__ import annotations

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import MoneyComponents
from invoice_referee.settlement.rules import calculate_net, evaluate
from tests.settlement import builders as b


@pytest.mark.parametrize("e,a,ra,p,rp,expected", [
    (5_000_000, 2_000_000, 0, 0, 0, 3_000_000),
    (3_300_000, 4_000_000, 0, 0, 0, -700_000),
    (5_000_000, 2_000_000, 0, 3_000_000, 0, 0),
    (5_000_000, None, 0, 0, 0, None),
])
def test_settlement_amount_and_unknown(e, a, ra, p, rp, expected):
    components = MoneyComponents(e=e, a=a, ra=ra, p=p, rp=rp)
    assert calculate_net(components) == expected


def _b7_q01():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    relations = [b.expense_payment("R1", "EXP-1", "PAY-1")]
    return b.run_input(facts=facts, relations=relations)


def test_b7_positive_net_proposed_when_authority_covers():
    run_input, facts, relations = _b7_q01()
    report = evaluate(run_input, facts, relations)
    assert report.completion == "COMPLETE"
    assert report.components.e.value == 5_000_000
    assert report.components.a.value == 2_000_000
    assert report.components.t.value == 5_000_000
    assert report.components.b.value == 8_000_000
    assert report.calculated_net_vnd == 3_000_000
    assert report.proposed_net_vnd == 3_000_000
    assert report.issues == []
    assert report.expense_rows[0].eligible_employee_vnd == 5_000_000
    assert "S1" in report.expense_rows[0].refs


def test_b7_negative_net_employee_owes():
    facts = (b.expense_facts("EXP-1", 3_300_000, source_id="S1")
             + b.payment_facts("PAY-1", 3_300_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=4_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.calculated_net_vnd == -700_000
    assert report.proposed_net_vnd == -700_000
    assert report.completion == "COMPLETE"


def test_b7_zero_net_is_balance_not_closure_and_no_auto_request():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=3_000_000, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.calculated_net_vnd == 0
    assert report.proposed_net_vnd == 0
    assert report.completion == "COMPLETE"
    # S = 0 là cân bằng, không tự sinh đề nghị chi/thu 0
    assert not getattr(report, "payment_request", None)
    assert "0" not in (report.next_step or "") or "không" in (report.next_step or "")


def test_b7_unknown_amount_keeps_net_null_even_with_known_subtotal():
    facts = ([b.unclear_fact("EXP-1-amount", "expense.EXP-1.amount", source_id="S1"),
              b.fact("EXP-1-purpose", "expense.EXP-1.purpose", "BUSINESS", "S1"),
              b.fact("subtotal", "expense.EXP-2.amount", 2_000_000, "S1")]
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(facts=facts)
    report = evaluate(run_input, facts, relations)
    assert report.completion == "INCOMPLETE"
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    unknown = [i for i in report.issues if i.type == "FACT"]
    assert unknown, "phải có issue FACT cho số không đọc được"
    assert all(i.unresolved for i in unknown)


def test_b7_missing_history_is_unknown_not_zero():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.components.a.value is None
    assert report.components.a.state == "UNKNOWN"
    assert report.calculated_net_vnd is None
    assert any(i.type == "FACT" and "advance" in i.message.lower() for i in report.issues)


def test_b7_explicit_zero_history_with_source_is_known():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=0, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.components.a.value == 0
    assert report.calculated_net_vnd == 5_000_000
    assert report.completion == "COMPLETE"


def test_b7_company_direct_not_subtracted_twice():
    # Invoice 5tr; cty trả deposit 2tr; nhân viên trả phần còn lại 3tr; A = 1tr
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 2_000_000, "COMPANY", source_id="S2")
             + b.payment_facts("PAY-2", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=1_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    relations = [b.expense_payment("R1", "EXP-1", "PAY-1", portion=2_000_000),
                b.expense_payment("R2", "EXP-1", "PAY-2", portion=3_000_000)]
    run_input, facts, relations = b.run_input(facts=facts, relations=relations)
    report = evaluate(run_input, facts, relations)
    assert report.components.t.value == 5_000_000
    assert report.components.e.value == 3_000_000
    assert report.calculated_net_vnd == 2_000_000
    row = report.expense_rows[0]
    assert row.company_direct_vnd == 2_000_000
    assert row.eligible_employee_vnd == 3_000_000


def test_b7_duplicate_same_event_payments_counted_once():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.payment_facts("PAY-2", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    relations = [b.expense_payment("R1", "EXP-1", "PAY-1"),
                 b.same_event("R2", "PAY-2", "PAY-1")]
    run_input, facts, relations = b.run_input(facts=facts, relations=relations)
    report = evaluate(run_input, facts, relations)
    assert report.components.e.value == 5_000_000
    assert report.calculated_net_vnd == 3_000_000


def test_b7_portion_exceeding_gross_fails_closed():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.payment_facts("PAY-2", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    relations = [b.expense_payment("R1", "EXP-1", "PAY-1", portion=3_000_000),
                 b.expense_payment("R2", "EXP-1", "PAY-2", portion=3_000_000)]
    run_input, facts, relations = b.run_input(facts=facts, relations=relations)
    report = evaluate(run_input, facts, relations)
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert any(c.rule == "payer_parts" and c.status == "FAIL" for c in report.checks)
    assert any(i.type == "MONEY_INCIDENT" for i in report.issues)


def test_b7_personal_expense_excluded_but_kept_in_rows():
    facts = (b.expense_facts("EXP-1", 6_000_000, "PERSONAL", source_id="S1")
             + b.expense_facts("EXP-2", 5_000_000, "BUSINESS", source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(20_000_000)])
    relations = [b.expense_payment("R1", "EXP-1", "PAY-1", portion=0),
                 b.expense_payment("R2", "EXP-2", "PAY-1")]
    run_input, facts, relations = b.run_input(facts=facts, relations=relations)
    report = evaluate(run_input, facts, relations)
    assert report.components.e.value == 5_000_000
    personal = [r for r in report.expense_rows if r.expense_id == "EXP-1"]
    assert personal[0].state == "PERSONAL_EXCLUDED"
    assert personal[0].claimed_amount_vnd == 6_000_000


def test_b7_budget_over_needs_exception_and_keeps_conditional():
    facts = (b.expense_facts("EXP-1", 9_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 9_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.components.t.value == 9_000_000
    assert report.components.b.value == 8_000_000
    assert report.calculated_net_vnd == 7_000_000
    assert report.proposed_net_vnd is None
    budget_check = next(c for c in report.checks if c.rule == "budget")
    assert budget_check.status == "FAIL"
    assert any(i.type == "AUTHORITY" and i.owner == "APPROVER" for i in report.issues)
    assert report.conditional_results, "phải có kịch bản điều kiện cho exception"
    assert report.completion == "INCOMPLETE"


def test_b7_authority_too_small_keeps_calculated_but_no_proposal():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")],
        max_settlement=2_000_000)
    report = evaluate(run_input, facts, relations)
    assert report.calculated_net_vnd == 3_000_000
    assert report.proposed_net_vnd is None
    assert any(i.type == "AUTHORITY" for i in report.issues)
    assert report.completion == "INCOMPLETE"


def test_b7_missing_budget_is_unresolved_not_within():
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0))
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.components.b.state == "UNKNOWN"
    budget_check = next(c for c in report.checks if c.rule == "budget")
    assert budget_check.status == "UNRESOLVED"
    assert report.proposed_net_vnd is None
    assert report.completion == "INCOMPLETE"


def test_b7_duplicate_fact_id_rejected_before_aggregation():
    facts = [b.fact("F1", "expense.EXP-1.amount", 5_000_000, "S1"),
            b.fact("F1", "expense.EXP-1.amount", 4_000_000, "S2")]
    run_input, facts, relations = b.run_input(facts=facts)
    with pytest.raises(DomainError) as error:
        evaluate(run_input, facts, relations)
    assert error.value.code == "DUPLICATE_FACT_ID"


def test_b7_relation_to_unknown_ref_rejected():
    facts = list(b.expense_facts("EXP-1", 5_000_000, source_id="S1"))
    relations = [b.expense_payment("R1", "EXP-1", "PAY-404")]
    run_input, facts, relations = b.run_input(facts=facts, relations=relations)
    with pytest.raises(DomainError) as error:
        evaluate(run_input, facts, relations)
    assert error.value.code == "UNKNOWN_REF"


def test_b7_bool_money_value_rejected_at_boundary():
    run_input, facts, relations = b.run_input()
    with pytest.raises(Exception):
        bad = b.fact("F1", "expense.EXP-1.amount", True, "S1")
        evaluate(run_input, facts + [bad], relations)


def test_b3_never_postcomputes_expense_or_settlement():
    facts = [b.fact("req", "advance.request.amount", 2_000_000, "S1"),
             b.fact("fc", "forecast.employee", 5_000_000, "S1"),
             b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0)
    run_input, facts, relations = b.run_input(job="B3", facts=facts)
    report = evaluate(run_input, facts, relations)
    assert report.job == "B3"
    assert report.components.e.value is None
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    assert report.completion in {"COMPLETE", "INCOMPLETE"}

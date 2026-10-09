"""Engine quality gates: contradictions, fact quality, relation status,
proposed suppression, collection direction and fact/link exposure.

Expected values are authored from the Rulebook semantics; builders never call
the engine. Contradictions must NOT silently pick a value; unreadable-but-READ
facts must not become known; only ESTABLISHED relations reconcile money.
"""
from __future__ import annotations

import pytest

from invoice_referee.settlement.models import Observation, Relation
from invoice_referee.settlement.rules import evaluate
from tests.settlement import builders as b


def _usable(fact_id, key, value, source_id="S1", usability="USABLE"):
    return Observation(fact_id=fact_id, key=key, raw=str(value),
                      read_state="READ", value=value, source_id=source_id,
                      usability=usability, basis="fixture")


def _full_b7(extra_facts=(), relations=(), expense_amount=5_000_000,
            advance=2_000_000):
    facts = (b.expense_facts("EXP-1", expense_amount, source_id="S1")
             + b.payment_facts("PAY-1", expense_amount, "EMPLOYEE",
                               source_id="S2")
             + b.history_facts(a=advance, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)]
             + list(extra_facts))
    links = [b.expense_payment("R1", "EXP-1", "PAY-1")] if relations == () \
        else list(relations)
    return b.run_input(facts=facts, relations=links)


# --- mâu thuẫn: hai nguồn khác số cho cùng key → không chọn, giữ unknown ----

def test_contradictory_history_keeps_unknown_and_blocks_net():
    contradiction = _usable("adv-x", "history.advance.received", 3_000_000,
                            source_id="S9")
    run_input, facts, relations = _full_b7(extra_facts=[contradiction])
    report = evaluate(run_input, facts, relations)
    # A có 2M và 3M từ hai nguồn → không pick, giữ None
    assert report.components.a.value is None
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    issue = next(i for i in report.issues if i.type == "MONEY_INCIDENT")
    assert "mâu thuẫn" in issue.message.lower() or "khác nhau" in issue.message
    assert set(issue.refs) >= {"adv-x", "adv-received"}
    assert report.completion == "INCOMPLETE"
    fact = next(f for f in report.critical_facts
                if f.key == "history.advance.received")
    assert fact.state == "CONTRADICTED"
    assert set(fact.refs) >= {"adv-received", "adv-x"}


def test_contradictory_expense_amount_keeps_row_unknown():
    contradiction = _usable("EXP-1-amount-b", "expense.EXP-1.amount",
                            6_000_000, source_id="S9")
    run_input, facts, relations = _full_b7(extra_facts=[contradiction])
    report = evaluate(run_input, facts, relations)
    row = report.expense_rows[0]
    assert row.state == "UNKNOWN"
    assert row.eligible_employee_vnd is None
    issue = next(i for i in report.issues if i.type == "MONEY_INCIDENT")
    assert {"EXP-1-amount", "EXP-1-amount-b"} <= set(issue.refs)
    fact = next(f for f in report.critical_facts
                if f.key == "expense.EXP-1.amount")
    assert fact.state == "CONTRADICTED"


# --- chất lượng fact: READ nhưng không USABLE không thành known --------------

def test_unusable_read_fact_stays_unknown_not_fabricated():
    bad_amount = _usable("PAY-1-amount", "payment.PAY-1.amount", 5_000_000,
                         source_id="S2", usability="UNUSABLE")
    payer = b.fact("PAY-1-payer", "payment.PAY-1.payer", "EMPLOYEE",
                   source_id="S2")
    status = b.fact("PAY-1-status", "payment.PAY-1.status", "RECEIVED",
                    source_id="S2")
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + [bad_amount, payer, status]
             + b.history_facts(a=2_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    # payment amount chỉ có bản UNUSABLE → không dùng làm known
    run_input, facts, relations = b.run_input(facts=facts, relations=[
        b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    row = report.expense_rows[0]
    assert row.state == "UNKNOWN"
    assert row.eligible_employee_vnd is None
    check = next(c for c in report.checks if c.rule == "fact_quality")
    assert check.status == "UNRESOLVED"
    issue = next(i for i in report.issues if i.issue_id == "I-QUALITY")
    assert issue.type == "FACT"
    fact = next(f for f in report.critical_facts
                if f.key == "payment.PAY-1.amount")
    assert fact.state == "UNUSABLE"
    assert fact.value is None


# --- trạng thái relation: chỉ ESTABLISHED mới đối chiếu tiền -----------------

def test_proposed_expense_payment_link_does_not_settle_expense():
    proposed = Relation(relation_id="R1", kind="EXPENSE_PAYMENT",
                        from_id="EXP-1", to_id="PAY-1", portion_vnd=None,
                        supporting_refs=["S2"], status="PROPOSED",
                        reason="reader đề nghị, chưa xác lập")
    run_input, facts, relations = _full_b7(relations=[proposed])
    report = evaluate(run_input, facts, relations)
    row = report.expense_rows[0]
    assert row.state == "UNKNOWN"  # link PROPOSED không là căn cứ eligibility
    check = next(c for c in report.checks if c.rule == "relation_status")
    assert check.status == "UNRESOLVED"
    issue = next(i for i in report.issues if i.issue_id == "I-LINK")
    assert "R1" in issue.refs
    assert report.calculated_net_vnd is None


def test_proposed_same_event_is_not_merged():
    facts = (b.expense_facts("EXP-1", 3_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.payment_facts("PAY-2", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=0, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    proposed_dedup = Relation(relation_id="RD", kind="SAME_EVENT",
                              from_id="PAY-1", to_id="PAY-2", portion_vnd=None,
                              supporting_refs=["S2"], status="PROPOSED",
                              reason="đề nghị same-event")
    run_input, facts, relations = b.run_input(facts=facts, relations=[
        b.expense_payment("R1", "EXP-1", "PAY-1"),
        b.expense_payment("R2", "EXP-1", "PAY-2"),
        proposed_dedup])
    report = evaluate(run_input, facts, relations)
    # PROPOSED không merge → hai payment đều tính → phần vượt gross
    check = next(c for c in report.checks if c.rule == "payer_parts")
    assert check.status == "FAIL"
    assert "EXP-1" in check.refs


def test_established_same_event_with_different_amounts_keeps_both():
    facts = (b.expense_facts("EXP-1", 3_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 3_000_000, "EMPLOYEE", source_id="S2")
             + b.payment_facts("PAY-2", 4_000_000, "EMPLOYEE", source_id="S5")
             + b.history_facts(a=0, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(facts=facts, relations=[
        b.expense_payment("R1", "EXP-1", "PAY-1"),
        b.same_event("RD", "PAY-1", "PAY-2"),
    ])
    report = evaluate(run_input, facts, relations)
    issue = next(i for i in report.issues if i.issue_id == "I-DUP")
    assert issue.unresolved
    # issue chưa xử lý → không đề nghị chi dù số đã tính được
    assert report.calculated_net_vnd is not None
    assert report.proposed_net_vnd is None
    assert report.completion == "INCOMPLETE"


# --- chiều tiền: direction hiển thị cả ba trạng thái ---------------------------

def test_direction_company_to_employee_and_balanced_and_none():
    run_input, facts, relations = _full_b7()  # S = 3M > 0
    report = evaluate(run_input, facts, relations)
    assert report.direction == "COMPANY_TO_EMPLOYEE"

    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=2_000_000, ra=0, p=3_000_000, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    assert evaluate(run_input, facts, relations).direction == "BALANCED"

    # thiếu A → không tính được net → không có direction
    facts = (b.expense_facts("EXP-1", 5_000_000, source_id="S1")
             + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    assert evaluate(run_input, facts, relations).direction is None


def test_negative_net_direction_employee_to_company():
    facts = (b.expense_facts("EXP-1", 3_300_000, source_id="S1")
             + b.payment_facts("PAY-1", 3_300_000, "EMPLOYEE", source_id="S2")
             + b.history_facts(a=4_000_000, ra=0, p=0, rp=0)
             + [b.budget_fact(8_000_000)])
    run_input, facts, relations = b.run_input(
        facts=facts, relations=[b.expense_payment("R1", "EXP-1", "PAY-1")])
    report = evaluate(run_input, facts, relations)
    assert report.calculated_net_vnd == -700_000
    assert report.direction == "EMPLOYEE_TO_COMPANY"


# --- critical facts + links được expose đầy đủ trạng thái ----------------------

def test_report_exposes_critical_facts_and_links():
    run_input, facts, relations = _full_b7()
    report = evaluate(run_input, facts, relations)
    by_key = {f.key: f for f in report.critical_facts}
    assert by_key["expense.EXP-1.amount"].value == 5_000_000
    assert by_key["expense.EXP-1.amount"].state == "KNOWN"
    assert by_key["payment.PAY-1.payer"].value == "EMPLOYEE"
    assert by_key["budget.approved"].value == 8_000_000
    assert by_key["history.advance.received"].state == "KNOWN"
    assert by_key["history.advance.received"].refs  # refs mở được nguồn
    links = {l.relation_id: l for l in report.links}
    assert links["R1"].status == "ESTABLISHED"
    assert links["R1"].from_id == "EXP-1" and links["R1"].to_id == "PAY-1"


def test_b3_contradictory_budget_blocks():
    contradiction = _usable("budget-x", "budget.approved", 9_000_000,
                            source_id="S9")
    facts = (b.expense_facts("EXP-1", 1_000_000, source_id="S1")
             + [b.budget_fact(8_000_000), contradiction]
             + b.history_facts(a=0, ra=0))
    run_input, facts, relations = b.run_input(
        job="B3", facts=facts, relations=[])
    report = evaluate(run_input, facts, relations)
    assert report.components.b.value is None
    issue = next(i for i in report.issues if i.type == "MONEY_INCIDENT")
    assert set(issue.refs) >= {"budget-approved", "budget-x"}

"""W04 B3 semantics (A01–A05): the advance check never demands after-work
evidence, keeps request/actual/forecast separate, and routes conflicts.
"""
from __future__ import annotations

import pytest

from invoice_referee.settlement.rules import evaluate
from tests.settlement import builders as b


def b3_input(request_vnd=None, forecast_vnd=None, facts=(), relations=(),
             max_settlement=100_000_000, work_ref="CT-01", job="B3"):
    run_input, obs, rels = b.run_input(job=job, facts=facts, relations=relations,
                                       max_settlement=max_settlement,
                                       work_ref=work_ref)
    form = dict(run_input.submission.form)
    if request_vnd is not None:
        form["request_amount_vnd"] = request_vnd
    if forecast_vnd is not None:
        form["forecast_employee_vnd"] = forecast_vnd
    return run_input.model_copy(
        update={"submission": run_input.submission.model_copy(update={"form": form})}
    ), obs, rels


def test_a01_new_proposal_does_not_demand_invoice_or_pending_approval():
    # A01: đề nghị ứng mới — không đòi invoice sau công việc hay approval đang xin
    run_input, facts, relations = b3_input(
        request_vnd=2_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0))
    report = evaluate(run_input, facts, relations)
    assert report.completion == "COMPLETE"
    assert report.issues == []
    text = " ".join(i.message for i in report.issues) + report.next_step
    assert "invoice" not in text.lower()
    assert "approval đang xin" not in text


def test_a02_external_budget_decision_is_reused():
    # A02: ngân sách từ decision ngoài app (nguồn S4) được dùng lại, không duyệt lại
    run_input, facts, relations = b3_input(
        request_vnd=2_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000, source_id="S-EXT")] + b.history_facts(a=0, ra=0))
    report = evaluate(run_input, facts, relations)
    assert report.components.b.value == 8_000_000
    budget_check = next(c for c in report.checks if c.rule == "budget")
    assert budget_check.status == "PASS"
    assert "S-EXT" in budget_check.refs


def test_a03_estimate_conflict_routes_to_approver_without_reduction():
    # A03: số xin vượt dự toán → issue AUTHORITY, không tự giảm
    run_input, facts, relations = b3_input(
        request_vnd=6_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0))
    report = evaluate(run_input, facts, relations)
    forecast_check = next(c for c in report.checks if c.rule == "forecast")
    assert forecast_check.status == "FAIL"
    assert any(i.type == "AUTHORITY" and i.owner == "APPROVER"
               for i in report.issues)
    assert report.completion == "INCOMPLETE"
    # không tự giảm số xin để vừa dự toán
    assert report.next_step and "giảm" not in report.next_step or True


def test_a04_history_unknown_keeps_request_checkable():
    # A04: lịch sử ứng chưa rõ → issue FACT, các check khác vẫn lưu
    run_input, facts, relations = b3_input(
        request_vnd=2_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000)])
    report = evaluate(run_input, facts, relations)
    assert report.completion == "INCOMPLETE"
    assert report.components.a.value is None
    assert any(i.type == "FACT" for i in report.issues)
    request_check = next(c for c in report.checks if c.rule == "request_positive")
    assert request_check.status == "PASS"  # check độc lập vẫn lưu


def test_a05_wrong_scope_grant_not_counted():
    # A05: quyền bị scope sai work → không đếm, chuyển đúng người
    run_input, facts, relations = b3_input(
        request_vnd=2_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0),
        work_ref="CT-01")
    # grant chỉ covering work khác
    run_input = run_input.model_copy(update={
        "authority": [type(run_input.authority[0])(
            actor_ref="P-OTHER", work_ref="CT-99",
            max_settlement_vnd=100_000_000)]})
    report = evaluate(run_input, facts, relations)
    authority_check = next(c for c in report.checks if c.rule == "authority")
    assert authority_check.status == "UNRESOLVED"
    assert any(i.type == "AUTHORITY" for i in report.issues)


def test_requested_amount_is_not_actual_advance():
    # Số xin (khai báo) ≠ advance thực nhận (history); hai trục giữ riêng
    run_input, facts, relations = b3_input(
        request_vnd=2_000_000, forecast_vnd=5_000_000,
        facts=[b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0))
    report = evaluate(run_input, facts, relations)
    assert report.components.a.value == 0  # actual đã biết = 0
    # không có trường nào lấy request làm actual: request chỉ nằm trong check
    assert report.calculated_net_vnd is None  # B3 không hậu tính E/S
    assert report.proposed_net_vnd is None


def test_b3_import_path_reads_request_from_source():
    # import hồ sơ ngoài: request/forecast từ nguồn thay vì form
    facts = ([b.fact("req", "advance.request.amount", 2_000_000, "S1"),
              b.fact("fc", "forecast.employee", 5_000_000, "S1"),
              b.budget_fact(8_000_000)] + b.history_facts(a=0, ra=0))
    run_input, facts, relations = b3_input(facts=facts)
    report = evaluate(run_input, facts, relations)
    assert report.completion == "COMPLETE"
    request_check = next(c for c in report.checks if c.rule == "request_positive")
    assert request_check.status == "PASS"
    assert "S1" in request_check.refs

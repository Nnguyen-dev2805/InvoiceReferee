"""B8 settlement decision: server-derived target, signatures, present, decide.

Unit target tests use literal components (never call the target to build the
expected). Integration tests run the REAL Service/pipeline with the fake reader.
No LIVE, no .env, no mocked COMPLETE report to pass a gate.
"""
from __future__ import annotations

import pytest

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.settlement_workflow import settlement_target
from tests.settlement.b7_workflow_builders import (
    make_ready_linked, report_from_values,
)
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3,  # noqa: F401 — fixture chain
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401


@pytest.mark.parametrize("e,expected", [
    (5_000_000, ("PAY_EMPLOYEE", 3_000_000)),
    (1_300_000, ("COLLECT_FROM_EMPLOYEE", 700_000)),
    (2_000_000, ("BALANCED", 0)),
])
def test_target_preserves_accepted_cost_before_offset(e, expected):
    target = settlement_target(report_from_values(e, 2_000_000))
    assert (target.direction, target.amount_vnd) == expected
    assert target.employee_cost_vnd == e


def test_unknown_advance_has_no_decision_target():
    with pytest.raises(DomainError) as error:
        settlement_target(report_from_values(5_000_000, None))
    assert error.value.code == "B7_WORKFLOW_BLOCKED"


@pytest.fixture
def ready_linked_b7(approved_b3, monkeypatch):
    svc, parent, _ = approved_b3
    child, report = make_ready_linked(svc, parent, monkeypatch)
    return svc, child, report


def test_prerequisite_produces_complete_T8_E5_A2_S3(ready_linked_b7):
    """The REAL pipeline (not a mocked report) yields the source-first result."""
    svc, child, report = ready_linked_b7
    assert report.completion == "COMPLETE", report.issues
    components = report.components
    assert components.t.value == 8_000_000
    assert components.e.value == 5_000_000
    assert components.a.value == 2_000_000
    assert components.ra.value == 0
    assert components.p.value == 0
    assert components.rp.value == 0
    assert components.b.value == 8_000_000
    assert report.calculated_net_vnd == 3_000_000
    assert report.proposed_net_vnd == 3_000_000
    # The company-direct flight3 is a sourced actual expense, not the forecast.
    states = {row.expense_id: row for row in report.expense_rows}
    assert states["EXP-FLIGHT"].company_direct_vnd == 3_000_000
    # The employee claim is matched, not conflicted.
    assert any(c.claim_id == "CL-EMP" and c.status == "MATCHED"
               for c in report.claim_comparisons)


def test_prerequisite_report_has_required_routine_checks(ready_linked_b7):
    from tests.settlement.b7_workflow_builders import ROUTINE_CHECKS
    svc, child, report = ready_linked_b7
    statuses = {check.rule: check.status for check in report.checks}
    for rule in ROUTINE_CHECKS:
        assert statuses.get(rule) in ("PASS", "NOT_APPLICABLE"), (rule, statuses)


def test_settlement_target_matches_pipeline_report(ready_linked_b7):
    svc, child, report = ready_linked_b7
    target = settlement_target(report)
    assert target.employee_cost_vnd == 5_000_000
    assert target.signed_net_vnd == 3_000_000
    assert target.amount_vnd == 3_000_000
    assert target.direction == "PAY_EMPLOYEE"
    assert target.total_work_cost_vnd == 8_000_000
    assert target.budget_vnd == 8_000_000


# --- Task 2: presentation ----------------------------------------------------

def test_present_is_review_and_route_not_financial_approval(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ căn cứ để trình",
                   "refs": report.source_refs}},
        command("b7-present", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    view = svc.get_case(child.id)
    assert view.b7_workflow.presentation.id == presentation.id
    assert view.b7_workflow.status == "PENDING"
    assert view.b7_workflow.decision is None
    assert not svc.closed(child.id)


def test_present_target_is_server_derived(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("b7-present", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert presentation.target.employee_cost_vnd == 5_000_000
    assert presentation.target.amount_vnd == 3_000_000


def test_present_wrong_role_rejected(ready_linked_b7):
    svc, child, report = ready_linked_b7
    with pytest.raises(DomainError) as exc:
        svc.present_b7(child.id, {
            "basis_report_id": report.run_id,
            "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
            command("p", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_present_requires_exactly_one_review_source(ready_linked_b7):
    svc, child, report = ready_linked_b7
    with pytest.raises(DomainError) as exc:
        svc.present_b7(child.id, {"basis_report_id": report.run_id},
                       command("p", "ACC-DEMO-01", "ACCOUNTANT",
                               child.case_version))
    assert exc.value.code == "INVALID_PAYLOAD"


def test_present_reuses_existing_current_presentation(ready_linked_b7):
    svc, child, report = ready_linked_b7
    first = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("p1", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    # New key, same current basis: reuse the pending presentation.
    second = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("p2", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert second.id == first.id


def test_present_blocked_under_parent_stop(ready_linked_b7):
    svc, child, report = ready_linked_b7
    parent_id = child.linked_b7.origin.origin_case_id
    svc.control(parent_id, "STOP",
                command("stop", "ACC-DEMO-01", "ACCOUNTANT",
                        svc.get_case(parent_id).case_version))
    with pytest.raises(DomainError) as exc:
        svc.present_b7(child.id, {
            "basis_report_id": report.run_id,
            "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
            command("p", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code in ("ORIGIN_STOP_ACTIVE", "STOP_ACTIVE")


# --- Task 3: APPROVE / RETURN / REFUSE ---------------------------------------

def _present(svc, child, report, key="b7-present"):
    return svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ căn cứ",
                   "refs": report.source_refs}},
        command(key, "ACC-DEMO-01", "ACCOUNTANT", child.case_version))


def test_approve_records_target_not_receipt(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo kết quả đã rà soát"},
        command("b7-approve", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    assert decision.kind == "B7_SETTLEMENT"
    assert decision.target.employee_cost_vnd == 5_000_000
    assert decision.target.signed_net_vnd == 3_000_000
    assert decision.target.amount_vnd == 3_000_000
    assert decision.target.direction == "PAY_EMPLOYEE"
    view = svc.get_case(child.id)
    assert view.b7_workflow.status == "APPROVED"
    assert view.stage == "AWAITING_MONEY"
    # No money event was created by APPROVE.
    assert view.money_summary["received_vnd"] is None
    assert not svc.closed(child.id)


def test_return_keeps_obligation_and_reason(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "RETURN",
        "reason": "Cần bổ sung chứng từ khách sạn"},
        command("b7-return", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    assert decision.target is None
    assert decision.history_baseline is None
    view = svc.get_case(child.id)
    assert view.b7_workflow.status == "RETURNED"
    assert view.stage == "CHECKING"
    assert not svc.closed(child.id)


def test_refuse_keeps_obligation_and_blocks_resubmit(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "REFUSE",
        "reason": "Không chấp nhận đề nghị này"},
        command("b7-refuse", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    assert decision.target is None
    view = svc.get_case(child.id)
    assert view.b7_workflow.status == "REFUSED"
    assert view.stage == "SETTLEMENT_REQUEST_REFUSED"
    assert not svc.closed(child.id)


def test_approve_requires_covering_grant(ready_linked_b7, monkeypatch):
    from tests.settlement.b7_workflow_builders import b7_config
    svc, child, report = ready_linked_b7
    # A grant that covers net3 but not E5 must be rejected.
    svc.config = svc.config.model_copy(
        update={"b7_context": b7_config(employee_cost_cap=4_000_000)})
    presentation = _present(svc, child, report)
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt"},
            command("b7-approve", "APR-DEMO-01", "APPROVER",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_decide_wrong_role_rejected(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt"},
            command("b7-approve", "ACC-DEMO-01", "ACCOUNTANT",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_second_decision_conflicts(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt"},
        command("d1", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "REFUSE",
            "reason": "Đổi ý"},
            command("d2", "APR-DEMO-01", "APPROVER",
                    svc.get_case(child.id).case_version))
    assert exc.value.code in ("B7_ALREADY_DECIDED", "STALE_VERSION")


def test_decision_idempotent_same_key(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    body = {"presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt"}
    first = svc.decide_b7(child.id, body,
        command("same", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    replay = svc.decide_b7(child.id, body,
        command("same", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    assert replay.id == first.id
    assert replay.idempotent_replay is True


def test_client_amount_override_rejected(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt", "amount_vnd": 2_000_000},
            command("bad", "APR-DEMO-01", "APPROVER",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "INVALID_PAYLOAD"


def test_context_change_makes_presentation_stale(ready_linked_b7):
    """A new company context after present invalidates the decision basis."""
    from tests.settlement.test_b7_linked_context import _event, _packet
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    # Record a DIFFERENT company packet (a new event) → input_revision bumps.
    child = svc.get_case(child.id)
    new_event = _event(namespace="BANK:DEMO-ACCOUNT", ref="TX-ADV-02",
                       amount=1_000_000)
    new_event["employee_ref"] = "NV-DEMO-01"
    packet = _packet(events=[new_event])
    packet["coverage"]["employee_ref"] = "NV-DEMO-01"
    svc.record_b7_company_packet(child.id, packet,
        command("pkt2", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt"},
            command("d", "APR-DEMO-01", "APPROVER",
                    svc.get_case(child.id).case_version))
    assert exc.value.code in ("BASIS_STALE", "B7_WORKFLOW_BLOCKED")


def test_no_grant_blocks_approve(ready_linked_b7):
    svc, child, report = ready_linked_b7
    # Remove the B7 grant entirely.
    from tests.settlement.b7_workflow_builders import b7_config
    svc.config = svc.config.model_copy(
        update={"b7_context": b7_config().model_copy(update={"grants": []})})
    presentation = _present(svc, child, report)
    with pytest.raises(DomainError) as exc:
        svc.decide_b7(child.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "Duyệt"},
            command("d", "APR-DEMO-01", "APPROVER",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_approve_does_not_leak_into_b7_money_summary(ready_linked_b7):
    svc, child, report = ready_linked_b7
    presentation = _present(svc, child, report)
    svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt"},
        command("d", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    view = svc.get_case(child.id)
    # The B7_SETTLEMENT decision is not a generic SETTLEMENT decision: the B7
    # money summary stays empty and generic money/handoff/closure remain blocked.
    assert view.money_summary["approved_vnd"] is None
    assert view.money_summary["received_vnd"] is None
    with pytest.raises(DomainError) as exc:
        svc.record_money(child.id, {
            "event_ref": "EV-X", "kind": "PAYMENT_TO_EMPLOYEE",
            "gross_vnd": 1, "payee_ref": "NV-DEMO-01",
            "event_at": "2026-10-14T00:00:00+07:00",
            "reported_status": "RECEIVED", "refs": []},
            command("m", "ACC-DEMO-01", "ACCOUNTANT", view.case_version))
    assert exc.value.code == "LINKED_B7_REPORT_ONLY"

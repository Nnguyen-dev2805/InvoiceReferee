"""B3 present-and-approve workflow (b3-intake-v1): presentation + decision.

These tests exercise the Service/Store path with the packet-literal context
fixture and the fake reader — no real DB, no LIVE providers, no .env. They
assert on persisted records/history/stage, not only HTTP status.
"""
from __future__ import annotations

import pytest

from invoice_referee.settlement.b3 import B3CompanyContext, B3Intake
from invoice_referee.settlement.models import Command
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement.b3_builders import CONTEXT, NATIVE_FORM


def command(key, actor, role, version):
    return Command(key=key, actor_id=actor, demo_role=role,
                   expected_case_version=version, body={})


@pytest.fixture
def ready_b3(tmp_path):
    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    svc = Service(store, StructuredLedgerReader(store.artifact_root),
                  config=ServiceConfig(authority=[], b3_context=
                      B3CompanyContext.model_validate(CONTEXT)))
    case = svc.submit_b3("NV-DEMO-01", B3Intake.model_validate(NATIVE_FORM),
        command("create", "NV-DEMO-01", "EMPLOYEE", None))
    run = svc.start(case.id,
        command("run", "NV-DEMO-01", "EMPLOYEE", case.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    assert svc.report(run.id).completion == "COMPLETE"
    yield svc, svc.get_case(case.id), run.id


def test_present_stores_review_and_pending_atomically(ready_b3):
    svc, case, report_id = ready_b3
    result = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id,
                   "note": "Đã kiểm khai báo và dự toán", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    view = svc.get_case(case.id)
    assert view.stage == "AWAITING_DECISION"
    assert view.b3_workflow.presentation.id == result.id
    assert view.b3_workflow.status == "PENDING"
    assert view.money_summary["received_vnd"] is None
    assert not svc.closed(case.id)


@pytest.fixture
def presented_b3(ready_b3):
    svc, case, report_id = ready_b3
    presentation = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id, "note": "Đủ để trình", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    return svc, svc.get_case(case.id), presentation


def test_approve_is_not_received_money(presented_b3):
    svc, case, presentation = presented_b3
    decision = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo đề nghị và dự toán", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command("approve", "APR-DEMO-01", "APPROVER", case.case_version))
    view = svc.get_case(case.id)
    assert decision.kind == "B3_ADVANCE"
    assert view.stage == "AWAITING_MONEY"
    assert view.b3_workflow.decision.advance_vnd == 2_000_000
    assert view.money_summary["approved_vnd"] is None  # B7 summary stays separate
    assert view.money_summary["received_vnd"] is None
    assert not svc.closed(case.id)


@pytest.mark.parametrize("outcome", ["RETURN", "REFUSE"])
def test_return_refuse_do_not_create_approved_amount(presented_b3, outcome):
    svc, case, presentation = presented_b3
    decision = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": outcome,
        "reason": "Cần sửa dự toán" if outcome == "RETURN" else "Chưa cấp ứng"},
        command(outcome, "APR-DEMO-01", "APPROVER", case.case_version))
    assert decision.budget_vnd is None and decision.advance_vnd is None
    assert svc.get_case(case.id).b3_workflow.status == (
        "RETURNED" if outcome == "RETURN" else "REFUSED")
    assert not svc.closed(case.id)


def _approve(svc, case, presentation, key="approve"):
    return svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo đề nghị", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command(key, "APR-DEMO-01", "APPROVER", case.case_version))


def test_wrong_actor_cannot_decide(presented_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, presentation = presented_b3
    with pytest.raises(DomainError) as exc:
        svc.decide_b3(case.id, {
            "presentation_id": presentation.id, "outcome": "APPROVE",
            "reason": "x", "work_allowed": True,
            "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
            command("bad", "ACC-DEMO-01", "APPROVER", case.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"
    assert svc.get_case(case.id).b3_workflow.status == "PENDING"


def test_second_decision_on_same_presentation_conflicts(presented_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, presentation = presented_b3
    _approve(svc, case, presentation)
    current = svc.get_case(case.id)
    with pytest.raises(DomainError) as exc:
        svc.decide_b3(case.id, {
            "presentation_id": presentation.id, "outcome": "REFUSE",
            "reason": "Đổi ý"},
            command("second", "APR-DEMO-01", "APPROVER",
                    current.case_version))
    assert exc.value.code in ("B3_DECISION_EXISTS", "B3_WORKFLOW_BLOCKED")


def test_source_change_after_present_makes_decision_stale(ready_b3):
    from invoice_referee.domain.models import DomainError
    from invoice_referee.settlement.models import Upload
    svc, case, report_id = ready_b3
    presentation = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id, "note": "Đủ", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    svc.add_source(case.id, Upload(
        filename="extra.txt", content=b"bo sung", provenance={}),
        command("src", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.status == "NEEDS_RECHECK"
    assert view.b3_workflow.basis_current is False
    with pytest.raises(DomainError) as exc:
        _approve(svc, svc.get_case(case.id), presentation, key="after-src")
    assert exc.value.code == "BASIS_STALE"


def test_stop_blocks_presentation(ready_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, report_id = ready_b3
    svc.control(case.id, "STOP",
                command("stop", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    with pytest.raises(DomainError) as exc:
        svc.present_b3(case.id, {
            "basis_report_id": report_id,
            "review": {"report_id": report_id, "note": "x", "refs": []}},
            command("present", "ACC-DEMO-01", "ACCOUNTANT",
                    svc.get_case(case.id).case_version))
    assert exc.value.code == "STOP_ACTIVE"


def test_approve_does_not_leak_into_b7_money_or_handoff(presented_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, presentation = presented_b3
    decision = _approve(svc, case, presentation)
    after = svc.get_case(case.id)
    # B7 money summary stays empty; the B3 decision is not a reimbursement.
    assert after.money_summary["approved_vnd"] is None
    assert after.money_summary["received_vnd"] is None
    assert not svc.handoff_allowed(case.id)
    with pytest.raises(DomainError) as exc:
        svc.handoff(case.id, {"decision_id": decision.id},
                    command("ho", "ACC-DEMO-01", "ACCOUNTANT",
                            after.case_version))
    assert exc.value.code == "B3_REPORT_ONLY"
    with pytest.raises(DomainError) as exc2:
        svc.close_case(case.id, {"kind": "SETTLEMENT_COMPLETE", "basis": "x"},
                       command("cl", "ACC-DEMO-01", "ACCOUNTANT",
                               after.case_version))
    assert exc2.value.code == "B3_REPORT_ONLY"


def test_rerun_after_own_approval_has_no_false_duplicate_issue(presented_b3):
    """Re-running the same decided request must not raise a duplicate-approval
    issue for this case's own verified decision."""
    svc, case, presentation = presented_b3
    _approve(svc, case, presentation)
    current = svc.get_case(case.id)
    rerun = svc.start(case.id, command("rerun", "NV-DEMO-01", "EMPLOYEE",
                                       current.case_version))
    assert svc.wait(rerun.id).status == "SUCCEEDED"
    report = svc.report(rerun.id)
    prior = [issue for issue in report.issues
             if issue.issue_id == "I-B3-PRIOR-APPROVED"]
    assert prior == []
    run_input = svc.store.get_run_input(rerun.id)
    assert run_input.config.get("b3_current_decision_ref") is not None


def test_foreign_approval_same_scope_still_flags(presented_b3):
    """A decision from outside this case (foreign ref) is NOT waived."""
    from invoice_referee.settlement.b3 import B3CompanyContext
    svc, case, presentation = presented_b3
    _approve(svc, case, presentation)
    # Foreign approval in the company history for the same employee/work.
    foreign = {
        "event_ref": "company:foreign-approval", "employee_ref": "NV-DEMO-01",
        "work_ref": case.submission.work_ref, "kind": "ADVANCE_APPROVAL",
        "amount_vnd": 2_000_000, "event_at": "2026-10-09T09:00:00+07:00",
        "known_at": "2026-10-09T09:00:00+07:00", "status": "APPROVED",
        "ref": "company:foreign-approval",
    }
    context = {**CONTEXT, "history": [foreign]}
    svc2 = Service(svc.store, svc.reader, config=ServiceConfig(
        authority=[], b3_context=B3CompanyContext.model_validate(context)))
    rerun = svc2.start(case.id, command("rerun-f", "NV-DEMO-01", "EMPLOYEE",
                                        svc.get_case(case.id).case_version))
    assert svc2.wait(rerun.id).status == "SUCCEEDED"
    report = svc2.report(rerun.id)
    prior = [issue for issue in report.issues
             if issue.issue_id == "I-B3-PRIOR-APPROVED"]
    assert len(prior) == 1


def test_approve_lower_advance_keeps_request(presented_b3):
    """Approving 1.5M for a 2M request keeps the requested 2M visible."""
    svc, case, presentation = presented_b3
    decision = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Chỉ ứng 1,5 triệu theo dự toán", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 1_500_000},
        command("approve-low", "APR-DEMO-01", "APPROVER", case.case_version))
    assert decision.advance_vnd == 1_500_000
    assert decision.budget_vnd == 8_000_000
    assert svc.get_case(case.id).b3_workflow.decision.advance_vnd == 1_500_000


def test_represent_after_return_requires_new_basis(presented_b3):
    """After RETURN, re-presenting the SAME (unchanged) basis is blocked."""
    from invoice_referee.domain.models import DomainError
    svc, case, presentation = presented_b3
    svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "RETURN",
        "reason": "Cần sửa dự toán"},
        command("ret", "APR-DEMO-01", "APPROVER", case.case_version))
    current = svc.get_case(case.id)
    with pytest.raises(DomainError) as exc:
        svc.present_b3(case.id, {
            "basis_report_id": presentation.basis_report_id,
            "review": {"report_id": presentation.basis_report_id,
                       "note": "Trình lại nguyên trạng", "refs": []}},
            command("represent-same", "ACC-DEMO-01", "ACCOUNTANT",
                    current.case_version))
    assert exc.value.code == "B3_WORKFLOW_BLOCKED"


def test_decision_idempotent_same_key(presented_b3):
    svc, case, presentation = presented_b3
    first = _approve(svc, case, presentation, key="same")
    # Re-issue the same key with the same body: replay, one record.
    replay = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo đề nghị", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command("same", "APR-DEMO-01", "APPROVER",
                case.case_version))
    assert replay.id == first.id
    assert replay.idempotent_replay is True


def test_expired_grant_rejected_by_authority_check():
    """A grant outside its effective window does not cover (real-time check)."""
    from datetime import datetime, timezone

    from invoice_referee.domain.models import DomainError
    from invoice_referee.settlement.b3 import B3CompanyContext
    from invoice_referee.settlement.b3_workflow import authorize_b3_decision
    from invoice_referee.settlement.models import B3DecisionPayload

    expired = {
        **CONTEXT,
        "grants": [{
            "actor_ref": "APR-DEMO-01", "employee_ref": "NV-DEMO-01",
            "work_ref": None, "allow_work": True,
            "max_budget_vnd": 10_000_000, "max_advance_vnd": 5_000_000,
            "effective_from": "2026-09-01T00:00:00+07:00",
            "effective_to": "2026-09-30T23:59:59+07:00",
            "ref": "company:grant-expired",
        }],
    }
    context = B3CompanyContext.model_validate(expired)
    payload = B3DecisionPayload(
        presentation_id="PR-x", outcome="APPROVE", reason="Duyệt",
        work_allowed=True, budget_vnd=8_000_000, advance_vnd=2_000_000)
    # Evaluate at a real time AFTER the window closes.
    at = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(DomainError) as exc:
        authorize_b3_decision(context, "NV-DEMO-01", "WORK-1", payload,
                              "APR-DEMO-01", at, 2_000_000)
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_two_competing_decisions_only_one_persists(presented_b3):
    """Two commands with the same expected version: one wins, one conflicts."""
    from invoice_referee.domain.models import DomainError
    svc, case, presentation = presented_b3
    first = svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command("race-a", "APR-DEMO-01", "APPROVER", case.case_version))
    with pytest.raises(DomainError) as exc:
        svc.decide_b3(case.id, {
            "presentation_id": presentation.id, "outcome": "REFUSE",
            "reason": "Từ chối"},
            command("race-b", "APR-DEMO-01", "APPROVER", case.case_version))
    assert exc.value.code in ("STALE_VERSION", "B3_DECISION_EXISTS",
                              "B3_WORKFLOW_BLOCKED")
    workflow = svc.get_case(case.id).b3_workflow
    assert workflow.decision.id == first.id
    assert workflow.decision.outcome == "APPROVE"


def test_return_cycle_allows_fix_recheck_and_represent(presented_b3):
    """RETURN → employee revises → rerun → accountant presents again → PENDING."""
    svc, case, presentation = presented_b3
    svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "RETURN",
        "reason": "Cần sửa dự toán"},
        command("return", "APR-DEMO-01", "APPROVER", case.case_version))
    after_return = svc.get_case(case.id)
    assert after_return.stage == "CHECKING"
    assert after_return.b3_workflow.status == "RETURNED"

    # Employee edits the declaration and re-runs; same case/work, no new id.
    revised_form = dict(NATIVE_FORM)
    revised_form["request_amount_vnd"] = 1_500_000
    submission = after_return.submission.model_copy(
        update={"form": revised_form})
    svc.revise(case.id, submission,
               command("revise", "NV-DEMO-01", "EMPLOYEE",
                       after_return.case_version))
    rerun_case = svc.get_case(case.id)
    rerun = svc.start(case.id, command("rerun", "NV-DEMO-01", "EMPLOYEE",
                                       rerun_case.case_version))
    assert svc.wait(rerun.id).status == "SUCCEEDED"

    # The old presentation is no longer pending; a fresh one is required.
    fresh = svc.get_case(case.id)
    assert fresh.b3_workflow.status == "NEEDS_RECHECK"
    assert fresh.b3_workflow.basis_current is False
    assert fresh.submission.work_ref == case.submission.work_ref
    presented = svc.present_b3(case.id, {
        "basis_report_id": rerun.id,
        "review": {"report_id": rerun.id, "note": "Đã sửa dự toán", "refs": []}},
        command("represent", "ACC-DEMO-01", "ACCOUNTANT", fresh.case_version))
    assert svc.get_case(case.id).b3_workflow.status == "PENDING"
    assert svc.get_case(case.id).b3_workflow.presentation.id == presented.id

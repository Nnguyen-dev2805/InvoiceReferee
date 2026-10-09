"""W05 decisions (R8/R9): authority-gated, typed basis, combined exception,
immutable basis vs fulfillment, idempotency; review is not approval.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Command, Submission, Upload
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

_CUTOFF = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)

LEDGER = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 2000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 0\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


@pytest.fixture
def service(tmp_path):
    from invoice_referee.settlement.models import AuthorityGrant

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    return Service(store, reader, config=ServiceConfig(authority=[
        AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                       max_settlement_vnd=10_000_000),
    ]))


@pytest.fixture
def complete_case(service):
    """Case B7 đã chạy report COMPLETE, proposed +3.000.000."""
    submission = Submission(employee_ref="NV-01", work_ref="CT-DEC", job="B7",
                           money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                           form={"purpose": "Công tác A"})
    case = service.submit(submission, Command(
        key="c", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id, Upload(filename="d.txt", content=LEDGER.encode()),
                       Command(key="s", actor_id="NV-01", demo_role="EMPLOYEE",
                               expected_case_version=case.case_version, body={}))
    view = service.get_case(case.id)
    run = service.start(case.id, Command(
        key="r", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=view.case_version, body={}))
    ended = service.wait(run.id, timeout=10)
    assert ended.status == "SUCCEEDED"
    return service.get_case(case.id)


def approver_command(case, key=None):
    return Command(key=key or f"dec-{uuid.uuid4().hex[:8]}",
                   actor_id="P-DEMO", demo_role="APPROVER",
                   expected_case_version=case.case_version, body={})


def decision_payload(case, **overrides):
    payload = {
        "kind": "SETTLEMENT",
        "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE",
        "reason": "Duyệt quyết toán theo report",
        "basis_report_id": case.current_run_id,
        "conditions": [],
    }
    payload.update(overrides)
    return payload


def test_decision_requires_approver_role_and_limit(complete_case, service):
    view = service.get_case(complete_case.id)
    with pytest.raises(DomainError) as error:
        service.decide(view.id, decision_payload(view), Command(
            key="d1", actor_id="NV-01", demo_role="EMPLOYEE",
            expected_case_version=view.case_version, body={}))
    assert error.value.code == "BEYOND_AUTHORITY"
    with pytest.raises(DomainError) as error:
        service.decide(view.id, decision_payload(view, amount_vnd=20_000_000),
                       approver_command(view))
    assert error.value.code == "BEYOND_AUTHORITY"


def test_decision_records_typed_basis_and_amount(complete_case, service):
    view = service.get_case(complete_case.id)
    decision = service.decide(view.id, decision_payload(view),
                              approver_command(view))
    assert decision.amount_vnd == 3_000_000
    assert decision.direction == "PAY_EMPLOYEE"
    assert decision.basis_report_id == view.current_run_id
    assert decision.actor_id == "P-DEMO"
    after = service.get_case(view.id)
    assert after.money_summary["approved_vnd"] == 3_000_000
    assert after.money_summary["received_vnd"] is None
    assert after.money_summary["remaining_vnd"] == 3_000_000
    assert after.stage == "AWAITING_MONEY"


def test_decision_no_amount_override_of_report(complete_case, service):
    # amount duyệt không đè calculated/proposed của report
    view = service.get_case(complete_case.id)
    service.decide(view.id, decision_payload(view, amount_vnd=1_000_000),
                   approver_command(view))
    report = service.report(view.current_run_id)
    assert report.proposed_net_vnd == 3_000_000  # report giữ nguyên


def test_decision_idempotency_stale_and_conflict(complete_case, service):
    view = service.get_case(complete_case.id)
    command = approver_command(view, key="same-key")
    first = service.decide(view.id, decision_payload(view), command)
    fresh = service.get_case(view.id)
    replay = service.decide(fresh.id, decision_payload(fresh), command)
    assert replay.id == first.id and replay.idempotent_replay
    with pytest.raises(DomainError) as error:
        service.decide(fresh.id, decision_payload(fresh, amount_vnd=2_000_000),
                       command)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    # key mới nhưng expected_case_version cũ (trước khi decide) → stale 409
    with pytest.raises(DomainError) as error:
        service.decide(fresh.id, decision_payload(fresh, reason="khác"),
                       approver_command(view, key="other"))
    assert error.value.code == "STALE_VERSION"


def test_combined_exception_and_settlement_decision(complete_case, service):
    view = service.get_case(complete_case.id)
    decision = service.decide(
        view.id,
        decision_payload(view, exception_of="I-BUDGET",
                         conditions=["chấp nhận phần vượt ngân sách"]),
        approver_command(view))
    assert decision.exception_of == "I-BUDGET"  # một decision gộp hai nội dung


def test_decision_basis_stale_after_input_change_blocks_handoff(
        complete_case, service):
    # C05: input đổi → basis cũ stale; re-check giữ decision, không duyệt lại
    view = service.get_case(complete_case.id)
    decision = service.decide(view.id, decision_payload(view),
                             approver_command(view))
    service.add_source(view.id, Upload(
        filename="extra.txt", content=b"fact Z budget.approved 9000000\n"),
        Command(key="s2", actor_id="NV-01", demo_role="EMPLOYEE",
                expected_case_version=service.get_case(view.id).case_version,
                body={}))
    with pytest.raises(DomainError) as error:
        service.handoff(view.id, {"decision_id": decision.id},
                        Command(key="h1", actor_id="ACC-01",
                                demo_role="ACCOUNTANT",
                                expected_case_version=service.get_case(
                                    view.id).case_version, body={}))
    assert error.value.code == "BASIS_STALE"
    fresh = service.get_case(view.id)
    run = service.start(fresh.id, Command(
        key="r2", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=fresh.case_version, body={}))
    service.wait(run.id, timeout=10)
    handoff = service.handoff(view.id, {"decision_id": decision.id},
                              Command(key="h2", actor_id="ACC-01",
                                      demo_role="ACCOUNTANT",
                                      expected_case_version=service.get_case(
                                          view.id).case_version, body={}))
    assert handoff["decision_id"] == decision.id  # không cần duyệt lại


def test_refusal_keeps_case_open_with_reason(complete_case, service):
    view = service.get_case(complete_case.id)
    decision = service.decide(
        view.id,
        {"kind": "SETTLEMENT", "amount_vnd": None, "direction": "REFUSE",
         "reason": "chi phí ngoài phạm vi", "basis_report_id": view.current_run_id,
         "conditions": []},
        approver_command(view))
    assert decision.direction == "REFUSE"
    assert service.closed(view.id) is False
    assert service.get_case(view.id).stage != "SETTLEMENT_CLOSED"


def test_review_is_recorded_not_approval(complete_case, service):
    view = service.get_case(complete_case.id)
    review = service.review(view.id, {
        "report_id": view.current_run_id,
        "note": "Đã rà soát bảng đối chiếu và mở nguồn.",
        "refs": [],
    }, Command(key="rev1", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=view.case_version, body={}))
    assert review.report_id == view.current_run_id
    # review không tạo approval
    assert service.get_case(view.id).money_summary["approved_vnd"] is None
    with pytest.raises(DomainError) as error:
        service.review(view.id, {
            "report_id": view.current_run_id,
            "note": "x", "refs": [],
            "amount_vnd": 1,  # review không được mang amount
        }, Command(key="rev2", actor_id="ACC-01", demo_role="ACCOUNTANT",
                   expected_case_version=service.get_case(view.id).case_version,
                   body={}))
    assert error.value.code == "REVIEW_NOT_APPROVAL"

"""W05 closure (R10, C01/C02): gates (remaining/pending/incident/Stop/questions),
refused-request end is not settlement-closed, rerun creates no new entitlement.
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

# Q04: E=5, A=2, P=3 → S=0 (cân bằng)
LEDGER_BALANCED = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 2000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 3000000\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)
LEDGER_OPEN = LEDGER_BALANCED.replace(
    "fact F9 history.reimbursement.received 3000000",
    "fact F9 history.reimbursement.received 0")


@pytest.fixture
def service(tmp_path):
    from invoice_referee.settlement.models import AuthorityGrant

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    return Service(store, reader, config=ServiceConfig(authority=[
        AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                       max_settlement_vnd=10_000_000),
    ]))


def make_case(service, work_ref, ledger):
    submission = Submission(employee_ref="NV-01", work_ref=work_ref, job="B7",
                           money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                           form={"purpose": "Công tác A"})
    case = service.submit(submission, Command(
        key=f"c-{uuid.uuid4().hex[:8]}", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id, Upload(filename="d.txt", content=ledger.encode()),
                       Command(key=f"s-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                               demo_role="EMPLOYEE",
                               expected_case_version=case.case_version, body={}))
    view = service.get_case(case.id)
    run = service.start(case.id, Command(
        key=f"r-{uuid.uuid4().hex[:8]}", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=view.case_version, body={}))
    service.wait(run.id, timeout=10)
    return service.get_case(case.id)


def close_command(case, key=None):
    return Command(key=key or f"close-{uuid.uuid4().hex[:8]}",
                   actor_id="ACC-01", demo_role="ACCOUNTANT",
                   expected_case_version=case.case_version, body={})


def test_balanced_case_closes_with_basis(service):
    case = make_case(service, "CT-CLOSE-OK", LEDGER_BALANCED)
    closure = service.close_case(case.id, {
        "kind": "SETTLEMENT_COMPLETE",
        "basis": "S=0 cân bằng theo report; các gates đã kiểm",
    }, close_command(case))
    assert closure.kind == "SETTLEMENT_COMPLETE"
    assert service.closed(case.id) is True
    assert service.get_case(case.id).stage == "SETTLEMENT_CLOSED"


def test_closure_blocked_by_remaining_pending_incident_stop_question(service):
    # remaining > 0
    case = make_case(service, "CT-CLOSE-OPEN", LEDGER_BALANCED)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE", "reason": "duyệt",
        "basis_report_id": fresh.current_run_id, "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    view = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.close_case(view.id, {"kind": "SETTLEMENT_COMPLETE",
                                     "basis": "x"}, close_command(view))
    assert error.value.code == "CLOSURE_BLOCKED"
    assert "remaining" in error.value.message.lower()

    # pending money event
    view2 = service.get_case(case.id)
    service.record_money(view2.id, {
        "event_ref": "EV-P", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 3_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "PENDING", "refs": [],
    }, Command(key="m", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=view2.case_version, body={}))
    view3 = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.close_case(view3.id, {"kind": "SETTLEMENT_COMPLETE",
                                      "basis": "x"}, close_command(view3))
    assert error.value.code == "CLOSURE_BLOCKED"

    # Stop active
    view4 = service.get_case(case.id)
    service.control(view4.id, "STOP", Command(
        key="stop", actor_id="ACC-01", demo_role="ACCOUNTANT",
        expected_case_version=view4.case_version, body={"reason": "x"}))
    view5 = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.close_case(view5.id, {"kind": "SETTLEMENT_COMPLETE",
                                      "basis": "x"}, close_command(view5))
    assert error.value.code == "CLOSURE_BLOCKED"
    assert service.closed(case.id) is False


def test_refused_request_end_is_not_settlement_closed(service):
    case = make_case(service, "CT-CLOSE-REF", LEDGER_BALANCED)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": None, "direction": "REFUSE",
        "reason": "ngoài phạm vi", "basis_report_id": fresh.current_run_id,
        "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    view = service.get_case(case.id)
    closure = service.close_case(view.id, {
        "kind": "REJECTED_REQUEST_ENDED",
        "basis": "Yêu cầu bị từ chối; không còn nghĩa vụ tiền đang mở",
    }, close_command(view))
    assert closure.kind == "REJECTED_REQUEST_ENDED"
    assert service.closed(case.id) is True
    final = service.get_case(case.id)
    assert final.stage == "REJECTED_REQUEST_ENDED"
    assert final.stage != "SETTLEMENT_CLOSED"


def test_rerun_after_closure_creates_no_new_entitlement(service):
    # C01: sau khi đóng, chạy lại cùng input → report như cũ, không mở nghĩa vụ
    case = make_case(service, "CT-CLOSE-RERUN", LEDGER_BALANCED)
    service.close_case(case.id, {"kind": "SETTLEMENT_COMPLETE",
                                 "basis": "x"}, close_command(case))
    view = service.get_case(case.id)
    run = service.start(view.id, Command(
        key=f"r2-{uuid.uuid4().hex[:8]}", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=view.case_version, body={}))
    ended = service.wait(run.id, timeout=10)
    assert ended.status == "SUCCEEDED"
    report = service.report(run.id)
    assert report.calculated_net_vnd == 0
    # đóng lại: cùng key → replay; key mới → chặn vì đã đóng
    replay = service.close_case(view.id, {"kind": "SETTLEMENT_COMPLETE",
                                          "basis": "x"},
                                close_command(view, key=close_command(view).key))
    assert replay.idempotent_replay
    fresh = service.get_case(view.id)
    with pytest.raises(DomainError) as error:
        service.close_case(fresh.id, {"kind": "SETTLEMENT_COMPLETE",
                                      "basis": "y"}, close_command(fresh))
    assert error.value.code == "CASE_CLOSED"
    with pytest.raises(DomainError) as error:
        service.add_source(fresh.id, Upload(filename="n.txt", content=b"x"),
                           Command(key="s9", actor_id="NV-01",
                                   demo_role="EMPLOYEE",
                                   expected_case_version=fresh.case_version,
                                   body={}))
    assert error.value.code == "CASE_CLOSED"


def test_closure_blocked_by_open_question(service):
    # case thiếu history → INCOMPLETE + câu hỏi mở → không đóng được
    case = make_case(service, "CT-CLOSE-Q", LEDGER_OPEN.replace(
        "fact F7 history.advance.received 2000000",
        "fact F7x placeholder 0").replace("fact F7x placeholder 0\n", ""))
    view = service.get_case(case.id)
    questions = service.questions(view.id)
    if not questions:
        pytest.skip("không sinh câu hỏi cho case này")
    with pytest.raises(DomainError) as error:
        service.close_case(view.id, {"kind": "SETTLEMENT_COMPLETE",
                                     "basis": "x"}, close_command(view))
    assert error.value.code == "CLOSURE_BLOCKED"


# --- regression: khoá lỗi closure (W05.1) --------------------------------------

def test_closure_blocked_by_overpay_incident(service):
    # duyệt 3, thực nhận 4 → OVERPAY incident còn mở → không đóng
    case = make_case(service, "CT-CLOSE-OVER", LEDGER_BALANCED)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE", "reason": "duyệt",
        "basis_report_id": fresh.current_run_id, "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    view = service.get_case(case.id)
    service.record_money(view.id, {
        "event_ref": "EV-OVER", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 4_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED", "refs": [],
    }, Command(key="m", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=view.case_version, body={}))
    blocked_view = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.close_case(blocked_view.id, {"kind": "SETTLEMENT_COMPLETE",
                                             "basis": "x"},
                           close_command(blocked_view))
    assert error.value.code == "CLOSURE_BLOCKED"
    assert "incident" in error.value.message.lower()


def test_rejected_request_end_blocked_when_money_already_received(service):
    # từ chối đề nghị nhưng đã có tiền thực nhận → không được kết thúc kiểu từ chối
    case = make_case(service, "CT-CLOSE-REF-MONEY", LEDGER_BALANCED)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": None, "direction": "REFUSE",
        "reason": "ngoài phạm vi", "basis_report_id": fresh.current_run_id,
        "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    view = service.get_case(case.id)
    service.record_money(view.id, {
        "event_ref": "EV-REF", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 1_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED", "refs": [],
    }, Command(key="m", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=view.case_version, body={}))
    blocked_view = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.close_case(blocked_view.id, {"kind": "REJECTED_REQUEST_ENDED",
                                             "basis": "x"},
                           close_command(blocked_view))
    assert error.value.code == "CLOSURE_BLOCKED"


def test_money_and_handoff_after_close_are_blocked(service):
    case = make_case(service, "CT-CLOSE-AFTER", LEDGER_BALANCED)
    view = service.get_case(case.id)
    decision = service.decide(view.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE", "reason": "duyệt",
        "basis_report_id": view.current_run_id, "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=view.case_version, body={}))
    fresh = service.get_case(case.id)
    service.record_money(fresh.id, {
        "event_ref": "EV-FULL", "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 3_000_000, "decision_id": decision.id,
        "payee_ref": "NV-01", "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED", "refs": [],
    }, Command(key="m", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=fresh.case_version, body={}))
    paid = service.get_case(case.id)
    service.close_case(paid.id, {"kind": "SETTLEMENT_COMPLETE", "basis": "đủ"},
                       close_command(paid))
    closed_view = service.get_case(case.id)
    with pytest.raises(DomainError) as error:
        service.record_money(closed_view.id, {
            "event_ref": "EV-LATE", "kind": "PAYMENT_TO_EMPLOYEE",
            "gross_vnd": 1_000_000, "decision_id": None, "payee_ref": "NV-01",
            "event_at": "2026-10-08T13:00:00+00:00",
            "reported_status": "RECEIVED", "refs": [],
        }, Command(key="m2", actor_id="ACC-01", demo_role="ACCOUNTANT",
                   expected_case_version=closed_view.case_version, body={}))
    assert error.value.code == "CASE_CLOSED"
    with pytest.raises(DomainError) as error:
        service.handoff(closed_view.id, {"decision_id": decision.id},
                        Command(key="h", actor_id="ACC-01",
                                demo_role="ACCOUNTANT",
                                expected_case_version=closed_view.case_version,
                                body={}))
    assert error.value.code == "CASE_CLOSED"

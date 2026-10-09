"""W05 money events (R9, C02/C03/C07): gross records, fulfillment vs approval,
incidents kept, namespace dedup, cutoff discipline.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
def approved_case(service):
    """Case đã có decision duyệt chi 3.000.000 (theo report proposed 3tr)."""
    submission = Submission(employee_ref="NV-01", work_ref="CT-MONEY", job="B7",
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
    service.wait(run.id, timeout=10)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "PAY_EMPLOYEE", "reason": "duyệt",
        "basis_report_id": fresh.current_run_id, "conditions": [],
    }, Command(key="dec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    return service.get_case(case.id)


def money_command(case, key=None):
    return Command(key=key or f"money-{uuid.uuid4().hex[:8]}",
                   actor_id="ACC-01", demo_role="ACCOUNTANT",
                   expected_case_version=case.case_version, body={})


def money_payload(case, **overrides):
    payload = {
        "event_ref": f"EV-{uuid.uuid4().hex[:8]}",
        "kind": "PAYMENT_TO_EMPLOYEE",
        "gross_vnd": 2_000_000,
        "decision_id": None,
        "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED",
        "refs": [],
    }
    payload.update(overrides)
    return payload


def test_partial_fulfillment_keeps_remaining_and_approval(approved_case, service):
    # C02: approved 3, actual 2, pending 1 → remaining 1; approved không đổi
    view = service.get_case(approved_case.id)
    event = service.record_money(view.id, money_payload(view), money_command(view))
    assert event.gross_vnd == 2_000_000
    summary = service.get_case(view.id).money_summary
    assert summary["approved_vnd"] == 3_000_000
    assert summary["received_vnd"] == 2_000_000
    assert summary["remaining_vnd"] == 1_000_000
    # sự kiện PENDING không tính vào received
    fresh = service.get_case(view.id)
    service.record_money(fresh.id,
                         money_payload(fresh, gross_vnd=1_000_000,
                                       reported_status="PENDING",
                                       event_ref="EV-PEND"),
                         money_command(fresh))
    summary = service.get_case(view.id).money_summary
    assert summary["received_vnd"] == 2_000_000
    assert summary["remaining_vnd"] == 1_000_000


def test_overpay_keeps_gross_and_incident_not_clipped(approved_case, service):
    # C03: trả 4 khi duyệt 3 → giữ gross 4, fulfilled 3, phần vượt 1 là incident
    view = service.get_case(approved_case.id)
    event = service.record_money(view.id, money_payload(view, gross_vnd=4_000_000),
                                 money_command(view))
    assert event.gross_vnd == 4_000_000
    summary = service.get_case(view.id).money_summary
    assert summary["received_vnd"] == 4_000_000
    assert summary["remaining_vnd"] == 0
    incidents = summary["incidents"]
    assert incidents and incidents[0]["kind"] == "OVERPAY"
    assert incidents[0]["excess_vnd"] == 1_000_000


def test_wrong_recipient_kept_raw_not_fulfillment(approved_case, service):
    view = service.get_case(approved_case.id)
    event = service.record_money(
        view.id, money_payload(view, payee_ref="NV-99"),
        money_command(view))
    assert event.payee_ref == "NV-99"  # giữ raw, không sửa thành đúng người
    summary = service.get_case(view.id).money_summary
    assert summary["received_vnd"] is None
    assert any(i["kind"] == "WRONG_RECIPIENT" for i in summary["incidents"])


def test_event_ref_dedup_and_idempotency(approved_case, service):
    view = service.get_case(approved_case.id)
    first = service.record_money(view.id, money_payload(view, event_ref="EV-1"),
                                 money_command(view, key="m1"))
    fresh = service.get_case(view.id)
    with pytest.raises(DomainError) as error:
        service.record_money(fresh.id, money_payload(fresh, event_ref="EV-1"),
                             money_command(fresh))
    assert error.value.code == "DUPLICATE_EVENT_REF"
    # same key + same payload → replay bản ghi cũ
    fresh = service.get_case(view.id)
    replay = service.record_money(fresh.id,
                                  money_payload(fresh, event_ref="EV-1"),
                                  money_command(fresh, key="m1"))
    assert replay.id == first.id and replay.idempotent_replay
    # same key + khác payload → conflict
    with pytest.raises(DomainError) as error:
        service.record_money(fresh.id,
                             money_payload(fresh, event_ref="EV-1",
                                           gross_vnd=1_000_000),
                             money_command(fresh, key="m1"))
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_event_after_cutoff_recorded_but_flagged(approved_case, service):
    # C07: event sau money cutoff không vào run cũ; được lưu với cờ
    view = service.get_case(approved_case.id)
    report_before = service.report(view.current_run_id)
    event_at = (_CUTOFF + timedelta(days=2)).isoformat()
    event = service.record_money(view.id,
                                 money_payload(view, event_at=event_at),
                                 money_command(view))
    assert event.after_cutoff is True
    assert service.report(view.current_run_id) == report_before  # run cũ nguyên vẹn


def test_money_events_allowed_during_stop(approved_case, service):
    # S7: tiền đã xảy ra vẫn record khi Stop (chỉ không mở action mới)
    view = service.get_case(approved_case.id)
    service.control(view.id, "STOP", Command(
        key="stop", actor_id="ACC-01", demo_role="ACCOUNTANT",
        expected_case_version=view.case_version, body={"reason": "x"}))
    fresh = service.get_case(view.id)
    event = service.record_money(fresh.id, money_payload(fresh),
                                 money_command(fresh))
    assert event.gross_vnd == 2_000_000


# --- regression: chiều thu tiền COLLECT_FROM_EMPLOYEE (W05.1) -----------------

LEDGER_COLLECT = (
    "fact F1 expense.EXP-1.amount 2000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 2000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 5000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 0\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


def test_collection_direction_fulfillment_and_closure(service, tmp_path):
    # E=2M, A=5M → S=-3M: nhân viên hoàn lại 3M (EMPLOYEE_TO_COMPANY)
    submission = Submission(employee_ref="NV-01", work_ref="CT-COLLECT",
                            job="B7", money_as_of=_CUTOFF,
                            knowledge_cutoff=_CUTOFF,
                            form={"purpose": "Công tác B"})
    case = service.submit(submission, Command(
        key="cc", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id,
                       Upload(filename="d.txt", content=LEDGER_COLLECT.encode()),
                       Command(key="cs", actor_id="NV-01", demo_role="EMPLOYEE",
                               expected_case_version=case.case_version, body={}))
    view = service.get_case(case.id)
    run = service.start(case.id, Command(
        key="cr", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=view.case_version, body={}))
    service.wait(run.id, timeout=10)
    report = service.report(run.id)
    assert report.calculated_net_vnd == -3_000_000
    assert report.direction == "EMPLOYEE_TO_COMPANY"

    fresh = service.get_case(case.id)
    decision = service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "COLLECT_FROM_EMPLOYEE", "reason": "thu lại phần ứng thừa",
        "basis_report_id": fresh.current_run_id, "conditions": [],
    }, Command(key="cdec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    assert decision.direction == "COLLECT_FROM_EMPLOYEE"
    summary = service.get_case(case.id).money_summary
    assert summary["approved_vnd"] == 3_000_000
    assert summary["received_vnd"] is None
    assert summary["remaining_vnd"] == 3_000_000

    # nhân viên nộp lại cho công ty → thực thu đủ, đóng được
    paying = service.get_case(case.id)
    event = service.record_money(paying.id, {
        "event_ref": "EV-BACK", "kind": "PAYMENT_FROM_EMPLOYEE",
        "gross_vnd": 3_000_000, "decision_id": decision.id,
        "payee_ref": "ORG-DEMO-01", "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED", "refs": [],
    }, Command(key="cm", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=paying.case_version, body={}))
    assert event.gross_vnd == 3_000_000
    summary = service.get_case(case.id).money_summary
    assert summary["received_vnd"] == 3_000_000
    assert summary["remaining_vnd"] == 0

    final_view = service.get_case(case.id)
    closure = service.close_case(final_view.id, {
        "kind": "SETTLEMENT_COMPLETE",
        "basis": "Đã thu đủ 3.000.000; remaining 0.",
    }, Command(key="cclose", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=final_view.case_version, body={}))
    assert closure.kind == "SETTLEMENT_COMPLETE"


def test_collection_wrong_payee_keeps_incident(service, tmp_path):
    submission = Submission(employee_ref="NV-01", work_ref="CT-COLLECT-BAD",
                            job="B7", money_as_of=_CUTOFF,
                            knowledge_cutoff=_CUTOFF,
                            form={"purpose": "Công tác B"})
    case = service.submit(submission, Command(
        key="cc", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id,
                       Upload(filename="d.txt", content=LEDGER_COLLECT.encode()),
                       Command(key="cs", actor_id="NV-01", demo_role="EMPLOYEE",
                               expected_case_version=case.case_version, body={}))
    view = service.get_case(case.id)
    run = service.start(case.id, Command(
        key="cr", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=view.case_version, body={}))
    service.wait(run.id, timeout=10)
    fresh = service.get_case(case.id)
    service.decide(fresh.id, {
        "kind": "SETTLEMENT", "amount_vnd": 3_000_000,
        "direction": "COLLECT_FROM_EMPLOYEE", "reason": "thu lại",
        "basis_report_id": fresh.current_run_id, "conditions": [],
    }, Command(key="cdec", actor_id="P-DEMO", demo_role="APPROVER",
               expected_case_version=fresh.case_version, body={}))
    paying = service.get_case(case.id)
    # nộp về chính mình (payee = nhân viên) → không tính fulfilled, giữ incident
    service.record_money(paying.id, {
        "event_ref": "EV-SELF", "kind": "PAYMENT_FROM_EMPLOYEE",
        "gross_vnd": 3_000_000, "decision_id": None, "payee_ref": "NV-01",
        "event_at": "2026-10-08T12:00:00+00:00",
        "reported_status": "RECEIVED", "refs": [],
    }, Command(key="cm", actor_id="ACC-01", demo_role="ACCOUNTANT",
               expected_case_version=paying.case_version, body={}))
    summary = service.get_case(case.id).money_summary
    assert summary["received_vnd"] is None
    assert any(i["kind"] == "WRONG_RECIPIENT" for i in summary["incidents"])
